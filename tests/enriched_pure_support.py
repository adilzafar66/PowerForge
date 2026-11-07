"""Actual native preparation/derivation for pure adapter regression controls."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

from powerforge_document_processing.layout_derive import derive_layout
from powerforge_document_processing.layout_readings import align_readings, selected_readings
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.enriched_observations import RESPONSES, SCHEMAS
from powerforge_extraction.enriched_profiles import enriched_profile
from powerforge_extraction.enriched_runtime import projection
from powerforge_extraction.enriched_sources import BoundSnapshot, EnrichedSources
from powerforge_extraction.identities import canonical_json
from powerforge_shared.config import Settings
from spatial_layout_support import prepare_pdf
from spatial_layout_support import sources as source_bytes


def native_sources(payload, stage="TABLE_RECONSTRUCTION"):
    return from_prepared(prepare_pdf(payload), stage)


def from_prepared(output, stage="TABLE_RECONSTRUCTION"):
    geometry, text = source_bytes(output)
    prepared = output.manifest
    layout = derive_layout(prepared, geometry, text, uuid4(), uuid4(), uuid4())
    raw, bodies = selected_readings(prepared, geometry, text)
    readings, _ = align_readings(raw, prepared.page_frame.width, prepared.page_frame.height)
    snapshot = BoundSnapshot(
        SimpleNamespace(manifest=prepared),
        layout,
        "layout",
        1,
        "0" * 64,
        prepared.base_artifacts[0],
        "image",
    )
    run, unit = uuid4(), uuid4()
    return EnrichedSources(
        snapshot,
        geometry,
        text,
        bodies,
        tuple(readings),
        b"test-image",
        run,
        unit,
        stage + ":page:000001",
        stage,
    )


def fake(sources, upstream=None):
    table = sources.stage.startswith("TABLE_")
    profile = enriched_profile(
        "tables-test-enriched-v1" if table else "engineering-test-enriched-v1",
        Settings(_env_file=None),
    )
    request = SimpleNamespace(
        text=projection(sources, profile),
        stage=sources.stage,
        schema_version=SCHEMAS[sources.stage],
        response_model=RESPONSES[sources.stage],
        upstream_context=upstream,
    )
    return FakeEnrichedProvider().execute(request).result


def table_interpretation(sources, reconstruction):
    later = replace(
        sources,
        unit_id=uuid4(),
        unit_key="TABLE_INTERPRETATION:page:000001",
        stage="TABLE_INTERPRETATION",
    )
    upstream = canonical_json(
        dict(
            tables=[
                dict(
                    table_ref=t.layout.metadata["observation"]["local_ref"],
                    observation=t.layout.metadata["observation"],
                    structure_basis=t.layout.metadata["structure_basis"],
                )
                for t in reconstruction.tables
            ]
        )
    )
    return later, fake(later, upstream)
