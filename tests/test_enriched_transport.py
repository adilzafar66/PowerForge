"""Actual production Responses adapter with controlled transport, never paid calls."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from documents_support import client
from enriched_support import enrich, finish, start_enriched
from enrichment_support import build_source
from enrichment_support import enrichment_ctx as enrichment_ctx
from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.enriched_observations import RESPONSES, SCHEMAS

pytestmark = pytest.mark.integration


class ModelTransport:
    def __init__(self):
        self.responses = self
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        stage = next(s for s, model in RESPONSES.items() if model is kwargs["text_format"])
        messages = kwargs["input"]
        source = json.loads(messages[0]["content"][0]["text"])
        assert source["untrusted"] is True
        upstream = (
            json.loads(messages[1]["content"][0]["text"])["observations"]
            if len(messages) == 2
            else None
        )
        request = SimpleNamespace(
            stage=stage,
            text=json.dumps(source["source"]),
            upstream_context=json.dumps(upstream) if upstream is not None else None,
            schema_version=SCHEMAS[stage],
            response_model=kwargs["text_format"],
        )
        result = FakeEnrichedProvider().execute(request).result
        return SimpleNamespace(
            status="completed",
            output_parsed=result,
            output=[],
            usage=SimpleNamespace(input_tokens=20, output_tokens=30),
        )


@pytest.mark.parametrize("table", [False, True])
def test_supported_production_profiles_run_two_bounded_calls_with_mocked_transport(
    enrichment_ctx, table
):
    from test_enriched_grounding import prose_pdf

    ctx = enrichment_ctx
    payload = (
        Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes()
        if table
        else prose_pdf(["2-Winding Transformer TX-1", "Secondary Voltage: 600 V"])
    )
    build_source(ctx, payload, "production.pdf")
    binding = enrich(ctx)
    ctx["settings"].extraction_external_enabled = True
    profile = "tables-openai-enriched-v1" if table else "engineering-openai-enriched-v1"
    pending = start_enriched(ctx, binding, profile=profile)
    transport = ModelTransport()

    # Exercise the actual production adapter/parse path; only external I/O is controlled.
    class BoundProvider:
        def execute(self, request):
            from powerforge_extraction.controls import RunExecution
            from powerforge_extraction.models import ExtractionWorkUnit
            from powerforge_extraction.profiles import read_profile

            with ctx["factory"]() as session:
                unit = session.get(ExtractionWorkUnit, request.work_unit_id)
                pinned = read_profile(session.get(RunExecution, unit.run_id).configuration)
            return OpenAIExtractionProvider(
                ctx["settings"], client=transport, profile=pinned
            ).execute(request)

    done = finish(ctx, pending, BoundProvider())
    assert done["run"]["status"] == "COMPLETED", done
    assert len(transport.calls) == 2 and done["execution"]["reported_calls"] == 2
    for call in transport.calls:
        assert call["store"] is False
        assert call["max_output_tokens"] <= 32768
        assert "TX-1" not in call["instructions"]
        assert call["input"][0]["content"][-1]["type"] == "input_image"
    rid = done["run"]["id"]
    values = client.get(ctx["base"] + f"/extraction/runs/{rid}/candidates").json()["items"]
    assert any(
        c["mapping_status"] == "MAPPED" and c["attribute_key"] == "secondary_voltage"
        for c in values
    )
    assert all(not c["diagnostics"].get("synthetic") for c in values)
    assert all(c["diagnostics"]["printed_text_independently_verified"] is False for c in values)
