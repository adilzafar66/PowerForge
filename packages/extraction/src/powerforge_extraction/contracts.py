"""Validated persistence inputs. No HTTP, ORM, workers or provider SDKs."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    field_serializer,
    field_validator,
    model_validator,
)

from powerforge_ai.extraction import MAX_VALIDATION_ISSUES, ValidationIssue
from powerforge_engineering_model.enums import AttributeValueType
from powerforge_engineering_model.registry import (
    get_attribute_definition,
    get_equipment_definition,
    normalize_attribute_value,
)
from powerforge_extraction.enums import (
    AICallOutcome,
    CandidateKind,
    EvidenceRole,
    EvidenceSourceKind,
    ExtractionMethod,
    MappingStatus,
    TableKind,
)
from powerforge_provenance.locations import SourceLocation


def exact_decimal(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("Use a decimal string or Decimal, not a binary float")
    return value


ExactDecimal = Annotated[Decimal, BeforeValidator(exact_decimal)]
ShortText = Annotated[str, Field(min_length=1, max_length=2000)]
Identity = Annotated[str, Field(min_length=1, max_length=200)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunInput(Contract):
    document_id: UUID
    processing_run_id: UUID
    extractor_version: Identity
    schema_version: Identity
    registry_version: Identity = "registry-v1"
    profile_version: Identity
    profile_hash: Identity
    provider: Identity
    model: Identity
    prompt_version: Identity
    prompt_hash: Identity
    selected_pages: list[int] = Field(min_length=1, max_length=1000)
    stages: list[Identity] = Field(min_length=1, max_length=20)
    input_artifact_ids: list[UUID] = Field(min_length=1, max_length=10000)
    context_fingerprint: Identity | None = None
    context_revision_id: UUID | None = None
    initiated_from_revision_document_id: UUID | None = None
    requested_by: UUID | None = None
    reextracts_run_id: UUID | None = None

    @model_validator(mode="after")
    def selections(self) -> "RunInput":
        if self.registry_version != "registry-v1":
            raise ValueError("Unsupported registry snapshot")
        if self.selected_pages != sorted(set(self.selected_pages)) or min(self.selected_pages) < 1:
            raise ValueError("Select distinct positive pages in ascending order")
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("Duplicate stages")
        if len(set(self.input_artifact_ids)) != len(self.input_artifact_ids):
            raise ValueError("Duplicate input artifacts")
        if (self.context_fingerprint is None) != (self.context_revision_id is None):
            raise ValueError("Context-dependent inputs require a revision and fingerprint")
        return self


class WorkUnitInput(Contract):
    unit_key: Identity
    stage: Identity
    page_numbers: list[int] = Field(min_length=1, max_length=1000)
    input_artifact_ids: list[UUID] = Field(min_length=1, max_length=10000)
    attempt_number: int = Field(default=1, ge=1)
    retry_of_work_unit_id: UUID | None = None
    required: bool = True
    execution_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def stable_inputs(self) -> "WorkUnitInput":
        if self.page_numbers != sorted(set(self.page_numbers)) or min(self.page_numbers) < 1:
            raise ValueError("Work units need distinct positive pages in ascending order")
        if len(set(self.input_artifact_ids)) != len(self.input_artifact_ids):
            raise ValueError("Duplicate work-unit input artifacts")
        if len(json.dumps(self.execution_metadata, allow_nan=False).encode()) > 16000:
            raise ValueError("Execution metadata exceeds 16 KB")
        return self


class EvidenceInput(Contract):
    id: UUID = Field(default_factory=uuid4)
    location: SourceLocation
    source_kind: EvidenceSourceKind
    extraction_method: ExtractionMethod
    source_snippet: str | None = Field(default=None, max_length=2000)
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, ge=0)
    offset_convention: str | None = None
    table_id: UUID | None = None
    cell_id: Identity | None = None

    @model_validator(mode="after")
    def offsets(self) -> "EvidenceInput":
        if self.text_start is not None or self.text_end is not None:
            if (
                self.text_start is None
                or self.text_end is None
                or self.text_end <= self.text_start
                or self.location.page_artifact_id is None
                or self.offset_convention != "UNICODE_CODEPOINT"
            ):
                raise ValueError("Offsets need a versioned text artifact and codepoint convention")
        elif self.offset_convention is not None:
            raise ValueError("Offset convention requires offsets")
        if self.cell_id is not None and self.table_id is None:
            raise ValueError("Cell locator requires a table")
        return self


class SourceGroupInput(Contract):
    id: UUID = Field(default_factory=uuid4)
    local_key: Identity
    equipment_type_hint: str | None = None
    tag_text: str | None = Field(default=None, max_length=200)
    label: str | None = Field(default=None, max_length=500)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def hint(self) -> "SourceGroupInput":
        if self.equipment_type_hint is not None:
            get_equipment_definition(self.equipment_type_hint)
        return self


class TableCell(Contract):
    id: Identity
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    text: str = Field(max_length=2000)
    is_header: bool = False
    location: SourceLocation | None = None


class TableLayout(Contract):
    title: str | None = Field(default=None, max_length=500)
    rows: list[str] = Field(max_length=10000)
    columns: list[str] = Field(max_length=1000)
    cells: list[TableCell] = Field(max_length=50000)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def cells_in_grid(self) -> "TableLayout":
        if len({c.id for c in self.cells}) != len(self.cells):
            raise ValueError("Cell IDs must be unique")
        for cell in self.cells:
            if cell.row + cell.row_span > len(self.rows) or (
                cell.column + cell.column_span > len(self.columns)
            ):
                raise ValueError("Cell is outside the table grid")
        return self


class TableInput(Contract):
    id: UUID = Field(default_factory=uuid4)
    layout_schema_version: str = "table-layout-v1"
    table_kind: TableKind = TableKind.UNCLASSIFIED
    source_locations: list[SourceLocation] = Field(min_length=1, max_length=1000)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=100)
    layout: TableLayout

    @model_validator(mode="after")
    def version(self) -> "TableInput":
        if self.layout_schema_version != "table-layout-v1":
            raise ValueError("Unsupported table layout version")
        return self


class CandidateInput(Contract):
    id: UUID = Field(default_factory=uuid4)
    kind: CandidateKind
    mapping_status: MappingStatus
    raw_text: ShortText
    raw_value: str | None = Field(default=None, max_length=2000)
    raw_unit: str | None = Field(default=None, max_length=100)
    observed_tag: str | None = Field(default=None, max_length=200)
    source_group_id: UUID | None = None
    equipment_mention_candidate_id: UUID | None = None
    equipment_type_key: str | None = None
    attribute_key: str | None = None
    value_type: AttributeValueType | None = None
    numeric_value: ExactDecimal | None = None
    integer_value: StrictInt | None = Field(default=None, ge=-(2**63), le=2**63 - 1)
    text_value: str | None = Field(default=None, max_length=2000)
    boolean_value: StrictBool | None = None
    unit: str | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    confidence_band: Identity | None = None
    confidence_method: Identity | None = None
    reason_code: Identity | None = None
    explanation: str | None = Field(default=None, max_length=1000)
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)

    @field_serializer("integer_value", when_used="json")
    def integer_string(self, value: int | None) -> str | None:
        return None if value is None else str(value)

    @field_validator("diagnostics")
    @classmethod
    def bounded_diagnostics(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if len(json.dumps(value, allow_nan=False).encode()) > 16000:
            raise ValueError("Candidate diagnostics exceed 16 KB")
        return value

    @model_validator(mode="after")
    def mapping(self) -> "CandidateInput":
        if self.equipment_type_key is not None:
            get_equipment_definition(self.equipment_type_key)
        slots = [self.numeric_value, self.integer_value, self.text_value, self.boolean_value]
        if (
            self.mapping_status == MappingStatus.MAPPED
            and self.kind == CandidateKind.ATTRIBUTE_VALUE
        ):
            if self.equipment_type_key is None or self.attribute_key is None:
                raise ValueError("Mapped attributes need registry type and key")
            definition = get_attribute_definition(self.equipment_type_key, self.attribute_key)
            if self.value_type != definition.value_type or self.unit != definition.canonical_unit:
                raise ValueError("Mapped value type/unit differs from registry")
            index = {"NUMBER": 0, "INTEGER": 1, "TEXT": 2, "ENUM": 2, "BOOLEAN": 3}[self.value_type]
            if sum(v is not None for v in slots) != 1 or slots[index] is None:
                raise ValueError("Exactly one compatible typed value is required")
            normalize_attribute_value(
                self.equipment_type_key, self.attribute_key, slots[index], self.unit
            )
        else:
            if (
                any(v is not None for v in slots)
                or self.value_type is not None
                or self.unit is not None
            ):
                raise ValueError("Only mapped attributes have normalized typed slots")
            if self.attribute_key is not None:
                raise ValueError("Unmapped keys belong in raw observations")
            if self.mapping_status == MappingStatus.MAPPED and (
                self.kind != CandidateKind.EQUIPMENT_MENTION or self.equipment_type_key is None
            ):
                raise ValueError("Mapped equipment mentions need a registry type")
        if self.kind == CandidateKind.EQUIPMENT_MENTION and self.equipment_mention_candidate_id:
            raise ValueError("Equipment mentions cannot refer to another mention")
        return self


class CandidateEvidenceInput(Contract):
    candidate_id: UUID
    evidence_id: UUID
    role: EvidenceRole = EvidenceRole.PRIMARY
    position: int = Field(default=0, ge=0)


class AICallInput(Contract):
    id: UUID = Field(default_factory=uuid4)
    provider: Identity
    model: Identity
    prompt_version: Identity
    prompt_hash: Identity
    schema_version: Identity
    request_correlation_id: Identity | None = None
    outcome: AICallOutcome
    error_code: Identity | None = None
    validation_diagnostics: tuple[ValidationIssue, ...] = Field(
        default=(), max_length=MAX_VALIDATION_ISSUES
    )
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: ExactDecimal | None = Field(default=None, ge=0)
    pricing_basis: Identity | None = None

    @model_validator(mode="after")
    def timing_and_cost(self) -> "AICallInput":
        if self.finished_at < self.started_at:
            raise ValueError("Call finish precedes start")
        if self.estimated_cost_usd is not None and self.pricing_basis is None:
            raise ValueError("Estimated cost needs a recorded pricing basis")
        if self.cached_input_tokens is not None and self.input_tokens is not None:
            if self.cached_input_tokens > self.input_tokens:
                raise ValueError("Cached tokens exceed input tokens")
        return self


class WorkUnitOutput(Contract):
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=10000)
    source_groups: list[SourceGroupInput] = Field(default_factory=list, max_length=10000)
    tables: list[TableInput] = Field(default_factory=list, max_length=1000)
    candidates: list[CandidateInput] = Field(default_factory=list, max_length=10000)
    candidate_evidence: list[CandidateEvidenceInput] = Field(default_factory=list, max_length=50000)
    ai_calls: list[AICallInput] = Field(default_factory=list, max_length=1000)
    diagnostic_counts: dict[
        Literal[
            "rejected_ungrounded",
            "rejected_source_fields",
            "detached_associations",
            "skipped_empty_tables",
        ],
        Annotated[int, Field(strict=True, ge=0, le=10000)],
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_output(self) -> "WorkUnitOutput":
        if len(self.model_dump_json().encode()) > 8 * 1024 * 1024:
            raise ValueError("Work-unit output exceeds 8 MB; use smaller logical units")
        return self
