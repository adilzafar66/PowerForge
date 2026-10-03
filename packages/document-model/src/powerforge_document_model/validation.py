"""Pure file-validation rules. No Pillow, SQLAlchemy, FastAPI, or storage SDKs."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from types import MappingProxyType

from powerforge_document_model.enums import FileFormat
from powerforge_document_model.errors import InvalidFilename

_MAX_FILENAME_CHARS = 255
_PDF_MARKER = b"%PDF-"
_PDF_WINDOW = 1024
_BIDI_CHARS = frozenset(
    {
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
    }
)

SUPPORTED_FORMATS: Mapping[str, FileFormat] = MappingProxyType(
    {
        ".pdf": FileFormat.PDF,
        ".png": FileFormat.PNG,
        ".jpg": FileFormat.JPEG,
        ".jpeg": FileFormat.JPEG,
        ".tif": FileFormat.TIFF,
        ".tiff": FileFormat.TIFF,
    }
)

MIME_TYPES: Mapping[FileFormat, str] = MappingProxyType(
    {
        FileFormat.PDF: "application/pdf",
        FileFormat.PNG: "image/png",
        FileFormat.JPEG: "image/jpeg",
        FileFormat.TIFF: "image/tiff",
    }
)


def _basename(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def _strip_drive_prefix(name: str) -> str:
    if len(name) >= 2 and name[1] == ":" and name[0].isalpha():
        return name[2:]
    return name


def _is_stripped_char(char: str) -> bool:
    return unicodedata.category(char) == "Cc" or char in _BIDI_CHARS


def _split_stem_ext(name: str) -> tuple[str, str]:
    if "." not in name or name.endswith("."):
        return name, ""
    stem, ext = name.rsplit(".", 1)
    if not stem:
        return name, ""
    return stem, f".{ext}"


def normalize_extension(filename: str) -> str:
    """Return the final extension, lowercased with a leading dot, or ``""``."""
    name = _basename(filename)
    stem, ext = _split_stem_ext(name)
    if not ext:
        return ""
    return ext.lower()


def format_for_extension(ext: str) -> FileFormat | None:
    if not ext:
        return None
    normalized = ext if ext.startswith(".") else f".{ext}"
    return SUPPORTED_FORMATS.get(normalized.lower())


def mime_type_for(fmt: FileFormat) -> str:
    return MIME_TYPES[fmt]


def sanitize_filename(raw: str) -> str:
    """Return a stored basename. Never used in storage keys."""
    name = _strip_drive_prefix(_basename(raw))
    name = "".join(char for char in name if not _is_stripped_char(char))
    name = name.strip()
    if len(name) > _MAX_FILENAME_CHARS:
        stem, ext = _split_stem_ext(name)
        if len(ext) >= _MAX_FILENAME_CHARS:
            name = ext[:_MAX_FILENAME_CHARS]
        else:
            name = f"{stem[: _MAX_FILENAME_CHARS - len(ext)]}{ext}"
    if not name or name in {".", ".."}:
        raise InvalidFilename("Filename must be a non-empty basename")
    return name


def looks_like_pdf(header: bytes) -> bool:
    """True if the full ``%PDF-`` marker lies within the first 1024 bytes."""
    return header[:_PDF_WINDOW].find(_PDF_MARKER) != -1


def format_matches_extension(detected: FileFormat, extension: str) -> bool:
    if not extension:
        return False
    normalized = extension if extension.startswith(".") else f".{extension}"
    return SUPPORTED_FORMATS.get(normalized.lower()) == detected
