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
    ExtractionCandidate,
    ExtractionRun,
    ExtractionWorkUnit,
    SourceGroup,
)
from powerforge_extraction.persistence import effective_units
from powerforge_provenance.locations import Region


class ExtractionReadService:
    def __init__(
        self, session: Session, project_id: UUID, revision_id: UUID, revision_document_id: UUID
    ) -> None:
        self.session = session
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
        return RunDetail(
            run=RunResponse.model_validate(run),
            coverage=coverage,
            attempts=[
                UnitResponse.model_validate(
                    {
                        **{k: getattr(r, k) for k in UnitResponse.model_fields if k != "effective"},
                        "effective": r.status == WorkUnitStatus.COMPLETED,
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
        grouped = {}
        for link, evidence in links:
            grouped.setdefault(link.candidate_id, []).append(
                Citation(
                    evidence=EvidenceSummary.model_validate(evidence),
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
        url = None
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
            **EvidenceSummary.model_validate(row).model_dump(),
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
