"""Load versioned classifier prompts. Editing a prompt requires a new version id."""

from __future__ import annotations

from importlib.resources import files

document_classifier_v1 = "document_classifier_v1"
page_classifier_v1 = "page_classifier_v1"


def load_prompt(filename: str) -> str:
    """Return the text of one prompt file shipped inside this package."""
    return files("powerforge_document_classification").joinpath("prompts", filename).read_text(
        encoding="utf-8"
    )


def document_classifier_prompt() -> str:
    return load_prompt(f"{document_classifier_v1}.txt")


def page_classifier_prompt() -> str:
    return load_prompt(f"{page_classifier_v1}.txt")
