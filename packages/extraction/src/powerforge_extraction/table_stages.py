"""Offline table stages/resources. No profile registration, provider I/O or publication."""

from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files

from pydantic import BaseModel

from powerforge_engineering_model.registry import list_equipment_definitions
from powerforge_extraction.engineering_stages import RenderedInstructions
from powerforge_extraction.identities import canonical_json, identity_hash
from powerforge_extraction.observations import ObservationResponse
from powerforge_extraction.registry_context import (
    CONTEXT_VERSION,
    attribute_context,
    equipment_catalog,
    registry_projection_hash,
)
from powerforge_extraction.table_layout import (
    MAX_CONTEXT_BYTES,
    layout_identity,
    validate_claim_references,
)
from powerforge_extraction.table_observations import (
    INTERPRETATION_SCHEMA_VERSION,
    MAX_ATTRIBUTES,
    MAX_CELLS,
    MAX_COLUMNS,
    MAX_EQUIPMENT,
    MAX_ROWS,
    MAX_TABLES,
    RECONSTRUCTION_SCHEMA_VERSION,
    TableInterpretationResponse,
    TableReconstructionResponse,
)
from powerforge_extraction.terminology import terminology_hash, terminology_policy

STAGE_MANIFEST_VERSION = "table-stage-manifest-v1"
PROMPT_VERSION = "table-prompts-v1"
MAX_INSTRUCTION_BYTES = 128 * 1024


@dataclass(frozen=True)
class TableStage:
    key: str
    schema_version: str
    response_model: type[ObservationResponse]
    prompt_resource: str
    prerequisite: str | None

    @property
    def template(self):
        root = files("powerforge_extraction").joinpath("prompts")
        return (
            root.joinpath("table_common_v1.txt").read_text(encoding="utf-8")
            + "\n"
            + root.joinpath(self.prompt_resource).read_text(encoding="utf-8")
        )

    def identity(self):
        from powerforge_extraction.identities import content_hash

        return {
            "stage": self.key,
            "prerequisite": self.prerequisite,
            "prompt_version": PROMPT_VERSION,
            "template_hash": content_hash(self.template),
            "schema_version": self.schema_version,
            "schema_hash": identity_hash(self.response_model.model_json_schema()),
        }

    def render_instructions(self) -> RenderedInstructions:
        # Reconstruction creates no mapped types. Interpretation therefore keeps all
        # registry definitions rather than guessing a subset from tags or orientation.
        registry = (
            equipment_catalog()
            if self.prerequisite is None
            else attribute_context(e.key for e in list_equipment_definitions())
        )
        context = {"registry": registry, "terminology": terminology_policy()}
        text = self.template + "\nApproved metadata (not extracted source facts):\n"
        text += canonical_json(context) + "\n"
        if len(text.encode()) > MAX_INSTRUCTION_BYTES:
            raise ValueError("Table instructions exceed their versioned bound")
        return RenderedInstructions(text, identity_hash(context))

    def validate_result(
        self,
        payload: object,
        *,
        available_sources: Iterable[str],
        table_context: TableReconstructionResponse | None = None,
    ) -> ObservationResponse:
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        result = self.response_model.model_validate(payload)
        sources = set(available_sources)
        if not sources <= {"native_text", "analysis_image"}:
            raise ValueError("Unsupported source roles")
        if isinstance(result, TableReconstructionResponse):
            if table_context is not None:
                raise ValueError("Reconstruction has no table prerequisite")
            context = result
        else:
            if table_context is None:
                raise ValueError("Interpretation requires an explicit table context")
            context = TableReconstructionResponse.model_validate(
                table_context.model_dump(mode="json")
            )
            validate_claim_references(result, context)
        for table in context.tables:
            items = [table, *table.cells, *table.notes, *([table.title] if table.title else [])]
            for item in items:
                if any(anchor.source_ref not in sources for anchor in item.anchors):
                    raise ValueError("Observation references an unavailable source")
        return result


STAGES = (
    TableStage(
        "TABLE_RECONSTRUCTION",
        RECONSTRUCTION_SCHEMA_VERSION,
        TableReconstructionResponse,
        "table_reconstruction_v1.txt",
        None,
    ),
    TableStage(
        "TABLE_INTERPRETATION",
        INTERPRETATION_SCHEMA_VERSION,
        TableInterpretationResponse,
        "table_interpretation_v1.txt",
        "TABLE_RECONSTRUCTION",
    ),
)


def get_table_stage(key: str, version: str = STAGE_MANIFEST_VERSION) -> TableStage:
    if version == STAGE_MANIFEST_VERSION:
        for stage in STAGES:
            if stage.key == key:
                return stage
    raise ValueError("Unsupported table stage/version")


def table_manifest() -> dict:
    return {
        "version": STAGE_MANIFEST_VERSION,
        "registry_version": "registry-v1",
        "registry_context_version": CONTEXT_VERSION,
        "registry_projection_hash": registry_projection_hash(),
        "terminology_hash": terminology_hash(),
        "layout": layout_identity(),
        "bounds": {
            "tables_per_page": MAX_TABLES,
            "rows_per_table": MAX_ROWS,
            "columns_per_table": MAX_COLUMNS,
            "cells_per_page": MAX_CELLS,
            "equipment_per_page": MAX_EQUIPMENT,
            "attributes_per_page": MAX_ATTRIBUTES,
            "reconstruction_bytes": TableReconstructionResponse.max_response_bytes,
            "interpretation_bytes": TableInterpretationResponse.max_response_bytes,
            "instruction_bytes": MAX_INSTRUCTION_BYTES,
            "upstream_bytes": MAX_CONTEXT_BYTES,
        },
        "stages": [stage.identity() for stage in STAGES],
    }
