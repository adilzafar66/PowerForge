"""Independent publisher and SQL fences reject fabricated v2 evidence atomically."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from enriched_support import enrich, execute, extraction_detail, start_enriched
from enrichment_support import build_source
from enrichment_support import enrichment_ctx as enrichment_ctx
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.enriched_publication import prepare_publication
from powerforge_extraction.enriched_runtime import request_for
from powerforge_extraction.enriched_tables import reconstruct
from powerforge_extraction.models import (
    Evidence,
    ExtractedTable,
    ExtractionAICall,
    ExtractionRun,
    ExtractionWorkUnit,
)
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.persistence import ExtractionPersistence
from test_enrichment_celery import copy_source

pytestmark = pytest.mark.integration


def claimed(ctx):
    build_source(
        ctx, Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(), "guard.pdf"
    )
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding)
    uid = UUID(next(a["id"] for a in pending["attempts"] if a["stage"] == "TABLE_RECONSTRUCTION"))
    with ctx["factory"].begin() as session:
        claim = ExtractionCoordinator(session, ctx["settings"]).claim(uid)
    request, source, _ = request_for(claim, ctx["storage"], ctx["factory"])
    output, _ = reconstruct(FakeEnrichedProvider().execute(request).result, source)
    return claim, output


def test_publisher_rederives_offsets_geometry_and_cell_membership_before_inserting(enrichment_ctx):
    ctx = enrichment_ctx
    claim, original = claimed(ctx)
    first = original.evidence[0]
    region = first.location.region
    changes = [
        first.model_copy(update={"text_end": first.text_end + 1}),
        first.model_copy(update={"source_snippet": "invented"}),
        first.model_copy(update={"cell_id": "other-cell"}),
        first.model_copy(
            update={
                "location": first.location.model_copy(
                    update={"region": region.model_copy(update={"x": region.x + region.width / 10})}
                )
            }
        ),
    ]
    for changed in changes:
        output = original.model_copy(update={"evidence": [changed, *original.evidence[1:]]})
        with pytest.raises(ValueError):
            prepare_publication(ctx["factory"], ctx["storage"], claim.unit_id, output)
    verification = prepare_publication(ctx["factory"], ctx["storage"], claim.unit_id, original)
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        coordinator._authorized(claim.unit_id, claim.token)
        persistence = ExtractionPersistence(session)
        with pytest.raises(ValueError, match="requires independent source verification"):
            persistence.publish(claim.unit_id, original)
        with pytest.raises(ValueError, match="differs from its verified"):
            persistence.publish(claim.unit_id, output, verification=verification)
        assert_no_publication(session, claim.run_id)
        assert session.get(ExtractionWorkUnit, claim.unit_id).status == "RUNNING"
        persistence.publish(claim.unit_id, original, verification=verification)
        coordinator.aggregate(session.get(ExtractionRun, claim.run_id))


def assert_no_publication(session, run_id):
    for model in (Evidence, ExtractedTable, ExtractionAICall):
        assert (
            session.scalar(select(func.count()).select_from(model).where(model.run_id == run_id))
            == 0
        )


@pytest.mark.parametrize("operation", ["cancel", "recover"])
def test_slow_publication_read_allows_cancellation_and_recovery(
    enrichment_ctx, s3_scratch_storage, monkeypatch, operation
):
    ctx = enrichment_ctx
    build_source(
        ctx, Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(), "slow.pdf"
    )
    pending = start_enriched(ctx, enrich(ctx))
    rid = UUID(pending["run"]["id"])
    uid = UUID(next(a["id"] for a in pending["attempts"] if a["stage"] == "TABLE_RECONSTRUCTION"))
    copy_source(ctx, s3_scratch_storage)
    worker_ctx = {**ctx, "storage": s3_scratch_storage}
    model_returned, read_started, release_read = Event(), Event(), Event()
    get = s3_scratch_storage.get

    class Provider(FakeEnrichedProvider):
        def execute(self, request):
            response = super().execute(request)
            model_returned.set()
            return response

    def delayed_get(key):
        if model_returned.is_set() and not read_started.is_set():
            read_started.set()
            assert release_read.wait(timeout=15), "Timed out waiting to release publication read"
        return get(key)

    monkeypatch.setattr(s3_scratch_storage, "get", delayed_get)
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(execute, worker_ctx, uid, Provider())
        try:
            assert read_started.wait(timeout=10)
            with ctx["factory"].begin() as session:
                session.execute(text("SET LOCAL lock_timeout = '2s'"))
                coordinator = ExtractionCoordinator(session, ctx["settings"])
                if operation == "cancel":
                    assert coordinator.cancel(rid).status == "CANCELLED"
                else:
                    coordinator._run(rid)
                    session.get(ExtractionWorkUnit, uid).lease_expires_at = (
                        coordinator.now() - timedelta(seconds=1)
                    )
                    session.flush()
                    assert coordinator.reconcile() >= 1
            assert not worker.done()
        finally:
            release_read.set()
        assert worker.result(timeout=10) is False

    with ctx["factory"]() as session:
        assert_no_publication(session, rid)
        attempt = session.get(ExtractionWorkUnit, uid)
        if operation == "cancel":
            assert attempt.status == "CANCELLED"
            return
        assert attempt.status == "FAILED" and attempt.error_code == "WORKER_INTERRUPTED"
    retry = next(
        a for a in extraction_detail(ctx, rid)["attempts"] if a["retry_of_work_unit_id"] == str(uid)
    )
    assert execute(worker_ctx, retry["id"])
    interpretation = next(
        a for a in extraction_detail(ctx, rid)["attempts"] if a["stage"] == "TABLE_INTERPRETATION"
    )
    assert execute(worker_ctx, interpretation["id"])
    assert extraction_detail(ctx, rid)["run"]["status"] == "COMPLETED"


def test_direct_database_insert_rejects_unowned_lease_and_foreign_source_support(enrichment_ctx):
    ctx = enrichment_ctx
    claim, output = claimed(ctx)
    first = next(e for e in output.evidence if e.table_id and e.text_start is not None)

    def row(locator=None):
        data = first.model_dump(exclude={"location", "table_id", "cell_id"})
        loc = first.location
        data["source_kind"] = "NATIVE_TEXT"
        selected = locator or loc.model_dump(mode="json")
        selected["structure_basis"] = "UNRESOLVED"
        return Evidence(
            **data,
            run_id=claim.run_id,
            work_unit_id=claim.unit_id,
            document_id=ctx["document"],
            processing_run_id=ctx["processing"],
            document_page_id=loc.document_page_id,
            page_artifact_id=None,
            enrichment_artifact_id=loc.enrichment_artifact_id,
            geometry_artifact_id=loc.geometry_artifact_id,
            source_locator=selected,
            **loc.region.model_dump(),
        )

    with pytest.raises(DBAPIError, match="lease"):
        with ctx["factory"].begin() as session:
            session.add(row())
            session.flush()
    bad = first.location.model_dump(mode="json")
    bad["support"][0]["ref"] = "foreign-token"
    with pytest.raises(DBAPIError, match="bound text and geometry"):
        with ctx["factory"].begin() as session:
            ExtractionCoordinator(session, ctx["settings"])._authorized(claim.unit_id, claim.token)
            session.add(row(bad))
            session.flush()
