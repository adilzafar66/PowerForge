"""Real database state, failure, recovery and fencing behavior; no billable calls."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from documents_support import client, make_project, make_revision
from extraction_execution_support import add_page, detail, execute, expire, start_run, units
from extraction_execution_support import execution_ctx as execution_ctx
from powerforge_ai.extraction import ErrorCode, ExecutionUsage, ProviderFailure
from powerforge_document_processing.models import (
    DocumentProcessingRun,
    ProjectRevision,
    RevisionDocument,
)
from powerforge_extraction.contracts import WorkUnitOutput
from powerforge_extraction.controls import UnitExecution
from powerforge_extraction.errors import LeaseLost
from powerforge_extraction.fake import FakeExtractionProvider, SimulatedWorkerInterruption
from powerforge_extraction.models import ExtractionAICall, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.persistence import ExtractionPersistence

pytestmark = pytest.mark.integration


def test_fake_http_execution_reuse_reextract_and_no_canonical_writes(execution_ctx):
    ctx = execution_ctx
    with ctx["factory"]() as session:
        before = session.get(ProjectRevision, UUID(ctx["revision_id"])).updated_at
    first = start_run(ctx)
    rid = first["run"]["id"]
    assert first["execution"]["execution_kind"] == "FAKE_TEST"
    assert first["run"]["status"] == "PENDING"
    assert start_run(ctx)["run"]["id"] == rid
    assert start_run(ctx, mode="reextract")["run"]["id"] == rid
    provider = FakeExtractionProvider()
    assert execute(ctx, units(ctx, rid)[0], provider)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
    assert start_run(ctx)["run"]["id"] == rid
    second = start_run(ctx, mode="reextract")
    assert second["run"]["id"] != rid and second["run"]["reextracts_run_id"] == rid
    candidates = client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["items"]
    assert len(candidates) == 1 and candidates[0]["diagnostics"]["synthetic"] is True
    assert len(provider.calls) == 1
    with ctx["factory"]() as session:
        assert session.get(ProjectRevision, UUID(ctx["revision_id"])).updated_at == before
        assert (
            session.scalar(
                text("SELECT count(*) FROM equipment WHERE revision_id=:r"),
                {"r": UUID(ctx["revision_id"])},
            )
            == 0
        )


def test_profiles_pages_unknown_classification_and_disabled_external(execution_ctx):
    ctx = execution_ctx
    profiles = client.get(ctx["base"] + "/profiles").json()["items"]
    assert len(profiles) == 8 and not profiles[1]["enabled"]
    assert {p["key"] for p in profiles if p["requires_enrichment"]} == {
        "engineering-openai-enriched-v1",
        "tables-openai-enriched-v1",
    }
    assert not any(p["production_extractor"] for p in profiles[:2])
    assert all(p["production_extractor"] and not p["enabled"] for p in profiles[2:])
    assert (
        client.post(
            ctx["base"] + "/runs", json={"profile_key": "infrastructure-openai-v1"}
        ).status_code
        == 409
    )
    assert (
        client.post(ctx["base"] + "/runs", json={"profile_key": "equipment-production"}).status_code
        == 422
    )
    assert client.post(ctx["base"] + "/runs", json={"pages": [99]}).status_code == 422
    assert client.post(ctx["base"] + "/runs", json={"pages": [True]}).status_code == 422
    add_page(ctx)
    response = start_run(ctx, pages=[2], profile_key="infrastructure-fake-v1")
    assert response["run"]["selected_pages"] == [2]
    assert response["attempts"][0]["unit_key"] == "SOURCE_PROBE:page:000002"
    assert execute(ctx, UUID(response["attempts"][0]["id"]))
    assert detail(ctx, response["run"]["id"])["run"]["status"] == "COMPLETED"


def test_unprocessed_unrelated_and_inherited_read_only_actions(execution_ctx):
    ctx = execution_ctx
    with ctx["factory"].begin() as session:
        processing = session.get(DocumentProcessingRun, ctx["src"]["processing"])
        processing.status = "RUNNING"
    assert client.post(ctx["base"] + "/runs", json={}).status_code == 409
    with ctx["factory"].begin() as session:
        session.get(DocumentProcessingRun, ctx["src"]["processing"]).status = "COMPLETED"
    rid = start_run(ctx)["run"]["id"]
    new = make_revision(
        ctx["project_id"],
        "next",
        based_on_revision_id=ctx["revision_id"],
        carry_forward_documents=True,
        activate=True,
    )
    assert new.status_code == 201, new.text
    # Old revision is now superseded and can still create document-scoped derived records.
    assert start_run(ctx)["run"]["id"] == rid
    with ctx["factory"]() as session:
        association = session.scalar(
            select(RevisionDocument).where(
                RevisionDocument.revision_id == UUID(new.json()["id"]),
                RevisionDocument.document_id == ctx["src"]["document"],
            )
        )
        path = (
            f"/api/projects/{ctx['project_id']}/revisions/{new.json()['id']}"
            f"/documents/{association.id}/extraction"
        )
    assert client.post(path + "/runs", json={}).json()["run"]["id"] == rid
    other = make_project()
    bad = ctx["base"].replace(ctx["project_id"], other)
    assert client.post(bad + f"/runs/{rid}/cancel").status_code == 404
    assert client.post(path + f"/runs/{uuid4()}/retry").status_code == 404


def test_duplicate_delivery_and_concurrent_claim_issue_one_call(execution_ctx):
    ctx = execution_ctx
    rid = start_run(ctx)["run"]["id"]
    uid = units(ctx, rid)[0]
    provider = FakeExtractionProvider(delay_seconds=0.1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(ctx, uid, provider), range(2)))
    assert sum(results) == 1 and len(provider.calls) == 1
    assert execute(ctx, uid, provider) is False
    assert detail(ctx, rid)["execution"]["calls_admitted"] == 1


def test_provider_call_has_no_open_database_transaction(execution_ctx):
    ctx = execution_ctx
    rid = start_run(ctx)["run"]["id"]
    with ctx["factory"]() as session:
        engine = session.get_bind()

    class Provider(FakeExtractionProvider):
        def execute(self, request):
            assert engine.pool.checkedout() == 0
            return super().execute(request)

    assert execute(ctx, units(ctx, rid)[0], Provider())
    with ctx["factory"]() as session:
        uid = units(ctx, rid)[0]
        started = session.get(UnitExecution, uid).provider_started_at
        call = session.scalar(select(ExtractionAICall).where(ExtractionAICall.work_unit_id == uid))
        assert call.started_at == started


def test_partial_failure_manual_retry_preserves_successful_key(execution_ctx):
    ctx = execution_ctx
    add_page(ctx)
    rid = start_run(ctx)["run"]["id"]
    a, b = units(ctx, rid)
    successful = FakeExtractionProvider()
    execute(ctx, a, successful)
    execute(ctx, b, FakeExtractionProvider("permanent"))
    partial = detail(ctx, rid)
    assert partial["run"]["status"] == "PARTIALLY_COMPLETED"
    assert partial["attempts"][1]["retryable"]
    assert start_run(ctx)["run"]["id"] == rid
    assert len(units(ctx, rid)) == 2
    response = client.post(ctx["base"] + f"/runs/{rid}/retry")
    assert response.status_code == 202, response.text
    attempt = UUID(response.json()["attempts"][-1]["id"])
    execute(ctx, attempt)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED" and len(done["attempts"]) == 3
    assert len(successful.calls) == 1
    assert done["attempts"][0]["id"] == str(a) and done["attempts"][1]["status"] == "FAILED"
    assert done["attempts"][2]["retry_of_work_unit_id"] == str(b)


def test_transient_backoff_and_exhaustion(execution_ctx):
    ctx = execution_ctx
    ctx["settings"].extraction_backoff_seconds = 1
    ctx["settings"].extraction_max_attempts = 2
    rid = start_run(ctx)["run"]["id"]

    class Unavailable:
        def execute(self, request):
            raise ProviderFailure(ErrorCode.UNAVAILABLE)

    execute(ctx, units(ctx, rid)[0], Unavailable())
    retry = units(ctx, rid)[1]
    assert not execute(ctx, retry, Unavailable())
    assert detail(ctx, rid)["run"]["status"] == "RUNNING"
    time.sleep(1.1)
    execute(ctx, retry, Unavailable())
    exhausted = detail(ctx, rid)
    assert exhausted["run"]["status"] == "FAILED" and len(exhausted["attempts"]) == 2
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 409


def test_worker_interruption_recovery_fences_old_attempt(execution_ctx):
    ctx = execution_ctx
    rid = start_run(ctx)["run"]["id"]
    uid = units(ctx, rid)[0]
    with pytest.raises(SimulatedWorkerInterruption):
        execute(ctx, uid, FakeExtractionProvider("interrupted"))
    with ctx["factory"]() as session:
        token = session.get(UnitExecution, uid).token
    expire(ctx, uid)
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).reconcile() >= 1
    retried = units(ctx, rid)[1]
    with ctx["factory"].begin() as session:
        with pytest.raises(LeaseLost):
            ExtractionCoordinator(session, ctx["settings"]).complete(
                uid, token, WorkUnitOutput(), ExecutionUsage(), ctx["storage"]
            )
    execute(ctx, retried)
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED"
    assert done["attempts"][0]["error_code"] == "WORKER_INTERRUPTED"
    assert done["execution"]["unreported_admissions"] == 1
    assert done["execution"]["estimated_cost_usd"] is None


def test_database_fence_rejects_unowned_and_expired_empty_publication(execution_ctx):
    ctx = execution_ctx
    rid = start_run(ctx)["run"]["id"]
    uid = units(ctx, rid)[0]
    with ctx["factory"].begin() as session:
        claim = ExtractionCoordinator(session, ctx["settings"]).claim(uid)
    with ctx["factory"]() as session:
        with pytest.raises(IntegrityError, match="lease does not authorize"):
            ExtractionPersistence(session).publish(uid, WorkUnitOutput())
        session.rollback()
    expire(ctx, uid)
    with ctx["factory"]() as session:
        session.execute(
            text("SELECT set_config('powerforge.extraction_lease_token', :token, true)"),
            {"token": str(claim.token)},
        )
        with pytest.raises(IntegrityError, match="lease does not authorize"):
            ExtractionPersistence(session).publish(uid, WorkUnitOutput())


def test_durable_dispatch_recovers_broker_failure_and_never_started_delivery(execution_ctx, caplog):
    ctx = execution_ctx
    ctx["delivery"].fail = True
    rid = start_run(ctx)["run"]["id"]
    assert "PRIVATE" not in caplog.text
    assert ctx["delivery"].ids == []
    time.sleep(1.1)
    ctx["delivery"].fail = False
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).dispatch(ctx["delivery"]) >= 1
    assert detail(ctx, rid)["run"]["status"] == "PENDING"
    time.sleep(1.1)
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).dispatch(ctx["delivery"]) >= 1
    assert ctx["delivery"].ids.count(units(ctx, rid)[0]) == 2
    execute(ctx, units(ctx, rid)[0])
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"


def test_heartbeat_keeps_slow_execution_owned(execution_ctx):
    ctx = execution_ctx
    ctx["settings"].extraction_lease_seconds = 3
    rid = start_run(ctx)["run"]["id"]
    uid = units(ctx, rid)[0]
    execute(ctx, uid, FakeExtractionProvider("slow", delay_seconds=3.2))
    with ctx["factory"]() as session:
        unit = session.get(ExtractionWorkUnit, uid)
        assert unit.status == "COMPLETED" and unit.heartbeat_at > unit.started_at


def test_cancellation_fences_inflight_preserves_committed_and_requires_reextract(execution_ctx):
    ctx = execution_ctx
    add_page(ctx)
    rid = start_run(ctx)["run"]["id"]
    a, b = units(ctx, rid)
    execute(ctx, a)
    began, finish = Event(), Event()

    class Paused(FakeExtractionProvider):
        def execute(self, request):
            began.set()
            assert finish.wait(5)
            return super().execute(request)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute, ctx, b, Paused())
        try:
            assert began.wait(5)
            cancelled = client.post(ctx["base"] + f"/runs/{rid}/cancel")
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["run"]["status"] == "CANCELLED"
            assert client.post(ctx["base"] + f"/runs/{rid}/cancel").status_code == 200
        finally:
            finish.set()
        assert future.result(timeout=10) is False
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 1
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 409
    new = start_run(ctx, mode="reextract")
    assert new["run"]["reextracts_run_id"] == rid


def test_cancel_pending_and_completed_conflict(execution_ctx):
    ctx = execution_ctx
    rid = start_run(ctx)["run"]["id"]
    assert client.post(ctx["base"] + f"/runs/{rid}/cancel").json()["run"]["status"] == "CANCELLED"
    assert not execute(ctx, units(ctx, rid)[0])
    assert start_run(ctx)["run"]["id"] == rid
    new = start_run(ctx, mode="reextract")["run"]["id"]
    execute(ctx, units(ctx, new)[0])
    assert client.post(ctx["base"] + f"/runs/{new}/cancel").status_code == 409


def test_call_budget_partial_and_limits_are_pinned(execution_ctx):
    ctx = execution_ctx
    add_page(ctx)
    ctx["settings"].extraction_max_calls = 1
    rid = start_run(ctx)["run"]["id"]
    ctx["settings"].extraction_max_calls = 50
    a, b = units(ctx, rid)
    execute(ctx, a)
    assert not execute(ctx, b)
    result = detail(ctx, rid)
    assert result["run"]["status"] == "PARTIALLY_COMPLETED"
    assert result["execution"]["call_budget"] == 1
    assert result["attempts"][1]["error_code"] == "CALL_BUDGET_EXHAUSTED"
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 409


@pytest.mark.parametrize(
    "scenario,expected", [("empty", "COMPLETED"), ("invalid", "FAILED"), ("permanent", "FAILED")]
)
def test_fake_outcomes_and_usage_are_honest(execution_ctx, scenario, expected):
    ctx = execution_ctx
    rid = start_run(ctx)["run"]["id"]
    execute(ctx, units(ctx, rid)[0], FakeExtractionProvider(scenario))
    result = detail(ctx, rid)
    assert result["run"]["status"] == expected
    assert start_run(ctx)["run"]["id"] == rid
    assert result["execution"]["reported_calls"] == 1
    assert result["execution"]["estimated_cost_usd"] is None
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 0


def test_concurrency_admission_releases_slot_after_commit(execution_ctx):
    ctx = execution_ctx
    ctx["settings"].extraction_max_concurrent_global = 1
    add_page(ctx)
    rid = start_run(ctx)["run"]["id"]
    a, b = units(ctx, rid)
    with ctx["factory"].begin() as session:
        owned = ExtractionCoordinator(session, ctx["settings"]).claim(a)
        assert owned is not None
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).claim(b) is None
    with ctx["factory"].begin() as session:
        service = ExtractionCoordinator(session, ctx["settings"])
        service.mark_provider_started(a, owned.token)
        service.complete(a, owned.token, WorkUnitOutput(), ExecutionUsage(), ctx["storage"])
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).claim(b) is not None


def test_external_revocation_before_claim_never_invokes_adapter(execution_ctx):
    ctx = execution_ctx
    ctx["settings"].extraction_external_enabled = True
    rid = start_run(ctx, profile_key="infrastructure-openai-v1")["run"]["id"]
    ctx["settings"].extraction_external_enabled = False
    provider = FakeExtractionProvider()
    assert not execute(ctx, units(ctx, rid)[0], provider)
    result = detail(ctx, rid)
    assert result["run"]["status"] == "FAILED" and not provider.calls
    assert result["execution"]["calls_admitted"] == 0


def test_known_pricing_basis_has_exact_cost_and_probe_has_no_engineering_candidates(execution_ctx):
    from decimal import Decimal

    ctx = execution_ctx
    ctx["settings"].extraction_external_enabled = True
    ctx["settings"].extraction_pricing_basis = "fixture-flat-input-and-output-v1"
    ctx["settings"].extraction_input_usd_per_million = Decimal("2")
    ctx["settings"].extraction_output_usd_per_million = Decimal("3")
    rid = start_run(ctx, profile_key="infrastructure-openai-v1")["run"]["id"]
    # Inject a provider double; no external call is made.
    execute(ctx, units(ctx, rid)[0], FakeExtractionProvider())
    result = detail(ctx, rid)
    assert result["execution"]["estimated_cost_usd"] == "0.000098"
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 0
    with ctx["factory"]() as session:
        call = session.scalar(select(ExtractionAICall).where(ExtractionAICall.run_id == UUID(rid)))
        assert call.pricing_basis == "fixture-flat-input-and-output-v1"


def test_image_fallback_limits_and_no_fabricated_observations(execution_ctx):
    import hashlib
    from io import BytesIO

    from PIL import Image

    from powerforge_document_processing.models import PageArtifact

    ctx = execution_ctx
    content = BytesIO()
    Image.new("RGB", (20, 20), "white").save(content, format="PNG")
    data = content.getvalue()
    with ctx["factory"].begin() as session:
        processing = DocumentProcessingRun(
            document_id=ctx["src"]["document"],
            processor_version="image-v2",
            profile_version="v2",
            profile_hash="image",
            status="COMPLETED",
        )
        session.add(processing)
        session.flush()
        key = f"processing/{processing.id}/analysis.png"
        session.add(
            PageArtifact(
                document_page_id=ctx["src"]["page"],
                processing_run_id=processing.id,
                artifact_type="ANALYSIS_IMAGE",
                storage_key=key,
                mime_type="image/png",
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                width_px=20,
                height_px=20,
            )
        )
        ctx["storage"].put(key, BytesIO(data), len(data), "image/png")
    ctx["settings"].extraction_max_image_pixels = 10
    assert client.post(ctx["base"] + "/runs", json={}).status_code == 422
    ctx["settings"].extraction_max_image_pixels = 1000
    ctx["settings"].extraction_max_input_bytes = 1
    assert client.post(ctx["base"] + "/runs", json={}).status_code == 422
    ctx["settings"].extraction_max_input_bytes = 2000
    rid = start_run(ctx)["run"]["id"]
    execute(ctx, units(ctx, rid)[0])
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 0


def test_ungrounded_provider_quote_is_invalid_and_preserves_usage(execution_ctx):
    from powerforge_ai.extraction import ExtractionResponse, ProbeResult

    ctx = execution_ctx
    rid = start_run(ctx)["run"]["id"]

    class Ungrounded:
        def execute(self, request):
            return ExtractionResponse(
                result=ProbeResult(acknowledged=True, excerpt="not in the source"),
                usage=ExecutionUsage(input_tokens=10, output_tokens=5),
            )

    execute(ctx, units(ctx, rid)[0], Ungrounded())
    result = detail(ctx, rid)
    assert result["run"]["status"] == "FAILED"
    assert result["attempts"][0]["error_code"] == "INVALID_PROVIDER_RESPONSE"
    assert result["execution"]["input_tokens"] == 10
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 0


def test_action_payload_allowlists_reject_forged_controls(execution_ctx):
    ctx = execution_ctx
    rid = start_run(ctx)["run"]["id"]
    assert client.post(ctx["base"] + "/runs", json={"provider": "openai"}).status_code == 422
    assert client.post(ctx["base"] + f"/runs/{rid}/cancel", json={"force": True}).status_code == 422
    assert (
        client.post(ctx["base"] + f"/runs/{rid}/retry", json={"token": str(uuid4())}).status_code
        == 422
    )


def test_reextract_with_changed_profile_links_prior_completed_run(execution_ctx):
    ctx = execution_ctx
    prior = start_run(ctx)["run"]["id"]
    execute(ctx, units(ctx, prior)[0])
    ctx["settings"].extraction_external_enabled = True
    new = start_run(ctx, profile_key="infrastructure-openai-v1", mode="reextract")
    assert new["run"]["id"] != prior
    assert new["run"]["reextracts_run_id"] == prior
    assert new["run"]["provider"] == "openai"
    assert new["execution"]["calls_admitted"] == 0  # No external adapter was invoked.
