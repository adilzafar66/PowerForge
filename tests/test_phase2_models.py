"""Phase 2 ORM models match the migration vocabulary (no database)."""

from __future__ import annotations

import warnings

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, LargeBinary, UniqueConstraint
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import configure_mappers

from powerforge_api.models import Base, Document, ProjectRevision, RevisionDocument
from powerforge_document_model import (
    DocumentClassification,
    DocumentOrigin,
    RevisionDocumentStatus,
)

EXPECTED_PROJECT_REVISION_CONSTRAINTS = {
    "uq_project_revisions_project_id_id",
    "fk_project_revisions_based_on",
    "ck_project_revisions_based_on_not_self",
}
EXPECTED_DOCUMENT_CONSTRAINTS = {
    "fk_documents_project_id",
    "uq_documents_storage_key",
    "uq_documents_project_id_id",
    "ck_documents_size_positive",
}
EXPECTED_DOCUMENT_INDEXES = {"ix_documents_project_id", "ix_documents_project_id_sha256"}
EXPECTED_REVISION_DOCUMENT_CONSTRAINTS = {
    "uq_revision_documents_revision_id_document_id",
    "fk_revision_documents_revision",
    "fk_revision_documents_document",
    "fk_revision_documents_inherited_from",
    "ck_revision_documents_origin_inherited_from",
    "ck_revision_documents_status_removed_at",
    "ck_revision_documents_inherited_not_self",
}
EXPECTED_REVISION_DOCUMENT_INDEXES = {
    "ix_revision_documents_revision_id",
    "ix_revision_documents_document_id",
    "ix_revision_documents_revision_id_status",
    "ix_revision_documents_revision_id_document_type",
}


def _constraint_names(table) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint | ForeignKeyConstraint | CheckConstraint)
        and constraint.name
    }


def _index_names(table) -> set[str]:
    return {index.name for index in table.indexes if isinstance(index, Index)}


def test_mapper_configuration_emits_no_sqlalchemy_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        configure_mappers()


def test_new_tables_registered() -> None:
    assert {"documents", "revision_documents"} <= set(Base.metadata.tables)


def test_enum_labels_match_python_enums() -> None:
    document_type = RevisionDocument.__table__.c.document_type.type
    origin = RevisionDocument.__table__.c.origin.type
    status = RevisionDocument.__table__.c.status.type
    assert list(document_type.enums) == [m.value for m in DocumentClassification]
    assert list(origin.enums) == [m.value for m in DocumentOrigin]
    assert list(status.enums) == [m.value for m in RevisionDocumentStatus]
    assert document_type.name == "document_classification"
    assert origin.name == "document_origin"
    assert status.name == "revision_document_status"


def test_project_revision_lineage_constraints() -> None:
    table = ProjectRevision.__table__
    assert "based_on_revision_id" in table.c
    assert table.c.based_on_revision_id.nullable is True
    assert EXPECTED_PROJECT_REVISION_CONSTRAINTS <= _constraint_names(table)


def test_document_constraints_and_indexes() -> None:
    table = Document.__table__
    assert EXPECTED_DOCUMENT_CONSTRAINTS <= _constraint_names(table)
    assert EXPECTED_DOCUMENT_INDEXES <= _index_names(table)
    assert table.c.size_bytes.nullable is False


def test_revision_document_constraints_and_indexes() -> None:
    table = RevisionDocument.__table__
    assert EXPECTED_REVISION_DOCUMENT_CONSTRAINTS <= _constraint_names(table)
    assert EXPECTED_REVISION_DOCUMENT_INDEXES <= _index_names(table)


def test_no_table_can_hold_file_content() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, LargeBinary), f"{table.name}.{column.name}"
    assert "storage_key" in Document.__table__.c


def test_no_cascading_deletes() -> None:
    for table in (ProjectRevision.__table__, Document.__table__, RevisionDocument.__table__):
        for constraint in table.constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                assert constraint.ondelete is None, constraint.name


def test_revision_document_composite_foreign_keys_start_with_project_id() -> None:
    table = RevisionDocument.__table__
    foreign_keys = {
        constraint.name: [column.name for column in constraint.columns]
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert foreign_keys["fk_revision_documents_revision"] == ["project_id", "revision_id"]
    assert foreign_keys["fk_revision_documents_document"] == ["project_id", "document_id"]
    assert foreign_keys["fk_revision_documents_inherited_from"] == [
        "project_id",
        "inherited_from_revision_id",
    ]
