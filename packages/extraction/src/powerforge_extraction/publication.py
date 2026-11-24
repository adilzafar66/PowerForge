"""Preserve page-local observations and normalize only supported registry assertions."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from typing import Literal

from powerforge_extraction.evidence_localization import EvidenceLocalizer
from powerforge_extraction.stage_contracts import (
    AttributeResponse,
    InferredAssertion,
    NoEligibleAttributes,
    RegistryAssertion,
)
from powerforge_extraction.unit_notation import SCALAR
from powerforge_extraction.value_proposal import normalize_proposal

VERSION = "phase-6r-publication-v11"
ValueSourceSupport = Literal["TEXT_MATCH", "TEXT_MISMATCH", "UNVERIFIED"]


@dataclass
class Observation:
    fields: dict
    evidence: list[dict]
    issues: tuple[str, ...] = ()


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
    localizer = EvidenceLocalizer(
        source, getattr(wire, "input_version", None), getattr(wire, "page", None)
    )
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
        eligible = [
            f
            for f in evidence
            if f.get("reason_code")
            not in {"READING_NOT_EXPOSED", "QUOTE_NOT_EXPOSED", "IMAGE_NOT_EXPOSED"}
        ]
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
            status, reason, normalized = normalize_proposal(item, definition, eligible)
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
                value_source_support=_value_source_support(item, definition, eligible, localizer),
                qualifiers=list(item.qualifiers),
                value_form=item.value_form,
            )
        if isinstance(item, RegistryAssertion):
            fields.update(
                proposed_value=item.proposed_value,
                proposed_unit=item.proposed_unit,
                alternate_representations=[
                    alternate.model_dump(mode="json")
                    for alternate in item.alternate_representations
                ],
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
