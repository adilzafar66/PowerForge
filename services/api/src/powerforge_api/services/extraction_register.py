"""Set-based extraction status for bounded sets of revision document associations."""

from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from powerforge_api.exceptions import ProjectError, RevisionNotFound
from powerforge_api.schemas.extraction import DocumentExtractionStatus, RegisterRun
from powerforge_api.services.revision_writes import assert_revision_mutable
from powerforge_document_model import DEFAULT_PROFILE
from powerforge_document_processing.models import (
    DocumentProcessingRun,
    PageArtifact,
    RevisionDocument,
)
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.enriched_profiles import ENGINEERING, TABLES
from powerforge_extraction.enrichment_profiles import PURPOSE
from powerforge_extraction.models import ExtractionRun
from powerforge_extraction.production_profiles import PRODUCTION_PROFILES
from powerforge_extraction.table_profiles import TABLE_PRODUCTION_PROFILES
from powerforge_persistence import Project, ProjectRevision

PROFILE_KEY = RunExecution.configuration["key"].as_string()
FAMILY_PROFILES = {
    "engineering": (*PRODUCTION_PROFILES, ENGINEERING),
    "tables": (*TABLE_PRODUCTION_PROFILES, TABLES),
}
RESULT_STATUSES = ("COMPLETED", "PARTIALLY_COMPLETED")


def revision_read_only(session: Session, project_id: UUID, revision_id: UUID) -> bool:
    context = session.execute(
        select(Project, ProjectRevision)
        .join(ProjectRevision, ProjectRevision.project_id == Project.id)
        .where(Project.id == project_id, ProjectRevision.id == revision_id)
    ).one_or_none()
    if context is None:
        raise RevisionNotFound("Revision not found")
    try:
        assert_revision_mutable(*context)
    except ProjectError:
        return True
    return False


def register_status(
    session: Session, project_id: UUID, revision_id: UUID, ids: list[UUID]
) -> list[DocumentExtractionStatus]:
    read_only = revision_read_only(session, project_id, revision_id)

    # The document viewer serves artifacts from the completed run of DEFAULT_PROFILE.
    # Only one completed/live processing run is allowed for that document and profile.
    processing = DocumentProcessingRun
    associations = session.execute(
        select(
            RevisionDocument,
            processing.id.label("processing_run_id"),
            exists(
                select(PageArtifact.id).where(
                    PageArtifact.processing_run_id == processing.id,
                    PageArtifact.artifact_type == "ANALYSIS_IMAGE",
                )
            ).label("has_image"),
        )
        .outerjoin(
            processing,
            and_(
                processing.document_id == RevisionDocument.document_id,
                processing.processor_version == DEFAULT_PROFILE.processor_version,
                processing.profile_hash == DEFAULT_PROFILE.profile_hash,
                processing.status == "COMPLETED",
            ),
        )
        .where(
            RevisionDocument.project_id == project_id,
            RevisionDocument.revision_id == revision_id,
            RevisionDocument.id.in_(ids),
        )
    ).all()
    status_by_id = {}
    included = {}
    processing_ids = []
    for association, processing_id, has_image in associations:
        reason = None
        if association.status != "INCLUDED":
            reason = "REMOVED"
        else:
            included[association.document_id] = association.id
            if processing_id:
                processing_ids.append(processing_id)
            if read_only:
                reason = "READ_ONLY"
            elif not processing_id:
                reason = "PROCESSING_REQUIRED"
            elif not has_image:
                reason = "NO_PAGE_ARTIFACTS"
        status_by_id[association.id] = DocumentExtractionStatus(
            revision_document_id=association.id,
            processing_run_id=processing_id if association.status == "INCLUDED" else None,
            ineligible_reason=reason,
        )

    if not included:
        return [status_by_id[id_] for id_ in dict.fromkeys(ids) if id_ in status_by_id]

    run = ExtractionRun
    family = case(
        (run.execution_purpose == PURPOSE, "enrichment"),
        (PROFILE_KEY.in_(FAMILY_PROFILES["engineering"]), "engineering"),
        else_="tables",
    )
    order = (run.created_at.desc(), run.id.desc())
    effective = and_(run.processing_run_id.in_(processing_ids), run.status.in_(RESULT_STATUSES))
    ranked = (
        select(
            run.id,
            run.document_id,
            run.status,
            run.processing_run_id,
            run.created_at,
            PROFILE_KEY.label("profile_key"),
            family.label("family"),
            effective.label("effective"),
            func.row_number()
            .over(partition_by=(run.document_id, family), order_by=order)
            .label("attempt_rank"),
            func.row_number()
            .over(partition_by=(run.document_id, family, effective), order_by=order)
            .label("result_rank"),
        )
        .join(RunExecution, RunExecution.run_id == run.id)
        .where(
            run.document_id.in_(included),
            or_(run.context_revision_id.is_(None), run.context_revision_id == revision_id),
            or_(
                and_(run.execution_purpose == PURPOSE, run.processing_run_id.in_(processing_ids)),
                and_(
                    run.execution_purpose == "EXTRACTION",
                    run.provider == "openai",
                    PROFILE_KEY.in_([*FAMILY_PROFILES["engineering"], *FAMILY_PROFILES["tables"]]),
                ),
            ),
        )
        .subquery()
    )
    for row in session.execute(
        select(ranked).where(
            or_(ranked.c.attempt_rank == 1, and_(ranked.c.effective, ranked.c.result_rank == 1))
        )
    ):
        status = status_by_id[included[row.document_id]]
        value = RegisterRun.model_validate(row)
        if row.family == "enrichment":
            if row.attempt_rank == 1:
                status.enrichment = value
        else:
            runs = status.engineering if row.family == "engineering" else status.tables
            if row.attempt_rank == 1:
                runs.latest_attempt = value
            if row.effective and row.result_rank == 1:
                runs.effective_result = value

    return [status_by_id[id_] for id_ in dict.fromkeys(ids) if id_ in status_by_id]
