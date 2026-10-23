"""Small decimal-safe unit system; no engineering calculations or base conversion."""

from dataclasses import dataclass
from decimal import Context, Decimal, DecimalException, localcontext
from enum import StrEnum
from types import MappingProxyType

from powerforge_engineering_model.errors import (
    IncompatibleUnit,
    InvalidAttributeValue,
    UnknownUnit,
)


class UnitSemanticContext(StrEnum):
    MOTOR_ACTIVE_POWER = "MOTOR_ACTIVE_POWER"
    VFD_ACTIVE_POWER = "VFD_ACTIVE_POWER"
    TEMPERATURE_DIFFERENCE = "TEMPERATURE_DIFFERENCE"


@dataclass(frozen=True, slots=True)
class Unit:
    dimension: str
    numerator: Decimal
    denominator: Decimal = Decimal(1)


def _unit(dimension: str, numerator: str, denominator: str = "1") -> Unit:
    return Unit(dimension, Decimal(numerator), Decimal(denominator))


# Ratios retain exact conversion factors, including ohms per 1000 international feet.
UNITS = MappingProxyType(
    {
        "V": _unit("voltage", "1"),
        "kV": _unit("voltage", "1000"),
        "MV": _unit("voltage", "1000000"),
        "A": _unit("current", "1"),
        "kA": _unit("current", "1000"),
        "VA": _unit("apparent_power", "1"),
        "kVA": _unit("apparent_power", "1000"),
        "MVA": _unit("apparent_power", "1000000"),
        "W": _unit("active_power", "1"),
        "kW": _unit("active_power", "1000"),
        "MW": _unit("active_power", "1000000"),
        "hp": _unit("active_power", "745.69987158227022"),  # mechanical horsepower
        "var": _unit("reactive_power", "1"),
        "kvar": _unit("reactive_power", "1000"),
        "Mvar": _unit("reactive_power", "1000000"),
        "mΩ": _unit("impedance", "0.001"),
        "Ω": _unit("impedance", "1"),
        "kΩ": _unit("impedance", "1000"),
        "Ω/m": _unit("impedance_per_length", "1"),
        "Ω/km": _unit("impedance_per_length", "1", "1000"),
        "Ω/1000 ft": _unit("impedance_per_length", "1", "304.8"),
        "mm": _unit("length", "0.001"),
        "cm": _unit("length", "0.01"),
        "m": _unit("length", "1"),
        "km": _unit("length", "1000"),
        "in": _unit("length", "0.0254"),
        "ft": _unit("length", "0.3048"),
        "ms": _unit("time", "0.001"),
        "s": _unit("time", "1"),
        "Hz": _unit("frequency", "1"),
        "rpm": _unit("speed", "1"),
        "nF": _unit("capacitance", "0.001"),
        "µF": _unit("capacitance", "1"),
        "mF": _unit("capacitance", "1000"),
        "µH": _unit("inductance", "0.001"),
        "mH": _unit("inductance", "1"),
        "H": _unit("inductance", "1000"),
        "%": _unit("percentage", "1"),
        "p.u.": _unit("per_unit", "1"),
        "°C": _unit("temperature", "1"),
        "°F": _unit("temperature", "5", "9"),
    }
)


def get_unit(unit: str) -> Unit:
    try:
        return UNITS[unit]
    except (KeyError, TypeError):
        raise UnknownUnit(f"Unsupported unit: {unit!r}") from None


def as_decimal(value: object) -> Decimal:
    """Accept decimal strings and numeric inputs, never booleans or non-finite values."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise InvalidAttributeValue("Expected a finite number")
    try:
        number = Decimal(str(value))
    except (DecimalException, ValueError):
        raise InvalidAttributeValue("Expected a finite number") from None
    if not number.is_finite():
        raise InvalidAttributeValue("Expected a finite number")
    return number


def normalize_value(
    value: object,
    input_unit: str | None,
    canonical_unit: str | None,
    *,
    semantic_context: UnitSemanticContext | None = None,
) -> Decimal | int:
    """Convert with an isolated 34-digit, half-even Decimal context.

    None means unitless, not an unspecified unit. Identity conversions preserve ints.
    Percent and per-unit have distinct dimensions. Horsepower needs an explicit context.
    """
    number = as_decimal(value)
    source = get_unit(input_unit) if input_unit is not None else None
    target = get_unit(canonical_unit) if canonical_unit is not None else None
    if (source is None) != (target is None) or (
        source is not None and target is not None and source.dimension != target.dimension
    ):
        raise IncompatibleUnit(f"Cannot convert {input_unit!r} to {canonical_unit!r}")
    if "hp" in (input_unit, canonical_unit) and semantic_context not in (
        UnitSemanticContext.MOTOR_ACTIVE_POWER,
        UnitSemanticContext.VFD_ACTIVE_POWER,
    ):
        raise IncompatibleUnit("Horsepower is permitted only for motor/VFD active-power ratings")
    if input_unit == canonical_unit:
        return value if type(value) is int else number
    assert source is not None and target is not None
    try:
        with localcontext(Context(prec=34)):
            if source.dimension == "temperature":
                if semantic_context == UnitSemanticContext.TEMPERATURE_DIFFERENCE:
                    return (
                        number
                        * source.numerator
                        * target.denominator
                        / (source.denominator * target.numerator)
                    )
                if input_unit == "°F":
                    return (number - 32) * 5 / 9
                return number * 9 / 5 + 32
            return (
                number
                * source.numerator
                * target.denominator
                / (source.denominator * target.numerator)
            )
    except DecimalException:
        raise InvalidAttributeValue("Number exceeds the supported conversion range") from None
