"""Committed same-run/page table prerequisite loading; caller owns source I/O and transaction."""

from sqlalchemy import select

from powerforge_extraction.contracts import EvidenceInput, TableInput, WorkUnitOutput
from powerforge_extraction.models import (
    Evidence,
    ExtractedTable,
    ExtractionCandidate,
    ExtractionWorkUnit,
    SourceGroup,
)
from powerforge_extraction.table_grounding import context_from_output
from powerforge_provenance.locations import Region, SourceLocation


def load_table_context(session, sources, reconstruction_unit_id):
    target = sources.spec
    unit = session.get(ExtractionWorkUnit, reconstruction_unit_id)
    if (
        unit is None
        or unit.status != "COMPLETED"
        or unit.stage != "TABLE_RECONSTRUCTION"
        or (
            unit.id == target.unit_id
            or unit.run_id != target.run_id
            or unit.document_id != target.document_id
            or unit.processing_run_id != target.processing_run_id
            or unit.page_numbers != [target.page_number]
            or unit.unit_key != f"TABLE_RECONSTRUCTION:page:{target.page_number:06d}"
            or set(unit.input_artifact_ids) != {str(a.id) for a in target.artifacts}
        )
    ):
        raise ValueError("Table context requires a completed same-run/page reconstruction")
    for model in (ExtractionCandidate, SourceGroup):
        if session.scalar(select(model.id).where(model.work_unit_id == unit.id).limit(1)):
            raise ValueError("Reconstruction cannot own engineering candidates/groups")
    rows = list(
        session.scalars(
            select(ExtractedTable)
            .where(ExtractedTable.work_unit_id == unit.id)
            .order_by(ExtractedTable.id)
            .limit(9)
        )
    )
    if len(rows) > 8:
        raise ValueError("Committed tables exceed their page bound")
    tables = [
        TableInput.model_validate({name: getattr(row, name) for name in TableInput.model_fields})
        for row in rows
    ]
    evidence = []
    for row in session.scalars(
        select(Evidence).where(Evidence.work_unit_id == unit.id).limit(10001)
    ):
        evidence.append(
            EvidenceInput(
                **{
                    name: getattr(row, name)
                    for name in EvidenceInput.model_fields
                    if name != "location"
                },
                location=SourceLocation(
                    document_page_id=row.document_page_id,
                    page_artifact_id=row.page_artifact_id,
                    region=Region(x=row.x, y=row.y, width=row.width, height=row.height)
                    if row.x is not None
                    else None,
                ),
            )
        )
    return context_from_output(sources, WorkUnitOutput(tables=tables, evidence=evidence), unit.id)
