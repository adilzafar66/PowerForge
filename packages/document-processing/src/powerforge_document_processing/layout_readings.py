"""Unique occurrence alignment using exact readings, local context and same-page geometry."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from powerforge_document_processing.layout_limits import LayoutBound
from powerforge_provenance.layout_observations import LAYOUT_POLICY, LayoutReading, ReadingOverlap
from powerforge_provenance.spatial_layout import SourceSupport
from powerforge_provenance.spatial_sources import load_positioned_text

D = Decimal


@dataclass(frozen=True)
class Reading:
    model: LayoutReading
    text: str
    box: tuple | None
    kind: str
    horizontal: bool
    engine_line: tuple
    engine_order: int
    confidence: object = None


def area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def intersect(a, b):
    return max(D(0), min(a[2], b[2]) - max(a[0], b[0])) * max(
        D(0), min(a[3], b[3]) - max(a[1], b[1])
    )


def contains(outer, inner, margin=0):
    return (
        outer[0] + margin <= inner[0]
        and outer[1] + margin <= inner[1]
        and inner[2] <= outer[2] - margin
        and inner[3] <= outer[3] - margin
    )


def height(box):
    return box[3] - box[1]


def same_baseline(a, b):
    return max(D(0), min(a[3], b[3]) - max(a[1], b[1])) / min(height(a), height(b)) >= D(
        LAYOUT_POLICY["baseline_overlap"]
    )


def horizontal_direction(body, line):
    if body.producer.kind == "OCR":
        return True  # Axis-aligned engine boxes, not independently verified glyph orientation.
    if line is None or line.direction is None:
        return False
    x, y = line.direction
    rotation = body.transform.rotation_degrees
    if rotation == 90:
        x, y = -y, x
    elif rotation == 180:
        x, y = -x, -y
    elif rotation == 270:
        x, y = y, -x
    return (
        x >= D(".99")
        and abs(y) <= D(".01")
        and not body.transform.mirror_x
        and not body.transform.mirror_y
    )


def selected_readings(prepared, geometry, text):
    prepared = type(prepared).model_validate(prepared)
    if set(geometry) != {r.ref for r in prepared.representations} or set(text) != set(geometry):
        raise ValueError("Layout requires the exact selected representation set")
    if sum(r.token_count for r in prepared.representations) > LAYOUT_POLICY["max_readings"]:
        raise LayoutBound("Layout reading bound exceeded; no truncation", "LAYOUT_READING_LIMIT")
    raw = []
    bodies = {}
    for descriptor in sorted(prepared.representations, key=lambda r: r.ref):
        body, _ = load_positioned_text(
            prepared, descriptor.ref, geometry[descriptor.ref], text[descriptor.ref]
        )
        bodies[descriptor.ref] = body
        lines = {ref: line for line in body.lines for ref in line.token_refs}
        for token in body.tokens:
            support = SourceSupport(representation_ref=descriptor.ref, kind="TOKEN", ref=token.ref)
            region = body.transform.map_rectangle(token.source_box) if token.source_box else None
            box = (
                (
                    region.x * prepared.page_frame.width,
                    region.y * prepared.page_frame.height,
                    region.right * prepared.page_frame.width,
                    region.bottom * prepared.page_frame.height,
                )
                if region
                else None
            )
            line = lines.get(token.ref)
            horizontal = horizontal_direction(body, line)
            if token.source_quad is not None:
                points = [body.transform.map_point(p) for p in token.source_quad]
                eps = D(LAYOUT_POLICY["coordinate_epsilon_fraction"])
                horizontal = (
                    horizontal
                    and abs(points[0].y - points[1].y) <= eps
                    and abs(points[2].y - points[3].y) <= eps
                    and abs(points[0].x - points[3].x) <= eps
                    and abs(points[1].x - points[2].x) <= eps
                )
            issues = []
            if region is None:
                issues.append("MISSING_GEOMETRY")
            if not horizontal:
                issues.append("UNSUPPORTED_DIRECTION")
            if "\ufffd" in token.raw_text and body.producer.kind == "NATIVE_PDF":
                issues.append("NATIVE_REPLACEMENT")
            model = LayoutReading(
                ref=f"q{len(raw)}",
                members=(support,),
                preferred=support,
                region=region,
                issues=tuple(issues),
            )
            raw.append(
                Reading(
                    model,
                    token.raw_text,
                    box,
                    body.producer.kind,
                    horizontal,
                    (descriptor.ref, line.ref if line else None),
                    token.engine_order,
                    token.confidence,
                )
            )
    return raw, bodies


def align_readings(raw, width, height_value):
    buckets = defaultdict(list)
    candidates = set()
    pairs = []
    same_kind_pairs = []

    def keys(box):
        x0 = max(0, int(box[0] / width * 32))
        x1 = min(31, int(box[2] / width * 32))
        y0 = max(0, int(box[1] / height_value * 32))
        y1 = min(31, int(box[3] / height_value * 32))
        return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]

    for i, reading in enumerate(raw):
        if reading.box is None:
            continue
        nearby = {j for key in keys(reading.box) for j in buckets[key]}
        for j in sorted(nearby):
            other = raw[j]
            overlap = intersect(reading.box, other.box)
            if overlap == 0:
                continue
            candidates.add((j, i))
            if len(candidates) > LAYOUT_POLICY["max_overlap_pairs"]:
                raise LayoutBound("Overlap comparison bound exceeded", "LAYOUT_OVERLAP_LIMIT")
            if other.kind == reading.kind:
                if overlap / min(area(reading.box), area(other.box)) >= D(
                    LAYOUT_POLICY["overlap_iou"]
                ):
                    same_kind_pairs.append((j, i))
                continue
            union = area(reading.box) + area(other.box) - overlap
            if (
                overlap / union >= D(LAYOUT_POLICY["overlap_iou"])
                or overlap / min(area(reading.box), area(other.box)) >= D(".8")
            ) and same_baseline(reading.box, other.box):
                pairs.append((j, i))
        for key in keys(reading.box):
            buckets[key].append(i)
    links = defaultdict(set)
    for a, b in pairs:
        links[a].add(b)
        links[b].add(a)
    unique = {(a, b) for a, b in pairs if len(links[a]) == len(links[b]) == 1}

    def context(a, b):
        for c, d in unique:
            if (c, d) == (a, b) or raw[c].kind != raw[a].kind or raw[c].text != raw[d].text:
                continue
            aa, bb, cc, dd = [raw[k].box for k in (a, b, c, d)]
            if not (same_baseline(aa, cc) and same_baseline(bb, dd)):
                continue
            if (aa[0] < cc[0]) != (bb[0] < dd[0]):
                continue
            gap = max(cc[0] - aa[2], aa[0] - cc[2], dd[0] - bb[2], bb[0] - dd[2], D(0))
            if gap <= 3 * max(height(aa), height(bb), height(cc), height(dd)):
                return True
        return False

    agreements = {}
    issues = defaultdict(set)
    for a, b in same_kind_pairs:
        issues[a].add("AMBIGUOUS_OVERLAP")
        issues[b].add("AMBIGUOUS_OVERLAP")
    for a, b in pairs:
        supported = (a, b) in unique and raw[a].horizontal and raw[b].horizontal and context(a, b)
        kind = (
            "AGREEMENT"
            if supported and raw[a].text == raw[b].text
            else "CONFLICT"
            if supported
            else "AMBIGUOUS"
        )
        if kind == "AGREEMENT":
            agreements[a] = b
        else:
            prefer_native = kind == "AMBIGUOUS" and (a, b) in unique and raw[a].text == raw[b].text
            for i in (a, b):
                if prefer_native and raw[i].kind == "NATIVE_PDF":
                    continue
                issues[i].add(
                    "TRANSCRIPTION_CONFLICT" if kind == "CONFLICT" else "AMBIGUOUS_OVERLAP"
                )
                if prefer_native and raw[i].kind == "OCR":
                    issues[i].add("NATIVE_PREFERRED_UNALIGNED")
    overlaps = [
        ReadingOverlap(
            left=raw[a].model.preferred,
            right=raw[b].model.preferred,
            kind="AGREEMENT"
            if agreements.get(a) == b
            else "CONFLICT"
            if "TRANSCRIPTION_CONFLICT" in issues[a] and (a, b) in unique and context(a, b)
            else "AMBIGUOUS",
        )
        for a, b in pairs
    ]
    overlaps.extend(
        ReadingOverlap(left=raw[a].model.preferred, right=raw[b].model.preferred, kind="AMBIGUOUS")
        for a, b in same_kind_pairs
    )
    skipped = set(agreements.values())
    result = []
    for index, reading in enumerate(raw):
        if index in skipped:
            continue
        members = (reading.model.preferred,)
        preferred = reading
        combined_issues = set(reading.model.issues) | issues[index]
        if index in agreements:
            other_index = agreements[index]
            other = raw[other_index]
            members += other.model.members
            preferred = reading if reading.kind == "NATIVE_PDF" else other
            combined_issues.update(other.model.issues)
            combined_issues.update(issues[other_index])
        model = preferred.model.model_copy(
            update={
                "ref": f"q{len(result)}",
                "members": members,
                "issues": tuple(sorted(combined_issues)),
            }
        )
        result.append(
            Reading(
                model,
                preferred.text,
                preferred.box,
                preferred.kind,
                preferred.horizontal,
                preferred.engine_line,
                preferred.engine_order,
                preferred.confidence,
            )
        )
    return result, overlaps
