"""Exercise the live adapter using the installed SDK and an in-process HTTP transport."""

import json
from uuid import uuid4

import httpx
import openai
import pytest

from extraction_worker.openai_phase6r import OpenAIPhase6RProvider
from powerforge_ai.extraction import ErrorCode, ExtractionRequest, ProviderFailure
from powerforge_extraction.phase6r_profile import PROMPTS, RESPONSES, STAGES, phase6r_profile
from powerforge_shared.config import Settings


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("outcome", ["success", "incomplete", "refusal", "invalid"])
def test_responses_transport_is_bounded_and_retains_measured_usage(stage, outcome):
    settings = Settings(_env_file=None, extraction_external_enabled=True)
    profile = phase6r_profile(settings)
    payload = {
        "version": "phase-6r-v1",
        "stage": stage,
        "page_context_hash": "a" * 64,
        **(
            {"equipment": []}
            if stage == STAGES[0]
            else {
                "upstream_hash": "b" * 64,
                "attributes": [],
                "raw_unmapped": [],
            }
        ),
    }
    seen = []

    def respond(http_request):
        wire = json.loads(http_request.content)
        seen.append(wire)
        assert http_request.url.path == "/v1/responses"
        assert wire["store"] is False and "tools" not in wire
        assert wire["instructions"] == PROMPTS[stage]
        (message,) = wire["input"]
        assert message["role"] == "user"
        assert message["content"][0]["text"] == "Untrusted pinned source"
        assert message["content"][1]["image_url"].startswith("data:image/png;base64,")
        fmt = wire["text"]["format"]
        assert fmt["strict"] and set(fmt["schema"]["required"]) == set(fmt["schema"]["properties"])
        return httpx.Response(
            200,
            json={
                "id": "resp_mock",
                "object": "response",
                "created_at": 1,
                "model": profile.model,
                "status": "incomplete" if outcome == "incomplete" else "completed",
                "output": [
                    {
                        "id": "msg_mock",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "refusal", "refusal": "test"}
                            if outcome == "refusal"
                            else {
                                "type": "output_text",
                                "text": "{" if outcome == "invalid" else json.dumps(payload),
                                "annotations": [],
                            },
                        ],
                    }
                ],
                "usage": {"input_tokens": 200, "output_tokens": 45, "total_tokens": 245},
            },
        )

    request = ExtractionRequest(
        work_unit_id=uuid4(),
        unit_key=f"{stage}:page:000001",
        attempt_number=1,
        model=profile.model,
        instructions=PROMPTS[stage],
        schema_version=profile.schema_version,
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        text="Untrusted pinned source",
        image=b"mock-png",
        image_mime_type="image/png",
        image_detail="high",
        stage=stage,
        response_model=RESPONSES[stage],
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        sdk = openai.OpenAI(api_key="test", max_retries=0, http_client=http)
        provider = OpenAIPhase6RProvider(settings, profile, sdk)
        if outcome == "success":
            response = provider.execute(request)
            assert response.result.model_dump(mode="json") == payload
            assert response.usage.output_tokens == 45
        else:
            with pytest.raises(ProviderFailure) as error:
                provider.execute(request)
            assert error.value.code == (
                ErrorCode.REFUSAL if outcome == "refusal" else ErrorCode.INVALID
            )
            assert error.value.usage.output_tokens == 45
        assert len(seen) == 1


def test_live_transport_requires_worker_credentials():
    settings = Settings(_env_file=None, extraction_external_enabled=True)
    with pytest.raises(ProviderFailure) as error:
        OpenAIPhase6RProvider(settings, phase6r_profile(settings))
    assert error.value.code == ErrorCode.AUTH
