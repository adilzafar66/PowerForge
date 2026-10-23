"""Pure completeness evaluation; results never prevent saving incomplete equipment."""

from collections import defaultdict
from collections.abc import Mapping

from powerforge_engineering_model.definitions import (
    AttributeState,
    MissingAlternative,
    RequirementCondition,
    RequirementResult,
    RequirementRule,
)
from powerforge_engineering_model.enums import (
    ConditionType,
    EquipmentType,
    InformationState,
    RequirementRuleType,
    RequirementStatus,
)
from powerforge_engineering_model.errors import InvalidAttributeValue
from powerforge_engineering_model.registry import (
    get_attribute_definition,
    get_equipment_definition,
    normalize_attribute_value,
)


def _present(values: Mapping[str, AttributeState], key: str) -> bool:
    state = values.get(key)
    return state is not None and state.information_state == InformationState.PRESENT


def _condition_applies(
    condition: RequirementCondition,
    values: Mapping[str, AttributeState],
    context: Mapping[str, bool],
) -> bool | None:
    match condition.kind:
        case ConditionType.ALWAYS:
            return True
        case ConditionType.EXTERNAL_CONTEXT:
            assert condition.context_key is not None
            return context.get(condition.context_key)
        case ConditionType.ANY_PRESENT:
            return any(_present(values, key) for key in condition.attributes)
        case ConditionType.ATTRIBUTE_EQUALS | ConditionType.ATTRIBUTE_IN:
            assert condition.attribute is not None
            if not _present(values, condition.attribute):
                return None
            return values[condition.attribute].value in condition.values
    raise AssertionError("Registry condition was not validated")


def evaluate_requirements(
    equipment_type: EquipmentType | str,
    attribute_values: Mapping[str, AttributeState],
    external_context: Mapping[str, bool] | None = None,
) -> tuple[RequirementResult, ...]:
    """Evaluate unconditional flags and groups in registry order.

    External context uses the rule's context_key (the stable rule ID) and strict bools.
    Non-PRESENT states must have no value; PRESENT values must match the registry.
    Unknown selectors return NOT_EVALUATED, never an assumed NOT_APPLICABLE.
    """
    equipment = get_equipment_definition(equipment_type)
    values: dict[str, AttributeState] = {}
    for key, state in attribute_values.items():
        get_attribute_definition(equipment_type, key)
        if not isinstance(state, AttributeState) or not isinstance(
            state.information_state,
            InformationState,
        ):
            raise InvalidAttributeValue(f"{key} requires an AttributeState with InformationState")
        if state.information_state == InformationState.PRESENT:
            values[key] = AttributeState(
                state.information_state,
                normalize_attribute_value(equipment_type, key, state.value),
            )
        else:
            if state.value is not None:
                raise InvalidAttributeValue(f"Non-PRESENT attribute {key} cannot contain a value")
            values[key] = state
    context = external_context if external_context is not None else {}
    context_keys = {
        row.condition.context_key
        for row in equipment.requirements
        if row.condition.kind == ConditionType.EXTERNAL_CONTEXT
    }
    for key, value in context.items():
        if key not in context_keys or type(value) is not bool:
            raise InvalidAttributeValue(f"Unknown context key or non-boolean context: {key!r}")
    results: list[RequirementResult] = []
    for attribute in equipment.attributes:
        if attribute.required:
            satisfied = _present(values, attribute.key)
            results.append(
                RequirementResult(
                    f"REQUIRED:{attribute.key}",
                    RequirementStatus.SATISFIED if satisfied else RequirementStatus.UNSATISFIED,
                    () if satisfied else (MissingAlternative(None, (attribute.key,)),),
                )
            )
    groups: dict[str, list[RequirementRule]] = defaultdict(list)
    for row in equipment.requirements:
        groups[row.rule_id].append(row)
    for rule_id, rows in groups.items():
        row = rows[0]
        applies = _condition_applies(row.condition, values, context)
        if applies is None:
            results.append(RequirementResult(rule_id, RequirementStatus.NOT_EVALUATED))
            continue
        if not applies:
            results.append(RequirementResult(rule_id, RequirementStatus.NOT_APPLICABLE))
            continue
        if row.rule_type == RequirementRuleType.ALL_OR_NONE and not any(
            _present(values, key) for key in row.attributes
        ):
            results.append(RequirementResult(rule_id, RequirementStatus.NOT_APPLICABLE))
            continue
        alternatives = tuple(
            MissingAlternative(
                item.alternative, tuple(key for key in item.attributes if not _present(values, key))
            )
            for item in rows
        )
        satisfied = any(not alternative.attributes for alternative in alternatives)
        results.append(
            RequirementResult(
                rule_id,
                RequirementStatus.SATISFIED if satisfied else RequirementStatus.UNSATISFIED,
                () if satisfied else alternatives,
            )
        )
    return tuple(results)
