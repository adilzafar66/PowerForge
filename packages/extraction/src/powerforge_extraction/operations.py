"""Advance reviewed Phase 6F intents using the existing per-document coordinators."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    RevisionDocument,
)
from powerforge_document_processing.storage.base import StorageError
from powerforge_extraction.enrichment_execution import read_exact
from powerforge_extraction.enrichment_profiles import PURPOSE
from powerforge_extraction.enrichment_service import preparation_identity, source_snapshot
from powerforge_extraction.errors import ExtractionConflict, ExtractionError, ExtractionNotFound
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.layout_models import SourceSpatialResult
from powerforge_extraction.layout_profiles import layout_profile
from powerforge_extraction.layout_service import start_layout
from powerforge_extraction.models import ExtractionRun
from powerforge_extraction.operation_models import (
    ExtractionOperation,
    OperationItem,
    OperationRequest,
)
from powerforge_extraction.operation_plan import (
    OperationPolicy,
    PlannedDocument,
    compatible_pair,
    preview_operation,
)
from powerforge_extraction.orchestration import ACTIVE, ExtractionCoordinator
from powerforge_extraction.phase6r_profile import phase6r_profile
from powerforge_persistence import Project, ProjectRevision

logger = logging.getLogger(__name__)


def now(session):
    return session.scalar(select(func.clock_timestamp()))


def admit_operation(
    session, settings, project_id, revision_id, request_key, review_hash, selection
):
    """Called with the revision write lock. One transaction binds consent and its inputs."""
    request_hash = identity_hash(
        {"selection": selection.model_dump(mode="json"), "review": review_hash}
    )
    previous = session.get(OperationRequest, (revision_id, request_key))
    if previous:
        if previous.request_hash != request_hash:
            raise ExtractionConflict("This submission key was used for a different review.")
        return session.get(ExtractionOperation, previous.operation_id)

    preview = preview_operation(session, settings, project_id, revision_id, selection)
    if preview.review_hash is None or preview.review_hash != review_hash:
        raise ExtractionConflict(
            "The reviewed extraction plan changed. Review it before submitting."
        )
    policy = preview.policy.model_dump(mode="json")
    intent = identity_hash(
        {
            "selection": selection.model_dump(mode="json"),
            "profile_hash": policy["profile_hash"],
            "layout": policy["layout_profile_hash"],
            "page_identities": [
                [page.preparation_hash for page in item.pages] for item in preview.documents
            ],
        }
    )
    operation = session.scalar(
        select(ExtractionOperation).where(
            ExtractionOperation.revision_id == revision_id,
            ExtractionOperation.intent_hash == intent,
            ExtractionOperation.next_check_at.is_not(None),
            ExtractionOperation.cancel_requested_at.is_(None),
        )
    )
    if operation is None:
        operation = ExtractionOperation(
            project_id=project_id,
            revision_id=revision_id,
            intent_hash=intent,
            policy=policy,
            next_check_at=now(session),
        )
        session.add(operation)
        session.flush()
        for item in preview.documents:
            session.add(
                OperationItem(
                    operation_id=operation.id,
                    revision_document_id=item.selection.revision_document_id,
                    document_id=item.document_id,
                    processing_run_id=item.selection.processing_run_id,
                    selection=item.model_dump(mode="json"),
                )
            )
    session.add(
        OperationRequest(
            revision_id=revision_id,
            request_key=request_key,
            operation_id=operation.id,
            request_hash=request_hash,
        )
    )
    session.flush()
    return operation


def get_operation(session, project_id, revision_id, operation_id, *, lock=False):
    stmt = select(ExtractionOperation).where(
        ExtractionOperation.id == operation_id,
        ExtractionOperation.project_id == project_id,
        ExtractionOperation.revision_id == revision_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    operation = session.scalar(stmt)
    if operation is None:
        raise ExtractionNotFound("Extraction operation not found.")
    return operation


def included(association, operation, item):
    return (
        association is not None
        and association.status == "INCLUDED"
        and association.project_id == operation.project_id
        and association.revision_id == operation.revision_id
        and association.document_id == item.document_id
    )


def items_for(session, operation):
    return session.scalars(
        select(OperationItem)
        .where(OperationItem.operation_id == operation.id)
        .order_by(OperationItem.revision_document_id)
    ).all()


def child_runs(session, items):
    ids = {
        run_id
        for item in items
        for run_id in (item.layout_run_id, item.extraction_run_id)
        if run_id
    }
    if not ids:
        return {}
    return {
        run.id: run
        for run in session.scalars(select(ExtractionRun).where(ExtractionRun.id.in_(ids)))
    }


def active_child(item, runs):
    return any(
        run_id in runs and runs[run_id].status in ACTIVE
        for run_id in (item.layout_run_id, item.extraction_run_id)
    )


def ready_to_admit(item, runs):
    if item.blocked_reason or item.extraction_run_id:
        return False
    return item.layout_run_id is None or runs[item.layout_run_id].status == "COMPLETED"


class OperationAdmission(ExtractionCoordinator):
    """Distinguish new admissions from pre-existing runs returned by ensure."""

    def __init__(self, session, settings):
        super().__init__(session, settings)
        self.created = set()

    def _delivery(self, unit, available):
        super()._delivery(unit, available)
        self.created.add(unit.run_id)


def verify_plan_sources(session, planned, layout):
    document = session.get(Document, planned.document_id)
    processing = session.get(DocumentProcessingRun, planned.selection.processing_run_id)
    if not processing or processing.status != "COMPLETED" or processing.document_id != document.id:
        raise ExtractionConflict("The pinned processing run is unavailable.")
    for page in planned.pages:
        actual_page = session.get(DocumentPage, page.document_page_id)
        if (
            actual_page is None
            or actual_page.document_id != document.id
            or actual_page.page_number != page.page_number
        ):
            raise ExtractionConflict("The pinned source page is unavailable.")
        _, original, base, _ = source_snapshot(session, document, processing, actual_page)
        if (
            preparation_identity(
                layout.preparation,
                original,
                base,
                force_ocr=page.page_number in planned.selection.force_ocr_pages,
            )
            != page.preparation_hash
        ):
            raise ExtractionConflict("The pinned source artifacts changed.")


def advance_item(session, settings, item, policy, verification):
    if (
        not settings.enrichment_enabled
        or not settings.extraction_enabled
        or not settings.extraction_phase6r_fake
    ):
        item.blocked_reason = "PROCESSING_DISABLED"
        return
    layout = layout_profile(settings)
    if (
        layout.identity_hash != policy.layout_profile_hash
        or phase6r_profile(settings).identity_hash != policy.profile_hash
    ):
        item.blocked_reason = "PROFILE_CHANGED"
        return

    planned = PlannedDocument.model_validate(item.selection)
    missing = [page for page in planned.pages if not page.spatial_result_id]
    if missing and not item.layout_run_id:
        verify_plan_sources(session, planned, layout)
        pages = [page.page_number for page in missing]
        run = start_layout(
            session,
            settings,
            item.document_id,
            item.processing_run_id,
            pages,
            sorted(set(planned.selection.force_ocr_pages).intersection(pages)),
            item.revision_document_id,
            prepared_result_ids=[
                page.prepared_result_id for page in missing if page.prepared_result_id
            ],
            allow_partial_prepared=True,
        )
        item.layout_run_id = run.id
        return

    if verification is None or verification.document_id != item.revision_document_id:
        return
    if verification.error:
        item.blocked_reason = verification.error
        return
    verify_plan_sources(session, planned, layout)
    snapshots = bound_sources(session, item, planned, layout.algorithm_sha256)
    if references(snapshots) != verification.bindings:
        return
    bindings = [
        {"prepared_result_id": prepared_id, "spatial_result_id": spatial_id}
        for prepared_id, spatial_id in verification.bindings
    ]

    coordinator = OperationAdmission(session, settings)
    run = coordinator.start(
        item.document_id,
        revision_document_id=item.revision_document_id,
        pages=planned.selection.pages,
        mode=policy.mode,
        enrichment_bindings=bindings,
    )
    item.extraction_run_id = run.id
    item.owns_extraction = run.id in coordinator.created
    session.flush()


def bound_sources(session, item, planned, layout_hash):
    generated = (
        {
            row.document_page_id: row
            for row in session.scalars(
                select(SourceSpatialResult).where(SourceSpatialResult.run_id == item.layout_run_id)
            )
        }
        if item.layout_run_id
        else {}
    )
    snapshots = []
    for page in planned.pages:
        if page.spatial_result_id:
            prepared_id, spatial_id = page.prepared_result_id, page.spatial_result_id
        else:
            result = generated.get(page.document_page_id)
            if result is None:
                raise ExtractionConflict("A required layout result is missing.")
            prepared_id, spatial_id = result.prepared_result_id, result.id
        snapshots.append(
            compatible_pair(
                session,
                page,
                prepared_id,
                spatial_id,
                layout_hash,
                item.processing_run_id,
            )
        )

    return snapshots


def references(snapshots):
    return tuple((source.prepared.manifest.id, source.layout.id) for source in snapshots)


@dataclass(frozen=True)
class Verification:
    document_id: UUID
    bindings: tuple[tuple[UUID, UUID], ...] = ()
    error: str | None = None


def verify_ready_document(factory, settings, storage, operation_id):
    """Check one ready document per scan without holding scheduling or publication locks."""
    if not settings.enrichment_enabled or not settings.extraction_phase6r_fake:
        return None
    try:
        layout = layout_profile(settings)
    except (ValueError, KeyError):
        return None
    with factory() as session:
        operation = session.get(ExtractionOperation, operation_id)
        if operation is None or operation.cancel_requested_at:
            return None
        policy = OperationPolicy.model_validate(operation.policy)
        items = items_for(session, operation)
        runs = child_runs(session, items)
        if sum(active_child(item, runs) for item in items) >= policy.parallel_documents:
            return None
        for item in items:
            if not ready_to_admit(item, runs):
                continue
            association = session.get(RevisionDocument, item.revision_document_id)
            if not included(association, operation, item):
                continue
            planned = PlannedDocument.model_validate(item.selection)
            if not item.layout_run_id and any(not page.spatial_result_id for page in planned.pages):
                continue
            document_id = item.revision_document_id
            try:
                snapshots = bound_sources(session, item, planned, layout.algorithm_sha256)
            except (ExtractionError, ValueError, KeyError, StopIteration):
                return Verification(document_id, error="EXACT_SOURCE_REQUIRED")
            break
        else:
            return None

    # The locked admission pass rechecks these same result IDs and manifests.
    try:
        for snapshot in snapshots:
            read_exact(
                storage, snapshot.image_key, snapshot.image.size_bytes, snapshot.image.sha256
            )
            read_exact(storage, snapshot.spatial_key, snapshot.spatial_size, snapshot.spatial_hash)
            for descriptor, key in snapshot.prepared.objects:
                read_exact(storage, key, descriptor.size_bytes, descriptor.sha256)
    except (StorageError, ValueError):
        return Verification(document_id, error="SOURCE_ARTIFACT_UNAVAILABLE")
    return Verification(document_id, references(snapshots))


def writable(project, revision):
    return (
        project is not None
        and revision is not None
        and project.status not in {"ARCHIVED", "CANCELLED"}
        and revision.status != "SUPERSEDED"
    )


def reconcile_operation(session, settings, operation_id, project_id, revision_id, verification):
    # Match API lock ordering: project, revision, then operation. Membership changes
    # require a revision write lock, so they cannot race a downstream admission.
    project = session.scalar(
        select(Project).where(Project.id == project_id).with_for_update(read=True)
    )
    revision = session.scalar(
        select(ProjectRevision)
        .where(
            ProjectRevision.project_id == project_id,
            ProjectRevision.id == revision_id,
        )
        .with_for_update(read=True)
    )
    operation = session.scalar(
        select(ExtractionOperation)
        .where(
            ExtractionOperation.id == operation_id,
            ExtractionOperation.next_check_at <= now(session),
        )
        .with_for_update(skip_locked=True)
    )
    if operation is None:
        return
    policy = OperationPolicy.model_validate(operation.policy)
    items = items_for(session, operation)
    runs = child_runs(session, items)
    active = sum(active_child(item, runs) for item in items)
    slots = max(0, policy.parallel_documents - active)
    for item in items:
        association = session.get(RevisionDocument, item.revision_document_id)
        if not included(association, operation, item):
            item.blocked_reason = "SOURCE_UNAVAILABLE"
            continue
        if not writable(project, revision):
            if not item.extraction_run_id:
                item.blocked_reason = "REVISION_READ_ONLY"
            continue
        if not slots or operation.cancel_requested_at or not ready_to_admit(item, runs):
            continue
        try:
            with session.begin_nested():
                advance_item(session, settings, item, policy, verification)
        except (ExtractionError, ValueError, KeyError, StopIteration):
            item.blocked_reason = "EXACT_SOURCE_REQUIRED"
        # Only active documents consume a slot. Terminal reuse and failed sources
        # allow other documents to proceed in the same pass.
        new_runs = child_runs(session, [item])
        runs.update(new_runs)
        if active_child(item, new_runs):
            slots -= 1
    waiting = any(
        active_child(item, runs)
        or (not operation.cancel_requested_at and ready_to_admit(item, runs))
        for item in items
    )
    operation.next_check_at = (
        now(session) + timedelta(seconds=settings.extraction_recovery_interval_seconds)
        if waiting
        else None
    )


def reconcile_operations(factory, settings, storage, limit=20):
    """Fair bounded scan. Each operation commits independently of broker delivery."""
    with factory() as session:
        due = session.execute(
            select(
                ExtractionOperation.id,
                ExtractionOperation.project_id,
                ExtractionOperation.revision_id,
            )
            .where(ExtractionOperation.next_check_at <= now(session))
            .order_by(ExtractionOperation.next_check_at, ExtractionOperation.id)
            .limit(limit)
        ).all()
    for identity in due:
        try:
            verification = verify_ready_document(factory, settings, storage, identity.id)
            with factory.begin() as session:
                reconcile_operation(session, settings, *identity, verification)
        except SQLAlchemyError as exc:
            logger.warning("Extraction operation reconciliation deferred (%s)", type(exc).__name__)


def cancel_operation(session, settings, operation):
    if operation.cancel_requested_at is None and operation.next_check_at is not None:
        operation.cancel_requested_at = now(session)
        coordinator = ExtractionCoordinator(session, settings)
        for item in items_for(session, operation):
            if item.owns_extraction:
                run = coordinator._run(item.extraction_run_id)
                if run.status in ACTIVE:
                    coordinator.cancel(run.id)
        operation.next_check_at = None


def retry_operation_item(
    session,
    settings,
    operation,
    revision_document_id,
    step,
    expected_attempts,
    acknowledge_unknown,
    *,
    page_id=None,
    stage=None,
    expected_attempt=None,
):
    if operation.cancel_requested_at:
        raise ExtractionConflict("A cancelled operation cannot be retried.")
    item = session.get(OperationItem, (operation.id, revision_document_id))
    association = session.get(RevisionDocument, revision_document_id)
    if item is None or not included(association, operation, item):
        raise ExtractionNotFound("Extraction operation source not found.")
    policy = OperationPolicy.model_validate(operation.policy)
    if operation.next_check_at is None and session.scalar(
        select(ExtractionOperation.id).where(
            ExtractionOperation.id != operation.id,
            ExtractionOperation.revision_id == operation.revision_id,
            ExtractionOperation.intent_hash == operation.intent_hash,
            ExtractionOperation.next_check_at.is_not(None),
            ExtractionOperation.cancel_requested_at.is_(None),
        )
    ):
        raise ExtractionConflict("An identical operation is already active.")
    if step == "resume":
        if item.blocked_reason not in {
            "PROCESSING_DISABLED",
            "PROVIDER_UNAVAILABLE",
            "EXACT_SOURCE_REQUIRED",
            "SOURCE_ARTIFACT_UNAVAILABLE",
        }:
            raise ExtractionConflict("This source requires a new review before it can be started.")
        item.blocked_reason = None
    else:
        if step != "layout" and step != "extraction":
            raise ExtractionNotFound("Extraction operation step not found.")
        run_id = getattr(item, f"{step}_run_id")
        if not run_id:
            raise ExtractionConflict("This step has not been admitted.")
        coordinator = ExtractionCoordinator(session, settings)
        run = coordinator._run(run_id)
        if stage is None and len(coordinator._units(run.id)) != expected_attempts:
            return  # This action was based on an older attempt list.
        if run.status not in ACTIVE:
            runs = child_runs(session, items_for(session, operation))
            if sum(
                active_child(source, runs) for source in items_for(session, operation)
            ) >= policy.parallel_documents and not active_child(item, runs):
                raise ExtractionConflict(
                    "All operation document slots are busy. Try again when a document finishes."
                )
        coordinator.retry(
            run.id,
            purpose=PURPOSE if step == "layout" else "EXTRACTION",
            acknowledge_unknown_outcome=acknowledge_unknown,
            page_id=page_id,
            stage=stage,
            expected_attempt=expected_attempt,
        )
        item.blocked_reason = None
    operation.next_check_at = now(session)
