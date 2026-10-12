"""Response schemas for revision documents."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from powerforge_document_model import (
    ClassificationRunStatus,
    ClassificationStage,
    ConfidenceBand,
    DocumentClassification,
    DocumentOrigin,
    PageArtifactType,
    ProcessingRunStatus,
    RevisionDocumentStatus,
    SourceUnit,
)

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


class ProcessingSummary(BaseModel):
    """The current processing run only. Older failed attempts are not included."""

    status: ProcessingRunStatus
    attempt_count: int
    pages_processed: int
    pages_total: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class ProcessingStatusResponse(BaseModel):
    """Current-run summary plus the profile identity of that run."""

    processing: ProcessingSummary | None = None
    processor_version: str | None = None
    profile_version: str | None = None
    profile_hash: str | None = None


class PageArtifactInfo(BaseModel):
    """A derived artifact stored for the current completed run. No storage key."""

    artifact_type: PageArtifactType
    mime_type: str
    width_px: int | None = None
    height_px: int | None = None


class DocumentPageResponse(BaseModel):
    id: UUID
    page_number: int
    source_width: Decimal
    source_height: Decimal
    source_unit: SourceUnit
    rotation_degrees: int
    native_text_char_count: int
    artifacts: list[PageArtifactInfo]


class DocumentPageListResponse(BaseModel):
    items: list[DocumentPageResponse]


class ClassificationSuggestionSummary(BaseModel):
    """Latest completed document prediction for the current processing run."""

    predicted_type: DocumentClassification
    confidence_band: ConfidenceBand
    accepted: bool
    requires_page_classification: bool


class ClassificationAttemptSummary(BaseModel):
    """Newest classification run of any status. A failed attempt does not hide the suggestion."""

    status: ClassificationRunStatus
    stage: ClassificationStage | None = None
    pages_total: int
    pages_classified: int
    error_code: str | None = None


class ClassificationSummaryResponse(BaseModel):
    enabled: bool
    suggestion: ClassificationSuggestionSummary | None = None
    attempt: ClassificationAttemptSummary | None = None


class ClassificationAlternativeResponse(BaseModel):
    type: str
    score: float


class ClassificationDetailResponse(ClassificationSummaryResponse):
    """Suggestion and attempt, plus the score, alternatives, and rationale of the suggestion."""

    confidence_score: float | None = None
    alternatives: list[ClassificationAlternativeResponse] = Field(default_factory=list)
    rationale: str | None = None


class ClassificationRunResponse(BaseModel):
    """One historical run. No prompt, document text, image, storage key, or provider payload."""

    id: UUID
    status: ClassificationRunStatus
    stage: ClassificationStage | None = None
    pages_total: int
    pages_classified: int
    error_code: str | None = None
    created_at: datetime
    attempt_number: int
    provider: str
    model: str
    classifier_version: str
    taxonomy_version: str
    prompt_version: str
    sampling_profile_version: str
    processing_run_id: UUID
    predicted_type: DocumentClassification | None = None
    confidence_band: ConfidenceBand | None = None
    confidence_score: float | None = None


class ClassificationRunListResponse(BaseModel):
    enabled: bool
    items: list[ClassificationRunResponse]


class ClassificationPagePredictionResponse(BaseModel):
    page_number: int
    predicted_type: DocumentClassification
    confidence_band: ConfidenceBand
    confidence_score: float
    alternatives: list[ClassificationAlternativeResponse] = Field(default_factory=list)
    rationale: str | None = None


class ClassificationPageListResponse(BaseModel):
    enabled: bool
    items: list[ClassificationPagePredictionResponse]


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
    processing: ProcessingSummary | None = None
    classification: ClassificationSummaryResponse


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


class DownloadUrlResponse(BaseModel):
    """A short-lived signed URL; the bytes are served by object storage, not the API."""

    url: str
    expires_at: datetime
    filename: str


class UploadResponse(RevisionDocumentResponse):
    duplicate_detected: bool = False
    duplicate_document_ids: list[UUID] = Field(default_factory=list)
