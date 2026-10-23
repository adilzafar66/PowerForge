"""Pure effective-value semantics for revision-level engineering assumptions."""

from decimal import Decimal

from powerforge_engineering_model.definitions import AttributeState, EffectiveModelValue
from powerforge_engineering_model.enums import InformationState
from powerforge_engineering_model.errors import InvalidAttributeValue


def resolve_effective_model_value(
    explicit: AttributeState | None,
    revision_value: Decimal | int | None,
) -> EffectiveModelValue:
    """Prefer an explicit PRESENT value, otherwise use the revision default.

    The explicit state is never modified. A disagreement is reported while both
    values are preserved by their callers; persistent validation belongs to Phase 10.
    """
    if explicit is not None and explicit.information_state == InformationState.PRESENT:
        if explicit.value is None or isinstance(explicit.value, (str, bool)):
            raise InvalidAttributeValue("Effective engineering values must be numeric")
        mismatch = revision_value is not None and explicit.value != revision_value
        return EffectiveModelValue(explicit.value, "EQUIPMENT", mismatch)
    if revision_value is not None:
        return EffectiveModelValue(revision_value, "REVISION")
    return EffectiveModelValue(None, "UNSPECIFIED")
