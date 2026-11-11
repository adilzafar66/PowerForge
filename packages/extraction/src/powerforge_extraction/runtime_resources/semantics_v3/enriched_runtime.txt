"""Fixed enhanced page plans and bounded projections of immutable committed outputs."""

import json
from dataclasses import replace
from importlib.resources import files

from sqlalchemy import select

from powerforge_extraction.contracts import CandidateInput
from powerforge_extraction.enriched_grounding import line_groups, table_readings
from powerforge_extraction.enriched_output import convert_equipment
from powerforge_extraction.enriched_planning import metadata
from powerforge_extraction.enriched_profiles import (
    EnrichedTableProfile,
    is_semantic,
    prompt_for,
    require_enriched,
    stage_models,
    stage_schemas,
)
from powerforge_extraction.enriched_sources import bound_snapshot, load_bound
from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.models import ExtractedTable, ExtractionCandidate, ExtractionWorkUnit
from powerforge_extraction.registry_context import attribute_context, equipment_catalog
from powerforge_extraction.stage_runtime import StageCall, successful_prerequisite
from powerforge_extraction.terminology import terminology_policy


def validate_plan(session, unit, profile):
    require_enriched(profile)
    source = bound_snapshot(session, unit)
    binding = session.scalar(
        select(RunSourceEnrichmentBinding).where(
            RunSourceEnrichmentBinding.run_id == unit.run_id,
            RunSourceEnrichmentBinding.document_page_id == source.layout.owner.document_page_id,
        )
    )
    if (
        unit.stage not in profile.stages
        or len(unit.page_numbers) != 1
        or unit.execution_metadata != metadata(profile, unit.stage, unit.page_numbers[0], binding)
    ):
        raise ValueError("Unit differs from its exact enhanced page plan")


def stage_call(session, unit, profile):
    validate_plan(session, unit, profile)
    parent = successful_prerequisite(session, unit)
    upstream, selected = None, set()
    if unit.execution_metadata.get("prerequisite_key"):
        if parent is None:
            raise ValueError("Committed upstream output is required")
        if isinstance(profile, EnrichedTableProfile):
            tables = list(
                session.scalars(
                    select(ExtractedTable).where(ExtractedTable.work_unit_id == parent.id)
                )
            )
            upstream = canonical_json(
                dict(
                    tables=[
                        dict(
                            table_ref=t.layout["metadata"]["observation"]["local_ref"],
                            observation=t.layout["metadata"]["observation"],
                            structure_basis=t.layout["metadata"]["structure_basis"],
                            printed_text_independently_verified=False,
                        )
                        for t in tables
                    ]
                )
            )
        else:
            candidates = list(
                session.scalars(
                    select(ExtractionCandidate).where(ExtractionCandidate.work_unit_id == parent.id)
                )
            )
            if is_semantic(profile):
                candidates = [c for c in candidates if c.kind == "EQUIPMENT_MENTION"]
            if len(candidates) > 32 or any(c.kind != "EQUIPMENT_MENTION" for c in candidates):
                raise ValueError("Invalid committed equipment context")
            selected = {c.equipment_type_key for c in candidates if c.equipment_type_key}
            upstream = canonical_json(
                dict(
                    equipment=[
                        dict(
                            local_ref=c.diagnostics["source_local_ref"],
                            raw_expression=c.raw_text,
                            observed_tag=c.observed_tag,
                            equipment_type=c.equipment_type_key,
                            mapping_status=c.mapping_status,
                        )
                        for c in candidates
                    ]
                )
            )
    registry = (
        equipment_catalog()
        if unit.stage == "EQUIPMENT_RECOGNITION"
        else attribute_context(
            [e["key"] for e in equipment_catalog()["equipment_types"]]
            if isinstance(profile, EnrichedTableProfile) or is_semantic(profile)
            else selected
        )
    )
    instructions = (
        files("powerforge_extraction").joinpath(prompt_for(profile, unit.stage)).read_text()
    )
    instructions += (
        "\nCurrent stage: "
        + unit.stage
        + ". Required schema: "
        + stage_schemas(profile)[unit.stage]
    )
    instructions += "\nTrusted registry metadata and qualified terminology:\n" + canonical_json(
        dict(registry=registry, terminology=terminology_policy())
    )
    if (
        len(instructions.encode()) > profile.max_instruction_bytes
        or len((upstream or "").encode()) > profile.max_upstream_bytes
    ):
        raise ValueError("Enhanced instructions/upstream exceed their pinned bounds")
    return StageCall(
        stage_models(profile)[unit.stage],
        stage_schemas(profile)[unit.stage],
        instructions,
        upstream,
        parent.id if parent else None,
    )


def projection(sources, profile):
    owned = table_readings(sources)
    table = isinstance(profile, EnrichedTableProfile)
    readings = [
        r
        for r in sources.readings
        if "NATIVE_PREFERRED_UNALIGNED" not in r.model.issues
        and (table or is_semantic(profile) or r.model.ref not in owned)
    ]
    allowed = {r.model.ref for r in readings}
    data = dict(
        version="enriched-source-context-v1",
        untrusted=True,
        serialized_readings_are_printed_quotes=False,
        printed_text_independently_verified=False,
        coverage=sources.prepared.text_coverage,
        readings=[
            dict(
                ref=r.model.ref,
                raw_text=r.text,
                reading_basis=r.kind,
                issues=list(r.model.issues),
                confidence=r.confidence.model_dump(mode="json") if r.confidence else None,
            )
            for r in readings
        ],
        lines=[
            dict(reading_refs=[r.model.ref for r in line])
            for line in line_groups(sources).values()
            if all(r.model.ref in allowed for r in line)
        ],
        tables=[
            dict(
                ref=t.ref,
                rows=t.rows,
                columns=t.columns,
                captions=list(t.captions),
                structure_basis=t.structure_basis,
                cells=[
                    dict(
                        ref=c.ref,
                        row=c.row,
                        column=c.column,
                        row_span=c.row_span,
                        column_span=c.column_span,
                        reading_refs=list(c.readings),
                        header_role=c.header_role,
                        headers=list(c.headers),
                        state=c.state,
                    )
                    for c in t.cells
                ],
            )
            for t in sources.layout.tables
        ]
        if table
        else [],
    )
    text = canonical_json(data)
    if len(text.encode()) > 131072 or len(text) > profile.max_text_chars:
        raise ValueError("Enhanced source projection exceeds its independent bound")
    return text


def upstream_output(session, sources, parent, profile):
    original = replace(sources, unit_id=parent.id, unit_key=parent.unit_key, stage=parent.stage)
    if isinstance(profile, EnrichedTableProfile):
        from powerforge_extraction.enriched_contracts import EnrichedTableInput
        from powerforge_extraction.enriched_tables import reconstruct

        rows = list(
            session.scalars(select(ExtractedTable).where(ExtractedTable.work_unit_id == parent.id))
        )
        response = stage_models(profile)[parent.stage].model_validate(
            dict(
                schema_version=stage_schemas(profile)[parent.stage],
                overflowed=False,
                tables=[r.layout["metadata"]["reported_observation"] for r in rows],
            )
        )
        output, context = reconstruct(response, original)
        actual = {
            r.id: EnrichedTableInput.model_validate_json(
                json.dumps(
                    dict(
                        id=str(r.id),
                        layout_schema_version=r.layout_schema_version,
                        table_kind=r.table_kind,
                        source_locations=r.source_locations,
                        evidence_ids=r.evidence_ids,
                        layout=r.layout,
                    )
                )
            )
            for r in rows
        }
        if {t.id: t for t in output.tables} != actual:
            raise ValueError("Committed table reconstruction differs from its exact source")
        return context
    rows = list(
        session.scalars(
            select(ExtractionCandidate).where(ExtractionCandidate.work_unit_id == parent.id)
        )
    )
    if is_semantic(profile):
        from powerforge_extraction.semantic_output import committed_recognition

        return committed_recognition(
            original, [row for row in rows if row.kind == "EQUIPMENT_MENTION"]
        )
    response = stage_models(profile)[parent.stage].model_validate(
        dict(
            schema_version=stage_schemas(profile)[parent.stage],
            overflowed=False,
            equipment=[r.diagnostics["observation"] for r in rows],
        )
    )
    output = convert_equipment(response, original)
    expected = {c.id: c for c in output.candidates}
    for row in rows:
        data = {field: getattr(row, field) for field in CandidateInput.model_fields}
        data["diagnostics"] = {
            k: v for k, v in data["diagnostics"].items() if k not in ("synthetic", "execution_kind")
        }
        if expected.get(row.id) != CandidateInput.model_validate(data):
            raise ValueError("Committed equipment differs from its pinned source")
    return output


def request_for(claim, storage, factory):
    from powerforge_ai.extraction import ExtractionRequest

    with factory() as session:
        unit = session.get(ExtractionWorkUnit, claim.unit_id)
        call = stage_call(session, unit, claim.profile)
        snapshot = bound_snapshot(session, unit)
        if call.upstream_unit_id != claim.upstream_unit_id:
            raise ValueError("Upstream attempt differs from admission")
    sources = load_bound(snapshot, storage, unit, claim.profile)
    context = None
    if call.upstream_unit_id:
        with factory() as session:
            parent = session.get(ExtractionWorkUnit, call.upstream_unit_id)
            context = upstream_output(session, sources, parent, claim.profile)
    text = projection(sources, claim.profile)
    if (
        len(text.encode()) + len(sources.image) + len((call.upstream_context or "").encode())
        > claim.profile.max_total_input_bytes
    ):
        raise ValueError("Enhanced page exceeds total provider input bound")
    return (
        ExtractionRequest(
            work_unit_id=claim.unit_id,
            unit_key=claim.unit_key,
            attempt_number=claim.attempt_number,
            model=claim.profile.model,
            instructions=call.instructions,
            schema_version=call.schema_version,
            timeout_seconds=claim.profile.timeout_seconds,
            max_output_tokens=claim.profile.max_output_tokens,
            text=text,
            image=sources.image,
            image_mime_type="image/png",
            response_model=call.response_model,
            stage=unit.stage,
            source_roles=("spatial_readings", "analysis_image"),
            upstream_context=call.upstream_context,
            image_detail=claim.profile.image_detail,
        ),
        sources,
        context,
    )
