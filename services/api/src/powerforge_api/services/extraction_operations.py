"""Scoped operation read models. Only live included items expose source and run details."""

from sqlalchemy import select

from powerforge_document_processing.models import Document, RevisionDocument
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.dependencies import latest_units, retryable_keys
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.operation_models import UNKNOWN_PROVIDER_OUTCOME
from powerforge_extraction.operation_plan import OperationPolicy, PlannedDocument
from powerforge_extraction.operations import child_runs, included, items_for
from powerforge_extraction.orchestration import ACTIVE


def describe_run(session, run, settings, can_write):
    units = session.scalars(
        select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run.id)
    ).all()
    control = session.get(RunExecution, run.id)
    enabled = (
        settings.enrichment_enabled
        if run.provider == "local"
        else (settings.extraction_enabled and settings.extraction_external_enabled)
    )
    keys = retryable_keys(units, control.configuration["max_attempts"]) if control else set()
    return {
        "run_id": run.id,
        "status": run.status,
        "error_code": run.error_code,
        "attempts": len(units),
        "unknown_provider_outcome": any(
            unit.error_code == UNKNOWN_PROVIDER_OUTCOME for unit in latest_units(units).values()
        ),
        "can_retry": bool(
            can_write
            and enabled
            and keys
            and run.status in {"FAILED", "PARTIALLY_COMPLETED"}
            and control.calls_admitted < control.configuration["max_calls"]
        ),
    }


def pending_step(status):
    return {
        "run_id": None,
        "status": status,
        "error_code": None,
        "attempts": 0,
        "unknown_provider_outcome": False,
        "can_retry": False,
    }


def item_status(layout, children, blocked, cancelled):
    statuses = [child["status"] for child in children.values()]
    if "RUNNING" in statuses or layout["status"] == "RUNNING":
        return "RUNNING"
    if "PENDING" in statuses or layout["status"] == "PENDING":
        return "QUEUED"
    if all(status == "COMPLETED" for status in statuses):
        return "COMPLETED"
    if any(status in {"COMPLETED", "PARTIALLY_COMPLETED"} for status in statuses):
        return "PARTIAL"
    if cancelled or all(status == "CANCELLED" for status in statuses):
        return "CANCELLED"
    if blocked:
        return "BLOCKED"
    if any(status in {"FAILED", "CANCELLED"} for status in statuses):
        return "FAILED"
    return "QUEUED"


def operation_status(states, cancelled):
    if "RUNNING" in states:
        return "RUNNING"
    if "QUEUED" in states:
        return "QUEUED"
    if states and all(state == "COMPLETED" for state in states):
        return "COMPLETED"
    if cancelled:
        return "CANCELLED"
    if any(state in {"COMPLETED", "PARTIAL"} for state in states):
        return "PARTIAL"
    if "BLOCKED" in states:
        return "BLOCKED"
    return "FAILED" if "FAILED" in states else "CANCELLED"


def operation_detail(session, settings, operation, *, can_write):
    policy = OperationPolicy.model_validate(operation.policy)
    rows = items_for(session, operation)
    associations = {
        row.id: row
        for row in session.scalars(
            select(RevisionDocument).where(
                RevisionDocument.id.in_([item.revision_document_id for item in rows])
            )
        )
    }
    visible = [
        item
        for item in rows
        if included(associations.get(item.revision_document_id), operation, item)
    ]
    documents = {
        row.id: row.original_filename
        for row in session.scalars(
            select(Document).where(Document.id.in_([item.document_id for item in visible]))
        )
    }
    runs = child_runs(session, visible)
    cancelled = operation.cancel_requested_at is not None
    descriptions = {
        run_id: describe_run(session, run, settings, can_write and not cancelled)
        for run_id, run in runs.items()
        if run.context_revision_id in (None, operation.revision_id)
    }
    can_cancel = False
    items = []
    for item in visible:
        planned = PlannedDocument.model_validate(item.selection)
        layout = descriptions.get(item.layout_run_id)
        local_ready = all(page.spatial_result_id for page in planned.pages)
        layout_blocked = layout and layout["status"] not in (*ACTIVE, "COMPLETED")
        blocked = item.blocked_reason or ("PREPARATION_UNSUCCESSFUL" if layout_blocked else None)
        waiting = "CANCELLED" if cancelled else "BLOCKED" if blocked else "WAITING"
        if layout is None:
            layout = pending_step("REUSED" if local_ready else waiting)
        families = {
            family: descriptions.get(getattr(item, f"{family}_run_id"), pending_step(waiting))
            for family in policy.profiles
        }
        can_cancel |= waiting == "WAITING" and any(not run["run_id"] for run in families.values())
        items.append(
            {
                "revision_document_id": item.revision_document_id,
                "filename": documents[item.document_id],
                "processing_run_id": item.processing_run_id,
                "pages": planned.selection.pages,
                "force_ocr_pages": planned.selection.force_ocr_pages,
                "status": item_status(layout, families, blocked, cancelled),
                "blocked_reason": blocked,
                "can_resume": can_write
                and not cancelled
                and item.blocked_reason
                in {
                    "PROCESSING_DISABLED",
                    "PROVIDER_UNAVAILABLE",
                    "EXACT_SOURCE_REQUIRED",
                    "SOURCE_ARTIFACT_UNAVAILABLE",
                },
                "layout": layout,
                "profiles": families,
            }
        )
    unavailable = len(rows) - len(visible)
    return {
        "id": operation.id,
        "created_at": operation.created_at,
        "status": operation_status(
            [item["status"] for item in items] + ["BLOCKED"] * unavailable, cancelled
        ),
        "cancel_requested": cancelled,
        "can_cancel": can_write and can_cancel,
        "mode": policy.mode,
        "provider_admissions": policy.provider_admissions,
        "unavailable_sources": unavailable,
        "items": items,
    }
