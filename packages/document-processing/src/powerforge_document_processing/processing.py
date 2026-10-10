"""Create, retry, and claim document processing runs, then store page artifacts.

The enqueue argument is a port with ``enqueue_document_processing(run_id)``.
This module does not import FastAPI, Celery, Pillow, or PyMuPDF.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Collection
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from powerforge_document_model import (
    DEFAULT_PROFILE,
    PageArtifactType,
    ProcessingErrorCode,
    ProcessingProfile,
    ProcessingRunStatus,
    build_artifact_key,
)
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
)
from powerforge_document_processing.rendering import RenderedPage, RenderingFailed, render_pages
from powerforge_document_processing.storage.base import ObjectStorage, StorageError

logger = logging.getLogger(__name__)

_ONE_LIVE_RUN = "uq_document_processing_runs_one_live"
_LIVE_STATUSES = (
    ProcessingRunStatus.PENDING,
    ProcessingRunStatus.RUNNING,
    ProcessingRunStatus.COMPLETED,
)
_READ_FAILED = "Could not read the original file"
_WRITE_FAILED = "Could not store a derived artifact"
_INCOMPLETE = "Processing did not finish every page"
_UNKNOWN = "Processing failed"


class DocumentNotFound(Exception):
    """No document exists for the requested id."""

    def __init__(self) -> None:
        super().__init__("Document not found")


class ProcessingNotRetryable(Exception):
    """The current run is not FAILED, or there is no run."""

    def __init__(self) -> None:
        super().__init__("Processing cannot be retried")


class DocumentProcessingEnqueue(Protocol):
    """Port that schedules a claimed worker for one run id."""

    def enqueue_document_processing(self, run_id: UUID) -> None:
        """Schedule processing for ``run_id``. May raise if the broker is down."""
        ...


class _ArtifactWriteFailed(Exception):
    """A derived object could not be stored. The message stays off the run row."""


class _IncompleteProcessing(Exception):
    """Rendered pages and stored artifacts do not match."""


class ProcessingService:
    """Lifecycle for one document plus the active processor version and profile hash."""

    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        enqueue: DocumentProcessingEnqueue,
        *,
        profile: ProcessingProfile = DEFAULT_PROFILE,
        max_image_pixels: int = 600_000_000,
    ) -> None:
        self.session = session
        self.storage = storage
        self._enqueue = enqueue
        self.profile = profile
        self.max_image_pixels = max_image_pixels

    def current_run(self, document_id: UUID) -> DocumentProcessingRun | None:
        """Return the live run for this target, else the latest failed run, else none."""
        live = self.session.scalar(self._target_query(document_id).where(
            DocumentProcessingRun.status.in_(_LIVE_STATUSES)
        ))
        if live is not None:
            return live
        return self.session.scalar(
            self._target_query(document_id)
            .where(DocumentProcessingRun.status == ProcessingRunStatus.FAILED)
            .order_by(
                DocumentProcessingRun.attempt_count.desc(),
                DocumentProcessingRun.created_at.desc(),
            )
            .limit(1)
        )

    def current_runs(
        self,
        document_ids: Collection[UUID],
    ) -> dict[UUID, DocumentProcessingRun | None]:
        """Return ``current_run`` for each id. This read does not enqueue."""
        ids = list(document_ids)
        if not ids:
            return {}
        rows = self.session.scalars(
            select(DocumentProcessingRun).where(
                DocumentProcessingRun.document_id.in_(ids),
                DocumentProcessingRun.processor_version == self.profile.processor_version,
                DocumentProcessingRun.profile_hash == self.profile.profile_hash,
            )
        ).all()
        chosen: dict[UUID, DocumentProcessingRun] = {}
        for run in rows:
            current = chosen.get(run.document_id)
            if current is None or _prefer_current_run(run, current):
                chosen[run.document_id] = run
        return {document_id: chosen.get(document_id) for document_id in ids}

    def ensure_document_processing(self, document_id: UUID) -> DocumentProcessingRun:
        """Return the current run, creating and enqueueing the first one when absent.

        An unclaimed pending run is enqueued again. A running, completed, or failed
        run is returned without a new row and without enqueue.
        """
        self._require_document(document_id)
        current = self.current_run(document_id)
        if current is None:
            run, inserted = self._insert_pending(document_id, attempt_count=1)
            if inserted:
                return self._commit_and_enqueue(run)
            return run
        if current.status == ProcessingRunStatus.PENDING:
            self._enqueue_run(current)
            return current
        return current

    def retry_failed_processing(self, document_id: UUID) -> DocumentProcessingRun:
        """Insert a new pending attempt after a failed current run and enqueue it.

        The failed run, its artifact rows, and its objects stay in place. Page rows
        are not deleted. A concurrent insert that loses the live-run index returns
        the winning pending run and does not enqueue again.
        """
        self._require_document(document_id)
        current = self.current_run(document_id)
        if current is None or current.status != ProcessingRunStatus.FAILED:
            raise ProcessingNotRetryable
        run, inserted = self._insert_pending(document_id, self._next_attempt_count(document_id))
        if not inserted:
            return run
        return self._commit_and_enqueue(run)

    def claim_and_process(self, run_id: UUID) -> None:
        """Move a pending run to running and store pages, or return if it was not pending."""
        if not self._claim(run_id):
            return
        try:
            self._process(run_id)
        except RenderingFailed as exc:
            self._fail(run_id, exc.code, str(exc))
        except _ArtifactWriteFailed:
            self._fail(run_id, ProcessingErrorCode.STORAGE_WRITE_FAILED, _WRITE_FAILED)
        except StorageError:
            self._fail(run_id, ProcessingErrorCode.STORAGE_READ_FAILED, _READ_FAILED)
        except _IncompleteProcessing:
            self._fail(run_id, ProcessingErrorCode.UNKNOWN_PROCESSING_ERROR, _INCOMPLETE)
        except Exception as exc:
            if exc.__class__.__name__ == "SoftTimeLimitExceeded":
                raise
            logger.exception(
                "processing run failed unexpectedly",
                extra={"run_id": str(run_id)},
            )
            self.session.rollback()
            self._fail(run_id, ProcessingErrorCode.UNKNOWN_PROCESSING_ERROR, _UNKNOWN)

    def _target_query(self, document_id: UUID):
        return select(DocumentProcessingRun).where(
            DocumentProcessingRun.document_id == document_id,
            DocumentProcessingRun.processor_version == self.profile.processor_version,
            DocumentProcessingRun.profile_hash == self.profile.profile_hash,
        )

    def _require_document(self, document_id: UUID) -> None:
        found = self.session.scalar(select(Document.id).where(Document.id == document_id))
        if found is None:
            raise DocumentNotFound

    def _next_attempt_count(self, document_id: UUID) -> int:
        count = self.session.scalar(
            select(func.count())
            .select_from(DocumentProcessingRun)
            .where(
                DocumentProcessingRun.document_id == document_id,
                DocumentProcessingRun.processor_version == self.profile.processor_version,
                DocumentProcessingRun.profile_hash == self.profile.profile_hash,
            )
        )
        return int(count or 0) + 1

    def _insert_pending(
        self,
        document_id: UUID,
        attempt_count: int,
    ) -> tuple[DocumentProcessingRun, bool]:
        run = DocumentProcessingRun(
            document_id=document_id,
            processor_version=self.profile.processor_version,
            profile_version=self.profile.profile_version,
            profile_hash=self.profile.profile_hash,
            status=ProcessingRunStatus.PENDING,
            pages_processed=0,
            attempt_count=attempt_count,
        )
        try:
            with self.session.begin_nested():
                self.session.add(run)
                self.session.flush()
        except IntegrityError as exc:
            if run in self.session:
                self.session.expunge(run)
            if _constraint_name(exc) != _ONE_LIVE_RUN:
                raise
            winner = self.current_run(document_id)
            if winner is None:
                raise
            return winner, False
        return run, True

    def _commit_and_enqueue(self, run: DocumentProcessingRun) -> DocumentProcessingRun:
        run_id = run.id
        document_id = run.document_id
        self._commit()
        self._log(run_id, document_id, ProcessingRunStatus.PENDING)
        self._enqueue_run_id(run_id, document_id)
        loaded = self.session.get(DocumentProcessingRun, run_id)
        if loaded is None:
            raise DocumentNotFound
        return loaded

    def _enqueue_run(self, run: DocumentProcessingRun) -> None:
        self._enqueue_run_id(run.id, run.document_id)

    def _enqueue_run_id(self, run_id: UUID, document_id: UUID) -> None:
        try:
            self._enqueue.enqueue_document_processing(run_id)
        except Exception:
            logger.exception(
                "document processing enqueue failed",
                extra={"run_id": str(run_id), "document_id": str(document_id)},
            )

    def _claim(self, run_id: UUID) -> bool:
        document_id = self.session.execute(
            update(DocumentProcessingRun)
            .where(
                DocumentProcessingRun.id == run_id,
                DocumentProcessingRun.status == ProcessingRunStatus.PENDING,
            )
            .values(status=ProcessingRunStatus.RUNNING, started_at=func.now())
            .returning(DocumentProcessingRun.document_id)
        ).scalar_one_or_none()
        if document_id is None:
            self.session.rollback()
            return False
        self._commit()
        self._log(run_id, document_id, ProcessingRunStatus.RUNNING)
        return True

    def _process(self, run_id: UUID) -> None:
        run = self._load_run(run_id)
        document = self._load_document(run.document_id)
        data = self._read_original(document)
        rendered_pages = render_pages(
            data,
            document.file_extension,
            self.profile,
            self.max_image_pixels,
        )
        run.pages_total = len(rendered_pages)
        self._commit()
        stored: list[tuple[RenderedPage, UUID]] = []
        for rendered in rendered_pages:
            run = self._load_run(run_id)
            document = self._load_document(run.document_id)
            page = self._reconcile_page(document, rendered)
            self._store_artifacts(document, run, page, rendered)
            page_id = page.id
            self._commit()
            run = self._load_run(run_id)
            run.pages_processed += 1
            self._commit()
            stored.append((rendered, page_id))
        run = self._load_run(run_id)
        self._require_complete(run, stored)
        run.status = ProcessingRunStatus.COMPLETED
        run.completed_at = datetime.now(UTC)
        document_id = run.document_id
        self._commit()
        self._log(run_id, document_id, ProcessingRunStatus.COMPLETED)

    def _read_original(self, document: Document) -> bytes:
        stream = self.storage.get(document.storage_key)
        try:
            return stream.read()
        finally:
            stream.close()

    def _reconcile_page(self, document: Document, rendered: RenderedPage) -> DocumentPage:
        page = self.session.scalar(
            select(DocumentPage).where(
                DocumentPage.document_id == document.id,
                DocumentPage.page_number == rendered.page_number,
            )
        )
        width = Decimal(str(rendered.source_width))
        height = Decimal(str(rendered.source_height))
        if page is None:
            page = DocumentPage(
                document_id=document.id,
                page_number=rendered.page_number,
                source_width=width,
                source_height=height,
                source_unit=rendered.source_unit,
                rotation_degrees=rendered.rotation_degrees,
                native_text_char_count=rendered.native_text_char_count,
            )
            self.session.add(page)
            self.session.flush()
            return page
        page.source_width = width
        page.source_height = height
        page.source_unit = rendered.source_unit
        page.rotation_degrees = rendered.rotation_degrees
        page.native_text_char_count = rendered.native_text_char_count
        return page

    def _store_artifacts(
        self,
        document: Document,
        run: DocumentProcessingRun,
        page: DocumentPage,
        rendered: RenderedPage,
    ) -> None:
        self._put_artifact(
            document,
            run,
            page,
            PageArtifactType.ANALYSIS_IMAGE,
            rendered.analysis_png,
            "image/png",
            rendered.width_px,
            rendered.height_px,
            rendered.effective_dpi,
        )
        self._put_artifact(
            document,
            run,
            page,
            PageArtifactType.THUMBNAIL,
            rendered.thumbnail,
            _thumbnail_mime(rendered.thumbnail),
            None,
            None,
            rendered.effective_dpi,
        )
        if rendered.native_text is not None:
            self._put_artifact(
                document,
                run,
                page,
                PageArtifactType.NATIVE_TEXT,
                rendered.native_text.encode("utf-8"),
                "text/plain",
                None,
                None,
                None,
            )

    def _put_artifact(
        self,
        document: Document,
        run: DocumentProcessingRun,
        page: DocumentPage,
        artifact_type: PageArtifactType,
        payload: bytes,
        mime_type: str,
        width_px: int | None,
        height_px: int | None,
        effective_dpi: float | None,
    ) -> None:
        key = build_artifact_key(
            document.project_id,
            document.id,
            run.id,
            page.page_number,
            artifact_type,
        )
        try:
            self.storage.put(key, BytesIO(payload), len(payload), mime_type)
        except StorageError as exc:
            raise _ArtifactWriteFailed from exc
        dpi = None if effective_dpi is None else Decimal(str(effective_dpi))
        self.session.add(
            PageArtifact(
                document_page_id=page.id,
                processing_run_id=run.id,
                artifact_type=artifact_type,
                storage_key=key,
                mime_type=mime_type,
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                width_px=width_px,
                height_px=height_px,
                effective_dpi=dpi,
            )
        )

    def _require_complete(
        self,
        run: DocumentProcessingRun,
        stored: list[tuple[RenderedPage, UUID]],
    ) -> None:
        rows = self.session.scalars(
            select(PageArtifact).where(PageArtifact.processing_run_id == run.id)
        ).all()
        by_page: dict[UUID, set[PageArtifactType]] = {}
        for row in rows:
            by_page.setdefault(row.document_page_id, set()).add(row.artifact_type)
        for rendered, page_id in stored:
            types = by_page.get(page_id, set())
            if (
                PageArtifactType.ANALYSIS_IMAGE not in types
                or PageArtifactType.THUMBNAIL not in types
            ):
                raise _IncompleteProcessing
            has_text = rendered.native_text is not None
            if has_text != (PageArtifactType.NATIVE_TEXT in types):
                raise _IncompleteProcessing

    def _fail(self, run_id: UUID, code: ProcessingErrorCode, message: str) -> None:
        run = self.session.get(DocumentProcessingRun, run_id)
        if run is None:
            return
        run.status = ProcessingRunStatus.FAILED
        run.failed_at = datetime.now(UTC)
        run.error_code = code.value
        run.error_message = message
        document_id = run.document_id
        self._commit()
        logger.info(
            "processing run failed",
            extra={
                "run_id": str(run_id),
                "document_id": str(document_id),
                "status": ProcessingRunStatus.FAILED.value,
                "error_code": code.value,
            },
        )

    def _load_run(self, run_id: UUID) -> DocumentProcessingRun:
        run = self.session.get(DocumentProcessingRun, run_id)
        if run is None:
            raise DocumentNotFound
        return run

    def _load_document(self, document_id: UUID) -> Document:
        document = self.session.get(Document, document_id)
        if document is None:
            raise DocumentNotFound
        return document

    def _commit(self) -> None:
        self.session.commit()
        self.session.expire_all()

    def _log(self, run_id: UUID, document_id: UUID, status: ProcessingRunStatus) -> None:
        logger.info(
            "processing run status changed",
            extra={
                "run_id": str(run_id),
                "document_id": str(document_id),
                "status": status.value,
            },
        )


def _prefer_current_run(
    candidate: DocumentProcessingRun,
    incumbent: DocumentProcessingRun,
) -> bool:
    """True when ``candidate`` is the current run instead of ``incumbent``."""
    candidate_live = candidate.status in _LIVE_STATUSES
    incumbent_live = incumbent.status in _LIVE_STATUSES
    if candidate_live != incumbent_live:
        return candidate_live
    if candidate_live:
        return False
    return (candidate.attempt_count, candidate.created_at) > (
        incumbent.attempt_count,
        incumbent.created_at,
    )


def _constraint_name(exc: BaseException) -> str | None:
    """Return ``exc.orig.diag.constraint_name`` when present, else ``None``."""
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


def _thumbnail_mime(payload: bytes) -> str:
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"
