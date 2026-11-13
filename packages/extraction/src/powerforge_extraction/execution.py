"""Provider I/O outside DB transactions, then fenced atomic publication."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Event, Thread
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from powerforge_ai.extraction import (
    ErrorCode,
    ExecutionUsage,
    ExtractionProvider,
    ProviderFailure,
)
from powerforge_document_processing.storage.base import (
    ObjectStorage,
    StorageError,
    TransientStorageError,
)
from powerforge_extraction.errors import LeaseLost
from powerforge_extraction.orchestration import Claim, ExtractionCoordinator
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
) -> bool:
    with factory.begin() as session:
        claim = ExtractionCoordinator(session, settings).claim(unit_id)
    if claim is None:
        return False
    usage = None
    try:
        with heartbeats(factory, claim, settings):
            from powerforge_extraction.phase6r_contracts import parse_response
            from powerforge_extraction.phase6r_runtime import request_for as stage_request

            wire, request = stage_request(factory, storage, claim)
            result = wire
            if request is not None:
                provider = provider_factory(claim)
                with factory.begin() as session:
                    ExtractionCoordinator(session, settings).mark_provider_started(
                        claim.unit_id, claim.token, request
                    )
                response = provider.execute(request)
                usage = ExecutionUsage.model_validate(response.usage.model_dump())
                if (
                    usage.output_tokens is not None
                    and usage.output_tokens > request.max_output_tokens
                ):
                    raise ProviderFailure(ErrorCode.INVALID, usage)
                try:
                    result = parse_response(wire, response.result.model_dump_json().encode())
                except ValueError:
                    raise ProviderFailure(ErrorCode.INVALID, usage) from None
            with factory.begin() as session:
                ExtractionCoordinator(session, settings).complete_stage(
                    claim.unit_id, claim.token, wire, result, usage
                )
    except LeaseLost:
        return False
    except Exception as exc:
        if isinstance(exc, ProviderFailure):
            code, usage = exc.code, exc.usage
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
                    claim.unit_id, claim.token, code, usage
                )
        except LeaseLost:
            return False
        except Exception:
            # Do not let Celery render SQL/provider exception contexts containing source data.
            raise RuntimeError("Extraction state unavailable; lease recovery is required") from None
    return True
