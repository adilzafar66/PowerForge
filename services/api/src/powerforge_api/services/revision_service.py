"""Revision create / update / activate services."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from powerforge_api.db_errors import integrity_guard
from powerforge_api.exceptions import (
    DuplicateRevisionIdentifier,
    InvalidBaseRevision,
    InvalidRevisionIdentifier,
    ProjectNotFound,
    RevisionNotActivatable,
    RevisionNotFound,
    RevisionProjectMismatch,
)
from powerforge_api.models import Project, ProjectRevision
from powerforge_api.schemas.projects import RevisionCreate, RevisionUpdate
from powerforge_api.services.revision_documents import (
    assert_project_modifiable,
    copy_included_associations,
    lock_revision,
)
from powerforge_project import RevisionStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RevisionCreateResult:
    revision: ProjectRevision
    inherited_document_count: int


class RevisionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_revision(self, project_id: uuid.UUID, data: RevisionCreate) -> RevisionCreateResult:
        try:
            return self._create_revision(project_id, data)
        except Exception:
            # integrity_guard only rolls back IntegrityError; any other failure must
            # also leave nothing behind (no revision row, no partial associations).
            self.session.rollback()
            raise

    def _create_revision(self, project_id: uuid.UUID, data: RevisionCreate) -> RevisionCreateResult:
        base_is_explicit_null = (
            "based_on_revision_id" in data.model_fields_set and data.based_on_revision_id is None
        )
        # Lock the project row before resolving the base or replacing ACTIVE, same
        # serialization as activate_revision(). Lock order is always project -> revision.
        project = self._get_project_for_write(
            project_id,
            for_update=data.activate or not base_is_explicit_null,
        )
        identifier = data.identifier.strip()
        if not identifier:
            raise InvalidRevisionIdentifier("Revision identifier must not be blank")

        base = self._resolve_base(project, data, base_is_explicit_null=base_is_explicit_null)
        carry_forward = self._resolve_carry_forward(data, base)

        revision = ProjectRevision(
            project_id=project.id,
            identifier=identifier,
            description=data.description,
            status=RevisionStatus.DRAFT,
            based_on_revision_id=base.id if base is not None else None,
        )
        inherited = 0
        with integrity_guard(
            self.session,
            {
                "uq_project_revisions_project_id_identifier": DuplicateRevisionIdentifier(
                    f"Revision identifier '{identifier}' already exists on this project"
                ),
                "uq_project_revisions_one_active": RevisionNotActivatable(
                    "Could not activate revision; another active revision exists"
                ),
                "fk_project_revisions_based_on": InvalidBaseRevision(
                    "Base revision must be an existing revision of this project"
                ),
                "ck_project_revisions_based_on_not_self": InvalidBaseRevision(
                    "A revision cannot be based on itself"
                ),
            },
            operation="create_revision",
        ):
            self.session.add(revision)
            self.session.flush()
            if carry_forward and base is not None:
                inherited = copy_included_associations(self.session, base, revision)
            # Activation runs after the copy so the base package is read before the
            # base can be superseded.
            if data.activate:
                self._activate_locked(project, revision)
            project.updated_at = datetime.now(UTC)
            self.session.commit()
        self.session.refresh(revision)
        if carry_forward and base is not None:
            logger.info(
                "revision document inheritance completed",
                extra={
                    "project_id": project.id,
                    "revision_id": revision.id,
                    "base_revision_id": base.id,
                    "inherited_document_count": inherited,
                },
            )
        return RevisionCreateResult(revision=revision, inherited_document_count=inherited)

    def _resolve_base(
        self,
        project: Project,
        data: RevisionCreate,
        *,
        base_is_explicit_null: bool,
    ) -> ProjectRevision | None:
        if base_is_explicit_null:
            return None
        if data.based_on_revision_id is not None:
            base = lock_revision(self.session, project.id, data.based_on_revision_id)
            if base is None:
                raise InvalidBaseRevision(
                    "Base revision must be an existing revision of this project"
                )
            return base
        stmt = (
            select(ProjectRevision)
            .where(
                ProjectRevision.project_id == project.id,
                ProjectRevision.status == RevisionStatus.ACTIVE,
            )
            .with_for_update()
        )
        return self.session.scalar(stmt)

    @staticmethod
    def _resolve_carry_forward(data: RevisionCreate, base: ProjectRevision | None) -> bool:
        if data.carry_forward_documents is None:
            return base is not None
        if data.carry_forward_documents and base is None:
            raise InvalidBaseRevision("carry_forward_documents requires a base revision")
        return data.carry_forward_documents

    def base_identifier(self, revision: ProjectRevision) -> str | None:
        if revision.based_on_revision_id is None:
            return None
        return self.session.scalar(
            select(ProjectRevision.identifier).where(
                ProjectRevision.id == revision.based_on_revision_id
            )
        )

    def list_revisions(self, project_id: uuid.UUID) -> list[ProjectRevision]:
        self._require_project(project_id)
        stmt = (
            select(ProjectRevision)
            .where(ProjectRevision.project_id == project_id)
            .order_by(ProjectRevision.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_revision(self, project_id: uuid.UUID, revision_id: uuid.UUID) -> ProjectRevision:
        self._require_project(project_id)
        revision = self.session.get(ProjectRevision, revision_id)
        if revision is None:
            raise RevisionNotFound(f"Revision {revision_id} not found")
        if revision.project_id != project_id:
            raise RevisionProjectMismatch("Revision does not belong to this project")
        return revision

    def update_revision(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        data: RevisionUpdate,
    ) -> ProjectRevision:
        project = self._get_project_for_write(project_id)
        revision = self.get_revision(project_id, revision_id)
        updates = data.model_dump(exclude_unset=True)
        if "identifier" in updates and updates["identifier"] is not None:
            identifier = updates["identifier"].strip()
            if not identifier:
                raise InvalidRevisionIdentifier("Revision identifier must not be blank")
            updates["identifier"] = identifier
        for field, value in updates.items():
            setattr(revision, field, value)
        revision.updated_at = datetime.now(UTC)
        project.updated_at = datetime.now(UTC)
        with integrity_guard(
            self.session,
            {
                "uq_project_revisions_project_id_identifier": DuplicateRevisionIdentifier(
                    "Revision identifier already exists on this project"
                ),
            },
            operation="update_revision",
        ):
            self.session.commit()
        self.session.refresh(revision)
        return revision

    def activate_revision(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
    ) -> ProjectRevision:
        project = self._get_project_for_write(project_id, for_update=True)
        revision = self.get_revision(project_id, revision_id)
        with integrity_guard(
            self.session,
            {
                "uq_project_revisions_one_active": RevisionNotActivatable(
                    "Could not activate revision; another active revision exists"
                ),
            },
            operation="activate_revision",
        ):
            self._activate_locked(project, revision)
            project.updated_at = datetime.now(UTC)
            self.session.commit()
        self.session.refresh(revision)
        return revision

    def _activate_locked(self, project: Project, revision: ProjectRevision) -> None:
        if revision.status == RevisionStatus.ACTIVE:
            return
        if revision.status == RevisionStatus.SUPERSEDED:
            raise RevisionNotActivatable(
                "Superseded revisions cannot be activated"
            )

        current_active = self.session.scalar(
            select(ProjectRevision).where(
                ProjectRevision.project_id == project.id,
                ProjectRevision.status == RevisionStatus.ACTIVE,
            )
        )
        if current_active is not None and revision.created_at <= current_active.created_at:
            raise RevisionNotActivatable(
                "Only revisions created after the current active revision can be activated"
            )

        # Supersede and flush first so the partial unique index is never violated
        # mid-statement when SQLAlchemy batches UPDATEs.
        if current_active is not None:
            current_active.status = RevisionStatus.SUPERSEDED
            current_active.updated_at = datetime.now(UTC)
            self.session.flush()
        revision.status = RevisionStatus.ACTIVE
        revision.updated_at = datetime.now(UTC)

    def _require_project(self, project_id: uuid.UUID) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        return project

    def _get_project_for_write(
        self,
        project_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Project:
        stmt = select(Project).where(Project.id == project_id)
        if for_update:
            stmt = stmt.with_for_update()
        project = self.session.scalar(stmt)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        assert_project_modifiable(project)
        return project
