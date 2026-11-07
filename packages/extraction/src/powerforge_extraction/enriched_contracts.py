"""Explicit v2 output contracts; frozen 6A/6C/6D contracts stay unchanged."""

from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from powerforge_extraction.contracts import (
    Contract,
    Identity,
    TableCell,
    TableLayout,
    WorkUnitOutput,
)
from powerforge_extraction.enums import EvidenceSourceKind, ExtractionMethod, TableKind
from powerforge_provenance.enriched_locations import EnrichedLocation


class EnrichedEvidence(Contract):
    id: UUID = Field(default_factory=uuid4)
    location: EnrichedLocation
    source_kind: EvidenceSourceKind
    extraction_method: ExtractionMethod
    source_snippet: str | None = Field(default=None, max_length=2000)
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, ge=0)
    offset_convention: Literal["UNICODE_CODEPOINT"] | None = None
    table_id: UUID | None = None
    cell_id: Identity | None = None

    @model_validator(mode="after")
    def offsets(self):
        text = self.location.enrichment_artifact_id is not None
        if text != (
            self.text_start is not None
            and self.text_end is not None
            and self.offset_convention is not None
            and self.source_snippet is not None
        ):
            raise ValueError("Text offsets require exactly the selected enrichment text artifact")
        if text and self.text_end <= self.text_start:
            raise ValueError("Text span must be nonempty")
        if not text and any(
            x is not None
            for x in (self.text_start, self.text_end, self.offset_convention, self.source_snippet)
        ):
            raise ValueError("Visual observations do not verify characters or offsets")
        if self.cell_id is not None and self.table_id is None:
            raise ValueError("Cell evidence requires a table")
        return self


class EnrichedTableCell(TableCell):
    location: EnrichedLocation | None = None


class EnrichedTableLayout(TableLayout):
    cells: list[EnrichedTableCell] = Field(max_length=512)


class EnrichedTableInput(Contract):
    id: UUID = Field(default_factory=uuid4)
    layout_schema_version: Literal["table-layout-v2"] = "table-layout-v2"
    table_kind: TableKind = TableKind.UNCLASSIFIED
    source_locations: list[EnrichedLocation] = Field(min_length=1, max_length=1000)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=4096)
    layout: EnrichedTableLayout


class EnrichedOutput(WorkUnitOutput):
    evidence: list[EnrichedEvidence] = Field(default_factory=list, max_length=10000)
    tables: list[EnrichedTableInput] = Field(default_factory=list, max_length=8)
