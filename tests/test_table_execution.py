"""Fixed two-stage table execution through real admission, fences and PostgreSQL publication."""

import json
from uuid import UUID

import pytest
from sqlalchemy import select

from documents_support import client
from extraction_execution_support import detail, expire
from extraction_execution_support import execute as execute_once
from powerforge_ai.extraction import ErrorCode, ProviderFailure
from powerforge_extraction.controls import RunExecution, UnitExecution
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.models import ExtractionAICall, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from table_execution_support import TableProvider, attempt, claim_ready, execute, start_tables
from table_execution_support import execution_ctx as execution_ctx
from table_execution_support import table_ctx as table_ctx

pytestmark = pytest.mark.integration
R, INTERPRET = "TABLE_RECONSTRUCTION", "TABLE_INTERPRETATION"


def test_table_plan_gates_interpretation_and_publishes_reconstruction_first(table_ctx):
    ctx = table_ctx
    rid = start_tables(ctx)["run"]["id"]
    r, i = attempt(ctx, rid, R), attempt(ctx, rid, INTERPRET)
    provider = TableProvider()
    assert execute_once(ctx, i, provider) is False
    assert detail(ctx, rid)["execution"]["calls_admitted"] == 0
    assert execute(ctx, r, provider)
    assert client.get(ctx["base"] + f"/runs/{rid}/tables").json()["total"] == 1
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 0
    assert execute(ctx, i, provider)
    assert not execute(ctx, i, provider)
    result = detail(ctx, rid)
    assert result["run"]["status"] == "COMPLETED"
    assert result["execution"]["calls_admitted"] == result["execution"]["reported_calls"] == 2
    context = json.loads(provider.requests[1].upstream_context)
    assert context["version"] == "committed-table-context-v1"
    assert context["tables"][0]["structure_basis"] == "NATIVE_DELIMITED"
    assert context["tables"][0]["cell_text_basis"]["c1_3"] == "NATIVE_VERIFIED"
    assert "producer_unit_id" not in provider.requests[1].upstream_context
    values = client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["items"]
    assert values[-1]["numeric_value"] == "0.6" or values[0]["numeric_value"] == "0.6"
    with ctx["factory"]() as session:
        calls = list(
            session.scalars(select(ExtractionAICall).where(ExtractionAICall.run_id == UUID(rid)))
        )
        assert any(f"upstream:{r}" in c.request_correlation_id for c in calls)


def test_empty_table_interpretation_is_admitted_fenced_and_skips_provider(table_ctx):
    ctx = table_ctx
    rid = start_tables(ctx)["run"]["id"]
    provider = TableProvider(empty=True)
    execute(ctx, attempt(ctx, rid, R), provider)
    i = attempt(ctx, rid, INTERPRET)

    def forbidden(_):
        raise AssertionError("Empty interpretation must not construct a provider")

    from test_extraction_celery_integration import wait_for

    wait_for(
        lambda: execute_unit(i, ctx["factory"], ctx["storage"], ctx["settings"], forbidden),
        seconds=5,
    )
    result = detail(ctx, rid)
    assert result["run"]["status"] == "COMPLETED"
    assert result["execution"]["calls_admitted"] == 2 and result["execution"]["reported_calls"] == 1
    with ctx["factory"]() as session:
        unit = session.get(ExtractionWorkUnit, i)
        assert unit.output_counts["skipped_empty_tables"] == 1
        assert session.get(UnitExecution, i).provider_started_at is None
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "stage,code",
    [(R, ErrorCode.AUTH), (INTERPRET, ErrorCode.AUTH), (INTERPRET, ErrorCode.UNAVAILABLE)],
)
def test_table_failures_keep_outputs_and_retry_only_unsuccessful_stage(table_ctx, stage, code):
    ctx = table_ctx
    rid = start_tables(ctx)["run"]["id"]
    provider = TableProvider(
        failure=lambda request: (
            ProviderFailure(code)
            if request.stage == stage and request.attempt_number == 1
            else None
        )
    )
    execute(ctx, attempt(ctx, rid, R), provider)
    if stage == INTERPRET:
        execute(ctx, attempt(ctx, rid, INTERPRET), provider)
    result = detail(ctx, rid)
    if code == ErrorCode.AUTH:
        assert result["run"]["status"] == ("FAILED" if stage == R else "PARTIALLY_COMPLETED")
        response = client.post(ctx["base"] + f"/runs/{rid}/retry")
        assert response.status_code == 202, response.text
    if stage == R:
        assert execute(ctx, attempt(ctx, rid, R), provider)
    assert execute(ctx, attempt(ctx, rid, INTERPRET), provider)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
    assert client.get(ctx["base"] + f"/runs/{rid}/tables").json()["total"] == 1
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 2
    if stage == INTERPRET:
        assert sum(r.stage == R for r in provider.requests) == 1
        assert provider.requests[1].upstream_context == provider.requests[2].upstream_context


def test_table_budget_failure_keeps_reconstruction_inspectable(table_ctx):
    ctx = table_ctx
    ctx["settings"].extraction_max_calls = 1
    rid = start_tables(ctx)["run"]["id"]
    provider = TableProvider()
    execute(ctx, attempt(ctx, rid, R), provider)
    assert execute(ctx, attempt(ctx, rid, INTERPRET), provider) is False
    result = detail(ctx, rid)
    assert result["run"]["status"] == "PARTIALLY_COMPLETED"
    assert len(provider.requests) == 1
    assert client.get(ctx["base"] + f"/runs/{rid}/tables").json()["total"] == 1


def test_empty_skip_also_obeys_original_admission_budget(table_ctx):
    ctx = table_ctx
    ctx["settings"].extraction_max_calls = 1
    rid = start_tables(ctx)["run"]["id"]
    provider = TableProvider(empty=True)
    execute(ctx, attempt(ctx, rid, R), provider)
    assert not execute(ctx, attempt(ctx, rid, INTERPRET), provider)
    assert detail(ctx, rid)["run"]["status"] == "PARTIALLY_COMPLETED"


@pytest.mark.parametrize("expired_stage", [R, INTERPRET])
def test_expired_table_attempts_recover_with_prerequisite_reuse(table_ctx, expired_stage):
    ctx = table_ctx
    rid = start_tables(ctx)["run"]["id"]
    provider = TableProvider()
    if expired_stage == INTERPRET:
        execute(ctx, attempt(ctx, rid, R), provider)
    lost = attempt(ctx, rid, expired_stage)
    assert claim_ready(ctx, lost)
    expire(ctx, lost)
    with ctx["factory"].begin() as session:
        assert ExtractionCoordinator(session, ctx["settings"]).reconcile() >= 1
    execute(ctx, attempt(ctx, rid, expired_stage), provider)
    if expired_stage == R:
        execute(ctx, attempt(ctx, rid, INTERPRET), provider)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"


def test_cancellation_fences_table_output_after_provider_boundary(table_ctx):
    ctx = table_ctx
    rid = start_tables(ctx)["run"]["id"]

    def cancel(request):
        if request.stage == INTERPRET:
            assert client.post(ctx["base"] + f"/runs/{rid}/cancel").status_code == 200

    provider = TableProvider(on_call=cancel)
    execute(ctx, attempt(ctx, rid, R), provider)
    assert not execute(ctx, attempt(ctx, rid, INTERPRET), provider)
    assert detail(ctx, rid)["run"]["status"] == "CANCELLED"
    assert client.get(ctx["base"] + f"/runs/{rid}/tables").json()["total"] == 1
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 0


@pytest.mark.parametrize("family", ["v1", "v2", "v3"])
def test_pre_table_pinned_active_profiles_still_claim_retry_and_publish(
    table_ctx, monkeypatch, family
):
    from pathlib import Path

    from engineering_execution_support import StageProvider, processing
    from powerforge_extraction import orchestration
    from powerforge_extraction.fake import FakeExtractionProvider
    from powerforge_extraction.profiles import engineering_profile, read_profile
    from powerforge_shared.config import Settings

    ctx = table_ctx
    processing(ctx, native="2-Winding Transformer TX-1\nSecondary Voltage: 600 V")
    root = Path(__file__).parent / "fixtures/extraction"
    if family == "v2":
        legacy = json.loads((root / "legacy_source_probe_v1.json").read_text())
        profile = engineering_profile(
            "engineering-test-v1", Settings(_env_file=None, **legacy["settings"])
        )
        assert (
            profile.identity_hash
            == json.loads((root / "engineering_execution_v1_identity.json").read_text())[
                "profiles"
            ][profile.key]
        )
    else:
        fixture = (
            "legacy_source_probe_v1.json"
            if family == "v1"
            else "engineering_production_v1_identity.json"
        )
        key = "infrastructure-fake-v1" if family == "v1" else "engineering-openai-v1"
        snapshot = json.loads((root / fixture).read_text())["profiles"][key]
        profile = read_profile(json.loads(snapshot["wire_json"]))
        assert profile.model_dump_json() == snapshot["wire_json"]
    ctx["settings"].extraction_external_enabled = True
    monkeypatch.setattr(orchestration, "resolve_profile", lambda *args: profile)
    rid = start_tables(ctx, profile_key=profile.key)["run"]["id"]
    if family == "v1":
        target = attempt(ctx, rid, "SOURCE_PROBE")

        class FailOnce:
            def execute(self, request):
                if request.attempt_number == 1:
                    raise ProviderFailure(ErrorCode.AUTH)
                return FakeExtractionProvider().execute(request)

        provider = FailOnce()
    else:
        execute(ctx, attempt(ctx, rid, "EQUIPMENT_RECOGNITION"), StageProvider())
        target = attempt(ctx, rid, "ATTRIBUTE_EXTRACTION")
        provider = StageProvider(
            failure=lambda req: ProviderFailure(ErrorCode.AUTH) if req.attempt_number == 1 else None
        )
    assert execute(ctx, target, provider)
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 202
    stage = "SOURCE_PROBE" if family == "v1" else "ATTRIBUTE_EXTRACTION"
    assert execute(ctx, attempt(ctx, rid, stage), provider)
    assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
    with ctx["factory"]() as session:
        assert session.get(RunExecution, UUID(rid)).configuration == profile.model_dump(mode="json")


@pytest.mark.parametrize(
    "limit",
    ["max_text_chars", "max_instruction_bytes", "max_upstream_bytes", "runtime", "schema_hash"],
)
def test_table_pinned_limits_fail_without_provider_calls_or_probe_fallback(
    table_ctx, monkeypatch, limit
):
    from powerforge_extraction import orchestration
    from powerforge_extraction.table_profiles import TABLE_TEST_PROFILE, table_profile

    ctx = table_ctx
    profile = table_profile(TABLE_TEST_PROFILE, ctx["settings"])
    value = (
        {"version": "future"} if limit == "runtime" else "future" if limit == "schema_hash" else 1
    )
    profile = profile.model_copy(update={limit: value})
    monkeypatch.setattr(orchestration, "resolve_profile", lambda *args: profile)
    rid = start_tables(ctx)["run"]["id"]
    provider = TableProvider()
    execute(ctx, attempt(ctx, rid, R), provider)
    if limit == "max_upstream_bytes":
        execute(ctx, attempt(ctx, rid, INTERPRET), provider)
    assert len(provider.requests) == (1 if limit == "max_upstream_bytes" else 0)
    assert detail(ctx, rid)["run"]["status"] == (
        "PARTIALLY_COMPLETED" if limit == "max_upstream_bytes" else "FAILED"
    )


def test_empty_skip_cannot_complete_an_unclaimed_or_nonempty_interpretation(table_ctx):
    from uuid import uuid4

    from powerforge_extraction.errors import LeaseLost

    ctx = table_ctx
    rid = start_tables(ctx)["run"]["id"]
    unit = attempt(ctx, rid, INTERPRET)
    with ctx["factory"].begin() as session:
        with pytest.raises(LeaseLost):
            ExtractionCoordinator(session, ctx["settings"]).complete_empty_table(
                unit, uuid4(), ctx["storage"]
            )
    execute(ctx, attempt(ctx, rid, R), TableProvider())
    claim = claim_ready(ctx, unit)
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        with pytest.raises(ValueError, match="Nonempty"):
            coordinator.complete_empty_table(unit, claim.token, ctx["storage"])
        assert session.get(UnitExecution, unit).provider_started_at is None


def test_table_discovery_opt_in_and_existing_fake_default_remain_explicit(table_ctx):
    from powerforge_extraction.table_profiles import TABLE_PRODUCTION_PROFILES

    ctx = table_ctx
    profiles = client.get(ctx["base"] + "/profiles").json()["items"]
    tables = [p for p in profiles if p["key"] in TABLE_PRODUCTION_PROFILES]
    assert len(tables) == 2 and all(p["production_extractor"] and not p["enabled"] for p in tables)
    for key in TABLE_PRODUCTION_PROFILES:
        assert client.post(ctx["base"] + "/runs", json={"profile_key": key}).status_code == 409
    ctx["settings"].extraction_external_enabled = True
    for key in TABLE_PRODUCTION_PROFILES:
        result = start_tables(ctx, profile_key=key)
        assert result["run"]["profile_version"] == "execution-profile-v4"
        assert result["execution"]["execution_kind"] == "TABLE_EXTRACTION"
        assert len(result["attempts"]) == 2 and result["execution"]["calls_admitted"] == 0
    assert (
        client.post(ctx["base"] + "/runs", json={}).json()["execution"]["profile_key"]
        == "infrastructure-fake-v1"
    )


def test_exhausted_table_reconstruction_blocks_interpretation_without_admission(table_ctx):
    ctx = table_ctx
    ctx["settings"].extraction_max_attempts = 1
    rid = start_tables(ctx)["run"]["id"]
    provider = TableProvider(failure=lambda request: ProviderFailure(ErrorCode.UNAVAILABLE))
    execute(ctx, attempt(ctx, rid, R), provider)
    result = detail(ctx, rid)
    assert result["run"]["status"] == "FAILED"
    assert result["execution"]["calls_admitted"] == 1 and len(provider.requests) == 1
    blocked = next(u for u in result["attempts"] if u["stage"] == INTERPRET)
    assert blocked["status"] == "FAILED" and blocked["error_code"] == "PREREQUISITE_FAILED"
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 409


def test_table_sources_and_request_rendering_run_outside_metadata_transaction(
    table_ctx, monkeypatch
):
    from sqlalchemy import event

    from powerforge_extraction.table_execution import table_request
    from powerforge_extraction.table_stages import TableStage

    ctx = table_ctx
    rid = start_tables(ctx)["run"]["id"]
    execute(ctx, attempt(ctx, rid, R), TableProvider())
    claim = claim_ready(ctx, attempt(ctx, rid, INTERPRET))
    active = set()

    def began(session, transaction, connection):
        active.add(session)

    def ended(session, transaction):
        if transaction.parent is None:
            active.discard(session)

    original_render = TableStage.render_instructions
    original_get = ctx["storage"].get

    def render(stage):
        assert not active, "Request rendering held a metadata transaction"
        return original_render(stage)

    def get(key):
        assert not active, "Source object I/O held a metadata transaction"
        return original_get(key)

    monkeypatch.setattr(TableStage, "render_instructions", render)
    monkeypatch.setattr(ctx["storage"], "get", get)
    event.listen(ctx["factory"].class_, "after_begin", began)
    event.listen(ctx["factory"].class_, "after_transaction_end", ended)
    try:
        request, _, context = table_request(claim, ctx["storage"], ctx["factory"])
        assert request.stage == INTERPRET and len(context.tables) == 1 and not active
    finally:
        event.remove(ctx["factory"].class_, "after_begin", began)
        event.remove(ctx["factory"].class_, "after_transaction_end", ended)
