"""Response schemas for revision documents."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from powerforge_document_model import DocumentClassification, DocumentOrigin, RevisionDocumentStatus

MAX_DOCUMENT_NUMBER_LENGTH = 128
MAX_DESCRIPTION_LENGTH = 2000
MAX_NOTES_LENGTH = 10000
METADATA_FIELDS = frozenset({"document_type", "document_number", "description", "notes"})


class DocumentStatusFilter(StrEnum):
    INCLUDED = "INCLUDED"
    REMOVED = "REMOVED"
    ALL = "ALL"


class DocumentSummary(BaseModel):
    """The immutable file facts of a Document. Never exposes the storage key."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    mime_type: str
    file_extension: str
    size_bytes: int
    sha256: str
    uploaded_at: datetime


class RevisionDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision_id: UUID
    document: DocumentSummary
    origin: DocumentOrigin
    inherited_from_revision_id: UUID | None = None
    inherited_from_revision_identifier: str | None = None
    status: RevisionDocumentStatus
    document_type: DocumentClassification
    document_number: str | None = None
    description: str | None = None
    notes: str | None = None
    added_at: datetime
    removed_at: datetime | None = None


class RevisionDocumentListResponse(BaseModel):
    items: list[RevisionDocumentResponse]


class _MetadataFields(BaseModel):
    """Revision-scoped metadata that clients may set after upload.

    Omitted fields mean "leave alone" (``model_fields_set``); an explicit null
    clears a text field. ``document_type`` cannot be null (the column is NOT NULL).
    """

    model_config = ConfigDict(extra="forbid")

    document_type: DocumentClassification | None = None
    document_number: str | None = Field(default=None, max_length=MAX_DOCUMENT_NUMBER_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    notes: str | None = Field(default=None, max_length=MAX_NOTES_LENGTH)

    @field_validator("document_number", "description", "notes")
    @classmethod
    def blank_is_null(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def document_type_is_not_null(self) -> Self:
        if "document_type" in self.model_fields_set and self.document_type is None:
            raise ValueError("document_type must not be null")
        return self

    def provided_metadata(self) -> dict[str, Any]:
        """The metadata fields the client actually sent, with their (possibly null) values."""
        return {name: getattr(self, name) for name in self.model_fields_set & METADATA_FIELDS}


class RevisionDocumentUpdate(_MetadataFields):
    """PATCH body. Unknown or immutable fields are rejected (422)."""


class ReuseDocumentRequest(_MetadataFields):
    """Body for adding an existing project document to another revision."""

    source_revision_document_id: UUID


class UploadResponse(RevisionDocumentResponse):
    duplicate_detected: bool = False
    duplicate_document_ids: list[UUID] = Field(default_factory=list)
