"""Independent source geometry/header gold and meaningful negative controls."""

from pathlib import Path

from spatial_layout_support import derive, drawn_table, prepare_pdf


def test_accepted_positioned_pdf_has_new_justified_cells_and_header_ownership():
    source = Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes()
    layout, projection = derive(prepare_pdf(source))
    assert len(layout.tables) == 1
    table = layout.tables[0]
    assert (table.rows, table.columns) == (2, 2)
    assert table.structure_basis == "NATIVE_GEOMETRY_SUPPORTED"
    assert table.header_basis == "GEOMETRIC_LABEL_HEADER"
    cells = {(c["row"], c["column"]): c for c in projection["tables"][0]["cells"]}

    def words(cell):
        return " ".join(r["raw_text"] for r in cell["readings"])

    assert words(cells[0, 0]) == "Equipment"
    assert words(cells[0, 1]) == "Secondary (V)"
    assert words(cells[1, 0]) == "TX-1" and words(cells[1, 1]) == "600"
    assert cells[1, 0]["headers"] == [cells[0, 0]["ref"]]
    assert cells[1, 1]["headers"] == [cells[0, 1]["ref"]]
    assert (
        " ".join(r["raw_text"] for r in projection["tables"][0]["captions"])
        == "2-Winding Transformer Schedule"
    )
    assert layout.printed_text_independently_verified is False


def test_ruled_repeated_values_are_separate_rows_and_notes_do_not_join_table():
    layout, projection = derive(prepare_pdf(drawn_table(nearby=True)))
    assert len(layout.tables) == 1
    table = projection["tables"][0]
    values = [c for c in table["cells"] if c["row"] > 0 and c["column"] == 1]
    assert [c["readings"][0]["raw_text"] for c in values] == ["600", "600"]
    assert values[0]["readings"][0]["source_members"] != values[1]["readings"][0]["source_members"]
    assert not any("999" in r["raw_text"] for c in table["cells"] for r in c["readings"])


def test_clear_borderless_repeated_alignment_supplies_conditional_header_paths():
    layout, projection = derive(prepare_pdf(drawn_table(ruled=False)))
    assert len(layout.tables) == 1
    table = layout.tables[0]
    assert table.method == "REPEATED_ALIGNMENT" and table.rows == 3
    assert all(c.headers for c in table.cells if c.row > 0)


def test_merged_hierarchical_native_headers_have_distinct_nested_paths():
    layout, projection = derive(prepare_pdf(drawn_table(merged=True)))
    assert len(layout.tables) == 1
    cells = projection["tables"][0]["cells"]
    lookup = {c["ref"]: " ".join(r["raw_text"] for r in c["readings"]) for c in cells}
    primary = next(c for c in cells if c["row"] == 2 and c["column"] == 1)
    secondary = next(c for c in cells if c["row"] == 2 and c["column"] == 2)
    assert [lookup[r] for r in primary["headers"]] == ["Voltage", "Primary"]
    assert [lookup[r] for r in secondary["headers"]] == ["Voltage", "Secondary"]


def test_nearby_separate_native_tables_keep_independent_cells_and_repeated_values():
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=700, height=350)
    for left, tag in ((30, "TX-1"), (380, "TX-2")):
        for y in (50, 100, 150):
            page.draw_line((left, y), (left + 280, y))
        for x in (left, left + 140, left + 280):
            page.draw_line((x, 50), (x, 150))
        for x, y, label in (
            (left + 8, 80, "Equipment"),
            (left + 150, 80, "Voltage"),
            (left + 8, 130, tag),
            (left + 150, 130, "600 V"),
        ):
            page.insert_text((x, y), label)
    data = doc.tobytes()
    doc.close()
    layout, projection = derive(prepare_pdf(data))
    assert len(layout.tables) == 2
    tokens = [
        [r["raw_text"] for cell in t["cells"] for r in cell["readings"]]
        for t in projection["tables"]
    ]
    assert sum("TX-1" in table for table in tokens) == 1
    assert sum("TX-2" in table for table in tokens) == 1
    assert not any("TX-1" in table and "TX-2" in table for table in tokens)
    assert all(len(t.cells) == 4 for t in layout.tables)


def test_attribute_rows_keep_cell_geometry_without_inventing_column_headers():
    layout, _ = derive(
        prepare_pdf(
            drawn_table(
                rows=[
                    ("Secondary Voltage", "600 V"),
                    ("Primary Voltage", "12470 V"),
                    ("Rated Capacity", "750 kVA"),
                ]
            )
        )
    )
    assert len(layout.tables) == 1
    assert layout.tables[0].header_basis == "UNRESOLVED"
    assert all(not c.headers for c in layout.tables[0].cells)


def test_delimiter_only_baseline_still_abstains_while_geometry_adds_header_membership():
    import json

    from powerforge_extraction.table_grounding import _grid
    from powerforge_extraction.table_observations import TableObservation

    recording = json.loads(Path("evals/tables/v1/scripted.json").read_text())["cases"][
        "pdf_native_unresolved"
    ]["reconstruction"]["tables"][0]
    table = TableObservation.model_validate(recording)
    assert (
        _grid(table, Path("evals/tables/v1/sources/pdf_native_unresolved.txt").read_text()) is None
    )
    layout, projection = derive(
        prepare_pdf(Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes())
    )
    assert len(layout.tables[0].cells) == 4
    assert len([c for c in layout.tables[0].cells if c.headers]) == 2
    # The existing visible-source gold is independent of both recognizers. Preserve
    # its original reliability labels; compare only source cell/header geometry here.
    corpus = json.loads(Path("evals/tables/v1/corpus.json").read_text())
    gold = next(c for c in corpus["cases"] if c["id"] == "pdf_native_unresolved")["tables"][0]
    cells = projection["tables"][0]["cells"]
    aliases = {c["ref"]: [c["row"], c["column"]] for c in cells}
    actual = {
        (c["row"], c["column"]): (
            " ".join(r["raw_text"] for r in c["readings"]),
            [aliases[h] for h in c["headers"]],
            c["row_span"],
            c["column_span"],
        )
        for c in cells
    }
    assert actual == {
        tuple(c["position"]): (c["text"], c["headers"], c["row_span"], c["column_span"])
        for c in gold["cells"]
    }


def test_value_crossing_a_native_column_boundary_removes_structural_credit():
    from powerforge_provenance.spatial_geometry import Rectangle
    from spatial_layout_support import alter_body

    output = prepare_pdf(drawn_table())

    def cross(body):
        tokens = list(body.tokens)
        i = next(i for i, t in enumerate(tokens) if t.raw_text == "600")
        old = tokens[i]
        tokens[i] = old.model_copy(
            update={
                "source_box": Rectangle(
                    x="260",
                    y=old.source_box.y,
                    width=old.source_box.width,
                    height=old.source_box.height,
                )
            }
        )
        return body.model_copy(update={"tokens": tuple(tokens)})

    changed = alter_body(output, "native", cross)
    layout, _ = derive(changed)
    assert not layout.tables and any(r.reason == "AMBIGUOUS_ASSIGNMENT" for r in layout.unresolved)


def test_overprinted_equal_values_do_not_collapse_into_one_confident_cell():
    from powerforge_provenance.spatial_geometry import Rectangle
    from spatial_layout_support import alter_body

    def overlap(body):
        tokens = list(body.tokens)
        indices = [i for i, t in enumerate(tokens) if t.raw_text == "600"]
        first, second = indices
        source = tokens[first]
        tokens[first] = source.model_copy(
            update={"source_box": Rectangle(**tokens[second].source_box.model_dump())}
        )
        return body.model_copy(update={"tokens": tuple(tokens)})

    layout, _ = derive(alter_body(prepare_pdf(drawn_table()), "native", overlap))
    assert not layout.tables
    assert len([r for r in layout.readings if "AMBIGUOUS_OVERLAP" in r.issues]) >= 2


def test_missing_value_geometry_cannot_borrow_the_equal_value_from_another_row():
    from spatial_layout_support import alter_body

    def remove(body):
        tokens = list(body.tokens)
        i = next(i for i, t in enumerate(tokens) if t.raw_text == "600")
        tokens[i] = tokens[i].model_copy(
            update={"source_box": None, "geometry_unavailable_reason": "UNAVAILABLE"}
        )
        return body.model_copy(update={"tokens": tuple(tokens)})

    layout, _ = derive(alter_body(prepare_pdf(drawn_table()), "native", remove))
    table = layout.tables[0]
    cell = next(c for c in table.cells if c.row == 1 and c.column == 1)
    assert cell.state == "NO_READINGS" and not cell.readings
    assert len(next(c for c in table.cells if c.row == 2 and c.column == 1).readings) == 1


def test_open_native_borders_are_not_silently_truncated_into_a_smaller_complete_table():
    from spatial_layout_support import alter_body

    def remove(body):
        return body.model_copy(
            update={
                "native_primitives": tuple(
                    p
                    for p in body.native_primitives
                    if not all(point.y == 185 for point in p.points)
                )
            }
        )

    layout, _ = derive(alter_body(prepare_pdf(drawn_table()), "native", remove))
    assert not layout.tables and any(
        r.reason == "OPEN_OR_IRREGULAR_GRID" for r in layout.unresolved
    )


def test_unknown_or_qualified_headers_supply_no_inferred_attribute_path():
    for label in ("Secondary (not verified)", "Normal", "N/A"):
        layout, _ = derive(
            prepare_pdf(drawn_table(rows=[("Equipment", label), ("TX-1", "600"), ("TX-2", "480")]))
        )
        assert layout.tables[0].header_basis == "UNRESOLVED"
        assert all(not c.headers for c in layout.tables[0].cells)


def test_sparse_native_cells_are_no_readings_rather_than_fabricated_printed_blanks():
    layout, projection = derive(
        prepare_pdf(
            drawn_table(rows=[("Equipment", "Secondary (V)"), ("TX-1", ""), ("TX-2", "480")])
        )
    )
    cell = next(c for c in layout.tables[0].cells if c.row == 1 and c.column == 1)
    assert cell.state == "NO_READINGS" and not cell.readings


def test_borderless_two_row_fragment_and_unrecognized_headers_do_not_establish_table_ownership():
    for rows in (
        [("Equipment", "Secondary (V)"), ("TX-1", "600")],
        [("Normal", "Standby"), ("TX-1", "600"), ("TX-2", "480")],
    ):
        layout, _ = derive(prepare_pdf(drawn_table(ruled=False, rows=rows)))
        assert not layout.tables


def test_forged_header_geometry_or_source_binding_fails_independent_admission():
    import pytest

    from powerforge_document_processing.layout_derive import admit_layout
    from powerforge_provenance.spatial_geometry import NormalizedRegion
    from spatial_layout_support import sources

    output = prepare_pdf(drawn_table())
    layout, _ = derive(output)
    geometry, text = sources(output)
    table = layout.tables[0]
    cell = table.cells[-1]
    for changed in (
        layout.model_copy(update={"owner": layout.owner.model_copy(update={"page_number": 2})}),
        layout.model_copy(
            update={"prepared": layout.prepared.model_copy(update={"manifest_sha256": "0" * 64})}
        ),
        layout.model_copy(
            update={
                "tables": (
                    table.model_copy(
                        update={
                            "cells": (
                                *table.cells[:-1],
                                cell.model_copy(
                                    update={
                                        "region": NormalizedRegion(
                                            x="0", y="0", width="1", height="1"
                                        )
                                    }
                                ),
                            )
                        }
                    ),
                )
            }
        ),
        layout.model_copy(
            update={
                "tables": (
                    table.model_copy(
                        update={
                            "cells": (
                                *table.cells[:-1],
                                cell.model_copy(update={"headers": (table.cells[0].ref,)}),
                            )
                        }
                    ),
                )
            }
        ),
    ):
        with pytest.raises(ValueError):
            admit_layout(output.manifest, geometry, text, changed)


def test_non_upright_or_slanted_native_text_remains_unresolved():
    from decimal import Decimal

    from spatial_layout_support import alter_body

    for direction in ((-1, 0), (0, 1), ("0.7", "0.7")):

        def turn(body, direction=direction):
            return body.model_copy(
                update={
                    "lines": tuple(
                        line.model_copy(update={"direction": tuple(Decimal(x) for x in direction)})
                        for line in body.lines
                    )
                }
            )

        layout, _ = derive(alter_body(prepare_pdf(drawn_table()), "native", turn))
        assert not layout.tables and any(
            "UNSUPPORTED_DIRECTION" in r.issues for r in layout.readings
        )


def test_competing_borderless_partitions_are_preserved_unresolved():
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    for row, words in enumerate(
        [
            ("Equipment", "Value", "Equipment", "Value"),
            ("TX-1", "600", "TX-2", "480"),
            ("TX-3", "600", "TX-4", "480"),
        ]
    ):
        for col, text in enumerate(words):
            page.insert_text((30 + col * 140, 80 + row * 45), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    layout, _ = derive(prepare_pdf(data))
    assert not layout.tables and any(r.reason == "COMPETING_PARTITIONS" for r in layout.unresolved)


def test_non_english_qualifier_is_not_discarded_during_header_recognition():
    from powerforge_document_processing.layout_grid import header_label

    assert header_label("Secondary (V)")
    assert not header_label("Secondary (未確認)")
    assert not header_label("Secondary (?)")


def test_layout_geometry_is_independent_of_the_callers_decimal_context():
    from decimal import ROUND_UP, localcontext
    from uuid import uuid4

    from powerforge_document_processing.layout_derive import derive_layout
    from spatial_layout_support import sources

    output = prepare_pdf(drawn_table())
    geometry, text = sources(output)
    ids = (uuid4(), uuid4(), uuid4())
    expected = derive_layout(output.manifest, geometry, text, *ids)
    with localcontext() as context:
        context.prec = 5
        context.rounding = ROUND_UP
        assert derive_layout(output.manifest, geometry, text, *ids) == expected


def test_partial_reading_order_keeps_separate_columns_without_flattening_page():
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=600, height=300)
    page.insert_text((30, 80), "Left paragraph words", fontsize=12)
    page.insert_text((330, 80), "Right paragraph words", fontsize=12)
    data = doc.tobytes()
    doc.close()
    layout, _ = derive(prepare_pdf(data))
    assert not layout.tables
    assert len(layout.order) == 4
    assert not any(e.before == "q2" and e.after == "q3" for e in layout.order)
    assert all(e.basis == "SAME_BASELINE" for e in layout.order)


def test_maximum_cell_grid_fits_storage_but_overlarge_provider_projection_fails_explicitly():
    from uuid import uuid4

    import pymupdf
    import pytest

    from powerforge_document_processing.layout_derive import derive_layout, table_context
    from powerforge_provenance.spatial_base import canonical_json
    from spatial_layout_support import sources

    doc = pymupdf.open()
    page = doc.new_page(width=650, height=740)
    for row in range(65):
        page.draw_line((20, 40 + row * 10), (620, 40 + row * 10))
    for col in range(9):
        page.draw_line((20 + col * 75, 40), (20 + col * 75, 680))
    for row in range(64):
        for col in range(8):
            page.insert_text(
                (25 + col * 75, 47.7 if row == 0 else 49 + row * 10),
                "Value" if row == 0 else "W" * 200,
                fontsize=7 if row == 0 else 0.3,
            )
    data = doc.tobytes()
    doc.close()
    output = prepare_pdf(data)
    geometry, text = sources(output)
    layout = derive_layout(output.manifest, geometry, text, uuid4(), uuid4(), uuid4())
    assert len(layout.tables) == 1 and len(layout.tables[0].cells) == 512
    assert len(canonical_json(layout.model_dump(mode="json")).encode()) < 4 * 1024 * 1024
    with pytest.raises(ValueError, match="projection exceeds"):
        table_context(output.manifest, geometry, text, layout)


def test_shape_validity_cannot_promote_a_numeric_marker_to_text_verification():
    import pytest

    from powerforge_provenance.layout_observations import SpatialLayout

    layout, _ = derive(prepare_pdf(drawn_table()))
    with pytest.raises(ValueError, match="boolean"):
        SpatialLayout.model_validate(
            layout.model_copy(update={"printed_text_independently_verified": 0})
        )


def test_structural_order_rejects_cycles_and_foreign_reading_references():
    import pytest

    from powerforge_provenance.layout_observations import ReadingOrder, SpatialLayout

    layout, _ = derive(prepare_pdf(drawn_table()))
    a, b = layout.readings[:2]
    for edges in (
        (
            ReadingOrder(before=a.ref, after=b.ref, basis="SAME_BASELINE"),
            ReadingOrder(before=b.ref, after=a.ref, basis="SAME_BASELINE"),
        ),
        (ReadingOrder(before=a.ref, after="foreign", basis="SAME_BASELINE"),),
    ):
        with pytest.raises(ValueError):
            SpatialLayout.model_validate(layout.model_copy(update={"order": edges}))


def test_successor_preserves_native_table_among_disconnected_drawing_lines():
    from uuid import uuid4

    from powerforge_document_processing.layout_derive import admit_layout, derive_layout
    from spatial_layout_support import disconnected_drawing, sources

    prepared = prepare_pdf(disconnected_drawing())
    geometry, text = sources(prepared)
    arguments = (prepared.manifest, geometry, text, uuid4(), uuid4(), uuid4())
    result = derive_layout(*arguments)
    assert len(result.tables) == 1 and len(result.tables[0].cells) == 6
    assert result.tables[0].structure_basis == "NATIVE_GEOMETRY_SUPPORTED"
    assert not result.unresolved
    assert admit_layout(*arguments[:3], result) == result


def test_candidate_budget_reports_skipped_region_and_keeps_verified_partition(monkeypatch):
    from uuid import uuid4

    import pymupdf

    from powerforge_document_processing import layout_grid
    from powerforge_document_processing.layout_derive import admit_layout, derive_layout
    from spatial_layout_support import sources

    with pymupdf.open(stream=drawn_table(), filetype="pdf") as doc:
        page = doc[0]
        for y in (260, 310, 360):
            page.draw_line((100, y), (500, y))
        for x in (100, 300, 500):
            page.draw_line((x, 260), (x, 360))
        prepared = prepare_pdf(doc.tobytes())
    geometry, text = sources(prepared)
    monkeypatch.setattr(layout_grid, "MAX_GRID_CANDIDATES", 1)
    result = derive_layout(prepared.manifest, geometry, text, uuid4(), uuid4(), uuid4())
    assert len(result.tables) == 1 and len(result.tables[0].cells) == 6
    (skipped,) = result.unresolved
    assert skipped.reason == "GRID_CANDIDATE_LIMIT"
    assert skipped.region is not None and skipped.region.y > result.tables[0].region.bottom
    assert admit_layout(prepared.manifest, geometry, text, result) == result


def test_segment_budget_keeps_readings_and_reports_page_level_limit(monkeypatch):
    from uuid import uuid4

    from powerforge_document_processing import layout_grid
    from powerforge_document_processing.layout_derive import derive_layout
    from spatial_layout_support import sources

    prepared = prepare_pdf(drawn_table())
    geometry, text = sources(prepared)
    monkeypatch.setattr(
        layout_grid, "LAYOUT_POLICY", {**layout_grid.LAYOUT_POLICY, "max_segments": 4}
    )
    result = derive_layout(prepared.manifest, geometry, text, uuid4(), uuid4(), uuid4())
    assert result.readings
    assert any(
        item.reason == "NATIVE_SEGMENT_LIMIT" and item.region is None for item in result.unresolved
    )
