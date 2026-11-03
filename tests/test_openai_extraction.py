"""No sockets: real adapter request shape, safe errors and structured validation."""

import socket
from types import SimpleNamespace
from uuid import uuid4

import httpx
import openai
import pytest

from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_ai.extraction import ErrorCode, ExtractionRequest, ProbeResult, ProviderFailure
from powerforge_extraction.profiles import FAKE_PROFILE, PROMPT, SCHEMA_VERSION, resolve_profile
from powerforge_shared.config import Settings


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("No real provider calls in tests")

    monkeypatch.setattr(socket, "create_connection", blocked)


class Client:
    def __init__(self, response):
        self.responses = self
        self.response, self.calls = response, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def request():
    return ExtractionRequest(
        work_unit_id=uuid4(),
        unit_key="SOURCE_PROBE:page:000001",
        attempt_number=1,
        model="explicit-model",
        instructions=PROMPT,
        schema_version=SCHEMA_VERSION,
        timeout_seconds=12,
        max_output_tokens=128,
        text="750 kVA",
    )


def response(**changes):
    return SimpleNamespace(
        **{
            "status": "completed",
            "output": [],
            "output_parsed": {"acknowledged": True, "excerpt": "750 kVA"},
            "usage": SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                input_tokens_details=SimpleNamespace(cached_tokens=2),
            ),
            **changes,
        }
    )


def enabled():
    return Settings(_env_file=None, extraction_external_enabled=True, openai_api_key=None)


def test_explicit_enablement_and_missing_credentials():
    with pytest.raises(ProviderFailure) as exc:
        OpenAIExtractionProvider(
            Settings(_env_file=None, extraction_external_enabled=False), Client(response())
        )
    assert exc.value.code == ErrorCode.DISABLED
    with pytest.raises(ProviderFailure) as exc:
        OpenAIExtractionProvider(enabled())
    assert exc.value.code == ErrorCode.AUTH


def test_structured_request_bounds_model_no_tools_storage_and_usage():
    client = Client(response())
    result = OpenAIExtractionProvider(enabled(), client).execute(request())
    assert result.result.excerpt == "750 kVA" and result.usage.cached_input_tokens == 2
    call = client.calls[0]
    assert call["text_format"] is ProbeResult and call["store"] is False
    assert call["model"] == "explicit-model" and call["max_output_tokens"] == 128
    assert call["timeout"] == 12 and "tools" not in call and "background" not in call
    assert "sk-" not in str(call)


def test_image_payload_is_bounded_private_bytes_not_storage_url():
    client = Client(response(output_parsed={"acknowledged": True, "excerpt": None}))
    req = request().model_copy(
        update={"text": None, "image": b"png-fixture", "image_mime_type": "image/png"}
    )
    OpenAIExtractionProvider(enabled(), client).execute(req)
    image = client.calls[0]["input"][0]["content"][1]
    assert image["image_url"].startswith("data:image/png;base64,")
    assert image["detail"] == "low"


@pytest.mark.parametrize(
    "bad",
    [
        {"status": "incomplete"},
        {"output_parsed": None},
        {"output_parsed": {"acknowledged": True, "excerpt": "x" * 257}},
        {"output_parsed": {"acknowledged": False, "excerpt": None}},
        {
            "usage": SimpleNamespace(
                input_tokens=1,
                output_tokens=1,
                input_tokens_details=SimpleNamespace(cached_tokens=2),
            )
        },
    ],
)
def test_invalid_or_incomplete_payload_is_rejected(bad):
    with pytest.raises(ProviderFailure) as exc:
        OpenAIExtractionProvider(enabled(), Client(response(**bad))).execute(request())
    assert exc.value.code == ErrorCode.INVALID


def test_refusal_is_safe_and_unknown_usage_remains_unknown():
    refused = response(output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])])
    with pytest.raises(ProviderFailure) as exc:
        OpenAIExtractionProvider(enabled(), Client(refused)).execute(request())
    assert exc.value.code == ErrorCode.REFUSAL
    result = OpenAIExtractionProvider(enabled(), Client(response(usage=None))).execute(request())
    assert result.usage.input_tokens is None


@pytest.mark.parametrize(
    "status,error,code",
    [
        (429, openai.RateLimitError, ErrorCode.RATE_LIMIT),
        (401, openai.AuthenticationError, ErrorCode.AUTH),
        (503, openai.InternalServerError, ErrorCode.UNAVAILABLE),
    ],
)
def test_provider_failures_are_classified_without_sdk_messages(status, error, code):
    http_response = httpx.Response(
        status, request=httpx.Request("POST", "https://api.openai.com/v1/responses")
    )
    sdk_error = error("SECRET DOCUMENT CONTENT", response=http_response, body=None)
    client = Client(sdk_error)
    with pytest.raises(ProviderFailure) as exc:
        OpenAIExtractionProvider(enabled(), client).execute(request())
    assert exc.value.code == code and "SECRET" not in str(exc.value)
    assert len(client.calls) == 1  # Persistence owns bounded retry attempts.


def test_profile_hash_versions_all_material_execution_configuration():
    a = Settings(_env_file=None)
    b = Settings(_env_file=None, extraction_max_calls=a.extraction_max_calls + 1)
    c = Settings(_env_file=None, extraction_lease_seconds=a.extraction_lease_seconds + 1)
    assert len({resolve_profile(FAKE_PROFILE, s).identity_hash for s in [a, b, c]}) == 3
    assert not a.extraction_external_enabled


@pytest.mark.parametrize(
    "error_type,code",
    [
        (openai.APITimeoutError, ErrorCode.TIMEOUT),
        (openai.APIConnectionError, ErrorCode.UNAVAILABLE),
    ],
)
def test_timeout_and_connection_errors_are_safe_and_not_retried_in_adapter(error_type, code):
    sdk_error = error_type(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    client = Client(sdk_error)
    with pytest.raises(ProviderFailure) as exc:
        OpenAIExtractionProvider(enabled(), client).execute(request())
    assert exc.value.code == code and len(client.calls) == 1
