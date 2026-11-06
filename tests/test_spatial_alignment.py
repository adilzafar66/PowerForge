"""Authored detached hybrid readings exercise occurrence alignment, not OCR accuracy."""

from decimal import Decimal
from uuid import uuid4

import pytest

from powerforge_document_processing.layout_derive import derive_layout
from powerforge_document_processing.layout_readings import selected_readings
from powerforge_provenance.spatial_geometry import Rectangle
from powerforge_provenance.spatial_sources import PreparedPage
from spatial_support import replace_body, snapshot


def hybrid(native, ocr):
    results = []
    for kind, records in (("NATIVE_PDF", native), ("OCR", ocr)):
        source = snapshot(kind, text="\n".join(r[0] for r in records))
        body = source.body.model_copy(
            update={
                "tokens": tuple(
                    t.model_copy(update={"source_box": Rectangle(x=x, y=y, width=w, height=h)})
                    for t, (_, x, y, w, h) in zip(source.body.tokens, records, strict=True)
                ),
                "lines": tuple(
                    line.model_copy(update={"direction": (Decimal(1), Decimal(0))})
                    for line in source.body.lines
                ),
            }
        )
        results.append(replace_body(source, body))
    first, second = results
    prepared = PreparedPage.model_validate(
        first.prepared.model_copy(
            update={
                "representations": (
                    *first.prepared.representations,
                    *second.prepared.representations,
                ),
                "ocr_decision": "RUN",
            }
        )
    )
    return (
        prepared,
        {"native": first.geometry, "ocr": second.geometry},
        {"native": first.text, "ocr": second.text},
    )


def test_equal_repeated_readings_align_by_location_and_local_context_without_merging_rows():
    native = [
        ("600", 100, 100, 30, 20),
        ("V", 135, 100, 10, 20),
        ("600", 100, 200, 30, 20),
        ("V", 135, 200, 10, 20),
    ]
    # OCR traversal is row-reversed; each occurrence still has its own geometry.
    ocr = native[2:] + native[:2]
    prepared, geometry, text = hybrid(native, ocr)
    layout = derive_layout(prepared, geometry, text, uuid4(), uuid4(), uuid4())
    assert len(layout.readings) == 4 and all(len(r.members) == 2 for r in layout.readings)
    assert all(r.preferred.representation_ref == "native" for r in layout.readings)
    assert all(p.kind == "AGREEMENT" for p in layout.overlaps)
    sixes = [r for r in layout.readings if r.preferred.ref in ("w0", "w2")]
    assert sixes[0].region != sixes[1].region
    assert sixes[0].members[1].ref == "w2" and sixes[1].members[1].ref == "w0"


def test_conflicting_overlapping_transcriptions_keep_both_sources_and_a_disagreement():
    native = [("600", 100, 100, 30, 20), ("V", 135, 100, 10, 20)]
    ocr = [("690", 100, 100, 30, 20), ("V", 135, 100, 10, 20)]
    prepared, geometry, text = hybrid(native, ocr)
    layout = derive_layout(prepared, geometry, text, uuid4(), uuid4(), uuid4())
    assert any(p.kind == "CONFLICT" for p in layout.overlaps)
    assert len([r for r in layout.readings if "TRANSCRIPTION_CONFLICT" in r.issues]) == 2
    assert len([r for r in layout.readings if len(r.members) == 1]) == 4


def test_equal_isolated_strings_do_not_align_without_context_or_geometric_overlap():
    for ocr in ([("600", 100, 100, 30, 20)], [("600", 400, 100, 30, 20)]):
        prepared, geometry, text = hybrid([("600", 100, 100, 30, 20)], ocr)
        layout = derive_layout(prepared, geometry, text, uuid4(), uuid4(), uuid4())
        assert len(layout.readings) == 2 and all(len(r.members) == 1 for r in layout.readings)


def test_split_vs_joined_readings_abstain_from_one_to_many_fusion():
    prepared, geometry, text = hybrid(
        [("600", 100, 100, 30, 20), ("V", 135, 100, 10, 20)], [("600 V", 100, 100, 45, 20)]
    )
    layout = derive_layout(prepared, geometry, text, uuid4(), uuid4(), uuid4())
    assert len(layout.readings) == 3 and all(len(r.members) == 1 for r in layout.readings)
    assert any(p.kind == "AMBIGUOUS" for p in layout.overlaps)


def test_foreign_page_or_unselected_source_bytes_cannot_enter_alignment():
    prepared, geometry, text = hybrid(
        [("600", 100, 100, 30, 20), ("V", 135, 100, 10, 20)],
        [("600", 100, 100, 30, 20), ("V", 135, 100, 10, 20)],
    )
    for data in ({**geometry, "foreign": b"{}"}, {**geometry, "native": geometry["native"] + b" "}):
        with pytest.raises(ValueError):
            derive_layout(prepared, data, text, uuid4(), uuid4(), uuid4())


def test_pair_and_reading_limits_fail_explicitly_instead_of_truncating(monkeypatch):
    from powerforge_document_processing import layout_readings

    prepared, geometry, text = hybrid(
        [("600", 100, 100, 30, 20), ("V", 135, 100, 10, 20)],
        [("600", 100, 100, 30, 20), ("V", 135, 100, 10, 20)],
    )
    monkeypatch.setattr(
        layout_readings, "LAYOUT_POLICY", {**layout_readings.LAYOUT_POLICY, "max_readings": 3}
    )
    with pytest.raises(ValueError, match="reading bound"):
        selected_readings(prepared, geometry, text)


def test_image_reported_geometry_can_support_borderless_structure_without_native_relabeling():
    records = [
        ("Equipment", 100, 100, 100, 20),
        ("Value", 500, 100, 100, 20),
        ("TX-1", 100, 200, 60, 20),
        ("600", 500, 200, 60, 20),
        ("TX-2", 100, 300, 60, 20),
        ("480", 500, 300, 60, 20),
    ]
    prepared, geometry, text = hybrid(records, records)
    # Select the OCR representation only; the source remains explicitly OCR-recognized.
    prepared = PreparedPage.model_validate(
        prepared.model_copy(update={"representations": (prepared.representations[1],)})
    )
    layout = derive_layout(
        prepared, {"ocr": geometry["ocr"]}, {"ocr": text["ocr"]}, uuid4(), uuid4(), uuid4()
    )
    assert len(layout.tables) == 1 and layout.tables[0].structure_basis == "OCR_GEOMETRY_SUPPORTED"
    assert all(m.representation_ref == "ocr" for r in layout.readings for m in r.members)
    assert layout.printed_text_independently_verified is False


def test_slight_box_displacement_aligns_only_matching_occurrences_with_local_context():
    records = [("600", 100, 100, 30, 20), ("V", 135, 100, 10, 20)]
    shifted = [(word, x + 1, y + 1, w, h) for word, x, y, w, h in records]
    prepared, geometry, text = hybrid(records, shifted)
    layout = derive_layout(prepared, geometry, text, uuid4(), uuid4(), uuid4())
    assert len(layout.readings) == 2 and all(len(r.members) == 2 for r in layout.readings)
    assert all(pair.kind == "AGREEMENT" for pair in layout.overlaps)


def test_unaligned_redundant_ocr_is_retained_without_destroying_native_only_structure():
    records = [
        ("Equipment", 100, 100, 100, 20),
        ("Value", 500, 100, 100, 20),
        ("TX-1", 100, 200, 60, 20),
        ("600", 500, 200, 60, 20),
        ("TX-2", 100, 300, 60, 20),
        ("480", 500, 300, 60, 20),
    ]
    prepared, geometry, text = hybrid(records, records)
    layout = derive_layout(prepared, geometry, text, uuid4(), uuid4(), uuid4())
    assert len(layout.readings) == 12  # No unsupported occurrence fusion.
    assert len(layout.tables) == 1
    assert layout.tables[0].structure_basis == "NATIVE_GEOMETRY_SUPPORTED"
    assert sum("NATIVE_PREFERRED_UNALIGNED" in r.issues for r in layout.readings) == 6
    assert all(pair.kind == "AMBIGUOUS" for pair in layout.overlaps)


def test_supplementary_ocr_retains_its_identity_in_a_supported_mixed_partition():
    native = [
        ("Equipment", 100, 100, 100, 20),
        ("Value", 500, 100, 100, 20),
        ("TX-1", 100, 200, 60, 20),
        ("600", 500, 200, 60, 20),
        ("TX-2", 100, 300, 60, 20),
    ]
    prepared, geometry, text = hybrid(native, [("480", 500, 300, 60, 20)])
    layout = derive_layout(prepared, geometry, text, uuid4(), uuid4(), uuid4())
    assert len(layout.tables) == 1
    assert layout.tables[0].structure_basis == "MIXED_GEOMETRY_SUPPORTED"
    assert sum(r.preferred.representation_ref == "ocr" for r in layout.readings) == 1
