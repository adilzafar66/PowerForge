"""Response schemas for revision documents."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from powerforge_document_model import DocumentClassification, DocumentOrigin, RevisionDocumentStatus

MAX_DOCUMENT_NUMBER_LENGTH = 128
MAX_DESCRIPTION_LENGTH = 2000
MAX_NOTES_LENGTH = 10000


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


class UploadResponse(RevisionDocumentResponse):
    duplicate_detected: bool = False
    duplicate_document_ids: list[UUID] = Field(default_factory=list)
