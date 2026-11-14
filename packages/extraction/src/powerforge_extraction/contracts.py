"""Validated persistence inputs. No HTTP, ORM, workers or provider SDKs."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from powerforge_ai.extraction import MAX_VALIDATION_ISSUES, ValidationIssue
from powerforge_extraction.enums import (
    AICallOutcome,
)

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
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
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
