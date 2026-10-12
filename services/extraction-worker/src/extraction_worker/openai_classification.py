"""OpenAI Responses API adapter. Returns only the package result models."""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

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
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_RETRYABLE = frozenset(
    {
        ClassificationErrorCode.PROVIDER_RATE_LIMITED,
        ClassificationErrorCode.PROVIDER_UNAVAILABLE,
        ClassificationErrorCode.PROVIDER_TIMEOUT,
    }
)


class _PageBatchSchema(BaseModel):
    pages: list[PageClassificationResult]


class OpenAIClassificationProvider:
    """One stateless Responses call at a time. No tools, no stored responses."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._settings = settings
        self._client = client if client is not None else _openai_client(settings)

    def classify_document(self, request: ClassifyDocumentRequest) -> DocumentClassificationResponse:
        parsed, usage = self._parse(
            schema=DocumentClassificationResult,
            instructions=request.instructions,
            content=_document_content(request, self._settings.ai_classification_image_detail),
            image_count=len(request.images),
        )
        return DocumentClassificationResponse(result=parsed, usage=usage)

    def classify_pages(self, request: ClassifyPagesRequest) -> PageClassificationResponse:
        images = [page.image for page in request.pages if page.image is not None]
        parsed, usage = self._parse(
            schema=_PageBatchSchema,
            instructions=request.instructions,
            content=_page_content(request, self._settings.ai_classification_image_detail),
            image_count=len(images),
        )
        return PageClassificationResponse(pages=parsed.pages, usage=usage)

    def _parse(
        self,
        *,
        schema: type[BaseModel],
        instructions: str,
        content: list[dict[str, Any]],
        image_count: int,
    ) -> tuple[Any, ClassificationUsage]:
        last: ClassificationProviderError | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            started = time.perf_counter()
            try:
                response = self._client.responses.parse(
                    model=self._settings.ai_classification_model,
                    instructions=instructions,
                    input=[{"role": "user", "content": content}],
                    text_format=schema,
                    store=False,
                    reasoning={"effort": self._settings.ai_classification_reasoning_effort},
                    timeout=float(self._settings.ai_classification_timeout_seconds),
                )
                parsed = _validated(response, schema)
                return parsed, _usage(self._settings, response, image_count, started)
            except ClassificationProviderError as exc:
                last = exc
            except Exception as exc:
                last = _map_sdk_error(exc)
            if last.code not in _RETRYABLE or attempt == _MAX_ATTEMPTS:
                raise last
            logger.warning(
                "classification provider call failed",
                extra={"error_code": last.code.value, "attempt": attempt},
            )
        raise last


def _openai_client(settings: Settings) -> openai.OpenAI:
    return openai.OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.ai_classification_timeout_seconds,
        max_retries=0,
    )


def _document_content(request: ClassifyDocumentRequest, detail: str) -> list[dict[str, Any]]:
    parts = [
        _text(
            f"filename: {request.filename}\n"
            f"extension: {request.extension}\n"
            f"page_count: {request.page_count}"
        )
    ]
    parts.extend(
        _text(f"page {excerpt.page_number}:\n{excerpt.text}") for excerpt in request.text_excerpts
    )
    parts.extend(_image(image, detail) for image in request.images)
    return parts


def _page_content(request: ClassifyPagesRequest, detail: str) -> list[dict[str, Any]]:
    parts = [_text(f"filename: {request.filename}\nextension: {request.extension}")]
    for page in request.pages:
        if page.text:
            parts.append(_text(f"page {page.page_number}:\n{page.text}"))
        if page.image is not None:
            parts.append(_image(page.image, detail))
    return parts


def _text(text: str) -> dict[str, str]:
    return {"type": "input_text", "text": text}


def _image(image: ClassificationImageInput, detail: str) -> dict[str, str]:
    encoded = base64.b64encode(image.data).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:{image.mime_type};base64,{encoded}",
        "detail": detail,
    }


def _validated(response: object, schema: type[BaseModel]) -> BaseModel:
    if _refused(response):
        raise ClassificationProviderError(ClassificationErrorCode.PROVIDER_REFUSAL)
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raise ClassificationProviderError(ClassificationErrorCode.INVALID_PROVIDER_RESPONSE)
    try:
        return schema.model_validate(parsed)
    except ValidationError:
        raise ClassificationProviderError(
            ClassificationErrorCode.INVALID_PROVIDER_RESPONSE
        ) from None


def _refused(response: object) -> bool:
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) == "refusal":
            return True
        for content in getattr(item, "content", None) or []:
            if getattr(content, "type", None) == "refusal":
                return True
    return False


def _usage(
    settings: Settings,
    response: object,
    image_count: int,
    started: float,
) -> ClassificationUsage:
    raw = getattr(response, "usage", None)
    if raw is None:
        raise ClassificationProviderError(ClassificationErrorCode.INVALID_PROVIDER_RESPONSE)
    input_details = getattr(raw, "input_tokens_details", None)
    output_details = getattr(raw, "output_tokens_details", None)
    return ClassificationUsage(
        provider="openai",
        model=settings.ai_classification_model,
        provider_response_id=getattr(response, "id", None),
        input_tokens=getattr(raw, "input_tokens", None),
        cached_input_tokens=(
            getattr(input_details, "cached_tokens", None) if input_details is not None else None
        ),
        output_tokens=getattr(raw, "output_tokens", None),
        reasoning_tokens=(
            getattr(output_details, "reasoning_tokens", None)
            if output_details is not None
            else None
        ),
        image_count=image_count,
        latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )


def _map_sdk_error(exc: Exception) -> ClassificationProviderError:
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return ClassificationProviderError(ClassificationErrorCode.PROVIDER_AUTH_ERROR)
    if isinstance(exc, openai.RateLimitError):
        return ClassificationProviderError(ClassificationErrorCode.PROVIDER_RATE_LIMITED)
    if isinstance(exc, openai.APITimeoutError):
        return ClassificationProviderError(ClassificationErrorCode.PROVIDER_TIMEOUT)
    if isinstance(exc, openai.APIConnectionError):
        return ClassificationProviderError(ClassificationErrorCode.PROVIDER_UNAVAILABLE)
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return ClassificationProviderError(ClassificationErrorCode.PROVIDER_UNAVAILABLE)
    return ClassificationProviderError(ClassificationErrorCode.INVALID_PROVIDER_RESPONSE)
