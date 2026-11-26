"""F1-A2 transcript and association metrics over completed source projections."""

from collections import Counter, defaultdict
from dataclasses import replace
from itertools import pairwise

from source_metrics import normalized, reading_order, score

from extraction_worker.spatial_evaluation_scoring import envelope

LOCATED = {"EXACT", "DISPLAY_VARIANT"}
UNCERTAIN = {
    "AMBIGUOUS_OVERLAP",
    "TRANSCRIPTION_CONFLICT",
    "NATIVE_PREFERRED_UNALIGNED",
    "NATIVE_REPLACEMENT",
    "UNSUPPORTED_DIRECTION",
    "MISSING_GEOMETRY",
}
BARRIER = "\uffff"


def coherent_views(words, details):
    """One whole representation at a time. Never choose the best token independently."""
    views = defaultdict(list)
    for word in words:
        preferred, alternatives, _ = details.get(word.ref, (word.stream, (), ()))
        alternatives_by_rep = defaultdict(set)
        for representation, text in ((preferred, word.text), *alternatives):
            alternatives_by_rep[representation].add(text)
        for representation, texts in alternatives_by_rep.items():
            # Even within one representation, two readings with the same witness
            # slot cannot establish an unambiguous sequence.
            text = next(iter(texts)) if len(texts) == 1 else BARRIER
            views[representation].append(replace(word, text=text, stream=representation))
    return [reading_order([word for word in view if word.box]) for view in views.values()]


def unambiguous_words(words, details):
    result = []
    for word in words:
        _, alternatives, issues = details.get(word.ref, (word.stream, (), ()))
        distinct = any(
            normalized(text, True) != normalized(word.text, True) for _, text in alternatives
        )
        # A barrier prevents the adjacent words from joining across a disputed token.
        result.append(
            replace(word, text=BARRIER) if distinct or UNCERTAIN.intersection(issues) else word
        )
    return result


def association_targets(gold):
    """Gold provides endpoints, expected links, and candidate roles only."""
    expected = {key: defaultdict(set) for key in ("row", "column", "header", "label_value")}
    headers, labels, candidates = set(), set(), set()
    for table in gold.tables:
        cells = [c for c in table.cells if c.text is not None and c.legibility == "LEGIBLE"]

        def key(cell, table_id=table.id):
            return f"{table_id}/{cell.row}/{cell.column}"

        candidates.update(key(cell) for cell in cells)
        columns = defaultdict(list)
        rows = defaultdict(list)
        for cell in cells:
            if cell.row in table.header_rows:
                headers.add(key(cell))
            if cell.column == "label":
                labels.add(key(cell))
            if cell.column_span is None and cell.row_end is None:
                rows[cell.row].append(cell)
                columns[cell.column].append(cell)
            for other in cells:
                if (
                    cell.row not in table.header_rows
                    and other.row in table.header_rows
                    and other.row < cell.row
                    and set(cell.column_span or [cell.column])
                    <= set(other.column_span or [other.column])
                ):
                    expected["header"][key(cell)].add(key(other))
                if cell.column != "label" and other.column == "label" and cell.row == other.row:
                    expected["label_value"][key(cell)].add(key(other))
        for group, axis, ordering in (
            (rows, "row", lambda c, columns=table.columns: columns.index(c.column)),
            (columns, "column", lambda c: c.row),
        ):
            for members in group.values():
                for first, second in pairwise(sorted(members, key=ordering)):
                    expected[axis][key(first)].add(key(second))
    return expected, {
        "row": candidates,
        "column": candidates,
        "header": headers,
        "label_value": labels,
    }


def center(box, axis):
    return (box[axis] + box[axis + 2]) / 2


def proximity(source, target, mode):
    horizontal = mode in ("row", "label_value")
    axis = 0 if horizontal else 1
    cross = 1 - axis
    forward = mode in ("row", "column")
    span = (target[axis] - source[axis + 2]) if forward else (source[axis] - target[axis + 2])
    movement = (center(target, axis) - center(source, axis)) * (1 if forward else -1)
    extent = min(source[cross + 2] - source[cross], target[cross + 2] - target[cross])
    overlap = min(source[cross + 2], target[cross + 2]) - max(source[cross], target[cross])
    delta = abs(center(target, cross) - center(source, cross))
    # Keep candidates on the same line or column. Use left alignment for
    # vertical text where labels and values have different widths.
    aligned = overlap >= extent * 0.25 or (not horizontal and abs(source[0] - target[0]) <= 0.009)
    if not aligned or movement <= 0.002 or span < -0.004:
        return None
    # Section headers can be farther above a value. No direction can link
    # across most of the page on the strength of a shared axis alone.
    limit = {"row": 0.36, "column": 0.16, "header": 0.48, "label_value": 0.72}[mode]
    if movement > limit:
        return None
    return max(span, 0) + (2 if horizontal else 0.5) * delta


def geometric_associations(gold, detail, words):
    """Score nearest geometric links among localized, gold-identified endpoints."""
    expected, pools = association_targets(gold)
    boxes = {word.ref: word.box for word in words}
    located = {
        key: envelope([boxes[ref] for ref in row["references"]])
        for key, row in detail.items()
        if row["references"]
    }
    counts, missed = {}, {}
    for mode, links in expected.items():
        tally = Counter()
        examples = []
        for key, targets in links.items():
            selected = None
            if key not in located:
                outcome = "missing_source"
            else:
                candidates = [
                    (cost, name)
                    for name in sorted(pools[mode] & located.keys() - {key})
                    if (cost := proximity(located[key], located[name], mode)) is not None
                ]
                candidates.sort()
                if not candidates:
                    outcome = "no_candidate" if targets & located.keys() else "missing_target"
                elif len(candidates) > 1 and candidates[1][0] - candidates[0][0] <= max(
                    0.003, candidates[0][0] * 0.12
                ):
                    outcome = "ambiguous"
                    selected = [name for _, name in candidates[:2]]
                else:
                    selected = candidates[0][1]
                    outcome = "correct" if selected in targets else "incorrect"
            tally[outcome] += 1
            if outcome in ("ambiguous", "incorrect") and len(examples) < 8:
                examples.append(
                    dict(source=key, expected=sorted(targets), selected=selected, outcome=outcome)
                )
        counts[mode] = dict(tally)
        if examples:
            missed[mode] = examples
    return {"geometric_associations": counts, "geometric_examples": missed}


def refined_score(gold, words, layout=None, details=None, *, associations=True):
    details = details or {}

    def hook(detail):
        return geometric_associations(gold, detail, words)

    preferred = score(gold, words, layout, detail_hook=hook if associations else None)
    has_alternates = any(alternates for _, alternates, _ in details.values())
    available = (
        score(gold, words, extra_views=coherent_views(words, details))
        if has_alternates
        else preferred
    )
    if details:
        unambiguous = score(gold, unambiguous_words(words, details))
    else:
        unambiguous = preferred

    def summary(result):
        return {key: result[key] for key in ("status", "totals", "geometry")}

    return {
        "preferred": summary(preferred),
        "available": summary(available),
        "unambiguous": summary(unambiguous),
        "explicit_structure": preferred["structure"],
        "geometric_associations": preferred.get("geometric_associations", {}),
        "geometric_examples": preferred.get("geometric_examples", {}),
        "alt_only": [
            key
            for key, item in available["annotations"].items()
            if item["status"] in LOCATED and preferred["annotations"][key]["status"] not in LOCATED
        ],
        "annotations": {
            key: dict(
                preferred=item["status"],
                available=available["annotations"][key]["status"],
                unambiguous=unambiguous["annotations"][key]["status"],
                preferred_numeric=item["located_numeric_literals"],
                available_numeric=available["annotations"][key]["located_numeric_literals"],
            )
            for key, item in preferred["annotations"].items()
        },
    }


def construction_changes(prepared, readings):
    changes = defaultdict(list)
    for key, item in prepared["annotations"].items():
        if item["available"] not in LOCATED:
            continue
        downstream = readings["annotations"][key]
        if downstream["preferred"] in LOCATED:
            continue
        if downstream["available"] in LOCATED:
            reason = "retained_as_alternate"
        elif downstream["available"] == "UNLOCALIZED_TEXT_MATCH":
            reason = "available_without_local_match"
        else:
            reason = "local_transcript_lost"
        changes[reason].append(key)
    return dict(changes)
