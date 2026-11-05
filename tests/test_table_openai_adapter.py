"""Actual Responses SDK serialization/parsing through a socket-free mocked transport."""

import json
import socket

import httpx
import openai
import pytest

from engineering_openai_support import sdk_response
from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_ai.extraction import ErrorCode, ProviderFailure
from powerforge_extraction.table_profiles import TABLE_OPENAI_TEXT_PROFILE
from powerforge_shared.config import Settings
from table_openai_support import profile_for, scripted_observations, stage_request


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Paid/live calls are forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)


def adapter(profile, handler):
    client = openai.OpenAI(
        api_key="fixture-credential",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return OpenAIExtractionProvider(
        Settings(_env_file=None, extraction_external_enabled=True), client, profile=profile
    )


@pytest.mark.parametrize("stage", ["TABLE_RECONSTRUCTION", "TABLE_INTERPRETATION"])
@pytest.mark.parametrize("mode", ["text", "hybrid", "image"])
def test_sdk_table_schema_inputs_and_context_are_explicit_and_bounded(stage, mode):
    profile = profile_for(TABLE_OPENAI_TEXT_PROFILE) if mode == "text" else profile_for()
    request = stage_request(stage, profile=profile, mode=mode)
    calls = []

    def handle(req):
        body = json.loads(req.content)
        calls.append(body)
        assert req.url.path == "/v1/responses"
        assert body["instructions"] == request.instructions
        assert body["text"]["format"]["name"] == request.response_model.__name__
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False and not body.get("tools")
        assert body["reasoning"] == {"effort": "none"}
        assert body["max_output_tokens"] == profile.max_output_tokens
        content = body["input"][0]["content"]
        if mode != "image":
            native = json.loads(content[0]["text"])
            assert native["schema_version"] == "table-source-input-v1"
            assert native["text"] == request.text and native["untrusted"] is True
        if mode != "text":
            image = next(c for c in content if c["type"] == "input_image")
            assert image["detail"] == "high" and image["image_url"].startswith(
                "data:image/png;base64,"
            )
        if stage == "TABLE_INTERPRETATION":
            context = json.loads(body["input"][1]["content"][0]["text"])
            assert context["schema_version"] == "table-upstream-input-v1" and context["untrusted"]
            assert context["observations"] == json.loads(request.upstream_context)
            assert str(request.work_unit_id) not in body["input"][1]["content"][0]["text"]
        return httpx.Response(
            200, json=sdk_response(scripted_observations(stage, visual=mode == "image"))
        )

    provider = adapter(profile, handle)
    try:
        result = provider.execute(request)
        assert isinstance(result.result, request.response_model) and len(calls) == 1
        assert result.usage.input_tokens == 20 and provider.client.max_retries == 0
    finally:
        provider.client.close()


@pytest.mark.parametrize(
    "mutation", ["stage", "schema", "instructions", "roles", "upstream", "foreign_field", "bound"]
)
def test_invalid_table_requests_never_reach_sdk(mutation):
    profile = profile_for()
    request = stage_request("TABLE_INTERPRETATION", profile=profile)
    if mutation == "stage":
        request = request.model_copy(update={"stage": "ATTRIBUTE_EXTRACTION"})
    elif mutation == "schema":
        request = request.model_copy(update={"schema_version": "old"})
    elif mutation == "instructions":
        request = request.model_copy(update={"instructions": "injected source instructions"})
    elif mutation == "roles":
        request = request.model_copy(update={"source_roles": ("native_text",)})
    elif mutation == "upstream":
        request = request.model_copy(update={"upstream_context": None})
    elif mutation == "foreign_field":
        upstream = json.loads(request.upstream_context)
        upstream["tables"][0]["database_id"] = "forged"
        request = request.model_copy(update={"upstream_context": json.dumps(upstream)})
    else:
        request = request.model_copy(update={"text": "x" * (profile.max_text_chars + 1)})
    provider = adapter(profile, lambda req: pytest.fail("SDK must not be called"))
    try:
        with pytest.raises(ProviderFailure) as error:
            provider.execute(request)
        assert error.value.code == ErrorCode.INPUT
    finally:
        provider.client.close()


@pytest.mark.parametrize(
    "failure", ["refusal", "incomplete", "malformed", "rate_limit", "unavailable", "auth"]
)
def test_table_sdk_failures_have_safe_categories_usage_and_no_hidden_retries(failure, caplog):
    profile, calls = profile_for(), []

    def handle(req):
        calls.append(req)
        if failure in {"rate_limit", "unavailable", "auth"}:
            return httpx.Response(
                {"rate_limit": 429, "unavailable": 503, "auth": 401}[failure],
                json={"error": {"message": "PRIVATE SOURCE CONTENT", "type": "fixture_error"}},
            )
        response = sdk_response(scripted_observations("TABLE_RECONSTRUCTION"))
        if failure == "refusal":
            response["output"][0]["content"] = [
                {"type": "refusal", "refusal": "PRIVATE SOURCE CONTENT"}
            ]
        elif failure == "incomplete":
            response["status"] = "incomplete"
        else:
            response["output"][0]["content"][0]["text"] = '{"bad": true}'
        return httpx.Response(200, json=response)

    provider = adapter(profile, handle)
    try:
        with pytest.raises(ProviderFailure) as error:
            provider.execute(stage_request(profile=profile))
        assert len(calls) == 1
        assert (
            error.value.code
            == {
                "refusal": ErrorCode.REFUSAL,
                "incomplete": ErrorCode.INVALID,
                "malformed": ErrorCode.INVALID,
                "rate_limit": ErrorCode.RATE_LIMIT,
                "unavailable": ErrorCode.UNAVAILABLE,
                "auth": ErrorCode.AUTH,
            }[failure]
        )
        assert "PRIVATE" not in str(error.value) + caplog.text
    finally:
        provider.client.close()


def test_nested_upstream_reliability_does_not_accept_foreign_fields_or_objects():
    profile = profile_for()
    request = stage_request("TABLE_INTERPRETATION", profile=profile)
    upstream = json.loads(request.upstream_context)
    upstream["tables"][0]["cell_text_basis"]["c1_3"] = {"storage_key": "PRIVATE"}
    provider = adapter(profile, lambda req: pytest.fail("SDK must not be called"))
    try:
        with pytest.raises(ProviderFailure) as error:
            provider.execute(request.model_copy(update={"upstream_context": json.dumps(upstream)}))
        assert error.value.code == ErrorCode.INPUT
    finally:
        provider.client.close()
