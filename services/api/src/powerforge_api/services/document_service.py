"""Upload, list, get, edit, remove, restore, reuse and download links for revision documents.

Locking follows decision D11: a mutation holds the project row FOR SHARE, then the
revision row FOR UPDATE, then re-checks mutability. It never upgrades its project
lock. Object storage is written before any lock is taken, so slow uploads never hold
database locks; a failure after the write removes the object again.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session, aliased

from powerforge_api.db_errors import integrity_guard
from powerforge_api.exceptions import (
    CrossProjectDocumentAccess,
    DocumentAlreadyInRevision,
    DocumentRemoved,
    PageNotFound,
    ProcessingNotComplete,
    ProcessingNotRetryableError,
    ProjectError,
    ProjectNotFound,
    RevisionDocumentNotFound,
    RevisionNotFound,
    RevisionProjectMismatch,
    StorageDownloadFailed,
    StorageUploadFailed,
)
from powerforge_api.schemas.documents import (
    DocumentPageResponse,
    DocumentStatusFilter,
    DocumentSummary,
    DownloadUrlResponse,
    PageArtifactInfo,
    ProcessingStatusResponse,
    ProcessingSummary,
    ReuseDocumentRequest,
    RevisionDocumentResponse,
    RevisionDocumentUpdate,
    UploadResponse,
)
from powerforge_api.services.file_ingest import IngestedUpload, ingest_upload
from powerforge_api.services.file_inspector import FileInspector, InspectionResult
from powerforge_api.services.revision_documents import (
    assert_documents_mutable,
    lock_project_shared,
    lock_revision,
)
from powerforge_document_model import (
    DocumentClassification,
    DocumentOrigin,
    PageArtifactType,
    ProcessingRunStatus,
    RevisionDocumentStatus,
    build_storage_key,
)
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
    Project,
    ProjectRevision,
    RevisionDocument,
)
from powerforge_document_processing.processing import (
    DocumentProcessingEnqueue,
    ProcessingNotRetryable,
    ProcessingService,
)
from powerforge_document_processing.storage.base import DispositionType, ObjectStorage
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)

_LIKE_ESCAPE = "\\"
_ARTIFACT_FILENAMES = {
    PageArtifactType.ANALYSIS_IMAGE: "analysis.png",
    PageArtifactType.THUMBNAIL: "thumbnail.webp",
    PageArtifactType.NATIVE_TEXT: "native.txt",
}


class _ReadOnlyEnqueue:
    """Stand-in so a read can construct ProcessingService without publishing a task."""

    def enqueue_document_processing(self, run_id: uuid.UUID) -> None:
        return None


@dataclass(frozen=True)
class UploadMetadata:
    """Revision-scoped metadata supplied by the uploader. Blank values are None."""

    document_type: DocumentClassification = DocumentClassification.UNKNOWN
    document_number: str | None = None
    description: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class _MutationResult:
    """What a mutation did, so the caller can log and decide whether the revision changed."""

    revision_document_id: uuid.UUID
    document_id: uuid.UUID
    changed: bool = True
    log_extra: Mapping[str, Any] = field(default_factory=dict)


class DocumentService:
    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        settings: Settings,
        enqueue: DocumentProcessingEnqueue | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.settings = settings
        self._enqueue = enqueue

    def upload(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        fileobj: BinaryIO,
        filename: str,
        metadata: UploadMetadata | None = None,
    ) -> UploadResponse:
        metadata = metadata or UploadMetadata()
        project, revision = self._load_context(project_id, revision_id)
        assert_documents_mutable(project, revision)
        # Release the connection before the slow ingest and storage work; the locked
        # step below reloads everything it needs.
        self.session.rollback()

        document_id = uuid.uuid4()
        with ingest_upload(fileobj, filename, self.settings.max_upload_bytes) as upload:
            inspection = FileInspector(self.settings.max_image_pixels).inspect(
                upload.file, upload.extension
            )
            key = build_storage_key(project_id, document_id, upload.extension)
            self._store_object(project_id, revision_id, document_id, key, upload, inspection)
            try:
                revision_document_id, duplicate_ids = self._record(
                    project_id,
                    revision_id,
                    document_id,
                    key,
                    upload,
                    inspection,
                    metadata,
                )
            except BaseException as exc:
                self.session.rollback()
                self._log_database_failure(project_id, revision_id, document_id, exc)
                self._discard_object(project_id, document_id, key)
                raise

        # The upload is committed from here on; nothing below may remove the object.
        # Ensure runs before the response is built so a new upload already shows PENDING.
        self._ensure_processing(document_id)
        response = self._load_response(project_id, revision_id, revision_document_id)
        logger.info(
            "document uploaded",
            extra={
                "project_id": project_id,
                "revision_id": revision_id,
                "document_id": document_id,
                "revision_document_id": revision_document_id,
                "size_bytes": upload.size,
                "duplicate_detected": bool(duplicate_ids),
            },
        )
        if duplicate_ids:
            logger.info(
                "duplicate document detected",
                extra={
                    "project_id": project_id,
                    "revision_id": revision_id,
                    "document_id": document_id,
                    "duplicate_count": len(duplicate_ids),
                },
            )
        return UploadResponse(
            **response.model_dump(),
            duplicate_detected=bool(duplicate_ids),
            duplicate_document_ids=duplicate_ids,
        )

    def _ensure_processing(self, document_id: uuid.UUID) -> None:
        """Start processing after the document row is committed. Never fails the upload."""
        if self._enqueue is None:
            return
        try:
            ProcessingService(
                self.session,
                self.storage,
                self._enqueue,
            ).ensure_document_processing(document_id)
        except Exception:
            logger.exception(
                "document processing ensure failed",
                extra={"document_id": document_id},
            )

    def list_documents(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        *,
        status: DocumentStatusFilter = DocumentStatusFilter.INCLUDED,
        document_type: DocumentClassification | None = None,
        origin: DocumentOrigin | None = None,
        search: str | None = None,
    ) -> list[RevisionDocumentResponse]:
        self._load_context(project_id, revision_id)
        stmt = self._view_statement(project_id, revision_id)
        if status != DocumentStatusFilter.ALL:
            stmt = stmt.where(RevisionDocument.status == RevisionDocumentStatus(status.value))
        if document_type is not None:
            stmt = stmt.where(RevisionDocument.document_type == document_type)
        if origin is not None:
            stmt = stmt.where(RevisionDocument.origin == origin)
        if search and search.strip():
            pattern = _like_pattern(search)
            stmt = stmt.where(
                or_(
                    Document.original_filename.ilike(pattern, escape=_LIKE_ESCAPE),
                    RevisionDocument.document_number.ilike(pattern, escape=_LIKE_ESCAPE),
                    RevisionDocument.description.ilike(pattern, escape=_LIKE_ESCAPE),
                )
            )
        stmt = stmt.order_by(
            RevisionDocument.added_at,
            Document.original_filename,
            RevisionDocument.id,
        )
        return self._with_processing(list(self.session.execute(stmt).all()))

    def get_document(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> RevisionDocumentResponse:
        self._load_context(project_id, revision_id)
        return self._load_response(project_id, revision_id, revision_document_id)

    def get_processing(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> ProcessingStatusResponse:
        """The current run for this association. No run is a 200 with a null summary."""
        _, document = self._require_association(project_id, revision_id, revision_document_id)
        return _status_response(self._processing().current_run(document.id))

    def retry_processing(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> ProcessingStatusResponse:
        """Start a new attempt after a failed run. Not a revision mutation."""
        _, document = self._require_association(project_id, revision_id, revision_document_id)
        try:
            run = self._processing().retry_failed_processing(document.id)
        except ProcessingNotRetryable as exc:
            raise ProcessingNotRetryableError("Processing cannot be retried") from exc
        return _status_response(run)

    def list_pages(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> list[DocumentPageResponse]:
        _, document = self._require_association(project_id, revision_id, revision_document_id)
        run = self._require_completed(document.id)
        return self._pages_for(document.id, run.id)

    def get_page(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
        page_id: uuid.UUID,
    ) -> DocumentPageResponse:
        _, document = self._require_association(project_id, revision_id, revision_document_id)
        run = self._require_completed(document.id)
        page = self._require_page(document.id, page_id)
        artifacts = self._artifacts_for(run.id, [page.id])
        return _page_response(page, artifacts.get(page.id, []))

    def create_artifact_url(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
        page_id: uuid.UUID,
        artifact_type: str,
    ) -> DownloadUrlResponse:
        """Sign one artifact of the current completed run. No storage key in the body."""
        _, document = self._require_association(project_id, revision_id, revision_document_id)
        run = self._require_completed(document.id)
        page = self._require_page(document.id, page_id)
        parsed = _parse_artifact_type(artifact_type)
        artifact = self.session.scalar(
            select(PageArtifact).where(
                PageArtifact.processing_run_id == run.id,
                PageArtifact.document_page_id == page.id,
                PageArtifact.artifact_type == parsed,
            )
        )
        if artifact is None:
            raise PageNotFound("Artifact not found")
        filename = _ARTIFACT_FILENAMES[parsed]
        disposition: DispositionType = (
            "attachment" if parsed == PageArtifactType.NATIVE_TEXT else "inline"
        )
        expires_seconds = self.settings.s3_signed_url_expires_seconds
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_seconds)
        try:
            url = self.storage.create_download_url(
                artifact.storage_key,
                filename,
                artifact.mime_type,
                disposition,
                expires_seconds,
            )
        except Exception as exc:
            logger.error(
                "artifact url signing failed",
                extra={
                    "project_id": project_id,
                    "document_id": document.id,
                    "page_id": page_id,
                    "error_class": type(exc).__name__,
                },
            )
            raise StorageDownloadFailed("Could not create a download link") from None
        return DownloadUrlResponse(url=url, expires_at=expires_at, filename=filename)

    def create_download_url(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
        disposition: DispositionType = "attachment",
    ) -> DownloadUrlResponse:
        """Sign a download URL for one association. A read: no locks, any status allowed."""
        self._load_context(project_id, revision_id)
        row = self.session.execute(
            self._view_statement(project_id, revision_id).where(
                RevisionDocument.id == revision_document_id
            )
        ).one_or_none()
        if row is None:
            raise RevisionDocumentNotFound(f"Document {revision_document_id} not found")
        _, document, _ = row
        key, filename, mime_type = (
            document.storage_key,
            document.original_filename,
            document.mime_type,
        )
        document_id = document.id
        expires_seconds = self.settings.s3_signed_url_expires_seconds
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_seconds)
        try:
            url = self.storage.create_download_url(
                key, filename, mime_type, disposition, expires_seconds
            )
        except Exception as exc:
            logger.error(
                "download url signing failed",
                extra={
                    "project_id": project_id,
                    "revision_id": revision_id,
                    "document_id": document_id,
                    "error_class": type(exc).__name__,
                },
            )
            # The SDK message can carry endpoints or request details; never forward it.
            raise StorageDownloadFailed("Could not create a download link") from None
        logger.info(
            "document download url issued",
            extra={
                "project_id": project_id,
                "revision_id": revision_id,
                "document_id": document_id,
                "revision_document_id": revision_document_id,
                "disposition": disposition,
                "expires_seconds": expires_seconds,
            },
        )
        return DownloadUrlResponse(url=url, expires_at=expires_at, filename=filename)

    def _load_context(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
    ) -> tuple[Project, ProjectRevision]:
        project = self.session.get(Project, project_id)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        revision = self.session.get(ProjectRevision, revision_id)
        if revision is None:
            raise RevisionNotFound(f"Revision {revision_id} not found")
        if revision.project_id != project_id:
            raise RevisionProjectMismatch("Revision does not belong to this project")
        return project, revision

    def update_metadata(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
        data: RevisionDocumentUpdate,
    ) -> RevisionDocumentResponse:
        updates = data.provided_metadata()

        def apply(_revision: ProjectRevision) -> _MutationResult:
            association = self._load_association(project_id, revision_id, revision_document_id)
            if association.status == RevisionDocumentStatus.REMOVED:
                raise DocumentRemoved("Restore the document before editing its metadata")
            changed = sorted(
                name for name, value in updates.items() if getattr(association, name) != value
            )
            for name in changed:
                setattr(association, name, updates[name])
            return _MutationResult(
                association.id,
                association.document_id,
                changed=bool(changed),
                log_extra={"changed_fields": changed},
            )

        result = self._mutate(project_id, revision_id, "update_document_metadata", apply)
        if result.changed:
            self._log("document metadata updated", project_id, revision_id, result)
        return self._load_response(project_id, revision_id, result.revision_document_id)

    def remove(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> RevisionDocumentResponse:
        def apply(_revision: ProjectRevision) -> _MutationResult:
            association = self._load_association(project_id, revision_id, revision_document_id)
            if association.status == RevisionDocumentStatus.REMOVED:
                return _MutationResult(association.id, association.document_id, changed=False)
            association.status = RevisionDocumentStatus.REMOVED
            association.removed_at = datetime.now(UTC)
            association.removed_by = None
            return _MutationResult(association.id, association.document_id)

        result = self._mutate(project_id, revision_id, "remove_document", apply)
        if result.changed:
            self._log("document removed", project_id, revision_id, result)
        return self._load_response(project_id, revision_id, result.revision_document_id)

    def restore(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> RevisionDocumentResponse:
        def apply(_revision: ProjectRevision) -> _MutationResult:
            association = self._load_association(project_id, revision_id, revision_document_id)
            if association.status == RevisionDocumentStatus.INCLUDED:
                return _MutationResult(association.id, association.document_id, changed=False)
            association.status = RevisionDocumentStatus.INCLUDED
            association.removed_at = None
            association.removed_by = None
            return _MutationResult(association.id, association.document_id)

        result = self._mutate(project_id, revision_id, "restore_document", apply)
        if result.changed:
            self._log("document restored", project_id, revision_id, result)
        return self._load_response(project_id, revision_id, result.revision_document_id)

    def reuse(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        data: ReuseDocumentRequest,
    ) -> RevisionDocumentResponse:
        overrides = data.provided_metadata()

        def apply(_revision: ProjectRevision) -> _MutationResult:
            # The source revision is deliberately not locked: only the target is, so two
            # reuses in opposite directions cannot deadlock. The source is read after the
            # target lock, and a concurrent change to it only affects this snapshot.
            source = self.session.execute(
                select(RevisionDocument)
                .where(RevisionDocument.id == data.source_revision_document_id)
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if source is None:
                raise RevisionDocumentNotFound(
                    f"Document {data.source_revision_document_id} not found"
                )
            if source.project_id != project_id:
                raise CrossProjectDocumentAccess(
                    "The source document belongs to a different project"
                )
            # Checked before anything else: reusing into the source's own revision, or
            # into a revision that already holds the document, is a conflict.
            existing = self._existing_association(revision_id, source.document_id)
            if existing is not None:
                if existing.status == RevisionDocumentStatus.REMOVED:
                    message = (
                        "This document was removed from the revision; restore it instead "
                        "of adding it again"
                    )
                else:
                    message = "This document is already in the revision"
                raise DocumentAlreadyInRevision(message, existing.id, existing.status.value)
            if source.status == RevisionDocumentStatus.REMOVED:
                raise DocumentRemoved(
                    "The source document was removed from its revision; restore it first"
                )

            fields = {
                "document_type": source.document_type,
                "document_number": source.document_number,
                "description": source.description,
                "notes": source.notes,
                **overrides,
            }
            association = RevisionDocument(
                project_id=project_id,
                revision_id=revision_id,
                document_id=source.document_id,
                origin=DocumentOrigin.INHERITED,
                inherited_from_revision_id=source.revision_id,
                status=RevisionDocumentStatus.INCLUDED,
                **fields,
            )
            self.session.add(association)
            self.session.flush()
            return _MutationResult(
                association.id,
                source.document_id,
                log_extra={
                    "source_revision_document_id": source.id,
                    "source_revision_id": source.revision_id,
                },
            )

        result = self._mutate(
            project_id,
            revision_id,
            "reuse_document",
            apply,
            {
                "uq_revision_documents_revision_id_document_id": DocumentAlreadyInRevision(
                    "This document is already in the revision; if it was removed, "
                    "restore it instead"
                )
            },
        )
        self._log("document reused", project_id, revision_id, result)
        return self._load_response(project_id, revision_id, result.revision_document_id)

    def _mutate(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        operation: str,
        apply: Callable[[ProjectRevision], _MutationResult],
        constraint_errors: Mapping[str, ProjectError] | None = None,
    ) -> _MutationResult:
        """Run ``apply`` under the shared lock-and-recheck path, then commit.

        Project and revision existence is checked first (404s). ``apply`` runs with the
        project locked FOR SHARE, the revision locked FOR UPDATE and mutability re-checked.
        """
        self._load_context(project_id, revision_id)
        try:
            with integrity_guard(self.session, constraint_errors or {}, operation=operation):
                revision = self._lock_for_mutation(project_id, revision_id)
                result = apply(revision)
                if result.changed:
                    revision.updated_at = datetime.now(UTC)
                self.session.commit()
        except BaseException:
            # Release the locks on every failure, not only integrity errors.
            self.session.rollback()
            raise
        return result

    def _lock_for_mutation(self, project_id: uuid.UUID, revision_id: uuid.UUID) -> ProjectRevision:
        """Project FOR SHARE, then revision FOR UPDATE, then the mutability re-check (D11)."""
        project = lock_project_shared(self.session, project_id)
        if project is None:
            raise ProjectNotFound(f"Project {project_id} not found")
        revision = lock_revision(self.session, project_id, revision_id)
        if revision is None:
            raise RevisionNotFound(f"Revision {revision_id} not found")
        assert_documents_mutable(project, revision)
        return revision

    def _load_association(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> RevisionDocument:
        association = self.session.execute(
            select(RevisionDocument)
            .where(
                RevisionDocument.id == revision_document_id,
                RevisionDocument.revision_id == revision_id,
                RevisionDocument.project_id == project_id,
            )
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if association is None:
            raise RevisionDocumentNotFound(f"Document {revision_document_id} not found")
        return association

    def _existing_association(
        self,
        revision_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> RevisionDocument | None:
        return self.session.execute(
            select(RevisionDocument)
            .where(
                RevisionDocument.revision_id == revision_id,
                RevisionDocument.document_id == document_id,
            )
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()

    @staticmethod
    def _log(
        message: str,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        result: _MutationResult,
    ) -> None:
        logger.info(
            message,
            extra={
                "project_id": project_id,
                "revision_id": revision_id,
                "document_id": result.document_id,
                "revision_document_id": result.revision_document_id,
                **result.log_extra,
            },
        )

    def _store_object(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        document_id: uuid.UUID,
        key: str,
        upload: IngestedUpload,
        inspection: InspectionResult,
    ) -> None:
        try:
            self.storage.put(key, upload.file, upload.size, inspection.mime_type)
        except Exception as exc:
            logger.error(
                "object storage upload failed",
                extra={
                    "project_id": project_id,
                    "revision_id": revision_id,
                    "document_id": document_id,
                    "error_class": type(exc).__name__,
                },
            )
            # The SDK message can carry endpoints or request details; never forward it.
            raise StorageUploadFailed("Could not store the uploaded file") from None

    def _record(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        document_id: uuid.UUID,
        key: str,
        upload: IngestedUpload,
        inspection: InspectionResult,
        metadata: UploadMetadata,
    ) -> tuple[uuid.UUID, list[uuid.UUID]]:
        with integrity_guard(self.session, {}, operation="upload_document"):
            revision = self._lock_for_mutation(project_id, revision_id)

            duplicate_ids = list(
                self.session.scalars(
                    select(Document.id)
                    .where(Document.project_id == project_id, Document.sha256 == upload.sha256)
                    .order_by(Document.uploaded_at, Document.id)
                )
            )
            self.session.add(
                Document(
                    id=document_id,
                    project_id=project_id,
                    original_filename=upload.filename,
                    storage_key=key,
                    mime_type=inspection.mime_type,
                    file_extension=upload.extension,
                    size_bytes=upload.size,
                    sha256=upload.sha256,
                )
            )
            self.session.flush()
            association = RevisionDocument(
                project_id=project_id,
                revision_id=revision_id,
                document_id=document_id,
                origin=DocumentOrigin.UPLOADED,
                status=RevisionDocumentStatus.INCLUDED,
                document_type=metadata.document_type,
                document_number=metadata.document_number,
                description=metadata.description,
                notes=metadata.notes,
            )
            self.session.add(association)
            self.session.flush()
            revision.updated_at = datetime.now(UTC)
            revision_document_id = association.id
            self.session.commit()
        return revision_document_id, duplicate_ids

    def _log_database_failure(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        document_id: uuid.UUID,
        exc: BaseException,
    ) -> None:
        # Mutability and ownership rejections are expected outcomes, not faults.
        level = logging.WARNING if isinstance(exc, ProjectError) else logging.ERROR
        logger.log(
            level,
            "document database step failed",
            extra={
                "project_id": project_id,
                "revision_id": revision_id,
                "document_id": document_id,
                "error_class": type(exc).__name__,
            },
        )

    def _discard_object(self, project_id: uuid.UUID, document_id: uuid.UUID, key: str) -> None:
        """Best-effort removal of an object whose database record was not committed."""
        try:
            self.storage.delete(key)
        except Exception as exc:
            logger.error(
                "orphan object cleanup failed",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "error_class": type(exc).__name__,
                },
            )

    def _view_statement(self, project_id: uuid.UUID, revision_id: uuid.UUID) -> Select[Any]:
        inherited = aliased(ProjectRevision)
        stmt = (
            select(RevisionDocument, Document, inherited.identifier)
            .join(
                Document,
                and_(
                    Document.id == RevisionDocument.document_id,
                    Document.project_id == RevisionDocument.project_id,
                ),
            )
            .outerjoin(inherited, inherited.id == RevisionDocument.inherited_from_revision_id)
            .where(
                RevisionDocument.project_id == project_id,
                RevisionDocument.revision_id == revision_id,
            )
        )
        return stmt

    def _load_response(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> RevisionDocumentResponse:
        stmt = self._view_statement(project_id, revision_id)
        row = self.session.execute(
            stmt.where(RevisionDocument.id == revision_document_id)
        ).one_or_none()
        if row is None:
            raise RevisionDocumentNotFound(f"Document {revision_document_id} not found")
        return self._with_processing([row])[0]

    def _with_processing(self, rows: list[Any]) -> list[RevisionDocumentResponse]:
        runs = self._processing().current_runs([row[1].id for row in rows])
        return [_to_response(*row, runs.get(row[1].id)) for row in rows]

    def _processing(self) -> ProcessingService:
        enqueue = self._enqueue if self._enqueue is not None else _ReadOnlyEnqueue()
        return ProcessingService(self.session, self.storage, enqueue)

    def _require_association(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> tuple[RevisionDocument, Document]:
        """Load the association without the mutation lock. Removed rows are included."""
        self._load_context(project_id, revision_id)
        row = self.session.execute(
            self._view_statement(project_id, revision_id).where(
                RevisionDocument.id == revision_document_id
            )
        ).one_or_none()
        if row is None:
            raise RevisionDocumentNotFound(f"Document {revision_document_id} not found")
        association, document, _identifier = row
        return association, document

    def _require_completed(self, document_id: uuid.UUID) -> DocumentProcessingRun:
        run = self._processing().current_run(document_id)
        if run is None or run.status != ProcessingRunStatus.COMPLETED:
            raise ProcessingNotComplete("Processing is not complete")
        return run

    def _require_page(self, document_id: uuid.UUID, page_id: uuid.UUID) -> DocumentPage:
        page = self.session.get(DocumentPage, page_id)
        if page is None or page.document_id != document_id:
            raise PageNotFound("Page not found")
        return page

    def _pages_for(self, document_id: uuid.UUID, run_id: uuid.UUID) -> list[DocumentPageResponse]:
        pages = list(
            self.session.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number, DocumentPage.id)
            ).all()
        )
        artifacts = self._artifacts_for(run_id, [page.id for page in pages])
        return [_page_response(page, artifacts.get(page.id, [])) for page in pages]

    def _artifacts_for(
        self,
        run_id: uuid.UUID,
        page_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[PageArtifact]]:
        if not page_ids:
            return {}
        rows = self.session.scalars(
            select(PageArtifact).where(
                PageArtifact.processing_run_id == run_id,
                PageArtifact.document_page_id.in_(page_ids),
            )
        ).all()
        grouped: dict[uuid.UUID, list[PageArtifact]] = {}
        for artifact in rows:
            grouped.setdefault(artifact.document_page_id, []).append(artifact)
        return grouped


def _like_pattern(term: str) -> str:
    escaped = (
        term.strip()
        .replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


def _to_response(
    association: RevisionDocument,
    document: Document,
    inherited_identifier: str | None,
    run: DocumentProcessingRun | None = None,
) -> RevisionDocumentResponse:
    return RevisionDocumentResponse(
        id=association.id,
        revision_id=association.revision_id,
        document=DocumentSummary.model_validate(document),
        origin=association.origin,
        inherited_from_revision_id=association.inherited_from_revision_id,
        inherited_from_revision_identifier=inherited_identifier,
        status=association.status,
        document_type=association.document_type,
        document_number=association.document_number,
        description=association.description,
        notes=association.notes,
        added_at=association.added_at,
        removed_at=association.removed_at,
        processing=_summary(run),
    )


def _summary(run: DocumentProcessingRun | None) -> ProcessingSummary | None:
    if run is None:
        return None
    return ProcessingSummary(
        status=run.status,
        attempt_count=run.attempt_count,
        pages_processed=run.pages_processed,
        pages_total=run.pages_total,
        error_code=run.error_code,
        error_message=run.error_message,
    )


def _status_response(run: DocumentProcessingRun | None) -> ProcessingStatusResponse:
    if run is None:
        return ProcessingStatusResponse()
    return ProcessingStatusResponse(
        processing=_summary(run),
        processor_version=run.processor_version,
        profile_version=run.profile_version,
        profile_hash=run.profile_hash,
    )


def _page_response(page: DocumentPage, artifacts: list[PageArtifact]) -> DocumentPageResponse:
    ordered = sorted(artifacts, key=lambda artifact: artifact.artifact_type.value)
    return DocumentPageResponse(
        id=page.id,
        page_number=page.page_number,
        source_width=page.source_width,
        source_height=page.source_height,
        source_unit=page.source_unit,
        rotation_degrees=page.rotation_degrees,
        native_text_char_count=page.native_text_char_count,
        artifacts=[
            PageArtifactInfo(
                artifact_type=artifact.artifact_type,
                mime_type=artifact.mime_type,
                width_px=artifact.width_px,
                height_px=artifact.height_px,
            )
            for artifact in ordered
        ],
    )


def _parse_artifact_type(value: str) -> PageArtifactType:
    try:
        return PageArtifactType(value)
    except ValueError as exc:
        raise PageNotFound("Artifact not found") from exc
