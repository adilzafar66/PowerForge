"""Revision create / update / activate services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from powerforge_api.exceptions import (
    ArchivedProject,
    CancelledProject,
    DuplicateRevisionIdentifier,
    InvalidRevisionIdentifier,
    ProjectNotFound,
    RevisionNotActivatable,
    RevisionNotFound,
    RevisionProjectMismatch,
)
from powerforge_api.models import Project, ProjectRevision
from powerforge_api.schemas.projects import RevisionCreate, RevisionUpdate
from powerforge_project import ProjectStatus, RevisionStatus


class RevisionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_revision(self, project_id: uuid.UUID, data: RevisionCreate) -> ProjectRevision:
        project = self._get_project_for_write(project_id)
        identifier = data.identifier.strip()
        if not identifier:
            raise InvalidRevisionIdentifier("Revision identifier must not be blank")

        revision = ProjectRevision(
            project_id=project.id,
            identifier=identifier,
            description=data.description,
            status=RevisionStatus.DRAFT,
        )
        self.session.add(revision)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateRevisionIdentifier(
                f"Revision identifier '{identifier}' already exists on this project"
            ) from exc

        if data.activate:
            self._activate_locked(project, revision)

        project.updated_at = datetime.now(UTC)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateRevisionIdentifier(
                f"Revision identifier '{identifier}' already exists on this project"
            ) from exc
        self.session.refresh(revision)
        return revision

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
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateRevisionIdentifier(
                "Revision identifier already exists on this project"
            ) from exc
        self.session.refresh(revision)
        return revision

    def activate_revision(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
    ) -> ProjectRevision:
        project = self._get_project_for_write(project_id, for_update=True)
        revision = self.get_revision(project_id, revision_id)
        self._activate_locked(project, revision)
        project.updated_at = datetime.now(UTC)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateRevisionIdentifier(
                "Could not activate revision; another active revision exists"
            ) from exc
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
        if project.status == ProjectStatus.ARCHIVED:
            raise ArchivedProject("Archived projects cannot be modified")
        if project.status == ProjectStatus.CANCELLED:
            raise CancelledProject("Cancelled projects cannot be modified")
        return project
