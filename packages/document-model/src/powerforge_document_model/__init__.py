"""Document module vocabulary, pure file-validation rules, and storage keys.

Owns classification, origin, and status enums, the processing profile and
artifact-key builder, filename/extension/PDF-header rules, and the original
storage-key builder. Has no third-party dependencies and must not import
SQLAlchemy, FastAPI, storage SDKs, Pillow, or PyMuPDF. Must not contain
engineering-model logic or calculations.
"""

from powerforge_document_model.artifact_key import build_artifact_key
from powerforge_document_model.coordinates import NormalizedBox
from powerforge_document_model.enums import (
    DocumentClassification,
    DocumentOrigin,
    FileFormat,
    PageArtifactType,
    ProcessingErrorCode,
    ProcessingRunStatus,
    RevisionDocumentStatus,
    SourceUnit,
)
from powerforge_document_model.errors import (
    DocumentValidationError,
    InvalidArtifactKey,
    InvalidFilename,
    UnsupportedExtension,
)
from powerforge_document_model.profile import (
    DEFAULT_PROFILE,
    PROCESSOR_VERSION,
    PROFILE_VERSION,
    ProcessingProfile,
    hash_material_fields,
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
    "DEFAULT_PROFILE",
    "DocumentClassification",
    "DocumentOrigin",
    "DocumentValidationError",
    "FileFormat",
    "InvalidArtifactKey",
    "InvalidFilename",
    "MIME_TYPES",
    "NormalizedBox",
    "PROFILE_VERSION",
    "PROCESSOR_VERSION",
    "PageArtifactType",
    "ProcessingErrorCode",
    "ProcessingProfile",
    "ProcessingRunStatus",
    "RevisionDocumentStatus",
    "SUPPORTED_FORMATS",
    "SourceUnit",
    "UnsupportedExtension",
    "build_artifact_key",
    "build_storage_key",
    "format_for_extension",
    "format_matches_extension",
    "hash_material_fields",
    "looks_like_pdf",
    "mime_type_for",
    "normalize_extension",
    "sanitize_filename",
]
