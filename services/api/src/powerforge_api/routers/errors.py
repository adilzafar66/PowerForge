"""Single mapping point from domain errors to HTTP responses."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status

from powerforge_api.exceptions import (
    AIClassificationDisabled,
    ArchivedProject,
    CancelledProject,
    ClassificationInProgressError,
    ClassificationNotAcceptable,
    ClassificationNotComplete,
    ClassificationNotRetryableError,
    ClassificationPredictionNotFound,
    ClassificationRunNotFound,
    CrossProjectDocumentAccess,
    DocumentAlreadyInRevision,
    DocumentRemoved,
    DuplicateProjectNumber,
    DuplicateRevisionIdentifier,
    EquipmentAttributeNotFound,
    EquipmentNotFound,
    EquipmentRemoved,
    EquipmentTypeChangeConflict,
    FileTooLarge,
    InconsistentEquipment,
    InvalidBaseRevision,
    InvalidEngineeringModelInput,
    InvalidEquipmentAttributeState,
    InvalidFileContent,
    InvalidRevisionIdentifier,
    InvalidStatusTransition,
    InvalidSystemFrequency,
    InvalidSystemPhaseCount,
    InvalidTopology,
    ModelConnectionNotFound,
    ModelInheritanceConflict,
    ModelNodeNotFound,
    PageNotFound,
    ProcessingNotComplete,
    ProcessingNotRetryableError,
    ProjectError,
    ProjectNotFound,
    ProjectNotModifiable,
    RevisionDocumentNotFound,
    RevisionNotActivatable,
    RevisionNotFound,
    RevisionProjectMismatch,
    RevisionReadOnly,
    StorageDownloadFailed,
    StorageUploadFailed,
    TopologyObjectRemoved,
    UnexpectedIntegrityError,
    UnsupportedDocumentType,
)
from powerforge_engineering_model.errors import (
    IncompatibleUnit,
    InvalidAttributeValue,
    UnknownAttribute,
    UnknownEquipmentType,
    UnknownUnit,
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
        | CrossProjectDocumentAccess
        | PageNotFound
        | ClassificationPredictionNotFound
        | ClassificationRunNotFound
        | EquipmentNotFound
        | EquipmentAttributeNotFound
        | ModelNodeNotFound
        | ModelConnectionNotFound,
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
        | RevisionReadOnly
        | DocumentAlreadyInRevision
        | DocumentRemoved
        | ProcessingNotComplete
        | ProcessingNotRetryableError
        | AIClassificationDisabled
        | ClassificationInProgressError
        | ClassificationNotRetryableError
        | ClassificationNotComplete
        | ClassificationNotAcceptable
        | EquipmentRemoved
        | TopologyObjectRemoved
        | EquipmentTypeChangeConflict,
    ):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, FileTooLarge):
        status_code = _TOO_LARGE
    elif isinstance(exc, UnsupportedDocumentType):
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif isinstance(
        exc,
        InvalidRevisionIdentifier
        | InvalidBaseRevision
        | InvalidFileContent
        | InvalidSystemFrequency
        | InvalidSystemPhaseCount
        | ModelInheritanceConflict
        | InvalidEngineeringModelInput
        | InvalidEquipmentAttributeState
        | InvalidTopology,
    ):
        status_code = _UNPROCESSABLE
    elif isinstance(exc, StorageUploadFailed | StorageDownloadFailed):
        status_code = status.HTTP_502_BAD_GATEWAY
    elif isinstance(exc, UnexpectedIntegrityError | InconsistentEquipment):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: dict[str, str] = {"detail": exc.message, "code": exc.code}
    if isinstance(exc, InconsistentEquipment):
        detail["detail"] = "An internal engineering model consistency error occurred"
    if isinstance(exc, DocumentAlreadyInRevision):
        if exc.existing_revision_document_id is not None:
            detail["existing_revision_document_id"] = str(exc.existing_revision_document_id)
        if exc.existing_status is not None:
            detail["existing_status"] = exc.existing_status
    if isinstance(exc, ClassificationInProgressError):
        detail["run_id"] = str(exc.run_id)
    return HTTPException(status_code=status_code, detail=detail)


@contextmanager
def model_api_errors() -> Iterator[None]:
    """Translate known input failures only; registry-definition bugs remain server errors."""
    try:
        yield
    except ProjectError as exc:
        raise http_for(exc) from exc
    except (
        UnknownEquipmentType,
        UnknownAttribute,
        InvalidAttributeValue,
        UnknownUnit,
        IncompatibleUnit,
    ) as exc:
        raise http_for(InvalidEngineeringModelInput(str(exc))) from exc
