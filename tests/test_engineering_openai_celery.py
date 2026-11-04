"""Production profiles through real worker/beat/Redis/Postgres/S3, with SDK transport mocked."""

import json
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select, text

from documents_support import client
from engineering_execution_support import attempt, processing, start_engineering
from engineering_execution_support import engineering_ctx as engineering_ctx
from engineering_execution_support import execution_ctx as execution_ctx
from extraction_execution_support import detail
from powerforge_api.main import app
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.controls import UnitExecution
from powerforge_extraction.models import ExtractionAICall, ExtractionWorkUnit
from powerforge_extraction.production_profiles import (
    ENGINEERING_OPENAI_PROFILE,
    ENGINEERING_OPENAI_TEXT_PROFILE,
)
from test_extraction_celery_integration import copy_source, live_worker, wait_for

pytestmark = pytest.mark.integration


def sdk_env(path, scenario="success"):
    return {
        "EXTRACTION_EXTERNAL_ENABLED": "true",
        "OPENAI_API_KEY": "fixture-credential",
        "M5_SDK_AUDIT": str(path),
        "M5_SDK_SCENARIO": scenario,
        "OPENAI_LOG": "warn",
    }


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize(
    "mode,scenario",
    [
        ("hybrid", "success"),
        ("text", "transient-attribute"),
        ("image", "success"),
        ("text", "invalid-attribute"),
    ],
)
def test_production_sdk_worker_beat_publish_grounded_candidates_and_preserve_retries(
    engineering_ctx,
    s3_scratch_storage,
    tmp_path,
    mode,
    scenario,
):
    ctx = engineering_ctx
    ctx["settings"].extraction_external_enabled = True
    if mode == "image":
        processing(
            ctx, native=None, image_label="2-Winding Transformer TX-1\nSecondary Voltage: 600 V"
        )
    copy_source(ctx, s3_scratch_storage)
    key = ENGINEERING_OPENAI_TEXT_PROFILE if mode == "text" else ENGINEERING_OPENAI_PROFILE
    with ctx["factory"]() as session:
        before = session.scalar(
            text("SELECT updated_at FROM project_revisions WHERE id=:id"),
            {"id": ctx["revision_id"]},
        )
    rid = start_engineering(ctx, profile_key=key)["run"]["id"]
    audit = tmp_path / "sdk.jsonl"
    # API notifications are deliberately not sent to Redis. Beat must find the plan.
    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "worker",
        beat=True,
        app_module="engineering_openai_worker_fixture",
        extra_env=sdk_env(audit, scenario),
    ):
        if scenario == "invalid-attribute":
            wait_for(lambda: detail(ctx, rid)["run"]["status"] == "PARTIALLY_COMPLETED")
            assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 1
            response = client.post(ctx["base"] + f"/runs/{rid}/retry")
            assert response.status_code == 202, response.text
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
    result = detail(ctx, rid)
    observed = records(audit)
    expected_calls = 2 if scenario == "success" else 3
    assert result["execution"]["execution_kind"] == "ENGINEERING_EXTRACTION"
    assert (
        result["execution"]["calls_admitted"]
        == result["execution"]["reported_calls"]
        == expected_calls
    )
    assert (
        len(observed) == expected_calls
        and sum(r["stage"] == "EQUIPMENT_RECOGNITION" for r in observed) == 1
    )
    attrs = [r for r in observed if r["stage"] == "ATTRIBUTE_EXTRACTION"]
    if len(attrs) > 1:
        assert attrs[0]["instruction_hash"] == attrs[1]["instruction_hash"]
        assert (
            attrs[0]["input_hash"] == attrs[1]["input_hash"]
            and attrs[0]["schema_hash"] == attrs[1]["schema_hash"]
        )
    assert all(r["reasoning"] == {"effort": "none"} and r["store"] is False for r in observed)
    assert all(r["image_detail"] == (None if mode == "text" else "high") for r in observed)
    candidates = client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["items"]
    assert len(candidates) == 2 and not any(c["diagnostics"].get("synthetic") for c in candidates)
    value = next(c for c in candidates if c["attribute_key"] == "secondary_voltage")
    assert value["numeric_value"] == "0.6"
    assert value["source_group"]["tag_text"] == "TX-1"
    assert value["diagnostics"]["text_verified"] == (mode != "image")
    assert value["evidence"][0]["evidence"]["grounding_precision"] == (
        "VISUAL_PAGE" if mode == "image" else "TEXT_OFFSETS"
    )
    previous = app.dependency_overrides[get_object_storage]
    app.dependency_overrides[get_object_storage] = lambda: s3_scratch_storage
    try:
        evidence = client.get(
            ctx["base"] + f"/evidence/{value['evidence'][0]['evidence']['id']}"
        ).json()
        downloaded = httpx.get(evidence["artifact_url"], timeout=5)
        assert downloaded.status_code == 200
        assert (evidence["text_start"] is None) == (mode == "image")
    finally:
        app.dependency_overrides[get_object_storage] = previous
    with ctx["factory"]() as session:
        assert (
            session.scalar(
                text("SELECT updated_at FROM project_revisions WHERE id=:id"),
                {"id": ctx["revision_id"]},
            )
            == before
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM equipment WHERE revision_id=:id"),
                {"id": ctx["revision_id"]},
            )
            == 0
        )
        calls = list(
            session.scalars(select(ExtractionAICall).where(ExtractionAICall.run_id == UUID(rid)))
        )
        for call in calls:
            record = next(r for r in observed if r["request_id"] == str(call.work_unit_id))
            assert call.prompt_hash == record["instruction_hash"]
    logs = (tmp_path / "worker/worker.log").read_text() + (tmp_path / "worker/beat.log").read_text()
    assert "PRIVATE PROVIDER CONTENT" not in logs and "fixture-credential" not in logs
    assert "Secondary Voltage: 600 V" not in logs


def test_killed_production_worker_reuses_committed_recognition_after_restart(
    engineering_ctx,
    s3_scratch_storage,
    tmp_path,
):
    ctx = engineering_ctx
    ctx["settings"].extraction_external_enabled = True
    ctx["settings"].extraction_lease_seconds = 3
    copy_source(ctx, s3_scratch_storage)
    rid = start_engineering(ctx, profile_key=ENGINEERING_OPENAI_PROFILE)["run"]["id"]
    attr = attempt(ctx, rid, "ATTRIBUTE_EXTRACTION")
    audit = tmp_path / "sdk.jsonl"
    env = sdk_env(audit, "slow-attribute")

    def started():
        with ctx["factory"]() as session:
            return (
                session.get(UnitExecution, attr).provider_started_at is not None
                and audit.exists()
                and len(records(audit)) >= 2
            )

    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "crashed",
        beat=True,
        app_module="engineering_openai_worker_fixture",
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
        app_module="engineering_openai_worker_fixture",
        extra_env=env,
    ):
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
    result = detail(ctx, rid)
    assert len(result["attempts"]) == 3
    assert result["execution"]["unreported_provider_calls"] == 1
    assert result["execution"]["calls_admitted"] == len(records(audit)) == 3
    assert sum(r["stage"] == "EQUIPMENT_RECOGNITION" for r in records(audit)) == 1
    with ctx["factory"]() as session:
        assert session.get(ExtractionWorkUnit, attr).error_code == "WORKER_INTERRUPTED"
