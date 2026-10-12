"""Offline classification evaluation. The fake provider needs no OpenAI key."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from powerforge_document_classification.eval import PageLabel, evaluate, load_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals" / "classification" / "example-manifest.json"

REPORT_KEYS = {
    "document_exact_match_accuracy",
    "per_class",
    "confusion_matrix",
    "top2_accuracy",
    "unknown_rate",
    "mixed_document_precision",
    "mixed_document_recall",
    "page_accuracy",
    "average_input_tokens",
    "average_output_tokens",
    "latency_ms",
}


def test_example_manifest_validates() -> None:
    manifest, files = load_manifest(MANIFEST)
    assert len(manifest.items) == 4
    assert len(files) == 4
    assert all(path.is_file() for path in files)
    mixed = next(item for item in manifest.items if item.expected_document_type == "MIXED_DOCUMENT")
    assert mixed.expected_page_types[0].expected_type == "ELECTRICAL_DRAWING"


def test_page_label_rejects_mixed_document() -> None:
    with pytest.raises(ValidationError):
        PageLabel(page_number=1, expected_type="MIXED_DOCUMENT")


def test_command_scores_fixtures_without_an_openai_key() -> None:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    code = (
        "from powerforge_document_classification.eval import main\n"
        f"main(['--manifest', {str(MANIFEST)!r}])\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert REPORT_KEYS <= report.keys()
    assert "estimated_cost_usd" not in report
    assert "estimated_cost_usd" not in completed.stdout
    assert report["document_exact_match_accuracy"] == 1.0
    assert report["page_accuracy"] == 1.0
    assert report["unknown_rate"] == 0.25
    assert set(report["latency_ms"]) == {"mean", "p50", "max"}
    single = report["per_class"]["SINGLE_LINE_DIAGRAM"]
    assert set(single) == {"precision", "recall", "f1"}


def test_evaluate_report_matches_the_command_keys() -> None:
    report = evaluate(MANIFEST)
    assert REPORT_KEYS <= report.keys()
    assert report["mixed_document_precision"] == 1.0
    assert report["mixed_document_recall"] == 1.0
    assert report["top2_accuracy"] == 1.0


def test_private_evaluation_documents_are_gitignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "evals/classification/private/" in ignored


def test_ci_does_not_run_the_evaluation_command() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "powerforge-eval-classification" not in workflow


def test_importing_eval_does_not_import_openai_or_the_extraction_worker() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    code = (
        "import powerforge_document_classification.eval\n"
        "import sys\n"
        "assert 'openai' not in sys.modules\n"
        "assert not any("
        "name == 'extraction_worker' or name.startswith('extraction_worker.') "
        "for name in sys.modules)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
