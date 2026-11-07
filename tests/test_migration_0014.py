"""Fresh and accepted-0013 upgrade/downgrade against real disposable PostgreSQL."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text

from powerforge_extraction.enrichment_models import (
    RunSourceEnrichmentBinding,
    SourceEnrichmentArtifact,
    SourceEnrichmentPageResult,
)
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
PREVIOUS = "0013_extraction_execution"
HEAD = "0014_source_enrichment"


def test_fresh_local_schema_has_exact_orm_columns_and_guards(scratch_url):
    _alembic(scratch_url, "upgrade", HEAD)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        for model in (
            SourceEnrichmentArtifact,
            SourceEnrichmentPageResult,
            RunSourceEnrichmentBinding,
        ):
            columns = {c["name"]: c for c in inspect(engine).get_columns(model.__tablename__)}
            accepted = set(model.__table__.columns.keys())
            if model is RunSourceEnrichmentBinding:
                accepted -= {"spatial_result_id", "spatial_manifest_hash", "binding_hash"}
            assert set(columns) == accepted
            assert all(
                columns[c.name]["nullable"] == c.nullable
                for c in model.__table__.columns
                if c.name in accepted
            )
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname='source_enrichment_guard'")
                )
                == 11
            )
    finally:
        engine.dispose()


def test_upgrade_preserves_legacy_rows_metadata_and_downgrade_round_trip(scratch_url):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        seeded = _seed_phase3(engine)
        rid = uuid4()
        artifact = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO page_artifacts(id,processing_run_id,document_page_id,artifact_type,
                  storage_key,mime_type,size_bytes,sha256)
                VALUES(:id,:pr,:page,'NATIVE_TEXT','legacy-native','text/plain',1,:sha)
                """),
                dict(id=artifact, pr=seeded["run_id"], page=seeded["page_id"], sha="0" * 64),
            )
            connection.execute(
                text("""
                INSERT INTO extraction_runs(id,document_id,processing_run_id,extractor_version,
                  schema_version,registry_version,profile_version,profile_hash,input_identity_hash,
                  provider,model,prompt_version,prompt_hash,selected_pages,stages,input_artifact_ids,
                  status)
                VALUES(:id,:doc,:pr,'legacy','legacy','registry-v1','legacy','legacy','legacy',
                  'fake','legacy','legacy','legacy','[1]','["SOURCE_PROBE"]',
                  cast(:artifacts as jsonb),'PENDING')
                """),
                dict(
                    id=rid,
                    doc=seeded["document_id"],
                    pr=seeded["run_id"],
                    artifacts=json.dumps([str(artifact)]),
                ),
            )

        def snapshot():
            with engine.connect() as connection:
                return {
                    table: connection.execute(
                        text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id")
                    )
                    .scalars()
                    .all()
                    for table in (
                        "documents",
                        "document_pages",
                        "document_processing_runs",
                        "page_artifacts",
                        "extraction_runs",
                    )
                }

        before = snapshot()
        _alembic(scratch_url, "upgrade", HEAD)
        after = snapshot()
        purpose = after["extraction_runs"][0].pop("execution_purpose")
        assert purpose == "EXTRACTION" and before == after
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert snapshot() == before
        _alembic(scratch_url, "upgrade", HEAD)
        after = snapshot()
        after["extraction_runs"][0].pop("execution_purpose")
        assert before == after
        with engine.connect() as connection:
            original = {"z": ["😀", 1, False, None], "a": "é\né"}
            actual = connection.scalar(
                text("SELECT source_json_canonical(cast(:v as jsonb))"), {"v": json.dumps(original)}
            )
            assert actual == json.dumps(
                original, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
    finally:
        engine.dispose()
