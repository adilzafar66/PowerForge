"""Scripted engineering observations for SDK transport and worker tests, never live AI."""

import json
from uuid import uuid4

from engineering_grounding_support import attribute, attributes, equipment, recognition
from powerforge_ai.extraction import ExtractionRequest
from powerforge_extraction.engineering_stages import get_engineering_stage
from powerforge_extraction.identities import canonical_json
from powerforge_extraction.production_profiles import ENGINEERING_OPENAI_PROFILE, production_profile
from powerforge_shared.config import Settings

TEXT = "2-Winding Transformer TX-1\nSecondary Voltage: 600 V"


def profile_for(key=ENGINEERING_OPENAI_PROFILE):
    return production_profile(key, Settings(_env_file=None, extraction_external_enabled=True))


def stage_request(stage="EQUIPMENT_RECOGNITION", *, profile=None, mode="hybrid"):
    profile = profile or profile_for()
    definition = get_engineering_stage(stage)
    return ExtractionRequest(
        work_unit_id=uuid4(),
        unit_key=f"{stage}:page:000001",
        attempt_number=1,
        model=profile.model,
        instructions=definition.render_instructions(
            ["TWO_WINDING_TRANSFORMER"] if stage == "ATTRIBUTE_EXTRACTION" else ()
        ).text,
        schema_version=definition.schema_version,
        timeout_seconds=profile.timeout_seconds,
        max_output_tokens=profile.max_output_tokens,
        response_model=definition.response_model,
        stage=stage,
        text=None if mode == "image" else TEXT,
        image=None if mode == "text" else b"fixture-png",
        image_mime_type=None if mode == "text" else "image/png",
        image_detail=profile.image_detail,
        source_roles=("analysis_image",)
        if mode == "image"
        else ("native_text",)
        if mode == "text"
        else ("native_text", "analysis_image"),
        upstream_context=canonical_json(
            {"equipment": [{"local_ref": "eq1", "raw_expression": "2-Winding Transformer TX-1"}]}
        )
        if stage == "ATTRIBUTE_EXTRACTION"
        else None,
    )


def scripted_observations(stage, *, visual=False):
    if stage == "EQUIPMENT_RECOGNITION":
        return recognition(
            equipment("2-Winding Transformer TX-1", tag="TX-1", visual=visual)
        ).model_dump(mode="json")
    return attributes(attribute(visual=visual)).model_dump(mode="json")


def sdk_response(payload, *, model="gpt-6-luna", status="completed"):
    return {
        "id": "resp_local_fixture",
        "object": "response",
        "created_at": 1,
        "model": model,
        "status": status,
        "error": None,
        "incomplete_details": None,
        "output": [
            {
                "id": "msg_local_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "phase": "final_answer",
                "content": [
                    {"type": "output_text", "text": json.dumps(payload), "annotations": []}
                ],
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 16,
            "total_tokens": 36,
            "input_tokens_details": {"cached_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }
