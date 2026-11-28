import json
from pathlib import Path

import pytest
from investigation_a import ARMS, Reply, build_body, digest, score_review
from pydantic import ValidationError

from powerforge_extraction.provider_body import encoded_body


def test_arms_hold_vision_and_settings_fixed():
    original = b"same raster"
    a1, a2, a3 = (build_body(arm, original) for arm in ARMS)
    fixed = {key: value for key, value in a1.items() if key != "instructions"}
    assert a1["input"] == a2["input"] == a3["input"]
    assert a1["input"][0]["content"] == [
        {
            "type": "input_image",
            "detail": "high",
            "image_url": "data:image/png;base64,c2FtZSByYXN0ZXI=",
        }
    ]
    assert "text" not in a1
    for arm in (a2, a3):
        assert {
            key: value for key, value in arm.items() if key not in {"instructions", "text"}
        } == fixed
    assert a2["text"] == a3["text"]
    assert a3["instructions"].startswith(a2["instructions"] + "\n")
    assert "LV_BREAKER" in a3["instructions"]
    assert "LV_BREAKER" not in a2["instructions"]
    assert "reasoning" not in a1


@pytest.mark.parametrize(
    "payload",
    [
        {"equipment": [{"identification": "row", "type": "breaker"}]},
        {"equipment": [{"identification": "  ", "type": "breaker", "tag": None}]},
        {"equipment": [{"identification": "row", "type": "breaker", "tag": 2}]},
        {"equipment": [{"identification": "row", "type": "breaker", "tag": None}] * 129},
        {"equipment": [], "page_context_hash": "unused"},
    ],
)
def test_minimal_contract_rejects_malformed_replies_locally(payload):
    with pytest.raises(ValidationError):
        Reply.model_validate(payload)


def test_minimal_contract_preserves_unknowns_for_review():
    reply = Reply.model_validate(
        {"equipment": [{"identification": "left", "type": None, "tag": None}]}
    )
    assert reply.equipment[0].identification == "left"


def test_adjudication_keeps_detection_separate_from_classification_and_scope():
    assert score_review(
        [
            ("breaker-1", False, True),
            ("breaker-1", False, True),
            ("space", False, False),
            ("upstream", False, False),
            (None, False, False),
        ],
        {"breaker-1", "breaker-2"},
        {"space": "PROVISION", "upstream": "REFERENCE_ONLY"},
    ) == {
        "supplied_detected": 1,
        "missing_supplied": 1,
        "duplicate_claims": 1,
        "prepared_space": 1,
        "reference_only": 1,
        "other_excluded": 0,
        "unresolved": 1,
        "classification_correct": 0,
        "tag_correct": 1,
    }


def test_review_manifest_pins_current_prompts_and_schema():
    manifest = json.loads(Path(__file__).with_name("a-preflight.json").read_text())
    for arm in ARMS:
        body = build_body(arm, b"")
        spec = manifest["arm_specs"][arm]
        assert body["instructions"] == spec["instructions"]
        assert body.get("text") == spec["text"]
        for page in manifest["pages"]:
            pins = page["requests"][arm]
            assert pins["prompt_sha256"] == digest(body["instructions"].encode())
            schema = spec["text"]["format"]["schema"] if spec["text"] else None
            assert pins["schema_sha256"] == (digest(encoded_body(schema)) if schema else None)
    assert manifest["provider_calls"] == 0
