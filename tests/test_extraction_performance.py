import json
from uuid import uuid4

import httpx
import openai
import pytest
from pydantic import ValidationError

from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_ai.extraction import ExtractionRequest, ProviderFailure
from powerforge_extraction import performance
from powerforge_extraction.extraction_profile import PROMPTS, RESPONSES, extraction_profile
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.stage_contracts import stage_schema_version
from powerforge_shared.config import Settings


def test_failed_phase_uses_monotonic_time_and_leaves_unreached_phases_null(monkeypatch):
    values = iter((20_000_000, 24_900_000, 25_000_000, 32_000_000))
    monkeypatch.setattr(performance.time, "perf_counter_ns", lambda: next(values))
    metrics = performance.AttemptPerformance()
    token = performance.active_performance.set(metrics)
    try:
        with performance.measure("request_build"):
            pass
        with pytest.raises(ValueError), performance.measure("provider_call"):
            raise ValueError("private request")
    finally:
        performance.active_performance.reset(token)
    assert metrics.request_build_ms == 4 and metrics.provider_call_ms == 7
    assert metrics.failure_stage == "provider_call" and metrics.admission_ms is None
    with pytest.raises(ValidationError):
        performance.AttemptPerformance.model_validate({"source_text": "private request"})
    with pytest.raises(ValidationError):
        performance.AttemptPerformance(provider_call_ms=-1)


@pytest.mark.parametrize("status", ["completed", "incomplete"])
@pytest.mark.parametrize("effort", ["medium", "low", "none"])
def test_request_metrics_match_http_body_and_exclude_content(status, effort):
    private = 'private OCR text Ω "quote"'
    settings = Settings(
        _env_file=None,
        extraction_external_enabled=True,
        extraction_attribute_reasoning_effort=effort,
    )
    profile = extraction_profile(settings)
    stage = "ATTRIBUTE_EXTRACTION"
    data = {
        "page": {
            "image_width": 10,
            "image_height": 20,
            "readings": {"rows": [["q1", private, "OCR", ["alt"], ["AMBIGUOUS_OVERLAP"]]]},
            "layout": {
                "tables": [{"cells": [{}]}],
                "order": {"rows": []},
                "overlaps": [{"kind": "AMBIGUOUS"}],
            },
        },
        "attribute_catalog": [{"equipment_type": "BUS"}],
        "upstream": {"equipment": [{"source_description": private}]},
    }
    request = ExtractionRequest(
        work_unit_id=uuid4(),
        unit_key="ATTRIBUTE_EXTRACTION:page:000001",
        attempt_number=1,
        model=profile.model,
        instructions=PROMPTS[stage],
        schema_version=stage_schema_version(stage),
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        text=canonical_json(data),
        image=b"image",
        image_mime_type="image/png",
        image_detail="high",
        stage=stage,
        response_model=RESPONSES[stage],
        reasoning_effort=profile.reasoning_effort_for(stage),
    )
    sizes = []

    def respond(req):
        sizes.append(len(req.content))
        assert json.loads(req.content)["reasoning"] == {"effort": effort}
        return httpx.Response(
            200,
            json=dict(
                status=status,
                output=[
                    dict(
                        type="message",
                        content=[
                            dict(type="output_text", text='{"attributes":[],"raw_unmapped":[]}')
                        ],
                    )
                ],
            ),
        )

    metrics = performance.AttemptPerformance()
    token = performance.active_performance.set(metrics)
    try:
        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            sdk = openai.OpenAI(api_key="test", max_retries=0, http_client=http)
            provider = OpenAIExtractionProvider(settings, profile, sdk)
            foreign_effort = "medium" if effort != "medium" else "low"
            with pytest.raises(ProviderFailure, match="INVALID_SOURCE_INPUT"):
                provider.execute(request.model_copy(update={"reasoning_effort": foreign_effort}))
            assert not sizes
            if status == "incomplete":
                with pytest.raises(ProviderFailure):
                    provider.execute(request)
            else:
                assert provider.execute(request).usage.output_tokens is None
    finally:
        performance.active_performance.reset(token)
    assert metrics.response_status == status
    assert metrics.request.body_bytes == sizes[0]
    assert metrics.request.encoded_image_bytes == 8
    assert metrics.request.ocr_readings == 1 and metrics.request.native_readings == 0
    assert metrics.request.reading_text_chars == len(private) + 3
    assert metrics.request.alternate_readings == metrics.request.conflicting_overlap_count == 1
    assert metrics.request.cell_count == 1
    assert metrics.reasoning_tokens is None and metrics.visible_output_tokens is None
    assert len(metrics.model_dump_json()) < 4096
    assert private not in metrics.model_dump_json()
