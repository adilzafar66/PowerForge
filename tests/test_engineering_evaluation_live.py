"""Live entrypoint controls and normal DB execution tested with injected providers only."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from engineering_execution_support import execution_ctx as execution_ctx
from extraction_support import source
from extraction_worker.evaluation_live import run_live
from powerforge_ai.extraction import ErrorCode, ExecutionUsage, ExtractionResponse, ProviderFailure
from powerforge_document_processing.models import DocumentProcessingRun, PageArtifact
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.evaluation import load_corpus, read_json, source_bytes
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit

pytestmark = pytest.mark.integration
CORPUS = Path(__file__).resolve().parents[1] / "evals/extraction/v1/corpus.json"


def bind(ctx, selected):
    corpus, _ = load_corpus(CORPUS)
    bindings = {}
    for case in corpus.cases:
        if case.id not in selected:
            continue
        src = source(ctx, native_text="Unselected initial processor representation")
        with ctx["factory"].begin() as session:
            processing = DocumentProcessingRun(
                document_id=src["document"],
                processor_version="eval-fixture",
                profile_version="v1",
                profile_hash=str(uuid4()),
                status="COMPLETED",
            )
            session.add(processing)
            session.flush()
            for item in case.sources:
                key = f"processing/{processing.id}/{item.role}"
                data = source_bytes(CORPUS.parent, item)
                ctx["storage"].put(
                    key,
                    BytesIO(data),
                    len(data),
                    "text/plain" if item.role == "native_text" else "image/png",
                )
                session.add(
                    PageArtifact(
                        document_page_id=src["page"],
                        processing_run_id=processing.id,
                        artifact_type="NATIVE_TEXT"
                        if item.role == "native_text"
                        else "ANALYSIS_IMAGE",
                        storage_key=key,
                        mime_type="text/plain" if item.role == "native_text" else "image/png",
                        size_bytes=item.size_bytes,
                        sha256=item.sha256,
                        width_px=item.width,
                        height_px=item.height,
                    )
                )
        bindings[case.id] = str(src["document"])
    return bindings


def provider_for(bindings, requests, *, fail=False):
    by_document = {uid: case_id for case_id, uid in bindings.items()}
    recorded = read_json(CORPUS.parent / "scripted.json")["cases"]

    def factory(claim):
        case_id = by_document[str(claim.page_spec.document_id)]

        class Provider:
            def execute(self, request):
                requests.append(request)
                if fail and request.stage == "ATTRIBUTE_EXTRACTION":
                    raise ProviderFailure(ErrorCode.AUTH)
                key = "equipment" if request.stage == "EQUIPMENT_RECOGNITION" else "attributes"
                return ExtractionResponse[request.response_model](
                    result=recorded[case_id][key],
                    usage=ExecutionUsage(input_tokens=20, output_tokens=16),
                )

        return Provider()

    return factory


def test_bounded_live_path_reuses_real_admission_grounding_and_publication_without_spending(
    execution_ctx,
):
    ctx = execution_ctx
    ctx["settings"].extraction_external_enabled = True
    bindings = bind(ctx, {"breaker", "tagless_visual", "missed_colon_header"})
    requests = []
    result = run_live(
        CORPUS,
        bindings,
        set(bindings),
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        provider_for(bindings, requests),
    )
    assert len(requests) == 6 and result["case_count"] == 3
    assert result["provenance"] == "UNVERIFIED_PIPELINE"
    assert not result["live_model_quality_measured"]
    assert result["metrics"]["normalized_value_correctness"]["numerator"] == 5
    assert result["rejections"]["detached_associations"] == 1
    for entry in result["execution"].values():
        assert (
            entry["status"] == "COMPLETED"
            and entry["calls_admitted"] == entry["reported_calls"] == 2
        )
        with ctx["factory"]() as session:
            control = session.scalar(
                select(RunExecution).where(RunExecution.run_id == entry["run_id"])
            )
            assert (
                control.configuration["max_attempts"] == 1
                and control.configuration["max_calls"] == 2
            )


def test_invalid_binding_rolls_back_entire_batch_before_any_admission(execution_ctx):
    ctx = execution_ctx
    ctx["settings"].extraction_external_enabled = True
    bindings = bind(ctx, {"transformer", "breaker"})
    # Transformer planning succeeds first; a later mismatched binding must roll it back.
    bindings["breaker"] = str(source(ctx, native_text="Wrong fixture content")["document"])
    requests = []
    with pytest.raises(ValueError, match="differ"):
        run_live(
            CORPUS,
            bindings,
            set(bindings),
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            provider_for(bindings, requests),
        )
    assert not requests
    with ctx["factory"]() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExtractionRun)
                .where(ExtractionRun.document_id.in_(bindings.values()))
            )
            == 0
        )


def test_failed_stage_is_not_retried_or_excluded_from_gold_coverage(execution_ctx):
    ctx = execution_ctx
    ctx["settings"].extraction_external_enabled = True
    bindings = bind(ctx, {"transformer"})
    requests = []
    result = run_live(
        CORPUS,
        bindings,
        set(bindings),
        ctx["factory"],
        ctx["storage"],
        ctx["settings"],
        provider_for(bindings, requests, fail=True),
    )
    assert len(requests) == 2
    assert result["execution"]["transformer"]["status"] == "PARTIALLY_COMPLETED"
    assert result["metrics"]["attribute_detection_recall"] == {
        "numerator": 0,
        "denominator": 4,
        "rate": 0.0,
    }


def test_timeout_settles_only_evaluation_runs_without_provider_calls(execution_ctx):
    from powerforge_extraction.orchestration import ExtractionCoordinator

    ctx = execution_ctx
    ctx["settings"].extraction_external_enabled = True
    with ctx["factory"].begin() as session:
        unrelated = ExtractionCoordinator(session, ctx["settings"]).start(ctx["src"]["document"]).id
    bindings = bind(ctx, {"breaker"})
    requests = []
    with pytest.raises(TimeoutError):
        run_live(
            CORPUS,
            bindings,
            set(bindings),
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            provider_for(bindings, requests),
            wait_seconds=0,
        )
    assert not requests
    with ctx["factory"]() as session:
        run = session.scalar(
            select(ExtractionRun).where(ExtractionRun.document_id.in_(bindings.values()))
        )
        assert run.status == "CANCELLED"
        assert session.get(ExtractionRun, unrelated).status == "PENDING"
        assert all(
            unit.status == "CANCELLED"
            for unit in session.scalars(
                select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run.id)
            )
        )
