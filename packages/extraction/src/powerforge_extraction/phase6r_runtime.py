"""Build requests from exact source artifacts and persist immutable stage results."""

import json
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_ai.extraction import ExecutionUsage, ExtractionRequest, ExtractionResponse
from powerforge_extraction.enriched_planning import metadata
from powerforge_extraction.enriched_sources import bound_snapshot, load_bound
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.phase6r_contracts import (
    VERSION,
    AttributeRequest,
    AttributeResponse,
    NoEligibleAttributes,
    PinnedPageContext,
    ReadingCitation,
    ReadingText,
    RecognitionRequest,
    RecognitionResponse,
    VisualCitation,
    attribute_catalog,
    contract_hash,
    equipment_catalog,
    validate_request,
)
from powerforge_extraction.phase6r_profile import PROMPTS, RESPONSES, STAGES
from powerforge_persistence.base import Base
from powerforge_provenance.spatial_sources import PageOwner


class StageResult(Base):
    __tablename__ = "extraction_stage_results"

    work_unit_id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID]
    document_page_id: Mapped[UUID]
    stage: Mapped[str]
    outcome: Mapped[Literal["RESULT", "NO_ELIGIBLE_ATTRIBUTES"]]
    page_context_hash: Mapped[str]
    upstream_work_unit_id: Mapped[UUID | None]
    upstream_hash: Mapped[str | None]
    request_hash: Mapped[str]
    result_hash: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    diagnostics: Mapped[list[dict]] = mapped_column(JSONB)


def prerequisite_result(session, unit):
    if unit.stage == STAGES[0]:
        return None
    return session.scalar(
        select(StageResult)
        .join(ExtractionWorkUnit, ExtractionWorkUnit.id == StageResult.work_unit_id)
        .where(
            StageResult.run_id == unit.run_id,
            StageResult.document_page_id == UUID(unit.execution_metadata["source_page_id"]),
            StageResult.stage == STAGES[0],
            StageResult.outcome == "RESULT",
            ExtractionWorkUnit.unit_key == unit.execution_metadata["prerequisite_key"],
            ExtractionWorkUnit.status == "COMPLETED",
        )
    )


def recognition_result(row):
    result = RecognitionResponse.model_validate_json(canonical_json(row.payload))
    if (
        contract_hash(result) != row.result_hash
        or result.page_context_hash != row.page_context_hash
    ):
        raise ValueError("Stored prerequisite identity differs")
    return result


def validate_plan(session, unit, profile):
    from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding

    snapshot = bound_snapshot(session, unit)
    owner = snapshot.layout.owner
    binding = session.scalar(
        select(RunSourceEnrichmentBinding).where(
            RunSourceEnrichmentBinding.run_id == unit.run_id,
            RunSourceEnrichmentBinding.document_page_id == owner.document_page_id,
        )
    )
    if (
        binding is None
        or snapshot.layout.algorithm_sha256 != profile.source_rules
        or unit.stage not in STAGES
        or metadata(profile, unit.stage, owner.page_number, binding) != unit.execution_metadata
    ):
        raise ValueError("Unit differs from its pinned Phase 6R plan")
    return snapshot


def project_page(source):
    from powerforge_provenance.spatial_layout import SourceSupport

    # The loader verifies the representation bodies against the exact pinned bytes.
    text = {
        SourceSupport(representation_ref=alias, kind="TOKEN", ref=token.ref): token.raw_text
        for alias, body in source.bodies.items()
        for token in body.tokens
    }
    snapshot = source.snapshot
    return PinnedPageContext(
        owner=source.layout.owner,
        source_sha256=source.prepared.original.sha256,
        page_image_id=snapshot.image.id,
        image_sha256=snapshot.image.sha256,
        image_bytes=snapshot.image.size_bytes,
        image_width=snapshot.image.width_px,
        image_height=snapshot.image.height_px,
        preparation_sha256=source.prepared.identity_hash,
        layout_sha256=source.layout.identity_hash,
        layout=source.layout,
        readings=tuple(
            ReadingText(
                reading_ref=reading.ref,
                text=text[reading.preferred],
                modality=source.bodies[reading.preferred.representation_ref].producer.kind,
                alternate_texts=tuple(
                    text[member] for member in reading.members if member != reading.preferred
                ),
            )
            for reading in source.layout.readings
        ),
    )


def request_for(factory, storage, claim):
    profile = claim.profile
    with factory() as session:
        unit = session.get(ExtractionWorkUnit, claim.unit_id)
        snapshot = validate_plan(session, unit, profile)
        parent = prerequisite_result(session, unit)
        owner = PageOwner(
            document_id=unit.document_id,
            document_page_id=UUID(unit.execution_metadata["source_page_id"]),
            processing_run_id=unit.processing_run_id,
            page_number=unit.page_numbers[0],
        )
    source = load_bound(snapshot, storage, unit, profile)
    page = project_page(source)
    context_hash = contract_hash(page)
    if page.owner != owner:
        raise ValueError("Source page differs from the authorized binding")
    common = dict(
        version=VERSION,
        stage=unit.stage,
        page=page,
        page_context_hash=context_hash,
        registry_version=profile.manifest["registry_version"],
    )
    if unit.stage == STAGES[0]:
        wire = RecognitionRequest(
            **common,
            description_version=profile.manifest["descriptions"],
            equipment_catalog=equipment_catalog(),
        )
    else:
        if parent is None or parent.page_context_hash != context_hash:
            raise ValueError("Attribute stage requires exact successful recognition")
        upstream = recognition_result(parent)
        definitions = attribute_catalog(upstream)
        if not definitions:
            skip = NoEligibleAttributes(
                version=VERSION,
                stage=unit.stage,
                outcome="NO_ELIGIBLE_ATTRIBUTES",
                page_context_hash=context_hash,
                upstream_hash=parent.result_hash,
                provider_calls=0,
            )
            return skip, None
        wire = AttributeRequest(
            **common,
            upstream=upstream,
            upstream_hash=parent.result_hash,
            attribute_catalog=definitions,
        )
    validate_request(wire, expected_owner=owner)
    payload = canonical_json(wire.model_dump(mode="json"))
    request = ExtractionRequest(
        work_unit_id=claim.unit_id,
        unit_key=claim.unit_key,
        attempt_number=claim.attempt_number,
        model=profile.model,
        instructions=PROMPTS[unit.stage],
        schema_version=VERSION,
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        text=payload,
        image=source.image,
        image_mime_type="image/png",
        image_detail="high",
        stage=unit.stage,
        response_model=RESPONSES[unit.stage],
    )

    # Bound the actual encoded text and image envelope, including JSON escaping.
    envelope = {
        "instructions": request.instructions,
        "input": [
            {"type": "input_text", "text": request.text},
            {"type": "input_image", "image_url": "data:image/png;base64,", "detail": "high"},
        ],
    }
    encoded_size = len(canonical_json(envelope).encode()) + 4 * ((len(source.image) + 2) // 3)
    if encoded_size > profile.max_transport_bytes:
        raise ValueError("Phase 6R encoded input exceeds its transport budget")
    return wire, request


def stage_diagnostics(wire, result):
    """Keep invalid proposals and citations inspectable without establishing links."""
    diagnostics = []
    if isinstance(result, NoEligibleAttributes):
        return diagnostics
    readings = {reading.reading_ref: reading for reading in wire.page.readings}
    if isinstance(result, AttributeResponse):
        owners = {item.local_ref: item for item in wire.upstream.equipment}
        definitions = {(item.equipment_type, item.key): item for item in wire.attribute_catalog}
        from powerforge_extraction.phase6r_contracts import RegistryAssertion

        for item in (*result.attributes, *result.raw_unmapped):
            owner = owners.get(item.equipment_ref)
            if (
                item.association == "UNASSIGNED"
                and item.equipment_ref is not None
                or item.association != "UNASSIGNED"
                and owner is None
                or owner is not None
                and owner.qualification == "LEGEND_ONLY"
            ):
                diagnostics.append({"ref": item.local_ref, "code": "INVALID_OWNER_REFERENCE"})
            if isinstance(item, RegistryAssertion):
                definition = (
                    definitions.get((owner.registry_type, item.attribute_key)) if owner else None
                )
                if definition is None and owner is not None:
                    diagnostics.append({"ref": item.local_ref, "code": "UNSUPPORTED_ATTRIBUTE_KEY"})
                elif (
                    definition is not None
                    and item.proposed_enum_value is not None
                    and (
                        definition.value_type != "ENUM"
                        or item.proposed_enum_value not in definition.allowed_values
                    )
                ):
                    diagnostics.append({"ref": item.local_ref, "code": "INVALID_ENUM_PROPOSAL"})
        observations = (*result.attributes, *result.raw_unmapped)
    else:
        observations = result.equipment
    for item in observations:
        for index, citation in enumerate(item.evidence):
            code = None
            if isinstance(citation, ReadingCitation):
                reading = readings.get(citation.reading_ref)
                if reading is None:
                    code = "UNKNOWN_READING_REFERENCE"
                elif citation.quote is not None and not any(
                    citation.quote in value for value in (reading.text, *reading.alternate_texts)
                ):
                    code = "READING_QUOTE_MISMATCH"
            elif isinstance(citation, VisualCitation):
                box = citation.region
                if (
                    box.x < 0
                    or box.y < 0
                    or box.width <= 0
                    or box.height <= 0
                    or box.x + box.width > 1
                    or box.y + box.height > 1
                ):
                    code = "INVALID_VISUAL_BOUNDS"
            if code:
                diagnostics.append({"ref": item.local_ref, "citation": index, "code": code})
    if len(diagnostics) > 128:
        return [*diagnostics[:127], {"code": "DIAGNOSTIC_LIMIT", "omitted": len(diagnostics) - 127}]
    return diagnostics


def store_result(session, unit, wire, result):
    parent = prerequisite_result(session, unit)
    skip = isinstance(result, NoEligibleAttributes)
    if result.stage != unit.stage or result.page_context_hash != wire.page_context_hash:
        raise ValueError("Result differs from the pinned request")
    if unit.stage == STAGES[1] and (
        parent is None
        or parent.result_hash != result.upstream_hash
        or parent.page_context_hash != result.page_context_hash
        or skip != (not attribute_catalog(recognition_result(parent)))
    ):
        raise ValueError("Result differs from its committed recognition prerequisite")
    session.add(
        StageResult(
            work_unit_id=unit.id,
            run_id=unit.run_id,
            document_page_id=UUID(unit.execution_metadata["source_page_id"]),
            stage=unit.stage,
            outcome="NO_ELIGIBLE_ATTRIBUTES" if skip else "RESULT",
            page_context_hash=result.page_context_hash,
            upstream_work_unit_id=parent.work_unit_id if parent else None,
            upstream_hash=parent.result_hash if parent else None,
            request_hash=contract_hash(wire),
            result_hash=contract_hash(result),
            payload=result.model_dump(mode="json"),
            diagnostics=stage_diagnostics(wire, result),
        )
    )
    session.flush()


class FakePhase6RProvider:
    def __init__(self, scenario):
        self.scenario = scenario

    def execute(self, request):
        from powerforge_ai.extraction import ErrorCode, ProviderFailure

        if self.scenario in {"transient", "interrupted"} and request.attempt_number == 1:
            raise ProviderFailure(ErrorCode.UNAVAILABLE)
        if self.scenario in {"invalid", "permanent"}:
            raise ProviderFailure(ErrorCode.INVALID)
        payload = {
            "version": VERSION,
            "stage": request.stage,
        }
        wire = json.loads(request.text)
        payload["page_context_hash"] = wire["page_context_hash"]
        if request.stage == STAGES[0]:
            payload["equipment"] = (
                [
                    dict(
                        local_ref="equipment-1",
                        source_description="Synthetic equipment",
                        registry_type="TWO_WINDING_TRANSFORMER",
                        tag_state="ABSENT",
                        tag=None,
                        qualification="UNKNOWN",
                        raw_qualification=None,
                        evidence=[],
                    )
                ]
                if self.scenario != "empty"
                else []
            )
        else:
            payload.update(upstream_hash=wire["upstream_hash"], attributes=[], raw_unmapped=[])
        return ExtractionResponse[request.response_model](
            result=request.response_model.model_validate_json(canonical_json(payload)),
            usage=ExecutionUsage(),
        )
