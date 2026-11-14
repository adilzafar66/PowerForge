"""Preserve page-local observations and normalize only supported registry assertions."""

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, DecimalException

from powerforge_engineering_model.errors import EngineeringModelError
from powerforge_engineering_model.registry import normalize_attribute_value
from powerforge_engineering_model.units import UNITS
from powerforge_extraction.phase6r_contracts import (
    AttributeResponse,
    NoEligibleAttributes,
    RegistryAssertion,
)
from powerforge_extraction.phase6r_evidence import EvidenceLocalizer

VERSION = "phase-6r-publication-v1"
SCALAR = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
BOOLEAN = {"true": True, "yes": True, "false": False, "no": False}


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
    raw = item.raw_value.strip()
    units = set()
    ambiguous = False
    vocabulary = UNITS.keys() | ({reported} if reported else set())
    for fragment in evidence:
        if fragment["localization"] != "RESOLVED":
            continue
        quote = fragment["quote"]
        role = fragment["role"]
        matches = set()
        if role in {"UNIT", "HEADER"} or (reported and role == "LABEL"):
            matches = {unit for unit in vocabulary if _literal_unit(quote, unit)}
            if role == "UNIT" and not matches:
                # A separately cited unsupported expression can conflict with a supported unit.
                matches.add(quote.strip())
        if role == "VALUE":
            for unit in vocabulary:
                # Require the literal raw number beside the unit. An unrelated
                # number in the same source fragment cannot establish its unit.
                number = raw[: -len(unit)].strip() if raw.endswith(unit) else raw
                if SCALAR.fullmatch(number) and re.search(
                    rf"(?<![\w.,+/−-]){re.escape(number)}\s*{re.escape(unit)}(?![\w/])",
                    quote,
                ):
                    matches.add(unit)
        if matches and {"TRANSCRIPTION_CONFLICT", "AMBIGUOUS_OVERLAP"}.intersection(
            fragment.get("source_issues", ())
        ):
            ambiguous = True
        units.update(matches)
    if ambiguous or len(units) != 1 or (reported is not None and reported not in units):
        return None, raw
    unit = units.pop()
    if raw.endswith(unit) and SCALAR.fullmatch(raw[: -len(unit)].strip()):
        raw = raw[: -len(unit)].strip()
    return unit, raw


def _value(item, definition, evidence):
    value_type = definition.value_type
    raw = item.raw_value.strip()
    unit = None
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
            value = item.proposed_enum_value
            if value not in definition.allowed_values:
                return "INVALID", "INVALID_VALUE", {}
        else:
            if not raw:
                return "INVALID", "INVALID_VALUE", {}
            value = item.raw_value
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
        registry_assertion = isinstance(item, RegistryAssertion)
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
            "raw_label": item.raw_label,
            "raw_value": item.raw_value,
            "raw_unit": item.raw_unit,
            "qualifiers": list(item.qualifiers),
            "value_form": item.value_form,
            "proposed_attribute_key": key,
            "proposed_enum_value": item.proposed_enum_value if registry_assertion else None,
            **normalized,
        }
        observations.append(Observation(fields, evidence, issues))
        if normalized:
            comparable[(owner.local_ref, key, tuple(sorted(item.qualifiers)))].append(
                (fields, tuple(normalized.values()))
            )
    for group in comparable.values():
        if len({value for _, value in group}) > 1:
            for fields, _ in group:
                fields["conflict"] = True
    return observations


def publication_diagnostics(observations):
    diagnostics = []
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
