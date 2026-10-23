"""Fresh and existing-data upgrades plus downgrade/re-upgrade in isolated databases."""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import ENUM

from powerforge_persistence.engineering import Equipment, EquipmentAttribute, EquipmentLineage
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url
from test_phase4_constraints import make_classification_run

pytestmark = pytest.mark.integration
HEAD = "0007_engineering_model_core"
PREVIOUS = "0006_document_classification"
TABLES = {"equipment_lineages", "equipment", "equipment_attributes"}
ENUMS = {
    "model_lifecycle_status",
    "model_information_state",
    "model_verification_state",
    "model_value_origin",
    "model_attribute_value_type",
}


def assert_schema(engine) -> None:
    inspector = inspect(engine)
    assert TABLES <= set(inspector.get_table_names())
    assert not {"model_nodes", "model_connections", "engineering_models"} & set(
        inspector.get_table_names()
    )
    for model in [EquipmentLineage, Equipment, EquipmentAttribute]:
        table = model.__table__
        columns = {c["name"]: c for c in inspector.get_columns(table.name)}
        assert set(columns) == set(table.columns.keys())
        for column in table.columns:
            actual = columns[column.name]
            assert actual["nullable"] == column.nullable
            assert actual["type"]._type_affinity == column.type._type_affinity
            if isinstance(column.type, ENUM):
                assert actual["type"].enums == column.type.enums
        actual_constraints = {
            item["name"]
            for method in [
                inspector.get_unique_constraints,
                inspector.get_foreign_keys,
                inspector.get_check_constraints,
            ]
            for item in method(table.name)
        }
        assert {c.name for c in table.constraints if c.name} == actual_constraints
        indexes = {i["name"]: i for i in inspector.get_indexes(table.name)}
        for index in table.indexes:
            assert indexes[index.name]["column_names"] == [c.name for c in index.columns]
            assert bool(indexes[index.name]["unique"]) == bool(index.unique)
        # Composite ownership must include all columns, not just similarly named constraints.
        actual_fks = {fk["name"]: fk for fk in inspector.get_foreign_keys(table.name)}
        for fk in table.foreign_key_constraints:
            assert actual_fks[fk.name]["constrained_columns"] == [
                e.parent.name for e in fk.elements
            ]
            assert actual_fks[fk.name]["referred_columns"] == [e.column.name for e in fk.elements]
    with engine.connect() as conn:
        assert all(
            conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
            for table in TABLES
        )


def test_fresh_upgrade_to_head_has_exact_orm_schema(scratch_url) -> None:
    _alembic(scratch_url, "upgrade", HEAD)
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        assert_schema(engine)
    finally:
        engine.dispose()


def test_existing_documents_and_classification_survive_upgrade_downgrade_reupgrade(
    scratch_url,
) -> None:
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        seeded = _seed_phase3(engine)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT project_id, revision_id FROM revision_documents WHERE id=:id"),
                {"id": seeded["association_id"]},
            ).one()
            seeded.update(project_id=row.project_id, revision_id=row.revision_id)
        with engine.begin() as conn:
            make_classification_run(conn, seeded["document_id"], seeded["run_id"])
        legacy_tables = [
            "projects",
            "project_revisions",
            "documents",
            "revision_documents",
            "document_pages",
            "document_processing_runs",
            "document_classification_runs",
        ]

        def legacy():
            with engine.connect() as conn:
                return {
                    table: conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
                    .scalars()
                    .all()
                    for table in legacy_tables
                }

        before = legacy()
        _alembic(scratch_url, "upgrade", HEAD)
        assert _version(engine) == HEAD
        assert_schema(engine)
        assert legacy() == before
        # Downgrade also succeeds when the new tables contain a coherent model snapshot.
        with engine.begin() as conn:
            lineage = conn.execute(
                text("INSERT INTO equipment_lineages(project_id) VALUES (:p) RETURNING id"),
                {"p": seeded["project_id"]},
            ).scalar_one()
            equipment = conn.execute(
                text(
                    "INSERT INTO "
                    "equipment(project_id,revision_id,lineage_id,equipment_type) VALUES "
                    "(:p,:r,:l,'BUS') RETURNING id"
                ),
                {"p": seeded["project_id"], "r": seeded["revision_id"], "l": lineage},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO "
                    "equipment_attributes(project_id,revision_id,equipment_id,attribute_key,value_type,unit)"
                    " VALUES (:p,:r,:e,'nominal_voltage','NUMBER','kV')"
                ),
                {"p": seeded["project_id"], "r": seeded["revision_id"], "e": equipment},
            )
        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert _version(engine) == PREVIOUS
        assert not TABLES & set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT typname FROM pg_type WHERE typname = ANY(:names)"),
                    {"names": list(ENUMS)},
                ).all()
                == []
            )
        assert legacy() == before
        _alembic(scratch_url, "upgrade", HEAD)
        assert _version(engine) == HEAD
        assert_schema(engine)
        assert legacy() == before
    finally:
        engine.dispose()
