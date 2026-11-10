"""Verify the Phase 6F migration and retention of operation consent."""

import pytest
from sqlalchemy import create_engine, inspect, text

from powerforge_extraction.operation_models import (
    ExtractionOperation,
    OperationItem,
    OperationRequest,
)
from test_migration_0006 import _alembic, _seed_phase3, _version
from test_migration_0006 import scratch_url as scratch_url

pytestmark = pytest.mark.integration
PREVIOUS = "0016_enriched_extraction"
REVISION = "0017_extraction_operations"


def test_operation_schema_and_downgrade_protects_consent(scratch_url):
    _alembic(scratch_url, "upgrade", PREVIOUS)
    engine = create_engine(scratch_url)
    try:
        source = _seed_phase3(engine)
        _alembic(scratch_url, "upgrade", REVISION)
        assert _version(engine) == REVISION
        tables = (
            ExtractionOperation.__table__,
            OperationItem.__table__,
            OperationRequest.__table__,
        )
        for table in tables:
            actual = inspect(engine).get_columns(table.name)
            assert {column["name"]: column["nullable"] for column in actual} == {
                column.name: column.nullable for column in table.columns
            }

        _alembic(scratch_url, "downgrade", PREVIOUS)
        assert _version(engine) == PREVIOUS
        assert {table.name for table in tables}.isdisjoint(inspect(engine).get_table_names())
        _alembic(scratch_url, "upgrade", REVISION)
        with engine.begin() as connection:
            operation_id = connection.execute(
                text("""
                    INSERT INTO extraction_operations(project_id, revision_id, intent_hash, policy)
                    SELECT project_id, revision_id, repeat('a', 64),
                           '{"consent_version":"external-openai-v1"}'::jsonb
                    FROM revision_documents WHERE id = :association_id RETURNING id
                """),
                source,
            ).scalar_one()

        with pytest.raises(
            AssertionError, match="Cannot downgrade with retained extraction operation"
        ):
            _alembic(scratch_url, "downgrade", PREVIOUS)
        assert _version(engine) == REVISION
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT policy->>'consent_version' FROM extraction_operations "
                        "WHERE id = :id"
                    ),
                    {"id": operation_id},
                ).scalar_one()
                == "external-openai-v1"
            )
    finally:
        engine.dispose()
