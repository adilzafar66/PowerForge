"""Provider I/O outside DB transactions, then fenced atomic publication."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from hashlib import sha256
from threading import Event, Thread
from time import perf_counter_ns
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from powerforge_ai.extraction import (
    AttributeOutput,
    ErrorCode,
    ExecutionUsage,
    ExtractionProvider,
    ProviderFailure,
    ResponseValidationFailure,
    ValidationIssue,
)
from powerforge_document_processing.storage.base import (
    ObjectStorage,
    StorageError,
    TransientStorageError,
)
from powerforge_extraction.errors import LeaseLost
from powerforge_extraction.orchestration import Claim, ExtractionCoordinator
from powerforge_extraction.performance import AttemptPerformance, active_performance, measure
from powerforge_extraction.response_diagnostics import validation_issues
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)


@contextmanager
def heartbeats(factory: sessionmaker[Session], claim: Claim, settings: Settings) -> Iterator[None]:
    stop = Event()

    interval = max(1, claim.profile.lease_seconds / 3)

    def maintain() -> None:
        while True:
            waiting_at = perf_counter_ns()
            if stop.wait(interval):
                return
            started_at = perf_counter_ns()
            scheduling_delay_ms = max(
                0, (started_at - waiting_at) // 1_000_000 - int(interval * 1000)
            )
            details = {
                "work_unit_id": str(claim.unit_id),
                "heartbeat_schedule_delay_ms": scheduling_delay_ms,
            }
            if scheduling_delay_ms >= interval * 1000:
                logger.warning("extraction heartbeat woke late", extra=details)
            try:
                with factory.begin() as session:
                    if not ExtractionCoordinator(session, settings).heartbeat(
                        claim.unit_id, claim.token
                    ):
                        return
            except Exception as exc:
                sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
                logger.warning(
                    "extraction heartbeat unavailable",
                    extra={
                        **details,
                        "error_class": type(exc).__name__,
                        "sqlstate": (
                            sqlstate
                            if isinstance(sqlstate, str)
                            and len(sqlstate) == 5
                            and sqlstate.isascii()
                            and sqlstate.isalnum()
                            else None
                        ),
                        "heartbeat_db_ms": (perf_counter_ns() - started_at) // 1_000_000,
                    },
                )
            else:
                db_ms = (perf_counter_ns() - started_at) // 1_000_000
                logger.debug(
                    "extraction heartbeat renewed",
                    extra={**details, "heartbeat_db_ms": db_ms},
                )
                if db_ms >= interval * 1000:
                    logger.warning(
                        "extraction heartbeat database renewal was slow",
                        extra={**details, "heartbeat_db_ms": db_ms},
                    )

    thread = Thread(target=maintain, name="extraction-lease-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2)


def execute_unit(
    unit_id: UUID,
    factory: sessionmaker[Session],
    storage: ObjectStorage,
    settings: Settings,
    provider_factory: Callable[[Claim], ExtractionProvider],
    *,
    audit_storage: ObjectStorage | None = None,
) -> bool:
    with factory.begin() as session:
        claim = ExtractionCoordinator(session, settings).claim(unit_id)
    if claim is None:
        return False
    performance = (
        AttemptPerformance(queue_wait_ms=claim.queue_wait_ms)
        if claim.unit_key.startswith("ATTRIBUTE_EXTRACTION:")
        else None
    )
    token = active_performance.set(performance)
    try:
        return _execute_claim(claim, factory, storage, settings, provider_factory, audit_storage)
    finally:
        active_performance.reset(token)


def _execute_claim(claim, factory, storage, settings, provider_factory, audit_storage):
    unit_id = claim.unit_id
    attempt_start = perf_counter_ns()
    usage = None
    audit = None
    try:
        with heartbeats(factory, claim, settings):
            from powerforge_extraction.attribute_admission import (
                AttributeAdmission,
                admit_attributes,
            )
            from powerforge_extraction.identities import canonical_json
            from powerforge_extraction.publication import build_publication
            from powerforge_extraction.response_audit import response_audit_writer, retain_output
            from powerforge_extraction.stage_contracts import AttributeRequest, parse_response
            from powerforge_extraction.stage_execution import provider_input, request_for

            wire, request, source = request_for(factory, storage, claim)
            result = wire
            if request is not None:
                provider = provider_factory(claim)
                live_attributes = (
                    isinstance(wire, AttributeRequest) and claim.profile.provider == "openai"
                )
                with measure("request_build"):
                    if isinstance(wire, AttributeRequest) and (
                        wire.attribute_description_version
                        != claim.profile.manifest["attribute_descriptions"]
                        or wire.output_version != claim.profile.attribute_output_version
                        or request.input_version != wire.input_version
                        or ((request.image is None) != (wire.input_version == "readable-text-v1"))
                        or (
                            request.image is not None
                            and sha256(request.image).hexdigest() != wire.page.image_sha256
                        )
                        or request.text != canonical_json(provider_input(wire))
                    ):
                        raise ProviderFailure(ErrorCode.INPUT)
                with (
                    measure("audit_store")
                    if live_attributes and audit_storage is None
                    else nullcontext()
                ):
                    if live_attributes and audit_storage is None:
                        audit_storage = response_audit_writer(
                            settings, claim.profile.response_audit_retention_days
                        )
                with factory.begin() as session:
                    ExtractionCoordinator(session, settings).mark_provider_started(
                        claim.unit_id, claim.token, request
                    )
                response = provider.execute(request)
                usage = ExecutionUsage.model_validate(response.usage.model_dump())
                over_budget = (
                    usage.output_tokens is not None
                    and usage.output_tokens > request.max_output_tokens
                )
                budget_issue = ValidationIssue(category="CAPACITY", error_type="output_token_limit")
                if isinstance(wire, AttributeRequest):
                    with measure("admission"):
                        if (
                            not isinstance(response, AttributeOutput)
                            or response.request is not request
                        ):
                            raise ProviderFailure(
                                ErrorCode.INVALID,
                                usage,
                                diagnostics=(
                                    ValidationIssue(
                                        category="ENVELOPE", error_type="request_binding_mismatch"
                                    ),
                                ),
                            )
                    raw = response.output_text
                    retained = None
                    if audit_storage is not None:
                        with measure("audit_store"):
                            retained = retain_output(
                                audit_storage,
                                claim.unit_id,
                                claim.profile.response_audit_retention_days,
                                raw,
                                datetime.now(UTC),
                            )
                    with measure("admission"):
                        admission = (
                            AttributeAdmission(fatal=(budget_issue,))
                            if over_budget
                            else admit_attributes(wire, raw)
                        )
                        if (performance := active_performance.get()) is not None:
                            performance.assertions_received = admission.received
                            performance.assertions_accepted = admission.accepted
                            performance.assertions_quarantined = len(admission.rejected)
                            performance.assertions_overflowed = len(admission.overflow_indices)
                        if retained is not None:
                            audit = (wire, retained, admission, request)
                        if admission.result is None:
                            raise ProviderFailure(
                                ErrorCode.INVALID, usage, diagnostics=admission.fatal
                            )
                        result = admission.result
                else:
                    if over_budget:
                        raise ProviderFailure(ErrorCode.INVALID, usage, diagnostics=(budget_issue,))
                    try:
                        result = parse_response(wire, response.result.model_dump_json().encode())
                    except ResponseValidationFailure as exc:
                        raise ProviderFailure(
                            ErrorCode.INVALID, usage, diagnostics=(exc.issue,)
                        ) from None
                    except ValidationError as exc:
                        raise ProviderFailure(
                            ErrorCode.INVALID, usage, diagnostics=validation_issues(exc)
                        ) from None
            with measure("localization_normalization"):
                publication = build_publication(wire, result, source)
            try:
                with factory.begin() as session:
                    ExtractionCoordinator(session, settings).complete_stage(
                        claim.unit_id,
                        claim.token,
                        wire,
                        result,
                        usage,
                        publication,
                        audit=audit,
                        request=request,
                        attempt_start=attempt_start,
                    )
            except Exception:
                if (performance := active_performance.get()) is not None:
                    performance.failure_stage = "db_publish"
                raise
    except LeaseLost:
        return False
    except Exception as exc:
        diagnostics = ()
        if isinstance(exc, ProviderFailure):
            code, usage, diagnostics = exc.code, exc.usage or usage, exc.diagnostics
        elif isinstance(exc, ValidationError):
            code = ErrorCode.INVALID
        elif isinstance(exc, TransientStorageError):
            code = ErrorCode.SOURCE_UNAVAILABLE
        elif isinstance(exc, StorageError | UnicodeError | ValueError):
            code = ErrorCode.INPUT
        elif type(exc).__name__ == "SoftTimeLimitExceeded":
            code = ErrorCode.TIMEOUT
        else:
            code = ErrorCode.INTERNAL
        logger.warning(
            "extraction attempt failed",
            extra={"error_code": code.value, "work_unit_id": str(unit_id)},
        )
        try:
            with factory.begin() as session:
                ExtractionCoordinator(session, settings).fail(
                    claim.unit_id,
                    claim.token,
                    code,
                    usage,
                    diagnostics=diagnostics,
                    audit=audit,
                    attempt_start=attempt_start,
                )
        except LeaseLost:
            return False
        except Exception:
            # Do not let Celery render SQL/provider exception contexts containing source data.
            raise RuntimeError("Extraction state unavailable; lease recovery is required") from None
    return True
