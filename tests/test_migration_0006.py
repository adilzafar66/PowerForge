"""Migration 0006 against scratch databases. Requires RUN_INTEGRATION=1.

Alembic runs in a subprocess so its logging configuration cannot leak into the test session.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine, make_url

from powerforge_document_model import (
    ClassificationCallKind,
    ClassificationRunStatus,
    ClassificationScope,
    ClassificationStage,
    ConfidenceBand,
    DocumentClassification,
)
from powerforge_shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = "database/alembic.ini"
HEAD = "0006_document_classification"
PREVIOUS = "0005_document_processing"

PHASE4_TABLES = {
    "document_classification_runs",
    "classification_predictions",
    "classification_ai_calls",
}
PHASE4_ENUMS = {
    "classification_run_status",
    "classification_stage",
    "classification_scope",
    "confidence_band",
    "classification_call_kind",
}
RUN_CONSTRAINTS = {
    "fk_document_classification_runs_document_id",
    "fk_document_classification_runs_processing_run",
    "fk_document_classification_runs_retry_of",
    "uq_document_classification_runs_id_document_id",
    "ck_document_classification_runs_pages_total_nonnegative",
    "ck_document_classification_runs_pages_classified_nonnegative",
    "ck_document_classification_runs_attempt_positive",
}
RUN_INDEXES = {
    "ix_document_classification_runs_document_id",
    "ix_document_classification_runs_processing_run_id",
    "ix_document_classification_runs_identity",
    "uq_document_classification_runs_one_live",
}
PREDICTION_CONSTRAINTS = {
    "fk_classification_predictions_document_id",
    "fk_classification_predictions_run",
    "fk_classification_predictions_page",
    "uq_classification_predictions_id_document_id",
    "ck_classification_predictions_scope_page",
    "ck_classification_predictions_page_not_mixed",
    "ck_classification_predictions_score",
    "ck_classification_predictions_alternatives",
    "ck_classification_predictions_rationale",
}
PREDICTION_INDEXES = {
    "ix_classification_predictions_document_id",
    "ix_classification_predictions_document_page_id",
    "uq_classification_predictions_one_document",
    "uq_classification_predictions_run_page",
}
CALL_CONSTRAINTS = {
    "fk_classification_ai_calls_classification_run_id",
    "ck_classification_ai_calls_usage_nonnegative",
    "ck_classification_ai_calls_page_numbers",
}
CALL_INDEXES = {"ix_classification_ai_calls_classification_run_id"}


def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION") == "1"


def _base_url() -> URL:
    return make_url(get_settings().database_url)


def _alembic(url: URL, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", ALEMBIC_INI, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"
    )


@pytest.fixture
def scratch_url() -> Iterator[URL]:
    if not _integration_enabled():
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    base = _base_url()
    name = f"powerforge_mig_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        yield base.set(database=name)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _version(engine: Engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _enum_labels(engine: Engine, type_name: str) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :name ORDER BY e.enumsortorder"
            ),
            {"name": type_name},
        )
        return [row[0] for row in rows]


def _enum_types(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT typname FROM pg_type WHERE typname = ANY(:names)"),
            {"names": sorted(PHASE4_ENUMS)},
        )
        return {row[0] for row in rows}


def _constraint_names(engine: Engine, table: str) -> set[str]:
    inspector = inspect(engine)
    names = {item["name"] for item in inspector.get_unique_constraints(table)}
    names |= {item["name"] for item in inspector.get_foreign_keys(table)}
    names |= {item["name"] for item in inspector.get_check_constraints(table)}
    return names


def _index_names(engine: Engine, table: str) -> set[str]:
    return {item["name"] for item in inspect(engine).get_indexes(table)}


def _seed_phase3(engine: Engine) -> dict[str, uuid.UUID]:
    storage_key = f"projects/{uuid.uuid4()}/documents/{uuid.uuid4()}/original.pdf"
    with engine.begin() as connection:
        project_id = connection.execute(
            text(
                "INSERT INTO projects (project_number, project_name) "
                "VALUES (:number, 'Legacy') RETURNING id"
            ),
            {"number": f"MIG-{uuid.uuid4().hex[:8]}"},
        ).scalar_one()
        revision_id = connection.execute(
            text(
                "INSERT INTO project_revisions (project_id, identifier) "
                "VALUES (:project_id, '0') RETURNING id"
            ),
            {"project_id": project_id},
        ).scalar_one()
        document_id = connection.execute(
            text(
                "INSERT INTO documents (project_id, original_filename, storage_key, mime_type, "
                "file_extension, size_bytes, sha256) "
                "VALUES (:project_id, 'a.pdf', :storage_key, 'application/pdf', 'pdf', 10, :sha) "
                "RETURNING id"
            ),
            {"project_id": project_id, "storage_key": storage_key, "sha": "a" * 64},
        ).scalar_one()
        association_id = connection.execute(
            text(
                "INSERT INTO revision_documents (project_id, revision_id, document_id, origin) "
                "VALUES (:project_id, :revision_id, :document_id, 'UPLOADED'::document_origin) "
                "RETURNING id"
            ),
            {
                "project_id": project_id,
                "revision_id": revision_id,
                "document_id": document_id,
            },
        ).scalar_one()
        page_id = connection.execute(
            text(
                "INSERT INTO document_pages (document_id, page_number, source_width, "
                "source_height, source_unit, rotation_degrees) "
                "VALUES (:document_id, 1, 612, 792, 'POINTS'::source_unit, 0) RETURNING id"
            ),
            {"document_id": document_id},
        ).scalar_one()
        run_id = connection.execute(
            text(
                "INSERT INTO document_processing_runs "
                "(document_id, processor_version, profile_version, profile_hash, status) "
                "VALUES (:document_id, '1', 'engineering-default-v1', 'abc', "
                "'COMPLETED'::processing_run_status) RETURNING id"
            ),
            {"document_id": document_id},
        ).scalar_one()
    return {
        "document_id": document_id,
        "association_id": association_id,
        "page_id": page_id,
        "run_id": run_id,
    }


@pytest.mark.integration
def test_fresh_upgrade_reaches_0006_with_expected_schema(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", HEAD)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        inspector = inspect(engine)
        assert PHASE4_TABLES <= set(inspector.get_table_names())
        labels = _enum_labels(engine, "document_classification")
        assert labels == [member.value for member in DocumentClassification]
        assert labels[labels.index("OTHER") - 1] == "MIXED_DOCUMENT"
        assert labels[-1] == "UNKNOWN"
        assert _enum_labels(engine, "classification_run_status") == [
            member.value for member in ClassificationRunStatus
        ]
        assert _enum_labels(engine, "classification_stage") == [
            member.value for member in ClassificationStage
        ]
        assert _enum_labels(engine, "classification_scope") == [
            member.value for member in ClassificationScope
        ]
        assert _enum_labels(engine, "confidence_band") == [
            member.value for member in ConfidenceBand
        ]
        assert _enum_labels(engine, "classification_call_kind") == [
            member.value for member in ClassificationCallKind
        ]
        assert RUN_CONSTRAINTS <= _constraint_names(engine, "document_classification_runs")
        assert RUN_INDEXES <= _index_names(engine, "document_classification_runs")
        assert PREDICTION_CONSTRAINTS <= _constraint_names(engine, "classification_predictions")
        assert PREDICTION_INDEXES <= _index_names(engine, "classification_predictions")
        assert CALL_CONSTRAINTS <= _constraint_names(engine, "classification_ai_calls")
        assert CALL_INDEXES <= _index_names(engine, "classification_ai_calls")
        assert "uq_document_pages_id_document_id" in _constraint_names(engine, "document_pages")
        assert "uq_document_processing_runs_id_document_id" in _constraint_names(
            engine, "document_processing_runs"
        )
        assert "fk_revision_documents_accepted_prediction" in _constraint_names(
            engine, "revision_documents"
        )
        call_columns = {
            column["name"] for column in inspector.get_columns("classification_ai_calls")
        }
        assert "estimated_cost_usd" not in call_columns
        assert "pricing_version" not in call_columns
    finally:
        engine.dispose()


@pytest.mark.integration
def test_upgrade_from_0005_preserves_existing_rows(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == PREVIOUS
        seeded = _seed_phase3(engine)
        _alembic(scratch_url, "upgrade", HEAD)
        assert _version(engine) == HEAD
        with engine.connect() as connection:
            page_id = connection.execute(
                text("SELECT id FROM document_pages WHERE id = :id"),
                {"id": seeded["page_id"]},
            ).scalar_one()
            run_id = connection.execute(
                text("SELECT id FROM document_processing_runs WHERE id = :id"),
                {"id": seeded["run_id"]},
            ).scalar_one()
            accepted = connection.execute(
                text(
                    "SELECT accepted_classification_prediction_id FROM revision_documents "
                    "WHERE id = :id"
                ),
                {"id": seeded["association_id"]},
            ).scalar_one()
            counts = [
                connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in sorted(PHASE4_TABLES)
            ]
        assert page_id == seeded["page_id"]
        assert run_id == seeded["run_id"]
        assert accepted is None
        assert counts == [0, 0, 0]
    finally:
        engine.dispose()


@pytest.mark.integration
def test_downgrade_leaves_mixed_document_and_reupgrade_succeeds(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        seeded = _seed_phase3(engine)
        _alembic(scratch_url, "upgrade", HEAD)
        _alembic(scratch_url, "downgrade", PREVIOUS)

        assert _version(engine) == PREVIOUS
        inspector = inspect(engine)
        assert not (PHASE4_TABLES & set(inspector.get_table_names()))
        assert _enum_types(engine) == set()
        columns = {column["name"] for column in inspector.get_columns("revision_documents")}
        assert "accepted_classification_prediction_id" not in columns
        assert "uq_document_pages_id_document_id" not in _constraint_names(engine, "document_pages")
        labels = _enum_labels(engine, "document_classification")
        assert labels.count("MIXED_DOCUMENT") == 1
        with engine.connect() as connection:
            page_id = connection.execute(
                text("SELECT id FROM document_pages WHERE id = :id"),
                {"id": seeded["page_id"]},
            ).scalar_one()
        assert page_id == seeded["page_id"]

        _alembic(scratch_url, "upgrade", HEAD)
        assert _version(engine) == HEAD
        assert _enum_types(engine) == PHASE4_ENUMS
        assert _enum_labels(engine, "document_classification").count("MIXED_DOCUMENT") == 1
    finally:
        engine.dispose()
