"""Bounded successor input envelope over the existing single-call Responses transport."""

import base64
import json

from powerforge_extraction.enriched_profiles import require_enriched, stage_models, stage_schemas
from powerforge_extraction.identities import canonical_json


def enriched_production_input(request, profile):
    require_enriched(profile)
    if (
        profile.provider != "openai"
        or request.stage not in profile.stages
        or request.response_model is not stage_models(profile)[request.stage]
        or request.schema_version != stage_schemas(profile)[request.stage]
        or request.source_roles != ("spatial_readings", "analysis_image")
        or request.text is None
        or request.image is None
        or request.image_mime_type != "image/png"
        or request.model != profile.model
        or request.timeout_seconds != profile.timeout_seconds
        or request.max_output_tokens != profile.max_output_tokens
        or request.image_detail != profile.image_detail
        or (
            (request.stage in ("ATTRIBUTE_EXTRACTION", "TABLE_INTERPRETATION"))
            != (request.upstream_context is not None)
        )
    ):
        raise ValueError("Request differs from its enhanced production profile")
    projection = json.loads(request.text)
    if (
        projection.get("version") != "enriched-source-context-v1"
        or projection.get("untrusted") is not True
    ):
        raise ValueError("Unsupported enhanced source envelope")
    if (
        len(request.text.encode()) > min(131072, profile.max_input_bytes)
        or len(request.text) > profile.max_text_chars
        or len(request.image) > profile.max_input_bytes
        or len(request.text.encode())
        + len(request.image)
        + len((request.upstream_context or "").encode())
        > profile.max_total_input_bytes
        or len(request.instructions.encode()) > profile.max_instruction_bytes
        or len((request.upstream_context or "").encode()) > profile.max_upstream_bytes
    ):
        raise ValueError("Enhanced provider input exceeds its pinned bounds")
    content = [
        dict(
            type="input_text",
            text=canonical_json(
                dict(
                    version="enriched-provider-source-envelope-v1",
                    untrusted=True,
                    source=projection,
                )
            ),
        ),
        dict(
            type="input_text",
            text="Untrusted pinned analysis_image; printed text is not independently verified.",
        ),
        dict(
            type="input_image",
            detail=request.image_detail,
            image_url="data:image/png;base64," + base64.b64encode(request.image).decode(),
        ),
    ]
    messages = [dict(role="user", content=content)]
    if request.upstream_context is not None:
        messages.append(
            dict(
                role="user",
                content=[
                    dict(
                        type="input_text",
                        text=canonical_json(
                            dict(
                                version="enriched-provider-upstream-v1",
                                untrusted=True,
                                observations=json.loads(request.upstream_context),
                            )
                        ),
                    )
                ],
            )
        )
    return messages
