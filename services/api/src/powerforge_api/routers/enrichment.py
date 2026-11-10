"""Explicit enrichment before enhanced extraction; no external-provider admission."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from powerforge_api.exceptions import ProjectError
from powerforge_api.routers.errors import http_for, model_api_errors
from powerforge_api.routers.extraction import (
    EnqueueDep,
    Limit,
    Offset,
    SessionDep,
    SettingsDep,
    action_errors,
    dispatch_committed,
    lock_viewer_action,
)
from powerforge_api.services.enrichment_service import EnrichmentReadService
from powerforge_api.services.extraction_register import revision_read_only
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.enrichment_profiles import (
    PREPARATION_PROFILE,
    PURPOSE,
    preparation_profile,
)
from powerforge_extraction.enrichment_service import start_preparation
from powerforge_extraction.errors import ExtractionError
from powerforge_extraction.layout_profiles import LAYOUT_PROFILE, layout_profile
from powerforge_extraction.layout_service import start_layout
from powerforge_extraction.orchestration import ExtractionCoordinator

router = APIRouter(
    prefix="/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/source-enrichment",
    tags=["source-enrichment"],
)


def service(project_id: UUID, revision_id: UUID, revision_document_id: UUID, session: SessionDep):
    try:
        return EnrichmentReadService(session, project_id, revision_id, revision_document_id)
    except ProjectError as exc:
        raise http_for(exc) from exc


Reader = Annotated[EnrichmentReadService, Depends(service)]


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    processing_run_id: UUID
    pages: list[StrictInt] = Field(min_length=1, max_length=50)
    force_ocr_pages: list[StrictInt] = Field(default_factory=list, max_length=50)
    profile_key: Literal["source-preparation-v1", "source-layout-v1"] = PREPARATION_PROFILE
    mode: Literal["ensure", "reextract"] = "ensure"
    prepared_result_ids: list[UUID] = Field(default_factory=list, max_length=50)


@router.get("/profiles")
def profiles(reader: Reader, settings: SettingsDep):
    items = []
    for key, resolver in (
        (PREPARATION_PROFILE, preparation_profile),
        (LAYOUT_PROFILE, layout_profile),
    ):
        try:
            profile = resolver(settings)
        except (ValueError, KeyError):
            items.append(
                dict(key=key, enabled=False, reason="LOCAL_ENGINE_IDENTITY_NOT_CONFIGURED")
            )
        else:
            items.append(
                dict(
                    key=key,
                    enabled=True,
                    profile_hash=profile.identity_hash,
                    stages=list(profile.stages) if key == LAYOUT_PROFILE else [profile.stage],
                    text_coverage="UNKNOWN",
                    description=(
                        "Configured local source preparation/layout; readiness does not verify "
                        "recognition. Separate extraction run required."
                    ),
                )
            )
    return dict(items=items)


@router.get("/inputs")
def inputs(reader: Reader, limit: Limit = 50, offset: Offset = 0):
    return reader.inputs(limit, offset)


@router.get("/runs")
def history(reader: Reader, limit: Limit = 50, offset: Offset = 0):
    return reader.history(limit, offset)


@router.get("/runs/{run_id}")
def detail(
    project_id: UUID, reader: Reader, run_id: UUID, settings: SettingsDep, viewer: bool = False
):
    with model_api_errors():
        writable = viewer and not revision_read_only(reader.session, project_id, reader.revision_id)
        return reader.detail(
            run_id, viewer=writable, enrichment_enabled=settings.enrichment_enabled
        )


@router.get("/runs/{run_id}/results/{result_id}")
def result(reader: Reader, run_id: UUID, result_id: UUID):
    with model_api_errors():
        row, manifest = reader.result(run_id, result_id)
        return dict(
            id=row.id,
            manifest_hash=row.manifest_hash,
            manifest=manifest.model_dump(mode="json"),
            usage=row.usage,
        )


@router.get("/runs/{run_id}/artifacts/{artifact_id}")
def artifact(
    reader: Reader,
    run_id: UUID,
    artifact_id: UUID,
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    settings: SettingsDep,
):
    with model_api_errors():
        return reader.artifact(run_id, artifact_id, storage, settings.s3_signed_url_expires_seconds)


@router.post("/runs", status_code=202)
def start(
    reader: Reader,
    body: StartRequest,
    session: SessionDep,
    settings: SettingsDep,
    enqueue: EnqueueDep,
):
    with action_errors(session):
        if body.profile_key == PREPARATION_PROFILE and body.prepared_result_ids:
            raise ExtractionError("Preparation-only requests cannot bind reused layout inputs")
        starter = start_layout if body.profile_key == LAYOUT_PROFILE else start_preparation
        extra = (
            {"prepared_result_ids": body.prepared_result_ids}
            if body.profile_key == LAYOUT_PROFILE
            else {}
        )
        run = starter(
            session,
            settings,
            reader.document_id,
            body.processing_run_id,
            body.pages,
            body.force_ocr_pages,
            reader.revision_document_id,
            body.mode,
            **extra,
        )
        run_id = run.id
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return reader.detail(run_id)


@router.post("/runs/{run_id}/retry", status_code=202)
def retry(
    project_id: UUID,
    reader: Reader,
    run_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    enqueue: EnqueueDep,
    viewer: bool = False,
):
    with action_errors(session):
        if viewer:
            reader = lock_viewer_action(reader, project_id)
        reader._run(run_id)
        ExtractionCoordinator(session, settings).retry(run_id, purpose=PURPOSE)
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return reader.detail(run_id)


@router.post("/runs/{run_id}/cancel")
def cancel(
    project_id: UUID,
    reader: Reader,
    run_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    viewer: bool = False,
):
    with action_errors(session):
        if viewer:
            reader = lock_viewer_action(reader, project_id)
        reader._run(run_id)
        ExtractionCoordinator(session, settings).cancel(run_id, purpose=PURPOSE)
        session.commit()
        return reader.detail(run_id)


@router.get("/runs/{run_id}/spatial-results/{result_id}")
def spatial_result(reader: Reader, run_id: UUID, result_id: UUID):
    with model_api_errors():
        row, layout = reader.spatial_result(run_id, result_id)
        return dict(
            id=row.id,
            prepared_result_id=row.prepared_result_id,
            manifest_hash=row.manifest_hash,
            manifest=layout.model_dump(mode="json"),
            usage=row.usage,
        )


@router.get("/runs/{run_id}/spatial-results/{result_id}/artifact")
def spatial_artifact(
    reader: Reader,
    run_id: UUID,
    result_id: UUID,
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    settings: SettingsDep,
):
    with model_api_errors():
        return reader.spatial_artifact(
            run_id, result_id, storage, settings.s3_signed_url_expires_seconds
        )
