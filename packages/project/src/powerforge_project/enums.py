from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle status for a project."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class RevisionStatus(StrEnum):
    """Lifecycle status for a project revision."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
