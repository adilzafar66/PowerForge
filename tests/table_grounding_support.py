"""Independently authored table sources/observations; no normalizer-generated expectations."""

import copy
from dataclasses import replace
from uuid import uuid4

from engineering_grounding_support import anchor, page
from powerforge_extraction.table_grounding import context_from_output, convert_table_reconstruction
from powerforge_extraction.table_output import convert_table_interpretation


def schedule(
    rows=None, *, title="2-Winding Transformer Schedule", kind="EQUIPMENT_ROWS", visual=False
):
    rows = rows or [
        ["Equipment", "Capacity (kVA)", "Primary (kV)", "Secondary (V)"],
        ["TX-1", "750", "12.47", "600"],
        ["TX-2", "500", "12.47", "480"],
    ]
    cells = []
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            header = (
                r == 0
                if kind == "EQUIPMENT_ROWS"
                else c == 0
                if kind == "ATTRIBUTE_ROWS"
                else False
            )
            parent = (
                []
                if header
                else [f"c0_{c}"]
                if kind == "EQUIPMENT_ROWS"
                else [f"c{r}_0"]
                if kind == "ATTRIBUTE_ROWS"
                else []
            )
            cells.append(
                dict(
                    local_ref=f"c{r}_{c}",
                    row=r,
                    column=c,
                    row_span=1,
                    column_span=1,
                    state="BLANK" if value == "" else "VALUE",
                    raw_text=value,
                    header_role="COLUMN"
                    if header and kind == "EQUIPMENT_ROWS"
                    else "ROW"
                    if header
                    else "NONE",
                    header_refs=parent,
                    anchors=[anchor(value or "|".join(values), visual=visual)],
                    ambiguous=False,
                    ambiguity_reason=None,
                )
            )
    table = dict(
        local_ref="t1",
        proposed_kind=kind,
        title=dict(
            local_ref="title",
            raw_text=title,
            anchors=[anchor(title, visual=visual)],
            ambiguous=False,
            ambiguity_reason=None,
        )
        if title
        else None,
        notes=[],
        rows=[f"r{i}" for i in range(len(rows))],
        columns=[f"v{i}" for i in range(len(rows[0]))],
        cells=cells,
        anchors=[anchor(title or "|".join(rows[0]), visual=visual)],
        truncated=False,
        truncation_reason=None,
        ambiguous=False,
        ambiguity_reason=None,
    )
    text = (title + "\n" if title else "") + "\n".join("|".join(row) for row in rows)
    return dict(
        schema_version="table-reconstruction-schema-v1", overflowed=False, tables=[table]
    ), text


def equipment(
    ref="e1", *, cell="c1_0", expression="TX-1", typ="TWO_WINDING_TRANSFORMER", tag="TX-1"
):
    return dict(
        local_ref=ref,
        table_ref="t1",
        raw_expression=expression,
        source_refs=[cell, "title"],
        observed_tag=tag,
        observed_name=None,
        proposed_equipment_type=typ,
        ambiguous=False,
        ambiguity_reason=None,
    )


def attribute(
    ref="a1",
    *,
    cell="c1_3",
    label="c0_3",
    value="600",
    expression=None,
    unit="V",
    typ="TWO_WINDING_TRANSFORMER",
    key="secondary_voltage",
    eq="e1",
):
    return dict(
        local_ref=ref,
        table_ref="t1",
        equipment_ref=eq,
        value_cell_ref=cell,
        label_refs=[label],
        unit_refs=[],
        qualifier_refs=[],
        raw_expression=expression or value,
        source_label=None,
        raw_value=value,
        raw_unit=unit,
        proposed_equipment_type=typ,
        proposed_attribute_key=key,
        ambiguous=False,
        ambiguity_reason=None,
    )


def claims(eqs=None, attrs=None):
    return dict(
        schema_version="table-interpretation-schema-v1",
        overflowed=False,
        equipment=eqs if eqs is not None else [equipment()],
        attributes=attrs if attrs is not None else [attribute()],
    )


def converted(reconstruction=None, interpretation=None, *, text=None, image=False):
    reconstruction, generated = (
        schedule() if reconstruction is None else (copy.deepcopy(reconstruction), None)
    )
    sources, storage = page(
        text if text is not None else generated, image=image, stage="TABLE_RECONSTRUCTION"
    )
    output = convert_table_reconstruction(reconstruction, sources)
    target = replace(
        sources,
        spec=replace(
            sources.spec,
            stage="TABLE_INTERPRETATION",
            unit_id=uuid4(),
            unit_key="TABLE_INTERPRETATION:page:000001",
        ),
    )
    context = context_from_output(target, output, sources.spec.unit_id)
    result = convert_table_interpretation(interpretation or claims(), target, context)
    return sources, output, target, context, result, storage
