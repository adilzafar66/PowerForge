"""SQLAlchemy ORM models for projects, revisions, and revision-scoped documents."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from powerforge_document_model import (
    DocumentClassification,
    DocumentOrigin,
    RevisionDocumentStatus,
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
