"""Exercise the lexical source-unit guard with resolved fragments."""

import pytest

from powerforge_engineering_model.registry_v1 import REGISTRY
from powerforge_engineering_model.units import UNITS
from powerforge_extraction.unit_notation import matches_proposal, source_supports_unit

CATALOG_UNITS = sorted(
    {unit for family in REGISTRY.unit_families for unit in family.supported_input_units}
)


def resolved(role, quote, **fields):
    return dict(localization="RESOLVED", role=role, quote=quote, **fields)


@pytest.mark.parametrize("unit", CATALOG_UNITS)
def test_catalog_symbols_ground_inline_and_explicit_headers(unit):
    assert matches_proposal(unit, unit, tuple(UNITS))
    assert source_supports_unit("12.50", unit, unit, [resolved("VALUE", f"12.50 {unit}")])
    assert source_supports_unit("12.50", unit, unit, [resolved("HEADER", f"Rating ({unit})")])
    assert not any(matches_proposal(unit, other, tuple(UNITS)) for other in UNITS if other != unit)


@pytest.mark.parametrize(
    "role,quote,raw_unit,unit,expected",
    [
        ("HEADER", "Width in:", "in", "in", False),
        ("LABEL", "Width in.", "in", "in", False),
        ("UNIT", "in", "in", "in", False),
        ("HEADER", "Width in millimetres", "in", "in", False),
        ("HEADER", "Width (in)", "in", "in", True),
        ("LABEL", "Width [in.]", "in", "in", True),
        ("UNIT", "Units: in", "in", "in", True),
        ("HEADER", "Units: in the drawing", "in", "in", False),
        ("HEADER", "Width in inches", "inches", "in", True),
        ("VALUE", "12 in", "in", "in", True),
        ("UNIT", "12 in", "in", "in", True),
        ("VALUE", "12 in the drawing", "in", "in", False),
        ("VALUE", "12 in 2026", "in", "in", False),
        ("VALUE", '12" wide', '"', "in", True),
        ("VALUE", "12″", "″", "in", True),
        ("VALUE", "12'", "'", "ft", True),
        ("VALUE", "12′", "′", "ft", True),
        ("HEADER", 'Width (")', '"', "in", True),
        ("HEADER", "Length (′)", "′", "ft", True),
        ("HEADER", 'Width "nominal"', '"', "in", False),
        ("VALUE", '"12"', '"', "in", False),
        ("VALUE", "'12'", "'", "ft", False),
        ("VALUE", '"Width is 12"', '"', "in", False),
        ("VALUE", "12’", "’", "ft", False),
        ("VALUE", "12”", "”", "in", False),
        ("VALUE", "12° 5″", "″", "in", False),
        ("VALUE", "12′-5″", "′", "ft", False),
        ("VALUE", "12'5\"", "'", "ft", False),
        ("VALUE", "5′ 12″", "″", "in", False),
        ("VALUE", "12 ft 5 in", "ft", "ft", False),
        ("VALUE", "12 ft\n5 in", "ft", "ft", True),
        ("VALUE", "12 HP", "HP", "hp", True),
        ("HEADER", "Speed (RPM)", "RPM", "rpm", True),
    ],
)
def test_unit_notation_requires_the_right_source_context(role, quote, raw_unit, unit, expected):
    assert source_supports_unit("12", raw_unit, unit, [resolved(role, quote)]) is expected


@pytest.mark.parametrize(
    "quote,raw_value,raw_unit,unit,expected",
    [
        ("65 kA at 40 °C", "65", "kA", "kA", True),
        ("40 °C; 65 kA", "65", "kA", "kA", True),
        ("65 kA\nA: 40 °C", "65", "kA", "kA", True),
        ("65\nkA", "65", "kA", "kA", False),
        ("12° 5″", "5", "″", "in", False),
        ("12° 3′ 5″", "5", "″", "in", False),
        ("40 kV A; 65 kA", "65", "kA", "kA", True),
        ("65 V in the specification", "65", "V", "V", True),
        ("65 V at 40 in the specification", "65", "V", "V", True),
        ("65 KA and 65 kA", "65", "KA", "kA", True),
        ("65 KA and 65 mA", "65", "KA", "kA", False),
        ("65 kA or A", "65", "kA", "kA", False),
        ("65 kA or 40 A", "65", "kA", "kA", True),
        ("65 kA; 65 (A)", "65", "kA", "kA", False),
        ("65 kV A; 40 kA", "65", "kV", "kV", False),
        ("40 kA; 65 kV", "65", "kA", "kA", False),
        ("Width - 12 in", "12", "in", "in", True),
        ("65 Ω / 1000 ft", "65", "Ω / 1000 ft", "Ω/1000 ft", True),
        ("65 Ω / 1000 ft; 1000 m", "65", "Ω / 1000 ft", "Ω/1000 ft", True),
        ("65 Ω / 1000 ft", "65", "Ω", "Ω", False),
        ("65 Ω / 1000 ft", "1000", "ft", "ft", False),
        ("Ω / 1000 ft", "1000", "ft", "ft", False),
        ("65 Ω / (1000 ft)", "1000", "ft", "ft", False),
        ("65 Ω per 1000 ft", "1000", "ft", "ft", False),
        ("65 Ω / 1000 ft; 1000 ft", "1000", "ft", "ft", True),
    ],
)
def test_units_are_scoped_to_the_selected_literal_number(
    quote, raw_value, raw_unit, unit, expected
):
    assert source_supports_unit(raw_value, raw_unit, unit, [resolved("VALUE", quote)]) is expected


@pytest.mark.parametrize(
    "raw_unit,unit,permitted",
    [
        ("HP", "hp", ("kW", "hp")),
        ("RPM", "rpm", ("rpm",)),
        ('"', "in", ("m", "in", "ft")),
        ("′", "ft", ("m", "in", "ft")),
        ("Ω / 1000 ft", "Ω/1000 ft", ("Ω/m", "Ω/km", "Ω/1000 ft")),
    ],
)
def test_general_spellings_require_the_exact_allowed_proposal(raw_unit, unit, permitted):
    assert matches_proposal(raw_unit, unit, permitted)
    assert not matches_proposal(raw_unit, unit, tuple(u for u in permitted if u != unit))


def test_compatible_value_citation_does_not_override_a_conflicting_header():
    fragments = [resolved("VALUE", "65 kA at 40 °C"), resolved("HEADER", "Current (A)")]
    assert not source_supports_unit("65", "kA", "kA", fragments)


def test_header_can_support_a_unit_beside_an_unrelated_quantity():
    assert source_supports_unit("65", "kA", "kA", [resolved("HEADER", "Current (kA) at 40 °C")])
