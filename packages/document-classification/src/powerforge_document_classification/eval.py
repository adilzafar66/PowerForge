"""Score a labeled manifest against the classification provider.

Not a FastAPI route and not run by CI. The default provider is the filename
fake, which needs no database and no OpenAI key. ``--provider openai`` is the
only live path.
"""

from __future__ import annotations

import argparse
import importlib
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from powerforge_ai.providers import (
    ClassificationImageInput,
    ClassificationProvider,
    ClassificationTextExcerpt,
    ClassificationUsage,
    ClassifyDocumentRequest,
    ClassifyPageInput,
    ClassifyPagesRequest,
    DocumentClassificationResult,
)
from powerforge_document_classification.errors import ClassificationProviderError
from powerforge_document_classification.fake import FakeClassificationProvider
from powerforge_document_classification.profile import (
    DEFAULT_CLASSIFICATION_PROFILE,
    ClassificationProfile,
)
from powerforge_document_classification.prompts import (
    document_classifier_prompt,
    page_classifier_prompt,
)
from powerforge_document_classification.sampling import sample_page_numbers
from powerforge_document_classification.taxonomy import (
    DOCUMENT_TYPES,
    MIXED_DOCUMENT,
    PAGE_TYPES,
    require_page_type,
)
from powerforge_shared.config import Settings, get_settings

_UNKNOWN = "UNKNOWN"


class PageLabel(BaseModel):
    page_number: int = Field(ge=1)
    expected_type: str

    @field_validator("expected_type")
    @classmethod
    def _page_type(cls, value: str) -> str:
        return require_page_type(value)


class EvalItem(BaseModel):
    path: str = Field(min_length=1)
    expected_document_type: str
    expected_page_types: list[PageLabel] = Field(default_factory=list)

    @field_validator("expected_document_type")
    @classmethod
    def _document_type(cls, value: str) -> str:
        if value not in DOCUMENT_TYPES:
            raise ValueError(f"{value} is not a document classification")
        return value

    @model_validator(mode="after")
    def _unique_pages(self) -> EvalItem:
        numbers = [label.page_number for label in self.expected_page_types]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"{self.path} repeats a page number")
        return self


class EvalManifest(BaseModel):
    items: list[EvalItem] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class _DocumentScore:
    expected: str
    predicted: str
    top2: bool
    page_hits: int
    page_total: int
    input_tokens: int
    output_tokens: int
    latency_ms: int


def load_manifest(path: Path) -> tuple[EvalManifest, list[Path]]:
    """Validate the manifest and resolve each file next to it."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = EvalManifest.model_validate(payload)
    root = path.parent
    files: list[Path] = []
    for item in manifest.items:
        resolved = (root / item.path).resolve()
        if not resolved.is_file():
            raise ValueError(f"Evaluation file does not exist: {item.path}")
        files.append(resolved)
    return manifest, files


def evaluate(manifest_path: Path, *, provider_name: str = "fake") -> dict[str, Any]:
    """Classify every manifest item and return the quality report."""
    manifest, files = load_manifest(manifest_path)
    provider, settings = _provider(provider_name)
    profile = DEFAULT_CLASSIFICATION_PROFILE
    scores = [
        _score_item(item, file_path, provider, settings, profile)
        for item, file_path in zip(manifest.items, files, strict=True)
    ]
    return _report(scores)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Score classification quality for a labeled manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--provider", choices=("fake", "openai"), default="fake")
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.manifest, provider_name=args.provider)
    except (ValidationError, ValueError, json.JSONDecodeError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    text = json.dumps(report, indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(text)
        return
    args.output.write_text(text, encoding="utf-8")


def _provider(name: str) -> tuple[ClassificationProvider, Settings | None]:
    if name == "fake":
        return FakeClassificationProvider(), None
    if name == "openai":
        return _openai_provider()
    raise SystemExit(f"Unknown classification provider: {name}")


def _openai_provider() -> tuple[ClassificationProvider, Settings]:
    # Loaded by name so this package does not statically depend on the worker.
    try:
        module = importlib.import_module("extraction_worker.openai_classification")
    except ImportError as exc:
        raise SystemExit(
            "The extraction-worker package is required for --provider openai"
        ) from exc
    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is required when --provider openai")
    return module.OpenAIClassificationProvider(settings), settings


def _score_item(
    item: EvalItem,
    path: Path,
    provider: ClassificationProvider,
    settings: Settings | None,
    profile: ClassificationProfile,
) -> _DocumentScore:
    rendered = None if settings is None else _render(path, settings)
    page_count = len(rendered) if rendered is not None else _labeled_page_count(item)
    document_request = _document_request(path, page_count, rendered, profile)
    document_response = _call_document(provider, document_request)
    usages = [document_response.usage]
    result = document_response.result
    page_predictions: dict[int, str] = {}
    if _requires_pages(result, profile):
        batches = _page_batches(path, page_count, rendered, profile)
        for batch in batches:
            page_response = _call_pages(provider, batch)
            usages.append(page_response.usage)
            _record_pages(batch, page_response.pages, page_predictions)
    page_hits, page_total = _page_hits(item, page_predictions)
    return _DocumentScore(
        expected=item.expected_document_type,
        predicted=result.predicted_type,
        top2=_top2(item.expected_document_type, result),
        page_hits=page_hits,
        page_total=page_total,
        input_tokens=_tokens(usages, "input_tokens"),
        output_tokens=_tokens(usages, "output_tokens"),
        latency_ms=sum(usage.latency_ms for usage in usages),
    )


def _labeled_page_count(item: EvalItem) -> int:
    numbers = [label.page_number for label in item.expected_page_types]
    return max(numbers) if numbers else 1


def _render(path: Path, settings: Settings) -> list[Any]:
    # Loaded by name so the fake evaluation path does not depend on the renderer.
    from powerforge_document_model import DEFAULT_PROFILE

    rendering = importlib.import_module("powerforge_document_processing.rendering")
    extension = path.suffix.lstrip(".").lower()
    try:
        with rendering.open_rendered_pages(
            path,
            extension,
            DEFAULT_PROFILE,
            settings.max_image_pixels,
            settings.max_processing_pages,
        ) as source:
            return list(source)
    except (rendering.RenderingFailed, OSError) as exc:
        raise SystemExit(f"Could not render {path.name} for classification") from exc


def _document_request(
    path: Path,
    page_count: int,
    rendered: list[Any] | None,
    profile: ClassificationProfile,
) -> ClassifyDocumentRequest:
    images: list[ClassificationImageInput] = []
    excerpts: list[ClassificationTextExcerpt] = []
    if rendered is not None:
        by_number = {page.page_number: page for page in rendered}
        mime = _thumbnail_mime()
        for number in sample_page_numbers(page_count, profile.document_image_sample_count):
            images.append(
                ClassificationImageInput(
                    page_number=number,
                    mime_type=mime,
                    data=by_number[number].thumbnail,
                )
            )
        for number in sample_page_numbers(page_count, profile.document_text_sample_count):
            text = by_number[number].native_text or ""
            excerpts.append(
                ClassificationTextExcerpt(
                    page_number=number,
                    text=text[: profile.max_text_chars_per_page],
                )
            )
    return ClassifyDocumentRequest(
        filename=path.name,
        extension=path.suffix.lstrip(".").lower(),
        page_count=page_count,
        text_excerpts=excerpts,
        images=images,
        allowed_types=DOCUMENT_TYPES,
        instructions=document_classifier_prompt(),
    )


def _page_batches(
    path: Path,
    page_count: int,
    rendered: list[Any] | None,
    profile: ClassificationProfile,
) -> list[ClassifyPagesRequest]:
    by_number = {} if rendered is None else {page.page_number: page for page in rendered}
    mime = "" if rendered is None else _thumbnail_mime()
    prepared: list[ClassifyPageInput] = []
    for number in range(1, page_count + 1):
        page = by_number.get(number)
        image = None
        text = None
        if page is not None:
            image = ClassificationImageInput(
                page_number=number,
                mime_type=mime,
                data=page.thumbnail,
            )
            text = (page.native_text or "")[: profile.max_text_chars_per_page]
        prepared.append(ClassifyPageInput(page_number=number, text=text, image=image))
    requests: list[ClassifyPagesRequest] = []
    batch_size = profile.page_classification_batch_size
    for start in range(0, len(prepared), batch_size):
        requests.append(
            ClassifyPagesRequest(
                filename=path.name,
                extension=path.suffix.lstrip(".").lower(),
                pages=prepared[start : start + batch_size],
                allowed_types=PAGE_TYPES,
                instructions=page_classifier_prompt(),
            )
        )
    return requests


def _thumbnail_mime() -> str:
    from powerforge_document_model import DEFAULT_PROFILE

    if DEFAULT_PROFILE.thumbnail_format == "png":
        return "image/png"
    if DEFAULT_PROFILE.thumbnail_format == "jpeg":
        return "image/jpeg"
    return "image/webp"


def _requires_pages(result: DocumentClassificationResult, profile: ClassificationProfile) -> bool:
    """Match the service rule: mixed, unknown, or below the high-confidence threshold."""
    if result.predicted_type in {MIXED_DOCUMENT, _UNKNOWN}:
        return True
    return result.confidence_score < profile.high_confidence_threshold


def _call_document(provider: ClassificationProvider, request: ClassifyDocumentRequest) -> Any:
    try:
        return provider.classify_document(request)
    except ClassificationProviderError as exc:
        raise SystemExit(f"Classification failed: {exc.code.value}") from exc


def _call_pages(provider: ClassificationProvider, request: ClassifyPagesRequest) -> Any:
    try:
        return provider.classify_pages(request)
    except ClassificationProviderError as exc:
        raise SystemExit(f"Classification failed: {exc.code.value}") from exc


def _record_pages(batch: ClassifyPagesRequest, pages: list[Any], found: dict[int, str]) -> None:
    expected = {page.page_number for page in batch.pages}
    seen: set[int] = set()
    for item in pages:
        if item.page_number not in expected or item.page_number in seen:
            raise SystemExit("Classification failed: INVALID_PROVIDER_RESPONSE")
        try:
            require_page_type(item.predicted_type)
        except ValueError as exc:
            raise SystemExit("Classification failed: INVALID_PROVIDER_RESPONSE") from exc
        seen.add(item.page_number)
        found[item.page_number] = item.predicted_type
    if seen != expected:
        raise SystemExit("Classification failed: INVALID_PROVIDER_RESPONSE")


def _page_hits(item: EvalItem, predicted: dict[int, str]) -> tuple[int, int]:
    hits = 0
    for label in item.expected_page_types:
        if predicted.get(label.page_number) == label.expected_type:
            hits += 1
    return hits, len(item.expected_page_types)


def _top2(expected: str, result: DocumentClassificationResult) -> bool:
    candidates = [result.predicted_type]
    if result.alternatives:
        candidates.append(result.alternatives[0].type)
    return expected in candidates


def _tokens(usages: list[ClassificationUsage], field: str) -> int:
    total = 0
    for usage in usages:
        value = getattr(usage, field)
        total += 0 if value is None else value
    return total


def _report(scores: list[_DocumentScore]) -> dict[str, Any]:
    count = len(scores)
    expected = [score.expected for score in scores]
    predicted = [score.predicted for score in scores]
    labels = sorted(set(expected) | set(predicted))
    page_hits = sum(score.page_hits for score in scores)
    page_total = sum(score.page_total for score in scores)
    latencies = [score.latency_ms for score in scores]
    mixed_precision, mixed_recall, _mixed_f1 = _prf(MIXED_DOCUMENT, expected, predicted)
    return {
        "document_exact_match_accuracy": sum(
            score.expected == score.predicted for score in scores
        )
        / count,
        "per_class": {
            label: _class_metrics(label, expected, predicted) for label in labels
        },
        "confusion_matrix": _confusion(expected, predicted),
        "top2_accuracy": sum(score.top2 for score in scores) / count,
        "unknown_rate": predicted.count(_UNKNOWN) / count,
        "mixed_document_precision": mixed_precision,
        "mixed_document_recall": mixed_recall,
        "page_accuracy": None if page_total == 0 else page_hits / page_total,
        "average_input_tokens": sum(score.input_tokens for score in scores) / count,
        "average_output_tokens": sum(score.output_tokens for score in scores) / count,
        "latency_ms": {
            "mean": statistics.fmean(latencies),
            "p50": statistics.median(latencies),
            "max": max(latencies),
        },
    }


def _class_metrics(label: str, expected: list[str], predicted: list[str]) -> dict[str, float]:
    precision, recall, f1 = _prf(label, expected, predicted)
    return {"precision": precision, "recall": recall, "f1": f1}


def _prf(label: str, expected: list[str], predicted: list[str]) -> tuple[float, float, float]:
    true_positive = false_positive = false_negative = 0
    for wanted, got in zip(expected, predicted, strict=True):
        if wanted == label and got == label:
            true_positive += 1
        elif got == label:
            false_positive += 1
        elif wanted == label:
            false_negative += 1
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1


def _confusion(expected: list[str], predicted: list[str]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for wanted, got in zip(expected, predicted, strict=True):
        row = matrix.setdefault(wanted, {})
        row[got] = row.get(got, 0) + 1
    return matrix


if __name__ == "__main__":
    main()
