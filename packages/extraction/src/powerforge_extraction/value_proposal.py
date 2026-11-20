"""Validate typed proposals and their lexical source fidelity before normalization."""

import re
from decimal import Decimal, DecimalException
from fractions import Fraction
from typing import NamedTuple

from powerforge_engineering_model.enums import EquipmentType
from powerforge_engineering_model.errors import EngineeringModelError
from powerforge_engineering_model.registry import (
    exact_attribute_quantity,
    normalize_attribute_value,
)
from powerforge_extraction.stage_contracts import InferredAssertion
from powerforge_extraction.unit_notation import (
    SCALAR,
    is_unit_notation,
    matches_proposal,
    numeric_unit_spans,
    source_supports_unit,
)

BOOLEAN = {"true": True, "yes": True, "false": False, "no": False}
_NUMERIC_TYPES = {"NUMBER", "INTEGER"}
_COUNT_SUFFIX = re.compile(r"(?i:ph|phase|phases|pole|poles)\b")
_DESCRIPTIVE_SUFFIX = re.compile(r"(?i:sym|asym|rms|ac|dc)")
# These expressions require source components or qualifiers beyond a scalar.
_CONDITION = re.compile(
    r"(?i:\b(?:at|or|to|through|approx(?:imately)?|between|above|below|up to|"
    r"min(?:imum)?|max(?:imum)?|typical)\b)|[~≈<>≤≥±×*/÷^−–—]"
)


class SourceNumber(NamedTuple):
    literal: str
    start: int
    end: int
    unit: str | None
    embedded: bool


def _decimal(text: str) -> Decimal | None:
    if len(text) > 128 or not SCALAR.fullmatch(text):
        return None
    try:
        number = Decimal(text)
    except DecimalException:
        return None
    if abs(number.adjusted()) > 256 or abs(number.as_tuple().exponent) > 256:
        return None
    return number


def _numbers(text, *, count_suffix=False):
    following = {number: (span, token) for number, span, token in numeric_unit_spans(text)}
    units = {
        number: (span, token)
        for number, (span, token) in following.items()
        if is_unit_notation(token) and not (count_suffix and _COUNT_SUFFIX.fullmatch(token))
    }
    unit_spans = iter(sorted(span for span, _ in units.values()))
    covered = next(unit_spans, None)
    for match in SCALAR.finditer(text):
        start, end = match.span()
        while covered is not None and covered[1] <= start:
            covered = next(unit_spans, None)
        if covered is not None and covered[0] <= start < covered[1]:
            continue  # A numeric denominator belongs to the complete unit.
        span, unit = units.get(match.span(), ((end, end), None))
        token = following.get(match.span(), (None, ""))[1]
        before, after = text[start - 1 : start], text[end : end + 1]
        embedded = (
            bool(before and (before.isalnum() or before in "_.,"))
            or after in {".", ","}
            or bool(
                token
                and unit is None
                and _DESCRIPTIVE_SUFFIX.fullmatch(token) is None
                and not (count_suffix and _COUNT_SUFFIX.fullmatch(token))
            )
            or bool(
                after
                and (after.isalpha() or after == "_")
                and unit is None
                and _COUNT_SUFFIX.match(text, end) is None
            )
        )
        yield SourceNumber(match[0], start, span[1], unit, embedded)


def _qualified_or_compound(text, quantity_spans):
    # Inspect the remaining context without interpreting any engineering labels.
    # Keep operator characters outside numeric literals and complete unit spans.
    parts = []
    previous = 0
    for quantity in quantity_spans:
        parts.append(text[previous : quantity.start])
        previous = quantity.end
    parts.append(text[previous:])
    remainder = " ".join(parts)
    return (
        _CONDITION.search(remainder) is not None
        or re.search(r"[+-]\s*(?:$|[()])", remainder) is not None
        or any(character.isnumeric() for character in remainder)
    )


def _registry_value(proposal, definition, inferred):
    """Return the typed value or the publication classification for incompatibility."""
    kind = definition.value_type
    if proposal is None:
        return None, ("UNMAPPED", "NO_VALUE_PROPOSAL")
    expected = {"INTEGER": int, "BOOLEAN": bool}.get(kind, str)
    if type(proposal) is not expected:
        return None, ("INVALID" if inferred else "UNMAPPED", "PROPOSAL_TYPE_MISMATCH")
    if kind == "NUMBER":
        if not SCALAR.fullmatch(proposal):
            return None, ("INVALID" if inferred else "UNMAPPED", "PROPOSAL_TYPE_MISMATCH")
        value = _decimal(proposal)
        if value is None:
            return None, ("INVALID", "INVALID_VALUE")
        return value, None
    if kind == "INTEGER" and not -(2**63) <= proposal < 2**63:
        return None, ("INVALID", "INVALID_VALUE")
    if kind == "ENUM" and proposal not in definition.allowed_values:
        return None, ("INVALID", "INVALID_VALUE")
    return proposal, None


def _reported_enum(text, definition):
    """Verify a complete source spelling against the attribute's enum members."""
    literal = text.casefold()
    # This narrowly scoped spelling can verify an existing proposal. It never
    # supplies a missing proposal or interprets a longer source expression.
    if (
        literal == "star"
        and definition.equipment_type == EquipmentType.TWO_WINDING_TRANSFORMER
        and definition.key in {"primary_connection", "secondary_connection"}
    ):
        literal = "wye"
    matches = [member for member in definition.allowed_values if member.casefold() == literal]
    return matches[0] if len(matches) == 1 else None


_IDENTIFIER_KEYS = frozenset({"model", "catalog_number", "trip_unit_model"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:[ \t]+[0-9]+)?")


def _text_fidelity(text, value, definition, raw_label):
    proposal = value.strip()
    if text == proposal:
        return None
    label, delimiter, remainder = text.partition(":")
    if delimiter:
        label = label.strip()
        matches_label = (
            bool(label) and label == raw_label.strip()
            if raw_label is not None
            else label.casefold() == definition.name.casefold()
        )
        if not matches_label or ":" in remainder or len(text.splitlines()) != 1:
            return "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"
        text = remainder.strip()
        if text == proposal:
            return None
    if (
        definition.key in _IDENTIFIER_KEYS
        and _IDENTIFIER.fullmatch(text)
        and _IDENTIFIER.fullmatch(proposal)
        and proposal not in text.split()
    ):
        return "INVALID", "SOURCE_VALUE_MISMATCH"
    return "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"


def _single_fidelity(item, definition, value, quantities):
    text = item.raw_value.strip()
    kind = definition.value_type
    if kind in _NUMERIC_TYPES:
        if not quantities or any(quantity.embedded for quantity in quantities):
            return "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"
        if len(quantities) > 1:
            return "INVALID", "SOURCE_VALUE_MISMATCH"
        reported = _decimal(quantities[0].literal)
        if reported is None:
            return "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"
        if reported != value:
            return "INVALID", "SOURCE_VALUE_MISMATCH"
        if _qualified_or_compound(text, quantities):
            return "UNMAPPED", "UNREPRESENTABLE_VALUE_FORM"
    elif kind == "BOOLEAN":
        reported = BOOLEAN.get(text.casefold())
        if reported is None:
            return "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"
        if reported != value:
            return "INVALID", "SOURCE_VALUE_MISMATCH"
    elif kind == "TEXT":
        return _text_fidelity(text, value, definition, item.raw_label)
    elif kind == "ENUM":
        reported = _reported_enum(text, definition)
        if reported is None:
            return "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"
        if reported != value:
            return "INVALID", "SOURCE_VALUE_MISMATCH"
    return None


def _exact(definition, value, unit):
    return exact_attribute_quantity(definition.equipment_type, definition.key, value, unit)


def _equivalent_representations(item, definition, value, unit, quantities, evidence):
    if definition.value_type not in _NUMERIC_TYPES or not unit:
        return "UNMAPPED", "UNVERIFIED_REPRESENTATIONS"
    if len(quantities) != 1 + len(item.alternate_representations) or _qualified_or_compound(
        item.raw_value.strip(), quantities
    ):
        return "UNMAPPED", "UNVERIFIED_REPRESENTATIONS"
    pairs = [(value, item.raw_unit.strip(), unit)]
    for alternate in item.alternate_representations:
        other_value = _decimal(alternate.value)
        spelling = alternate.unit.strip()
        units = [u for u in definition.supported_units if matches_proposal(spelling, u, (u,))]
        if other_value is None or len(units) != 1:
            return "UNMAPPED", "UNVERIFIED_REPRESENTATIONS"
        pairs.append((other_value, spelling, units[0]))

    # Match each pair to a distinct complete source occurrence. A number alone
    # cannot prove a pairing, and an inferred or computed alternate is insufficient.
    exact = _exact(definition, value, unit)
    remaining = list(quantities)
    value_evidence = [fragment for fragment in evidence if fragment["role"] == "VALUE"]
    inconsistent = False
    for index, (magnitude, literal_unit, input_unit) in enumerate(pairs):
        matches = [
            quantity
            for quantity in remaining
            if not quantity.embedded
            and (quantity.unit == literal_unit or quantity.unit == literal_unit.removesuffix("."))
            and _decimal(quantity.literal) == magnitude
        ]
        if index == 0 and not matches and all(q.unit and not q.embedded for q in remaining):
            return "INVALID", "SOURCE_VALUE_MISMATCH"
        if len(matches) != 1:
            return "UNMAPPED", "UNVERIFIED_REPRESENTATIONS"
        same_value_alternate_units = frozenset(
            spelling.removesuffix(".")
            for pair_index, (other, spelling, _) in enumerate(pairs)
            if pair_index != index and other == magnitude
        )
        if not source_supports_unit(
            matches[0].literal,
            literal_unit,
            input_unit,
            value_evidence,
            same_value_alternate_units=same_value_alternate_units,
        ):
            return "UNMAPPED", "UNVERIFIED_REPRESENTATIONS"
        remaining.remove(matches[0])
        inconsistent |= _exact(definition, magnitude, input_unit) != exact
    if inconsistent:
        return "UNMAPPED", "INCONSISTENT_REPRESENTATIONS"
    return None


def _unit_failure(item, definition, unit, quantities, evidence):
    raw_unit = item.raw_unit.strip() if item.raw_unit is not None else None
    if definition.canonical_unit is None and raw_unit is None and unit is None:
        if quantities and quantities[0].unit is not None:
            return "UNMAPPED", "UNIT_MISSING_OR_AMBIGUOUS"
        return None
    if not raw_unit or unit is None:
        return "UNMAPPED", "UNIT_MISSING_OR_AMBIGUOUS"
    if not matches_proposal(raw_unit, unit, definition.supported_units):
        return "UNMAPPED", "UNIT_INTERPRETATION_UNVERIFIED"
    if item.value_form == "EQUIVALENT_UNITS":
        return None
    quantity = quantities[0]
    if quantity.unit is not None and not matches_proposal(
        quantity.unit, unit, definition.supported_units
    ):
        return "INVALID", "SOURCE_UNIT_MISMATCH"
    if not source_supports_unit(quantity.literal, raw_unit, unit, evidence):
        return "UNMAPPED", "UNIT_MISSING_OR_AMBIGUOUS"
    return None


def _extracted_failure(item, definition, value, unit, evidence):
    kind = definition.value_type
    if item.qualifiers or item.value_form not in {"SINGLE", "EQUIVALENT_UNITS"}:
        if kind in _NUMERIC_TYPES and item.value_form in {"RANGE", "MULTIPLE"}:
            return "INVALID", "SOURCE_VALUE_MISMATCH"
        return "UNMAPPED", "UNREPRESENTABLE_VALUE_FORM"
    quantities = (
        list(
            _numbers(
                item.raw_value.strip(),
                count_suffix=kind == "INTEGER" and definition.canonical_unit is None,
            )
        )
        if kind in _NUMERIC_TYPES
        else []
    )
    if item.value_form == "SINGLE":
        failure = _single_fidelity(item, definition, value, quantities)
        if failure:
            return failure
    elif kind not in _NUMERIC_TYPES:
        return "UNMAPPED", "UNVERIFIED_REPRESENTATIONS"
    failure = _unit_failure(item, definition, unit, quantities, evidence)
    if failure:
        return failure
    if item.value_form == "EQUIVALENT_UNITS":
        return _equivalent_representations(item, definition, value, unit, quantities, evidence)
    return None


def _inferred_failure(item, definition, value, unit):
    if definition.canonical_unit is not None and unit is None:
        return "UNMAPPED", "UNIT_MISSING_OR_AMBIGUOUS"
    if unit is not None and unit not in definition.supported_units:
        return "INVALID", "INVALID_UNIT"
    if definition.value_type not in _NUMERIC_TYPES or not item.source_expression:
        return None
    text = item.source_expression.strip()
    quantities = list(_numbers(text))
    if len(quantities) > 1 or _qualified_or_compound(text, quantities):
        return "UNMAPPED", "UNREPRESENTABLE_VALUE_FORM"
    if quantities:
        quantity = quantities[0]
        if not quantity.embedded and (quantity.unit or quantity.literal == text):
            reported = _decimal(quantity.literal)
            if reported is None:
                return "UNMAPPED", "SOURCE_EXPRESSION_UNVERIFIED"
            if reported != value:
                return "INVALID", "SOURCE_VALUE_MISMATCH"
            if quantity.unit and (
                unit is None
                or not matches_proposal(quantity.unit, unit, definition.supported_units)
            ):
                return "INVALID", "SOURCE_UNIT_MISMATCH"
    return None


def normalize_proposal(item, definition, evidence):
    inferred = isinstance(item, InferredAssertion)
    unit = item.proposed_unit
    kind = definition.value_type
    value, failure = _registry_value(item.proposed_value, definition, inferred)
    if failure:
        if (
            not inferred
            and kind == "ENUM"
            and failure == ("INVALID", "INVALID_VALUE")
            and (
                item.proposed_value.strip() == item.raw_value.strip() or item.value_form != "SINGLE"
            )
        ):
            return "UNMAPPED", "PROPOSAL_TYPE_MISMATCH", {}
        return *failure, {}
    try:
        failure = (
            _inferred_failure(item, definition, value, unit)
            if inferred
            else _extracted_failure(item, definition, value, unit, evidence)
        )
        if failure:
            return *failure, {}
        normalized = normalize_attribute_value(
            definition.equipment_type, definition.key, value, unit
        )
        if kind in _NUMERIC_TYPES and Fraction(normalized) != _exact(definition, value, unit):
            return "UNMAPPED", "INEXACT_NORMALIZATION", {}
        if kind == "INTEGER" and not -(2**63) <= normalized < 2**63:
            return "INVALID", "INVALID_VALUE", {}
    except (EngineeringModelError, DecimalException):
        return "INVALID", "INVALID_VALUE", {}
    slot = "text" if kind == "ENUM" else kind.lower()
    return (
        "MAPPED",
        None,
        {
            "normalized_type": kind,
            "normalized_unit": definition.canonical_unit,
            f"value_{slot}": normalized,
        },
    )
