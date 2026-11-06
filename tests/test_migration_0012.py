"""The review guard upgrades an existing 0011 database without rewriting outputs."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from extraction_support import inputs
from legacy_extraction_support import historical_run_mapper
from powerforge_extraction.contracts import WorkUnitInput
from powerforge_extraction.persistence import ExtractionPersistence
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
HEAD = "0012_extraction_terminal_guard"
PREVIOUS = "0011_extraction_persistence"


def test_fresh_head_includes_terminal_guard(scratch_url):
    _alembic(scratch_url, "upgrade", HEAD)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname='extraction_terminal_guard'")
                )
                == 1
            )
    finally:
        engine.dispose()


def test_upgrade_preserves_existing_attempts_and_downgrade_restores_0011(scratch_url, monkeypatch):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        historical_run_mapper(monkeypatch, engine)
        seeded = _seed_phase3(engine)
        with engine.begin() as conn:
            artifact = conn.execute(
                text(
                    "INSERT INTO page_artifacts(document_page_id,processing_run_id,artifact_type,"
                    "storage_key,mime_type,size_bytes,sha256) VALUES "
                    "(:page,:processing,'NATIVE_TEXT','pinned','text/plain',1,'hash') RETURNING id"
                ),
                {"page": seeded["page_id"], "processing": seeded["run_id"]},
            ).scalar_one()
        with Session(engine) as session:
            store = ExtractionPersistence(session)
            run = store.create_run(
                inputs(
                    {
                        "document": seeded["document_id"],
                        "processing": seeded["run_id"],
                        "artifact": artifact,
                    }
                )
            )
            run.status = "RUNNING"
            session.flush()
            unit = store.create_work_unit(
                run.id,
                WorkUnitInput(
                    unit_key="active",
                    stage="attributes",
                    page_numbers=[1],
                    input_artifact_ids=[artifact],
                ),
            )
            session.commit()
            run_id, unit_id = run.id, unit.id

        def snapshot():
            with engine.connect() as conn:
                return [
                    conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
                    .scalars()
                    .all()
                    for table in [
                        "documents",
                        "document_pages",
                        "page_artifacts",
                        "extraction_runs",
                        "extraction_work_units",
                    ]
                ]

        before = snapshot()
        _alembic(scratch_url, "upgrade", HEAD)
        assert _version(engine) == HEAD
        assert snapshot() == before
        with engine.connect() as conn:
            with pytest.raises(IntegrityError, match="Terminal extraction runs"):
                conn.execute(
                    text("UPDATE extraction_runs SET status='CANCELLED' WHERE id=:id"),
                    {"id": run_id},
                )
            conn.rollback()
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert snapshot() == before
        _alembic(scratch_url, "upgrade", HEAD)
        assert snapshot() == before
        # Attempts can settle first; the parent then reaches its terminal state normally.
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE extraction_work_units SET status='CANCELLED' WHERE id=:id"),
                {"id": unit_id},
            )
            conn.execute(
                text("UPDATE extraction_runs SET status='CANCELLED' WHERE id=:id"), {"id": run_id}
            )
    finally:
        engine.dispose()
