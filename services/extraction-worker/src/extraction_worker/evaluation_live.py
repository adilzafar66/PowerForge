"""Opt-in bounded live evaluation through normal claims/publication, never direct SDK calls."""

import time
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
)
from powerforge_document_processing.storage.factory import build_s3_storage
from powerforge_extraction.contracts import (
    CandidateEvidenceInput,
    CandidateInput,
    EvidenceInput,
    WorkUnitOutput,
)
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.engineering_sources import page_spec_for_unit
from powerforge_extraction.evaluation import load_corpus, read_json, resource_identity
from powerforge_extraction.evaluation_scoring import report, score_case
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.grounding import load_page_sources
from powerforge_extraction.models import (
    CandidateEvidence,
    Evidence,
    ExtractionAICall,
    ExtractionCandidate,
    ExtractionRun,
    ExtractionWorkUnit,
)
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.production_profiles import (
    ENGINEERING_OPENAI_PROFILE,
    ENGINEERING_OPENAI_TEXT_PROFILE,
)
from powerforge_provenance.locations import Region, SourceLocation
from powerforge_shared.config import get_settings


def planned_runs(session, corpus, bindings, selected, settings):
    """Caller commits the entire validated batch before any provider I/O/delivery."""
    cases = [case for case in corpus.cases if case.id in selected]
    if set(bindings) != {case.id for case in cases} or len(set(bindings.values())) != len(bindings):
        raise ValueError("Live bindings must be exact, distinct fixture Document UUIDs")
    # Consistent source lock order; all planned inputs are rechecked before commit.
    for uid in sorted(bindings.values()):
        if (
            session.scalar(select(Document).where(Document.id == UUID(uid)).with_for_update())
            is None
        ):
            raise ValueError("Bound source Document is unavailable")
    runs = {}
    for case in cases:
        document_id = UUID(bindings[case.id])
        processing = session.scalar(
            select(DocumentProcessingRun)
            .where(
                DocumentProcessingRun.document_id == document_id,
                DocumentProcessingRun.status == "COMPLETED",
            )
            .order_by(DocumentProcessingRun.created_at.desc(), DocumentProcessingRun.id.desc())
            .limit(1)
        )
        if processing is None:
            raise ValueError("Fixture requires completed document processing")
        page = session.scalar(
            select(DocumentPage).where(
                DocumentPage.document_id == document_id, DocumentPage.page_number == 1
            )
        )
        if page is None:
            raise ValueError("Fixture page is unavailable")
        artifacts = list(
            session.scalars(
                select(PageArtifact).where(
                    PageArtifact.processing_run_id == processing.id,
                    PageArtifact.document_page_id == page.id,
                    PageArtifact.artifact_type.in_(["NATIVE_TEXT", "ANALYSIS_IMAGE"]),
                )
            )
        )
        wanted = {source.role: source for source in case.sources}
        selected_artifacts = [
            item
            for item in artifacts
            if item.artifact_type == "NATIVE_TEXT" or "analysis_image" in wanted
        ]
        # Native-only profiles ignore unapproved images. Image-only fixtures may not
        # accidentally send an unapproved native representation alongside the image.
        found = {
            "native_text" if item.artifact_type == "NATIVE_TEXT" else "analysis_image": item
            for item in selected_artifacts
        }
        if set(found) != set(wanted) or any(
            found[role].sha256 != source.sha256
            or found[role].size_bytes != source.size_bytes
            or (
                role == "analysis_image"
                and (found[role].width_px, found[role].height_px) != (source.width, source.height)
            )
            for role, source in wanted.items()
        ):
            raise ValueError("Bound fixture artifacts differ from approved corpus bytes")
        key = (
            ENGINEERING_OPENAI_PROFILE
            if "analysis_image" in wanted
            else ENGINEERING_OPENAI_TEXT_PROFILE
        )
        run = ExtractionCoordinator(session, settings).start(
            document_id, profile_key=key, pages=[1], mode="reextract"
        )
        if run.processing_run_id != processing.id or set(run.input_artifact_ids) != {
            str(item.id) for item in found.values()
        }:
            raise ValueError("Planned source changed during preflight")
        if session.get(RunExecution, run.id).configuration["max_calls"] != 2:
            raise ValueError("Live fixture must have a two-admission budget")
        runs[case.id] = run.id
    return runs


def published_output(session, run_id):
    units = list(
        session.scalars(
            select(ExtractionWorkUnit).where(
                ExtractionWorkUnit.run_id == run_id, ExtractionWorkUnit.status == "COMPLETED"
            )
        )
    )
    ids = [unit.id for unit in units]
    candidates = [
        CandidateInput.model_validate(
            {name: getattr(row, name) for name in CandidateInput.model_fields}
        )
        for row in session.scalars(
            select(ExtractionCandidate).where(ExtractionCandidate.work_unit_id.in_(ids))
        )
    ]
    evidence = []
    for row in session.scalars(select(Evidence).where(Evidence.work_unit_id.in_(ids))):
        data = {
            name: getattr(row, name) for name in EvidenceInput.model_fields if name != "location"
        }
        region = (
            Region(x=row.x, y=row.y, width=row.width, height=row.height)
            if row.x is not None
            else None
        )
        evidence.append(
            EvidenceInput(
                **data,
                location=SourceLocation(
                    document_page_id=row.document_page_id,
                    page_artifact_id=row.page_artifact_id,
                    region=region,
                ),
            )
        )
    links = [
        CandidateEvidenceInput(
            candidate_id=row.candidate_id,
            evidence_id=row.evidence_id,
            role=row.role,
            position=row.position,
        )
        for row in session.scalars(
            select(CandidateEvidence).where(CandidateEvidence.work_unit_id.in_(ids))
        )
    ]
    diagnostics = {
        name: sum(unit.output_counts.get(name, 0) for unit in units)
        for name in ("rejected_ungrounded", "rejected_source_fields", "detached_associations")
        if any(name in unit.output_counts for unit in units)
    }
    return WorkUnitOutput(
        candidates=candidates,
        evidence=evidence,
        candidate_evidence=links,
        diagnostic_counts=diagnostics,
    ), units


def run_live(
    corpus_path,
    bindings,
    selected,
    factory,
    storage,
    settings,
    provider_factory,
    *,
    wait_seconds=300,
    approved_digest=None,
):
    """Execute with an injected provider; this helper cannot attest live provenance."""
    corpus, digest = load_corpus(corpus_path)
    if not selected or set(selected) - {case.id for case in corpus.cases}:
        raise ValueError("Live selection must name existing corpus cases")
    if approved_digest is not None and digest != approved_digest:
        raise ValueError("Approved corpus changed before planning")
    # No automatic/manual retries: the approval envelope is exactly two attempts per case.
    bounded = settings.model_copy(
        update={
            "extraction_max_calls": 2,
            "extraction_max_attempts": 1,
            "extraction_max_concurrent_per_run": 1,
        }
    )
    with factory.begin() as session:
        runs = planned_runs(session, corpus, bindings, selected, bounded)
    deadline = time.monotonic() + wait_seconds
    snapshots, execution = [], {}
    try:
        for case in corpus.cases:
            if case.id not in runs:
                continue
            rid = runs[case.id]
            while True:
                with factory() as session:
                    run = session.get(ExtractionRun, rid)
                    active = run.status in {"PENDING", "RUNNING"}
                    ids = list(
                        session.scalars(
                            select(ExtractionWorkUnit.id)
                            .where(
                                ExtractionWorkUnit.run_id == rid,
                                ExtractionWorkUnit.status == "PENDING",
                            )
                            .order_by(ExtractionWorkUnit.stage.desc())
                        )
                    )
                if not active:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Bounded live evaluation timed out")
                for uid in ids:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Live evaluation budget window expired")
                    execute_unit(uid, factory, storage, bounded, provider_factory)
                with factory.begin() as session:
                    ExtractionCoordinator(session, bounded).reconcile()
                time.sleep(0.05)
            with factory() as session:
                output, units = published_output(session, rid)
                # A failed recognition may have no successful output: snapshot its
                # original planned source rather than losing its zero-recall case.
                unit = (
                    units[0]
                    if units
                    else session.scalar(
                        select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == rid).limit(1)
                    )
                )
                spec = page_spec_for_unit(session, unit.id)
                control = session.get(RunExecution, rid)
                execution[case.id] = {
                    "run_id": str(rid),
                    "status": session.get(ExtractionRun, rid).status,
                    "calls_admitted": control.calls_admitted,
                    "profile_hash": session.get(ExtractionRun, rid).profile_hash,
                    "model": control.configuration["model"],
                    "call_budget": control.configuration["max_calls"],
                }
                calls = list(
                    session.scalars(select(ExtractionAICall).where(ExtractionAICall.run_id == rid))
                )
                execution[case.id]["reported_calls"] = len(calls)
                execution[case.id]["successful_calls"] = sum(
                    call.outcome == "SUCCEEDED" for call in calls
                )
            sources = load_page_sources(spec, storage)
            snapshots.append(score_case(case, sources, [output]))
    finally:
        for rid in runs.values():
            with factory.begin() as session:
                if session.get(ExtractionRun, rid).status in {"PENDING", "RUNNING"}:
                    ExtractionCoordinator(session, bounded).cancel(rid)
    result = report(
        snapshots,
        provenance="UNVERIFIED_PIPELINE",
        corpus_digest=digest,
        resources=resource_identity(),
    )
    result["execution"] = execution
    result["live_model_quality_measured"] = False
    return result


def evaluate_live(
    corpus_path, bindings_path, *, approved_digest, selected, max_calls, wait_seconds
):
    if load_corpus(corpus_path)[1] != approved_digest:
        raise ValueError("Approved corpus changed before live setup")
    settings = get_settings()
    if (
        not settings.extraction_enabled
        or not settings.extraction_external_enabled
        or not settings.openai_api_key
        or max_calls < 2 * len(selected)
    ):
        raise ValueError(
            "Live evaluation requires configured worker external processing and credentials"
        )
    from extraction_worker.extraction_tasks import provider_for

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        result = run_live(
            corpus_path,
            read_json(bindings_path),
            selected,
            sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
            build_s3_storage(settings),
            settings,
            provider_for,
            wait_seconds=wait_seconds,
            approved_digest=approved_digest,
        )
        # Only this guarded entrypoint selects the production factory itself.
        # An injected provider or its caller's label cannot designate a live run.
        result["provenance"] = "LIVE_OPENAI"
        result["live_model_quality_measured"] = any(
            item["successful_calls"] for item in result["execution"].values()
        )
        return result
    finally:
        engine.dispose()
