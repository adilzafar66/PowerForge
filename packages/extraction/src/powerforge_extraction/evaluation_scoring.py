"""One-to-one source matching; no matching by proposed key, value or model reference ID."""

from collections import Counter
from decimal import Decimal


def fraction(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def _value(candidate):
    return {
        "NUMBER": candidate.numeric_value,
        "INTEGER": candidate.integer_value,
        "TEXT": candidate.text_value,
        "ENUM": candidate.text_value,
        "BOOLEAN": candidate.boolean_value,
    }.get(candidate.value_type)


def _same_value(candidate, gold):
    actual = _value(candidate)
    if gold.value_type in {"NUMBER", "INTEGER"}:
        return actual is not None and Decimal(str(actual)) == Decimal(gold.value)
    return type(actual) is type(gold.value) and actual == gold.value


def score_case(case, sources, outputs) -> dict:
    candidates = sorted(
        [c for output in outputs for c in output.candidates], key=lambda c: str(c.id)
    )
    evidence = {e.id: e for output in outputs for e in output.evidence}
    links = [
        link for output in outputs for link in output.candidate_evidence if link.role == "PRIMARY"
    ]
    primary = {
        c.id: [
            evidence[link.evidence_id]
            for link in sorted(links, key=lambda item: item.position)
            if link.candidate_id == c.id and link.evidence_id in evidence
        ]
        for c in candidates
    }
    roles = {item.id: item.role for item in sources.spec.artifacts}

    def role(c):
        return roles.get(primary[c.id][0].location.page_artifact_id) if primary[c.id] else None

    def valid(c):
        items = primary[c.id]
        if not items:
            return False
        for e in items:
            if (
                e.location.document_page_id != sources.spec.page_id
                or e.location.page_artifact_id not in roles
            ):
                return False
            if roles[e.location.page_artifact_id] == "native_text":
                if (
                    e.source_kind != "NATIVE_TEXT"
                    or not e.source_snippet
                    or c.raw_text not in e.source_snippet
                    or e.source_snippet not in sources.text
                ):
                    return False
                if e.text_start is not None:
                    if (
                        e.text_end is None
                        or not 0 <= e.text_start < e.text_end <= len(sources.text)
                        or sources.text[e.text_start : e.text_end] != e.source_snippet
                        or e.offset_convention != "UNICODE_CODEPOINT"
                    ):
                        return False
                elif e.text_end is not None or e.offset_convention is not None:
                    return False
                if c.diagnostics.get("text_verified") is not True:
                    return False
            elif (
                e.source_kind != "VISUAL_REGION"
                or any(
                    value is not None
                    for value in (
                        e.source_snippet,
                        e.text_start,
                        e.text_end,
                        e.offset_convention,
                        e.location.region,
                    )
                )
                or c.diagnostics.get("text_verified") is not False
            ):
                return False
        return True

    def grounded(c, g):
        if (
            not valid(c)
            or role(c) != g.role
            or c.diagnostics.get("grounding_precision") not in g.precision
        ):
            return False
        if g.span is None:
            return True
        return any(
            e.text_start is not None and e.text_start <= g.span[0] and g.span[1] <= e.text_end
            for e in primary[c.id]
        )

    gold = sorted(case.expected, key=lambda g: g.id)
    choices = {
        g.id: sorted(
            [
                c
                for c in candidates
                if c.kind == g.kind
                and role(c) == g.role
                and (
                    g.expression in c.raw_text
                    or (
                        c.raw_text in g.expression
                        and any(g.expression in (e.source_snippet or "") for e in primary[c.id])
                    )
                )
            ],
            key=lambda c: (not grounded(c, g), str(c.id)),
        )
        for g in gold
    }
    owner = {}
    protected = set()

    def assign(g, visited, precise=False):
        for c in choices[g.id]:
            if (precise and not grounded(c, g)) or (c.id in owner and owner[c.id].id in protected):
                continue
            if c.id in visited:
                continue
            visited.add(c.id)
            if c.id not in owner or assign(owner[c.id], visited, precise):
                owner[c.id] = g
                return True
        return False

    for g in gold:
        assign(g, set(), precise=True)
    protected = {item.id for item in owner.values()}
    for g in gold:
        if g.id not in protected:
            assign(g, set())
    matched = {g.id: c for c in candidates if (g := owner.get(c.id)) is not None}

    def association(c, g):
        if g.equipment is None:
            return c.equipment_mention_candidate_id is None and c.source_group_id is None
        eq = matched.get(g.equipment)
        eq_gold = next(item for item in gold if item.id == g.equipment)
        return (
            eq is not None
            and grounded(eq, eq_gold)
            and eq.source_group_id is not None
            and c.equipment_mention_candidate_id == eq.id
            and c.source_group_id == eq.source_group_id
        )

    counts = Counter(
        expected=len(gold),
        predicted=len(candidates),
        matched=len(matched),
        grounding_valid=sum(valid(c) for c in candidates),
        unmatched=len(candidates) - len(matched),
    )
    issues = []
    for g in gold:
        c = matched.get(g.id)
        equipment = g.kind == "EQUIPMENT_MENTION"
        counts["expected_equipment" if equipment else "expected_attributes"] += 1
        if not equipment and g.status == "MAPPED":
            counts["expected_values"] += 1
        if not equipment and g.status in {"UNMAPPED", "INVALID"}:
            counts["expected_" + g.status.lower()] += 1
        if c is None:
            issues.append({"gold_id": g.id, "reason": "MISSED"})
            continue
        counts["detected_equipment" if equipment else "detected_attributes"] += 1
        location = grounded(c, g)
        counts["grounding_gold"] += location
        meaning = c.mapping_status == g.status and c.equipment_type_key == g.equipment_type
        if equipment:
            correct = meaning and c.observed_tag == g.tag and location
            counts["equipment_correct"] += correct
        else:
            counts["association_correct"] += association(c, g)
            mapping = (
                meaning and c.attribute_key == g.attribute_key and association(c, g) and location
            )
            counts["mapping_correct"] += mapping
            raw = c.raw_value == g.raw_value and c.raw_unit == g.raw_unit
            counts["raw_correct"] += raw
            if g.status == "MAPPED":
                value = mapping and c.value_type == g.value_type and _same_value(c, g)
                counts["value_correct"] += value
                counts["unit_correct"] += mapping and c.unit == g.unit
                correct = value and c.unit == g.unit and raw
            else:
                retained = (
                    c.mapping_status == g.status
                    and raw
                    and c.attribute_key is None
                    and c.value_type is None
                    and all(
                        value is None
                        for value in (
                            c.numeric_value,
                            c.integer_value,
                            c.text_value,
                            c.boolean_value,
                            c.unit,
                        )
                    )
                    and location
                )
                counts["retained_" + g.status.lower()] += retained
                correct = mapping and retained
        counts["correct"] += correct
        if not correct:
            issues.append(
                {
                    "gold_id": g.id,
                    "prediction_id": str(c.id),
                    "reason": "FIELD_ASSOCIATION_OR_GROUNDING_MISMATCH",
                }
            )
    counts["predicted_equipment"] = sum(c.kind == "EQUIPMENT_MENTION" for c in candidates)
    counts["predicted_attributes"] = len(candidates) - counts["predicted_equipment"]
    counts["false_candidates"] = len(candidates) - counts["correct"]
    for source_role in ("native_text", "analysis_image"):
        counts["predicted_" + source_role] = sum(role(c) == source_role for c in candidates)
        counts["grounding_" + source_role] = sum(
            valid(c) and role(c) == source_role for c in candidates
        )
    # Distinct mentions in the same case are independent assets/occurrences, even if tags repeat.
    groups = [
        matched[g.id].source_group_id
        for g in gold
        if g.kind == "EQUIPMENT_MENTION" and g.id in matched
    ]
    counts["group_pairs"] = len(groups) * (len(groups) - 1) // 2
    counts["separate_group_pairs"] = sum(
        a is not None and b is not None and a != b
        for i, a in enumerate(groups)
        for b in groups[i + 1 :]
    )
    return {
        "case_id": case.id,
        "family": case.family,
        "counts": dict(counts),
        "issues": issues,
        "rejections": dict(sum((Counter(o.diagnostic_counts) for o in outputs), Counter())),
    }


def report(
    case_reports: list[dict], *, provenance: str, corpus_digest: str, resources: dict
) -> dict:
    from powerforge_extraction.evaluation import evaluation_identity

    counts = Counter()
    for item in case_reports:
        counts.update(item["counts"])
    metrics = {
        "equipment_precision": ("equipment_correct", "predicted_equipment"),
        "equipment_recall": ("equipment_correct", "expected_equipment"),
        "attribute_detection_recall": ("detected_attributes", "expected_attributes"),
        "attribute_mapping_correctness": ("mapping_correct", "expected_attributes"),
        "normalized_value_correctness": ("value_correct", "expected_values"),
        "unit_correctness": ("unit_correct", "expected_values"),
        "raw_preservation": ("raw_correct", "expected_attributes"),
        "unmapped_retention": ("retained_unmapped", "expected_unmapped"),
        "invalid_retention": ("retained_invalid", "expected_invalid"),
        "grounding_location_validity": ("grounding_valid", "predicted"),
        "grounding_against_gold": ("grounding_gold", "predicted"),
        "association_correctness": ("association_correct", "expected_attributes"),
        "false_candidate_rate": ("false_candidates", "predicted"),
        "unmatched_candidate_rate": ("unmatched", "predicted"),
        "group_separation": ("separate_group_pairs", "group_pairs"),
        "native_location_validity": ("grounding_native_text", "predicted_native_text"),
        "visual_page_location_validity": ("grounding_analysis_image", "predicted_analysis_image"),
    }
    return {
        "evaluation_version": "engineering-evaluation-v1",
        "evaluation_rules_hash": evaluation_identity(),
        "visual_text_independently_verified": False,
        "provenance": provenance,
        "live_model_quality_measured": provenance == "LIVE_OPENAI",
        "corpus_sha256": corpus_digest,
        "resources": resources,
        "case_count": len(case_reports),
        "counts": dict(counts),
        "metrics": {name: fraction(counts[n], counts[d]) for name, (n, d) in metrics.items()},
        "cases": case_reports,
        "rejections": dict(sum((Counter(item["rejections"]) for item in case_reports), Counter())),
    }
