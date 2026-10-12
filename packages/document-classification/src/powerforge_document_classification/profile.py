"""Versioned classification sampling profile. The hash identifies the inputs, not the label."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from powerforge_document_model.profile import hash_material_fields

SAMPLING_PROFILE_VERSION = "classification-default-v1"

_MATERIAL_FIELDS = (
    "document_image_sample_count",
    "document_text_sample_count",
    "max_text_chars_per_page",
    "page_classification_batch_size",
    "image_artifact_type",
    "image_detail",
    "high_confidence_threshold",
    "medium_confidence_threshold",
)


@dataclass(frozen=True, slots=True)
class ClassificationProfile:
    """One classification sampling configuration. The version label is not part of the hash."""

    document_image_sample_count: int = 5
    document_text_sample_count: int = 20
    max_text_chars_per_page: int = 2000
    page_classification_batch_size: int = 8
    image_artifact_type: str = "THUMBNAIL"
    image_detail: str = "low"
    high_confidence_threshold: float = 0.85
    medium_confidence_threshold: float = 0.60
    profile_version: str = SAMPLING_PROFILE_VERSION

    def material_fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _MATERIAL_FIELDS}

    @property
    def profile_hash(self) -> str:
        return hash_material_fields(self.material_fields())


DEFAULT_CLASSIFICATION_PROFILE = ClassificationProfile()


def confidence_band(score: float, profile: ClassificationProfile | None = None) -> str:
    """Derive HIGH, MEDIUM, or LOW from the numeric score. The model does not return a band."""
    chosen = profile if profile is not None else DEFAULT_CLASSIFICATION_PROFILE
    if score >= chosen.high_confidence_threshold:
        return "HIGH"
    if score >= chosen.medium_confidence_threshold:
        return "MEDIUM"
    return "LOW"
