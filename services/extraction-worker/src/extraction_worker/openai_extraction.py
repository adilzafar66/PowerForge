"""One bounded Responses structured call. Retries belong to persisted work attempts."""

import base64
import json
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from powerforge_ai.extraction import (
    ErrorCode,
    ExecutionUsage,
    ExtractionRequest,
    ExtractionResponse,
    ProbeResult,
    ProviderFailure,
)
from powerforge_extraction.engineering_stages import get_engineering_stage
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.production_profiles import (
    ProductionProfile,
    input_contract,
    require_production_supported,
)
from powerforge_extraction.table_profiles import TableProfile
from powerforge_shared.config import Settings


def production_input(request: ExtractionRequest, profile: ProductionProfile) -> list[dict]:
    require_production_supported(profile)
    stage = get_engineering_stage(request.stage)
    roles = tuple(
        role
        for role, present in (
            ("native_text", request.text is not None),
            ("analysis_image", request.image is not None),
        )
        if present
    )
    if (
        request.response_model is not stage.response_model
        or request.schema_version != stage.schema_version
        or request.source_roles != roles
        or not roles
        or request.model != profile.model
        or request.timeout_seconds != profile.timeout_seconds
        or request.max_output_tokens != profile.max_output_tokens
        or request.image_detail != profile.image_detail
        or (request.image is not None and request.image_mime_type != "image/png")
        or (profile.input_strategy == "NATIVE_TEXT_ONLY" and roles != ("native_text",))
        or ((request.stage == "ATTRIBUTE_EXTRACTION") != (request.upstream_context is not None))
    ):
        raise ValueError("Request differs from its production profile")
    text_bytes = len(request.text.encode()) if request.text is not None else 0
    image_bytes = len(request.image) if request.image is not None else 0
    if (
        max(text_bytes, image_bytes) > profile.max_input_bytes
        or text_bytes + image_bytes > profile.max_total_input_bytes
        or len(request.text or "") > profile.max_text_chars
        or len(request.instructions.encode()) > profile.max_instruction_bytes
        or len((request.upstream_context or "").encode()) > profile.max_upstream_bytes
    ):
        raise ValueError("Request exceeds its production bounds")
    contract = input_contract()
    content = []
    if request.text is not None:
        content.append(
            {
                "type": "input_text",
                "text": canonical_json(
                    {
                        "schema_version": contract["source_envelope_version"],
                        "untrusted": True,
                        "source_ref": contract["native_source_ref"],
                        "text": request.text,
                    }
                ),
            }
        )
    if request.image is not None:
        content.extend(
            [
                {"type": "input_text", "text": contract["image_label"]},
                {
                    "type": "input_image",
                    "detail": request.image_detail,
                    "image_url": "data:image/png;base64,"
                    + base64.b64encode(request.image).decode(),
                },
            ]
        )
    messages = [{"role": "user", "content": content}]
    if request.upstream_context is not None:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": canonical_json(
                            {
                                "schema_version": contract["upstream_envelope_version"],
                                "untrusted": True,
                                "observations": json.loads(request.upstream_context),
                            }
                        ),
                    }
                ],
            }
        )
    return messages


class OpenAIExtractionProvider:
    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        *,
        profile: ProductionProfile | TableProfile | None = None,
    ) -> None:
        if not settings.extraction_external_enabled:
            raise ProviderFailure(ErrorCode.DISABLED)
        if client is None and not settings.openai_api_key:
            raise ProviderFailure(ErrorCode.AUTH)
        self.profile = profile
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
        if self.profile is not None:
            try:
                if isinstance(self.profile, TableProfile):
                    from powerforge_extraction.table_input import table_production_input

                    messages = table_production_input(request, self.profile)
                else:
                    messages = production_input(request, self.profile)
            except (ValueError, KeyError):
                raise ProviderFailure(ErrorCode.INPUT) from None
        elif request.stage != "SOURCE_PROBE" or request.response_model is not ProbeResult:
            raise ProviderFailure(ErrorCode.INPUT)
        else:
            messages = self._probe_input(request)
        options = {"reasoning": {"effort": self.profile.reasoning_effort}} if self.profile else {}
        try:
            response = self.client.responses.parse(
                model=request.model,
                instructions=request.instructions,
                input=messages,
                text_format=request.response_model,
                max_output_tokens=request.max_output_tokens,
                timeout=request.timeout_seconds,
                store=False,
                extra_headers={"X-Client-Request-Id": str(request.work_unit_id)},
                **options,
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
            result = request.response_model.model_validate(
                parsed.model_dump() if isinstance(parsed, BaseModel) else parsed
            )
        except (ValidationError, ValueError, AttributeError):
            raise ProviderFailure(ErrorCode.INVALID, usage) from None
        return ExtractionResponse[request.response_model](result=result, usage=usage)

    @staticmethod
    def _probe_input(request: ExtractionRequest) -> list[dict]:
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
        return [{"role": "user", "content": content}]
