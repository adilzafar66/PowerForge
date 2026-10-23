from dataclasses import replace
from decimal import Decimal

import pytest

from powerforge_engineering_model import (
    REGISTRY,
    AttributeState,
    InformationState,
    RequirementStatus,
    evaluate_requirements,
    get_attribute_definition,
)
from powerforge_engineering_model.definitions import RequirementRule
from powerforge_engineering_model.enums import AttributeValueType, ConditionType
from powerforge_engineering_model.errors import InvalidAttributeValue, UnknownAttribute

PRESENT = InformationState.PRESENT
SATISFIED = RequirementStatus.SATISFIED
UNSATISFIED = RequirementStatus.UNSATISFIED
NOT_APPLICABLE = RequirementStatus.NOT_APPLICABLE
NOT_EVALUATED = RequirementStatus.NOT_EVALUATED


def state(value: object) -> AttributeState:
    return AttributeState(PRESENT, value)


def populated(equipment: str, keys: tuple[str, ...]) -> dict[str, AttributeState]:
    result = {}
    for key in keys:
        attribute = get_attribute_definition(equipment, key)
        value = {
            AttributeValueType.NUMBER: Decimal(1),
            AttributeValueType.INTEGER: 1,
            AttributeValueType.TEXT: "example",
            AttributeValueType.BOOLEAN: False,
            AttributeValueType.ENUM: attribute.allowed_values[0]
            if attribute.allowed_values
            else "",
        }[attribute.value_type]
        result[key] = state(value)
    return result


def results(equipment: str, values: dict, context: dict | None = None) -> dict:
    return {r.rule_id: r for r in evaluate_requirements(equipment, values, context)}


@pytest.mark.parametrize(
    "equipment,rule,first,second",
    [
        (
            "UTILITY_SOURCE",
            "UTILITY_FAULT_DATA",
            ("three_phase_fault_current", "slg_fault_current", "three_phase_x_r", "slg_x_r"),
            (
                "positive_sequence_resistance",
                "positive_sequence_reactance",
                "zero_sequence_resistance",
                "zero_sequence_reactance",
            ),
        ),
        (
            "CABLE",
            "CABLE_ELECTRICAL_DEFINITION",
            ("conductor_material", "conductor_size", "core_count_per_cable", "parallel_run_count"),
            (
                "positive_sequence_resistance",
                "positive_sequence_reactance",
                "zero_sequence_resistance",
                "zero_sequence_reactance",
            ),
        ),
        (
            "STATIC_LOAD",
            "STATIC_LOAD_POWER_DEFINITION",
            ("rated_apparent_power", "power_factor"),
            ("rated_active_power", "rated_reactive_power"),
        ),
        (
            "LUMPED_LOAD",
            "LUMPED_LOAD_POWER_DEFINITION",
            ("rated_apparent_power",),
            ("power_factor",),
        ),
    ],
)
def test_alternative_representations(
    equipment: str, rule: str, first: tuple, second: tuple
) -> None:
    empty = results(equipment, {})[rule]
    assert empty.status == UNSATISFIED
    assert [a.attributes for a in empty.missing_alternatives] == [first, second]
    for alternative in (first, second):
        values = populated(equipment, alternative)
        assert results(equipment, values)[rule].status == SATISFIED
        values.pop(alternative[-1])
        assert results(equipment, values)[rule].status == UNSATISFIED
    if len(first) > 1:
        mixed = populated(equipment, (*first[:-1], *second[:-1]))
        assert results(equipment, mixed)[rule].status == UNSATISFIED


def test_unconditional_requirements_are_separate_from_alternatives() -> None:
    cable = results(
        "CABLE",
        populated(
            "CABLE",
            (
                "conductor_material",
                "conductor_size",
                "core_count_per_cable",
                "parallel_run_count",
            ),
        ),
    )
    assert cable["CABLE_ELECTRICAL_DEFINITION"].status == SATISFIED
    assert cable["REQUIRED:length"].status == UNSATISFIED
    lumped = results("LUMPED_LOAD", {"power_factor": state(Decimal("0.9"))})
    assert lumped["LUMPED_LOAD_POWER_DEFINITION"].status == SATISFIED
    assert lumped["REQUIRED:rated_active_power"].status == UNSATISFIED


@pytest.mark.parametrize("info_state", list(InformationState))
def test_only_present_satisfies_applicable_requirements(info_state: InformationState) -> None:
    value = Decimal(0) if info_state == PRESENT else None
    values = {"rated_active_power": AttributeState(info_state, value)}
    result = results("LUMPED_LOAD", values)["REQUIRED:rated_active_power"]
    assert result.status == (SATISFIED if info_state == PRESENT else UNSATISFIED)


@pytest.mark.parametrize(
    "equipment,rule,selector,selector_value,target",
    [
        (
            "SYNCHRONOUS_GENERATOR",
            "GEN_GROUNDING_RESISTANCE",
            "grounding_configuration",
            "RESISTANCE",
            "grounding_resistance",
        ),
        (
            "SYNCHRONOUS_GENERATOR",
            "GEN_GROUNDING_REACTANCE",
            "grounding_configuration",
            "REACTANCE",
            "grounding_reactance",
        ),
        (
            "TWO_WINDING_TRANSFORMER",
            "XFMR_PRIMARY_GROUND_R",
            "primary_grounding_configuration",
            "RESISTANCE",
            "primary_grounding_resistance",
        ),
        (
            "TWO_WINDING_TRANSFORMER",
            "XFMR_PRIMARY_GROUND_X",
            "primary_grounding_configuration",
            "REACTANCE",
            "primary_grounding_reactance",
        ),
        (
            "TWO_WINDING_TRANSFORMER",
            "XFMR_SECONDARY_GROUND_R",
            "secondary_grounding_configuration",
            "RESISTANCE",
            "secondary_grounding_resistance",
        ),
        (
            "TWO_WINDING_TRANSFORMER",
            "XFMR_SECONDARY_GROUND_X",
            "secondary_grounding_configuration",
            "REACTANCE",
            "secondary_grounding_reactance",
        ),
        (
            "CAPACITOR",
            "CAPACITOR_WYE_GROUNDING",
            "connection_type",
            "WYE",
            "neutral_grounding_type",
        ),
        (
            "LV_BREAKER",
            "LV_BREAKER_THERMAL_TRIP",
            "trip_unit_type",
            "THERMAL_MAGNETIC",
            "trip_rating",
        ),
        (
            "BUS",
            "BUS_SERIES_RATING_ISOLATION",
            "series_rating_applicable",
            True,
            "main_protective_device_isolated",
        ),
        (
            "UPS",
            "UPS_STATIC_BYPASS_INPUT",
            "static_bypass_available",
            True,
            "separate_bypass_input",
        ),
    ],
)
def test_conditional_requirements(
    equipment: str, rule: str, selector: str, selector_value: object, target: str
) -> None:
    assert results(equipment, {})[rule].status == NOT_EVALUATED
    values = {selector: state(selector_value)}
    assert results(equipment, values)[rule].status == UNSATISFIED
    values.update(populated(equipment, (target,)))
    assert results(equipment, values)[rule].status == SATISFIED
    attribute = get_attribute_definition(equipment, selector)
    other = (
        False
        if attribute.value_type == AttributeValueType.BOOLEAN
        else next(v for v in attribute.allowed_values if v != selector_value)
    )
    assert results(equipment, {selector: state(other)})[rule].status == NOT_APPLICABLE


@pytest.mark.parametrize(
    "equipment,rule,selector,value,targets",
    [
        (
            "UPS",
            "UPS_STATIC_BYPASS_RATING",
            "static_bypass_available",
            True,
            ("rated_bypass_current", "bypass_short_circuit_current_rating"),
        ),
        (
            "LV_BREAKER",
            "LV_BREAKER_ELECTRONIC_TRIP",
            "trip_unit_type",
            "ELECTRONIC",
            ("sensor_rating", "long_time_pickup", "trip_unit_model"),
        ),
    ],
)
def test_all_of_requires_every_member(
    equipment: str, rule: str, selector: str, value: object, targets: tuple
) -> None:
    values = {selector: state(value)}
    for key in targets:
        assert results(equipment, values)[rule].status == UNSATISFIED
        values.update(populated(equipment, (key,)))
    assert results(equipment, values)[rule].status == SATISFIED


@pytest.mark.parametrize(
    "equipment,rule,targets",
    [
        (
            "BUS",
            "BUS_SHORT_TIME_PAIR",
            ("short_time_withstand_current", "short_time_withstand_duration"),
        ),
        (
            "HV_BREAKER",
            "HV_BREAKER_SHORT_TIME_PAIR",
            ("short_time_withstand_current", "short_time_withstand_duration"),
        ),
        (
            "UPS",
            "UPS_BYPASS_SHORT_TIME_PAIR",
            ("bypass_short_time_withstand_current", "bypass_short_time_withstand_duration"),
        ),
        (
            "TWO_WINDING_TRANSFORMER",
            "XFMR_INRUSH_POINT",
            ("inrush_current_multiplier", "inrush_current_duration"),
        ),
    ],
)
def test_all_or_none(equipment: str, rule: str, targets: tuple) -> None:
    assert results(equipment, {})[rule].status == NOT_APPLICABLE
    for key in targets:
        assert results(equipment, {key: state(0)})[rule].status == UNSATISFIED
    assert results(equipment, populated(equipment, targets))[rule].status == SATISFIED
    assert (
        results(equipment, {key: AttributeState(InformationState.UNKNOWN) for key in targets})[
            rule
        ].status
        == NOT_APPLICABLE
    )


@pytest.mark.parametrize("reactor_type", ["SERIES", "CURRENT_LIMITING", "FILTER"])
def test_reactor_series_alternatives(reactor_type: str) -> None:
    values = {"reactor_type": state(reactor_type)}
    rule = "REACTOR_SERIES_IMPEDANCE"
    assert results("REACTOR", values)[rule].status == UNSATISFIED
    for key in ["positive_sequence_impedance", "rated_inductance"]:
        assert results("REACTOR", {**values, key: state(1)})[rule].status == SATISFIED
    assert results("REACTOR", values)["REACTOR_SHUNT_RATING"].status == NOT_APPLICABLE
    assert results("REACTOR", values)["REACTOR_CONNECTION"].status == (
        UNSATISFIED if reactor_type == "FILTER" else NOT_APPLICABLE
    )


@pytest.mark.parametrize(
    "reactor_type,rule,key",
    [
        ("SHUNT", "REACTOR_SHUNT_RATING", "rated_reactive_power"),
        ("NEUTRAL_GROUNDING", "REACTOR_NEUTRAL_GROUNDING", "neutral_grounding_impedance"),
    ],
)
def test_other_reactor_conditions(reactor_type: str, rule: str, key: str) -> None:
    values = {"reactor_type": state(reactor_type)}
    assert results("REACTOR", values)[rule].status == UNSATISFIED
    assert results("REACTOR", {**values, key: state(1)})[rule].status == SATISFIED
    assert results("REACTOR", values)["REACTOR_SERIES_IMPEDANCE"].status == NOT_APPLICABLE


EXTERNAL_RULES = [
    ("SYNCHRONOUS_GENERATOR", "GEN_REACTANCE_BASE_POWER", ("reactance_base_power",)),
    ("SYNCHRONOUS_GENERATOR", "GEN_REACTANCE_BASE_VOLTAGE", ("reactance_base_voltage",)),
    ("INDUCTION_MOTOR", "MOTOR_APPARENT_POWER_BASIS", ("full_load_current",)),
    ("VFD", "VFD_OUTPUT_FAULT_DEFINITION", ("output_short_circuit_current",)),
    ("UPS", "UPS_INVERTER_FAULT_CURRENT", ("output_short_circuit_current",)),
]


@pytest.mark.parametrize("equipment,rule,targets", EXTERNAL_RULES)
def test_external_context_is_never_guessed(equipment: str, rule: str, targets: tuple) -> None:
    values = populated(equipment, targets)
    assert results(equipment, {})[rule].status == NOT_EVALUATED
    assert results(equipment, values)[rule].status == NOT_EVALUATED
    assert results(equipment, {}, {rule: False})[rule].status == NOT_APPLICABLE
    assert results(equipment, {}, {rule: True})[rule].status == UNSATISFIED
    assert results(equipment, values, {rule: True})[rule].status == SATISFIED
    with pytest.raises(InvalidAttributeValue):
        evaluate_requirements(equipment, {}, {rule: "false"})
    with pytest.raises(InvalidAttributeValue):
        evaluate_requirements(equipment, {}, {"typo": True})


@pytest.mark.parametrize(
    "row", [r for r in REGISTRY.requirement_rules if isinstance(r, RequirementRule)]
)
def test_every_approved_rule_row_can_be_satisfied(row: RequirementRule) -> None:
    values = populated(row.equipment_type, row.attributes)
    condition = row.condition
    context = {}
    if condition.kind in (ConditionType.ATTRIBUTE_EQUALS, ConditionType.ATTRIBUTE_IN):
        values[condition.attribute] = state(condition.values[0])
    if condition.kind == ConditionType.EXTERNAL_CONTEXT:
        context[condition.context_key] = True
    result = results(row.equipment_type, values, context)[row.rule_id]
    assert result.status == SATISFIED
    assert result.missing_alternatives == ()


@pytest.mark.parametrize("info_state", [s for s in InformationState if s != PRESENT])
def test_unknown_condition_state_does_not_claim_non_applicability(
    info_state: InformationState,
) -> None:
    values = {"static_bypass_available": AttributeState(info_state)}
    assert results("UPS", values)["UPS_STATIC_BYPASS_INPUT"].status == NOT_EVALUATED


def test_invalid_state_inputs_are_rejected_and_inputs_are_not_mutated() -> None:
    for invalid in [
        state(None),
        state("bad"),
        AttributeState(InformationState.MISSING, 1),
        replace(state(1), information_state="PRESENT"),
    ]:
        with pytest.raises(InvalidAttributeValue):
            evaluate_requirements("BUS", {"nominal_voltage": invalid})
    with pytest.raises(UnknownAttribute):
        evaluate_requirements("BUS", {"made_up": state(1)})
    values = {"nominal_voltage": state(Decimal("0.6"))}
    original = values.copy()
    assert evaluate_requirements("BUS", values) == evaluate_requirements("BUS", values)
    assert values == original


def test_none_annotations_are_not_executable_rules() -> None:
    for equipment in ["OVERCURRENT_RELAY", "FUSE", "CT"]:
        assert all(r.rule_id.startswith("REQUIRED:") for r in evaluate_requirements(equipment, {}))
