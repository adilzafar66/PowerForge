"""Provider I/O outside DB transactions, then fenced atomic publication."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event, Thread
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
from powerforge_extraction.response_diagnostics import validation_issues
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)


@contextmanager
def heartbeats(factory: sessionmaker[Session], claim: Claim, settings: Settings) -> Iterator[None]:
    stop = Event()

    def maintain() -> None:
        while not stop.wait(max(1, claim.profile.lease_seconds / 3)):
            try:
                with factory.begin() as session:
                    if not ExtractionCoordinator(session, settings).heartbeat(
                        claim.unit_id, claim.token
                    ):
                        return
            except Exception as exc:
                logger.warning(
                    "extraction heartbeat unavailable", extra={"error_class": type(exc).__name__}
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
    usage = None
    audit = None
    try:
        with heartbeats(factory, claim, settings):
            from powerforge_extraction.attribute_admission import (
                AttributeAdmission,
                admit_attributes,
            )
            from powerforge_extraction.publication import build_publication
            from powerforge_extraction.response_audit import response_audit_writer, retain_output
            from powerforge_extraction.stage_contracts import AttributeRequest, parse_response
            from powerforge_extraction.stage_execution import request_for

            wire, request, source = request_for(factory, storage, claim)
            result = wire
            if request is not None:
                provider = provider_factory(claim)
                live_attributes = (
                    isinstance(wire, AttributeRequest) and claim.profile.provider == "openai"
                )
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
                    if live_attributes and not isinstance(response, AttributeOutput):
                        raise ProviderFailure(ErrorCode.AUDIT, usage)
                    raw = (
                        response.output_text
                        if isinstance(response, AttributeOutput)
                        else response.result.model_dump_json().encode()
                    )
                    retained = None
                    if isinstance(response, AttributeOutput):
                        if audit_storage is None:
                            raise ProviderFailure(ErrorCode.AUDIT, usage)
                        retained = retain_output(
                            audit_storage,
                            claim.unit_id,
                            claim.profile.response_audit_retention_days,
                            raw,
                            datetime.now(UTC),
                        )
                    admission = (
                        AttributeAdmission(fatal=(budget_issue,))
                        if over_budget
                        else admit_attributes(wire, raw)
                    )
                    if retained is not None:
                        audit = (wire, retained, admission)
                    if admission.result is None:
                        raise ProviderFailure(ErrorCode.INVALID, usage, diagnostics=admission.fatal)
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
            publication = build_publication(wire, result, source)
            with factory.begin() as session:
                ExtractionCoordinator(session, settings).complete_stage(
                    claim.unit_id, claim.token, wire, result, usage, publication, audit=audit
                )
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
                    claim.unit_id, claim.token, code, usage, diagnostics=diagnostics, audit=audit
                )
        except LeaseLost:
            return False
        except Exception:
            # Do not let Celery render SQL/provider exception contexts containing source data.
            raise RuntimeError("Extraction state unavailable; lease recovery is required") from None
    return True
