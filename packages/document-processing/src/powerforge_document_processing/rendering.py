"""Turn original bytes into upright pages and artifact bytes.

This module does not touch the database or object storage. Nothing in the API
calls it yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

import fitz
from PIL import Image, ImageOps, UnidentifiedImageError, features

from powerforge_document_model import (
    FileFormat,
    ProcessingErrorCode,
    ProcessingProfile,
    SourceUnit,
    format_for_extension,
)

_POINTS_PER_INCH = 72
_EXIF_ORIENTATION = 274
_QUARTER_TURNS = {3: 180, 6: 270, 8: 90}
_WHITE = (255, 255, 255)


class RenderingFailed(Exception):
    """A source file could not be turned into pages. The message is concise."""

    def __init__(self, code: ProcessingErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """One logical page and the bytes a later step can store. Not a database row."""

    page_number: int
    source_width: float
    source_height: float
    source_unit: SourceUnit
    rotation_degrees: int
    native_text_char_count: int
    native_text: str | None
    analysis_png: bytes
    thumbnail: bytes
    width_px: int
    height_px: int
    effective_dpi: float | None


def render_pages(
    data: bytes,
    extension: str,
    profile: ProcessingProfile,
    max_image_pixels: int,
) -> list[RenderedPage]:
    """Render every logical page of a PDF, PNG, JPEG, or TIFF."""
    file_format = format_for_extension(extension)
    if file_format is FileFormat.PDF:
        return _render_pdf(data, profile)
    if file_format in {FileFormat.PNG, FileFormat.JPEG, FileFormat.TIFF}:
        return _render_image(data, profile, max_image_pixels)
    raise RenderingFailed(ProcessingErrorCode.UNSUPPORTED_SOURCE, "Unsupported source type")


def _render_pdf(data: bytes, profile: ProcessingProfile) -> list[RenderedPage]:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise RenderingFailed(ProcessingErrorCode.CORRUPT_PDF, "PDF could not be opened") from None
    try:
        if document.needs_pass:
            raise RenderingFailed(
                ProcessingErrorCode.PASSWORD_PROTECTED_PDF,
                "PDF is password protected",
            )
        if document.page_count < 1:
            raise RenderingFailed(ProcessingErrorCode.CORRUPT_PDF, "PDF has no pages")
        return [
            _render_pdf_page(document[index], index + 1, profile)
            for index in range(document.page_count)
        ]
    finally:
        document.close()


def _page_failed() -> RenderingFailed:
    return RenderingFailed(ProcessingErrorCode.PAGE_RENDER_FAILED, "PDF page could not be rendered")


def _render_pdf_page(page: fitz.Page, page_number: int, profile: ProcessingProfile) -> RenderedPage:
    rotation = int(page.rotation) % 360
    if rotation not in {0, 90, 180, 270}:
        raise _page_failed()
    rect = page.rect
    source_width = float(rect.width)
    source_height = float(rect.height)
    if source_width <= 0 or source_height <= 0:
        raise _page_failed()
    target_width = source_width * profile.target_dpi / _POINTS_PER_INCH
    target_height = source_height * profile.target_dpi / _POINTS_PER_INCH
    scale = _downscale(
        target_width,
        target_height,
        profile.max_long_edge_px,
        profile.max_total_pixels,
    )
    zoom = profile.target_dpi / _POINTS_PER_INCH * scale
    try:
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        analysis = pixmap.tobytes("png")
    except Exception:
        raise _page_failed() from None
    text = page.get_text("text").strip()
    native_text = text or None
    image = Image.open(BytesIO(analysis))
    try:
        thumbnail = _thumbnail_bytes(image, profile)
        width_px, height_px = image.size
    finally:
        image.close()
    return RenderedPage(
        page_number=page_number,
        source_width=source_width,
        source_height=source_height,
        source_unit=SourceUnit.POINTS,
        rotation_degrees=rotation,
        native_text_char_count=len(text),
        native_text=native_text,
        analysis_png=analysis,
        thumbnail=thumbnail,
        width_px=width_px,
        height_px=height_px,
        effective_dpi=profile.target_dpi * scale,
    )


def _render_image(
    data: bytes,
    profile: ProcessingProfile,
    max_image_pixels: int,
) -> list[RenderedPage]:
    previous_ceiling = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = max_image_pixels
    try:
        try:
            with Image.open(BytesIO(data)) as image:
                frame_count = image.n_frames if getattr(image, "format", None) == "TIFF" else 1
                return [
                    _render_image_frame(image, index, frame_count, profile, max_image_pixels)
                    for index in range(frame_count)
                ]
        except RenderingFailed:
            raise
        except Image.DecompressionBombError:
            raise RenderingFailed(
                ProcessingErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Image exceeds the pixel ceiling",
            ) from None
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
            raise RenderingFailed(
                ProcessingErrorCode.IMAGE_DECODE_FAILED,
                "Image could not be decoded",
            ) from None
    finally:
        Image.MAX_IMAGE_PIXELS = previous_ceiling


def _render_image_frame(
    image: Image.Image,
    index: int,
    frame_count: int,
    profile: ProcessingProfile,
    max_image_pixels: int,
) -> RenderedPage:
    if frame_count > 1:
        image.seek(index)
    image.load()
    frame = image.copy()
    if frame.width * frame.height > max_image_pixels:
        raise RenderingFailed(
            ProcessingErrorCode.RESOURCE_LIMIT_EXCEEDED,
            "Image exceeds the pixel ceiling",
        )
    rotation = 0
    if profile.normalize_orientation:
        rotation = _quarter_turn(frame)
        frame = ImageOps.exif_transpose(frame) or frame
    upright = _to_rgb(frame)
    source_width, source_height = upright.size
    source_dpi = _source_dpi(upright)
    scale = _downscale(
        source_width,
        source_height,
        profile.max_long_edge_px,
        profile.max_total_pixels,
    )
    if scale < 1:
        upright = upright.resize(
            (max(1, math.floor(source_width * scale)), max(1, math.floor(source_height * scale))),
            Image.Resampling.LANCZOS,
        )
    width_px, height_px = upright.size
    return RenderedPage(
        page_number=index + 1,
        source_width=float(source_width),
        source_height=float(source_height),
        source_unit=SourceUnit.PIXELS,
        rotation_degrees=rotation,
        native_text_char_count=0,
        native_text=None,
        analysis_png=_png_bytes(upright),
        thumbnail=_thumbnail_bytes(upright, profile),
        width_px=width_px,
        height_px=height_px,
        effective_dpi=None if source_dpi is None else source_dpi * scale,
    )


def _quarter_turn(image: Image.Image) -> int:
    try:
        orientation = image.getexif().get(_EXIF_ORIENTATION)
    except Exception:
        return 0
    if not isinstance(orientation, int):
        return 0
    return _QUARTER_TURNS.get(orientation, 0)


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    dpi = image.info.get("dpi")
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, _WHITE)
        background.paste(rgba, mask=rgba.getchannel("A"))
    else:
        background = image.convert("RGB")
    if dpi:
        background.info["dpi"] = dpi
    return background


def _source_dpi(image: Image.Image) -> float | None:
    dpi = image.info.get("dpi")
    if not isinstance(dpi, tuple) or not dpi or not dpi[0]:
        return None
    return float(dpi[0])


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _thumbnail_bytes(image: Image.Image, profile: ProcessingProfile) -> bytes:
    width, height = image.size
    longest = max(width, height)
    target = min(profile.thumbnail_long_edge_px, longest)
    if longest > target > 0:
        factor = target / longest
        image = image.resize(
            (max(1, math.floor(width * factor)), max(1, math.floor(height * factor))),
            Image.Resampling.LANCZOS,
        )
    buffer = BytesIO()
    image.save(buffer, format=_thumbnail_format(profile))
    return buffer.getvalue()


def _thumbnail_format(profile: ProcessingProfile) -> str:
    if profile.thumbnail_format == "webp" and features.check("webp"):
        return "WEBP"
    return "PNG"


def _downscale(width: float, height: float, max_long_edge: int, max_total_pixels: int) -> float:
    scale = 1.0
    long_edge = max(width, height)
    if long_edge > max_long_edge > 0:
        scale = min(scale, max_long_edge / long_edge)
    pixels = width * height
    if pixels > max_total_pixels > 0:
        scale = min(scale, math.sqrt(max_total_pixels / pixels))
    return scale
