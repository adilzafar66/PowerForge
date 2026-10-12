"""Ensure, retry, reclassify, and claim classification runs.

The enqueue argument is a port with ``enqueue_document_classification(run_id)``.
This module does not import FastAPI, Celery, or a vendor SDK.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, null, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from powerforge_ai.providers import (
    ClassificationProvider,
    ClassificationUsage,
    DocumentClassificationResult,
    PageClassificationResponse,
    PageClassificationResult,
)
from powerforge_document_classification.assembly import (
    ClassificationAssemblyError,
    build_document_request,
    build_page_batches,
    load_page_set,
)
from powerforge_document_classification.errors import (
    ClassificationErrorCode,
    ClassificationProviderError,
)
from powerforge_document_classification.identity import CLASSIFIER_VERSION, classifier_identity_hash
from powerforge_document_classification.profile import ClassificationProfile, confidence_band
from powerforge_document_classification.prompts import classifier_prompt_version
from powerforge_document_classification.taxonomy import (
    DOCUMENT_TYPES,
    MIXED_DOCUMENT,
    PAGE_TYPES,
    TAXONOMY_VERSION,
    InvalidPageType,
    require_page_type,
)
from powerforge_document_model import (
    DEFAULT_PROFILE,
    ClassificationCallKind,
    ClassificationRunStatus,
    ClassificationScope,
    ClassificationStage,
    ConfidenceBand,
    DocumentClassification,
    ProcessingProfile,
    ProcessingRunStatus,
)
from powerforge_document_processing.models import (
    ClassificationAICall,
    ClassificationPrediction,
    Document,
    DocumentClassificationRun,
    DocumentPage,
    DocumentProcessingRun,
)
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_shared.config import Settings, get_settings

logger = logging.getLogger(__name__)

_ONE_LIVE = "uq_document_classification_runs_one_live"
_PROCESSING_LIVE = (
    ProcessingRunStatus.PENDING,
    ProcessingRunStatus.RUNNING,
    ProcessingRunStatus.COMPLETED,
)
_IN_FLIGHT = (ClassificationRunStatus.PENDING, ClassificationRunStatus.RUNNING)
_ERROR_MESSAGES = {
    ClassificationErrorCode.ARTIFACT_UNAVAILABLE: "A page thumbnail is not available",
    ClassificationErrorCode.PROVIDER_UNAVAILABLE: "The classification provider is unavailable",
    ClassificationErrorCode.PROVIDER_TIMEOUT: "The classification provider timed out",
    ClassificationErrorCode.INVALID_PROVIDER_RESPONSE: (
        "The classification provider returned an invalid result"
    ),
    ClassificationErrorCode.CLASSIFICATION_INPUT_ERROR: "The classification input is incomplete",
    ClassificationErrorCode.UNKNOWN_CLASSIFICATION_ERROR: "Classification failed",
}


class ClassificationDisabled(Exception):
    """Classification is turned off. Nothing is inserted."""

    code = ClassificationErrorCode.AI_CLASSIFICATION_DISABLED

    def __init__(self) -> None:
        super().__init__(self.code.value)


class ProcessingNotComplete(Exception):
    """The active processing run is missing or not COMPLETED."""

    def __init__(self) -> None:
        super().__init__("Processing is not complete")


class ClassificationInProgress(Exception):
    """This identity already has a PENDING or RUNNING run."""

    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        super().__init__("Classification is in progress")


class ClassificationNotRetryable(Exception):
    """The target run is not the newest FAILED run for its identity."""

    def __init__(self) -> None:
        super().__init__("Classification cannot be retried")


class _InvalidProviderResponse(Exception):
    """The provider returned a page set or type this taxonomy does not accept."""


class DocumentClassificationEnqueue(Protocol):
    """Port that schedules classification for one run id."""

    def enqueue_document_classification(self, run_id: UUID) -> None:
        """Schedule classification for ``run_id``. May raise if the broker is down."""
        ...


@dataclass(frozen=True, slots=True)
class _Identity:
    processing_run_id: UUID
    identity_hash: str
    provider: str
    model: str
    classifier_version: str
    taxonomy_version: str
    prompt_version: str
    sampling_profile_version: str
    sampling_profile_hash: str


def classification_profile(settings: Settings) -> ClassificationProfile:
    """Profile used for sampling and the identity hash. Image detail comes from settings."""
    return ClassificationProfile(image_detail=settings.ai_classification_image_detail)


class ClassificationService:
    """Lifecycle for classification of one immutable document."""

    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        enqueue: DocumentClassificationEnqueue,
        provider: ClassificationProvider,
        settings: Settings | None = None,
        *,
        processing_profile: ProcessingProfile = DEFAULT_PROFILE,
    ) -> None:
        self.session = session
        self.storage = storage
        self._enqueue = enqueue
        self._provider = provider
        self.settings = settings if settings is not None else get_settings()
        self.profile = classification_profile(self.settings)
        self.processing_profile = processing_profile

    def ensure_document_classification(self, document_id: UUID) -> DocumentClassificationRun:
        """Reuse a compatible completed or in-flight run. A failed run is not retried."""
        self._require_enabled()
        identity = self._current_identity(document_id)
        completed = self._latest(
            document_id, identity.identity_hash, ClassificationRunStatus.COMPLETED
        )
        if completed is not None:
            return completed
        running = self._latest(
            document_id, identity.identity_hash, ClassificationRunStatus.RUNNING
        )
        if running is not None:
            return running
        pending = self._latest(
            document_id, identity.identity_hash, ClassificationRunStatus.PENDING
        )
        if pending is not None:
            self._enqueue_run(pending)
            return pending
        failed = self._latest(
            document_id, identity.identity_hash, ClassificationRunStatus.FAILED
        )
        if failed is not None:
            return failed
        run, inserted = self._insert_pending(document_id, identity, retry_of_run_id=None)
        if not inserted:
            return run
        return self._commit_and_enqueue(run)

    def retry_failed_classification(self, run_id: UUID) -> DocumentClassificationRun:
        """Insert a new pending run pointing at the newest failed run for that identity."""
        self._require_enabled()
        target = self.session.get(DocumentClassificationRun, run_id)
        if target is None or target.status != ClassificationRunStatus.FAILED:
            raise ClassificationNotRetryable
        self._require_processing_run(target.processing_run_id)
        identity = _identity_from_run(target)
        live = self._live(target.document_id, identity.identity_hash)
        if live is not None:
            raise ClassificationInProgress(live.id)
        newest = self._newest(target.document_id, identity.identity_hash)
        if newest is None or newest.id != target.id:
            raise ClassificationNotRetryable
        run, inserted = self._insert_pending(
            target.document_id,
            identity,
            retry_of_run_id=target.id,
        )
        if not inserted:
            raise ClassificationInProgress(run.id)
        return self._commit_and_enqueue(run)

    def reclassify_document(self, document_id: UUID) -> DocumentClassificationRun:
        """Insert a pending run for the current identity even when a completed run exists."""
        self._require_enabled()
        identity = self._current_identity(document_id)
        live = self._live(document_id, identity.identity_hash)
        if live is not None:
            raise ClassificationInProgress(live.id)
        run, inserted = self._insert_pending(document_id, identity, retry_of_run_id=None)
        if not inserted:
            raise ClassificationInProgress(run.id)
        return self._commit_and_enqueue(run)

    def claim_and_classify(self, run_id: UUID) -> None:
        """Claim a PENDING run and classify it. Any other status returns without a provider call."""
        if not self._claim(run_id):
            return
        try:
            self._classify(run_id)
        except ClassificationAssemblyError as exc:
            self._fail(run_id, exc.code)
        except ClassificationProviderError as exc:
            self._fail(run_id, exc.code)
        except (_InvalidProviderResponse, InvalidPageType, ValidationError):
            self._fail(run_id, ClassificationErrorCode.INVALID_PROVIDER_RESPONSE)
        except Exception:
            logger.exception("classification failed", extra={"run_id": str(run_id)})
            self._fail(run_id, ClassificationErrorCode.UNKNOWN_CLASSIFICATION_ERROR)

    def latest_completed_document_prediction(
        self, document_id: UUID
    ) -> ClassificationPrediction | None:
        """Document prediction of the newest completed run for the current processing run."""
        processing = self._current_processing(document_id)
        if processing is None or processing.status != ProcessingRunStatus.COMPLETED:
            return None
        run = self.session.scalar(
            select(DocumentClassificationRun)
            .where(
                DocumentClassificationRun.document_id == document_id,
                DocumentClassificationRun.processing_run_id == processing.id,
                DocumentClassificationRun.status == ClassificationRunStatus.COMPLETED,
            )
            .order_by(DocumentClassificationRun.created_at.desc())
            .limit(1)
        )
        if run is None:
            return None
        return self._document_prediction(run.id)

    def _require_enabled(self) -> None:
        if not self.settings.ai_classification_enabled:
            raise ClassificationDisabled

    def _current_identity(self, document_id: UUID) -> _Identity:
        processing = self._require_completed_processing(document_id)
        return _identity_from_settings(self.settings, self.profile, processing.id)

    def _require_completed_processing(self, document_id: UUID) -> DocumentProcessingRun:
        processing = self._current_processing(document_id)
        if processing is None or processing.status != ProcessingRunStatus.COMPLETED:
            raise ProcessingNotComplete
        return processing

    def _require_processing_run(self, processing_run_id: UUID) -> None:
        processing = self.session.get(DocumentProcessingRun, processing_run_id)
        if processing is None or processing.status != ProcessingRunStatus.COMPLETED:
            raise ProcessingNotComplete

    def _current_processing(self, document_id: UUID) -> DocumentProcessingRun | None:
        query = select(DocumentProcessingRun).where(
            DocumentProcessingRun.document_id == document_id,
            DocumentProcessingRun.processor_version == self.processing_profile.processor_version,
            DocumentProcessingRun.profile_hash == self.processing_profile.profile_hash,
        )
        live = self.session.scalar(query.where(DocumentProcessingRun.status.in_(_PROCESSING_LIVE)))
        if live is not None:
            return live
        return self.session.scalar(
            query.where(DocumentProcessingRun.status == ProcessingRunStatus.FAILED)
            .order_by(DocumentProcessingRun.created_at.desc())
            .limit(1)
        )

    def _latest(
        self,
        document_id: UUID,
        identity_hash: str,
        status: ClassificationRunStatus,
    ) -> DocumentClassificationRun | None:
        return self.session.scalar(
            select(DocumentClassificationRun)
            .where(
                DocumentClassificationRun.document_id == document_id,
                DocumentClassificationRun.classifier_identity_hash == identity_hash,
                DocumentClassificationRun.status == status,
            )
            .order_by(DocumentClassificationRun.created_at.desc())
            .limit(1)
        )

    def _live(self, document_id: UUID, identity_hash: str) -> DocumentClassificationRun | None:
        return self.session.scalar(
            select(DocumentClassificationRun)
            .where(
                DocumentClassificationRun.document_id == document_id,
                DocumentClassificationRun.classifier_identity_hash == identity_hash,
                DocumentClassificationRun.status.in_(_IN_FLIGHT),
            )
            .order_by(DocumentClassificationRun.created_at.desc())
            .limit(1)
        )

    def _newest(self, document_id: UUID, identity_hash: str) -> DocumentClassificationRun | None:
        return self.session.scalar(
            select(DocumentClassificationRun)
            .where(
                DocumentClassificationRun.document_id == document_id,
                DocumentClassificationRun.classifier_identity_hash == identity_hash,
            )
            .order_by(
                DocumentClassificationRun.created_at.desc(),
                DocumentClassificationRun.attempt_number.desc(),
            )
            .limit(1)
        )

    def _next_attempt(self, document_id: UUID, identity_hash: str) -> int:
        count = self.session.scalar(
            select(func.count())
            .select_from(DocumentClassificationRun)
            .where(
                DocumentClassificationRun.document_id == document_id,
                DocumentClassificationRun.classifier_identity_hash == identity_hash,
            )
        )
        return int(count or 0) + 1

    def _insert_pending(
        self,
        document_id: UUID,
        identity: _Identity,
        *,
        retry_of_run_id: UUID | None,
    ) -> tuple[DocumentClassificationRun, bool]:
        run = DocumentClassificationRun(
            document_id=document_id,
            processing_run_id=identity.processing_run_id,
            retry_of_run_id=retry_of_run_id,
            attempt_number=self._next_attempt(document_id, identity.identity_hash),
            classifier_version=identity.classifier_version,
            taxonomy_version=identity.taxonomy_version,
            prompt_version=identity.prompt_version,
            sampling_profile_version=identity.sampling_profile_version,
            sampling_profile_hash=identity.sampling_profile_hash,
            classifier_identity_hash=identity.identity_hash,
            provider=identity.provider,
            model=identity.model,
            status=ClassificationRunStatus.PENDING,
            pages_total=0,
            pages_classified=0,
        )
        try:
            with self.session.begin_nested():
                self.session.add(run)
                self.session.flush()
        except IntegrityError as exc:
            if run in self.session:
                self.session.expunge(run)
            if _constraint_name(exc) != _ONE_LIVE:
                raise
            winner = self._live(document_id, identity.identity_hash)
            if winner is None:
                raise
            return winner, False
        return run, True

    def _commit_and_enqueue(self, run: DocumentClassificationRun) -> DocumentClassificationRun:
        run_id = run.id
        document_id = run.document_id
        self._commit()
        self._log(run_id, document_id, ClassificationRunStatus.PENDING)
        self._enqueue_id(run_id, document_id)
        loaded = self.session.get(DocumentClassificationRun, run_id)
        if loaded is None:
            raise ProcessingNotComplete
        return loaded

    def _enqueue_run(self, run: DocumentClassificationRun) -> None:
        self._enqueue_id(run.id, run.document_id)

    def _enqueue_id(self, run_id: UUID, document_id: UUID) -> None:
        try:
            self._enqueue.enqueue_document_classification(run_id)
        except Exception:
            logger.exception(
                "document classification enqueue failed",
                extra={"run_id": str(run_id), "document_id": str(document_id)},
            )

    def _claim(self, run_id: UUID) -> bool:
        document_id = self.session.execute(
            update(DocumentClassificationRun)
            .where(
                DocumentClassificationRun.id == run_id,
                DocumentClassificationRun.status == ClassificationRunStatus.PENDING,
            )
            .values(
                status=ClassificationRunStatus.RUNNING,
                started_at=func.now(),
                stage=ClassificationStage.DOCUMENT,
            )
            .returning(DocumentClassificationRun.document_id)
        ).scalar_one_or_none()
        if document_id is None:
            self.session.rollback()
            return False
        self._commit()
        self._log(run_id, document_id, ClassificationRunStatus.RUNNING)
        return True

    def _classify(self, run_id: UUID) -> None:
        run = self._load_run(run_id)
        document = self.session.get(Document, run.document_id)
        processing = self.session.get(DocumentProcessingRun, run.processing_run_id)
        if document is None or processing is None:
            raise ClassificationAssemblyError(ClassificationErrorCode.CLASSIFICATION_INPUT_ERROR)
        if processing.status != ProcessingRunStatus.COMPLETED:
            raise ClassificationAssemblyError(ClassificationErrorCode.CLASSIFICATION_INPUT_ERROR)
        pages = load_page_set(self.session, document.id, processing.pages_total)
        request = build_document_request(
            self.session,
            self.storage,
            document,
            processing.id,
            pages,
            self.profile,
        )
        response = self._provider.classify_document(request)
        document_id = document.id
        self._store_document_prediction(run, response.result)
        self._store_call(run, ClassificationCallKind.DOCUMENT, None, response.usage)
        requires_pages = _requires_page_classification(response.result, self.profile)
        run.requires_page_classification = requires_pages
        run.stage = ClassificationStage.DOCUMENT
        if not requires_pages:
            run.status = ClassificationRunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            self._commit()
            self._log_usage(run_id, document_id, ClassificationRunStatus.COMPLETED)
            return
        run.stage = ClassificationStage.PAGES
        run.pages_total = len(pages)
        self._commit()
        batches = build_page_batches(
            self.session,
            self.storage,
            document,
            processing.id,
            pages,
            self.profile,
        )
        for batch in batches:
            page_response = self._provider.classify_pages(batch)
            run = self._load_run(run_id)
            numbers = [page.page_number for page in batch.pages]
            self._store_page_predictions(run, pages, numbers, page_response)
            self._store_call(run, ClassificationCallKind.PAGE_BATCH, numbers, page_response.usage)
            run.pages_classified += len(numbers)
            self._commit()
        if self._document_prediction(run_id) is None or not self._pages_complete(run_id, pages):
            raise _InvalidProviderResponse
        run = self._load_run(run_id)
        run.status = ClassificationRunStatus.COMPLETED
        run.completed_at = datetime.now(UTC)
        self._commit()
        self._log_usage(run_id, document_id, ClassificationRunStatus.COMPLETED)

    def _store_document_prediction(
        self,
        run: DocumentClassificationRun,
        result: DocumentClassificationResult,
    ) -> None:
        predicted = _document_type(result.predicted_type)
        self.session.add(
            ClassificationPrediction(
                classification_run_id=run.id,
                document_id=run.document_id,
                scope=ClassificationScope.DOCUMENT,
                document_page_id=None,
                predicted_type=predicted,
                confidence_score=Decimal(str(result.confidence_score)),
                confidence_band=_band(result.confidence_score, self.profile),
                alternatives=_alternatives(result.alternatives, DOCUMENT_TYPES),
                rationale=result.rationale,
            )
        )

    def _store_page_predictions(
        self,
        run: DocumentClassificationRun,
        pages: list[DocumentPage],
        expected_numbers: list[int],
        response: PageClassificationResponse,
    ) -> None:
        by_number = {page.page_number: page for page in pages}
        found: dict[int, PageClassificationResult] = {}
        for item in response.pages:
            if item.page_number in found:
                raise _InvalidProviderResponse
            require_page_type(item.predicted_type)
            found[item.page_number] = item
        if set(found) != set(expected_numbers):
            raise _InvalidProviderResponse
        for number in expected_numbers:
            item = found[number]
            page = by_number.get(number)
            if page is None:
                raise _InvalidProviderResponse
            self.session.add(
                ClassificationPrediction(
                    classification_run_id=run.id,
                    document_id=run.document_id,
                    scope=ClassificationScope.PAGE,
                    document_page_id=page.id,
                    predicted_type=_page_type(item.predicted_type),
                    confidence_score=Decimal(str(item.confidence_score)),
                    confidence_band=_band(item.confidence_score, self.profile),
                    alternatives=_alternatives(item.alternatives, PAGE_TYPES),
                    rationale=item.rationale,
                )
            )

    def _store_call(
        self,
        run: DocumentClassificationRun,
        kind: ClassificationCallKind,
        page_numbers: list[int] | None,
        usage: ClassificationUsage,
    ) -> None:
        self.session.add(
            ClassificationAICall(
                classification_run_id=run.id,
                call_kind=kind,
                page_numbers=null() if page_numbers is None else page_numbers,
                provider=usage.provider,
                model=usage.model,
                provider_response_id=usage.provider_response_id,
                input_tokens=usage.input_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                output_tokens=usage.output_tokens,
                reasoning_tokens=usage.reasoning_tokens,
                image_count=usage.image_count,
                latency_ms=usage.latency_ms,
            )
        )

    def _document_prediction(self, run_id: UUID) -> ClassificationPrediction | None:
        return self.session.scalar(
            select(ClassificationPrediction).where(
                ClassificationPrediction.classification_run_id == run_id,
                ClassificationPrediction.scope == ClassificationScope.DOCUMENT,
            )
        )

    def _pages_complete(self, run_id: UUID, pages: list[DocumentPage]) -> bool:
        stored = set(
            self.session.scalars(
                select(ClassificationPrediction.document_page_id).where(
                    ClassificationPrediction.classification_run_id == run_id,
                    ClassificationPrediction.scope == ClassificationScope.PAGE,
                )
            ).all()
        )
        return stored == {page.id for page in pages}

    def _fail(self, run_id: UUID, code: ClassificationErrorCode) -> None:
        self.session.rollback()
        run = self.session.get(DocumentClassificationRun, run_id)
        if run is None or run.status != ClassificationRunStatus.RUNNING:
            return
        document_id = run.document_id
        run.status = ClassificationRunStatus.FAILED
        run.error_code = code.value
        run.error_message = _ERROR_MESSAGES.get(code, "Classification failed")
        run.failed_at = datetime.now(UTC)
        self._commit()
        self._log_usage(run_id, document_id, ClassificationRunStatus.FAILED, error_code=code.value)

    def _load_run(self, run_id: UUID) -> DocumentClassificationRun:
        run = self.session.get(DocumentClassificationRun, run_id)
        if run is None:
            raise _InvalidProviderResponse
        return run

    def _usage_totals(self, run_id: UUID) -> tuple[int, int, int]:
        rows = self.session.scalars(
            select(ClassificationAICall).where(ClassificationAICall.classification_run_id == run_id)
        ).all()
        input_tokens = sum(row.input_tokens or 0 for row in rows)
        output_tokens = sum(row.output_tokens or 0 for row in rows)
        latency_ms = sum(row.latency_ms for row in rows)
        return input_tokens, output_tokens, latency_ms

    def _log_usage(
        self,
        run_id: UUID,
        document_id: UUID,
        status: ClassificationRunStatus,
        *,
        error_code: str | None = None,
    ) -> None:
        input_tokens, output_tokens, latency_ms = self._usage_totals(run_id)
        self._log(
            run_id,
            document_id,
            status,
            error_code=error_code,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

    def _log(
        self,
        run_id: UUID,
        document_id: UUID,
        status: ClassificationRunStatus,
        *,
        error_code: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        extra: dict[str, object] = {
            "run_id": str(run_id),
            "document_id": str(document_id),
            "status": status.value,
        }
        if error_code is not None:
            extra["error_code"] = error_code
        if input_tokens is not None:
            extra["input_tokens"] = input_tokens
        if output_tokens is not None:
            extra["output_tokens"] = output_tokens
        if latency_ms is not None:
            extra["latency_ms"] = latency_ms
        logger.info("classification run status changed", extra=extra)

    def _commit(self) -> None:
        self.session.commit()
        self.session.expire_all()


def _identity_from_settings(
    settings: Settings,
    profile: ClassificationProfile,
    processing_run_id: UUID,
) -> _Identity:
    prompt_version = classifier_prompt_version()
    return _Identity(
        processing_run_id=processing_run_id,
        identity_hash=classifier_identity_hash(
            provider=settings.ai_provider,
            model=settings.ai_classification_model,
            processing_run_id=str(processing_run_id),
            prompt_version=prompt_version,
            sampling_profile_hash=profile.profile_hash,
        ),
        provider=settings.ai_provider,
        model=settings.ai_classification_model,
        classifier_version=CLASSIFIER_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
        prompt_version=prompt_version,
        sampling_profile_version=profile.profile_version,
        sampling_profile_hash=profile.profile_hash,
    )


def _identity_from_run(run: DocumentClassificationRun) -> _Identity:
    return _Identity(
        processing_run_id=run.processing_run_id,
        identity_hash=run.classifier_identity_hash,
        provider=run.provider,
        model=run.model,
        classifier_version=run.classifier_version,
        taxonomy_version=run.taxonomy_version,
        prompt_version=run.prompt_version,
        sampling_profile_version=run.sampling_profile_version,
        sampling_profile_hash=run.sampling_profile_hash,
    )


def _band(score: float, profile: ClassificationProfile) -> ConfidenceBand:
    return ConfidenceBand(confidence_band(score, profile))


def _requires_page_classification(
    result: DocumentClassificationResult,
    profile: ClassificationProfile,
) -> bool:
    if result.predicted_type in {MIXED_DOCUMENT, "UNKNOWN"}:
        return True
    return result.confidence_score < profile.high_confidence_threshold


def _document_type(value: str) -> DocumentClassification:
    if value not in DOCUMENT_TYPES:
        raise _InvalidProviderResponse
    try:
        return DocumentClassification(value)
    except ValueError as exc:
        raise _InvalidProviderResponse from exc


def _page_type(value: str) -> DocumentClassification:
    try:
        return DocumentClassification(require_page_type(value))
    except (InvalidPageType, ValueError) as exc:
        raise _InvalidProviderResponse from exc


def _alternatives(items: list, allowed: tuple[str, ...]) -> list[dict[str, object]]:
    stored: list[dict[str, object]] = []
    for item in items:
        if item.type not in allowed:
            raise _InvalidProviderResponse
        stored.append({"type": item.type, "score": item.score})
    return stored


def _constraint_name(exc: BaseException) -> str | None:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    diag = getattr(orig, "diag", None)
    if diag is None:
        return None
    name = getattr(diag, "constraint_name", None)
    if not name:
        return None
    return name
