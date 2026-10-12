from typing import Any, Protocol

from pydantic import BaseModel, Field

# Spec §24 requires a hard rationale bound and does not set the number.
# 500 characters is the Phase 4 cap: a short user-facing explanation, not a trace.
RATIONALE_MAX_CHARS = 500
ALTERNATIVES_MAX_ITEMS = 3


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


class ClassificationAlternative(BaseModel):
    """One other class the model considered. Types are taxonomy strings, not a vendor enum."""

    type: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)


class ClassificationUsage(BaseModel):
    """Raw usage from one provider call. No prompts, images, document text, or cost."""

    provider: str
    model: str
    provider_response_id: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    image_count: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


class ClassificationImageInput(BaseModel):
    """Private image bytes already read by the caller. Not a storage URL."""

    page_number: int = Field(ge=1)
    mime_type: str = Field(min_length=1)
    data: bytes


class ClassificationTextExcerpt(BaseModel):
    page_number: int = Field(ge=1)
    text: str


class ClassifyDocumentRequest(BaseModel):
    """Bounded evidence for one document classification. The original file is not included."""

    filename: str
    extension: str
    page_count: int = Field(ge=1)
    text_excerpts: list[ClassificationTextExcerpt]
    images: list[ClassificationImageInput]
    allowed_types: tuple[str, ...] = Field(min_length=1)
    instructions: str = Field(min_length=1)


class ClassifyPageInput(BaseModel):
    page_number: int = Field(ge=1)
    text: str | None = None
    image: ClassificationImageInput | None = None


class ClassifyPagesRequest(BaseModel):
    """One bounded page batch. allowed_types is the page taxonomy, which excludes MIXED_DOCUMENT."""

    filename: str
    extension: str
    pages: list[ClassifyPageInput] = Field(min_length=1)
    allowed_types: tuple[str, ...] = Field(min_length=1)
    instructions: str = Field(min_length=1)


class DocumentClassificationResult(BaseModel):
    """Structured document classification. The confidence band is derived later, not here."""

    predicted_type: str = Field(min_length=1)
    confidence_score: float = Field(ge=0.0, le=1.0)
    alternatives: list[ClassificationAlternative] = Field(
        default_factory=list,
        max_length=ALTERNATIVES_MAX_ITEMS,
    )
    rationale: str | None = Field(default=None, max_length=RATIONALE_MAX_CHARS)


class PageClassificationResult(BaseModel):
    """Structured page classification. page_number keeps the batch aligned with the request."""

    page_number: int = Field(ge=1)
    predicted_type: str = Field(min_length=1)
    confidence_score: float = Field(ge=0.0, le=1.0)
    alternatives: list[ClassificationAlternative] = Field(
        default_factory=list,
        max_length=ALTERNATIVES_MAX_ITEMS,
    )
    rationale: str | None = Field(default=None, max_length=RATIONALE_MAX_CHARS)


class DocumentClassificationResponse(BaseModel):
    result: DocumentClassificationResult
    usage: ClassificationUsage


class PageClassificationResponse(BaseModel):
    pages: list[PageClassificationResult]
    usage: ClassificationUsage


class ClassificationProvider(Protocol):
    """Vendor-neutral document and page classification. Implementations must not leak SDK types."""

    def classify_document(
        self, request: ClassifyDocumentRequest
    ) -> DocumentClassificationResponse: ...

    def classify_pages(self, request: ClassifyPagesRequest) -> PageClassificationResponse: ...
