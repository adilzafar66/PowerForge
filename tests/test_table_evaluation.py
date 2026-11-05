"""New M4 corpus/replay contract tests; no repeated database/worker regressions."""

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from powerforge_extraction.evaluation import read_json, sources_for
from powerforge_extraction.table_eval import evaluate, main
from powerforge_extraction.table_evaluation import (
    TableCorpus,
    evaluation_identity,
    load_table_corpus,
    replay,
    resources,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals/tables/v1/corpus.json"
RECORDINGS = CORPUS.parent / "scripted.json"
CASE_IDS = [c["id"] for c in read_json(CORPUS)["cases"]]


def write_recordings(tmp_path, mutate):
    data = read_json(RECORDINGS)
    mutate(data)
    path = tmp_path / "recorded.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_independent_corpus_counts_coverage_and_committed_scripted_report():
    corpus, digest = load_table_corpus(CORPUS)
    assert len(corpus.cases) == 27
    assert sum(len(c.tables) for c in corpus.cases) == 27
    assert sum(len(c.claims) for c in corpus.cases) == 73
    assert sum(len(t.cells) for c in corpus.cases for t in c.tables) == 146
    result = evaluate(CORPUS, RECORDINGS)
    assert result == read_json(CORPUS.parent / "scripted-report.json")
    assert result["corpus_sha256"] == digest
    assert result["provenance"] == "SCRIPTED_MOCK"
    assert not result["live_model_quality_measured"]
    assert not result["visual_text_independently_verified"]
    assert not result["visual_relationships_independently_verified"]
    counts = result["counts"]
    assert counts["matched_tables"] == 26
    assert counts["matched_cells"] == 142
    assert counts["matched_claims"] == 68
    assert counts["correct_claims"] == 65
    assert counts["value_correct"] == 30 and counts["expected_values"] == 34
    assert result["metrics"]["stage_coverage"] == {
        "numerator": 51,
        "denominator": 54,
        "rate": 51 / 54,
    }
    assert counts.get("incorrect_mapped_candidates", 0) == 0
    assert counts["retained_unmapped"] == 6 and counts["expected_unmapped"] == 7
    assert counts["retained_invalid"] == counts["expected_invalid"] == 1


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_every_case_preserves_denominators_and_declares_source_provenance(case_id):
    result = evaluate(CORPUS, RECORDINGS, [case_id])
    case = next(c for c in load_table_corpus(CORPUS)[0].cases if c.id == case_id)
    counts = result["counts"]
    assert counts.get("expected_tables", 0) == len(case.tables)
    assert counts.get("expected_claims", 0) == len(case.claims)
    assert counts.get("expected_cells", 0) == sum(len(t.cells) for t in case.tables)
    assert result["cases"][0]["source_provenance"] == "SYNTHETIC_AUTHORED"
    for metric in result["metrics"].values():
        assert set(metric) == {"numerator", "denominator", "rate"}
        if metric["denominator"] == 0:
            assert metric["rate"] is None


@pytest.mark.parametrize("stage", ["reconstruction", "interpretation"])
@pytest.mark.parametrize("failure", [None, {"overflowed": True}, {"unexpected": "field"}])
def test_failed_payloads_cannot_shrink_gold_or_publish_partial_stage(tmp_path, stage, failure):
    path = write_recordings(tmp_path, lambda d: d["cases"]["transformer"].update({stage: failure}))
    result = evaluate(CORPUS, path, ["transformer"])
    assert result["counts"]["expected_claims"] == 6
    assert result["counts"]["expected_cells"] == 12
    assert result["counts"].get("predicted_claims", 0) == 0
    assert result["counts"].get("predicted_tables", 0) == (0 if stage == "reconstruction" else 1)
    assert result["cases"][0]["stage_failures"]


@pytest.mark.parametrize("selection", [[], ["missing"], ["cable", "cable"]])
def test_selections_reject_unknown_duplicate_or_empty(selection):
    with pytest.raises(ValueError, match="selection"):
        evaluate(CORPUS, RECORDINGS, selection)


@pytest.mark.parametrize(
    "mutation", ["missing_case", "missing_stage", "resource", "corpus", "version"]
)
def test_recording_identity_and_completeness_fail_closed(tmp_path, mutation):
    def mutate(d):
        if mutation == "missing_case":
            del d["cases"]["cable"]
        elif mutation == "missing_stage":
            del d["cases"]["cable"]["interpretation"]
        elif mutation == "resource":
            d["resources"]["manifest"] = "unavailable"
        elif mutation == "corpus":
            d["corpus_sha256"] = "0" * 64
        else:
            d["version"] = "table-recordings-future"

    with pytest.raises(ValueError):
        evaluate(CORPUS, write_recordings(tmp_path, mutate))


def test_file_claim_of_live_provenance_cannot_designate_live_quality(tmp_path):
    path = write_recordings(tmp_path, lambda d: d.update(provenance="LIVE_OPENAI"))
    result = evaluate(CORPUS, path)
    assert result["provenance"] == "UNVERIFIED_RECORDING"
    assert not result["live_model_quality_measured"]


def test_empty_table_result_skips_malformed_dependent_payload_and_has_null_denominators(tmp_path):
    path = write_recordings(tmp_path, lambda d: d["cases"]["no_table"].update(interpretation=None))
    result = evaluate(CORPUS, path, ["no_table"])
    assert not result["cases"][0]["stage_failures"]
    assert result["metrics"]["equipment_precision"]["rate"] is None
    assert result["metrics"]["table_recall"]["rate"] is None
    assert result["metrics"]["stage_coverage"]["numerator"] == 2


def test_model_local_ids_and_array_order_do_not_select_tables_cells_or_claims(tmp_path):
    def mutate(d):
        rec = d["cases"]["multiple_tables"]
        replacements = {}
        for table in rec["reconstruction"]["tables"]:
            for value in [
                table["local_ref"],
                *table["rows"],
                *table["columns"],
                *(c["local_ref"] for c in table["cells"]),
                "title",
            ]:
                replacements[value] = "renamed_" + value
        for item in [*rec["interpretation"]["equipment"], *rec["interpretation"]["attributes"]]:
            replacements[item["local_ref"]] = "renamed_" + item["local_ref"]

        def rename(value):
            if isinstance(value, dict):
                return {
                    k: rename(v)
                    if k.endswith("ref")
                    or k.endswith("refs")
                    or k
                    in {"rows", "columns", "equipment", "attributes", "tables", "cells", "title"}
                    else v
                    for k, v in value.items()
                }
            if isinstance(value, list):
                return [rename(v) for v in value]
            return replacements.get(value, value) if isinstance(value, str) else value

        d["cases"]["multiple_tables"] = {k: rename(v) for k, v in rec.items()}
        for table in d["cases"]["multiple_tables"]["reconstruction"]["tables"]:
            table["cells"].reverse()
        d["cases"]["multiple_tables"]["reconstruction"]["tables"].reverse()

    original = evaluate(CORPUS, RECORDINGS, ["multiple_tables"])
    renamed = evaluate(CORPUS, write_recordings(tmp_path, mutate), ["multiple_tables"])
    assert renamed["metrics"] == original["metrics"]


@pytest.mark.parametrize(
    "mutation", ["path", "hash", "size", "span", "duplicate", "cell", "association"]
)
def test_corpus_contract_rejects_source_or_annotation_tampering(mutation):
    raw = read_json(CORPUS)
    if mutation in {"path", "hash", "size"}:
        case = TableCorpus.model_validate(raw).cases[0]
        source = case.sources[0]
        if mutation == "path":
            source.path = "../outside.txt"
        elif mutation == "hash":
            source.sha256 = "0" * 64
        else:
            source.size_bytes += 1
        with pytest.raises(ValueError):
            sources_for(case, CORPUS.parent)
        return
    case = raw["cases"][0]
    if mutation == "span":
        case["tables"][0]["cells"][0]["position"] = [-1, 0]
    elif mutation == "duplicate":
        case["claims"].append(copy.deepcopy(case["claims"][0]))
    elif mutation == "cell":
        case["claims"][0]["cell"] = [99, 99]
    else:
        case["claims"][2]["equipment"] = "foreign-equipment"
    with pytest.raises(ValueError):
        TableCorpus.model_validate(raw)


def test_new_identity_fixture_pins_evaluator_corpus_and_untouched_6c_sources():
    fixture = read_json(ROOT / "tests/fixtures/extraction/table_evaluation_v1_identity.json")
    assert fixture["evaluation_rules_hash"] == evaluation_identity()
    assert fixture["corpus_sha256"] == load_table_corpus(CORPUS)[1]
    assert fixture["resources"] == resources()
    for relative, digest in fixture["frozen_6c_files"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize(
    "mutation", ["source_span", "source_text", "pdf_bytes", "visual_offsets", "missing_span"]
)
def test_exact_gold_occurrences_and_original_pdf_are_verified(tmp_path, mutation):
    root = tmp_path / "corpus"
    shutil.copytree(CORPUS.parent, root)
    raw = read_json(root / "corpus.json")
    if mutation == "source_span":
        raw["cases"][0]["tables"][0]["span"] = [1, 20]
    elif mutation == "missing_span":
        raw["cases"][0]["tables"][0]["cells"][0]["span"] = None
    elif mutation == "source_text":
        raw["cases"][0]["tables"][0]["cells"][0]["text"] = "invented source cell"
    elif mutation == "pdf_bytes":
        (root / "sources/positioned_schedule.pdf").write_bytes(b"changed")
    else:
        case = next(c for c in raw["cases"] if c["id"] == "breaker_visual")
        case["tables"][0]["cells"][0]["span"] = [0, 9]
    (root / "corpus.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        load_table_corpus(root / "corpus.json")


def test_pdf_gold_uses_actual_processor_artifacts_without_claiming_native_grid_proof():
    from powerforge_document_model import DEFAULT_PROFILE
    from powerforge_document_processing.rendering import open_rendered_pages

    corpus, _ = load_table_corpus(CORPUS)
    native = next(c for c in corpus.cases if c.id == "pdf_native_unresolved")
    hybrid = next(c for c in corpus.cases if c.id == "pdf_hybrid")
    with open_rendered_pages(
        CORPUS.parent / hybrid.source_document.path, "pdf", DEFAULT_PROFILE, 600_000_000, 1000
    ) as pages:
        page = list(pages)[0]
    assert "|" not in page.native_text and "\t" not in page.native_text
    for source in hybrid.sources:
        data = page.native_text.encode() if source.role == "native_text" else page.analysis_png
        assert hashlib.sha256(data).hexdigest() == source.sha256
    rec = read_json(RECORDINGS)["cases"]
    _, native_outputs, errors = replay(native, CORPUS.parent, rec[native.id])
    assert not errors
    assert native_outputs[0].tables[0].table_kind == "UNCLASSIFIED"
    assert all(c.mapping_status == "UNMAPPED" for c in native_outputs[1].candidates)
    # Real engineering gold stays mapped: conservative inability to prove PDF
    # relationships costs recall, instead of changing the expected source meaning.
    assert all(c.status == "MAPPED" for c in native.claims)
    native_score = evaluate(CORPUS, RECORDINGS, [native.id])
    assert native_score["metrics"]["normalized_value_correctness"]["numerator"] == 0
    assert native_score["metrics"]["orientation_correctness"]["numerator"] == 0
    _, hybrid_outputs, errors = replay(hybrid, CORPUS.parent, rec[hybrid.id])
    assert not errors
    assert all(c.mapping_status == "MAPPED" for c in hybrid_outputs[1].candidates)
    assert (
        hybrid_outputs[0].tables[0].layout.metadata["reliability"]["structure_basis"]
        == "VISUAL_REPORTED"
    )


def test_cli_has_no_network_database_sdk_or_worker_imports(tmp_path):
    script = f"""
import builtins
original = builtins.__import__
blocked = {{'sqlalchemy','openai','extraction_worker','celery','fastapi','boto3'}}
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('Unexpected infrastructure import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from powerforge_extraction.table_eval import main
main(['--corpus', {str(CORPUS)!r}, '--case', 'no_table'])
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["case_count"] == 1
    out = tmp_path / "report.json"
    main(["--corpus", str(CORPUS), "--case", "no_table", "--output", str(out)])
    assert json.loads(out.read_text())["case_count"] == 1
    with pytest.raises(SystemExit):
        main(["--corpus", str(CORPUS), "--live"])
    with pytest.raises(SystemExit, match="Table evaluation failed"):
        main(["--corpus", str(tmp_path / "absent.json")])
