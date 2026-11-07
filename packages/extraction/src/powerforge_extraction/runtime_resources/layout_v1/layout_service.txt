"""Fixed local two-stage planning, direct preparation receipts and fenced spatial output."""

from sqlalchemy import select

from powerforge_document_processing.models import Document, DocumentPage, DocumentProcessingRun
from powerforge_extraction.contracts import WorkUnitInput
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.dependencies import unit_key
from powerforge_extraction.enrichment_models import SourceEnrichmentPageResult
from powerforge_extraction.enrichment_profiles import PURPOSE
from powerforge_extraction.enrichment_service import source_snapshot
from powerforge_extraction.errors import (
    ExtractionConflict,
    ExtractionDisabled,
    ExtractionError,
    ExtractionNotFound,
)
from powerforge_extraction.layout_models import SourcePreparationReceipt, SourceSpatialResult
from powerforge_extraction.layout_profiles import layout_profile
from powerforge_extraction.layout_sources import successful_prepared
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.orchestration import ACTIVE, ExtractionCoordinator
from powerforge_extraction.persistence import ExtractionPersistence
from powerforge_provenance.layout_observations import SpatialLayout
from powerforge_provenance.spatial_base import canonical_json, identity_hash


def start_layout(
    session,
    settings,
    document_id,
    processing_run_id,
    pages,
    force_ocr_pages,
    revision_document_id=None,
    mode="ensure",
    prepared_result_ids=(),
):
    if not settings.enrichment_enabled:
        raise ExtractionDisabled("Local enrichment is disabled")
    try:
        profile = layout_profile(settings)
    except (ValueError, KeyError):
        raise ExtractionDisabled("Local engine identity is not configured") from None
    if (
        mode not in ("ensure", "reextract")
        or not pages
        or pages != sorted(set(pages))
        or min(pages) < 1
        or len(pages) > profile.max_pages
        or force_ocr_pages != sorted(set(force_ocr_pages))
        or not set(force_ocr_pages) <= set(pages)
    ):
        raise ExtractionError(
            "Select distinct ascending pages and explicit OCR pages within limits"
        )
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
        raise ExtractionError("Document exceeds the configured size bound")
    explicit = {}
    for result_id in prepared_result_ids:
        row = session.get(SourceEnrichmentPageResult, result_id)
        if row is None or row.document_id != document_id:
            raise ExtractionNotFound("Selected source result not found")
        try:
            snapshot = successful_prepared(session, result_id)
        except ValueError:
            raise ExtractionConflict("Selected preparation is not successful") from None
        number = snapshot.manifest.owner.page_number
        if number in explicit or number not in pages:
            raise ExtractionError("Select one exact prepared result per selected page")
        explicit[number] = snapshot
    if prepared_result_ids and set(explicit) != set(pages):
        raise ExtractionError("Explicit prepared selection must cover every selected page")
    chosen = []
    for number in pages:
        page = session.scalar(
            select(DocumentPage).where(
                DocumentPage.document_id == document_id, DocumentPage.page_number == number
            )
        )
        if page is None:
            raise ExtractionError("Selected source page not found")
        try:
            owner, original, base, _ = source_snapshot(session, document, processing, page)
        except ValueError:
            raise ExtractionError("Unsupported bounded source artifacts") from None
        preparation_hash = identity_hash(
            {
                "profile": profile.preparation.identity_hash,
                "original": original.model_dump(mode="json"),
                "base": [a.model_dump(mode="json") for a in base],
                "force_ocr": number in force_ocr_pages,
            }
        )
        receipt = explicit.get(number)
        if receipt and (
            receipt.manifest.owner != owner
            or receipt.manifest.original != original
            or receipt.manifest.base_artifacts != base
            or receipt.manifest.preparation_sha256 != preparation_hash
        ):
            raise ExtractionConflict(
                "Selected preparation differs from the exact source/configuration"
            )
        chosen.append((owner, base, preparation_hash, receipt))
    target = identity_hash(
        {
            "purpose": PURPOSE,
            "profile": profile.identity_hash,
            "pages": [(o.page_number, h) for o, _, h, _ in chosen],
            "explicit_prepared": {str(n): str(s.manifest.id) for n, s in sorted(explicit.items())},
        }
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
        extractor_version="source-layout-v1",
        schema_version="source-spatial-layout-v1",
        registry_version=None,
        profile_version=profile.version,
        profile_hash=profile.identity_hash,
        input_identity_hash=target,
        provider="local",
        model=None,
        prompt_version=None,
        prompt_hash=None,
        selected_pages=pages,
        stages=list(profile.stages),
        input_artifact_ids=[str(a.id) for _, base, _, _ in chosen for a in base],
        status="PENDING",
    )
    session.add(run)
    session.flush()
    session.add(RunExecution(run_id=run.id, configuration=profile.model_dump(mode="json")))
    session.flush()
    coordinator = ExtractionCoordinator(session, settings)
    for owner, base, preparation_hash, receipt in chosen:
        if receipt is None:
            row = session.scalar(
                select(SourceEnrichmentPageResult)
                .join(
                    ExtractionWorkUnit,
                    ExtractionWorkUnit.id == SourceEnrichmentPageResult.work_unit_id,
                )
                .where(
                    SourceEnrichmentPageResult.document_id == document_id,
                    SourceEnrichmentPageResult.processing_run_id == processing.id,
                    SourceEnrichmentPageResult.document_page_id == owner.document_page_id,
                    SourceEnrichmentPageResult.preparation_hash == preparation_hash,
                    ExtractionWorkUnit.status == "COMPLETED",
                )
                .order_by(SourceEnrichmentPageResult.created_at, SourceEnrichmentPageResult.id)
                .limit(1)
            )
            if row is not None:
                receipt = successful_prepared(session, row.id)
        common = dict(
            preparation_hash=preparation_hash,
            force_ocr=owner.page_number in force_ocr_pages,
            plan_hash=profile.identity_hash,
        )
        for stage in profile.stages:
            metadata = {
                **common,
                "prerequisite_key": unit_key("SOURCE_PREPARE", owner.page_number)
                if stage == "SPATIAL_LAYOUT"
                else None,
            }
            if stage == "SOURCE_PREPARE" and receipt:
                metadata.update(
                    reuse_result_id=str(receipt.manifest.id),
                    reuse_manifest_hash=receipt.manifest.identity_hash,
                )
            unit = ExtractionPersistence(session).create_work_unit(
                run.id,
                WorkUnitInput(
                    unit_key=unit_key(stage, owner.page_number),
                    stage=stage,
                    page_numbers=[owner.page_number],
                    input_artifact_ids=[a.id for a in base],
                    execution_metadata=metadata,
                ),
            )
            coordinator._delivery(unit, coordinator.now())
    return run


def validate_layout_plan(unit, profile):
    if (
        len(unit.page_numbers) != 1
        or unit.stage not in profile.stages
        or unit.unit_key != unit_key(unit.stage, unit.page_numbers[0])
        or unit.execution_metadata.get("plan_hash") != profile.identity_hash
        or type(unit.execution_metadata.get("force_ocr")) is not bool
    ):
        raise ValueError("Unit differs from its fixed layout plan")
    expected = (
        unit_key("SOURCE_PREPARE", unit.page_numbers[0]) if unit.stage == "SPATIAL_LAYOUT" else None
    )
    if unit.execution_metadata.get("prerequisite_key") != expected:
        raise ValueError("Layout prerequisite differs from the fixed same-page stage")


def publish_receipt(session, settings, claim, snapshot):
    coordinator = ExtractionCoordinator(session, settings)
    run, unit, _ = coordinator._authorized(claim.unit_id, claim.token)
    validate_layout_plan(unit, claim.profile)
    manifest = snapshot.manifest
    if (
        run.execution_purpose != PURPOSE
        or unit.stage != "SOURCE_PREPARE"
        or unit.execution_metadata.get("reuse_result_id") != str(manifest.id)
        or unit.execution_metadata.get("reuse_manifest_hash") != manifest.identity_hash
        or unit.execution_metadata["preparation_hash"] != manifest.preparation_sha256
        or manifest.owner.document_id != run.document_id
        or manifest.owner.processing_run_id != run.processing_run_id
        or [manifest.owner.page_number] != unit.page_numbers
        or {str(a.id) for a in manifest.base_artifacts} != set(unit.input_artifact_ids)
    ):
        raise ValueError("Receipt differs from exact admitted original preparation")
    session.add(
        SourcePreparationReceipt(
            run_id=run.id,
            document_id=run.document_id,
            processing_run_id=run.processing_run_id,
            work_unit_id=unit.id,
            document_page_id=manifest.owner.document_page_id,
            prepared_result_id=manifest.id,
            preparation_hash=manifest.preparation_sha256,
            manifest_hash=manifest.identity_hash,
        )
    )
    session.flush()
    unit.status = "COMPLETED"
    unit.finished_at = coordinator.now()
    unit.output_counts = {"source_receipts": 1, "ocr_invocations": 0}
    session.flush()
    coordinator.aggregate(run)


def spatial_key(document_id, result_id):
    return f"source-spatial/{document_id}/{result_id}.json"


def publish_layout(session, settings, claim, snapshot, geometry, text, layout, usage):
    from powerforge_extraction.layout_sources import preparation_for_layout

    coordinator = ExtractionCoordinator(session, settings)
    run, unit, _ = coordinator._authorized(claim.unit_id, claim.token)
    validate_layout_plan(unit, claim.profile)
    exact = preparation_for_layout(session, unit)
    from powerforge_document_processing.layout_derive import admit_layout

    layout = SpatialLayout.model_validate(layout)
    admit_layout(snapshot.manifest, geometry, text, layout)
    if (
        run.execution_purpose != PURPOSE
        or unit.stage != "SPATIAL_LAYOUT"
        or exact.manifest != snapshot.manifest
        or layout.prepared.id != snapshot.manifest.id
        or layout.prepared.manifest_sha256 != snapshot.manifest.identity_hash
        or layout.owner != snapshot.manifest.owner
        or layout.producer_run_id != run.id
        or layout.producer_work_unit_id != unit.id
        or layout.algorithm_sha256 != claim.profile.algorithm_sha256
    ):
        raise ValueError("Spatial output differs from its exact admitted source/producer")
    data = canonical_json(layout.model_dump(mode="json")).encode()
    session.add(
        SourceSpatialResult(
            id=layout.id,
            run_id=run.id,
            document_id=run.document_id,
            processing_run_id=run.processing_run_id,
            work_unit_id=unit.id,
            document_page_id=layout.owner.document_page_id,
            prepared_result_id=snapshot.manifest.id,
            layout_hash=layout.algorithm_sha256,
            manifest_hash=layout.identity_hash,
            manifest=layout.model_dump(mode="json"),
            storage_key=spatial_key(run.document_id, layout.id),
            size_bytes=len(data),
            usage=usage,
        )
    )
    session.flush()
    unit.status = "COMPLETED"
    unit.finished_at = coordinator.now()
    unit.output_counts = {
        "spatial_results": 1,
        "tables": len(layout.tables),
        "source_conflicts": sum(p.kind == "CONFLICT" for p in layout.overlaps),
        "ocr_invocations": 0,
    }
    session.flush()
    coordinator.aggregate(run)
