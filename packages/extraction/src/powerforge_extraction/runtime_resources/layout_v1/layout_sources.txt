"""Exact successful prepared snapshots and direct receipts; detached reads outside locks."""

from dataclasses import dataclass

from sqlalchemy import select

from powerforge_extraction.enrichment_execution import read_exact
from powerforge_extraction.enrichment_models import (
    SourceEnrichmentArtifact,
    SourceEnrichmentPageResult,
)
from powerforge_extraction.layout_models import SourcePreparationReceipt
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_provenance.spatial_base import canonical_json
from powerforge_provenance.spatial_sources import PreparedPage, load_positioned_text


@dataclass(frozen=True)
class PreparedSnapshot:
    manifest: PreparedPage
    objects: tuple


def successful_prepared(session, result_id):
    row = session.get(SourceEnrichmentPageResult, result_id)
    if row is None:
        raise ValueError("Selected preparation result is missing")
    unit = session.get(ExtractionWorkUnit, row.work_unit_id)
    run = session.get(ExtractionRun, row.run_id)
    if (
        unit is None
        or run is None
        or unit.status != "COMPLETED"
        or run.execution_purpose != "SOURCE_ENRICHMENT"
        or unit.stage != "SOURCE_PREPARE"
    ):
        raise ValueError("Preparation requires an original successful source producer")
    manifest = PreparedPage.model_validate_json(canonical_json(row.manifest))
    if (
        manifest.id,
        manifest.owner.document_id,
        manifest.owner.processing_run_id,
        manifest.owner.document_page_id,
        manifest.producer_run_id,
        manifest.producer_work_unit_id,
        manifest.preparation_sha256,
        manifest.identity_hash,
    ) != (
        row.id,
        row.document_id,
        row.processing_run_id,
        row.document_page_id,
        row.run_id,
        row.work_unit_id,
        row.preparation_hash,
        row.manifest_hash,
    ):
        raise ValueError("Committed preparation manifest differs from its owned producer")
    descriptors = [
        *manifest.derived_images,
        *(a for r in manifest.representations for a in (r.text_artifact, r.geometry_artifact)),
    ]
    objects = list(
        session.scalars(
            select(SourceEnrichmentArtifact).where(SourceEnrichmentArtifact.result_id == row.id)
        )
    )
    if {a.id for a in objects} != {a.id for a in descriptors}:
        raise ValueError("Committed prepared object set differs from manifest")
    by_id = {a.id: a for a in objects}
    snapshot = []
    for descriptor in descriptors:
        artifact = by_id[descriptor.id]
        if (
            artifact.document_id,
            artifact.processing_run_id,
            artifact.document_page_id,
            artifact.sha256,
            artifact.size_bytes,
            artifact.role,
            artifact.width_px,
            artifact.height_px,
        ) != (
            row.document_id,
            row.processing_run_id,
            row.document_page_id,
            descriptor.sha256,
            descriptor.size_bytes,
            descriptor.role,
            descriptor.width_px,
            descriptor.height_px,
        ):
            raise ValueError("Prepared object differs from the exact manifest descriptor")
        snapshot.append((descriptor, artifact.storage_key))
    return PreparedSnapshot(manifest, tuple(snapshot))


def load_prepared(snapshot, storage):
    blobs = {
        ref.id: read_exact(storage, key, ref.size_bytes, ref.sha256)
        for ref, key in snapshot.objects
    }
    geometry = {r.ref: blobs[r.geometry_artifact.id] for r in snapshot.manifest.representations}
    text = {r.ref: blobs[r.text_artifact.id] for r in snapshot.manifest.representations}
    for descriptor in snapshot.manifest.representations:
        load_positioned_text(
            snapshot.manifest, descriptor.ref, geometry[descriptor.ref], text[descriptor.ref]
        )
    return geometry, text, sum(len(v) for v in blobs.values())


def canonical_for_prepare_unit(session, unit):
    if unit.status != "COMPLETED" or unit.stage != "SOURCE_PREPARE":
        raise ValueError("Layout requires a committed same-run/page preparation stage")
    direct = session.scalar(
        select(SourceEnrichmentPageResult.id).where(
            SourceEnrichmentPageResult.work_unit_id == unit.id
        )
    )
    receipt = session.scalar(
        select(SourcePreparationReceipt).where(SourcePreparationReceipt.work_unit_id == unit.id)
    )
    if (direct is None) == (receipt is None):
        raise ValueError("Preparation requires exactly one canonical result or direct receipt")
    result_id = direct if direct else receipt.prepared_result_id
    snapshot = successful_prepared(session, result_id)
    manifest = snapshot.manifest
    if (
        manifest.owner.document_id,
        manifest.owner.processing_run_id,
        manifest.owner.page_number,
        manifest.preparation_sha256,
    ) != (
        unit.document_id,
        unit.processing_run_id,
        unit.page_numbers[0],
        unit.execution_metadata["preparation_hash"],
    ) or {str(a.id) for a in manifest.base_artifacts} != set(unit.input_artifact_ids):
        raise ValueError("Prepared prerequisite differs from exact planned sources")
    if receipt and (
        receipt.manifest_hash != manifest.identity_hash
        or str(result_id) != unit.execution_metadata.get("reuse_result_id")
    ):
        raise ValueError("Receipt does not pin the original successful producer")
    return snapshot


def prerequisite_unit(session, unit):
    key = unit.execution_metadata.get("prerequisite_key")
    return session.scalar(
        select(ExtractionWorkUnit).where(
            ExtractionWorkUnit.run_id == unit.run_id,
            ExtractionWorkUnit.unit_key == key,
            ExtractionWorkUnit.stage == "SOURCE_PREPARE",
            ExtractionWorkUnit.page_numbers == unit.page_numbers,
            ExtractionWorkUnit.input_artifact_ids == unit.input_artifact_ids,
            ExtractionWorkUnit.status == "COMPLETED",
        )
    )


def preparation_for_layout(session, unit):
    parent = prerequisite_unit(session, unit)
    if (
        parent is None
        or parent.execution_metadata.get("preparation_hash")
        != unit.execution_metadata.get("preparation_hash")
        or parent.execution_metadata.get("force_ocr") != unit.execution_metadata.get("force_ocr")
    ):
        raise ValueError("Layout prerequisite differs from its same-page source/configuration")
    return canonical_for_prepare_unit(session, parent)
