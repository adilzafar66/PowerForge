"""Provider-only Stage 2 objects and structural expansion into the current wire contract."""

from typing import Annotated, Literal

from pydantic import Field

from powerforge_extraction.stage_contracts import (
    MAX_ALTERNATE_REPRESENTATIONS,
    MAX_ATTRIBUTE_ASSERTIONS,
    MAX_CITATIONS,
    AlternateRepresentation,
    AssertionValue,
    Association,
    Contract,
    InferenceBasis,
    ProposedValue,
    Quote,
    Raw,
    Ref,
    ReportedRegion,
    Role,
    Short,
)

OUTPUT_VERSION = "compact-assertions-v1"
RAW_RECEIVE_LIMIT = 32

FIELD_NAMES = {
    "equipment": "equipment_ref",
    "key": "attribute_key",
    "raw": "raw_value",
    "label": "raw_label",
    "source_unit": "raw_unit",
    "value": "proposed_value",
    "unit": "proposed_unit",
    "form": "value_form",
    "alternates": "alternate_representations",
}
PROVIDER_NAMES = {full: short for short, full in FIELD_NAMES.items()}


class Reading(Contract):
    role: Role
    reading: Ref


class ReadingQuote(Reading):
    quote: Quote


class LiteralQuote(Contract):
    role: Role
    quote: Quote


class Visual(Contract):
    role: Role
    region: ReportedRegion
    reported_text: Quote | None


CompactCitations = Annotated[
    tuple[Reading | ReadingQuote | LiteralQuote | Visual, ...], Field(max_length=MAX_CITATIONS)
]


class Reported(Contract):
    equipment: Ref | None
    association: Association
    raw: AssertionValue
    source_unit: Short | None
    qualifiers: Annotated[tuple[Short, ...], Field(max_length=8)]
    form: Literal["SINGLE", "RANGE", "MULTIPLE", "QUALIFIED"]
    evidence: CompactCitations


class CompactExtracted(Reported):
    origin: Literal["EXTRACTED"]
    key: Ref
    label: Short | None
    value: ProposedValue | None
    unit: Short | None
    form: Literal["SINGLE", "RANGE", "MULTIPLE", "QUALIFIED", "EQUIVALENT_UNITS"]
    alternates: Annotated[
        tuple[AlternateRepresentation, ...], Field(max_length=MAX_ALTERNATE_REPRESENTATIONS)
    ]


class CompactInferred(Contract):
    origin: Literal["INFERRED"]
    equipment: Ref
    association: Literal["ASSERTED", "UNCERTAIN"]
    key: Ref
    value: ProposedValue
    unit: Short | None
    inference_explanation: str
    inference_basis: InferenceBasis | None
    source_expression: Raw | None
    evidence: CompactCitations


class CompactUnmapped(Reported):
    label: Short
    display_label: Short | None


class CompactAttributeResponse(Contract):
    attributes: Annotated[
        tuple[CompactExtracted | CompactInferred, ...], Field(max_length=MAX_ATTRIBUTE_ASSERTIONS)
    ]
    raw_unmapped: Annotated[tuple[CompactUnmapped, ...], Field(max_length=RAW_RECEIVE_LIMIT)]


def assertion_ref(collection, index):
    return f"{'attr' if collection == 'attributes' else 'raw'}-{index}"


def expand_assertion(assertion, ref):
    fields = assertion.model_dump(mode="json")
    evidence = []
    for citation in fields.pop("evidence"):
        if "reading" in citation:
            evidence.append(
                {
                    "kind": "READING",
                    "role": citation["role"],
                    "reading_ref": citation["reading"],
                    "quote": citation.get("quote"),
                }
            )
        elif "region" in citation:
            evidence.append({"kind": "VISUAL", **citation})
        else:
            evidence.append({"kind": "QUOTE", **citation})
    return {
        "local_ref": ref,
        **{FIELD_NAMES.get(key, key): value for key, value in fields.items()},
        "evidence": evidence,
    }


def compact_assertion(item):
    """Project a retained legacy assertion for offline comparison."""
    if not isinstance(item, dict):
        return item
    compact = {
        PROVIDER_NAMES.get(key, key): value
        for key, value in item.items()
        if key not in ("local_ref", "evidence")
    }
    if "evidence" in item:
        compact["evidence"] = item["evidence"]
    if isinstance(item.get("evidence"), list):
        evidence = []
        for original in item["evidence"]:
            if not isinstance(original, dict):
                evidence.append(original)
                continue
            citation = dict(original)
            kind = citation.get("kind")
            if kind in ("READING", "QUOTE", "VISUAL"):
                citation.pop("kind")
            if kind == "READING" and "reading_ref" in citation:
                citation["reading"] = citation.pop("reading_ref")
                if citation.get("quote") is None:
                    citation.pop("quote", None)
            evidence.append(citation)
        compact["evidence"] = evidence
    return compact
