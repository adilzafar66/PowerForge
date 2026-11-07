"""Real broker recovery and signed OCR evidence on the ordinary extraction queue."""

from datetime import timedelta
from uuid import UUID

import httpx
import pytest

from documents_support import client
from enriched_support import enrich, extraction_detail, start_enriched
from enrichment_support import build_source, detail
from enrichment_support import enrichment_ctx as enrichment_ctx
from powerforge_api.main import app
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from test_enriched_execution import scan_lines, source_run_for
from test_enrichment_celery import copy_source
from test_extraction_celery_integration import live_worker, wait_for

pytestmark = pytest.mark.integration


def test_enhanced_worker_recovery_reuses_real_ocr_and_signs_its_original_text(
    enrichment_ctx, s3_scratch_storage, tmp_path
):
    ctx = enrichment_ctx
    build_source(
        ctx,
        scan_lines(["2-Winding Transformer TX-1", "Secondary Voltage: 600 V"]),
        "recovery-ocr.png",
    )
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding, profile="engineering-test-enriched-v1")
    rid = pending["run"]["id"]
    uid = UUID(next(a["id"] for a in pending["attempts"] if a["stage"] == "EQUIPMENT_RECOGNITION"))
    copy_source(ctx, s3_scratch_storage)

    def running():
        with ctx["factory"]() as session:
            return session.get(ExtractionWorkUnit, uid).status == "RUNNING"

    with live_worker(
        ctx,
        s3_scratch_storage,
        tmp_path / "killed-enhanced",
        beat=True,
        app_module="enrichment_crash_worker",
    ) as worker:
        wait_for(running)
        worker.kill()
        worker.wait(timeout=5)
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        session.get(ExtractionWorkUnit, uid).lease_expires_at = coordinator.now() - timedelta(
            seconds=1
        )
    with live_worker(ctx, s3_scratch_storage, tmp_path / "enhanced-restart", beat=True):
        wait_for(lambda: extraction_detail(ctx, rid)["run"]["status"] == "COMPLETED")
    done = extraction_detail(ctx, rid)
    assert done["execution"]["calls_admitted"] == 3
    assert done["execution"]["provider_calls_started"] == 2
    assert (
        next(a for a in done["attempts"] if a["id"] == str(uid))["error_code"]
        == "WORKER_INTERRUPTED"
    )
    assert detail(ctx, source_run_for(ctx, binding))["confirmed_ocr_invocations"] == 1

    values = client.get(ctx["base"] + f"/extraction/runs/{rid}/candidates").json()["items"]
    value = next(c for c in values if c["attribute_key"] == "secondary_voltage")
    citation = next(
        e["evidence"] for e in value["evidence"] if e["evidence"]["source_snippet"] == "600"
    )
    previous = app.dependency_overrides[get_object_storage]
    app.dependency_overrides[get_object_storage] = lambda: s3_scratch_storage
    try:
        reply = client.get(ctx["base"] + f"/extraction/evidence/{citation['id']}")
        assert reply.status_code == 200, reply.text
        evidence = reply.json()
        text = httpx.get(evidence["artifact_url"], timeout=5)
        assert text.status_code == 200
        assert text.text[evidence["text_start"] : evidence["text_end"]] == "600"
        image = httpx.get(evidence["source_image_url"], timeout=5)
        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    finally:
        app.dependency_overrides[get_object_storage] = previous
