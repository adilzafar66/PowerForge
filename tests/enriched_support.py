"""Actual source preparation/layout followed by the supported enhanced request path."""

from uuid import UUID

from documents_support import client
from enrichment_support import detail, start
from extraction_worker.extraction_tasks import provider_for
from powerforge_extraction.execution import execute_unit
from test_spatial_execution import run_unit, stage


def enrich(ctx, **overrides):
    pending = start(ctx, profile_key="source-layout-v1", **overrides)
    run_unit(ctx, stage(pending, "SOURCE_PREPARE"))
    run_unit(ctx, stage(pending, "SPATIAL_LAYOUT"))
    source = detail(ctx, pending["run"]["id"])
    assert source["run"]["status"] == "COMPLETED", source
    return dict(
        prepared_result_id=source["results"][0]["id"],
        spatial_result_id=source["spatial_results"][0]["id"],
    )


def start_enriched(ctx, binding, profile="tables-test-enriched-v1", **overrides):
    response = client.post(
        ctx["base"] + "/extraction/runs",
        json=dict(profile_key=profile, pages=[1], enrichment_bindings=[binding], **overrides),
    )
    assert response.status_code == 202, response.text
    return response.json()


def extraction_detail(ctx, run_id):
    response = client.get(ctx["base"] + f"/extraction/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def execute(ctx, unit_id, provider=None):
    return execute_unit(
        UUID(str(unit_id)),
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        (lambda claim: provider) if provider else provider_for,
    )


def finish(ctx, pending, provider=None):
    rid = pending["run"]["id"]
    for attempt in pending["attempts"]:
        if attempt["stage"] in ("EQUIPMENT_RECOGNITION", "TABLE_RECONSTRUCTION"):
            execute(ctx, attempt["id"], provider)
    current = extraction_detail(ctx, rid)
    for attempt in current["attempts"]:
        if attempt["status"] == "PENDING":
            execute(ctx, attempt["id"], provider)
    return extraction_detail(ctx, rid)
