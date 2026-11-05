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
    ExecutionUsage,
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
from powerforge_extraction.profiles import PROMPT, PROMPT_HASH, SCHEMA_HASH, EngineeringProfile
from powerforge_provenance.locations import SourceLocation
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)


def engineering_request(claim: Claim, storage: ObjectStorage, factory: sessionmaker[Session]):
    from powerforge_extraction.engineering_sources import load_recognition_context
    from powerforge_extraction.grounding import load_page_sources
    from powerforge_extraction.models import ExtractionWorkUnit
    from powerforge_extraction.stage_runtime import require_supported, stage_call

    profile = claim.profile
    require_supported(profile)
    if claim.page_spec is None:
        raise ValueError("Pinned engineering page descriptors are required")
    sources = load_page_sources(
        claim.page_spec,
        storage,
        max_artifact_bytes=profile.max_input_bytes,
        max_total_bytes=profile.max_total_input_bytes,
        max_image_pixels=profile.max_image_pixels,
    )
    if sources.text is not None and len(sources.text) > profile.max_text_chars:
        raise ValueError("Native text exceeds the pinned context limit")
    with factory.begin() as session:
        unit = session.get(ExtractionWorkUnit, claim.unit_id)
        call = stage_call(session, unit, profile)
        if call.upstream_unit_id != claim.upstream_unit_id:
            raise ValueError("Recognition attempt differs from claimed context")
        context = (
            load_recognition_context(session, sources, call.upstream_unit_id)
            if call.upstream_unit_id
            else None
        )
    request = ExtractionRequest(
        work_unit_id=claim.unit_id,
        unit_key=claim.unit_key,
        attempt_number=claim.attempt_number,
        model=profile.model,
        instructions=call.instructions,
        schema_version=call.schema_version,
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        text=sources.text,
        image=sources.image,
        image_mime_type="image/png" if sources.image is not None else None,
        response_model=call.response_model,
        stage=claim.page_spec.stage,
        source_roles=tuple(item.role for item in claim.page_spec.artifacts),
        upstream_context=call.upstream_context,
        image_detail=profile.image_detail,
    )
    return request, sources, context


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
            if isinstance(claim.profile, EngineeringProfile):
                request, sources, context = engineering_request(claim, storage, factory)
            else:
                request = request_for(claim, storage)
            provider = provider_factory(claim)
            with factory.begin() as session:
                ExtractionCoordinator(session, settings).mark_provider_started(
                    claim.unit_id, claim.token, request
                )
            response = provider.execute(request)
            # Revalidate objects even if an adapter bypassed constructors.
            usage = ExecutionUsage.model_validate(response.usage.model_dump())
            response = ExtractionResponse[request.response_model].model_validate(
                response.model_dump()
            )
            if usage.output_tokens is not None and usage.output_tokens > request.max_output_tokens:
                raise ProviderFailure(ErrorCode.INVALID, usage)
            if isinstance(claim.profile, EngineeringProfile):
                from powerforge_extraction.engineering_output import (
                    convert_attributes,
                    convert_equipment,
                )

                try:
                    output = (
                        convert_equipment(response.result, sources)
                        if request.stage == "EQUIPMENT_RECOGNITION"
                        else convert_attributes(response.result, sources, context)
                    )
                except (ValueError, ValidationError):
                    raise ProviderFailure(ErrorCode.INVALID, usage) from None
                if claim.profile.execution_kind == "FAKE_TEST":
                    output = output.model_copy(
                        update={
                            "candidates": [
                                candidate.model_copy(
                                    update={
                                        "diagnostics": {
                                            **candidate.diagnostics,
                                            "synthetic": True,
                                            "execution_kind": "FAKE_TEST",
                                        }
                                    }
                                )
                                for candidate in output.candidates
                            ]
                        }
                    )
            else:
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
