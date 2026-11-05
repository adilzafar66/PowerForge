"""Actual artifact admission, typed cell interpretation and conservative association controls."""

import copy
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from engineering_grounding_support import anchor, page
from powerforge_extraction.contracts import WorkUnitOutput
from powerforge_extraction.grounding import load_page_sources
from powerforge_extraction.table_grounding import context_from_output, convert_table_reconstruction
from powerforge_extraction.table_output import convert_table_interpretation
from table_grounding_support import attribute, claims, converted, equipment, schedule


def test_native_schedule_has_separate_row_groups_exact_values_and_real_cell_citations():
    attrs = [attribute(), attribute("a2", cell="c2_3", value="480", eq="e2")]
    _, layout, target, context, result, _ = converted(
        interpretation=claims(
            [equipment(), equipment("e2", cell="c2_0", expression="TX-2", tag="TX-2")], attrs
        )
    )
    assert len(layout.tables) == 1 and not layout.candidates
    assert context.tables[0].basis == "NATIVE_DELIMITED"
    assert [c.numeric_value for c in result.candidates if c.kind == "ATTRIBUTE_VALUE"] == [
        Decimal("0.6"),
        Decimal("0.48"),
    ]
    assert len(result.source_groups) == 2
    by_id = {e.id: e for e in layout.evidence}
    for candidate in result.candidates:
        for link in [
            citation
            for citation in result.candidate_evidence
            if citation.candidate_id == candidate.id
        ]:
            evidence = by_id[link.evidence_id]
            assert evidence.table_id == layout.tables[0].id
            assert target.text[evidence.text_start : evidence.text_end] == evidence.source_snippet
    value = next(c for c in result.candidates if c.attribute_key == "secondary_voltage")
    assert value.raw_text == "600" and value.raw_unit == "V" and value.unit == "kV"
    assert not result.tables and not result.evidence


def test_attribute_rows_share_one_proven_equipment_context():
    recon, text = schedule(
        [
            ["Equipment", "TX-1"],
            ["Rated Capacity", "750 kVA"],
            ["Secondary Voltage", "600 V"],
            ["Impedance", "5.75%"],
        ],
        title="2-Winding Transformer Specification",
        kind="ATTRIBUTE_ROWS",
    )
    eq = equipment(cell="c0_1")
    attrs = [
        attribute(cell="c2_1", label="c2_0", expression="600 V"),
        attribute(
            "a2",
            cell="c3_1",
            label="c3_0",
            value="5.75",
            expression="5.75%",
            unit="%",
            key="positive_sequence_impedance",
        ),
    ]
    *_, result, _ = converted(recon, claims([eq], attrs), text=text)
    assert len(result.source_groups) == 1
    assert {c.numeric_value for c in result.candidates if c.kind == "ATTRIBUTE_VALUE"} == {
        Decimal("0.6"),
        Decimal("5.75"),
    }


@pytest.mark.parametrize(
    "mutation",
    ["wrong_row", "unknown_type", "qualified_header", "unresolved_layout", "conditional_note"],
)
def test_uncertain_context_is_retained_without_borrowed_mapping(mutation):
    recon, text = schedule()
    response = claims([equipment(), equipment("e2", cell="c2_0", expression="TX-2", tag="TX-2")])
    if mutation == "wrong_row":
        response["attributes"][0]["equipment_ref"] = "e2"
    elif mutation == "unknown_type":
        recon["tables"][0]["title"]["raw_text"] = "Equipment Schedule"
        recon["tables"][0]["title"]["anchors"] = [anchor("Equipment Schedule")]
        recon["tables"][0]["anchors"] = [anchor("Equipment Schedule")]
        text = text.replace("2-Winding Transformer Schedule", "Equipment Schedule")
    elif mutation == "qualified_header":
        c = recon["tables"][0]["cells"][3]
        c["raw_text"] = "Secondary (not verified) (V)"
        c["anchors"] = [anchor(c["raw_text"])]
        text = text.replace("Secondary (V)", c["raw_text"])
    elif mutation == "unresolved_layout":
        text = text.replace("|", " ")
    else:
        recon["tables"][0]["notes"] = [
            dict(
                local_ref="note",
                raw_text="Emergency values not verified",
                anchors=[anchor("Emergency values not verified")],
                ambiguous=False,
                ambiguity_reason=None,
            )
        ]
        text += "\nEmergency values not verified"
    *_, result, _ = converted(recon, response, text=text)
    a = next(c for c in result.candidates if c.kind == "ATTRIBUTE_VALUE")
    assert a.mapping_status == "UNMAPPED" and a.numeric_value is None
    if mutation in {"wrong_row", "unresolved_layout"}:
        assert a.equipment_mention_candidate_id is None and a.source_group_id is None


def test_visual_and_hybrid_relationships_do_not_acquire_native_structural_verification():
    recon, _ = schedule(visual=True)
    *_, context, result, _ = converted(recon, claims(), image=True)
    assert context.tables[0].basis == "VISUAL_REPORTED"
    assert next(
        c for c in result.candidates if c.kind == "ATTRIBUTE_VALUE"
    ).numeric_value == Decimal("0.6")
    assert all(not c.diagnostics["text_verified"] for c in result.candidates)
    for e in context.output.evidence:
        assert e.source_snippet is None and e.text_start is None and e.location.region is None
    recon, text = schedule()
    recon["tables"][0]["anchors"].append(anchor(visual=True))
    *_, context, result, _ = converted(recon, claims(), text=text.replace("|", " "), image=True)
    assert context.tables[0].basis == "VISUAL_REPORTED"
    a = next(c for c in result.candidates if c.kind == "ATTRIBUTE_VALUE")
    assert (
        a.diagnostics["text_verified"]
        and a.diagnostics["interpretation_limit"] == "VISUAL_REPORTED"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "invented_cell",
        "wrong_occurrence",
        "borrowed_tag",
        "wrong_header",
        "wrong_value",
        "wrong_unit",
        "wrong_key",
    ],
)
def test_model_assertions_do_not_override_the_original_source(mutation):
    recon, text = schedule()
    response = claims()
    if mutation == "invented_cell":
        recon["tables"][0]["cells"][7]["raw_text"] = "690"
    elif mutation == "wrong_occurrence":
        recon["tables"][0]["cells"][4]["anchors"] = [anchor("TX-2")]
    elif mutation == "borrowed_tag":
        response["equipment"][0]["observed_tag"] = "TX-2"
    elif mutation == "wrong_header":
        response["attributes"][0]["label_refs"] = ["c0_2"]
    elif mutation == "wrong_value":
        response["attributes"][0]["raw_value"] = "60"
    elif mutation == "wrong_unit":
        response["attributes"][0]["raw_unit"] = "kV"
    elif mutation == "wrong_key":
        response["attributes"][0]["proposed_attribute_key"] = "primary_voltage"
    sources, _ = page(text, stage="TABLE_RECONSTRUCTION")
    output = convert_table_reconstruction(recon, sources)
    if mutation in {"invented_cell", "wrong_occurrence"}:
        assert not output.tables and output.diagnostic_counts == {"rejected_ungrounded": 1}
        return
    target = replace(
        sources,
        spec=replace(
            sources.spec,
            stage="TABLE_INTERPRETATION",
            unit_id=uuid4(),
            unit_key="TABLE_INTERPRETATION:page:000001",
        ),
    )
    context = context_from_output(target, output, sources.spec.unit_id)
    result = convert_table_interpretation(response, target, context)
    assert not any(
        c.mapping_status == "MAPPED" and c.kind == "ATTRIBUTE_VALUE" for c in result.candidates
    )


@pytest.mark.parametrize(
    "field,value,unit,key,expected,status",
    [
        ("Length (ft)", "250", None, "length", Decimal("76.2"), "MAPPED"),
        (
            "Parallel Run Count",
            "9007199254740993",
            None,
            "parallel_run_count",
            9007199254740993,
            "MAPPED",
        ),
        ("Parallel Run Count", "9223372036854775808", None, "parallel_run_count", None, "INVALID"),
        ("Conductor Material", "Cu", None, "conductor_material", "COPPER", "MAPPED"),
        ("Conductor Material", "Copper/Aluminum", None, "conductor_material", None, "UNMAPPED"),
        ("Conductor Size", "4/0 AWG", None, "conductor_size", "4/0 AWG", "MAPPED"),
        ("Length", "10 furlong", "furlong", "length", None, "INVALID"),
    ],
)
def test_exact_registry_values_units_and_failures(field, value, unit, key, expected, status):
    recon, text = schedule([["Equipment", field], ["C-1", value]], title="Cable Schedule")
    eq = equipment(expression="C-1", tag="C-1", typ="CABLE")
    raw_value = "10" if unit else value
    a = attribute(
        cell="c1_1",
        label="c0_1",
        value=raw_value,
        expression=value,
        unit=unit,
        typ="CABLE",
        key=key,
    )
    *_, result, _ = converted(recon, claims([eq], [a]), text=text)
    candidate = next(c for c in result.candidates if c.kind == "ATTRIBUTE_VALUE")
    assert candidate.mapping_status == status
    actual = (
        candidate.numeric_value
        if candidate.value_type == "NUMBER"
        else candidate.integer_value
        if candidate.value_type == "INTEGER"
        else candidate.text_value
    )
    assert actual == expected


def test_false_and_distinct_frame_trip_ratings_survive_shared_cell_evidence():
    recon, text = schedule(
        [["Equipment", "Rating", "Normally Closed"], ["CB-1", "400 AF / 250 AT", "No"]],
        title="LV Breaker thermal-magnetic schedule",
    )
    eq = equipment(expression="CB-1", tag="CB-1", typ="LV_BREAKER")
    attrs = [
        attribute(
            cell="c1_1",
            label="c0_1",
            value="400",
            expression="400 AF",
            unit="AF",
            typ="LV_BREAKER",
            key="frame_rating",
        ),
        attribute(
            "a2",
            cell="c1_1",
            label="c0_1",
            value="250",
            expression="250 AT",
            unit="AT",
            typ="LV_BREAKER",
            key="trip_rating",
        ),
        attribute(
            "a3",
            cell="c1_2",
            label="c0_2",
            value="No",
            unit=None,
            typ="LV_BREAKER",
            key="normally_closed",
        ),
    ]
    *_, result, _ = converted(recon, claims([eq], attrs), text=text)
    by_key = {c.attribute_key: c for c in result.candidates if c.kind == "ATTRIBUTE_VALUE"}
    assert (
        by_key["frame_rating"].numeric_value == 400 and by_key["trip_rating"].numeric_value == 250
    )
    assert by_key["normally_closed"].boolean_value is False
    assert by_key["frame_rating"].raw_text == "400 AF"


def test_corrupt_source_and_context_cannot_be_reused():
    sources, output, target, context, _, storage = converted()
    bad = replace(sources.spec, artifacts=(replace(sources.spec.artifacts[0], sha256="0" * 64),))
    with pytest.raises(ValueError, match="integrity"):
        load_page_sources(bad, storage)
    tampered = copy.deepcopy(output)
    tampered.tables[0].layout.metadata["reliability"]["structure_basis"] = "VISUAL_REPORTED"
    with pytest.raises(ValueError, match="differs"):
        context_from_output(target, tampered, sources.spec.unit_id)
    with pytest.raises(ValueError, match="another pinned"):
        convert_table_interpretation(
            claims(), replace(target, spec=replace(target.spec, page_id=uuid4())), context
        )


def test_empty_and_unreadable_layout_output_never_creates_fabricated_values():
    sources, _ = page("Nothing tabular here", stage="TABLE_RECONSTRUCTION")
    output = convert_table_reconstruction(
        dict(schema_version="table-reconstruction-schema-v1", overflowed=False, tables=[]), sources
    )
    assert output == WorkUnitOutput()
    recon, _ = schedule(visual=True)
    cell = recon["tables"][0]["cells"][7]
    cell.update(state="UNREADABLE", raw_text=None, ambiguous=True, ambiguity_reason="Obscured")
    sources, _ = page(image=True, stage="TABLE_RECONSTRUCTION")
    output = convert_table_reconstruction(recon, sources)
    assert output.tables[0].layout.cells[7].text == ""
    assert output.tables[0].layout.metadata["observation"]["cells"][7]["raw_text"] is None


@pytest.mark.parametrize(
    "header", ["Secondary Voltage", "Rating (not verified)", "Unknown meaning"]
)
def test_value_designations_cannot_discard_conflicting_or_unresolved_headers(header):
    recon, text = schedule(
        [["Equipment", header], ["CB-1", "400 AF"]], title="LV Breaker thermal-magnetic schedule"
    )
    eq = equipment(expression="CB-1", tag="CB-1", typ="LV_BREAKER")
    a = attribute(
        cell="c1_1",
        label="c0_1",
        value="400",
        expression="400 AF",
        unit="AF",
        typ="LV_BREAKER",
        key="frame_rating",
    )
    *_, result, _ = converted(recon, claims([eq], [a]), text=text)
    assert result.candidates[-1].mapping_status == "UNMAPPED"


def test_numeric_identity_cell_does_not_acquire_equipment_type_from_caption():
    recon, text = schedule([["Equipment", "Secondary (V)"], ["750", "600"]])
    eq = equipment(expression="750", tag=None)
    a = attribute(cell="c1_1", label="c0_1")
    *_, result, _ = converted(recon, claims([eq], [a]), text=text)
    assert all(c.mapping_status == "UNMAPPED" for c in result.candidates)


@pytest.mark.parametrize("mutation", ["header", "caption", "truncated", "partial_cell"])
def test_admitted_uncertainty_cannot_be_lost_during_interpretation(mutation):
    recon, text = schedule()
    table = recon["tables"][0]
    if mutation == "truncated":
        table.update(truncated=True, truncation_reason="Table continues outside view")
    else:
        item = (
            table["title"]
            if mutation == "caption"
            else table["cells"][3 if mutation == "header" else 7]
        )
        item.update(ambiguous=True, ambiguity_reason="Uncertain source")
        if mutation == "partial_cell":
            item["state"] = "UNREADABLE"
    *_, result, _ = converted(recon, claims(), text=text)
    assert result.candidates[-1].mapping_status == "UNMAPPED"


def test_repeated_tags_and_values_remain_separate_source_local_observations():
    recon, text = schedule(
        [["Equipment", "Secondary (V)"], ["TX-1", "600"], ["TX-1", "600"], ["TX-1", "600"]]
    )
    eqs = [equipment(f"e{r}", cell=f"c{r}_0") for r in range(1, 4)]
    attrs = [attribute(f"a{r}", cell=f"c{r}_1", label="c0_1", eq=f"e{r}") for r in range(1, 4)]
    _, layout, target, _, result, _ = converted(recon, claims(eqs, attrs), text=text)
    assert len(result.source_groups) == 3
    assert len(result.candidates) == 6
    assert all(c.mapping_status == "MAPPED" for c in result.candidates)
    evidence = [e for e in layout.evidence if e.cell_id in {"c1_1", "c2_1", "c3_1"}]
    assert len({e.text_start for e in evidence}) == 3
    assert all(target.text[e.text_start : e.text_end] == "600" for e in evidence)


@pytest.mark.parametrize(
    "label,key,value,unit,expected",
    [
        ("Three-Phase Fault Current (kA)", "three_phase_fault_current", "25", "kA", Decimal("25")),
        ("SLG Fault Current (kA)", "slg_fault_current", "18", "kA", Decimal("18")),
        ("Three-Phase X/R", "three_phase_x_r", "10", None, Decimal("10")),
        ("SLG X/R", "slg_x_r", "8", None, Decimal("8")),
    ],
)
def test_utility_fault_context_stays_qualified(label, key, value, unit, expected):
    recon, text = schedule([["Equipment", label], ["U-1", value]], title="Utility Source Schedule")
    eq = equipment(expression="U-1", tag="U-1", typ="UTILITY_SOURCE")
    a = attribute(cell="c1_1", label="c0_1", value=value, unit=unit, typ="UTILITY_SOURCE", key=key)
    *_, result, _ = converted(recon, claims([eq], [a]), text=text)
    assert result.candidates[-1].numeric_value == expected


@pytest.mark.parametrize("mutation", ["remote", "other_device"])
def test_caption_cannot_supply_an_unrelated_devices_type(mutation):
    recon, text = schedule()
    if mutation == "remote":
        text = text.replace("Schedule\n", "Schedule\nUnrelated intervening text\n")
    else:
        title = "2-Winding Transformer TX-2"
        text = text.replace("2-Winding Transformer Schedule", title)
        recon["tables"][0]["title"].update(raw_text=title, anchors=[anchor(title)])
        recon["tables"][0]["anchors"] = [anchor(title)]
    *_, result, _ = converted(recon, claims(), text=text)
    assert all(c.mapping_status == "UNMAPPED" for c in result.candidates)


def test_multiple_tables_with_identical_cell_aliases_have_distinct_ownership():
    first, a = schedule()
    second, b = schedule(
        [["Equipment", "Secondary (V)"], ["TX-1", "690"]],
        title="2-Winding Transformer Second Schedule",
    )
    second["tables"][0]["local_ref"] = "t2"
    first["tables"] += second["tables"]
    eq2 = dict(equipment("e2"), table_ref="t2")
    attr2 = dict(attribute("a2", cell="c1_1", label="c0_1", value="690", eq="e2"), table_ref="t2")
    *_, result, _ = converted(
        first, claims([equipment(), eq2], [attribute(), attr2]), text=a + "\n\n" + b
    )
    assert len(result.source_groups) == 2
    assert {c.numeric_value for c in result.candidates if c.kind == "ATTRIBUTE_VALUE"} == {
        Decimal("0.6"),
        Decimal("0.69"),
    }


def test_hybrid_cell_keeps_each_declared_source_without_upgrading_visual_structure():
    recon, text = schedule()
    recon["tables"][0]["anchors"].append(anchor(visual=True))
    recon["tables"][0]["cells"][7]["anchors"].append(anchor(visual=True))
    _, layout, _, context, result, _ = converted(
        recon, claims(), text=text.replace("|", " "), image=True
    )
    es = [e for e in layout.evidence if e.cell_id == "c1_3"]
    assert len(es) == 2 and sum(e.source_snippet is not None for e in es) == 1
    assert len(layout.tables[0].layout.metadata["cell_source_locations"]["c1_3"]) == 2
    assert context.tables[0].basis == "VISUAL_REPORTED"
    assert result.candidates[-1].mapping_status == "MAPPED"
    assert result.candidates[-1].diagnostics["text_verified"]


def test_merged_visual_header_path_preserves_spans_and_unreadable_values():
    import json
    from pathlib import Path

    case = next(
        c
        for c in json.loads(
            (Path(__file__).parent / "fixtures/extraction/table_observations_v1.json").read_text()
        )["cases"]
        if c["id"] == "visual-merged-sparse-unreadable"
    )
    recon = copy.deepcopy(case["reconstruction"])
    recon["tables"][0].update(truncated=False, truncation_reason=None)
    _, layout, _, _, result, _ = converted(recon, case["interpretation"], image=True)
    assert layout.tables[0].layout.cells[0].column_span == 3
    assert result.candidates[1].numeric_value == 400
    assert result.candidates[-1].mapping_status == "UNMAPPED"
    assert result.candidates[-1].raw_text == "2?0 AT"


@pytest.mark.parametrize("parents", [("Voltage (V)", "Secondary"), ("Secondary", "Voltage (V)")])
def test_complete_hierarchical_header_meaning_in_either_reading_order(parents):
    from powerforge_extraction.interpretation_v1 import InterpretationContext
    from powerforge_extraction.table_semantics import _definition

    definition = _definition(
        "TWO_WINDING_TRANSFORMER",
        list(parents),
        InterpretationContext("header meaning", "2-Winding Transformer"),
    )
    assert definition is not None and definition.key == "secondary_voltage"


def test_duplicate_equipment_alias_cannot_upgrade_an_unmapped_published_mention():
    first = equipment(typ="CABLE")
    second = equipment("e2")
    *_, result, _ = converted(interpretation=claims([first, second], [attribute(eq="e2")]))
    assert len(result.candidates) == 2
    assert all(c.mapping_status == "UNMAPPED" for c in result.candidates)


def test_two_tags_in_one_identity_cell_do_not_establish_a_unique_equipment_row():
    recon, text = schedule([["Equipment", "Secondary (V)"], ["TX-1 / TX-2", "600"]])
    eqs = [
        equipment(expression="TX-1 / TX-2"),
        equipment("e2", expression="TX-1 / TX-2", tag="TX-2"),
    ]
    *_, result, _ = converted(
        recon, claims(eqs, [attribute(cell="c1_1", label="c0_1", eq="e2")]), text=text
    )
    assert all(c.mapping_status == "UNMAPPED" for c in result.candidates)


@pytest.mark.parametrize(
    "typ,status",
    [("2-Winding Transformer", "MAPPED"), ("Cable", "UNMAPPED"), ("Widget", "UNMAPPED")],
)
def test_explicit_same_row_type_cannot_be_overridden_by_caption(typ, status):
    recon, text = schedule([["Equipment", "Type", "Secondary (V)"], ["TX-1", typ, "600"]])
    *_, result, _ = converted(
        recon, claims([equipment()], [attribute(cell="c1_2", label="c0_2")]), text=text
    )
    assert result.candidates[-1].mapping_status == status


def test_table_grounding_identity_is_pinned_separately_from_m1_and_6c():
    import json
    from pathlib import Path

    from powerforge_extraction.table_grounding import table_identity

    expected = json.loads(
        (Path(__file__).parent / "fixtures/extraction/table_grounding_v1_identity.json").read_text()
    )
    assert table_identity() == expected


def test_unclassified_header_relationships_do_not_acquire_row_ownership():
    recon, text = schedule()
    for cell in recon["tables"][0]["cells"]:
        cell["header_refs"] = []
    _, layout, _, _, result, _ = converted(recon, claims(), text=text)
    assert layout.tables[0].table_kind == "UNCLASSIFIED"
    assert all(c.mapping_status == "UNMAPPED" for c in result.candidates)
    assert not result.source_groups


def test_tagless_explicit_equipment_expression_is_retained_and_can_map():
    recon, text = schedule(
        [["Equipment", "Secondary (V)"], ["2-Winding Transformer", "600"]],
        title="Equipment Schedule",
    )
    eq = equipment(expression="2-Winding Transformer", tag=None)
    *_, result, _ = converted(
        recon, claims([eq], [attribute(cell="c1_1", label="c0_1")]), text=text
    )
    assert result.candidates[0].mapping_status == "MAPPED"
    assert result.candidates[0].observed_tag is None
    assert result.candidates[-1].numeric_value == Decimal("0.6")


def test_repeated_entire_native_table_remains_structurally_unresolved():
    recon, text = schedule()
    _, output, _, context, result, _ = converted(recon, claims(), text=text + "\n\n" + text)
    assert context.tables[0].basis == "UNRESOLVED"
    assert all(c.mapping_status == "UNMAPPED" for c in result.candidates)
    assert all(e.text_start is None for e in output.evidence)


def test_alternate_excerpts_of_one_value_do_not_duplicate_the_source_claim():
    attrs = [attribute(), attribute("a2", expression="600")]
    *_, result, _ = converted(interpretation=claims(attrs=attrs))
    assert len(result.candidates) == 2
    recon, text = schedule(
        [["Equipment", "Rating"], ["CB-1", "400 AF / 250 AT"]],
        title="LV Breaker thermal-magnetic schedule",
    )
    eq = equipment(expression="CB-1", tag="CB-1", typ="LV_BREAKER")
    attrs = [
        attribute(
            cell="c1_1",
            label="c0_1",
            value="400",
            expression=expression,
            unit="AF",
            typ="LV_BREAKER",
            key="frame_rating",
            ref=f"a{i}",
        )
        for i, expression in enumerate(["400", "400 AF"])
    ]
    *_, result, _ = converted(recon, claims([eq], attrs), text=text)
    assert len(result.candidates) == 2 and result.candidates[-1].numeric_value == 400


@pytest.mark.parametrize(
    "header,value,unit,status",
    [
        ("Frame (A)", "400 AF", "AF", "MAPPED"),
        ("Frame (AT)", "400", "AT", "UNMAPPED"),
        ("Frame (A)", "400 AT", "AT", "UNMAPPED"),
    ],
)
def test_header_and_value_designations_must_agree_with_the_resolved_attribute(
    header, value, unit, status
):
    recon, text = schedule(
        [["Equipment", header], ["CB-1", value]], title="LV Breaker thermal-magnetic schedule"
    )
    eq = equipment(expression="CB-1", tag="CB-1", typ="LV_BREAKER")
    a = attribute(
        cell="c1_1",
        label="c0_1",
        value="400",
        expression=value,
        unit=unit,
        typ="LV_BREAKER",
        key="frame_rating",
    )
    *_, result, _ = converted(recon, claims([eq], [a]), text=text)
    assert result.candidates[-1].mapping_status == status
