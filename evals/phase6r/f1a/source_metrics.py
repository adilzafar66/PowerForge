"""Score frozen source annotations against finished, gold-blind projections."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import pairwise

from extraction_worker.spatial_evaluation_scoring import bounds, distance, envelope, iou

GLYPHS = str.maketrans(
    {"–": "-", "−": "-", "‑": "-", "”": '"', "″": '"', "’": "'", "′": "'", "µ": "μ"}
)
NUMERAL = re.compile(r"(?<![\d.])(?:\d+\.\d+|\.\d+|\d+)(?![\d.])")


@dataclass(frozen=True)
class Word:
    ref: str
    text: str
    box: tuple | None
    stream: str


def normalized(text, relaxed=False):
    if relaxed:
        return "".join(text.translate(GLYPHS).split())
    return " ".join(text.split())


def normalized_box(box, frame):
    x0, y0, x1, y1 = box
    w, h = frame
    return x0 / w, y0 / h, x1 / w, y1 / h


def contains_center(outer, box):
    if box is None:
        return False
    x0, y0, x1, y1 = outer
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return x0 <= x < x1 and y0 <= y < y1


def reading_order(words):
    # Group by baseline using a fixed representative, not transitive chaining.
    rows = []
    for word in sorted(words, key=lambda w: ((w.box[1] + w.box[3]) / 2, w.box[0])):
        if rows:
            box = rows[-1][0].box
            common = min(box[3], word.box[3]) - max(box[1], word.box[1])
            if common >= 0.5 * min(box[3] - box[1], word.box[3] - word.box[1]):
                rows[-1].append(word)
                continue
        rows.append([word])
    return [word for row in rows for word in sorted(row, key=lambda w: w.box[0])]


def find_words(views, target, relaxed):
    expected = normalized(target, relaxed)
    separator = "" if relaxed else " "
    for view in views:
        strings = [normalized(word.text, relaxed) for word in view]
        for start, initial in enumerate(strings):
            if not initial or not expected.startswith(initial):
                continue
            candidate = initial
            for end in range(start, len(view)):
                if end > start:
                    candidate += separator + strings[end]
                if candidate == expected:
                    return view[start : end + 1]
                if not expected.startswith(candidate):
                    break
    return None


def local_score(words, annotation, gold_frame, page_views, extra_views=()):
    box = normalized_box(annotation.box, gold_frame)
    near = [w for w in words if contains_center(box, w.box)]
    streams = defaultdict(list)
    for word in near:
        streams[word.stream].append(word)
    # Try the combined view and each engine independently, so overlapping
    # duplicate readings do not hide a complete transcription in one engine.
    views = [reading_order(near), *(reading_order(items) for items in streams.values())]
    views.extend([w for w in view if contains_center(box, w.box)] for view in extra_views)
    target = annotation.text
    exact = find_words(views, target, False)
    match = exact or find_words(views, target, True)
    source = normalized(target)
    if match:
        status = "EXACT" if exact else "DISPLAY_VARIANT"
        transcript = normalized(" ".join(w.text for w in match))
        match_box = envelope([w.box for w in match])
        area = (match_box[2] - match_box[0]) * (match_box[3] - match_box[1])
        intersection = max(0, min(box[2], match_box[2]) - max(box[0], match_box[0])) * max(
            0, min(box[3], match_box[3]) - max(box[1], match_box[1])
        )
        geometry = dict(
            containment=round(intersection / area, 4), iou=round(iou(box, match_box), 4)
        )
    else:
        status = (
            "UNLOCALIZED_TEXT_MATCH"
            if find_words(page_views, target, True)
            else "LOCAL_TRANSCRIPTION_DIFFERS"
            if near
            else "NO_READING_AT_LOCATION"
        )
        candidates = [normalized(" ".join(w.text for w in view)) for view in views]
        transcript = min(candidates, key=lambda value: distance(source, value))
        geometry = None
    expected_literals = Counter(NUMERAL.findall(source))
    # Require location and preserve precision, leading zeros and decimal notation.
    literal_count = max(
        (
            sum(
                (
                    expected_literals & Counter(NUMERAL.findall(" ".join(w.text for w in view)))
                ).values()
            )
            for view in views
        ),
        default=0,
    )
    return dict(
        status=status,
        references=[w.ref for w in match or ()],
        geometry=geometry,
        text_characters=len(source),
        edit_distance=distance(source, transcript),
        numeric_literals=len(list(NUMERAL.finditer(source))),
        located_numeric_literals=literal_count,
    )


def structure_metrics(gold, scores, layout):
    counts = Counter()
    predicted = {}
    if layout is not None:
        for table in layout.tables:
            for cell in table.cells:
                for ref in cell.readings:
                    predicted[ref] = (table.ref, cell.ref, cell.row, cell.column, cell.headers)

    def structural_match(key):
        refs = scores.get(key, {}).get("references", ())
        if refs:
            matches = {predicted.get(ref) for ref in refs}
            if len(matches) == 1:
                return matches.pop()
        return None

    for table in gold.tables:
        groups = {"row": defaultdict(list), "column": defaultdict(list)}
        cells = {}
        for cell in table.cells:
            if cell.text is None or cell.legibility != "LEGIBLE":
                continue
            key = f"{table.id}/{cell.row}/{cell.column}"
            matches = structural_match(key)
            cells[(cell.row, cell.column)] = matches
            counts["cells"] += 1
            if matches:
                counts["cells_in_one_predicted_cell"] += 1
            if cell.column_span is None and cell.row_end is None:
                groups["row"][cell.row].append((table.columns.index(cell.column), matches))
                groups["column"][cell.column].append((cell.row, matches))
        for axis, members in groups.items():
            index = 2 if axis == "row" else 3
            for group in members.values():
                for (_, first), (_, second) in pairwise(sorted(group)):
                    counts[f"{axis}_pairs"] += 1
                    if first and second and first[0] == second[0] and first[1] != second[1]:
                        if first[index] == second[index] and first[5 - index] < second[5 - index]:
                            counts[f"{axis}_pairs_matched"] += 1
        for (row, column), actual in cells.items():
            if column == "label" or (row, "label") not in cells:
                continue
            label = cells[(row, "label")]
            counts["label_value_pairs"] += 1
            if (
                label
                and actual
                and label[0] == actual[0]
                and label[1] != actual[1]
                and label[2] == actual[2]
                and label[3] < actual[3]
            ):
                counts["label_value_pairs_matched"] += 1
        for cell in table.cells:
            if cell.text is None or cell.legibility != "LEGIBLE" or cell.row in table.header_rows:
                continue
            span = set(cell.column_span or [cell.column])
            for header in table.cells:
                if (
                    header.row not in table.header_rows
                    or header.row >= cell.row
                    or header.text is None
                    or header.legibility != "LEGIBLE"
                    or not span <= set(header.column_span or [header.column])
                ):
                    continue
                counts["header_links"] += 1
                actual, head = cells[(cell.row, cell.column)], cells[(header.row, header.column)]
                if actual and head and actual[0] == head[0] and head[1] in actual[4]:
                    counts["header_links_matched"] += 1
    return dict(counts)


def score(gold, words, layout=None, *, extra_views=(), detail_hook=None):
    streams = defaultdict(list)
    for word in words:
        streams[word.stream].append(word)
    global_views = [
        *streams.values(),
        *(reading_order([w for w in items if w.box]) for items in streams.values()),
    ]
    global_views.extend(extra_views)
    detail = {
        key: local_score(words, annotation, gold.frame, global_views, extra_views)
        for key, annotation in gold.annotations()
        if annotation.legibility == "LEGIBLE" and annotation.text is not None
    }
    result = {
        "status": dict(Counter(item["status"] for item in detail.values())),
        "totals": {
            metric: sum(d[metric] for d in detail.values())
            for metric in (
                "text_characters",
                "edit_distance",
                "numeric_literals",
                "located_numeric_literals",
            )
        },
        "geometry": {
            "matches": sum(d["geometry"] is not None for d in detail.values()),
            "containment_sum": round(
                sum(d["geometry"]["containment"] for d in detail.values() if d["geometry"]), 4
            ),
            "iou_sum": round(
                sum(d["geometry"]["iou"] for d in detail.values() if d["geometry"]), 4
            ),
        },
        "structure": structure_metrics(gold, detail, layout),
        "annotations": {
            key: {k: v for k, v in value.items() if k != "references"}
            for key, value in detail.items()
        },
    }
    if detail_hook is not None:
        result.update(detail_hook(detail))
    return result


def normalized_region(region):
    return tuple(map(float, bounds(region))) if region else None
