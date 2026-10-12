"""Phase 2 ORM models match the migration vocabulary (no database)."""

from __future__ import annotations

import warnings

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, LargeBinary, UniqueConstraint
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import configure_mappers

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
from powerforge_document_processing.models import (
    Base,
    ClassificationAICall,
    ClassificationPrediction,
    Document,
    DocumentClassificationRun,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
    ProjectRevision,
    RevisionDocument,
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
    "ix_revision_documents_accepted_prediction",
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
    assert {
        "documents",
        "revision_documents",
        "document_pages",
        "document_processing_runs",
        "page_artifacts",
        "document_classification_runs",
        "classification_predictions",
        "classification_ai_calls",
    } <= set(Base.metadata.tables)


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


def test_processing_enum_labels_match_python_enums() -> None:
    status = DocumentProcessingRun.__table__.c.status.type
    unit = DocumentPage.__table__.c.source_unit.type
    artifact_type = PageArtifact.__table__.c.artifact_type.type
    assert list(status.enums) == [member.value for member in ProcessingRunStatus]
    assert list(unit.enums) == [member.value for member in SourceUnit]
    assert list(artifact_type.enums) == [member.value for member in PageArtifactType]
    assert status.name == "processing_run_status"
    assert unit.name == "source_unit"
    assert artifact_type.name == "page_artifact_type"
    assert DocumentProcessingRun.__table__.c.error_code.nullable is True


def test_classification_enum_labels_match_python_enums() -> None:
    run_status = DocumentClassificationRun.__table__.c.status.type
    stage = DocumentClassificationRun.__table__.c.stage.type
    scope = ClassificationPrediction.__table__.c.scope.type
    band = ClassificationPrediction.__table__.c.confidence_band.type
    call_kind = ClassificationAICall.__table__.c.call_kind.type
    assert list(run_status.enums) == [member.value for member in ClassificationRunStatus]
    assert list(stage.enums) == [member.value for member in ClassificationStage]
    assert list(scope.enums) == [member.value for member in ClassificationScope]
    assert list(band.enums) == [member.value for member in ConfidenceBand]
    assert list(call_kind.enums) == [member.value for member in ClassificationCallKind]
    assert run_status.name == "classification_run_status"
    assert stage.name == "classification_stage"
    assert scope.name == "classification_scope"
    assert band.name == "confidence_band"
    assert call_kind.name == "classification_call_kind"
    assert DocumentClassificationRun.__table__.c.error_code.nullable is True
    assert "estimated_cost_usd" not in ClassificationAICall.__table__.c
    assert "pricing_version" not in ClassificationAICall.__table__.c


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
    for table in (
        ProjectRevision.__table__,
        Document.__table__,
        RevisionDocument.__table__,
        DocumentPage.__table__,
        DocumentProcessingRun.__table__,
        PageArtifact.__table__,
        DocumentClassificationRun.__table__,
        ClassificationPrediction.__table__,
        ClassificationAICall.__table__,
    ):
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
    assert foreign_keys["fk_revision_documents_accepted_prediction"] == [
        "accepted_classification_prediction_id",
        "document_id",
    ]
