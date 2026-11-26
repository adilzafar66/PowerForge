from pathlib import Path

import pymupdf
import pytest
from pydantic import ValidationError
from verify_ground_truth import CORPUS, FIXTURES, Fixture, Page, Table, pdf_rect


@pytest.mark.parametrize("filename", CORPUS)
def test_fixture_covers_every_declared_pdf_page(filename: str) -> None:
    fixture_path = FIXTURES / Path(filename).with_suffix(".json")
    fixture = Fixture.model_validate_json(fixture_path.read_bytes())
    assert fixture.pdf == filename
    assert [page.pdf_page for page in fixture.pages] == list(range(1, CORPUS[filename] + 1))


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"box": (-1, 0, 3, 4)}, "outside the frame"),
        ({"box": (0, 0, 101, 4)}, "outside the frame"),
        ({"legibility": "UNREADABLE"}, "cannot claim a transcription"),
        ({"legibility": "AMBIGUOUS"}, "document non-text or uncertain"),
    ],
)
def test_invalid_annotation_is_rejected(change: dict, error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        Page.model_validate(
            {
                "pdf_page": 1,
                "frame": (100, 100),
                "regions": [
                    {"id": "label", "kind": "value", "box": (0, 0, 3, 4), "text": "225A"} | change
                ],
                "tables": [],
            }
        )


def test_relation_cannot_reference_unknown_annotation() -> None:
    with pytest.raises(ValidationError, match="unknown endpoint"):
        Page.model_validate(
            {
                "pdf_page": 1,
                "frame": (100, 100),
                "regions": [{"id": "label", "kind": "value", "box": (0, 0, 3, 4), "text": "225A"}],
                "tables": [],
                "relations": [{"source": "label", "target": "missing", "observation": "test"}],
            }
        )


def test_merged_cell_cannot_overlap_another_cell() -> None:
    with pytest.raises(ValidationError, match="repeats grid position"):
        Table.model_validate(
            {
                "id": "table",
                "columns": ["left", "right"],
                "cells": [
                    {
                        "row": 0,
                        "column": "left",
                        "column_span": ["left", "right"],
                        "box": (0, 0, 10, 2),
                        "text": "Terminations",
                    },
                    {"row": 0, "column": "right", "box": (5, 0, 10, 2), "text": "Lugs"},
                ],
            }
        )


def test_upright_coordinates_convert_on_rotated_pdf() -> None:
    with pymupdf.open() as doc:
        page = doc.new_page(width=100, height=200)
        page.set_rotation(90)
        assert pdf_rect((0, 0, 50, 50), (200, 100), page) == pymupdf.Rect(0, 150, 50, 200)
