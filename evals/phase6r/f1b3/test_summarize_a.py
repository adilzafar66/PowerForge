import json

import pytest
from investigation_a import revised_gold
from summarize_a import evaluate, page_scope, tag_verdict


def test_revised_eaton_scope_and_tag_override():
    original, revised, _ = revised_gold()
    document = next(doc for doc in original.development if doc.pdf.startswith("eaton"))
    supplied, excluded = page_scope(document, revised["documents"][document.pdf], 1)
    assert "upstream-reference" not in supplied
    assert excluded["upstream-reference"] == "REFERENCE_ONLY"
    assert excluded["provision-7"] == "PROVISION"
    assert supplied["panel"] == ("BUS", None)


@pytest.mark.parametrize(
    ("anchor", "tag", "verdict"),
    [
        ("panel", "P1", "EXACT"),
        ("panel", "p1", "CASE_ONLY"),
        ("panel", None, "MISSING"),
        ("panel", "P9", "INCORRECT"),
        ("breaker", "B9", "INVENTED"),
        ("breaker", "p1", "WRONG_OWNER"),
        ("breaker", None, "ABSENT_AS_EXPECTED"),
    ],
)
def test_tag_verdict(anchor, tag, verdict):
    assert tag_verdict(anchor, tag, {"panel": ("BUS", "P1"), "breaker": ("LV_BREAKER", None)}) == (
        verdict
    )


@pytest.mark.parametrize("arm", ["A3", "B1", "B2", "B3"])
def test_wrong_recognition_is_scored_and_not_rejected(arm):
    raw = json.dumps(
        {
            "equipment": [
                {"identification": "panel", "type": "LV_BREAKER", "tag": "WRONG"},
                {"identification": "breaker", "type": "UNSUPPORTED", "tag": "P1"},
                {"identification": "upstream", "type": "LV_BREAKER", "tag": None},
            ]
        }
    ).encode()
    review = {
        "observations": [
            {"anchor": "panel", "semantic_classification": "INCORRECT"},
            {"anchor": "breaker", "semantic_classification": "INCORRECT"},
            {"anchor": "upstream", "semantic_classification": "NOT_APPLICABLE"},
        ]
    }
    result = evaluate(
        raw,
        arm,
        review,
        {"panel": ("BUS", "P1"), "breaker": ("LV_BREAKER", None), "other": ("BUS", "P2")},
        {"upstream": "REFERENCE_ONLY"},
        {"BUS", "LV_BREAKER"},
    )
    assert result["registry_key_member_rows"] == 2
    assert result["registry_type_correct_supplied"] == 0
    quality = result["quality"]
    assert quality["classification_correct"] == 0
    assert quality["classification_evaluated"] == 2
    assert quality["reference_only"] == 1
    assert quality["exact_tagged_matches"] == 0
    assert quality["undetected_tagged_occurrences"] == 1
    assert quality["tag_verdict_counts"]["WRONG_OWNER"] == 1
    assert [row["registry_classification"] for row in result["observation_verdicts"]] == [
        "INCORRECT",
        "UNSUPPORTED",
        "NOT_APPLICABLE",
    ]
