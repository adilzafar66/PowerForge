"""Pure document-domain vocabulary and validation (PR-02)."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from powerforge_document_model import (
    MIME_TYPES,
    SUPPORTED_FORMATS,
    DocumentClassification,
    DocumentOrigin,
    FileFormat,
    InvalidFilename,
    RevisionDocumentStatus,
    UnsupportedExtension,
    build_storage_key,
    format_matches_extension,
    looks_like_pdf,
    mime_type_for,
    normalize_extension,
    sanitize_filename,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "document-model"
SRC_ROOT = PACKAGE_ROOT / "src" / "powerforge_document_model"
FORBIDDEN_IMPORTS = frozenset({"sqlalchemy", "fastapi", "boto3", "PIL", "pydantic", "starlette"})

CLASSIFICATION_VALUES = (
    "SINGLE_LINE_DIAGRAM",
    "ELECTRICAL_DRAWING",
    "PANEL_SCHEDULE",
    "EQUIPMENT_SCHEDULE",
    "CABLE_SCHEDULE",
    "TRANSFORMER_SHOP_DRAWING",
    "SWITCHGEAR_SHOP_DRAWING",
    "BREAKER_DOCUMENT",
    "MOTOR_DATA",
    "FAULT_DATA",
    "SPECIFICATION",
    "EQUIPMENT_PHOTO",
    "NAMEPLATE_PHOTO",
    "STUDY_DOCUMENT",
    "OTHER",
    "UNKNOWN",
)

ALLOWED_PAIRS = {
    (FileFormat.PDF, ".pdf"),
    (FileFormat.PNG, ".png"),
    (FileFormat.JPEG, ".jpg"),
    (FileFormat.JPEG, ".jpeg"),
    (FileFormat.TIFF, ".tif"),
    (FileFormat.TIFF, ".tiff"),
}


def test_document_classification_values_and_order() -> None:
    values = [member.value for member in DocumentClassification]
    assert values == list(CLASSIFICATION_VALUES)
    assert DocumentClassification.OTHER in DocumentClassification
    assert DocumentClassification.UNKNOWN in DocumentClassification
    assert values.index("OTHER") < values.index("UNKNOWN")
    assert values[-1] == "UNKNOWN"
    assert DocumentClassification.SINGLE_LINE_DIAGRAM == "SINGLE_LINE_DIAGRAM"


def test_origin_status_and_format_values() -> None:
    assert {member.value for member in DocumentOrigin} == {"UPLOADED", "INHERITED"}
    assert {member.value for member in RevisionDocumentStatus} == {"INCLUDED", "REMOVED"}
    assert {member.value for member in FileFormat} == {"pdf", "png", "jpeg", "tiff"}
    assert DocumentOrigin.UPLOADED == "UPLOADED"
    assert RevisionDocumentStatus.INCLUDED == "INCLUDED"
    assert FileFormat.PDF == "pdf"


def test_sanitize_strips_unix_and_windows_paths() -> None:
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename(r"C:\x\y.pdf") == "y.pdf"
    assert sanitize_filename("C:y.pdf") == "y.pdf"


def test_sanitize_strips_control_and_bidi_characters() -> None:
    assert sanitize_filename("report\x00\x07.pdf") == "report.pdf"
    spoofed = "safe\u202epdf.exe"
    assert sanitize_filename(spoofed) == "safepdf.exe"
    assert "\u202e" not in sanitize_filename(spoofed)


def test_sanitize_truncates_preserving_extension() -> None:
    stem = "a" * 300
    result = sanitize_filename(f"{stem}.pdf")
    assert result.endswith(".pdf")
    assert len(result) == 255
    assert result == ("a" * 251) + ".pdf"


def test_sanitize_rejects_empty_and_dot_names() -> None:
    for raw in ("", "   ", ".", "..", " / ", r"C:\..", "../../"):
        with pytest.raises(InvalidFilename):
            sanitize_filename(raw)


def test_sanitize_preserves_unicode_and_trims() -> None:
    assert sanitize_filename("  単線結線図.pdf  ") == "単線結線図.pdf"


def test_normalize_extension_cases() -> None:
    assert normalize_extension("report.PDF") == ".pdf"
    assert normalize_extension("photo.JpEg") == ".jpeg"
    assert normalize_extension("scan.tif") == ".tif"
    assert normalize_extension("a.pdf.exe") == ".exe"
    assert normalize_extension("noext") == ""
    assert normalize_extension("trailing.") == ""
    assert normalize_extension(".pdf") == ""


def test_looks_like_pdf_window() -> None:
    marker = b"%PDF-"
    assert looks_like_pdf(marker + b"1.4\n")
    assert looks_like_pdf(b"\x00" * 1019 + marker)
    assert not looks_like_pdf(b"\x00" * 1020 + marker)
    assert not looks_like_pdf(b"%PDF")
    assert not looks_like_pdf(b"")
    assert not looks_like_pdf(b"not a pdf")


def test_format_extension_agreement_matrix() -> None:
    extensions = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exe", ""]
    for fmt in FileFormat:
        for ext in extensions:
            expected = (fmt, ext) in ALLOWED_PAIRS
            assert format_matches_extension(fmt, ext) is expected, (fmt, ext)


def test_mime_types_are_canonical() -> None:
    assert mime_type_for(FileFormat.PDF) == "application/pdf"
    assert mime_type_for(FileFormat.PNG) == "image/png"
    assert mime_type_for(FileFormat.JPEG) == "image/jpeg"
    assert mime_type_for(FileFormat.TIFF) == "image/tiff"
    assert set(MIME_TYPES) == set(FileFormat)
    assert set(SUPPORTED_FORMATS.values()) == set(FileFormat)


def test_build_storage_key_exact_format() -> None:
    project_id = UUID("11111111-1111-1111-1111-111111111111")
    document_id = UUID("22222222-2222-2222-2222-222222222222")
    key = build_storage_key(project_id, document_id, ".PDF")
    assert key == (
        "projects/11111111-1111-1111-1111-111111111111/"
        "documents/22222222-2222-2222-2222-222222222222/original.pdf"
    )
    assert "report" not in key
    assert "IFC" not in key
    assert "SINGLE_LINE" not in key


def test_build_storage_key_rejects_unsupported_and_non_uuid() -> None:
    project_id = uuid4()
    document_id = uuid4()
    with pytest.raises(UnsupportedExtension):
        build_storage_key(project_id, document_id, ".exe")
    with pytest.raises(UnsupportedExtension):
        build_storage_key(project_id, document_id, "../x")
    with pytest.raises(TypeError):
        build_storage_key("not-a-uuid", document_id, ".pdf")  # type: ignore[arg-type]


def test_package_has_no_forbidden_imports() -> None:
    for path in SRC_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                root = module.split(".", 1)[0]
                assert root not in FORBIDDEN_IMPORTS, f"{path.name} imports {module}"


def test_package_declares_zero_third_party_dependencies() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["dependencies"] == []
