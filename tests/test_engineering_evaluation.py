"""Closed-corpus measurements and sensitivity controls, not assertions of model quality."""

import copy
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from powerforge_extraction.eval import evaluate, main
from powerforge_extraction.evaluation import load_corpus, read_json, replay, sources_for
from powerforge_extraction.evaluation_scoring import score_case
from powerforge_provenance.locations import Region

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals/extraction/v1/corpus.json"
RECORDINGS = CORPUS.parent / "scripted.json"


def snapshot(case_id):
    corpus, _ = load_corpus(CORPUS)
    case = next(c for c in corpus.cases if c.id == case_id)
    sources, outputs, errors = replay(case, CORPUS.parent, read_json(RECORDINGS)["cases"][case_id])
    assert not errors
    return case, sources, outputs


def changed(outputs, predicate, changes):
    return [
        output.model_copy(
            update={
                "candidates": [
                    c.model_copy(update=changes) if predicate(c) else c for c in output.candidates
                ]
            }
        )
        for output in outputs
    ]


def test_corpus_and_scripted_baseline_have_independent_explicit_denominators():
    corpus, digest = load_corpus(CORPUS)
    assert len(corpus.cases) == 15 and sum(len(c.expected) for c in corpus.cases) == 50
    assert {"transformer", "lv_breaker", "cable", "utility", "negative", "ambiguous"} <= {
        c.family for c in corpus.cases
    }
    result = evaluate(CORPUS, RECORDINGS)
    assert result["provenance"] == "SCRIPTED_MOCK" and not result["live_model_quality_measured"]
    assert result["corpus_sha256"] == digest
    assert result["metrics"]["equipment_recall"] == {
        "numerator": 14,
        "denominator": 16,
        "rate": 0.875,
    }
    assert result["metrics"]["normalized_value_correctness"]["denominator"] == 24
    assert result["metrics"]["unmapped_retention"]["denominator"] == 8
    assert result["metrics"]["invalid_retention"]["denominator"] == 2
    assert result["metrics"]["false_candidate_rate"] == {
        "numerator": 0,
        "denominator": 48,
        "rate": 0.0,
    }
    assert result["rejections"] == {"rejected_source_fields": 1, "detached_associations": 4}


@pytest.mark.parametrize(
    "case_id",
    [
        "transformer",
        "breaker",
        "cable",
        "utility",
        "isolated_unicode",
        "unknown_equipment",
        "repeated_tags",
        "missed_colon_header",
        "borrowed_tag",
        "no_equipment",
        "qualifiers",
        "invalid_values",
        "tagless_visual",
        "breaker_visual",
        "hybrid_conflict",
    ],
)
def test_all_curated_cases_replay_without_hidden_provider_calls(case_id):
    case, sources, outputs = snapshot(case_id)
    scored = score_case(case, sources, outputs)
    assert scored["counts"]["expected"] == len(case.expected)
    assert scored["counts"]["grounding_valid"] == scored["counts"]["predicted"]


@pytest.mark.parametrize(
    "changes",
    [{"numeric_value": Decimal("99")}, {"attribute_key": "primary_voltage"}, {"unit": "V"}],
)
def test_wrong_values_keys_and_units_reduce_correctness_without_changing_source_matching(changes):
    case, sources, outputs = snapshot("transformer")
    altered = changed(outputs, lambda c: c.attribute_key == "secondary_voltage", changes)
    scored = score_case(case, sources, altered)
    assert scored["counts"]["matched"] == 5 and scored["counts"]["false_candidates"] == 1
    assert scored["issues"][0]["gold_id"] == "g3"


def test_missing_duplicate_and_false_candidates_are_not_hidden_by_matching(tmp_path):
    recorded = read_json(RECORDINGS)
    recorded["cases"]["transformer"]["attributes"]["attributes"].pop()
    duplicate = copy.deepcopy(recorded["cases"]["breaker"]["attributes"]["attributes"][0])
    duplicate["local_ref"] = "duplicate"
    recorded["cases"]["breaker"]["attributes"]["attributes"].append(duplicate)
    path = tmp_path / "recorded.json"
    path.write_text(json.dumps(recorded))
    result = evaluate(CORPUS, path)
    assert result["counts"]["detected_attributes"] == 33
    assert result["metrics"]["false_candidate_rate"]["numerator"] == 1
    assert result["metrics"]["normalized_value_correctness"]["numerator"] == 23


def test_a_verified_native_fragment_matches_its_full_gold_field_without_using_the_proposed_key():
    corpus, _ = load_corpus(CORPUS)
    case = next(c for c in corpus.cases if c.id == "transformer")
    recorded = read_json(RECORDINGS)["cases"][case.id]
    item = recorded["attributes"]["attributes"][2]
    item["raw_expression"] = "600 V"  # Exact label remains in the verified full-line evidence.
    sources, outputs, failures = replay(case, CORPUS.parent, recorded)
    assert not failures
    scored = score_case(case, sources, outputs)
    assert scored["counts"]["matched"] == 5 and scored["counts"]["value_correct"] == 4


def test_wrong_repeated_tag_association_and_merged_groups_are_scored_as_errors():
    case, sources, outputs = snapshot("repeated_tags")
    eqs = outputs[0].candidates
    first = next(c for c in eqs if c.diagnostics["source_scope"][0] == 0)
    altered = changed(
        outputs,
        lambda c: c.raw_value == "690",
        {"equipment_mention_candidate_id": first.id, "source_group_id": first.source_group_id},
    )
    scored = score_case(case, sources, altered)
    assert scored["counts"]["association_correct"] == 1 and scored["counts"]["value_correct"] == 1
    merged = changed(
        outputs, lambda c: c.kind == "EQUIPMENT_MENTION", {"source_group_id": first.source_group_id}
    )
    assert score_case(case, sources, merged)["counts"]["separate_group_pairs"] == 0


def test_bad_duplicate_grounding_cannot_displace_the_correct_source_occurrence():
    case, sources, outputs = snapshot("repeated_tags")
    eq_output = outputs[0]
    altered_evidence = [
        e.model_copy(update={"text_start": e.text_start + 1}) if e.text_start > 0 else e
        for e in eq_output.evidence
    ]
    altered = eq_output.model_copy(update={"evidence": altered_evidence})
    counts = score_case(case, sources, [altered, outputs[1]])["counts"]
    assert counts["equipment_correct"] == 1 and counts["matched"] == 4
    assert counts["association_correct"] == 1


@pytest.mark.parametrize("failure", ["foreign_artifact", "offset", "text_verified"])
def test_grounding_checks_are_independent_of_mapping_and_provider_assertions(failure):
    case, sources, outputs = snapshot("isolated_unicode")
    output = outputs[1]
    first = output.evidence[0]
    if failure == "foreign_artifact":
        first = first.model_copy(
            update={"location": first.location.model_copy(update={"page_artifact_id": uuid4()})}
        )
    elif failure == "offset":
        first = first.model_copy(update={"text_start": first.text_start + 1})
    else:
        output = output.model_copy(
            update={
                "candidates": [
                    c.model_copy(update={"diagnostics": {**c.diagnostics, "text_verified": False}})
                    for c in output.candidates
                ]
            }
        )
    output = output.model_copy(update={"evidence": [first, *output.evidence[1:]]})
    assert score_case(case, sources, [outputs[0], output])["counts"]["grounding_valid"] < 3


def test_visual_page_markers_do_not_receive_credit_for_invented_geometry():
    case, sources, outputs = snapshot("tagless_visual")
    first = outputs[0].evidence[0]
    forged = first.model_copy(
        update={
            "location": first.location.model_copy(
                update={"region": Region(x=0, y=0, width=1, height=1)}
            )
        }
    )
    altered = outputs[0].model_copy(update={"evidence": [forged]})
    assert score_case(case, sources, [altered, outputs[1]])["counts"]["grounding_valid"] == 2


def test_zero_denominators_are_unknown_and_silent_dataset_shrinkage_is_rejected(tmp_path):
    result = evaluate(CORPUS, RECORDINGS, ["no_equipment"])
    assert result["metrics"]["equipment_precision"]["rate"] is None
    assert result["metrics"]["equipment_recall"]["rate"] is None
    recorded = read_json(RECORDINGS)
    del recorded["cases"]["no_equipment"]
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(recorded))
    with pytest.raises(ValueError, match="Missing"):
        evaluate(CORPUS, path)


def test_recording_claim_of_live_origin_does_not_become_measured_live_quality(tmp_path):
    recorded = read_json(RECORDINGS)
    recorded["provenance"] = "LIVE_OPENAI"
    path = tmp_path / "claimed-live.json"
    path.write_text(json.dumps(recorded))
    result = evaluate(CORPUS, path)
    assert (
        result["provenance"] == "UNVERIFIED_RECORDING" and not result["live_model_quality_measured"]
    )


@pytest.mark.parametrize("stage", ["equipment", "attributes"])
def test_schema_failure_retains_missing_gold_in_denominators(tmp_path, stage):
    recorded = read_json(RECORDINGS)
    recorded["cases"]["transformer"][stage]["overflowed"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(recorded))
    result = evaluate(CORPUS, path, ["transformer"])
    assert result["counts"]["expected"] == 5
    assert result["cases"][0]["stage_failures"]
    assert result["counts"]["predicted"] == (0 if stage == "equipment" else 1)


def test_source_and_resource_tampering_and_path_escape_are_rejected(tmp_path):
    recorded = read_json(RECORDINGS)
    recorded["resources"]["manifest"] = "unavailable"
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(recorded))
    with pytest.raises(ValueError, match="identity"):
        evaluate(CORPUS, path)
    corpus, _ = load_corpus(CORPUS)
    case = corpus.cases[0].model_copy(deep=True)
    case.sources[0].path = "../private.txt"
    with pytest.raises(ValueError, match="inside"):
        sources_for(case, CORPUS.parent)
    case.sources[0].path = corpus.cases[0].sources[0].path
    case.sources[0].sha256 = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        sources_for(case, CORPUS.parent)


def test_offline_command_imports_no_sdk_db_or_broker_and_live_is_explicit():
    script = f"""
import builtins
original = builtins.__import__
blocked = {{'sqlalchemy','openai','extraction_worker','celery','fastapi','boto3'}}
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('Unexpected infrastructure import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from powerforge_extraction.eval import main
main(['--corpus', {str(CORPUS)!r}, '--case', 'no_equipment'])
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["case_count"] == 1
    with pytest.raises(SystemExit, match="Evaluation failed"):
        main(["--corpus", str(CORPUS), "--live"])
    assert "evals/extraction/private/" in (ROOT / ".gitignore").read_text()


@pytest.mark.parametrize("case_id", ["tagless_visual", "breaker_visual", "hybrid_conflict"])
def test_png_fixtures_retain_exact_approved_bytes_through_the_real_processor(case_id):
    import hashlib

    from powerforge_document_model import DEFAULT_PROFILE
    from powerforge_document_processing.rendering import open_rendered_pages

    corpus, _ = load_corpus(CORPUS)
    case = next(c for c in corpus.cases if c.id == case_id)
    item = next(s for s in case.sources if s.role == "analysis_image")
    with open_rendered_pages(
        CORPUS.parent / item.path, "png", DEFAULT_PROFILE, 600_000_000, 1000
    ) as pages:
        page = list(pages)[0]
    assert page.native_text is None
    assert hashlib.sha256(page.analysis_png).hexdigest() == item.sha256


@pytest.mark.parametrize("enabled", [False, True])
def test_missing_live_controls_stop_before_database_or_provider_setup(monkeypatch, enabled):
    from extraction_worker import evaluation_live
    from powerforge_shared.config import Settings

    monkeypatch.setattr(
        evaluation_live,
        "get_settings",
        lambda: Settings(_env_file=None, extraction_external_enabled=enabled, openai_api_key=None),
    )
    monkeypatch.setattr(
        evaluation_live,
        "create_engine",
        lambda *args, **kwargs: pytest.fail("Database setup before explicit live credentials"),
    )
    with pytest.raises(ValueError, match="credentials"):
        evaluation_live.evaluate_live(
            CORPUS,
            Path("unused.json"),
            approved_digest=load_corpus(CORPUS)[1],
            selected={"transformer"},
            max_calls=2,
            wait_seconds=1,
        )
