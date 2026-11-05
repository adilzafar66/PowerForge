"""Closed, independently annotated table corpus and offline production-converter replay."""

from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid5

from pydantic import Field, model_validator

from powerforge_extraction.contracts import WorkUnitOutput
from powerforge_extraction.evaluation import Label, SourceFile, read_json, source_bytes, sources_for
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.table_grounding import (
    context_from_output,
    convert_table_reconstruction,
    table_identity,
)
from powerforge_extraction.table_observations import require_acyclic_headers
from powerforge_extraction.table_output import convert_table_interpretation
from powerforge_extraction.table_stages import table_manifest

VERSION = "table-evaluation-v1"
Position = Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=2, max_length=2)]


class GoldCell(Label):
    position: Position = Field(min_length=2, max_length=2)
    text: str | None
    state: Literal["VALUE", "BLANK", "UNREADABLE"] = "VALUE"
    row_span: int = Field(default=1, ge=1, le=128)
    column_span: int = Field(default=1, ge=1, le=32)
    header_role: Literal["NONE", "ROW", "COLUMN", "BOTH"] = "NONE"
    headers: list[Position] = Field(default_factory=list)
    role: Literal["native_text", "analysis_image"]
    span: Position | None = None
    text_basis: Literal["NATIVE_VERIFIED", "VISUAL_REPORTED", "UNVERIFIED"]


class GoldTable(Label):
    id: str
    role: Literal["native_text", "analysis_image"]
    anchor: str = Field(min_length=1)
    span: Position | None = None
    # Visual matching uses visible caption/landmarks, never invented pixel coordinates.
    landmarks: list[Position] = Field(min_length=1)
    title: str | None
    rows: int = Field(ge=1, le=128)
    columns: int = Field(ge=1, le=32)
    orientation: Literal["EQUIPMENT_ROWS", "ATTRIBUTE_ROWS", "MIXED", "UNCLASSIFIED"]
    structure_basis: Literal["NATIVE_DELIMITED", "VISUAL_REPORTED", "UNRESOLVED"]
    cells: list[GoldCell] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def grid(self):
        by_position = {tuple(c.position): c for c in self.cells}
        if len(by_position) != len(self.cells):
            raise ValueError("Duplicate gold cell positions")
        occupied = set()
        for c in self.cells:
            r, col = c.position
            if min(r, col) < 0 or r + c.row_span > self.rows or col + c.column_span > self.columns:
                raise ValueError("Gold cell outside grid")
            slots = {
                (i, j) for i in range(r, r + c.row_span) for j in range(col, col + c.column_span)
            }
            if occupied & slots:
                raise ValueError("Overlapping gold spans")
            occupied |= slots
            if (
                c.state == "BLANK"
                and c.text != ""
                or c.state == "VALUE"
                and not c.text
                or c.state == "UNREADABLE"
                and c.text == ""
                or len({tuple(p) for p in c.headers}) != len(c.headers)
                or any(
                    tuple(p) not in by_position or tuple(p) == tuple(c.position) for p in c.headers
                )
            ):
                raise ValueError("Inconsistent gold cell/header annotation")
            for pos in c.headers:
                header = by_position[tuple(pos)]
                row_axis = (
                    header.position[0] <= r
                    and r + c.row_span <= header.position[0] + header.row_span
                )
                column_axis = (
                    header.position[1] <= col
                    and col + c.column_span <= header.position[1] + header.column_span
                )
                if not (
                    header.header_role in {"ROW", "BOTH"}
                    and row_axis
                    or header.header_role in {"COLUMN", "BOTH"}
                    and column_axis
                ):
                    raise ValueError("Gold header does not cover its declared axis")
        if any(tuple(p) not in by_position for p in self.landmarks):
            raise ValueError("Missing gold landmark")
        require_acyclic_headers({str(c.position): {str(p) for p in c.headers} for c in self.cells})
        return self


class GoldClaim(Label):
    id: str
    table: str
    # None means the caption (single-equipment specification), not an invented cell.
    cell: Position | None
    kind: Literal["EQUIPMENT_MENTION", "ATTRIBUTE_VALUE"]
    expression: str = Field(min_length=1)
    status: Literal["MAPPED", "UNMAPPED", "INVALID"]
    equipment_type: str | None = None
    tag: str | None = None
    attribute_key: str | None = None
    value_type: Literal["NUMBER", "INTEGER", "TEXT", "ENUM", "BOOLEAN"] | None = None
    value: str | bool | None = None
    unit: str | None = None
    raw_value: str | None = None
    raw_unit: str | None = None
    equipment: str | None = None

    @model_validator(mode="after")
    def typed_value(self):
        from decimal import Decimal

        from powerforge_engineering_model.registry import (
            get_attribute_definition,
            get_equipment_definition,
        )

        if self.equipment_type is not None:
            get_equipment_definition(self.equipment_type)
        if self.kind == "EQUIPMENT_MENTION" and (
            self.status == "MAPPED"
            and self.equipment_type is None
            or self.tag is not None
            and self.tag not in self.expression
            or self.equipment is not None
        ):
            raise ValueError("Invalid gold equipment identity")
        if self.kind == "ATTRIBUTE_VALUE" and self.cell is None:
            raise ValueError("Gold attributes require a source value cell")

        if self.kind == "ATTRIBUTE_VALUE" and self.status == "MAPPED":
            definition = get_attribute_definition(self.equipment_type, self.attribute_key)
            if (
                self.value_type != definition.value_type
                or self.unit != definition.canonical_unit
                or self.value is None
                or (self.value_type == "BOOLEAN") != isinstance(self.value, bool)
            ):
                raise ValueError("Gold typed value differs from registry metadata")
            if self.value_type in {"NUMBER", "INTEGER"}:
                value = Decimal(self.value)
                if not value.is_finite() or self.value_type == "INTEGER" and value != int(value):
                    raise ValueError("Gold numbers must be finite and integers exact")
        elif any(
            v is not None for v in (self.attribute_key, self.value_type, self.value, self.unit)
        ):
            raise ValueError("Only mapped attributes have normalized gold")
        return self


class SourceDocument(Label):
    format: Literal["pdf"]
    path: str
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=1, le=2_000_000)


class TableCase(Label):
    id: str
    family: str
    note: str
    provenance: Literal["SYNTHETIC_AUTHORED", "ANONYMIZED_AUTHORIZED"]
    provenance_note: str = Field(min_length=1)
    source_document: SourceDocument | None = None
    sources: list[SourceFile] = Field(min_length=1, max_length=2)
    tables: list[GoldTable] = Field(max_length=8)
    claims: list[GoldClaim] = Field(max_length=320)

    @model_validator(mode="after")
    def references(self):
        tables = {t.id: t for t in self.tables}
        claims = {c.id: c for c in self.claims}
        roles = {s.role for s in self.sources}
        if (
            len(tables) != len(self.tables)
            or len(claims) != len(self.claims)
            or len(roles) != len(self.sources)
        ):
            raise ValueError("Duplicate gold/source identities")
        readings = [
            (c.table, tuple(c.cell) if c.cell is not None else None, c.kind, c.expression)
            for c in self.claims
        ]
        if len(set(readings)) != len(readings):
            raise ValueError("Gold source readings must be distinct")
        for t in self.tables:
            if t.role not in roles or any(c.role not in roles for c in t.cells):
                raise ValueError("Gold cites absent source")
        for c in self.claims:
            t = tables.get(c.table)
            cell = next((s for s in t.cells if s.position == c.cell), None) if t else None
            text = cell.text if cell else t.title if t and c.cell is None else None
            if not text or c.expression not in text:
                raise ValueError("Gold claim absent from declared source cell/caption")
            if c.equipment is not None:
                eq = claims.get(c.equipment)
                if not eq or eq.kind != "EQUIPMENT_MENTION" or eq.table != c.table:
                    raise ValueError("Gold association must name same-table equipment")
        return self


class TableCorpus(Label):
    version: Literal["table-corpus-v1"]
    cases: list[TableCase] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("Duplicate corpus cases")
        return self


def _verify_text(text, expression, span):
    if (
        expression not in text
        or span is not None
        and (
            len(span) != 2
            or not 0 <= span[0] < span[1] <= len(text)
            or text[slice(*span)] != expression
        )
    ):
        raise ValueError("Gold source occurrence differs from pinned text")


def load_table_corpus(path: Path):
    corpus = TableCorpus.model_validate(read_json(path))
    for case in corpus.cases:
        if case.source_document:
            source_bytes(path.parent, case.source_document)
        sources = sources_for(case, path.parent)
        for table in case.tables:
            if table.role == "native_text":
                if table.span is None:
                    raise ValueError("Native table gold requires an exact source occurrence")
                _verify_text(sources.text, table.anchor, table.span)
            elif table.span is not None:
                raise ValueError("Visual gold cannot claim text offsets")
            for cell in table.cells:
                if cell.role == "native_text" and cell.text:
                    if cell.span is None:
                        raise ValueError("Readable native cell gold requires an exact occurrence")
                    _verify_text(sources.text, cell.text, cell.span)
                elif cell.span is not None:
                    raise ValueError("Empty/visual cell gold cannot claim text offsets")
    return corpus, identity_hash(corpus.model_dump(mode="json"))


def resources():
    return {"manifest": identity_hash(table_manifest()), "grounding": table_identity()}


def evaluation_identity():
    root = files("powerforge_extraction")
    return identity_hash(
        {
            name: root.joinpath(name).read_text(encoding="utf-8")
            for name in (
                "table_evaluation.py",
                "table_evaluation_scoring.py",
                "table_eval.py",
                "evaluation.py",
                "evaluation_scoring.py",
            )
        }
    )


def replay(case: TableCase, root: Path, recorded: dict):
    sources = sources_for(case, root)
    sources = replace(
        sources,
        spec=replace(
            sources.spec, stage="TABLE_RECONSTRUCTION", unit_key="TABLE_RECONSTRUCTION:page:000001"
        ),
    )
    try:
        reconstruction = convert_table_reconstruction(recorded["reconstruction"], sources)
    except ValueError:
        return sources, [WorkUnitOutput()], ["TABLE_RECONSTRUCTION_INVALID_RESPONSE"]
    target = replace(
        sources,
        spec=replace(
            sources.spec,
            stage="TABLE_INTERPRETATION",
            unit_key="TABLE_INTERPRETATION:page:000001",
            unit_id=uuid5(sources.spec.run_id, "table-interpretation"),
        ),
    )
    if not reconstruction.tables:
        # Same production empty-table rule: no dependent model payload is interpreted.
        return sources, [reconstruction, WorkUnitOutput()], []
    try:
        context = context_from_output(target, reconstruction, sources.spec.unit_id)
        interpretation = convert_table_interpretation(recorded["interpretation"], target, context)
    except ValueError:
        return sources, [reconstruction], ["TABLE_INTERPRETATION_INVALID_RESPONSE"]
    return sources, [reconstruction, interpretation], []
