"""SQLAlchemy ORM models for projects, revisions, documents, and processing.

The API and document-worker both load these mappings. The worker does not
import FastAPI.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from powerforge_document_model import (
    ClassificationCallKind,
    ClassificationRunStatus,
    ClassificationScope,
    ClassificationStage,
    ConfidenceBand,
    DocumentClassification,
    DocumentOrigin,
    PageArtifactType,
    ProcessingRunStatus,
    RevisionDocumentStatus,
    SourceUnit,
)
from powerforge_project import ProjectStatus, RevisionStatus

project_status_enum = ENUM(
    ProjectStatus,
    name="project_status",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
revision_status_enum = ENUM(
    RevisionStatus,
    name="revision_status",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
document_classification_enum = ENUM(
    DocumentClassification,
    name="document_classification",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
document_origin_enum = ENUM(
    DocumentOrigin,
    name="document_origin",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
revision_document_status_enum = ENUM(
    RevisionDocumentStatus,
    name="revision_document_status",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
processing_run_status_enum = ENUM(
    ProcessingRunStatus,
    name="processing_run_status",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
page_artifact_type_enum = ENUM(
    PageArtifactType,
    name="page_artifact_type",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
source_unit_enum = ENUM(
    SourceUnit,
    name="source_unit",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
classification_run_status_enum = ENUM(
    ClassificationRunStatus,
    name="classification_run_status",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
classification_stage_enum = ENUM(
    ClassificationStage,
    name="classification_stage",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
classification_scope_enum = ENUM(
    ClassificationScope,
    name="classification_scope",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
confidence_band_enum = ENUM(
    ConfidenceBand,
    name="confidence_band",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
classification_call_kind_enum = ENUM(
    ClassificationCallKind,
    name="classification_call_kind",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("project_number", name="uq_projects_project_number"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_number: Mapped[str] = mapped_column(Text, nullable=False)
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    project_address: Mapped[str | None] = mapped_column(Text)
    project_scope: Mapped[str | None] = mapped_column(Text)
    client_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    engineer_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    status: Mapped[ProjectStatus] = mapped_column(
        project_status_enum,
        nullable=False,
        server_default=text("'ACTIVE'::project_status"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_before_archive: Mapped[ProjectStatus | None] = mapped_column(project_status_enum)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    revisions: Mapped[list[ProjectRevision]] = relationship(
        back_populates="project",
        cascade="save-update",
    )


class ProjectRevision(Base):
    __tablename__ = "project_revisions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "identifier",
            name="uq_project_revisions_project_id_identifier",
        ),
        Index(
            "uq_project_revisions_one_active",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        UniqueConstraint("project_id", "id", name="uq_project_revisions_project_id_id"),
        ForeignKeyConstraint(
            ["project_id", "based_on_revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_project_revisions_based_on",
        ),
        CheckConstraint(
            "based_on_revision_id IS NULL OR based_on_revision_id <> id",
            name="ck_project_revisions_based_on_not_self",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", name="fk_project_revisions_project_id"),
        nullable=False,
    )
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RevisionStatus] = mapped_column(
        revision_status_enum,
        nullable=False,
        server_default=text("'DRAFT'::revision_status"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    based_on_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    project: Mapped[Project] = relationship(back_populates="revisions")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        UniqueConstraint("project_id", "id", name="uq_documents_project_id_id"),
        CheckConstraint("size_bytes > 0", name="ck_documents_size_positive"),
        Index("ix_documents_project_id", "project_id"),
        Index("ix_documents_project_id_sha256", "project_id", "sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", name="fk_documents_project_id"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_extension: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class RevisionDocument(Base):
    """Revision-scoped association of a Document.

    ``project_id`` is intentionally denormalized so composite foreign keys can
    guarantee the revision, document, and inheritance source share one project.
    """

    __tablename__ = "revision_documents"
    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "document_id",
            name="uq_revision_documents_revision_id_document_id",
        ),
        ForeignKeyConstraint(
            ["project_id", "revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_revision_documents_revision",
        ),
        ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            name="fk_revision_documents_document",
        ),
        ForeignKeyConstraint(
            ["project_id", "inherited_from_revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_revision_documents_inherited_from",
        ),
        CheckConstraint(
            "(origin = 'INHERITED') = (inherited_from_revision_id IS NOT NULL)",
            name="ck_revision_documents_origin_inherited_from",
        ),
        CheckConstraint(
            "(status = 'REMOVED') = (removed_at IS NOT NULL)",
            name="ck_revision_documents_status_removed_at",
        ),
        CheckConstraint(
            "inherited_from_revision_id IS NULL OR inherited_from_revision_id <> revision_id",
            name="ck_revision_documents_inherited_not_self",
        ),
        Index("ix_revision_documents_revision_id", "revision_id"),
        Index("ix_revision_documents_document_id", "document_id"),
        Index("ix_revision_documents_revision_id_status", "revision_id", "status"),
        Index(
            "ix_revision_documents_revision_id_document_type",
            "revision_id",
            "document_type",
        ),
        Index(
            "ix_revision_documents_accepted_prediction",
            "accepted_classification_prediction_id",
            postgresql_where=text("accepted_classification_prediction_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    origin: Mapped[DocumentOrigin] = mapped_column(document_origin_enum, nullable=False)
    inherited_from_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[RevisionDocumentStatus] = mapped_column(
        revision_document_status_enum,
        nullable=False,
        server_default=text("'INCLUDED'::revision_document_status"),
    )
    document_type: Mapped[DocumentClassification] = mapped_column(
        document_classification_enum,
        nullable=False,
        server_default=text("'UNKNOWN'::document_classification"),
    )
    accepted_classification_prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    document_number: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    document: Mapped[Document] = relationship(
        viewonly=True,
        foreign_keys=[project_id, document_id],
        primaryjoin=(
            "and_(RevisionDocument.project_id == Document.project_id, "
            "RevisionDocument.document_id == Document.id)"
        ),
    )
    revision: Mapped[ProjectRevision] = relationship(
        viewonly=True,
        foreign_keys=[project_id, revision_id],
        primaryjoin=(
            "and_(RevisionDocument.project_id == ProjectRevision.project_id, "
            "RevisionDocument.revision_id == ProjectRevision.id)"
        ),
    )


class DocumentPage(Base):
    """Stable logical page of a Document. Not tied to a processing run."""

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "page_number",
            name="uq_document_pages_document_id_page_number",
        ),
        UniqueConstraint("id", "document_id", name="uq_document_pages_id_document_id"),
        CheckConstraint("page_number >= 1", name="ck_document_pages_page_number_positive"),
        CheckConstraint(
            "rotation_degrees IN (0, 90, 180, 270)",
            name="ck_document_pages_rotation_degrees",
        ),
        Index("ix_document_pages_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", name="fk_document_pages_document_id"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_width: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    source_height: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    source_unit: Mapped[SourceUnit] = mapped_column(source_unit_enum, nullable=False)
    rotation_degrees: Mapped[int] = mapped_column(Integer, nullable=False)
    native_text_char_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DocumentProcessingRun(Base):
    """One attempt to process a document under a processor version and profile hash."""

    __tablename__ = "document_processing_runs"
    __table_args__ = (
        Index("ix_document_processing_runs_document_id", "document_id"),
        Index(
            "ix_document_processing_runs_target",
            "document_id",
            "processor_version",
            "profile_hash",
        ),
        Index(
            "uq_document_processing_runs_one_live",
            "document_id",
            "processor_version",
            "profile_hash",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING', 'COMPLETED')"),
        ),
        UniqueConstraint(
            "id",
            "document_id",
            name="uq_document_processing_runs_id_document_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", name="fk_document_processing_runs_document_id"),
        nullable=False,
    )
    processor_version: Mapped[str] = mapped_column(Text, nullable=False)
    profile_version: Mapped[str] = mapped_column(Text, nullable=False)
    profile_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProcessingRunStatus] = mapped_column(
        processing_run_status_enum,
        nullable=False,
        server_default=text("'PENDING'::processing_run_status"),
    )
    pages_total: Mapped[int | None] = mapped_column(Integer)
    pages_processed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class PageArtifact(Base):
    """Derived file for one page of one processing attempt."""

    __tablename__ = "page_artifacts"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_page_artifacts_storage_key"),
        UniqueConstraint(
            "processing_run_id",
            "document_page_id",
            "artifact_type",
            name="uq_page_artifacts_run_page_type",
        ),
        Index("ix_page_artifacts_document_page_id", "document_page_id"),
        Index("ix_page_artifacts_processing_run_id", "processing_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_pages.id", name="fk_page_artifacts_document_page_id"),
        nullable=False,
    )
    processing_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_processing_runs.id", name="fk_page_artifacts_processing_run_id"),
        nullable=False,
    )
    artifact_type: Mapped[PageArtifactType] = mapped_column(page_artifact_type_enum, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    effective_dpi: Mapped[Decimal | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DocumentClassificationRun(Base):
    """One AI classification attempt for one document and classifier identity."""

    __tablename__ = "document_classification_runs"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "document_id",
            name="uq_document_classification_runs_id_document_id",
        ),
        ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["document_processing_runs.id", "document_processing_runs.document_id"],
            name="fk_document_classification_runs_processing_run",
        ),
        ForeignKeyConstraint(
            ["retry_of_run_id", "document_id"],
            ["document_classification_runs.id", "document_classification_runs.document_id"],
            name="fk_document_classification_runs_retry_of",
        ),
        CheckConstraint(
            "pages_total >= 0",
            name="ck_document_classification_runs_pages_total_nonnegative",
        ),
        CheckConstraint(
            "pages_classified >= 0",
            name="ck_document_classification_runs_pages_classified_nonnegative",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_document_classification_runs_attempt_positive",
        ),
        Index("ix_document_classification_runs_document_id", "document_id"),
        Index("ix_document_classification_runs_processing_run_id", "processing_run_id"),
        Index("ix_document_classification_runs_identity", "classifier_identity_hash"),
        Index(
            "uq_document_classification_runs_one_live",
            "classifier_identity_hash",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", name="fk_document_classification_runs_document_id"),
        nullable=False,
    )
    processing_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    retry_of_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    classifier_version: Mapped[str] = mapped_column(Text, nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    sampling_profile_version: Mapped[str] = mapped_column(Text, nullable=False)
    sampling_profile_hash: Mapped[str] = mapped_column(Text, nullable=False)
    classifier_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ClassificationRunStatus] = mapped_column(
        classification_run_status_enum,
        nullable=False,
        server_default=text("'PENDING'::classification_run_status"),
    )
    stage: Mapped[ClassificationStage | None] = mapped_column(classification_stage_enum)
    requires_page_classification: Mapped[bool | None] = mapped_column(Boolean)
    pages_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    pages_classified: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class ClassificationPrediction(Base):
    """Immutable document or page prediction written by a classification run."""

    __tablename__ = "classification_predictions"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "document_id",
            name="uq_classification_predictions_id_document_id",
        ),
        ForeignKeyConstraint(
            ["classification_run_id", "document_id"],
            ["document_classification_runs.id", "document_classification_runs.document_id"],
            name="fk_classification_predictions_run",
        ),
        ForeignKeyConstraint(
            ["document_page_id", "document_id"],
            ["document_pages.id", "document_pages.document_id"],
            name="fk_classification_predictions_page",
        ),
        CheckConstraint(
            "(scope = 'DOCUMENT' AND document_page_id IS NULL) "
            "OR (scope = 'PAGE' AND document_page_id IS NOT NULL)",
            name="ck_classification_predictions_scope_page",
        ),
        CheckConstraint(
            "scope <> 'PAGE' OR predicted_type <> 'MIXED_DOCUMENT'",
            name="ck_classification_predictions_page_not_mixed",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_classification_predictions_score",
        ),
        CheckConstraint(
            "jsonb_typeof(alternatives) = 'array' AND jsonb_array_length(alternatives) <= 3",
            name="ck_classification_predictions_alternatives",
        ),
        CheckConstraint(
            "rationale IS NULL OR char_length(rationale) <= 500",
            name="ck_classification_predictions_rationale",
        ),
        Index("ix_classification_predictions_document_id", "document_id"),
        Index("ix_classification_predictions_document_page_id", "document_page_id"),
        Index(
            "uq_classification_predictions_one_document",
            "classification_run_id",
            unique=True,
            postgresql_where=text("scope = 'DOCUMENT'"),
        ),
        Index(
            "uq_classification_predictions_run_page",
            "classification_run_id",
            "document_page_id",
            unique=True,
            postgresql_where=text("scope = 'PAGE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    classification_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", name="fk_classification_predictions_document_id"),
        nullable=False,
    )
    scope: Mapped[ClassificationScope] = mapped_column(classification_scope_enum, nullable=False)
    document_page_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    predicted_type: Mapped[DocumentClassification] = mapped_column(
        document_classification_enum,
        nullable=False,
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    confidence_band: Mapped[ConfidenceBand] = mapped_column(confidence_band_enum, nullable=False)
    alternatives: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ClassificationAICall(Base):
    """Raw usage for one provider call. No prompts, images, document text, or cost."""

    __tablename__ = "classification_ai_calls"
    __table_args__ = (
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) "
            "AND (cached_input_tokens IS NULL OR cached_input_tokens >= 0) "
            "AND (output_tokens IS NULL OR output_tokens >= 0) "
            "AND (reasoning_tokens IS NULL OR reasoning_tokens >= 0) "
            "AND image_count >= 0 AND latency_ms >= 0",
            name="ck_classification_ai_calls_usage_nonnegative",
        ),
        CheckConstraint(
            "page_numbers IS NULL OR jsonb_typeof(page_numbers) = 'array'",
            name="ck_classification_ai_calls_page_numbers",
        ),
        Index("ix_classification_ai_calls_classification_run_id", "classification_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    classification_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "document_classification_runs.id",
            name="fk_classification_ai_calls_classification_run_id",
        ),
        nullable=False,
    )
    call_kind: Mapped[ClassificationCallKind] = mapped_column(
        classification_call_kind_enum,
        nullable=False,
    )
    page_numbers: Mapped[list | None] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


RevisionDocument.__table__.append_constraint(
    ForeignKeyConstraint(
        ["accepted_classification_prediction_id", "document_id"],
        ["classification_predictions.id", "classification_predictions.document_id"],
        name="fk_revision_documents_accepted_prediction",
    )
)
