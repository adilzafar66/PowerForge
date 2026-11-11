"""Upgrade 6F history without backfilling or reinterpreting prior attempts."""

from io import BytesIO

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from extraction_worker.extraction_tasks import provider_for
from powerforge_document_processing.storage import InMemoryObjectStorage
from powerforge_extraction.enrichment_prepare import sha
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.models import Evidence, ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_shared.config import Settings
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
PREVIOUS = "0017_extraction_operations"
REVISION = "0018_extraction_stage_trace"


def test_upgrade_and_empty_downgrade_preserve_historical_and_pending_attempts(scratch_url):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    factory = sessionmaker(engine, autoflush=False)
    storage = InMemoryObjectStorage()
    settings = Settings(_env_file=None)
    original = b"Rated 350 kVA"
    key = "legacy-native-fixture.txt"
    storage.put(key, BytesIO(original), len(original), "text/plain")

    try:
        source = _seed_phase3(engine)
        with engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO page_artifacts(processing_run_id,document_page_id,artifact_type,
                    storage_key,mime_type,size_bytes,sha256)
                VALUES(:run_id,:page_id,'NATIVE_TEXT',:key,'text/plain',:size,:digest)
            """),
                source | {"key": key, "size": len(original), "digest": sha(original)},
            )

        def admit(mode):
            with factory.begin() as session:
                run = ExtractionCoordinator(session, settings).start(
                    source["document_id"], mode=mode
                )
                unit = session.scalar(
                    select(ExtractionWorkUnit.id).where(ExtractionWorkUnit.run_id == run.id)
                )
                return run.id, unit, run.profile_hash

        completed_id, completed_unit, _ = admit("ensure")
        assert execute_unit(completed_unit, factory, storage, settings, provider_for)
        pending_id, pending_unit, profile_hash = admit("reextract")

        def history():
            with engine.connect() as connection:
                return connection.execute(
                    text("""
                    SELECT to_jsonb(u), to_jsonb(e)
                    FROM extraction_work_units u JOIN extraction_evidence e ON u.id = e.work_unit_id
                    WHERE u.id = :unit
                """),
                    {"unit": completed_unit},
                ).one()

        before = history()
        _alembic(scratch_url, "upgrade", REVISION)
        assert _version(engine) == REVISION
        assert history() == before
        assert execute_unit(pending_unit, factory, storage, settings, provider_for)
        with factory() as session:
            run = session.get(ExtractionRun, pending_id)
            assert run.status == "COMPLETED" and run.profile_hash == profile_hash
            evidence = session.scalar(select(Evidence).where(Evidence.run_id == pending_id))
            assert evidence.source_snippet == original.decode()
            assert session.get(ExtractionRun, completed_id).status == "COMPLETED"
            assert session.scalar(text("SELECT count(*) FROM extraction_stage_traces")) == 0
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert "extraction_stage_traces" not in inspect(engine).get_table_names()
        assert history() == before
    finally:
        engine.dispose()
