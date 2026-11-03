"""One bounded Responses structured call. Retries belong to persisted work attempts."""

import base64
from typing import Any

import openai
from pydantic import ValidationError

from powerforge_ai.extraction import (
    ErrorCode,
    ExecutionUsage,
    ExtractionRequest,
    ExtractionResponse,
    ProbeResult,
    ProviderFailure,
)
from powerforge_shared.config import Settings


class OpenAIExtractionProvider:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if not settings.extraction_external_enabled:
            raise ProviderFailure(ErrorCode.DISABLED)
        if client is None and not settings.openai_api_key:
            raise ProviderFailure(ErrorCode.AUTH)
        self.client = (
            client
            if client is not None
            else openai.OpenAI(
                api_key=settings.openai_api_key,
                max_retries=0,
                timeout=settings.extraction_timeout_seconds,
            )
        )

    def execute(self, request: ExtractionRequest) -> ExtractionResponse:
        content = [
            {
                "type": "input_text",
                "text": request.text
                if request.text is not None
                else "No native text; acknowledge image input only.",
            }
        ]
        if request.image:
            encoded = base64.b64encode(request.image).decode()
            content.append(
                {
                    "type": "input_image",
                    "detail": "low",
                    "image_url": f"data:{request.image_mime_type};base64,{encoded}",
                }
            )
        try:
            response = self.client.responses.parse(
                model=request.model,
                instructions=request.instructions,
                input=[{"role": "user", "content": content}],
                text_format=ProbeResult,
                max_output_tokens=request.max_output_tokens,
                timeout=request.timeout_seconds,
                store=False,
                extra_headers={"X-Client-Request-Id": str(request.work_unit_id)},
            )
        except Exception as exc:
            if isinstance(exc, openai.RateLimitError):
                code = ErrorCode.RATE_LIMIT
            elif isinstance(exc, openai.APITimeoutError):
                code = ErrorCode.TIMEOUT
            elif isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
                code = ErrorCode.AUTH
            elif (
                isinstance(exc, openai.APIConnectionError)
                or isinstance(exc, openai.APIStatusError)
                and exc.status_code >= 500
            ):
                code = ErrorCode.UNAVAILABLE
            else:
                code = ErrorCode.INVALID
            raise ProviderFailure(code) from None
        raw = getattr(response, "usage", None)
        try:
            usage = ExecutionUsage(
                input_tokens=getattr(raw, "input_tokens", None),
                cached_input_tokens=getattr(
                    getattr(raw, "input_tokens_details", None), "cached_tokens", None
                ),
                output_tokens=getattr(raw, "output_tokens", None),
            )
        except ValidationError:
            raise ProviderFailure(ErrorCode.INVALID) from None
        refused = any(
            getattr(c, "type", None) == "refusal"
            for item in (getattr(response, "output", None) or [])
            for c in (getattr(item, "content", None) or [])
        )
        if refused:
            raise ProviderFailure(ErrorCode.REFUSAL, usage)
        try:
            if getattr(response, "status", None) != "completed" or response.output_parsed is None:
                raise ValueError("Incomplete structured response")
            parsed = response.output_parsed
            result = ProbeResult.model_validate(
                parsed.model_dump() if isinstance(parsed, ProbeResult) else parsed
            )
        except (ValidationError, ValueError, AttributeError):
            raise ProviderFailure(ErrorCode.INVALID, usage) from None
        return ExtractionResponse(result=result, usage=usage)
