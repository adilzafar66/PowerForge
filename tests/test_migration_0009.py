"""Topology migration alignment and preservation of accepted Phase 5C data."""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Session

from engineering_support import seed_revision
from powerforge_api.services.engineering_model_service import EngineeringModelService
from powerforge_persistence.topology import ModelConnection, ModelNode
from test_migration_0006 import _alembic, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
HEAD = "0009_topology_persistence"
PREVIOUS = "0008_revision_model_metadata"


def assert_schema(engine):
    inspector = inspect(engine)
    for model in [ModelNode, ModelConnection]:
        table = model.__table__
        columns = {c["name"]: c for c in inspector.get_columns(table.name)}
        assert set(columns) == set(table.columns.keys())
        for column in table.columns:
            actual = columns[column.name]
            assert actual["nullable"] == column.nullable
            assert actual["type"]._type_affinity == column.type._type_affinity
            if isinstance(column.type, ENUM):
                assert actual["type"].enums == column.type.enums
                assert not column.type.create_type
        constraints = {
            item["name"]
            for method in [
                inspector.get_unique_constraints,
                inspector.get_foreign_keys,
                inspector.get_check_constraints,
            ]
            for item in method(table.name)
        }
        assert constraints == {c.name for c in table.constraints if c.name}
        indexes = {i["name"]: i for i in inspector.get_indexes(table.name)}
        for index in table.indexes:
            assert indexes[index.name]["column_names"] == [c.name for c in index.columns]
        actual_fks = {fk["name"]: fk for fk in inspector.get_foreign_keys(table.name)}
        for fk in table.foreign_key_constraints:
            assert actual_fks[fk.name]["constrained_columns"] == [
                e.parent.name for e in fk.elements
            ]
            assert actual_fks[fk.name]["referred_columns"] == [e.column.name for e in fk.elements]


def test_fresh_topology_schema(scratch_url):
    _alembic(scratch_url, "upgrade", "head")
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        assert_schema(engine)
    finally:
        engine.dispose()


def test_topology_upgrade_downgrade_preserves_existing_model(scratch_url):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        with Session(engine) as session:
            ids = seed_revision(session)
            equipment = EngineeringModelService(session).create_equipment(*ids, "CABLE")
            equipment_id = equipment.id

        def existing():
            with engine.connect() as conn:
                return {
                    table: conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
                    .scalars()
                    .all()
                    for table in [
                        "projects",
                        "project_revisions",
                        "equipment_lineages",
                        "equipment",
                        "equipment_attributes",
                    ]
                }

        before = existing()
        _alembic(scratch_url, "upgrade", "head")
        assert_schema(engine)
        assert existing() == before
        with engine.begin() as conn:
            for table in ["model_nodes", "model_connections"]:
                assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
            terminal = conn.execute(
                text(
                    "INSERT INTO model_nodes"
                    "(project_id,revision_id,kind,equipment_id,terminal_key) "
                    "VALUES (:p,:r,'EQUIPMENT_TERMINAL',:e,'A') RETURNING id"
                ),
                {"p": ids[0], "r": ids[1], "e": equipment_id},
            ).scalar_one()
            node = conn.execute(
                text(
                    "INSERT INTO model_nodes(project_id,revision_id,kind) "
                    "VALUES (:p,:r,'ELECTRICAL_NODE') RETURNING id"
                ),
                {"p": ids[0], "r": ids[1]},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO model_connections(project_id,revision_id,from_node_id,to_node_id) "
                    "VALUES (:p,:r,:a,:b)"
                ),
                {"p": ids[0], "r": ids[1], "a": terminal, "b": node},
            )
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert existing() == before
        assert not {"model_nodes", "model_connections"} & set(inspect(engine).get_table_names())
        enums = {item["name"] for item in inspect(engine).get_enums()}
        assert (
            not {"model_node_kind", "model_connection_kind", "model_connection_direction"} & enums
        )
        assert {"model_lifecycle_status", "model_value_origin", "model_verification_state"} <= enums
        _alembic(scratch_url, "upgrade", "head")
        assert existing() == before
        assert _version(engine) == HEAD
        assert_schema(engine)
    finally:
        engine.dispose()
