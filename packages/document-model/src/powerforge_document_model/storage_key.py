"""Build immutable object-storage keys from stable identifiers only."""

from __future__ import annotations

from uuid import UUID

from powerforge_document_model.errors import UnsupportedExtension
from powerforge_document_model.validation import SUPPORTED_FORMATS


def build_storage_key(project_id: UUID, document_id: UUID, extension: str) -> str:
    """Return ``projects/{project}/documents/{document}/original{ext}``."""
    if not isinstance(project_id, UUID):
        raise TypeError("project_id must be a UUID")
    if not isinstance(document_id, UUID):
        raise TypeError("document_id must be a UUID")
    ext = extension if extension.startswith(".") else f".{extension}"
    ext = ext.lower()
    if ext not in SUPPORTED_FORMATS:
        raise UnsupportedExtension(f"Unsupported extension: {extension}")
    return f"projects/{project_id}/documents/{document_id}/original{ext}"
