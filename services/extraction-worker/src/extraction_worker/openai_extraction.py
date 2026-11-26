"""OpenAI Responses transport for the two pinned extraction stages."""

import json
import logging
from typing import Any

import openai
from pydantic import ValidationError

from powerforge_ai.extraction import (
    AttributeOutput,
    ErrorCode,
    ExecutionUsage,
    ExtractionRequest,
    ExtractionResponse,
    ProviderFailure,
    RecognitionOutput,
    ValidationIssue,
)
from powerforge_extraction.extraction_profile import (
    provider_available,
)
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.performance import (
    EFFORTS,
    RESPONSE_STATUSES,
    SERVICE_TIERS,
    active_performance,
    measure,
    request_metrics,
)
from powerforge_extraction.provider_body import encoded_body, responses_body
from powerforge_extraction.stage_contracts import MAX_RESPONSE_BYTES, stage_schema_version
from powerforge_shared.config import Settings

logger = logging.getLogger(__name__)


class OpenAIExtractionProvider:
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

    def execute(self, request: ExtractionRequest) -> ExtractionResponse | AttributeOutput:
        model = self.profile.response_model_for(request.stage)
        if (
            model is None
            or request.response_model is not model
            or request.instructions != self.profile.instructions_for(request.stage)
            or request.schema_version != stage_schema_version(request.stage)
            or request.model != self.profile.model
            or request.request_digest_version != self.profile.request_digest_for(request.stage)
            or request.reasoning_effort != self.profile.reasoning_effort_for(request.stage)
            or request.timeout_seconds != self.profile.timeout_seconds
            or request.max_output_tokens != self.profile.max_output_tokens
            or not request.text
            or (
                request.stage == "ATTRIBUTE_EXTRACTION"
                and request.input_version != self.profile.manifest["attribute_input_version"]
            )
            or (
                request.stage != "ATTRIBUTE_EXTRACTION"
                and request.input_version != "compact-page-v1"
            )
            or ((request.image is None) != (request.input_version == "readable-text-v1"))
            or (request.image_mime_type != (None if request.image is None else "image/png"))
            or request.image == b""
            or request.image_detail != "high"
        ):
            raise ProviderFailure(ErrorCode.INPUT)
        performance = active_performance.get()
        with measure("request_build"):
            body = responses_body(request, model)
            body_size = len(encoded_body(body))
            if body_size > self.profile.max_transport_bytes:
                raise ProviderFailure(ErrorCode.INPUT)
            if performance is not None:
                try:
                    performance.request = request_metrics(
                        json.loads(request.text),
                        body_bytes=body_size,
                        encoded_image_bytes=4 * ((len(request.image or b"") + 2) // 3),
                        image_detail=request.image_detail,
                        instructions=request.instructions,
                        schema_bytes=len(canonical_json(body["text"]["format"]["schema"]).encode()),
                    )
                except (ValueError, KeyError, IndexError, TypeError):
                    logger.warning("extraction request metrics unavailable")
        try:
            response = self._send(body, request)
        except ProviderFailure as exc:
            if performance is not None:
                performance.response_status = (
                    "timeout" if exc.code == ErrorCode.TIMEOUT else "transport_error"
                )
            raise
        with measure("admission"):
            try:
                return self._admit_response(response, request, model)
            except ProviderFailure as exc:
                if request.stage == "EQUIPMENT_RECOGNITION" and exc.code == ErrorCode.INVALID:
                    raw = self._recover_recognition_text(response)
                    if raw is not None:
                        return RecognitionOutput(raw, exc.usage or ExecutionUsage(), request, exc)
                raise

    @staticmethod
    def _recover_recognition_text(response):
        output = getattr(response, "output", None)
        if not isinstance(output, list):
            return None
        parts = []
        for item in output:
            if getattr(item, "type", None) == "message":
                content = getattr(item, "content", None)
                if not isinstance(content, list):
                    return None
                parts.extend(content)
        if len(parts) != 1 or getattr(parts[0], "type", None) != "output_text":
            return None
        text = getattr(parts[0], "text", None)
        if not isinstance(text, str) or len(text) > MAX_RESPONSE_BYTES:
            return None
        try:
            raw = text.encode()
        except UnicodeError:
            return None
        return raw if len(raw) <= MAX_RESPONSE_BYTES else None

    def _send(self, body, request):
        try:
            with measure("provider_call"):
                return self.client.responses.create(
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
            raise ProviderFailure(
                ErrorCode.UNAVAILABLE,
                diagnostics=(ValidationIssue(category="TRANSPORT", error_type="connection_error"),),
            ) from None
        except (openai.APIResponseValidationError, ValueError, TypeError):
            raise ProviderFailure(
                ErrorCode.INVALID,
                diagnostics=(ValidationIssue(category="ENVELOPE", error_type="invalid_envelope"),),
            ) from None
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderFailure(
                    ErrorCode.UNAVAILABLE,
                    diagnostics=(
                        ValidationIssue(category="TRANSPORT", error_type="upstream_http_error"),
                    ),
                ) from None
            diagnostics = (
                ValidationIssue(
                    category="ENVELOPE",
                    error_type="invalid_json_schema"
                    if exc.code == "invalid_json_schema"
                    else "http_rejection",
                ),
            )
            raise ProviderFailure(
                ErrorCode.INVALID,
                diagnostics=diagnostics,
            ) from None

    @staticmethod
    def _admit_response(response, request, model):
        performance = active_performance.get()
        status = getattr(response, "status", None)
        if performance is not None:
            tier = getattr(response, "service_tier", None)
            effort = getattr(getattr(response, "reasoning", None), "effort", None)
            performance.service_tier = tier if tier in SERVICE_TIERS else None
            performance.reasoning_effort = effort if effort in EFFORTS else None
            performance.response_status = status if status in RESPONSE_STATUSES else None

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
            raise ProviderFailure(
                ErrorCode.INVALID,
                diagnostics=(
                    ValidationIssue(
                        category="ENVELOPE", error_type="invalid_usage", path=("usage",)
                    ),
                ),
            ) from None

        if performance is not None:
            reasoning = getattr(
                getattr(raw_usage, "output_tokens_details", None), "reasoning_tokens", None
            )
            if type(reasoning) is int and 0 <= reasoning <= 2**53 - 1:
                if usage.output_tokens is None or reasoning <= usage.output_tokens:
                    performance.reasoning_tokens = reasoning
                    if usage.output_tokens is not None and usage.output_tokens <= 2**53 - 1:
                        performance.visible_output_tokens = usage.output_tokens - reasoning
        output = getattr(response, "output", None)
        parts = []
        envelope_error = ValidationIssue(
            category="ENVELOPE", error_type="invalid_envelope", path=("output",)
        )
        if isinstance(output, list):
            for item in output:
                if getattr(item, "type", None) == "message":
                    content = getattr(item, "content", None)
                    if not isinstance(content, list):
                        raise ProviderFailure(
                            ErrorCode.INVALID, usage, diagnostics=(envelope_error,)
                        )
                    parts.extend(content)
        if any(getattr(part, "type", None) == "refusal" for part in parts):
            if performance is not None:
                performance.response_status = "refusal"
            raise ProviderFailure(
                ErrorCode.REFUSAL,
                usage,
                diagnostics=(
                    ValidationIssue(category="REFUSAL", error_type="refusal", path=("output",)),
                ),
            )
        if status == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            raise ProviderFailure(
                ErrorCode.INVALID,
                usage,
                diagnostics=(
                    ValidationIssue(
                        category="INCOMPLETE",
                        error_type=reason
                        if reason in ("max_output_tokens", "content_filter")
                        else "incomplete",
                        path=("status",),
                    ),
                ),
            )
        if (
            status != "completed"
            or len(parts) != 1
            or getattr(parts[0], "type", None) != "output_text"
            or not isinstance(getattr(parts[0], "text", None), str)
        ):
            raise ProviderFailure(ErrorCode.INVALID, usage, diagnostics=(envelope_error,))
        try:
            raw = parts[0].text.encode()
        except UnicodeError:
            raise ProviderFailure(ErrorCode.INVALID, usage, diagnostics=(envelope_error,)) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderFailure(
                ErrorCode.INVALID,
                usage,
                diagnostics=(
                    ValidationIssue(category="CAPACITY", error_type="response_byte_limit"),
                ),
            )
        if request.stage == "ATTRIBUTE_EXTRACTION":
            return AttributeOutput(raw, usage, request)
        return RecognitionOutput(raw, usage, request)
