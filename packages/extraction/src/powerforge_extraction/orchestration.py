"""Database-authoritative execution. Methods flush; callers own transactions/commits."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from powerforge_ai.extraction import ErrorCode, ExecutionUsage, ExtractionRequest
from powerforge_document_model import PageArtifactType, ProcessingRunStatus
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
)
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_extraction.contracts import AICallInput, RunInput, WorkUnitInput, WorkUnitOutput
from powerforge_extraction.controls import RunExecution, UnitExecution
from powerforge_extraction.dependencies import latest_units, retryable_keys, unit_key
from powerforge_extraction.enums import ExtractionRunStatus as RS
from powerforge_extraction.enums import WorkUnitStatus as US
from powerforge_extraction.errors import (
    ExtractionConflict,
    ExtractionDisabled,
    ExtractionError,
    ExtractionNotFound,
    LeaseLost,
)
from powerforge_extraction.grounding import PageSpec
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.persistence import ExtractionPersistence
from powerforge_extraction.profiles import (
    FAKE_PROFILE,
    EngineeringProfile,
    ExecutionProfile,
    read_profile,
    resolve_profile,
)
from powerforge_extraction.table_profiles import TableProfile
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)
ACTIVE = (RS.PENDING, RS.RUNNING)
UNIT_ACTIVE = (US.PENDING, US.RUNNING)
TRANSIENT = {
    ErrorCode.TIMEOUT.value,
    ErrorCode.UNAVAILABLE.value,
    ErrorCode.RATE_LIMIT.value,
    ErrorCode.INTERRUPTED.value,
    ErrorCode.SOURCE_UNAVAILABLE.value,
    "OCR_TIMEOUT",
    "OCR_INTERRUPTED",
}


class Enqueue(Protocol):
    def enqueue(self, unit_id: UUID) -> None: ...

    def enqueue_source(self, unit_id: UUID) -> None: ...


@dataclass(frozen=True)
class Claim:
    run_id: UUID
    unit_id: UUID
    token: UUID
    profile: ExecutionProfile
    unit_key: str
    attempt_number: int
    artifact_id: UUID
    document_page_id: UUID
    page_number: int
    storage_key: str
    artifact_type: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_spec: PageSpec | None = None
    upstream_unit_id: UUID | None = None


def dependency_ready():
    """Correlated SQL gate so blocked deliveries cannot occupy the dispatch window."""
    upstream = aliased(ExtractionWorkUnit)
    key = ExtractionWorkUnit.execution_metadata["prerequisite_key"].astext
    return or_(
        key.is_(None),
        exists(
            select(upstream.id).where(
                upstream.run_id == ExtractionWorkUnit.run_id,
                upstream.unit_key == key,
                upstream.status == US.COMPLETED,
            )
        ).correlate(ExtractionWorkUnit),
    )


def blocked_dependency():
    upstream = aliased(ExtractionWorkUnit)
    key = ExtractionWorkUnit.execution_metadata["prerequisite_key"].astext
    return key.is_not(None) & ~exists(
        select(upstream.id).where(
            upstream.run_id == ExtractionWorkUnit.run_id,
            upstream.unit_key == key,
            upstream.status.in_((*UNIT_ACTIVE, US.COMPLETED)),
        )
    ).correlate(ExtractionWorkUnit)


class ExtractionCoordinator:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session, self.settings = session, settings
        self.persistence = ExtractionPersistence(session)

    def now(self) -> datetime:
        return self.session.scalar(select(func.clock_timestamp()))

    def _run(self, run_id: UUID) -> ExtractionRun:
        run = self.session.scalar(
            select(ExtractionRun)
            .where(ExtractionRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise ExtractionError("Extraction run not found")
        return run

    def _execution(self, run_id: UUID) -> RunExecution:
        row = self.session.get(RunExecution, run_id, populate_existing=True)
        if row is None:
            raise ExtractionConflict(
                "This historical run has no executable profile; re-extract instead"
            )
        return row

    def start(
        self,
        document_id: UUID,
        *,
        revision_document_id: UUID | None = None,
        profile_key: str = FAKE_PROFILE,
        pages: list[int] | None = None,
        mode: str = "ensure",
    ) -> ExtractionRun:
        if not self.settings.extraction_enabled:
            raise ExtractionDisabled("Extraction is disabled")
        try:
            profile = resolve_profile(profile_key, self.settings)
        except ValueError:
            raise ExtractionError("Unknown or invalid extraction profile") from None
        if profile.provider == "openai" and not self.settings.extraction_external_enabled:
            raise ExtractionDisabled("External extraction must be explicitly enabled")
        document = self.session.scalar(
            select(Document).where(Document.id == document_id).with_for_update()
        )
        if document is None:
            raise ExtractionError("Source document not found")
        if document.size_bytes > self.settings.extraction_max_document_bytes:
            raise ExtractionError("Document exceeds the configured extraction size limit")
        processing = self.session.scalar(
            select(DocumentProcessingRun)
            .where(
                DocumentProcessingRun.document_id == document_id,
                DocumentProcessingRun.status == ProcessingRunStatus.COMPLETED,
            )
            .order_by(DocumentProcessingRun.created_at.desc(), DocumentProcessingRun.id.desc())
            .limit(1)
        )
        if processing is None:
            raise ExtractionConflict("A completed document-processing run is required")
        page_rows = list(
            self.session.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            )
        )
        selected = pages if pages is not None else [p.page_number for p in page_rows]
        if (
            not selected
            or selected != sorted(set(selected))
            or len(selected) > profile.max_pages
            or min(selected) < 1
        ):
            raise ExtractionError("Select distinct ascending pages within the configured limit")
        by_number = {p.page_number: p for p in page_rows}
        artifacts = list(
            self.session.scalars(
                select(PageArtifact).where(PageArtifact.processing_run_id == processing.id)
            )
        )
        chosen = []
        for number in selected:
            page = by_number.get(number)
            if page is None:
                raise ExtractionError("Selected page does not belong to the document")
            available = {a.artifact_type: a for a in artifacts if a.document_page_id == page.id}
            native = available.get(PageArtifactType.NATIVE_TEXT)
            image = available.get(PageArtifactType.ANALYSIS_IMAGE)
            if isinstance(profile, (EngineeringProfile, TableProfile)):
                if profile.input_strategy == "NATIVE_TEXT_ONLY" and native is None:
                    raise ExtractionError("This profile requires pinned native text on every page")
                selected_artifacts = [
                    a
                    for a in (native, image)
                    if a is not None
                    and (a is native or profile.input_strategy != "NATIVE_TEXT_ONLY")
                ]
                if sum(a.size_bytes for a in selected_artifacts) > profile.max_total_input_bytes:
                    raise ExtractionError("Selected page exceeds the combined input limit")
            else:
                selected_artifacts = [native or image] if native or image else []
            if not selected_artifacts or any(
                a.size_bytes > profile.max_input_bytes for a in selected_artifacts
            ):
                raise ExtractionError("Selected page lacks a usable bounded processing artifact")
            for artifact in selected_artifacts:
                if isinstance(
                    profile, (EngineeringProfile, TableProfile)
                ) and artifact.mime_type != (
                    "text/plain"
                    if artifact.artifact_type == PageArtifactType.NATIVE_TEXT
                    else "image/png"
                ):
                    raise ExtractionError("Selected artifact has an unsupported media type")
                if artifact.artifact_type == PageArtifactType.ANALYSIS_IMAGE and (
                    artifact.width_px is None
                    or artifact.height_px is None
                    or artifact.width_px * artifact.height_px > profile.max_image_pixels
                ):
                    raise ExtractionError(
                        "Selected analysis image exceeds the configured pixel limit"
                    )
            chosen.append((page, selected_artifacts))
        compatible = select(ExtractionRun).where(
            ExtractionRun.document_id == document_id,
            ExtractionRun.execution_purpose == "EXTRACTION",
            ExtractionRun.processing_run_id == processing.id,
            ExtractionRun.profile_hash == profile.identity_hash,
            ExtractionRun.selected_pages == selected,
            ExtractionRun.context_fingerprint.is_(None),
        )
        latest = self.session.scalar(
            compatible.order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc()).limit(1)
        )
        active = self.session.scalar(compatible.where(ExtractionRun.status.in_(ACTIVE)).limit(1))
        if active is not None:
            return active
        if mode == "ensure":
            completed = self.session.scalar(
                compatible.where(ExtractionRun.status == RS.COMPLETED)
                .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
                .limit(1)
            )
            if completed is not None:
                return completed
            if latest is not None:
                # A repeated ensure is not permission to spend a fresh full-run budget.
                # Preserve partial successes and require explicit retry/re-extraction.
                return latest
        elif mode != "reextract":
            raise ExtractionError("Unknown extraction request mode")
        predecessor = latest
        if mode == "reextract" and predecessor is None:
            predecessor = self.session.scalar(
                select(ExtractionRun)
                .where(
                    ExtractionRun.document_id == document_id,
                    ExtractionRun.execution_purpose == "EXTRACTION",
                    ExtractionRun.status.not_in(ACTIVE),
                    ExtractionRun.context_fingerprint.is_(None),
                )
                .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
                .limit(1)
            )
        run = self.persistence.create_run(
            RunInput(
                document_id=document_id,
                processing_run_id=processing.id,
                initiated_from_revision_document_id=revision_document_id,
                extractor_version="orchestration-v1",
                schema_version=profile.schema_version,
                profile_version=profile.version,
                profile_hash=profile.identity_hash,
                provider=profile.provider,
                model=profile.model,
                prompt_version=profile.prompt_version,
                prompt_hash=profile.prompt_hash,
                selected_pages=selected,
                stages=list(profile.stages)
                if isinstance(profile, (EngineeringProfile, TableProfile))
                else [profile.stage],
                input_artifact_ids=[a.id for _, artifacts in chosen for a in artifacts],
                reextracts_run_id=predecessor.id if predecessor else None,
            )
        )
        self.session.add(RunExecution(run_id=run.id, configuration=profile.model_dump(mode="json")))
        self.session.flush()
        for page, artifacts in chosen:
            stages = (
                profile.stages
                if isinstance(profile, (EngineeringProfile, TableProfile))
                else [profile.stage]
            )
            for stage in stages:
                metadata = {}
                if isinstance(profile, (EngineeringProfile, TableProfile)):
                    from powerforge_extraction.stage_runtime import planned_metadata

                    metadata = planned_metadata(profile, stage, page.page_number)
                unit = self.persistence.create_work_unit(
                    run.id,
                    WorkUnitInput(
                        unit_key=unit_key(stage, page.page_number),
                        stage=stage,
                        page_numbers=[page.page_number],
                        input_artifact_ids=[artifact.id for artifact in artifacts],
                        execution_metadata=metadata,
                    ),
                )
                self._delivery(unit, self.now())
        self.session.flush()
        return run

    def _delivery(self, unit: ExtractionWorkUnit, available: datetime) -> None:
        self.session.add(
            UnitExecution(
                work_unit_id=unit.id,
                run_id=unit.run_id,
                unit_key=unit.unit_key,
                available_at=available,
                dispatch_after=available,
            )
        )
        self.session.flush()

    def _units(self, run_id: UUID) -> list[ExtractionWorkUnit]:
        return list(
            self.session.scalars(
                select(ExtractionWorkUnit)
                .where(ExtractionWorkUnit.run_id == run_id)
                .order_by(ExtractionWorkUnit.unit_key, ExtractionWorkUnit.attempt_number)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    def aggregate(self, run: ExtractionRun) -> None:
        units = self._units(run.id)
        latest = latest_units(units)
        for unit in latest.values():
            parent = unit.execution_metadata.get("prerequisite_key")
            if (
                unit.status == US.PENDING
                and parent
                and (
                    parent not in latest
                    or latest[parent].status not in (*UNIT_ACTIVE, US.COMPLETED)
                )
            ):
                unit.status, unit.error_code, unit.finished_at = (
                    US.FAILED,
                    ErrorCode.DEPENDENCY.value,
                    self.now(),
                )
        self.session.flush()
        if any(u.status in UNIT_ACTIVE for u in units):
            return
        required = {u.unit_key for u in units if u.required}
        success = {u.unit_key for u in units if u.required and u.status == US.COMPLETED}
        control = self._execution(run.id)
        run.status = (
            RS.CANCELLED
            if control.cancel_requested_at
            else (
                RS.COMPLETED
                if required and required == success
                else RS.PARTIALLY_COMPLETED
                if success
                else RS.FAILED
            )
        )
        run.finished_at = self.now()
        run.error_code = (
            None
            if run.status == RS.COMPLETED
            else (
                "EXTRACTION_CANCELLED" if run.status == RS.CANCELLED else "UNSUCCESSFUL_WORK_UNITS"
            )
        )
        self.session.flush()

    def claim(self, unit_id: UUID, *, purpose: str = "EXTRACTION") -> Claim | None:
        # Serializes admission across processes without holding a lock during provider I/O.
        self.session.execute(text("SELECT pg_advisory_xact_lock(6006001)"))
        unit = self.session.get(ExtractionWorkUnit, unit_id)
        if unit is None:
            return None
        run = self._run(unit.run_id)
        if run.execution_purpose != purpose:
            return None
        control = self._execution(run.id)
        profile = read_profile(control.configuration)
        unit = self.session.get(ExtractionWorkUnit, unit_id, populate_existing=True)
        delivery = self.session.get(UnitExecution, unit_id, populate_existing=True)
        now = self.now()
        if (
            run.status not in ACTIVE
            or control.cancel_requested_at
            or unit.status != US.PENDING
            or delivery is None
            or delivery.available_at > now
        ):
            return None
        if profile.version == "source-layout-profile-v1":
            from powerforge_extraction.layout_service import validate_layout_plan
            from powerforge_extraction.layout_sources import prerequisite_unit

            try:
                validate_layout_plan(unit, profile)
            except ValueError:
                unit.status, unit.error_code, unit.finished_at = (
                    US.FAILED,
                    ErrorCode.INPUT.value,
                    now,
                )
                self.session.flush()
                self.aggregate(run)
                return None
            if unit.stage == "SPATIAL_LAYOUT" and prerequisite_unit(self.session, unit) is None:
                self.aggregate(run)
                return None
        if isinstance(profile, (EngineeringProfile, TableProfile)):
            from powerforge_extraction.stage_runtime import successful_prerequisite, validate_plan

            try:
                validate_plan(unit, profile)
            except (ValueError, KeyError, StopIteration):
                unit.status, unit.error_code, unit.finished_at = (
                    US.FAILED,
                    ErrorCode.INPUT.value,
                    now,
                )
                self.session.flush()
                self.aggregate(run)
                return None
            if (
                unit.execution_metadata.get("prerequisite_key")
                and successful_prerequisite(self.session, unit) is None
            ):
                self.aggregate(run)
                return None
        if control.calls_admitted >= profile.max_calls:
            unit.status, unit.error_code, unit.finished_at = US.FAILED, ErrorCode.BUDGET.value, now
            self.session.flush()
            self.aggregate(run)
            return None
        running = list(
            self.session.execute(
                select(ExtractionWorkUnit.run_id)
                .join(ExtractionRun, ExtractionRun.id == ExtractionWorkUnit.run_id)
                .join(UnitExecution, UnitExecution.work_unit_id == ExtractionWorkUnit.id)
                .where(
                    ExtractionWorkUnit.status == US.RUNNING,
                    ExtractionRun.execution_purpose == purpose,
                )
            )
        )
        if (
            len(running)
            >= (
                self.settings.enrichment_max_concurrent_global
                if purpose == "SOURCE_ENRICHMENT"
                else self.settings.extraction_max_concurrent_global
            )
            or sum(r[0] == run.id for r in running) >= profile.max_concurrent
        ):
            return None
        if (
            not self.settings.enrichment_enabled
            if run.execution_purpose == "SOURCE_ENRICHMENT"
            else not self.settings.extraction_enabled
        ) or (profile.provider == "openai" and not self.settings.extraction_external_enabled):
            unit.status, unit.error_code, unit.finished_at = (
                US.FAILED,
                ErrorCode.DISABLED.value,
                now,
            )
            self.session.flush()
            self.aggregate(run)
            return None
        token = uuid4()
        if run.status == RS.PENDING:
            run.status, run.started_at = RS.RUNNING, now
            self.session.flush()
        timeout = (
            profile.layout_timeout_seconds
            if profile.version == "source-layout-profile-v1" and unit.stage == "SPATIAL_LAYOUT"
            else profile.timeout_seconds
        )
        unit.status, unit.started_at, unit.heartbeat_at = US.RUNNING, now, now
        unit.lease_expires_at = now + timedelta(seconds=min(profile.lease_seconds, timeout + 15))
        delivery.token = token
        delivery.hard_deadline_at = now + timedelta(seconds=timeout + 15)
        control.calls_admitted += 1
        self.session.flush()
        artifact = self.session.get(PageArtifact, UUID(unit.input_artifact_ids[0]))
        page = self.session.get(DocumentPage, artifact.document_page_id)
        page_spec, upstream_id = None, None
        if isinstance(profile, (EngineeringProfile, TableProfile)):
            from powerforge_extraction.engineering_sources import page_spec_for_unit
            from powerforge_extraction.stage_runtime import successful_prerequisite

            page_spec = page_spec_for_unit(self.session, unit.id)
            parent = successful_prerequisite(self.session, unit)
            upstream_id = parent.id if parent else None
        return Claim(
            run.id,
            unit.id,
            token,
            profile,
            unit.unit_key,
            unit.attempt_number,
            artifact.id,
            page.id,
            page.page_number,
            artifact.storage_key,
            artifact.artifact_type.value,
            artifact.mime_type,
            artifact.size_bytes,
            artifact.sha256,
            page_spec,
            upstream_id,
        )

    def _authorized(self, unit_id: UUID, token: UUID):
        unit = self.session.get(ExtractionWorkUnit, unit_id)
        if unit is None:
            raise LeaseLost("Execution lease no longer owns this attempt")
        run = self._run(unit.run_id)
        unit = self.session.get(ExtractionWorkUnit, unit_id, populate_existing=True)
        delivery = self.session.get(UnitExecution, unit_id, populate_existing=True)
        control = self._execution(run.id)
        now = self.now()
        if (
            run.status != RS.RUNNING
            or control.cancel_requested_at
            or unit.status != US.RUNNING
            or delivery is None
            or delivery.token != token
            or unit.lease_expires_at <= now
            or delivery.hard_deadline_at <= now
        ):
            raise LeaseLost("Execution lease no longer owns this attempt")
        self.session.execute(
            text("SELECT set_config('powerforge.extraction_lease_token', :token, true)"),
            {"token": str(token)},
        )
        return run, unit, delivery

    def heartbeat(self, unit_id: UUID, token: UUID) -> bool:
        try:
            run, unit, delivery = self._authorized(unit_id, token)
        except LeaseLost:
            return False
        profile = read_profile(self._execution(run.id).configuration)
        now = self.now()
        unit.heartbeat_at = now
        unit.lease_expires_at = min(
            delivery.hard_deadline_at, now + timedelta(seconds=profile.lease_seconds)
        )
        self.session.flush()
        return True

    def mark_provider_started(
        self, unit_id: UUID, token: UUID, request: ExtractionRequest | None = None
    ) -> None:
        """Persist the external-call boundary, with no transaction held over the call."""
        run, unit, delivery = self._authorized(unit_id, token)
        if delivery.provider_started_at is not None:
            raise LeaseLost("This attempt already crossed the provider-call boundary")
        profile = read_profile(self._execution(run.id).configuration)
        if isinstance(profile, (EngineeringProfile, TableProfile)):
            from powerforge_extraction.stage_runtime import require_supported, stage_call

            require_supported(profile)
            call = stage_call(self.session, unit, profile)
            if request is None or (
                request.stage != unit.stage
                or request.instructions != call.instructions
                or request.schema_version != call.schema_version
                or request.response_model is not call.response_model
                or request.upstream_context != call.upstream_context
            ):
                raise ValueError("Request differs from its pinned stage context")
        delivery.provider_started_at = self.now()
        self.session.flush()

    def _telemetry(
        self,
        unit: ExtractionWorkUnit,
        profile: ExecutionProfile,
        now: datetime,
        outcome: str,
        error: str | None,
        usage: ExecutionUsage | None,
    ) -> None:
        if profile.provider == "local":
            return
        started = self.session.get(UnitExecution, unit.id).provider_started_at
        if started is None:
            return
        prompt_version, prompt_hash = profile.prompt_version, profile.prompt_hash
        schema_version, correlation = profile.schema_version, str(unit.id)
        if isinstance(profile, (EngineeringProfile, TableProfile)):
            from powerforge_extraction.stage_runtime import stage_call

            call = stage_call(self.session, unit, profile)
            prompt_hash, schema_version = call.instruction_hash, call.schema_version
            correlation = call.correlation_id(unit.id)
        # Missing usage stays unknown; admissions retain interrupted call uncertainty.
        cost = None
        if (
            usage
            and profile.pricing_basis
            and profile.input_usd_per_million is not None
            and profile.output_usd_per_million is not None
            and usage.input_tokens is not None
            and usage.output_tokens is not None
        ):
            cost = (
                usage.input_tokens * profile.input_usd_per_million
                + usage.output_tokens * profile.output_usd_per_million
            ) / 1_000_000
        self.persistence.record_ai_call(
            unit.id,
            AICallInput(
                provider=profile.provider,
                model=profile.model,
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
                schema_version=schema_version,
                request_correlation_id=correlation,
                outcome=outcome,
                error_code=error,
                started_at=started,
                finished_at=now,
                duration_ms=max(0, int((now - started).total_seconds() * 1000)),
                input_tokens=usage.input_tokens if usage else None,
                cached_input_tokens=usage.cached_input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                estimated_cost_usd=cost,
                pricing_basis=profile.pricing_basis if cost is not None else None,
            ),
        )

    def complete(
        self,
        unit_id: UUID,
        token: UUID,
        output: WorkUnitOutput,
        usage: ExecutionUsage,
        storage: ObjectStorage,
    ) -> None:
        run, unit, _ = self._authorized(unit_id, token)
        profile = read_profile(self._execution(run.id).configuration)
        self._telemetry(unit, profile, self.now(), "SUCCEEDED", None, usage)
        ExtractionPersistence(self.session, storage).publish(unit.id, output)
        self.aggregate(run)

    def complete_empty_table(self, unit_id: UUID, token: UUID, storage: ObjectStorage) -> None:
        """An ordinary leased admission; no external-call row or invented zero usage."""
        import json

        from powerforge_extraction.stage_runtime import require_supported, stage_call

        run, unit, delivery = self._authorized(unit_id, token)
        profile = read_profile(self._execution(run.id).configuration)
        if (
            not isinstance(profile, TableProfile)
            or unit.stage != "TABLE_INTERPRETATION"
            or delivery.provider_started_at is not None
        ):
            raise ValueError("Empty completion requires an uncalled table interpretation")
        require_supported(profile)
        call = stage_call(self.session, unit, profile)
        if json.loads(call.upstream_context)["tables"]:
            raise ValueError("Nonempty tables require ordinary interpretation execution")
        ExtractionPersistence(self.session, storage).publish(
            unit.id, WorkUnitOutput(diagnostic_counts={"skipped_empty_tables": 1})
        )
        self.aggregate(run)

    def _append_retry(
        self,
        run: ExtractionRun,
        failed: ExtractionWorkUnit,
        profile: ExecutionProfile,
        *,
        delayed: bool,
    ) -> ExtractionWorkUnit:
        new = self.persistence.create_work_unit(
            run.id,
            WorkUnitInput(
                unit_key=failed.unit_key,
                stage=failed.stage,
                page_numbers=failed.page_numbers,
                input_artifact_ids=[UUID(x) for x in failed.input_artifact_ids],
                required=failed.required,
                attempt_number=failed.attempt_number + 1,
                retry_of_work_unit_id=failed.id,
                execution_metadata=failed.execution_metadata,
            ),
        )
        seconds = (
            min(300, profile.backoff_seconds * 2 ** (failed.attempt_number - 1)) if delayed else 0
        )
        self._delivery(new, self.now() + timedelta(seconds=seconds))
        return new

    def fail(
        self, unit_id: UUID, token: UUID, code: ErrorCode, usage: ExecutionUsage | None = None
    ) -> None:
        run, unit, _ = self._authorized(unit_id, token)
        profile = read_profile(self._execution(run.id).configuration)
        self._telemetry(unit, profile, self.now(), "FAILED", code.value, usage)
        self._settle_failure(run, unit, profile, code.value)

    def _settle_failure(
        self, run: ExtractionRun, unit: ExtractionWorkUnit, profile: ExecutionProfile, code: str
    ) -> None:
        unit.status, unit.error_code, unit.finished_at = US.FAILED, code, self.now()
        self.session.flush()
        control = self._execution(run.id)
        if (
            code in TRANSIENT
            and unit.attempt_number < profile.max_attempts
            and control.calls_admitted < profile.max_calls
        ):
            self._append_retry(run, unit, profile, delayed=True)
        self.aggregate(run)

    def retry(self, run_id: UUID, *, purpose: str = "EXTRACTION") -> ExtractionRun:
        run = self._run(run_id)
        if run.execution_purpose != purpose:
            raise ExtractionNotFound("Run not found")
        if run.status in ACTIVE:
            return run
        if run.status in (RS.COMPLETED, RS.CANCELLED):
            raise ExtractionConflict(
                "Completed/cancelled history is immutable; request explicit re-extraction"
            )
        control = self._execution(run.id)
        profile = read_profile(control.configuration)
        if (
            not self.settings.enrichment_enabled
            if run.execution_purpose == "SOURCE_ENRICHMENT"
            else not self.settings.extraction_enabled
        ) or (profile.provider == "openai" and not self.settings.extraction_external_enabled):
            raise ExtractionDisabled("Extraction provider is disabled")
        if control.calls_admitted >= profile.max_calls:
            raise ExtractionConflict(
                "Provider-call budget exhausted; explicit re-extraction is required"
            )
        units = self._units(run.id)
        latest = latest_units(units)
        keys = retryable_keys(units, profile.max_attempts)
        eligible = [u for u in latest.values() if u.unit_key in keys]
        if not eligible:
            raise ExtractionConflict(
                "No unsuccessful logical units remain within the pinned attempt limit"
            )
        run.status, run.finished_at, run.error_code = RS.RUNNING, None, None
        self.session.flush()
        for unit in eligible:
            self._append_retry(run, unit, profile, delayed=False)
        return run

    def cancel(self, run_id: UUID, *, purpose: str = "EXTRACTION") -> ExtractionRun:
        run = self._run(run_id)
        if run.execution_purpose != purpose:
            raise ExtractionNotFound("Run not found")
        if run.status == RS.CANCELLED:
            return run
        if run.status == RS.COMPLETED:
            raise ExtractionConflict("A completed run cannot be cancelled")
        if run.status not in ACTIVE:
            raise ExtractionConflict("Only active runs can be cancelled")
        control = self._execution(run.id)
        control.cancel_requested_at = self.now()
        for unit in self._units(run.id):
            if unit.status in UNIT_ACTIVE:
                unit.status, unit.finished_at, unit.error_code = (
                    US.CANCELLED,
                    self.now(),
                    "EXTRACTION_CANCELLED",
                )
        self.session.flush()
        self.aggregate(run)
        return run

    def reconcile(self, limit: int = 100) -> int:
        now = self.now()
        # Healthy active runs must not consume the bounded recovery window. Once an
        # expired attempt settles, its pending retry yields the next cycle to other runs.
        expired_at = (
            select(func.min(ExtractionWorkUnit.lease_expires_at))
            .where(
                ExtractionWorkUnit.run_id == ExtractionRun.id,
                ExtractionWorkUnit.status == US.RUNNING,
                ExtractionWorkUnit.lease_expires_at <= now,
            )
            .correlate(ExtractionRun)
            .scalar_subquery()
        )
        has_active_units = exists(
            select(ExtractionWorkUnit.id).where(
                ExtractionWorkUnit.run_id == ExtractionRun.id,
                ExtractionWorkUnit.status.in_(UNIT_ACTIVE),
            )
        ).correlate(ExtractionRun)
        has_blocked_units = exists(
            select(ExtractionWorkUnit.id).where(
                ExtractionWorkUnit.run_id == ExtractionRun.id,
                ExtractionWorkUnit.status == US.PENDING,
                blocked_dependency(),
            )
        ).correlate(ExtractionRun)
        runs = list(
            self.session.scalars(
                select(ExtractionRun)
                .join(RunExecution, RunExecution.run_id == ExtractionRun.id)
                .where(
                    ExtractionRun.status.in_(ACTIVE),
                    or_(expired_at.is_not(None), ~has_active_units, has_blocked_units),
                )
                .order_by(expired_at.asc().nulls_last(), ExtractionRun.id)
                .limit(limit)
                .with_for_update(of=ExtractionRun, skip_locked=True)
            )
        )
        recovered = 0
        for run in runs:
            profile = read_profile(self._execution(run.id).configuration)
            for unit in self._units(run.id):
                if unit.status == US.RUNNING and unit.lease_expires_at <= self.now():
                    self._settle_failure(run, unit, profile, ErrorCode.INTERRUPTED.value)
                    recovered += 1
            # No provider call is fabricated for interrupted/ambiguous external work.
            if run.status in ACTIVE:
                self.aggregate(run)
        return recovered

    def dispatch(
        self, enqueue: Enqueue, limit: int = 100, *, purpose: str | None = "EXTRACTION"
    ) -> int:
        now = self.now()
        rows = list(
            self.session.scalars(
                select(UnitExecution)
                .join(ExtractionWorkUnit, ExtractionWorkUnit.id == UnitExecution.work_unit_id)
                .join(ExtractionRun, ExtractionRun.id == UnitExecution.run_id)
                .where(
                    ExtractionWorkUnit.status == US.PENDING,
                    ExtractionRun.status.in_(ACTIVE),
                    UnitExecution.available_at <= now,
                    UnitExecution.dispatch_after <= now,
                    dependency_ready(),
                    True if purpose is None else ExtractionRun.execution_purpose == purpose,
                )
                .order_by(UnitExecution.dispatch_after, UnitExecution.work_unit_id)
                .limit(limit)
                .with_for_update(of=UnitExecution, skip_locked=True)
            )
        )
        sent = 0
        for delivery in rows:
            delivery.dispatch_after = now + timedelta(
                seconds=self.settings.extraction_redispatch_seconds
            )
            delivery.dispatch_count += 1
            try:
                delivery_purpose = self.session.get(
                    ExtractionRun, delivery.run_id
                ).execution_purpose
                if delivery_purpose == "SOURCE_ENRICHMENT":
                    enqueue.enqueue_source(delivery.work_unit_id)
                else:
                    enqueue.enqueue(delivery.work_unit_id)
            except Exception as exc:
                logger.warning(
                    "extraction dispatch deferred", extra={"error_class": type(exc).__name__}
                )
                break
            else:
                delivery.dispatched_at = now
                sent += 1
        self.session.flush()
        return sent
