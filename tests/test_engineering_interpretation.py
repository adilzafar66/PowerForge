"""Semantic authority is local source meaning, not model-proposed registry identifiers."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from engineering_interpretation_support import attribute, equipment
from powerforge_engineering_model.registry import list_equipment_definitions
from powerforge_extraction.interpretation import (
    InterpretationContext,
    interpret_attribute,
    interpret_equipment,
    interpretation_identity,
)
from powerforge_extraction.observations import AttributeObservation, EquipmentObservation

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/extraction/engineering_observations_v1.json").read_text()
)["cases"]


@pytest.mark.parametrize("definition", list_equipment_definitions(), ids=lambda item: item.key)
def test_all_twenty_explicit_registry_type_names_use_the_same_resolver(definition):
    observation, context = equipment(f"{definition.display_name} item-1", definition.key, "item-1")
    result = interpret_equipment(observation, context)
    assert result.mapping_status == "MAPPED"
    assert result.equipment_type_key == definition.key
    assert result.observed_tag == "item-1"
    assert result.attribute_key is None and result.value is None


@pytest.mark.parametrize(
    "source,proposal",
    [
        ("CT-1", "CT"),
        ("BUS-1", "BUS"),
        ("Transformer TX-1", "TWO_WINDING_TRANSFORMER"),
        ("No Cable", "CABLE"),
        ("Cable or Bus", "CABLE"),
        ("LV/HV breaker", "LV_BREAKER"),
        ("LV Breaker?", "LV_BREAKER"),
        ("Flux conditioner", "UNREGISTERED_TYPE"),
        ("Cable C-1", "BUS"),
    ],
)
def test_equipment_uncertainty_and_wrong_proposals_never_force_registered_types(source, proposal):
    result = interpret_equipment(*equipment(source, proposal))
    assert result.mapping_status == "UNMAPPED" and result.equipment_type_key is None


def test_tagless_equipment_and_source_tag_boundaries():
    result = interpret_equipment(*equipment("Two-winding transformer", None))
    assert result.mapping_status == "MAPPED" and result.observed_tag is None
    for invented in ["TX-1", "TX-100"]:
        result = interpret_equipment(
            *equipment("2-Winding Transformer TX-10", "TWO_WINDING_TRANSFORMER", invented)
        )
        assert result.rejected and result.reason_code == "SOURCE_FIELD_MISMATCH"


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case["id"])
def test_curated_source_shapes_now_receive_conservative_interpretations(case):
    headers = {
        item["local_ref"]: item["raw_expression"] for item in case["recognition"]["equipment"]
    }
    results = []
    for item in case["attributes"]["attributes"]:
        if case["native_text"] is not None:
            assert item["raw_expression"] in case["native_text"]
            if item["equipment_ref"] is not None:
                assert headers[item["equipment_ref"]] in case["native_text"]
        observation = AttributeObservation.model_validate(item)
        context = InterpretationContext(
            item["raw_expression"],
            headers.get(item["equipment_ref"]),
            "NATIVE_TEXT" if case["native_text"] else "VISUAL_PAGE",
        )
        results.append(interpret_attribute(observation, context))
    by_key = {item.attribute_key: item for item in results if item.mapping_status == "MAPPED"}
    expected = case["future_expectations"]
    if case["id"] == "transformer-tagged":
        assert by_key["secondary_voltage"].value == Decimal(
            expected["secondary_voltage"]["numeric_value"]
        )
        assert by_key["secondary_voltage"].unit == "kV"
        assert by_key["positive_sequence_impedance"].value == Decimal("5.75")
        assert set(by_key).isdisjoint(expected["forbidden_inferences"])
    elif case["id"] == "breaker-distinct-ratings-and-false":
        assert by_key["frame_rating"].value == Decimal(expected["frame_rating"])
        assert by_key["trip_rating"].value == Decimal(expected["trip_rating"])
        assert by_key["normally_closed"].value is False
        assert set(by_key).isdisjoint(expected["forbidden_inferences"])
    elif case["id"] == "cable-and-integer-precision":
        assert by_key["conductor_material"].value == expected["conductor_material"]
        assert by_key["length"].value == Decimal(expected["length"]["numeric_value"])
        assert by_key["parallel_run_count"].value == int(expected["parallel_run_count"])
    elif case["id"] == "utility-qualified-and-unqualified-fault-data":
        assert by_key["three_phase_fault_current"].value == Decimal("25")
        assert by_key["slg_fault_current"].value == Decimal("15")
        assert results[-1].mapping_status == "UNMAPPED"
    elif case["id"] == "tagless-visual-nameplate":
        assert by_key["secondary_voltage"].value == Decimal("0.6")
        item = EquipmentObservation.model_validate(case["recognition"]["equipment"][0])
        assert (
            interpret_equipment(
                item, InterpretationContext(item.raw_expression, source_kind="VISUAL_PAGE")
            ).observed_tag
            is None
        )
    else:
        assert not by_key and all(item.mapping_status == "UNMAPPED" for item in results)


def test_valid_but_wrong_attribute_key_and_type_proposals_are_not_authoritative():
    observation, context = attribute("Secondary Voltage", "600", "V", "primary_voltage")
    result = interpret_attribute(observation, context)
    assert (
        result.mapping_status == "UNMAPPED" and result.reason_code == "ATTRIBUTE_PROPOSAL_CONFLICT"
    )
    assert result.attribute_key is None and result.value is None and result.unit is None
    assert result.raw_text == "Secondary Voltage: 600 V" and result.raw_value == "600"
    wrong_type = observation.model_copy(update={"proposed_equipment_type": "CABLE"})
    assert interpret_attribute(wrong_type, context).reason_code == "EQUIPMENT_PROPOSAL_CONFLICT"
    no_proposal = observation.model_copy(update={"proposed_attribute_key": None})
    assert interpret_attribute(no_proposal, context).value == Decimal("0.6")


@pytest.mark.parametrize("ambiguous", [False, True])
@pytest.mark.parametrize(
    "field,bad", [("raw_value", "900"), ("raw_unit", "kV"), ("source_label", "Primary Voltage")]
)
def test_source_field_checks_precede_mapping_and_model_uncertainty(field, bad, ambiguous):
    observation, context = attribute("Secondary Voltage", "600", "V", None, ambiguous=ambiguous)
    forged = observation.model_copy(update={field: bad})
    result = interpret_attribute(forged, context)
    assert result.rejected and result.value is None and result.attribute_key is None
    unknown = replace(context, equipment_text="Flux conditioner")
    assert interpret_attribute(forged, unknown).rejected


def test_source_numbers_cannot_be_borrowed_from_a_label_or_changed_in_magnitude():
    observation, context = attribute(
        "3-Phase Fault Current",
        "25",
        "kA",
        "three_phase_fault_current",
        equipment="Utility Source U1",
        equipment_type="UTILITY_SOURCE",
    )
    assert interpret_attribute(observation.model_copy(update={"raw_value": "3"}), context).rejected
    observation, context = attribute("Secondary Voltage", "1e3", "V", "secondary_voltage")
    assert interpret_attribute(observation.model_copy(update={"raw_value": "1"}), context).rejected


@pytest.mark.parametrize(
    "header",
    [
        "LV Breaker CB-1",
        "LV Breaker CB-1 electronic",
        "LV Breaker CB-1 thermal-magnetic electronic",
    ],
)
def test_at_without_clear_thermal_magnetic_context_cannot_become_a_trip_or_pickup(header):
    observation, context = attribute(
        "AT",
        "250",
        "AT",
        "trip_rating",
        statement="250 AT",
        equipment=header,
        equipment_type="LV_BREAKER",
    )
    result = interpret_attribute(observation, context)
    assert result.mapping_status == "UNMAPPED" and result.attribute_key is None
    frame, context = attribute(
        "AF",
        "400",
        "AF",
        "frame_rating",
        statement="400 AF",
        equipment=header,
        equipment_type="LV_BREAKER",
    )
    assert interpret_attribute(frame, context).value == Decimal("400")


def test_isolated_impedance_and_qualified_sequence_distinctions():
    observation, context = attribute(
        "Impedance", "5.5", "%", "positive_sequence_impedance", equipment=None
    )
    assert interpret_attribute(observation, context).reason_code == "NO_EQUIPMENT_CONTEXT"
    for header in [
        "Two-Winding Transformer zero-sequence data",
        "Two-Winding Transformer on alternate base",
    ]:
        assert (
            interpret_attribute(observation, replace(context, equipment_text=header)).mapping_status
            == "UNMAPPED"
        )
    explicit, context = attribute("Zero Sequence Impedance", "5.5", "%", "zero_sequence_impedance")
    assert interpret_attribute(explicit, context).attribute_key == "zero_sequence_impedance"


def test_no_association_or_missing_attribute_is_invented():
    observation, context = attribute("Secondary Voltage", "600", "V", "secondary_voltage")
    assert observation.equipment_ref is None
    result = interpret_attribute(observation, context)
    assert result.mapping_status == "MAPPED"  # Context need not be a persisted equipment mention.
    standalone = interpret_attribute(observation, replace(context, equipment_text=None))
    assert standalone.mapping_status == "UNMAPPED" and standalone.value is None
    assert (
        interpret_attribute(
            observation.model_copy(update={"raw_value": None, "raw_unit": None}), context
        ).reason_code
        == "MISSING_VALUE"
    )


def test_input_context_and_version_are_explicit_boundaries():
    with pytest.raises(ValueError):
        InterpretationContext(" ")
    with pytest.raises(ValueError):
        interpret_attribute(
            *attribute("Secondary Voltage", "600", "V", "secondary_voltage"),
            version="engineering-interpretation-v999",
        )
    identity = interpretation_identity()
    assert identity["version"] == "engineering-interpretation-v1"
    assert len(identity["rules_hash"]) == 64
    assert identity == interpretation_identity()
