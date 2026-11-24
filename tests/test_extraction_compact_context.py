"""Check that the candidate presentation preserves every original source witness."""

from copy import deepcopy
from random import Random

import pytest

from powerforge_extraction.compact_context import (
    MAX_GROUP_CHARS,
    MAX_GROUP_MEMBERS,
    compact_page,
    expand_compact_page,
)
from powerforge_extraction.identities import canonical_json


def reading(index, text, *, modality="OCR", alternatives=None, issues=None, geometry=True):
    region = [str(index / 1000), "0.1", "0.0008", "0.008"] if geometry else [None] * 4
    return [f"q{index}", text, modality, alternatives or [], issues or [], *region]


def page_for(rows):
    return {
        "readings": {"columns": ["reading_ref", "text", "modality"], "rows": rows},
        "layout": {
            "order": {
                "columns": ["before", "after", "basis"],
                "rows": [
                    [first[0], second[0], "SAME_BASELINE"]
                    for first, second in zip(rows, rows[1:], strict=False)
                ],
            },
            "overlaps": [],
            "tables": [],
            "unresolved": [],
        },
    }


def packed(page):
    candidate = deepcopy(page)
    compact_page(candidate)
    assert expand_compact_page(candidate) == page
    return candidate


def test_group_keeps_exact_unicode_offsets_and_repeated_occurrences():
    originals = [
        reading(i, value, modality="NATIVE_PDF")
        for i, value in enumerate(["RÉ🧪", "800", "A", "800", "Code", "Label"])
    ]
    page = page_for(originals)
    candidate = packed(page)
    (group,) = candidate["readings"]["rows"]
    assert group["kind"] == "LINE"
    assert group["members"][0][:3] == ["q0", 0, 3]
    assert group["members"][3][0] == "q3"
    for source, (ref, start, end, *region) in zip(originals, group["members"], strict=True):
        assert (ref, group["text"][start:end], region) == (source[0], source[1], source[-4:])


@pytest.mark.parametrize(
    "kind",
    ["different-modality", "missing-geometry", "rotated", "multiline", "ambiguous", "branched"],
)
def test_unsafe_baseline_keeps_members_standalone(kind):
    rows = [reading(i, "600") for i in range(3)]
    center = rows[1]
    if kind == "different-modality":
        center[2] = "NATIVE_PDF"
    if kind == "missing-geometry":
        center[-4:] = [None] * 4
    if kind == "rotated":
        center[4] = ["UNSUPPORTED_DIRECTION"]
    if kind == "multiline":
        center[1] = "600\nA"
    if kind == "ambiguous":
        center[3] = ["800"]
        center[4] = ["AMBIGUOUS_OVERLAP"]
    page = page_for(rows)
    if kind == "branched":
        page["layout"]["order"]["rows"].append(["q0", "q2", "SAME_BASELINE"])
    assert packed(page)["readings"]["rows"] == rows


def test_preserves_header_paths_support_kinds_and_conflicting_transcriptions():
    rows = [
        reading(i, text, modality="NATIVE_PDF")
        for i, text in enumerate(
            [
                "Rated",
                "System",
                "Current",
                "Listed",
                "By",
                "Code",
                "800",
                "A",
                "maximum",
                "for",
                "this",
                "system",
                "900",
            ]
        )
    ]
    rows[12][3:5] = [["600"], ["TRANSCRIPTION_CONFLICT"]]
    page = page_for(rows)
    layout = page["layout"]
    native = {"representation_ref": "native", "kind": "TOKEN", "ref": "w6"}
    ocr = {"representation_ref": "ocr", "kind": "TOKEN", "ref": "w6"}
    ruling = {"representation_ref": "native", "kind": "NATIVE_PRIMITIVE", "ref": "w6"}
    layout["overlaps"] = [{"left": native, "right": ocr, "kind": "CONFLICT"}]
    layout["reading_sources"] = {"q12": {"members": [native, ocr], "preferred": ocr}}
    layout["unresolved"] = [{"reason": "OVERLAPPING_TABLES", "support": [ruling, ocr]}]
    layout["tables"] = [
        {
            "ref": "t1",
            "cells": [
                {
                    "ref": "h",
                    "state": "READINGS",
                    "readings": [f"q{i}" for i in range(6)],
                    "header_role": "COLUMN",
                    "boundary_support": [ruling],
                    "headers": [],
                },
                {
                    "ref": "c",
                    "state": "READINGS",
                    "readings": [f"q{i}" for i in range(6, 12)],
                    "header_role": "UNRESOLVED",
                    "boundary_support": [ruling],
                    "headers": ["h"],
                },
            ],
        }
    ]
    candidate = packed(page)
    header, data, conflict = candidate["readings"]["rows"]
    assert header["kind"] == data["kind"] == "CELL"
    assert conflict == rows[12]
    assert candidate["layout"]["support"] == [
        ["native", "TOKEN", "w6"],
        ["ocr", "TOKEN", "w6"],
        ["native", "NATIVE_PRIMITIVE", "w6"],
    ]
    assert candidate["layout"]["reading_sources"] == [["q12", [0, 1], 1]]
    assert candidate["layout"]["tables"][0]["cells"][1]["headers"] == ["h"]


def test_group_bounds_and_determinism_over_varied_readings():
    for seed in range(35):
        rng = Random(seed)
        strings = [
            rng.choice(["800", "Ω", "V", "W" * 145, "列", "A\nB"])
            for _ in range(rng.randrange(1, 100))
        ]
        page = page_for([reading(i, text) for i, text in enumerate(strings)])
        candidate = packed(page)
        assert canonical_json(candidate) == canonical_json(packed(page))
        for group in candidate["readings"]["rows"]:
            if isinstance(group, dict):
                assert len(group["members"]) <= MAX_GROUP_MEMBERS
                assert len(group["text"]) <= MAX_GROUP_CHARS
