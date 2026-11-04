"""Pure observation/context builders; no artifact admission or candidate publication."""

from powerforge_extraction.interpretation import InterpretationContext
from powerforge_extraction.observations import AttributeObservation, EquipmentObservation


def attribute(
    label,
    value,
    unit,
    key,
    *,
    equipment="2-Winding Transformer TX-1",
    equipment_type="TWO_WINDING_TRANSFORMER",
    statement=None,
    ambiguous=False,
):
    source = (
        statement if statement is not None else f"{label}: {value}" + (f" {unit}" if unit else "")
    )
    observation = AttributeObservation(
        local_ref="a1",
        raw_expression=source,
        equipment_ref=None,
        source_label=label,
        raw_value=value,
        raw_unit=unit,
        proposed_equipment_type=equipment_type,
        proposed_attribute_key=key,
        ambiguous=ambiguous,
        ambiguity_reason="Source meaning is uncertain" if ambiguous else None,
        anchors=[
            dict(
                kind="NATIVE_TEXT", source_ref="native_text", quote=source, prefix=None, suffix=None
            )
        ],
    )
    return observation, InterpretationContext(source, equipment)


def equipment(expression, proposed, tag=None, *, ambiguous=False):
    observation = EquipmentObservation(
        local_ref="eq1",
        raw_expression=expression,
        proposed_equipment_type=proposed,
        observed_tag=tag,
        observed_name=None,
        ambiguous=ambiguous,
        ambiguity_reason="Equipment category is uncertain" if ambiguous else None,
        anchors=[
            dict(
                kind="NATIVE_TEXT",
                source_ref="native_text",
                quote=expression,
                prefix=None,
                suffix=None,
            )
        ],
    )
    return observation, InterpretationContext(expression)
