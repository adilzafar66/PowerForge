"""Structured-cell meaning and exact normalization. No synthetic source-quote verification."""

import re
from dataclasses import replace
from decimal import Decimal, DecimalException

from powerforge_engineering_model.errors import EngineeringModelError
from powerforge_engineering_model.registry import (
    get_attribute_definition,
    normalize_attribute_value,
)
from powerforge_extraction import interpretation_v1 as v1
from powerforge_extraction.grounding import _RATING_PAIR

# Table-specific abbreviations, qualified by an explicit source equipment type.
# Full registry labels, enum interpretation and value/unit semantics remain registry-v1/6C.
HEADER_ALIASES = {
    ("TWO_WINDING_TRANSFORMER", "capacity"): "rated_apparent_power",
    ("TWO_WINDING_TRANSFORMER", "primary"): "primary_voltage",
    ("TWO_WINDING_TRANSFORMER", "secondary"): "secondary_voltage",
    ("LV_BREAKER", "frame"): "frame_rating",
    ("LV_BREAKER", "trip"): "trip_rating",
    ("CABLE", "material"): "conductor_material",
}
HEADER_CONTAINERS = {
    "LV_BREAKER": {"breaker ratings"},
    "TWO_WINDING_TRANSFORMER": {"transformer ratings"},
}
_CONDITIONAL = re.compile(
    r"\b(not verified|n/a|normal|emergency|standby|possibly|maybe)\b|\?", re.I
)


def unresolved(raw_text, value=None, unit=None, reason="UNKNOWN_ATTRIBUTE_MEANING"):
    return v1.Interpretation(
        v1.MappingStatus.UNMAPPED, reason, raw_text, raw_value=value, raw_unit=unit
    )


def equipment_meaning(claim, passages, *, uncertain=False):
    result = v1.Interpretation(
        v1.MappingStatus.UNMAPPED,
        "UNKNOWN_EQUIPMENT_MEANING",
        claim.raw_expression,
        observed_tag=claim.observed_tag,
        observed_name=claim.observed_name,
    )
    if any(
        v is not None and not v1._literal(v, claim.raw_expression)
        for v in (claim.observed_tag, claim.observed_name)
    ):
        return replace(result, mapping_status=None, reason_code="SOURCE_FIELD_MISMATCH")
    if (
        not claim.observed_tag
        and not claim.observed_name
        and v1._equipment_type(claim.raw_expression) is None
    ):
        return result
    if (
        uncertain
        or claim.ambiguous
        or any(
            re.search(r"\b(not|no|maybe|reference|ref|either|or)\b|\?", text, re.I)
            for text in [claim.raw_expression, *passages]
        )
    ):
        return replace(result, reason_code="AMBIGUOUS_OBSERVATION")
    own = (
        claim.raw_expression.replace(claim.observed_tag, " ")
        if claim.observed_tag
        else claim.raw_expression
    )
    meanings = {typ for text in [own, *passages] if (typ := v1._equipment_type(text)) is not None}
    if len(meanings) != 1:
        return result
    typ = next(iter(meanings))
    if claim.proposed_equipment_type not in (None, typ):
        return replace(result, reason_code="EQUIPMENT_PROPOSAL_CONFLICT")
    return replace(
        result,
        mapping_status=v1.MappingStatus.MAPPED,
        equipment_type_key=typ,
        reason_code="EQUIPMENT_MEANING_RESOLVED",
    )


def _label_parts(label):
    name, unit = v1._label_parts(label)
    designation = re.fullmatch(r"(.+?)\s*\((AF|AT|%Z)\)", label) if unit is None else None
    return (designation[1].strip(), designation[2]) if designation else (name, unit)


def _definition(typ, labels, context):
    names = [
        _label_parts(label)[0]
        for label in labels
        if label not in v1.UNITS and v1._fold(label) not in HEADER_CONTAINERS.get(typ, set())
    ]
    if not names:
        return None
    # Consume the whole path, rather than dropping an unsupported parent qualifier.
    label = " ".join(names)
    definitions = {
        d.key: d
        for phrase in {label, " ".join(reversed(names))}
        if (d := v1._attribute(typ, phrase, context)) is not None
    }
    definition = next(iter(definitions.values())) if len(definitions) == 1 else None
    if definition is None and len(names) == 1:
        key = HEADER_ALIASES.get((typ, v1._fold(label)))
        if key and (key != "trip_rating" or v1._alias_allowed("breaker-trip", context)):
            definition = get_attribute_definition(typ, key)
    return definition


def attribute_meaning(claim, cell, labels, equipment, equipment_text, *, uncertain=False, notes=()):
    result = unresolved(claim.raw_expression, claim.raw_value, claim.raw_unit)
    raw = cell.raw_text
    if raw is None or claim.raw_expression not in raw:
        return replace(result, mapping_status=None, reason_code="SOURCE_FIELD_MISMATCH")
    if claim.source_label is not None and claim.source_label not in labels:
        return replace(result, mapping_status=None, reason_code="SOURCE_LABEL_MISMATCH")
    clause = raw.strip()
    paired = _RATING_PAIR.fullmatch(clause)
    shorthand = None
    if paired:
        clauses = [paired[1], paired[2]]
        selected = [p for p in clauses if claim.raw_expression in p]
        if len(selected) != 1:
            return replace(result, reason_code="UNRESOLVED_SOURCE_FIELD")
        clause = selected[0]
        shorthand = "AF" if clause.endswith("AF") else "AT"
    elif re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?\s*(AF|AT|%Z)", clause):
        shorthand = re.search(r"(AF|AT|%Z)$", clause)[0]
    if claim.raw_value is None:
        return replace(result, reason_code="UNRESOLVED_SOURCE_FIELD")
    suffix = v1._value_body(clause, claim.raw_value, numeric=True)
    if suffix is None:
        return replace(result, mapping_status=None, reason_code="SOURCE_VALUE_MISMATCH")
    units = {_label_parts(label)[1] for label in labels}
    units.update(label for label in labels if label in v1.UNITS)
    units.discard(None)
    if suffix:
        units.add(suffix)
    if claim.raw_unit is not None and claim.raw_unit not in units:
        return replace(result, mapping_status=None, reason_code="SOURCE_UNIT_MISMATCH")
    if (
        uncertain
        or claim.ambiguous
        or cell.ambiguous
        or cell.state != "VALUE"
        or notes
        or any(_CONDITIONAL.search(label) for label in labels)
    ):
        return replace(result, reason_code="AMBIGUOUS_TABLE_CONTEXT")
    if equipment is None:
        return replace(result, reason_code="NO_EQUIPMENT_CONTEXT")
    typ = equipment.equipment_type_key
    if typ is None or equipment.mapping_status != "MAPPED":
        return replace(result, reason_code="NO_EQUIPMENT_CONTEXT")
    result = replace(result, equipment_type_key=typ)
    if claim.proposed_equipment_type not in (None, typ):
        return replace(result, reason_code="EQUIPMENT_PROPOSAL_CONFLICT")
    context_text = "\n".join([*labels, clause, *notes])
    if len(context_text) > 4000 or len(equipment_text) > 2000:
        return replace(result, reason_code="TABLE_CONTEXT_TOO_LARGE")
    # Meaning-only context for frozen qualification helpers, never Evidence or native verification.
    context = v1.InterpretationContext(context_text, equipment_text)
    meaning_labels = [shorthand] if shorthand else labels
    definition = _definition(typ, meaning_labels, context)
    if shorthand:
        header_definition = _definition(typ, labels, context)
        # A designation may qualify a generic Rating column, but may never replace
        # contradictory meaning or discard an unresolved parent/header qualifier.
        generic = all(
            v1._fold(label) in {"rating", "ratings", "value", "a", "%"} for label in labels
        )
        if header_definition is None and not generic:
            return result
        if (
            header_definition is not None
            and definition is not None
            and header_definition.key != definition.key
        ):
            return replace(result, reason_code="ATTRIBUTE_PROPOSAL_CONFLICT")
    if definition is None:
        return result
    for designation in units & {"AF", "AT", "%Z"}:
        qualified = _definition(typ, [designation], context)
        if qualified is None or qualified.key != definition.key:
            return replace(result, reason_code="ATTRIBUTE_PROPOSAL_CONFLICT")
    if claim.proposed_attribute_key not in (None, definition.key):
        return replace(result, reason_code="ATTRIBUTE_PROPOSAL_CONFLICT")
    numeric = definition.value_type in {"NUMBER", "INTEGER"}
    if v1._value_body(clause, claim.raw_value, numeric) is None:
        return replace(result, mapping_status=None, reason_code="SOURCE_VALUE_MISMATCH")
    normalized_units = {{"AF": "A", "AT": "A", "%Z": "%"}.get(u, u) for u in units}
    if len(normalized_units) > 1:
        return replace(result, reason_code="CONFLICTING_SOURCE_UNITS")
    source_unit = suffix if suffix else next(iter(units)) if units else None
    result = replace(result, raw_unit=source_unit)
    unit = {"AF": "A", "AT": "A", "%Z": "%"}.get(source_unit, source_unit)
    if numeric and definition.canonical_unit is not None and unit is None:
        return replace(result, reason_code="MISSING_UNIT")
    value = claim.raw_value
    if numeric:
        if "," in value:
            return replace(result, reason_code="AMBIGUOUS_NUMERIC_FORMAT")
        if v1._NUMBER.fullmatch(value) is None:
            return replace(
                result, mapping_status=v1.MappingStatus.INVALID, reason_code="INVALID_NUMERIC_VALUE"
            )
        try:
            value = Decimal(value)
        except DecimalException:
            return replace(
                result, mapping_status=v1.MappingStatus.INVALID, reason_code="INVALID_NUMERIC_VALUE"
            )
        if (
            not value.is_finite()
            or not v1._representable_number(value)
            or (
                definition.value_type == "INTEGER"
                and not v1._INTEGER_MIN <= value <= v1._INTEGER_MAX
            )
        ):
            return replace(
                result, mapping_status=v1.MappingStatus.INVALID, reason_code="VALUE_OUT_OF_RANGE"
            )
    elif definition.value_type == "ENUM":
        value = v1._enum_value(typ, definition, value)
        if value is None:
            return replace(result, reason_code="UNKNOWN_ENUM_EXPRESSION")
    elif definition.value_type == "BOOLEAN":
        value = v1._BOOLEAN.get(value.casefold())
        if value is None:
            return replace(
                result, mapping_status=v1.MappingStatus.INVALID, reason_code="INVALID_BOOLEAN_VALUE"
            )
    try:
        normalized = normalize_attribute_value(typ, definition.key, value, unit)
    except (EngineeringModelError, DecimalException):
        return replace(
            result,
            mapping_status=v1.MappingStatus.INVALID,
            reason_code="REGISTRY_NORMALIZATION_FAILED",
        )
    if isinstance(normalized, Decimal) and not v1._representable_number(normalized):
        return replace(
            result, mapping_status=v1.MappingStatus.INVALID, reason_code="VALUE_OUT_OF_RANGE"
        )
    return replace(
        result,
        mapping_status=v1.MappingStatus.MAPPED,
        reason_code="ATTRIBUTE_NORMALIZED",
        attribute_key=definition.key,
        value_type=definition.value_type,
        value=normalized,
        unit=definition.canonical_unit,
    )
