"""Verify source-only gold fixtures and optionally render private review overlays."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from pathlib import Path
from typing import Literal, Self

import pymupdf
from pydantic import BaseModel, ConfigDict, Field, model_validator

Box = tuple[int, int, int, int]
Legibility = Literal["LEGIBLE", "AMBIGUOUS", "UNREADABLE"]
FIXTURES = Path(__file__).with_name("ground_truth")
CORPUS = {
    "delta-transformer-drawing.pdf": 1,
    "eaton-panel-drawing.pdf": 1,
    "rex-transformer-drawing.pdf": 1,
    "schneider-panel-drawing.pdf": 1,
    "siemens-panel-drawing.pdf": 1,
    "simson-generator-drawing.pdf": 2,
}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Annotation(Contract):
    box: Box
    text: str | None
    legibility: Legibility = "LEGIBLE"
    note: str | None = None

    @model_validator(mode="after")
    def check_transcription(self) -> Self:
        if self.text is not None and not self.text.strip():
            raise ValueError("use null for non-text annotations")
        if self.legibility == "UNREADABLE" and self.text is not None:
            raise ValueError("unreadable content cannot claim a transcription")
        if (self.text is None or self.legibility != "LEGIBLE") and not self.note:
            raise ValueError("document non-text or uncertain annotations")
        return self


class Region(Annotation):
    id: str
    kind: Literal["identifier", "label", "value", "note", "diagram", "dimension"]

    @model_validator(mode="after")
    def check_non_text(self) -> Self:
        if self.text is None and self.legibility == "LEGIBLE" and self.kind != "diagram":
            raise ValueError("only diagram observations may be legible without a transcript")
        return self


class Cell(Annotation):
    row: int = Field(ge=0)
    row_end: int | None = Field(default=None, ge=0)
    column: str
    column_span: list[str] | None = None


class Table(Contract):
    id: str
    columns: list[str] = Field(min_length=1)
    cells: list[Cell] = Field(min_length=1)
    header_rows: list[int] = Field(default_factory=list)
    note: str | None = None

    @model_validator(mode="after")
    def check_grid(self) -> Self:
        if len(set(self.columns)) != len(self.columns) or any(
            not column.strip() for column in self.columns
        ):
            raise ValueError("columns must have distinct nonempty names")
        occupied = set()
        for cell in self.cells:
            if cell.column not in self.columns:
                raise ValueError(f"{self.id} has an unknown column")
            columns = cell.column_span if cell.column_span is not None else [cell.column]
            start_column = self.columns.index(cell.column)
            if not columns or columns != self.columns[start_column : start_column + len(columns)]:
                raise ValueError(f"{self.id} has a nonconsecutive column span")
            last_row = cell.row if cell.row_end is None else cell.row_end
            if not cell.row <= last_row < len(self.cells):
                raise ValueError(f"{self.id} has an invalid row interval")
            for row in range(cell.row, last_row + 1):
                for column in columns:
                    if (row, column) in occupied:
                        raise ValueError(f"{self.id} repeats grid position {row}/{column}")
                    occupied.add((row, column))
        rows = {row for row, _ in occupied}
        if rows != set(range(max(rows) + 1)) or not set(self.header_rows) <= rows:
            raise ValueError(f"{self.id} has missing rows or an unknown header row")
        if len(set(self.header_rows)) != len(self.header_rows):
            raise ValueError(f"{self.id} repeats a header row")
        return self


class Relation(Contract):
    source: str
    target: str
    observation: str = Field(min_length=1)


class Page(Contract):
    pdf_page: int = Field(ge=1)
    frame: tuple[int, int]
    printed_page: str | None = None
    regions: list[Region]
    tables: list[Table]
    relations: list[Relation] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_references(self) -> Self:
        ids = [item.id for item in (*self.regions, *self.tables)]
        if not ids or len(set(ids)) != len(ids) or any(not item.strip() for item in ids):
            raise ValueError(f"page {self.pdf_page} needs distinct nonempty annotation IDs")
        for relation in self.relations:
            if relation.source not in ids or relation.target not in ids:
                raise ValueError(f"page {self.pdf_page} relation has an unknown endpoint")
        width, height = self.frame
        if min(self.frame) <= 0:
            raise ValueError("frame dimensions must be positive")
        for _, annotation in self.annotations():
            x0, y0, x1, y1 = annotation.box
            if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                raise ValueError(f"page {self.pdf_page} annotation is outside the frame")
        return self

    def annotations(self):
        for region in self.regions:
            yield region.id, region
        for table in self.tables:
            for cell in table.cells:
                yield f"{table.id}/{cell.row}/{cell.column}", cell


class Fixture(Contract):
    version: Literal["f1a-source-gold-v1"]
    pdf: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pages: list[Page] = Field(min_length=1)


def pdf_rect(box: Box, frame: tuple[int, int], page: pymupdf.Page) -> pymupdf.Rect:
    x0, y0, x1, y1 = box
    width, height = frame
    # PDF drawing APIs accept unrotated points, while the gold frame is upright.
    rect = pymupdf.Rect(
        x0 / width * page.rect.width,
        y0 / height * page.rect.height,
        x1 / width * page.rect.width,
        y1 / height * page.rect.height,
    )
    return rect * page.derotation_matrix


def render_overlay(page: pymupdf.Page, gold: Page, image_path: Path) -> None:
    colors = {
        "LEGIBLE": (0, 0.55, 0.15),
        "AMBIGUOUS": (0.86, 0.40, 0),
        "UNREADABLE": (0.75, 0, 0.2),
    }
    index = []
    for number, (key, annotation) in enumerate(gold.annotations(), start=1):
        rect = pdf_rect(annotation.box, gold.frame, page)
        color = colors[annotation.legibility]
        page.draw_rect(rect, color=color, width=0.6, stroke_opacity=0.7)
        # Put the number at the top edge so that the source text remains visible.
        page.insert_text(rect.tl + (1, 4), str(number), fontsize=4, color=color)
        index.append(f"{number:>3} {key}\n")
    page.get_pixmap(dpi=200, alpha=False).save(image_path)
    image_path.with_suffix(".txt").write_text("".join(index), encoding="utf-8")


def verify(
    source_dir: Path, overlay_dir: Path | None, fixture_dir: Path = FIXTURES
) -> Counter[str]:
    fixtures = {}
    for fixture_path in sorted(fixture_dir.glob("*.json")):
        fixture = Fixture.model_validate_json(fixture_path.read_bytes())
        if fixture.pdf in fixtures or fixture_path.stem + ".pdf" != fixture.pdf:
            raise ValueError(f"duplicate or mismatched fixture name {fixture_path.name}")
        fixtures[fixture.pdf] = fixture
    if fixtures.keys() != CORPUS.keys():
        raise ValueError("fixture set differs from the declared F1-A corpus")

    if overlay_dir is not None:
        overlay_dir.mkdir(parents=True, exist_ok=True)
    totals: Counter[str] = Counter()
    for filename, page_count in CORPUS.items():
        fixture = fixtures[filename]
        path = source_dir / filename
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != fixture.sha256:
                raise ValueError(f"{filename} differs from the pinned PDF")
        with pymupdf.open(path) as doc:
            pages = [page.pdf_page for page in fixture.pages]
            if doc.page_count != page_count or pages != list(range(1, doc.page_count + 1)):
                raise ValueError(f"{filename} lacks complete PDF page coverage")
            counts: Counter[str] = Counter()
            for gold, page in zip(fixture.pages, doc, strict=True):
                expected_height = gold.frame[0] * page.rect.height / page.rect.width
                if abs(expected_height - gold.frame[1]) > 1:
                    raise ValueError(f"{filename} page {gold.pdf_page} frame aspect ratio differs")
                counts.update(annotation.legibility for _, annotation in gold.annotations())
                counts["regions"] += len(gold.regions)
                counts["tables"] += len(gold.tables)
                counts["cells"] += sum(len(table.cells) for table in gold.tables)
                counts["relations"] += len(gold.relations)
                if overlay_dir is not None:
                    overlay = overlay_dir / f"{path.stem}-{gold.pdf_page}.png"
                    render_overlay(page, gold, overlay)
            counts["pages"] = page_count
            totals.update(counts)
            print(f"{filename}: {dict(sorted(counts.items()))}")
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="directory containing the six original PDFs")
    parser.add_argument(
        "--overlay-dir", type=Path, help="optional private directory for review images"
    )
    args = parser.parse_args()
    totals = verify(args.source_dir, args.overlay_dir)
    print(f"Verified {len(CORPUS)} documents: {dict(sorted(totals.items()))}")


if __name__ == "__main__":
    main()
