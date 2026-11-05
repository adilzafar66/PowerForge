"""Test-only actual worker with the Responses SDK restricted to MockTransport."""

import json
import os
import time
from pathlib import Path

import httpx
import openai

from engineering_openai_support import sdk_response
from powerforge_extraction.identities import content_hash, identity_hash
from table_openai_support import scripted_observations

AUDIT = Path(os.environ["TABLE_SDK_AUDIT"])
SCENARIO = os.environ.get("TABLE_SDK_SCENARIO", "success")
real_openai = openai.OpenAI


def handle(request):
    body = json.loads(request.content)
    name = body["text"]["format"]["name"]
    stage = {
        "TableReconstructionResponse": "TABLE_RECONSTRUCTION",
        "TableInterpretationResponse": "TABLE_INTERPRETATION",
    }[name]
    previous = (
        [json.loads(line) for line in AUDIT.read_text().splitlines()] if AUDIT.exists() else []
    )
    first = not any(r["stage"] == stage for r in previous)
    content = body["input"][0]["content"]
    visual = not any(
        c["type"] == "input_text" and '"source_ref":"native_text"' in c["text"] for c in content
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
        "image_detail": next((c["detail"] for c in content if c["type"] == "input_image"), None),
    }
    with AUDIT.open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    assert body["store"] is False and not body.get("tools")
    if first and stage == "TABLE_INTERPRETATION":
        if SCENARIO == "transient-interpretation":
            return httpx.Response(
                503, json={"error": {"message": "PRIVATE PROVIDER CONTENT", "type": "server_error"}}
            )
        if SCENARIO == "slow-interpretation":
            time.sleep(5)
        if SCENARIO == "invalid-interpretation":
            return httpx.Response(200, json=sdk_response({"wrong_stage": True}))
    payload = scripted_observations(
        stage, visual=visual, empty=SCENARIO == "empty", multiple=SCENARIO == "multiple"
    )
    return httpx.Response(200, json=sdk_response(payload, model=body["model"]))


def fixture_openai(**kwargs):
    assert kwargs["api_key"] == "fixture-credential" and kwargs["max_retries"] == 0
    return real_openai(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))


openai.OpenAI = fixture_openai

from extraction_worker.celery_app import celery_app as celery_app  # noqa: E402
