"""Exact successful cross-run bindings; source I/O remains outside database locks."""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, localcontext
from uuid import UUID

from sqlalchemy import select

from powerforge_document_processing.layout_derive import admit_layout, preparation_reference
from powerforge_document_processing.layout_readings import align_readings, selected_readings
from powerforge_extraction.enrichment_execution import read_exact
from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding
from powerforge_extraction.layout_models import SourceSpatialResult
from powerforge_extraction.layout_sources import load_prepared, successful_prepared
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_provenance.layout_observations import SpatialLayout
from powerforge_provenance.spatial_base import canonical_json
from powerforge_provenance.spatial_sources import load_positioned_text


@dataclass(frozen=True)
class BoundSnapshot:
    prepared: object
    layout: SpatialLayout
    spatial_key: str
    spatial_size: int
    spatial_hash: str
    image: object
    image_key: str


def selected_snapshot(session, prepared_id, spatial_id):
    prepared = successful_prepared(session, prepared_id)
    row = session.get(SourceSpatialResult, spatial_id)
    if row is None:
        raise ValueError("Selected spatial result is missing")
    unit = session.get(ExtractionWorkUnit, row.work_unit_id)
    run = session.get(ExtractionRun, row.run_id)
    layout = SpatialLayout.model_validate_json(canonical_json(row.manifest))
    if (
        row.prepared_result_id != prepared_id
        or unit.status != "COMPLETED"
        or run.execution_purpose != "SOURCE_ENRICHMENT"
        or unit.stage != "SPATIAL_LAYOUT"
        or layout.id != row.id
        or layout.producer_run_id != row.run_id
        or layout.producer_work_unit_id != row.work_unit_id
        or layout.identity_hash != row.manifest_hash
        or layout.owner != prepared.manifest.owner
        or layout.prepared.id != prepared_id
        or layout.prepared.manifest_sha256 != prepared.manifest.identity_hash
        or layout.prepared != preparation_reference(prepared.manifest)
    ):
        raise ValueError("Selected sources require exact successful compatible producers")
    from powerforge_document_processing.models import PageArtifact

    image = next(a for a in prepared.manifest.base_artifacts if a.role == "ANALYSIS_IMAGE")
    base = session.get(PageArtifact, image.id)
    if (base.sha256, base.size_bytes, base.width_px, base.height_px) != (
        image.sha256,
        image.size_bytes,
        image.width_px,
        image.height_px,
    ):
        raise ValueError("Pinned base image differs from its descriptor")
    return BoundSnapshot(
        prepared,
        layout,
        row.storage_key,
        row.size_bytes,
        row.manifest_hash,
        image,
        base.storage_key,
    )


def bound_snapshot(session, unit):
    binding = session.scalar(
        select(RunSourceEnrichmentBinding).where(
            RunSourceEnrichmentBinding.run_id == unit.run_id,
            RunSourceEnrichmentBinding.document_page_id
            == UUID(unit.execution_metadata["source_page_id"]),
        )
    )
    if binding is None or binding.spatial_result_id is None:
        raise ValueError("Exact completed enrichment binding required")
    result = selected_snapshot(session, binding.prepared_result_id, binding.spatial_result_id)
    owner = result.layout.owner
    if (
        owner.document_id != unit.document_id
        or owner.processing_run_id != unit.processing_run_id
        or owner.document_page_id != binding.document_page_id
        or [owner.page_number] != unit.page_numbers
        or binding.manifest_hash != result.prepared.manifest.identity_hash
        or binding.spatial_manifest_hash != result.layout.identity_hash
        or unit.execution_metadata.get("binding_hash") != binding.binding_hash
        or set(unit.input_artifact_ids)
        != {str(a.id) for a in result.prepared.manifest.base_artifacts}
    ):
        raise ValueError("Enrichment binding differs from planned unit ownership")
    return result


@dataclass(frozen=True)
class EnrichedSources:
    snapshot: BoundSnapshot
    geometry: dict
    text: dict
    bodies: dict
    readings: tuple
    image: bytes
    run_id: UUID
    unit_id: UUID
    unit_key: str
    stage: str

    @property
    def layout(self):
        return self.snapshot.layout

    @property
    def prepared(self):
        return self.snapshot.prepared.manifest


def load_bound(snapshot, storage, unit, profile):
    geometry, text, _ = load_prepared(snapshot.prepared, storage)
    read_exact(storage, snapshot.spatial_key, snapshot.spatial_size, snapshot.spatial_hash)
    admit_layout(snapshot.prepared.manifest, geometry, text, snapshot.layout)
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        raw, bodies = selected_readings(snapshot.prepared.manifest, geometry, text)
        readings, _ = align_readings(
            raw,
            snapshot.prepared.manifest.page_frame.width,
            snapshot.prepared.manifest.page_frame.height,
        )
    if tuple(r.model for r in readings) != snapshot.layout.readings:
        raise ValueError("Selected reading alignment differs from committed layout")
    for descriptor in snapshot.prepared.manifest.representations:
        load_positioned_text(
            snapshot.prepared.manifest,
            descriptor.ref,
            geometry[descriptor.ref],
            text[descriptor.ref],
        )
    image = read_exact(
        storage, snapshot.image_key, snapshot.image.size_bytes, snapshot.image.sha256
    )
    if (
        len(image) > profile.max_input_bytes
        or snapshot.image.width_px * snapshot.image.height_px > profile.max_image_pixels
    ):
        raise ValueError("Pinned analysis image exceeds profile bounds")
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(image)) as decoded:
        if decoded.format != "PNG" or decoded.size != (
            snapshot.image.width_px,
            snapshot.image.height_px,
        ):
            raise ValueError("Pinned image format/dimensions differ")
        decoded.verify()
    return EnrichedSources(
        snapshot,
        geometry,
        text,
        bodies,
        tuple(readings),
        image,
        unit.run_id,
        unit.id,
        unit.unit_key,
        unit.stage,
    )
