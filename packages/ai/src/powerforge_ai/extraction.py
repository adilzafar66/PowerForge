"""Provider-neutral bounded extraction execution contracts; no vendor SDK types."""

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
    INTERRUPTED = "WORKER_INTERRUPTED"
    BUDGET = "CALL_BUDGET_EXHAUSTED"
    DISABLED = "EXTERNAL_PROCESSING_DISABLED"
    INTERNAL = "EXECUTION_FAILED"


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


class ProviderFailure(Exception):
    """Only safe categories cross the integration boundary; never SDK messages."""

    def __init__(self, code: ErrorCode, usage: ExecutionUsage | None = None) -> None:
        self.code, self.usage = code, usage
        super().__init__(code.value)

    @property
    def retryable(self) -> bool:
        return self.code in {
            ErrorCode.TIMEOUT,
            ErrorCode.UNAVAILABLE,
            ErrorCode.RATE_LIMIT,
            ErrorCode.INTERRUPTED,
        }


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    acknowledged: Literal[True]
    excerpt: str | None = Field(max_length=256)


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_unit_id: UUID
    unit_key: str
    attempt_number: int
    model: str
    instructions: str
    schema_version: str
    timeout_seconds: int
    max_output_tokens: int
    text: str | None = None
    image: bytes | None = None
    image_mime_type: str | None = None


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: ProbeResult
    usage: ExecutionUsage


class ExtractionProvider(Protocol):
    def execute(self, request: ExtractionRequest) -> ExtractionResponse: ...
