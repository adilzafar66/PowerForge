"""Table source I/O and request building outside the provider transaction boundary."""

from powerforge_ai.extraction import ExtractionRequest
from powerforge_extraction.grounding import load_page_sources
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.stage_runtime import (
    require_supported,
    successful_prerequisite,
    validate_plan,
)
from powerforge_extraction.table_runtime import render_table_call
from powerforge_extraction.table_sources import load_table_context


def table_request(claim, storage, factory):
    profile = claim.profile
    require_supported(profile)
    if claim.page_spec is None:
        raise ValueError("Pinned table page descriptors are required")
    sources = load_page_sources(
        claim.page_spec,
        storage,
        max_artifact_bytes=profile.max_input_bytes,
        max_total_bytes=profile.max_total_input_bytes,
        max_image_pixels=profile.max_image_pixels,
    )
    if sources.text is not None and len(sources.text) > profile.max_text_chars:
        raise ValueError("Native text exceeds the pinned table limit")
    with factory.begin() as session:
        unit = session.get(ExtractionWorkUnit, claim.unit_id)
        validate_plan(unit, profile)
        parent = successful_prerequisite(session, unit)
        upstream_id = parent.id if parent else None
        if upstream_id != claim.upstream_unit_id:
            raise ValueError("Table reconstruction attempt differs from the claimed context")
        context = load_table_context(session, sources, upstream_id) if upstream_id else None
    call = render_table_call(
        claim.page_spec.stage,
        profile,
        [
            (table.table_kind, table.layout.model_dump(mode="json"))
            for table in context.output.tables
        ]
        if context
        else (),
        upstream_id,
    )
    return (
        ExtractionRequest(
            work_unit_id=claim.unit_id,
            unit_key=claim.unit_key,
            attempt_number=claim.attempt_number,
            model=profile.model,
            instructions=call.instructions,
            schema_version=call.schema_version,
            timeout_seconds=profile.timeout_seconds,
            max_output_tokens=profile.max_output_tokens,
            text=sources.text,
            image=sources.image,
            image_mime_type="image/png" if sources.image is not None else None,
            response_model=call.response_model,
            stage=claim.page_spec.stage,
            source_roles=tuple(a.role for a in claim.page_spec.artifacts),
            upstream_context=call.upstream_context,
            image_detail=profile.image_detail,
        ),
        sources,
        context,
    )
