"""Scoped exact-artifact v2 signing; reading an extraction never executes enrichment."""

from powerforge_api.exceptions import RevisionDocumentNotFound, StorageDownloadFailed
from powerforge_api.schemas.extraction import EvidenceDetail
from powerforge_document_processing.storage.base import StorageError
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.enriched_grounding import image_location, reading_evidence
from powerforge_extraction.enriched_sources import bound_snapshot, load_bound
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.profiles import read_profile
from powerforge_provenance.enriched_locations import EnrichedLocation


def evidence_detail(reader, row, storage, expires):
    from powerforge_api.services.extraction_service import _evidence_summary

    unit = reader.session.get(ExtractionWorkUnit, row.work_unit_id)
    profile = read_profile(reader.session.get(RunExecution, row.run_id).configuration)
    try:
        snapshot = bound_snapshot(reader.session, unit)
        source = load_bound(snapshot, storage, unit, profile)
        from powerforge_provenance.spatial_base import canonical_json

        loc = EnrichedLocation.model_validate_json(canonical_json(row.source_locator))
        if (
            loc.document_page_id != row.document_page_id
            or loc.page_artifact_id != row.page_artifact_id
            or loc.enrichment_artifact_id != row.enrichment_artifact_id
            or loc.geometry_artifact_id != row.geometry_artifact_id
        ):
            raise ValueError("Evidence columns differ from explicit source locator")
        if loc.reading_basis == "VISUAL_REPORTED":
            if loc != image_location(source, loc.structure_basis):
                raise ValueError("Invalid visual evidence")
            text_key = None
        else:
            reading = next(r for r in source.readings if r.model.preferred in loc.support)
            expected = reading_evidence(
                source,
                reading,
                table_id=row.table_id,
                cell_id=row.cell_id,
                structure=loc.structure_basis,
            )
            if (
                loc != expected.location
                or row.source_snippet != expected.source_snippet
                or (row.text_start, row.text_end, row.offset_convention)
                != (expected.text_start, expected.text_end, expected.offset_convention)
            ):
                raise ValueError("Evidence differs from exact representation/geometry support")
            text_key = next(
                key
                for ref, key in snapshot.prepared.objects
                if ref.id == loc.enrichment_artifact_id
            )
        image_url = storage.create_download_url(
            snapshot.image_key, f"page-{loc.document_page_id}.png", "image/png", "inline", expires
        )
        url = (
            storage.create_download_url(
                text_key,
                f"reading-{loc.enrichment_artifact_id}.txt",
                "text/plain",
                "inline",
                expires,
            )
            if text_key
            else image_url
        )
    except StorageError:
        raise StorageDownloadFailed("Pinned evidence artifact unavailable") from None
    except (ValueError, StopIteration, KeyError):
        raise RevisionDocumentNotFound("Pinned enriched evidence unavailable") from None
    return EvidenceDetail(
        **_evidence_summary(row).model_dump(),
        run_id=row.run_id,
        document_id=row.document_id,
        processing_run_id=row.processing_run_id,
        work_unit_id=row.work_unit_id,
        page_number=snapshot.layout.owner.page_number,
        region=loc.region,
        text_start=row.text_start,
        text_end=row.text_end,
        offset_convention=row.offset_convention,
        created_at=row.created_at,
        artifact_url=url,
        artifact_url_expires_seconds=expires,
        source_image_url=image_url,
    )
