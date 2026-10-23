"""Pure Phase 5C effective-value and mismatch semantics."""

from decimal import Decimal

import pytest

from powerforge_engineering_model import (
    AttributeState,
    InformationState,
    resolve_effective_model_value,
)
from powerforge_engineering_model.errors import InvalidAttributeValue


def test_explicit_value_wins_and_reports_frequency_mismatch() -> None:
    result = resolve_effective_model_value(
        AttributeState(InformationState.PRESENT, Decimal("50")), Decimal("60")
    )
    assert result.value == Decimal("50")
    assert result.source == "EQUIPMENT"
    assert result.mismatch


def test_revision_default_applies_without_changing_nonpresent_state() -> None:
    state = AttributeState(InformationState.NOT_EXTRACTED)
    result = resolve_effective_model_value(state, Decimal("60"))
    assert result.value == Decimal("60")
    assert result.source == "REVISION"
    assert not result.mismatch
    assert state == AttributeState(InformationState.NOT_EXTRACTED)


def test_phase_mismatch_and_unspecified_values_are_observable() -> None:
    mismatch = resolve_effective_model_value(AttributeState(InformationState.PRESENT, 1), 3)
    assert (mismatch.value, mismatch.source, mismatch.mismatch) == (1, "EQUIPMENT", True)
    assert resolve_effective_model_value(None, None).source == "UNSPECIFIED"


def test_malformed_present_value_is_rejected() -> None:
    with pytest.raises(InvalidAttributeValue):
        resolve_effective_model_value(AttributeState(InformationState.PRESENT, None), 3)
