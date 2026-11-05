"""Pure layout inspection/reference checks. No artifact admission or persistence conversion."""

from dataclasses import dataclass
from importlib.resources import files
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from powerforge_extraction.identities import canonical_json, content_hash, identity_hash
from powerforge_extraction.observations import LocalReference
from powerforge_extraction.table_observations import (
    MAX_CELLS,
    TableInterpretationResponse,
    TableObservation,
    TableObservationContract,
    TableOrientation,
    TableReconstructionResponse,
    require_acyclic_headers,
)

LAYOUT_RULES_VERSION = "table-layout-observations-v1"
METADATA_VERSION = "table-source-metadata-v1"
CONTEXT_VERSION = "table-observation-context-v1"
MAX_CONTEXT_BYTES = 128 * 1024


class CellReliability(TableObservationContract):
    """Server-authored metadata only; never part of either provider response schema."""

    cell_ref: LocalReference
    state: Literal["VALUE", "BLANK", "UNREADABLE"]
    header_role: Literal["NONE", "ROW", "COLUMN", "BOTH"]
    header_refs: list[LocalReference] = Field(max_length=8)
    text_basis: Literal["UNVERIFIED", "NATIVE_VERIFIED", "VISUAL_REPORTED"]
    evidence_ids: list[UUID] = Field(max_length=8)

    @model_validator(mode="after")
    def evidence_for_admission(self):
        if self.header_role != "NONE" and self.state != "VALUE":
            raise ValueError("Header metadata requires readable text")
        if len(set(self.header_refs)) != len(self.header_refs):
            raise ValueError("Duplicate metadata header references")
        if self.text_basis != "UNVERIFIED" and not self.evidence_ids:
            raise ValueError("Admitted cell text requires evidence")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Duplicate cell evidence")
        return self


class TableSourceMetadata(TableObservationContract):
    version: Literal["table-source-metadata-v1"]
    structure_basis: Literal["UNRESOLVED", "NATIVE_DELIMITED", "VISUAL_REPORTED"]
    structure_evidence_ids: list[UUID] = Field(max_length=16)
    cells: list[CellReliability] = Field(max_length=MAX_CELLS)

    @model_validator(mode="after")
    def metadata_shape(self):
        if self.structure_basis != "UNRESOLVED" and not self.structure_evidence_ids:
            raise ValueError("Admitted structure requires evidence")
        if len(set(self.structure_evidence_ids)) != len(self.structure_evidence_ids):
            raise ValueError("Duplicate structure evidence")
        if len({c.cell_ref for c in self.cells}) != len(self.cells):
            raise ValueError("Duplicate metadata cell references")
        cells = {c.cell_ref: c for c in self.cells}
        for cell in self.cells:
            if any(
                ref not in cells or ref == cell.cell_ref or cells[ref].header_role == "NONE"
                for ref in cell.header_refs
            ):
                raise ValueError("Metadata references an unavailable header")
        require_acyclic_headers({c.cell_ref: set(c.header_refs) for c in self.cells})
        return self


@dataclass(frozen=True)
class ObservedLayout:
    table: TableObservation
    orientation_hint: TableOrientation
    reason: str
    reliability: TableSourceMetadata


def inspect_layout(table: TableObservation) -> ObservedLayout:
    """Preserve the sparse observed grid and conservative hint; verify no source claim."""
    table = TableObservation.model_validate(table.model_dump(mode="json"))
    kind, reason = table.proposed_kind, "MODEL_ORIENTATION_PROPOSAL"
    if table.ambiguous:
        kind, reason = "UNCLASSIFIED", "UNRESOLVED_LAYOUT"
    elif kind in {"EQUIPMENT_ROWS", "ATTRIBUTE_ROWS"} and not any(
        cell.header_refs for cell in table.cells
    ):
        kind, reason = "UNCLASSIFIED", "NO_HEADER_RELATIONSHIPS"
    return ObservedLayout(
        table,
        kind,
        reason,
        TableSourceMetadata(
            version=METADATA_VERSION,
            structure_basis="UNRESOLVED",
            structure_evidence_ids=[],
            cells=[
                CellReliability(
                    cell_ref=c.local_ref,
                    state=c.state,
                    header_role=c.header_role,
                    header_refs=list(c.header_refs),
                    text_basis="UNVERIFIED",
                    evidence_ids=[],
                )
                for c in table.cells
            ],
        ),
    )


def source_items(table: TableObservation) -> dict:
    return {
        item.local_ref: item
        for item in [*table.cells, *table.notes, *([table.title] if table.title else [])]
    }


def validate_claim_references(
    result: TableInterpretationResponse, context: TableReconstructionResponse
) -> None:
    """Reference authorization within an offline snapshot, not DB or semantic authority."""
    tables = {t.local_ref: t for t in context.tables}
    equipment = {e.local_ref: e for e in result.equipment}
    for claim in [*result.equipment, *result.attributes]:
        if claim.table_ref not in tables:
            raise ValueError("Claim references an unavailable table")
        table = tables[claim.table_ref]
        items = source_items(table)
        if hasattr(claim, "source_refs"):
            refs = claim.source_refs
        else:
            refs = [
                claim.value_cell_ref,
                *claim.label_refs,
                *claim.unit_refs,
                *claim.qualifier_refs,
            ]
            cell = next((c for c in table.cells if c.local_ref == claim.value_cell_ref), None)
            if cell is None or cell.state == "BLANK":
                raise ValueError("Attribute needs an existing nonblank value cell")
            if claim.equipment_ref is not None and (
                claim.equipment_ref not in equipment
                or equipment[claim.equipment_ref].table_ref != claim.table_ref
            ):
                raise ValueError("Equipment reference must name a claim in the same table")
        if any(ref not in items for ref in refs):
            raise ValueError("Claim references a cell/caption/note outside its table")
    # Row/column ownership, raw readings and mapping remain M2 responsibilities.


def observation_context(response: TableReconstructionResponse) -> str:
    """Bounded offline projection. Future workers must supply committed, admitted context."""
    response = TableReconstructionResponse.model_validate(response.model_dump(mode="json"))
    tables = []
    for table in response.tables:
        observed = inspect_layout(table)
        tables.append(
            {
                "local_ref": table.local_ref,
                "proposed_kind": observed.orientation_hint,
                "rows": table.rows,
                "columns": table.columns,
                "cells": [c.model_dump(mode="json", exclude={"anchors"}) for c in table.cells],
                "title": table.title.model_dump(exclude={"anchors"}) if table.title else None,
                "notes": [n.model_dump(exclude={"anchors"}) for n in table.notes],
                "ambiguous": table.ambiguous,
                "ambiguity_reason": table.ambiguity_reason,
                "truncated": table.truncated,
                "truncation_reason": table.truncation_reason,
                "structure_basis": observed.reliability.structure_basis,
            }
        )
    rendered = canonical_json({"version": CONTEXT_VERSION, "tables": tables})
    if len(rendered.encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("Table context exceeds its byte limit; do not truncate")
    return rendered


def layout_identity() -> dict:
    root = files("powerforge_extraction")
    return {
        "version": LAYOUT_RULES_VERSION,
        "rules_hash": identity_hash(
            {
                name: content_hash(root.joinpath(name).read_text(encoding="utf-8"))
                for name in (
                    "table_observations.py",
                    "table_layout.py",
                    "table_stages.py",
                    "observations.py",
                )
            }
        ),
        "metadata_version": METADATA_VERSION,
        "metadata_schema_hash": identity_hash(TableSourceMetadata.model_json_schema()),
        "context_version": CONTEXT_VERSION,
    }
