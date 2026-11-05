"""Real worker/beat/Redis/Postgres/MinIO with the production table SDK transport mocked."""

import json

import httpx
import pytest
from sqlalchemy import text

from documents_support import client
from engineering_execution_support import processing
from extraction_execution_support import detail
from powerforge_api.main import app
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.controls import UnitExecution
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.table_profiles import TABLE_OPENAI_PROFILE, TABLE_OPENAI_TEXT_PROFILE
from table_execution_support import attempt, start_tables
from table_execution_support import execution_ctx as execution_ctx
from table_execution_support import table_ctx as table_ctx
from table_grounding_support import schedule
from test_extraction_celery_integration import copy_source, live_worker, wait_for

pytestmark = pytest.mark.integration


def sdk_env(path, scenario="success"):
    return {
        "EXTRACTION_EXTERNAL_ENABLED": "true",
        "OPENAI_API_KEY": "fixture-credential",
        "TABLE_SDK_AUDIT": str(path),
        "TABLE_SDK_SCENARIO": scenario,
        "OPENAI_LOG": "warn",
    }


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize(
    "mode,scenario",
    [
        ("hybrid", "success"),
        ("image", "success"),
        ("text", "transient-interpretation"),
        ("text", "invalid-interpretation"),
        ("text", "empty"),
        ("text", "multiple"),
    ],
)
def test_table_production_worker_commits_layouts_then_claims_and_reuses_prerequisites(
    table_ctx, s3_scratch_storage, tmp_path, mode, scenario
):
    ctx = table_ctx
    ctx["settings"].extraction_external_enabled = True
    if mode == "image":
        processing(
            ctx,
            native=None,
            image_label=schedule()[1],
        )
    if scenario == "multiple":
        processing(
            ctx,
            native=schedule()[1]
            + "\n\n"
            + schedule(title="2-Winding Transformer Auxiliary Schedule")[1],
        )
    copy_source(ctx, s3_scratch_storage)
    key = TABLE_OPENAI_TEXT_PROFILE if mode == "text" else TABLE_OPENAI_PROFILE
    rid = start_tables(ctx, profile_key=key)["run"]["id"]
    audit = tmp_path / "table-sdk.jsonl"
    with ctx["factory"]() as session:
        before = session.scalar(
            text("SELECT updated_at FROM project_revisions WHERE id=:id"),
            {"id": ctx["revision_id"]},
        )
    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "worker",
        beat=True,
        app_module="table_openai_worker_fixture",
        extra_env=sdk_env(audit, scenario),
    ):
        if scenario == "invalid-interpretation":
            wait_for(lambda: detail(ctx, rid)["run"]["status"] == "PARTIALLY_COMPLETED")
            assert client.get(ctx["base"] + f"/runs/{rid}/tables").json()["total"] == 1
            assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 202
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
    observed = records(audit)
    result = detail(ctx, rid)
    expected_calls = 1 if scenario == "empty" else 2 if scenario in {"success", "multiple"} else 3
    expected_admissions = 2 if scenario in {"empty", "success", "multiple"} else 3
    assert len(observed) == result["execution"]["reported_calls"] == expected_calls
    assert result["execution"]["calls_admitted"] == expected_admissions
    assert sum(r["stage"] == "TABLE_RECONSTRUCTION" for r in observed) == 1
    assert all(r["store"] is False and r["reasoning"] == {"effort": "none"} for r in observed)
    assert all(r["image_detail"] == (None if mode == "text" else "high") for r in observed)
    interpretations = [r for r in observed if r["stage"] == "TABLE_INTERPRETATION"]
    if len(interpretations) > 1:
        assert interpretations[0]["input_hash"] == interpretations[1]["input_hash"]
        assert interpretations[0]["instruction_hash"] == interpretations[1]["instruction_hash"]
    tables = client.get(ctx["base"] + f"/runs/{rid}/tables").json()["items"]
    candidates = client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["items"]
    assert len(tables) == (0 if scenario == "empty" else 2 if scenario == "multiple" else 1)
    assert len(candidates) == (0 if scenario == "empty" else 2)
    if scenario != "empty":
        value = next(c for c in candidates if c["kind"] == "ATTRIBUTE_VALUE")
        assert value["numeric_value"] == "0.6" and not value["diagnostics"].get("synthetic")
        primary = next(c["evidence"] for c in value["evidence"] if c["role"] == "PRIMARY")
        assert primary["table_id"] in {t["id"] for t in tables} and primary["cell_id"] == "c1_3"
        previous = app.dependency_overrides[get_object_storage]
        app.dependency_overrides[get_object_storage] = lambda: s3_scratch_storage
        try:
            evidence = client.get(ctx["base"] + f"/evidence/{primary['id']}").json()
            assert evidence["grounding_precision"] == (
                "VISUAL_PAGE" if mode == "image" else "TEXT_OFFSETS"
            )
            assert httpx.get(evidence["artifact_url"], timeout=5).status_code == 200
        finally:
            app.dependency_overrides[get_object_storage] = previous
    else:
        assert (
            result["execution"]["unreported_admissions"] == 1
            and result["execution"]["input_tokens"] is None
        )
    with ctx["factory"]() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM equipment WHERE revision_id=:id"),
                {"id": ctx["revision_id"]},
            )
            == 0
        )
        assert (
            session.scalar(
                text("SELECT updated_at FROM project_revisions WHERE id=:id"),
                {"id": ctx["revision_id"]},
            )
            == before
        )
    logs = (tmp_path / "worker/worker.log").read_text() + (tmp_path / "worker/beat.log").read_text()
    assert "fixture-credential" not in logs and "PRIVATE PROVIDER CONTENT" not in logs


def test_killed_table_worker_recovers_without_repeating_committed_reconstruction(
    table_ctx, s3_scratch_storage, tmp_path
):
    ctx = table_ctx
    ctx["settings"].extraction_external_enabled = True
    ctx["settings"].extraction_lease_seconds = 3
    copy_source(ctx, s3_scratch_storage)
    rid = start_tables(ctx, profile_key=TABLE_OPENAI_PROFILE)["run"]["id"]
    interpretation = attempt(ctx, rid, "TABLE_INTERPRETATION")
    audit = tmp_path / "table-sdk.jsonl"
    env = sdk_env(audit, "slow-interpretation")

    def started():
        with ctx["factory"]() as session:
            return (
                session.get(UnitExecution, interpretation).provider_started_at is not None
                and audit.exists()
                and len(records(audit)) >= 2
            )

    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "crashed",
        beat=True,
        app_module="table_openai_worker_fixture",
        extra_env=env,
    ) as worker:
        wait_for(started)
        worker.kill()
        worker.wait(timeout=5)
    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "restarted",
        beat=True,
        app_module="table_openai_worker_fixture",
        extra_env=env,
    ):
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
    result = detail(ctx, rid)
    assert len(result["attempts"]) == 3
    assert result["execution"]["calls_admitted"] == len(records(audit)) == 3
    assert result["execution"]["unreported_provider_calls"] == 1
    assert sum(r["stage"] == "TABLE_RECONSTRUCTION" for r in records(audit)) == 1
    with ctx["factory"]() as session:
        assert session.get(ExtractionWorkUnit, interpretation).error_code == "WORKER_INTERRUPTED"


def test_cancelled_table_worker_cannot_publish_late_sdk_results(
    table_ctx, s3_scratch_storage, tmp_path
):
    ctx = table_ctx
    ctx["settings"].extraction_external_enabled = True
    copy_source(ctx, s3_scratch_storage)
    rid = start_tables(ctx, profile_key=TABLE_OPENAI_PROFILE)["run"]["id"]
    interpretation = attempt(ctx, rid, "TABLE_INTERPRETATION")
    audit = tmp_path / "table-sdk.jsonl"

    def started():
        with ctx["factory"]() as session:
            return (
                session.get(UnitExecution, interpretation).provider_started_at is not None
                and audit.exists()
                and len(records(audit)) >= 2
            )

    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "cancelled",
        beat=True,
        app_module="table_openai_worker_fixture",
        extra_env=sdk_env(audit, "slow-interpretation"),
    ):
        wait_for(started)
        assert client.post(ctx["base"] + f"/runs/{rid}/cancel").status_code == 200
    result = detail(ctx, rid)
    assert result["run"]["status"] == "CANCELLED"
    assert client.get(ctx["base"] + f"/runs/{rid}/tables").json()["total"] == 1
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 0
