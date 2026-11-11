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
from powerforge_ai.extraction_diagnostics import FailureDetail, validation_issues
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
from powerforge_extraction.local_diagnostic_capture import LocalDiagnosticCapture
from powerforge_extraction.orchestration import Claim, ExtractionCoordinator, empty_table_output
from powerforge_extraction.profiles import PROMPT, PROMPT_HASH, SCHEMA_HASH, EngineeringProfile
from powerforge_extraction.stage_diagnostics import SourceRejection, StageDiagnostics
from powerforge_extraction.table_profiles import TableProfile
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
    *,
    capture: LocalDiagnosticCapture | None = None,
) -> bool:
    with factory.begin() as session:
        claim = ExtractionCoordinator(session, settings).claim(unit_id)
    if claim is None:
        return False
    usage = None
    diagnostics = None
    failure_reason = None
    try:
        with heartbeats(factory, claim, settings):
            from powerforge_extraction.enriched_profiles import (
                COMPACT_TABLES,
                DISTRIBUTED_ENGINEERING,
                SOURCE_SUPPORTED_TABLES,
                EnrichedTableProfile,
                is_enriched,
                is_semantic,
            )
            from powerforge_extraction.enriched_publication import prepare_publication

            enriched = is_enriched(claim.profile)
            if enriched:
                diagnostics = StageDiagnostics(capture.bind(unit_id) if capture else None)
                from powerforge_extraction.enriched_runtime import request_for as enriched_request

                try:
                    request, sources, context = enriched_request(claim, storage, factory)
                except (ValidationError, OSError):
                    raise ProviderFailure(ErrorCode.INPUT) from None
                diagnostics.request_ready(request, sources)
                if (
                    isinstance(claim.profile, EnrichedTableProfile)
                    and context is not None
                    and not context.tables
                ):
                    diagnostics.provider_outcome = "SKIPPED_EMPTY_PREREQUISITE"
                    diagnostics.phase = "PUBLICATION"
                    empty = empty_table_output()
                    try:
                        verification = prepare_publication(factory, storage, claim.unit_id, empty)
                    except (ValidationError, OSError):
                        raise ProviderFailure(ErrorCode.INPUT) from None
                    with factory.begin() as session:
                        ExtractionCoordinator(session, settings).complete_empty_table(
                            claim.unit_id,
                            claim.token,
                            storage,
                            verification=verification,
                            trace=diagnostics.publication_trace(empty),
                        )
                    if diagnostics.capture is not None:
                        diagnostics.capture.committed()
                    return True
            elif isinstance(claim.profile, TableProfile):
                from powerforge_extraction.table_execution import table_request

                request, sources, context = table_request(claim, storage, factory)
                if context is not None and not context.tables:
                    with factory.begin() as session:
                        ExtractionCoordinator(session, settings).complete_empty_table(
                            claim.unit_id, claim.token, storage
                        )
                    return True
            elif isinstance(claim.profile, EngineeringProfile):
                request, sources, context = engineering_request(claim, storage, factory)
            else:
                request = request_for(claim, storage)
            if diagnostics:
                diagnostics.phase = "PROVIDER"
            provider = provider_factory(claim)
            with factory.begin() as session:
                ExtractionCoordinator(session, settings).mark_provider_started(
                    claim.unit_id, claim.token, request
                )
            if diagnostics:
                diagnostics.provider_outcome = "ATTEMPTED"
            response = provider.execute(request)
            if diagnostics:
                diagnostics.phase = "PARSE"
            # Revalidate objects even if an adapter bypassed constructors.
            usage = ExecutionUsage.model_validate(response.usage.model_dump())
            response = ExtractionResponse[request.response_model].model_validate(
                response.model_dump()
            )
            if diagnostics:
                diagnostics.parsed(response.result)
            if usage.output_tokens is not None and usage.output_tokens > request.max_output_tokens:
                raise ProviderFailure(
                    ErrorCode.INVALID, usage, detail=FailureDetail.OUTPUT_TOKEN_LIMIT
                )
            verification = None
            if enriched:
                from powerforge_extraction.enriched_output import (
                    convert_attributes,
                    convert_equipment,
                )
                from powerforge_extraction.enriched_tables import interpret, reconstruct

                diagnostics.phase = "CONVERSION"
                try:
                    if is_semantic(claim.profile) and request.stage != "TABLE_RECONSTRUCTION":
                        from powerforge_extraction.semantic_output import convert_engineering
                        from powerforge_extraction.semantic_tables import interpret_tables

                        if request.stage == "TABLE_INTERPRETATION":
                            output = interpret_tables(
                                response.result,
                                sources,
                                context,
                                trace=diagnostics,
                                source_supported=claim.profile.key
                                in (SOURCE_SUPPORTED_TABLES, COMPACT_TABLES),
                                compact=claim.profile.key == COMPACT_TABLES,
                            )
                        else:
                            output = convert_engineering(
                                response.result,
                                sources,
                                context,
                                trace=diagnostics,
                                distributed=claim.profile.key == DISTRIBUTED_ENGINEERING,
                            )
                    elif request.stage == "EQUIPMENT_RECOGNITION":
                        output = convert_equipment(response.result, sources, trace=diagnostics)
                    elif request.stage == "ATTRIBUTE_EXTRACTION":
                        output = convert_attributes(
                            response.result, sources, context, trace=diagnostics
                        )
                    elif request.stage == "TABLE_RECONSTRUCTION":
                        if claim.profile.key == COMPACT_TABLES:
                            from powerforge_extraction.table_reconstruction_v4 import (
                                reconstruct_compact,
                            )

                            output, _ = reconstruct_compact(
                                response.result,
                                sources,
                                trace=diagnostics,
                                legacy_blank_cells=claim.profile.legacy_blank_cells,
                            )
                        else:
                            output, _ = reconstruct(response.result, sources, trace=diagnostics)
                    else:
                        output = interpret(response.result, sources, context, trace=diagnostics)
                except (ValueError, ValidationError) as exc:
                    if isinstance(exc, SourceRejection):
                        failure_reason = exc.reason
                        diagnostics.observe("GROUNDING_REJECTED", reason=exc.reason)
                    raise ProviderFailure(ErrorCode.INVALID, usage) from None
                if claim.profile.execution_kind == "FAKE_TEST":
                    output = output.model_copy(
                        update={
                            "candidates": [
                                c.model_copy(
                                    update={
                                        "diagnostics": {
                                            **c.diagnostics,
                                            "synthetic": True,
                                            "execution_kind": "FAKE_TEST",
                                        }
                                    }
                                )
                                for c in output.candidates
                            ]
                        }
                    )
                diagnostics.phase = "PUBLICATION"
                diagnostics.counts["CONVERTED_CANDIDATES"] = len(output.candidates)
                diagnostics.counts["CONVERTED_TABLES"] = len(output.tables)
                try:
                    verification = prepare_publication(factory, storage, claim.unit_id, output)
                except (ValidationError, OSError):
                    raise ProviderFailure(ErrorCode.INPUT, usage) from None
            elif isinstance(claim.profile, TableProfile):
                from powerforge_extraction.table_grounding import convert_table_reconstruction
                from powerforge_extraction.table_output import convert_table_interpretation

                try:
                    output = (
                        convert_table_reconstruction(response.result, sources)
                        if request.stage == "TABLE_RECONSTRUCTION"
                        else convert_table_interpretation(response.result, sources, context)
                    )
                except (ValueError, ValidationError):
                    raise ProviderFailure(ErrorCode.INVALID, usage) from None
                if claim.profile.execution_kind == "FAKE_TEST":
                    output = output.model_copy(
                        update={
                            "candidates": [
                                c.model_copy(
                                    update={
                                        "diagnostics": {
                                            **c.diagnostics,
                                            "synthetic": True,
                                            "execution_kind": "FAKE_TEST",
                                        }
                                    }
                                )
                                for c in output.candidates
                            ]
                        }
                    )
            elif isinstance(claim.profile, EngineeringProfile):
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
                    claim.unit_id,
                    claim.token,
                    output,
                    usage,
                    storage,
                    verification=verification,
                    trace=diagnostics.publication_trace(output) if diagnostics else None,
                )
            if diagnostics and diagnostics.capture is not None:
                diagnostics.capture.committed()
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
        trace = None
        if diagnostics:
            if diagnostics.phase in ("PROVIDER", "PARSE"):
                if isinstance(exc, ProviderFailure):
                    diagnostics.provider_detail, diagnostics.issues = exc.detail, exc.issues
                elif isinstance(exc, ValidationError):
                    diagnostics.issues = validation_issues(exc, request.response_model)
                    diagnostics.provider_detail = (
                        diagnostics.issues[0].reason
                        if diagnostics.issues
                        else FailureDetail.SCHEMA_VALIDATION
                    )
                if diagnostics.provider_outcome == "ATTEMPTED":
                    diagnostics.provider_outcome = (
                        "REQUEST_REJECTED" if code == ErrorCode.INPUT else code.value
                    )
                if code == ErrorCode.INVALID and diagnostics.provider_detail not in (
                    FailureDetail.PROVIDER_HTTP_ERROR,
                    FailureDetail.PROVIDER_FAILED_RESPONSE,
                ):
                    diagnostics.phase = "PARSE"
            trace = diagnostics.result(reason=failure_reason or code.value)
        log_context = {"error_code": code.value, "work_unit_id": str(unit_id)}
        if trace is not None:
            log_context.update(
                stage=claim.unit_key.split(":", 1)[0],
                profile_version=claim.profile.version,
                schema_version=trace.schema_version,
                diagnostic_phase=trace.phase,
                diagnostic_reason=trace.reason,
                provider_detail=trace.provider_detail,
                validation_issues=[issue.model_dump(mode="json") for issue in trace.issues],
            )
        logger.warning("extraction attempt failed", extra=log_context)
        try:
            with factory.begin() as session:
                ExtractionCoordinator(session, settings).fail(
                    claim.unit_id, claim.token, code, usage, trace=trace
                )
        except LeaseLost:
            return False
        except Exception:
            # Do not let Celery render SQL/provider exception contexts containing source data.
            raise RuntimeError("Extraction state unavailable; lease recovery is required") from None
    return True
