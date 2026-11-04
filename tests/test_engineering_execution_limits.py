"""Pinned limits and no-fallback failures at the real M4 execution boundary."""

from io import BytesIO
from uuid import UUID

import pytest
from sqlalchemy import select

from documents_support import client
from engineering_execution_support import StageProvider, attempt, processing, start_engineering
from engineering_execution_support import engineering_ctx as engineering_ctx
from engineering_execution_support import execution_ctx as execution_ctx
from engineering_grounding_support import equipment, recognition
from extraction_execution_support import detail, execute
from powerforge_ai.extraction import ExecutionUsage, ExtractionResponse
from powerforge_document_processing.models import PageArtifact
from powerforge_document_processing.storage import TransientStorageError
from powerforge_extraction import orchestration
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.observations import SourceAnchor
from powerforge_extraction.profiles import ENGINEERING_TEXT_TEST_PROFILE, engineering_profile

pytestmark = pytest.mark.integration
EQ, ATTR = "EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"


@pytest.mark.parametrize("limit", ["max_total_input_bytes", "max_input_bytes"])
def test_oversized_selected_inputs_are_rejected_before_planning(
    engineering_ctx, monkeypatch, limit
):
    ctx = engineering_ctx
    profile = engineering_profile("engineering-test-v1", ctx["settings"]).model_copy(
        update={limit: 1}
    )
    monkeypatch.setattr(orchestration, "resolve_profile", lambda *args: profile)
    response = client.post(ctx["base"] + "/runs", json={"profile_key": profile.key})
    assert response.status_code == 422
    with ctx["factory"]() as session:
        assert (
            session.scalar(
                select(RunExecution)
                .join(orchestration.ExtractionRun)
                .where(orchestration.ExtractionRun.document_id == ctx["src"]["document"])
            )
            is None
        )


@pytest.mark.parametrize(
    "limit",
    ["max_text_chars", "max_instruction_bytes", "max_upstream_bytes", "runtime", "schema_hash"],
)
def test_unavailable_resources_and_context_overflow_fail_without_provider_calls(
    engineering_ctx, monkeypatch, limit
):
    ctx = engineering_ctx
    value = (
        {"version": "unavailable"}
        if limit == "runtime"
        else "unavailable"
        if limit == "schema_hash"
        else 1
    )
    profile = engineering_profile("engineering-test-v1", ctx["settings"]).model_copy(
        update={limit: value}
    )
    monkeypatch.setattr(orchestration, "resolve_profile", lambda *args: profile)
    rid = start_engineering(ctx)["run"]["id"]
    provider = StageProvider()
    execute(ctx, attempt(ctx, rid, EQ), provider)
    if limit == "max_upstream_bytes":
        execute(ctx, attempt(ctx, rid, ATTR), provider)
    result = detail(ctx, rid)
    assert result["run"]["status"] == (
        "PARTIALLY_COMPLETED" if limit == "max_upstream_bytes" else "FAILED"
    )
    assert len(provider.requests) == (1 if limit == "max_upstream_bytes" else 0)
    assert any(u["error_code"] == "INVALID_SOURCE_INPUT" for u in result["attempts"])
    assert result["execution"]["provider_calls_started"] == len(provider.requests)


def test_text_only_requires_text_and_hybrid_never_drops_an_oversized_image(engineering_ctx):
    ctx = engineering_ctx
    processing(ctx, native=None)
    assert (
        client.post(
            ctx["base"] + "/runs", json={"profile_key": ENGINEERING_TEXT_TEST_PROFILE}
        ).status_code
        == 422
    )
    processing(ctx)
    ctx["settings"].extraction_max_image_pixels = 10
    assert (
        client.post(ctx["base"] + "/runs", json={"profile_key": "engineering-test-v1"}).status_code
        == 422
    )
    rid = start_engineering(ctx, profile_key=ENGINEERING_TEXT_TEST_PROFILE)["run"]["id"]
    provider = StageProvider()
    execute(ctx, attempt(ctx, rid, EQ), provider)
    assert provider.requests[0].image is None


@pytest.mark.parametrize("role", ["NATIVE_TEXT", "ANALYSIS_IMAGE"])
@pytest.mark.parametrize("transient", [True, False])
def test_one_artifact_failure_never_falls_back_to_the_other_modality(
    engineering_ctx, role, transient
):
    ctx = engineering_ctx
    rid = start_engineering(ctx)["run"]["id"]
    first = attempt(ctx, rid, EQ)
    with ctx["factory"]() as session:
        unit = session.get(ExtractionWorkUnit, first)
        target = session.scalar(
            select(PageArtifact).where(
                PageArtifact.id.in_([UUID(i) for i in unit.input_artifact_ids]),
                PageArtifact.artifact_type == role,
            )
        ).storage_key
    original = ctx["storage"]

    class Storage:
        failed = False

        def get(self, key):
            if key == target and not self.failed:
                self.failed = True
                if transient:
                    raise TransientStorageError("private endpoint details")
                return BytesIO(b"corrupt")
            return original.get(key)

        def __getattr__(self, name):
            return getattr(original, name)

    ctx["storage"] = Storage()
    provider = StageProvider()
    execute(ctx, first, provider)
    assert not provider.requests
    if transient:
        retry = attempt(ctx, rid, EQ)
        assert retry != first
        execute(ctx, retry, provider)
        execute(ctx, attempt(ctx, rid, ATTR), provider)
        assert detail(ctx, rid)["run"]["status"] == "COMPLETED"
        assert all(r.source_roles == ("native_text", "analysis_image") for r in provider.requests)
    else:
        assert detail(ctx, rid)["run"]["status"] == "FAILED"
    assert detail(ctx, rid)["execution"]["calls_admitted"] == len(provider.requests) + 1


@pytest.mark.parametrize("failure", ["schema", "source_role", "overflow", "tokens"])
def test_stage_revalidation_rejects_bad_payloads_and_preserves_known_usage(
    engineering_ctx, failure
):
    ctx = engineering_ctx
    rid = start_engineering(ctx, profile_key=ENGINEERING_TEXT_TEST_PROFILE)["run"]["id"]

    class Invalid:
        def execute(self, request):
            item = equipment("2-Winding Transformer TX-1")
            result = recognition(item)
            if failure == "schema":
                result = result.model_copy(update={"schema_version": "unavailable"})
            elif failure == "source_role":
                item = item.model_copy(
                    update={
                        "anchors": [
                            SourceAnchor(
                                kind="VISUAL_PAGE",
                                source_ref="analysis_image",
                                quote=None,
                                prefix=None,
                                suffix=None,
                            )
                        ]
                    }
                )
                result = recognition(item)
            elif failure == "overflow":
                result = result.model_copy(update={"overflowed": True})
            return ExtractionResponse[request.response_model].model_construct(
                result=result,
                usage=ExecutionUsage(
                    input_tokens=17, output_tokens=9000 if failure == "tokens" else 3
                ),
            )

    execute(ctx, attempt(ctx, rid, EQ), Invalid())
    result = detail(ctx, rid)
    assert result["run"]["status"] == "FAILED"
    assert (
        next(u for u in result["attempts"] if u["stage"] == EQ)["error_code"]
        == "INVALID_PROVIDER_RESPONSE"
    )
    assert result["execution"]["input_tokens"] == 17
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 0
