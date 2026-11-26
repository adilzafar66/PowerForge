from ocr_experiments import Recipe, preprocess, sparse_tiles
from PIL import Image, ImageDraw
from refined_scoring import construction_changes, refined_score
from source_metrics import Word
from verify_ground_truth import Page


def gold_for(text):
    return Page.model_validate(
        {
            "pdf_page": 1,
            "frame": (100, 100),
            "tables": [],
            "regions": [{"id": "value", "kind": "value", "box": (0, 0, 95, 20), "text": text}],
        }
    )


def test_agreeing_alternate_keeps_preferred_match_unambiguous():
    result = refined_score(
        gold_for("600 A"),
        [
            Word("a", "600", (0.1, 0.05, 0.18, 0.08), "NATIVE_PDF"),
            Word("b", "A", (0.2, 0.05, 0.24, 0.08), "NATIVE_PDF"),
        ],
        details={"a": ("native", (("ocr", "600"),), ()), "b": ("native", (("ocr", "A"),), ())},
    )
    assert result["preferred"]["status"] == {"EXACT": 1}
    assert result["available"]["status"] == {"EXACT": 1}
    assert result["unambiguous"]["status"] == {"EXACT": 1}


def test_correct_alternate_is_retained_but_disputed():
    gold = gold_for("600 A")
    native = Word("a", "800", (0.1, 0.05, 0.18, 0.08), "NATIVE_PDF")
    units = Word("b", "A", (0.2, 0.05, 0.24, 0.08), "OCR")
    result = refined_score(
        gold,
        [native, units],
        details={
            "a": ("native", (("ocr", "600"),), ("TRANSCRIPTION_CONFLICT",)),
            "b": ("ocr", (), ()),
        },
    )
    assert result["preferred"]["status"] == {"LOCAL_TRANSCRIPTION_DIFFERS": 1}
    assert result["available"]["status"] == {"EXACT": 1}
    assert result["available"]["totals"]["located_numeric_literals"] == 1
    assert result["unambiguous"]["status"] == {"LOCAL_TRANSCRIPTION_DIFFERS": 1}
    assert result["alt_only"] == ["value"]
    before = refined_score(gold, [Word("x", "600", native.box, "OCR"), units])
    assert construction_changes(before, result) == {"retained_as_alternate": ["value"]}


def test_available_text_cannot_mix_alternates_from_incompatible_witnesses():
    result = refined_score(
        gold_for("600 A"),
        [
            Word("a", "800", (0.1, 0.05, 0.18, 0.08), "NATIVE_PDF"),
            Word("b", "V", (0.2, 0.05, 0.24, 0.08), "NATIVE_PDF"),
        ],
        details={
            "a": ("native", (("ocr1", "600"), ("ocr2", "700")), ()),
            "b": ("native", (("ocr1", "V"), ("ocr2", "A")), ()),
        },
    )
    assert result["available"]["status"] == {"LOCAL_TRANSCRIPTION_DIFFERS": 1}
    assert result["alt_only"] == []


def test_correct_preferred_can_be_ambiguous_and_genuinely_missing_can_be_distinguished():
    gold = gold_for("600")
    word = Word("a", "600", (0.1, 0.05, 0.18, 0.08), "NATIVE_PDF")
    before = refined_score(gold, [word])
    disputed = refined_score(
        gold, [word], details={"a": ("native", (), ("TRANSCRIPTION_CONFLICT",))}
    )
    assert disputed["available"]["status"] == {"EXACT": 1}
    assert disputed["unambiguous"]["totals"]["located_numeric_literals"] == 0
    missing = refined_score(gold, [])
    assert missing["available"]["status"] == {"NO_READING_AT_LOCATION": 1}
    assert construction_changes(before, missing) == {"local_transcript_lost": ["value"]}


def test_excluded_word_blocks_matching_across_disputed_span():
    gold = gold_for("600 A")
    words = [
        Word("a", "600", (0.1, 0.05, 0.18, 0.08), "OCR"),
        Word("b", "V", (0.2, 0.05, 0.23, 0.08), "OCR"),
        Word("c", "A", (0.25, 0.05, 0.28, 0.08), "OCR"),
    ]
    result = refined_score(gold, words, details={"b": ("ocr", (), ("AMBIGUOUS_OVERLAP",))})
    assert result["unambiguous"]["status"] == {"LOCAL_TRANSCRIPTION_DIFFERS": 1}


def test_geometry_reports_wrong_and_ambiguous_links_without_awarding_table_credit():
    gold = Page.model_validate(
        {
            "pdf_page": 1,
            "frame": (100, 100),
            "regions": [],
            "tables": [
                {
                    "id": "correct",
                    "columns": ["label", "value"],
                    "cells": [
                        {"row": 0, "column": "label", "box": (0, 0, 10, 10), "text": "Rating"},
                        {"row": 0, "column": "value", "box": (30, 0, 40, 10), "text": "800A"},
                    ],
                },
                {
                    "id": "nearby",
                    "columns": ["label"],
                    "cells": [
                        {"row": 0, "column": "label", "box": (15, 0, 25, 10), "text": "Other"},
                    ],
                },
                {
                    "id": "tie",
                    "columns": ["label"],
                    "cells": [
                        {"row": 0, "column": "label", "box": (15, 0, 25, 10), "text": "Rival"},
                    ],
                },
            ],
        }
    )
    words = [
        Word("l", "Rating", (0.02, 0.02, 0.08, 0.05), "OCR"),
        Word("v", "800A", (0.32, 0.02, 0.38, 0.05), "OCR"),
        Word("o", "Other", (0.18, 0.02, 0.22, 0.05), "OCR"),
        Word("r", "Rival", (0.18, 0.02, 0.22, 0.05), "NATIVE_PDF"),
    ]
    assert refined_score(gold, words[:2])["geometric_associations"]["label_value"] == {"correct": 1}
    assert refined_score(gold, words[:3])["geometric_associations"]["label_value"] == {
        "incorrect": 1
    }
    result = refined_score(gold, words)
    assert result["geometric_associations"]["label_value"] == {"ambiguous": 1}
    assert result["explicit_structure"].get("label_value_pairs_matched", 0) == 0


def test_geometric_column_and_role_conditional_header_are_separate():
    cells = [
        {"row": 0, "column": "label", "box": (0, 0, 22, 10), "text": "Item"},
        {"row": 0, "column": "value", "box": (25, 0, 50, 10), "text": "Rating"},
        {"row": 1, "column": "label", "box": (0, 12, 22, 22), "text": "Breaker"},
        {"row": 1, "column": "value", "box": (25, 12, 50, 22), "text": "800A"},
    ]
    gold = Page.model_validate(
        {
            "pdf_page": 1,
            "frame": (100, 100),
            "regions": [],
            "tables": [
                {"id": "test", "columns": ["label", "value"], "header_rows": [0], "cells": cells}
            ],
        }
    )
    words = [
        Word(str(i), cell["text"], tuple(value / 100 for value in cell["box"]), "OCR")
        for i, cell in enumerate(cells)
    ]
    result = refined_score(gold, words)
    assert result["geometric_associations"]["column"] == {"correct": 2}
    assert result["geometric_associations"]["header"] == {"correct": 2}


def test_sparse_selection_avoids_ink_already_covered_by_several_native_words():
    image = Image.new("RGB", (400, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 90, 25), fill="black")
    draw.rectangle((310, 10, 390, 25), fill="black")
    native = [
        Word(str(i), "label", (0.02 + i * 0.05, 0.03, 0.04 + i * 0.05, 0.05), "NATIVE_PDF")
        for i in range(3)
    ]
    cores = [core for core, _ in sparse_tiles(image, native)]
    assert cores == [(300, 0, 400, 100)]


def test_long_line_preprocessing_keeps_small_glyph_ink_and_frame():
    image = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.line((10, 20, 350, 20), fill="black")
    draw.line((100, 35, 100, 185), fill="black")
    draw.rectangle((160, 90, 171, 100), fill="black")
    processed = preprocess(image, Recipe(preprocess="remove_lines"))
    assert processed.size == image.size
    assert processed.getpixel((40, 20)) == 255
    assert processed.getpixel((100, 100)) == 255
    assert processed.getpixel((164, 92)) == 0
