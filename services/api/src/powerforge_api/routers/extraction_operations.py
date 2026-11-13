"""Phase 6F review, consent and recovery at the revision boundary."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator
from sqlalchemy import select

from powerforge_api.routers.errors import model_api_errors
from powerforge_api.routers.extraction import (
    EnqueueDep,
    SessionDep,
    SettingsDep,
    action_errors,
    dispatch_committed,
)
from powerforge_api.services.extraction_operations import operation_detail
from powerforge_api.services.extraction_register import revision_read_only
from powerforge_api.services.revision_writes import lock_writable_revision
from powerforge_document_processing.models import RevisionDocument
from powerforge_extraction.operation_models import ExtractionOperation, OperationItem
from powerforge_extraction.operation_plan import (
    MAX_DOCUMENTS,
    Contract,
    OperationSelection,
    preview_operation,
    source_options,
)
from powerforge_extraction.operations import (
    admit_operation,
    cancel_operation,
    get_operation,
    retry_operation_item,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/revisions/{revision_id}/extraction/operations",
    tags=["extraction operations"],
)


class SourcesRequest(Contract):
    revision_document_ids: list[UUID] = Field(min_length=1, max_length=MAX_DOCUMENTS)

    @field_validator("revision_document_ids")
    @classmethod
    def distinct(cls, ids):
        if len(set(ids)) != len(ids):
            raise ValueError("Select each document once")
        return ids


class StartRequest(Contract):
    selection: OperationSelection
    review_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_key: UUID
    external_processing_consent: Literal[True]

    @field_validator("external_processing_consent", mode="before")
    @classmethod
    def require_explicit_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit consent for OpenAI processing is required")
        return value


class RetryRequest(Contract):
    revision_document_id: UUID
    step: Literal["layout", "resume"] | None = None
    stage: Literal["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"] | None = None
    page_id: UUID | None = None
    expected_attempt: StrictInt | None = Field(default=None, ge=1)
    expected_attempts: StrictInt = Field(default=0, ge=0)
    acknowledge_unknown_outcome: StrictBool = False

    @model_validator(mode="after")
    def target(self):
        if self.stage is not None:
            if self.step is not None or self.page_id is None or self.expected_attempt is None:
                raise ValueError("Select the page and expected attempt for this AI stage")
        elif self.step is None or self.page_id is not None or self.expected_attempt is not None:
            raise ValueError("Select either a preparation action or a page stage")
        return self


@router.post("/sources")
def sources(
    project_id: UUID,
    revision_id: UUID,
    body: SourcesRequest,
    session: SessionDep,
    settings: SettingsDep,
):
    with model_api_errors():
        readonly = revision_read_only(session, project_id, revision_id)
        return {
            **source_options(
                session, settings, project_id, revision_id, body.revision_document_ids
            ),
            "read_only": readonly,
        }


@router.post("/preview")
def preview(
    project_id: UUID,
    revision_id: UUID,
    body: OperationSelection,
    session: SessionDep,
    settings: SettingsDep,
):
    with model_api_errors():
        readonly = revision_read_only(session, project_id, revision_id)
        result = preview_operation(session, settings, project_id, revision_id, body)
        if readonly:
            result.errors.append("This revision is read-only.")
        return result.response()


@router.post("", status_code=202)
def start(
    project_id: UUID,
    revision_id: UUID,
    body: StartRequest,
    session: SessionDep,
    settings: SettingsDep,
):
    with action_errors(session):
        lock_writable_revision(session, project_id, revision_id)
        operation = admit_operation(
            session,
            settings,
            project_id,
            revision_id,
            body.request_key,
            body.review_hash,
            body.selection,
        )
        operation_id = operation.id
        session.commit()
        return {"id": operation_id}


@router.get("")
def recent(project_id: UUID, revision_id: UUID, revision_document_id: UUID, session: SessionDep):
    with model_api_errors():
        revision_read_only(session, project_id, revision_id)
        rows = session.execute(
            select(ExtractionOperation.id, ExtractionOperation.created_at)
            .join(OperationItem, OperationItem.operation_id == ExtractionOperation.id)
            .join(RevisionDocument, RevisionDocument.id == OperationItem.revision_document_id)
            .where(
                ExtractionOperation.project_id == project_id,
                ExtractionOperation.revision_id == revision_id,
                RevisionDocument.id == revision_document_id,
                RevisionDocument.project_id == project_id,
                RevisionDocument.revision_id == revision_id,
                RevisionDocument.status == "INCLUDED",
                RevisionDocument.document_id == OperationItem.document_id,
            )
            .order_by(ExtractionOperation.created_at.desc(), ExtractionOperation.id.desc())
            .limit(10)
        )
        return {"items": [{"id": row.id, "created_at": row.created_at} for row in rows]}


@router.get("/{operation_id}")
def detail(
    project_id: UUID,
    revision_id: UUID,
    operation_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
):
    with action_errors(session):
        operation = get_operation(session, project_id, revision_id, operation_id)
        readonly = revision_read_only(session, project_id, revision_id)
        return operation_detail(session, settings, operation, can_write=not readonly)


@router.post("/{operation_id}/cancel")
def cancel(
    project_id: UUID,
    revision_id: UUID,
    operation_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
):
    with action_errors(session):
        lock_writable_revision(session, project_id, revision_id)
        operation = get_operation(session, project_id, revision_id, operation_id, lock=True)
        if operation_detail(session, settings, operation, can_write=True)["can_cancel"]:
            cancel_operation(session, settings, operation)
        session.commit()
        return operation_detail(session, settings, operation, can_write=True)


@router.post("/{operation_id}/retry", status_code=202)
def retry(
    project_id: UUID,
    revision_id: UUID,
    operation_id: UUID,
    body: RetryRequest,
    session: SessionDep,
    settings: SettingsDep,
    enqueue: EnqueueDep,
):
    with action_errors(session):
        lock_writable_revision(session, project_id, revision_id)
        operation = get_operation(session, project_id, revision_id, operation_id, lock=True)
        retry_operation_item(
            session,
            settings,
            operation,
            body.revision_document_id,
            body.step or "extraction",
            body.expected_attempts,
            body.acknowledge_unknown_outcome,
            page_id=body.page_id,
            stage=body.stage,
            expected_attempt=body.expected_attempt,
        )
        session.commit()
        dispatch_committed(session, settings, enqueue)
        return operation_detail(session, settings, operation, can_write=True)
