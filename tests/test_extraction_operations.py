"""Phase 6R admission, source barriers, recovery and scope."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pymupdf
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from documents_support import client, make_project, make_revision
from enrichment_support import Delivery, build_source
from powerforge_api.db import get_session_factory
from powerforge_api.main import app
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    PageArtifact,
    RevisionDocument,
)
from powerforge_document_processing.storage.base import TransientStorageError
from powerforge_extraction.controls import UnitExecution
from powerforge_extraction.enqueue import get_extraction_enqueue
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.layout_execution import execute_enrichment
from powerforge_extraction.layout_service import start_layout
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.operation_models import ExtractionOperation, OperationRequest
from powerforge_extraction.operations import now, reconcile_operations
from powerforge_extraction.orchestration import ACTIVE, ExtractionCoordinator
from powerforge_shared.config import Settings, get_settings
from test_enrichment_native import native_pdf

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
        extraction_use_fake_provider=True,
        extraction_operation_max_concurrent_documents=1,
        extraction_backoff_seconds=0,
        extraction_recovery_interval_seconds=1,
        extraction_redispatch_seconds=1,
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


def wait_for_availability(ctx, unit_id):
    # Tests call the worker synchronously, without the scheduler's redelivery interval.
    deadline = monotonic() + 2
    with ctx["factory"]() as session:
        available_at = session.get(UnitExecution, unit_id).available_at
        while now(session) < available_at:
            assert monotonic() < deadline, f"Work unit {unit_id} is still unavailable"
            sleep(0.02)


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
        wait_for_availability(ctx, unit_id)
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


def admitted_page(ctx, source):
    preparation(ctx, source)
    _, body = reviewed(ctx, [source])
    reply = start_operation(ctx, body)
    assert reply.status_code == 202, reply.text
    operation_id = reply.json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    with ctx["factory"]() as session:
        units = {
            unit.stage: unit.id
            for unit in session.scalars(
                select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id)
            )
        }
    for unit_id in units.values():
        wait_for_availability(ctx, unit_id)
    return operation_id, run_id, units


def test_publication_profile_change_stops_old_run_and_preserves_published_rows(
    operation_context, monkeypatch
):
    from powerforge_extraction import publication
    from powerforge_extraction.controls import RunExecution
    from powerforge_extraction.errors import ExtractionConflict
    from powerforge_extraction.publication_records import Candidate
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    with monkeypatch.context() as previous:
        previous.setattr(publication, "VERSION", "phase-6r-publication-v1")
        _, run_id, units = admitted_page(ctx, new_source(ctx, "publication-pin.pdf"))
        assert execute_unit(
            units["EQUIPMENT_RECOGNITION"],
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: FakeExtractionProvider("success"),
        )
    with ctx["factory"].begin() as session:
        recognition = units["EQUIPMENT_RECOGNITION"]
        attribute = units["ATTRIBUTE_EXTRACTION"]
        assert session.get(RunExecution, run_id).configuration["manifest"][
            "publication_version"
        ] == ("phase-6r-publication-v1")
        result_hash = session.get(StageResult, recognition).result_hash
        candidate = session.scalar(
            select(Candidate.id).where(Candidate.work_unit_id == recognition)
        )
        assert candidate is not None
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        assert coordinator.claim(attribute) is None
        assert (
            session.get(ExtractionWorkUnit, attribute).error_code
            == "EXTRACTION_PROFILE_UNAVAILABLE"
        )
        assert session.get(ExtractionRun, run_id).status == "PARTIALLY_COMPLETED"
        assert session.get(StageResult, attribute) is None
        assert session.get(StageResult, recognition).result_hash == result_hash
        assert session.get(Candidate, candidate).work_unit_id == recognition
        with pytest.raises(ExtractionConflict, match="Pinned extraction resources"):
            coordinator.retry(run_id)


def test_preview_expiry_and_revalidation_preserve_idempotent_replay(operation_context):
    from powerforge_extraction.operation_models import OperationPreview

    ctx = operation_context
    source = new_source(ctx, "expiry.pdf")
    preview, body = reviewed(ctx, [source])
    assert preview["review_expires_at"]
    assert (
        start_operation(
            ctx, {**body, "selection": {**body["selection"], "mode": "reextract"}}
        ).status_code
        == 409
    )
    ctx["settings"].extraction_max_attempts += 1
    assert start_operation(ctx, body).status_code == 409
    ctx["settings"].extraction_max_attempts -= 1
    accepted = start_operation(ctx, body)
    assert accepted.status_code == 202, accepted.text
    with ctx["factory"].begin() as session:
        record = session.get(OperationPreview, body["review_hash"])
        record.expires_at = now(session) - timedelta(seconds=1)
    assert start_operation(ctx, body).json() == accepted.json()
    expired = start_operation(ctx, {**body, "request_key": str(uuid4())})
    assert expired.status_code == 409 and "expired" in expired.text


def test_run_history_and_operation_retry_share_the_document_slot_limit(operation_context):
    from powerforge_extraction.stage_execution import FakeExtractionProvider

    ctx = operation_context
    sources = [new_source(ctx, "one.pdf"), new_source(ctx, "two.pdf")]
    for source in sources:
        preparation(ctx, source)
    _, body = reviewed(ctx, sources)
    reply = start_operation(ctx, body)
    assert reply.status_code == 202, reply.text
    operation_id = reply.json()["id"]
    advance(ctx, operation_id)
    items = detail_operation(ctx, operation_id)["items"]
    first = next(item for item in items if item["extraction"]["run_id"])
    run_id = UUID(first["extraction"]["run_id"])
    with ctx["factory"]() as session:
        recognition = session.scalar(
            select(ExtractionWorkUnit.id).where(
                ExtractionWorkUnit.run_id == run_id,
                ExtractionWorkUnit.stage == "EQUIPMENT_RECOGNITION",
            )
        )
    assert execute_unit(
        recognition,
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        lambda _: FakeExtractionProvider("invalid"),
    )
    advance(ctx, operation_id)
    items = detail_operation(ctx, operation_id)["items"]
    assert all(item["extraction"]["run_id"] for item in items)
    first = next(item for item in items if item["extraction"]["run_id"] == str(run_id))
    doc_id = first["revision_document_id"]
    base = ctx["operation_base"].removesuffix("/extraction")
    history = client.post(f"{base}/documents/{doc_id}/extraction/runs/{run_id}/retry")
    assert history.status_code == 409 and "slots are busy" in history.text
    target = first["extraction"]["retry_targets"][0]
    operation = client.post(
        ctx["operation_base"] + f"/operations/{operation_id}/retry",
        json={
            "revision_document_id": doc_id,
            "stage": target["stage"],
            "page_id": target["page_id"],
            "expected_attempt": target["expected_attempt"],
        },
    )
    assert operation.status_code == 409 and "slots are busy" in operation.text


def test_admission_reviews_exact_inputs_and_coalesces_concurrent_submissions(operation_context):
    ctx = operation_context
    first = new_source(ctx, "first.pdf")
    second = new_source(ctx, "second.pdf")
    root = ctx["operation_base"]
    runs_url = (
        root.removesuffix("/extraction")
        + f"/documents/{first['revision_document_id']}/extraction/runs"
    )
    assert client.post(runs_url, json={}).status_code == 405
    selected = [first, second]
    for key in ("engineering-openai-enriched-v1", "tables-openai-enriched-v1"):
        assert (
            client.post(
                root + "/operations/preview", json={"documents": selected, "profile_key": key}
            ).status_code
            == 422
        )
    discovery = client.post(
        root + "/operations/sources",
        json={"revision_document_ids": [item["revision_document_id"] for item in selected]},
    )
    assert discovery.status_code == 200, discovery.text
    assert all(item["available_pages"] == [1] for item in discovery.json()["items"])
    plan, request = reviewed(ctx, selected)
    assert plan["review_hash"]
    assert plan["planned_runs"] == 2
    assert plan["provider_admissions"] == 12
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
    assert all(item["extraction"]["run_id"] is None for item in active["items"])
    reply = client.post(root + f"/operations/{operation_id}/cancel")
    assert reply.status_code == 200 and reply.json()["cancel_requested"]
    advance(ctx, operation_id)
    cancelled = detail_operation(ctx, operation_id)
    assert sum(item["layout"]["run_id"] is not None for item in cancelled["items"]) == 1
    assert all(item["extraction"]["status"] == "CANCELLED" for item in cancelled["items"])
    assert start_operation(ctx, request).json()["id"] == operation_id
    first_admitted = next(item for item in cancelled["items"] if item["layout"]["run_id"])
    doc_id = first_admitted["revision_document_id"]
    document_base = root.removesuffix("/extraction") + f"/documents/{doc_id}"
    assert client.post(document_base + "/remove").status_code == 200
    hidden = detail_operation(ctx, operation_id)
    assert hidden["unavailable_sources"] == 1
    assert all(item["revision_document_id"] != doc_id for item in hidden["items"])
    assert first_admitted["layout"]["run_id"] not in json.dumps(hidden)


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
    assert item["extraction"]["run_id"] is None
    ctx["storage"].put(key, BytesIO(original.data), len(original.data), original.content_type)
    reply = client.post(
        ctx["operation_base"] + f"/operations/{operation_id}/retry",
        json={"revision_document_id": source["revision_document_id"], "step": "resume"},
    )
    assert reply.status_code == 202, reply.text
    advance(ctx, operation_id)
    item = detail_operation(ctx, operation_id)["items"][0]
    assert item["extraction"]["run_id"]


@pytest.mark.parametrize("scenario", ["success", "empty"])
def test_unified_operation_finishes_with_immutable_page_results(operation_context, scenario):
    from powerforge_extraction.controls import RunExecution
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    ctx["settings"].extraction_fake_scenario = scenario
    with pymupdf.open(stream=native_pdf(), filetype="pdf") as page, pymupdf.open() as document:
        document.insert_pdf(page)
        document.insert_pdf(page)
        source = new_source(ctx, "two-pages.pdf", document.tobytes())
    source["pages"] = [1, 2]
    preparation(ctx, source)
    plan, body = reviewed(ctx, [source])
    assert plan["planned_runs"] == 1
    reply = start_operation(ctx, body)
    assert reply.status_code == 202, reply.text
    operation_id = reply.json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    with ctx["factory"]() as session:
        units = session.scalars(
            select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id)
        ).all()
    recognition = [unit for unit in units if unit.stage == "EQUIPMENT_RECOGNITION"]
    attributes = [unit for unit in units if unit.stage == "ATTRIBUTE_EXTRACTION"]
    assert len(recognition) == len(attributes) == 2

    class FixtureProvider:
        def execute(self, request):
            result = FakeExtractionProvider("success").execute(request)
            if scenario == "empty" and request.stage == "EQUIPMENT_RECOGNITION":
                from dataclasses import replace

                payload = json.loads(result.output_text)
                payload["equipment"][0]["registry_type"] = None
                result = replace(result, output_text=json.dumps(payload).encode())
            elif scenario == "empty":
                pytest.fail("An unknown equipment observation must not start Call 2")
            return result

    def execute(unit):
        return execute_unit(
            unit.id,
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: FixtureProvider(),
        )

    assert not execute(attributes[0])
    for unit in recognition + attributes:
        assert execute(unit)
        assert not execute(unit)
    with ctx["factory"]() as session:
        run = session.get(ExtractionRun, run_id)
        assert (run.status, run.pages_processed, run.units_completed) == ("COMPLETED", 2, 4)
        assert session.get(RunExecution, run_id).calls_admitted == (2 if scenario == "empty" else 4)
        results = session.scalars(select(StageResult).where(StageResult.run_id == run_id)).all()
        assert len(results) == 4
        by_unit = {row.work_unit_id: row for row in results}
        for unit in attributes:
            row = by_unit[unit.id]
            parent = by_unit[row.upstream_work_unit_id]
            assert (row.document_page_id, row.page_context_hash, row.upstream_hash) == (
                parent.document_page_id,
                parent.page_context_hash,
                parent.result_hash,
            )
            assert row.outcome == ("NO_ELIGIBLE_ATTRIBUTES" if scenario == "empty" else "RESULT")
            if scenario == "empty":
                (unknown,) = parent.payload["equipment"]
                assert unknown["registry_type"] is None
        tables = set(inspect(session.connection()).get_table_names())
        assert "extraction_stage_results" in tables
        assert "extracted_tables" not in tables
        assert {"extraction_candidates", "extraction_evidence"} <= tables
        with pytest.raises(DBAPIError, match="Stage results are immutable"), session.begin_nested():
            session.execute(
                text("UPDATE extraction_stage_results SET outcome=outcome WHERE work_unit_id=:id"),
                {"id": recognition[0].id},
            )
    root = ctx["operation_base"].removesuffix("/extraction")
    reply = client.get(
        f"{root}/documents/{source['revision_document_id']}/extraction/runs/{run_id}"
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["can_browse_candidates"]
    for attempt in reply.json()["attempts"]:
        assert attempt["result_sha256"]
        assert attempt["provider_calls"] == int(attempt["stage_outcome"] == "RESULT")
        assert attempt["estimated_cost"] is None
    assert {attempt["stage_outcome"] for attempt in reply.json()["attempts"]} == (
        {"RESULT", "NO_ELIGIBLE_ATTRIBUTES"} if scenario == "empty" else {"RESULT"}
    )
    register = client.get(
        ctx["operation_base"] + "/status",
        params={"revision_document_ids": source["revision_document_id"]},
    )
    assert register.status_code == 200, register.text
    (status,) = register.json()["items"]
    assert status["extraction"]["latest_attempt"]["id"] == str(run_id)
    assert status["extraction"]["effective_result"]["id"] == str(run_id)


@pytest.mark.parametrize(
    "cancel,output_version",
    [
        (False, "legacy-v7"),
        (True, "legacy-v7"),
        (False, "compact-assertions-v1"),
        (False, "server-owned-assertions-v1"),
    ],
)
def test_attribute_retry_reuses_recognition_and_cancellation_fences_result(
    operation_context, cancel, output_version
):
    from powerforge_ai.extraction import ErrorCode, ProviderFailure
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    ctx["settings"].extraction_attribute_prompt_variant = "core-catalog-v1"
    ctx["settings"].extraction_attribute_output_version = output_version
    source = new_source(ctx, "retry.pdf")
    preparation(ctx, source)
    _, body = reviewed(ctx, [source])
    reply = start_operation(ctx, body)
    assert reply.status_code == 202, reply.text
    operation_id = reply.json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    fake = FakeExtractionProvider("success")

    def execute(unit_id, provider=fake):
        return execute_unit(
            unit_id, ctx["factory"], ctx["storage"], ctx["settings"], lambda _claim: provider
        )

    with ctx["factory"]() as session:
        units = {
            unit.stage: unit.id
            for unit in session.scalars(
                select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id)
            )
        }
    recognition = units["EQUIPMENT_RECOGNITION"]
    attributes = units["ATTRIBUTE_EXTRACTION"]
    assert execute(recognition)
    document_root = ctx["operation_base"].removesuffix("/extraction")
    browser = (
        f"{document_root}/documents/{source['revision_document_id']}"
        f"/extraction/runs/{run_id}/candidates"
    )
    groups_before = client.get(browser, params={"view": "groups"}).json()
    assert groups_before["total"] == 1
    root = ctx["operation_base"] + f"/operations/{operation_id}"

    first = []

    class AttributeProvider:
        def execute(self, request):
            from powerforge_extraction.provider_body import dispatch_hash

            assert "## Source format" in request.instructions
            assert "equipment_extraction_guidance" in json.loads(request.text)
            first.append(dispatch_hash(request))
            if cancel:
                reply = client.post(root + "/cancel")
                assert reply.status_code == 200 and reply.json()["cancel_requested"]
                return fake.execute(request)
            raise ProviderFailure(ErrorCode.INVALID)

    assert execute(attributes, AttributeProvider()) is not cancel
    with ctx["factory"]() as session:
        assert session.get(StageResult, attributes) is None
        digest = session.get(StageResult, recognition).result_hash
        run = session.get(ExtractionRun, run_id)
        assert run.status == ("CANCELLED" if cancel else "PARTIALLY_COMPLETED")
        assert run.pages_processed == 0
    assert client.get(browser, params={"view": "groups"}).json() == groups_before
    if cancel:
        return
    ctx["settings"].extraction_attribute_prompt_variant = "legacy"
    ctx["settings"].extraction_attribute_output_version = (
        "compact-assertions-v1" if output_version == "legacy-v7" else "legacy-v7"
    )
    (target,) = detail_operation(ctx, operation_id)["items"][0]["extraction"]["retry_targets"]
    target.pop("page_number")
    target.pop("unknown_provider_outcome")
    response = client.post(
        root + "/retry", json={"revision_document_id": source["revision_document_id"], **target}
    )
    assert response.status_code == 202, response.text
    with ctx["factory"]() as session:
        retry = session.scalar(
            select(ExtractionWorkUnit).where(
                ExtractionWorkUnit.run_id == run_id,
                ExtractionWorkUnit.attempt_number == 2,
            )
        )
        assert retry.stage == "ATTRIBUTE_EXTRACTION"
        retry_id = retry.id
    assert execute(retry_id)
    assert client.get(browser, params={"view": "groups"}).json() == groups_before
    with ctx["factory"]() as session:
        result = session.get(StageResult, retry_id)
        assert (result.upstream_work_unit_id, result.upstream_hash) == (recognition, digest)
        assert [result.request_hash] == first
        assert session.get(ExtractionRun, run_id).status == "COMPLETED"


def test_disabled_test_profile_and_insufficient_budget_block_review(operation_context):
    ctx = operation_context
    source = new_source(ctx, "limits.pdf")
    settings = ctx["settings"]
    settings.extraction_use_fake_provider = False
    settings.extraction_external_enabled = False
    disabled, _ = reviewed(ctx, [source])
    assert disabled["review_hash"] is None
    assert disabled["profile"]["enabled"] is False
    settings.extraction_use_fake_provider = True
    settings.extraction_max_calls = 1
    limited, _ = reviewed(ctx, [source])
    assert limited["review_hash"] is None
    assert "admission budget" in limited["items"][0]["error"]


def test_expired_recognition_lease_is_fenced_and_reconciled(operation_context):
    from powerforge_extraction.errors import LeaseLost
    from powerforge_extraction.stage_execution import (
        FakeExtractionProvider,
        StageResult,
        request_for,
    )

    ctx = operation_context
    source = new_source(ctx, "expired-lease.pdf")
    preparation(ctx, source)
    _, body = reviewed(ctx, [source])
    reply = start_operation(ctx, body)
    assert reply.status_code == 202, reply.text
    operation_id = reply.json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    with ctx["factory"].begin() as session:
        units = {
            unit.stage: unit.id
            for unit in session.scalars(
                select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id)
            )
        }
        recognition = units["EQUIPMENT_RECOGNITION"]
        attributes = units["ATTRIBUTE_EXTRACTION"]
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        assert coordinator.claim(attributes) is None
        claim = coordinator.claim(recognition)
        assert claim is not None
    wire, request, _ = request_for(ctx["factory"], ctx["storage"], claim)
    with ctx["factory"].begin() as session:
        ExtractionCoordinator(session, ctx["settings"]).mark_provider_started(
            recognition, claim.token, request
        )
        session.get(ExtractionWorkUnit, recognition).lease_expires_at = now(session) - timedelta(
            seconds=1
        )
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        assert not coordinator.heartbeat(recognition, claim.token)
        assert coordinator.reconcile() == 1
        assert coordinator.claim(attributes) is None
        retry = session.scalar(
            select(ExtractionWorkUnit).where(
                ExtractionWorkUnit.run_id == run_id,
                ExtractionWorkUnit.attempt_number == 2,
            )
        )
        assert retry.stage == "EQUIPMENT_RECOGNITION"
        retry_id = retry.id

    from powerforge_extraction.stage_contracts import parse_response

    response = FakeExtractionProvider("success").execute(request)
    with pytest.raises(LeaseLost), ctx["factory"].begin() as session:
        ExtractionCoordinator(session, ctx["settings"]).complete_stage(
            recognition,
            claim.token,
            wire,
            parse_response(wire, response.output_text),
            response.usage,
        )
    for unit_id in (retry_id, attributes):
        assert execute_unit(
            unit_id,
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: FakeExtractionProvider("success"),
        )
    with ctx["factory"]() as session:
        assert session.get(StageResult, recognition) is None
        assert session.get(StageResult, attributes).upstream_work_unit_id == retry_id
        assert session.get(ExtractionRun, run_id).status == "COMPLETED"


def test_worker_task_dispatches_only_the_ready_stage(operation_context, monkeypatch):
    from extraction_worker import extraction_tasks
    from powerforge_extraction.enqueue import QUEUE, UNIT_TASK

    ctx = operation_context
    source = new_source(ctx, "worker-task.pdf")
    preparation(ctx, source)
    _, body = reviewed(ctx, [source])
    reply = start_operation(ctx, body)
    assert reply.status_code == 202, reply.text
    operation_id = reply.json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    with ctx["factory"]() as session:
        units = {
            unit.stage: unit.id
            for unit in session.scalars(
                select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id)
            )
        }
    recognition = units["EQUIPMENT_RECOGNITION"]
    attributes = units["ATTRIBUTE_EXTRACTION"]
    messages = []

    def send(task, *, args, queue, retry):
        messages.append((task, args, queue, retry))

    monkeypatch.setattr(extraction_tasks, "_engine", lambda: ctx["factory"].kw["bind"])
    monkeypatch.setattr(extraction_tasks, "get_settings", lambda: ctx["settings"])
    monkeypatch.setattr(extraction_tasks, "build_s3_storage", lambda _: ctx["storage"])
    monkeypatch.setattr(extraction_tasks.celery_app, "send_task", send)
    task = extraction_tasks.celery_app.tasks[UNIT_TASK]
    task.run(str(recognition))
    assert messages == [(UNIT_TASK, [str(attributes)], QUEUE, False)]
    task.run(str(attributes))
    task.run(str(recognition))
    assert len(messages) == 1
    with ctx["factory"]() as session:
        assert session.get(ExtractionRun, run_id).status == "COMPLETED"


@pytest.mark.parametrize("failure", ["missing", "same_size_corruption", "transient"])
def test_worker_reverifies_pinned_layout_after_admission(operation_context, monkeypatch, failure):
    from powerforge_ai.extraction import ErrorCode
    from powerforge_extraction.controls import UnitExecution
    from powerforge_extraction.pinned_sources import bound_snapshot
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    _, run_id, units = admitted_page(ctx, new_source(ctx, "damaged-layout.pdf"))
    recognition = units["EQUIPMENT_RECOGNITION"]
    with ctx["factory"]() as session:
        key = bound_snapshot(session, session.get(ExtractionWorkUnit, recognition)).spatial_key
    storage = ctx["storage"]
    original = storage.objects[key]
    if failure != "transient":
        storage.delete(key)
        if failure == "same_size_corruption":
            corrupted = bytes([original.data[0] ^ 1]) + original.data[1:]
            storage.put(key, BytesIO(corrupted), len(corrupted), original.content_type)
    else:
        read = storage.get

        def interrupted(object_key):
            if object_key == key:
                raise TransientStorageError("test interruption")
            return read(object_key)

        monkeypatch.setattr(storage, "get", interrupted)

    assert execute_unit(
        recognition,
        ctx["factory"],
        storage,
        ctx["settings"],
        lambda _: pytest.fail("Unverified source reached the provider"),
    )
    with ctx["factory"]() as session:
        attempt = session.get(ExtractionWorkUnit, recognition)
        assert attempt.status == "FAILED"
        assert session.get(UnitExecution, recognition).provider_started_at is None
        assert session.get(StageResult, recognition) is None
        successor = session.scalar(
            select(ExtractionWorkUnit).where(
                ExtractionWorkUnit.run_id == run_id, ExtractionWorkUnit.attempt_number == 2
            )
        )
        if failure != "transient":
            assert attempt.error_code == ErrorCode.INPUT
            assert successor is None
            assert session.get(ExtractionWorkUnit, units["ATTRIBUTE_EXTRACTION"]).error_code == (
                ErrorCode.DEPENDENCY
            )
            return
        assert attempt.error_code == ErrorCode.SOURCE_UNAVAILABLE
        assert successor is not None
        retry_id = successor.id

    monkeypatch.undo()
    for unit_id in (retry_id, units["ATTRIBUTE_EXTRACTION"]):
        assert execute_unit(
            unit_id,
            ctx["factory"],
            storage,
            ctx["settings"],
            lambda _: FakeExtractionProvider("success"),
        )
    with ctx["factory"]() as session:
        assert session.get(StageResult, units["ATTRIBUTE_EXTRACTION"]).upstream_work_unit_id == (
            retry_id
        )


def test_concurrent_redelivery_cannot_start_another_call(operation_context):
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    _, _, units = admitted_page(ctx, new_source(ctx, "duplicate.pdf"))
    recognition = units["EQUIPMENT_RECOGNITION"]
    entered, release = Event(), Event()

    class HeldProvider:
        def execute(self, request):
            entered.set()
            assert release.wait(10)
            return FakeExtractionProvider("success").execute(request)

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(
            execute_unit,
            recognition,
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: HeldProvider(),
        )
        try:
            assert entered.wait(10)
            assert not execute_unit(
                recognition,
                ctx["factory"],
                ctx["storage"],
                ctx["settings"],
                lambda _: pytest.fail("A duplicate delivery reached the provider"),
            )
        finally:
            release.set()
        assert worker.result(timeout=10)
    with ctx["factory"]() as session:
        assert session.get(StageResult, recognition) is not None


def test_retry_can_exhaust_budget_before_dependent_admission(operation_context):
    from powerforge_ai.extraction import ErrorCode
    from powerforge_extraction.controls import RunExecution, UnitExecution
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    settings = ctx["settings"]
    settings.extraction_max_calls = 2
    _, run_id, units = admitted_page(ctx, new_source(ctx, "retry-budget.pdf"))
    assert execute_unit(
        units["EQUIPMENT_RECOGNITION"],
        ctx["factory"],
        ctx["storage"],
        settings,
        lambda _: FakeExtractionProvider("transient"),
    )
    with ctx["factory"]() as session:
        successor = session.scalar(
            select(ExtractionWorkUnit).where(
                ExtractionWorkUnit.run_id == run_id, ExtractionWorkUnit.attempt_number == 2
            )
        )
        assert successor.stage == "EQUIPMENT_RECOGNITION"
        retry_id = successor.id
    assert execute_unit(
        retry_id,
        ctx["factory"],
        ctx["storage"],
        settings,
        lambda _: FakeExtractionProvider("success"),
    )
    attributes = units["ATTRIBUTE_EXTRACTION"]
    assert not execute_unit(
        attributes,
        ctx["factory"],
        ctx["storage"],
        settings,
        lambda _: pytest.fail("An exhausted budget allowed another provider call"),
    )
    with ctx["factory"]() as session:
        assert session.get(RunExecution, run_id).calls_admitted == 2
        assert session.get(UnitExecution, attributes).provider_started_at is None
        assert session.get(ExtractionWorkUnit, attributes).error_code == ErrorCode.BUDGET
        assert session.get(StageResult, retry_id) is not None
        assert session.get(StageResult, attributes) is None
        run = session.get(ExtractionRun, run_id)
        assert (run.status, run.pages_processed) == ("PARTIALLY_COMPLETED", 0)


@pytest.mark.parametrize("limit", ["calls", "attempts", "none"])
def test_unknown_provider_outcome_requires_acknowledgement_and_keeps_limits(
    operation_context, limit
):
    from powerforge_extraction.controls import RunExecution, UnitExecution
    from powerforge_extraction.operation_models import UNKNOWN_PROVIDER_OUTCOME
    from powerforge_extraction.stage_execution import StageResult, request_for

    ctx = operation_context
    settings = ctx["settings"]
    settings.extraction_max_calls = 2 if limit == "calls" else 6
    settings.extraction_max_attempts = 1 if limit == "attempts" else 3
    settings.extraction_use_fake_provider = False
    settings.extraction_external_enabled = True
    source = new_source(ctx, "unknown-outcome.pdf")
    operation_id, run_id, units = admitted_page(ctx, source)
    recognition = units["EQUIPMENT_RECOGNITION"]
    # Consume one earlier admission, before the provider boundary, to exhaust the
    # two-call budget with the next attempt.
    if limit == "calls":
        with ctx["factory"].begin() as session:
            coordinator = ExtractionCoordinator(session, settings)
            assert coordinator.claim(recognition) is not None
            session.get(ExtractionWorkUnit, recognition).lease_expires_at = now(
                session
            ) - timedelta(seconds=1)
        with ctx["factory"].begin() as session:
            assert ExtractionCoordinator(session, settings).reconcile() == 1
            recognition = session.scalar(
                select(ExtractionWorkUnit.id).where(
                    ExtractionWorkUnit.run_id == run_id, ExtractionWorkUnit.attempt_number == 2
                )
            )
    with ctx["factory"].begin() as session:
        claim = ExtractionCoordinator(session, settings).claim(recognition)
        assert claim is not None
    _, request, _ = request_for(ctx["factory"], ctx["storage"], claim)
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, settings)
        coordinator.mark_provider_started(recognition, claim.token, request)
        session.get(ExtractionWorkUnit, recognition).lease_expires_at = now(session) - timedelta(
            seconds=1
        )
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, settings)
        assert coordinator.reconcile() == 1
        attempt = session.get(ExtractionWorkUnit, recognition)
        assert attempt.error_code == UNKNOWN_PROVIDER_OUTCOME
        assert not coordinator.heartbeat(recognition, claim.token)
        assert session.get(StageResult, recognition) is None
        admitted = session.get(RunExecution, run_id).calls_admitted
        assert admitted == (2 if limit == "calls" else 1)
        assert len(coordinator._units(run_id)) == admitted + 1
        assert session.get(UnitExecution, recognition).provider_started_at is not None
        retry = {
            "revision_document_id": source["revision_document_id"],
            "stage": attempt.stage,
            "page_id": attempt.execution_metadata["source_page_id"],
            "expected_attempt": attempt.attempt_number,
        }
    url = ctx["operation_base"] + f"/operations/{operation_id}/retry"
    rejected = client.post(url, json=retry)
    assert rejected.status_code == 409, rejected.text
    retry["acknowledge_unknown_outcome"] = True
    acknowledged = client.post(url, json=retry)
    if limit != "none":
        assert acknowledged.status_code == 409, acknowledged.text
        assert ("budget exhausted" if limit == "calls" else "attempt limit") in acknowledged.text
    else:
        assert "Provider outcome unknown" in rejected.text
        assert acknowledged.status_code == 202, acknowledged.text
    with ctx["factory"]() as session:
        assert session.get(RunExecution, run_id).calls_admitted == admitted


def test_provider_projection_preserves_pinned_prose_and_schedule_readings(operation_context):
    from powerforge_extraction.stage_execution import FakeExtractionProvider
    from spatial_layout_support import drawn_table

    ctx = operation_context
    source = new_source(ctx, "mixed.pdf", drawn_table(nearby=True))
    preparation(ctx, source)
    _, body = reviewed(ctx, [source])
    reply = start_operation(ctx, body)
    assert reply.status_code == 202, reply.text
    operation_id = reply.json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    with ctx["factory"]() as session:
        units = {
            unit.stage: unit.id
            for unit in session.scalars(
                select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id)
            )
        }

    class CapturingProvider:
        def execute(self, request):
            assert request.image_mime_type == "image/png"
            assert request.image.startswith(b"\x89PNG")
            calls.append(json.loads(request.text))
            return FakeExtractionProvider("success").execute(request)

    calls = []
    for stage in ("EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"):
        assert execute_unit(
            units[stage],
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _claim: CapturingProvider(),
        )
    first, second = calls
    assert {"upstream_hash", "page_context_hash"}.isdisjoint(second)
    assert first["page"]["owner"] == second["page"]["owner"]
    assert "layout_sha256" not in first["page"]
    page = second["page"]
    table_refs = {
        ref
        for table in page["layout"]["tables"]
        for cell in table["cells"]
        for ref in cell["readings"]
    }
    assert table_refs
    readings = {row[0]: row[1] for row in page["readings"]["rows"]}
    assert readings == {item["reading_ref"]: item["text"] for item in first["page"]["readings"]}
    assert table_refs <= readings.keys()
    assert "600" in {readings[ref] for ref in table_refs}
    assert any("Unrelated" in text for ref, text in readings.items() if ref not in table_refs)


@pytest.mark.parametrize(
    "input_version,prompt_variant,output_version",
    [
        (input_version, "core-catalog-v1", output_version)
        for output_version in ("compact-assertions-v1", "server-owned-assertions-v1")
        for input_version in (
            "compact-page-v1",
            "compact-page-v2",
            "readable-hybrid-v1",
            "image-only-v1",
            "readable-text-v1",
        )
    ]
    + [
        ("compact-page-v1", "legacy", "legacy-v7"),
        ("compact-page-v2", "legacy", "legacy-v7"),
        ("readable-hybrid-v1", "legacy", "legacy-v7"),
        ("image-only-v1", "legacy", "legacy-v7"),
        ("readable-text-v1", "legacy", "legacy-v7"),
        ("compact-page-v1", "core-v1", "legacy-v7"),
        ("compact-page-v1", "core-catalog-v1", "legacy-v7"),
        ("readable-text-v1", "core-catalog-v1", "legacy-v7"),
    ],
)
def test_mocked_live_operation_persists_both_stages_and_recoverable_diagnostics(
    operation_context, monkeypatch, input_version, prompt_variant, output_version
):
    from datetime import UTC, datetime, timedelta
    from hashlib import sha256
    from types import SimpleNamespace

    from extraction_worker import read_response_audit
    from extraction_worker.openai_extraction import OpenAIExtractionProvider
    from extraction_worker.read_response_audit import read_audit
    from powerforge_document_processing.storage import InMemoryObjectStorage
    from powerforge_extraction.compact_context import reading_rows
    from powerforge_extraction.compact_output import OUTPUT_VERSION, compact_assertion
    from powerforge_extraction.controls import UnitExecution
    from powerforge_extraction.extraction_profile import stage_request_hash
    from powerforge_extraction.identities import canonical_json, identity_hash
    from powerforge_extraction.models import ExtractionAICall
    from powerforge_extraction.publication_records import Fragment
    from powerforge_extraction.readable_context import reading_blocks
    from powerforge_extraction.response_audit import ResponseAudit
    from powerforge_extraction.stage_execution import StageResult
    from spatial_layout_support import drawn_table

    compact = output_version == OUTPUT_VERSION
    server_owned = output_version != "legacy-v7"
    ctx = operation_context
    ctx["settings"].extraction_use_fake_provider = False
    ctx["settings"].extraction_external_enabled = True
    ctx["settings"].extraction_attribute_input_version = input_version
    ctx["settings"].extraction_attribute_prompt_variant = prompt_variant
    ctx["settings"].extraction_attribute_output_version = output_version
    source = new_source(ctx, "mocked-live-schedule.pdf", drawn_table(nearby=True))
    _, run_id, units = admitted_page(ctx, source)
    calls = []
    bodies = []
    originals = []
    audit_storage = InMemoryObjectStorage()

    class Responses:
        def create(self, **kwargs):
            wire = json.loads(kwargs["input"][0]["content"][0]["text"])
            calls.append(wire)
            bodies.append(
                {k: v for k, v in kwargs.items() if k not in ("timeout", "extra_headers")}
            )
            payload = {}
            if kwargs["text"]["format"]["name"] == "equipment_recognition":
                assert "reasoning" not in kwargs
                payload["equipment"] = [
                    {
                        "local_ref": "local-1",
                        "source_description": "Transformer",
                        "registry_type": "TWO_WINDING_TRANSFORMER",
                        "tag_state": "ABSENT",
                        "tag": None,
                        "qualification": "UNKNOWN",
                        "raw_qualification": None,
                        "evidence": [
                            {
                                "kind": "READING",
                                "role": "EQUIPMENT",
                                "reading_ref": "unavailable-reading",
                                "quote": None,
                            }
                        ],
                    }
                ]
            else:
                assert kwargs["reasoning"] == {"effort": "medium"}
                assert wire["upstream"]["equipment"][0]["local_ref"] == "local-1"
                assert {item["equipment_type"] for item in wire["attribute_catalog"]} == {
                    "TWO_WINDING_TRANSFORMER"
                }
                if prompt_variant == "core-catalog-v1":
                    assert set(wire["equipment_extraction_guidance"]) == {"TWO_WINDING_TRANSFORMER"}
                    assert all(
                        "extraction_guidance" not in item for item in wire["attribute_catalog"]
                    )
                else:
                    assert "equipment_extraction_guidance" not in wire
                    assert all("extraction_guidance" in item for item in wire["attribute_catalog"])
                assert ("## Source format" in kwargs["instructions"]) == (
                    prompt_variant != "legacy"
                )
                content = kwargs["input"][0]["content"]
                assert [x["type"] for x in content] == (
                    ["input_text"]
                    if input_version == "readable-text-v1"
                    else ["input_text", "input_image"]
                )
                if input_version == "image-only-v1":
                    assert "page" not in wire
                    panel_ref = "q1"
                elif "blocks" in wire["page"]:
                    panel_ref = next(
                        r[0]
                        for block in reading_blocks(wire["page"])
                        for line in block["lines"]
                        for r in line
                        if r[1] == "TX-1"
                    )
                else:
                    panel_ref = next(
                        r[0] for r in reading_rows(wire["page"]["readings"]) if r[1] == "TX-1"
                    )
                payload.update(
                    attributes=[],
                    raw_unmapped=[
                        {
                            "display_label": None,
                            "local_ref": "raw-1",
                            "equipment_ref": "foreign-owner",
                            "association": "ASSERTED",
                            "raw_label": "Unsupported",
                            "raw_value": "source reading",
                            "raw_unit": None,
                            "qualifiers": [],
                            "value_form": "SINGLE",
                            "evidence": [
                                {
                                    "kind": "READING",
                                    "role": "VALUE",
                                    "reading_ref": panel_ref,
                                    "quote": None,
                                }
                            ],
                        }
                    ],
                )
                payload["raw_unmapped"] += [
                    dict(payload["raw_unmapped"][0], local_ref="private-ref", raw_value=""),
                    dict(
                        payload["raw_unmapped"][0],
                        local_ref="raw-2",
                        raw_value="second source reading",
                    ),
                ]
                if server_owned:
                    payload["raw_unmapped"].extend(
                        dict(
                            payload["raw_unmapped"][0],
                            local_ref=f"extra-{index}",
                            raw_value=f"additional source reading {index}",
                        )
                        for index in range(15)
                    )
                    payload["raw_unmapped"] = [
                        compact_assertion(item)
                        if compact
                        else {key: value for key, value in item.items() if key != "local_ref"}
                        for item in payload["raw_unmapped"]
                    ]
            original = json.dumps(payload, indent=2)
            originals.append(original.encode())
            return SimpleNamespace(
                status="completed",
                usage=SimpleNamespace(
                    input_tokens=100,
                    output_tokens=30,
                    output_tokens_details=SimpleNamespace(reasoning_tokens=7),
                ),
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[SimpleNamespace(type="output_text", text=original)],
                    )
                ],
            )

    # Changing defaults after admission must not rewrite the pinned Stage 2 resources.
    ctx["settings"].extraction_attribute_prompt_variant = (
        "core-catalog-v1" if prompt_variant == "legacy" else "legacy"
    )
    ctx["settings"].extraction_attribute_reasoning_effort = "low"
    ctx["settings"].extraction_attribute_output_version = (
        "legacy-v7" if server_owned else OUTPUT_VERSION
    )
    ctx["settings"].extraction_attribute_input_version = (
        "compact-page-v1" if input_version == "compact-page-v2" else "compact-page-v2"
    )
    for stage in ("EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"):
        assert execute_unit(
            units[stage],
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda claim: OpenAIExtractionProvider(
                ctx["settings"], claim.profile, SimpleNamespace(responses=Responses())
            ),
            audit_storage=audit_storage,
        )
    assert len(calls) == 2
    assert {"page_context_hash", "upstream_hash"}.isdisjoint(calls[1])
    assert calls[1]["input_version"] == input_version
    with ctx["factory"]() as session:
        recognition = session.get(StageResult, units["EQUIPMENT_RECOGNITION"])
        attribute = session.get(StageResult, units["ATTRIBUTE_EXTRACTION"])
        assert calls[1]["upstream"] == {
            key: value for key, value in recognition.payload.items() if key != "page_context_hash"
        }
        assert attribute.page_context_hash == recognition.page_context_hash
        assert attribute.upstream_hash == recognition.result_hash
        assert {"version", "stage", "page_context_hash"}.isdisjoint(calls[0])
        assert {"source_sha256", "image_sha256", "preparation_sha256", "layout_sha256"}.isdisjoint(
            calls[0]["page"]
        )
        assert recognition.request_hash == identity_hash(bodies[0])
        assert (
            session.get(ExtractionWorkUnit, recognition.work_unit_id).performance["request"][
                "body_bytes"
            ]
            > 0
        )
        expected_digest = (
            stage_request_hash(canonical_json(calls[1]), "medium")
            if input_version.startswith("compact-")
            and prompt_variant == "legacy"
            and not server_owned
            else identity_hash(bodies[1])
        )
        assert attribute.request_hash == expected_digest
        assert attribute.request_hash != identity_hash(calls[1])
        assert recognition.diagnostics[0]["code"] == "UNKNOWN_READING"
        assert any(item["code"] == "INVALID_OWNER_REFERENCE" for item in attribute.diagnostics)
        assert attribute.payload["raw_unmapped"][0]["equipment_ref"] == "foreign-owner"
        fragments = session.scalars(
            select(Fragment).where(Fragment.work_unit_id == units["ATTRIBUTE_EXTRACTION"])
        ).all()
        assert len(fragments) == (16 if server_owned else 2)
        if input_version == "image-only-v1":
            assert all(
                item.localization == "UNRESOLVED" and item.reason_code == "READING_NOT_EXPOSED"
                for item in fragments
            )
        else:
            assert all(
                item.localization == "RESOLVED" and item.quote == "TX-1" for item in fragments
            )
        expected_refs = (
            ["raw-0", *(f"raw-{i}" for i in range(2, 17))] if server_owned else ["raw-1", "raw-2"]
        )
        assert [item["local_ref"] for item in attribute.payload["raw_unmapped"]] == expected_refs
        metrics = session.get(ExtractionWorkUnit, units["ATTRIBUTE_EXTRACTION"]).performance
        assert metrics["provider_call_ms"] <= metrics["attempt_total_ms"]
        assert metrics["input_configuration"] == input_version
        assert metrics["request"]["native_readings"] == (
            0 if input_version == "image-only-v1" else metrics["available_readings"]
        )
        assert metrics["request"]["image_sent"] == (input_version != "readable-text-v1")
        assert metrics["request"]["body_bytes"] > metrics["request"]["page_bytes"]
        assert metrics["reasoning_tokens"] == 7 and metrics["visible_output_tokens"] == 23
        assert metrics["response_status"] == "completed"
        assert "source reading" not in json.dumps(metrics)
        retained = session.get(ResponseAudit, units["ATTRIBUTE_EXTRACTION"])
        delivery = session.get(UnitExecution, units["ATTRIBUTE_EXTRACTION"])
        assert delivery.provider_request_hash == retained.request_hash == attribute.request_hash
        assert retained.attribute_reasoning_effort == "medium"
        assert retained.output_sha256 == sha256(originals[1]).hexdigest()
        expected_counts = {
            "received": 18 if server_owned else 3,
            "accepted": 16 if server_owned else 2,
            "quarantined": 1,
            "overflowed": int(server_owned),
        }
        assert retained.received == expected_counts["received"]
        assert retained.accepted == expected_counts["accepted"]
        assert retained.quarantined == 1
        assert retained.output_version == (output_version if server_owned else None)
        assert retained.overflow_indices == ([17] if server_owned else [])
        assert all(metrics[f"assertions_{key}"] == count for key, count in expected_counts.items())
        assert metrics["output_version"] == output_version
        assert (
            retained.rejections[0]["local_ref_sha256"]
            == sha256(b"raw-1" if server_owned else b"private-ref").hexdigest()
        )
        engine = session.get_bind()
        audit = session.scalars(
            select(ExtractionAICall).where(ExtractionAICall.run_id == run_id)
        ).all()
        assert len(audit) == 2
        assert all(call.input_tokens == 100 and call.output_tokens == 30 for call in audit)
        assert all(call.estimated_cost_usd is None for call in audit)
        with (
            pytest.raises(DBAPIError, match="Dispatched extraction request identity is immutable"),
            session.begin_nested(),
        ):
            delivery.provider_request_hash = "f" * 64
            session.flush()
    assert read_audit(engine, audit_storage, units["ATTRIBUTE_EXTRACTION"]) == originals[1]

    class AfterExpiry(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) + timedelta(days=31)

    monkeypatch.setattr(read_response_audit, "datetime", AfterExpiry)
    with pytest.raises(ValueError, match="expired"):
        read_audit(engine, audit_storage, units["ATTRIBUTE_EXTRACTION"])
    audit_storage.delete(retained.object_key)
    with ctx["factory"]() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM extraction_response_audit_reads WHERE work_unit_id=:id"),
                {"id": units["ATTRIBUTE_EXTRACTION"]},
            )
            == 1
        )
    base = ctx["operation_base"].removesuffix("/extraction")
    run_url = f"{base}/documents/{source['revision_document_id']}/extraction/runs/{run_id}"
    detail = client.get(run_url)
    attempts = detail.json()["attempts"]
    attributes = next(attempt for attempt in attempts if attempt["stage"] == "ATTRIBUTE_EXTRACTION")
    assert attributes["status"] == "COMPLETED" and not attributes["retryable"]
    assert attributes["assertion_validation"] == {
        "state": "PARTIALLY_VALIDATED",
        "counts": expected_counts,
        "rejections": [
            {
                "category": "FIELD_CONSTRAINT",
                "error_type": "string_too_short",
                "path": ["raw_unmapped", 1, "raw" if compact else "raw_value"],
            }
        ],
    }
    assert "private-ref" not in detail.text and "object_key" not in detail.text
    source_counts = client.get(f"{run_url}/sources").json()["items"][0]["assertion_counts"]
    assert source_counts == expected_counts
    assert all(
        attempt["usage"] == {"input_tokens": 100, "output_tokens": 30} for attempt in attempts
    )
    assert all(attempt["latency_ms"] is not None for attempt in attempts)
    assert all(attempt["estimated_cost"] is None for attempt in attempts)


@pytest.mark.parametrize("malformed", ["schema", "tag", "json", "incomplete"])
def test_invalid_response_audit_is_fenced_and_redacted(operation_context, caplog, malformed):
    from types import SimpleNamespace

    from extraction_worker.openai_extraction import OpenAIExtractionProvider
    from powerforge_document_processing.storage import InMemoryObjectStorage
    from powerforge_extraction.models import ExtractionAICall
    from powerforge_extraction.response_audit import ResponseAudit
    from powerforge_extraction.stage_execution import StageResult

    ctx = operation_context
    ctx["settings"].extraction_use_fake_provider = False
    private = "PRIVATE-PANEL-IDENTIFIER"
    source = new_source(ctx, "redaction.pdf")
    _, run_id, units = admitted_page(ctx, source)
    recognition = units["EQUIPMENT_RECOGNITION"]

    audit_storage = InMemoryObjectStorage()
    sent = []

    def create(**kwargs):
        payload = {}
        item = dict(
            local_ref="valid-ref",
            source_description=private,
            registry_type=None,
            tag_state="ABSENT",
            tag=private,
            qualification="UNKNOWN",
            raw_qualification=None,
            evidence=[],
        )
        if malformed == "schema":
            item[private] = private
        payload["equipment"] = [item]
        sent.append(b"{" if malformed == "json" else json.dumps(payload).encode())
        return SimpleNamespace(
            status="incomplete" if malformed == "incomplete" else "completed",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            usage=SimpleNamespace(input_tokens=85, output_tokens=30),
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text=sent[0].decode())],
                )
            ],
        )

    assert execute_unit(
        recognition,
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        lambda claim: OpenAIExtractionProvider(
            ctx["settings"],
            claim.profile,
            SimpleNamespace(responses=SimpleNamespace(create=create)),
        ),
        audit_storage=audit_storage,
    )
    diagnostic = {
        "category": "SCHEMA" if malformed == "schema" else "CROSS_FIELD",
        "error_type": "extra_forbidden" if malformed == "schema" else "invalid_tag_state",
        "path": ["equipment", 0, "*" if malformed == "schema" else "tag"],
    }
    if malformed == "json":
        diagnostic = dict(category="JSON", error_type="json_invalid", path=[])
    if malformed == "incomplete":
        diagnostic = dict(category="INCOMPLETE", error_type="max_output_tokens", path=["status"])
    with ctx["factory"]() as session:
        call = session.scalar(select(ExtractionAICall).where(ExtractionAICall.run_id == run_id))
        assert call.error_code == "INVALID_PROVIDER_RESPONSE"
        assert call.output_tokens == 30
        assert call.validation_diagnostics == [diagnostic]
        audit = session.get(ResponseAudit, recognition)
        assert audit.stage == "EQUIPMENT_RECOGNITION"
        assert audit.fatal_diagnostics == [diagnostic]
        assert audit.object_key.startswith("stage1/")
        assert audit_storage.get(audit.object_key).read() == sent[0]
        assert audit.received is None and audit.accepted is None
        assert session.get(StageResult, recognition) is None
        assert session.get(ExtractionWorkUnit, units["ATTRIBUTE_EXTRACTION"]).error_code == (
            "PREREQUISITE_FAILED"
        )
    base = ctx["operation_base"].removesuffix("/extraction")
    detail = client.get(
        f"{base}/documents/{source['revision_document_id']}/extraction/runs/{run_id}"
    )
    assert detail.status_code == 200
    attempt = next(row for row in detail.json()["attempts"] if row["id"] == str(recognition))
    assert attempt["validation_diagnostics"] == [diagnostic]
    assert private not in detail.text and private not in caplog.text


def test_recognition_rejects_response_bound_to_a_different_work_unit(operation_context):
    from powerforge_extraction.models import ExtractionAICall
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    class ForeignResponseProvider:
        def execute(self, request):
            foreign_request = request.model_copy(update={"work_unit_id": uuid4()})
            return FakeExtractionProvider("success").execute(foreign_request)

    ctx = operation_context
    _, _, units = admitted_page(ctx, new_source(ctx, "recognition-binding.pdf"))
    recognition = units["EQUIPMENT_RECOGNITION"]
    assert execute_unit(
        recognition,
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        lambda _: ForeignResponseProvider(),
    )
    with ctx["factory"]() as session:
        assert session.get(UnitExecution, recognition).provider_request_hash is not None
        assert session.get(StageResult, recognition) is None
        call = session.scalar(
            select(ExtractionAICall).where(ExtractionAICall.work_unit_id == recognition)
        )
        assert call.validation_diagnostics[0]["error_type"] == "request_binding_mismatch"
        assert session.get(ExtractionWorkUnit, units["ATTRIBUTE_EXTRACTION"]).error_code == (
            "PREREQUISITE_FAILED"
        )


def test_publication_browser_scoped_evidence_and_raw_values(operation_context):
    from powerforge_ai.extraction import AttributeOutput, ExecutionUsage, RecognitionOutput
    from powerforge_extraction.publication_records import Candidate, Fragment
    from spatial_layout_support import drawn_table

    ctx = operation_context
    source = new_source(
        ctx,
        "publication.pdf",
        drawn_table(
            rows=[("Equipment", "Secondary (KV)"), ("TX-1", "600"), ("TX-2", "600")], nearby=True
        ),
    )
    _, run_id, units = admitted_page(ctx, source)
    root = ctx["operation_base"].removesuffix("/extraction")
    path = f"{root}/documents/{source['revision_document_id']}/extraction"
    candidate_url = f"{path}/runs/{run_id}/candidates"

    class SourceProvider:
        def execute(self, request):
            wire = json.loads(request.text)
            readings = wire["page"]["readings"]
            if request.stage == "ATTRIBUTE_EXTRACTION":
                readings = [
                    dict(zip(readings["columns"], row, strict=True)) for row in readings["rows"]
                ]
            label = next(item["reading_ref"] for item in readings if item["text"] == "TX-1")
            header = next(item["reading_ref"] for item in readings if item["text"] == "(KV)")
            value = next(item["reading_ref"] for item in readings if item["text"] == "600")
            response = {}
            if request.stage == "EQUIPMENT_RECOGNITION":
                response["equipment"] = [
                    dict(
                        local_ref=f"e{index}",
                        source_description="Straße transformer",
                        registry_type="TWO_WINDING_TRANSFORMER",
                        tag_state="PRESENT",
                        tag="TX-1",
                        qualification="INSTALLED",
                        raw_qualification=None,
                        evidence=[
                            dict(kind="READING", role="TAG", reading_ref=label, quote="TX-1")
                        ],
                    )
                    for index in range(2)
                ]
            else:
                attribute = dict(
                    origin="EXTRACTED",
                    local_ref="rating",
                    attribute_key="secondary_voltage",
                    proposed_value="600",
                    alternate_representations=[],
                    proposed_unit="kV",
                    equipment_ref="e0",
                    association="UNCERTAIN",
                    raw_label="Secondary",
                    raw_value="600",
                    raw_unit="KV",
                    qualifiers=[],
                    value_form="SINGLE",
                    evidence=[
                        dict(kind="READING", role="HEADER", reading_ref=header, quote=None),
                        dict(kind="READING", role="VALUE", reading_ref=value, quote=None),
                        dict(kind="QUOTE", role="VALUE", quote="600"),
                    ],
                )
                raw = {
                    "display_label": None,
                    **{
                        k: v
                        for k, v in attribute.items()
                        if k
                        not in {
                            "attribute_key",
                            "proposed_value",
                            "proposed_unit",
                            "origin",
                            "alternate_representations",
                        }
                    },
                }
                inference = dict(
                    origin="INFERRED",
                    local_ref="inferred-rating",
                    equipment_ref="e0",
                    association="UNCERTAIN",
                    attribute_key="secondary_voltage",
                    proposed_value="0.7",
                    proposed_unit="kV",
                    inference_explanation="Test fixture for a competing voltage proposal.",
                    inference_basis="ENGINEERING_KNOWLEDGE",
                    source_expression="Product configuration note",
                    evidence=[],
                )
                response.update(
                    attributes=[
                        attribute,
                        dict(
                            attribute,
                            local_ref="mismatched-rating",
                            raw_value="601",
                            proposed_value="601",
                            evidence=attribute["evidence"][:2],
                        ),
                        dict(
                            attribute,
                            local_ref="repeated-rating",
                            qualifiers=["An adjacent annotation"],
                            value_form="QUALIFIED",
                        ),
                        inference,
                        dict(
                            inference,
                            local_ref="inferred-with-citations",
                            evidence=[
                                dict(
                                    kind="READING", role="CONTEXT", reading_ref=header, quote=None
                                ),
                                dict(kind="READING", role="VALUE", reading_ref=value, quote=None),
                            ],
                        ),
                    ],
                    raw_unmapped=[
                        dict(
                            raw,
                            local_ref="owned-raw",
                            raw_label="Noise_100%",
                            raw_value="50",
                            display_label="Noise Level (Unspecified)",
                        ),
                        dict(
                            raw, local_ref="unowned-raw", equipment_ref="foreign", raw_label="Other"
                        ),
                    ],
                )
            if request.stage == "ATTRIBUTE_EXTRACTION":
                return AttributeOutput(json.dumps(response).encode(), ExecutionUsage(), request)
            return RecognitionOutput(json.dumps(response).encode(), ExecutionUsage(), request)

    def browse(**params):
        response = client.get(candidate_url, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    def run(stage):
        assert execute_unit(
            units[stage],
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: SourceProvider(),
        )

    run("EQUIPMENT_RECOGNITION")
    first_groups = browse(view="groups")
    assert first_groups["total"] == 2
    assert len({g["group_id"] for g in first_groups["items"]}) == 2
    assert {g["tag"] for g in first_groups["items"]} == {"TX-1"}
    run("ATTRIBUTE_EXTRACTION")

    all_groups = browse(view="groups")
    assert all_groups["total"] == 3
    assert [g["group_id"] for g in all_groups["items"]] == [
        *(g["group_id"] for g in first_groups["items"]),
        "unassigned",
    ]
    first_page = browse(view="groups", limit=2)
    last_page = browse(view="groups", limit=2, cursor=first_page["next_cursor"])
    assert [group["group_id"] for group in last_page["items"]] == ["unassigned"]
    assert browse(view="groups", limit=2, cursor=last_page["previous_cursor"]) == first_page
    assert (
        client.get(
            candidate_url,
            params={
                "view": "groups",
                "search": "different",
                "cursor": first_page["next_cursor"],
            },
        ).status_code
        == 404
    )
    assert browse(view="groups", search="  STRASSE ", kind="ATTRIBUTE")["total"] == 1
    assert browse(view="groups", search="%")["total"] == 1
    (match,) = browse(view="groups", search="noise_100%", mapping_status="UNMAPPED")["items"]
    group = match["group_id"]
    assert match["matching_candidate_count"] == 1
    members = browse(view="members", group_id=group, search="Noise_100%")
    assert members["group"] == match
    assert members["items"][0]["kind"] == "ATTRIBUTE"
    assert members["items"][0]["equipment_id"] == group and members["items"][0]["raw_unmapped"]
    assert members["items"][0]["source_display_label"] == "Noise Level (Unspecified)"
    assert browse(view="groups", search="Noise Level (Unspecified)")["items"] == [match]
    assert (
        browse(view="members", group_id=group, search="missing")["group"][
            "matching_candidate_count"
        ]
        == 0
    )
    assert browse(view="members", group_id=group, page_id=str(uuid4()))["items"] == []

    first_member = browse(view="members", group_id=group, limit=1)
    second_member = browse(
        view="members", group_id=group, limit=1, cursor=first_member["next_cursor"]
    )
    assert second_member["items"][0]["id"] != first_member["items"][0]["id"]
    assert (
        browse(view="members", group_id=group, limit=1, cursor=second_member["previous_cursor"])[
            "items"
        ]
        == first_member["items"]
    )
    ratings = browse(equipment_id=group, kind="ATTRIBUTE", mapping_status="MAPPED")["items"]
    rating, mismatch = sorted(
        (item for item in ratings if item["origin"] == "EXTRACTED"),
        key=lambda candidate: candidate["raw_value"],
    )
    inferred, contextual = sorted(
        (item for item in ratings if item["origin"] == "INFERRED"),
        key=lambda candidate: len(candidate["evidence_ids"]),
    )
    assert inferred["attribute_display_name"] == rating["attribute_display_name"]
    assert inferred["attribute_display_name"] == "Secondary Voltage (kV)"
    assert inferred["proposed_value"] == "0.7" and inferred["proposed_unit"] == "kV"
    assert inferred["inference_basis"] == "ENGINEERING_KNOWLEDGE"
    assert inferred["inference_explanation"]
    assert inferred["source_expression"] == "Product configuration note"
    assert inferred["raw_label"] is None and inferred["raw_value"] is None
    assert inferred["normalized"] == {"type": "NUMBER", "value": "0.7", "unit": "kV"}
    assert inferred["value_source_support"] == "UNVERIFIED" and inferred["evidence_ids"] == []
    assert inferred["conflict"] and rating["conflict"]
    repeated = browse(equipment_id=group, search="600", mapping_status="UNMAPPED")["items"]
    (repeat,) = [item for item in repeated if item["redundant_with_id"]]
    assert repeat["redundant_with_id"] == rating["id"]
    assert repeat["raw_value"] == "600" and repeat["qualifiers"] == ["An adjacent annotation"]
    identity = browse(view="members", group_id=group, limit=1)["identification"]
    assert identity["kind"] == "EQUIPMENT" and identity["tag"] == "TX-1"
    assert identity["display_name"] == "TX-1"
    summary = next(item for item in all_groups["items"] if item["group_id"] == group)
    assert summary["matching_attribute_count"] == 6
    assert summary["matching_identification_count"] == 1
    context_resolved, context_unresolved = [
        client.get(f"{path}/evidence/{evidence_id}").json()
        for evidence_id in contextual["evidence_ids"]
    ]
    assert context_resolved["localization"] == "RESOLVED"
    assert context_resolved["role"] == "CONTEXT"
    assert context_resolved["candidate_value_source_support"] == "UNVERIFIED"
    assert context_unresolved["reason_code"] == "INFERRED_VALUE_CITATION"
    assert (
        context_unresolved["localization"] == "UNRESOLVED" and "regions" not in context_unresolved
    )
    assert rating["association"] == "UNCERTAIN"
    assert rating["raw_unit"] == "KV" and rating["proposed_unit"] == "kV"
    assert rating["raw_value"] == "600"
    assert rating["normalized"] == {"type": "NUMBER", "value": "600", "unit": "kV"}
    assert rating["value_source_support"] == "TEXT_MATCH"
    assert mismatch["value_source_support"] == "TEXT_MISMATCH"
    assert mismatch["raw_value"] == "601"
    assert mismatch["association"] == "UNCERTAIN"
    assert mismatch["normalized"] == {"type": "NUMBER", "value": "601", "unit": "kV"}
    mismatch_fragment = client.get(f"{path}/evidence/{mismatch['evidence_ids'][1]}")
    assert mismatch_fragment.status_code == 200, mismatch_fragment.text
    assert mismatch_fragment.json()["quote"] == "600"
    assert mismatch_fragment.json()["localization"] == "RESOLVED"
    assert mismatch_fragment.json()["candidate_value_source_support"] == "TEXT_MISMATCH"
    assert browse(view="members", group_id=group, candidate_id=rating["id"])["items"] == [rating]
    assert (
        client.get(
            candidate_url,
            params={
                "view": "members",
                "group_id": "unassigned",
                "candidate_id": rating["id"],
            },
        ).status_code
        == 404
    )
    (unassigned,) = browse(view="members", group_id="unassigned")["items"]
    assert unassigned["equipment_id"] is None and unassigned["association"] == "UNASSIGNED"
    assert unassigned["value_source_support"] == "TEXT_MATCH"
    assert not browse(view="groups", equipment_type="LV_BREAKER")["items"]

    pages = client.get(f"{path}/runs/{run_id}/sources").json()["items"]
    assert pages[0]["page_id"] == rating["page_id"] and pages[0]["page_context_hash"]
    stored = []
    for evidence_id in rating["evidence_ids"]:
        reply = client.get(f"{path}/evidence/{evidence_id}")
        assert reply.status_code == 200, reply.text
        assert "storage_key" not in reply.text
        stored.append(reply.json())
    assert [f["localization"] for f in stored] == ["RESOLVED", "RESOLVED", "UNRESOLVED"]
    assert {f["candidate_value_source_support"] for f in stored} == {"TEXT_MATCH"}
    assert stored[0]["role"] == "HEADER" and stored[1]["role"] == "VALUE"
    assert stored[0]["regions"] != stored[1]["regions"]
    assert stored[2]["reason_code"] == "AMBIGUOUS_QUOTE" and "regions" not in stored[2]
    assert stored[1]["quote"] == "600" and stored[1]["text_artifact"]["url"]
    assert stored[1]["page_image_id"] == pages[0]["page_image_id"]
    foreign = new_source(ctx, "foreign.pdf")
    foreign_path = f"{root}/documents/{foreign['revision_document_id']}/extraction"
    assert client.get(f"{foreign_path}/evidence/{rating['evidence_ids'][0]}").status_code == 404
    assert client.get(f"{foreign_path}/runs/{run_id}/candidates").status_code == 404
    assert (
        client.get(
            candidate_url,
            params={
                "view": "members",
                "group_id": str(uuid4()),
            },
        ).status_code
        == 404
    )
    assert client.get(candidate_url, params={"cursor": "%%%"}).status_code == 404
    _, new_body = reviewed(ctx, [source], mode="reextract")
    newer_operation = start_operation(ctx, new_body)
    assert newer_operation.status_code == 202, newer_operation.text
    newer_operation_id = newer_operation.json()["id"]
    advance(ctx, newer_operation_id)
    newer_run = detail_operation(ctx, newer_operation_id)["items"][0]["extraction"]["run_id"]
    history = client.get(path + "/runs", params={"limit": 1}).json()
    assert history["items"][0]["id"] == newer_run and history["total"] == 2
    older = client.get(path + "/runs", params={"limit": 1, "cursor": history["next_cursor"]}).json()
    assert older["items"][0]["id"] == str(run_id)
    assert (
        client.get(path + "/runs", params={"limit": 1, "cursor": older["previous_cursor"]}).json()
        == history
    )
    assert (
        client.get(foreign_path + "/runs", params={"cursor": history["next_cursor"]}).status_code
        == 404
    )
    assert (
        client.get(
            f"{path}/runs/{newer_run}/candidates",
            params={
                "view": "groups",
                "cursor": first_page["next_cursor"],
            },
        ).status_code
        == 404
    )
    with ctx["factory"]() as session:
        artifact = session.get(PageArtifact, UUID(stored[1]["page_image_id"]))
        key = artifact.storage_key
    ctx["storage"].delete(key)
    unavailable = client.get(f"{path}/evidence/{rating['evidence_ids'][1]}")
    assert unavailable.status_code == 502 and key not in unavailable.text

    with ctx["factory"]() as session:
        canonical_count = session.scalar(
            text("SELECT count(*) FROM equipment WHERE project_id=:id"), {"id": ctx["project_id"]}
        )
        assert canonical_count == 0
        row = session.get(Candidate, UUID(unassigned["id"]))
        assert row.claimed_owner_ref == "foreign" and row.equipment_id is None
        with pytest.raises(DBAPIError, match="Published evidence is immutable"):
            session.delete(session.get(Fragment, UUID(rating["evidence_ids"][0])))
            session.flush()


@pytest.mark.parametrize(
    "breakage",
    [
        "missing-candidate",
        "missing-fragment",
        "foreign-owner",
        "boolean-as-text",
        "integer-as-text",
        "wrong-alternates",
        "missing-audit",
        "old-contract",
        "foreign-response",
        "wrong-dispatch-hash",
        "wrong-upstream-binding",
        "wrong-audit-effort",
        "wrong-audit-output-version",
    ],
)
def test_stage_publication_rolls_back_atomically(operation_context, monkeypatch, breakage):
    from powerforge_ai.extraction import AttributeOutput, ExecutionUsage, ValidationIssue
    from powerforge_document_processing.storage import InMemoryObjectStorage
    from powerforge_extraction.models import ExtractionAICall
    from powerforge_extraction.publication_records import Candidate, Fragment
    from powerforge_extraction.response_audit import ResponseAudit
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    if breakage in {"missing-audit", "wrong-audit-effort", "wrong-audit-output-version"}:
        ctx["settings"].extraction_use_fake_provider = False
        ctx["settings"].extraction_external_enabled = True
    if breakage == "wrong-audit-output-version":
        ctx["settings"].extraction_attribute_output_version = "compact-assertions-v1"
    audit_storage = InMemoryObjectStorage()
    with pymupdf.open(stream=native_pdf(), filetype="pdf") as page, pymupdf.open() as document:
        document.insert_pdf(page)
        document.insert_pdf(page)
        source = new_source(ctx, "atomic.pdf", document.tobytes())
    source["pages"] = [1, 2]
    preparation(ctx, source)
    _, body = reviewed(ctx, [source])
    operation_id = start_operation(ctx, body).json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    with ctx["factory"]() as session:
        rows = session.scalars(
            select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id)
        ).all()
        units = {(row.stage, row.page_numbers[0]): row.id for row in rows}

    previous_output = None

    class Provider:
        def execute(self, request):
            nonlocal previous_output
            if request.stage == "EQUIPMENT_RECOGNITION":
                return FakeExtractionProvider("success").execute(request)
            if breakage == "foreign-response" and previous_output is not None:
                return previous_output
            payload = {}
            payload.update(
                raw_unmapped=[],
                attributes=[
                    dict(
                        origin="EXTRACTED",
                        local_ref="a1",
                        attribute_key="primary_connection",
                        proposed_value="WYE",
                        alternate_representations=[],
                        proposed_unit=None,
                        equipment_ref="equipment-1",
                        association="ASSERTED",
                        raw_label="Connection",
                        raw_value="Star",
                        raw_unit=None,
                        qualifiers=[],
                        value_form="SINGLE",
                        evidence=[],
                    )
                ],
            )
            if breakage in {"boolean-as-text", "integer-as-text"}:
                payload["attributes"][0].update(
                    proposed_value=(True if breakage == "boolean-as-text" else 7),
                )
            if breakage == "wrong-alternates":
                payload["attributes"][0].update(
                    raw_value="20 in (508 mm)",
                    raw_unit="in",
                    proposed_unit="in",
                    proposed_value="20",
                    value_form="EQUIVALENT_UNITS",
                    alternate_representations=[{"value": "508", "unit": "mm"}],
                )
            payload["attributes"].append(
                dict(payload["attributes"][0], local_ref="invalid", raw_value="")
            )
            if breakage == "wrong-audit-output-version":
                from powerforge_extraction.compact_output import compact_assertion

                payload["attributes"] = [compact_assertion(item) for item in payload["attributes"]]
            previous_output = AttributeOutput(
                json.dumps(payload).encode(), ExecutionUsage(), request
            )
            return previous_output

    def execute(stage, page):
        wait_for_availability(ctx, units[(stage, page)])
        return execute_unit(
            units[(stage, page)],
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: Provider(),
            audit_storage=audit_storage,
        )

    assert execute("EQUIPMENT_RECOGNITION", 1)
    assert execute("EQUIPMENT_RECOGNITION", 2)
    assert execute("ATTRIBUTE_EXTRACTION", 2)
    from powerforge_extraction import publication_records

    real_publish = publication_records.publish

    def broken_publish(session, stage, image_id, observations):
        from types import SimpleNamespace

        if breakage == "missing-candidate":
            return
        if breakage == "missing-fragment":
            observations[0].evidence = []
        if breakage == "boolean-as-text":
            observations[0].fields["proposed_value"] = "true"
        if breakage == "integer-as-text":
            observations[0].fields["proposed_value"] = "7"
        if breakage == "wrong-alternates":
            observations[0].fields["alternate_representations"] = [{"value": "500", "unit": "mm"}]
        if breakage == "foreign-owner":
            stage = SimpleNamespace(
                work_unit_id=stage.work_unit_id,
                run_id=stage.run_id,
                document_page_id=stage.document_page_id,
                upstream_work_unit_id=units[("EQUIPMENT_RECOGNITION", 2)],
                stage=stage.stage,
                payload=stage.payload,
            )
        real_publish(session, stage, image_id, observations)

    monkeypatch.setattr(publication_records, "publish", broken_publish)
    if breakage == "missing-audit":
        from powerforge_extraction import response_audit

        real_record = response_audit.record_audit
        completion, failure = [], []

        def omit_during_completion(session, unit, *args):
            if completion:
                failure.append(unit.id)
                return real_record(session, unit, *args)
            completion.append(unit.id)

        monkeypatch.setattr(response_audit, "record_audit", omit_during_completion)
    if breakage == "old-contract":
        from powerforge_extraction import stage_execution

        real_store = stage_execution.store_result

        def store_old_version(session, unit, snapshot, wire, result, observations, request):
            old = {"version": "phase-6r-attributes-v4"}
            return real_store(
                session,
                unit,
                snapshot,
                wire.model_copy(update=old),
                result.model_copy(update={**old, "attributes": ()}),
                [],
            )

        monkeypatch.setattr(stage_execution, "store_result", store_old_version)
    if breakage in {"wrong-dispatch-hash", "wrong-upstream-binding"}:
        from powerforge_extraction import stage_execution

        real_store = stage_execution.store_result
        real_projection = stage_execution.provider_input

        def store_wrong_binding(session, unit, snapshot, wire, result, observations, request):
            if breakage == "wrong-upstream-binding":
                result = result.model_copy(update={"upstream_hash": "f" * 64})
            else:
                monkeypatch.setattr(
                    stage_execution,
                    "provider_input",
                    lambda value: {**real_projection(value), "foreign_input": True},
                )
            try:
                return real_store(session, unit, snapshot, wire, result, observations, request)
            finally:
                monkeypatch.setattr(stage_execution, "provider_input", real_projection)

        monkeypatch.setattr(stage_execution, "store_result", store_wrong_binding)
    from sqlalchemy import event

    errors = []

    def observe_database_rejection(context):
        diagnostics = getattr(context.original_exception, "diag", None)
        if diagnostics is not None:
            errors.append(diagnostics.message_primary)

    engine = ctx["factory"].kw["bind"]

    if breakage in {"wrong-audit-effort", "wrong-audit-output-version"}:
        # The dispatch digest remains valid while another pinned identity is tampered with.
        from powerforge_extraction import response_audit

        real_add = response_audit.ResponseAudit
        seen = []

        audit_field = (
            "attribute_reasoning_effort" if breakage == "wrong-audit-effort" else "output_version"
        )

        def build_audit(**metadata):
            if not seen:
                metadata[audit_field] = "low" if breakage == "wrong-audit-effort" else None
            seen.append(metadata[audit_field])
            return real_add(**metadata)

        monkeypatch.setattr(response_audit, "ResponseAudit", build_audit)

    event.listen(engine, "handle_error", observe_database_rejection)
    try:
        assert execute("ATTRIBUTE_EXTRACTION", 1)
    finally:
        event.remove(engine, "handle_error", observe_database_rejection)
    if breakage in {"boolean-as-text", "integer-as-text", "wrong-alternates"}:
        assert errors == ["Candidate must preserve the attribute origin and proposal"]
    if breakage == "old-contract":
        assert errors == ["Stage 2 result must use the pinned typed contract"]
    if breakage == "wrong-dispatch-hash":
        assert errors == ["Stage 2 result differs from its dispatched request"]
    if breakage == "wrong-audit-effort":
        assert errors == ["Response audit differs from its pinned reasoning effort"]
        assert seen == ["low", "medium"]
    if breakage == "wrong-audit-output-version":
        assert errors == ["Response audit differs from its pinned output version"]
        assert seen == [None, "compact-assertions-v1"]
    attempt_id = units[("ATTRIBUTE_EXTRACTION", 1)]
    if breakage == "missing-audit":
        # Commit rejected the result. The fenced failure transaction retained
        # the response audit on its own, just as for other publication failures.
        assert completion == failure == [attempt_id]
        assert errors == ["Stage 2 publication requires its retained response audit"]
    with ctx["factory"]() as session:
        assert session.get(StageResult, attempt_id) is None
        retained = session.get(ResponseAudit, attempt_id)
        if breakage == "foreign-response":
            assert retained is None
            call = session.scalar(
                select(ExtractionAICall).where(ExtractionAICall.work_unit_id == attempt_id)
            )
            assert call.validation_diagnostics == [
                ValidationIssue(
                    category="ENVELOPE", error_type="request_binding_mismatch"
                ).model_dump(mode="json")
            ]
        else:
            assert retained.accepted == retained.quarantined == 1
            assert retained.rejections[0]["index"] == 1
        assert (
            session.scalar(select(Candidate.id).where(Candidate.work_unit_id == attempt_id)) is None
        )
        assert (
            session.scalar(select(Fragment.id).where(Fragment.work_unit_id == attempt_id)) is None
        )
        failed = session.get(ExtractionWorkUnit, attempt_id)
        assert failed.status == "FAILED"
        assert failed.performance["failure_stage"] == (
            "admission" if breakage == "foreign-response" else "db_publish"
        )
        assert failed.performance["attempt_total_ms"] >= failed.performance["admission_ms"]
        if breakage == "wrong-upstream-binding":
            assert session.get(ExtractionWorkUnit, attempt_id).error_code == "INVALID_SOURCE_INPUT"
        assert session.get(ExtractionRun, run_id).status == "PARTIALLY_COMPLETED"
        assert session.get(ExtractionRun, run_id).pages_processed == 1
        assert session.get(StageResult, units[("EQUIPMENT_RECOGNITION", 1)]) is not None


def test_equipment_names_are_stable_across_pages_filters_and_pagination(operation_context):
    from powerforge_engineering_model.registry import get_equipment_definition
    from powerforge_extraction.stage_execution import FakeExtractionProvider

    ctx = operation_context
    with pymupdf.open(stream=native_pdf(), filetype="pdf") as page, pymupdf.open() as document:
        document.insert_pdf(page)
        document.insert_pdf(page)
        source = new_source(ctx, "two-page-names.pdf", document.tobytes())
    source["pages"] = [1, 2]
    preparation(ctx, source)
    _, body = reviewed(ctx, [source])
    operation_id = start_operation(ctx, body).json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    with ctx["factory"]() as session:
        units = session.scalars(
            select(ExtractionWorkUnit)
            .where(
                ExtractionWorkUnit.run_id == run_id,
                ExtractionWorkUnit.stage == "EQUIPMENT_RECOGNITION",
            )
            .order_by(ExtractionWorkUnit.page_numbers)
        ).all()
    for unit in units:
        assert execute_unit(
            unit.id,
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: FakeExtractionProvider("success"),
        )
    path = ctx["operation_base"].removesuffix("/extraction")
    url = f"{path}/documents/{source['revision_document_id']}/extraction/runs/{run_id}/candidates"

    def browse(**params):
        response = client.get(url, params={"view": "groups", **params})
        assert response.status_code == 200, response.text
        return response.json()

    before = browse()
    display_type = get_equipment_definition("TWO_WINDING_TRANSFORMER").display_name
    assert [item["label"] for item in before["items"]] == [f"{display_type} 1", f"{display_type} 2"]
    assert all(item["matching_attribute_count"] == 0 for item in before["items"])
    assert all(item["matching_identification_count"] == 1 for item in before["items"])
    first = browse(limit=1)
    second = browse(limit=1, cursor=first["next_cursor"])
    assert second["items"] == [before["items"][1]]
    assert browse(search=f"{display_type} 2")["items"] == second["items"]
    assert (
        browse(page_id=str(units[1].execution_metadata["source_page_id"]))["items"]
        == second["items"]
    )
    assert browse(search="Synthetic equipment", mapping_status="MAPPED")["items"] == before["items"]
    group_id = second["items"][0]["group_id"]
    members = client.get(url, params={"view": "members", "group_id": group_id, "kind": "ATTRIBUTE"})
    assert members.status_code == 200
    assert members.json()["items"] == []
    assert members.json()["identification"]["display_name"] == f"{display_type} 2"


@pytest.mark.parametrize(
    "case", ["wrong-upstream", "all-rejected", "storage-failure", "lease-loss"]
)
def test_attribute_audit_failure_boundaries(operation_context, case):
    from powerforge_ai.extraction import AttributeOutput, ExecutionUsage
    from powerforge_document_processing.storage import InMemoryObjectStorage
    from powerforge_document_processing.storage.base import StorageError
    from powerforge_extraction.publication_records import Candidate
    from powerforge_extraction.response_audit import ResponseAudit
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    source = new_source(ctx, "attribute-audit-boundaries.pdf")
    _, run_id, units = admitted_page(ctx, source)
    attr_id = units["ATTRIBUTE_EXTRACTION"]
    expected_error = (
        "RESPONSE_AUDIT_UNAVAILABLE" if case == "storage-failure" else "INVALID_PROVIDER_RESPONSE"
    )

    class AuditStorage(InMemoryObjectStorage):
        def put(self, key, fileobj, size, content_type):
            if case == "storage-failure":
                raise StorageError("test failure")
            super().put(key, fileobj, size, content_type)
            if case == "lease-loss":
                with ctx["factory"].begin() as session:
                    ExtractionCoordinator(session, ctx["settings"]).cancel(run_id)

    audit_storage = AuditStorage()
    calls = []

    class Provider:
        def execute(self, request):
            calls.append(request.stage)
            if request.stage == "EQUIPMENT_RECOGNITION":
                return FakeExtractionProvider("success").execute(request)
            payload = {}
            if case == "wrong-upstream":
                payload["upstream_hash"] = "f" * 64
            payload.update(
                attributes=[],
                raw_unmapped=[
                    dict(
                        local_ref="raw-1",
                        equipment_ref=None,
                        association="UNASSIGNED",
                        raw_label="Original source label",
                        display_label=None,
                        raw_value="",
                        raw_unit=None,
                        qualifiers=[],
                        value_form="SINGLE",
                        evidence=[],
                    )
                ],
            )
            return AttributeOutput(json.dumps(payload).encode(), ExecutionUsage(), request)

    assert execute_unit(
        units["EQUIPMENT_RECOGNITION"],
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        lambda _: Provider(),
        audit_storage=audit_storage,
    )
    finished = execute_unit(
        attr_id,
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        lambda _: Provider(),
        audit_storage=audit_storage,
    )
    assert finished is (case != "lease-loss")
    assert calls == ["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"]
    with ctx["factory"]() as session:
        assert session.get(StageResult, attr_id) is None
        assert session.scalar(select(Candidate.id).where(Candidate.work_unit_id == attr_id)) is None
        attempt = session.get(ExtractionWorkUnit, attr_id)
        audit = session.get(ResponseAudit, attr_id)
        if case == "lease-loss":
            assert attempt.status == "CANCELLED" and audit is None
        else:
            assert attempt.status == "FAILED" and attempt.error_code == expected_error
            if case == "storage-failure":
                assert audit is None
            else:
                if case == "all-rejected":
                    assert (audit.received, audit.accepted) == (1, 0)
                else:
                    assert audit.received is None and audit.accepted is None
                assert audit.quarantined == (case == "all-rejected")


def test_typed_proposals_survive_publication_read_and_search(operation_context):
    from powerforge_ai.extraction import AttributeOutput, ExecutionUsage, RecognitionOutput
    from powerforge_extraction.publication_records import Candidate
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult
    from spatial_layout_support import drawn_table

    ctx = operation_context
    width = "20 in (508.000 mm)"
    alternate = {"value": "508.000", "unit": "mm"}
    source = new_source(ctx, "typed-proposals.pdf", drawn_table(rows=[("Width", width)]))
    _, run_id, units = admitted_page(ctx, source)
    cases = (
        ("bus", "enclosure_width", width, "20", "in", "20"),
        ("breaker", "pole_count", "37 Pole", 37, None, "37"),
        ("breaker", "normally_closed", "No", False, None, "false"),
        ("breaker", "model", "Model: UNIT-MODEL-98", "UNIT-MODEL-98", None, "unit-model-98"),
        ("transformer", "primary_connection", "Star", "WYE", None, "wye"),
        ("breaker", "manufacturer", "Unknown", None, None, None),
    )

    class Provider:
        def execute(self, request):
            if request.stage == "EQUIPMENT_RECOGNITION":
                response = FakeExtractionProvider("success").execute(request)
                payload = json.loads(response.output_text)
                prototype = payload["equipment"][0]
                payload["equipment"] = [
                    {**prototype, "local_ref": ref, "registry_type": kind}
                    for ref, kind in (
                        ("bus", "BUS"),
                        ("breaker", "LV_BREAKER"),
                        ("transformer", "TWO_WINDING_TRANSFORMER"),
                    )
                ]
            else:
                payload = {}
                payload["attributes"] = [
                    dict(
                        origin="EXTRACTED",
                        local_ref=key,
                        equipment_ref=owner,
                        attribute_key=key,
                        association="ASSERTED",
                        raw_label=None,
                        raw_value=raw,
                        raw_unit=unit,
                        proposed_value=proposal,
                        proposed_unit=unit,
                        qualifiers=[],
                        value_form="EQUIVALENT_UNITS" if unit else "SINGLE",
                        alternate_representations=[alternate] if unit else [],
                        evidence=[{"kind": "QUOTE", "role": "VALUE", "quote": width}]
                        if unit
                        else [],
                    )
                    for owner, key, raw, proposal, unit, _ in cases
                ]
                payload["raw_unmapped"] = []
                return AttributeOutput(json.dumps(payload).encode(), ExecutionUsage(), request)
            return RecognitionOutput(json.dumps(payload).encode(), ExecutionUsage(), request)

    for unit_id in (units["EQUIPMENT_RECOGNITION"], units["ATTRIBUTE_EXTRACTION"]):
        assert execute_unit(
            unit_id, ctx["factory"], ctx["storage"], ctx["settings"], lambda _: Provider()
        )
    root = ctx["operation_base"].removesuffix("/extraction")
    url = f"{root}/documents/{source['revision_document_id']}/extraction/runs/{run_id}/candidates"
    reply = client.get(url, params={"kind": "ATTRIBUTE"})
    assert reply.status_code == 200, reply.text
    public = {row["proposed_attribute_key"]: row for row in reply.json()["items"]}
    assert len(public) == len(cases)
    width_row = public["enclosure_width"]
    assert width_row["value_form"] == "EQUIVALENT_UNITS"
    assert width_row["alternate_representations"] == [alternate]
    assert width_row["normalized"]["unit"] == "mm"
    assert Decimal(width_row["normalized"]["value"]) == Decimal("508")
    assert public["normally_closed"]["normalized"]["value"] is False
    assert public["manufacturer"]["reason_code"] == "NO_VALUE_PROPOSAL"
    with ctx["factory"]() as session:
        attempt = units["ATTRIBUTE_EXTRACTION"]
        stage = session.get(StageResult, attempt)
        assert stage.payload["version"] == "phase-6r-attributes-v7"
        rows = {
            row.local_ref: row
            for row in session.scalars(select(Candidate).where(Candidate.work_unit_id == attempt))
        }
        assert rows["enclosure_width"].alternate_representations == [alternate]
        assert "508.000 mm" in rows["enclosure_width"].search_terms
        assert session.scalar(
            text("SELECT proposed_value IS NULL FROM extraction_candidates WHERE id=:id"),
            {"id": rows["manufacturer"].id},
        )
        for _, key, raw, proposal, unit, term in cases:
            row = rows[key]
            api = public[key]
            assert row.proposed_value == api["proposed_value"] == proposal
            assert type(row.proposed_value) is type(api["proposed_value"]) is type(proposal)
            assert api["raw_value"] == raw and api["proposed_unit"] == unit
            assert "proposed_enum_value" not in api
            if term:
                assert api["mapping_status"] == "MAPPED"
                assert term in row.search_terms
                found = client.get(url, params={"kind": "ATTRIBUTE", "search": term})
                assert api["id"] in {item["id"] for item in found.json()["items"]}
        alternate_match = client.get(url, params={"kind": "ATTRIBUTE", "search": "508.000 mm"})
        assert alternate_match.json()["items"] == [width_row]
        for column, value in (
            ("raw_value", "changed"),
            ("proposed_value", '"changed"'),
            ("value_number", "999"),
            ("alternate_representations", "[]"),
        ):
            with (
                pytest.raises(DBAPIError, match="Published candidates are immutable"),
                session.begin_nested(),
            ):
                session.execute(
                    text(f"UPDATE extraction_candidates SET {column}=:value WHERE id=:id"),
                    {"value": value, "id": rows["enclosure_width"].id},
                )


def test_diagnostic_timeout_uses_pinned_lease_and_worker_deadlines(operation_context):
    from extraction_worker.extraction_tasks import execute_work_unit
    from powerforge_extraction.stage_execution import FakeExtractionProvider

    ctx = operation_context
    ctx["settings"].extraction_timeout_seconds = 180
    _, _, units = admitted_page(ctx, new_source(ctx, "diagnostic-timeout.pdf"))
    ctx["settings"].extraction_timeout_seconds = 100
    assert execute_unit(
        units["EQUIPMENT_RECOGNITION"],
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        lambda claim: FakeExtractionProvider("success"),
    )
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        key = units["ATTRIBUTE_EXTRACTION"]
        claim = coordinator.claim(key)
        assert claim.profile.timeout_seconds == 180
        unit = session.get(ExtractionWorkUnit, key)
        deadline = session.get(UnitExecution, key).hard_deadline_at
        assert deadline - unit.started_at == timedelta(seconds=195)
        assert coordinator.heartbeat(key, claim.token)
        assert unit.started_at < unit.lease_expires_at <= deadline
        assert 195 < execute_work_unit.soft_time_limit < execute_work_unit.time_limit


@pytest.mark.parametrize("scenario", ["connection-recovers", "lease-expires", "run-lock"])
def test_stage_two_heartbeat_during_provider_io(operation_context, monkeypatch, caplog, scenario):
    from sqlalchemy.exc import OperationalError

    from powerforge_document_processing.storage import InMemoryObjectStorage
    from powerforge_extraction.response_audit import ResponseAudit
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    settings = ctx["settings"]
    settings.extraction_use_fake_provider = False
    settings.extraction_lease_seconds = 3 if scenario == "run-lock" else 6
    settings.extraction_max_attempts = 1
    _, run_id, units = admitted_page(ctx, new_source(ctx, "heartbeat.pdf"))
    attr_id = units["ATTRIBUTE_EXTRACTION"]
    provider = FakeExtractionProvider("success")
    audit_storage = InMemoryObjectStorage()

    def execute(unit, adapter):
        return execute_unit(
            unit,
            ctx["factory"],
            ctx["storage"],
            settings,
            lambda _: adapter,
            audit_storage=audit_storage,
        )

    assert execute(units["EQUIPMENT_RECOGNITION"], provider)

    first_renewal = Event()
    advance_clock = Event()
    real_heartbeat = ExtractionCoordinator.heartbeat
    real_now = ExtractionCoordinator.now

    def heartbeat(self, unit_id, token):
        if scenario == "connection-recovers" and unit_id == attr_id and not first_renewal.is_set():
            first_renewal.set()
            raise OperationalError("sensitive SQL", {}, ConnectionError("sensitive credential"))
        return real_heartbeat(self, unit_id, token)

    def db_now(self):
        observed = real_now(self)
        return observed + timedelta(seconds=7) if advance_clock.is_set() else observed

    monkeypatch.setattr(ExtractionCoordinator, "heartbeat", heartbeat)
    monkeypatch.setattr(ExtractionCoordinator, "now", db_now)

    class Adapter:
        def execute(self, request):
            if scenario == "lease-expires":
                advance_clock.set()
            elif scenario == "run-lock":
                with ctx["factory"]() as session:
                    session.execute(
                        select(ExtractionRun.id).where(ExtractionRun.id == run_id).with_for_update()
                    )
                    work = session.get(ExtractionWorkUnit, attr_id)
                    deadline = monotonic() + 8
                    while now(session) <= work.lease_expires_at:
                        assert monotonic() < deadline
                        sleep(0.05)
            else:
                assert first_renewal.wait(10)
                deadline = monotonic() + 12
                while monotonic() < deadline:
                    with ctx["factory"]() as session:
                        work = session.get(ExtractionWorkUnit, attr_id)
                        if now(session) > work.started_at + timedelta(seconds=6):
                            assert work.heartbeat_at > work.started_at
                            assert work.lease_expires_at > now(session)
                            break
                    sleep(0.05)
                else:
                    pytest.fail("The initial lease period did not elapse during provider I/O")
            return provider.execute(request)

    completed = execute(attr_id, Adapter())
    if scenario in {"lease-expires", "run-lock"}:
        assert not completed
        with ctx["factory"].begin() as session:
            coordinator = ExtractionCoordinator(session, settings)
            assert coordinator.reconcile() >= 1
        assert any(
            getattr(record, "lease_action", None) == "publication"
            and getattr(record, "lease_reason", None) == "LEASE_EXPIRED"
            and record.work_unit_id == str(attr_id)
            for record in caplog.records
        )
    else:
        assert completed
        assert any(
            record.message == "extraction heartbeat unavailable"
            and record.work_unit_id == str(attr_id)
            and record.error_class == "OperationalError"
            for record in caplog.records
        )
        assert "sensitive" not in caplog.text
    with ctx["factory"]() as session:
        attempt = session.get(ExtractionWorkUnit, attr_id)
        assert (session.get(StageResult, attr_id) is not None) is completed
        assert (session.get(ResponseAudit, attr_id) is not None) is completed
        if completed:
            assert attempt.status == "COMPLETED"
        else:
            assert attempt.error_code == "EXTRACTION_PROVIDER_OUTCOME_UNKNOWN"
            assert attempt.heartbeat_at == attempt.started_at
            assert (
                len(
                    session.scalars(
                        select(ExtractionWorkUnit).where(
                            ExtractionWorkUnit.run_id == run_id,
                            ExtractionWorkUnit.stage == "ATTRIBUTE_EXTRACTION",
                        )
                    ).all()
                )
                == 1
            )


@pytest.mark.parametrize("fault", ["missing-audit", "store-failure", "stale-lease"])
def test_recognition_audit_is_atomic(operation_context, monkeypatch, fault):
    from powerforge_document_processing.storage import InMemoryObjectStorage
    from powerforge_document_processing.storage.base import StorageError
    from powerforge_extraction import response_audit
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    ctx["settings"].extraction_use_fake_provider = False
    _, run_id, units = admitted_page(ctx, new_source(ctx, "recognition-audit.pdf"))

    class AuditStorage(InMemoryObjectStorage):
        def put(self, key, fileobj, size, content_type):
            if fault == "store-failure":
                raise StorageError("Audit unavailable")
            super().put(key, fileobj, size, content_type)
            if fault == "stale-lease":
                with ctx["factory"].begin() as session:
                    ExtractionCoordinator(session, ctx["settings"]).cancel(run_id)

    if fault == "missing-audit":
        monkeypatch.setattr(response_audit, "record_audit", lambda *_: None)
    recognition = units["EQUIPMENT_RECOGNITION"]
    assert execute_unit(
        recognition,
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        lambda _: FakeExtractionProvider("success"),
        audit_storage=AuditStorage(),
    ) is (fault != "stale-lease")
    with ctx["factory"]() as session:
        assert session.get(response_audit.ResponseAudit, recognition) is None
        assert session.get(StageResult, recognition) is None
        assert session.get(ExtractionWorkUnit, recognition).status == (
            "CANCELLED" if fault == "stale-lease" else "FAILED"
        )


@pytest.mark.parametrize("stage", ["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"])
@pytest.mark.parametrize("late", [False, True])
def test_publication_near_and_past_coordinator_deadline(
    operation_context, monkeypatch, caplog, stage, late
):
    from dataclasses import replace

    from powerforge_document_processing.storage import InMemoryObjectStorage
    from powerforge_extraction.publication_records import Fragment
    from powerforge_extraction.response_audit import ResponseAudit
    from powerforge_extraction.stage_execution import FakeExtractionProvider, StageResult

    ctx = operation_context
    settings = ctx["settings"]
    settings.extraction_use_fake_provider = False
    settings.extraction_timeout_seconds = 100
    settings.extraction_lease_seconds = 30
    _, _, units = admitted_page(ctx, new_source(ctx, "publication-deadline.pdf"))
    store = InMemoryObjectStorage()
    provider = FakeExtractionProvider("success")

    def execute(unit_id, factory):
        return execute_unit(
            unit_id, ctx["factory"], ctx["storage"], settings, factory, audit_storage=store
        )

    if stage == "ATTRIBUTE_EXTRACTION":
        assert execute(units["EQUIPMENT_RECOGNITION"], lambda _: provider)

    unit_id = units[stage]
    offset = 3
    original_now = ExtractionCoordinator.now
    monkeypatch.setattr(
        ExtractionCoordinator,
        "now",
        lambda coordinator: original_now(coordinator) + timedelta(seconds=offset),
    )

    class SlowProvider:
        def __init__(self, claim):
            self.claim = claim

        def execute(self, request):
            nonlocal offset
            for heartbeat_offset in range(13, 104, 10):
                offset = heartbeat_offset
                with ctx["factory"].begin() as session:
                    assert ExtractionCoordinator(session, settings).heartbeat(
                        unit_id, self.claim.token
                    )
            offset = 119 if late else 103
            result = provider.execute(request)
            if stage == "ATTRIBUTE_EXTRACTION":
                result = replace(
                    result,
                    output_text=json.dumps(
                        {
                            "attributes": [],
                            "raw_unmapped": [
                                {
                                    "local_ref": "raw-1",
                                    "equipment_ref": "equipment-1",
                                    "association": "ASSERTED",
                                    "raw_label": "Nameplate",
                                    "display_label": None,
                                    "raw_value": "400 AF",
                                    "raw_unit": None,
                                    "qualifiers": [],
                                    "value_form": "SINGLE",
                                    "evidence": [
                                        {"kind": "QUOTE", "role": "VALUE", "quote": "400 AF"}
                                    ],
                                }
                            ],
                        }
                    ).encode(),
                )
            else:
                payload = json.loads(result.output_text)
                payload["equipment"][0]["evidence"] = [
                    {"kind": "QUOTE", "role": "EQUIPMENT", "quote": "TX-1"}
                ]
                result = replace(result, output_text=json.dumps(payload).encode())
            return result

    assert execute(unit_id, SlowProvider) is not late
    if late:
        assert any(
            getattr(record, "lease_reason", None) == "HARD_DEADLINE" for record in caplog.records
        )
    with ctx["factory"]() as session:
        attempt = session.get(ExtractionWorkUnit, unit_id)
        delivery = session.get(UnitExecution, unit_id)
        assert delivery.hard_deadline_at - attempt.started_at == timedelta(seconds=115)
        assert (session.get(ResponseAudit, unit_id) is not None) is not late
        assert (session.get(StageResult, unit_id) is not None) is not late
        fragment = session.scalar(select(Fragment).where(Fragment.work_unit_id == unit_id))
        assert (fragment is not None) is not late
        if not late:
            assert fragment.localization == "RESOLVED"
            assert attempt.finished_at < delivery.hard_deadline_at
            assert attempt.output_counts["candidates"] == 1
            expected_ready = delivery.available_at
            if stage == "ATTRIBUTE_EXTRACTION":
                parent = session.get(ExtractionWorkUnit, units["EQUIPMENT_RECOGNITION"])
                expected_ready = max(expected_ready, parent.finished_at)
            assert attempt.performance["queue_wait_ms"] == (
                (attempt.started_at - expected_ready) // timedelta(milliseconds=1)
            )
