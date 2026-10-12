"""Migration 0005 against scratch databases. Requires RUN_INTEGRATION=1.

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

from powerforge_document_model import PageArtifactType, ProcessingRunStatus, SourceUnit
from powerforge_shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = "database/alembic.ini"
HEAD = "0005_document_processing"
PREVIOUS = "0004_documents_and_lineage"

PHASE3_TABLES = {"document_pages", "document_processing_runs", "page_artifacts"}
PHASE3_ENUMS = {"processing_run_status", "page_artifact_type", "source_unit"}

PAGE_CONSTRAINTS = {
    "fk_document_pages_document_id",
    "uq_document_pages_document_id_page_number",
    "ck_document_pages_page_number_positive",
    "ck_document_pages_rotation_degrees",
}
PAGE_INDEXES = {"ix_document_pages_document_id"}
RUN_INDEXES = {
    "ix_document_processing_runs_document_id",
    "ix_document_processing_runs_target",
    "uq_document_processing_runs_one_live",
}
ARTIFACT_CONSTRAINTS = {
    "fk_page_artifacts_document_page_id",
    "fk_page_artifacts_processing_run_id",
    "uq_page_artifacts_storage_key",
    "uq_page_artifacts_run_page_type",
}
ARTIFACT_INDEXES = {
    "ix_page_artifacts_document_page_id",
    "ix_page_artifacts_processing_run_id",
}


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
            {"names": sorted(PHASE3_ENUMS)},
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


def _seed_document(engine: Engine) -> tuple[uuid.UUID, str]:
    storage_key = f"projects/{uuid.uuid4()}/documents/{uuid.uuid4()}/original.pdf"
    with engine.begin() as connection:
        project_id = connection.execute(
            text(
                "INSERT INTO projects (project_number, project_name) "
                "VALUES (:number, 'Legacy') RETURNING id"
            ),
            {"number": f"MIG-{uuid.uuid4().hex[:8]}"},
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
    return document_id, storage_key


@pytest.mark.integration
def test_fresh_upgrade_reaches_0005_with_expected_schema(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", HEAD)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        inspector = inspect(engine)
        assert PHASE3_TABLES <= set(inspector.get_table_names())
        assert PAGE_CONSTRAINTS <= _constraint_names(engine, "document_pages")
        assert PAGE_INDEXES <= _index_names(engine, "document_pages")
        assert {"fk_document_processing_runs_document_id"} <= _constraint_names(
            engine, "document_processing_runs"
        )
        assert RUN_INDEXES <= _index_names(engine, "document_processing_runs")
        assert ARTIFACT_CONSTRAINTS <= _constraint_names(engine, "page_artifacts")
        assert ARTIFACT_INDEXES <= _index_names(engine, "page_artifacts")
        assert _enum_labels(engine, "processing_run_status") == [
            member.value for member in ProcessingRunStatus
        ]
        assert _enum_labels(engine, "page_artifact_type") == [
            member.value for member in PageArtifactType
        ]
        assert _enum_labels(engine, "source_unit") == [member.value for member in SourceUnit]
    finally:
        engine.dispose()


@pytest.mark.integration
def test_upgrade_from_0004_preserves_existing_documents(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == PREVIOUS
        document_id, storage_key = _seed_document(engine)

        _alembic(scratch_url, "upgrade", HEAD)

        assert _version(engine) == HEAD
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT id, storage_key FROM documents WHERE id = :id"),
                {"id": document_id},
            ).one()
            counts = [
                connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in sorted(PHASE3_TABLES)
            ]
        assert (row.id, row.storage_key) == (document_id, storage_key)
        assert counts == [0, 0, 0]
    finally:
        engine.dispose()


@pytest.mark.integration
def test_backfill_after_upgrade_from_0004_creates_one_run_per_document(scratch_url: URL) -> None:
    """Documents that predate processing get one run, and a second pass adds none."""
    from sqlalchemy.orm import sessionmaker

    from powerforge_document_processing.backfill import backfill_documents
    from powerforge_document_processing.storage.memory import InMemoryObjectStorage

    class _Enqueue:
        def __init__(self) -> None:
            self.calls: list[uuid.UUID] = []

        def enqueue_document_processing(self, run_id: uuid.UUID) -> None:
            self.calls.append(run_id)

    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        first, _key = _seed_document(engine)
        second, _other = _seed_document(engine)
        _alembic(scratch_url, "upgrade", HEAD)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        storage = InMemoryObjectStorage()
        enqueue = _Enqueue()
        with factory() as session:
            assert backfill_documents(session, storage, enqueue, limit=10) == 2
            counts = dict(
                session.execute(
                    text(
                        "SELECT document_id, count(*) FROM document_processing_runs "
                        "GROUP BY document_id"
                    )
                ).all()
            )
        assert counts == {first: 1, second: 1}
        assert len(enqueue.calls) == 2

        with factory() as session:
            assert backfill_documents(session, storage, enqueue, limit=10) == 2
            again = dict(
                session.execute(
                    text(
                        "SELECT document_id, count(*) FROM document_processing_runs "
                        "GROUP BY document_id"
                    )
                ).all()
            )
        assert again == {first: 1, second: 1}
    finally:
        engine.dispose()


@pytest.mark.integration
def test_downgrade_to_0004_and_reupgrade(scratch_url: URL) -> None:
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        document_id, storage_key = _seed_document(engine)
        _alembic(scratch_url, "upgrade", HEAD)

        _alembic(scratch_url, "downgrade", PREVIOUS)

        assert _version(engine) == PREVIOUS
        inspector = inspect(engine)
        assert not (PHASE3_TABLES & set(inspector.get_table_names()))
        assert _enum_types(engine) == set()
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT id, storage_key FROM documents WHERE id = :id"),
                {"id": document_id},
            ).one()
        assert (row.id, row.storage_key) == (document_id, storage_key)

        _alembic(scratch_url, "upgrade", HEAD)
        assert _version(engine) == HEAD
        assert _enum_types(engine) == PHASE3_ENUMS
    finally:
        engine.dispose()
