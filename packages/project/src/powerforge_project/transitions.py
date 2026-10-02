from powerforge_project.enums import ProjectStatus

# Allowed (from, to) pairs for project lifecycle actions.
_ALLOWED_TRANSITIONS: frozenset[tuple[ProjectStatus, ProjectStatus]] = frozenset(
    {
        (ProjectStatus.ACTIVE, ProjectStatus.PAUSED),
        (ProjectStatus.PAUSED, ProjectStatus.ACTIVE),
        (ProjectStatus.ACTIVE, ProjectStatus.CANCELLED),
        (ProjectStatus.PAUSED, ProjectStatus.CANCELLED),
        (ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED),
        (ProjectStatus.PAUSED, ProjectStatus.ARCHIVED),
        (ProjectStatus.CANCELLED, ProjectStatus.ARCHIVED),
        (ProjectStatus.ARCHIVED, ProjectStatus.ARCHIVED),  # idempotent archive
        (ProjectStatus.ARCHIVED, ProjectStatus.ACTIVE),
        (ProjectStatus.ARCHIVED, ProjectStatus.PAUSED),
        (ProjectStatus.ARCHIVED, ProjectStatus.CANCELLED),
    }
)


def can_transition(from_status: ProjectStatus, to_status: ProjectStatus) -> bool:
    """Return True if moving from_status → to_status is allowed."""
    return (from_status, to_status) in _ALLOWED_TRANSITIONS


def assert_transition(from_status: ProjectStatus, to_status: ProjectStatus) -> None:
    """Raise ValueError if the transition is not allowed."""
    if not can_transition(from_status, to_status):
        raise ValueError(f"Invalid project status transition: {from_status} → {to_status}")
