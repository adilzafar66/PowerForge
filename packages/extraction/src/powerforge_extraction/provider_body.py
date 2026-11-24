"""Assemble the exact JSON body used for dispatch and offline reconstruction."""

import base64
import json

from powerforge_extraction.extraction_profile import stage_request_hash, structured_schema
from powerforge_extraction.identities import identity_hash
from powerforge_shared.config import EXPERIMENTAL_INPUTS


def responses_body(request, model):
    content = [{"type": "input_text", "text": request.text}]
    if request.image is not None:
        content.append(
            {
                "type": "input_image",
                "detail": request.image_detail,
                "image_url": "data:image/png;base64," + base64.b64encode(request.image).decode(),
            }
        )
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
    if request.reasoning_effort is not None:
        body["reasoning"] = {"effort": request.reasoning_effort}
    if request.input_version in EXPERIMENTAL_INPUTS:
        body["service_tier"] = "default"
    return body


def encoded_body(body):
    # Same UTF-8 JSON encoding as the Responses transport (verified by mock HTTP).
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def dispatch_hash(request):
    if request.input_version in EXPERIMENTAL_INPUTS:
        return identity_hash(responses_body(request, request.response_model))
    return stage_request_hash(request.text, request.reasoning_effort)
