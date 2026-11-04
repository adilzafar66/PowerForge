"""Conservative source-qualified interpretation, frozen behind engineering-interpretation-v1.

Inputs are local passages already admitted by the grounding caller, not arbitrary full pages
or model assertions of verified context. This module does not prove artifact membership,
visual transcription, geometry or equipment association and performs no provider/storage I/O.
"""

import re
from dataclasses import dataclass, replace
from decimal import Decimal, DecimalException
from importlib.resources import files
from typing import Literal

from powerforge_engineering_model.definitions import AttributeDefinition, AttributeValue
from powerforge_engineering_model.enums import AttributeValueType
from powerforge_engineering_model.errors import EngineeringModelError
from powerforge_engineering_model.registry import (
    get_equipment_definition,
    list_equipment_definitions,
    normalize_attribute_value,
)
from powerforge_engineering_model.units import UNITS
from powerforge_extraction.enums import MappingStatus
from powerforge_extraction.identities import content_hash
from powerforge_extraction.observations import AttributeObservation, EquipmentObservation
from powerforge_extraction.registry_context import registry_projection_hash
from powerforge_extraction.terminology import TERMINOLOGY, terminology_hash

VERSION = "engineering-interpretation-v1"
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_BOOLEAN = {"true": True, "false": False, "yes": True, "no": False}
_INTEGER_MIN, _INTEGER_MAX = -(2**63), 2**63 - 1


@dataclass(frozen=True)
class InterpretationContext:
    """Admitted local statement plus separately associated equipment context.

    M3 must establish both passages' provenance and association. For visual inputs it
    must explicitly admit the transcription with page-level verification limitations.
    Model-proposed labels/types/qualifiers must never be substituted for these passages.
    """

    statement: str
    equipment_text: str | None = None
    source_kind: Literal["NATIVE_TEXT", "VISUAL_PAGE"] = "NATIVE_TEXT"

    def __post_init__(self) -> None:
        if (
            type(self.statement) is not str
            or not self.statement.strip()
            or len(self.statement) > 4000
        ):
            raise ValueError("A bounded admitted source statement is required")
        if self.equipment_text is not None and (
            type(self.equipment_text) is not str
            or not self.equipment_text.strip()
            or len(self.equipment_text) > 2000
        ):
            raise ValueError("Equipment context must be a bounded admitted local passage")
        if self.source_kind not in {"NATIVE_TEXT", "VISUAL_PAGE"}:
            raise ValueError("Unsupported interpretation source kind")


@dataclass(frozen=True)
class Interpretation:
    # None is rejected model output, not a fourth persisted MappingStatus.
    mapping_status: MappingStatus | None
    reason_code: str
    raw_text: str
    raw_value: str | None = None
    raw_unit: str | None = None
    observed_tag: str | None = None
    observed_name: str | None = None
    equipment_type_key: str | None = None
    attribute_key: str | None = None
    value_type: AttributeValueType | None = None
    value: AttributeValue | None = None
    unit: str | None = None

    @property
    def rejected(self) -> bool:
        return self.mapping_status is None


def _fold(text: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", text.casefold()))


def _phrase(expression: str, text: str) -> bool:
    words = re.findall(r"[^\W_]+", expression)
    pattern = r"[\s_\-/]+".join(re.escape(word) for word in words)
    return bool(pattern and re.search(r"(?<![\w-])" + pattern + r"(?![\w-])", text, re.I))


def _literal(expression: str, text: str) -> bool:
    return bool(re.search(r"(?<![\w/-])" + re.escape(expression) + r"(?![\w/-])", text))


def _equipment_type(text: str) -> str | None:
    if "?" in text or re.search(
        r"\b(or|nor|versus|vs|either|neither|possibly|maybe|not|no|never|without)\b"
        r"|[A-Za-z]\s*/\s*[A-Za-z]",
        text,
        re.I,
    ):
        return None
    matches = {
        equipment.key.value
        for equipment in list_equipment_definitions()
        if any(_phrase(label, text) for label in (equipment.key.value, equipment.display_name))
    }
    matches.update(
        entry.equipment_type
        for entry in TERMINOLOGY
        if entry.kind == "EQUIPMENT_NAME"
        and entry.key == "lv-breaker-name"
        and any(_phrase(label, text) for label in entry.expressions)
    )
    return next(iter(matches)) if len(matches) == 1 else None


def _reject(result: Interpretation, reason: str) -> Interpretation:
    return replace(result, mapping_status=None, reason_code=reason)


def _unmapped(result: Interpretation, reason: str) -> Interpretation:
    return replace(result, reason_code=reason)


def _invalid(result: Interpretation, reason: str) -> Interpretation:
    return replace(result, mapping_status=MappingStatus.INVALID, reason_code=reason)


def interpret_equipment(
    observation: EquipmentObservation,
    context: InterpretationContext,
) -> Interpretation:
    observation = EquipmentObservation.model_validate(observation.model_dump())
    result = Interpretation(
        MappingStatus.UNMAPPED,
        "UNKNOWN_EQUIPMENT_MEANING",
        observation.raw_expression,
        observed_tag=observation.observed_tag,
        observed_name=observation.observed_name,
    )
    if observation.raw_expression not in context.statement or any(
        field is not None and not _literal(field, observation.raw_expression)
        for field in (observation.observed_tag, observation.observed_name)
    ):
        return _reject(result, "SOURCE_FIELD_MISMATCH")
    if observation.ambiguous:
        return _unmapped(result, "AMBIGUOUS_OBSERVATION")
    # A tag prefix (CT-1, BUS-1) is not an observed equipment classification.
    source = observation.raw_expression
    if observation.observed_tag:
        source = source.replace(observation.observed_tag, " ")
    equipment = _equipment_type(source)
    if equipment is None:
        return result
    if observation.proposed_equipment_type not in (None, equipment):
        return _unmapped(result, "EQUIPMENT_PROPOSAL_CONFLICT")
    return replace(
        result,
        mapping_status=MappingStatus.MAPPED,
        reason_code="EQUIPMENT_MEANING_RESOLVED",
        equipment_type_key=equipment,
    )


def _label_parts(label: str) -> tuple[str, str | None]:
    parenthesis = re.search(r"\s*\(([^()]*)\)\s*$", label)
    if parenthesis:
        return label[: parenthesis.start()].strip(), parenthesis[1].strip()
    for unit in sorted(UNITS, key=len, reverse=True):
        if label.endswith(" " + unit):
            return label[: -len(unit)].strip(), unit
    return label.strip(), None


def _label_units(label: str) -> set[str]:
    return {unit for unit in UNITS if _literal(unit, label)}


def _field(statement: str, value: str) -> tuple[str, str] | None:
    if ":" in statement:
        label, body = statement.split(":", 1)
        return label.strip(), body.strip()
    positions = list(re.finditer(re.escape(value), statement))
    if len(positions) != 1:
        return None
    found = positions[0]
    before, after = statement[: found.start()].strip(), statement[found.end() :].strip()
    if before:
        return before, statement[found.start() :].strip()
    # Numeric-first engineering shorthand only; no general unit-to-attribute inference.
    if after in {"AF", "AT", "%Z"}:
        return after, value
    return None


def _alias_allowed(key: str, context: InterpretationContext) -> bool:
    equipment = context.equipment_text or ""
    if key == "breaker-trip":
        return _phrase("thermal magnetic", equipment) and not _phrase("electronic", equipment)
    if key == "transformer-normal-impedance":
        return not re.search(
            r"\b(zero[ -]?sequence|z0|base|per[ -]?unit)\b|p\.u\.",
            context.statement + " " + equipment,
            re.I,
        )
    # New qualified terminology must not acquire an implicit executable interpretation.
    return key in {
        "transformer-capacity",
        "breaker-frame",
        "utility-three-phase-current",
        "utility-slg-current",
    }


def _attribute(
    equipment_type: str,
    label: str,
    context: InterpretationContext,
) -> AttributeDefinition | None:
    if "?" in label:
        return None
    wanted = _fold(_label_parts(label)[0])
    equipment = get_equipment_definition(equipment_type)
    keys = {
        definition.key
        for definition in equipment.attributes
        if wanted in {_fold(definition.key), _fold(_label_parts(definition.display_name)[0])}
    }
    keys.update(
        entry.attribute_key
        for entry in TERMINOLOGY
        if entry.kind == "ATTRIBUTE_LABEL"
        and entry.equipment_type == equipment_type
        and any(
            wanted == _fold(expression) and ("%" not in expression or "%" in label)
            for expression in entry.expressions
        )
        and _alias_allowed(entry.key, context)
    )
    if len(keys) != 1:
        return None
    return next(definition for definition in equipment.attributes if definition.key in keys)


def _value_body(body: str, value: str, numeric: bool) -> str | None:
    """Return a unit suffix only if the source value lexeme agrees exactly."""
    if not body.startswith(value):
        return None
    if not numeric:
        return "" if body == value else None
    source_number = _NUMBER.match(body)
    if _NUMBER.fullmatch(value) and source_number is not None and source_number[0] != value:
        return None
    suffix = body[len(value) :]
    if suffix and suffix[0].isdigit():
        return None
    return suffix.strip()


def _enum_value(equipment: str, attribute: AttributeDefinition, value: str) -> str | None:
    def spelling(text: str) -> str:
        return re.sub(r"[\s_-]+", " ", text.casefold()).strip()

    matches = {
        allowed for allowed in attribute.allowed_values if spelling(allowed) == spelling(value)
    }
    matches.update(
        entry.enum_value
        for entry in TERMINOLOGY
        if entry.kind == "ENUM_VALUE"
        and entry.key in {"copper-symbol", "aluminum-symbol"}
        and entry.equipment_type == equipment
        and entry.attribute_key == attribute.key
        and any(value == expression for expression in entry.expressions)
    )
    return next(iter(matches)) if len(matches) == 1 else None


def _source_fields(
    observation: AttributeObservation,
    context: InterpretationContext,
) -> str | None:
    """Check asserted source fields even for observations that will remain unmapped."""
    if observation.raw_expression not in context.statement:
        return "SOURCE_FIELD_MISMATCH"
    if observation.raw_value is None:
        if observation.source_label and observation.source_label not in context.statement:
            return "SOURCE_LABEL_MISMATCH"
        if observation.raw_unit and not re.search(
            r"(?<![\w])" + re.escape(observation.raw_unit) + r"(?![\w])", context.statement
        ):
            return "SOURCE_UNIT_MISMATCH"
        return None
    split = _field(context.statement.strip(), observation.raw_value)
    label, body = split if split else ("", context.statement.strip())
    if observation.source_label is not None and _fold(
        _label_parts(observation.source_label)[0]
    ) != (_fold(_label_parts(label)[0])):
        return "SOURCE_LABEL_MISMATCH"
    suffix = _value_body(body, observation.raw_value, numeric=True)
    if suffix is None:
        return "SOURCE_VALUE_MISMATCH"
    units = {suffix, _label_parts(label)[1], label if label in {"AF", "AT", "%Z"} else None}
    units.update(_label_units(label))
    if observation.raw_unit is not None and observation.raw_unit not in units:
        return "SOURCE_UNIT_MISMATCH"
    return None


def _representable_number(value: Decimal) -> bool:
    # PostgreSQL unconstrained NUMERIC capacity; no equipment operating thresholds.
    return -16383 <= value.adjusted() < 131072 and -16383 <= value.as_tuple().exponent < 131072


def interpret_attribute(
    observation: AttributeObservation,
    context: InterpretationContext,
) -> Interpretation:
    observation = AttributeObservation.model_validate(observation.model_dump())
    result = Interpretation(
        MappingStatus.UNMAPPED,
        "UNKNOWN_ATTRIBUTE_MEANING",
        observation.raw_expression,
        raw_value=observation.raw_value,
        raw_unit=observation.raw_unit,
    )
    source_failure = _source_fields(observation, context)
    if source_failure:
        return _reject(result, source_failure)
    if observation.ambiguous:
        return _unmapped(result, "AMBIGUOUS_OBSERVATION")
    if observation.raw_value is None:
        return _unmapped(result, "MISSING_VALUE")
    split = _field(context.statement.strip(), observation.raw_value)
    if split is None:
        return _unmapped(result, "UNRESOLVED_SOURCE_FIELD")
    label, body = split
    if observation.source_label is not None and _fold(
        _label_parts(observation.source_label)[0]
    ) != (_fold(_label_parts(label)[0])):
        return _reject(result, "SOURCE_LABEL_MISMATCH")
    equipment = _equipment_type(context.equipment_text or label)
    if equipment is None:
        return _unmapped(result, "NO_EQUIPMENT_CONTEXT")
    result = replace(result, equipment_type_key=equipment)
    if observation.proposed_equipment_type not in (None, equipment):
        return _unmapped(result, "EQUIPMENT_PROPOSAL_CONFLICT")
    definition = _attribute(equipment, label, context)
    if definition is None:
        return result
    if observation.proposed_attribute_key not in (None, definition.key):
        return _unmapped(result, "ATTRIBUTE_PROPOSAL_CONFLICT")
    numeric = definition.value_type in {AttributeValueType.NUMBER, AttributeValueType.INTEGER}
    suffix = _value_body(body, observation.raw_value, numeric)
    if suffix is None:
        return _reject(result, "SOURCE_VALUE_MISMATCH")
    _, header_unit = _label_parts(label)
    header_unit = header_unit if numeric else None
    label_units = _label_units(label) if numeric else set()
    if len(label_units) > 1:
        return _unmapped(result, "CONFLICTING_SOURCE_UNITS")
    if header_unit is None and label_units:
        header_unit = next(iter(label_units))
    shorthand = label if label in {"AF", "AT", "%Z"} else None
    source_unit = suffix or header_unit or shorthand
    if suffix and header_unit and suffix != header_unit:
        return _unmapped(result, "CONFLICTING_SOURCE_UNITS")
    if observation.raw_unit is not None and observation.raw_unit != source_unit:
        return _reject(result, "SOURCE_UNIT_MISMATCH")
    result = replace(result, raw_unit=source_unit)
    input_unit = {"AF": "A", "AT": "A", "%Z": "%"}.get(source_unit, source_unit)
    if numeric and definition.canonical_unit is not None and input_unit is None:
        return _unmapped(result, "MISSING_UNIT")
    value: object = observation.raw_value
    if numeric:
        if "," in observation.raw_value:
            return _unmapped(result, "AMBIGUOUS_NUMERIC_FORMAT")
        if _NUMBER.fullmatch(observation.raw_value) is None:
            return _invalid(result, "INVALID_NUMERIC_VALUE")
        try:
            value = Decimal(observation.raw_value)
        except DecimalException:
            return _invalid(result, "INVALID_NUMERIC_VALUE")
        if not value.is_finite():
            return _invalid(result, "INVALID_NUMERIC_VALUE")
        # Storage representation limits, not inferred engineering operating limits.
        if definition.value_type == AttributeValueType.INTEGER and not (
            _INTEGER_MIN <= value <= _INTEGER_MAX
        ):
            return _invalid(result, "INTEGER_OUT_OF_RANGE")
        if not _representable_number(value):
            return _invalid(result, "NUMBER_OUT_OF_RANGE")
    elif definition.value_type == AttributeValueType.ENUM:
        value = _enum_value(equipment, definition, observation.raw_value)
        if value is None:
            return _unmapped(result, "UNKNOWN_ENUM_EXPRESSION")
    elif definition.value_type == AttributeValueType.BOOLEAN:
        value = _BOOLEAN.get(observation.raw_value.casefold())
        if value is None:
            return _invalid(result, "INVALID_BOOLEAN_VALUE")
    try:
        normalized = normalize_attribute_value(equipment, definition.key, value, input_unit)
    except (EngineeringModelError, DecimalException):
        return _invalid(result, "REGISTRY_NORMALIZATION_FAILED")
    if isinstance(normalized, Decimal) and not _representable_number(normalized):
        return _invalid(result, "NUMBER_OUT_OF_RANGE")
    return replace(
        result,
        mapping_status=MappingStatus.MAPPED,
        reason_code="ATTRIBUTE_NORMALIZED",
        attribute_key=definition.key,
        value_type=definition.value_type,
        value=normalized,
        unit=definition.canonical_unit,
    )


def interpretation_identity() -> dict:
    return {
        "version": VERSION,
        "rules_hash": content_hash(
            files("powerforge_extraction")
            .joinpath("interpretation_v1.py")
            .read_text(encoding="utf-8")
        ),
        "registry_projection_hash": registry_projection_hash(),
        "terminology_hash": terminology_hash(),
    }
