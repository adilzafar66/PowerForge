"""Phase 6A exposes read-only document extraction resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from powerforge_api.db import get_session
from powerforge_api.exceptions import ProjectError
from powerforge_api.routers.errors import http_for, model_api_errors
from powerforge_api.schemas.extraction import (
    CandidateList,
    EvidenceDetail,
    ExtractionSummary,
    RunDetail,
    RunList,
    TableList,
)
from powerforge_api.services.extraction_service import ExtractionReadService
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.enums import CandidateKind, MappingStatus
from powerforge_shared.config import Settings, get_settings

router = APIRouter(
    prefix="/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/extraction",
    tags=["extraction"],
)


def service(
    project_id: UUID,
    revision_id: UUID,
    revision_document_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> ExtractionReadService:
    try:
        return ExtractionReadService(session, project_id, revision_id, revision_document_id)
    except ProjectError as exc:
        raise http_for(exc) from exc


Service = Annotated[ExtractionReadService, Depends(service)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


@router.get("", response_model=ExtractionSummary)
def summary(reader: Service) -> ExtractionSummary:
    return reader.summary()


@router.get("/runs", response_model=RunList)
def history(reader: Service, limit: Limit = 50, offset: Offset = 0) -> RunList:
    return reader.history(limit, offset)


@router.get("/runs/{run_id}", response_model=RunDetail)
def detail(reader: Service, run_id: UUID) -> RunDetail:
    with model_api_errors():
        return reader.detail(run_id)


@router.get("/runs/{run_id}/candidates", response_model=CandidateList)
def candidates(
    reader: Service,
    run_id: UUID,
    limit: Limit = 50,
    offset: Offset = 0,
    kind: CandidateKind | None = None,
    mapping_status: MappingStatus | None = None,
    source_group_id: UUID | None = None,
    equipment_type_key: str | None = None,
    attribute_key: str | None = None,
    supported_only: bool = True,
) -> CandidateList:
    with model_api_errors():
        return reader.candidates(
            run_id,
            limit,
            offset,
            kind=kind,
            mapping_status=mapping_status,
            source_group_id=source_group_id,
            equipment_type_key=equipment_type_key,
            attribute_key=attribute_key,
            supported_only=supported_only,
        )


@router.get("/runs/{run_id}/tables", response_model=TableList)
def tables(reader: Service, run_id: UUID, limit: Limit = 50, offset: Offset = 0) -> TableList:
    with model_api_errors():
        return reader.tables(run_id, limit, offset)


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetail)
def evidence(
    reader: Service,
    evidence_id: UUID,
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EvidenceDetail:
    with model_api_errors():
        return reader.evidence(evidence_id, storage, settings.s3_signed_url_expires_seconds)
