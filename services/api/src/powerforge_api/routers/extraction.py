"""Revision-scoped extraction run resources."""

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
    ExtractionActionRequest,
    ExtractionRegisterStatus,
    ExtractionSummary,
    RunDetail,
    RunList,
)
from powerforge_api.services.extraction_register import register_status, revision_read_only
from powerforge_api.services.extraction_service import ExtractionReadService
from powerforge_api.services.revision_writes import lock_writable_revision
from powerforge_extraction.enqueue import CeleryExtractionEnqueue, get_extraction_enqueue
from powerforge_extraction.errors import ExtractionError
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.phase6r_profile import provider_available
from powerforge_shared.config import Settings, get_settings

router = APIRouter(
    prefix="/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/extraction",
    tags=["extraction"],
)


register_router = APIRouter(
    prefix="/api/projects/{project_id}/revisions/{revision_id}/extraction",
    tags=["extraction"],
)


@register_router.get("/status", response_model=ExtractionRegisterStatus)
def revision_status(
    project_id: UUID,
    revision_id: UUID,
    revision_document_ids: Annotated[list[UUID], Query(min_length=1, max_length=100)],
    session: Annotated[Session, Depends(get_session)],
) -> ExtractionRegisterStatus:
    with model_api_errors():
        return ExtractionRegisterStatus(
            items=register_status(session, project_id, revision_id, revision_document_ids)
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
def detail(
    project_id: UUID,
    reader: Service,
    run_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunDetail:
    with model_api_errors():
        result = reader.detail(run_id)
        if not revision_read_only(reader.session, project_id, reader.revision_id):
            result.can_cancel = result.run.status in {"PENDING", "RUNNING"}
            result.can_retry = provider_available(settings, result.run.provider) and any(
                unit.retryable for unit in result.attempts
            )
        return result


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
        ExtractionCoordinator(session, settings).dispatch(enqueue, purpose=None)
        session.commit()
    except Exception as exc:
        session.rollback()
        logging.getLogger(__name__).warning(
            "extraction delivery awaits recovery", extra={"error_class": type(exc).__name__}
        )


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EnqueueDep = Annotated[CeleryExtractionEnqueue, Depends(get_extraction_enqueue)]


@router.get("/runs/{run_id}/sources")
def bound_sources(reader: Service, run_id: UUID):
    with model_api_errors():
        reader._run(run_id)
        from sqlalchemy import select

        from powerforge_extraction.enriched_sources import selected_snapshot
        from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding

        bindings = reader.session.scalars(
            select(RunSourceEnrichmentBinding).where(
                RunSourceEnrichmentBinding.run_id == run_id,
                RunSourceEnrichmentBinding.spatial_result_id.is_not(None),
            )
        )
        items = []
        for binding in bindings:
            source = selected_snapshot(
                reader.session, binding.prepared_result_id, binding.spatial_result_id
            )
            items.append(
                dict(
                    page_number=source.layout.owner.page_number,
                    prepared_result_id=binding.prepared_result_id,
                    spatial_result_id=binding.spatial_result_id,
                    prepared_manifest_hash=binding.manifest_hash,
                    spatial_manifest_hash=binding.spatial_manifest_hash,
                    preparation_producer_run_id=source.prepared.manifest.producer_run_id,
                    layout_producer_run_id=source.layout.producer_run_id,
                    text_coverage=source.prepared.manifest.text_coverage,
                    printed_text_independently_verified=False,
                )
            )
        return dict(items=sorted(items, key=lambda x: x["page_number"]))


def lock_viewer_action(reader: ExtractionReadService, project_id: UUID):
    lock_writable_revision(reader.session, project_id, reader.revision_id)
    return type(reader)(reader.session, project_id, reader.revision_id, reader.revision_document_id)


@router.post("/runs/{run_id}/retry", response_model=RunDetail, status_code=202)
def retry(
    project_id: UUID,
    reader: Service,
    run_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    enqueue: EnqueueDep,
    body: ExtractionActionRequest | None = None,
) -> RunDetail:
    with action_errors(session):
        reader = lock_viewer_action(reader, project_id)
        reader._run(run_id)
        ExtractionCoordinator(session, settings).retry(
            run_id, acknowledge_unknown_outcome=bool(body and body.acknowledge_unknown_outcome)
        )
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return reader.detail(run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunDetail)
def cancel(
    project_id: UUID,
    reader: Service,
    run_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    body: ExtractionActionRequest | None = None,
) -> RunDetail:
    with action_errors(session):
        reader = lock_viewer_action(reader, project_id)
        reader._run(run_id)
        ExtractionCoordinator(session, settings).cancel(run_id)
        session.commit()
        return reader.detail(run_id)
