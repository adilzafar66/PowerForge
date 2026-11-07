"""Fresh execution schema and data-preserving 0012 upgrade/downgrade."""

import pytest
from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.orm import Session, registry

from extraction_support import run_and_unit
from legacy_extraction_support import historical_run_mapper
from powerforge_document_processing.models import PageArtifact
from powerforge_extraction.contracts import (
    CandidateEvidenceInput,
    CandidateInput,
    EvidenceInput,
    WorkUnitOutput,
)
from powerforge_extraction.controls import RunExecution, UnitExecution
from powerforge_extraction.persistence import ExtractionPersistence
from powerforge_provenance.locations import SourceLocation
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
HEAD = "0013_extraction_execution"
PREVIOUS = "0012_extraction_terminal_guard"


def test_fresh_execution_schema_matches_orm(scratch_url):
    _alembic(scratch_url, "upgrade", HEAD)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        for model in [RunExecution, UnitExecution]:
            actual = {c["name"]: c for c in inspect(engine).get_columns(model.__tablename__)}
            assert set(actual) == set(model.__table__.columns.keys())
            assert all(actual[c.name]["nullable"] == c.nullable for c in model.__table__.columns)
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname='extraction_fence_guard'")
                )
                == 7
            )
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_preserve_existing_source_and_6a_guards(scratch_url, monkeypatch):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        historical_run_mapper(monkeypatch, engine)
        import powerforge_extraction.persistence as persistence

        class HistoricalEvidence:
            pass

        evidence_table = Table("extraction_evidence", MetaData(), autoload_with=engine)
        registry().map_imperatively(HistoricalEvidence, evidence_table)
        monkeypatch.setattr(persistence, "Evidence", HistoricalEvidence)
        seeded = _seed_phase3(engine)
        with Session(engine) as session:
            artifact = PageArtifact(
                document_page_id=seeded["page_id"],
                processing_run_id=seeded["run_id"],
                artifact_type="NATIVE_TEXT",
                storage_key="legacy-6a-text",
                mime_type="text/plain",
                size_bytes=1,
                sha256="legacy",
            )
            session.add(artifact)
            session.flush()
            src = {
                "document": seeded["document_id"],
                "processing": seeded["run_id"],
                "artifact": artifact.id,
            }
            run, unit = run_and_unit(session, src)
            evidence = EvidenceInput(
                location=SourceLocation(document_page_id=seeded["page_id"]),
                source_kind="VISUAL_REGION",
                extraction_method="AI_VISION",
                source_snippet="Legacy source claim",
            )
            candidate = CandidateInput(
                kind="ATTRIBUTE_VALUE",
                mapping_status="MAPPED",
                raw_text="Legacy length",
                equipment_type_key="CABLE",
                attribute_key="length",
                value_type="NUMBER",
                unit="m",
                numeric_value="0.1234567890123456789",
            )
            ExtractionPersistence(session).publish(
                unit.id,
                WorkUnitOutput(
                    evidence=[evidence],
                    candidates=[candidate],
                    candidate_evidence=[
                        CandidateEvidenceInput(candidate_id=candidate.id, evidence_id=evidence.id)
                    ],
                ),
            )
            run.status = "COMPLETED"
            session.commit()

        def snapshot():
            with engine.connect() as conn:
                return [
                    conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
                    .scalars()
                    .all()
                    for table in [
                        "projects",
                        "project_revisions",
                        "documents",
                        "revision_documents",
                        "document_pages",
                        "document_processing_runs",
                        "page_artifacts",
                        "extraction_runs",
                        "extraction_work_units",
                        "extraction_evidence",
                        "extraction_candidates",
                        "candidate_evidence",
                    ]
                ]

        before = snapshot()
        _alembic(scratch_url, "upgrade", HEAD)
        assert snapshot() == before
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert snapshot() == before
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname='extraction_terminal_guard'")
                )
                == 1
            )
            assert (
                conn.scalar(
                    text("SELECT count(*) FROM document_pages WHERE id=:id"),
                    {"id": seeded["page_id"]},
                )
                == 1
            )
        _alembic(scratch_url, "upgrade", HEAD)
        assert snapshot() == before
    finally:
        engine.dispose()
