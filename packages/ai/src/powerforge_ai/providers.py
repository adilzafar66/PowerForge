from typing import Any, Protocol

from pydantic import BaseModel, Field


class StructuredExtractionResult(BaseModel):
    """Provider-agnostic extraction envelope. Vendor payloads are not the domain model."""

    data: dict[str, Any]
    provider: str
    model: str
    model_version: str
    prompt_version: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class LLMProvider(Protocol):
    def extract_structured(
        self,
        input: Any,
        schema: type[BaseModel],
        context: dict[str, Any] | None = None,
    ) -> StructuredExtractionResult: ...


class VisionProvider(Protocol):
    def extract_structured(
        self,
        input: Any,
        schema: type[BaseModel],
        context: dict[str, Any] | None = None,
    ) -> StructuredExtractionResult: ...


class OCRProvider(Protocol):
    def extract_text(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> StructuredExtractionResult: ...
