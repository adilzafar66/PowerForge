"""Catalog checks for the clean 6R-B Alembic installation."""

import pytest
from sqlalchemy import inspect, text

from powerforge_api.db import get_engine

pytestmark = pytest.mark.integration


def test_phase6r_b_schema_exposes_only_unified_extraction(require_db):
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == [
            "6r_0013c_admission"
        ]
        catalog = inspect(conn)
        assert {
            "extraction_runs",
            "extraction_work_units",
            "extraction_ai_calls",
            "extraction_run_execution",
            "extraction_unit_execution",
            "extraction_stage_results",
            "run_source_enrichment_bindings",
            "source_enrichment_page_results",
            "source_enrichment_artifacts",
            "source_preparation_receipts",
            "source_spatial_results",
            "extraction_operations",
            "extraction_operation_items",
            "extraction_operation_requests",
            "extraction_operation_previews",
        } <= set(catalog.get_table_names())
        assert not {
            "extracted_tables",
            "extraction_candidates",
            "extraction_evidence",
            "candidate_evidence",
            "extraction_source_groups",
        } & set(catalog.get_table_names())
        assert {
            row["name"] for row in catalog.get_enums() if row["name"].startswith("extraction_")
        } == {"extraction_run_status", "extraction_work_unit_status", "extraction_ai_call_outcome"}
        assert not {"engineering_run_id", "tables_run_id"} & {
            column["name"] for column in catalog.get_columns("extraction_operation_items")
        }
        checks = {
            row["name"]: row["sqltext"] for row in catalog.get_check_constraints("extraction_runs")
        }
        purpose = checks["ck_extraction_purpose_metadata"]
        assert all(
            value in purpose
            for value in ("phase-6r-profile-v1", "EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION")
        )
        assert "TABLE_RECONSTRUCTION" not in purpose and "TABLE_INTERPRETATION" not in purpose
        keys = {
            tuple(row["constrained_columns"]): row["referred_table"]
            for row in catalog.get_foreign_keys("extraction_stage_results")
        }
        assert keys["run_id", "document_page_id"] == "run_source_enrichment_bindings"
        assert (
            keys[
                "upstream_work_unit_id",
                "run_id",
                "document_page_id",
                "page_context_hash",
                "upstream_hash",
            ]
            == "extraction_stage_results"
        )
        for table, names in {
            "extraction_work_units": {
                "uq_extraction_work_units_active",
                "uq_extraction_work_units_success",
            },
            "extraction_operation_items": {"uq_extraction_operation_items_extraction_owner"},
            "extraction_operations": {"uq_extraction_operations_active_intent"},
        }.items():
            assert names <= {row["name"] for row in catalog.get_indexes(table) if row["unique"]}
        triggers = {
            (table, name): deferred
            for table, name, deferred in conn.execute(
                text(
                    "SELECT tgrelid::regclass::text, tgname, tginitdeferred "
                    "FROM pg_trigger WHERE NOT tgisinternal AND tgenabled = 'O'"
                )
            )
        }
        assert ("run_source_enrichment_bindings", "extraction_binding_guard") in triggers
        assert ("extraction_stage_results", "extraction_stage_guard") in triggers
        assert ("extraction_stage_results", "extraction_fence_guard") in triggers
        assert triggers["extraction_stage_results", "extraction_stage_terminal_guard"]
