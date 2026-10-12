"""Build bounded classification requests from one completed processing run.

Reads thumbnail and native-text artifacts only. The original file is never opened.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from powerforge_ai.providers import (
    ClassificationImageInput,
    ClassificationTextExcerpt,
    ClassifyDocumentRequest,
    ClassifyPageInput,
    ClassifyPagesRequest,
)
from powerforge_document_classification.errors import ClassificationErrorCode
from powerforge_document_classification.profile import ClassificationProfile
from powerforge_document_classification.prompts import (
    document_classifier_prompt,
    page_classifier_prompt,
)
from powerforge_document_classification.sampling import sample_page_numbers
from powerforge_document_classification.taxonomy import DOCUMENT_TYPES, PAGE_TYPES
from powerforge_document_model import PageArtifactType
from powerforge_document_processing.models import Document, DocumentPage, PageArtifact
from powerforge_document_processing.storage.base import ObjectNotFound, ObjectStorage


class ClassificationAssemblyError(Exception):
    """Input or artifact problem found before a provider result can be stored."""

    def __init__(self, code: ClassificationErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


def load_page_set(
    session: Session,
    document_id: object,
    pages_total: int | None,
) -> list[DocumentPage]:
    """Return pages 1..pages_total. Higher page numbers are ignored."""
    if pages_total is None or pages_total < 1:
        raise ClassificationAssemblyError(ClassificationErrorCode.CLASSIFICATION_INPUT_ERROR)
    pages = list(
        session.scalars(
            select(DocumentPage)
            .where(
                DocumentPage.document_id == document_id,
                DocumentPage.page_number >= 1,
                DocumentPage.page_number <= pages_total,
            )
            .order_by(DocumentPage.page_number)
        ).all()
    )
    expected = list(range(1, pages_total + 1))
    if [page.page_number for page in pages] != expected:
        raise ClassificationAssemblyError(ClassificationErrorCode.CLASSIFICATION_INPUT_ERROR)
    return pages


def build_document_request(
    session: Session,
    storage: ObjectStorage,
    document: Document,
    processing_run_id: object,
    pages: list[DocumentPage],
    profile: ClassificationProfile,
) -> ClassifyDocumentRequest:
    """Sample images and text. A missing sampled thumbnail stops classification."""
    by_number = {page.page_number: page for page in pages}
    page_count = len(pages)
    image_numbers = sample_page_numbers(page_count, profile.document_image_sample_count)
    text_numbers = sample_page_numbers(page_count, profile.document_text_sample_count)
    images = [
        _thumbnail(session, storage, processing_run_id, by_number[number])
        for number in image_numbers
    ]
    excerpts = [
        ClassificationTextExcerpt(
            page_number=number,
            text=_native_text(
                session,
                storage,
                processing_run_id,
                by_number[number],
                profile.max_text_chars_per_page,
            ),
        )
        for number in text_numbers
    ]
    return ClassifyDocumentRequest(
        filename=document.original_filename,
        extension=document.file_extension,
        page_count=page_count,
        text_excerpts=excerpts,
        images=images,
        allowed_types=DOCUMENT_TYPES,
        instructions=document_classifier_prompt(),
    )


def build_page_batches(
    session: Session,
    storage: ObjectStorage,
    document: Document,
    processing_run_id: object,
    pages: list[DocumentPage],
    profile: ClassificationProfile,
) -> list[ClassifyPagesRequest]:
    """One request per batch. Every page in the page set is included."""
    batch_size = profile.page_classification_batch_size
    if batch_size < 1:
        raise ClassificationAssemblyError(ClassificationErrorCode.CLASSIFICATION_INPUT_ERROR)
    prepared: list[ClassifyPageInput] = []
    for page in pages:
        prepared.append(
            ClassifyPageInput(
                page_number=page.page_number,
                text=_native_text(
                    session,
                    storage,
                    processing_run_id,
                    page,
                    profile.max_text_chars_per_page,
                ),
                image=_thumbnail(session, storage, processing_run_id, page),
            )
        )
    requests: list[ClassifyPagesRequest] = []
    for start in range(0, len(prepared), batch_size):
        chunk = prepared[start : start + batch_size]
        requests.append(
            ClassifyPagesRequest(
                filename=document.original_filename,
                extension=document.file_extension,
                pages=chunk,
                allowed_types=PAGE_TYPES,
                instructions=page_classifier_prompt(),
            )
        )
    return requests


def _artifact(
    session: Session,
    processing_run_id: object,
    page: DocumentPage,
    artifact_type: PageArtifactType,
) -> PageArtifact | None:
    return session.scalar(
        select(PageArtifact).where(
            PageArtifact.processing_run_id == processing_run_id,
            PageArtifact.document_page_id == page.id,
            PageArtifact.artifact_type == artifact_type,
        )
    )


def _read(storage: ObjectStorage, key: str) -> bytes:
    stream = storage.get(key)
    try:
        return stream.read()
    finally:
        stream.close()


def _thumbnail(
    session: Session,
    storage: ObjectStorage,
    processing_run_id: object,
    page: DocumentPage,
) -> ClassificationImageInput:
    artifact = _artifact(session, processing_run_id, page, PageArtifactType.THUMBNAIL)
    if artifact is None:
        raise ClassificationAssemblyError(ClassificationErrorCode.ARTIFACT_UNAVAILABLE)
    try:
        data = _read(storage, artifact.storage_key)
    except ObjectNotFound as exc:
        raise ClassificationAssemblyError(ClassificationErrorCode.ARTIFACT_UNAVAILABLE) from exc
    return ClassificationImageInput(
        page_number=page.page_number,
        mime_type=artifact.mime_type,
        data=data,
    )


def _native_text(
    session: Session,
    storage: ObjectStorage,
    processing_run_id: object,
    page: DocumentPage,
    limit: int,
) -> str:
    artifact = _artifact(session, processing_run_id, page, PageArtifactType.NATIVE_TEXT)
    if artifact is None:
        return ""
    try:
        data = _read(storage, artifact.storage_key)
    except ObjectNotFound:
        return ""
    return data.decode("utf-8", errors="replace")[:limit]
