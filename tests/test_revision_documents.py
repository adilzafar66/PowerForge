"""Unit tests for the shared revision-document helpers and the new request schema."""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from powerforge_api.exceptions import (
    ArchivedProject,
    CancelledProject,
    RevisionReadOnly,
)
from powerforge_api.schemas.projects import RevisionCreate, RevisionUpdate
from powerforge_api.services.revision_documents import (
    assert_documents_mutable,
    assert_project_modifiable,
)
from powerforge_project import ProjectStatus, RevisionStatus

API_SOURCE = Path(__file__).resolve().parents[1] / "services" / "api" / "src" / "powerforge_api"


def _project(status: ProjectStatus) -> SimpleNamespace:
    return SimpleNamespace(status=status)


def _revision(status: RevisionStatus) -> SimpleNamespace:
    return SimpleNamespace(status=status)


@pytest.mark.parametrize("project_status", list(ProjectStatus))
@pytest.mark.parametrize("revision_status", list(RevisionStatus))
def test_assert_documents_mutable_matrix(
    project_status: ProjectStatus, revision_status: RevisionStatus
) -> None:
    project = _project(project_status)
    revision = _revision(revision_status)

    if project_status is ProjectStatus.ARCHIVED:
        with pytest.raises(ArchivedProject):
            assert_documents_mutable(project, revision)
    elif project_status is ProjectStatus.CANCELLED:
        with pytest.raises(CancelledProject):
            assert_documents_mutable(project, revision)
    elif revision_status is RevisionStatus.SUPERSEDED:
        with pytest.raises(RevisionReadOnly):
            assert_documents_mutable(project, revision)
    else:
        assert_documents_mutable(project, revision)


def test_project_check_wins_over_revision_check() -> None:
    with pytest.raises(ArchivedProject):
        assert_documents_mutable(
            _project(ProjectStatus.ARCHIVED), _revision(RevisionStatus.SUPERSEDED)
        )


def test_paused_projects_remain_modifiable() -> None:
    assert_project_modifiable(_project(ProjectStatus.PAUSED))  # type: ignore[arg-type]
    assert_project_modifiable(_project(ProjectStatus.ACTIVE))  # type: ignore[arg-type]


def test_revision_create_distinguishes_omitted_from_explicit_null() -> None:
    omitted = RevisionCreate.model_validate({"identifier": "1"})
    explicit_null = RevisionCreate.model_validate(
        {"identifier": "1", "based_on_revision_id": None, "carry_forward_documents": None}
    )
    with_uuid = RevisionCreate.model_validate(
        {"identifier": "1", "based_on_revision_id": str(uuid.uuid4())}
    )

    assert "based_on_revision_id" not in omitted.model_fields_set
    assert "carry_forward_documents" not in omitted.model_fields_set
    assert "based_on_revision_id" in explicit_null.model_fields_set
    assert explicit_null.based_on_revision_id is None
    assert isinstance(with_uuid.based_on_revision_id, uuid.UUID)


def test_revision_create_rejects_a_malformed_base_id() -> None:
    with pytest.raises(ValidationError):
        RevisionCreate.model_validate({"identifier": "1", "based_on_revision_id": "not-a-uuid"})


def test_lineage_is_not_editable_through_update() -> None:
    with pytest.raises(ValidationError):
        RevisionUpdate.model_validate({"based_on_revision_id": str(uuid.uuid4())})
    with pytest.raises(ValidationError):
        RevisionUpdate.model_validate({"carry_forward_documents": True})


def test_helper_module_does_not_import_the_services_that_use_it() -> None:
    tree = ast.parse((API_SOURCE / "services" / "revision_documents.py").read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    forbidden = {
        "powerforge_api.services.revision_service",
        "powerforge_api.services.project_service",
    }
    assert imported.isdisjoint(forbidden)
