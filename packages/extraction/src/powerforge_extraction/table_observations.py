"""Offline table observations, not persistence entities or source-verification assertions."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from powerforge_extraction.observations import (
    Expression,
    LocalReference,
    ObservationResponse,
    ProposedKey,
    SourceAnchor,
)

RECONSTRUCTION_SCHEMA_VERSION = "table-reconstruction-schema-v1"
INTERPRETATION_SCHEMA_VERSION = "table-interpretation-schema-v1"
TableOrientation = Literal["EQUIPMENT_ROWS", "ATTRIBUTE_ROWS", "MIXED", "UNCLASSIFIED"]
MAX_TABLES = 8
MAX_ROWS = 128
MAX_COLUMNS = 32
MAX_CELLS = 512
MAX_EQUIPMENT = 64
MAX_ATTRIBUTES = 256
References = Annotated[list[LocalReference], Field(max_length=16)]


def require_acyclic_headers(graph: dict[str, set[str]]) -> None:
    """Call after reference membership checks; iterate over bounded model input."""
    pending = {ref: set(parents) for ref, parents in graph.items()}
    ready = {ref for ref, parents in pending.items() if not parents}
    while ready:
        for ref in ready:
            del pending[ref]
        for parents in pending.values():
            parents.difference_update(ready)
        ready = {ref for ref, parents in pending.items() if not parents}
    if pending:
        raise ValueError("Cyclic header relationships")


class TableObservationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @field_validator("*")
    @classmethod
    def nonblank_strings(cls, value, info):
        if isinstance(value, str) and info.field_name != "raw_text" and not value.strip():
            raise ValueError("Observation text must not be blank")
        return value


class Uncertainty(TableObservationContract):
    ambiguous: bool
    ambiguity_reason: Annotated[str, Field(min_length=1, max_length=500)] | None

    @model_validator(mode="after")
    def uncertainty(self):
        if self.ambiguous != (self.ambiguity_reason is not None):
            raise ValueError("Ambiguous observations require a reason; clear ones use null")
        return self


class TableTextObservation(Uncertainty):
    local_ref: LocalReference
    raw_text: Expression
    anchors: list[SourceAnchor] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def nonblank_text(self):
        if not self.raw_text.strip():
            raise ValueError("Caption/note text must not be blank")
        return self


class TableCellObservation(Uncertainty):
    local_ref: LocalReference
    row: int = Field(ge=0, lt=MAX_ROWS)
    column: int = Field(ge=0, lt=MAX_COLUMNS)
    row_span: int = Field(ge=1, le=MAX_ROWS)
    column_span: int = Field(ge=1, le=MAX_COLUMNS)
    state: Literal["VALUE", "BLANK", "UNREADABLE"]
    raw_text: Annotated[str, Field(max_length=2000)] | None
    header_role: Literal["NONE", "ROW", "COLUMN", "BOTH"]
    header_refs: list[LocalReference] = Field(max_length=8)
    anchors: list[SourceAnchor] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def cell_state(self):
        if self.state == "BLANK" and self.raw_text != "":
            raise ValueError("Observed blank cells use an explicit empty string")
        if self.state == "VALUE" and (self.raw_text is None or not self.raw_text.strip()):
            raise ValueError("Value cells require original nonblank text")
        if self.state == "UNREADABLE" and (
            not self.ambiguous or self.raw_text is not None and not self.raw_text.strip()
        ):
            raise ValueError("Unreadable cells require uncertainty and null or partial text")
        if self.header_role != "NONE" and self.state != "VALUE":
            raise ValueError("A header relationship requires a readable header")
        return self


class TableObservation(Uncertainty):
    local_ref: LocalReference
    proposed_kind: TableOrientation
    title: TableTextObservation | None
    notes: list[TableTextObservation] = Field(max_length=8)
    rows: list[LocalReference] = Field(min_length=1, max_length=MAX_ROWS)
    columns: list[LocalReference] = Field(min_length=1, max_length=MAX_COLUMNS)
    cells: list[TableCellObservation] = Field(min_length=1, max_length=MAX_CELLS)
    anchors: list[SourceAnchor] = Field(min_length=1, max_length=4)
    truncated: bool
    truncation_reason: Annotated[str, Field(min_length=1, max_length=500)] | None

    @model_validator(mode="after")
    def grid(self):
        if self.truncated != (self.truncation_reason is not None):
            raise ValueError("Source truncation requires a reason; it is not response overflow")
        if len(set(self.rows)) != len(self.rows) or len(set(self.columns)) != len(self.columns):
            raise ValueError("Row and column references must be distinct")
        items = [*self.cells, *self.notes, *([self.title] if self.title else [])]
        if len({item.local_ref for item in items}) != len(items):
            raise ValueError("Cell/caption/note references must be unique within a table")
        by_ref = {cell.local_ref: cell for cell in self.cells}
        occupied = set()
        for cell in self.cells:
            if cell.row + cell.row_span > len(self.rows) or (
                cell.column + cell.column_span > len(self.columns)
            ):
                raise ValueError("Cell span is outside the observed grid")
            slots = {
                (r, c)
                for r in range(cell.row, cell.row + cell.row_span)
                for c in range(cell.column, cell.column + cell.column_span)
            }
            if occupied & slots:
                raise ValueError("Overlapping cells must be one spanning cell, not copies")
            occupied.update(slots)
            if len(set(cell.header_refs)) != len(cell.header_refs):
                raise ValueError("Duplicate header references")
            for ref in cell.header_refs:
                header = by_ref.get(ref)
                if header is None or header.header_role == "NONE" or header is cell:
                    raise ValueError("Header reference requires another header in this table")
                row_aligned = (
                    header.row <= cell.row
                    and cell.row + cell.row_span <= header.row + header.row_span
                )
                column_aligned = (
                    header.column <= cell.column
                    and cell.column + cell.column_span <= header.column + header.column_span
                )
                if not (
                    header.header_role in {"ROW", "BOTH"}
                    and row_aligned
                    or header.header_role in {"COLUMN", "BOTH"}
                    and column_aligned
                ):
                    raise ValueError("Header span does not cover its declared relationship axis")
        require_acyclic_headers({cell.local_ref: set(cell.header_refs) for cell in self.cells})
        return self


class TableReconstructionResponse(ObservationResponse):
    max_response_bytes = 1024 * 1024
    schema_version: Literal["table-reconstruction-schema-v1"]
    tables: list[TableObservation] = Field(max_length=MAX_TABLES)

    @model_validator(mode="after")
    def page_bounds(self):
        if len({t.local_ref for t in self.tables}) != len(self.tables):
            raise ValueError("Duplicate table references")
        if sum(len(t.cells) for t in self.tables) > MAX_CELLS:
            raise ValueError("Page exceeds its total cell bound")
        return self


class TableEquipmentObservation(Uncertainty):
    local_ref: LocalReference
    table_ref: LocalReference
    raw_expression: Expression
    source_refs: References
    observed_tag: Annotated[str, Field(min_length=1, max_length=200)] | None
    observed_name: Annotated[str, Field(min_length=1, max_length=500)] | None
    proposed_equipment_type: ProposedKey | None

    @model_validator(mode="after")
    def support(self):
        if not self.source_refs or len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("Equipment needs distinct source references")
        return self


class TableAttributeObservation(Uncertainty):
    local_ref: LocalReference
    table_ref: LocalReference
    equipment_ref: LocalReference | None
    value_cell_ref: LocalReference
    label_refs: References
    unit_refs: References
    qualifier_refs: References
    raw_expression: Expression
    source_label: Expression | None
    raw_value: Expression | None
    raw_unit: Annotated[str, Field(min_length=1, max_length=100)] | None
    proposed_equipment_type: ProposedKey | None
    proposed_attribute_key: ProposedKey | None

    @model_validator(mode="after")
    def distinct_support(self):
        for refs in (self.label_refs, self.unit_refs, self.qualifier_refs):
            if len(set(refs)) != len(refs):
                raise ValueError("Duplicate supporting source references")
        return self


class TableInterpretationResponse(ObservationResponse):
    max_response_bytes = 512 * 1024
    schema_version: Literal["table-interpretation-schema-v1"]
    equipment: list[TableEquipmentObservation] = Field(max_length=MAX_EQUIPMENT)
    attributes: list[TableAttributeObservation] = Field(max_length=MAX_ATTRIBUTES)

    @model_validator(mode="after")
    def unique_claims(self):
        claims = [*self.equipment, *self.attributes]
        if len({c.local_ref for c in claims}) != len(claims):
            raise ValueError("Claim references must be unique across both collections")
        return self
