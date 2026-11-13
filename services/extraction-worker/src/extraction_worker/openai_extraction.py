"""One bounded Responses structured call. Retries belong to persisted work attempts."""

import base64
import json
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from extraction_worker.openai_response_log import save_structured_response
from powerforge_ai.extraction import (
    ErrorCode,
    ExecutionUsage,
    ExtractionRequest,
    ExtractionResponse,
    ProbeResult,
    ProviderFailure,
)
from powerforge_ai.extraction_diagnostics import FailureDetail, validation_issues
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


def _incomplete_detail(reason: str | None) -> FailureDetail:
    if reason == "max_output_tokens":
        return FailureDetail.OUTPUT_TOKEN_LIMIT
    if reason == "content_filter":
        return FailureDetail.CONTENT_FILTERED
    return FailureDetail.INCOMPLETE_RESPONSE


def _raw_terminal_detail(raw_response) -> FailureDetail | None:
    # SDK structured parsing can raise before returning the typed response. Inspect
    # only terminal metadata on the already received HTTP response. Never retain it.
    if raw_response is None or len(raw_response.content) > 2 * 1024 * 1024:
        return None
    try:
        body = json.loads(raw_response.content)
    except (ValueError, RecursionError):
        return None
    if not isinstance(body, dict):
        return None
    if body.get("status") == "failed":
        return FailureDetail.PROVIDER_FAILED_RESPONSE
    if body.get("status") == "incomplete":
        details = body.get("incomplete_details")
        return _incomplete_detail(details.get("reason") if isinstance(details, dict) else None)
    return None


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
        self.response_log_dir = settings.openai_response_log_dir
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
        from powerforge_extraction.enriched_profiles import is_enriched

        enriched = self.profile is not None and is_enriched(self.profile)
        if self.profile is not None:
            try:
                if enriched:
                    from powerforge_extraction.enriched_input import enriched_production_input

                    messages = enriched_production_input(request, self.profile)
                elif isinstance(self.profile, TableProfile):
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
        raw_response = None
        try:
            use_raw = enriched and isinstance(self.client, openai.OpenAI)
            responses = (
                self.client.responses.with_raw_response if use_raw else self.client.responses
            )
            response = responses.parse(
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
            if use_raw:
                raw_response = response
                response = raw_response.parse()
        except ValidationError as exc:
            issues = validation_issues(exc, request.response_model)
            raise ProviderFailure(
                ErrorCode.INVALID,
                detail=_raw_terminal_detail(raw_response)
                or (issues[0].reason if issues else FailureDetail.SDK_PARSE_FAILURE),
                issues=issues,
            ) from None
        except Exception as exc:
            detail = None
            if isinstance(exc, openai.RateLimitError):
                code = ErrorCode.RATE_LIMIT
            elif isinstance(exc, openai.APITimeoutError):
                code = ErrorCode.TIMEOUT
            elif isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
                code = ErrorCode.AUTH
            elif isinstance(exc, openai.APIConnectionError):
                code, detail = ErrorCode.UNAVAILABLE, FailureDetail.TRANSPORT_ERROR
            elif isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
                code, detail = ErrorCode.UNAVAILABLE, FailureDetail.UPSTREAM_SERVER_ERROR
            else:
                code = ErrorCode.INVALID
                if isinstance(exc, openai.LengthFinishReasonError):
                    detail = FailureDetail.OUTPUT_TOKEN_LIMIT
                elif isinstance(exc, openai.ContentFilterFinishReasonError):
                    detail = FailureDetail.CONTENT_FILTERED
                elif isinstance(exc, openai.APIStatusError):
                    detail = FailureDetail.PROVIDER_HTTP_ERROR
                else:
                    detail = _raw_terminal_detail(raw_response) or FailureDetail.SDK_PARSE_FAILURE
            raise ProviderFailure(code, detail=detail) from None
        save_structured_response(
            self.response_log_dir,
            response,
            stage=request.stage,
            schema_version=request.schema_version,
            work_unit_id=str(request.work_unit_id),
            attempt_number=request.attempt_number,
            model=request.model,
        )
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
            raise ProviderFailure(ErrorCode.INVALID, detail=FailureDetail.INVALID_USAGE) from None
        refused = any(
            getattr(c, "type", None) == "refusal"
            for item in (getattr(response, "output", None) or [])
            for c in (getattr(item, "content", None) or [])
        )
        if refused:
            raise ProviderFailure(ErrorCode.REFUSAL, usage)
        status = getattr(response, "status", None)
        if status != "completed":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            detail = (
                FailureDetail.PROVIDER_FAILED_RESPONSE
                if status == "failed"
                else _incomplete_detail(reason)
            )
            raise ProviderFailure(ErrorCode.INVALID, usage, detail=detail)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ProviderFailure(
                ErrorCode.INVALID, usage, detail=FailureDetail.MISSING_PARSED_OUTPUT
            )
        try:
            result = request.response_model.model_validate(
                parsed.model_dump() if isinstance(parsed, BaseModel) else parsed
            )
        except ValidationError as exc:
            issues = validation_issues(exc, request.response_model)
            raise ProviderFailure(
                ErrorCode.INVALID,
                usage,
                detail=issues[0].reason if issues else FailureDetail.SCHEMA_VALIDATION,
                issues=issues,
            ) from None
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
