"""Explicit read allowlists; storage keys and internal execution metadata stay private."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from powerforge_extraction.contracts import CandidateInput, TableLayout
from powerforge_extraction.enums import (
    EvidenceRole,
    EvidenceSourceKind,
    ExtractionMethod,
    ExtractionRunStatus,
    TableKind,
    WorkUnitStatus,
)
from powerforge_provenance.locations import Region, SourceLocation


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
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    retryable: bool = False
    stale: bool = False
    effective: bool


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


class ExtractionSummary(BaseModel):
    latest_result: RunResponse | None
    current_run: RunResponse | None


class PageInfo(BaseModel):
    total: int
    limit: int
    offset: int


class RunList(PageInfo):
    items: list[RunResponse]


class EvidenceSummary(ReadModel):
    id: UUID
    document_page_id: UUID
    page_artifact_id: UUID | None
    source_kind: EvidenceSourceKind
    extraction_method: ExtractionMethod
    source_snippet: str | None
    table_id: UUID | None
    cell_id: str | None
    grounding_precision: Literal[
        "TEXT_OFFSETS", "TEXT_PAGE", "VISUAL_REGION", "VISUAL_PAGE", "PAGE_ONLY"
    ] = "PAGE_ONLY"


class Citation(BaseModel):
    evidence: EvidenceSummary
    role: EvidenceRole
    position: int


class SourceGroupSummary(ReadModel):
    id: UUID
    local_key: str
    equipment_type_hint: str | None
    tag_text: str | None
    label: str | None
    evidence_ids: list[UUID]


class CandidateResponse(CandidateInput):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    run_id: UUID
    document_id: UUID
    work_unit_id: UUID
    created_at: datetime
    source_group: SourceGroupSummary | None = None
    supported: bool = False
    evidence: list[Citation] = Field(default_factory=list)


class CandidateList(PageInfo):
    run_id: UUID
    status: ExtractionRunStatus
    coverage: Coverage
    items: list[CandidateResponse]


class TableResponse(ReadModel):
    id: UUID
    run_id: UUID
    document_id: UUID
    work_unit_id: UUID
    layout_schema_version: str
    table_kind: TableKind
    source_locations: list[SourceLocation]
    evidence_ids: list[UUID]
    layout: TableLayout
    created_at: datetime


class TableList(PageInfo):
    run_id: UUID
    status: ExtractionRunStatus
    coverage: Coverage
    items: list[TableResponse]


class EvidenceDetail(EvidenceSummary):
    run_id: UUID
    document_id: UUID
    processing_run_id: UUID
    work_unit_id: UUID
    page_number: int
    region: Region | None
    text_start: int | None
    text_end: int | None
    offset_convention: str | None
    created_at: datetime
    artifact_url: str | None
    artifact_url_expires_seconds: int | None


class ExtractionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    profile_key: str = Field(default="infrastructure-fake-v1", min_length=1, max_length=100)
    pages: list[int] | None = Field(default=None, min_length=1, max_length=1000)
    mode: Literal["ensure", "reextract"] = "ensure"


class ProfileInfo(BaseModel):
    key: str
    execution_kind: str
    provider: str
    model: str
    enabled: bool
    production_extractor: bool = False
    description: str


class ProfileList(BaseModel):
    items: list[ProfileInfo]


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
