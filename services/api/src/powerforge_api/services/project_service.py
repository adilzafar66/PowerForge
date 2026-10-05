"""Project lifecycle and metadata services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from powerforge_api.db_errors import integrity_guard
from powerforge_api.exceptions import (
    DuplicateProjectNumber,
    InvalidStatusTransition,
    ProjectNotFound,
)
from powerforge_api.models import Project, ProjectRevision
from powerforge_api.schemas.projects import ProjectCreate, ProjectUpdate
from powerforge_api.services.revision_documents import assert_project_modifiable
from powerforge_project import ProjectStatus, RevisionStatus, can_transition


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_project(self, data: ProjectCreate) -> Project:
        project = Project(
            project_number=data.project_number,
            project_name=data.project_name,
            project_address=data.project_address,
            project_scope=data.project_scope,
            client_name=data.client_name,
            description=data.description,
            engineer_names=list(data.engineer_names),
            status=ProjectStatus.ACTIVE,
        )
        with integrity_guard(
            self.session,
            {
                "uq_projects_project_number": DuplicateProjectNumber(
                    f"Project number '{data.project_number}' already exists"
                )
            },
            operation="create_project",
        ):
            self.session.add(project)
            self.session.commit()
        self.session.refresh(project)
        return project

    def get_project(self, project_id: uuid.UUID) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        return project

    def list_projects(
        self,
        *,
        search: str | None = None,
        status: ProjectStatus | None = None,
    ) -> list[tuple[Project, str | None]]:
        stmt = (
            select(Project)
            .options(selectinload(Project.revisions))
            .order_by(Project.updated_at.desc())
        )
        if status is not None:
            stmt = stmt.where(Project.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Project.project_number.ilike(pattern),
                    Project.project_name.ilike(pattern),
                    Project.client_name.ilike(pattern),
                    Project.project_address.ilike(pattern),
                )
            )
        projects = list(self.session.scalars(stmt).unique().all())
        return [(project, self._active_identifier(project)) for project in projects]

    def update_project(self, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
        project = self.get_project(project_id)
        self._reject_if_locked(project)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return project
        for field, value in updates.items():
            setattr(project, field, value)
        project.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(project)
        return project

    def _get_project_for_update(self, project_id: uuid.UUID) -> Project:
        """Load the project row FOR UPDATE, refreshing any cached copy.

        Transitions that block document writes take this lock before reading the
        status, so they wait for in-flight document mutations (which hold the
        project FOR SHARE) and later mutations see the new status.
        """
        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        project = self.session.scalar(stmt)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        return project

    def pause_project(self, project_id: uuid.UUID) -> Project:
        return self._transition(project_id, ProjectStatus.PAUSED)

    def resume_project(self, project_id: uuid.UUID) -> Project:
        return self._transition(
            project_id,
            ProjectStatus.ACTIVE,
            from_statuses={ProjectStatus.PAUSED},
        )

    def cancel_project(self, project_id: uuid.UUID) -> Project:
        return self._transition(
            project_id,
            ProjectStatus.CANCELLED,
            from_statuses={ProjectStatus.ACTIVE, ProjectStatus.PAUSED},
            lock_project=True,
        )

    def archive_project(self, project_id: uuid.UUID) -> Project:
        project = self._get_project_for_update(project_id)
        if project.status == ProjectStatus.ARCHIVED:
            return project
        if not can_transition(project.status, ProjectStatus.ARCHIVED):
            raise InvalidStatusTransition(
                f"Cannot archive project from status {project.status}"
            )
        project.status_before_archive = project.status
        project.status = ProjectStatus.ARCHIVED
        project.archived_at = datetime.now(UTC)
        project.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(project)
        return project

    def unarchive_project(self, project_id: uuid.UUID) -> Project:
        project = self.get_project(project_id)
        if project.status != ProjectStatus.ARCHIVED:
            raise InvalidStatusTransition(
                f"Cannot unarchive project with status {project.status}"
            )
        restore_status = project.status_before_archive or ProjectStatus.ACTIVE
        if not can_transition(project.status, restore_status):
            raise InvalidStatusTransition(
                f"Cannot unarchive project to status {restore_status}"
            )
        project.status = restore_status
        project.status_before_archive = None
        project.archived_at = None
        project.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(project)
        return project

    def _transition(
        self,
        project_id: uuid.UUID,
        to_status: ProjectStatus,
        *,
        from_statuses: set[ProjectStatus] | None = None,
        lock_project: bool = False,
    ) -> Project:
        project = (
            self._get_project_for_update(project_id)
            if lock_project
            else self.get_project(project_id)
        )
        self._reject_if_locked(project)
        if from_statuses is not None and project.status not in from_statuses:
            raise InvalidStatusTransition(
                f"Cannot transition from {project.status} to {to_status}"
            )
        if not can_transition(project.status, to_status):
            raise InvalidStatusTransition(
                f"Cannot transition from {project.status} to {to_status}"
            )
        project.status = to_status
        project.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(project)
        return project

    @staticmethod
    def _reject_if_locked(project: Project) -> None:
        assert_project_modifiable(project)

    @staticmethod
    def _active_identifier(project: Project) -> str | None:
        for revision in project.revisions:
            if revision.status == RevisionStatus.ACTIVE:
                return revision.identifier
        return None

    def active_revision_identifier(self, project_id: uuid.UUID) -> str | None:
        stmt = select(ProjectRevision.identifier).where(
            ProjectRevision.project_id == project_id,
            ProjectRevision.status == RevisionStatus.ACTIVE,
        )
        return self.session.scalar(stmt)
