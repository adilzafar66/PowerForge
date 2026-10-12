"""Deterministic classifier identity.

A changed prompt, taxonomy, or processing run is a new identity.
"""

from __future__ import annotations

from powerforge_document_classification.taxonomy import TAXONOMY_VERSION
from powerforge_document_model.profile import hash_material_fields

CLASSIFIER_VERSION = "1"


def classifier_identity_hash(
    *,
    provider: str,
    model: str,
    processing_run_id: str,
    prompt_version: str,
    sampling_profile_hash: str,
    taxonomy_version: str = TAXONOMY_VERSION,
    classifier_version: str = CLASSIFIER_VERSION,
) -> str:
    """SHA-256 of the fields that must match before a completed run can be reused."""
    return hash_material_fields(
        {
            "provider": provider,
            "model": model,
            "processing_run_id": processing_run_id,
            "classifier_version": classifier_version,
            "taxonomy_version": taxonomy_version,
            "prompt_version": prompt_version,
            "sampling_profile_hash": sampling_profile_hash,
        }
    )
