"""SQLAlchemy ORM models for projects and revisions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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

    project: Mapped[Project] = relationship(back_populates="revisions")
