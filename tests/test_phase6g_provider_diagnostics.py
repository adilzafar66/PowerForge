"""Bounded provider failure taxonomy using the frozen Table Reconstruction schema."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import openai
import pytest
from pydantic import ValidationError

from enriched_pure_support import fake, native_sources
from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_ai.extraction import ErrorCode, ExtractionRequest, ProviderFailure
from powerforge_ai.extraction_diagnostics import validation_issues
from powerforge_extraction.enriched_observations import EnrichedReconstructionResponse
from powerforge_extraction.enriched_profiles import enriched_profile
from powerforge_shared.config import Settings
from test_openai_extraction import Client, enabled, request, response


@pytest.fixture(scope="module")
def schedule():
    return fake(
        native_sources(Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes())
    ).model_dump(mode="json")


@pytest.mark.parametrize(
    ("corruption", "reason", "path"),
    [
        ("missing", "MISSING_FIELD", "tables.0.cells.0.raw_text"),
        ("alias", "INVALID_TABLE_GRAPH", "tables.0"),
        ("span", "INVALID_CELL_SPAN", "tables.0"),
        ("cycle", "INVALID_TABLE_GRAPH", "tables.0"),
        ("duplicate", "DUPLICATE_ALIAS", ""),
        ("overflow", "RESPONSE_OVERFLOW", ""),
        ("malformed", "MALFORMED_JSON", ""),
    ],
)
def test_table_schema_failure_subtypes(schedule, corruption, reason, path):
    model = EnrichedReconstructionResponse
    payload = deepcopy(schedule)
    table = payload["tables"][0]
    if corruption == "missing":
        del table["cells"][0]["raw_text"]
    elif corruption == "alias":
        table["cells"][0]["header_refs"] = ["foreign-header"]
    elif corruption == "span":
        table["cells"][0]["row_span"] = 3
    elif corruption == "cycle":
        first, second = [cell for cell in table["cells"] if cell["row"] == 0]
        first.update(header_role="BOTH", header_refs=[second["local_ref"]])
        second.update(header_role="BOTH", header_refs=[first["local_ref"]])
    elif corruption == "duplicate":
        payload["tables"].append(deepcopy(table))
    elif corruption == "overflow":
        payload["overflowed"] = True

    with pytest.raises(ValidationError) as exc:
        if corruption == "malformed":
            model.model_validate_json('{"private input that must be omitted"')
        else:
            model.model_validate(payload)
    issue = validation_issues(exc.value, model)[0]
    assert (issue.reason, issue.path) == (reason, path)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"status": "incomplete"}, "INCOMPLETE_RESPONSE"),
        (
            {
                "status": "incomplete",
                "incomplete_details": SimpleNamespace(reason="max_output_tokens"),
            },
            "OUTPUT_TOKEN_LIMIT",
        ),
        (
            {
                "status": "incomplete",
                "incomplete_details": SimpleNamespace(reason="content_filter"),
            },
            "CONTENT_FILTERED",
        ),
        ({"status": "failed"}, "PROVIDER_FAILED_RESPONSE"),
        ({"output_parsed": None}, "MISSING_PARSED_OUTPUT"),
    ],
)
def test_safe_terminal_outcome_without_response_content(changes, reason):
    client = Client(response(**changes))
    with pytest.raises(ProviderFailure) as exc:
        OpenAIExtractionProvider(enabled(), client).execute(request())
    assert exc.value.code == ErrorCode.INVALID and exc.value.detail == reason
    assert len(client.calls) == 1


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("truncated", [False, True])
def test_sdk_raw_wrapper_preserves_valid_output_and_observable_token_limit(
    schedule, truncated, compact
):
    from powerforge_extraction.table_reconstruction_v4 import CompactReconstructionResponse

    if compact:
        schedule = dict(
            schema_version="table-reconstruction-schema-v3",
            overflowed=False,
            partitions=[],
            reported_tables=[],
        )
    calls = []
    if issubclass(openai.DefaultHttpxClient, httpx.Client):
        transport_api = httpx
    else:
        import httpx2 as transport_api

    def mocked(http_request):
        calls.append(http_request)
        return transport_api.Response(
            200,
            json={
                "id": "resp_fixture",
                "status": "incomplete" if truncated else "completed",
                "incomplete_details": {"reason": "max_output_tokens"} if truncated else None,
                "output": [
                    {
                        "id": "msg_fixture",
                        "type": "message",
                        "role": "assistant",
                        "status": "incomplete" if truncated else "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "text": '{"tables": [' if truncated else json.dumps(schedule),
                            }
                        ],
                    }
                ],
            },
        )

    settings = Settings(_env_file=None, extraction_external_enabled=True)
    profile = enriched_profile(f"tables-openai-enriched-v{4 if compact else 1}", settings)
    req = ExtractionRequest(
        work_unit_id=uuid4(),
        unit_key="TABLE_RECONSTRUCTION:page:000001",
        attempt_number=1,
        stage="TABLE_RECONSTRUCTION",
        model=profile.model,
        instructions="synthetic instructions",
        schema_version=schedule["schema_version"],
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        text='{"version":"enriched-source-context-v1","untrusted":true,"readings":[]}',
        source_roles=("spatial_readings", "analysis_image"),
        image=b"synthetic-image",
        image_mime_type="image/png",
        image_detail=profile.image_detail,
        response_model=CompactReconstructionResponse if compact else EnrichedReconstructionResponse,
    )
    with openai.OpenAI(
        api_key="fixture-only",
        max_retries=0,
        http_client=transport_api.Client(transport=transport_api.MockTransport(mocked)),
    ) as client:
        provider = OpenAIExtractionProvider(settings, client, profile=profile)
        if truncated:
            with pytest.raises(ProviderFailure) as exc:
                provider.execute(req)
            assert exc.value.code == ErrorCode.INVALID
            assert exc.value.detail == "OUTPUT_TOKEN_LIMIT"
            assert exc.value.issues[0].reason == "MALFORMED_JSON"
        else:
            assert provider.execute(req).result.model_dump(mode="json") == schedule
    assert len(calls) == 1
