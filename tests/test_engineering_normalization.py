"""Exact registry normalization after source-label, context and unit admission checks."""

from dataclasses import replace
from decimal import Decimal

import pytest

from engineering_interpretation_support import attribute
from powerforge_extraction.contracts import CandidateInput
from powerforge_extraction.interpretation import interpret_attribute


@pytest.mark.parametrize(
    "label,value,unit,key,expected,canonical",
    [
        ("Secondary Voltage", "600", "V", "secondary_voltage", "0.6", "kV"),
        ("primary_voltage", "12.47", "kV", "primary_voltage", "12.47", "kV"),
        ("Rated Apparent Power", "0.75", "MVA", "rated_apparent_power", "750", "kVA"),
        ("Temperature Rise", "18", "°F", "temperature_rise", "10", "°C"),
        ("Primary Grounding Resistance", "200", "mΩ", "primary_grounding_resistance", "0.2", "Ω"),
        (
            "Rated Capacity",
            "750.123456789012345678901234567890123456",
            "kVA",
            "rated_apparent_power",
            "750.123456789012345678901234567890123456",
            "kVA",
        ),
    ],
)
def test_supported_representation_changes_use_registry_decimal_semantics(
    label, value, unit, key, expected, canonical
):
    result = interpret_attribute(*attribute(label, value, unit, key))
    assert result.mapping_status == "MAPPED" and type(result.value) is Decimal
    assert result.value == Decimal(expected) and result.unit == canonical
    assert result.raw_value == value and result.raw_unit == unit


def test_explicit_source_header_unit_is_used_but_never_assumed_from_registry():
    observation, context = attribute("Secondary Voltage (V)", "600", None, "secondary_voltage")
    result = interpret_attribute(observation, context)
    assert result.value == Decimal("0.6") and result.raw_unit == "V"
    no_unit, context = attribute("Secondary Voltage", "600", None, "secondary_voltage")
    result = interpret_attribute(no_unit, context)
    assert result.mapping_status == "UNMAPPED" and result.reason_code == "MISSING_UNIT"
    assert result.value is None and result.attribute_key is None and result.unit is None
    invented_unit = no_unit.model_copy(update={"raw_unit": "kV"})
    assert interpret_attribute(invented_unit, context).rejected


def test_source_label_unit_prefix_and_multiple_header_units_are_not_canonical_defaults():
    result = interpret_attribute(*attribute("kVA rating", "750", None, "rated_apparent_power"))
    assert result.mapping_status == "MAPPED" and result.value == Decimal("750")
    assert result.raw_unit == "kVA"
    result = interpret_attribute(
        *attribute("Primary Voltage (V or kV)", "600", None, "primary_voltage")
    )
    assert result.mapping_status == "UNMAPPED" and result.reason_code == "CONFLICTING_SOURCE_UNITS"


def test_percent_shorthand_does_not_silently_add_a_plain_z_alias():
    explicit = interpret_attribute(
        *attribute("%Z", "5.75", "%Z", "positive_sequence_impedance", statement="5.75 %Z")
    )
    assert explicit.mapping_status == "MAPPED" and explicit.value == Decimal("5.75")
    ambiguous = interpret_attribute(*attribute("Z", "5.75", "%", "positive_sequence_impedance"))
    assert ambiguous.mapping_status == "UNMAPPED" and ambiguous.attribute_key is None


@pytest.mark.parametrize("model_unit", [None, "V", "kV"])
def test_conflicting_explicit_units_are_preserved_without_picking_one(model_unit):
    observation, context = attribute(
        "Secondary Voltage (kV)",
        "600",
        model_unit,
        "secondary_voltage",
        statement="Secondary Voltage (kV): 600 V",
    )
    result = interpret_attribute(observation, context)
    assert result.mapping_status == "UNMAPPED" and result.reason_code == "CONFLICTING_SOURCE_UNITS"
    assert result.value is None and result.attribute_key is None


@pytest.mark.parametrize(
    "label,value,unit,key,reason",
    [
        (
            "Positive Sequence Impedance",
            "0.0575",
            "p.u.",
            "positive_sequence_impedance",
            "REGISTRY_NORMALIZATION_FAILED",
        ),
        ("Primary Voltage", "10", "A", "primary_voltage", "REGISTRY_NORMALIZATION_FAILED"),
        ("Primary Voltage", "10", "mW", "primary_voltage", "REGISTRY_NORMALIZATION_FAILED"),
        ("Primary Voltage", "NaN", "kV", "primary_voltage", "INVALID_NUMERIC_VALUE"),
        ("Primary Voltage", "Infinity", "kV", "primary_voltage", "INVALID_NUMERIC_VALUE"),
        ("Primary Voltage", "1e999999999", "kV", "primary_voltage", "NUMBER_OUT_OF_RANGE"),
        ("Primary Voltage", "0e-999999999", "kV", "primary_voltage", "NUMBER_OUT_OF_RANGE"),
    ],
)
def test_failed_normalization_retains_raw_without_any_normalized_slot(
    label, value, unit, key, reason
):
    result = interpret_attribute(*attribute(label, value, unit, key))
    assert result.mapping_status == "INVALID" and result.reason_code == reason
    assert result.raw_value == value and result.raw_unit == unit
    assert result.value is None and result.attribute_key is None and result.value_type is None
    assert result.unit is None


def test_locale_ambiguous_numeric_expression_is_not_silently_rewritten():
    result = interpret_attribute(*attribute("Primary Voltage", "1,000", "V", "primary_voltage"))
    assert result.mapping_status == "UNMAPPED" and result.reason_code == "AMBIGUOUS_NUMERIC_FORMAT"
    assert result.raw_value == "1,000" and result.value is None


@pytest.mark.parametrize(
    "value", ["9007199254740993", "9223372036854775807", "-9223372036854775808"]
)
def test_integer_precision_includes_existing_64_bit_limits_and_string_serialization(value):
    result = interpret_attribute(
        *attribute(
            "Parallel Run Count",
            value,
            None,
            "parallel_run_count",
            equipment="Cable C-1",
            equipment_type="CABLE",
        )
    )
    assert result.mapping_status == "MAPPED" and type(result.value) is int
    assert result.value == int(value)
    # Compatibility check only; no publication or output-converter implementation.
    candidate = CandidateInput(
        kind="ATTRIBUTE_VALUE",
        mapping_status=result.mapping_status,
        raw_text=result.raw_text,
        raw_value=result.raw_value,
        equipment_type_key=result.equipment_type_key,
        attribute_key=result.attribute_key,
        value_type=result.value_type,
        integer_value=result.value,
        unit=result.unit,
    )
    assert candidate.model_dump(mode="json")["integer_value"] == value


@pytest.mark.parametrize(
    "value", ["9223372036854775808", "-9223372036854775809", "1e999999999", "1.5"]
)
def test_nonrepresentable_or_fractional_counts_remain_invalid(value):
    result = interpret_attribute(
        *attribute(
            "Parallel Run Count",
            value,
            None,
            "parallel_run_count",
            equipment="Cable C-1",
            equipment_type="CABLE",
        )
    )
    assert result.mapping_status == "INVALID" and result.raw_value == value
    assert result.value is None


@pytest.mark.parametrize(
    "value,expected",
    [("COPPER", "COPPER"), ("copper", "COPPER"), ("Cu", "COPPER"), ("Al", "ALUMINUM")],
)
def test_enums_are_scoped_to_known_field_meanings(value, expected):
    result = interpret_attribute(
        *attribute(
            "Conductor Material",
            value,
            None,
            "conductor_material",
            equipment="Cable C-1",
            equipment_type="CABLE",
        )
    )
    assert result.mapping_status == "MAPPED" and result.value == expected


@pytest.mark.parametrize("value", ["COPPER?", "Cu/Al", "copper or aluminum", "unknown alloy"])
def test_unknown_or_uncertain_enums_are_unmapped_not_coerced(value):
    result = interpret_attribute(
        *attribute(
            "Conductor Material",
            value,
            None,
            "conductor_material",
            equipment="Cable C-1",
            equipment_type="CABLE",
        )
    )
    assert result.mapping_status == "UNMAPPED" and result.reason_code == "UNKNOWN_ENUM_EXPRESSION"
    assert result.value is None and result.raw_value == value


@pytest.mark.parametrize(
    "value,expected", [("No", False), ("false", False), ("Yes", True), ("TRUE", True)]
)
def test_explicit_boolean_values_do_not_disappear_through_truthiness(value, expected):
    result = interpret_attribute(
        *attribute(
            "Normally Closed",
            value,
            None,
            "normally_closed",
            equipment="LV Breaker CB1",
            equipment_type="LV_BREAKER",
        )
    )
    assert result.mapping_status == "MAPPED" and result.value is expected
    candidate = CandidateInput(
        kind="ATTRIBUTE_VALUE",
        mapping_status=result.mapping_status,
        raw_text=result.raw_text,
        equipment_type_key=result.equipment_type_key,
        attribute_key=result.attribute_key,
        value_type=result.value_type,
        boolean_value=result.value,
    )
    assert candidate.model_dump(mode="json")["boolean_value"] is expected


def test_text_is_preserved_without_catalog_lookups_or_extra_interpretation():
    result = interpret_attribute(
        *attribute(
            "Manufacturer",
            "Schneider Electric",
            None,
            "manufacturer",
            equipment="LV Breaker CB1",
            equipment_type="LV_BREAKER",
        )
    )
    assert result.mapping_status == "MAPPED" and result.value == "Schneider Electric"
    assert result.value_type == "TEXT" and result.unit is None


def test_material_symbols_in_model_identifiers_do_not_become_conductor_material():
    observation, context = attribute(
        "Model", "Al-100", None, "conductor_material", equipment="Cable C1", equipment_type="CABLE"
    )
    result = interpret_attribute(observation, context)
    assert (
        result.mapping_status == "UNMAPPED" and result.reason_code == "ATTRIBUTE_PROPOSAL_CONFLICT"
    )
    model = observation.model_copy(update={"proposed_attribute_key": "model"})
    assert interpret_attribute(model, context).value == "Al-100"


@pytest.mark.parametrize(
    "label,key",
    [("3-Phase X/R Ratio", "three_phase_x_r"), ("Single Line-to-Ground X/R Ratio", "slg_x_r")],
)
def test_qualified_utility_xr_roles_are_distinct_from_unqualified_ratios(label, key):
    observation, context = attribute(
        label, "10", None, key, equipment="Utility Source U1", equipment_type="UTILITY_SOURCE"
    )
    result = interpret_attribute(observation, context)
    assert result.mapping_status == "MAPPED" and result.attribute_key == key
    assert result.value == Decimal("10") and result.unit is None
    unqualified, context = attribute(
        "X/R", "10", None, key, equipment="Utility Source U1", equipment_type="UTILITY_SOURCE"
    )
    assert interpret_attribute(unqualified, context).mapping_status == "UNMAPPED"


def test_registry_horsepower_context_is_respected_instead_of_global_unit_conversion():
    observation, context = attribute(
        "Rated Active Power",
        "1",
        "hp",
        "rated_active_power",
        equipment="Induction Motor M1",
        equipment_type="INDUCTION_MOTOR",
    )
    assert interpret_attribute(observation, context).value == Decimal("0.74569987158227022")
    unsupported = observation.model_copy(update={"proposed_equipment_type": "STATIC_LOAD"})
    result = interpret_attribute(unsupported, replace(context, equipment_text="Static Load L1"))
    assert result.mapping_status == "INVALID" and result.value is None


def test_competing_source_values_and_unknown_labels_are_not_reconciled_or_discarded():
    results = [
        interpret_attribute(*attribute("Secondary Voltage", value, "V", "secondary_voltage"))
        for value in ["600", "690"]
    ]
    assert [result.value for result in results] == [Decimal("0.6"), Decimal("0.69")]
    unknown = interpret_attribute(*attribute("Flux alignment", "42", "quux", "flux_alignment"))
    assert unknown.mapping_status == "UNMAPPED" and unknown.raw_text == "Flux alignment: 42 quux"
