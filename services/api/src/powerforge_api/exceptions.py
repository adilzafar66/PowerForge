"""Domain exceptions for the project module."""

import uuid


class ProjectError(Exception):
    """Base class for project-domain errors."""

    code: str = "project_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ProjectNotFound(ProjectError):
    code = "project_not_found"


class DuplicateProjectNumber(ProjectError):
    code = "duplicate_project_number"


class InvalidStatusTransition(ProjectError):
    code = "invalid_status_transition"


class ProjectNotModifiable(ProjectError):
    code = "project_not_modifiable"


class ArchivedProject(ProjectNotModifiable):
    code = "archived_project"


class CancelledProject(ProjectNotModifiable):
    code = "cancelled_project"


class RevisionNotFound(ProjectError):
    code = "revision_not_found"


class RevisionProjectMismatch(ProjectError):
    code = "revision_project_mismatch"


class DuplicateRevisionIdentifier(ProjectError):
    code = "duplicate_revision_identifier"


class InvalidRevisionIdentifier(ProjectError):
    code = "invalid_revision_identifier"


class RevisionNotActivatable(ProjectError):
    code = "revision_not_activatable"


class InvalidBaseRevision(ProjectError):
    code = "invalid_base_revision"


class RevisionReadOnly(ProjectError):
    code = "revision_read_only"


class UnsupportedDocumentType(ProjectError):
    code = "unsupported_document_type"


class InvalidFileContent(ProjectError):
    code = "invalid_file_content"


class FileTooLarge(ProjectError):
    code = "file_too_large"


class RevisionDocumentNotFound(ProjectError):
    code = "revision_document_not_found"


class CrossProjectDocumentAccess(ProjectError):
    code = "cross_project_document_access"


class StorageUploadFailed(ProjectError):
    code = "storage_upload_failed"


class StorageDownloadFailed(ProjectError):
    code = "storage_download_failed"


class DocumentAlreadyInRevision(ProjectError):
    """The target revision already holds an association for this Document.

    ``existing_revision_document_id`` and ``existing_status`` let a client offer
    "restore" when the existing association is REMOVED.
    """

    code = "document_already_in_revision"

    def __init__(
        self,
        message: str,
        existing_revision_document_id: uuid.UUID | None = None,
        existing_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.existing_revision_document_id = existing_revision_document_id
        self.existing_status = existing_status


class DocumentRemoved(ProjectError):
    code = "document_removed"


class ProcessingNotComplete(ProjectError):
    code = "processing_not_complete"


class ProcessingNotRetryableError(ProjectError):
    code = "processing_not_retryable"


class PageNotFound(ProjectError):
    code = "page_not_found"


class AIClassificationDisabled(ProjectError):
    code = "ai_classification_disabled"


class ClassificationInProgressError(ProjectError):
    code = "classification_in_progress"

    def __init__(self, message: str, run_id: uuid.UUID) -> None:
        super().__init__(message)
        self.run_id = run_id


class ClassificationNotRetryableError(ProjectError):
    code = "classification_not_retryable"


class ClassificationNotComplete(ProjectError):
    code = "classification_not_complete"


class ClassificationNotAcceptable(ProjectError):
    code = "classification_not_acceptable"


class ClassificationPredictionNotFound(ProjectError):
    code = "classification_prediction_not_found"


class ClassificationRunNotFound(ProjectError):
    code = "classification_run_not_found"


class UnexpectedIntegrityError(ProjectError):
    code = "unexpected_integrity_error"

    def __init__(
        self,
        message: str = "An unexpected database integrity error occurred",
    ) -> None:
        super().__init__(message)


class EquipmentNotFound(ProjectError):
    code = "equipment_not_found"


class EquipmentAttributeNotFound(ProjectError):
    code = "equipment_attribute_not_found"


class EquipmentTypeChangeConflict(ProjectError):
    code = "equipment_type_change_conflict"


class InvalidEquipmentAttributeState(ProjectError):
    code = "invalid_equipment_attribute_state"


class InconsistentEquipment(ProjectError):
    code = "inconsistent_equipment"


class EquipmentRemoved(ProjectError):
    code = "equipment_removed"


class ModelInheritanceConflict(ProjectError):
    code = "model_inheritance_conflict"


class InvalidSystemFrequency(ProjectError):
    code = "invalid_system_frequency"


class InvalidSystemPhaseCount(ProjectError):
    code = "invalid_system_phase_count"
