"""Read-only, revision-membership-scoped extraction queries."""

from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from powerforge_api.exceptions import RevisionDocumentNotFound
from powerforge_api.schemas.extraction import (
    Coverage,
    ExecutionSummary,
    ExtractionSummary,
    RunDetail,
    RunList,
    RunResponse,
    UnitResponse,
)
from powerforge_document_model import RevisionDocumentStatus
from powerforge_document_processing.models import (
    Document,
    ProjectRevision,
    RevisionDocument,
)
from powerforge_extraction.controls import RunExecution, UnitExecution
from powerforge_extraction.dependencies import retryable_keys
from powerforge_extraction.enums import (
    ExtractionRunStatus,
    WorkUnitStatus,
)
from powerforge_extraction.models import (
    ExtractionAICall,
    ExtractionRun,
    ExtractionWorkUnit,
)
from powerforge_extraction.phase6r_runtime import StageResult
from powerforge_extraction.profiles import read_profile


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
            all_reported = len(calls) == started
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
        results = {
            row.work_unit_id: row
            for row in self.session.scalars(select(StageResult).where(StageResult.run_id == run.id))
        }
        diagnostics = {call.work_unit_id: call.validation_diagnostics for call in calls}
        computed = {
            "effective",
            "retryable",
            "stale",
            "stage_outcome",
            "stage_diagnostics",
            "validation_diagnostics",
        }
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
                        "validation_diagnostics": diagnostics.get(r.id, []),
                        "effective": r.status == WorkUnitStatus.COMPLETED,
                        "stage_outcome": results[r.id].outcome if r.id in results else None,
                        "stage_diagnostics": results[r.id].diagnostics if r.id in results else [],
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
