"""Source availability uses bounded append-only retries without losing published siblings."""

from io import BytesIO

import pytest

from documents_support import client
from extraction_execution_support import add_page, detail, start_run, units
from extraction_execution_support import execution_ctx as execution_ctx
from powerforge_document_processing.storage import (
    ObjectNotFound,
    StorageError,
    TransientStorageError,
)
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.fake import FakeExtractionProvider

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("phase", ["get", "stream", "publication"])
def test_transient_source_failure_retries_without_repeating_success(
    execution_ctx, monkeypatch, caplog, phase
):
    ctx = execution_ctx
    add_page(ctx)
    rid = start_run(ctx)["run"]["id"]
    a, b = units(ctx, rid)
    provider = FakeExtractionProvider()

    def execute(uid):
        return execute_unit(
            uid, ctx["factory"], ctx["storage"], ctx["settings"], lambda claim: provider
        )

    assert execute(a)
    original_get = ctx["storage"].get
    reads = 0
    broken_stream = None

    class InterruptedStream(BytesIO):
        def read(self, size=-1):
            raise TransientStorageError("PRIVATE connection details")

    def get(key):
        nonlocal reads, broken_stream
        reads += 1
        if reads == (2 if phase == "publication" else 1):
            if phase == "stream":
                broken_stream = InterruptedStream()
                return broken_stream
            raise TransientStorageError("PRIVATE connection details")
        return original_get(key)

    monkeypatch.setattr(ctx["storage"], "get", get)
    assert execute(b)
    interrupted = detail(ctx, rid)
    assert interrupted["run"]["status"] == "RUNNING"
    first, failed, retry = interrupted["attempts"]
    assert first["id"] == str(a) and first["status"] == "COMPLETED"
    assert failed["id"] == str(b) and failed["status"] == "FAILED"
    assert failed["error_code"] == "SOURCE_UNAVAILABLE"
    assert retry["status"] == "PENDING" and retry["retry_of_work_unit_id"] == str(b)
    # Failed publication rolls back its telemetry/output; only actual calls are reported later.
    expected_calls = 2 if phase == "publication" else 1
    assert len(provider.calls) == expected_calls
    assert interrupted["execution"]["reported_calls"] == expected_calls
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 1
    if broken_stream is not None:
        assert broken_stream.closed
    assert "PRIVATE" not in caplog.text

    assert execute(units(ctx, rid)[-1])
    done = detail(ctx, rid)
    assert done["run"]["status"] == "COMPLETED"
    assert len(done["attempts"]) == 3 and done["attempts"][1] == failed
    assert len(provider.calls) == expected_calls + 1
    assert provider.calls.count(first["unit_key"]) == 1
    assert client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["total"] == 2


@pytest.mark.parametrize("failure", ["missing", "denied", "corrupt", "invalid_utf8"])
def test_permanent_source_failure_never_automatically_retries(execution_ctx, monkeypatch, failure):
    import hashlib

    from powerforge_document_processing.models import PageArtifact

    ctx = execution_ctx
    # Pin the hash to invalid UTF-8 to exercise decoding independently of integrity checks.
    if failure == "invalid_utf8":
        with ctx["factory"].begin() as session:
            artifact = session.get(PageArtifact, ctx["src"]["artifact"])
            artifact.size_bytes = 1
            artifact.sha256 = hashlib.sha256(b"\xff").hexdigest()
    rid = start_run(ctx)["run"]["id"]
    provider = FakeExtractionProvider()
    if failure in {"missing", "denied"}:
        error = (
            ObjectNotFound("Object not found") if failure == "missing" else StorageError("Denied")
        )
        ctx["storage"].fail_on("get", error)
    else:
        payload = b"corrupt" if failure == "corrupt" else b"\xff"
        monkeypatch.setattr(ctx["storage"], "get", lambda key: BytesIO(payload))
    assert execute_unit(
        units(ctx, rid)[0], ctx["factory"], ctx["storage"], ctx["settings"], lambda claim: provider
    )
    result = detail(ctx, rid)
    assert result["run"]["status"] == "FAILED"
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["error_code"] == "INVALID_SOURCE_INPUT"
    assert result["execution"]["reported_calls"] == 0 and not provider.calls


@pytest.mark.parametrize("attempts,call_budget", [(2, 10), (3, 1)])
def test_source_outage_stops_at_original_attempt_or_admission_limit(
    execution_ctx, attempts, call_budget
):
    ctx = execution_ctx
    ctx["settings"].extraction_max_attempts = attempts
    ctx["settings"].extraction_max_calls = call_budget
    rid = start_run(ctx)["run"]["id"]
    ctx["storage"].fail_on("get", TransientStorageError("Temporarily unavailable"))
    provider = FakeExtractionProvider()
    for _ in range(min(attempts, call_budget)):
        assert execute_unit(
            units(ctx, rid)[-1],
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda claim: provider,
        )
    result = detail(ctx, rid)
    assert result["run"]["status"] == "FAILED"
    assert len(result["attempts"]) == min(attempts, call_budget)
    assert {a["error_code"] for a in result["attempts"]} == {"SOURCE_UNAVAILABLE"}
    assert result["execution"]["calls_admitted"] == min(attempts, call_budget)
    assert result["execution"]["reported_calls"] == 0 and not provider.calls
    assert client.post(ctx["base"] + f"/runs/{rid}/retry").status_code == 409
