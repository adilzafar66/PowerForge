"""Provider I/O outside DB transactions, then fenced atomic publication."""

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from io import BytesIO
from threading import Event, Thread
from uuid import UUID

from PIL import Image
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from powerforge_ai.extraction import (
    ErrorCode,
    ExtractionProvider,
    ExtractionRequest,
    ExtractionResponse,
    ProviderFailure,
)
from powerforge_document_processing.storage.base import (
    ObjectStorage,
    StorageError,
    TransientStorageError,
)
from powerforge_extraction.contracts import (
    CandidateEvidenceInput,
    CandidateInput,
    EvidenceInput,
    WorkUnitOutput,
)
from powerforge_extraction.errors import LeaseLost
from powerforge_extraction.orchestration import Claim, ExtractionCoordinator
from powerforge_extraction.profiles import PROMPT, PROMPT_HASH, SCHEMA_HASH
from powerforge_provenance.locations import SourceLocation
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)


def request_for(claim: Claim, storage: ObjectStorage) -> ExtractionRequest:
    profile = claim.profile
    if profile.prompt_hash != PROMPT_HASH or profile.schema_hash != SCHEMA_HASH:
        raise ProviderFailure(ErrorCode.INPUT)
    stream = storage.get(claim.storage_key)
    try:
        data = stream.read(profile.max_input_bytes + 1)
    finally:
        stream.close()
    if (
        len(data) > profile.max_input_bytes
        or len(data) != claim.size_bytes
        or hashlib.sha256(data).hexdigest() != claim.sha256
    ):
        raise ProviderFailure(ErrorCode.INPUT)
    native = None
    image = None
    if claim.artifact_type == "NATIVE_TEXT":
        try:
            native = data.decode("utf-8")
        except UnicodeError:
            raise ProviderFailure(ErrorCode.INPUT) from None
    elif claim.artifact_type == "ANALYSIS_IMAGE":
        try:
            with Image.open(BytesIO(data)) as parsed:
                if (
                    parsed.width * parsed.height > profile.max_image_pixels
                    or parsed.format != "PNG"
                ):
                    raise ValueError("Invalid analysis image")
                parsed.verify()
        except Exception:
            raise ProviderFailure(ErrorCode.INPUT) from None
        image = data
    else:
        raise ProviderFailure(ErrorCode.INPUT)
    return ExtractionRequest(
        work_unit_id=claim.unit_id,
        unit_key=claim.unit_key,
        attempt_number=claim.attempt_number,
        model=profile.model,
        instructions=PROMPT,
        schema_version=profile.schema_version,
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        text=native,
        image=image,
        image_mime_type=claim.mime_type if image else None,
    )


def output_for(
    claim: Claim, request: ExtractionRequest, response: ExtractionResponse
) -> WorkUnitOutput:
    excerpt = response.result.excerpt
    if not excerpt:
        return WorkUnitOutput()
    position = request.text.find(excerpt) if request.text is not None else -1
    if position < 0:
        raise ProviderFailure(ErrorCode.INVALID, response.usage)
    evidence = EvidenceInput(
        location=SourceLocation(
            document_page_id=claim.document_page_id, page_artifact_id=claim.artifact_id
        ),
        source_kind="NATIVE_TEXT",
        extraction_method="AI_TEXT",
        source_snippet=excerpt,
        text_start=position,
        text_end=position + len(excerpt),
        offset_convention="UNICODE_CODEPOINT",
    )
    if claim.profile.execution_kind != "FAKE_TEST":
        # A transport probe is not a production engineering extractor.
        return WorkUnitOutput(evidence=[evidence])
    candidate = CandidateInput(
        kind="UNMAPPED_OBSERVATION",
        mapping_status="UNMAPPED",
        raw_text=excerpt,
        reason_code="FAKE_TEST_OUTPUT",
        explanation="Synthetic test profile; no engineering interpretation performed",
        diagnostics={"synthetic": True, "execution_kind": "FAKE_TEST"},
    )
    return WorkUnitOutput(
        evidence=[evidence],
        candidates=[candidate],
        candidate_evidence=[
            CandidateEvidenceInput(candidate_id=candidate.id, evidence_id=evidence.id)
        ],
    )


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
            request = request_for(claim, storage)
            provider = provider_factory(claim)
            with factory.begin() as session:
                ExtractionCoordinator(session, settings).mark_provider_started(
                    claim.unit_id, claim.token
                )
            response = provider.execute(request)
            # Revalidate objects even if an adapter bypassed constructors.
            response = ExtractionResponse.model_validate(response.model_dump())
            usage = response.usage
            if usage.output_tokens is not None and usage.output_tokens > request.max_output_tokens:
                raise ProviderFailure(ErrorCode.INVALID, usage)
            output = output_for(claim, request, response)
            with factory.begin() as session:
                ExtractionCoordinator(session, settings).complete(
                    claim.unit_id, claim.token, output, usage, storage
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
