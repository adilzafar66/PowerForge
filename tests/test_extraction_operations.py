"""Durable Phase 6F admission, source barriers, recovery and scope."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pymupdf
import pytest
from sqlalchemy import select

from documents_support import client, make_project, make_revision
from enrichment_support import Delivery, build_source
from powerforge_ai.extraction import ErrorCode, ProviderFailure
from powerforge_api.db import get_session_factory
from powerforge_api.main import app
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    PageArtifact,
    RevisionDocument,
)
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.enqueue import get_extraction_enqueue
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.layout_execution import execute_enrichment
from powerforge_extraction.layout_service import start_layout
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.operation_models import ExtractionOperation, OperationRequest
from powerforge_extraction.operations import now, reconcile_operations
from powerforge_extraction.orchestration import ACTIVE, ExtractionCoordinator
from powerforge_shared.config import Settings, get_settings
from test_enrichment_native import native_pdf, scan_png
from test_extraction_celery_integration import live_worker, wait_for

pytestmark = pytest.mark.integration


@pytest.fixture
def operation_context(ctx):
    fixture = Path(__file__).parent / "fixtures/enrichment/preparation_v1_environment.json"
    configuration = json.dumps(json.loads(fixture.read_text())["configuration"])
    settings = Settings(
        _env_file=None,
        enrichment_enabled=True,
        enrichment_ocr_configuration=configuration,
        extraction_external_enabled=True,
        extraction_operation_max_concurrent_documents=1,
        extraction_backoff_seconds=0,
        extraction_recovery_interval_seconds=1,
        extraction_redispatch_seconds=1,
        openai_api_key="phase6f-test-stub",
    )
    delivery = Delivery()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_extraction_enqueue] = lambda: delivery
    factory = get_session_factory()
    yield {
        **ctx,
        "factory": factory,
        "settings": settings,
        "delivery": delivery,
        "operation_base": (
            f"/api/projects/{ctx['project_id']}/revisions/{ctx['revision_id']}/extraction"
        ),
    }
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_extraction_enqueue, None)
    with factory.begin() as session:
        for op in session.scalars(
            select(ExtractionOperation).where(
                ExtractionOperation.revision_id == UUID(ctx["revision_id"])
            )
        ):
            op.next_check_at = None
        for run in session.scalars(
            select(ExtractionRun)
            .join(Document, Document.id == ExtractionRun.document_id)
            .where(Document.project_id == UUID(ctx["project_id"]), ExtractionRun.status.in_(ACTIVE))
        ):
            ExtractionCoordinator(session, settings).cancel(run.id, purpose=run.execution_purpose)


def new_source(ctx, filename, content=None):
    data = build_source(dict(ctx), content or native_pdf(), filename)
    return {
        "revision_document_id": data["base"].rsplit("/", 1)[-1],
        "processing_run_id": str(data["processing"]),
        "pages": [1],
    }


def preparation(ctx, source):
    with ctx["factory"].begin() as session:
        membership = session.get(RevisionDocument, UUID(source["revision_document_id"]))
        run = start_layout(
            session,
            ctx["settings"],
            membership.document_id,
            UUID(source["processing_run_id"]),
            source["pages"],
            source.get("force_ocr_pages", []),
            membership.id,
        )
        run_id = run.id
        units = session.scalars(
            select(ExtractionWorkUnit)
            .where(ExtractionWorkUnit.run_id == run_id)
            .order_by(ExtractionWorkUnit.stage)
        ).all()
        ids = [unit.id for unit in units]
    for unit_id in ids:
        assert execute_enrichment(
            unit_id,
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda: pytest.fail("Native preparation should not start OCR"),
        )
    with ctx["factory"]() as session:
        assert session.get(ExtractionRun, run_id).status == "COMPLETED"
    return run_id


def reviewed(ctx, documents, **overrides):
    selection = {"documents": documents, **overrides}
    response = client.post(ctx["operation_base"] + "/operations/preview", json=selection)
    assert response.status_code == 200, response.text
    plan = response.json()
    return plan, {
        "selection": selection,
        "review_hash": plan["review_hash"],
        "request_key": str(uuid4()),
        "external_processing_consent": True,
    }


def start_operation(ctx, body):
    return client.post(ctx["operation_base"] + "/operations", json=body)


def detail_operation(ctx, operation_id):
    response = client.get(ctx["operation_base"] + f"/operations/{operation_id}")
    assert response.status_code == 200, response.text
    return response.json()


def advance(ctx, operation_id):
    with ctx["factory"].begin() as session:
        op = session.get(ExtractionOperation, UUID(operation_id))
        op.next_check_at = now(session) - timedelta(seconds=1)
    reconcile_operations(ctx["factory"], ctx["settings"], ctx["storage"])


def test_admission_reviews_exact_inputs_and_coalesces_concurrent_submissions(operation_context):
    ctx = operation_context
    first = new_source(ctx, "first.pdf")
    second = new_source(ctx, "second.pdf")
    root = ctx["operation_base"]
    selected = [first, second]
    discovery = client.post(
        root + "/operations/sources",
        json={"revision_document_ids": [item["revision_document_id"] for item in selected]},
    )
    assert discovery.status_code == 200, discovery.text
    assert all(item["available_pages"] == [1] for item in discovery.json()["items"])
    plan, request = reviewed(ctx, selected)
    assert plan["review_hash"]
    assert plan["planned_runs"] == 4
    assert plan["provider_admissions"] == 24
    assert all(not item["pages"][0]["reuse_layout"] for item in plan["items"])
    with ctx["factory"]() as session:
        assert (
            session.scalar(
                select(ExtractionRun.id).where(
                    ExtractionRun.processing_run_id.in_(
                        [UUID(doc["processing_run_id"]) for doc in selected]
                    )
                )
            )
            is None
        )
    assert (
        start_operation(ctx, {**request, "external_processing_consent": False}).status_code == 422
    )
    assert start_operation(ctx, {**request, "review_hash": "a" * 64}).status_code == 409
    response = client.post(
        root + "/operations/preview",
        json={
            "documents": [{**first, "force_ocr_pages": [2]}],
        },
    )
    assert response.status_code == 422

    requests = [request, {**request, "request_key": str(uuid4())}, request]
    with ThreadPoolExecutor(max_workers=3) as executor:
        responses = list(executor.map(lambda body: start_operation(ctx, body), requests))
    assert all(response.status_code == 202 for response in responses), [r.text for r in responses]
    operation_ids = {response.json()["id"] for response in responses}
    assert len(operation_ids) == 1
    [operation_id] = operation_ids
    with ctx["factory"]() as session:
        assert (
            len(
                session.scalars(
                    select(OperationRequest).where(
                        OperationRequest.operation_id == UUID(operation_id)
                    )
                ).all()
            )
            == 2
        )
    status = client.get(
        root + "/status",
        params=[
            ("revision_document_ids", first["revision_document_id"]),
        ],
    )
    assert status.json()["items"][0]["pending_operation"]["id"] == operation_id
    assert detail_operation(ctx, operation_id)["status"] == "QUEUED"

    foreign = make_project()
    revision = make_revision(foreign, "0", activate=True).json()["id"]
    assert (
        client.get(
            f"/api/projects/{foreign}/revisions/{revision}/extraction/operations/{operation_id}"
        ).status_code
        == 404
    )
    advance(ctx, operation_id)
    active = detail_operation(ctx, operation_id)
    assert sum(item["layout"]["run_id"] is not None for item in active["items"]) == 1
    assert all(
        step["run_id"] is None for item in active["items"] for step in item["profiles"].values()
    )
    reply = client.post(root + f"/operations/{operation_id}/cancel")
    assert reply.status_code == 200 and reply.json()["cancel_requested"]
    advance(ctx, operation_id)
    cancelled = detail_operation(ctx, operation_id)
    assert sum(item["layout"]["run_id"] is not None for item in cancelled["items"]) == 1
    assert all(
        step["status"] == "CANCELLED"
        for item in cancelled["items"]
        for step in item["profiles"].values()
    )
    assert start_operation(ctx, request).json()["id"] == operation_id
    first_admitted = next(item for item in cancelled["items"] if item["layout"]["run_id"])
    doc_id = first_admitted["revision_document_id"]
    document_base = root.removesuffix("/extraction") + f"/documents/{doc_id}"
    assert client.post(document_base + "/remove").status_code == 200
    hidden = detail_operation(ctx, operation_id)
    assert hidden["unavailable_sources"] == 1
    assert all(item["revision_document_id"] != doc_id for item in hidden["items"])
    assert first_admitted["layout"]["run_id"] not in json.dumps(hidden)


def test_ambiguous_provider_outcome_requires_acknowledgement(operation_context):
    ctx = operation_context
    source = new_source(ctx, "exact.pdf")
    preparation(ctx, source)
    ready, request = reviewed(ctx, [source], families=["engineering"])
    assert ready["items"][0]["pages"][0]["reuse_layout"]
    forced, _ = reviewed(ctx, [{**source, "force_ocr_pages": [1]}], families=["engineering"])
    assert forced["review_hash"] != ready["review_hash"]
    assert not forced["items"][0]["pages"][0]["reuse_preparation"]
    response = start_operation(ctx, request)
    assert response.status_code == 202, response.text
    operation_id = response.json()["id"]
    advance(ctx, operation_id)
    item = detail_operation(ctx, operation_id)["items"][0]
    assert item["layout"]["status"] == "REUSED"
    run_id = item["profiles"]["engineering"]["run_id"]
    assert run_id
    with ctx["factory"]() as session:
        unit_id = session.scalar(
            select(ExtractionWorkUnit.id).where(
                ExtractionWorkUnit.run_id == UUID(run_id),
                ExtractionWorkUnit.stage == "EQUIPMENT_RECOGNITION",
            )
        )

    class Timeout:
        def execute(self, _request):
            raise ProviderFailure(ErrorCode.TIMEOUT)

    execute_unit(unit_id, ctx["factory"], ctx["storage"], ctx["settings"], lambda _claim: Timeout())
    failed = detail_operation(ctx, operation_id)["items"][0]["profiles"]["engineering"]
    assert failed["unknown_provider_outcome"]
    assert failed["can_retry"]
    assert failed["attempts"] == 2  # No automatic third attempt.
    retry = ctx["operation_base"] + f"/operations/{operation_id}/retry"
    body = {
        "revision_document_id": source["revision_document_id"],
        "step": "engineering",
        "expected_attempts": failed["attempts"],
    }
    assert client.post(retry, json=body).status_code == 409
    approved = client.post(retry, json={**body, "acknowledge_unknown_outcome": True})
    assert approved.status_code == 202, approved.text
    replay = client.post(retry, json={**body, "acknowledge_unknown_outcome": True})
    assert replay.status_code == 202
    assert replay.json()["items"][0]["profiles"]["engineering"]["attempts"] == 4


def test_missing_object_on_one_selected_page_blocks_all_provider_runs(operation_context):
    ctx = operation_context
    with pymupdf.open(stream=native_pdf(), filetype="pdf") as page, pymupdf.open() as document:
        document.insert_pdf(page)
        document.insert_pdf(page)
        source = new_source(ctx, "two-pages.pdf", document.tobytes())
    source["pages"] = [1, 2]
    preparation(ctx, source)
    plan, body = reviewed(ctx, [source])
    assert all(page["reuse_layout"] for page in plan["items"][0]["pages"])
    accepted = start_operation(ctx, body)
    assert accepted.status_code == 202, accepted.text
    operation_id = accepted.json()["id"]
    with ctx["factory"]() as session:
        key = session.scalar(
            select(PageArtifact.storage_key)
            .join(DocumentPage, DocumentPage.id == PageArtifact.document_page_id)
            .where(
                PageArtifact.processing_run_id == UUID(source["processing_run_id"]),
                PageArtifact.artifact_type == "ANALYSIS_IMAGE",
                DocumentPage.page_number == 2,
            )
        )
    original = ctx["storage"].objects[key]
    ctx["storage"].delete(key)
    advance(ctx, operation_id)
    item = detail_operation(ctx, operation_id)["items"][0]
    assert item["blocked_reason"] == "SOURCE_ARTIFACT_UNAVAILABLE"
    assert item["can_resume"]
    assert all(step["run_id"] is None for step in item["profiles"].values())
    ctx["storage"].put(key, BytesIO(original.data), len(original.data), original.content_type)
    reply = client.post(
        ctx["operation_base"] + f"/operations/{operation_id}/retry",
        json={"revision_document_id": source["revision_document_id"], "step": "resume"},
    )
    assert reply.status_code == 202, reply.text
    advance(ctx, operation_id)
    item = detail_operation(ctx, operation_id)["items"][0]
    assert all(step["run_id"] for step in item["profiles"].values())


def test_beat_advances_mixed_batch_using_real_transport(
    operation_context, s3_scratch_storage, tmp_path
):
    ctx = operation_context
    storage = s3_scratch_storage
    ctx["storage"] = storage
    previous = app.dependency_overrides[get_object_storage]
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        ready = new_source(ctx, "ready.pdf")
        missing = new_source(ctx, "unreadable-ocr.png", scan_png())
        automatic = new_source(ctx, "force-ocr.pdf")
        automatic["force_ocr_pages"] = [1]
        preparation(ctx, ready)
        preview, request = reviewed(ctx, [ready, missing, automatic])
        assert preview["review_hash"]
        result = start_operation(ctx, request)
        assert result.status_code == 202, result.text
        operation_id = result.json()["id"]
        assert detail_operation(ctx, operation_id)["status"] == "QUEUED"
        with live_worker(
            ctx,
            storage,
            tmp_path / "operations",
            beat=True,
            app_module="operation_test_worker",
            queue="document_extraction,source_enrichment",
            extra_env={
                "ENRICHMENT_ENABLED": "true",
                "ENRICHMENT_OCR_CONFIGURATION": ctx["settings"].enrichment_ocr_configuration,
                "EXTRACTION_EXTERNAL_ENABLED": "true",
                "EXTRACTION_BACKOFF_SECONDS": "0",
                "OPENAI_API_KEY": "phase6f-test-stub",
            },
        ):
            wait_for(lambda: detail_operation(ctx, operation_id)["status"] == "PARTIAL")
        result = detail_operation(ctx, operation_id)
        by_name = {item["filename"]: item for item in result["items"]}
        assert by_name["ready.pdf"]["status"] == "COMPLETED"
        assert by_name["ready.pdf"]["layout"]["status"] == "REUSED"
        assert {step["status"] for step in by_name["ready.pdf"]["profiles"].values()} == {
            "COMPLETED"
        }
        assert by_name["force-ocr.pdf"]["status"] == "COMPLETED", by_name["force-ocr.pdf"]
        assert by_name["force-ocr.pdf"]["layout"]["status"] == "COMPLETED"
        assert by_name["force-ocr.pdf"]["force_ocr_pages"] == [1]
        assert {step["status"] for step in by_name["force-ocr.pdf"]["profiles"].values()} == {
            "COMPLETED"
        }
        assert by_name["unreadable-ocr.png"]["status"] == "BLOCKED"
        assert by_name["unreadable-ocr.png"]["layout"]["status"] == "FAILED"
        assert all(
            step["run_id"] is None for step in by_name["unreadable-ocr.png"]["profiles"].values()
        )

        original_id = by_name["ready.pdf"]["profiles"]["engineering"]["run_id"]
        _, reextract = reviewed(ctx, [ready], families=["engineering"], mode="reextract")
        again = start_operation(ctx, reextract)
        assert again.status_code == 202, again.text
        advance(ctx, again.json()["id"])
        replacement = detail_operation(ctx, again.json()["id"])["items"][0]["profiles"][
            "engineering"
        ]
        assert replacement["run_id"] != original_id
        with ctx["factory"]() as session:
            assert session.get(
                ExtractionRun, UUID(replacement["run_id"])
            ).reextracts_run_id == UUID(original_id)

    finally:
        app.dependency_overrides[get_object_storage] = previous


def test_wizard_automatically_uses_canonical_layout_for_dense_drawing(operation_context):
    from powerforge_document_processing.layout_derive import layout_rules_identity
    from powerforge_extraction.layout_models import SourceSpatialResult
    from spatial_layout_support import disconnected_drawing

    ctx = operation_context
    source = new_source(ctx, "disconnected-drawing.pdf", disconnected_drawing())
    _, request = reviewed(ctx, [source])
    accepted = start_operation(ctx, request)
    assert accepted.status_code == 202, accepted.text
    operation_id = accepted.json()["id"]
    advance(ctx, operation_id)
    item = detail_operation(ctx, operation_id)["items"][0]
    layout_run_id = UUID(item["layout"]["run_id"])
    with ctx["factory"]() as session:
        units = session.scalars(
            select(ExtractionWorkUnit)
            .where(ExtractionWorkUnit.run_id == layout_run_id)
            .order_by(ExtractionWorkUnit.stage)
        ).all()
        unit_ids = [unit.id for unit in units]
    for unit_id in unit_ids:
        assert execute_enrichment(
            unit_id,
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda: pytest.fail("Native preparation should not start OCR"),
        )
    with ctx["factory"]() as session:
        run = session.get(ExtractionRun, layout_run_id)
        layout = session.scalar(
            select(SourceSpatialResult).where(SourceSpatialResult.run_id == layout_run_id)
        )
        assert run.extractor_version == "source-layout-v1" and run.status == "COMPLETED"
        assert layout.layout_hash == layout_rules_identity()
        assert len(layout.manifest["tables"]) == 1
    advance(ctx, operation_id)
    item = detail_operation(ctx, operation_id)["items"][0]
    assert set(item["profiles"]) == {"engineering", "tables"}
    assert all(step["run_id"] for step in item["profiles"].values())
