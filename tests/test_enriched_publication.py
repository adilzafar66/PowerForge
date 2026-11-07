"""Independent publisher and SQL fences reject fabricated v2 evidence atomically."""

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from enriched_support import enrich, start_enriched
from enrichment_support import build_source
from enrichment_support import enrichment_ctx as enrichment_ctx
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.enriched_runtime import request_for
from powerforge_extraction.enriched_tables import reconstruct
from powerforge_extraction.models import Evidence, ExtractedTable, ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.persistence import ExtractionPersistence

pytestmark = pytest.mark.integration


def claimed(ctx):
    build_source(
        ctx, Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(), "guard.pdf"
    )
    binding = enrich(ctx)
    pending = start_enriched(ctx, binding)
    uid = UUID(next(a["id"] for a in pending["attempts"] if a["stage"] == "TABLE_RECONSTRUCTION"))
    with ctx["factory"].begin() as session:
        claim = ExtractionCoordinator(session, ctx["settings"]).claim(uid)
    request, source, _ = request_for(claim, ctx["storage"], ctx["factory"])
    output, _ = reconstruct(FakeEnrichedProvider().execute(request).result, source)
    return claim, output


def test_publisher_rederives_offsets_geometry_and_cell_membership_before_inserting(enrichment_ctx):
    ctx = enrichment_ctx
    claim, original = claimed(ctx)
    first = original.evidence[0]
    region = first.location.region
    changes = [
        first.model_copy(update={"text_end": first.text_end + 1}),
        first.model_copy(update={"source_snippet": "invented"}),
        first.model_copy(update={"cell_id": "other-cell"}),
        first.model_copy(
            update={
                "location": first.location.model_copy(
                    update={"region": region.model_copy(update={"x": region.x + region.width / 10})}
                )
            }
        ),
    ]
    for changed in changes:
        output = original.model_copy(update={"evidence": [changed, *original.evidence[1:]]})
        with ctx["factory"].begin() as session:
            coordinator = ExtractionCoordinator(session, ctx["settings"])
            coordinator._authorized(claim.unit_id, claim.token)
            with pytest.raises(ValueError):
                ExtractionPersistence(session, ctx["storage"]).publish(claim.unit_id, output)
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Evidence)
                    .where(Evidence.run_id == claim.run_id)
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ExtractedTable)
                    .where(ExtractedTable.run_id == claim.run_id)
                )
                == 0
            )
            assert session.get(ExtractionWorkUnit, claim.unit_id).status == "RUNNING"
    with ctx["factory"].begin() as session:
        coordinator = ExtractionCoordinator(session, ctx["settings"])
        coordinator._authorized(claim.unit_id, claim.token)
        ExtractionPersistence(session, ctx["storage"]).publish(claim.unit_id, original)
        coordinator.aggregate(session.get(ExtractionRun, claim.run_id))


def test_direct_database_insert_rejects_unowned_lease_and_foreign_source_support(enrichment_ctx):
    ctx = enrichment_ctx
    claim, output = claimed(ctx)
    first = next(e for e in output.evidence if e.table_id and e.text_start is not None)

    def row(locator=None):
        data = first.model_dump(exclude={"location", "table_id", "cell_id"})
        loc = first.location
        data["source_kind"] = "NATIVE_TEXT"
        selected = locator or loc.model_dump(mode="json")
        selected["structure_basis"] = "UNRESOLVED"
        return Evidence(
            **data,
            run_id=claim.run_id,
            work_unit_id=claim.unit_id,
            document_id=ctx["document"],
            processing_run_id=ctx["processing"],
            document_page_id=loc.document_page_id,
            page_artifact_id=None,
            enrichment_artifact_id=loc.enrichment_artifact_id,
            geometry_artifact_id=loc.geometry_artifact_id,
            source_locator=selected,
            **loc.region.model_dump(),
        )

    with pytest.raises(DBAPIError, match="lease"):
        with ctx["factory"].begin() as session:
            session.add(row())
            session.flush()
    bad = first.location.model_dump(mode="json")
    bad["support"][0]["ref"] = "foreign-token"
    with pytest.raises(DBAPIError, match="bound text and geometry"):
        with ctx["factory"].begin() as session:
            ExtractionCoordinator(session, ctx["settings"])._authorized(claim.unit_id, claim.token)
            session.add(row(bad))
            session.flush()
