"""Separate prose/table runs keep their results and historical evidence behind one summary."""

import pytest

from documents_support import client
from engineering_execution_support import StageProvider, processing, start_engineering
from extraction_execution_support import detail, execute
from powerforge_ai.extraction import ErrorCode, ProviderFailure
from table_execution_support import TableProvider, attempt, start_tables
from table_execution_support import execution_ctx as execution_ctx
from table_execution_support import table_ctx as table_ctx
from table_grounding_support import schedule
from test_extraction_celery_integration import wait_for

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "tables_first,state",
    [
        (False, "completed"),
        (False, "partial"),
        (False, "empty"),
        (False, "pending"),
        (False, "cancelled"),
        (True, "completed"),
    ],
)
def test_cross_profile_summary_history_pagination_and_signed_older_evidence(
    table_ctx, tables_first, state
):
    ctx = table_ctx
    _, text = schedule()
    processing(ctx, native="2-Winding Transformer TX-1\nSecondary Voltage: 600 V\n\n" + text)

    def prose():
        rid = start_engineering(ctx)["run"]["id"]
        provider = StageProvider()
        for stage in ["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"]:
            # Start/claim use database availability timestamps. History assertions
            # should wait for admission readiness, rather than require same-tick dispatch.
            wait_for(
                lambda stage=stage: execute(ctx, attempt(ctx, rid, stage), provider), seconds=5
            )
        return rid

    def tables():
        rid = start_tables(ctx)["run"]["id"]
        if state not in {"pending", "cancelled"}:
            provider = TableProvider(
                empty=state == "empty",
                failure=lambda req: (
                    ProviderFailure(ErrorCode.AUTH)
                    if state == "partial" and req.stage == "TABLE_INTERPRETATION"
                    else None
                ),
            )
            for stage in ["TABLE_RECONSTRUCTION", "TABLE_INTERPRETATION"]:
                wait_for(
                    lambda stage=stage: execute(ctx, attempt(ctx, rid, stage), provider), seconds=5
                )
        if state == "cancelled":
            assert client.post(ctx["base"] + f"/runs/{rid}/cancel").status_code == 200
        return rid

    older = tables() if tables_first else prose()
    old_candidates = client.get(ctx["base"] + f"/runs/{older}/candidates").json()["items"]
    assert len(old_candidates) == 2
    old_evidence = old_candidates[0]["evidence"][0]["evidence"]["id"]
    before = client.get(ctx["base"] + f"/evidence/{old_evidence}").json()
    newer = prose() if tables_first else tables()
    summary = client.get(ctx["base"]).json()
    expected_latest = older if state in {"pending", "cancelled"} else newer
    assert summary["current_run"]["id"] == newer
    assert summary["latest_result"]["id"] == expected_latest
    page1 = client.get(ctx["base"] + "/runs?limit=1&offset=0").json()
    page2 = client.get(ctx["base"] + "/runs?limit=1&offset=1").json()
    assert page1["total"] == page2["total"] == 2
    assert [page1["items"][0]["id"], page2["items"][0]["id"]] == [newer, older]
    assert client.get(ctx["base"] + f"/runs/{older}/candidates").json()["items"] == old_candidates
    after = client.get(ctx["base"] + f"/evidence/{old_evidence}").json()
    assert before["page_artifact_id"] == after["page_artifact_id"] and after["artifact_url"]
    if state == "partial":
        result = detail(ctx, newer)
        assert (
            result["run"]["status"] == "PARTIALLY_COMPLETED" and not result["coverage"]["complete"]
        )
        assert client.get(ctx["base"] + f"/runs/{newer}/tables").json()["total"] == 1
