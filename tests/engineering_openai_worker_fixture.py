"""Test-only worker bootstrap: real OpenAI SDK, transport replaced before task imports.

Run with celery -A engineering_openai_worker_fixture only in explicit integration tests.
It is never packaged into the worker. There is no socket-capable SDK client fallback.
"""

import json
import os
import time
from pathlib import Path

import httpx
import openai

from engineering_openai_support import scripted_observations, sdk_response
from powerforge_extraction.identities import content_hash, identity_hash

AUDIT = Path(os.environ["M5_SDK_AUDIT"])
SCENARIO = os.environ.get("M5_SDK_SCENARIO", "success")
real_openai = openai.OpenAI


def handle(request):
    body = json.loads(request.content)
    name = body["text"]["format"]["name"]
    stage = (
        "EQUIPMENT_RECOGNITION"
        if name == "EquipmentRecognitionResponse"
        else "ATTRIBUTE_EXTRACTION"
    )
    previous = (
        [json.loads(line) for line in AUDIT.read_text().splitlines()] if AUDIT.exists() else []
    )
    first_attribute = stage == "ATTRIBUTE_EXTRACTION" and not any(
        item["stage"] == stage for item in previous
    )
    content = body["input"][0]["content"]
    visual = not any(
        item["type"] == "input_text" and '"source_ref":"native_text"' in item["text"]
        for item in content
    )
    record = {
        "stage": stage,
        "request_id": request.headers["x-client-request-id"],
        "instruction_hash": content_hash(body["instructions"]),
        "input_hash": identity_hash(body["input"]),
        "schema_hash": identity_hash(body["text"]["format"]),
        "visual_only": visual,
        "model": body["model"],
        "reasoning": body.get("reasoning"),
        "max_output_tokens": body["max_output_tokens"],
        "store": body["store"],
        "image_detail": next(
            (item["detail"] for item in content if item["type"] == "input_image"), None
        ),
    }
    with AUDIT.open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    assert not body.get("tools") and body["store"] is False
    if first_attribute and SCENARIO == "transient-attribute":
        return httpx.Response(
            503,
            json={
                "error": {
                    "message": "PRIVATE PROVIDER CONTENT",
                    "type": "server_error",
                    "code": "server_error",
                }
            },
        )
    if first_attribute and SCENARIO == "slow-attribute":
        time.sleep(5)
    payload = (
        {"wrong_stage": True}
        if first_attribute and SCENARIO == "invalid-attribute"
        else scripted_observations(stage, visual=visual)
    )
    return httpx.Response(200, json=sdk_response(payload, model=body["model"]))


def fixture_openai(**kwargs):
    assert kwargs["api_key"] == "fixture-credential" and kwargs["max_retries"] == 0
    return real_openai(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))


openai.OpenAI = fixture_openai

# Export the actual application; its real extraction tasks and coordinator are unchanged.
from extraction_worker.celery_app import celery_app as celery_app  # noqa: E402
