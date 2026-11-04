"""M4 executes the complete fenced page-stage pipeline with scripted providers only."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from documents_support import client
from engineering_execution_support import (
    TEXT,
    StageProvider,
    attempt,
    processing,
    start_engineering,
)
from engineering_execution_support import engineering_ctx as engineering_ctx
from engineering_execution_support import execution_ctx as execution_ctx
from extraction_execution_support import detail, execute, expire, units
from powerforge_ai.extraction import (
    ErrorCode,
    ExecutionUsage,
    ExtractionResponse,
    ProbeResult,
    ProviderFailure,
)
from powerforge_extraction.contracts import WorkUnitOutput
from powerforge_extraction.controls import UnitExecution
from powerforge_extraction.errors import LeaseLost
from powerforge_extraction.fake import SimulatedWorkerInterruption
from powerforge_extraction.identities import content_hash
from powerforge_extraction.models import ExtractionAICall, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.profiles import ENGINEERING_TEXT_TEST_PROFILE

pytestmark = pytest.mark.integration
EQ, ATTR = "EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"


def test_planning_dependency_dispatch_and_two_actual_calls_publish_same_run_links(engineering_ctx):
    ctx = engineering_ctx
    with ctx["factory"]() as session:
        before = session.scalar(
            text("SELECT updated_at FROM project_revisions WHERE id=:id"),
            {"id": ctx["revision_id"]},
        )
        engine = session.get_bind()
    plan = start_engineering(ctx)
    rid = plan["run"]["id"]
    eq, attr = attempt(ctx, rid, EQ), attempt(ctx, rid, ATTR)
    assert len(plan["attempts"]) == 2 and plan["run"]["stages"] == [EQ, ATTR]
    assert plan["execution"]["execution_kind"] == "FAKE_TEST"
    assert ctx["delivery"].ids == [eq]
    assert start_engineering(ctx)["run"]["id"] == rid
    provider = StageProvider(on_call=lambda request: _no_transaction(engine))
    assert not execute(ctx, attr, provider)
    assert not provider.requests and detail(ctx, rid)["execution"]["calls_admitted"] == 0
    assert execute(ctx, eq, provider)
    assert detail(ctx, rid)["run"]["status"] == "RUNNING"
    ctx["delivery"].ids.clear()
    with ctx["factory"].begin() as session:
        assert (
            ExtractionCoordinator(session, ctx["settings"]).dispatch(ctx["delivery"], limit=1) == 1
        )
    assert ctx["delivery"].ids == [attr]
    assert execute(ctx, attr, provider)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED"
    assert done["execution"]["calls_admitted"] == done["execution"]["reported_calls"] == 2
    assert done["execution"]["provider_calls_started"] == 2
    first, second = provider.requests
    assert first.text == second.text == TEXT and first.image == second.image
    assert first.image is not None and first.source_roles == ("native_text", "analysis_image")
    assert first.image_detail == "high" and first.max_output_tokens == 8192
    assert second.upstream_context and '"local_ref":"eq1"' in second.upstream_context
    assert str(eq) not in second.upstream_context and "storage_key" not in second.upstream_context
    candidates = client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["items"]
    mention = next(c for c in candidates if c["kind"] == "EQUIPMENT_MENTION")
    value = next(c for c in candidates if c["kind"] == "ATTRIBUTE_VALUE")
    assert (
        value["numeric_value"] == "0.6" and value["equipment_mention_candidate_id"] == mention["id"]
    )
    assert value["source_group_id"] == mention["source_group_id"]
    assert all(c["diagnostics"]["synthetic"] for c in candidates)
    with ctx["factory"]() as session:
        calls = list(
            session.scalars(select(ExtractionAICall).where(ExtractionAICall.run_id == UUID(rid)))
        )
        for call in calls:
            request = next(r for r in provider.requests if r.work_unit_id == call.work_unit_id)
            assert call.schema_version == request.schema_version
            assert call.prompt_hash == content_hash(request.instructions)
            if call.work_unit_id == attr:
                assert str(eq) in call.request_correlation_id
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


def _no_transaction(engine):
    assert engine.pool.checkedout() == 0


def test_attribute_retry_reuses_recognition_and_exact_rendering_and_original_artifacts(
    engineering_ctx,
):
    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    provider = StageProvider(
        failure=lambda r: (
            ProviderFailure(ErrorCode.UNAVAILABLE, ExecutionUsage(input_tokens=7, output_tokens=1))
            if r.stage == ATTR and r.attempt_number == 1
            else None
        )
    )
    eq, first = attempt(ctx, rid, EQ), attempt(ctx, rid, ATTR)
    execute(ctx, eq, provider)
    execute(ctx, first, provider)
    second = attempt(ctx, rid, ATTR)
    assert second != first and len(units(ctx, rid)) == 3
    # New processing output must not become either retry's input/context.
    processing(ctx, native="A later processing representation", image=False)
    execute(ctx, second, provider)
    requests = [r for r in provider.requests if r.stage == ATTR]
    assert len(requests) == 2 and sum(r.stage == EQ for r in provider.requests) == 1
    for field in (
        "instructions",
        "schema_version",
        "response_model",
        "upstream_context",
        "text",
        "image",
        "source_roles",
    ):
        assert getattr(requests[0], field) == getattr(requests[1], field)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 2


def test_permanent_upstream_failure_settles_waiter_then_manual_retry_appends_both(engineering_ctx):
    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    failed = StageProvider(failure=lambda r: ProviderFailure(ErrorCode.AUTH))
    execute(ctx, attempt(ctx, rid, EQ), failed)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "FAILED" and len(failed.requests) == 1
    blocked = next(u for u in done["attempts"] if u["stage"] == ATTR)
    assert blocked["error_code"] == "PREREQUISITE_FAILED" and blocked["retryable"]
    assert done["execution"]["calls_admitted"] == done["execution"]["reported_calls"] == 1
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 202
    assert len(units(ctx, rid)) == 4
    provider = StageProvider()
    assert not execute(ctx, attempt(ctx, rid, ATTR), provider)
    execute(ctx, attempt(ctx, rid, EQ), provider)
    execute(ctx, attempt(ctx, rid, ATTR), provider)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
    assert len(provider.requests) == 2


def test_exhausted_upstream_does_not_consume_blocked_manual_retry_history(engineering_ctx):
    ctx = engineering_ctx
    ctx["settings"].extraction_max_attempts = 2
    rid = start_engineering(ctx)["run"]["id"]
    provider = StageProvider(failure=lambda r: ProviderFailure(ErrorCode.UNAVAILABLE))
    execute(ctx, attempt(ctx, rid, EQ), provider)
    assert detail(ctx, rid)["run"]["status"] == "RUNNING"
    assert (
        next(u for u in detail(ctx, rid)["attempts"] if u["stage"] == ATTR)["status"] == "PENDING"
    )
    execute(ctx, attempt(ctx, rid, EQ), provider)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "FAILED"
    assert all(not u["retryable"] for u in done["attempts"])
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 409
    assert len(units(ctx, rid)) == 3 and len(provider.requests) == 2


@pytest.mark.parametrize("success", [True, False])
def test_budget_denial_settles_dependencies_without_extra_calls(engineering_ctx, success):
    ctx = engineering_ctx
    ctx["settings"].extraction_max_calls = 1
    rid = start_engineering(ctx)["run"]["id"]
    provider = StageProvider(
        failure=None if success else lambda r: ProviderFailure(ErrorCode.UNAVAILABLE)
    )
    execute(ctx, attempt(ctx, rid, EQ), provider)
    assert not execute(ctx, attempt(ctx, rid, ATTR), provider)
    done = detail(ctx, rid)
    assert done["run"]["status"] == ("PARTIALLY_COMPLETED" if success else "FAILED")
    assert all(u["status"] not in {"PENDING", "RUNNING"} for u in done["attempts"])
    assert done["execution"]["calls_admitted"] == len(provider.requests) == 1


@pytest.mark.parametrize("attempts", [1, 2])
def test_expired_upstream_recovers_or_settles_dependents_and_fences_old_token(
    engineering_ctx, attempts
):
    ctx = engineering_ctx
    ctx["settings"].extraction_max_attempts = attempts
    rid = start_engineering(ctx)["run"]["id"]
    first = attempt(ctx, rid, EQ)

    def crash(request):
        raise SimulatedWorkerInterruption()

    provider = StageProvider(on_call=crash)
    with pytest.raises(SimulatedWorkerInterruption):
        execute(ctx, first, provider)
    with ctx["factory"]() as session:
        token = session.get(UnitExecution, first).token
    expire(ctx, first)
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).reconcile() >= 1
    with ctx["factory"].begin() as session:
        with pytest.raises(LeaseLost):
            ExtractionCoordinator(session, ctx["settings"]).complete(
                first, token, WorkUnitOutput(), ExecutionUsage(), ctx["storage"]
            )
    if attempts == 1:
        assert detail(ctx, rid)["run"]["status"] == "FAILED"
        assert (
            next(u for u in detail(ctx, rid)["attempts"] if u["stage"] == ATTR)["error_code"]
            == "PREREQUISITE_FAILED"
        )
    else:
        successful = StageProvider()
        execute(ctx, attempt(ctx, rid, EQ), successful)
        execute(ctx, attempt(ctx, rid, ATTR), successful)
        assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
    assert detail(ctx, rid)["execution"]["unreported_provider_calls"] == 1


def test_cancel_waiting_and_inflight_units_preserves_committed_recognition(engineering_ctx):
    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    provider = StageProvider()
    execute(ctx, attempt(ctx, rid, EQ), provider)
    began, finish = Event(), Event()

    def pause(request):
        began.set()
        assert finish.wait(10)

    provider.on_call = pause
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute, ctx, attempt(ctx, rid, ATTR), provider)
        try:
            assert began.wait(10)
            assert client.post(ctx["base"] + f"/runs/{rid}/cancel").status_code == 200
        finally:
            finish.set()
        assert future.result(timeout=10) is False
    assert detail(ctx, rid)["run"]["status"] == "CANCELLED"
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 1
    new = start_engineering(ctx, mode="reextract")["run"]["id"]
    assert client.post(ctx["base"] + f"/runs/{new}/cancel").status_code == 200
    assert all(u["status"] == "CANCELLED" for u in detail(ctx, new)["attempts"])
    assert detail(ctx, new)["execution"]["calls_admitted"] == 0


@pytest.mark.parametrize("mode", ["hybrid", "image", "text", "empty"])
def test_hybrid_image_text_and_empty_recognition_still_execute_both_stages(engineering_ctx, mode):
    ctx = engineering_ctx
    if mode == "image":
        processing(ctx, native=None)
    profile = ENGINEERING_TEXT_TEST_PROFILE if mode == "text" else "engineering-test-v1"
    rid = start_engineering(ctx, profile_key=profile)["run"]["id"]
    provider = StageProvider(visual=mode == "image", empty_recognition=mode == "empty")
    execute(ctx, attempt(ctx, rid, EQ), provider)
    execute(ctx, attempt(ctx, rid, ATTR), provider)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED" and len(provider.requests) == 2
    assert all((r.text is None) == (mode == "image") for r in provider.requests)
    assert all((r.image is None) == (mode == "text") for r in provider.requests)
    values = client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["items"]
    if mode == "empty":
        assert len(values) == 1 and values[0]["mapping_status"] == "UNMAPPED"
    elif mode == "image":
        assert all(c["diagnostics"]["grounding_precision"] == "VISUAL_PAGE" for c in values)


def test_wrong_stage_response_keeps_usage_and_manual_retry_resends_only_attributes(engineering_ctx):
    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    provider = StageProvider()
    execute(ctx, attempt(ctx, rid, EQ), provider)

    class WrongStage:
        def execute(self, request):
            return ExtractionResponse(
                result=ProbeResult(acknowledged=True, excerpt=None),
                usage=ExecutionUsage(input_tokens=12, output_tokens=1),
            )

    execute(ctx, attempt(ctx, rid, ATTR), WrongStage())
    failed = detail(ctx, rid)
    assert failed["run"]["status"] == "PARTIALLY_COMPLETED"
    assert (
        next(u for u in failed["attempts"] if u["stage"] == ATTR)["error_code"]
        == "INVALID_PROVIDER_RESPONSE"
    )
    assert failed["execution"]["input_tokens"] == 32
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 202
    execute(ctx, attempt(ctx, rid, ATTR), provider)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED" and len(units(ctx, rid)) == 3


def test_failed_managed_publication_rolls_back_attribute_output_and_success_telemetry(
    engineering_ctx, monkeypatch
):
    from powerforge_extraction import engineering_output

    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    provider = StageProvider()
    execute(ctx, attempt(ctx, rid, EQ), provider)
    convert = engineering_output.convert_attributes

    def broken(*args):
        output = convert(*args)
        return output.model_copy(
            update={
                "candidates": [output.candidates[0].model_copy(update={"source_group_id": uuid4()})]
            }
        )

    monkeypatch.setattr(engineering_output, "convert_attributes", broken)
    failed = attempt(ctx, rid, ATTR)
    execute(ctx, failed, provider)
    assert detail(ctx, rid)["run"]["status"] == "PARTIALLY_COMPLETED"
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 1
    with ctx["factory"]() as session:
        calls = list(
            session.scalars(select(ExtractionAICall).where(ExtractionAICall.work_unit_id == failed))
        )
        assert len(calls) == 1 and calls[0].outcome == "FAILED"
        assert calls[0].schema_version == provider.requests[-1].schema_version
        assert session.get(ExtractionWorkUnit, failed).output_counts == {}
    monkeypatch.setattr(engineering_output, "convert_attributes", convert)
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 202
    execute(ctx, attempt(ctx, rid, ATTR), provider)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"


def test_each_stage_loads_only_pinned_inputs_once_outside_metadata_transactions(engineering_ctx):
    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    original, reads = ctx["storage"], []
    with ctx["factory"]() as session:
        engine = session.get_bind()

    class Storage:
        def get(self, key):
            reads.append((key, engine.pool.checkedout()))
            return original.get(key)

        def __getattr__(self, name):
            return getattr(original, name)

    ctx["storage"] = Storage()
    provider = StageProvider()
    execute(ctx, attempt(ctx, rid, EQ), provider)
    execute(ctx, attempt(ctx, rid, ATTR), provider)
    outside = [key for key, connections in reads if connections == 0]
    assert len(outside) == 4 and len(set(outside)) == 2
    assert all(outside.count(key) == 2 for key in set(outside))
    assert all(key.endswith("NATIVE_TEXT") for key, connections in reads if connections)
    assert len(reads) == 6  # The existing 6A publisher also verifies pinned text per stage.
