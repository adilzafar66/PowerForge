"""Table shape/reference boundaries only; no admitted artifacts or model-quality claims."""

import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from powerforge_extraction.table_layout import (
    CellReliability,
    TableSourceMetadata,
    inspect_layout,
    observation_context,
)
from powerforge_extraction.table_stages import get_table_stage

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/extraction/table_observations_v1.json").read_text()
)["cases"]


def fixture(case_id="transformer-equipment-rows"):
    return copy.deepcopy(next(c for c in FIXTURES if c["id"] == case_id))


def reconstruct(case):
    return get_table_stage("TABLE_RECONSTRUCTION").validate_result(
        case["reconstruction"], available_sources=case["available_sources"]
    )


@pytest.mark.parametrize("case", FIXTURES, ids=lambda c: c["id"])
def test_all_orientations_and_raw_claims_round_trip_without_normalization(case):
    context = reconstruct(case)
    interpreted = get_table_stage("TABLE_INTERPRETATION").validate_result(
        case["interpretation"],
        available_sources=case["available_sources"],
        table_context=context,
    )
    assert context.model_dump(mode="json") == case["reconstruction"]
    assert interpreted.model_dump(mode="json") == case["interpretation"]
    assert all(a.raw_value is None or type(a.raw_value) is str for a in interpreted.attributes)


def test_layout_keeps_merged_blank_unreadable_and_absent_cells_distinct():
    table = reconstruct(fixture("visual-merged-sparse-unreadable")).tables[0]
    layout = inspect_layout(table)
    assert layout.orientation_hint == "EQUIPMENT_ROWS"
    assert len(layout.table.cells) == 8  # Not a manufactured 4x3 rectangle.
    by_ref = {c.local_ref: c for c in layout.table.cells}
    assert by_ref["top"].column_span == 3
    assert by_ref["blank"].state == "BLANK" and by_ref["blank"].raw_text == ""
    assert by_ref["partial"].raw_text == "2?0 AT" and by_ref["partial"].ambiguous
    assert not any(c.row == 3 and c.column in (0, 1) for c in layout.table.cells)
    assert layout.table.truncated and layout.table.truncation_reason
    assert layout.reliability.structure_basis == "UNRESOLVED"
    assert all(c.text_basis == "UNVERIFIED" for c in layout.reliability.cells)
    assert not layout.reliability.structure_evidence_ids
    metadata = {c.cell_ref: c for c in layout.reliability.cells}
    assert metadata["blank"].state == "BLANK"
    assert metadata["partial"].state == "UNREADABLE"
    assert metadata["h1"].header_refs == ["top"]


def test_orientation_stays_an_unverified_hint_and_can_conservatively_abstain():
    table = reconstruct(fixture()).tables[0]
    assert inspect_layout(table).reason == "MODEL_ORIENTATION_PROPOSAL"
    for c in table.cells:
        c.header_refs.clear()
    assert inspect_layout(table).orientation_hint == "UNCLASSIFIED"
    assert inspect_layout(reconstruct(fixture("mixed-conditional-readings")).tables[0])
    unknown = inspect_layout(reconstruct(fixture("flattened-unclassified")).tables[0])
    assert unknown.orientation_hint == "UNCLASSIFIED" and unknown.reason == "UNRESOLVED_LAYOUT"


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate_cell",
        "duplicate_table",
        "duplicate_row",
        "duplicate_column",
        "overlap",
        "outside_grid",
        "zero_span",
        "float_index",
        "bool_index",
        "missing_header",
        "nonheader_ref",
        "self_header",
        "duplicate_header",
        "wrong_header_axis",
        "forged_geometry",
        "forged_offsets",
        "verified_assertion",
        "missing_nullable",
        "invalid_blank",
        "empty_value",
        "uncertain_unreadable",
        "unreadable_header",
        "truncation_without_reason",
        "uncertainty_without_reason",
        "empty_table",
        "overflow",
        "too_many_tables",
        "too_many_rows",
        "too_many_columns",
        "long_cell",
        "unknown_schema",
        "visual_quote",
        "unknown_role",
    ],
)
def test_malformed_or_unsupported_table_assertions_are_rejected(failure):
    case = fixture()
    response = case["reconstruction"]
    table = response["tables"][0]
    c = table["cells"][4]
    if failure == "duplicate_cell":
        c["local_ref"] = "h0"
    elif failure == "duplicate_table":
        response["tables"].append(copy.deepcopy(table))
    elif failure == "duplicate_row":
        table["rows"][1] = table["rows"][0]
    elif failure == "duplicate_column":
        table["columns"][1] = table["columns"][0]
    elif failure == "overlap":
        c["row"] = 0
    elif failure == "outside_grid":
        c["column_span"] = 5
    elif failure == "zero_span":
        c["row_span"] = 0
    elif failure == "float_index":
        c["row"] = 1.0
    elif failure == "bool_index":
        c["row"] = True
    elif failure == "missing_header":
        c["header_refs"] = ["not_on_this_page"]
    elif failure == "nonheader_ref":
        c["header_refs"] = ["v2_0"]
    elif failure == "self_header":
        table["cells"][0]["header_refs"] = ["h0"]
    elif failure == "duplicate_header":
        c["header_refs"] = ["h0", "h0"]
    elif failure == "wrong_header_axis":
        c["header_refs"] = ["h1"]
    elif failure == "forged_geometry":
        c["anchors"][0]["x"] = 0.1
    elif failure == "forged_offsets":
        c["anchors"][0]["text_start"] = 10
    elif failure == "verified_assertion":
        c["text_verified"] = True
    elif failure == "missing_nullable":
        del table["title"]
    elif failure == "invalid_blank":
        c["state"] = "BLANK"
    elif failure == "empty_value":
        c["raw_text"] = ""
    elif failure == "uncertain_unreadable":
        c.update(state="UNREADABLE", raw_text=None)
    elif failure == "unreadable_header":
        c.update(state="BLANK", raw_text="", header_role="COLUMN")
    elif failure == "truncation_without_reason":
        table["truncated"] = True
    elif failure == "uncertainty_without_reason":
        table["ambiguous"] = True
    elif failure == "empty_table":
        table["cells"] = []
    elif failure == "overflow":
        response["overflowed"] = True
    elif failure == "too_many_tables":
        response["tables"] = [dict(table, local_ref=f"t{i}") for i in range(9)]
    elif failure == "too_many_rows":
        table["rows"] = [f"r{i}" for i in range(129)]
    elif failure == "too_many_columns":
        table["columns"] = [f"c{i}" for i in range(33)]
    elif failure == "long_cell":
        c["raw_text"] = "x" * 2001
    elif failure == "unknown_schema":
        response["schema_version"] = "table-reconstruction-schema-v999"
    elif failure == "visual_quote":
        c["anchors"][0].update(kind="VISUAL_PAGE", source_ref="analysis_image")
        case["available_sources"].append("analysis_image")
    elif failure == "unknown_role":
        c["anchors"][0]["source_ref"] = "other_document"
    with pytest.raises((ValidationError, ValueError)):
        reconstruct(case)


def test_header_cycles_are_rejected_even_when_every_reference_is_local_and_aligned():
    case = fixture()
    table = case["reconstruction"]["tables"][0]
    first, second = table["cells"][0], table["cells"][4]
    second["header_role"] = "COLUMN"
    first["header_refs"] = [second["local_ref"]]
    with pytest.raises(ValidationError, match="Cyclic"):
        reconstruct(case)


@pytest.mark.parametrize(
    "failure",
    [
        "table",
        "cell",
        "caption_as_value",
        "blank_value",
        "equipment",
        "cross_table_equipment",
        "duplicate_claim",
        "new_grid",
        "float",
        "boolean",
        "normalized_slot",
    ],
)
def test_interpretation_cannot_rewrite_tables_or_escape_its_reference_scope(failure):
    case = fixture("multiple-tables-repeated-tags")
    context = reconstruct(case)
    data = case["interpretation"]
    c = data["attributes"][0]
    if failure == "table":
        c["table_ref"] = "other"
    elif failure == "cell":
        c["label_refs"] = ["other"]
    elif failure == "caption_as_value":
        c["value_cell_ref"] = "caption"
    elif failure == "blank_value":
        context.tables[0].cells[-1] = (
            context.tables[0].cells[-1].model_copy(update={"state": "BLANK", "raw_text": ""})
        )
    elif failure == "equipment":
        c["equipment_ref"] = "other"
    elif failure == "cross_table_equipment":
        c["equipment_ref"] = "e2"
    elif failure == "duplicate_claim":
        c["local_ref"] = data["equipment"][0]["local_ref"]
    elif failure == "new_grid":
        data["tables"] = []
    elif failure == "float":
        c["raw_value"] = 0.6
    elif failure == "boolean":
        c["raw_value"] = False
    elif failure == "normalized_slot":
        c["numeric_value"] = "400"
    with pytest.raises((ValidationError, ValueError)):
        get_table_stage("TABLE_INTERPRETATION").validate_result(
            data, available_sources=case["available_sources"], table_context=context
        )


@pytest.mark.parametrize("source_text", [None, "2?0 AT"])
def test_unreadable_value_cells_require_some_source_text_before_interpretation(source_text):
    case = fixture("visual-merged-sparse-unreadable")
    case["reconstruction"]["tables"][0]["cells"][-1]["raw_text"] = source_text
    context = reconstruct(case)  # Entirely unreadable cells remain valid layout observations.
    if source_text is None:
        case["interpretation"]["attributes"][-1].update(
            raw_expression="400 A", raw_value="400", raw_unit="A"
        )
        with pytest.raises(ValueError, match="readable source text"):
            get_table_stage("TABLE_INTERPRETATION").validate_result(
                case["interpretation"], available_sources=["analysis_image"], table_context=context
            )
    else:
        result = get_table_stage("TABLE_INTERPRETATION").validate_result(
            case["interpretation"], available_sources=["analysis_image"], table_context=context
        )
        assert result.attributes[-1].ambiguous
        assert result.attributes[-1].raw_expression == source_text
        assert result.attributes[-1].raw_value is None
        # Partial text remains an uncertain observation; M2 must establish actual grounding.


def test_unknown_mapping_tagless_equipment_and_wrong_but_local_association_are_not_verified():
    case = fixture()
    case["interpretation"]["equipment"][0]["observed_tag"] = None
    a = case["interpretation"]["attributes"][0]
    a.update(proposed_attribute_key="flux_alignment", equipment_ref="e2")
    context = reconstruct(case)
    result = get_table_stage("TABLE_INTERPRETATION").validate_result(
        case["interpretation"], available_sources=["native_text"], table_context=context
    )
    assert result.equipment[0].observed_tag is None
    assert result.attributes[0].equipment_ref == "e2"
    assert result.attributes[0].proposed_attribute_key == "flux_alignment"
    assert inspect_layout(context.tables[0]).reliability.structure_basis == "UNRESOLVED"
    # M2 must prove row ownership and source meanings, not trust these shape-valid assertions.


def large_grid(count, text="600"):
    case = fixture()
    table = case["reconstruction"]["tables"][0]
    template = table["cells"][4]
    table.update(rows=[f"r{i}" for i in range(count)], columns=["c0"])
    table["cells"] = [
        dict(
            template,
            local_ref=f"v{i}",
            row=i,
            column=0,
            header_refs=[],
            raw_text=text,
            anchors=[dict(template["anchors"][0], quote=text)],
        )
        for i in range(count)
    ]
    return case


def test_page_cell_total_is_bounded_across_individually_valid_tables():
    case = large_grid(128)
    t = case["reconstruction"]["tables"][0]
    case["reconstruction"]["tables"] = [dict(t, local_ref=f"t{i}") for i in range(5)]
    with pytest.raises(ValidationError, match="total cell bound"):
        reconstruct(case)


def test_native_quote_occurrence_is_not_verified_by_shape_or_reference_validation():
    case = fixture()
    case["reconstruction"]["tables"][0]["cells"][4]["anchors"][0]["quote"] = "Invented"
    layout = inspect_layout(reconstruct(case).tables[0])
    assert all(c.text_basis == "UNVERIFIED" for c in layout.reliability.cells)


def test_context_is_bounded_separate_untrusted_data_and_preserves_sparse_raw_content():
    context = observation_context(reconstruct(fixture("visual-merged-sparse-unreadable")))
    parsed = json.loads(context)
    assert parsed["version"] == "table-observation-context-v1"
    table = parsed["tables"][0]
    assert table["structure_basis"] == "UNRESOLVED"
    assert len(table["cells"]) == 8
    assert not any("anchors" in cell for cell in table["cells"])
    assert table["cells"][-2]["raw_text"] == ""
    with pytest.raises(ValueError, match="context exceeds"):
        observation_context(reconstruct(large_grid(64, "x" * 2000)))


def test_utf8_response_limit_and_nested_container_mutation_are_checked():
    case = large_grid(64, "変" * 2000)
    for c in case["reconstruction"]["tables"][0]["cells"]:
        c["anchors"] *= 4
    with pytest.raises(ValidationError, match="byte limit"):
        reconstruct(case)
    context = reconstruct(fixture())
    context.tables[0].cells[4].header_refs.append("bad")
    with pytest.raises(ValidationError, match="Header reference"):
        get_table_stage("TABLE_INTERPRETATION").validate_result(
            fixture()["interpretation"], available_sources=["native_text"], table_context=context
        )
    with pytest.raises(ValidationError):
        inspect_layout(context.tables[0])


def test_server_metadata_does_not_mistake_valid_shape_for_grounding_proof():
    with pytest.raises(ValidationError, match="requires evidence"):
        TableSourceMetadata(
            version="table-source-metadata-v1",
            structure_basis="NATIVE_DELIMITED",
            structure_evidence_ids=[],
            cells=[],
        )
    with pytest.raises(ValidationError, match="requires evidence"):
        CellReliability(
            cell_ref="c1",
            state="VALUE",
            header_role="NONE",
            header_refs=[],
            text_basis="NATIVE_VERIFIED",
            evidence_ids=[],
        )
    # An evidence ID is a shape requirement. Only the future M2 ownership loader can admit it.
    item = CellReliability(
        cell_ref="c1",
        state="VALUE",
        header_role="NONE",
        header_refs=[],
        text_basis="NATIVE_VERIFIED",
        evidence_ids=[uuid4()],
    )
    assert item.model_dump_json()


def test_exact_source_strings_survive_and_repeated_tags_are_not_merged():
    cable = reconstruct(fixture("cable-exact-source-strings"))
    assert cable.tables[0].title.raw_text.endswith("é🙂")
    assert cable.tables[0].cells[-2].raw_text == "9007199254740993"
    assert cable.tables[0].cells[-1].raw_text == "4/0 AWG"
    repeated = reconstruct(fixture("multiple-tables-repeated-tags"))
    assert len(repeated.tables) == 2
    assert repeated.tables[0].cells[-2].raw_text == repeated.tables[1].cells[-2].raw_text
