"""Migration 0008 revision metadata against scratch databases."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

HEAD = "0008_revision_model_metadata"
PREVIOUS = "0007_engineering_model_core"
CONSTRAINTS = {
    "ck_project_revisions_system_frequency_positive",
    "ck_project_revisions_system_phase_count",
}


def _checks(engine) -> set[str]:
    return {item["name"] for item in inspect(engine).get_check_constraints("project_revisions")}


@pytest.mark.integration
def test_fresh_upgrade_has_nullable_metadata_and_constraints(scratch_url) -> None:
    _alembic(scratch_url, "upgrade", "head")
    engine = create_engine(scratch_url)
    try:
        assert _version(engine) == HEAD
        columns = {item["name"]: item for item in inspect(engine).get_columns("project_revisions")}
        assert columns["system_frequency"]["nullable"]
        assert columns["system_phase_count"]["nullable"]
        assert CONSTRAINTS <= _checks(engine)
    finally:
        engine.dispose()


@pytest.mark.integration
def test_upgrade_preserves_model_rows_enforces_values_and_round_trips(scratch_url) -> None:
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        seeded = _seed_phase3(engine)
        with engine.connect() as connection:
            ownership = connection.execute(
                text("SELECT project_id, revision_id FROM revision_documents WHERE id=:id"),
                {"id": seeded["association_id"]},
            ).one()
        with engine.begin() as connection:
            lineage = connection.execute(
                text("INSERT INTO equipment_lineages(project_id) VALUES (:p) RETURNING id"),
                {"p": ownership.project_id},
            ).scalar_one()
            equipment = connection.execute(
                text(
                    "INSERT INTO equipment(project_id,revision_id,lineage_id,equipment_type) "
                    "VALUES (:p,:r,:l,'BUS') RETURNING id"
                ),
                {"p": ownership.project_id, "r": ownership.revision_id, "l": lineage},
            ).scalar_one()
            attribute = connection.execute(
                text(
                    "INSERT INTO equipment_attributes"
                    "(project_id,revision_id,equipment_id,attribute_key,value_type,unit) "
                    "VALUES (:p,:r,:e,'nominal_voltage','NUMBER','kV') RETURNING id"
                ),
                {"p": ownership.project_id, "r": ownership.revision_id, "e": equipment},
            ).scalar_one()

        _alembic(scratch_url, "upgrade", "head")
        assert _version(engine) == HEAD
        with engine.connect() as connection:
            metadata = connection.execute(
                text(
                    "SELECT system_frequency, system_phase_count FROM project_revisions "
                    "WHERE id=:id"
                ),
                {"id": ownership.revision_id},
            ).one()
            assert metadata == (None, None)
            assert (
                connection.execute(
                    text("SELECT count(*) FROM equipment WHERE id=:id"), {"id": equipment}
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM equipment_attributes WHERE id=:id"),
                    {"id": attribute},
                ).scalar_one()
                == 1
            )

        for frequency in [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")]:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(
                    text("UPDATE project_revisions SET system_frequency=:value WHERE id=:id"),
                    {"value": frequency, "id": ownership.revision_id},
                )
        for phase_count in [0, 2, 4]:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(
                    text("UPDATE project_revisions SET system_phase_count=:value WHERE id=:id"),
                    {"value": phase_count, "id": ownership.revision_id},
                )
        with engine.begin() as connection:
            for frequency, phase_count in [(Decimal("50"), 1), (Decimal("60.125"), 3)]:
                connection.execute(
                    text(
                        "UPDATE project_revisions SET system_frequency=:f, "
                        "system_phase_count=:p WHERE id=:id"
                    ),
                    {"f": frequency, "p": phase_count, "id": ownership.revision_id},
                )

        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert _version(engine) == PREVIOUS
        columns = {item["name"] for item in inspect(engine).get_columns("project_revisions")}
        assert not {"system_frequency", "system_phase_count"} & columns
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM equipment WHERE id=:id"), {"id": equipment}
                ).scalar_one()
                == 1
            )
        _alembic(scratch_url, "upgrade", "head")
        assert _version(engine) == HEAD
    finally:
        engine.dispose()
