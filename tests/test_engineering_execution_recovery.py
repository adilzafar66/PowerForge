"""Dependency recovery fairness, duplicate deliveries and committed upstream visibility."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import select

from engineering_execution_support import StageProvider, attempt, processing, start_engineering
from engineering_execution_support import engineering_ctx as engineering_ctx
from engineering_execution_support import execution_ctx as execution_ctx
from extraction_execution_support import add_page, detail, execute
from powerforge_extraction.controls import UnitExecution
from powerforge_extraction.fake import FakeEngineeringProvider
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator

pytestmark = pytest.mark.integration
EQ, ATTR = "EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"


def test_blocked_dispatch_and_expired_recovery_progress_past_100_healthy_runs(engineering_ctx):
    ctx = engineering_ctx
    healthy, expired, blocked = [], None, None
    for index in range(103):
        settings = ctx["settings"].model_copy(update={"extraction_max_calls": 1000 + index})
        with ctx["factory"].begin() as session:
            coordinator = ExtractionCoordinator(session, settings)
            run = coordinator.start(ctx["src"]["document"], profile_key="engineering-test-v1")
            by_stage = {u.stage: u for u in coordinator._units(run.id)}
            # Make blocked delivery records older than every ready notification.
            session.get(UnitExecution, by_stage[ATTR].id).dispatch_after = (
                coordinator.now() - timedelta(days=1)
            )
            if index < 101:
                healthy.append(run.id)
            elif index == 101:
                claim = coordinator.claim(by_stage[EQ].id)
                assert claim is not None
                by_stage[EQ].lease_expires_at = coordinator.now() - timedelta(seconds=1)
                expired = run.id
            else:
                # Simulate a historical/pre-settlement pending dependent. Reconcile
                # must find it even though there is no expired RUNNING unit in its run.
                by_stage[EQ].status = "FAILED"
                by_stage[EQ].error_code = "INVALID_SOURCE_INPUT"
                by_stage[EQ].finished_at = coordinator.now()
                blocked = run.id
    ctx["delivery"].ids.clear()
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        assert coordinator.dispatch(ctx["delivery"], limit=1) == 1
        dispatched = session.get(ExtractionWorkUnit, ctx["delivery"].ids[0])
        assert dispatched.stage == EQ  # Blocked rows did not fill the bounded window.
        assert coordinator.reconcile(limit=1) == 1  # Expiry is still first priority.
    assert detail(ctx, expired)["run"]["status"] == "RUNNING"
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).reconcile(limit=1) == 0
    assert detail(ctx, blocked)["run"]["status"] == "FAILED"
    with ctx["factory"]() as session:
        assert all(session.get(ExtractionRun, rid).status == "PENDING" for rid in healthy)


def test_duplicate_stage_delivery_and_uncommitted_upstream_do_not_issue_extra_calls(
    engineering_ctx,
):
    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    provider = StageProvider()
    eq, attr = attempt(ctx, rid, EQ), attempt(ctx, rid, ATTR)
    entered, finish = Event(), Event()

    def wait_for_source(request):
        entered.set()
        assert finish.wait(10)

    provider.on_call = wait_for_source
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(execute, ctx, eq, provider)
        try:
            assert entered.wait(10)
            assert execute(ctx, eq, provider) is False
            assert execute(ctx, attr, provider) is False
            assert detail(ctx, rid)["execution"]["calls_admitted"] == 1
        finally:
            finish.set()
        assert future.result(timeout=10)
    provider.on_call = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(ctx, attr, provider), range(2)))
    assert sum(results) == 1 and len(provider.requests) == 2
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"


def test_real_worker_provider_factory_supports_empty_stages_without_production_openai(
    engineering_ctx,
):
    from extraction_worker.extraction_tasks import provider_for
    from powerforge_extraction.execution import execute_unit

    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    for stage in (EQ, ATTR):
        assert execute_unit(
            attempt(ctx, rid, stage), ctx["factory"], ctx["storage"], ctx["settings"], provider_for
        )
    result = detail(ctx, rid)
    assert result["run"]["status"] == "COMPLETED"
    assert result["execution"]["reported_calls"] == 2
    assert all(u["output_counts"]["candidates"] == 0 for u in result["attempts"])


def test_page_dependencies_and_per_run_concurrency_are_independent(engineering_ctx):
    ctx = engineering_ctx
    pid, _ = processing(ctx)
    add_page({**ctx, "src": {**ctx["src"], "processing": pid}})
    ctx["settings"].extraction_max_concurrent_per_run = 1
    rid = start_engineering(ctx)["run"]["id"]
    with ctx["factory"]() as session:
        selected = {
            (u.stage, u.page_numbers[0]): u.id
            for u in session.scalars(
                select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == rid)
            )
        }
    entered, finish = Event(), Event()

    def pause(request):
        entered.set()
        assert finish.wait(10)

    provider, empty = StageProvider(on_call=pause), FakeEngineeringProvider()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute, ctx, selected[EQ, 1], provider)
        try:
            assert entered.wait(10)
            assert not execute(ctx, selected[EQ, 2], empty)
            assert not execute(ctx, selected[ATTR, 1], provider)
            assert not execute(ctx, selected[ATTR, 2], empty)
        finally:
            finish.set()
        assert future.result(timeout=10)
    provider.on_call = None
    assert not execute(ctx, selected[ATTR, 2], empty)
    assert execute(ctx, selected[EQ, 2], empty)
    assert execute(ctx, selected[ATTR, 2], empty)
    assert execute(ctx, selected[ATTR, 1], provider)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED" and done["coverage"]["required_units"] == 4
    assert done["execution"]["calls_admitted"] == 4
    assert len(provider.requests) + len(empty.calls) == 4
