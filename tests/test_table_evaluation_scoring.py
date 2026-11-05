"""Mutation controls show table scores respond to incorrect structure and provenance."""

import copy
from decimal import Decimal
from uuid import uuid4

import pytest

from powerforge_extraction.evaluation import read_json
from powerforge_extraction.table_evaluation import load_table_corpus, replay
from powerforge_extraction.table_evaluation_scoring import score_case
from powerforge_provenance.locations import Region
from test_table_evaluation import CORPUS, RECORDINGS


def snapshot(case_id="transformer"):
    case = next(c for c in load_table_corpus(CORPUS)[0].cases if c.id == case_id)
    sources, outputs, failures = replay(
        case, CORPUS.parent, read_json(RECORDINGS)["cases"][case_id]
    )
    assert not failures
    return case, sources, outputs


def counts(case, sources, outputs):
    return score_case(case, sources, outputs)["counts"]


def change_candidate(outputs, predicate, changes):
    return [
        o.model_copy(
            update={
                "candidates": [
                    c.model_copy(update=changes) if predicate(c) else c for c in o.candidates
                ]
            }
        )
        for o in outputs
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"numeric_value": Decimal("999")},
        {"attribute_key": "primary_voltage"},
        {"unit": "V"},
        {"value_type": "INTEGER"},
        {"mapping_status": "UNMAPPED"},
        {"equipment_type_key": "LV_BREAKER"},
    ],
)
def test_wrong_semantics_do_not_change_source_matching_or_earn_value_credit(changes):
    case, sources, outputs = snapshot()
    baseline = counts(case, sources, outputs)
    altered = change_candidate(outputs, lambda c: c.raw_text == "600", changes)
    score = counts(case, sources, altered)
    assert score["matched_claims"] == baseline["matched_claims"] == 6
    assert score["correct_claims"] < baseline["correct_claims"]
    assert score["false_candidates"] == 1


@pytest.mark.parametrize(
    "slot,wrong",
    [
        ("integer_value", 9007199254740992),
        ("text_value", "4 AWG"),
    ],
)
def test_exact_bigint_and_text_are_measured_without_float_coercion(slot, wrong):
    case, sources, outputs = snapshot("cable")
    altered = change_candidate(
        outputs,
        lambda c: (
            getattr(c, slot) is not None
            and (slot != "text_value" or c.attribute_key == "conductor_size")
        ),
        {slot: wrong},
    )
    assert counts(case, sources, altered)["value_correct"] == 3


def test_false_boolean_is_not_equivalent_to_zero_or_missing():
    case, sources, outputs = snapshot("breaker")
    for value in (0, None, True):
        altered = change_candidate(
            outputs, lambda c: c.attribute_key == "normally_closed", {"boolean_value": value}
        )
        assert counts(case, sources, altered)["value_correct"] == 2


@pytest.mark.parametrize(
    "mutation", ["content", "span", "headers", "orientation", "basis", "row_count", "column_count"]
)
def test_layout_mutations_lower_independent_reconstruction_scores(mutation):
    case, sources, outputs = snapshot()
    outputs = copy.deepcopy(outputs)
    table = outputs[0].tables[0]
    layout = table.layout
    metric = {
        "content": "cell_content_correct",
        "span": "cell_spans_correct",
        "headers": "cell_headers_correct",
        "orientation": "orientation_correct",
        "basis": "structure_basis_correct",
        "row_count": "row_count_correct",
        "column_count": "column_count_correct",
    }[mutation]
    before = counts(case, sources, outputs)[metric]
    if mutation == "content":
        layout.cells[7] = layout.cells[7].model_copy(update={"text": "480"})
    elif mutation == "span":
        layout.cells[7] = layout.cells[7].model_copy(update={"row_span": 2})
    elif mutation == "headers":
        layout.metadata["observation"]["cells"][7]["header_refs"] = ["c0_2"]
    elif mutation == "orientation":
        outputs[0].tables[0] = table.model_copy(update={"table_kind": "ATTRIBUTE_ROWS"})
    elif mutation == "basis":
        layout.metadata["reliability"]["structure_basis"] = "VISUAL_REPORTED"
    elif mutation == "row_count":
        layout.rows.append("extra-row")
    else:
        layout.columns.append("extra-column")
    score = counts(case, sources, outputs)
    assert score[metric] < before
    assert score["expected_cells"] == 12 and score["expected_claims"] == 6
    if mutation in {"content", "span", "headers", "orientation", "basis"}:
        assert score["value_correct"] < 4


@pytest.mark.parametrize("axis", ["row", "column"])
def test_ordered_source_coordinates_detect_swapped_rows_or_columns(axis):
    case, sources, outputs = snapshot()
    outputs = copy.deepcopy(outputs)
    cells = outputs[0].tables[0].layout.cells
    for i, cell in enumerate(cells):
        value = getattr(cell, axis)
        if value in (1, 2):
            cells[i] = cell.model_copy(update={axis: 3 - value})
    score = counts(case, sources, outputs)
    assert score["rows_correct"] < score["expected_rows"]
    assert score["columns_correct"] < score["expected_columns"]


@pytest.mark.parametrize(
    "mutation", ["offset", "page", "artifact", "geometry", "cell", "table", "snippet", "kind"]
)
def test_forged_cell_evidence_costs_credit_despite_correct_registry_value(mutation):
    case, sources, outputs = snapshot()
    outputs = copy.deepcopy(outputs)
    for i, e in enumerate(outputs[0].evidence):
        if e.cell_id != "c1_3":
            continue
        if mutation == "offset":
            change = {"text_start": e.text_start + 1}
        elif mutation == "page":
            change = {"location": e.location.model_copy(update={"document_page_id": uuid4()})}
        elif mutation == "artifact":
            change = {"location": e.location.model_copy(update={"page_artifact_id": uuid4()})}
        elif mutation == "geometry":
            change = {
                "location": e.location.model_copy(
                    update={"region": Region(x=0, y=0, width=0.1, height=0.1)}
                )
            }
        elif mutation == "cell":
            change = {"cell_id": "c2_3"}
        elif mutation == "table":
            change = {"table_id": uuid4()}
        elif mutation == "snippet":
            change = {"source_snippet": "600 V invented"}
        else:
            change = {"source_kind": "NATIVE_TEXT"}
        outputs[0].evidence[i] = e.model_copy(update=change)
    score = counts(case, sources, outputs)
    assert score["value_correct"] == (2 if mutation == "cell" else 3)
    assert score["claim_evidence_correct"] < score["expected_claims"]


def test_foreign_visual_artifact_without_text_is_not_accepted_as_page_grounding():
    case, sources, outputs = snapshot("breaker_visual")
    outputs = copy.deepcopy(outputs)
    for i, e in enumerate(outputs[0].evidence):
        if e.cell_id == "c1_1":
            outputs[0].evidence[i] = e.model_copy(
                update={"location": e.location.model_copy(update={"page_artifact_id": uuid4()})}
            )
    assert counts(case, sources, outputs)["value_correct"] == 0


def test_bad_header_evidence_cannot_support_correct_looking_values():
    case, sources, outputs = snapshot()
    outputs = copy.deepcopy(outputs)
    for i, e in enumerate(outputs[0].evidence):
        if e.cell_id == "c0_3":
            outputs[0].evidence[i] = e.model_copy(update={"source_snippet": "Primary (V)"})
    assert counts(case, sources, outputs)["value_correct"] == 2


def test_same_repeated_tag_does_not_hide_wrong_equipment_association_or_merged_groups():
    case, sources, outputs = snapshot("repeated_tags")
    eqs = [c for c in outputs[1].candidates if c.kind == "EQUIPMENT_MENTION"]
    altered = change_candidate(
        outputs,
        lambda c: c.raw_text == "480",
        {
            "equipment_mention_candidate_id": eqs[0].id,
            "source_group_id": eqs[0].source_group_id,
        },
    )
    assert counts(case, sources, altered)["association_correct"] == 1
    merged = change_candidate(
        outputs,
        lambda c: c.kind == "EQUIPMENT_MENTION",
        {
            "source_group_id": eqs[0].source_group_id,
        },
    )
    assert counts(case, sources, merged).get("association_correct", 0) == 0


def test_two_tables_on_same_page_do_not_share_value_cell_ownership():
    case, sources, outputs = snapshot("multiple_tables")
    outputs = copy.deepcopy(outputs)
    attrs = [c for c in outputs[1].candidates if c.kind == "ATTRIBUTE_VALUE"]
    primary = {
        link.candidate_id: link for link in outputs[1].candidate_evidence if link.role == "PRIMARY"
    }
    a, b = attrs
    outputs[1] = outputs[1].model_copy(
        update={
            "candidate_evidence": [
                link.model_copy(update={"evidence_id": primary[b.id].evidence_id})
                if link.candidate_id == a.id and link.role == "PRIMARY"
                else link
                for link in outputs[1].candidate_evidence
            ]
        }
    )
    assert counts(case, sources, outputs)["value_correct"] == 1


def test_duplicates_and_extra_tables_are_explicit_and_do_not_inflate_recall():
    case, sources, outputs = snapshot()
    outputs = copy.deepcopy(outputs)
    candidate = outputs[1].candidates[-1]
    duplicate = candidate.model_copy(update={"id": uuid4()})
    outputs[1].candidates.append(duplicate)
    outputs[1].candidate_evidence.extend(
        [
            link.model_copy(update={"candidate_id": duplicate.id})
            for link in list(outputs[1].candidate_evidence)
            if link.candidate_id == candidate.id
        ]
    )
    score = counts(case, sources, outputs)
    assert score["matched_claims"] == 6 and score["duplicate_candidates"] == 1
    assert score["false_candidates"] == score["unmatched_candidates"] == 1
    # An extra table with no corresponding evidence cannot earn source detection credit.
    outputs[0].tables.append(outputs[0].tables[0].model_copy(update={"id": uuid4()}))
    assert counts(case, sources, outputs)["predicted_tables"] == 2
    assert counts(case, sources, outputs)["matched_tables"] == 1


@pytest.mark.parametrize(
    "case_id,status", [("unknown_type", "UNMAPPED"), ("invalid_value", "INVALID")]
)
def test_unmapped_invalid_retention_checks_raw_fields_status_and_empty_normalized_slots(
    case_id, status
):
    case, sources, outputs = snapshot(case_id)
    for changes in (
        {"raw_value": "invented"},
        {"numeric_value": Decimal("400")},
        {"mapping_status": "MAPPED"},
    ):
        altered = change_candidate(outputs, lambda c: c.kind == "ATTRIBUTE_VALUE", changes)
        assert counts(case, sources, altered)["retained_" + status.lower()] == 0


def test_visual_geometry_and_false_text_verification_reduce_page_report_credit():
    case, sources, outputs = snapshot("breaker_visual")
    altered = change_candidate(
        outputs,
        lambda c: True,
        {
            "diagnostics": {
                **outputs[1].candidates[0].diagnostics,
                "text_verified": True,
            }
        },
    )
    assert counts(case, sources, altered)["claim_evidence_correct"] == 0
    outputs = copy.deepcopy(outputs)
    for i, e in enumerate(outputs[0].evidence):
        outputs[0].evidence[i] = e.model_copy(update={"text_start": 0, "text_end": 10})
    assert counts(case, sources, outputs)["matched_tables"] == 0


def test_missing_cells_and_failed_stages_keep_the_same_gold_denominators():
    case, sources, outputs = snapshot()
    outputs[0].tables[0].layout.cells.pop()
    score = counts(case, sources, outputs)
    assert score["expected_cells"] == 12 and score["matched_cells"] == 11
    assert score["expected_claims"] == 6
    assert score["value_correct"] == 3


def test_correct_literal_at_the_wrong_repeated_source_occurrence_costs_equipment_credit():
    case, sources, outputs = snapshot("repeated_tags")
    outputs = copy.deepcopy(outputs)
    wrong_start = sources.text.rindex("TX-1")
    for i, e in enumerate(outputs[0].evidence):
        if e.cell_id == "c1_0":
            outputs[0].evidence[i] = e.model_copy(
                update={
                    "text_start": wrong_start,
                    "text_end": wrong_start + 4,
                }
            )
    score = counts(case, sources, outputs)
    assert score["equipment_correct"] == 1
    assert score["value_correct"] == 1


def test_missing_candidate_header_citation_does_not_earn_mapping_credit():
    case, sources, outputs = snapshot()
    evidence = {e.id: e for e in outputs[0].evidence}
    altered = copy.deepcopy(outputs)
    altered[1] = altered[1].model_copy(
        update={
            "candidate_evidence": [
                link
                for link in altered[1].candidate_evidence
                if evidence[link.evidence_id].cell_id != "c0_3"
            ]
        }
    )
    assert counts(case, sources, altered)["value_correct"] == 2


def test_visual_candidate_must_retain_explicit_interpretation_limit_marker():
    case, sources, outputs = snapshot("breaker_visual")
    altered = change_candidate(
        outputs,
        lambda c: True,
        {
            "diagnostics": {
                **outputs[1].candidates[0].diagnostics,
                "interpretation_limit": "SOURCE_REPORTED",
            }
        },
    )
    assert counts(case, sources, altered)["correct_claims"] == 0


@pytest.mark.parametrize("metadata", ["cell_source_locations", "item_evidence"])
def test_persisted_cell_locator_metadata_must_agree_with_primary_evidence(metadata):
    case, sources, outputs = snapshot()
    outputs = copy.deepcopy(outputs)
    outputs[0].tables[0].layout.metadata[metadata]["c1_3"] = []
    assert counts(case, sources, outputs)["value_correct"] == 3
