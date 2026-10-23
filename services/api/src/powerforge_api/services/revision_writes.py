"""Shared project/revision mutability and locking for documents and engineering writes."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from powerforge_api.exceptions import (
    ArchivedProject,
    CancelledProject,
    ProjectNotFound,
    RevisionNotFound,
    RevisionReadOnly,
)
from powerforge_persistence import Project, ProjectRevision
from powerforge_project import ProjectStatus, RevisionStatus


def assert_project_modifiable(project: Project) -> None:
    """Reject writes to archived or cancelled projects. PAUSED stays editable."""
    if project.status == ProjectStatus.ARCHIVED:
        raise ArchivedProject("Archived projects cannot be modified")
    if project.status == ProjectStatus.CANCELLED:
        raise CancelledProject("Cancelled projects cannot be modified")


def assert_revision_mutable(
    project: Project,
    revision: ProjectRevision,
    *,
    read_only_message: str = "Superseded revisions are read-only",
) -> None:
    """Revision writes need a modifiable project and a DRAFT or ACTIVE revision."""
    assert_project_modifiable(project)
    if revision.status == RevisionStatus.SUPERSEDED:
        raise RevisionReadOnly(read_only_message)


def lock_project_shared(session: Session, project_id: uuid.UUID) -> Project | None:
    """Lock the project row FOR SHARE and return a fresh copy.

    Revision mutations take this lock first, so concurrent mutations do not block
    each other, while archive, cancel and activation (which lock the project FOR
    UPDATE) wait for them. A mutation must never upgrade this lock to FOR UPDATE.
    """
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    return session.scalar(stmt)


def lock_revision(
    session: Session,
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
) -> ProjectRevision | None:
    """Lock one revision row FOR UPDATE, only if it belongs to ``project_id``.

    Filtering by project means a revision of another project is reported as missing
    and its row is never locked. Callers must already hold the project lock
    (lock order is always project, then revision). The returned row is always
    re-read, never a stale cached copy.
    """
    stmt = (
        select(ProjectRevision)
        .where(ProjectRevision.id == revision_id, ProjectRevision.project_id == project_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return session.scalar(stmt)


def lock_writable_revision(
    session: Session,
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
    *,
    read_only_message: str = "Superseded revisions are read-only",
) -> ProjectRevision:
    """Always lock project FOR SHARE before revision FOR UPDATE; refresh cached status."""
    project = lock_project_shared(session, project_id)
    if project is None:
        raise ProjectNotFound(f"Project {project_id} not found")
    revision = lock_revision(session, project_id, revision_id)
    if revision is None:
        raise RevisionNotFound(f"Revision {revision_id} not found")
    assert_revision_mutable(project, revision, read_only_message=read_only_message)
    return revision
