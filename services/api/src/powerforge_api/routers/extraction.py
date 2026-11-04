"""Phase 6A exposes read-only document extraction resources."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from powerforge_api.db import get_session
from powerforge_api.exceptions import ProjectError
from powerforge_api.routers.errors import http_for, model_api_errors
from powerforge_api.schemas.extraction import (
    CandidateList,
    EvidenceDetail,
    ExtractionActionRequest,
    ExtractionStartRequest,
    ExtractionSummary,
    ProfileInfo,
    ProfileList,
    RunDetail,
    RunList,
    TableList,
)
from powerforge_api.services.extraction_service import ExtractionReadService
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.enqueue import CeleryExtractionEnqueue, get_extraction_enqueue
from powerforge_extraction.enums import CandidateKind, MappingStatus
from powerforge_extraction.errors import ExtractionError
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.profiles import FAKE_PROFILE, OPENAI_PROFILE, resolve_profile
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


@contextmanager
def action_errors(session: Session) -> Iterator[None]:
    try:
        with model_api_errors():
            yield
    except ExtractionError as exc:
        session.rollback()
        raise HTTPException(
            status_code=exc.status_code, detail={"detail": str(exc), "code": exc.code}
        ) from None
    except Exception:
        session.rollback()
        raise


def dispatch_committed(
    session: Session, settings: Settings, enqueue: CeleryExtractionEnqueue
) -> None:
    try:
        ExtractionCoordinator(session, settings).dispatch(enqueue)
        session.commit()
    except Exception as exc:
        session.rollback()
        logging.getLogger(__name__).warning(
            "extraction delivery awaits recovery", extra={"error_class": type(exc).__name__}
        )


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EnqueueDep = Annotated[CeleryExtractionEnqueue, Depends(get_extraction_enqueue)]


@router.get("/profiles", response_model=ProfileList)
def profiles(reader: Service, settings: SettingsDep) -> ProfileList:
    from powerforge_extraction.production_profiles import PRODUCTION_PROFILES

    items = []
    for key in [FAKE_PROFILE, OPENAI_PROFILE, *PRODUCTION_PROFILES]:
        profile = resolve_profile(key, settings)
        items.append(
            ProfileInfo(
                key=key,
                execution_kind=profile.execution_kind,
                provider=profile.provider,
                model=profile.model,
                production_extractor=profile.execution_kind == "ENGINEERING_EXTRACTION",
                enabled=settings.extraction_enabled
                and (profile.provider == "fake" or settings.extraction_external_enabled),
                description="Opt-in engineering AI candidates; extraction accuracy is unmeasured"
                if profile.execution_kind == "ENGINEERING_EXTRACTION"
                else "Synthetic test execution; no engineering interpretation"
                if profile.provider == "fake"
                else ("Opt-in provider/source probe; no engineering extraction"),
            )
        )
    return ProfileList(items=items)


@router.post("/runs", response_model=RunDetail, status_code=202)
def start(
    reader: Service,
    body: ExtractionStartRequest,
    session: SessionDep,
    settings: SettingsDep,
    enqueue: EnqueueDep,
) -> RunDetail:
    with action_errors(session):
        run = ExtractionCoordinator(session, settings).start(
            reader.document_id,
            revision_document_id=reader.revision_document_id,
            profile_key=body.profile_key,
            pages=body.pages,
            mode=body.mode,
        )
        run_id = run.id
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return reader.detail(run_id)


@router.post("/runs/{run_id}/retry", response_model=RunDetail, status_code=202)
def retry(
    reader: Service,
    run_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    enqueue: EnqueueDep,
    body: ExtractionActionRequest | None = None,
) -> RunDetail:
    with action_errors(session):
        reader._run(run_id)
        ExtractionCoordinator(session, settings).retry(run_id)
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return reader.detail(run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunDetail)
def cancel(
    reader: Service,
    run_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    body: ExtractionActionRequest | None = None,
) -> RunDetail:
    with action_errors(session):
        reader._run(run_id)
        ExtractionCoordinator(session, settings).cancel(run_id)
        session.commit()
        return reader.detail(run_id)
