"""Fresh schema and representative Phase 5 upgrade/downgrade preservation."""

import pytest
from sqlalchemy import create_engine, inspect, text

from powerforge_extraction import models
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
HEAD = "0011_extraction_persistence"
PREVIOUS = "0010_authoring_refinement"


def test_fresh_schema_matches_orm(scratch_url):
    _alembic(scratch_url, "upgrade", HEAD)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        inspector = inspect(engine)
        for model in [
            models.ExtractionRun,
            models.ExtractionWorkUnit,
            models.SourceGroup,
            models.ExtractedTable,
            models.Evidence,
            models.ExtractionCandidate,
            models.CandidateEvidence,
            models.ExtractionAICall,
        ]:
            actual = {c["name"]: c for c in inspector.get_columns(model.__tablename__)}
            current = set(model.__table__.columns.keys())
            if model is models.ExtractionRun:
                current.remove("execution_purpose")
            if model is models.Evidence:
                current -= {"enrichment_artifact_id", "geometry_artifact_id", "source_locator"}
            assert set(actual) == current
            for col in model.__table__.columns:
                if col.name == "execution_purpose":
                    continue
                if model is models.Evidence and col.name in {
                    "enrichment_artifact_id",
                    "geometry_artifact_id",
                    "source_locator",
                }:
                    continue
                historical_required = model is models.ExtractionRun and col.name in {
                    "registry_version",
                    "model",
                    "prompt_version",
                    "prompt_hash",
                }
                assert actual[col.name]["nullable"] == (
                    False if historical_required else col.nullable
                )
                if hasattr(col.type, "enums"):
                    assert actual[col.name]["type"].enums == col.type.enums
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_preserve_all_phase5_data(scratch_url):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        seeded = _seed_phase3(engine)
        with engine.begin() as conn:
            project, revision = conn.execute(
                text("SELECT project_id, revision_id FROM revision_documents WHERE id=:a"),
                {"a": seeded["association_id"]},
            ).one()
            params = {
                "p": project,
                "r": revision,
                "d": seeded["document_id"],
                "processing": seeded["run_id"],
            }
            lineage = conn.execute(
                text("INSERT INTO equipment_lineages(project_id) VALUES (:p) RETURNING id"), params
            ).scalar_one()
            eq = conn.execute(
                text(
                    "INSERT INTO equipment(project_id,revision_id,lineage_id,equipment_type) "
                    "VALUES (:p,:r,:l,'CABLE') RETURNING id"
                ),
                {**params, "l": lineage},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO "
                    "equipment_attributes(project_id,revision_id,equipment_id,attribute_key,value_type,information_state,numeric_value,unit)"
                    " VALUES (:p,:r,:e,'length','NUMBER','PRESENT',123.1234567890123456789,'m')"
                ),
                {**params, "e": eq},
            )
            a = conn.execute(
                text(
                    "INSERT INTO "
                    "model_nodes(project_id,revision_id,equipment_id,kind,terminal_key) VALUES "
                    "(:p,:r,:e,'EQUIPMENT_TERMINAL','END_A') RETURNING id"
                ),
                {**params, "e": eq},
            ).scalar_one()
            b = conn.execute(
                text(
                    "INSERT INTO "
                    "model_nodes(project_id,revision_id,equipment_id,kind,terminal_key) VALUES "
                    "(:p,:r,:e,'EQUIPMENT_TERMINAL','END_B') RETURNING id"
                ),
                {**params, "e": eq},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO "
                    "model_connections(project_id,revision_id,from_node_id,to_node_id) VALUES "
                    "(:p,:r,:a,:b)"
                ),
                {**params, "a": a, "b": b},
            )
            conn.execute(
                text(
                    "INSERT INTO "
                    "document_classification_runs(document_id,processing_run_id,classifier_version,taxonomy_version,prompt_version,sampling_profile_version,sampling_profile_hash,classifier_identity_hash,provider,model,status)"
                    " VALUES "
                    "(:d,:processing,'v1','v1','v1','v1','hash','identity','fake','fake','COMPLETED')"
                ),
                params,
            )
        tables = [
            "projects",
            "project_revisions",
            "documents",
            "revision_documents",
            "document_pages",
            "document_processing_runs",
            "document_classification_runs",
            "equipment_lineages",
            "equipment",
            "equipment_attributes",
            "model_nodes",
            "model_connections",
        ]

        def snapshot():
            with engine.connect() as conn:
                return {
                    table: conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
                    .scalars()
                    .all()
                    for table in tables
                }

        before = snapshot()
        _alembic(scratch_url, "upgrade", HEAD)
        assert _version(engine) == HEAD
        assert snapshot() == before
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert snapshot() == before
        assert "extraction_runs" not in inspect(engine).get_table_names()
        _alembic(scratch_url, "upgrade", HEAD)
        assert snapshot() == before
    finally:
        engine.dispose()
