"""Versioned document taxonomy. The live DocumentClassification enum is unchanged."""

from __future__ import annotations

from powerforge_document_model import DocumentClassification

TAXONOMY_VERSION = "document-taxonomy-v2"
MIXED_DOCUMENT = "MIXED_DOCUMENT"

# UNKNOWN: not enough evidence to choose a class.
# OTHER: the document is understood, and no defined class fits it well.
# MIXED_DOCUMENT: several substantive sections belong to different classes.
# A cover, title, contents, or notes page plus one substantive class is not mixed.
TYPE_DEFINITIONS: dict[str, str] = {
    "UNKNOWN": "There is not enough evidence to confidently determine the class.",
    "OTHER": (
        "There is enough evidence to understand the document, but no defined class fits it well."
    ),
    "MIXED_DOCUMENT": (
        "The document contains multiple substantive sections belonging to different classes."
    ),
}

_LIVE_TYPES = tuple(member.value for member in DocumentClassification)
DOCUMENT_TYPES: tuple[str, ...] = (
    _LIVE_TYPES if MIXED_DOCUMENT in _LIVE_TYPES else _LIVE_TYPES + (MIXED_DOCUMENT,)
)
PAGE_TYPES: tuple[str, ...] = tuple(value for value in DOCUMENT_TYPES if value != MIXED_DOCUMENT)


class InvalidPageType(ValueError):
    """A page prediction used a class that is not in the page taxonomy."""


def require_page_type(value: str) -> str:
    """Return ``value`` when it is a page class. MIXED_DOCUMENT is rejected."""
    if value not in PAGE_TYPES:
        raise InvalidPageType(f"{value} is not a page classification")
    return value
