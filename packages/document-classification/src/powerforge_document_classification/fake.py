"""Filename-driven classification provider. No network and no vendor SDK."""

from __future__ import annotations

from powerforge_ai.providers import (
    ClassificationImageInput,
    ClassificationUsage,
    ClassifyDocumentRequest,
    ClassifyPagesRequest,
    DocumentClassificationResponse,
    DocumentClassificationResult,
    PageClassificationResponse,
    PageClassificationResult,
)
from powerforge_document_classification.errors import (
    ClassificationErrorCode,
    ClassificationProviderError,
)

FAKE_PROVIDER = "fake"
FAKE_MODEL = "fake-classifier"
FAKE_RESPONSE_ID = "resp_fake_1"
FAKE_INPUT_TOKENS = 120
FAKE_CACHED_INPUT_TOKENS = 0
FAKE_OUTPUT_TOKENS = 40
FAKE_REASONING_TOKENS = 0
FAKE_LATENCY_MS = 25

_PAGE_TYPE = "ELECTRICAL_DRAWING"
_PAGE_SCORE = 0.80
_TOKENS = ("timeout", "fail", "invalid", "mixed", "unknown", "low")
_RATIONALE = "Fake classification."


def _scenario(filename: str) -> str:
    lowered = filename.lower()
    for token in _TOKENS:
        if token in lowered:
            return token
    if "transformer" in lowered:
        return "transformer"
    return "default"


def _usage(images: list[ClassificationImageInput]) -> ClassificationUsage:
    return ClassificationUsage(
        provider=FAKE_PROVIDER,
        model=FAKE_MODEL,
        provider_response_id=FAKE_RESPONSE_ID,
        input_tokens=FAKE_INPUT_TOKENS,
        cached_input_tokens=FAKE_CACHED_INPUT_TOKENS,
        output_tokens=FAKE_OUTPUT_TOKENS,
        reasoning_tokens=FAKE_REASONING_TOKENS,
        image_count=len(images),
        latency_ms=FAKE_LATENCY_MS,
    )


def _document_result(scenario: str) -> DocumentClassificationResult:
    if scenario == "mixed" or scenario == "invalid":
        predicted_type, score = "MIXED_DOCUMENT", 0.92
    elif scenario == "unknown":
        predicted_type, score = "UNKNOWN", 0.40
    elif scenario == "low":
        predicted_type, score = "PANEL_SCHEDULE", 0.50
    elif scenario == "transformer":
        predicted_type, score = "TRANSFORMER_SHOP_DRAWING", 0.95
    else:
        predicted_type, score = "SINGLE_LINE_DIAGRAM", 0.95
    return DocumentClassificationResult(
        predicted_type=predicted_type,
        confidence_score=score,
        rationale=_RATIONALE,
    )


class FakeClassificationProvider:
    """Choose one scenario from the filename. The service does not branch on these names."""

    def classify_document(self, request: ClassifyDocumentRequest) -> DocumentClassificationResponse:
        scenario = _scenario(request.filename)
        if scenario == "fail":
            raise ClassificationProviderError(ClassificationErrorCode.PROVIDER_UNAVAILABLE)
        if scenario == "timeout":
            raise ClassificationProviderError(ClassificationErrorCode.PROVIDER_TIMEOUT)
        return DocumentClassificationResponse(
            result=_document_result(scenario),
            usage=_usage(request.images),
        )

    def classify_pages(self, request: ClassifyPagesRequest) -> PageClassificationResponse:
        scenario = _scenario(request.filename)
        if scenario == "fail":
            raise ClassificationProviderError(ClassificationErrorCode.PROVIDER_UNAVAILABLE)
        if scenario == "timeout":
            raise ClassificationProviderError(ClassificationErrorCode.PROVIDER_TIMEOUT)
        pages: list[PageClassificationResult] = []
        for index, page in enumerate(request.pages):
            predicted_type = _PAGE_TYPE
            if scenario == "invalid" and index == 0:
                predicted_type = "MIXED_DOCUMENT"
            pages.append(
                PageClassificationResult(
                    page_number=page.page_number,
                    predicted_type=predicted_type,
                    confidence_score=_PAGE_SCORE,
                    rationale=_RATIONALE,
                )
            )
        images = [page.image for page in request.pages if page.image is not None]
        return PageClassificationResponse(pages=pages, usage=_usage(images))
