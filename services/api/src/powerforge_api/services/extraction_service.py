"""Read-only, revision-membership-scoped extraction queries."""

from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from powerforge_api.exceptions import RevisionDocumentNotFound, StorageDownloadFailed
from powerforge_api.schemas.extraction import (
    CandidateList,
    CandidateResponse,
    Citation,
    Coverage,
    EvidenceDetail,
    EvidenceSummary,
    ExecutionSummary,
    ExtractionSummary,
    RunDetail,
    RunList,
    RunResponse,
    SourceGroupSummary,
    TableList,
    TableResponse,
    UnitResponse,
)
from powerforge_document_model import RevisionDocumentStatus
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    PageArtifact,
    ProjectRevision,
    RevisionDocument,
)
from powerforge_document_processing.storage.base import ObjectStorage, StorageError
from powerforge_extraction.controls import RunExecution, UnitExecution
from powerforge_extraction.dependencies import retryable_keys
from powerforge_extraction.enums import (
    CandidateKind,
    EvidenceRole,
    ExtractionRunStatus,
    MappingStatus,
    WorkUnitStatus,
)
from powerforge_extraction.models import (
    CandidateEvidence,
    Evidence,
    ExtractedTable,
    ExtractionAICall,
    ExtractionCandidate,
    ExtractionRun,
    ExtractionWorkUnit,
    SourceGroup,
)
from powerforge_extraction.persistence import effective_units
from powerforge_extraction.profiles import read_profile
from powerforge_provenance.locations import Region


def _evidence_summary(row: Evidence, artifact_type: str | None = None) -> EvidenceSummary:
    precision = "PAGE_ONLY"
    if row.source_kind in {"NATIVE_TEXT", "OCR_TEXT"}:
        precision = "TEXT_OFFSETS" if row.text_start is not None else "TEXT_PAGE"
    elif row.source_kind == "VISUAL_REGION":
        precision = "VISUAL_REGION" if row.x is not None else "VISUAL_PAGE"
    elif row.source_kind == "TABLE_CELL":
        if artifact_type == "NATIVE_TEXT" and row.source_snippet is not None:
            precision = "TEXT_OFFSETS" if row.text_start is not None else "TEXT_PAGE"
        elif artifact_type == "ANALYSIS_IMAGE":
            precision = "VISUAL_REGION" if row.x is not None else "VISUAL_PAGE"
    return EvidenceSummary(
        **EvidenceSummary.model_validate(row).model_dump(exclude={"grounding_precision"}),
        grounding_precision=precision,
    )


class ExtractionReadService:
    def __init__(
        self, session: Session, project_id: UUID, revision_id: UUID, revision_document_id: UUID
    ) -> None:
        self.session = session
        self.revision_document_id = revision_document_id
        self.revision_id = revision_id
        self.document_id = session.scalar(
            select(RevisionDocument.document_id)
            .join(Document, Document.id == RevisionDocument.document_id)
            .join(ProjectRevision, ProjectRevision.id == RevisionDocument.revision_id)
            .where(
                RevisionDocument.id == revision_document_id,
                RevisionDocument.project_id == project_id,
                RevisionDocument.revision_id == revision_id,
                RevisionDocument.status == RevisionDocumentStatus.INCLUDED,
                Document.project_id == project_id,
                ProjectRevision.project_id == project_id,
            )
        )
        if self.document_id is None:
            raise RevisionDocumentNotFound("Included document not found")

    def _runs(self) -> Select[tuple[ExtractionRun]]:
        return select(ExtractionRun).where(
            ExtractionRun.document_id == self.document_id,
            ExtractionRun.execution_purpose == "EXTRACTION",
            or_(
                ExtractionRun.context_revision_id.is_(None),
                ExtractionRun.context_revision_id == self.revision_id,
            ),
        )

    def _run(self, run_id: UUID) -> ExtractionRun:
        row = self.session.scalar(self._runs().where(ExtractionRun.id == run_id))
        if row is None:
            raise RevisionDocumentNotFound("Extraction run not found")
        return row

    def summary(self) -> ExtractionSummary:
        ordered = self._runs().order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        result = self.session.scalar(
            ordered.where(
                ExtractionRun.status.in_(
                    [ExtractionRunStatus.COMPLETED, ExtractionRunStatus.PARTIALLY_COMPLETED]
                )
            ).limit(1)
        )
        current = self.session.scalar(ordered.limit(1))
        return ExtractionSummary(
            latest_result=RunResponse.model_validate(result) if result else None,
            current_run=RunResponse.model_validate(current) if current else None,
        )

    def history(self, limit: int, offset: int) -> RunList:
        stmt = self._runs()
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = self.session.scalars(
            stmt.order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return RunList(
            items=[RunResponse.model_validate(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def coverage(self, run: ExtractionRun) -> tuple[Coverage, list[ExtractionWorkUnit]]:
        rows = list(
            self.session.scalars(
                select(ExtractionWorkUnit)
                .where(ExtractionWorkUnit.run_id == run.id)
                .order_by(
                    ExtractionWorkUnit.unit_key,
                    ExtractionWorkUnit.attempt_number,
                    ExtractionWorkUnit.id,
                )
            )
        )
        required = {r.unit_key for r in rows if r.required}
        successful = [r for r in rows if r.status == WorkUnitStatus.COMPLETED]
        completed = {r.unit_key for r in successful if r.required}
        return Coverage(
            required_units=len(required),
            completed_required_units=len(completed),
            effective_work_unit_ids=[r.id for r in successful],
            complete=run.status == ExtractionRunStatus.COMPLETED and required == completed,
        ), rows

    def detail(self, run_id: UUID) -> RunDetail:
        run = self._run(run_id)
        coverage, rows = self.coverage(run)
        control = self.session.get(RunExecution, run.id)
        profile = read_profile(control.configuration) if control else None
        eligible = retryable_keys(rows, profile.max_attempts) if profile else set()
        now = self.session.scalar(select(func.clock_timestamp()))
        calls = (
            list(
                self.session.scalars(
                    select(ExtractionAICall).where(ExtractionAICall.run_id == run.id)
                )
            )
            if control
            else []
        )
        execution = None
        if control:
            started = self.session.scalar(
                select(func.count())
                .select_from(UnitExecution)
                .where(
                    UnitExecution.run_id == run.id, UnitExecution.provider_started_at.is_not(None)
                )
            )
            all_reported = len(calls) == control.calls_admitted
            execution = ExecutionSummary(
                profile_key=profile.key,
                execution_kind=profile.execution_kind,
                cancel_requested_at=control.cancel_requested_at,
                calls_admitted=control.calls_admitted,
                call_budget=profile.max_calls,
                reported_calls=len(calls),
                provider_calls_started=started,
                unreported_provider_calls=max(0, started - len(calls)),
                unreported_admissions=control.calls_admitted - len(calls),
                input_tokens=sum(c.input_tokens for c in calls)
                if all_reported and calls and all(c.input_tokens is not None for c in calls)
                else None,
                output_tokens=sum(c.output_tokens for c in calls)
                if all_reported and calls and all(c.output_tokens is not None for c in calls)
                else None,
                estimated_cost_usd=sum(c.estimated_cost_usd for c in calls)
                if all_reported and calls and all(c.estimated_cost_usd is not None for c in calls)
                else None,
            )
        computed = {"effective", "retryable", "stale"}
        return RunDetail(
            run=RunResponse.model_validate(run),
            coverage=coverage,
            execution=execution,
            attempts=[
                UnitResponse.model_validate(
                    {
                        **{
                            k: getattr(r, k) for k in UnitResponse.model_fields if k not in computed
                        },
                        "effective": r.status == WorkUnitStatus.COMPLETED,
                        "retryable": bool(
                            profile
                            and run.status
                            in {ExtractionRunStatus.FAILED, ExtractionRunStatus.PARTIALLY_COMPLETED}
                            and r.status in {WorkUnitStatus.FAILED, WorkUnitStatus.CANCELLED}
                            and r.attempt_number < profile.max_attempts
                            and r.unit_key in eligible
                            and control.calls_admitted < profile.max_calls
                            and not any(
                                other.unit_key == r.unit_key
                                and other.attempt_number > r.attempt_number
                                for other in rows
                            )
                        ),
                        "stale": r.status == WorkUnitStatus.RUNNING
                        and r.lease_expires_at is not None
                        and r.lease_expires_at <= now,
                    }
                )
                for r in rows
            ],
        )

    def candidates(
        self,
        run_id: UUID,
        limit: int,
        offset: int,
        *,
        kind: CandidateKind | None = None,
        mapping_status: MappingStatus | None = None,
        source_group_id: UUID | None = None,
        equipment_type_key: str | None = None,
        attribute_key: str | None = None,
        supported_only: bool = True,
    ) -> CandidateList:
        run = self._run(run_id)
        supported = exists(
            select(CandidateEvidence.id).where(
                CandidateEvidence.candidate_id == ExtractionCandidate.id,
                CandidateEvidence.role.in_([EvidenceRole.PRIMARY, EvidenceRole.SUPPORTING]),
            )
        )
        stmt = select(ExtractionCandidate).where(
            ExtractionCandidate.run_id == run_id,
            ExtractionCandidate.work_unit_id.in_(effective_units(run_id)),
        )
        for key, value in {
            "kind": kind,
            "mapping_status": mapping_status,
            "source_group_id": source_group_id,
            "equipment_type_key": equipment_type_key,
            "attribute_key": attribute_key,
        }.items():
            if value is not None:
                stmt = stmt.where(getattr(ExtractionCandidate, key) == value)
        if supported_only:
            stmt = stmt.where(supported)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = list(
            self.session.scalars(
                stmt.order_by(ExtractionCandidate.created_at, ExtractionCandidate.id)
                .limit(limit)
                .offset(offset)
            )
        )
        links = (
            self.session.execute(
                select(CandidateEvidence, Evidence)
                .join(Evidence, Evidence.id == CandidateEvidence.evidence_id)
                .where(CandidateEvidence.candidate_id.in_([r.id for r in rows]))
                .order_by(CandidateEvidence.position, CandidateEvidence.evidence_id)
            ).all()
            if rows
            else []
        )
        artifact_types = (
            dict(
                self.session.execute(
                    select(PageArtifact.id, PageArtifact.artifact_type).where(
                        PageArtifact.id.in_(
                            [e.page_artifact_id for _, e in links if e.source_kind == "TABLE_CELL"]
                        )
                    )
                ).all()
            )
            if links
            else {}
        )
        grouped = {}
        for link, evidence in links:
            grouped.setdefault(link.candidate_id, []).append(
                Citation(
                    evidence=_evidence_summary(
                        evidence, artifact_types.get(evidence.page_artifact_id)
                    ),
                    role=link.role,
                    position=link.position,
                )
            )
        group_ids = {r.source_group_id for r in rows if r.source_group_id is not None}
        groups = (
            {
                g.id: SourceGroupSummary.model_validate(g)
                for g in self.session.scalars(
                    select(SourceGroup).where(SourceGroup.id.in_(group_ids))
                )
            }
            if group_ids
            else {}
        )
        items = []
        for row in rows:
            item = CandidateResponse.model_validate(row)
            citations = grouped.get(row.id, [])
            items.append(
                item.model_copy(
                    update={
                        "evidence": citations,
                        "source_group": groups.get(row.source_group_id),
                        "supported": any(
                            c.role in [EvidenceRole.PRIMARY, EvidenceRole.SUPPORTING]
                            for c in citations
                        ),
                    }
                )
            )
        return CandidateList(
            run_id=run.id,
            status=run.status,
            coverage=self.coverage(run)[0],
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def tables(self, run_id: UUID, limit: int, offset: int) -> TableList:
        run = self._run(run_id)
        stmt = select(ExtractedTable).where(
            ExtractedTable.run_id == run_id,
            ExtractedTable.work_unit_id.in_(effective_units(run_id)),
        )
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = self.session.scalars(
            stmt.order_by(ExtractedTable.created_at, ExtractedTable.id).limit(limit).offset(offset)
        )
        return TableList(
            run_id=run.id,
            status=run.status,
            coverage=self.coverage(run)[0],
            items=[TableResponse.model_validate(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def evidence(self, evidence_id: UUID, storage: ObjectStorage, expires: int) -> EvidenceDetail:
        row = self.session.scalar(
            select(Evidence).where(
                Evidence.id == evidence_id,
                Evidence.document_id == self.document_id,
                Evidence.work_unit_id.in_(
                    select(ExtractionWorkUnit.id).where(
                        ExtractionWorkUnit.status == WorkUnitStatus.COMPLETED
                    )
                ),
            )
        )
        if row is None:
            raise RevisionDocumentNotFound("Extraction evidence not found")
        self._run(row.run_id)
        page = self.session.get(DocumentPage, row.document_page_id)
        url, artifact = None, None
        if row.page_artifact_id:
            artifact = self.session.get(PageArtifact, row.page_artifact_id)
            try:
                url = storage.create_download_url(
                    artifact.storage_key,
                    f"page-{page.page_number}",
                    artifact.mime_type,
                    "inline",
                    expires,
                )
            except StorageError as exc:
                raise StorageDownloadFailed("Evidence artifact access unavailable") from exc
        return EvidenceDetail(
            **_evidence_summary(row, artifact.artifact_type if artifact else None).model_dump(),
            run_id=row.run_id,
            document_id=row.document_id,
            processing_run_id=row.processing_run_id,
            work_unit_id=row.work_unit_id,
            page_number=page.page_number,
            region=Region(x=row.x, y=row.y, width=row.width, height=row.height)
            if row.x is not None
            else None,
            text_start=row.text_start,
            text_end=row.text_end,
            offset_convention=row.offset_convention,
            created_at=row.created_at,
            artifact_url=url,
            artifact_url_expires_seconds=expires if url else None,
        )
