"""Independent gold schema and immutable corpus input boundary for spatial evaluation v1."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from powerforge_extraction.enrichment_prepare import sha

VERSION = "spatial-extraction-evaluation-v1"
MAX_SOURCE_BYTES = 25 * 1024 * 1024
Box = tuple[float, float, float, float]
Slot = tuple[int, int]


class Gold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def valid_box(box: Box) -> bool:
    x0, y0, x1, y1 = box
    return 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


class Word(Gold):
    id: str
    text: str = Field(min_length=1)
    box: Box
    basis: Literal["NATIVE_PDF", "OCR"]
    categories: list[Literal["tag", "value", "unit", "punctuation"]]
    printed: bool = True

    @model_validator(mode="after")
    def bounds(self):
        if not valid_box(self.box) or (not self.printed and self.basis != "NATIVE_PDF"):
            raise ValueError("Invalid word geometry or hidden source designation")
        return self


class Line(Gold):
    id: str
    words: list[str] = Field(min_length=1)
    order: bool = True


class Cell(Gold):
    position: Slot
    span: Slot
    line: str | None
    headers: list[Slot]


class Table(Gold):
    id: str
    box: Box
    rows: int = Field(ge=2, le=128)
    columns: int = Field(ge=2, le=32)
    cells: list[Cell] = Field(min_length=1, max_length=512)
    factors: list[
        Literal[
            "ruled",
            "irregular_gaps",
            "sparse",
            "four_columns",
            "hierarchical",
            "merged",
            "mixed_orientation",
            "qualified_header",
        ]
    ]

    @model_validator(mode="after")
    def grid(self):
        slots = set()
        starts = {cell.position for cell in self.cells}
        if not valid_box(self.box) or len(starts) != len(self.cells):
            raise ValueError("Invalid gold table geometry or repeated cell")
        for cell in self.cells:
            row, column = cell.position
            height, width = cell.span
            coverage = {
                (r, c) for r in range(row, row + height) for c in range(column, column + width)
            }
            if (
                not (
                    0 <= row < row + height <= self.rows
                    and 0 <= column < column + width <= self.columns
                )
                or coverage & slots
                or not set(cell.headers) <= starts - {cell.position}
            ):
                raise ValueError("Invalid gold cell partition or headers")
            slots.update(coverage)
        if len(slots) != self.rows * self.columns:
            raise ValueError("Gold partition must declare blank cells")
        return self


class Claim(Gold):
    id: str
    line: str
    kind: Literal["EQUIPMENT_MENTION", "ATTRIBUTE_VALUE"]
    equipment_type: str | None
    tag: str | None
    attribute: str | None
    value_type: Literal["NUMBER", "INTEGER", "TEXT", "ENUM", "BOOLEAN"] | None
    value: str | bool | None
    unit: str | None
    status: Literal["MAPPED", "UNMAPPED", "INVALID"]
    owner: str | None


class Case(Gold):
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,60}$")]
    source: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    size_bytes: int = Field(gt=0, le=MAX_SOURCE_BYTES)
    page: int = Field(ge=1, le=50)
    ocr_gold: bool
    force_ocr: bool
    note: str
    baseline: Literal["table-pdf", "prose-native", "prose-image"] | None = None
    conflicts: list[tuple[str, str]] = Field(default_factory=list)
    words: list[Word] = Field(max_length=3000)
    lines: list[Line] = Field(max_length=1000)
    tables: list[Table] = Field(max_length=8)
    claims: list[Claim] = Field(max_length=256)

    @model_validator(mode="after")
    def references(self):
        words = {word.id for word in self.words}
        lines = {line.id for line in self.lines}
        equipment = {c.id for c in self.claims if c.kind == "EQUIPMENT_MENTION"}
        owned = [word for line in self.lines for word in line.words]
        if (
            len(words) != len(self.words)
            or len(lines) != len(self.lines)
            or len({c.id for c in self.claims}) != len(self.claims)
            or len({(c.line, c.kind) for c in self.claims}) != len(self.claims)
            or len({t.id for t in self.tables}) != len(self.tables)
            or set(owned) != words
            or len(owned) != len(words)
            or any(c.line not in lines or c.owner and c.owner not in equipment for c in self.claims)
            or any(c.line and c.line not in lines for t in self.tables for c in t.cells)
            or any({left, right} - words or left == right for left, right in self.conflicts)
        ):
            raise ValueError("Duplicate or unresolved gold source occurrence")
        return self


class Corpus(Gold):
    version: Literal["spatial-extraction-corpus-v1"]
    provenance: Literal["SYNTHETIC_AUTHORED"]
    cases: list[Case] = Field(min_length=1, max_length=100)


def load_cases(path: Path, source_root: Path, selection: list[str] | None):
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Corpus metadata exceeds bound")
    data = path.read_bytes()
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("Corpus metadata exceeds bound")
    corpus = Corpus.model_validate_json(data)
    ids = {case.id for case in corpus.cases}
    if len(ids) != len(corpus.cases) or (
        selection is not None
        and (not selection or set(selection) - ids or len(selection) != len(set(selection)))
    ):
        raise ValueError("Duplicate or unknown corpus selection")
    cases = []
    for case in corpus.cases:
        if selection is not None and case.id not in selection:
            continue
        root = source_root.resolve()
        file = (root / case.source).resolve()
        if (
            not file.is_relative_to(root)
            or file.suffix.lower() not in {".pdf", ".png", ".tiff"}
            or file.stat().st_size != case.size_bytes
        ):
            raise ValueError(f"Corpus source path, type or size differs for {case.id}")
        cases.append((case, file))
    return cases, sha(data)


def read_source(case: Case, file: Path) -> bytes:
    with file.open("rb") as stream:
        data = stream.read(case.size_bytes + 1)
    if len(data) != case.size_bytes or sha(data) != case.sha256:
        raise ValueError(f"Corpus source digest differs for {case.id}")
    return data
