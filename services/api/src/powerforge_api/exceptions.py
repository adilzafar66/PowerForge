"""Domain exceptions for the project module."""


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
