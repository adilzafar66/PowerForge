"""Synthetic table data and actual SDK request inputs; no network/model fallback."""

import json
from uuid import uuid4

from powerforge_ai.extraction import ExtractionRequest
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.table_layout import observation_context
from powerforge_extraction.table_observations import TableReconstructionResponse
from powerforge_extraction.table_profiles import TABLE_OPENAI_PROFILE, table_profile
from powerforge_extraction.table_stages import get_table_stage
from powerforge_shared.config import Settings
from table_grounding_support import claims, converted, schedule


def profile_for(key=TABLE_OPENAI_PROFILE):
    return table_profile(key, Settings(_env_file=None, extraction_external_enabled=True))


def stage_request(stage="TABLE_RECONSTRUCTION", *, profile=None, mode="hybrid"):
    profile = profile or profile_for()
    reconstruction, text = schedule(visual=mode == "image")
    _, output, _, _, _, _ = converted(
        reconstruction, text=None if mode == "image" else text, image=mode != "text"
    )
    metadata = output.tables[0].layout.metadata
    upstream = json.loads(
        observation_context(TableReconstructionResponse.model_validate(reconstruction))
    )
    upstream["version"] = "committed-table-context-v1"
    item = upstream["tables"][0]
    item.update(
        structure_basis=metadata["reliability"]["structure_basis"],
        scoped_refs=metadata["scoped_refs"],
        cell_text_basis={c["cell_ref"]: c["text_basis"] for c in metadata["reliability"]["cells"]},
    )
    definition = get_table_stage(stage)
    return ExtractionRequest(
        work_unit_id=uuid4(),
        unit_key=f"{stage}:page:000001",
        attempt_number=1,
        model=profile.model,
        instructions=definition.render_instructions().text,
        schema_version=definition.schema_version,
        response_model=definition.response_model,
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        stage=stage,
        text=None if mode == "image" else text,
        image=None if mode == "text" else b"fixture-png",
        image_mime_type=None if mode == "text" else "image/png",
        image_detail=profile.image_detail,
        source_roles=("analysis_image",)
        if mode == "image"
        else ("native_text",)
        if mode == "text"
        else ("native_text", "analysis_image"),
        upstream_context=canonical_json(upstream) if stage == "TABLE_INTERPRETATION" else None,
    )


def scripted_observations(stage, *, visual=False, empty=False, multiple=False):
    if stage == "TABLE_RECONSTRUCTION":
        result = schedule(visual=visual)[0]
        if empty:
            result["tables"] = []
        if multiple:
            second = schedule(title="2-Winding Transformer Auxiliary Schedule", visual=visual)[0][
                "tables"
            ][0]
            second["local_ref"] = "t2"
            result["tables"].append(second)
        return result
    return claims()
