"""Read-only planning for the fixed Phase 6F preparation and extraction workflow."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import and_, select

from powerforge_document_model import DEFAULT_PROFILE
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
    RevisionDocument,
)
from powerforge_extraction.enriched_sources import selected_snapshot
from powerforge_extraction.enrichment_models import SourceEnrichmentPageResult
from powerforge_extraction.enrichment_service import preparation_identity, source_snapshot
from powerforge_extraction.errors import ExtractionError
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.layout_models import SourceSpatialResult
from powerforge_extraction.layout_profiles import layout_profile
from powerforge_extraction.layout_sources import successful_prepared
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.phase6r_profile import phase6r_profile

Mode = Literal["ensure", "reextract"]
MAX_DOCUMENTS = 50
CONSENT_VERSION = "external-openai-v1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSelection(Contract):
    revision_document_id: UUID
    processing_run_id: UUID
    pages: list[StrictInt] = Field(min_length=1, max_length=50)
    force_ocr_pages: list[StrictInt] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def check_pages(self):
        if (
            self.pages != sorted(set(self.pages))
            or self.pages[0] < 1
            or self.force_ocr_pages != sorted(set(self.force_ocr_pages))
            or not set(self.force_ocr_pages) <= set(self.pages)
        ):
            raise ValueError(
                "Select distinct ascending pages and limit OCR override to those pages"
            )
        return self


class OperationSelection(Contract):
    documents: list[SourceSelection] = Field(min_length=1, max_length=MAX_DOCUMENTS)
    mode: Mode = "ensure"

    @model_validator(mode="after")
    def normalize(self):
        if len({doc.revision_document_id for doc in self.documents}) != len(self.documents):
            raise ValueError("Select each document once")
        self.documents.sort(key=lambda doc: doc.revision_document_id)
        return self


class PlannedPage(Contract):
    page_number: int
    document_page_id: UUID
    preparation_hash: str
    prepared_result_id: UUID | None = None
    spatial_result_id: UUID | None = None


class PlannedDocument(Contract):
    selection: SourceSelection
    document_id: UUID
    pages: list[PlannedPage]


class OperationPolicy(Contract):
    consent_version: Literal["external-openai-v1"] = CONSENT_VERSION
    mode: Mode
    profile_hash: str
    layout_profile_hash: str
    provider_admissions: int
    ocr_attempts: int
    parallel_documents: int


@dataclass(frozen=True)
class Preview:
    documents: list[PlannedDocument]
    policy: OperationPolicy | None
    items: list[dict]
    profile: dict
    errors: list[str]

    @property
    def review_hash(self):
        if self.errors or any(item["error"] for item in self.items) or self.policy is None:
            return None
        return identity_hash(
            {
                "policy": self.policy.model_dump(mode="json"),
                "documents": [item.model_dump(mode="json") for item in self.documents],
            }
        )

    def response(self):
        return {
            "items": self.items,
            "errors": self.errors,
            "profile": self.profile,
            "review_hash": self.review_hash,
            "planned_runs": len(self.items),
            "provider_admissions": self.policy.provider_admissions if self.policy else None,
            "ocr_attempts": self.policy.ocr_attempts if self.policy else None,
            "parallel_documents": self.policy.parallel_documents if self.policy else None,
            "consent_version": CONSENT_VERSION,
        }


def scoped_sources(session, project_id, revision_id, ids):
    """Same active processing profile as Documents. Missing IDs never expose foreign metadata."""
    processing = DocumentProcessingRun
    rows = session.execute(
        select(RevisionDocument, Document, processing)
        .join(Document, Document.id == RevisionDocument.document_id)
        .outerjoin(
            processing,
            and_(
                processing.document_id == Document.id,
                processing.processor_version == DEFAULT_PROFILE.processor_version,
                processing.profile_hash == DEFAULT_PROFILE.profile_hash,
                processing.status == "COMPLETED",
            ),
        )
        .where(
            RevisionDocument.project_id == project_id,
            RevisionDocument.revision_id == revision_id,
            RevisionDocument.id.in_(ids),
            Document.project_id == project_id,
        )
    )
    return {row[0].id: tuple(row) for row in rows}


def source_error(source, settings):
    if source is None:
        return "Source is unavailable in this revision."
    association, document, processing = source
    if association.status != "INCLUDED":
        return "Document was removed from this revision."
    if processing is None:
        return "Source processing must complete first."
    if document.size_bytes > settings.extraction_max_document_bytes:
        return "The document exceeds the configured size limit."
    return None


def source_options(session, settings, project_id, revision_id, ids):
    sources = scoped_sources(session, project_id, revision_id, ids)
    items = []
    for id_ in ids:
        source = sources.get(id_)
        error = source_error(source, settings)
        processing = source[2] if source and not error else None
        pages = (
            list(
                session.scalars(
                    select(DocumentPage.page_number)
                    .join(PageArtifact, PageArtifact.document_page_id == DocumentPage.id)
                    .where(
                        PageArtifact.processing_run_id == processing.id,
                        PageArtifact.artifact_type == "ANALYSIS_IMAGE",
                    )
                    .order_by(DocumentPage.page_number)
                )
            )
            if processing
            else []
        )
        items.append(
            {
                "revision_document_id": id_,
                "filename": source[1].original_filename if source else None,
                "processing_run_id": processing.id if processing else None,
                "page_count": processing.pages_total if processing else None,
                "available_pages": pages,
                "error": error or (None if pages else "No processed page images are available."),
            }
        )
    return {
        "items": items,
        "max_pages_per_document": min(50, settings.extraction_max_pages),
        "max_documents": settings.extraction_operation_max_documents,
        "max_pages": settings.extraction_operation_max_pages,
    }


def compatible_pair(session, planned, prepared_id, spatial_id, layout_hash, processing_id):
    source = selected_snapshot(session, prepared_id, spatial_id)
    if (
        source.layout.owner.processing_run_id != processing_id
        or source.layout.owner.document_page_id != planned.document_page_id
        or source.layout.owner.page_number != planned.page_number
        or source.layout.algorithm_sha256 != layout_hash
        or source.prepared.manifest.preparation_sha256 != planned.preparation_hash
        or (planned.prepared_result_id and planned.prepared_result_id != prepared_id)
        or (planned.spatial_result_id and planned.spatial_result_id != spatial_id)
    ):
        raise ValueError("Source result differs from the pinned page plan")
    return source


def plan_document(session, source, selection, layout, profile):
    _, document, processing = source
    if selection.processing_run_id != processing.id:
        raise ExtractionError("The processed source changed. Review the source again.")
    if len(selection.pages) > min(layout.max_pages, profile.max_pages):
        raise ExtractionError("The selected pages exceed the profile page limit.")
    pages = {
        page.page_number: page
        for page in session.scalars(
            select(DocumentPage).where(
                DocumentPage.document_id == document.id,
                DocumentPage.page_number.in_(selection.pages),
            )
        )
    }
    if set(selection.pages) != set(pages):
        raise ExtractionError("One or more selected pages are outside the processed source.")

    planned = []
    for number in selection.pages:
        page = pages[number]
        owner, original, base, _ = source_snapshot(session, document, processing, page)
        image = next(a for a in base if a.role == "ANALYSIS_IMAGE")
        if (
            image.size_bytes > profile.max_input_bytes
            or image.width_px * image.height_px > profile.max_image_pixels
        ):
            raise ExtractionError(
                f"Page {number} exceeds the image limits for the selected profile."
            )
        preparation = preparation_identity(
            layout.preparation, original, base, force_ocr=number in selection.force_ocr_pages
        )
        item = PlannedPage(
            page_number=number, document_page_id=page.id, preparation_hash=preparation
        )
        prepared = SourceEnrichmentPageResult
        spatial = SourceSpatialResult
        ready = session.execute(
            select(spatial.id, prepared.id)
            .join(prepared, prepared.id == spatial.prepared_result_id)
            .join(ExtractionWorkUnit, ExtractionWorkUnit.id == spatial.work_unit_id)
            .join(ExtractionRun, ExtractionRun.id == spatial.run_id)
            .where(
                spatial.processing_run_id == processing.id,
                spatial.document_page_id == page.id,
                spatial.layout_hash == layout.algorithm_sha256,
                prepared.preparation_hash == preparation,
                ExtractionRun.profile_hash == layout.identity_hash,
                ExtractionWorkUnit.status == "COMPLETED",
            )
            .order_by(spatial.created_at, spatial.id)
            .limit(1)
        ).one_or_none()
        if ready:
            spatial_id, prepared_id = ready
            compatible_pair(
                session, item, prepared_id, spatial_id, layout.algorithm_sha256, processing.id
            )
            item.prepared_result_id = prepared_id
            item.spatial_result_id = spatial_id
        else:
            prepared_id = session.scalar(
                select(prepared.id)
                .join(ExtractionWorkUnit, ExtractionWorkUnit.id == prepared.work_unit_id)
                .where(
                    prepared.processing_run_id == processing.id,
                    prepared.document_page_id == page.id,
                    prepared.preparation_hash == preparation,
                    ExtractionWorkUnit.status == "COMPLETED",
                )
                .order_by(prepared.created_at, prepared.id)
                .limit(1)
            )
            if prepared_id:
                snapshot = successful_prepared(session, prepared_id)
                if (
                    snapshot.manifest.owner != owner
                    or snapshot.manifest.original != original
                    or snapshot.manifest.base_artifacts != base
                ):
                    raise ValueError("Committed preparation differs from the selected source")
                item.prepared_result_id = prepared_id
        planned.append(item)
    return PlannedDocument(selection=selection, document_id=document.id, pages=planned)


def preview_operation(session, settings, project_id, revision_id, selection):
    ids = [doc.revision_document_id for doc in selection.documents]
    sources = scoped_sources(session, project_id, revision_id, ids)
    errors = []
    if len(ids) > settings.extraction_operation_max_documents:
        errors.append(f"Select at most {settings.extraction_operation_max_documents} documents.")
    if sum(len(doc.pages) for doc in selection.documents) > settings.extraction_operation_max_pages:
        errors.append(
            f"Select at most {settings.extraction_operation_max_pages} pages per operation."
        )

    within_limits = not errors
    profile = phase6r_profile(settings)
    external = settings.extraction_enabled and settings.extraction_phase6r_fake
    if not external:
        errors.append(
            "Live extraction is unavailable until the Phase 6R provider adapter is installed."
        )
    try:
        layout = layout_profile(settings) if settings.enrichment_enabled else None
    except (ValueError, KeyError):
        layout = None
    if layout is None:
        errors.append("Local preparation and layout are unavailable on this deployment.")
    items = []
    plans = []
    remote_attempts = ocr_attempts = 0
    for doc in selection.documents:
        source = sources.get(doc.revision_document_id)
        error = source_error(source, settings)
        plan = None
        if not error and layout and within_limits:
            try:
                plan = plan_document(session, source, doc, layout, profile)
                missing = sum(page.spatial_result_id is None for page in plan.pages)
                if missing * 2 > layout.max_calls:
                    raise ExtractionError(
                        "The local admission budget cannot cover all required stages."
                    )
                if len(doc.pages) * len(profile.stages) > profile.max_calls:
                    raise ExtractionError(
                        "The provider admission budget cannot cover all required stages."
                    )
            except ExtractionError as exc:
                error, plan = str(exc), None
            except (ValueError, KeyError, StopIteration):
                error, plan = "Exact preparation or source artifacts are unavailable.", None
        elif not error and layout is None:
            error = "Local preparation and layout are unavailable."
        if plan:
            plans.append(plan)
            ocr_attempts += (
                sum(page.prepared_result_id is None for page in plan.pages) * layout.max_attempts
            )
            remote_attempts += min(
                profile.max_calls, len(doc.pages) * len(profile.stages) * profile.max_attempts
            )
        items.append(
            {
                "revision_document_id": doc.revision_document_id,
                "filename": source[1].original_filename if source else None,
                "processing_run_id": doc.processing_run_id,
                "error": error,
                "pages": [
                    {
                        "page_number": page.page_number,
                        "force_ocr": page.page_number in doc.force_ocr_pages,
                        "reuse_preparation": page.prepared_result_id is not None,
                        "reuse_layout": page.spatial_result_id is not None,
                    }
                    for page in plan.pages
                ]
                if plan
                else [],
            }
        )
    if remote_attempts > settings.extraction_operation_max_provider_admissions:
        errors.append(
            "The maximum provider admissions exceed the operation limit. Select fewer pages."
        )
    if ocr_attempts > settings.extraction_operation_max_ocr_attempts:
        errors.append("The maximum OCR attempts exceed the operation limit. Select fewer pages.")
    return Preview(
        documents=plans,
        policy=OperationPolicy(
            mode=selection.mode,
            profile_hash=profile.identity_hash,
            layout_profile_hash=layout.identity_hash,
            provider_admissions=remote_attempts,
            ocr_attempts=ocr_attempts,
            parallel_documents=settings.extraction_operation_max_concurrent_documents,
        )
        if layout
        else None,
        items=items,
        profile={
            "key": profile.key,
            "provider": profile.provider,
            "model": profile.model,
            "enabled": external,
        },
        errors=errors,
    )
