"""Conservative closed native grids and small repeated-alignment tables; no registry."""

import re
from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from powerforge_document_processing.layout_limits import LayoutBound
from powerforge_document_processing.layout_readings import (
    contains,
    height,
    intersect,
    same_baseline,
)
from powerforge_provenance.layout_observations import (
    LAYOUT_POLICY,
    LayoutCell,
    LayoutTable,
    UnresolvedLayout,
)
from powerforge_provenance.spatial_geometry import NormalizedRegion
from powerforge_provenance.spatial_layout import SourceSupport

D = Decimal


@dataclass(frozen=True)
class Segment:
    axis: str
    coordinate: D
    start: D
    end: D
    support: SourceSupport


def normalized(box, width, page_height):
    q = D("0.000000000001")
    left = (box[0] / width).quantize(q)
    top = (box[1] / page_height).quantize(q)
    right = (box[2] / width).quantize(q)
    bottom = (box[3] / page_height).quantize(q)
    return NormalizedRegion(x=left, y=top, width=right - left, height=bottom - top)


def native_segments(bodies, width, page_height, eps):
    result = []
    for alias, body in bodies.items():
        for primitive in body.native_primitives:
            points = [body.transform.map_point(p) for p in primitive.points]
            edges = (
                list(zip(points, points[1:] + points[:1], strict=True))
                if primitive.kind == "QUAD"
                else [(points[0], points[1])]
            )
            support = SourceSupport(
                representation_ref=alias, kind="NATIVE_PRIMITIVE", ref=primitive.ref
            )
            for a, b in edges:
                x, y, xx, yy = a.x * width, a.y * page_height, b.x * width, b.y * page_height
                if abs(y - yy) <= eps and abs(xx - x) > eps:
                    result.append(Segment("H", (y + yy) / 2, min(x, xx), max(x, xx), support))
                elif abs(x - xx) <= eps and abs(yy - y) > eps:
                    result.append(Segment("V", (x + xx) / 2, min(y, yy), max(y, yy), support))
    result = list({(s.axis, s.coordinate, s.start, s.end): s for s in reversed(result)}.values())
    result.reverse()
    if len(result) > LAYOUT_POLICY["max_segments"]:
        raise LayoutBound("Native grid segment bound exceeded", "NATIVE_SEGMENT_LIMIT")
    return result


def connected(segments, eps):
    parent = list(range(len(segments)))

    def root(i):
        while i != parent[i]:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(segments):
        for j in range(i):
            b = segments[j]
            if a.axis == b.axis:
                touch = (
                    abs(a.coordinate - b.coordinate) <= eps
                    and max(a.start, b.start) <= min(a.end, b.end) + eps
                )
            else:
                h, v = (a, b) if a.axis == "H" else (b, a)
                touch = (
                    h.start - eps <= v.coordinate <= h.end + eps
                    and v.start - eps <= h.coordinate <= v.end + eps
                )
            if touch:
                parent[root(i)] = root(j)
    groups = {}
    for i, segment in enumerate(segments):
        groups.setdefault(root(i), []).append(segment)
    return list(groups.values())


def coordinates(values, eps):
    groups = []
    for value in sorted(set(values)):
        if groups and value - groups[-1][-1] <= eps:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(g) / len(g) for g in groups]


def coverage(segments, axis, coordinate, start, end, eps):
    relevant = sorted(
        [
            s
            for s in segments
            if s.axis == axis
            and abs(s.coordinate - coordinate) <= eps
            and s.end > start + eps
            and s.start < end - eps
        ],
        key=lambda s: s.start,
    )
    if not relevant:
        return "NONE", ()
    covered = start
    used = []
    for segment in relevant:
        if segment.start > covered + eps:
            return "PARTIAL", ()
        covered = max(covered, segment.end)
        used.append(segment.support)
    return ("FULL" if covered >= end - eps else "PARTIAL"), tuple(dict.fromkeys(used))


def header_label(text):
    if not re.fullmatch(r"[A-Za-z ()/,%._-]+", text):
        return False
    if any(c.isdigit() for c in text):
        return False
    words = re.findall("[a-z]+", text.lower())
    return bool(words) and all(w in LAYOUT_POLICY["header_words"] for w in words)


def with_headers(cells, readings):
    lookup = {r.model.ref: r for r in readings}
    header_rows = 0
    headers = []
    for row in range(min(3, max(c.row + c.row_span for c in cells))):
        current = [c for c in cells if c.row <= row < c.row + c.row_span]
        if not current or any(
            c.state != "READINGS" or not header_label(" ".join(lookup[r].text for r in c.readings))
            for c in current
        ):
            break
        header_rows = row + 1
        headers.extend(c.ref for c in current if c.ref not in headers)
    for cell in cells:
        if cell.ref in headers and cell.column_span > 1:
            bands = row_bands([lookup[r] for r in cell.readings])
            if bands is None or any(len(split_row(band)) > 1 for band in bands):
                return cells, "UNRESOLVED"
    if not header_rows or header_rows == max(c.row + c.row_span for c in cells):
        return cells, "UNRESOLVED"
    result = []
    for cell in cells:
        if cell.ref in headers:
            result.append(cell.model_copy(update={"header_role": "COLUMN"}))
            continue
        path = [
            h
            for h in cells
            if h.ref in headers
            and h.row + h.row_span <= cell.row
            and h.column <= cell.column
            and cell.column + cell.column_span <= h.column + h.column_span
        ]
        # Header paths must be a nested chain, not two competing labels at one level.
        path.sort(key=lambda c: (c.row, -c.column_span))
        unique = all(
            a.row < b.row
            and a.column <= b.column
            and b.column + b.column_span <= a.column + a.column_span
            for a, b in zip(path, path[1:], strict=False)
        )
        result.append(
            cell.model_copy(update={"headers": tuple(h.ref for h in path) if unique else ()})
        )
    return tuple(result), "GEOMETRIC_LABEL_HEADER"


def grid_component(segments, readings, width, page_height, eps, ref):
    xs = coordinates(
        [v for s in segments for v in ((s.coordinate,) if s.axis == "V" else (s.start, s.end))], eps
    )
    ys = coordinates(
        [v for s in segments for v in ((s.coordinate,) if s.axis == "H" else (s.start, s.end))], eps
    )
    supports = tuple(dict.fromkeys(s.support for s in segments))
    if len(supports) > 512:
        raise LayoutBound("Table boundary support bound exceeded", "TABLE_SUPPORT_LIMIT")
    if len(xs) < 2 or len(ys) < 2:
        return None, None, None
    box = (xs[0], ys[0], xs[-1], ys[-1])
    region = normalized(box, width, page_height)

    def reject(reason):
        return None, UnresolvedLayout(region=region, reason=reason, support=supports), box

    nr, nc = len(ys) - 1, len(xs) - 1
    if (
        nr > LAYOUT_POLICY["max_rows"]
        or nc > LAYOUT_POLICY["max_columns"]
        or nr * nc > LAYOUT_POLICY["max_cells"]
    ):
        raise LayoutBound("Native grid partition bound exceeded", "GRID_PARTITION_LIMIT")
    if nr < 2 or nc < 2:
        return reject("OPEN_OR_IRREGULAR_GRID")
    for axis, coord, start, end in [
        ("H", ys[0], xs[0], xs[-1]),
        ("H", ys[-1], xs[0], xs[-1]),
        ("V", xs[0], ys[0], ys[-1]),
        ("V", xs[-1], ys[0], ys[-1]),
    ]:
        if coverage(segments, axis, coord, start, end, eps)[0] != "FULL":
            return reject("OPEN_OR_IRREGULAR_GRID")
    parent = {(r, c): (r, c) for r in range(nr) for c in range(nc)}

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k

    for r, c in parent:
        for neighbor, axis, coord, start, end in [
            ((r, c + 1), "V", xs[c + 1], ys[r], ys[r + 1]),
            ((r + 1, c), "H", ys[r + 1], xs[c], xs[c + 1]),
        ]:
            if neighbor not in parent:
                continue
            state, _ = coverage(segments, axis, coord, start, end, eps)
            if state == "PARTIAL":
                return reject("OPEN_OR_IRREGULAR_GRID")
            if state == "NONE":
                parent[root(neighbor)] = root((r, c))
    groups = {}
    for key in parent:
        groups.setdefault(root(key), []).append(key)
    slots = []
    for group in groups.values():
        top = min(r for r, c in group)
        bottom = max(r for r, c in group) + 1
        left = min(c for r, c in group)
        right = max(c for r, c in group) + 1
        if len(group) != (bottom - top) * (right - left):
            return reject("OPEN_OR_IRREGULAR_GRID")
        cell_box = (xs[left], ys[top], xs[right], ys[bottom])
        support = []
        for axis, coord, start, end in [
            ("H", ys[top], xs[left], xs[right]),
            ("H", ys[bottom], xs[left], xs[right]),
            ("V", xs[left], ys[top], ys[bottom]),
            ("V", xs[right], ys[top], ys[bottom]),
        ]:
            state, refs = coverage(segments, axis, coord, start, end, eps)
            if state != "FULL":
                return reject("OPEN_OR_IRREGULAR_GRID")
            support.extend(refs)
        slots.append(
            (top, left, bottom - top, right - left, cell_box, tuple(dict.fromkeys(support)))
        )
    assignments = {i: [] for i in range(len(slots))}
    for reading in readings:
        if "NATIVE_PREFERRED_UNALIGNED" in reading.model.issues:
            continue
        if reading.box is None or intersect(box, reading.box) == 0:
            continue
        matches = [i for i, s in enumerate(slots) if contains(s[4], reading.box, eps)]
        if len(matches) != 1 or not reading.horizontal or reading.model.issues:
            return reject("AMBIGUOUS_ASSIGNMENT")
        assignments[matches[0]].append(reading)
    cells = []
    for i, (r, c, rs, cs, cell_box, support) in enumerate(slots):
        bands = row_bands(assignments[i])
        if bands is None:
            return reject("AMBIGUOUS_ASSIGNMENT")
        owned = [
            reading
            for band in bands
            for reading in sorted(band, key=lambda q: (q.box[0], q.model.ref))
        ]
        cells.append(
            LayoutCell(
                ref=f"{ref}.r{r}c{c}",
                row=r,
                column=c,
                row_span=rs,
                column_span=cs,
                region=normalized(cell_box, width, page_height),
                readings=tuple(q.model.ref for q in owned),
                boundary_support=support,
                state="READINGS" if owned else "NO_READINGS",
            )
        )
    if any(
        not any(c.column == column and c.column_span == 1 for c in cells) for column in range(nc)
    ):
        return reject("OPEN_OR_IRREGULAR_GRID")
    cells, header_basis = with_headers(tuple(cells), readings)
    return (
        LayoutTable(
            ref=ref,
            region=region,
            method="NATIVE_RULED",
            structure_basis="MIXED_GEOMETRY_SUPPORTED"
            if any(r.kind == "OCR" for group in assignments.values() for r in group)
            else "NATIVE_GEOMETRY_SUPPORTED",
            header_basis=header_basis,
            rows=nr,
            columns=nc,
            cells=cells,
        ),
        None,
        box,
    )


# Keep the historical work budget, but apply it only to plausible components.
MAX_GRID_CANDIDATES = 64


def plausible_grid(component, eps):
    # A closed grid needs two distinct boundary coordinates on each axis.
    return all(
        len(coordinates([s.coordinate for s in component if s.axis == axis], eps)) >= 2
        for axis in ("H", "V")
    )


def component_box(component):
    return (
        min(s.start if s.axis == "H" else s.coordinate for s in component),
        min(s.start if s.axis == "V" else s.coordinate for s in component),
        max(s.end if s.axis == "H" else s.coordinate for s in component),
        max(s.end if s.axis == "V" else s.coordinate for s in component),
    )


def ruled_tables(readings, bodies, width, page_height):
    eps = max(width, page_height) * D(LAYOUT_POLICY["coordinate_epsilon_fraction"])
    try:
        segments = native_segments(bodies, width, page_height, eps)
    except LayoutBound as exc:
        return [], [UnresolvedLayout(region=None, reason=exc.reason, support=())], []
    tables = []
    unresolved = []
    excluded = []
    groups = sorted(
        connected(segments, eps),
        key=lambda group: min(s.coordinate for s in group),
    )
    groups = [group for group in groups if plausible_grid(group, eps)]
    for index, component in enumerate(groups):
        try:
            if index >= MAX_GRID_CANDIDATES:
                raise LayoutBound("Ruled grid candidate budget exhausted", "GRID_CANDIDATE_LIMIT")
            table, rejection, box = grid_component(
                component, readings, width, page_height, eps, f"t{len(tables)}"
            )
        except LayoutBound as exc:
            box = component_box(component)
            table = None
            rejection = UnresolvedLayout(
                region=normalized(box, width, page_height),
                reason=exc.reason,
                support=(),
            )
        if table:
            tables.append(table)
        if rejection:
            unresolved.append(rejection)
        if box:
            excluded.append(box)
    return tables, unresolved, excluded


def row_bands(readings):
    rows = []
    for reading in sorted(readings, key=lambda r: ((r.box[1] + r.box[3]) / 2, r.box[0])):
        matching = [row for row in rows if all(same_baseline(reading.box, r.box) for r in row)]
        if len(matching) > 1:
            return None
        if matching:
            matching[0].append(reading)
        else:
            rows.append([reading])
    return sorted(rows, key=lambda row: min(r.box[1] for r in row))


def split_row(row):
    row = sorted(row, key=lambda r: r.box[0])
    groups = []
    h = median(height(r.box) for r in row)
    for reading in row:
        if groups and reading.box[0] - max(r.box[2] for r in groups[-1]) <= h * D(
            LAYOUT_POLICY["word_gap_heights"]
        ):
            groups[-1].append(reading)
        else:
            groups.append([reading])
    return groups


def group_box(group):
    return (
        min(r.box[0] for r in group),
        min(r.box[1] for r in group),
        max(r.box[2] for r in group),
        max(r.box[3] for r in group),
    )


def borderless_tables(readings, excluded, width, page_height, start_index):
    available = [
        r
        for r in readings
        if r.box
        and r.horizontal
        and "NATIVE_PREFERRED_UNALIGNED" not in r.model.issues
        and not any(intersect(r.box, b) > 0 for b in excluded)
    ]
    rows = row_bands(available)
    if rows is None:
        return [], [UnresolvedLayout(region=None, reason="UNSUPPORTED_ALIGNMENT", support=())]
    groups = []
    current = []
    for row in rows:
        split = split_row(row)
        box = group_box(row)
        if len(split) < 2:
            if current:
                groups.append(current)
                current = []
            continue
        h = median(height(r.box) for r in row)
        if current and (
            len(split) != len(current[-1][0])
            or box[1] - current[-1][1][3] > h * D(LAYOUT_POLICY["max_row_gap_heights"])
        ):
            groups.append(current)
            current = []
        if current and all(header_label(" ".join(q.text for q in cell)) for cell in split):
            groups.append(current)
            current = []
        current.append((split, box))
    if current:
        groups.append(current)
    tables = []
    unresolved = []
    for group in groups:
        if len(group) < LAYOUT_POLICY["min_borderless_rows"]:
            continue
        ncols = len(group[0][0])
        box = (
            min(r[1][0] for r in group),
            group[0][1][1],
            max(r[1][2] for r in group),
            group[-1][1][3],
        )
        region = normalized(box, width, page_height)
        support = tuple(q.model.preferred for row, _ in group for cell in row for q in cell)
        if len(support) > 512:
            unresolved.append(
                UnresolvedLayout(region=region, reason="TABLE_SUPPORT_LIMIT", support=())
            )
            continue
        if (
            len(group) > LAYOUT_POLICY["max_rows"]
            or len(group) * ncols > LAYOUT_POLICY["max_cells"]
        ):
            unresolved.append(
                UnresolvedLayout(region=region, reason="GRID_PARTITION_LIMIT", support=())
            )
            continue

        def reject(reason, region=region, support=support):
            unresolved.append(UnresolvedLayout(region=region, reason=reason, support=support))

        if any(group[i][1][3] >= group[i + 1][1][1] for i in range(len(group) - 1)):
            reject("UNSUPPORTED_ALIGNMENT")
            continue
        if ncols > LAYOUT_POLICY["max_borderless_columns"]:
            reject("COMPETING_PARTITIONS")
            continue
        if any(q.box and not q.horizontal and intersect(q.box, box) > 0 for q in readings):
            reject("AMBIGUOUS_ASSIGNMENT")
            continue
        if any(q.model.issues for row, _ in group for cell in row for q in cell):
            reject("AMBIGUOUS_ASSIGNMENT")
            continue
        if not all(header_label(" ".join(q.text for q in cell)) for cell in group[0][0]):
            reject("UNSUPPORTED_HEADER")
            continue
        boxes = [[group_box(cell) for cell in row] for row, _ in group]
        h = median(height(q.box) for row, _ in group for cell in row for q in cell)
        tolerance = h * D(LAYOUT_POLICY["column_alignment_heights"])
        bands = [
            (min(row[c][0] for row in boxes), max(row[c][2] for row in boxes)) for c in range(ncols)
        ]
        if any(
            bands[c][1] + h * D(LAYOUT_POLICY["word_gap_heights"]) >= bands[c + 1][0]
            for c in range(ncols - 1)
        ) or any(
            not (
                min(row[c][0] for row in boxes) + tolerance >= max(row[c][0] for row in boxes)
                or min(row[c][2] for row in boxes) + tolerance >= max(row[c][2] for row in boxes)
            )
            for c in range(ncols)
        ):
            reject("UNSUPPORTED_ALIGNMENT")
            continue
        cells = []
        ref = f"t{start_index + len(tables)}"
        for r, (row, row_box) in enumerate(group):
            for c, cell in enumerate(row):
                cells.append(
                    LayoutCell(
                        ref=f"{ref}.r{r}c{c}",
                        row=r,
                        column=c,
                        region=normalized(
                            (bands[c][0], row_box[1], bands[c][1], row_box[3]), width, page_height
                        ),
                        readings=tuple(q.model.ref for q in cell),
                        state="READINGS",
                    )
                )
        cells, header_basis = with_headers(tuple(cells), readings)
        kinds = {q.kind for row, _ in group for cell in row for q in cell}
        basis = (
            "MIXED_GEOMETRY_SUPPORTED"
            if len(kinds) > 1
            else "NATIVE_GEOMETRY_SUPPORTED"
            if kinds == {"NATIVE_PDF"}
            else "OCR_GEOMETRY_SUPPORTED"
        )
        tables.append(
            LayoutTable(
                ref=ref,
                region=region,
                method="REPEATED_ALIGNMENT",
                structure_basis=basis,
                header_basis=header_basis,
                rows=len(group),
                columns=ncols,
                cells=cells,
            )
        )
    return tables, unresolved
