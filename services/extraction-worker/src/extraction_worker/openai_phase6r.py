"""Responses transport for the two pinned Phase 6R stages."""

import base64
from typing import Any

import openai
from pydantic import ValidationError

from powerforge_ai.extraction import (
    ErrorCode,
    ExecutionUsage,
    ExtractionRequest,
    ExtractionResponse,
    ProviderFailure,
)
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.phase6r_contracts import MAX_RESPONSE_BYTES, VERSION
from powerforge_extraction.phase6r_profile import (
    PROMPTS,
    RESPONSES,
    provider_available,
    structured_schema,
)
from powerforge_shared.config import Settings


class OpenAIPhase6RProvider:
    def __init__(self, settings: Settings, profile, client: Any | None = None):
        if profile.provider != "openai" or not provider_available(settings, profile.provider):
            raise ProviderFailure(ErrorCode.DISABLED)
        if client is None and not settings.openai_api_key:
            raise ProviderFailure(ErrorCode.AUTH)
        self.profile = profile
        self.client = (
            client
            if client is not None
            else openai.OpenAI(
                api_key=settings.openai_api_key, max_retries=0, timeout=profile.timeout_seconds
            )
        )

    def execute(self, request: ExtractionRequest) -> ExtractionResponse:
        model = RESPONSES.get(request.stage)
        if (
            model is None
            or request.response_model is not model
            or request.instructions != PROMPTS[request.stage]
            or request.schema_version != VERSION
            or request.model != self.profile.model
            or request.timeout_seconds != self.profile.timeout_seconds
            or request.max_output_tokens != self.profile.max_output_tokens
            or not request.text
            or not request.image
            or request.image_mime_type != "image/png"
            or request.image_detail != "high"
        ):
            raise ProviderFailure(ErrorCode.INPUT)
        content = [
            {"type": "input_text", "text": request.text},
            {
                "type": "input_image",
                "detail": request.image_detail,
                "image_url": "data:image/png;base64," + base64.b64encode(request.image).decode(),
            },
        ]
        body = {
            "model": request.model,
            "instructions": request.instructions,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.stage.lower(),
                    "strict": True,
                    "schema": structured_schema(model.model_json_schema()),
                }
            },
            "max_output_tokens": request.max_output_tokens,
            "store": False,
        }
        if len(canonical_json(body).encode()) > self.profile.max_transport_bytes:
            raise ProviderFailure(ErrorCode.INPUT)
        try:
            response = self.client.responses.create(
                **body,
                timeout=request.timeout_seconds,
                extra_headers={"X-Client-Request-Id": str(request.work_unit_id)},
            )
        except openai.RateLimitError:
            raise ProviderFailure(ErrorCode.RATE_LIMIT) from None
        except openai.APITimeoutError:
            raise ProviderFailure(ErrorCode.TIMEOUT) from None
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            raise ProviderFailure(ErrorCode.AUTH) from None
        except openai.APIConnectionError:
            raise ProviderFailure(ErrorCode.UNAVAILABLE) from None
        except openai.APIStatusError as exc:
            code = ErrorCode.UNAVAILABLE if exc.status_code >= 500 else ErrorCode.INVALID
            raise ProviderFailure(code) from None
        raw_usage = getattr(response, "usage", None)
        try:
            usage = ExecutionUsage(
                input_tokens=getattr(raw_usage, "input_tokens", None),
                output_tokens=getattr(raw_usage, "output_tokens", None),
                cached_input_tokens=getattr(
                    getattr(raw_usage, "input_tokens_details", None), "cached_tokens", None
                ),
            )
        except ValidationError:
            raise ProviderFailure(ErrorCode.INVALID) from None

        parts = [
            part
            for item in (response.output or [])
            if item.type == "message"
            for part in (item.content or [])
        ]
        if any(part.type == "refusal" for part in parts):
            raise ProviderFailure(ErrorCode.REFUSAL, usage)
        if response.status != "completed" or len(parts) != 1 or parts[0].type != "output_text":
            raise ProviderFailure(ErrorCode.INVALID, usage)
        raw = parts[0].text.encode()
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderFailure(ErrorCode.INVALID, usage)
        try:
            result = model.model_validate_json(raw)
        except ValidationError:
            raise ProviderFailure(ErrorCode.INVALID, usage) from None
        return ExtractionResponse[model](result=result, usage=usage)
