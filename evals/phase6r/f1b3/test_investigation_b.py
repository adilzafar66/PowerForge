import json

from investigation_a import build_body
from investigation_b import build_requests

from powerforge_extraction.provider_body import encoded_body


def test_only_source_supplement_changes():
    page = {
        "readings": [
            {"reading_ref": "r1", "text": "PS", "alternate_texts": ["P5", "P S"]},
            {"reading_ref": "r2", "text": "No geometry", "alternate_texts": []},
        ],
        "layout": {
            "readings": [
                {
                    "ref": "r1",
                    "region": {"x": "0.1", "y": "0.2", "width": "0.3", "height": "0.4"},
                    "issues": ["TRANSCRIPTION_CONFLICT"],
                    "members": ["internal witness"],
                },
                {"ref": "r2", "region": None, "issues": ["MISSING_GEOMETRY"]},
            ],
            "tables": [],
        },
    }
    control = build_body("A3", b"pinned")
    bodies = build_requests(b"pinned", page)
    assert bodies["B1"] == encoded_body(control)
    supplements = {}
    for arm in ("B2", "B3"):
        body = json.loads(bodies[arm])
        supplement = body["input"][0]["content"].pop(0)
        assert body == control
        assert supplement["type"] == "input_text"
        supplements[arm] = supplement["text"]
    assert json.loads(supplements["B3"]) == {"page": page}
    assert 'r1 [0.1,0.2,0.3,0.4] "PS" | alternatives ["P5", "P S"]' in supplements["B2"]
    assert "TRANSCRIPTION_CONFLICT" in supplements["B2"]
    assert "r2 [unpositioned]" in supplements["B2"]
    assert "internal witness" not in supplements["B2"]


def test_frozen_manifest_covers_twelve_matched_slots():
    from investigation_a import HERE
    from live_b import trial_slots

    a = json.loads((HERE / "a-preflight.json").read_bytes())
    b = json.loads((HERE / "b-preflight.json").read_bytes())
    trials = dict(trial_slots(b))
    assert len(trials) == b["max_calls"] == 12
    for historical, page in zip(a["pages"], b["pages"], strict=True):
        assert historical["pdf"] == page["pdf"]
        assert historical["analysis_png_sha256"] == page["image_sha256"]
        assert historical["requests"]["A3"]["body_sha256"] == page["requests"]["B1"]["body_sha256"]
        for arm, request in page["requests"].items():
            name = page["pdf"].removesuffix(".pdf")
            assert trials[f"{name}/1/{arm}"] == trials[f"{name}/2/{arm}"] == request["body_sha256"]


def test_transformer_manifest_pins_two_native_pages_and_twelve_slots():
    from investigation_a import HERE
    from live_b import trial_slots

    manifest = json.loads((HERE / "b-transformers-preflight.json").read_bytes())
    assert {page["pdf"] for page in manifest["pages"]} == {
        "delta-transformer-drawing.pdf",
        "rex-transformer-drawing.pdf",
    }
    assert all(
        page["pdf_page"] == 1 and page["preparation"] == "native" for page in manifest["pages"]
    )
    trials = dict(trial_slots(manifest))
    assert len(trials) == manifest["max_calls"] == 12
    for page in manifest["pages"]:
        for arm, request in page["requests"].items():
            name = page["pdf"].removesuffix(".pdf")
            assert trials[f"{name}/1/{arm}"] == trials[f"{name}/2/{arm}"] == request["body_sha256"]
