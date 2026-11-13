"""Database-authoritative execution. Methods flush; callers own transactions/commits."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from powerforge_ai.extraction import ErrorCode, ExecutionUsage, ExtractionRequest
from powerforge_document_processing.models import (
    DocumentPage,
    PageArtifact,
)
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_extraction.contracts import AICallInput, WorkUnitInput, WorkUnitOutput
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
    ExecutionProfile,
    read_profile,
)
from powerforge_shared.config import Settings

if TYPE_CHECKING:
    from powerforge_extraction.enriched_publication import VerifiedEnrichedPublication

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
            raise ExtractionConflict("Run has no pinned execution configuration")
        return row

    def start(
        self,
        document_id: UUID,
        *,
        revision_document_id: UUID | None = None,
        profile_key: str = "phase-6r",
        pages: list[int] | None = None,
        mode: str = "ensure",
        enrichment_bindings=None,
    ) -> ExtractionRun:
        from powerforge_extraction.enriched_planning import start_phase6r
        from powerforge_extraction.phase6r_profile import KEY

        if profile_key != KEY:
            raise ExtractionError("Unknown extraction profile")
        return start_phase6r(
            self, document_id, revision_document_id, pages, mode, enrichment_bindings
        )

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
        if (profile.provider == "local") != (purpose == "SOURCE_ENRICHMENT"):
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
        from powerforge_extraction.phase6r_profile import Phase6RProfile
        from powerforge_extraction.phase6r_runtime import prerequisite_result, validate_plan

        no_call = False
        if isinstance(profile, Phase6RProfile):
            try:
                validate_plan(self.session, unit, profile)
                if unit.stage == "ATTRIBUTE_EXTRACTION":
                    from powerforge_extraction.phase6r_contracts import attribute_catalog
                    from powerforge_extraction.phase6r_runtime import recognition_result

                    parent = prerequisite_result(self.session, unit)
                    if parent is None:
                        return None
                    no_call = not attribute_catalog(recognition_result(parent))
            except (ValueError, KeyError, StopIteration):
                unit.status, unit.error_code, unit.finished_at = (
                    US.FAILED,
                    ErrorCode.INPUT.value,
                    now,
                )
                self.session.flush()
                self.aggregate(run)
                return None
        if not no_call and control.calls_admitted >= profile.max_calls:
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
            else not (self.settings.extraction_enabled and self.settings.extraction_phase6r_fake)
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
        control.calls_admitted += int(not no_call)
        self.session.flush()
        artifact = self.session.get(PageArtifact, UUID(unit.input_artifact_ids[0]))
        page = self.session.get(DocumentPage, artifact.document_page_id)
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
        if profile.provider == "local":
            raise ValueError("Local source jobs cannot start an AI call")
        from powerforge_extraction.phase6r_profile import PROMPT, RESPONSES

        if request is None or (
            request.work_unit_id != unit.id
            or request.stage != unit.stage
            or request.instructions != PROMPT
            or request.response_model is not RESPONSES[unit.stage]
            or request.schema_version != profile.schema_version
        ):
            raise ValueError("Request differs from its pinned Phase 6R stage")
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
        *,
        verification: VerifiedEnrichedPublication | None = None,
    ) -> None:
        run, unit, _ = self._authorized(unit_id, token)
        profile = read_profile(self._execution(run.id).configuration)
        self._telemetry(unit, profile, self.now(), "SUCCEEDED", None, usage)
        ExtractionPersistence(self.session, storage).publish(
            unit.id, output, verification=verification
        )
        self.aggregate(run)

    def complete_stage(self, unit_id, token, wire, result, usage):
        from powerforge_extraction.phase6r_contracts import NoEligibleAttributes
        from powerforge_extraction.phase6r_runtime import store_result

        run, unit, delivery = self._authorized(unit_id, token)
        if isinstance(result, NoEligibleAttributes) != (delivery.provider_started_at is None):
            raise ValueError("Stage outcome differs from the provider call boundary")
        if run.execution_purpose != "EXTRACTION":
            raise ValueError("AI stage results require an extraction run")
        profile = read_profile(self._execution(run.id).configuration)
        store_result(self.session, unit, wire, result)
        self._telemetry(unit, profile, self.now(), "SUCCEEDED", None, usage)
        unit.status, unit.finished_at = US.COMPLETED, self.now()
        self.session.flush()
        units = self._units(run.id)
        successful = {row.unit_key for row in units if row.status == US.COMPLETED}
        run.units_completed = len(successful)
        run.pages_processed = sum(
            all(unit_key(stage, page) in successful for stage in profile.stages)
            for page in run.selected_pages
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
        if profile.provider == "openai" and code in {
            ErrorCode.INTERRUPTED.value,
            ErrorCode.TIMEOUT.value,
            ErrorCode.UNAVAILABLE.value,
        }:
            from powerforge_extraction.operation_models import (
                UNKNOWN_PROVIDER_OUTCOME,
                managed_remote_run,
            )

            delivery = self.session.get(UnitExecution, unit.id)
            if (
                delivery
                and delivery.provider_started_at
                and managed_remote_run(self.session, run.id)
            ):
                code = UNKNOWN_PROVIDER_OUTCOME
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

    def retry(
        self,
        run_id: UUID,
        *,
        purpose: str = "EXTRACTION",
        acknowledge_unknown_outcome: bool = False,
        page_id: UUID | None = None,
        stage: str | None = None,
        expected_attempt: int | None = None,
    ) -> ExtractionRun:
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
            else not (self.settings.extraction_enabled and self.settings.extraction_phase6r_fake)
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
        if stage is not None:
            target = next(
                (
                    u
                    for u in latest.values()
                    if u.stage == stage
                    and u.execution_metadata.get("source_page_id") == str(page_id)
                ),
                None,
            )
            if target is None:
                raise ExtractionNotFound("Extraction page stage not found")
            if target.attempt_number != expected_attempt:
                raise ExtractionConflict("The selected attempt changed")
            if target in eligible:
                eligible = [target]
                # Reopen a dependent that was never called because recognition failed.
                eligible.extend(
                    u
                    for u in latest.values()
                    if u.unit_key in keys
                    and u.error_code == ErrorCode.DEPENDENCY.value
                    and u.execution_metadata.get("prerequisite_key") == target.unit_key
                )
            else:
                eligible = []
        if not eligible:
            raise ExtractionConflict(
                "No unsuccessful logical units remain within the pinned attempt limit"
            )
        from powerforge_extraction.operation_models import UNKNOWN_PROVIDER_OUTCOME

        if not acknowledge_unknown_outcome and any(
            unit.error_code == UNKNOWN_PROVIDER_OUTCOME for unit in eligible
        ):
            raise ExtractionConflict(
                "Provider outcome unknown. Confirm that retry may incur another charge."
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
