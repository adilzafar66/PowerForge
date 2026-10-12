"""Document classification vocabulary and run orchestration.

Vocabulary modules stay free of SQLAlchemy. The service and input assembler
use the shared models and the object-storage port. This package does not
import FastAPI, Celery, or a vendor SDK.
"""

from powerforge_document_classification.errors import ClassificationErrorCode
from powerforge_document_classification.identity import CLASSIFIER_VERSION, classifier_identity_hash
from powerforge_document_classification.profile import (
    DEFAULT_CLASSIFICATION_PROFILE,
    SAMPLING_PROFILE_VERSION,
    ClassificationProfile,
    confidence_band,
)
from powerforge_document_classification.prompts import (
    document_classifier_prompt,
    document_classifier_v1,
    page_classifier_prompt,
    page_classifier_v1,
)
from powerforge_document_classification.sampling import sample_page_numbers
from powerforge_document_classification.taxonomy import (
    DOCUMENT_TYPES,
    MIXED_DOCUMENT,
    PAGE_TYPES,
    TAXONOMY_VERSION,
    TYPE_DEFINITIONS,
    InvalidPageType,
    require_page_type,
)

__all__ = [
    "CLASSIFIER_VERSION",
    "DEFAULT_CLASSIFICATION_PROFILE",
    "DOCUMENT_TYPES",
    "MIXED_DOCUMENT",
    "document_classifier_v1",
    "PAGE_TYPES",
    "SAMPLING_PROFILE_VERSION",
    "TAXONOMY_VERSION",
    "TYPE_DEFINITIONS",
    "ClassificationErrorCode",
    "ClassificationProfile",
    "InvalidPageType",
    "classifier_identity_hash",
    "confidence_band",
    "document_classifier_prompt",
    "page_classifier_prompt",
    "page_classifier_v1",
    "require_page_type",
    "sample_page_numbers",
]
