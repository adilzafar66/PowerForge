"""REST API for projects and project revisions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from powerforge_api.db import get_session
from powerforge_api.exceptions import ProjectError
from powerforge_api.models import Project, ProjectRevision
from powerforge_api.routers.errors import http_for as _http_for
from powerforge_api.schemas.projects import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
    RevisionCreate,
    RevisionListResponse,
    RevisionResponse,
    RevisionUpdate,
)
from powerforge_api.services.project_service import ProjectService
from powerforge_api.services.revision_service import RevisionService
from powerforge_project import ProjectStatus

router = APIRouter(tags=["projects"])

SessionDep = Annotated[Session, Depends(get_session)]
SearchQuery = Annotated[
    str | None,
    Query(description="Match project number, name, client, or address"),
]
StatusQuery = Annotated[
    ProjectStatus | None,
    Query(alias="status", description="Filter by project status"),
]


def _project_response(
    project: Project,
    active_revision_identifier: str | None = None,
) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        project_number=project.project_number,
        project_name=project.project_name,
        project_address=project.project_address,
        project_scope=project.project_scope,
        client_name=project.client_name,
        description=project.description,
        engineer_names=list(project.engineer_names or []),
        status=project.status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        status_before_archive=project.status_before_archive,
        created_by=project.created_by,
        active_revision_identifier=active_revision_identifier,
    )


def _revision_response(
    revision: ProjectRevision,
    base_identifier: str | None = None,
    inherited_document_count: int | None = None,
) -> RevisionResponse:
    response = RevisionResponse.model_validate(revision)
    response.based_on_identifier = base_identifier
    response.inherited_document_count = inherited_document_count
    return response


@router.post(
    "/api/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
def create_project(body: ProjectCreate, session: SessionDep) -> ProjectResponse:
    try:
        project = ProjectService(session).create_project(body)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    return _project_response(project)


@router.get(
    "/api/projects",
    response_model=ProjectListResponse,
    summary="List projects",
)
def list_projects(
    session: SessionDep,
    search: SearchQuery = None,
    status_filter: StatusQuery = None,
) -> ProjectListResponse:
    rows = ProjectService(session).list_projects(search=search, status=status_filter)
    return ProjectListResponse(
        items=[_project_response(project, active) for project, active in rows]
    )


@router.get(
    "/api/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Get a project",
)
def get_project(project_id: UUID, session: SessionDep) -> ProjectResponse:
    service = ProjectService(session)
    try:
        project = service.get_project(project_id)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    return _project_response(project, service.active_revision_identifier(project_id))


@router.patch(
    "/api/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Update project metadata",
)
def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    session: SessionDep,
) -> ProjectResponse:
    service = ProjectService(session)
    try:
        project = service.update_project(project_id, body)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    return _project_response(project, service.active_revision_identifier(project_id))


def _lifecycle(
    project_id: UUID,
    session: Session,
    action: str,
) -> ProjectResponse:
    service = ProjectService(session)
    try:
        if action == "pause":
            project = service.pause_project(project_id)
        elif action == "resume":
            project = service.resume_project(project_id)
        elif action == "cancel":
            project = service.cancel_project(project_id)
        elif action == "archive":
            project = service.archive_project(project_id)
        elif action == "unarchive":
            project = service.unarchive_project(project_id)
        else:
            raise ValueError(action)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    return _project_response(project, service.active_revision_identifier(project_id))


@router.post("/api/projects/{project_id}/pause", response_model=ProjectResponse)
def pause_project(project_id: UUID, session: SessionDep) -> ProjectResponse:
    return _lifecycle(project_id, session, "pause")


@router.post("/api/projects/{project_id}/resume", response_model=ProjectResponse)
def resume_project(project_id: UUID, session: SessionDep) -> ProjectResponse:
    return _lifecycle(project_id, session, "resume")


@router.post("/api/projects/{project_id}/cancel", response_model=ProjectResponse)
def cancel_project(project_id: UUID, session: SessionDep) -> ProjectResponse:
    return _lifecycle(project_id, session, "cancel")


@router.post("/api/projects/{project_id}/archive", response_model=ProjectResponse)
def archive_project(project_id: UUID, session: SessionDep) -> ProjectResponse:
    return _lifecycle(project_id, session, "archive")


@router.post("/api/projects/{project_id}/unarchive", response_model=ProjectResponse)
def unarchive_project(project_id: UUID, session: SessionDep) -> ProjectResponse:
    return _lifecycle(project_id, session, "unarchive")


@router.post(
    "/api/projects/{project_id}/revisions",
    response_model=RevisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a revision (always DRAFT; optional activate)",
)
def create_revision(
    project_id: UUID,
    body: RevisionCreate,
    session: SessionDep,
) -> RevisionResponse:
    service = RevisionService(session)
    try:
        result = service.create_revision(project_id, body)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    return _revision_response(
        result.revision,
        service.base_identifier(result.revision),
        result.inherited_document_count,
    )


@router.get(
    "/api/projects/{project_id}/revisions",
    response_model=RevisionListResponse,
    summary="List revisions for a project",
)
def list_revisions(project_id: UUID, session: SessionDep) -> RevisionListResponse:
    try:
        revisions = RevisionService(session).list_revisions(project_id)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    identifiers = {r.id: r.identifier for r in revisions}
    return RevisionListResponse(
        items=[_revision_response(r, identifiers.get(r.based_on_revision_id)) for r in revisions]
    )


@router.get(
    "/api/projects/{project_id}/revisions/{revision_id}",
    response_model=RevisionResponse,
    summary="Get a revision",
)
def get_revision(
    project_id: UUID,
    revision_id: UUID,
    session: SessionDep,
) -> RevisionResponse:
    service = RevisionService(session)
    try:
        revision = service.get_revision(project_id, revision_id)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    return _revision_response(revision, service.base_identifier(revision))


@router.patch(
    "/api/projects/{project_id}/revisions/{revision_id}",
    response_model=RevisionResponse,
    summary="Update revision description or identifier",
)
def update_revision(
    project_id: UUID,
    revision_id: UUID,
    body: RevisionUpdate,
    session: SessionDep,
) -> RevisionResponse:
    service = RevisionService(session)
    try:
        revision = service.update_revision(project_id, revision_id, body)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    return _revision_response(revision, service.base_identifier(revision))


@router.post(
    "/api/projects/{project_id}/revisions/{revision_id}/activate",
    response_model=RevisionResponse,
    summary="Activate a revision (atomic; supersedes previous ACTIVE)",
)
def activate_revision(
    project_id: UUID,
    revision_id: UUID,
    session: SessionDep,
) -> RevisionResponse:
    service = RevisionService(session)
    try:
        revision = service.activate_revision(project_id, revision_id)
    except ProjectError as exc:
        raise _http_for(exc) from exc
    return _revision_response(revision, service.base_identifier(revision))
