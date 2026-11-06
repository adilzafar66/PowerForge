"""Real forward schema and preservation of a published 0014 preparation."""

import json
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from enrichment_support import Delivery
from powerforge_document_processing.models import Document
from powerforge_document_processing.processing import ProcessingService
from powerforge_document_processing.storage import InMemoryObjectStorage
from powerforge_extraction.enrichment_execution import execute_preparation
from powerforge_extraction.enrichment_prepare import sha
from powerforge_extraction.enrichment_service import start_preparation
from powerforge_extraction.layout_models import SourcePreparationReceipt, SourceSpatialResult
from powerforge_extraction.layout_service import start_layout
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_shared.config import Settings
from test_enrichment_native import native_pdf
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
PREVIOUS = "0014_source_enrichment"
HEAD = "0015_source_spatial_layout"


def test_fresh_spatial_schema_has_exact_orm_columns_and_guards(scratch_url):
    _alembic(scratch_url, "upgrade", "head")
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        for model in (SourcePreparationReceipt, SourceSpatialResult):
            columns = {c["name"]: c for c in inspect(engine).get_columns(model.__tablename__)}
            assert set(columns) == set(model.__table__.columns.keys())
            assert all(columns[c.name]["nullable"] == c.nullable for c in model.__table__.columns)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname='source_spatial_guard'")
                )
                == 2
            )
    finally:
        engine.dispose()


def test_0014_published_preparation_survives_upgrade_downgrade_and_reupgrade(scratch_url):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    storage = InMemoryObjectStorage()
    configuration = json.loads(
        Path("tests/fixtures/enrichment/preparation_v1_environment.json").read_text()
    )["configuration"]
    settings = Settings(
        _env_file=None,
        enrichment_enabled=True,
        enrichment_ocr_configuration=json.dumps(configuration),
        extraction_backoff_seconds=0,
    )
    try:
        seeded = _seed_phase3(engine)
        payload = native_pdf()
        with factory.begin() as session:
            document = session.get(Document, seeded["document_id"])
            document.sha256 = sha(payload)
            document.size_bytes = len(payload)
            storage.put(document.storage_key, BytesIO(payload), len(payload), "application/pdf")
        with factory() as session:
            processing = ProcessingService(session, storage, Delivery())
            base = processing.ensure_document_processing(seeded["document_id"])
            processing.claim_and_process(base.id)
            processing_id = base.id
        with factory.begin() as session:
            run = start_preparation(
                session, settings, seeded["document_id"], processing_id, [1], []
            )
            unit_id = session.scalar(
                select(ExtractionWorkUnit.id).where(ExtractionWorkUnit.run_id == run.id)
            )

        def forbidden():
            raise AssertionError("Native migration fixture must not invoke OCR")

        assert execute_preparation(unit_id, factory, storage, settings, forbidden)

        def snapshot():
            with engine.connect() as connection:
                return {
                    table: connection.execute(
                        text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")
                    )
                    .scalars()
                    .all()
                    for table in (
                        "documents",
                        "document_pages",
                        "document_processing_runs",
                        "page_artifacts",
                        "extraction_runs",
                        "extraction_work_units",
                        "extraction_run_execution",
                        "extraction_unit_execution",
                        "source_enrichment_page_results",
                        "source_enrichment_artifacts",
                    )
                }

        before = snapshot()
        assert len(before["source_enrichment_page_results"]) == 1, json.dumps(
            before["extraction_work_units"]
        )
        objects_before = dict(storage.objects)
        _alembic(scratch_url, "upgrade", "head")
        assert snapshot() == before and storage.objects == objects_before
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert snapshot() == before
        _alembic(scratch_url, "upgrade", "head")
        assert snapshot() == before
        with factory.begin() as session:
            start_layout(session, settings, seeded["document_id"], processing_id, [1], [])
        with pytest.raises(AssertionError, match="Cannot discard source layout history"):
            _alembic(scratch_url, "downgrade", PREVIOUS)
        assert _version(engine) == HEAD
    finally:
        engine.dispose()
