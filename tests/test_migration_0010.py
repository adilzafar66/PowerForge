"""Fresh schema and representative 0009 data survive the authoring refinement."""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from engineering_support import seed_revision
from powerforge_engineering_model import InformationState
from powerforge_engineering_model.terminal_profiles import TERMINAL_PROFILES
from test_migration_0006 import _alembic, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
HEAD = "0010_authoring_refinement"


def test_refinement_migrates_existing_attributes_terminals_and_connections(scratch_url):
    _alembic(scratch_url, "upgrade", "0009_topology_persistence")
    engine = create_engine(scratch_url)
    try:
        with Session(engine) as session:
            project, revision = seed_revision(session)
        with engine.begin() as conn:
            equipment_ids = {}
            for kind in TERMINAL_PROFILES:
                lineage = conn.execute(
                    text("INSERT INTO equipment_lineages(project_id) VALUES (:p) RETURNING id"),
                    {"p": project},
                ).scalar_one()
                eq = conn.execute(
                    text(
                        "INSERT INTO "
                        "equipment(project_id,revision_id,lineage_id,equipment_type) VALUES "
                        "(:p,:r,:l,:t) RETURNING id"
                    ),
                    {"p": project, "r": revision, "l": lineage, "t": kind.value},
                ).scalar_one()
                equipment_ids[kind.value] = eq
            owner = equipment_ids["CABLE"]
            params = {"p": project, "r": revision, "e": owner}
            for key, state in [("length", "NOT_EXTRACTED"), ("phase_count", "UNKNOWN")]:
                conn.execute(
                    text(
                        "INSERT INTO "
                        "equipment_attributes(project_id,revision_id,"
                        "equipment_id,attribute_key,value_type,information_state) "
                        "VALUES (:p,:r,:e,:k,'NUMBER',CAST(:s AS model_information_state))"
                    ),
                    {**params, "k": key, "s": state},
                )
            a = conn.execute(
                text(
                    "INSERT INTO "
                    "model_nodes(project_id,revision_id,equipment_id,kind,terminal_key,label) "
                    "VALUES (:p,:r,:e,'EQUIPMENT_TERMINAL','END_A','Existing label') RETURNING id"
                ),
                params,
            ).scalar_one()
            custom = conn.execute(
                text(
                    "INSERT INTO "
                    "model_nodes(project_id,revision_id,equipment_id,kind,terminal_key) VALUES "
                    "(:p,:r,:e,'EQUIPMENT_TERMINAL','GROUND') RETURNING id"
                ),
                params,
            ).scalar_one()
            edge = conn.execute(
                text(
                    "INSERT INTO "
                    "model_connections(project_id,revision_id,from_node_id,to_node_id) VALUES "
                    "(:p,:r,:a,:b) RETURNING id"
                ),
                {**params, "a": a, "b": custom},
            ).scalar_one()
            conn.execute(
                text(
                    "UPDATE equipment SET lifecycle_status='REMOVED', removed_at=now() WHERE id=:e"
                ),
                {"e": equipment_ids["BUS"]},
            )
        _alembic(scratch_url, "upgrade", "head")
        assert _version(engine) == HEAD
        enums = {e["name"]: e["labels"] for e in inspect(engine).get_enums()}
        assert enums["model_information_state"] == [s.value for s in InformationState]
        with engine.connect() as conn:
            states = dict(
                conn.execute(
                    text(
                        "SELECT attribute_key,information_state::text FROM equipment_attributes "
                        "WHERE equipment_id=:e"
                    ),
                    {"e": owner},
                ).all()
            )
            assert states == {"length": "NOT_POPULATED", "phase_count": "MISSING"}
            nodes = (
                conn.execute(
                    text(
                        "SELECT "
                        "id,equipment_id,terminal_key,managed_by_profile,"
                        "lifecycle_status::text,label FROM model_nodes"
                    )
                )
                .mappings()
                .all()
            )
            for kind, keys in TERMINAL_PROFILES.items():
                assert {
                    n["terminal_key"]
                    for n in nodes
                    if n["equipment_id"] == equipment_ids[kind.value] and n["managed_by_profile"]
                } == set(keys)
            assert next(n for n in nodes if n["id"] == a)["label"] == "Existing label"
            assert next(n for n in nodes if n["id"] == a)["managed_by_profile"]
            assert not next(n for n in nodes if n["id"] == custom)["managed_by_profile"]
            assert (
                next(n for n in nodes if n["equipment_id"] == equipment_ids["BUS"])[
                    "lifecycle_status"
                ]
                == "REMOVED"
            )
            endpoints = conn.execute(
                text("SELECT from_node_id,to_node_id FROM model_connections WHERE id=:id"),
                {"id": edge},
            ).one()
            assert tuple(endpoints) == (a, custom)
            before = {n["id"] for n in nodes}
        _alembic(scratch_url, "downgrade", "0009_topology_persistence")
        _alembic(scratch_url, "upgrade", "head")
        with engine.connect() as conn:
            assert set(conn.execute(text("SELECT id FROM model_nodes")).scalars()) == before
            assert tuple(
                conn.execute(
                    text("SELECT from_node_id,to_node_id FROM model_connections WHERE id=:id"),
                    {"id": edge},
                ).one()
            ) == (a, custom)
    finally:
        engine.dispose()


def test_refinement_fresh_schema_matches_runtime(scratch_url):
    from powerforge_persistence.engineering import EquipmentAttribute
    from powerforge_persistence.topology import ModelNode

    _alembic(scratch_url, "upgrade", "head")
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        for model in (EquipmentAttribute, ModelNode):
            actual = {c["name"]: c for c in inspect(engine).get_columns(model.__tablename__)}
            assert set(actual) == set(model.__table__.columns.keys())
            for col in model.__table__.columns:
                assert actual[col.name]["nullable"] == col.nullable
                if hasattr(col.type, "enums"):
                    assert actual[col.name]["type"].enums == col.type.enums
    finally:
        engine.dispose()
