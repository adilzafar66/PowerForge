"""Recovery batches contain expired work, rather than the oldest healthy runs."""

from datetime import timedelta

import pytest

from extraction_execution_support import detail, units
from extraction_execution_support import execution_ctx as execution_ctx
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator

pytestmark = pytest.mark.integration


def test_expired_work_progresses_past_more_than_one_batch_of_healthy_runs(execution_ctx):
    ctx = execution_ctx
    healthy = []
    targets = []
    for i in range(103):
        # Separate transactions give the healthy runs strictly earlier creation times.
        with ctx["factory"].begin() as session:
            # Distinct immutable configurations allow independent active runs on this source.
            settings = ctx["settings"].model_copy(update={"extraction_max_calls": 1000 + i})
            coordinator = ExtractionCoordinator(session, settings)
            run = coordinator.start(ctx["src"]["document"])
            if i < 101:
                healthy.append(run.id)
                continue
            uid = coordinator._units(run.id)[0].id
            assert coordinator.claim(uid) is not None
            targets.append((run.id, uid))
    with ctx["factory"].begin() as session:
        # The newer run has the older lease. Recovery prioritizes expiry, not creation age.
        now = coordinator.now()
        for i, (_, uid) in enumerate(targets):
            session.get(ExtractionWorkUnit, uid).lease_expires_at = now - timedelta(seconds=i + 1)

    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).reconcile(limit=1) == 1
    older, newer = targets
    assert len(units(ctx, newer[0])) == 2
    assert len(units(ctx, older[0])) == 1
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).reconcile(limit=1) == 1
    assert len(units(ctx, older[0])) == 2
    for rid, _ in targets:
        result = detail(ctx, rid)
        assert result["attempts"][0]["error_code"] == "WORKER_INTERRUPTED"
        assert result["attempts"][1]["status"] == "PENDING"
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).reconcile(limit=100) == 0
        for rid in healthy:
            assert session.get(ExtractionRun, rid).status == "PENDING"
            unit = ExtractionCoordinator(session, ctx["settings"])._units(rid)[0]
            assert unit.status == "PENDING" and unit.attempt_number == 1


def test_reconcile_still_aggregates_active_runs_with_only_settled_units(execution_ctx):
    ctx = execution_ctx
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        run = coordinator.start(ctx["src"]["document"])
        rid = run.id
        unit = coordinator._units(rid)[0]
        unit.status, unit.error_code, unit.finished_at = (
            "FAILED",
            "INVALID_SOURCE_INPUT",
            coordinator.now(),
        )
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).reconcile() == 0
    assert detail(ctx, rid)["run"]["status"] == "FAILED"
