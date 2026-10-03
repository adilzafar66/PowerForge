"""Migration 0004 against scratch databases. Requires RUN_INTEGRATION=1.

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
    DocumentClassification,
    DocumentOrigin,
    RevisionDocumentStatus,
)
from powerforge_shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = "database/alembic.ini"

PHASE2_TABLES = {"documents", "revision_documents"}
PHASE2_ENUMS = {"document_classification", "document_origin", "revision_document_status"}
LINEAGE_CONSTRAINTS = {
    "uq_project_revisions_project_id_id",
    "fk_project_revisions_based_on",
    "ck_project_revisions_based_on_not_self",
}
DOCUMENT_CONSTRAINTS = {
    "fk_documents_project_id",
    "uq_documents_storage_key",
    "uq_documents_project_id_id",
    "ck_documents_size_positive",
}
REVISION_DOCUMENT_CONSTRAINTS = {
    "uq_revision_documents_revision_id_document_id",
    "fk_revision_documents_revision",
    "fk_revision_documents_document",
    "fk_revision_documents_inherited_from",
    "ck_revision_documents_origin_inherited_from",
    "ck_revision_documents_status_removed_at",
    "ck_revision_documents_inherited_not_self",
}
REVISION_DOCUMENT_INDEXES = {
    "ix_revision_documents_revision_id",
    "ix_revision_documents_document_id",
    "ix_revision_documents_revision_id_status",
    "ix_revision_documents_revision_id_document_type",
}
DOCUMENT_INDEXES = {"ix_documents_project_id", "ix_documents_project_id_sha256"}


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


def _existing_enum_types(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT typname FROM pg_type WHERE typname = ANY(:names)"),
            {"names": sorted(PHASE2_ENUMS)},
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


def _seed_phase1_rows(engine: Engine) -> tuple[uuid.UUID, list[uuid.UUID]]:
    with engine.begin() as connection:
        project_id = connection.execute(
            text(
                "INSERT INTO projects (project_number, project_name) "
                "VALUES (:number, 'Legacy') RETURNING id"
            ),
            {"number": f"MIG-{uuid.uuid4().hex[:8]}"},
        ).scalar_one()
        revision_ids = [
            connection.execute(
                text(
                    "INSERT INTO project_revisions (project_id, identifier) "
                    "VALUES (:project_id, :identifier) RETURNING id"
                ),
                {"project_id": project_id, "identifier": identifier},
            ).scalar_one()
            for identifier in ("0", "1")
        ]
    return project_id, revision_ids


@pytest.mark.integration
def test_fresh_upgrade_reaches_0004_with_expected_schema(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", "head")
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == "0004_documents_and_lineage"

        inspector = inspect(engine)
        assert PHASE2_TABLES <= set(inspector.get_table_names())
        columns = {column["name"] for column in inspector.get_columns("project_revisions")}
        assert "based_on_revision_id" in columns

        assert LINEAGE_CONSTRAINTS <= _constraint_names(engine, "project_revisions")
        assert DOCUMENT_CONSTRAINTS <= _constraint_names(engine, "documents")
        assert REVISION_DOCUMENT_CONSTRAINTS <= _constraint_names(engine, "revision_documents")
        assert DOCUMENT_INDEXES <= _index_names(engine, "documents")
        assert REVISION_DOCUMENT_INDEXES <= _index_names(engine, "revision_documents")

        assert _enum_labels(engine, "document_classification") == [
            member.value for member in DocumentClassification
        ]
        assert _enum_labels(engine, "document_origin") == [
            member.value for member in DocumentOrigin
        ]
        assert _enum_labels(engine, "revision_document_status") == [
            member.value for member in RevisionDocumentStatus
        ]
    finally:
        engine.dispose()


@pytest.mark.integration
def test_upgrade_from_0003_preserves_existing_rows(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", "0003_status_before_archive")
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == "0003_status_before_archive"
        assert not (PHASE2_TABLES & set(inspect(engine).get_table_names()))
        project_id, revision_ids = _seed_phase1_rows(engine)

        _alembic(scratch_url, "upgrade", "head")

        assert _version(engine) == "0004_documents_and_lineage"
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT id, project_id, based_on_revision_id FROM project_revisions "
                    "WHERE project_id = :project_id ORDER BY identifier"
                ),
                {"project_id": project_id},
            ).all()
        assert [row.id for row in rows] == revision_ids
        assert all(row.project_id == project_id for row in rows)
        assert all(row.based_on_revision_id is None for row in rows)
    finally:
        engine.dispose()


@pytest.mark.integration
def test_downgrade_to_0003_and_reupgrade(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", "0003_status_before_archive")
    engine = create_engine(scratch_url)
    try:
        project_id, revision_ids = _seed_phase1_rows(engine)
        _alembic(scratch_url, "upgrade", "head")

        _alembic(scratch_url, "downgrade", "0003_status_before_archive")

        assert _version(engine) == "0003_status_before_archive"
        inspector = inspect(engine)
        assert not (PHASE2_TABLES & set(inspector.get_table_names()))
        columns = {column["name"] for column in inspector.get_columns("project_revisions")}
        assert "based_on_revision_id" not in columns
        assert not (LINEAGE_CONSTRAINTS & _constraint_names(engine, "project_revisions"))
        assert _existing_enum_types(engine) == set()
        with engine.connect() as connection:
            surviving = (
                connection.execute(
                    text("SELECT id FROM project_revisions WHERE project_id = :project_id"),
                    {"project_id": project_id},
                )
                .scalars()
                .all()
            )
        assert sorted(surviving) == sorted(revision_ids)

        _alembic(scratch_url, "upgrade", "head")
        assert _version(engine) == "0004_documents_and_lineage"
        assert _existing_enum_types(engine) == PHASE2_ENUMS
    finally:
        engine.dispose()
