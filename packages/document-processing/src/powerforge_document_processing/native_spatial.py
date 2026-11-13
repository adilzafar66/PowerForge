"""Bounded unsorted PyMuPDF readings; no registry, lifecycle or structure inference."""

import hashlib
import math
from dataclasses import dataclass
from importlib import import_module
from importlib.resources import files
from pathlib import Path

import pymupdf

from powerforge_provenance.spatial_base import POLICY

NATIVE_PRIMITIVE_LIMIT = "NATIVE_DRAWING_PRIMITIVE_LIMIT"


@dataclass(frozen=True)
class NativeReading:
    text: str
    box: tuple[str, str, str, str] | None
    line: int
    block: int
    direction: tuple[str, str]


@dataclass(frozen=True)
class NativePage:
    width: str
    height: str
    source_width: str
    source_height: str
    rotation: int
    readings: tuple[NativeReading, ...]
    primitives: tuple[tuple[tuple[str, str], ...], ...]
    raster_boxes: tuple[tuple[str, str, str, str], ...]
    replacement_characters: int
    characters: int
    drawing_limitation: str | None = None


def native_identity():
    return dict(
        version="native-pymupdf-v2",
        engine_version=pymupdf.VersionBind,
        build_sha256=hashlib.sha256(
            Path(import_module("pymupdf._mupdf").__file__).read_bytes()
        ).hexdigest(),
        rules_sha256=hashlib.sha256(
            files("powerforge_document_processing").joinpath("native_spatial.py").read_bytes()
        ).hexdigest(),
    )


def exact(value):
    if not math.isfinite(value):
        raise ValueError("Nonfinite native coordinate")
    # MuPDF returns single-precision coordinates; retain their decimal representation.
    return str(value)


def extract_native(data: bytes, page_number: int) -> NativePage:
    if len(data) > 262_144_000:
        raise ValueError("Original exceeds document bound")
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass or not 1 <= page_number <= len(doc):
            raise ValueError("Unavailable PDF page")
        page = doc[page_number - 1]
        rotation = page.rotation
        width, height = page.rect.width, page.rect.height
        source_width, source_height = (height, width) if rotation in (90, 270) else (width, height)
        flags = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        raw = page.get_text("rawdict", flags=flags, sort=False)
        readings = []
        line_index = 0
        characters = 0
        replacements = 0
        for block_index, block in enumerate(raw["blocks"]):
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                direction = tuple(exact(v) for v in line["dir"])
                for span in line["spans"]:
                    chars = span["chars"]
                    characters += sum(len(c["c"]) for c in chars)
                    if characters > POLICY["max_text_characters"]:
                        raise ValueError("Native character bound exceeded")
                    replacements += sum(c["c"].count("\ufffd") for c in chars)
                    group = []

                    def emit(group, line_index, block_index, direction):
                        if not group:
                            return
                        text = "".join(c["c"] for c in group)
                        x0 = min(c["bbox"][0] for c in group)
                        y0 = min(c["bbox"][1] for c in group)
                        x1 = max(c["bbox"][2] for c in group)
                        y1 = max(c["bbox"][3] for c in group)
                        box = None
                        if 0 <= x0 < x1 <= source_width and 0 <= y0 < y1 <= source_height:
                            box = tuple(exact(v) for v in (x0, y0, x1 - x0, y1 - y0))
                        readings.append(
                            NativeReading(text, box, line_index, block_index, direction)
                        )
                        if len(readings) > POLICY["max_tokens"]:
                            raise ValueError("Native token bound exceeded")

                    for char in chars:
                        if char["c"].isspace():
                            emit(group, line_index, block_index, direction)
                            group = []
                        else:
                            group.append(char)
                    emit(group, line_index, block_index, direction)
                line_index += 1
                if line_index > POLICY["max_lines"]:
                    raise ValueError("Native line bound exceeded")
        # Drawings are candidates only. Curves, fills and unsupported paths make no primitives.
        primitives, drawing_limitation = drawing_primitives(page, source_width, source_height)
        images = page.get_image_info()
        if len(images) > 2048:
            raise ValueError("Native embedded image bound exceeded")
        raster_boxes = tuple(tuple(exact(v) for v in info["bbox"]) for info in images)
        return NativePage(
            exact(width),
            exact(height),
            exact(source_width),
            exact(source_height),
            rotation,
            tuple(readings),
            primitives,
            raster_boxes,
            replacements,
            characters,
            drawing_limitation,
        )


def drawing_primitives(page, source_width, source_height):
    primitives = []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                points = [item[1], item[2]]
            elif item[0] == "re":
                r = item[1]
                points = [r.tl, r.tr, r.br, r.bl]
            else:
                continue
            if all(0 <= p.x <= source_width and 0 <= p.y <= source_height for p in points) and len(
                set((p.x, p.y) for p in points)
            ) == len(points):
                if len(primitives) == POLICY["max_native_primitives"]:
                    # A prefix could create apparently closed grids or omit conflicting paths.
                    return (), NATIVE_PRIMITIVE_LIMIT
                primitives.append(tuple((exact(p.x), exact(p.y)) for p in points))
    return tuple(primitives), None


def rasterize_pdf(data: bytes, page_number: int) -> tuple[bytes, int, int]:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        page = doc[page_number - 1]
        width, height = page.rect.width, page.rect.height
        scale = min(300 / 72, math.sqrt((POLICY["max_raster_pixels"] - 20000) / (width * height)))
        pix = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale), alpha=False, colorspace=pymupdf.csRGB
        )
        data = pix.tobytes("png")
        if (
            pix.width * pix.height > POLICY["max_raster_pixels"]
            or len(data) > POLICY["max_raster_bytes"]
        ):
            raise ValueError("OCR raster exceeds pinned bounds")
        return data, pix.width, pix.height


def eligibility(native: NativePage | None, force: bool) -> tuple[bool, str]:
    if force:
        return True, "EXPLICIT_WHOLE_PAGE"
    if native is None or not native.readings:
        return True, "NO_NATIVE_READINGS"
    if native.replacement_characters * 100 >= max(1, native.characters):
        return True, "NATIVE_REPLACEMENT_RATE_AT_LEAST_1_PERCENT"
    if native.raster_boxes:
        # Unknown image content is not a measured text-coverage denominator.
        return False, "UNKNOWN_RASTER_CONTENT_EXPLICIT_SELECTION_REQUIRED"
    return False, "NATIVE_READINGS_PRESENT_NO_RASTER_OBSERVED"
