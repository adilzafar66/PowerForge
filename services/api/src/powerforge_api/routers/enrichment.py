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
)
from powerforge_api.services.enrichment_service import EnrichmentReadService
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.enrichment_profiles import (
    PREPARATION_PROFILE,
    PURPOSE,
    preparation_profile,
)
from powerforge_extraction.enrichment_service import start_preparation
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
    profile_key: Literal["source-preparation-v1"] = PREPARATION_PROFILE
    mode: Literal["ensure", "reextract"] = "ensure"


@router.get("/profiles")
def profiles(reader: Reader, settings: SettingsDep):
    try:
        profile = preparation_profile(settings)
    except (ValueError, KeyError):
        return dict(
            items=[
                dict(
                    key=PREPARATION_PROFILE,
                    enabled=False,
                    reason="LOCAL_ENGINE_IDENTITY_NOT_CONFIGURED",
                )
            ]
        )
    return dict(
        items=[
            dict(
                key=profile.key,
                enabled=True,
                profile_hash=profile.identity_hash,
                description=(
                    "Configured local OCR/native preparation; readiness does not verify "
                    "an engine invocation. Separate extraction run required."
                ),
                text_coverage="UNKNOWN",
            )
        ]
    )


@router.get("/inputs")
def inputs(reader: Reader, limit: Limit = 50, offset: Offset = 0):
    return reader.inputs(limit, offset)


@router.get("/runs")
def history(reader: Reader, limit: Limit = 50, offset: Offset = 0):
    return reader.history(limit, offset)


@router.get("/runs/{run_id}")
def detail(reader: Reader, run_id: UUID):
    with model_api_errors():
        return reader.detail(run_id)


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
        run = start_preparation(
            session,
            settings,
            reader.document_id,
            body.processing_run_id,
            body.pages,
            body.force_ocr_pages,
            reader.revision_document_id,
            body.mode,
        )
        run_id = run.id
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return reader.detail(run_id)


@router.post("/runs/{run_id}/retry", status_code=202)
def retry(
    reader: Reader, run_id: UUID, session: SessionDep, settings: SettingsDep, enqueue: EnqueueDep
):
    with action_errors(session):
        reader._run(run_id)
        ExtractionCoordinator(session, settings).retry(run_id, purpose=PURPOSE)
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return reader.detail(run_id)


@router.post("/runs/{run_id}/cancel")
def cancel(reader: Reader, run_id: UUID, session: SessionDep, settings: SettingsDep):
    with action_errors(session):
        reader._run(run_id)
        ExtractionCoordinator(session, settings).cancel(run_id, purpose=PURPOSE)
        session.commit()
        return reader.detail(run_id)
