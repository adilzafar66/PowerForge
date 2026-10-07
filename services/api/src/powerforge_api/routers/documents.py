"""REST API for revision documents: upload, list, get, edit, remove, restore and reuse."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import Response
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from powerforge_api.db import get_session
from powerforge_api.exceptions import FileTooLarge, ProjectError
from powerforge_api.routers.errors import http_for
from powerforge_api.schemas.documents import (
    MAX_DESCRIPTION_LENGTH,
    MAX_DOCUMENT_NUMBER_LENGTH,
    MAX_NOTES_LENGTH,
    DocumentStatusFilter,
    DownloadUrlResponse,
    ReuseDocumentRequest,
    RevisionDocumentListResponse,
    RevisionDocumentResponse,
    RevisionDocumentUpdate,
    UploadResponse,
)
from powerforge_api.services.document_service import DocumentService, UploadMetadata
from powerforge_api.storage.base import DispositionType, ObjectStorage
from powerforge_api.storage.factory import get_object_storage
from powerforge_document_model import DocumentClassification, DocumentOrigin
from powerforge_shared.config import Settings, get_settings

# Room for multipart boundaries and the text fields on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 256 * 1024

SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[ObjectStorage, Depends(get_object_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class UploadSizeGuardRoute(APIRoute):
    """Reject an oversized upload from its Content-Length before the body is read.

    FastAPI parses the multipart form before dependencies run, so this has to wrap
    the route handler. The header is client-supplied and only an optimisation; the
    streaming limit in ``ingest_upload`` is what actually enforces the cap.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            if request.method == "POST":
                _reject_oversized(request)
            return await original(request)

        return handler


def _reject_oversized(request: Request) -> None:
    header = request.headers.get("content-length")
    if header is None or not header.isdigit():
        return
    provider = request.app.dependency_overrides.get(get_settings, get_settings)
    limit = provider().max_upload_bytes + MULTIPART_OVERHEAD_BYTES
    if int(header) > limit:
        raise http_for(FileTooLarge("File exceeds the maximum upload size"))


router = APIRouter(
    prefix="/api/projects/{project_id}/revisions/{revision_id}/documents",
    tags=["documents"],
)


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def upload_document(
    project_id: UUID,
    revision_id: UUID,
    file: Annotated[UploadFile, File(description="PDF, PNG, JPEG or TIFF file")],
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    document_type: Annotated[DocumentClassification, Form()] = DocumentClassification.UNKNOWN,
    document_number: Annotated[str | None, Form(max_length=MAX_DOCUMENT_NUMBER_LENGTH)] = None,
    description: Annotated[str | None, Form(max_length=MAX_DESCRIPTION_LENGTH)] = None,
    notes: Annotated[str | None, Form(max_length=MAX_NOTES_LENGTH)] = None,
) -> UploadResponse:
    metadata = UploadMetadata(
        document_type=document_type,
        document_number=_blank_to_none(document_number),
        description=_blank_to_none(description),
        notes=_blank_to_none(notes),
    )
    service = DocumentService(session, storage, settings)
    try:
        return service.upload(project_id, revision_id, file.file, file.filename or "", metadata)
    except ProjectError as exc:
        raise http_for(exc) from exc


# Only the upload route carries the Content-Length guard; the JSON routes do not.
router.add_api_route(
    "",
    upload_document,
    methods=["POST"],
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document into a revision",
    route_class_override=UploadSizeGuardRoute,
)


@router.get(
    "",
    response_model=RevisionDocumentListResponse,
    summary="List documents in a revision",
)
def list_documents(
    project_id: UUID,
    revision_id: UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    status_filter: Annotated[
        DocumentStatusFilter,
        Query(alias="status", description="INCLUDED (default), REMOVED or ALL"),
    ] = DocumentStatusFilter.INCLUDED,
    document_type: Annotated[DocumentClassification | None, Query()] = None,
    origin: Annotated[DocumentOrigin | None, Query()] = None,
    search: Annotated[
        str | None,
        Query(description="Match filename, document number or description"),
    ] = None,
) -> RevisionDocumentListResponse:
    service = DocumentService(session, storage, settings)
    try:
        items = service.list_documents(
            project_id,
            revision_id,
            status=status_filter,
            document_type=document_type,
            origin=origin,
            search=search,
        )
    except ProjectError as exc:
        raise http_for(exc) from exc
    return RevisionDocumentListResponse(items=items)


@router.get(
    "/{revision_document_id}",
    response_model=RevisionDocumentResponse,
    summary="Get one document of a revision",
)
def get_document(
    project_id: UUID,
    revision_id: UUID,
    revision_document_id: UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> RevisionDocumentResponse:
    service = DocumentService(session, storage, settings)
    try:
        return service.get_document(project_id, revision_id, revision_document_id)
    except ProjectError as exc:
        raise http_for(exc) from exc


@router.get(
    "/{revision_document_id}/download-url",
    response_model=DownloadUrlResponse,
    summary="Get a short-lived signed URL for the original file",
)
def download_url(
    project_id: UUID,
    revision_id: UUID,
    revision_document_id: UUID,
    response: Response,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    disposition: Annotated[
        DispositionType,
        Query(description="attachment (default) downloads; inline lets the browser display it"),
    ] = "attachment",
) -> DownloadUrlResponse:
    service = DocumentService(session, storage, settings)
    try:
        result = service.create_download_url(
            project_id, revision_id, revision_document_id, disposition
        )
    except ProjectError as exc:
        raise http_for(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/reuse",
    response_model=RevisionDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an existing project document to this revision",
)
def reuse_document(
    project_id: UUID,
    revision_id: UUID,
    body: ReuseDocumentRequest,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> RevisionDocumentResponse:
    service = DocumentService(session, storage, settings)
    try:
        return service.reuse(project_id, revision_id, body)
    except ProjectError as exc:
        raise http_for(exc) from exc


@router.patch(
    "/{revision_document_id}",
    response_model=RevisionDocumentResponse,
    summary="Edit the metadata of a document in a revision",
)
def update_document(
    project_id: UUID,
    revision_id: UUID,
    revision_document_id: UUID,
    body: RevisionDocumentUpdate,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> RevisionDocumentResponse:
    service = DocumentService(session, storage, settings)
    try:
        return service.update_metadata(project_id, revision_id, revision_document_id, body)
    except ProjectError as exc:
        raise http_for(exc) from exc


@router.post(
    "/{revision_document_id}/remove",
    response_model=RevisionDocumentResponse,
    summary="Remove a document from a revision (the file is kept)",
)
def remove_document(
    project_id: UUID,
    revision_id: UUID,
    revision_document_id: UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> RevisionDocumentResponse:
    service = DocumentService(session, storage, settings)
    try:
        return service.remove(project_id, revision_id, revision_document_id)
    except ProjectError as exc:
        raise http_for(exc) from exc


@router.post(
    "/{revision_document_id}/restore",
    response_model=RevisionDocumentResponse,
    summary="Restore a removed document to a revision",
)
def restore_document(
    project_id: UUID,
    revision_id: UUID,
    revision_document_id: UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> RevisionDocumentResponse:
    service = DocumentService(session, storage, settings)
    try:
        return service.restore(project_id, revision_id, revision_document_id)
    except ProjectError as exc:
        raise http_for(exc) from exc
