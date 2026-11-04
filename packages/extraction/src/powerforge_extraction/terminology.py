"""Small scoped terminology policy; declarative proposals, never an alternate registry.

M2 must independently verify the source and each qualification before applying a term.
No resolver, enum coercion or unit conversion is implemented here.
"""

from dataclasses import asdict, dataclass
from typing import Literal

from powerforge_extraction.identities import identity_hash

TERMINOLOGY_VERSION = "engineering-terminology-v1"


@dataclass(frozen=True)
class TerminologyEntry:
    key: str
    kind: Literal["EQUIPMENT_NAME", "ATTRIBUTE_LABEL", "ENUM_VALUE"]
    equipment_type: str
    attribute_key: str | None
    enum_value: str | None
    expressions: tuple[str, ...]
    qualification: str


TERMINOLOGY = (
    TerminologyEntry(
        "lv-breaker-name",
        "EQUIPMENT_NAME",
        "LV_BREAKER",
        None,
        None,
        ("LV circuit breaker", "low-voltage circuit breaker"),
        "Explicit low-voltage breaker wording; an unqualified breaker tag is insufficient.",
    ),
    TerminologyEntry(
        "transformer-capacity",
        "ATTRIBUTE_LABEL",
        "TWO_WINDING_TRANSFORMER",
        "rated_apparent_power",
        None,
        ("Rated Capacity", "kVA rating"),
        "Confirmed two-winding transformer context and an explicit apparent-power unit.",
    ),
    TerminologyEntry(
        "transformer-normal-impedance",
        "ATTRIBUTE_LABEL",
        "TWO_WINDING_TRANSFORMER",
        "positive_sequence_impedance",
        None,
        ("Impedance", "%Z"),
        "Explicit normal two-winding/nameplate impedance context; not isolated, zero-sequence "
        "or uncertain base data. Never infer another sequence value or convert percent/per-unit.",
    ),
    TerminologyEntry(
        "breaker-frame",
        "ATTRIBUTE_LABEL",
        "LV_BREAKER",
        "frame_rating",
        None,
        ("AF", "Ampere Frame"),
        "Confirmed LV breaker and explicit frame-rating expression. No sensor or plug inference.",
    ),
    TerminologyEntry(
        "breaker-trip",
        "ATTRIBUTE_LABEL",
        "LV_BREAKER",
        "trip_rating",
        None,
        ("AT", "Ampere Trip"),
        "Confirmed thermal-magnetic LV breaker trip-rating context. Ambiguous/electronic "
        "devices do not establish trip_rating, sensor, plug or long_time_pickup from AT alone.",
    ),
    TerminologyEntry(
        "copper-symbol",
        "ENUM_VALUE",
        "CABLE",
        "conductor_material",
        "COPPER",
        ("Cu",),
        "Explicit conductor-material context; a symbol in a model identifier is insufficient.",
    ),
    TerminologyEntry(
        "aluminum-symbol",
        "ENUM_VALUE",
        "CABLE",
        "conductor_material",
        "ALUMINUM",
        ("Al",),
        "Explicit conductor-material context; preserve unknown or mixed materials as unmapped.",
    ),
    TerminologyEntry(
        "utility-three-phase-current",
        "ATTRIBUTE_LABEL",
        "UTILITY_SOURCE",
        "three_phase_fault_current",
        None,
        ("3PH fault current", "3-phase Isc"),
        "Explicit three-phase utility fault-current label/basis and current unit.",
    ),
    TerminologyEntry(
        "utility-slg-current",
        "ATTRIBUTE_LABEL",
        "UTILITY_SOURCE",
        "slg_fault_current",
        None,
        ("SLG fault current", "L-G fault current"),
        "Explicit single-line-to-ground utility fault-current label/basis and current unit.",
    ),
)


def terminology_policy() -> dict:
    return {
        "version": TERMINOLOGY_VERSION,
        "entries": [asdict(entry) for entry in TERMINOLOGY],
    }


def terminology_hash() -> str:
    return identity_hash(terminology_policy())
