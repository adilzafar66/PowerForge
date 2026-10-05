"""Upload, list and get for revision documents.

Locking follows decision D11: a mutation holds the project row FOR SHARE, then the
revision row FOR UPDATE, then re-checks mutability. It never upgrades its project
lock. Object storage is written before any lock is taken, so slow uploads never hold
database locks; a failure after the write removes the object again.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, BinaryIO

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session, aliased

from powerforge_api.db_errors import integrity_guard
from powerforge_api.exceptions import (
    ProjectError,
    ProjectNotFound,
    RevisionDocumentNotFound,
    RevisionNotFound,
    RevisionProjectMismatch,
    StorageUploadFailed,
)
from powerforge_api.models import Document, Project, ProjectRevision, RevisionDocument
from powerforge_api.schemas.documents import (
    DocumentStatusFilter,
    DocumentSummary,
    RevisionDocumentResponse,
    UploadResponse,
)
from powerforge_api.services.file_ingest import IngestedUpload, ingest_upload
from powerforge_api.services.file_inspector import FileInspector, InspectionResult
from powerforge_api.services.revision_documents import (
    assert_documents_mutable,
    lock_project_shared,
    lock_revision,
)
from powerforge_api.storage.base import ObjectStorage
from powerforge_document_model import (
    DocumentClassification,
    DocumentOrigin,
    RevisionDocumentStatus,
    build_storage_key,
)
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)

_LIKE_ESCAPE = "\\"


@dataclass(frozen=True)
class UploadMetadata:
    """Revision-scoped metadata supplied by the uploader. Blank values are None."""

    document_type: DocumentClassification = DocumentClassification.UNKNOWN
    document_number: str | None = None
    description: str | None = None
    notes: str | None = None


class DocumentService:
    def __init__(self, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self.session = session
        self.storage = storage
        self.settings = settings

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
        return [_to_response(*row) for row in self.session.execute(stmt).all()]

    def get_document(
        self,
        project_id: uuid.UUID,
        revision_id: uuid.UUID,
        revision_document_id: uuid.UUID,
    ) -> RevisionDocumentResponse:
        self._load_context(project_id, revision_id)
        return self._load_response(project_id, revision_id, revision_document_id)

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
            project = lock_project_shared(self.session, project_id)
            if project is None:
                raise ProjectNotFound(f"Project {project_id} not found")
            revision = lock_revision(self.session, project_id, revision_id)
            if revision is None:
                raise RevisionNotFound(f"Revision {revision_id} not found")
            assert_documents_mutable(project, revision)

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
        return _to_response(*row)


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
    )
