"""Purpose-specific planning/output on the shared durable coordinator. Caller commits."""

from sqlalchemy import select

from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
)
from powerforge_extraction.contracts import WorkUnitInput
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.enrichment_models import (
    SourceEnrichmentArtifact,
    SourceEnrichmentPageResult,
)
from powerforge_extraction.enrichment_profiles import PURPOSE, preparation_profile
from powerforge_extraction.errors import ExtractionConflict, ExtractionDisabled, ExtractionError
from powerforge_extraction.models import ExtractionRun
from powerforge_extraction.orchestration import ACTIVE, ExtractionCoordinator
from powerforge_extraction.persistence import ExtractionPersistence
from powerforge_provenance.spatial_base import identity_hash
from powerforge_provenance.spatial_sources import (
    OriginalDocument,
    PageArtifactRef,
    PageOwner,
    PreparedPage,
    checked_bytes,
    load_positioned_text,
)


def source_snapshot(session, document, processing, page, ids=None):
    owner = PageOwner(
        document_id=document.id,
        processing_run_id=processing.id,
        document_page_id=page.id,
        page_number=page.page_number,
    )
    format = {
        "application/pdf": "pdf",
        "image/png": "png",
        "image/jpeg": "jpeg",
        "image/tiff": "tiff",
    }.get(document.mime_type)
    original = OriginalDocument(
        document_id=document.id,
        sha256=document.sha256,
        size_bytes=document.size_bytes,
        format=format,
    )
    rows = list(
        session.scalars(
            select(PageArtifact)
            .where(
                PageArtifact.processing_run_id == processing.id,
                PageArtifact.document_page_id == page.id,
                PageArtifact.artifact_type.in_(["ANALYSIS_IMAGE", "NATIVE_TEXT"]),
            )
            .order_by(PageArtifact.id)
        )
    )
    if ids is not None and {str(a.id) for a in rows} != set(ids):
        raise ValueError("Pinned base artifact set differs from completed processing")
    base = tuple(
        PageArtifactRef(
            id=a.id,
            owner=owner,
            role=a.artifact_type.value,
            sha256=a.sha256,
            size_bytes=a.size_bytes,
            width_px=a.width_px,
            height_px=a.height_px,
        )
        for a in rows
    )
    if not any(a.role == "ANALYSIS_IMAGE" for a in base):
        raise ExtractionConflict("A bounded completed analysis image is required for each page")
    return owner, original, base, {a.id: a.storage_key for a in rows}


def start_preparation(
    session,
    settings,
    document_id,
    processing_run_id,
    pages,
    force_ocr_pages,
    revision_document_id=None,
    mode="ensure",
):
    if not settings.enrichment_enabled:
        raise ExtractionDisabled("Local enrichment is disabled")
    try:
        profile = preparation_profile(settings)
    except (ValueError, KeyError):
        raise ExtractionDisabled("Local OCR engine identity is not configured") from None
    if (
        mode not in ("ensure", "reextract")
        or not pages
        or pages != sorted(set(pages))
        or min(pages) < 1
        or len(pages) > profile.max_pages
        or force_ocr_pages != sorted(set(force_ocr_pages))
        or not set(force_ocr_pages) <= set(pages)
    ):
        raise ExtractionError("Select distinct ascending pages and bounded explicit OCR pages")
    document = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
    processing = session.get(DocumentProcessingRun, processing_run_id)
    if (
        document is None
        or processing is None
        or processing.document_id != document_id
        or processing.status != "COMPLETED"
    ):
        raise ExtractionConflict("Select a compatible completed processing run")
    if document.size_bytes > settings.extraction_max_document_bytes:
        raise ExtractionError("Original exceeds configured document bound")
    chosen = []
    for number in pages:
        page = session.scalar(
            select(DocumentPage).where(
                DocumentPage.document_id == document_id, DocumentPage.page_number == number
            )
        )
        if page is None:
            raise ExtractionError("Selected page not found")
        try:
            owner, original, base, keys = source_snapshot(session, document, processing, page)
        except ValueError:
            raise ExtractionError(
                "Selected source artifacts exceed supported preparation bounds"
            ) from None
        preparation_hash = identity_hash(
            {
                "profile": profile.identity_hash,
                "original": original.model_dump(mode="json"),
                "base": [a.model_dump(mode="json") for a in base],
                "force_ocr": number in force_ocr_pages,
            }
        )
        chosen.append((owner, base, preparation_hash))
    target = identity_hash(
        {"purpose": PURPOSE, "pages": [(o.page_number, h) for o, _, h in chosen]}
    )
    latest = session.scalar(
        select(ExtractionRun)
        .where(
            ExtractionRun.document_id == document_id,
            ExtractionRun.execution_purpose == PURPOSE,
            ExtractionRun.input_identity_hash == target,
        )
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        .limit(1)
    )
    if latest and (latest.status in ACTIVE or mode == "ensure"):
        return latest
    run = ExtractionRun(
        execution_purpose=PURPOSE,
        document_id=document_id,
        processing_run_id=processing.id,
        initiated_from_revision_document_id=revision_document_id,
        reextracts_run_id=latest.id if latest else None,
        extractor_version="source-preparation-v1",
        schema_version="prepared-source-page-v1",
        registry_version=None,
        profile_version=profile.version,
        profile_hash=profile.identity_hash,
        input_identity_hash=target,
        provider="local",
        model=None,
        prompt_version=None,
        prompt_hash=None,
        selected_pages=pages,
        stages=["SOURCE_PREPARE"],
        input_artifact_ids=[str(a.id) for _, base, _ in chosen for a in base],
        status="PENDING",
    )
    session.add(run)
    session.flush()
    session.add(RunExecution(run_id=run.id, configuration=profile.model_dump(mode="json")))
    session.flush()
    coordinator = ExtractionCoordinator(session, settings)
    for owner, base, preparation_hash in chosen:
        unit = ExtractionPersistence(session).create_work_unit(
            run.id,
            WorkUnitInput(
                unit_key=f"SOURCE_PREPARE:{owner.page_number}",
                stage="SOURCE_PREPARE",
                page_numbers=[owner.page_number],
                input_artifact_ids=[a.id for a in base],
                execution_metadata={
                    "preparation_hash": preparation_hash,
                    "force_ocr": owner.page_number in force_ocr_pages,
                },
            ),
        )
        coordinator._delivery(unit, coordinator.now())
    return run


def publish_preparation(session, settings, claim, output):
    coordinator = ExtractionCoordinator(session, settings)
    run, unit, _ = coordinator._authorized(claim.unit_id, claim.token)
    if (
        run.execution_purpose != PURPOSE
        or output.manifest.producer_work_unit_id != unit.id
        or output.manifest.preparation_sha256 != unit.execution_metadata["preparation_hash"]
    ):
        raise ValueError("Local output differs from authorized producer")
    manifest = PreparedPage.model_validate(output.manifest)
    document = session.get(Document, run.document_id)
    processing = session.get(DocumentProcessingRun, run.processing_run_id)
    page = session.get(DocumentPage, manifest.owner.document_page_id)
    owner, original, base, _ = source_snapshot(
        session, document, processing, page, unit.input_artifact_ids
    )
    expected_hash = identity_hash(
        {
            "profile": claim.profile.identity_hash,
            "original": original.model_dump(mode="json"),
            "base": [a.model_dump(mode="json") for a in base],
            "force_ocr": unit.execution_metadata["force_ocr"],
        }
    )
    if (
        manifest.owner != owner
        or manifest.original != original
        or manifest.base_artifacts != base
        or manifest.preparation_sha256 != expected_hash
    ):
        raise ValueError("Prepared snapshot differs from exact admitted source/configuration")
    refs = [
        *manifest.derived_images,
        *(a for r in manifest.representations for a in (r.text_artifact, r.geometry_artifact)),
    ]
    if set(output.blobs) != {a.id for a in refs}:
        raise ValueError("Published source object set differs from manifest")
    for ref in refs:
        actual, data = output.blobs[ref.id]
        if actual != ref:
            raise ValueError("Published source descriptor differs from manifest")
        checked_bytes(ref, data)
    for representation in manifest.representations:
        load_positioned_text(
            manifest,
            representation.ref,
            output.blobs[representation.geometry_artifact.id][1],
            output.blobs[representation.text_artifact.id][1],
        )
    result = SourceEnrichmentPageResult(
        id=manifest.id,
        run_id=run.id,
        document_id=run.document_id,
        processing_run_id=run.processing_run_id,
        work_unit_id=unit.id,
        document_page_id=manifest.owner.document_page_id,
        preparation_hash=manifest.preparation_sha256,
        manifest_hash=manifest.identity_hash,
        manifest=manifest.model_dump(mode="json"),
        usage=output.usage,
    )
    session.add(result)
    session.flush()
    for ref, _data in output.blobs.values():
        session.add(
            SourceEnrichmentArtifact(
                id=ref.id,
                result_id=result.id,
                document_id=run.document_id,
                processing_run_id=run.processing_run_id,
                document_page_id=manifest.owner.document_page_id,
                role=ref.role,
                storage_key=artifact_key(run.document_id, result.id, ref.id),
                mime_type="image/png"
                if ref.role == "OCR_INPUT_IMAGE"
                else "text/plain"
                if ref.role in ("OCR_TEXT", "NATIVE_POSITIONED_TEXT")
                else "application/json",
                size_bytes=ref.size_bytes,
                sha256=ref.sha256,
                width_px=ref.width_px,
                height_px=ref.height_px,
            )
        )
    session.flush()
    unit.status = "COMPLETED"
    unit.finished_at = coordinator.now()
    unit.output_counts = {
        **unit.output_counts,
        "source_results": 1,
        "source_artifacts": len(output.blobs),
        "ocr_invocations": output.usage["ocr_invocations"],
    }
    session.flush()
    coordinator.aggregate(run)


def artifact_key(document_id, result_id, artifact_id):
    return f"source-enrichment/{document_id}/{result_id}/{artifact_id}"
