from decimal import Decimal, localcontext

import pytest

from powerforge_engineering_model import (
    normalize_attribute_value,
    normalize_value,
    supported_input_units,
)
from powerforge_engineering_model.errors import (
    IncompatibleUnit,
    InvalidAttributeValue,
    InvalidEnumValue,
    UnknownUnit,
)
from powerforge_engineering_model.units import UnitSemanticContext


@pytest.mark.parametrize(
    "value,source,target,expected",
    [
        (1000, "V", "kV", "1"),
        (1, "MV", "kV", "1000"),
        (1000, "A", "kA", "1"),
        (1000, "VA", "kVA", "1"),
        (1000, "kVA", "MVA", "1"),
        (1000, "W", "kW", "1"),
        (1000, "kW", "MW", "1"),
        (1000, "var", "kvar", "1"),
        (1000, "kvar", "Mvar", "1"),
        (1000, "mΩ", "Ω", "1"),
        (1000, "Ω", "kΩ", "1"),
        (1, "Ω/m", "Ω/km", "1000"),
        ("304.8", "Ω/1000 ft", "Ω/m", "1"),
        (1000, "mm", "m", "1"),
        (1, "ft", "m", "0.3048"),
        (1, "in", "mm", "25.4"),
        (1, "km", "m", "1000"),
        (1, "cm", "mm", "10"),
        (1000, "ms", "s", "1"),
        (1000, "nF", "µF", "1"),
        (1, "mF", "µF", "1000"),
        (1000, "µH", "mH", "1"),
        (1000, "mH", "H", "1"),
        (32, "°F", "°C", "0"),
        (212, "°F", "°C", "100"),
        (-40, "°F", "°C", "-40"),
        (60, "Hz", "Hz", "60"),
        (1800, "rpm", "rpm", "1800"),
        (5, "%", "%", "5"),
        ("0.05", "p.u.", "p.u.", "0.05"),
    ],
)
def test_conversions_both_directions(
    value: object, source: str, target: str, expected: str
) -> None:
    assert normalize_value(value, source, target) == Decimal(expected)
    assert normalize_value(Decimal(expected), target, source) == Decimal(str(value))


@pytest.mark.parametrize(
    "source,target",
    [
        ("kV", "A"),
        ("kW", "kVA"),
        ("kvar", "kW"),
        ("Ω", "Ω/km"),
        ("%", "p.u."),
        ("p.u.", "%"),
        (None, "m"),
        ("m", None),
    ],
)
def test_incompatible_dimensions(source: str | None, target: str | None) -> None:
    with pytest.raises(IncompatibleUnit):
        normalize_value(1, source, target)


@pytest.mark.parametrize("unit", ["watts", "", "uF", "K", "furlong"])
def test_unknown_units_rejected(unit: str) -> None:
    with pytest.raises(UnknownUnit):
        normalize_value(1, unit, unit)


@pytest.mark.parametrize("value", [True, False, None, "bad", "NaN", "Infinity", float("inf"), []])
def test_invalid_numbers_rejected(value: object) -> None:
    with pytest.raises(InvalidAttributeValue):
        normalize_value(value, "kV", "kV")


def test_decimal_context_isolated_and_integers_preserved() -> None:
    with localcontext() as context:
        context.prec = 3
        assert normalize_value("12345.6789", "V", "kV") == Decimal("12.3456789")
        assert normalize_value(0.1, "kV", "V") == Decimal("100")
    assert type(normalize_value(3, None, None)) is int
    assert type(normalize_attribute_value("BUS", "phase_count", "3")) is int
    assert type(normalize_attribute_value("BUS", "nominal_voltage", 3)) is Decimal


def test_horsepower_requires_explicit_semantic_context() -> None:
    for context in [UnitSemanticContext.MOTOR_ACTIVE_POWER, UnitSemanticContext.VFD_ACTIVE_POWER]:
        assert normalize_value(1, "hp", "kW", semantic_context=context) == Decimal(
            "0.74569987158227022"
        )
    for source, target in [("hp", "kW"), ("kW", "hp"), ("hp", "hp")]:
        with pytest.raises(IncompatibleUnit):
            normalize_value(1, source, target)
    for equipment in ["INDUCTION_MOTOR", "VFD"]:
        assert "hp" in supported_input_units(equipment, "rated_active_power")
        assert normalize_attribute_value(equipment, "rated_active_power", 1, "hp") == Decimal(
            "0.74569987158227022"
        )
    for equipment in ["STATIC_LOAD", "LUMPED_LOAD"]:
        assert "hp" not in supported_input_units(equipment, "rated_active_power")
        with pytest.raises(IncompatibleUnit):
            normalize_attribute_value(equipment, "rated_active_power", 1, "hp")


def test_attribute_canonical_units_override_family_defaults() -> None:
    for equipment, attribute, value, unit, expected in [
        ("BUS", "electrode_gap", "0.025", "m", "25"),
        ("CT", "rated_burden", "0.01", "kVA", "10"),
        ("VFD", "output_short_circuit_trip_time", "0.01", "s", "10"),
        ("OVERCURRENT_RELAY", "trip_output_operating_time", 10, "ms", "0.01"),
        ("TWO_WINDING_TRANSFORMER", "temperature_rise", 18, "°F", "10"),
    ]:
        assert normalize_attribute_value(equipment, attribute, value, unit) == Decimal(expected)


@pytest.mark.parametrize(
    "equipment,attribute,value,error",
    [
        ("BUS", "phase_count", 1.5, InvalidAttributeValue),
        ("BUS", "phase_count", True, InvalidAttributeValue),
        ("BUS", "nominal_voltage", True, InvalidAttributeValue),
        ("BUS", "bus_type", "SWGR", InvalidEnumValue),
        ("BUS", "bus_type", "switchgear", InvalidEnumValue),
        ("BUS", "manufacturer", 1, InvalidAttributeValue),
        ("BUS", "series_rating_applicable", 1, InvalidAttributeValue),
        ("BUS", "series_rating_applicable", "true", InvalidAttributeValue),
    ],
)
def test_attribute_type_validation(
    equipment: str, attribute: str, value: object, error: type
) -> None:
    with pytest.raises(error):
        normalize_attribute_value(equipment, attribute, value)


def test_unitless_and_false_values() -> None:
    assert normalize_attribute_value("BUS", "series_rating_applicable", False) is False
    assert normalize_attribute_value("BUS", "manufacturer", "Acme") == "Acme"
    assert supported_input_units("BUS", "manufacturer") == ()
    for attribute in ["manufacturer", "phase_count", "bus_type", "series_rating_applicable"]:
        with pytest.raises(IncompatibleUnit):
            normalize_attribute_value("BUS", attribute, 1, "A")
