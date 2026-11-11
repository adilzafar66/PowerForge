"""Independent v2 source/geometry/table validation at the existing atomic publisher."""

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from powerforge_document_processing.models import PageArtifact
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.enriched_contracts import EnrichedEvidence, EnrichedOutput
from powerforge_extraction.enriched_grounding import image_location, reading_evidence
from powerforge_extraction.enriched_observations import EnrichedReconstructionResponse
from powerforge_extraction.enriched_sources import bound_snapshot, load_bound
from powerforge_extraction.enriched_tables import reconstruct
from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.models import ExtractedTable, ExtractionRun, ExtractionWorkUnit
from powerforge_provenance.enriched_locations import EnrichedLocation


@dataclass(frozen=True)
class VerifiedEnrichedPublication:
    unit_id: UUID
    profile_hash: str
    configuration_hash: str
    binding_hash: str
    prepared_id: UUID
    prepared_hash: str
    spatial_id: UUID
    spatial_hash: str
    image_id: UUID
    image_descriptor: tuple[str, str, int, int, int]
    output_hash: str

    def verify(self, session, run, unit, output):
        """Recheck the immutable source identities with no source replay or storage I/O."""
        source_page_id = UUID(unit.execution_metadata["source_page_id"])
        configuration = session.get(RunExecution, run.id).configuration
        binding = RunSourceEnrichmentBinding
        pinned = session.execute(
            select(
                binding.binding_hash,
                binding.prepared_result_id,
                binding.manifest_hash,
                binding.spatial_result_id,
                binding.spatial_manifest_hash,
            ).where(
                binding.run_id == run.id,
                binding.document_page_id == source_page_id,
            )
        ).one_or_none()
        # The base processing artifact is outside the immutable enrichment tables.
        image = session.execute(
            select(
                PageArtifact.storage_key,
                PageArtifact.sha256,
                PageArtifact.size_bytes,
                PageArtifact.width_px,
                PageArtifact.height_px,
            )
            .where(
                PageArtifact.id == self.image_id,
                PageArtifact.processing_run_id == unit.processing_run_id,
                PageArtifact.document_page_id == source_page_id,
                PageArtifact.artifact_type == "ANALYSIS_IMAGE",
            )
            .with_for_update(read=True)
        ).one_or_none()
        if (
            unit.id != self.unit_id
            or run.profile_hash != self.profile_hash
            or identity_hash(configuration) != self.configuration_hash
            or unit.execution_metadata["binding_hash"] != self.binding_hash
            or pinned
            != (
                self.binding_hash,
                self.prepared_id,
                self.prepared_hash,
                self.spatial_id,
                self.spatial_hash,
            )
            or image != self.image_descriptor
            or identity_hash(output.model_dump(mode="json")) != self.output_hash
        ):
            raise ValueError("Publication differs from its verified attempt, sources or output")


def prepare_publication(factory, storage, unit_id, output) -> VerifiedEnrichedPublication:
    """Independently replay evidence and tables against detached, exact source artifacts."""
    from powerforge_extraction.profiles import read_profile

    output = EnrichedOutput.model_validate(output.model_dump())
    with factory() as session:
        unit = session.get(ExtractionWorkUnit, unit_id)
        run = session.get(ExtractionRun, unit.run_id)
        configuration = session.get(RunExecution, unit.run_id).configuration
        profile = read_profile(configuration)
        snapshot = bound_snapshot(session, unit)
    sources = load_bound(snapshot, storage, unit, profile)
    from powerforge_extraction.enriched_profiles import CompactTableProfile

    validate_locations(sources, output, compact=isinstance(profile, CompactTableProfile))
    return VerifiedEnrichedPublication(
        unit_id=unit_id,
        profile_hash=run.profile_hash,
        # JSONB can reorder nested keys from the original profile wire format.
        configuration_hash=identity_hash(configuration),
        binding_hash=unit.execution_metadata["binding_hash"],
        prepared_id=snapshot.prepared.manifest.id,
        prepared_hash=snapshot.prepared.manifest.identity_hash,
        spatial_id=snapshot.layout.id,
        spatial_hash=snapshot.spatial_hash,
        image_id=snapshot.image.id,
        image_descriptor=(
            snapshot.image_key,
            snapshot.image.sha256,
            snapshot.image.size_bytes,
            snapshot.image.width_px,
            snapshot.image.height_px,
        ),
        output_hash=identity_hash(output.model_dump(mode="json")),
    )


def validate_locations(sources, output, *, compact=False):
    generated = {}
    for reading in sources.readings:
        if "NATIVE_PREFERRED_UNALIGNED" not in reading.model.issues:
            generated[reading.model.preferred] = reading
    for table in output.tables:
        if compact:
            from powerforge_extraction.table_reconstruction_v4 import (
                compact_response_from_layouts,
                reconstruct_compact,
            )

            response = compact_response_from_layouts([table.layout.model_dump(mode="json")])
            expected, _ = reconstruct_compact(response, sources)
        else:
            response = EnrichedReconstructionResponse.model_validate(
                dict(
                    schema_version="table-reconstruction-schema-v2",
                    overflowed=False,
                    tables=[table.layout.metadata["reported_observation"]],
                )
            )
            expected, _ = reconstruct(response, sources)
        if expected.tables != [table]:
            raise ValueError("Table layout does not reproduce from the exact pinned source")
        expected_evidence = {e.id: e for e in expected.evidence}
        actual = {e.id: e for e in output.evidence if e.table_id == table.id}
        if actual != expected_evidence:
            raise ValueError("Table evidence differs from admitted cells/captions")
    locations = [e.location for e in output.evidence]
    locations += [loc for table in output.tables for loc in table.source_locations]
    locations += [c.location for t in output.tables for c in t.layout.cells if c.location]
    for loc in locations:
        validate_location(sources, loc, generated)
    for evidence in output.evidence:
        if evidence.location.reading_basis == "VISUAL_REPORTED":
            continue
        reading = generated[evidence.location.support[0]]
        expected = reading_evidence(
            sources,
            reading,
            table_id=evidence.table_id,
            cell_id=evidence.cell_id,
            structure=evidence.location.structure_basis,
        )
        if evidence.model_copy(update={"id": expected.id}) != expected:
            raise ValueError("Evidence text/offsets differ from its exact selected occurrence")


def validate_location(sources, loc, readings):
    loc = EnrichedLocation.model_validate(loc)
    if loc.reading_basis == "VISUAL_REPORTED":
        expected = image_location(sources, loc.structure_basis)
    else:
        if len(loc.support) != 1 or loc.support[0] not in readings:
            raise ValueError("Source locator lacks a selected exact token occurrence")
        expected = reading_evidence(
            sources, readings[loc.support[0]], structure=loc.structure_basis
        ).location
    if loc != expected:
        raise ValueError("Source locator geometry/artifact/producer differs from pinned support")


def table_evidence(persistence, run_id, unit_id, evidence):
    session = persistence.session
    if evidence.source_kind == "TABLE_CELL" and evidence.cell_id is None:
        raise ValueError("Table-cell evidence requires its committed cell locator")
    table = session.get(ExtractedTable, evidence.table_id)
    unit = session.get(ExtractionWorkUnit, unit_id)
    producer = session.get(ExtractionWorkUnit, table.work_unit_id) if table else None
    if (
        table is None
        or table.layout_schema_version != "table-layout-v2"
        or table.run_id != run_id
        or producer is None
        or producer.id != unit_id
        and producer.status != "COMPLETED"
        or producer.processing_run_id != unit.processing_run_id
        or producer.page_numbers != unit.page_numbers
        or producer.input_artifact_ids != unit.input_artifact_ids
        or unit.stage == "TABLE_INTERPRETATION"
        and producer.stage != "TABLE_RECONSTRUCTION"
    ):
        raise ValueError(
            "Enhanced cell evidence requires its committed same-run/page reconstruction"
        )
    loc = (
        evidence.location
        if isinstance(evidence, EnrichedEvidence)
        else EnrichedLocation.model_validate_json(json.dumps(evidence.source_locator))
    )
    if loc.document_page_id != UUID(table.source_locations[0]["document_page_id"]):
        raise ValueError("Table source page differs from evidence")
    metadata = table.layout["metadata"]
    if str(evidence.id) not in {str(e) for e in table.evidence_ids}:
        raise ValueError("Evidence was not admitted by this table reconstruction")
    if evidence.cell_id is not None and str(evidence.id) not in metadata["cell_evidence_ids"].get(
        evidence.cell_id, []
    ):
        raise ValueError("Evidence belongs to another cell")
    if (
        str(loc.prepared_result_id) != metadata["prepared_result_id"]
        or str(loc.spatial_result_id) != metadata["spatial_result_id"]
    ):
        raise ValueError("Table source producer differs from the exact evidence binding")
