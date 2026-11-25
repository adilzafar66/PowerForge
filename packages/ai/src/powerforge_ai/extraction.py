"""Provider-neutral bounded extraction execution contracts; no vendor SDK types."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ErrorCode(StrEnum):
    TIMEOUT = "PROVIDER_TIMEOUT"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RATE_LIMIT = "PROVIDER_RATE_LIMITED"
    AUTH = "PROVIDER_AUTH_ERROR"
    REFUSAL = "PROVIDER_REFUSAL"
    INVALID = "INVALID_PROVIDER_RESPONSE"
    INPUT = "INVALID_SOURCE_INPUT"
    NO_TEXT = "NO_READABLE_SOURCE_TEXT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    INTERRUPTED = "WORKER_INTERRUPTED"
    BUDGET = "CALL_BUDGET_EXHAUSTED"
    DISABLED = "EXTERNAL_PROCESSING_DISABLED"
    INTERNAL = "EXECUTION_FAILED"
    AUDIT = "RESPONSE_AUDIT_UNAVAILABLE"
    DEPENDENCY = "PREREQUISITE_FAILED"


class ExecutionUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def cached_within_input(self) -> "ExecutionUsage":
        if (
            self.input_tokens is not None
            and self.cached_input_tokens is not None
            and self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("Cached tokens exceed input tokens")
        return self


ValidationCategory = Literal[
    "INCOMPLETE",
    "REFUSAL",
    "ENVELOPE",
    "JSON",
    "SCHEMA",
    "FIELD_CONSTRAINT",
    "CROSS_FIELD",
    "CAPACITY",
]
ValidationType = Literal[
    "incomplete",
    "max_output_tokens",
    "content_filter",
    "refusal",
    "invalid_envelope",
    "invalid_usage",
    "http_rejection",
    "invalid_json_schema",
    "json_invalid",
    "schema_invalid",
    "missing",
    "extra_forbidden",
    "model_type",
    "tuple_type",
    "string_type",
    "int_type",
    "bool_type",
    "decimal_type",
    "string_pattern_mismatch",
    "string_too_short",
    "string_too_long",
    "enum",
    "literal_error",
    "too_short",
    "too_long",
    "greater_than",
    "greater_than_equal",
    "less_than",
    "less_than_equal",
    "invalid_tag_state",
    "alternate_representations_mismatch",
    "duplicate_reference",
    "page_identity_mismatch",
    "upstream_identity_mismatch",
    "request_binding_mismatch",
    "response_byte_limit",
    "output_token_limit",
    "invalid_json_structure",
    "all_assertions_quarantined",
]
ValidationField = Literal[
    "version",
    "stage",
    "page_context_hash",
    "upstream_hash",
    "equipment",
    "attributes",
    "raw_unmapped",
    "local_ref",
    "source_description",
    "registry_type",
    "tag_state",
    "tag",
    "qualification",
    "raw_qualification",
    "evidence",
    "kind",
    "role",
    "reading_ref",
    "quote",
    "region",
    "reported_text",
    "x",
    "y",
    "width",
    "height",
    "equipment_ref",
    "association",
    "raw_label",
    "raw_value",
    "raw_unit",
    "qualifiers",
    "value_form",
    "attribute_key",
    "key",
    "raw",
    "label",
    "source_unit",
    "form",
    "alternates",
    "reading",
    "proposed_enum_value",
    "origin",
    "proposed_value",
    "proposed_unit",
    "alternate_representations",
    "value",
    "unit",
    "inference_explanation",
    "inference_basis",
    "source_expression",
    "display_label",
    "output",
    "status",
    "usage",
    "*",
]
MAX_VALIDATION_ISSUES = 8


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ValidationCategory
    error_type: ValidationType
    path: tuple[ValidationField | int, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def bounded_indexes(self):
        if any(isinstance(part, int) and not 0 <= part < 1024 for part in self.path):
            raise ValueError("Invalid diagnostic path index")
        return self


class ResponseValidationFailure(ValueError):
    def __init__(self, issue: ValidationIssue, message: str):
        self.issue = issue
        super().__init__(message)


class ProviderFailure(Exception):
    """Only safe categories cross the integration boundary; never SDK messages."""

    def __init__(
        self,
        code: ErrorCode,
        usage: ExecutionUsage | None = None,
        *,
        diagnostics: tuple[ValidationIssue, ...] = (),
    ) -> None:
        self.code, self.usage = code, usage
        self.diagnostics = diagnostics[:MAX_VALIDATION_ISSUES]
        super().__init__(code.value)

    @property
    def retryable(self) -> bool:
        return self.code in {
            ErrorCode.TIMEOUT,
            ErrorCode.UNAVAILABLE,
            ErrorCode.RATE_LIMIT,
            ErrorCode.INTERRUPTED,
            ErrorCode.SOURCE_UNAVAILABLE,
        }


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    work_unit_id: UUID
    unit_key: str
    attempt_number: int
    model: str
    instructions: str
    schema_version: str
    timeout_seconds: int
    max_output_tokens: int
    text: str | None = None
    input_version: str = "compact-page-v1"
    request_digest_version: Literal["responses-body-v1"] | None = None
    image: bytes | None = None
    image_mime_type: str | None = None
    # Selected by trusted execution code; never supplied by a model or import path.
    response_model: type[BaseModel] = Field(exclude=True)
    stage: Literal["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"]
    image_detail: Literal["low", "high", "auto"] = "low"
    reasoning_effort: Literal["none", "low", "medium"] | None = None


class ExtractionResponse[Result: BaseModel](BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Result
    usage: ExecutionUsage


@dataclass(frozen=True)
class AttributeOutput:
    output_text: bytes = field(repr=False)
    usage: ExecutionUsage
    # The transport returns the immutable request that produced these bytes.
    request: ExtractionRequest = field(repr=False)


class ExtractionProvider(Protocol):
    def execute(self, request: ExtractionRequest) -> ExtractionResponse | AttributeOutput: ...
