"""Exercise the live adapter using the installed SDK and an in-process HTTP transport."""

import json
from uuid import uuid4

import httpx
import openai
import pytest

from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_ai.extraction import (
    AttributeOutput,
    ErrorCode,
    ExtractionRequest,
    ProviderFailure,
    RecognitionOutput,
)
from powerforge_extraction.extraction_profile import PROMPTS, RESPONSES, STAGES, extraction_profile
from powerforge_extraction.performance import AttemptPerformance, active_performance
from powerforge_extraction.stage_contracts import stage_schema_version
from powerforge_shared.config import Settings


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize(
    "outcome, category, error_type",
    [
        ("success", None, None),
        ("timeout", None, None),
        ("connection", "TRANSPORT", "connection_error"),
        ("upstream", "TRANSPORT", "upstream_http_error"),
        ("incomplete", "INCOMPLETE", "max_output_tokens"),
        ("refusal", "REFUSAL", "refusal"),
        ("invalid", "JSON", "json_invalid"),
        ("envelope", "ENVELOPE", "invalid_envelope"),
        ("provider_schema", "ENVELOPE", "invalid_json_schema"),
        ("schema", "SCHEMA", "extra_forbidden"),
        ("pattern", "SCHEMA", "extra_forbidden"),
        ("cardinality", "FIELD_CONSTRAINT", "too_long"),
    ],
)
def test_responses_transport_is_bounded_and_retains_measured_usage(
    stage, outcome, category, error_type
):
    settings = Settings(_env_file=None, extraction_external_enabled=True)
    profile = extraction_profile(settings)
    payload = {"equipment": []} if stage == STAGES[0] else {"attributes": [], "raw_unmapped": []}
    secret = "CONFIDENTIAL SOURCE STRING"
    if outcome == "success" and stage == STAGES[1]:
        payload["attributes"] = [
            {
                "origin": "INFERRED",
                "local_ref": "a1",
                "equipment_ref": "eq1",
                "association": "ASSERTED",
                "attribute_key": "trip_unit_type",
                "proposed_value": "ELECTRONIC",
                "proposed_unit": None,
                "inference_explanation": "The specified unit identifies the trip technology.",
                "inference_basis": "EQUIPMENT_CHARACTERISTICS",
                "source_expression": None,
                "evidence": [],
            }
        ]
    if outcome == "schema":
        payload[secret] = secret
    if outcome == "pattern":
        payload["page_context_hash"] = secret
    if outcome == "cardinality":
        field = "equipment" if stage == STAGES[0] else "raw_unmapped"
        item = (
            dict(
                local_ref="ref",
                source_description=secret,
                registry_type=None,
                tag_state="ABSENT",
                tag=None,
                qualification="UNKNOWN",
                raw_qualification=None,
                evidence=[],
            )
            if stage == STAGES[0]
            else dict(
                local_ref="ref",
                equipment_ref=None,
                association="UNASSIGNED",
                display_label=None,
                raw_label=secret,
                raw_value=secret,
                raw_unit=None,
                qualifiers=[],
                value_form="SINGLE",
                evidence=[],
            )
        )
        payload[field] = [item] * 129
    seen = []

    def respond(http_request):
        wire = json.loads(http_request.content)
        seen.append(wire)
        assert http_request.url.path == "/v1/responses"
        assert wire["store"] is False and "tools" not in wire
        if stage == STAGES[1]:
            assert wire["reasoning"] == {"effort": "medium"}
        else:
            assert "reasoning" not in wire
        assert wire["instructions"] == PROMPTS[stage]
        (message,) = wire["input"]
        assert message["role"] == "user"
        assert message["content"][0]["text"] == "Untrusted pinned source"
        assert message["content"][1]["image_url"].startswith("data:image/png;base64,")
        fmt = wire["text"]["format"]
        assert fmt["strict"] and set(fmt["schema"]["required"]) == set(fmt["schema"]["properties"])
        schema_fields = fmt["schema"]["properties"]
        if stage == STAGES[1]:
            assert "at most 12 evidence citations per assertion" in wire["instructions"]
            union = schema_fields["attributes"]["items"]["anyOf"]
            assert len(union) == 2
            assert "proposed_unit" in fmt["schema"]["$defs"]["RegistryAssertion"]["required"]
            assert fmt["schema"]["$defs"]["InferredAssertion"]["properties"]["origin"]["enum"] == [
                "INFERRED"
            ]
        collection = "equipment" if stage == STAGES[0] else "raw_unmapped"
        assert "maxItems" not in schema_fields[collection]
        if stage == STAGES[1]:
            assert set(schema_fields) == {"attributes", "raw_unmapped"}
        else:
            assert set(schema_fields) == {"equipment"}
        if outcome == "timeout":
            raise httpx.ReadTimeout(secret, request=http_request)
        if outcome == "connection":
            raise httpx.ConnectError(secret, request=http_request)
        if outcome == "upstream":
            return httpx.Response(503, json={"error": {"message": secret}})
        if outcome == "provider_schema":
            return httpx.Response(
                400,
                json={
                    "error": {"code": "invalid_json_schema", "message": secret},
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "resp_mock",
                "object": "response",
                "created_at": 1,
                "model": profile.model,
                "status": "incomplete" if outcome == "incomplete" else "completed",
                "incomplete_details": {"reason": "max_output_tokens"}
                if outcome == "incomplete"
                else None,
                "output": []
                if outcome == "envelope"
                else [
                    {
                        "id": "msg_mock",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "refusal", "refusal": secret}
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
        schema_version=stage_schema_version(stage),
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        text="Untrusted pinned source",
        image=b"mock-png",
        image_mime_type="image/png",
        image_detail="high",
        stage=stage,
        response_model=RESPONSES[stage],
        reasoning_effort=profile.reasoning_effort_for(stage),
        request_digest_version=profile.request_digest_for(stage),
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        sdk = openai.OpenAI(api_key="test", max_retries=0, http_client=http)
        provider = OpenAIExtractionProvider(settings, profile, sdk)
        performance = AttemptPerformance()
        if outcome == "timeout":
            token = active_performance.set(performance)
            try:
                with pytest.raises(ProviderFailure) as error:
                    provider.execute(request)
            finally:
                active_performance.reset(token)
            assert error.value.code == ErrorCode.TIMEOUT
            assert error.value.usage is None and secret not in str(error.value)
            assert performance.provider_call_ms is not None
            assert performance.failure_stage == "provider_call"
            assert performance.response_status == "timeout"
            return
        if stage == STAGES[1] and outcome in {
            "success",
            "invalid",
            "schema",
            "pattern",
            "cardinality",
        }:
            response = provider.execute(request)
            assert isinstance(response, AttributeOutput)
            original = ("{" if outcome == "invalid" else json.dumps(payload)).encode()
            assert response.output_text == original
            assert response.request is request
            assert response.usage.output_tokens == 45
        elif stage == STAGES[0] and outcome in {
            "success",
            "invalid",
            "schema",
            "pattern",
            "cardinality",
            "incomplete",
        }:
            response = provider.execute(request)
            assert isinstance(response, RecognitionOutput)
            assert (
                response.output_text
                == ("{" if outcome == "invalid" else json.dumps(payload)).encode()
            )
            assert response.request is request
            assert response.usage.output_tokens == 45
            if outcome == "incomplete":
                issue = response.failure.diagnostics[0]
                assert (issue.category, issue.error_type) == (category, error_type)
            else:
                assert response.failure is None
        else:
            with pytest.raises(ProviderFailure) as error:
                provider.execute(request)
            assert error.value.code == (
                {
                    "refusal": ErrorCode.REFUSAL,
                    "connection": ErrorCode.UNAVAILABLE,
                    "upstream": ErrorCode.UNAVAILABLE,
                }.get(outcome, ErrorCode.INVALID)
            )
            if outcome in {"provider_schema", "connection", "upstream"}:
                assert error.value.usage is None
            else:
                assert error.value.usage.output_tokens == 45
            issue = error.value.diagnostics[0]
            assert (issue.category, issue.error_type) == (category, error_type)
            if outcome == "schema":
                assert issue.path == ("*",)
            assert secret not in str(error.value)
            assert all(secret not in issue.model_dump_json() for issue in error.value.diagnostics)
        assert len(seen) == 1


def test_live_transport_requires_worker_credentials():
    settings = Settings(_env_file=None, extraction_external_enabled=True)
    with pytest.raises(ProviderFailure) as error:
        OpenAIExtractionProvider(settings, extraction_profile(settings))
    assert error.value.code == ErrorCode.AUTH


@pytest.mark.parametrize("stage", STAGES)
def test_provider_visual_region_schema_only_offers_exact_coordinate_types(stage):
    from powerforge_extraction.extraction_profile import structured_schema

    schema = structured_schema(RESPONSES[stage].model_json_schema())
    fields = schema["$defs"]["ReportedRegion"]["properties"]
    assert set(fields) == {"x", "y", "width", "height"}
    for field in fields.values():
        assert field["anyOf"] == [{"type": "string"}, {"type": "integer"}]


def test_provider_typed_schema_has_only_supported_primitive_branches():
    from powerforge_extraction.extraction_profile import structured_schema

    schema = structured_schema(RESPONSES[STAGES[1]].model_json_schema())
    definitions = schema["$defs"]

    def check_shape(node):
        if "$ref" in node:
            assert node["$ref"].removeprefix("#/$defs/") in definitions
        if node.get("type") == "object":
            assert set(node["required"]) == set(node["properties"])
            assert node["additionalProperties"] is False
            for child in node["properties"].values():
                check_shape(child)
        for child in node.get("anyOf", ()):
            check_shape(child)
        if "items" in node:
            check_shape(node["items"])

    check_shape(schema)
    for definition, nullable in (("RegistryAssertion", True), ("InferredAssertion", False)):
        fields = definitions[definition]["properties"]
        assert "proposed_enum_value" not in fields
        assert ("alternate_representations" in fields) is nullable
        allowed = {"string", "integer", "boolean"}
        if nullable:
            allowed.add("null")
        assert {branch["type"] for branch in fields["proposed_value"]["anyOf"]} == allowed
    assert definitions["AlternateRepresentation"]["properties"]["value"]["type"] == "string"


@pytest.mark.parametrize(
    "reasoning, output, expected",
    [
        (None, 45, (None, None)),
        (0, 45, (0, 45)),
        (20, 45, (20, 25)),
        (46, 45, (None, None)),
        (-1, 45, (None, None)),
        ("12", 45, (None, None)),
        (True, 45, (None, None)),
        (20, None, (20, None)),
    ],
)
def test_optional_provider_details_never_change_admission(reasoning, output, expected):
    from types import SimpleNamespace

    stage = STAGES[1]
    response = SimpleNamespace(
        status="completed",
        service_tier="priority",
        reasoning=SimpleNamespace(effort="medium"),
        usage=SimpleNamespace(
            output_tokens=output, output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning)
        ),
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(type="output_text", text='{"attributes":[],"raw_unmapped":[]}')
                ],
            )
        ],
    )
    performance = AttemptPerformance()
    token = active_performance.set(performance)
    try:
        result = OpenAIExtractionProvider._admit_response(
            response, SimpleNamespace(stage=stage), RESPONSES[stage]
        )
    finally:
        active_performance.reset(token)
    assert result.usage.output_tokens == output
    assert (performance.reasoning_tokens, performance.visible_output_tokens) == expected
    assert performance.service_tier == "priority" and performance.reasoning_effort == "medium"
