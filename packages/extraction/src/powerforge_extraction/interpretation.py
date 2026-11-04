"""Versioned pure engineering interpretation. Artifact admission remains an M3 responsibility."""

from powerforge_extraction import interpretation_v1 as v1
from powerforge_extraction.interpretation_v1 import Interpretation, InterpretationContext
from powerforge_extraction.observations import AttributeObservation, EquipmentObservation

INTERPRETATION_VERSION = v1.VERSION
__all__ = [
    "INTERPRETATION_VERSION",
    "Interpretation",
    "InterpretationContext",
    "interpret_attribute",
    "interpret_equipment",
    "interpretation_identity",
]


def _version(version: str) -> None:
    if version != INTERPRETATION_VERSION:
        raise ValueError("Unsupported engineering interpretation version")


def interpret_equipment(
    observation: EquipmentObservation,
    context: InterpretationContext,
    *,
    version: str = INTERPRETATION_VERSION,
) -> Interpretation:
    _version(version)
    return v1.interpret_equipment(observation, context)


def interpret_attribute(
    observation: AttributeObservation,
    context: InterpretationContext,
    *,
    version: str = INTERPRETATION_VERSION,
) -> Interpretation:
    _version(version)
    return v1.interpret_attribute(observation, context)


def interpretation_identity(version: str = INTERPRETATION_VERSION) -> dict:
    _version(version)
    return v1.interpretation_identity()
