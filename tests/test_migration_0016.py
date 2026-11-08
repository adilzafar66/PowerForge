"""Verify fresh schema, M3 preservation and an accepted v4 retry across the upgrade."""

import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

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
from powerforge_extraction.profiles import FAKE_PROFILE, resolve_profile
from powerforge_extraction.table_fake import FakeTableProvider
from powerforge_shared.config import Settings
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
PREVIOUS = "0015_source_spatial_layout"
HEAD = "0016_enriched_extraction"


def test_accepted_0013_pending_probe_executes_after_upgrade_to_head(scratch_url):
    _alembic(scratch_url, "upgrade", "0013_extraction_execution")
    engine = create_engine(scratch_url)
    factory = sessionmaker(engine, autoflush=False)
    storage = InMemoryObjectStorage()
    settings = Settings(_env_file=None)
    profile = resolve_profile(FAKE_PROFILE, settings)
    original = b"Rated 750 kVA"
    key = "legacy-probe.txt"
    storage.put(key, BytesIO(original), len(original), "text/plain")
    try:
        ids = _seed_phase3(engine) | {
            "rid": uuid4(),
            "uid": uuid4(),
            "artifact": uuid4(),
            "key": key,
            "size": len(original),
            "digest": sha(original),
            "provider": profile.provider,
            "model": profile.model,
            "stage": profile.stage,
            "version": profile.version,
            "profile_hash": profile.identity_hash,
            "schema": profile.schema_version,
            "prompt_version": profile.prompt_version,
            "prompt_hash": profile.prompt_hash,
            "configuration": profile.model_dump_json(),
        }
        ids["artifacts"] = json.dumps([str(ids["artifact"])])
        with engine.begin() as connection:
            for statement in (
                """INSERT INTO page_artifacts(id,processing_run_id,document_page_id,artifact_type,
                     storage_key,mime_type,size_bytes,sha256)
                   VALUES(:artifact,:run_id,:page_id,'NATIVE_TEXT',:key,'text/plain',:size,:digest)""",
                """INSERT INTO extraction_runs(id,document_id,processing_run_id,extractor_version,
                     schema_version,registry_version,profile_version,profile_hash,input_identity_hash,
                     provider,model,prompt_version,prompt_hash,selected_pages,stages,input_artifact_ids,
                     status,units_total)
                   VALUES(:rid,:document_id,:run_id,'v1',:schema,'registry-v1',:version,:profile_hash,
                     :digest,:provider,:model,:prompt_version,:prompt_hash,'[1]',
                     jsonb_build_array(cast(:stage as text)),
                     cast(:artifacts as jsonb),'PENDING',1)""",
                """INSERT INTO extraction_work_units(id,run_id,document_id,processing_run_id,
                     unit_key,stage,page_numbers,input_artifact_ids,required,attempt_number,status)
                   VALUES(:uid,:rid,:document_id,:run_id,'SOURCE_PROBE:page:000001',:stage,'[1]',
                     cast(:artifacts as jsonb),true,1,'PENDING')""",
                """INSERT INTO extraction_run_execution(run_id,configuration)
                   VALUES(:rid,cast(:configuration as jsonb))""",
                """INSERT INTO extraction_unit_execution(work_unit_id,run_id,unit_key,
                     available_at,dispatch_after)
                   VALUES(:uid,:rid,'SOURCE_PROBE:page:000001',now(),now())""",
            ):
                connection.execute(text(statement), ids)
        _alembic(scratch_url, "upgrade", "head")
        assert _version(engine) == HEAD
        assert execute_unit(ids["uid"], factory, storage, settings, provider_for)
        with factory() as session:
            run = session.get(ExtractionRun, ids["rid"])
            assert (run.execution_purpose, run.status, run.profile_hash) == (
                "EXTRACTION",
                "COMPLETED",
                profile.identity_hash,
            )
            evidence = session.scalar(select(Evidence).where(Evidence.run_id == run.id))
            assert evidence.page_artifact_id == ids["artifact"] and evidence.source_locator is None
            assert (
                original.decode()[evidence.text_start : evidence.text_end]
                == evidence.source_snippet
            )
    finally:
        engine.dispose()


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
