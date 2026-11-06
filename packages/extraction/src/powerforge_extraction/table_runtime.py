"""Versioned fixed table plan and bounded projection of committed reconstruction."""

import json
from importlib.resources import files

from sqlalchemy import select

from powerforge_extraction.identities import canonical_json, content_hash, identity_hash
from powerforge_extraction.models import ExtractedTable
from powerforge_extraction.table_grounding import table_identity
from powerforge_extraction.table_layout import TableSourceMetadata, observation_context
from powerforge_extraction.table_observations import TableObservation, TableReconstructionResponse
from powerforge_extraction.table_profiles import ADAPTER_VERSION, TableProfile, table_input_contract
from powerforge_extraction.table_stages import get_table_stage, table_manifest

RUNTIME_VERSION = "table-page-runtime-v1"
CONTEXT_VERSION = "committed-table-context-v1"


def table_runtime_identity():
    root = files("powerforge_extraction")
    names = (
        "profiles.py",
        "stage_runtime.py",
        "dependencies.py",
        "orchestration.py",
        "execution.py",
        "table_profiles.py",
        "table_runtime.py",
        "table_execution.py",
        "table_fake.py",
        "table_input.py",
        "prompts/table_input_v1.json",
        "contracts.py",
    )
    return {
        "version": RUNTIME_VERSION,
        "rules_hash": identity_hash(
            {
                name: content_hash(
                    root.joinpath(
                        "runtime_resources/table_v1/"
                        + name.replace("/", "__").removesuffix(".py").removesuffix(".json")
                        + ".txt"
                    ).read_text()
                )
                for name in names
            }
        ),
    }


def require_table_supported(profile: TableProfile):
    manifest = table_manifest()
    if (
        profile.manifest != manifest
        or profile.prompt_hash != identity_hash(manifest)
        or profile.schema_hash != identity_hash(manifest)
        or profile.grounding != table_identity()
        or profile.runtime != table_runtime_identity()
        or profile.adapter_version != ADAPTER_VERSION
        or profile.adapter_hash != identity_hash(table_input_contract())
    ):
        raise ValueError("Pinned table resources are unavailable")


def _projection(tables, parent_id, profile):
    if len(tables) > 8:
        raise ValueError("Committed table context exceeds its count bound")
    tables = sorted(tables, key=lambda t: t[1]["metadata"]["observation"]["local_ref"])
    observations = []
    for _, layout in tables:
        metadata = layout["metadata"]
        if metadata["producer"] != profile.grounding or metadata["producer_unit_id"] != str(
            parent_id
        ):
            raise ValueError("Committed table producer differs from its pinned identity")
        observations.append(TableObservation.model_validate(metadata["observation"]))
    response = TableReconstructionResponse(
        schema_version="table-reconstruction-schema-v1", overflowed=False, tables=observations
    )
    projection = json.loads(observation_context(response))
    projection["version"] = CONTEXT_VERSION
    for item, (kind, layout) in zip(projection["tables"], tables, strict=True):
        metadata = layout["metadata"]
        reliability = TableSourceMetadata.model_validate_json(
            canonical_json(metadata["reliability"])
        )
        item["proposed_kind"] = kind
        item["structure_basis"] = reliability.structure_basis
        item["scoped_refs"] = sorted(metadata["scoped_refs"])
        item["cell_text_basis"] = {c.cell_ref: c.text_basis for c in reliability.cells}
    context = canonical_json(projection)
    if len(context.encode()) > profile.max_upstream_bytes:
        raise ValueError("Committed tables exceed the pinned upstream bound")
    return context


def render_table_call(stage_key, profile, tables=(), parent_id=None):
    """Pure rendering; the executor supplies a validated, detached M2 snapshot."""
    from powerforge_extraction.stage_runtime import StageCall

    stage = get_table_stage(stage_key, profile.manifest["version"])
    if bool(stage.prerequisite) != (parent_id is not None):
        raise ValueError("Table context differs from the selected stage")
    upstream = _projection(tables, parent_id, profile) if parent_id else None
    instructions = stage.render_instructions().text
    if len(instructions.encode()) > profile.max_instruction_bytes:
        raise ValueError("Table instructions exceed the pinned bound")
    return StageCall(stage.response_model, stage.schema_version, instructions, upstream, parent_id)


def table_stage_call(session, unit, profile):
    """Bounded independent recheck at call/publication telemetry fences; no source I/O."""
    from powerforge_extraction.stage_runtime import successful_prerequisite, validate_plan

    validate_plan(unit, profile)
    if unit.stage == "TABLE_RECONSTRUCTION":
        return render_table_call(unit.stage, profile)
    parent = successful_prerequisite(session, unit)
    if parent is None or (
        parent.document_id != unit.document_id
        or parent.processing_run_id != unit.processing_run_id
        or set(parent.input_artifact_ids) != set(unit.input_artifact_ids)
    ):
        raise ValueError("Committed same-run/page reconstruction is required")
    rows = list(
        session.scalars(
            select(ExtractedTable).where(ExtractedTable.work_unit_id == parent.id).limit(9)
        )
    )
    return render_table_call(
        unit.stage, profile, [(row.table_kind, row.layout) for row in rows], parent.id
    )
