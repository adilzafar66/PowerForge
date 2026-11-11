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
    EvidenceGroupList,
    ExtractionActionRequest,
    ExtractionRegisterStatus,
    ExtractionStartRequest,
    ExtractionSummary,
    ProfileInfo,
    ProfileList,
    RunDetail,
    RunFamily,
    RunList,
    TableList,
)
from powerforge_api.services.extraction_register import register_status, revision_read_only
from powerforge_api.services.extraction_service import ExtractionReadService
from powerforge_api.services.revision_writes import lock_writable_revision
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
PageNumber = Annotated[int, Query(ge=1)]
SearchText = Annotated[str, Query(max_length=200)]
EquipmentHint = Annotated[str, Query(min_length=1, max_length=100)]


@router.get("", response_model=ExtractionSummary)
def summary(reader: Service) -> ExtractionSummary:
    return reader.summary()


@router.get("/runs", response_model=RunList)
def history(
    reader: Service, limit: Limit = 50, offset: Offset = 0, family: RunFamily | None = None
) -> RunList:
    return reader.history(limit, offset, family)


@router.get("/groups", response_model=EvidenceGroupList)
def groups(
    reader: Service,
    engineering_run_id: UUID | None = None,
    tables_run_id: UUID | None = None,
    limit: Limit = 30,
    offset: Offset = 0,
    search: SearchText | None = None,
    page: PageNumber | None = None,
    equipment_hint: EquipmentHint | None = None,
    mapping_status: MappingStatus | None = None,
) -> EvidenceGroupList:
    with model_api_errors():
        return reader.groups(
            engineering_run_id,
            tables_run_id,
            limit,
            offset,
            search=search,
            page=page,
            equipment_hint=equipment_hint,
            mapping_status=mapping_status,
        )


@router.get("/runs/{run_id}", response_model=RunDetail)
def detail(
    project_id: UUID,
    reader: Service,
    run_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    family: RunFamily | None = None,
) -> RunDetail:
    with model_api_errors():
        if family:
            reader.family_run(run_id, family)
        result = reader.detail(run_id)
        if family and not revision_read_only(reader.session, project_id, reader.revision_id):
            result.can_cancel = result.run.status in {"PENDING", "RUNNING"}
            result.can_retry = (
                settings.extraction_enabled
                and settings.extraction_external_enabled
                and any(unit.retryable for unit in result.attempts)
            )
        return result


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
    family: RunFamily | None = None,
    ungrouped: bool = False,
    candidate_id: UUID | None = None,
    page: PageNumber | None = None,
    search: SearchText | None = None,
    equipment_hint: EquipmentHint | None = None,
) -> CandidateList:
    with model_api_errors():
        if family:
            reader.family_run(run_id, family)
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
            ungrouped=ungrouped,
            candidate_id=candidate_id,
            page=page,
            search=search,
            equipment_hint=equipment_hint,
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
    include_source_image: bool = False,
) -> EvidenceDetail:
    with model_api_errors():
        return reader.evidence(
            evidence_id,
            storage,
            settings.s3_signed_url_expires_seconds,
            include_source_image=include_source_image,
        )


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


@router.get("/profiles", response_model=ProfileList)
def profiles(reader: Service, settings: SettingsDep) -> ProfileList:
    from powerforge_extraction.enriched_profiles import PRODUCTION, SEMANTIC_PROFILES
    from powerforge_extraction.production_profiles import PRODUCTION_PROFILES
    from powerforge_extraction.table_profiles import TABLE_PRODUCTION_PROFILES

    enriched_profiles = (*PRODUCTION, *SEMANTIC_PROFILES)
    items = []
    for key in [
        FAKE_PROFILE,
        OPENAI_PROFILE,
        *PRODUCTION_PROFILES,
        *TABLE_PRODUCTION_PROFILES,
        *enriched_profiles,
    ]:
        profile = resolve_profile(key, settings)
        items.append(
            ProfileInfo(
                key=key,
                execution_kind=profile.execution_kind,
                provider=profile.provider,
                model=profile.model,
                production_extractor=profile.execution_kind
                in {"ENGINEERING_EXTRACTION", "TABLE_EXTRACTION"},
                requires_enrichment=key in enriched_profiles,
                enabled=settings.extraction_enabled
                and (profile.provider == "fake" or settings.extraction_external_enabled),
                description=(
                    "Opt-in table-only AI candidates; ordinary prose requires a separate run; "
                    "accuracy is unmeasured"
                )
                if profile.execution_kind == "TABLE_EXTRACTION"
                else "Opt-in engineering AI candidates; extraction accuracy is unmeasured"
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
            enrichment_bindings=body.enrichment_bindings,
        )
        run_id = run.id
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return reader.detail(run_id)


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
    family: RunFamily | None = None,
) -> RunDetail:
    with action_errors(session):
        if family:
            reader = lock_viewer_action(reader, project_id)
            reader.family_run(run_id, family)
        else:
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
    family: RunFamily | None = None,
) -> RunDetail:
    with action_errors(session):
        if family:
            reader = lock_viewer_action(reader, project_id)
            reader.family_run(run_id, family)
        else:
            reader._run(run_id)
        ExtractionCoordinator(session, settings).cancel(run_id)
        session.commit()
        return reader.detail(run_id)
