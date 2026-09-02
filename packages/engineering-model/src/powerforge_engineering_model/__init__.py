"""Canonical engineering model vocabulary.

This package must not import AI provider SDKs or electrical analysis software.
Persistence of equipment rows begins in later phases; Phase 0 establishes types only.
"""

from powerforge_engineering_model.enums import (
    EquipmentType,
    InformationState,
    VerificationState,
)

__all__ = ["EquipmentType", "InformationState", "VerificationState"]
