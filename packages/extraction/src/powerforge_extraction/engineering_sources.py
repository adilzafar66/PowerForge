"""Database ownership snapshots for grounding and committed recognition context. No commits."""

from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from powerforge_document_processing.models import DocumentPage, DocumentProcessingRun, PageArtifact
from powerforge_extraction.engineering_output import MentionContext, RecognitionContext
from powerforge_extraction.grounding import (
    GROUNDING_VERSION,
    ArtifactSpec,
    PageSources,
    PageSpec,
    line_span,
    occurrences,
    paragraph_span,
)
from powerforge_extraction.models import (
    CandidateEvidence,
    Evidence,
    ExtractionCandidate,
    ExtractionRun,
    ExtractionWorkUnit,
    SourceGroup,
)
from powerforge_extraction.observations import LocalReference


def page_spec_for_unit(session: Session, unit_id: UUID) -> PageSpec:
    unit = session.get(ExtractionWorkUnit, unit_id)
    if unit is None or len(unit.page_numbers) != 1:
        raise ValueError("Engineering grounding requires an existing single-page unit")
    run = session.get(ExtractionRun, unit.run_id)
    processing = session.get(DocumentProcessingRun, unit.processing_run_id)
    if (
        run is None
        or processing is None
        or processing.status != "COMPLETED"
        or processing.document_id != run.document_id
        or unit.document_id != run.document_id
        or unit.processing_run_id != run.processing_run_id
        or unit.stage not in run.stages
    ):
        raise ValueError("Work-unit source ownership is invalid")
    page = session.scalar(
        select(DocumentPage).where(
            DocumentPage.document_id == run.document_id,
            DocumentPage.page_number == unit.page_numbers[0],
        )
    )
    if page is None or page.page_number not in run.selected_pages:
        raise ValueError("Work-unit page is outside pinned run inputs")
    artifacts = []
    for uid in unit.input_artifact_ids:
        artifact = session.get(PageArtifact, UUID(uid))
        if (
            artifact is None
            or str(artifact.id) not in run.input_artifact_ids
            or artifact.document_page_id != page.id
            or artifact.processing_run_id != run.processing_run_id
            or artifact.artifact_type not in {"NATIVE_TEXT", "ANALYSIS_IMAGE"}
            or artifact.mime_type
            != ("text/plain" if artifact.artifact_type == "NATIVE_TEXT" else "image/png")
        ):
            raise ValueError("Artifact is outside pinned work-unit source ownership")
        role = "native_text" if artifact.artifact_type == "NATIVE_TEXT" else "analysis_image"
        artifacts.append(
            ArtifactSpec(
                artifact.id,
                role,
                artifact.storage_key,
                artifact.size_bytes,
                artifact.sha256,
                artifact.width_px,
                artifact.height_px,
            )
        )
    if len({item.role for item in artifacts}) != len(artifacts) or not artifacts:
        raise ValueError("Pinned page roles must be distinct and nonempty")
    return PageSpec(
        run.id,
        unit.id,
        unit.unit_key,
        unit.stage,
        run.document_id,
        run.processing_run_id,
        page.id,
        page.page_number,
        tuple(artifacts),
    )


def load_recognition_context(
    session: Session,
    sources: PageSources,
    recognition_unit_id: UUID,
) -> RecognitionContext:
    target = sources.spec
    unit = session.get(ExtractionWorkUnit, recognition_unit_id)
    if (
        unit is None
        or unit.status != "COMPLETED"
        or unit.stage != "EQUIPMENT_RECOGNITION"
        or unit.id == target.unit_id
        or unit.run_id != target.run_id
        or unit.document_id != target.document_id
        or unit.processing_run_id != target.processing_run_id
        or unit.page_numbers != [target.page_number]
    ):
        raise ValueError("Recognition context requires a completed same-run/page recognition unit")
    candidates = list(
        session.scalars(
            select(ExtractionCandidate)
            .where(
                ExtractionCandidate.work_unit_id == unit.id,
            )
            .order_by(ExtractionCandidate.id)
        )
    )
    if len(candidates) > 32:
        raise ValueError("Recognition context exceeds its observation bound")
    mentions = []
    for candidate in candidates:
        if (
            candidate.kind != "EQUIPMENT_MENTION"
            or candidate.diagnostics.get("grounding_version") != GROUNDING_VERSION
        ):
            raise ValueError("Recognition context is not grounded engineering output")
        ref = TypeAdapter(LocalReference).validate_python(
            candidate.diagnostics.get("source_local_ref")
        )
        evidence = list(
            session.scalars(
                select(Evidence)
                .join(
                    CandidateEvidence,
                    CandidateEvidence.evidence_id == Evidence.id,
                )
                .where(
                    CandidateEvidence.candidate_id == candidate.id,
                    CandidateEvidence.role == "PRIMARY",
                )
                .order_by(CandidateEvidence.position, Evidence.id)
            )
        )
        if not evidence:
            raise ValueError("Recognition context lacks source evidence")
        role = "native_text" if evidence[0].source_kind == "NATIVE_TEXT" else "analysis_image"
        artifact = sources.artifact(role)
        own_spans = set()
        for item in evidence:
            if (
                item.run_id != target.run_id
                or item.work_unit_id != unit.id
                or item.document_page_id != target.page_id
                or item.page_artifact_id != artifact.id
                or item.source_kind != ("NATIVE_TEXT" if role == "native_text" else "VISUAL_REGION")
            ):
                raise ValueError("Recognition evidence ownership differs from pinned target inputs")
            if role == "native_text":
                if (
                    sources.text is None
                    or not item.source_snippet
                    or candidate.raw_text not in item.source_snippet
                ):
                    raise ValueError("Recognition statement is not in pinned native text evidence")
                if item.text_start is not None:
                    if (
                        sources.text[item.text_start : item.text_end] != item.source_snippet
                        or item.offset_convention != "UNICODE_CODEPOINT"
                    ):
                        raise ValueError(
                            "Recognition evidence no longer matches its exact pinned source"
                        )
                    matches = occurrences(item.source_snippet, candidate.raw_text)
                    if len(matches) == 1:
                        start = item.text_start + matches[0]
                        own_spans.add((start, start + len(candidate.raw_text)))
                elif not occurrences(sources.text, item.source_snippet):
                    raise ValueError("Recognition excerpt is not in pinned native text")
        header, scope = candidate.raw_text, None
        if role == "native_text":
            header = ""
            if len(own_spans) == 1:
                own = next(iter(own_spans))
                header_span = line_span(sources.text, *own)
                header = sources.text[slice(*header_span)]
                declared = candidate.diagnostics.get("source_scope")
                paragraph = paragraph_span(sources.text, *own)
                if (
                    isinstance(declared, list)
                    and len(declared) == 2
                    and all(type(number) is int for number in declared)
                    and tuple(declared) == paragraph
                    and header_span[0] == paragraph[0]
                    and len(header) <= 2000
                ):
                    scope = paragraph
        group = (
            session.get(SourceGroup, candidate.source_group_id)
            if candidate.source_group_id
            else None
        )
        if group is not None and (
            group.run_id != target.run_id
            or group.work_unit_id != unit.id
            or not set(group.evidence_ids) <= {str(item.id) for item in evidence}
        ):
            raise ValueError("Recognition group ownership or evidence is inconsistent")
        mentions.append(
            MentionContext(
                ref,
                candidate.id,
                group.id if group else None,
                artifact.id,
                role,
                header,
                scope,
                candidate.observed_tag,
                tuple(item.id for item in evidence),
            )
        )
    if len({item.local_ref for item in mentions}) != len(mentions):
        raise ValueError("Recognition local references are not unique")
    return RecognitionContext(
        target.run_id,
        target.document_id,
        target.processing_run_id,
        target.page_id,
        unit.id,
        tuple(mentions),
    )
