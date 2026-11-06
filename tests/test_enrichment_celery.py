"""Real CPU worker/beat/Redis/MinIO; exact source identities survive worker restart."""

from io import BytesIO
from uuid import UUID

import httpx
import pytest

from documents_support import client
from enrichment_support import build_source, detail, start
from enrichment_support import enrichment_ctx as enrichment_ctx
from powerforge_api.main import app
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.models import ExtractionWorkUnit
from test_enrichment_native import scan_png
from test_extraction_celery_integration import live_worker, wait_for

pytestmark = pytest.mark.integration


def local_environment(ctx):
    return dict(
        ENRICHMENT_ENABLED="true",
        ENRICHMENT_WORKER_ONLY="true",
        ENRICHMENT_OCR_CONFIGURATION=ctx["settings"].enrichment_ocr_configuration,
        EXTRACTION_BACKOFF_SECONDS="0",
    )


def copy_source(ctx, storage):
    for key, obj in ctx["storage"].objects.items():
        storage.put(key, BytesIO(obj.data), len(obj.data), obj.content_type)


def test_real_source_worker_redis_recovery_minio_and_signed_exact_ocr_artifacts(
    enrichment_ctx, s3_scratch_storage, tmp_path
):
    ctx = enrichment_ctx
    build_source(ctx, scan_png(), "live-local.png")
    copy_source(ctx, s3_scratch_storage)
    run = start(ctx)
    rid = run["run"]["id"]
    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "source",
        beat=True,
        queue="source_enrichment",
        extra_env=local_environment(ctx),
    ):
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
    done = detail(ctx, rid)
    assert done["ocr_requests_started"] == 1 and done["run"]["admissions"] == 1
    result_id = done["results"][0]["id"]
    result = client.get(ctx["base"] + f"/source-enrichment/runs/{rid}/results/{result_id}").json()
    artifact = result["manifest"]["representations"][0]["text_artifact"]
    previous = app.dependency_overrides[get_object_storage]
    app.dependency_overrides[get_object_storage] = lambda: s3_scratch_storage
    try:
        reply = client.get(
            ctx["base"] + f"/source-enrichment/runs/{rid}/artifacts/{artifact['id']}"
        )
        assert reply.status_code == 200, reply.text
        download = httpx.get(reply.json()["url"], timeout=5)
        assert download.status_code == 200
        assert b"TX-1" in download.content and b"13.8" in download.content
    finally:
        app.dependency_overrides[get_object_storage] = previous


def test_killed_real_local_worker_recovers_its_persisted_lease_with_successor_attempt(
    enrichment_ctx, s3_scratch_storage, tmp_path
):
    ctx = enrichment_ctx
    copy_source(ctx, s3_scratch_storage)
    pending = start(ctx)
    rid = pending["run"]["id"]
    uid = UUID(pending["attempts"][0]["id"])
    # A real worker is deliberately held at source I/O by an isolated test entrypoint.
    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "killed",
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
    # Move only this abandoned test lease into the past, rather than waiting 30 seconds.
    from datetime import timedelta

    from powerforge_extraction.orchestration import ExtractionCoordinator

    with ctx["factory"].begin() as session:
        unit = session.get(ExtractionWorkUnit, uid)
        unit.lease_expires_at = ExtractionCoordinator(session, ctx["settings"]).now() - timedelta(
            seconds=1
        )
    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "restarted",
        beat=True,
        queue="source_enrichment",
        extra_env=local_environment(ctx),
    ):
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
    done = detail(ctx, rid)
    assert done["run"]["admissions"] == 2 and len(done["attempts"]) == 2
    assert done["attempts"][0]["error_code"] == "WORKER_INTERRUPTED"
