"""Explicit read allowlists; storage keys and internal execution metadata stay private."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from powerforge_extraction.contracts import CandidateInput, TableLayout
from powerforge_extraction.enriched_contracts import EnrichedTableLayout
from powerforge_extraction.enriched_planning import EnrichmentSelection
from powerforge_extraction.enums import (
    EvidenceRole,
    EvidenceSourceKind,
    ExtractionMethod,
    ExtractionRunStatus,
    TableKind,
    WorkUnitStatus,
)
from powerforge_extraction.stage_diagnostics import StageTrace
from powerforge_provenance.enriched_locations import EnrichedLocation
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
    stage_trace: StageTrace | None = None
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
    can_retry: bool = False
    can_cancel: bool = False


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
    source_page_number: int | None = None
    table_id: UUID | None
    cell_id: str | None
    enrichment_artifact_id: UUID | None = None
    geometry_artifact_id: UUID | None = None
    source_locator: EnrichedLocation | None = None

    @field_validator("source_locator", mode="before")
    @classmethod
    def locator_from_json(cls, value):
        if isinstance(value, dict):
            import json

            return EnrichedLocation.model_validate_json(json.dumps(value, default=str))
        return value

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
    source_locations: list[SourceLocation | EnrichedLocation]
    evidence_ids: list[UUID]
    layout: TableLayout | EnrichedTableLayout
    created_at: datetime

    @field_validator("source_locations", mode="before")
    @classmethod
    def locations_from_json(cls, value):
        from powerforge_provenance.spatial_base import canonical_json

        return [
            EnrichedLocation.model_validate_json(canonical_json(v))
            if isinstance(v, dict) and v.get("version") == "source-location-v2"
            else v
            for v in value
        ]

    @field_validator("layout", mode="before")
    @classmethod
    def layout_from_json(cls, value):
        from powerforge_provenance.spatial_base import canonical_json

        if (
            isinstance(value, dict)
            and value.get("metadata", {}).get("version") == "enriched-table-metadata-v1"
        ):
            return EnrichedTableLayout.model_validate_json(canonical_json(value))
        return value


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
    source_image_url: str | None = None
    source_image_width_px: int | None = None
    source_image_height_px: int | None = None


class ExtractionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    profile_key: str = Field(default="infrastructure-fake-v1", min_length=1, max_length=100)
    pages: list[int] | None = Field(default=None, min_length=1, max_length=1000)
    mode: Literal["ensure", "reextract"] = "ensure"
    enrichment_bindings: list[EnrichmentSelection] = Field(default_factory=list, max_length=50)


class ProfileInfo(BaseModel):
    key: str
    execution_kind: str
    provider: str
    model: str
    enabled: bool
    production_extractor: bool = False
    requires_enrichment: bool = False
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
    acknowledge_unknown_outcome: bool = False


RunFamily = Literal["engineering", "tables"]


class RegisterRun(ReadModel):
    id: UUID
    status: ExtractionRunStatus
    processing_run_id: UUID
    created_at: datetime
    profile_key: str


class FamilyRuns(BaseModel):
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
    engineering: FamilyRuns = Field(default_factory=FamilyRuns)
    tables: FamilyRuns = Field(default_factory=FamilyRuns)
    enrichment: RegisterRun | None = None
    pending_operation: PendingOperation | None = None


class ExtractionRegisterStatus(BaseModel):
    items: list[DocumentExtractionStatus]


class EvidenceGroupRow(BaseModel):
    run_id: UUID
    family: RunFamily
    source_group_id: UUID | None
    label: str | None
    tag_text: str | None
    equipment_type_hint: str | None
    page_numbers: list[int]
    candidate_count: int


class EvidenceGroupList(PageInfo):
    items: list[EvidenceGroupRow]
