"""Spatial layout v1: source-local relationships, never engineering identities or meaning."""

import hashlib
import json
from importlib.resources import files
from types import MappingProxyType
from typing import Literal, get_args
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from powerforge_provenance.spatial_base import (
    SHA256,
    LocalRef,
    SpatialContract,
    bounded_json,
    identity_hash,
)
from powerforge_provenance.spatial_geometry import NormalizedRegion
from powerforge_provenance.spatial_layout import EnrichmentResultRef, SourceSupport
from powerforge_provenance.spatial_sources import PageOwner

_policy = json.loads(
    files("powerforge_provenance").joinpath("resources/layout_v1.json").read_text()
)
LAYOUT_POLICY = MappingProxyType({**_policy, "header_words": tuple(_policy["header_words"])})
del _policy

Basis = Literal[
    "NATIVE_GEOMETRY_SUPPORTED", "OCR_GEOMETRY_SUPPORTED", "MIXED_GEOMETRY_SUPPORTED", "UNRESOLVED"
]
StructuralLimit = Literal[
    "NATIVE_DRAWING_PRIMITIVE_LIMIT",
    "NATIVE_GRID_SEGMENT_LIMIT",
    "NATIVE_GRID_COMPONENT_LIMIT",
    "TABLE_SUPPORT_LIMIT",
    "TABLE_PARTITION_LIMIT",
    "TABLE_LAYOUT_LIMIT",
]
STRUCTURAL_LIMITS = frozenset(get_args(StructuralLimit))


class LayoutReading(SpatialContract):
    ref: LocalRef
    members: tuple[SourceSupport, ...] = Field(min_length=1, max_length=8)
    preferred: SourceSupport
    region: NormalizedRegion | None
    issues: tuple[
        Literal[
            "MISSING_GEOMETRY",
            "UNSUPPORTED_DIRECTION",
            "TRANSCRIPTION_CONFLICT",
            "AMBIGUOUS_OVERLAP",
            "NATIVE_REPLACEMENT",
            "NATIVE_PREFERRED_UNALIGNED",
        ],
        ...,
    ] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def distinct(self):
        if (
            self.preferred not in self.members
            or len(set(self.members)) != len(self.members)
            or any(m.kind != "TOKEN" for m in self.members)
        ):
            raise ValueError(
                "Reading requires distinct exact token occurrences and one preferred member"
            )
        return self


class ReadingOverlap(SpatialContract):
    left: SourceSupport
    right: SourceSupport
    kind: Literal["AGREEMENT", "CONFLICT", "AMBIGUOUS"]


class ReadingOrder(SpatialContract):
    before: LocalRef
    after: LocalRef
    basis: Literal["SAME_BASELINE", "TABLE_ROW", "TABLE_COLUMN"]


class LayoutCell(SpatialContract):
    ref: LocalRef
    row: int = Field(ge=0, lt=128)
    column: int = Field(ge=0, lt=32)
    row_span: int = Field(default=1, ge=1, le=128)
    column_span: int = Field(default=1, ge=1, le=32)
    region: NormalizedRegion
    readings: tuple[LocalRef, ...] = Field(max_length=512)
    boundary_support: tuple[SourceSupport, ...] = Field(default=(), max_length=512)
    header_role: Literal["COLUMN", "UNRESOLVED"] = "UNRESOLVED"
    headers: tuple[LocalRef, ...] = Field(default=(), max_length=8)
    state: Literal["READINGS", "NO_READINGS", "UNCERTAIN"]


class LayoutTable(SpatialContract):
    ref: LocalRef
    region: NormalizedRegion
    method: Literal["NATIVE_RULED", "REPEATED_ALIGNMENT"]
    structure_basis: Basis
    header_basis: Literal["GEOMETRIC_LABEL_HEADER", "UNRESOLVED"]
    rows: int = Field(ge=2, le=128)
    columns: int = Field(ge=2, le=32)
    cells: tuple[LayoutCell, ...] = Field(min_length=1, max_length=512)
    captions: tuple[LocalRef, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def partition(self):
        refs = {c.ref for c in self.cells}
        occupied = set()
        used = set()
        if len(refs) != len(self.cells):
            raise ValueError("Duplicate cell alias")
        for cell in self.cells:
            if (
                cell.row + cell.row_span > self.rows
                or cell.column + cell.column_span > self.columns
            ):
                raise ValueError("Cell exceeds the table partition")
            slots = {
                (r, c)
                for r in range(cell.row, cell.row + cell.row_span)
                for c in range(cell.column, cell.column + cell.column_span)
            }
            if (
                slots & occupied
                or set(cell.readings) & used
                or len(set(cell.readings)) != len(cell.readings)
            ):
                raise ValueError("Overlapping cells or duplicated reading ownership")
            occupied |= slots
            used.update(cell.readings)
            if not set(cell.headers) <= refs or cell.ref in cell.headers:
                raise ValueError("Foreign/self header reference")
            for header_ref in cell.headers:
                header = next(c for c in self.cells if c.ref == header_ref)
                if (
                    header.header_role != "COLUMN"
                    or header.row + header.row_span > cell.row
                    or not (
                        header.column <= cell.column
                        and cell.column + cell.column_span <= header.column + header.column_span
                    )
                ):
                    raise ValueError("Header path does not cover this cell from above")
        if len(occupied) != self.rows * self.columns:
            raise ValueError("A geometric partition must not silently fill missing cells")
        return self


class UnresolvedLayout(SpatialContract):
    region: NormalizedRegion | None
    reason: (
        StructuralLimit
        | Literal[
            "OPEN_OR_IRREGULAR_GRID",
            "AMBIGUOUS_ASSIGNMENT",
            "OVERLAPPING_TABLES",
            "UNSUPPORTED_HEADER",
            "COMPETING_PARTITIONS",
            "UNSUPPORTED_ALIGNMENT",
        ]
    )
    support: tuple[SourceSupport, ...] = Field(max_length=512)

    @model_validator(mode="after")
    def page_scope_for_limits(self):
        if self.reason in STRUCTURAL_LIMITS and (self.region is not None or self.support):
            raise ValueError("Page-wide structure limits cannot assert region or geometry support")
        return self


class SpatialLayout(SpatialContract):
    version: Literal["source-spatial-layout-v1"] = "source-spatial-layout-v1"
    id: UUID
    owner: PageOwner
    producer_run_id: UUID
    producer_work_unit_id: UUID
    algorithm_sha256: SHA256
    prepared: EnrichmentResultRef
    readings: tuple[LayoutReading, ...] = Field(max_length=LAYOUT_POLICY["max_readings"])
    overlaps: tuple[ReadingOverlap, ...] = Field(max_length=LAYOUT_POLICY["max_overlap_pairs"])
    order: tuple[ReadingOrder, ...] = Field(max_length=LAYOUT_POLICY["max_edges"])
    tables: tuple[LayoutTable, ...] = Field(max_length=LAYOUT_POLICY["max_tables"])
    unresolved: tuple[UnresolvedLayout, ...] = Field(max_length=64)
    printed_text_independently_verified: Literal[False] = False

    @field_validator("printed_text_independently_verified", mode="before")
    @classmethod
    def boolean_marker(cls, value):
        if type(value) is not bool:
            raise ValueError("Reading verification requires a boolean")
        return value

    @model_validator(mode="after")
    def references(self):
        if (
            self.prepared.owner != self.owner
            or self.prepared.result_kind != "PREPARED"
            or self.prepared.id == self.id
        ):
            raise ValueError("Layout requires an exact distinct owned preparation result")
        refs = {r.ref for r in self.readings}
        members = [m for r in self.readings for m in r.members]
        member_set = set(members)
        if len(refs) != len(self.readings) or len(member_set) != len(members):
            raise ValueError("Duplicate reading or source occurrence")
        if (
            len({t.ref for t in self.tables}) != len(self.tables)
            or sum(len(t.cells) for t in self.tables) > LAYOUT_POLICY["max_cells"]
        ):
            raise ValueError("Duplicate table or aggregate cell overflow")
        if any(r.reason in STRUCTURAL_LIMITS for r in self.unresolved) and (
            self.tables or any(edge.basis != "SAME_BASELINE" for edge in self.order)
        ):
            raise ValueError("Unresolved page structure cannot carry table claims")
        all_owned = {r for table in self.tables for cell in table.cells for r in cell.readings}
        used = set()
        for table in self.tables:
            owned = {r for c in table.cells for r in c.readings}
            if (
                not owned <= refs
                or owned & used
                or not set(table.captions) <= refs
                or set(table.captions) & all_owned
            ):
                raise ValueError("Foreign or multiply owned table readings")
            used |= owned
        graph = {r: set() for r in refs}
        predecessors = {r: 0 for r in refs}
        for edge in self.order:
            if edge.before not in refs or edge.after not in refs or edge.before == edge.after:
                raise ValueError("Foreign/self reading order")
            if edge.after not in graph[edge.before]:
                graph[edge.before].add(edge.after)
                predecessors[edge.after] += 1
        ready = [ref for ref, count in predecessors.items() if count == 0]
        visited = 0
        while ready:
            ref = ready.pop()
            visited += 1
            for after in graph[ref]:
                predecessors[after] -= 1
                if predecessors[after] == 0:
                    ready.append(after)
        if visited != len(refs):
            raise ValueError("Cyclic reading order")
        for pair in self.overlaps:
            if (
                pair.left not in member_set
                or pair.right not in member_set
                or pair.left == pair.right
            ):
                raise ValueError("Overlap outside the selected source occurrences")
        bounded_json(self, LAYOUT_POLICY["max_manifest_bytes"])
        return self

    @property
    def identity_hash(self):
        return identity_hash(self.model_dump(mode="json"))


def layout_contract_identity():
    root = files("powerforge_provenance")
    return dict(
        version="source-spatial-layout-v1",
        rules_hash=hashlib.sha256(root.joinpath("layout_observations.py").read_bytes()).hexdigest(),
        policy_sha256=hashlib.sha256(
            root.joinpath("resources/layout_v1.json").read_bytes()
        ).hexdigest(),
        schema_sha256=identity_hash(SpatialLayout.model_json_schema()),
    )
