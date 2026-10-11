"""Page rendering. Fixtures are built in-test. No database."""

from __future__ import annotations

import ast
import tempfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from PIL import Image

from powerforge_document_model import (
    DEFAULT_PROFILE,
    ProcessingErrorCode,
    ProcessingProfile,
    SourceUnit,
)
from powerforge_document_processing.rendering import (
    RenderedPage,
    RenderingFailed,
    open_rendered_pages,
)

MAX_IMAGE_PIXELS = 600_000_000
API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api" / "src" / "powerforge_api"
PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "document-processing"
    / "src"
    / "powerforge_document_processing"
)
OCR_ROOTS = frozenset({"pytesseract", "tesseract", "easyocr", "paddleocr", "cv2"})


def _pdf(pages: list[tuple[str, int]], *, width: float = 200, height: float = 100) -> bytes:
    document = fitz.open()
    try:
        for text, rotation in pages:
            page = document.new_page(width=width, height=height)
            if text:
                page.insert_text((36, 36), text)
            if rotation:
                page.set_rotation(rotation)
        return document.tobytes()
    finally:
        document.close()


def _image_only_pdf() -> bytes:
    document = fitz.open()
    try:
        page = document.new_page(width=200, height=100)
        page.draw_rect(fitz.Rect(10, 10, 40, 40), color=(0, 0, 0), fill=(0, 0, 0))
        return document.tobytes()
    finally:
        document.close()


def _encrypted_pdf() -> bytes:
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "secret")
        return document.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="secret",
            owner_pw="owner",
        )
    finally:
        document.close()


def _save_image(image: Image.Image, image_format: str, **options: object) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()


def _render(
    data: bytes,
    extension: str,
    profile: ProcessingProfile = DEFAULT_PROFILE,
    *,
    max_image_pixels: int = MAX_IMAGE_PIXELS,
    max_pages: int = 1000,
) -> list[RenderedPage]:
    with tempfile.NamedTemporaryFile(suffix=extension) as handle:
        handle.write(data)
        handle.flush()
        with open_rendered_pages(
            handle.name,
            extension,
            profile,
            max_image_pixels,
            max_pages,
        ) as source:
            return list(source)


def _expect_failure(data: bytes, extension: str, code: ProcessingErrorCode) -> None:
    with pytest.raises(RenderingFailed) as caught:
        _render(data, extension)
    assert caught.value.code is code
    assert "Traceback" not in str(caught.value)


def test_single_page_pdf_extracts_text() -> None:
    pages = _render(_pdf([("hello", 0)]), ".pdf")
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].native_text == "hello"
    assert pages[0].native_text_char_count == len("hello")
    assert pages[0].source_unit is SourceUnit.POINTS


def test_multipage_pdf_keeps_order() -> None:
    pages = _render(_pdf([("alpha", 0), ("beta", 0), ("gamma", 0)]), ".pdf")
    assert [page.native_text for page in pages] == ["alpha", "beta", "gamma"]
    assert [page.page_number for page in pages] == [1, 2, 3]


def test_image_only_pdf_has_no_text() -> None:
    page = _render(_image_only_pdf(), ".pdf")[0]
    assert page.native_text is None
    assert page.native_text_char_count == 0


def test_whitespace_only_pdf_text_is_empty() -> None:
    page = _render(_pdf([("   \n\t  ", 0)]), ".pdf")[0]
    assert page.native_text is None
    assert page.native_text_char_count == 0


def test_rotated_pdf_stores_upright_points() -> None:
    page = _render(_pdf([("turned", 90)]), ".pdf")[0]
    assert page.rotation_degrees == 90
    assert page.source_width == pytest.approx(100)
    assert page.source_height == pytest.approx(200)


def test_corrupt_pdf_fails_with_named_code() -> None:
    _expect_failure(b"this is not a pdf", ".pdf", ProcessingErrorCode.CORRUPT_PDF)


def test_password_protected_pdf_fails_without_the_library_text() -> None:
    with pytest.raises(RenderingFailed) as caught:
        _render(_encrypted_pdf(), ".pdf")
    assert caught.value.code is ProcessingErrorCode.PASSWORD_PROTECTED_PDF
    message = str(caught.value)
    assert "Traceback" not in message
    assert "secret" not in message


def test_png_and_jpeg_are_one_page() -> None:
    image = Image.new("RGB", (30, 20), (10, 20, 30))
    for extension, image_format in ((".png", "PNG"), (".jpg", "JPEG")):
        pages = _render(_save_image(image, image_format), extension)
        assert len(pages) == 1
        assert pages[0].source_unit is SourceUnit.PIXELS
        assert pages[0].native_text is None
        assert pages[0].native_text_char_count == 0
        assert (pages[0].source_width, pages[0].source_height) == (30, 20)


def test_exif_orientation_6_is_transposed() -> None:
    image = Image.new("RGB", (40, 10), (255, 0, 0))
    exif = Image.Exif()
    exif[274] = 6
    page = _render(_save_image(image, "JPEG", exif=exif.tobytes()), ".jpg")[0]
    assert page.rotation_degrees == 270
    assert (page.source_width, page.source_height) == (10, 40)


def test_single_and_multipage_tiff() -> None:
    frame = Image.new("RGB", (12, 8), (0, 0, 0))
    assert len(_render(_save_image(frame, "TIFF"), ".tif")) == 1
    frames = [Image.new("RGB", (12, 8), color) for color in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    data = _save_image(frames[0], "TIFF", save_all=True, append_images=frames[1:])
    pages = _render(data, ".tiff")
    assert [page.page_number for page in pages] == [1, 2, 3]
    assert all(page.native_text is None for page in pages)


def test_malformed_image_fails() -> None:
    _expect_failure(b"not an image", ".png", ProcessingErrorCode.IMAGE_DECODE_FAILED)


def test_webp_profile_fails_when_webp_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "powerforge_document_processing.rendering.features.check",
        lambda _feature: False,
    )
    with pytest.raises(RenderingFailed) as caught:
        _render(_pdf([("hello", 0)]), ".pdf")
    assert caught.value.code is ProcessingErrorCode.PAGE_RENDER_FAILED
    assert str(caught.value) == "WebP thumbnails are not available"
    assert "Traceback" not in str(caught.value)

    png_profile = replace(DEFAULT_PROFILE, thumbnail_format="png")
    page = _render(_pdf([("hello", 0)]), ".pdf", png_profile)
    assert page[0].thumbnail.startswith(b"\x89PNG")


def test_png_profile_writes_png() -> None:
    profile = replace(DEFAULT_PROFILE, thumbnail_format="png")
    page = _render(_pdf([("hello", 0)]), ".pdf", profile)[0]
    assert page.thumbnail.startswith(b"\x89PNG")


def test_every_successful_page_has_analysis_and_thumbnail() -> None:
    pages = _render(_pdf([("one", 0), ("two", 0)]), ".pdf")
    for page in pages:
        assert page.analysis_png.startswith(b"\x89PNG")
        assert page.thumbnail.startswith(b"RIFF")
        assert page.thumbnail[8:12] == b"WEBP"
        assert page.width_px > 0
        assert page.height_px > 0


def test_oversized_pdf_and_image_are_scaled_down() -> None:
    profile = replace(DEFAULT_PROFILE, max_long_edge_px=40, target_dpi=200)
    pdf_page = _render(_pdf([("big", 0)], width=144, height=72), ".pdf", profile)[0]
    assert max(pdf_page.width_px, pdf_page.height_px) <= 40
    assert pdf_page.effective_dpi is not None
    assert pdf_page.effective_dpi < profile.target_dpi

    image = Image.new("RGB", (400, 200), (0, 0, 0))
    image_page = _render(_save_image(image, "PNG", dpi=(100, 100)), ".png", profile)[0]
    assert max(image_page.width_px, image_page.height_px) <= 40
    assert image_page.effective_dpi == pytest.approx(10, abs=0.01)
    assert (image_page.source_width, image_page.source_height) == (400, 200)


def test_pixel_ceiling_rejects_a_small_png_and_the_phase2_cap_accepts_it() -> None:
    data = _save_image(Image.new("RGB", (20, 20), (1, 2, 3)), "PNG")
    with pytest.raises(RenderingFailed) as caught:
        _render(data, ".png", max_image_pixels=100)
    assert caught.value.code is ProcessingErrorCode.RESOURCE_LIMIT_EXCEEDED
    page = _render(data, ".png")[0]
    assert (page.width_px, page.height_px) == (20, 20)


def test_pdf_over_the_page_ceiling_yields_nothing() -> None:
    data = _pdf([("a", 0), ("b", 0), ("c", 0)])
    with pytest.raises(RenderingFailed) as caught:
        _render(data, ".pdf", max_pages=2)
    assert caught.value.code is ProcessingErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert "Traceback" not in str(caught.value)


def test_tiff_over_the_page_ceiling_yields_nothing() -> None:
    frames = [Image.new("RGB", (8, 8), color) for color in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    data = _save_image(frames[0], "TIFF", save_all=True, append_images=frames[1:])
    with pytest.raises(RenderingFailed) as caught:
        _render(data, ".tiff", max_pages=2)
    assert caught.value.code is ProcessingErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert "Traceback" not in str(caught.value)


def test_package_does_not_import_ocr_and_api_does_not_call_the_renderer() -> None:
    for path in PACKAGE_ROOT.rglob("*.py"):
        roots = _roots(path)
        assert not (roots & OCR_ROOTS), path.name
    for path in API_ROOT.rglob("*.py"):
        roots = _roots(path)
        assert "fitz" not in roots
        text = path.read_text(encoding="utf-8")
        assert "powerforge_document_processing.rendering" not in text


def _roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return {module.split(".", 1)[0] for module in modules}
