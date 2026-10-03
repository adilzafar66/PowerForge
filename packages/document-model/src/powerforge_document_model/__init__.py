"""Document module vocabulary, pure file-validation rules, and storage keys.

Owns classification, origin, and status enums, filename/extension/PDF-header
rules, and the storage-key builder. Has no third-party dependencies and must
not import SQLAlchemy, FastAPI, storage SDKs, or Pillow. Must not contain
engineering-model logic or calculations.
"""

from powerforge_document_model.enums import (
    DocumentClassification,
    DocumentOrigin,
    FileFormat,
    RevisionDocumentStatus,
)
from powerforge_document_model.errors import (
    DocumentValidationError,
    InvalidFilename,
    UnsupportedExtension,
)
from powerforge_document_model.storage_key import build_storage_key
from powerforge_document_model.validation import (
    MIME_TYPES,
    SUPPORTED_FORMATS,
    format_for_extension,
    format_matches_extension,
    looks_like_pdf,
    mime_type_for,
    normalize_extension,
    sanitize_filename,
)

__all__ = [
    "DocumentClassification",
    "DocumentOrigin",
    "DocumentValidationError",
    "FileFormat",
    "InvalidFilename",
    "MIME_TYPES",
    "RevisionDocumentStatus",
    "SUPPORTED_FORMATS",
    "UnsupportedExtension",
    "build_storage_key",
    "format_for_extension",
    "format_matches_extension",
    "looks_like_pdf",
    "mime_type_for",
    "normalize_extension",
    "sanitize_filename",
]
