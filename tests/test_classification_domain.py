"""Phase 4 classification vocabulary. No database and no provider calls."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from powerforge_ai.providers import DocumentClassificationResult
from powerforge_document_classification import (
    DOCUMENT_TYPES,
    MIXED_DOCUMENT,
    PAGE_TYPES,
    TYPE_DEFINITIONS,
    ClassificationErrorCode,
    ClassificationProfile,
    InvalidPageType,
    classifier_identity_hash,
    confidence_band,
    document_classifier_prompt,
    page_classifier_prompt,
    require_page_type,
    sample_page_numbers,
)
from powerforge_document_model import DocumentClassification
from powerforge_document_model.profile import hash_material_fields

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORTS = frozenset({"fastapi", "celery", "boto3", "openai", "PIL", "fitz"})
SQLALCHEMY_ALLOWED = frozenset({"assembly.py", "service.py"})
PROCESSING_BOUNDARIES = frozenset(
    {
        "powerforge_document_processing.rendering",
        "powerforge_document_processing.enqueue",
        "powerforge_document_processing.processing",
    }
)
PACKAGE_ROOTS = (
    REPO_ROOT
    / "packages"
    / "document-classification"
    / "src"
    / "powerforge_document_classification",
    REPO_ROOT / "packages" / "ai" / "src" / "powerforge_ai",
)


def test_taxonomy_matches_the_live_enum() -> None:
    live = tuple(member.value for member in DocumentClassification)
    assert len(live) == 17
    assert MIXED_DOCUMENT in live
    assert live[live.index("OTHER") - 1] == MIXED_DOCUMENT
    assert live[-1] == "UNKNOWN"
    assert DOCUMENT_TYPES == live
    assert PAGE_TYPES == tuple(value for value in live if value != MIXED_DOCUMENT)
    assert len({DocumentClassification.UNKNOWN, DocumentClassification.OTHER, MIXED_DOCUMENT}) == 3
    assert set(TYPE_DEFINITIONS) == {"UNKNOWN", "OTHER", "MIXED_DOCUMENT"}


def test_page_taxonomy_rejects_mixed_document() -> None:
    with pytest.raises(InvalidPageType):
        require_page_type(MIXED_DOCUMENT)
    assert require_page_type("UNKNOWN") == "UNKNOWN"
    assert require_page_type("OTHER") == "OTHER"


def test_profile_hash_is_stable_and_ignores_key_order_and_version_label() -> None:
    profile = ClassificationProfile()
    assert profile.profile_hash == ClassificationProfile().profile_hash
    assert profile.profile_hash != ClassificationProfile(document_image_sample_count=6).profile_hash
    assert profile.profile_hash != ClassificationProfile(high_confidence_threshold=0.9).profile_hash
    assert profile.profile_hash == ClassificationProfile(profile_version="other-label").profile_hash
    fields = profile.material_fields()
    reversed_fields = dict(reversed(list(fields.items())))
    assert hash_material_fields(fields) == hash_material_fields(reversed_fields)
    assert profile.profile_hash == hash_material_fields(fields)


def test_identity_hash_changes_with_prompt_taxonomy_or_processing_run() -> None:
    shared = {
        "provider": "fake",
        "model": "gpt-6-luna",
        "processing_run_id": "run-1",
        "prompt_version": "document_classifier_v1",
        "sampling_profile_hash": "abc",
    }
    original = classifier_identity_hash(**shared)
    changed_prompt = classifier_identity_hash(
        **{**shared, "prompt_version": "document_classifier_v2"}
    )
    changed_taxonomy = classifier_identity_hash(
        **{**shared, "taxonomy_version": "document-taxonomy-v3"}
    )
    changed_run = classifier_identity_hash(**{**shared, "processing_run_id": "run-2"})
    assert len({original, changed_prompt, changed_taxonomy, changed_run}) == 4


def test_sampling_uses_every_page_when_the_document_is_small() -> None:
    assert sample_page_numbers(3, 5) == (1, 2, 3)


def test_sampling_of_a_large_document_includes_first_and_last_and_repeats() -> None:
    first = sample_page_numbers(18, 5)
    assert first[0] == 1
    assert first[-1] == 18
    assert first == tuple(sorted(set(first)))
    assert len(first) == 5
    assert sample_page_numbers(18, 5) == first


def test_confidence_bands_follow_the_profile_thresholds() -> None:
    assert confidence_band(0.59) == "LOW"
    assert confidence_band(0.60) == "MEDIUM"
    assert confidence_band(0.84) == "MEDIUM"
    assert confidence_band(0.85) == "HIGH"


def test_prompts_state_the_taxonomy_and_do_not_ask_for_engineering_facts() -> None:
    document = document_classifier_prompt()
    page = page_classifier_prompt()
    document_lower = document.lower()
    page_lower = page.lower()
    assert "untrusted" in document_lower
    assert "untrusted" in page_lower
    for value in DOCUMENT_TYPES:
        assert value in document
    for value in PAGE_TYPES:
        assert value in page
    assert "mixed_document is prohibited" in page_lower
    assert "rating" not in document_lower
    assert "rating" not in page_lower
    assert "topology" not in document_lower
    assert "topology" not in page_lower


def test_rationale_is_bounded_and_the_result_has_no_band() -> None:
    DocumentClassificationResult(
        predicted_type="OTHER",
        confidence_score=0.5,
        rationale="x" * 500,
    )
    with pytest.raises(ValidationError):
        DocumentClassificationResult(
            predicted_type="OTHER",
            confidence_score=0.5,
            rationale="x" * 501,
        )
    assert "confidence_band" not in DocumentClassificationResult.model_fields


def test_timeout_codes_stay_distinct() -> None:
    provider_timeout = ClassificationErrorCode.PROVIDER_TIMEOUT
    task_timeout = ClassificationErrorCode.CLASSIFICATION_TASK_TIMEOUT
    assert provider_timeout != task_timeout
    assert provider_timeout.value == "PROVIDER_TIMEOUT"
    assert task_timeout.value == "CLASSIFICATION_TASK_TIMEOUT"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return set(modules)


def test_classification_packages_do_not_import_frameworks_or_openai() -> None:
    for root in PACKAGE_ROOTS:
        for path in root.rglob("*.py"):
            imported = _imported_modules(path)
            overlap = {module.split(".", 1)[0] for module in imported} & FORBIDDEN_IMPORTS
            assert overlap == set(), f"{path} imports {sorted(overlap)}"
            if "sqlalchemy" in {module.split(".", 1)[0] for module in imported}:
                assert path.name in SQLALCHEMY_ALLOWED, f"{path} imports sqlalchemy"
            assert PROCESSING_BOUNDARIES.isdisjoint(imported), path
