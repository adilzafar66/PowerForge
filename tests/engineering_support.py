"""Focused service-test setup; tests use the configured disposable integration database."""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from powerforge_api.db import get_session_factory
from powerforge_api.services.engineering_model_service import EngineeringModelService
from powerforge_persistence import Project, ProjectRevision


def seed_revision(session: Session) -> tuple[UUID, UUID]:
    project = Project(project_number=f"EM-{uuid4().hex}", project_name="Engineering test")
    session.add(project)
    session.flush()
    revision = ProjectRevision(project_id=project.id, identifier="0")
    session.add(revision)
    session.commit()
    return project.id, revision.id


@dataclass
class EngineeringContext:
    session: Session
    service: EngineeringModelService
    project_id: UUID
    revision_id: UUID

    @property
    def ids(self) -> tuple[UUID, UUID]:
        return self.project_id, self.revision_id


@pytest.fixture
def engineering_context(require_db: None) -> Iterator[EngineeringContext]:
    with get_session_factory()() as session:
        project_id, revision_id = seed_revision(session)
        yield EngineeringContext(session, EngineeringModelService(session), project_id, revision_id)
