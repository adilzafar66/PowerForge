"""Single mapping point from domain errors to HTTP responses."""

from __future__ import annotations

from fastapi import HTTPException, status

from powerforge_api.exceptions import (
    ArchivedProject,
    CancelledProject,
    CrossProjectDocumentAccess,
    DuplicateProjectNumber,
    DuplicateRevisionIdentifier,
    FileTooLarge,
    InvalidBaseRevision,
    InvalidFileContent,
    InvalidRevisionIdentifier,
    InvalidStatusTransition,
    ProjectError,
    ProjectNotFound,
    ProjectNotModifiable,
    RevisionDocumentNotFound,
    RevisionNotActivatable,
    RevisionNotFound,
    RevisionProjectMismatch,
    RevisionReadOnly,
    StorageUploadFailed,
    UnexpectedIntegrityError,
    UnsupportedDocumentType,
)

_UNPROCESSABLE = 422
_TOO_LARGE = 413


def http_for(exc: ProjectError) -> HTTPException:
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(
        exc,
        ProjectNotFound
        | RevisionNotFound
        | RevisionProjectMismatch
        | RevisionDocumentNotFound
        | CrossProjectDocumentAccess,
    ):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        exc,
        DuplicateProjectNumber
        | DuplicateRevisionIdentifier
        | InvalidStatusTransition
        | ProjectNotModifiable
        | ArchivedProject
        | CancelledProject
        | RevisionNotActivatable
        | RevisionReadOnly,
    ):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, FileTooLarge):
        status_code = _TOO_LARGE
    elif isinstance(exc, UnsupportedDocumentType):
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif isinstance(exc, InvalidRevisionIdentifier | InvalidBaseRevision | InvalidFileContent):
        status_code = _UNPROCESSABLE
    elif isinstance(exc, StorageUploadFailed):
        status_code = status.HTTP_502_BAD_GATEWAY
    elif isinstance(exc, UnexpectedIntegrityError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return HTTPException(
        status_code=status_code,
        detail={"detail": exc.message, "code": exc.code},
    )
