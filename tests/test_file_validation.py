"""Unit tests for upload ingestion and content inspection (no DB, no storage)."""

from __future__ import annotations

import ast
import hashlib
import inspect
import io
import logging
from pathlib import Path

import pytest
from PIL import Image

from file_factory import PDF, jpeg_bytes, png_bytes, png_header_only, tiff_bytes
from powerforge_api.exceptions import (
    FileTooLarge,
    InvalidFileContent,
    UnsupportedDocumentType,
)
from powerforge_api.services import file_inspector
from powerforge_api.services.file_ingest import ingest_upload
from powerforge_api.services.file_inspector import FileInspector
from powerforge_document_model import FileFormat, build_storage_key

API_SOURCE = Path(__file__).resolve().parents[1] / "services" / "api" / "src" / "powerforge_api"
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 600_000_000


class CountingStream:
    """A lazy stream of zero bytes that records how much was actually read."""

    def __init__(self, total: int) -> None:
        self.remaining = total
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        n = self.remaining if size < 0 else min(size, self.remaining)
        self.remaining -= n
        self.bytes_read += n
        return b"\x00" * n


def run(data: bytes, filename: str, *, max_pixels: int = MAX_PIXELS):
    """Ingest then inspect, the way the upload service will."""
    with ingest_upload(io.BytesIO(data), filename, MAX_BYTES) as upload:
        result = FileInspector(max_pixels).inspect(upload.file, upload.extension)
        return upload, result


@pytest.mark.parametrize(
    ("data", "filename", "fmt", "mime"),
    [
        (PDF, "plan.pdf", FileFormat.PDF, "application/pdf"),
        (png_bytes(), "scan.png", FileFormat.PNG, "image/png"),
        (jpeg_bytes(), "photo.jpg", FileFormat.JPEG, "image/jpeg"),
        (jpeg_bytes(), "photo.JPEG", FileFormat.JPEG, "image/jpeg"),
        (tiff_bytes(), "scan.tif", FileFormat.TIFF, "image/tiff"),
        (tiff_bytes(), "scan.TIFF", FileFormat.TIFF, "image/tiff"),
        (tiff_bytes(pages=3), "multi.tiff", FileFormat.TIFF, "image/tiff"),
    ],
)
def test_valid_files_are_accepted_with_mime_derived_from_content(data, filename, fmt, mime) -> None:
    _, result = run(data, filename)
    assert result.file_format is fmt
    assert result.mime_type == mime


@pytest.mark.parametrize("filename", ["notes.txt", "payload.exe", "archive", "image.gif", ".pdf"])
def test_unsupported_extension_is_rejected_before_the_body_is_read(filename: str) -> None:
    stream = CountingStream(1024)
    with pytest.raises(UnsupportedDocumentType):
        ingest_upload(stream, filename, MAX_BYTES)
    assert stream.bytes_read == 0


@pytest.mark.parametrize(
    ("data", "filename"),
    [
        (b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 200, "setup.pdf"),
        (b"<html><script>alert(1)</script></html>", "image.png"),
        (png_bytes()[:40], "truncated.png"),
        (jpeg_bytes()[:5], "truncated.jpg"),
        (tiff_bytes()[:6], "truncated.tif"),
        (jpeg_bytes(), "wrong.png"),
        (png_bytes(), "wrong.pdf"),
        (PDF, "wrong.png"),
        (tiff_bytes(), "wrong.jpg"),
        (b"   \n\t  ", "blank.pdf"),
        (b"   \n\t  ", "blank.png"),
    ],
)
def test_invalid_or_mismatched_content_is_rejected(data: bytes, filename: str) -> None:
    with pytest.raises(InvalidFileContent):
        run(data, filename)


def test_known_limitation_truncated_jpeg_and_tiff_bodies_pass_header_validation() -> None:
    # Technical debt: verify() only walks PNG structure. JPEG and TIFF with an intact
    # header but a cut-off body are accepted because Phase 2 never decodes pixels
    # (Phase 3 does). If this test starts failing, the limitation was lifted: update docs.
    noisy = Image.effect_noise((200, 200), 80).convert("RGB")
    for fmt, name in [("JPEG", "cut.jpg"), ("TIFF", "cut.tif")]:
        buf = io.BytesIO()
        noisy.save(buf, fmt)
        data = buf.getvalue()
        _, result = run(data[: len(data) // 2], name)
        assert result.file_format is not FileFormat.PDF
    buf = io.BytesIO()
    noisy.save(buf, "PNG")
    with pytest.raises(InvalidFileContent):
        run(buf.getvalue()[: len(buf.getvalue()) // 2], "cut.png")


def test_empty_file_is_rejected() -> None:
    with pytest.raises(InvalidFileContent):
        ingest_upload(io.BytesIO(b""), "empty.pdf", MAX_BYTES)


def test_unusable_filename_is_invalid_file_content() -> None:
    with pytest.raises(InvalidFileContent):
        ingest_upload(io.BytesIO(PDF), "   ", MAX_BYTES)


def test_oversize_upload_stops_reading_early() -> None:
    chunk = 4096
    stream = CountingStream(1024 * 1024 * 1024)
    with pytest.raises(FileTooLarge):
        ingest_upload(stream, "huge.pdf", 10_000, chunk_size=chunk)
    assert stream.bytes_read <= 10_000 + chunk
    assert stream.remaining > 1024 * 1024 * 1000


def test_file_at_exactly_the_limit_is_accepted() -> None:
    data = PDF + b"\x00" * 100
    with ingest_upload(io.BytesIO(data), "limit.pdf", len(data)) as upload:
        assert upload.size == len(data)
    with pytest.raises(FileTooLarge):
        ingest_upload(io.BytesIO(data), "limit.pdf", len(data) - 1)


def test_memory_is_bounded_by_the_spool_threshold_not_file_size() -> None:
    data = PDF + b"\x00" * 50_000
    with ingest_upload(io.BytesIO(data), "big.pdf", MAX_BYTES, spool_max_bytes=1024) as upload:
        # SpooledTemporaryFile rolls over to a real file once it passes max_size.
        assert upload.file._rolled is True  # type: ignore[attr-defined]
    with ingest_upload(io.BytesIO(PDF), "small.pdf", MAX_BYTES, spool_max_bytes=1024) as upload:
        assert upload.file._rolled is False  # type: ignore[attr-defined]


def test_hash_size_and_rewind_over_multiple_chunks() -> None:
    data = PDF + bytes(range(256)) * 400
    with ingest_upload(io.BytesIO(data), "multi.pdf", MAX_BYTES, chunk_size=1000) as upload:
        assert upload.sha256 == hashlib.sha256(data).hexdigest()
        assert upload.size == len(data)
        assert upload.file.tell() == 0
        assert upload.file.read() == data


def test_inspect_rewinds_and_does_not_close_the_file() -> None:
    for data, name in [(PDF, "a.pdf"), (png_bytes(), "a.png"), (tiff_bytes(2), "a.tif")]:
        upload, _ = run(data, name)
        # run() closes the upload on exit; re-ingest to observe the open state.
        with ingest_upload(io.BytesIO(data), name, MAX_BYTES) as fresh:
            FileInspector(MAX_PIXELS).inspect(fresh.file, fresh.extension)
            assert not fresh.file.closed
            assert fresh.file.tell() == 0
            assert fresh.file.read() == data
        assert upload.sha256 == hashlib.sha256(data).hexdigest()


def test_inspect_rewinds_even_when_rejecting() -> None:
    buf = io.BytesIO(jpeg_bytes())
    with pytest.raises(InvalidFileContent):
        FileInspector(MAX_PIXELS).inspect(buf, ".png")
    assert buf.tell() == 0


def test_pixel_cap_is_enforced_from_the_header_without_decoding() -> None:
    data = png_header_only(40_000, 40_000)
    with pytest.raises(InvalidFileContent, match="dimensions"):
        run(data, "huge.png")


def test_pixel_cap_applies_to_real_images() -> None:
    data = png_bytes((20, 20))
    _, result = run(data, "ok.png", max_pixels=400)
    assert result.file_format is FileFormat.PNG
    with pytest.raises(InvalidFileContent, match="dimensions"):
        run(data, "big.png", max_pixels=399)


def test_images_between_pillow_default_and_our_cap_are_not_rejected_by_pillow() -> None:
    # 225M pixels is above Pillow's own 2x default (about 178M) but under our 600M cap.
    data = png_header_only(15_000, 15_000)
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (15_000, 15_000)
    with pytest.raises(InvalidFileContent) as excinfo:
        run(data, "scan.png")
    assert "dimensions" not in str(excinfo.value)


def test_decompression_bomb_error_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise Image.DecompressionBombError("too many pixels")

    monkeypatch.setattr(file_inspector.Image, "open", boom)
    with pytest.raises(InvalidFileContent):
        FileInspector(MAX_PIXELS).inspect(io.BytesIO(png_bytes()), ".png")


def test_filename_is_sanitized_and_never_part_of_a_storage_key() -> None:
    upload, _ = run(PDF, "C:\\evil\\..\\site/plan\u202e.PDF")
    assert upload.filename == "plan.PDF"
    assert upload.extension == ".pdf"
    params = inspect.signature(build_storage_key).parameters
    assert list(params) == ["project_id", "document_id", "extension"]


def test_errors_and_logs_never_contain_filename_or_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    secret_name = "confidential-substation-plan"
    secret_bytes = b"TOP-SECRET-BYTES"
    attempts = [
        (secret_bytes, f"{secret_name}.pdf"),
        (secret_bytes, f"{secret_name}.png"),
        (secret_bytes, f"{secret_name}.exe"),
        (b"", f"{secret_name}.pdf"),
    ]
    for data, name in attempts:
        with pytest.raises((InvalidFileContent, UnsupportedDocumentType)) as excinfo:
            run(data, name)
        assert secret_name not in str(excinfo.value)
        assert "TOP-SECRET" not in str(excinfo.value)
    with pytest.raises(FileTooLarge) as too_large:
        ingest_upload(io.BytesIO(PDF * 100), f"{secret_name}.pdf", 10)
    assert secret_name not in str(too_large.value)
    assert secret_name not in caplog.text
    assert "TOP-SECRET" not in caplog.text


def test_browser_content_type_is_not_an_input() -> None:
    for func in (ingest_upload, FileInspector.inspect, FileInspector.__init__):
        names = set(inspect.signature(func).parameters)
        assert not any("content_type" in n or "mime" in n for n in names)


def test_only_the_inspector_imports_pillow() -> None:
    offenders: list[str] = []
    for path in API_SOURCE.rglob("*.py"):
        if path == API_SOURCE / "services" / "file_inspector.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name.split(".")[0] == "PIL" for name in names):
                offenders.append(str(path.relative_to(API_SOURCE)))
    assert offenders == []
