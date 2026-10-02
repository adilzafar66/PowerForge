from powerforge_project import ProjectStatus, RevisionStatus, can_transition


def test_project_status_values() -> None:
    assert {status.value for status in ProjectStatus} == {
        "ACTIVE",
        "PAUSED",
        "CANCELLED",
        "ARCHIVED",
    }


def test_revision_status_values() -> None:
    assert {status.value for status in RevisionStatus} == {
        "DRAFT",
        "ACTIVE",
        "SUPERSEDED",
    }


def test_allowed_project_transitions() -> None:
    assert can_transition(ProjectStatus.ACTIVE, ProjectStatus.PAUSED)
    assert can_transition(ProjectStatus.PAUSED, ProjectStatus.ACTIVE)
    assert can_transition(ProjectStatus.ACTIVE, ProjectStatus.CANCELLED)
    assert can_transition(ProjectStatus.PAUSED, ProjectStatus.CANCELLED)
    assert can_transition(ProjectStatus.CANCELLED, ProjectStatus.ARCHIVED)
    assert can_transition(ProjectStatus.ARCHIVED, ProjectStatus.ACTIVE)
    assert can_transition(ProjectStatus.ARCHIVED, ProjectStatus.PAUSED)
    assert can_transition(ProjectStatus.ARCHIVED, ProjectStatus.CANCELLED)
    assert can_transition(ProjectStatus.ARCHIVED, ProjectStatus.ARCHIVED)


def test_disallowed_project_transitions() -> None:
    assert not can_transition(ProjectStatus.CANCELLED, ProjectStatus.ACTIVE)
    assert not can_transition(ProjectStatus.CANCELLED, ProjectStatus.PAUSED)
    assert not can_transition(ProjectStatus.ACTIVE, ProjectStatus.ACTIVE)
