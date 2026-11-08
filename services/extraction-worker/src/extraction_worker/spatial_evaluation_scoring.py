"""Source-first metrics. Predicted text, keys, and types never select geometry matches."""

from collections import Counter, defaultdict
from decimal import Decimal

IOU_THRESHOLDS = (0.25, 0.5, 0.75)
TABLE_IOU = 0.25
WORD_IOU = 0.5


class Counts(dict):
    def record(self, name, numerator, denominator):
        self[name] = {
            "numerator": int(numerator),
            "denominator": int(denominator),
            "rate": numerator / denominator if denominator else None,
        }

    def pair(self, name, correct, gold, predicted):
        self.record(f"{name}_recall", correct, gold)
        self.record(f"{name}_precision", correct, predicted)


def aggregate(records):
    totals = defaultdict(lambda: [0, 0])
    for record in records:
        for name, metric in record.items():
            totals[name][0] += metric["numerator"]
            totals[name][1] += metric["denominator"]
    result = Counts()
    for name, (n, d) in sorted(totals.items()):
        result.record(name, n, d)
    return result


def distance(expected, predicted):
    """Levenshtein distance with one row of memory."""
    row = list(range(len(predicted) + 1))
    for i, reference in enumerate(expected, 1):
        current = [i]
        for j, guess in enumerate(predicted, 1):
            current.append(min(row[j] + 1, current[-1] + 1, row[j - 1] + (guess != reference)))
        row = current
    return row[-1]


def bounds(region):
    return (
        float(region.x),
        float(region.y),
        float(region.x + region.width),
        float(region.y + region.height),
    )


def envelope(boxes):
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def iou(a, b):
    if not a or not b:
        return 0.0
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return overlap / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap)


def match(gold, predictions, threshold):
    """Deterministic one-to-one matching by IoU; repeated strings do not affect it."""
    edges = sorted(
        (
            (-score, gi, pi)
            for gi, g in enumerate(gold)
            for pi, p in enumerate(predictions)
            if (score := iou(g, p)) >= threshold
        )
    )
    pairs, used = {}, set()
    for _, gi, pi in edges:
        if gi not in used and pi not in pairs:
            pairs[pi] = gi
            used.add(gi)
    return pairs


def geometry(metrics, name, gold, predicted, threshold):
    primary = match(gold, predicted, threshold)
    metrics.pair(name, len(primary), len(gold), len(predicted))
    for cutoff in IOU_THRESHOLDS:
        matched = primary if cutoff == threshold else match(gold, predicted, cutoff)
        metrics.pair(f"{name}_iou_{cutoff}", len(matched), len(gold), len(predicted))
    metrics.record(f"{name}_unmatched", len(predicted) - len(primary), len(predicted))
    duplicates = sum(
        any(iou(g, box) >= threshold for g in gold)
        for i, box in enumerate(predicted)
        if i not in primary
    )
    metrics.record(f"{name}_duplicate", duplicates, len(predicted))
    return primary


def raw_readings(case, bodies):
    metrics = Counts()
    by_word = {w.id: w for w in case.words}
    supports = {}
    for alias in ("native", "ocr"):
        expected = (
            [w for w in case.words if w.printed]
            if alias == "ocr" and case.ocr_gold
            else [w for w in case.words if w.basis == "NATIVE_PDF"]
            if alias == "native"
            else []
        )
        expected_ids = {w.id for w in expected}
        body = bodies.get(alias)
        tokens = list(body.tokens) if body else []
        token_boxes = {
            t.ref: bounds(body.transform.map_rectangle(t.source_box)) if t.source_box else None
            for t in tokens
        }
        selected = geometry(
            metrics,
            f"{alias}_word",
            [w.box for w in expected],
            [token_boxes[t.ref] for t in tokens],
            WORD_IOU,
        )
        for pi, gi in selected.items():
            supports[(alias, tokens[pi].ref)] = expected[gi].id
        exact = {
            expected[g].id for p, g in selected.items() if tokens[p].raw_text == expected[g].text
        }
        metrics.record(f"{alias}_exact_word", len(exact), len(expected))
        for category in ("tag", "value", "unit", "punctuation"):
            labels = {w.id for w in expected if category in w.categories}
            metrics.record(f"{alias}_exact_{category}", len(labels & exact), len(labels))
        line_boxes = [
            envelope([by_word[w].box for w in line.words if w in expected_ids])
            for line in case.lines
            if expected_ids.intersection(line.words)
        ]
        predicted_lines = [
            envelope(boxes) if boxes else None
            for line in (body.lines if body else [])
            for boxes in [[token_boxes[r] for r in line.token_refs if token_boxes[r]]]
        ]
        geometry(metrics, f"{alias}_line", line_boxes, predicted_lines, WORD_IOU)
        if alias == "ocr" and case.ocr_gold:
            printed = [w.text for w in expected]
            output = [t.raw_text for t in sorted(tokens, key=lambda t: t.engine_order)]
            expected_chars, output_chars = " ".join(printed), " ".join(output)
            metrics.record("ocr_cer", distance(expected_chars, output_chars), len(expected_chars))
            metrics.record("ocr_wer", distance(printed, output), len(printed))
            metrics.record("ocr_eligible_pages_recognized", bool(tokens), 1)
        metrics.record(f"{alias}_representation_present", bool(body and expected), bool(expected))
    return metrics, supports


def token_key(support):
    return support.representation_ref, support.ref


def score_layout(case, layout, supports):
    metrics = Counts()
    gold_words = {w.id: w for w in case.words}
    readings = layout.readings if layout else ()
    selected = {r.ref: supports.get(token_key(r.preferred)) for r in readings}
    preferred = Counter(
        (selected[r.ref], r.preferred.representation_ref)
        for r in readings
        if "NATIVE_PREFERRED_UNALIGNED" not in r.issues
    )
    # Printed occurrences have a preferred representation. Hidden disagreements are scored
    # in overlap metrics, and never count as an independently verified printed reading.
    expected = {
        (w.id, "native" if w.basis == "NATIVE_PDF" else "ocr") for w in case.words if w.printed
    }
    metrics.pair(
        "preferred_source", len(expected & preferred.keys()), len(expected), sum(preferred.values())
    )

    gold_overlap = {
        (w.id, w.id, "AGREEMENT")
        for w in case.words
        if w.basis == "NATIVE_PDF" and w.printed and case.ocr_gold
    } | {(a, b, "CONFLICT") for a, b in case.conflicts}
    edges = Counter(
        (supports.get(token_key(edge.left)), supports.get(token_key(edge.right)), edge.kind)
        for edge in (layout.overlaps if layout else ())
    )
    metrics.pair(
        "native_ocr_overlap",
        len(gold_overlap & edges.keys()),
        len(gold_overlap),
        sum(edges.values()),
    )
    for kind in ("AGREEMENT", "CONFLICT"):
        wanted = {edge for edge in gold_overlap if edge[2] == kind}
        metrics.pair(
            f"overlap_{kind.lower()}",
            len(wanted & edges.keys()),
            len(wanted),
            sum(count for edge, count in edges.items() if edge[2] == kind),
        )

    expected_order = {
        (a, b)
        for line in case.lines
        if line.order
        for a, b in zip(line.words, line.words[1:], strict=False)
        if gold_words[a].printed and gold_words[b].printed
    }
    expected_order |= {
        (a.words[-1], b.words[0])
        for table in case.tables
        for cell in table.cells
        if cell.line
        for neighbor in table.cells
        if neighbor.line
        and (
            neighbor.position == (cell.position[0], cell.position[1] + cell.span[1])
            or neighbor.position == (cell.position[0] + cell.span[0], cell.position[1])
        )
        for a in case.lines
        if a.id == cell.line
        for b in case.lines
        if b.id == neighbor.line
    }
    order = Counter(
        (selected[edge.before], selected[edge.after]) for edge in (layout.order if layout else ())
    )
    metrics.pair(
        "reading_order_edge",
        len(expected_order & order.keys()),
        len(expected_order),
        sum(order.values()),
    )
    return metrics, score_tables(metrics, case, layout, selected)


def score_tables(metrics, case, layout, readings):
    predicted = layout.tables if layout else ()
    matched = geometry(
        metrics,
        "table_region",
        [t.box for t in case.tables],
        [bounds(t.region) for t in predicted],
        TABLE_IOU,
    )
    unresolved = layout.unresolved if layout else ()
    wanted_cells = sum(len(t.cells) for t in case.tables)
    actual_cells = sum(len(t.cells) for t in predicted)
    wanted_headers = sum(len(c.headers) for t in case.tables for c in t.cells)
    actual_headers = sum(len(c.headers) for t in predicted for c in t.cells)
    line_words = {line.id: set(line.words) for line in case.lines}
    word_basis = {word.id: word.basis for word in case.words}
    cells_correct = spans_correct = headers_correct = partitions = 0
    row_counts = column_counts = 0
    table_details = []
    for gi, gold in enumerate(case.tables):
        pi = next((pi for pi, index in matched.items() if index == gi), None)
        table = predicted[pi] if pi is not None else None
        wanted = {c.position: c for c in gold.cells}
        actual = {(c.row, c.column): c for c in table.cells} if table else {}
        good = {
            slot
            for slot, cell in actual.items()
            if slot in wanted
            and {readings[r] for r in cell.readings} == line_words.get(wanted[slot].line, set())
        }
        spans = {
            slot
            for slot in good
            if (actual[slot].row_span, actual[slot].column_span) == wanted[slot].span
        }
        position = {c.ref: key for key, c in actual.items()}
        correct_edges = sum(
            (header_slot := position[ref]) in spans and header_slot in wanted[slot].headers
            for slot in spans
            for ref in actual[slot].headers
        )
        cells_correct += len(good)
        spans_correct += len(spans)
        headers_correct += correct_edges
        complete = bool(
            table
            and (table.rows, table.columns) == (gold.rows, gold.columns)
            and len(spans) == len(gold.cells) == len(table.cells)
        )
        partitions += complete
        row_counts += bool(table and table.rows == gold.rows)
        column_counts += bool(table and table.columns == gold.columns)
        retained = not complete and any(
            u.region and iou(gold.box, bounds(u.region)) >= TABLE_IOU for u in unresolved
        )
        bases = {word_basis[w] for cell in gold.cells for w in line_words.get(cell.line, ())}
        table_details.append(
            {
                "factors": gold.factors or ["regular_borderless"],
                "gold_reading_basis": next(iter(bases)) if len(bases) == 1 else "MIXED",
                "geometry_matched": table is not None,
                "partition_correct": complete,
                "false_partition": table is not None and not complete,
                "unresolved_retained": retained,
                "structure_basis": table.structure_basis if table else None,
            }
        )
    metrics.pair("cell_occurrence", cells_correct, wanted_cells, actual_cells)
    metrics.record("cell_span", spans_correct, wanted_cells)
    metrics.pair("header_edge", headers_correct, wanted_headers, actual_headers)
    metrics.pair("supported_partition", partitions, len(case.tables), len(predicted))
    metrics.record("table_row_count", row_counts, len(case.tables))
    metrics.record("table_column_count", column_counts, len(case.tables))
    metrics.record("false_supported_partition", len(predicted) - partitions, len(predicted))
    metrics.record(
        "unresolved_layout_retention",
        sum(t["unresolved_retained"] for t in table_details),
        len(case.tables) - partitions,
    )
    return table_details


def check_evidence(e, sources):
    loc = e.location
    if (
        loc.prepared_result_id != sources.prepared.id
        or loc.spatial_result_id != sources.layout.id
        or loc.document_page_id != sources.prepared.owner.document_page_id
        or loc.printed_text_independently_verified
    ):
        return False
    if len(loc.support) != 1 or e.text_start is None:
        return False  # Page-level claims cannot earn positioned-source credit.
    alias, ref = token_key(loc.support[0])
    descriptor = next((r for r in sources.prepared.representations if r.ref == alias), None)
    if descriptor is None:
        return False
    body = sources.bodies[alias]
    token = next((t for t in body.tokens if t.ref == ref), None)
    if token is None:
        return False
    projected = body.transform.map_rectangle(token.source_box) if token.source_box else None
    return (
        loc.enrichment_artifact_id == descriptor.text_artifact.id
        and loc.geometry_artifact_id == descriptor.geometry_artifact.id
        and loc.reading_basis == body.producer.kind
        and (loc.region.model_dump() if loc.region else None)
        == (projected.model_dump() if projected else None)
        and loc.geometry_basis
        == (("NATIVE_DOCUMENT" if alias == "native" else "OCR_ENGINE") if projected else "NONE")
        and (e.text_start, e.text_end, e.offset_convention)
        == (token.span.start, token.span.end, "UNICODE_CODEPOINT")
        and e.source_snippet
        == token.raw_text
        == sources.text[alias].decode()[e.text_start : e.text_end]
    )


def equal_value(candidate, gold):
    if gold.value_type == "NUMBER":
        return candidate.numeric_value is not None and candidate.numeric_value == Decimal(
            gold.value
        )
    if gold.value_type == "INTEGER":
        return candidate.integer_value is not None and candidate.integer_value == int(gold.value)
    if gold.value_type == "BOOLEAN":
        return candidate.boolean_value is gold.value
    return candidate.text_value == gold.value


def score_claims(case, outputs, sources, supports, family):
    metrics = Counts()
    table_lines = {c.line for t in case.tables for c in t.cells}
    gold = [c for c in case.claims if (c.line in table_lines) == (family == "tables")]
    labels = {(c.line, c.kind): c for c in gold}
    lines = {w: line.id for line in case.lines for w in line.words}
    printed = {w.id: w.text for w in case.words if w.printed}
    candidates = [c for output in outputs for c in output.candidates]
    evidence = {e.id: e for output in outputs for e in output.evidence}
    tables = {t.id: t for output in outputs for t in output.tables}
    primary = defaultdict(list)
    for output in outputs:
        for link in output.candidate_evidence:
            if link.role == "PRIMARY":
                primary[link.candidate_id].append(evidence[link.evidence_id])
    matched, valid, claims_used = {}, set(), set()
    printed_agreement = 0
    duplicates = 0
    for candidate in candidates:
        citations = primary[candidate.id]
        origins = {
            lines.get(supports.get(token_key(e.location.support[0])))
            for e in citations
            if e.location.support
        }
        expected = labels.get((next(iter(origins)), candidate.kind)) if len(origins) == 1 else None
        if expected is None:
            continue
        if expected.id in claims_used:
            duplicates += 1
            continue
        claims_used.add(expected.id)
        matched[candidate.id] = expected
        if all(
            check_evidence(e, sources)
            and (
                e.table_id is None
                if family == "prose"
                else e.table_id in tables
                and e.location.structure_basis
                == tables[e.table_id].layout.metadata["structure_basis"]
                and str(e.id)
                in tables[e.table_id].layout.metadata["cell_evidence_ids"].get(e.cell_id, [])
            )
            for e in citations
        ):
            valid.add(candidate.id)
            printed_agreement += all(
                e.source_snippet == printed.get(supports.get(token_key(e.location.support[0])))
                for e in citations
            )

    correct = associations = normalized = mapping = 0
    retention = Counter()
    details = []
    for candidate in candidates:
        expected = matched.get(candidate.id)
        if expected is None:
            details.append({"status": candidate.mapping_status, "issue": "UNMATCHED_OR_DUPLICATE"})
            continue
        owner = matched.get(candidate.equipment_mention_candidate_id)
        association = (owner.id if owner else None) == expected.owner
        associations += bool(expected.owner and association and candidate.id in valid)
        status = candidate.mapping_status == expected.status
        if expected.status != "MAPPED":
            retention[expected.status] += status and candidate.id in valid
        meaning = (
            status
            and candidate.equipment_type_key == expected.equipment_type
            and candidate.observed_tag == expected.tag
            and candidate.attribute_key == expected.attribute
        )
        mapping += bool(
            expected.status == "MAPPED" and meaning and association and candidate.id in valid
        )
        value = (
            candidate.value_type == expected.value_type
            and candidate.unit == expected.unit
            and (expected.value_type is None or equal_value(candidate, expected))
        )
        normalized += bool(
            expected.value_type and meaning and association and value and candidate.id in valid
        )
        is_correct = bool(
            (meaning if expected.status == "MAPPED" else status)
            and association
            and value
            and candidate.id in valid
        )
        correct += is_correct
        details.append(
            {
                "gold_claim": expected.id,
                "status": candidate.mapping_status,
                "value": str(candidate.numeric_value)
                if candidate.numeric_value is not None
                else None,
                "unit": candidate.unit,
                "correct": is_correct,
                "printed_text_independently_verified": candidate.diagnostics.get(
                    "printed_text_independently_verified"
                ),
            }
        )
    metrics.pair("claim_occurrence", len(matched), len(gold), len(candidates))
    metrics.pair("correct_claim", correct, len(gold), len(candidates))
    for kind in ("EQUIPMENT_MENTION", "ATTRIBUTE_VALUE"):
        metrics.pair(
            kind.lower(),
            sum(c.kind == kind for c in matched.values()),
            sum(c.kind == kind for c in gold),
            sum(c.kind == kind for c in candidates),
        )
    metrics.record("mapped_claim", mapping, sum(c.status == "MAPPED" for c in gold))
    metrics.record(
        "exact_typed_value_unit", normalized, sum(c.value_type is not None for c in gold)
    )
    metrics.record("association", associations, sum(c.owner is not None for c in gold))
    metrics.record("positioned_evidence", len(valid), len(gold))
    metrics.record("primary_evidence_printed_agreement", printed_agreement, len(gold))
    metrics.record("false_claim", len(candidates) - correct, len(candidates))
    metrics.record("duplicate_claim", duplicates, len(candidates))
    for status in ("UNMAPPED", "INVALID"):
        metrics.record(
            f"{status.lower()}_retention", retention[status], sum(c.status == status for c in gold)
        )
    return metrics, details
