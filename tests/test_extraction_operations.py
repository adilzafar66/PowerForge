"""Phase 6R admission, source barriers, recovery and scope."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from threading import Event
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
        extraction_phase6r_fake=True,
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
    return operation_id, run_id, units


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
    from powerforge_extraction.phase6r_runtime import FakePhase6RProvider, StageResult

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
            result = FakePhase6RProvider("success").execute(request)
            if scenario == "empty" and request.stage == "EQUIPMENT_RECOGNITION":
                (equipment,) = result.result.equipment
                unknown = equipment.model_copy(update={"registry_type": None})
                result.result = result.result.model_copy(update={"equipment": (unknown,)})
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
        assert not {"extraction_candidates", "extracted_tables"} & tables
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
    assert status["extraction"]["effective_result"] is None


@pytest.mark.parametrize("cancel", [False, True])
def test_attribute_retry_reuses_recognition_and_cancellation_fences_result(
    operation_context, cancel
):
    from powerforge_ai.extraction import ErrorCode, ProviderFailure
    from powerforge_extraction.phase6r_runtime import FakePhase6RProvider, StageResult

    ctx = operation_context
    source = new_source(ctx, "retry.pdf")
    preparation(ctx, source)
    _, body = reviewed(ctx, [source])
    reply = start_operation(ctx, body)
    assert reply.status_code == 202, reply.text
    operation_id = reply.json()["id"]
    advance(ctx, operation_id)
    run_id = UUID(detail_operation(ctx, operation_id)["items"][0]["extraction"]["run_id"])
    fake = FakePhase6RProvider("success")

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
    root = ctx["operation_base"] + f"/operations/{operation_id}"

    class AttributeProvider:
        def execute(self, request):
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
    if cancel:
        return
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
    with ctx["factory"]() as session:
        result = session.get(StageResult, retry_id)
        assert (result.upstream_work_unit_id, result.upstream_hash) == (recognition, digest)
        assert session.get(ExtractionRun, run_id).status == "COMPLETED"


def test_disabled_test_profile_and_insufficient_budget_block_review(operation_context):
    ctx = operation_context
    source = new_source(ctx, "limits.pdf")
    settings = ctx["settings"]
    settings.extraction_phase6r_fake = False
    disabled, _ = reviewed(ctx, [source])
    assert disabled["review_hash"] is None
    assert disabled["profile"]["enabled"] is False
    settings.extraction_phase6r_fake = True
    settings.extraction_max_calls = 1
    limited, _ = reviewed(ctx, [source])
    assert limited["review_hash"] is None
    assert "admission budget" in limited["items"][0]["error"]


def test_expired_recognition_lease_is_fenced_and_reconciled(operation_context):
    from powerforge_extraction.errors import LeaseLost
    from powerforge_extraction.phase6r_runtime import FakePhase6RProvider, StageResult, request_for

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
    wire, request = request_for(ctx["factory"], ctx["storage"], claim)
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

    response = FakePhase6RProvider("success").execute(request)
    with pytest.raises(LeaseLost), ctx["factory"].begin() as session:
        ExtractionCoordinator(session, ctx["settings"]).complete_stage(
            recognition, claim.token, wire, response.result, response.usage
        )
    for unit_id in (retry_id, attributes):
        assert execute_unit(
            unit_id,
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: FakePhase6RProvider("success"),
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
    from powerforge_extraction.enriched_sources import bound_snapshot
    from powerforge_extraction.phase6r_runtime import FakePhase6RProvider, StageResult

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
            lambda _: FakePhase6RProvider("success"),
        )
    with ctx["factory"]() as session:
        assert session.get(StageResult, units["ATTRIBUTE_EXTRACTION"]).upstream_work_unit_id == (
            retry_id
        )


def test_concurrent_redelivery_cannot_start_another_call(operation_context):
    from powerforge_extraction.phase6r_runtime import FakePhase6RProvider, StageResult

    ctx = operation_context
    _, _, units = admitted_page(ctx, new_source(ctx, "duplicate.pdf"))
    recognition = units["EQUIPMENT_RECOGNITION"]
    entered, release = Event(), Event()

    class HeldProvider:
        def execute(self, request):
            entered.set()
            assert release.wait(10)
            return FakePhase6RProvider("success").execute(request)

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
    from powerforge_extraction.phase6r_runtime import FakePhase6RProvider, StageResult

    ctx = operation_context
    settings = ctx["settings"]
    settings.extraction_max_calls = 2
    _, run_id, units = admitted_page(ctx, new_source(ctx, "retry-budget.pdf"))
    assert execute_unit(
        units["EQUIPMENT_RECOGNITION"],
        ctx["factory"],
        ctx["storage"],
        settings,
        lambda _: FakePhase6RProvider("transient"),
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
        lambda _: FakePhase6RProvider("success"),
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
    operation_context, monkeypatch, limit
):
    from powerforge_extraction import enriched_planning, operation_plan, operations
    from powerforge_extraction.controls import RunExecution, UnitExecution
    from powerforge_extraction.operation_models import UNKNOWN_PROVIDER_OUTCOME
    from powerforge_extraction.phase6r_profile import phase6r_profile
    from powerforge_extraction.phase6r_runtime import StageResult, request_for

    ctx = operation_context
    settings = ctx["settings"]
    settings.extraction_max_calls = 2 if limit == "calls" else 6
    settings.extraction_max_attempts = 1 if limit == "attempts" else 3
    # Pin the OpenAI identity in the database but keep B's fake-only runtime gate.
    # Simulate a worker disappearing after admission without making a provider request.
    profile = phase6r_profile(settings.model_copy(update={"extraction_phase6r_fake": False}))
    for module in (enriched_planning, operation_plan, operations):
        monkeypatch.setattr(module, "phase6r_profile", lambda _: profile)
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
    _, request = request_for(ctx["factory"], ctx["storage"], claim)
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
    from powerforge_extraction.phase6r_runtime import FakePhase6RProvider
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
            return FakePhase6RProvider("success").execute(request)

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
    assert first["page_context_hash"] == second["page_context_hash"]
    assert first["page"] == second["page"]
    page = first["page"]
    table_refs = {
        ref
        for table in page["layout"]["tables"]
        for cell in table["cells"]
        for ref in cell["readings"]
    }
    assert table_refs
    readings = {reading["reading_ref"]: reading["text"] for reading in page["readings"]}
    assert table_refs <= readings.keys()
    assert "600" in {readings[ref] for ref in table_refs}
    assert any("Unrelated" in text for ref, text in readings.items() if ref not in table_refs)
