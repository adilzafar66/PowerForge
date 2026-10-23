"""Shared rules for revision document packages.

Used by revision creation now and by document mutations later. This module must not
import ``RevisionService`` or any document service, to avoid circular imports.
"""

from __future__ import annotations

from sqlalchemy import insert, literal, select
from sqlalchemy.orm import Session

from powerforge_api.services.revision_writes import (
    assert_project_modifiable as assert_project_modifiable,
)
from powerforge_api.services.revision_writes import (
    assert_revision_mutable,
)
from powerforge_api.services.revision_writes import (
    lock_project_shared as lock_project_shared,
)
from powerforge_api.services.revision_writes import (
    lock_revision as lock_revision,
)
from powerforge_document_model import DocumentOrigin, RevisionDocumentStatus
from powerforge_document_processing.models import (
    Project,
    ProjectRevision,
    RevisionDocument,
    document_origin_enum,
    revision_document_status_enum,
)


def assert_documents_mutable(project: Project, revision: ProjectRevision) -> None:
    """Compatibility wrapper retaining the existing document error message."""
    assert_revision_mutable(
        project,
        revision,
        read_only_message="Superseded revisions have a read-only document package",
    )


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
        "accepted_classification_prediction_id",
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
        RevisionDocument.accepted_classification_prediction_id,
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
