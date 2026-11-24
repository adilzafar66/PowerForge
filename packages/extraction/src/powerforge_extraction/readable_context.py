"""Readable Stage 2 page data. Only q references identify citable occurrences."""

from itertools import pairwise

from powerforge_extraction.compact_context import reading_sequences


def _box(region):
    if region is not None:
        values = region.model_dump(mode="json")
        return [values[k] for k in ("x", "y", "width", "height")]
    return None


def reading_blocks(page):
    """All literal occurrences, including readings placed directly in confirmed cells."""
    yield from page.get("blocks", ())
    for table in page.get("tables", ()):
        for row in table.get("rows", ()):
            for cell in row:
                yield from cell.get("blocks", ())


def readable_page(page):
    layout = page.layout
    members = {m: r.ref for r in layout.readings for m in r.members}
    overlaps = [[members[o.left], members[o.right], o.kind] for o in layout.overlaps]
    blocked = {ref for left, right, _ in overlaps for ref in (left, right)}
    blocked.update(
        ref
        for table in layout.tables
        if table.structure_basis == "UNRESOLVED"
        for cell in table.cells
        for ref in cell.readings
    )
    rows = []
    annotations = {}
    for reading, location in zip(page.readings, layout.readings, strict=True):
        box = _box(location.region)
        ref = reading.reading_ref
        rows.append(
            [
                ref,
                reading.text,
                reading.modality,
                reading.alternate_texts,
                location.issues or (ref in blocked),
                *(box or [None] * 4),
            ]
        )
        details = {}
        if reading.alternate_texts:
            details["alternatives"] = [
                [member.representation_ref, text]
                for member, text in zip(
                    (m for m in location.members if m != location.preferred),
                    reading.alternate_texts,
                    strict=True,
                )
            ]
        if location.issues:
            details["issues"] = location.issues
        if details:
            annotations[ref] = details
    tables = [
        t.model_dump(mode="json", exclude={"cells": {"__all__": {"boundary_support"}}})
        for t in layout.tables
    ]
    order = [[e.before, e.after, e.basis] for e in layout.order]
    cell_blocks = {}
    presented_tables = []
    for table in tables:
        record = {"box": table["region"], "basis": table["structure_basis"]}
        if table["captions"]:
            record["captions"] = table["captions"]
        presented_tables.append(record)
        if table["structure_basis"] == "UNRESOLVED":
            continue
        record.update(
            method=table["method"],
            header_basis=table["header_basis"],
            rows=[[] for _ in range(table["rows"])],
        )
        for cell in sorted(table["cells"], key=lambda c: (c["row"], c["column"])):
            item = {"cell": cell["ref"], "column": cell["column"]}
            record["rows"][cell["row"]].append(item)
            if cell["row_span"] != 1 or cell["column_span"] != 1:
                item["span"] = [cell["row_span"], cell["column_span"]]
            if cell["header_role"] == "COLUMN":
                item["header"] = True
            if cell["headers"]:
                item["headers"] = cell["headers"]
            if cell["state"] != "READINGS":
                item.update(state=cell["state"], box=cell["region"])
                if cell["readings"]:
                    item["reading_refs"] = cell["readings"]
            else:
                item["blocks"] = []
                cell_blocks.update((ref, item["blocks"]) for ref in cell["readings"])
    sequences = reading_sequences(
        rows, {"tables": tables, "order": {"rows": order}, "overlaps": []}
    )
    blocks = []
    joined = set()
    for sequence in sequences:
        modality = sequence[0][2]
        destination = cell_blocks.get(sequence[0][0], blocks)
        if not destination or destination[-1]["source"] != modality:
            destination.append({"source": modality, "lines": []})
        line = [
            [ref, text, *([coords] if coords[0] is not None else [])]
            for ref, text, _, _, _, *coords in sequence
        ]
        destination[-1]["lines"].append(line)
        joined.update((a[0], b[0]) for a, b in pairwise(line))
    result = {"blocks": blocks}
    if annotations:
        result["notes"] = annotations
    if overlaps:
        result["overlaps"] = overlaps
    remaining = [e for e in order if e[2] != "SAME_BASELINE" or tuple(e[:2]) not in joined]
    if remaining:
        result["order"] = remaining
    if presented_tables:
        result["tables"] = presented_tables
    if layout.unresolved:
        result["unresolved"] = [
            {
                "reason": item.reason,
                **({"box": _box(item.region)} if item.region else {}),
                **(
                    {"readings": refs}
                    if (refs := sorted({members[m] for m in item.support if m in members}))
                    else {}
                ),
            }
            for item in layout.unresolved
        ]
    return result
