"""Phase 6 fixtures use immutable source identities and an isolated integration DB."""

import hashlib
from datetime import UTC, datetime
from io import BytesIO

from documents_support import seed_association
from powerforge_api.db import get_session_factory
from powerforge_document_model import PageArtifactType, ProcessingRunStatus
from powerforge_document_processing.models import (
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
    RevisionDocument,
)
from powerforge_extraction.contracts import (
    CandidateEvidenceInput,
    CandidateInput,
    EvidenceInput,
    RunInput,
    WorkUnitInput,
    WorkUnitOutput,
)
from powerforge_extraction.enums import (
    CandidateKind,
    EvidenceSourceKind,
    ExtractionMethod,
    ExtractionRunStatus,
    MappingStatus,
    WorkUnitStatus,
)
from powerforge_extraction.persistence import ExtractionPersistence
from powerforge_provenance.locations import SourceLocation


def source(ctx, *, native_text="rated 750 kVA " + "x" * 87):
    text_bytes = native_text.encode("utf-8")
    association = seed_association(ctx["project_id"], ctx["revision_id"])
    with get_session_factory()() as s:
        doc = s.get(RevisionDocument, association).document_id
        page = DocumentPage(
            document_id=doc,
            page_number=1,
            source_width=612,
            source_height=792,
            source_unit="POINTS",
            rotation_degrees=0,
            native_text_char_count=len(native_text),
        )
        processing = DocumentProcessingRun(
            document_id=doc,
            processor_version="1",
            profile_version="v1",
            profile_hash="abc",
            status=ProcessingRunStatus.COMPLETED,
        )
        s.add_all([page, processing])
        s.flush()
        artifact = PageArtifact(
            document_page_id=page.id,
            processing_run_id=processing.id,
            artifact_type=PageArtifactType.NATIVE_TEXT,
            storage_key=f"processing/{processing.id}/text.txt",
            mime_type="text/plain",
            size_bytes=len(text_bytes),
            sha256=hashlib.sha256(text_bytes).hexdigest(),
        )
        ctx["storage"].put(artifact.storage_key, BytesIO(text_bytes), len(text_bytes), "text/plain")
        s.add(artifact)
        s.commit()
        return dict(
            association=association,
            document=doc,
            page=page.id,
            processing=processing.id,
            artifact=artifact.id,
        )


def inputs(src, **overrides):
    return RunInput(
        document_id=src["document"],
        processing_run_id=src["processing"],
        extractor_version="v1",
        schema_version="v1",
        profile_version="v1",
        profile_hash="profile",
        provider="fake",
        model="fixture",
        prompt_version="v1",
        prompt_hash="prompt",
        selected_pages=[1],
        stages=["attributes"],
        input_artifact_ids=[src["artifact"]],
        **overrides,
    )


def run_and_unit(s, src, key="attributes:1", run=None):
    store = ExtractionPersistence(s)
    run = run or store.create_run(inputs(src))
    run.status = ExtractionRunStatus.RUNNING
    s.flush()
    unit = store.create_work_unit(
        run.id,
        WorkUnitInput(
            unit_key=key, stage="attributes", page_numbers=[1], input_artifact_ids=[src["artifact"]]
        ),
    )
    unit.status = WorkUnitStatus.RUNNING
    unit.started_at = datetime.now(UTC)
    s.flush()
    return run, unit


def claim(**changes):
    return CandidateInput(
        kind=CandidateKind.UNMAPPED_OBSERVATION,
        mapping_status=MappingStatus.UNMAPPED,
        raw_text="Rated value, unidentified equipment",
        **changes,
    )


def grounded(src, candidates=None):
    candidates = candidates if candidates is not None else [claim()]
    evidence = EvidenceInput(
        location=SourceLocation(document_page_id=src["page"], page_artifact_id=src["artifact"]),
        source_kind=EvidenceSourceKind.NATIVE_TEXT,
        extraction_method=ExtractionMethod.AI_TEXT,
        source_snippet="rated 750 kVA",
        text_start=0,
        text_end=13,
        offset_convention="UNICODE_CODEPOINT",
    )
    return WorkUnitOutput(
        evidence=[evidence],
        candidates=candidates,
        candidate_evidence=[
            CandidateEvidenceInput(candidate_id=c.id, evidence_id=evidence.id) for c in candidates
        ],
    )


def url(ctx, src):
    return (
        f"/api/projects/{ctx['project_id']}/revisions/{ctx['revision_id']}"
        f"/documents/{src['association']}/extraction"
    )
