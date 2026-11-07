"""Verify fresh schema, M3 preservation and an accepted v4 retry across the upgrade."""

import json
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from enrichment_support import Delivery
from extraction_worker.extraction_tasks import provider_for
from powerforge_document_processing.models import Document
from powerforge_document_processing.processing import ProcessingService
from powerforge_document_processing.storage import InMemoryObjectStorage
from powerforge_extraction.enriched_planning import start_enriched
from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding
from powerforge_extraction.enrichment_prepare import sha
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.layout_execution import execute_enrichment
from powerforge_extraction.layout_models import SourceSpatialResult
from powerforge_extraction.layout_service import start_layout
from powerforge_extraction.models import Evidence, ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.table_fake import FakeTableProvider
from powerforge_shared.config import Settings
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
PREVIOUS = "0015_source_spatial_layout"
HEAD = "0016_enriched_extraction"


def test_fresh_head_enriched_columns_match_the_orm(scratch_url):
    _alembic(scratch_url, "upgrade", "head")
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        for model in (Evidence, RunSourceEnrichmentBinding):
            columns = {
                c["name"]: c["nullable"] for c in inspect(engine).get_columns(model.__tablename__)
            }
            assert columns == {c.name: c.nullable for c in model.__table__.columns}
        fks = {c["name"] for c in inspect(engine).get_foreign_keys("extraction_evidence")}
        assert {"fk_evidence_enriched_text", "fk_evidence_enriched_geometry"} <= fks
    finally:
        engine.dispose()


def test_upgrade_preserves_m3_results_and_active_v4_retry_and_downgrade_guards(scratch_url):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    factory = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    storage = InMemoryObjectStorage()
    record = json.loads(
        Path("tests/fixtures/enrichment/preparation_v1_environment.json").read_text()
    )
    settings = Settings(
        _env_file=None,
        enrichment_enabled=True,
        extraction_backoff_seconds=0,
        enrichment_ocr_configuration=json.dumps(record["configuration"]),
    )
    try:
        seeded = _seed_phase3(engine)
        document_id = seeded["document_id"]
        payload = Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes()
        with factory.begin() as session:
            document = session.get(Document, document_id)
            document.sha256 = sha(payload)
            document.size_bytes = len(payload)
            storage.put(document.storage_key, BytesIO(payload), len(payload), "application/pdf")
        with factory() as session:
            processing = ProcessingService(session, storage, Delivery())
            base = processing.ensure_document_processing(document_id)
            processing.claim_and_process(base.id)
            processing_id = base.id
        with factory.begin() as session:
            local = start_layout(session, settings, document_id, processing_id, [1], [])
            local_units = {
                u.stage: u.id
                for u in session.scalars(
                    select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == local.id)
                )
            }

        def forbidden():
            raise AssertionError("Native source must not recognize again")

        for stage in ("SOURCE_PREPARE", "SPATIAL_LAYOUT"):
            assert execute_enrichment(local_units[stage], factory, storage, settings, forbidden)
        with factory.begin() as session:
            layout = session.scalar(
                select(SourceSpatialResult).where(SourceSpatialResult.run_id == local.id)
            )
            assert layout is not None
            old = ExtractionCoordinator(session, settings).start(
                document_id, profile_key="tables-test-v1", pages=[1]
            )
            initial = session.scalar(
                select(ExtractionWorkUnit.id).where(
                    ExtractionWorkUnit.run_id == old.id,
                    ExtractionWorkUnit.stage == "TABLE_RECONSTRUCTION",
                )
            )
        assert execute_unit(
            initial, factory, storage, settings, lambda _: FakeTableProvider("transient")
        )

        def snapshot():
            with engine.connect() as connection:
                return {
                    table: connection.scalars(
                        text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")
                    ).all()
                    for table in (
                        "page_artifacts",
                        "source_enrichment_page_results",
                        "source_enrichment_artifacts",
                        "source_spatial_results",
                        "extraction_runs",
                        "extraction_work_units",
                        "extraction_run_execution",
                        "extraction_unit_execution",
                    )
                }

        before = snapshot()
        _alembic(scratch_url, "upgrade", HEAD)
        assert snapshot() == before
        with factory() as session:
            attempts = list(
                session.scalars(
                    select(ExtractionWorkUnit).where(
                        ExtractionWorkUnit.run_id == old.id, ExtractionWorkUnit.status == "PENDING"
                    )
                )
            )
        retry = next(a for a in attempts if a.stage == "TABLE_RECONSTRUCTION")
        assert retry.attempt_number == 2
        assert execute_unit(retry.id, factory, storage, settings, provider_for)
        second = next(a for a in attempts if a.stage == "TABLE_INTERPRETATION")
        assert execute_unit(second.id, factory, storage, settings, provider_for)
        with factory() as session:
            assert session.get(ExtractionRun, old.id).status == "COMPLETED"
            assert all(
                e.source_locator is None
                for e in session.scalars(select(Evidence).where(Evidence.run_id == old.id))
            )

        before_downgrade = snapshot()
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert snapshot() == before_downgrade
        _alembic(scratch_url, "upgrade", HEAD)
        with factory.begin() as session:
            start_enriched(
                ExtractionCoordinator(session, settings),
                document_id,
                None,
                "tables-test-enriched-v1",
                [1],
                "ensure",
                [dict(prepared_result_id=layout.prepared_result_id, spatial_result_id=layout.id)],
            )
        with pytest.raises(AssertionError, match="Cannot discard enhanced extraction history"):
            _alembic(scratch_url, "downgrade", PREVIOUS)
        assert _version(engine) == HEAD
    finally:
        engine.dispose()
