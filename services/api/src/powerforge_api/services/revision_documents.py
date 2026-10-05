"""Shared rules for revision document packages.

Used by revision creation now and by document mutations later. This module must not
import ``RevisionService`` or any document service, to avoid circular imports.
"""

from __future__ import annotations

import uuid

from sqlalchemy import insert, literal, select
from sqlalchemy.orm import Session

from powerforge_api.exceptions import ArchivedProject, CancelledProject, RevisionReadOnly
from powerforge_api.models import (
    Project,
    ProjectRevision,
    RevisionDocument,
    document_origin_enum,
    revision_document_status_enum,
)
from powerforge_document_model import DocumentOrigin, RevisionDocumentStatus
from powerforge_project import ProjectStatus, RevisionStatus


def assert_project_modifiable(project: Project) -> None:
    """Reject writes to archived or cancelled projects. PAUSED stays editable."""
    if project.status == ProjectStatus.ARCHIVED:
        raise ArchivedProject("Archived projects cannot be modified")
    if project.status == ProjectStatus.CANCELLED:
        raise CancelledProject("Cancelled projects cannot be modified")


def assert_documents_mutable(project: Project, revision: ProjectRevision) -> None:
    """Document mutations need a modifiable project and a DRAFT or ACTIVE revision."""
    assert_project_modifiable(project)
    if revision.status == RevisionStatus.SUPERSEDED:
        raise RevisionReadOnly("Superseded revisions have a read-only document package")


def lock_project_shared(session: Session, project_id: uuid.UUID) -> Project | None:
    """Lock the project row FOR SHARE and return a fresh copy.

    Document mutations take this lock first, so concurrent mutations do not block
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


def copy_included_associations(
    session: Session,
    base: ProjectRevision,
    target: ProjectRevision,
) -> int:
    """Copy the base's INCLUDED associations into ``target`` as INHERITED rows.

    The copies point at the same Document and carry the revision-scoped metadata.
    Row ids and the added/removed audit fields are not copied, so the database
    assigns fresh ones. Object storage is never involved. Returns the number copied.
    """
    columns = [
        "project_id",
        "revision_id",
        "document_id",
        "origin",
        "inherited_from_revision_id",
        "status",
        "document_type",
        "document_number",
        "description",
        "notes",
    ]
    source = select(
        RevisionDocument.project_id,
        literal(target.id, type_=RevisionDocument.revision_id.type),
        RevisionDocument.document_id,
        literal(DocumentOrigin.INHERITED, type_=document_origin_enum),
        literal(base.id, type_=RevisionDocument.inherited_from_revision_id.type),
        literal(RevisionDocumentStatus.INCLUDED, type_=revision_document_status_enum),
        RevisionDocument.document_type,
        RevisionDocument.document_number,
        RevisionDocument.description,
        RevisionDocument.notes,
    ).where(
        RevisionDocument.revision_id == base.id,
        RevisionDocument.project_id == base.project_id,
        RevisionDocument.status == RevisionDocumentStatus.INCLUDED,
    )
    # rowcount is unreliable for ORM INSERT ... SELECT (it can report -1), so count
    # the returned ids instead.
    statement = insert(RevisionDocument).from_select(columns, source).returning(RevisionDocument.id)
    return len(session.execute(statement).all())
