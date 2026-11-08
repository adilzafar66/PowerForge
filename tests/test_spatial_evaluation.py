"""Independent scorer mutations plus actual paired native and OCR replay."""

import json
from pathlib import Path

import pytest

from extraction_worker.spatial_evaluation import MeteredStorage, derive, evaluate, prepare, render
from extraction_worker.spatial_evaluation_gold import load_cases, read_source
from extraction_worker.spatial_evaluation_scoring import raw_readings, score_layout
from powerforge_extraction.enrichment_prepare import sha
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_provenance.spatial_sources import load_positioned_text
from powerforge_shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
CORPUS = EVALS / "spatial/v1/corpus.json"


def selected(case_id):
    cases, _ = load_cases(CORPUS, EVALS, [case_id])
    case, path = cases[0]
    return case, path, read_source(case, path)


def test_equal_text_in_the_wrong_cell_loses_ownership_and_partition_credit():
    case, file, data = selected("regular-borderless")
    record = json.loads(
        (ROOT / "tests/fixtures/enrichment/preparation_v1_environment.json").read_text()
    )
    profile = preparation_profile(
        Settings(
            _env_file=None,
            enrichment_enabled=True,
            enrichment_ocr_configuration=json.dumps(record["configuration"]),
        )
    )

    def no_ocr():
        raise AssertionError("This native page requires no OCR")

    storage = MeteredStorage(None)
    output, prepared, base = prepare(
        case, file, data, render(file, data, case.page), storage, profile, no_ocr, no_ocr
    )
    spatial = derive(prepared, output, base, storage).layout
    ref = prepared.manifest.representations[0]
    body, text = load_positioned_text(
        prepared.manifest,
        ref.ref,
        output.blobs[ref.geometry_artifact.id][1],
        output.blobs[ref.text_artifact.id][1],
    )
    _, support = raw_readings(case, {"native": body})
    baseline, _ = score_layout(case, spatial, support)
    assert baseline["supported_partition_recall"]["numerator"] == 1
    table = spatial.tables[0]
    cells = list(table.cells)
    indexes = {(c.row, c.column): i for i, c in enumerate(cells)}
    i, j = indexes[1, 1], indexes[2, 1]
    first, second = cells[i], cells[j]
    readings = {r.ref: r for r in spatial.readings}

    def raw(cell):
        token = readings[cell.readings[0]].preferred.ref
        span = next(t.span for t in body.tokens if t.ref == token)
        return text[span.start : span.end]

    assert raw(first) == raw(second) == "600"
    cells[i] = first.model_copy(update={"readings": second.readings})
    cells[j] = second.model_copy(update={"readings": first.readings})
    wrong_table = table.model_copy(update={"cells": tuple(cells)})
    wrong = spatial.model_copy(update={"tables": (wrong_table,)})
    metrics, _ = score_layout(case, wrong, support)
    assert metrics["table_region_recall"] == baseline["table_region_recall"]
    assert metrics["supported_partition_recall"]["numerator"] == 0
    assert metrics["false_supported_partition"]["numerator"] == 1
    assert metrics["cell_occurrence_recall"]["numerator"] == (
        baseline["cell_occurrence_recall"]["numerator"] - 2
    )


def test_missing_ocr_keeps_all_printed_denominators_and_empty_rates_are_null():
    case, _, _ = selected("hybrid-auto")
    expected = [word.text for word in case.words if word.printed]
    raw, matches = raw_readings(case, {})
    assert not matches
    assert raw["ocr_wer"] == {"numerator": len(expected), "denominator": len(expected), "rate": 1}
    assert raw["ocr_cer"]["denominator"] == len(" ".join(expected))
    assert raw["ocr_word_precision"]["rate"] is None
    assert raw["ocr_eligible_pages_recognized"]["numerator"] == 0


def test_source_digest_and_selection_fail_closed(tmp_path):
    case, _, data = selected("positioned-6d")
    tampered = tmp_path / "same-size.pdf"
    tampered.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(ValueError, match="source digest differs"):
        read_source(case, tampered)
    for selection in (["unknown"], ["positioned-6d", "positioned-6d"]):
        with pytest.raises(ValueError, match="selection"):
            load_cases(CORPUS, EVALS, selection)


def test_actual_paired_sources_and_numeric_error_keep_independent_structure_and_text(tmp_path):
    artifacts = tmp_path / "artifacts"
    report = evaluate(
        CORPUS,
        EVALS,
        selected=["positioned-6d", "scanned-schedule", "transformer-nameplate"],
        artifacts=artifacts,
    )
    assert report["model_provenance"] == "DETERMINISTIC_SOURCE_MOCK"
    assert report["live_openai_quality_measured"] is False
    assert report["provider_tokens"] is report["provider_cost_usd"] is None
    assert all(not case["failures"] for case in report["cases"])
    pair = report["legacy_comparisons"]["positioned-6d"]
    assert pair["legacy_replays"]["pdf_native_unresolved"]["correct_mapped"] == 0
    assert pair["enhanced"]["correct_claim_recall"]["numerator"] == 2
    assert pair["enhanced_supported_partition"]["numerator"] == 1
    assert report["legacy_comparisons"]["transformer-nameplate"]["legacy_profile_source"] == (
        "VISUAL_PAGE"
    )
    scanned = next(row for row in report["cases"] if row["id"] == "scanned-schedule")
    assert scanned["ocr_invocations_started"] == 1
    injected = report["controls"]["injected_numeric_error"]
    assert injected["replacements"] == 1
    changed = injected["result"]
    assert (
        changed["preprocessing"]["supported_partition_recall"]
        == (scanned["preprocessing"]["supported_partition_recall"])
    )
    good = scanned["mock_conversion"]["tables"]["metrics"]
    altered = changed["mock_conversion"]["tables"]["metrics"]
    assert altered["positioned_evidence"] == good["positioned_evidence"]
    for name in ("primary_evidence_printed_agreement", "exact_typed_value_unit"):
        assert altered[name]["numerator"] == good[name]["numerator"] - 1
    assert any(
        c["value"] == "0.6" and c["printed_text_independently_verified"] is False
        for c in changed["mock_conversion"]["tables"]["claims"]
    )
    for name, record in scanned["source_artifacts"].items():
        payload = (artifacts / "scanned-schedule" / name).read_bytes()
        assert (len(payload), sha(payload)) == (record["size_bytes"], record["sha256"])
