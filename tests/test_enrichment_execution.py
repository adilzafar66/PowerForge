"""Actual preparation, immutable outputs, purpose separation and bounded recovery."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from documents_support import client
from enrichment_support import build_source, detail, execute, snapshot_base, start
from enrichment_support import enrichment_ctx as enrichment_ctx
from powerforge_document_processing.storage.base import TransientStorageError
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.enrichment_models import (
    SourceEnrichmentArtifact,
    SourceEnrichmentPageResult,
)
from powerforge_extraction.enrichment_profiles import PURPOSE
from powerforge_extraction.enrichment_service import start_preparation
from powerforge_extraction.models import (
    ExtractionAICall,
    ExtractionWorkUnit,
)
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.phase6r_runtime import StageResult
from powerforge_provenance.spatial_sources import PreparedPage, load_positioned_text
from test_enrichment_native import scan_png

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("image", [False, True])
def test_real_preparation_reuses_exact_results_and_never_changes_phase3_or_canonical(
    ctx, enrichment_ctx, image
):
    ctx = enrichment_ctx
    if image:
        build_source(ctx, scan_png(), "scan.png")
    before = snapshot_base(ctx)
    with ctx["factory"]() as s:
        revision_before = s.scalar(
            text("SELECT to_jsonb(t) FROM project_revisions t WHERE id=:r"),
            {"r": UUID(ctx["revision_id"])},
        )
    pending = start(ctx)
    rid = pending["run"]["id"]
    uid = pending["attempts"][0]["id"]
    assert ctx["delivery"].sources and not ctx["delivery"].ids
    assert execute(ctx, uid)
    assert not execute(ctx, uid)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED", done
    assert done["run"]["execution_purpose"] == PURPOSE and done["run"]["operating_cost"] is None
    assert done["ocr_requests_started"] == int(image)
    result = done["results"][0]
    assert result["page_number"] == 1 and result["work_unit_id"] == uid
    manifest_reply = client.get(
        ctx["base"] + f"/source-enrichment/runs/{rid}/results/{result['id']}"
    )
    assert manifest_reply.status_code == 200, manifest_reply.text
    manifest = PreparedPage.model_validate_json(
        __import__("json").dumps(manifest_reply.json()["manifest"])
    )
    assert manifest.identity_hash == result["manifest_hash"]
    assert manifest.text_coverage == "UNKNOWN"
    texts = []
    with ctx["factory"]() as session:
        for descriptor in manifest.representations:
            geometry = session.get(SourceEnrichmentArtifact, descriptor.geometry_artifact.id)
            text_artifact = session.get(SourceEnrichmentArtifact, descriptor.text_artifact.id)
            body, read = load_positioned_text(
                manifest,
                descriptor.ref,
                ctx["storage"].get(geometry.storage_key).read(),
                ctx["storage"].get(text_artifact.storage_key).read(),
            )
            texts.append(read)
            reply = client.get(
                ctx["base"] + f"/source-enrichment/runs/{rid}/artifacts/{text_artifact.id}"
            )
            assert reply.status_code == 200, reply.text
            assert "storage_key" not in reply.text
            assert body.tokens[0].raw_text == "TX-1"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExtractionAICall)
                .where(ExtractionAICall.run_id == UUID(rid))
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count()).select_from(StageResult).where(StageResult.run_id == UUID(rid))
            )
            == 0
        )
        revision_after = session.scalar(
            text("SELECT to_jsonb(t) FROM project_revisions t WHERE id=:r"),
            {"r": UUID(ctx["revision_id"])},
        )
        assert revision_before == revision_after
    assert any(("750" if image else "600") in t for t in texts)
    assert start(ctx)["run"]["id"] == rid
    assert snapshot_base(ctx) == before
    assert start(ctx, mode="reextract")["run"]["id"] != rid


def test_reciprocal_direct_id_api_denials_have_no_side_effects(enrichment_ctx):
    ctx = enrichment_ctx
    source = start(ctx)
    sid = source["run"]["id"]
    eid = str(uuid4())

    def counts():
        with ctx["factory"]() as session:
            return (
                session.execute(
                    text("SELECT count(*),sum(calls_admitted) FROM extraction_run_execution")
                ).one(),
                len(ctx["storage"].calls),
                len(ctx["delivery"].sources),
                len(ctx["delivery"].ids),
            )

    before = counts()
    for suffix in ("", "/candidates", "/tables"):
        assert client.get(ctx["base"] + f"/extraction/runs/{sid}" + suffix).status_code == 404
    for suffix in ("/retry", "/cancel"):
        assert client.post(ctx["base"] + f"/extraction/runs/{sid}" + suffix).status_code == 404
        assert (
            client.post(ctx["base"] + f"/source-enrichment/runs/{eid}" + suffix).status_code == 404
        )
    for suffix in ("", f"/results/{uuid4()}", f"/artifacts/{uuid4()}"):
        assert (
            client.get(ctx["base"] + f"/source-enrichment/runs/{eid}" + suffix).status_code == 404
        )
    assert counts() == before
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        uid = session.scalar(
            select(ExtractionWorkUnit.id).where(ExtractionWorkUnit.run_id == UUID(sid))
        )
        assert coordinator.claim(uid, purpose="EXTRACTION") is None
        with pytest.raises(Exception, match="not found"):
            coordinator.cancel(UUID(sid), purpose="EXTRACTION")
    assert counts() == before


def test_concurrent_ensure_uses_one_target_and_one_admission(enrichment_ctx):
    ctx = enrichment_ctx

    def create(_):
        with ctx["factory"].begin() as session:
            return start_preparation(
                session, ctx["settings"], ctx["document"], ctx["processing"], [1], []
            ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(create, range(2)))
    assert ids[0] == ids[1]
    response = detail(ctx, ids[0])
    uid = UUID(response["attempts"][0]["id"])

    def claim(_):
        with ctx["factory"].begin() as session:
            return ExtractionCoordinator(session, ctx["settings"]).claim(uid, purpose=PURPOSE)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, range(2)))
    assert sum(c is not None for c in claims) == 1
    with ctx["factory"]() as session:
        assert session.get(RunExecution, ids[0]).calls_admitted == 1


def test_transient_object_failure_retries_but_corruption_is_permanent(enrichment_ctx, monkeypatch):
    ctx = enrichment_ctx
    run = start(ctx)
    rid = run["run"]["id"]
    uid = run["attempts"][0]["id"]
    get = ctx["storage"].get

    def unavailable(key):
        raise TransientStorageError("PRIVATE transport")

    monkeypatch.setattr(ctx["storage"], "get", unavailable)
    assert execute(ctx, uid)
    pending = detail(ctx, rid)
    assert pending["run"]["status"] == "RUNNING" and len(pending["attempts"]) == 2
    assert pending["attempts"][0]["error_code"] == "SOURCE_UNAVAILABLE"
    monkeypatch.setattr(ctx["storage"], "get", get)
    assert execute(ctx, pending["attempts"][-1]["id"])
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
    new = start(ctx, mode="reextract")
    rid = new["run"]["id"]
    from io import BytesIO

    monkeypatch.setattr(ctx["storage"], "get", lambda key: BytesIO(b"corrupt"))
    assert execute(ctx, new["attempts"][0]["id"])
    failed = detail(ctx, rid)
    assert failed["run"]["status"] == "FAILED" and len(failed["attempts"]) == 1


def test_expired_and_cancelled_attempts_cannot_publish_or_cross_purpose(enrichment_ctx):
    from powerforge_extraction.errors import LeaseLost

    ctx = enrichment_ctx
    pending = start(ctx)
    rid = UUID(pending["run"]["id"])
    uid = UUID(pending["attempts"][0]["id"])
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        claim = coordinator.claim(uid, purpose=PURPOSE)
        unit = session.get(ExtractionWorkUnit, uid)
        unit.lease_expires_at = coordinator.now() - timedelta(seconds=1)
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        assert coordinator.reconcile() == 1
        with pytest.raises(LeaseLost):
            coordinator._authorized(uid, claim.token)
    pending = detail(ctx, rid)
    assert len(pending["attempts"]) == 2
    retry_uid = UUID(pending["attempts"][-1]["id"])
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        retry = coordinator.claim(retry_uid, purpose=PURPOSE)
        coordinator.cancel(rid, purpose=PURPOSE)
        with pytest.raises(LeaseLost):
            coordinator._authorized(retry_uid, retry.token)
    assert not execute(ctx, retry_uid)
    assert detail(ctx, rid)["run"]["status"] == "CANCELLED"


def test_result_and_artifacts_are_append_only_and_success_needs_its_real_result(enrichment_ctx):
    ctx = enrichment_ctx
    pending = start(ctx)
    uid = UUID(pending["attempts"][0]["id"])
    with ctx["factory"].begin() as session:
        claim = ExtractionCoordinator(session, ctx["settings"]).claim(uid, purpose=PURPOSE)
    with ctx["factory"]() as session:
        with pytest.raises(DBAPIError):
            ExtractionCoordinator(session, ctx["settings"])._authorized(uid, claim.token)
            session.get(ExtractionWorkUnit, uid).status = "COMPLETED"
            session.flush()
        session.rollback()
    # Abandon the claimed lease, recover, then execute the successor normally.
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        session.get(ExtractionWorkUnit, uid).lease_expires_at = coordinator.now() - timedelta(
            seconds=1
        )
    with ctx["factory"].begin() as session:
        ExtractionCoordinator(session, ctx["settings"]).reconcile()
    pending = detail(ctx, pending["run"]["id"])
    execute(ctx, pending["attempts"][-1]["id"])
    rid = UUID(pending["run"]["id"])
    for table, column in (
        ("source_enrichment_page_results", "manifest_hash"),
        ("source_enrichment_artifacts", "sha256"),
    ):
        with ctx["factory"]() as session:
            with pytest.raises(DBAPIError):
                session.execute(
                    text(
                        f"UPDATE {table} SET {column}='"
                        + "0" * 64
                        + "' WHERE "
                        + (
                            "run_id=:r"
                            if table.endswith("results")
                            else (
                                "result_id IN (SELECT id FROM source_enrichment_page_results "
                                "WHERE run_id=:r)"
                            )
                        )
                    ),
                    {"r": rid},
                )
            session.rollback()


def test_partial_tiff_success_survives_retry_without_repeating_completed_ocr(
    enrichment_ctx, monkeypatch
):
    from io import BytesIO

    from PIL import Image

    from powerforge_document_processing.models import PageArtifact
    from powerforge_document_processing.storage.base import ObjectNotFound

    ctx = enrichment_ctx
    with Image.open(BytesIO(scan_png())) as frame:
        stream = BytesIO()
        frame.save(stream, format="TIFF", save_all=True, append_images=[frame.copy()])
    build_source(ctx, stream.getvalue(), "scanned.tiff")
    before = snapshot_base(ctx)
    pending = start(ctx, pages=[1, 2])
    rid = pending["run"]["id"]
    assert execute(ctx, pending["attempts"][0]["id"])
    with ctx["factory"]() as session:
        page2_id = session.scalar(
            select(ExtractionWorkUnit.id).where(
                ExtractionWorkUnit.run_id == UUID(rid), ExtractionWorkUnit.page_numbers == [2]
            )
        )
        second = session.get(ExtractionWorkUnit, page2_id)
        image = session.get(PageArtifact, UUID(second.input_artifact_ids[0]))
        key = image.storage_key
    original_get = ctx["storage"].get

    def missing(storage_key):
        if storage_key == key:
            raise ObjectNotFound("missing")
        return original_get(storage_key)

    monkeypatch.setattr(ctx["storage"], "get", missing)
    assert execute(ctx, page2_id)
    partial = detail(ctx, rid)
    assert partial["run"]["status"] == "PARTIALLY_COMPLETED" and len(partial["results"]) == 1
    completed_id = partial["results"][0]["id"]
    manifest_hash = partial["results"][0]["manifest_hash"]
    monkeypatch.setattr(ctx["storage"], "get", original_get)
    response = client.post(ctx["base"] + f"/source-enrichment/runs/{rid}/retry")
    assert response.status_code == 202, response.text
    successor = response.json()["attempts"][-1]["id"]
    execute(ctx, successor)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED" and len(done["results"]) == 2
    assert done["ocr_requests_started"] == 2
    assert any(
        r["id"] == completed_id and r["manifest_hash"] == manifest_hash for r in done["results"]
    )
    assert snapshot_base(ctx) == before


def test_hybrid_pdf_requires_explicit_selection_and_ocr_keeps_separate_native_readings(
    enrichment_ctx,
):
    from test_enrichment_native import native_pdf

    ctx = enrichment_ctx
    build_source(ctx, native_pdf(embedded=True), "hybrid.pdf")
    skipped = start(ctx)
    execute(ctx, skipped["attempts"][0]["id"])
    done = detail(ctx, skipped["run"]["id"])
    assert done["results"][0]["usage"]["ocr_invocations"] == 0
    assert (
        done["results"][0]["usage"]["eligibility_reason"]
        == "UNKNOWN_RASTER_CONTENT_EXPLICIT_SELECTION_REQUIRED"
    )
    selected = start(ctx, force_ocr_pages=[1])
    execute(ctx, selected["attempts"][0]["id"])
    done = detail(ctx, selected["run"]["id"])
    assert done["run"]["status"] == "COMPLETED", done
    result = client.get(
        ctx["base"]
        + f"/source-enrichment/runs/{selected['run']['id']}/results/{done['results'][0]['id']}"
    ).json()
    assert [r["ref"] for r in result["manifest"]["representations"]] == ["native", "ocr"]
    assert len(result["manifest"]["derived_images"]) == 1
    assert done["results"][0]["usage"]["ocr_invocations"] == 1


def test_source_reads_enforce_current_membership_inherited_and_superseded_access(enrichment_ctx):
    from documents_support import make_revision
    from powerforge_document_processing.models import RevisionDocument

    ctx = enrichment_ctx
    pending = start(ctx)
    execute(ctx, pending["attempts"][0]["id"])
    rid = pending["run"]["id"]
    next_revision = make_revision(
        ctx["project_id"],
        "next",
        based_on_revision_id=ctx["revision_id"],
        carry_forward_documents=True,
        activate=True,
    )
    assert next_revision.status_code == 201, next_revision.text
    with ctx["factory"]() as session:
        link = session.scalar(
            select(RevisionDocument).where(
                RevisionDocument.revision_id == UUID(next_revision.json()["id"]),
                RevisionDocument.document_id == ctx["document"],
            )
        )
        path = (
            f"/api/projects/{ctx['project_id']}/revisions/{next_revision.json()['id']}"
            f"/documents/{link.id}"
        )
    assert client.get(path + f"/source-enrichment/runs/{rid}").status_code == 200
    assert client.get(ctx["base"] + f"/source-enrichment/runs/{rid}").status_code == 200
    # Removal revokes source reads, including successful outputs and signing.
    with ctx["factory"].begin() as session:
        row = session.get(RevisionDocument, link.id)
        row.status = "REMOVED"
        row.removed_at = ExtractionCoordinator(session, ctx["settings"]).now()
    assert client.get(path + f"/source-enrichment/runs/{rid}").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"pages": [True]},
        {"pages": [1, 1]},
        {"pages": [99]},
        {"force_ocr_pages": [2]},
        {"profile_key": "infrastructure-fake-v1"},
    ],
)
def test_invalid_start_selections_fail_before_admission(enrichment_ctx, body):
    ctx = enrichment_ctx
    response = client.post(
        ctx["base"] + "/source-enrichment/runs",
        json={"processing_run_id": str(ctx["processing"]), "pages": [1], **body},
    )
    assert response.status_code == 422, response.text
    assert not ctx["delivery"].sources


def prepared_attempt(ctx):
    from powerforge_document_processing.models import Document, DocumentPage, DocumentProcessingRun
    from powerforge_extraction.enrichment_execution import read_exact
    from powerforge_extraction.enrichment_prepare import prepare_page
    from powerforge_extraction.enrichment_service import source_snapshot

    pending = start(ctx)
    uid = UUID(pending["attempts"][0]["id"])
    with ctx["factory"].begin() as session:
        claim = ExtractionCoordinator(session, ctx["settings"]).claim(uid, purpose=PURPOSE)
    with ctx["factory"]() as session:
        unit = session.get(ExtractionWorkUnit, uid)
        document = session.get(Document, unit.document_id)
        processing = session.get(DocumentProcessingRun, unit.processing_run_id)
        page = session.scalar(
            select(DocumentPage).where(
                DocumentPage.document_id == document.id, DocumentPage.page_number == 1
            )
        )
        owner, original, base, keys = source_snapshot(
            session, document, processing, page, unit.input_artifact_ids
        )
        original_key = document.storage_key
        metadata = unit.execution_metadata
    original_data = read_exact(ctx["storage"], original_key, original.size_bytes, original.sha256)
    bodies = {a.id: read_exact(ctx["storage"], keys[a.id], a.size_bytes, a.sha256) for a in base}
    output = prepare_page(
        owner,
        original,
        original_data,
        base,
        bodies,
        claim.run_id,
        uid,
        metadata["preparation_hash"],
        claim.profile,
        False,
        lambda: ctx["provider"],
    )
    return claim, output


@pytest.mark.parametrize("mutation", ["original", "blob", "base"])
def test_publication_rechecks_original_body_bytes_and_exact_source_set(enrichment_ctx, mutation):
    from dataclasses import replace

    from powerforge_extraction.enrichment_service import publish_preparation

    ctx = enrichment_ctx
    claim, output = prepared_attempt(ctx)
    if mutation == "original":
        output = replace(
            output,
            manifest=output.manifest.model_copy(
                update={
                    "original": output.manifest.original.model_copy(update={"sha256": "0" * 64})
                }
            ),
        )
    elif mutation == "base":
        output = replace(
            output,
            manifest=output.manifest.model_copy(
                update={"base_artifacts": output.manifest.base_artifacts[:1]}
            ),
        )
    else:
        ref, data = next(iter(output.blobs.values()))
        output.blobs[ref.id] = (ref, data + b"corrupted")
    with ctx["factory"]() as session:
        with pytest.raises(ValueError):
            publish_preparation(session, ctx["settings"], claim, output)
        session.rollback()
        assert not session.scalar(
            select(SourceEnrichmentPageResult.id).where(
                SourceEnrichmentPageResult.work_unit_id == claim.unit_id
            )
        )


def test_sql_does_not_allow_local_jobs_to_publish_ai_telemetry(
    enrichment_ctx,
):
    from powerforge_extraction.contracts import AICallInput
    from powerforge_extraction.persistence import ExtractionPersistence

    ctx = enrichment_ctx
    claim, _ = prepared_attempt(ctx)
    with ctx["factory"]() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        coordinator._authorized(claim.unit_id, claim.token)
        now = coordinator.now()
        call = AICallInput(
            provider="fake",
            model="fake",
            prompt_version="none",
            prompt_hash="none",
            schema_version="none",
            outcome="SUCCEEDED",
            started_at=now,
            finished_at=now,
            duration_ms=0,
        )
        with pytest.raises(DBAPIError, match=r"Local jobs cannot\s+publish"):
            ExtractionPersistence(session).record_ai_call(claim.unit_id, call)
        session.rollback()


def test_ocr_timeout_uses_bounded_retry_and_records_actual_started_invocations(
    enrichment_ctx, monkeypatch
):
    from powerforge_ai.ocr import OCRFailure, OCRFailureCode

    ctx = enrichment_ctx
    build_source(ctx, scan_png(), "timeout.png")
    original = ctx["provider"].recognize
    calls = []

    def recognize(request):
        calls.append(request.request_id)
        if len(calls) == 1:
            raise OCRFailure(OCRFailureCode.TIMEOUT)
        return original(request)

    monkeypatch.setattr(ctx["provider"], "recognize", recognize)
    pending = start(ctx)
    rid = pending["run"]["id"]
    execute(ctx, pending["attempts"][0]["id"])
    retry = detail(ctx, rid)
    assert (
        retry["run"]["status"] == "RUNNING" and retry["attempts"][0]["error_code"] == "OCR_TIMEOUT"
    )
    execute(ctx, retry["attempts"][-1]["id"])
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED" and done["ocr_requests_started"] == 2
    assert len(calls) == 2


def test_source_input_discovery_is_read_only_and_exposes_completed_processing_ids(enrichment_ctx):
    ctx = enrichment_ctx
    response = client.get(ctx["base"] + "/source-enrichment/inputs")
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["processing_run_id"] == str(ctx["processing"])
    assert response.json()["items"][0]["available_pages"] == [1]
    assert "storage_key" not in response.text
    assert not ctx["delivery"].sources
    with ctx["factory"]() as session:
        assert not session.scalar(
            select(ExtractionWorkUnit.id).where(ExtractionWorkUnit.document_id == ctx["document"])
        )


@pytest.mark.parametrize("force_ocr", [False, True])
def test_provider_initialization_is_deferred_until_ocr_is_selected(enrichment_ctx, force_ocr):
    from powerforge_ai.ocr import OCRFailure, OCRFailureCode
    from powerforge_extraction.enrichment_execution import execute_preparation

    ctx = enrichment_ctx
    pending = start(ctx, force_ocr_pages=[1] if force_ocr else [])
    calls = []

    def unavailable_provider():
        calls.append(True)
        raise OCRFailure(OCRFailureCode.ENGINE_UNAVAILABLE)

    assert execute_preparation(
        UUID(pending["attempts"][0]["id"]),
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        unavailable_provider,
    )
    result = detail(ctx, pending["run"]["id"])
    assert len(calls) == int(force_ocr)
    assert result["ocr_requests_started"] == 0
    if force_ocr:
        assert result["run"]["status"] == "FAILED"
        assert result["attempts"][0]["error_code"] == "OCR_ENGINE_UNAVAILABLE"
        assert result["results"] == []
    else:
        assert result["run"]["status"] == "COMPLETED"
        assert result["results"][0]["usage"]["ocr_invocations"] == 0
