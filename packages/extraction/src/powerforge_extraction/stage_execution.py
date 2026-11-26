"""Build requests from exact source artifacts and persist immutable stage results."""

from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_ai.extraction import (
    AttributeOutput,
    ErrorCode,
    ExecutionUsage,
    ExtractionRequest,
    ProviderFailure,
    RecognitionOutput,
)
from powerforge_extraction.compact_context import compact_page
from powerforge_extraction.controls import UnitExecution
from powerforge_extraction.extraction_profile import (
    BODY_DIGEST_VERSION,
    STAGES,
    stage_request_hash,
)
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.performance import active_performance, measure
from powerforge_extraction.pinned_sources import bound_snapshot, load_bound
from powerforge_extraction.provider_body import dispatch_hash, encoded_body, responses_body
from powerforge_extraction.readable_context import readable_page
from powerforge_extraction.run_planning import metadata
from powerforge_extraction.stage_contracts import (
    ATTRIBUTE_INPUT_VERSION,
    ATTRIBUTE_NOTES_VERSION,
    ATTRIBUTE_VERSION,
    LEGACY_ATTRIBUTE_INPUT_VERSION,
    AttributeRequest,
    NoEligibleAttributes,
    PinnedPageContext,
    ReadingText,
    RecognitionRequest,
    RecognitionResponse,
    attribute_catalog,
    consolidated_catalog,
    contract_hash,
    equipment_catalog,
    stage_schema_version,
    validate_request,
)
from powerforge_persistence.base import Base
from powerforge_provenance.spatial_sources import PageOwner
from powerforge_shared.config import EXPERIMENTAL_INPUTS


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
        raise ValueError("Unit differs from its pinned extraction plan")
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


def provider_input(wire: RecognitionRequest | AttributeRequest | NoEligibleAttributes) -> dict:
    """Serialize the provider view of a validated request."""
    if isinstance(wire, AttributeRequest) and wire.input_version in EXPERIMENTAL_INPUTS:
        result = wire.model_dump(mode="json", include={"upstream", "attribute_catalog"})
        del result["upstream"]["page_context_hash"]
        result["input_version"] = wire.input_version
        if wire.input_version != "image-only-v1":
            result["page"] = readable_page(wire.page)
        if wire.attribute_description_version == ATTRIBUTE_NOTES_VERSION:
            result.update(consolidated_catalog(wire.attribute_catalog))
        return result
    payload = wire.model_dump(mode="json")
    if isinstance(wire, RecognitionRequest):
        for key in ("version", "stage", "page_context_hash"):
            del payload[key]
        for key in ("source_sha256", "image_sha256", "preparation_sha256", "layout_sha256"):
            del payload["page"][key]
        return payload
    if not isinstance(wire, AttributeRequest):
        return payload

    del payload["page_context_hash"], payload["upstream_hash"]
    del payload["upstream"]["page_context_hash"]
    if wire.attribute_description_version == ATTRIBUTE_NOTES_VERSION:
        del payload["attribute_description_version"]
        payload.update(consolidated_catalog(wire.attribute_catalog))
    payload["input_version"] = wire.input_version
    page = payload["page"]
    layout = page["layout"]
    source_layout = wire.page.layout
    # Keep the token links needed to interpret alternate readings, uncertainty
    # and layout relationships that refer to tokens instead of reading IDs.
    referenced = {member for pair in source_layout.overlaps for member in (pair.left, pair.right)}
    referenced.update(member for item in source_layout.unresolved for member in item.support)
    referenced.update(
        member
        for table in source_layout.tables
        for cell in table.cells
        for member in cell.boundary_support
    )
    coordinates = ("x", "y", "width", "height")
    rows = []
    reading_sources = {}
    for reading, geometry, source_reading in zip(
        page["readings"], layout.pop("readings"), source_layout.readings, strict=True
    ):
        ref = reading["reading_ref"]
        region = geometry["region"] or {}
        rows.append(
            [
                ref,
                reading["text"],
                reading["modality"],
                reading["alternate_texts"],
                geometry["issues"],
                *(region.get(key) for key in coordinates),
            ]
        )
        if (
            len(source_reading.members) > 1
            or source_reading.issues
            or source_reading.preferred in referenced
        ):
            reading_sources[ref] = {
                "members": geometry["members"],
                "preferred": geometry["preferred"],
            }
    page["readings"] = {
        "columns": ["reading_ref", "text", "modality", "alternate_texts", "issues", *coordinates],
        "rows": rows,
    }
    if reading_sources:
        layout["reading_sources"] = reading_sources
    order_columns = ["before", "after", "basis"]
    layout["order"] = {
        "columns": order_columns,
        "rows": [[edge[key] for key in order_columns] for edge in layout["order"]],
    }
    if wire.input_version == ATTRIBUTE_INPUT_VERSION:
        compact_page(page)
    return payload


def request_for(factory, storage, claim):
    profile = claim.profile
    performance = active_performance.get()
    if performance is not None:
        performance.version = 2
        performance.profile_sha256 = profile.identity_hash
        if claim.unit_key.startswith("ATTRIBUTE_EXTRACTION:"):
            performance.output_version = profile.attribute_output_version
            performance.input_configuration = profile.manifest["attribute_input_version"]
            performance.source_projection = profile.manifest.get(
                "page_projection", performance.input_configuration
            )
        else:
            performance.source_projection = "recognition-page-v1"
    with measure("source_load"):
        with factory() as session:
            unit = session.get(ExtractionWorkUnit, claim.unit_id)
            if performance is not None:
                identity = unit.execution_metadata["stage_identity"]
                performance.prompt_sha256 = identity["prompt_hash"]
                performance.schema_sha256 = identity["transport_schema_hash"]
            snapshot = validate_plan(session, unit, profile)
            parent = prerequisite_result(session, unit)
            owner = PageOwner(
                document_id=unit.document_id,
                document_page_id=UUID(unit.execution_metadata["source_page_id"]),
                processing_run_id=unit.processing_run_id,
                page_number=unit.page_numbers[0],
            )
        source = load_bound(snapshot, storage, unit, profile)
    if performance is not None:
        performance.available_readings = len(source.layout.readings)
        performance.ocr_selected = source.prepared.ocr_decision == "RUN"
    with measure("request_build"):
        return _build_request(unit, parent, owner, source, claim)


def _build_request(unit, parent, owner, source, claim):
    profile = claim.profile
    page = project_page(source)
    context_hash = contract_hash(page)
    if page.owner != owner:
        raise ValueError("Source page differs from the authorized binding")
    common = dict(
        version=stage_schema_version(unit.stage),
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
        description_version = profile.manifest["attribute_descriptions"]
        definitions = attribute_catalog(upstream, description_version)
        if not definitions:
            skip = NoEligibleAttributes(
                version=ATTRIBUTE_VERSION,
                stage=unit.stage,
                outcome="NO_ELIGIBLE_ATTRIBUTES",
                page_context_hash=context_hash,
                upstream_hash=parent.result_hash,
                provider_calls=0,
            )
            return skip, None, source
        wire = AttributeRequest(
            **common,
            output_version=profile.attribute_output_version,
            input_version=profile.manifest["attribute_input_version"],
            upstream=upstream,
            attribute_description_version=description_version,
            upstream_hash=parent.result_hash,
            attribute_catalog=definitions,
        )
    validate_request(wire, expected_owner=owner)
    version = getattr(wire, "input_version", LEGACY_ATTRIBUTE_INPUT_VERSION)
    send_image = version != "readable-text-v1"
    if not send_image and not any(
        r.text.strip() or any(t.strip() for t in r.alternate_texts) for r in page.readings
    ):
        raise ProviderFailure(ErrorCode.NO_TEXT)
    payload = canonical_json(provider_input(wire))
    request = ExtractionRequest(
        work_unit_id=claim.unit_id,
        unit_key=claim.unit_key,
        attempt_number=claim.attempt_number,
        model=profile.model,
        instructions=profile.instructions_for(unit.stage),
        schema_version=wire.version,
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        text=payload,
        input_version=version,
        request_digest_version=profile.request_digest_for(unit.stage),
        image=source.image if send_image else None,
        image_mime_type="image/png" if send_image else None,
        image_detail="high",
        stage=unit.stage,
        response_model=profile.response_model_for(unit.stage),
        reasoning_effort=profile.reasoning_effort_for(unit.stage),
    )

    # Bound the actual encoded text and image envelope, including JSON escaping.
    if request.request_digest_version == BODY_DIGEST_VERSION:
        encoded_size = len(encoded_body(responses_body(request, request.response_model)))
    else:
        envelope = {
            "instructions": request.instructions,
            "input": [
                {"type": "input_text", "text": request.text},
                {"type": "input_image", "image_url": "data:image/png;base64,", "detail": "high"},
            ],
        }
        encoded_size = len(canonical_json(envelope).encode()) + 4 * ((len(source.image) + 2) // 3)
    if encoded_size > profile.max_transport_bytes:
        raise ValueError("Encoded extraction input exceeds its transport budget")
    return wire, request, source


def publication_request_hash(unit, wire, request):
    text = canonical_json(provider_input(wire))
    if isinstance(wire, RecognitionRequest) or (
        isinstance(wire, AttributeRequest)
        and (
            wire.input_version in EXPERIMENTAL_INPUTS
            or unit.execution_metadata.get("request_digest_version") == BODY_DIGEST_VERSION
        )
    ):
        if (
            request is None
            or request.work_unit_id != unit.id
            or request.input_version
            != getattr(wire, "input_version", LEGACY_ATTRIBUTE_INPUT_VERSION)
            or request.request_digest_version != BODY_DIGEST_VERSION
            or request.text != text
        ):
            raise ValueError("Publication differs from the dispatched input")
        return dispatch_hash(request)
    return stage_request_hash(text, unit.execution_metadata.get("attribute_reasoning_effort"))


def store_result(session, unit, snapshot, wire, result, observations, request=None):
    from powerforge_extraction.assertion_consistency import redundant_assertions
    from powerforge_extraction.publication import publication_diagnostics
    from powerforge_extraction.publication_records import publish

    parent = prerequisite_result(session, unit)
    skip = isinstance(result, NoEligibleAttributes)
    if (
        result.stage != unit.stage
        or result.version != wire.version
        or result.page_context_hash != wire.page_context_hash
    ):
        raise ValueError("Result differs from the pinned request")
    if not skip and (
        wire.page.owner != snapshot.layout.owner
        or wire.page.layout_sha256 != snapshot.layout.identity_hash
        or wire.page.preparation_sha256 != snapshot.prepared.manifest.identity_hash
        or wire.page.source_sha256 != snapshot.prepared.manifest.original.sha256
        or wire.page.page_image_id != snapshot.image.id
        or wire.page.image_sha256 != snapshot.image.sha256
        or contract_hash(wire.page) != wire.page_context_hash
    ):
        raise ValueError("Publication differs from the authorized page snapshot")
    if unit.stage == STAGES[1] and (
        parent is None
        or parent.result_hash != result.upstream_hash
        or parent.page_context_hash != result.page_context_hash
        or skip != (not attribute_catalog(recognition_result(parent)))
    ):
        raise ValueError("Result differs from its committed recognition prerequisite")
    request_hash = publication_request_hash(unit, wire, request)
    if unit.stage == STAGES[0]:
        delivery = session.get(UnitExecution, unit.id)
        if delivery is None or delivery.provider_request_hash != request_hash:
            raise ValueError("Recognition publication differs from the dispatched request")
    stage = StageResult(
        work_unit_id=unit.id,
        run_id=unit.run_id,
        document_page_id=UUID(unit.execution_metadata["source_page_id"]),
        stage=unit.stage,
        outcome="NO_ELIGIBLE_ATTRIBUTES" if skip else "RESULT",
        page_context_hash=result.page_context_hash,
        upstream_work_unit_id=parent.work_unit_id if parent else None,
        upstream_hash=parent.result_hash if parent else None,
        request_hash=request_hash,
        result_hash=contract_hash(result),
        payload=result.model_dump(mode="json"),
        diagnostics=publication_diagnostics(
            observations, redundant_assertions(result.model_dump(mode="json"))
        ),
    )
    session.add(stage)
    session.flush()
    if not skip:
        publish(session, stage, wire.page.page_image_id, observations)
    return {"candidates": len(observations), "evidence": sum(len(o.evidence) for o in observations)}


class FakeExtractionProvider:
    def __init__(self, scenario):
        self.scenario = scenario

    def execute(self, request):
        from powerforge_ai.extraction import ErrorCode, ProviderFailure

        if self.scenario in {"transient", "interrupted"} and request.attempt_number == 1:
            raise ProviderFailure(ErrorCode.UNAVAILABLE)
        if self.scenario in {"invalid", "permanent"}:
            raise ProviderFailure(ErrorCode.INVALID)
        if request.stage == STAGES[1]:
            return AttributeOutput(
                b'{"attributes":[],"raw_unmapped":[]}', ExecutionUsage(), request
            )
        equipment = (
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
        return RecognitionOutput(
            canonical_json({"equipment": equipment}).encode(), ExecutionUsage(), request
        )
