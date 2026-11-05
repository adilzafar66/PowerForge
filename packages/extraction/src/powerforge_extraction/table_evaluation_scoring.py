"""Source-first table scoring. Gold never comes from a converter or model-proposed key."""

from collections import Counter

from powerforge_extraction.evaluation_scoring import _same_value, fraction
from powerforge_extraction.identities import identity_hash

METRICS = {
    "table_precision": ("matched_tables", "predicted_tables"),
    "table_recall": ("matched_tables", "expected_tables"),
    "row_count_correctness": ("row_count_correct", "expected_tables"),
    "column_count_correctness": ("column_count_correct", "expected_tables"),
    "row_order_correctness": ("rows_correct", "expected_rows"),
    "column_order_correctness": ("columns_correct", "expected_columns"),
    "cell_detection_recall": ("matched_cells", "expected_cells"),
    "cell_content_correctness": ("cell_content_correct", "expected_cells"),
    "cell_span_correctness": ("cell_spans_correct", "expected_cells"),
    "header_relationship_correctness": ("cell_headers_correct", "expected_cells"),
    "orientation_correctness": ("orientation_correct", "expected_tables"),
    "table_evidence_correctness": ("table_evidence_correct", "expected_tables"),
    "cell_evidence_correctness": ("cell_evidence_correct", "expected_cells"),
    "structure_reliability_correctness": ("structure_basis_correct", "expected_tables"),
    "literal_text_reliability": ("native_cells_correct", "expected_native_cells"),
    "visual_report_reliability": ("visual_cells_correct", "expected_visual_cells"),
    "equipment_precision": ("equipment_correct", "predicted_equipment"),
    "equipment_recall": ("equipment_correct", "expected_equipment"),
    "attribute_detection_recall": ("detected_attributes", "expected_attributes"),
    "attribute_mapping_correctness": ("mapping_correct", "expected_attributes"),
    "normalized_value_correctness": ("value_correct", "expected_values"),
    "unit_correctness": ("unit_correct", "expected_values"),
    "association_correctness": ("association_correct", "expected_attributes"),
    "raw_preservation": ("raw_correct", "expected_attributes"),
    "unmapped_retention": ("retained_unmapped", "expected_unmapped"),
    "invalid_retention": ("retained_invalid", "expected_invalid"),
    "claim_evidence_correctness": ("claim_evidence_correct", "expected_claims"),
    "false_candidate_rate": ("false_candidates", "predicted_claims"),
    "incorrect_mapped_candidate_rate": ("incorrect_mapped_candidates", "predicted_mapped"),
    "unmatched_candidate_rate": ("unmatched_candidates", "predicted_claims"),
    "duplicate_candidate_rate": ("duplicate_candidates", "predicted_claims"),
    "extra_cell_rate": ("extra_cells", "predicted_cells"),
    "case_coverage": ("cases_completed", "expected_cases"),
    "stage_coverage": ("stages_completed", "planned_stages"),
    "claim_coverage": ("matched_claims", "expected_claims"),
}


def score_case(case, sources, outputs, failures=()):
    """Score published replay outputs, retaining gold denominators even after stage failure."""
    tables = [t for o in outputs for t in o.tables]
    candidates = [c for o in outputs for c in o.candidates]
    evidence = {e.id: e for o in outputs for e in o.evidence}
    links = [link for o in outputs for link in o.candidate_evidence]
    roles = {a.id: a.role for a in sources.spec.artifacts}
    primary = {
        c.id: [
            evidence[link.evidence_id]
            for link in links
            if link.candidate_id == c.id and link.role == "PRIMARY" and link.evidence_id in evidence
        ]
        for c in candidates
    }

    def valid_evidence(e, role):
        if (
            role not in {"native_text", "analysis_image"}
            or e.location.document_page_id != sources.spec.page_id
            or roles.get(e.location.page_artifact_id) != role
        ):
            return False
        expected_kind = (
            "TABLE_CELL"
            if e.cell_id is not None
            else "NATIVE_TEXT"
            if role == "native_text"
            else "VISUAL_REGION"
        )
        if e.source_kind != expected_kind:
            return False
        if role == "native_text":
            return bool(
                e.source_snippet
                and e.source_snippet in (sources.text or "")
                and e.location.region is None
                and (
                    e.text_start is None
                    and e.text_end is None
                    and e.offset_convention is None
                    or e.text_start is not None
                    and e.text_end is not None
                    and 0 <= e.text_start < e.text_end <= len(sources.text)
                    and sources.text[e.text_start : e.text_end] == e.source_snippet
                    and e.offset_convention == "UNICODE_CODEPOINT"
                )
            )
        return all(
            v is None
            for v in (
                e.source_snippet,
                e.text_start,
                e.text_end,
                e.offset_convention,
                e.location.region,
            )
        )

    def occurrence(e, role, text, span):
        if not valid_evidence(e, role):
            return False
        return role == "analysis_image" or (
            (not text or text in e.source_snippet)
            and (
                span is None
                or e.text_start is not None
                and e.text_start <= span[0]
                and span[1] <= e.text_end
            )
        )

    def table_matches(t, g):
        anchors = [evidence[eid] for eid in t.evidence_ids if eid in evidence]
        if not any(
            e.table_id == t.id and e.cell_id is None and occurrence(e, g.role, g.anchor, g.span)
            for e in anchors
        ):
            return False
        if g.role == "native_text":
            return True
        # A page-level image anchor alone cannot select one table from several.
        # Require independently labeled visible caption and positional landmarks.
        cells = {(c.row, c.column): c for c in t.layout.cells}
        gold_cells = {tuple(c.position): c for c in g.cells}
        return t.layout.title == g.title and all(
            tuple(p) in cells and cells[tuple(p)].text == (gold_cells[tuple(p)].text or "")
            for p in g.landmarks
        )

    # Ambiguous source occurrences abstain; duplicate predictions for one uniquely
    # identified occurrence earn at most one match and remain in precision's denominator.
    choices = {g.id: [t for t in tables if table_matches(t, g)] for g in case.tables}
    matched = {}
    for g in case.tables:
        unique = [t for t in choices[g.id] if sum(t in items for items in choices.values()) == 1]
        if unique:
            matched[g.id] = unique[0]
    counts = Counter({key: 0 for pair in METRICS.values() for key in pair})
    counts.update(
        expected_cases=1,
        cases_completed=int(not failures),
        planned_stages=2,
        stages_completed=0
        if "TABLE_RECONSTRUCTION_INVALID_RESPONSE" in failures
        else 1
        if failures
        else 2,
        expected_tables=len(case.tables),
        predicted_tables=len(tables),
        matched_tables=len(matched),
        expected_claims=len(case.claims),
        predicted_claims=len(candidates),
        expected_cells=sum(len(t.cells) for t in case.tables),
        predicted_cells=sum(len(t.layout.cells) for t in tables),
        expected_rows=sum(t.rows for t in case.tables),
        expected_columns=sum(t.columns for t in case.tables),
    )
    issues = []
    # A cell correspondence uses coordinates, not provider-local cell IDs or meanings.
    cells_by_table = {t.id: {(c.row, c.column): c for c in t.layout.cells} for t in tables}
    gold_by_table = {g.id: g for g in case.tables}
    cell_ok, cell_evidence_ok, table_ok = {}, {}, {}
    for g in case.tables:
        t = matched.get(g.id)
        for gc in g.cells:
            counts["expected_native_cells"] += gc.text_basis == "NATIVE_VERIFIED"
            counts["expected_visual_cells"] += gc.text_basis == "VISUAL_REPORTED"
        if t is None:
            issues.append({"gold_table": g.id, "reason": "MISSED_OR_AMBIGUOUS_TABLE"})
            continue
        by_position = cells_by_table[t.id]
        by_id = {c.id: (c.row, c.column) for c in t.layout.cells}
        observation = {
            c["local_ref"]: c for c in t.layout.metadata.get("observation", {}).get("cells", [])
        }
        reliability = t.layout.metadata.get("reliability", {})
        rel_cells = {c["cell_ref"]: c for c in reliability.get("cells", [])}
        basis = reliability.get("structure_basis") == g.structure_basis
        orient = t.table_kind == g.orientation
        anchors = [evidence[eid] for eid in t.evidence_ids if eid in evidence]
        table_evidence_ok = (
            bool(anchors)
            and all(
                e.table_id == t.id
                and e.cell_id is None
                and valid_evidence(e, roles.get(e.location.page_artifact_id))
                for e in anchors
            )
            and any(occurrence(e, g.role, g.anchor, g.span) for e in anchors)
        )
        counts["row_count_correct"] += len(t.layout.rows) == g.rows
        counts["column_count_correct"] += len(t.layout.columns) == g.columns
        counts["orientation_correct"] += orient
        counts["structure_basis_correct"] += basis
        counts["table_evidence_correct"] += table_evidence_ok
        table_ok[g.id] = basis and orient and table_evidence_ok
        for gc in g.cells:
            pos = tuple(gc.position)
            cell = by_position.get(pos)
            if cell is None:
                continue
            counts["matched_cells"] += 1
            obs = observation.get(cell.id, {})
            rel = rel_cells.get(cell.id, {})
            content = (
                cell.text == (gc.text or "")
                and obs.get("raw_text") == gc.text
                and obs.get("state") == gc.state
            )
            spans = cell.row_span == gc.row_span and cell.column_span == gc.column_span
            expected_headers = sorted(tuple(p) for p in gc.headers)
            header_ok = (
                cell.is_header == (gc.header_role != "NONE")
                and obs.get("header_role") == gc.header_role
                and rel.get("header_role") == gc.header_role
                and sorted(by_id.get(ref, (-1, -1)) for ref in obs.get("header_refs", []))
                == expected_headers
                and sorted(by_id.get(ref, (-1, -1)) for ref in rel.get("header_refs", []))
                == expected_headers
            )
            items = [
                evidence[eid]
                for eid in evidence
                if evidence[eid].table_id == t.id and evidence[eid].cell_id == cell.id
            ]
            good_evidence = (
                bool(items)
                and all(
                    e.source_kind == "TABLE_CELL"
                    and valid_evidence(e, roles.get(e.location.page_artifact_id))
                    for e in items
                )
                and any(occurrence(e, gc.role, gc.text, gc.span) for e in items)
            )
            # Persisted locator and declared reliability must agree with actual evidence.
            good_evidence = (
                good_evidence
                and cell.location is not None
                and any(cell.location == e.location for e in items)
                and rel.get("text_basis") == gc.text_basis
            )
            good_evidence = good_evidence and set(rel.get("evidence_ids", [])) == {
                str(e.id) for e in items
            }
            good_evidence = good_evidence and set(
                t.layout.metadata.get("item_evidence", {}).get(cell.id, [])
            ) == {str(e.id) for e in items}
            good_evidence = good_evidence and sorted(
                identity_hash(location)
                for location in t.layout.metadata.get("cell_source_locations", {}).get(cell.id, [])
            ) == sorted(identity_hash(e.location.model_dump(mode="json")) for e in items)
            cell_evidence_ok[g.id, pos] = good_evidence
            cell_ok[g.id, pos] = content and spans and header_ok
            counts["cell_content_correct"] += content
            counts["cell_spans_correct"] += spans
            counts["cell_headers_correct"] += header_ok
            counts["cell_evidence_correct"] += good_evidence
            counts["native_cells_correct"] += (
                gc.text_basis == "NATIVE_VERIFIED" and good_evidence and content
            )
            counts["visual_cells_correct"] += (
                gc.text_basis == "VISUAL_REPORTED" and good_evidence and content
            )

        def signature(c, gold=False):
            return (
                tuple(c.position) if gold else (c.row, c.column),
                c.text or "" if gold else c.text,
                c.row_span,
                c.column_span,
            )

        for axis, length, counter in (
            (0, g.rows, "rows_correct"),
            (1, g.columns, "columns_correct"),
        ):
            for index in range(length):
                actual = sorted(
                    signature(c) for c in t.layout.cells if (c.row, c.column)[axis] == index
                )
                expected = sorted(signature(c, True) for c in g.cells if c.position[axis] == index)
                counts[counter] += actual == expected
    counts["extra_cells"] = counts["predicted_cells"] - counts["matched_cells"]

    def claim_source(c, g):
        t = matched.get(g.table)
        if not t or c.kind != g.kind or c.raw_text != g.expression:
            return False
        cell = cells_by_table[t.id].get(tuple(g.cell)) if g.cell is not None else None
        return (
            bool(primary[c.id])
            and all(
                e.table_id == t.id and e.cell_id == (cell.id if cell else None)
                for e in primary[c.id]
            )
            and (g.cell is None or cell is not None)
        )

    # Match only on source table/cell/reading. Proposed registry keys/values/tags/status
    # and associations cannot make an incorrect prediction choose a more favorable gold.
    used, matched_claims = set(), {}
    for g in case.claims:
        choices_for_claim = [c for c in candidates if c.id not in used and claim_source(c, g)]
        if choices_for_claim:
            c = choices_for_claim[0]
            matched_claims[g.id] = c
            used.add(c.id)
    counts["matched_claims"] = len(matched_claims)

    def grounded(c, g):
        gt = gold_by_table[g.table]
        gc = next((x for x in gt.cells if x.position == g.cell), None)
        role, span, text = (gc.role, gc.span, gc.text) if gc else (gt.role, gt.span, gt.title)
        items = primary[c.id]
        native = any(e.source_snippet is not None for e in items)
        precision = (
            "TEXT_OFFSETS"
            if native
            and all(e.text_start is not None for e in items if e.source_snippet is not None)
            else "TEXT_PAGE"
            if native
            else "VISUAL_PAGE"
        )
        t = matched[g.table]
        supporting = [
            evidence[link.evidence_id]
            for link in links
            if link.candidate_id == c.id
            and link.role == "SUPPORTING"
            and link.evidence_id in evidence
        ]
        required_headers = (
            [cells_by_table[t.id].get(tuple(pos)) for pos in gc.headers]
            if (gc is not None and g.kind == "ATTRIBUTE_VALUE")
            else []
        )
        return (
            bool(items)
            and all(link.evidence_id in evidence for link in links if link.candidate_id == c.id)
            and all(valid_evidence(e, roles.get(e.location.page_artifact_id)) for e in items)
            and any(occurrence(e, role, text, span) for e in items)
            and c.diagnostics.get("table_id") == str(t.id)
            and c.diagnostics.get("text_verified") is native
            and c.diagnostics.get("grounding_precision") == precision
            and c.diagnostics.get("structure_basis") == gt.structure_basis
            and c.diagnostics.get("interpretation_limit")
            == ("VISUAL_REPORTED" if gt.structure_basis == "VISUAL_REPORTED" else "SOURCE_REPORTED")
            and all(
                header is not None and any(e.cell_id == header.id for e in supporting)
                for header in required_headers
            )
            and all(
                e.table_id == t.id and valid_evidence(e, roles.get(e.location.page_artifact_id))
                for e in supporting
            )
            and (gc is None or cell_evidence_ok.get((g.table, tuple(g.cell)), False))
        )

    def source_structure(g):
        gt = gold_by_table[g.table]
        if not table_ok.get(g.table, False):
            return False
        if g.cell is None:
            return True
        pending, checked = [tuple(g.cell)], set()
        by_position = {tuple(cell.position): cell for cell in gt.cells}
        while pending:
            pos = pending.pop()
            if pos in checked:
                continue
            checked.add(pos)
            if not cell_ok.get((g.table, pos), False) or not cell_evidence_ok.get(
                (g.table, pos), False
            ):
                return False
            pending.extend(tuple(p) for p in by_position[pos].headers)
        return True

    def association(c, g):
        if g.equipment is None:
            return c.equipment_mention_candidate_id is None and c.source_group_id is None
        eq = matched_claims.get(g.equipment)
        eqg = next(x for x in case.claims if x.id == g.equipment)
        return (
            eq is not None
            and grounded(eq, eqg)
            and source_structure(eqg)
            and eq.mapping_status == eqg.status
            and eq.equipment_type_key == eqg.equipment_type
            and eq.observed_tag == eqg.tag
            and eq.source_group_id is not None
            and sum(
                other.source_group_id == eq.source_group_id
                for gid, other in matched_claims.items()
                if next(x for x in case.claims if x.id == gid).kind == "EQUIPMENT_MENTION"
            )
            == 1
            and c.equipment_mention_candidate_id == eq.id
            and c.source_group_id == eq.source_group_id
        )

    for g in case.claims:
        equipment = g.kind == "EQUIPMENT_MENTION"
        counts["expected_equipment" if equipment else "expected_attributes"] += 1
        if not equipment:
            counts["expected_values"] += g.status == "MAPPED"
            counts["expected_unmapped"] += g.status == "UNMAPPED"
            counts["expected_invalid"] += g.status == "INVALID"
        c = matched_claims.get(g.id)
        if c is None:
            issues.append({"gold_claim": g.id, "reason": "MISSED_CLAIM"})
            continue
        location = grounded(c, g)
        counts["claim_evidence_correct"] += location
        structure = source_structure(g)
        meaning = (
            c.mapping_status == g.status
            and c.equipment_type_key == g.equipment_type
            and location
            and structure
        )
        if equipment:
            correct = meaning and c.observed_tag == g.tag
            counts["equipment_correct"] += correct
        else:
            counts["detected_attributes"] += 1
            assoc = association(c, g)
            counts["association_correct"] += assoc and location and structure
            mapping = meaning and c.attribute_key == g.attribute_key and assoc
            counts["mapping_correct"] += mapping
            raw = c.raw_value == g.raw_value and c.raw_unit == g.raw_unit
            counts["raw_correct"] += raw
            if g.status == "MAPPED":
                value = mapping and c.value_type == g.value_type and _same_value(c, g)
                unit = mapping and c.unit == g.unit
                counts["value_correct"] += value
                counts["unit_correct"] += unit
                correct = value and unit and raw
            else:
                retained = (
                    mapping
                    and raw
                    and c.attribute_key is None
                    and c.value_type is None
                    and all(
                        v is None
                        for v in (
                            c.numeric_value,
                            c.integer_value,
                            c.text_value,
                            c.boolean_value,
                            c.unit,
                        )
                    )
                )
                counts["retained_" + g.status.lower()] += retained
                correct = retained
        counts["correct_claims"] += correct
        counts["correct_mapped"] += correct and c.mapping_status == "MAPPED"
        if not correct:
            issues.append({"gold_claim": g.id, "reason": "FIELD_ASSOCIATION_OR_EVIDENCE_MISMATCH"})
    counts["predicted_equipment"] = sum(c.kind == "EQUIPMENT_MENTION" for c in candidates)
    counts["predicted_attributes"] = len(candidates) - counts["predicted_equipment"]
    counts["predicted_mapped"] = sum(c.mapping_status == "MAPPED" for c in candidates)
    counts["incorrect_mapped_candidates"] = counts["predicted_mapped"] - counts["correct_mapped"]
    counts["unmatched_candidates"] = len(candidates) - len(matched_claims)
    counts["false_candidates"] = len(candidates) - counts["correct_claims"]
    signatures = Counter(
        (
            c.kind,
            c.raw_text,
            tuple(sorted((str(e.table_id), e.cell_id or "") for e in primary[c.id])),
        )
        for c in candidates
    )
    counts["duplicate_candidates"] = sum(max(0, n - 1) for n in signatures.values())
    return {
        "case_id": case.id,
        "family": case.family,
        "source_provenance": case.provenance,
        "counts": dict(counts),
        "issues": issues,
        "stage_failures": list(failures),
        "rejections": dict(sum((Counter(o.diagnostic_counts) for o in outputs), Counter())),
    }


def report(cases, *, provenance, corpus_digest, resources):
    from powerforge_extraction.table_evaluation import VERSION, evaluation_identity

    counts = sum((Counter(c["counts"]) for c in cases), Counter())
    return {
        "evaluation_version": VERSION,
        "evaluation_rules_hash": evaluation_identity(),
        "corpus_sha256": corpus_digest,
        "resources": resources,
        "provenance": provenance,
        "live_model_quality_measured": False,
        "visual_text_independently_verified": False,
        "visual_relationships_independently_verified": False,
        "case_count": len(cases),
        "counts": dict(counts),
        "metrics": {key: fraction(counts[n], counts[d]) for key, (n, d) in METRICS.items()},
        "cases": cases,
        "rejections": dict(sum((Counter(c["rejections"]) for c in cases), Counter())),
    }
