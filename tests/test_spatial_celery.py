"""Actual local queue recovery derives layout from its original successful preparation."""

from datetime import timedelta
from uuid import UUID

import pytest

from enrichment_support import build_source, detail, start
from enrichment_support import enrichment_ctx as enrichment_ctx
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from test_enrichment_celery import copy_source, local_environment
from test_enrichment_native import scan_png
from test_extraction_celery_integration import live_worker, wait_for
from test_spatial_execution import run_unit, stage

pytestmark = pytest.mark.integration


def test_killed_layout_worker_recovers_without_repeating_real_ocr(
    enrichment_ctx, s3_scratch_storage, tmp_path
):
    ctx = enrichment_ctx
    build_source(ctx, scan_png(), "layout-recovery.png")
    pending = start(ctx, profile_key="source-layout-v1")
    rid = pending["run"]["id"]
    run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    prepared = detail(ctx, rid)["results"][0]["id"]
    copy_source(ctx, s3_scratch_storage)
    uid = UUID(stage(pending, "SPATIAL_LAYOUT"))
    # This existing test-only entrypoint pauses at storage.get after the real DB claim.
    # Preparation is already committed, so only the layout stage can be dispatched.
    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "killed-layout",
        beat=True,
        queue="source_enrichment",
        app_module="enrichment_crash_worker",
        extra_env=local_environment(ctx),
    ) as worker:

        def running():
            with ctx["factory"]() as session:
                return session.get(ExtractionWorkUnit, uid).status == "RUNNING"

        wait_for(running)
        worker.kill()
        worker.wait(timeout=5)
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        session.get(ExtractionWorkUnit, uid).lease_expires_at = coordinator.now() - timedelta(
            seconds=1
        )
    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "restarted-layout",
        beat=True,
        queue="source_enrichment",
        extra_env=local_environment(ctx),
    ):
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
    done = detail(ctx, rid)
    assert done["run"]["admissions"] == 3 and len(done["attempts"]) == 3
    assert done["confirmed_ocr_invocations"] == 1 and done["ocr_requests_started"] == 1
    assert done["results"][0]["id"] == prepared
    assert done["spatial_results"][0]["prepared_result_id"] == prepared
    assert next(a for a in done["attempts"] if a["id"] == str(uid))["error_code"] == (
        "WORKER_INTERRUPTED"
    )
