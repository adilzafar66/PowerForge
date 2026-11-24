"""Lossless Stage 2 presentation of pinned readings and spatial relationships."""

from collections import Counter

from powerforge_extraction.identities import canonical_json

SUPPORT_COLUMNS = ("representation_ref", "kind", "ref")
GROUP_MEMBER_COLUMNS = ("reading_ref", "start", "end", "x", "y", "width", "height")
MAX_GROUP_MEMBERS = 32
MAX_GROUP_CHARS = 2048


def reading_sequences(rows, layout):
    """Group neighbouring clean readings only within an unbranched pinned baseline."""
    cells = {
        ref: (table["ref"], cell["ref"], cell["state"])
        for table in layout["tables"]
        for cell in table["cells"]
        for ref in cell["readings"]
    }
    links = layout.get("reading_sources", {})
    overlap_support = {
        tuple(edge[side][field] for field in SUPPORT_COLUMNS)
        for edge in layout["overlaps"]
        for side in ("left", "right")
    }
    blocked = {
        ref
        for ref, record in links.items()
        if any(
            tuple(member[field] for field in SUPPORT_COLUMNS) in overlap_support
            for member in record["members"]
        )
    }
    edges = [
        (before, after)
        for before, after, basis in layout["order"]["rows"]
        if basis == "SAME_BASELINE"
    ]
    successors = Counter(before for before, _ in edges)
    predecessors = Counter(after for _, after in edges)
    supported = {
        (before, after) for before, after in edges if successors[before] == predecessors[after] == 1
    }

    def eligible(row):
        ref, text, _, alternates, issues, *region = row
        cell = cells.get(ref)
        return (
            ref not in blocked
            and not alternates
            and not issues
            and None not in region
            and text.strip() == text
            and bool(text)
            and "\n" not in text
            and "\r" not in text
            and (cell is None or cell[2] == "READINGS")
        )

    position = 0
    while position < len(rows):
        start = position
        row = rows[start]
        position += 1
        if eligible(row):
            size = len(row[1])
            while position < len(rows) and position - start < MAX_GROUP_MEMBERS:
                previous, member = rows[position - 1], rows[position]
                next_size = size + 1 + len(member[1])
                if (
                    (previous[0], member[0]) not in supported
                    or cells.get(row[0]) != cells.get(member[0])
                    or row[2] != member[2]
                    or next_size > MAX_GROUP_CHARS
                    or not eligible(member)
                ):
                    break
                size = next_size
                position += 1
        yield rows[start:position]


def _groups(rows, layout):
    cells = {
        ref for table in layout["tables"] for cell in table["cells"] for ref in cell["readings"]
    }
    for selected in reading_sequences(rows, layout):
        if len(selected) < 3:
            yield from selected
            continue
        row = selected[0]
        members = []
        offset = 0
        for ref, text, _, _, _, *region in selected:
            end = offset + len(text)
            members.append([ref, offset, end, *region])
            offset = end + 1
        group = {
            "kind": "CELL" if row[0] in cells else "LINE",
            "modality": row[2],
            "text": " ".join(member[1] for member in selected),
            "members": members,
        }
        # The ordinary rows are already in the outer array. Their list brackets
        # are excluded when comparing against the replacement object.
        if len(canonical_json(group).encode()) < len(canonical_json(selected).encode()) - 2:
            yield group
        else:
            yield from selected


def compact_page(page):
    """Replace repeated support objects with table references and group safe readings."""
    layout = page["layout"]
    readings = page["readings"]
    readings["rows"] = list(_groups(readings["rows"], layout))
    readings["member_columns"] = list(GROUP_MEMBER_COLUMNS)

    indices = {}

    def index(support):
        entry = tuple(support[key] for key in SUPPORT_COLUMNS)
        return indices.setdefault(entry, len(indices))

    layout["overlaps"] = [
        [index(edge["left"]), index(edge["right"]), edge["kind"]] for edge in layout["overlaps"]
    ]
    if "reading_sources" in layout:
        layout["reading_sources"] = [
            [ref, [index(item) for item in witness["members"]], index(witness["preferred"])]
            for ref, witness in layout["reading_sources"].items()
        ]
    for item in layout["unresolved"]:
        item["support"] = [index(support) for support in item["support"]]
    for table in layout["tables"]:
        for cell in table["cells"]:
            cell["boundary_support"] = [index(support) for support in cell["boundary_support"]]
    layout["support"] = [list(entry) for entry in indices]


def reading_rows(readings):
    """Iterate original reading rows across both provider presentations."""
    for row in readings["rows"]:
        if isinstance(row, list):
            yield row
        else:
            for ref, start, end, *region in row["members"]:
                yield [ref, row["text"][start:end], row["modality"], [], [], *region]


def expand_compact_page(page):
    """Reconstruct the v1 provider page for fixture and offline coverage comparisons."""
    from copy import deepcopy

    expanded = deepcopy(page)
    readings = expanded["readings"]
    del readings["member_columns"]
    readings["rows"] = list(reading_rows(readings))
    layout = expanded["layout"]
    supports = [dict(zip(SUPPORT_COLUMNS, row, strict=True)) for row in layout.pop("support")]
    layout["overlaps"] = [
        {"left": supports[left], "right": supports[right], "kind": kind}
        for left, right, kind in layout["overlaps"]
    ]
    if "reading_sources" in layout:
        layout["reading_sources"] = {
            ref: {"members": [supports[i] for i in members], "preferred": supports[preferred]}
            for ref, members, preferred in layout["reading_sources"]
        }
    for item in layout["unresolved"]:
        item["support"] = [supports[i] for i in item["support"]]
    for table in layout["tables"]:
        for cell in table["cells"]:
            cell["boundary_support"] = [supports[i] for i in cell["boundary_support"]]
    return expanded
