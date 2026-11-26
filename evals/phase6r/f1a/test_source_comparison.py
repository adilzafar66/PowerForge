from types import SimpleNamespace

import pymupdf
from evaluate_sources import (
    extract_native,
    extraction_profile,
    preparation_profile,
    render,
    run_arm,
    settings_for,
)
from PIL import Image, ImageDraw
from source_metrics import Word, score
from source_ocr import owns, selected_tiles
from verify_ground_truth import Page

from extraction_worker.tesseract import configuration
from powerforge_ai.ocr import OCRIdentity


def page_for(text):
    return Page.model_validate(
        {
            "pdf_page": 1,
            "frame": (100, 100),
            "tables": [],
            "regions": [
                {"id": "first", "kind": "value", "box": (0, 0, 45, 20), "text": text},
                {"id": "second", "kind": "value", "box": (45, 0, 95, 20), "text": text},
            ],
        }
    )


def test_repeated_text_only_grounds_at_its_own_location():
    result = score(page_for("100A"), [Word("r1", "100A", (0.5, 0.01, 0.6, 0.03), "NATIVE_PDF")])
    assert result["annotations"]["first"]["status"] == "UNLOCALIZED_TEXT_MATCH"
    assert result["annotations"]["first"]["located_numeric_literals"] == 0
    assert result["annotations"]["second"]["status"] == "EXACT"


def test_display_normalization_does_not_fix_magnitude_or_case():
    gold = page_for("4.50” FP")
    words = [
        Word("r1", '4.50"', (0.01, 0.02, 0.04, 0.06), "OCR"),
        Word("r2", "FP", (0.05, 0.02, 0.08, 0.06), "OCR"),
        Word("r3", '4.5"', (0.5, 0.02, 0.53, 0.06), "OCR"),
        Word("r4", "fp", (0.54, 0.02, 0.57, 0.06), "OCR"),
    ]
    result = score(gold, words)
    assert result["annotations"]["first"]["status"] == "DISPLAY_VARIANT"
    assert result["annotations"]["second"]["status"] == "UNLOCALIZED_TEXT_MATCH"
    assert result["annotations"]["second"]["located_numeric_literals"] == 0


def test_empty_layout_cannot_take_credit_for_geometric_table_text():
    gold = Page.model_validate(
        {
            "pdf_page": 1,
            "frame": (100, 100),
            "regions": [],
            "tables": [
                {
                    "id": "t",
                    "columns": ["label", "value"],
                    "cells": [
                        {"row": 0, "column": "label", "box": (0, 0, 50, 10), "text": "Rating"},
                        {"row": 0, "column": "value", "box": (50, 0, 100, 10), "text": "800A"},
                    ],
                }
            ],
        }
    )
    words = [
        Word("r1", "Rating", (0.05, 0.02, 0.15, 0.06), "OCR"),
        Word("r2", "800A", (0.55, 0.02, 0.65, 0.06), "OCR"),
    ]
    result = score(gold, words, SimpleNamespace(tables=[]))
    assert result["status"] == {"EXACT": 2}
    assert result["structure"] == {"cells": 2, "row_pairs": 1, "label_value_pairs": 1}

    cells = [
        SimpleNamespace(ref="c1", readings=("r1",), row=0, column=0, headers=()),
        SimpleNamespace(ref="c2", readings=("r2",), row=0, column=1, headers=()),
    ]
    result = score(gold, words, SimpleNamespace(tables=[SimpleNamespace(ref="t1", cells=cells)]))
    assert result["structure"]["row_pairs_matched"] == 1
    assert result["structure"]["label_value_pairs_matched"] == 1


def test_regional_selection_is_ink_based_and_halos_have_one_owner():
    image = Image.new("RGB", (400, 600), "white")
    assert list(selected_tiles(image)) == []
    draw = ImageDraw.Draw(image)
    draw.rectangle((160, 60, 240, 75), fill="black")
    tiles = list(selected_tiles(image))
    assert len(tiles) == 2
    assert tiles[0][1][2] > 200
    assert tiles[1][1][0] < 200
    assert sum(owns(core, 200, 70) for core, _ in tiles) == 1


def test_native_pdf_reaches_the_production_request_builder_without_ocr(tmp_path):
    path = tmp_path / "native.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Panel rating 800A")
        doc.save(path)
    data = path.read_bytes()
    digest = "0" * 64
    options = configuration(digest)
    provider = SimpleNamespace(
        settings=options,
        identity=OCRIdentity(
            adapter_version="test-v1",
            engine="tesseract",
            engine_version="5.3.0",
            build_sha256=digest,
            settings_sha256=options.identity_hash,
        ),
    )
    settings = settings_for(provider)
    result, streams, _ = run_arm(
        path,
        data,
        render(path, data, 1),
        1,
        extract_native(data, 1),
        preparation_profile(settings),
        provider,
        extraction_profile(settings),
        "existing",
    )
    assert result["failure"] is None
    assert result["metadata"]["ocr"]["ocr_invocations"] == 0
    assert [word.text for word in streams["packed"]] == ["Panel", "rating", "800A"]
    assert result["metadata"]["packing"]["encoded_body_bytes"] > 0
