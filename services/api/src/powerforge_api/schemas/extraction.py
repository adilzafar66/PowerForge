"""Explicit read allowlists; storage keys and internal execution metadata stay private."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from powerforge_ai.extraction import ValidationIssue
from powerforge_extraction.enums import (
    ExtractionRunStatus,
    WorkUnitStatus,
)


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RunResponse(ReadModel):
    id: UUID
    document_id: UUID
    processing_run_id: UUID
    status: ExtractionRunStatus
    extractor_version: str
    schema_version: str
    registry_version: str
    profile_version: str
    profile_hash: str
    input_identity_hash: str
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    selected_pages: list[int]
    stages: list[str]
    input_artifact_ids: list[UUID]
    context_fingerprint: str | None
    reextracts_run_id: UUID | None
    pages_processed: int
    units_total: int
    units_completed: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    # Error details are not trusted as safe provider-independent API text.


class UnitResponse(ReadModel):
    id: UUID
    unit_key: str
    stage: str
    attempt_number: int
    retry_of_work_unit_id: UUID | None
    required: bool
    status: WorkUnitStatus
    page_numbers: list[int]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    output_counts: dict[str, int]
    validation_diagnostics: list[ValidationIssue] = Field(default_factory=list)
    stage_diagnostics: list[dict] = Field(default_factory=list)
    result_sha256: str | None = None
    provider_calls: int = 0
    usage: "AttemptUsage | None" = None
    latency_ms: int | None = None
    estimated_cost: "AttemptCost | None" = None
    stage_outcome: Literal["RESULT", "NO_ELIGIBLE_ATTRIBUTES"] | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    retryable: bool = False
    stale: bool = False
    effective: bool


class AttemptUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class AttemptCost(BaseModel):
    currency: Literal["USD"] = "USD"
    amount: Decimal
    pricing_version: str


UnitResponse.model_rebuild()


class Coverage(BaseModel):
    required_units: int
    completed_required_units: int
    effective_work_unit_ids: list[UUID]
    complete: bool


class RunDetail(BaseModel):
    run: RunResponse
    coverage: Coverage
    attempts: list[UnitResponse]
    execution: "ExecutionSummary | None" = None
    can_retry: bool = False
    can_cancel: bool = False
    can_browse_candidates: bool = False


class ExtractionSummary(BaseModel):
    latest_result: RunResponse | None
    current_run: RunResponse | None


class PageInfo(BaseModel):
    total: int
    limit: int
    offset: int


class RunList(BaseModel):
    items: list[RunResponse]
    total: int
    next_cursor: str | None
    previous_cursor: str | None


class ExecutionSummary(BaseModel):
    profile_key: str
    execution_kind: str
    cancel_requested_at: datetime | None
    calls_admitted: int
    call_budget: int
    reported_calls: int
    provider_calls_started: int
    unreported_provider_calls: int
    unreported_admissions: int
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: Decimal | None


RunDetail.model_rebuild()


class ExtractionActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    acknowledge_unknown_outcome: bool = False


class RegisterRun(ReadModel):
    id: UUID
    status: ExtractionRunStatus
    processing_run_id: UUID
    created_at: datetime
    profile_key: str


class ExtractionRuns(BaseModel):
    latest_attempt: RegisterRun | None = None
    effective_result: RegisterRun | None = None


class PendingOperation(BaseModel):
    id: UUID
    preparing: bool


class DocumentExtractionStatus(BaseModel):
    revision_document_id: UUID
    processing_run_id: UUID | None
    ineligible_reason: (
        Literal["REMOVED", "READ_ONLY", "PROCESSING_REQUIRED", "NO_PAGE_ARTIFACTS"] | None
    )
    extraction: ExtractionRuns = Field(default_factory=ExtractionRuns)
    enrichment: RegisterRun | None = None
    pending_operation: PendingOperation | None = None


class ExtractionRegisterStatus(BaseModel):
    items: list[DocumentExtractionStatus]
