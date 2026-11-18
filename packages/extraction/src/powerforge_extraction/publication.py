"""Preserve page-local observations and normalize only supported registry assertions."""

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from typing import Literal

from powerforge_engineering_model.errors import EngineeringModelError
from powerforge_engineering_model.registry import normalize_attribute_value
from powerforge_engineering_model.units import UNITS
from powerforge_extraction.evidence_localization import EvidenceLocalizer
from powerforge_extraction.stage_contracts import (
    AttributeResponse,
    InferredAssertion,
    NoEligibleAttributes,
    RegistryAssertion,
)

VERSION = "phase-6r-publication-v4"
SCALAR = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
BOOLEAN = {"true": True, "yes": True, "false": False, "no": False}
# Electrical drawing convention only. Never case-fold units or SI prefixes.
SOURCE_UNIT_NOTATIONS = {"KA": "kA"}
ValueSourceSupport = Literal["TEXT_MATCH", "TEXT_MISMATCH", "UNVERIFIED"]


@dataclass
class Observation:
    fields: dict
    evidence: list[dict]
    issues: tuple[str, ...] = ()


def _literal_unit(text, unit):
    # A unit can follow a number directly. Avoid matching suffixes of longer
    # spellings, per-length expressions, and case-sensitive SI prefixes.
    return re.search(rf"(?<![^\W\d_]|[/_°º]){re.escape(unit)}(?![\w/])", text) is not None


def _unit(item, evidence):
    reported = item.raw_unit.strip() if item.raw_unit is not None else None
    reported = SOURCE_UNIT_NOTATIONS.get(reported, reported)
    raw = item.raw_value.strip()
    units = set()
    ambiguous = False
    vocabulary = {unit: unit for unit in UNITS} | SOURCE_UNIT_NOTATIONS
    if reported:
        vocabulary[reported] = reported
    for fragment in evidence:
        if fragment["localization"] != "RESOLVED":
            continue
        quote = fragment["quote"]
        role = fragment["role"]
        matches = set()
        if role in {"UNIT", "HEADER"} or (reported and role == "LABEL"):
            matches = {
                unit for spelling, unit in vocabulary.items() if _literal_unit(quote, spelling)
            }
            if role == "UNIT" and not matches:
                # A separately cited unsupported expression can conflict with a supported unit.
                matches.add(quote.strip())
        if role == "VALUE":
            numbers = set()
            for spelling, unit in vocabulary.items():
                # Require the literal raw number beside the unit. An unrelated
                # number in the same source fragment cannot establish its unit.
                number = raw[: -len(spelling)].strip() if raw.endswith(spelling) else raw
                if not SCALAR.fullmatch(number):
                    continue
                numbers.add(number)
                if re.search(
                    rf"(?<![\w.,+/−-]){re.escape(number)}\s*{re.escape(spelling)}(?![\w/])",
                    quote,
                ):
                    matches.add(unit)
            if matches:
                # Another spelling beside the same literal may change the unit
                # or expose ambiguity. Retain unknown spellings as conflicts.
                for number in numbers:
                    for match in re.finditer(
                        rf"(?<![\w.,+/−-]){re.escape(number)}\s*([A-Za-z][A-Za-z/°]{{0,31}})(?!\w)",
                        quote,
                    ):
                        spelling = match[1]
                        matches.add(vocabulary.get(spelling, spelling))
        if matches and {"TRANSCRIPTION_CONFLICT", "AMBIGUOUS_OVERLAP"}.intersection(
            fragment.get("source_issues", ())
        ):
            ambiguous = True
        units.update(matches)
    if ambiguous or len(units) != 1 or (reported is not None and reported not in units):
        return None, raw
    unit = units.pop()
    for spelling, canonical in vocabulary.items():
        if canonical == unit and raw.endswith(spelling):
            number = raw[: -len(spelling)].strip()
            if SCALAR.fullmatch(number):
                raw = number
                break
    return unit, raw


def _value(item, definition, evidence):
    value_type = definition.value_type
    if isinstance(item, InferredAssertion):
        text = item.proposed_value
        raw = text.strip()
        unit = item.proposed_unit
        enum = item.proposed_value
        if definition.canonical_unit is not None and unit is None:
            return "UNMAPPED", "UNIT_MISSING_OR_AMBIGUOUS", {}
    else:
        text = item.raw_value
        raw = text.strip()
        unit = None
        enum = item.proposed_enum_value
        if definition.canonical_unit is not None or item.raw_unit is not None:
            unit, raw = _unit(item, evidence)
            if unit is None:
                return "UNMAPPED", "UNIT_MISSING_OR_AMBIGUOUS", {}
        if item.value_form != "SINGLE" or item.qualifiers:
            return "UNMAPPED", "UNREPRESENTABLE_VALUE_FORM", {}
    if unit is not None and unit not in definition.supported_units:
        return "INVALID", "INVALID_UNIT", {}
    try:
        if value_type in {"NUMBER", "INTEGER"}:
            if len(raw) > 128 or not SCALAR.fullmatch(raw):
                return "INVALID", "INVALID_VALUE", {}
            value = Decimal(raw)
            if abs(value.adjusted()) > 256 or abs(value.as_tuple().exponent) > 256:
                return "INVALID", "INVALID_VALUE", {}
        elif value_type == "BOOLEAN":
            value = BOOLEAN[raw.casefold()]
        elif value_type == "ENUM":
            value = enum
            if value not in definition.allowed_values:
                return "INVALID", "INVALID_VALUE", {}
        else:
            if not raw:
                return "INVALID", "INVALID_VALUE", {}
            value = text
        value = normalize_attribute_value(definition.equipment_type, definition.key, value, unit)
        if value_type == "INTEGER" and not -(2**63) <= value < 2**63:
            return "INVALID", "INVALID_VALUE", {}
    except (EngineeringModelError, DecimalException, KeyError):
        return "INVALID", "INVALID_VALUE", {}
    slot = {"ENUM": "text", "TEXT": "text"}.get(value_type, value_type.lower())
    return (
        "MAPPED",
        None,
        {
            "normalized_type": value_type,
            "normalized_unit": definition.canonical_unit,
            f"value_{slot}": value,
        },
    )


def _value_source_support(item, definition, evidence, localizer) -> ValueSourceSupport:
    if item.value_form != "SINGLE" or item.qualifiers:
        return "UNVERIFIED"
    texts = set()
    incomplete = False
    for fragment in evidence:
        identifier = (
            definition is not None
            and definition.key in {"model", "catalog_number", "trip_unit_model"}
            and fragment["role"] == "EQUIPMENT"
        )
        if fragment["role"] != "VALUE" and not identifier:
            continue
        text = localizer.value_text(fragment)
        if text is None:
            if fragment["localization"] == "RESOLVED":
                return "UNVERIFIED"
            incomplete = True
        else:
            texts.add(text)
    raw = item.raw_value.strip()
    # An unresolved supplemental citation does not undo an exact reading citation.
    if texts == {raw}:
        return "TEXT_MATCH"
    # Compare only a unanimous, complete alternate scalar. Ignore alternate
    # numeric spellings of the same magnitude without calling them text matches.
    if len(texts) == 1 and not incomplete:
        (text,) = texts
        if all(0 < len(value) <= 128 and SCALAR.fullmatch(value) for value in (raw, text)):
            try:
                if Decimal(raw) != Decimal(text):
                    return "TEXT_MISMATCH"
            except DecimalException:
                pass
    return "UNVERIFIED"


def build_publication(wire, result, source):
    if isinstance(result, NoEligibleAttributes):
        return []
    localizer = EvidenceLocalizer(source)
    if not isinstance(result, AttributeResponse):
        return [
            Observation(
                {
                    "kind": "EQUIPMENT",
                    "local_ref": item.local_ref,
                    "mapping_status": "MAPPED" if item.registry_type is not None else "UNMAPPED",
                    "reason_code": None
                    if item.registry_type is not None
                    else "UNKNOWN_EQUIPMENT_TYPE",
                    "source_description": item.source_description,
                    "registry_type": item.registry_type,
                    "tag": item.tag,
                    "tag_state": item.tag_state,
                    "qualification": item.qualification,
                    "raw_qualification": item.raw_qualification,
                },
                localizer.locate(item.evidence, "EQUIPMENT"),
            )
            for item in result.equipment
        ]

    owners = {item.local_ref: item for item in wire.upstream.equipment}
    definitions = {(item.equipment_type, item.key): item for item in wire.attribute_catalog}
    observations = []
    comparable = defaultdict(list)
    for item in (*result.attributes, *result.raw_unmapped):
        inferred = isinstance(item, InferredAssertion)
        registry_assertion = inferred or isinstance(item, RegistryAssertion)
        if inferred:
            evidence = [
                {
                    "role": "VALUE",
                    "localization": "UNRESOLVED",
                    "reason_code": "INFERRED_VALUE_CITATION",
                }
                if citation.role == "VALUE"
                else localizer.locate((citation,), "CONTEXT")[0]
                for citation in item.evidence
            ]
        else:
            evidence = localizer.locate(item.evidence, "VALUE")
        owner = owners.get(item.equipment_ref)
        if (
            item.association == "UNASSIGNED"
            or owner is None
            or owner.registry_type is None
            or owner.qualification == "LEGEND_ONLY"
        ):
            owner = None
        issues = ()
        if owner is None and (item.association != "UNASSIGNED" or item.equipment_ref is not None):
            issues = ("INVALID_OWNER_REFERENCE",)
        key = item.attribute_key if registry_assertion else None
        definition = definitions.get((owner.registry_type, key)) if owner else None
        if not registry_assertion:
            status, reason, normalized = "UNMAPPED", "UNSUPPORTED_ATTRIBUTE", {}
        elif owner is None:
            status, reason, normalized = "UNMAPPED", "UNASSIGNED_OWNER", {}
        elif definition is None:
            status, reason, normalized = "UNMAPPED", "UNKNOWN_ATTRIBUTE_KEY", {}
        else:
            status, reason, normalized = _value(item, definition, evidence)
        fields = {
            "kind": "ATTRIBUTE",
            "local_ref": item.local_ref,
            "mapping_status": status,
            "reason_code": reason,
            "owner_ref": owner.local_ref if owner else None,
            "claimed_owner_ref": item.equipment_ref,
            "association": item.association if owner else "UNASSIGNED",
            "raw_unmapped": not registry_assertion,
            "attribute_origin": "INFERRED" if inferred else "EXTRACTED",
            "proposed_attribute_key": key,
            **normalized,
        }
        if inferred:
            fields.update(
                proposed_value=item.proposed_value,
                proposed_unit=item.proposed_unit,
                inference_explanation=item.inference_explanation,
                inference_basis=item.inference_basis,
                value_source_support="UNVERIFIED",
            )
        else:
            fields.update(
                raw_label=item.raw_label,
                raw_value=item.raw_value,
                raw_unit=item.raw_unit,
                value_source_support=_value_source_support(item, definition, evidence, localizer),
                qualifiers=list(item.qualifiers),
                value_form=item.value_form,
                proposed_enum_value=item.proposed_enum_value if registry_assertion else None,
            )
        observations.append(Observation(fields, evidence, issues))
        if normalized:
            qualifiers = tuple(sorted(fields.get("qualifiers", ())))
            comparable[(owner.local_ref, key, qualifiers)].append(
                (fields, tuple(normalized.values()))
            )
    for group in comparable.values():
        if len({value for _, value in group}) > 1:
            for fields, _ in group:
                fields["conflict"] = True
    return observations


def publication_diagnostics(observations, redundant=None):
    diagnostics = [
        {"ref": ref, "related_ref": primary, "code": "LIKELY_REDUNDANT_ASSERTION"}
        for ref, primary in (redundant or {}).items()
    ]
    for item in observations:
        ref = item.fields["local_ref"]
        diagnostics.extend({"ref": ref, "code": code} for code in item.issues)
        diagnostics.extend(
            {"ref": ref, "citation": index, "code": fragment["reason_code"]}
            for index, fragment in enumerate(item.evidence)
            if fragment["localization"] == "UNRESOLVED" and fragment["reason_code"] != "NO_CITATION"
        )
    if len(diagnostics) > 128:
        return [*diagnostics[:127], {"code": "DIAGNOSTIC_LIMIT", "omitted": len(diagnostics) - 127}]
    return diagnostics
