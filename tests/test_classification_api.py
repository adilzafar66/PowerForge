"""Classification reads, accept, reclassify, and provenance.

Integration cases need RUN_INTEGRATION=1.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select

from documents_support import client, code, docs_url, make_revision, upload
from powerforge_api.db import get_session_factory
from powerforge_api.main import create_app
from powerforge_document_classification.enqueue import get_classification_enqueue
from powerforge_document_classification.service import ClassificationService
from powerforge_document_model import (
    ClassificationRunStatus,
    ClassificationScope,
    ConfidenceBand,
    DocumentClassification,
    ProcessingRunStatus,
    SourceUnit,
)
from powerforge_document_processing.models import (
    ClassificationPrediction,
    DocumentClassificationRun,
    DocumentPage,
    DocumentProcessingRun,
    RevisionDocument,
)
from powerforge_shared.config import Settings, get_settings

_EMPTY = {"enabled": False, "suggestion": None, "attempt": None}


class _RecordingEnqueue:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enqueue_document_classification(self, run_id: object) -> None:
        self.calls.append(str(run_id))


@pytest.fixture
def classification_http(ctx: dict[str, Any]) -> Any:
    recorded = _RecordingEnqueue()
    app = client.app
    app.dependency_overrides[get_classification_enqueue] = lambda: recorded
    app.dependency_overrides[get_settings] = lambda: Settings(ai_classification_enabled=False)

    def enable() -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(ai_classification_enabled=True)

    ctx["enqueue"] = recorded
    ctx["enable"] = enable
    try:
        yield ctx
    finally:
        app.dependency_overrides.pop(get_classification_enqueue, None)
        app.dependency_overrides.pop(get_settings, None)


def test_openapi_lists_classification_routes() -> None:
    paths = create_app().openapi()["paths"]
    suffixes = (
        "/classification",
        "/classification/runs",
        "/classification/pages",
        "/classification/reclassify",
        "/classification/runs/{run_id}/retry",
        "/classification/predictions/{prediction_id}/accept",
    )
    for suffix in suffixes:
        assert any(path.endswith(suffix) for path in paths), suffix


def test_list_detail_and_upload_include_classification(classification_http: dict[str, Any]) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    assert client.get(docs_url(project_id, revision_id)).json()["items"] == []

    created = upload(project_id, revision_id)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["classification"] == _EMPTY
    assert body["document_type"] == "UNKNOWN"

    listed = client.get(docs_url(project_id, revision_id)).json()["items"]
    assert listed[0]["classification"] == _EMPTY
    detail = client.get(_doc(project_id, revision_id, body["id"])).json()
    assert detail["classification"] == _EMPTY


def test_list_loads_classification_summaries_once(
    classification_http: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    first = upload(project_id, revision_id, filename="a.pdf").json()
    second = upload(project_id, revision_id, filename="b.pdf").json()
    _complete_processing(first["document"]["id"])
    processing_id = _complete_processing(second["document"]["id"])
    seeded = _add_run(second["document"]["id"], processing_id)

    calls: list[list[object]] = []
    original = ClassificationService.summaries_for_documents

    def spy(self: ClassificationService, document_ids: Any) -> Any:
        calls.append(list(document_ids))
        return original(self, document_ids)

    monkeypatch.setattr(ClassificationService, "summaries_for_documents", spy)
    listed = client.get(docs_url(project_id, revision_id))
    assert listed.status_code == 200, listed.text
    assert len(calls) == 1
    assert {str(document_id) for document_id in calls[0]} == {
        first["document"]["id"],
        second["document"]["id"],
    }
    by_id = {item["id"]: item for item in listed.json()["items"]}
    assert by_id[first["id"]]["classification"]["suggestion"] is None
    suggestion = by_id[second["id"]]["classification"]["suggestion"]
    assert suggestion["prediction_id"] == seeded["prediction_id"]
    assert suggestion["predicted_type"] == "SINGLE_LINE_DIAGRAM"
    assert suggestion["accepted"] is False
    assert suggestion["confidence_band"] == "HIGH"
    assert by_id[second["id"]]["classification"]["attempt"]["id"] == seeded["run_id"]


def test_completed_suggestion_remains_after_failed_and_inflight_reclassify(
    classification_http: dict[str, Any],
) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    body = upload(project_id, revision_id).json()
    processing_id = _complete_processing(body["document"]["id"])
    moment = datetime.now(UTC) - timedelta(minutes=5)
    completed = _add_run(body["document"]["id"], processing_id, created_at=moment)
    failed_run = _add_run(
        body["document"]["id"],
        processing_id,
        status=ClassificationRunStatus.FAILED,
        error_code="PROVIDER_TIMEOUT",
        predicted_type=None,
        created_at=moment + timedelta(seconds=2),
    )

    failed = client.get(_doc(project_id, revision_id, body["id"], "/classification")).json()
    assert failed["suggestion"]["prediction_id"] == completed["prediction_id"]
    assert failed["suggestion"]["predicted_type"] == "SINGLE_LINE_DIAGRAM"
    assert failed["attempt"]["id"] == failed_run["run_id"]
    assert failed["attempt"]["status"] == "FAILED"
    assert failed["attempt"]["error_code"] == "PROVIDER_TIMEOUT"
    assert failed["confidence_score"] == pytest.approx(0.95)
    assert body["document_type"] == "UNKNOWN"

    classification_http["enable"]()
    started = client.post(_doc(project_id, revision_id, body["id"], "/classification/reclassify"))
    assert started.status_code == 200, started.text
    again = started.json()
    assert again["suggestion"]["prediction_id"] == completed["prediction_id"]
    assert again["suggestion"]["predicted_type"] == "SINGLE_LINE_DIAGRAM"
    assert again["attempt"]["id"] == classification_http["enqueue"].calls[0]
    assert again["attempt"]["status"] == "PENDING"
    detail = client.get(_doc(project_id, revision_id, body["id"])).json()
    assert detail["document_type"] == "UNKNOWN"
    assert len(classification_http["enqueue"].calls) == 1


def test_accept_sets_type_and_prediction_id(classification_http: dict[str, Any]) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    body = upload(project_id, revision_id).json()
    processing_id = _complete_processing(body["document"]["id"])
    seeded = _add_run(body["document"]["id"], processing_id, rationale="title block")

    accepted = client.post(
        _doc(
            project_id,
            revision_id,
            body["id"],
            f"/classification/predictions/{seeded['prediction_id']}/accept",
        )
    )
    assert accepted.status_code == 200, accepted.text
    payload = accepted.json()
    assert payload["document_type"] == "SINGLE_LINE_DIAGRAM"
    assert payload["classification"]["suggestion"]["prediction_id"] == seeded["prediction_id"]
    assert payload["classification"]["suggestion"]["accepted"] is True
    assert _accepted_id(body["id"]) == seeded["prediction_id"]
    detail = client.get(_doc(project_id, revision_id, body["id"], "/classification")).json()
    assert detail["rationale"] == "title block"
    assert detail["alternatives"] == [{"type": "PANEL_SCHEDULE", "score": 0.2}]


def test_accept_rejects_cross_document_page_and_failed_run(
    classification_http: dict[str, Any],
) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    first = upload(project_id, revision_id, filename="a.pdf").json()
    second = upload(project_id, revision_id, filename="b.pdf").json()
    processing_id = _complete_processing(first["document"]["id"])
    _complete_processing(second["document"]["id"])
    seeded = _add_run(first["document"]["id"], processing_id, page=True)
    failed = _add_run(
        first["document"]["id"],
        processing_id,
        status=ClassificationRunStatus.FAILED,
        error_code="PROVIDER_UNAVAILABLE",
    )

    missing = client.post(
        _doc(
            project_id,
            revision_id,
            first["id"],
            f"/classification/predictions/{uuid.uuid4()}/accept",
        )
    )
    assert (missing.status_code, code(missing)) == (404, "classification_prediction_not_found")

    cross = client.post(
        _doc(
            project_id,
            revision_id,
            second["id"],
            f"/classification/predictions/{seeded['prediction_id']}/accept",
        )
    )
    assert (cross.status_code, code(cross)) == (404, "classification_prediction_not_found")

    page = client.post(
        _doc(
            project_id,
            revision_id,
            first["id"],
            f"/classification/predictions/{seeded['page_prediction_id']}/accept",
        )
    )
    assert (page.status_code, code(page)) == (409, "classification_not_acceptable")

    failed_accept = client.post(
        _doc(
            project_id,
            revision_id,
            first["id"],
            f"/classification/predictions/{failed['prediction_id']}/accept",
        )
    )
    assert (failed_accept.status_code, code(failed_accept)) == (
        409,
        "classification_not_acceptable",
    )
    unchanged = client.get(_doc(project_id, revision_id, first["id"])).json()
    assert unchanged["document_type"] == "UNKNOWN"


def test_classification_does_not_change_document_type(classification_http: dict[str, Any]) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    body = upload(project_id, revision_id, document_type="PANEL_SCHEDULE").json()
    processing_id = _complete_processing(body["document"]["id"])
    _add_run(body["document"]["id"], processing_id)
    detail = client.get(_doc(project_id, revision_id, body["id"])).json()
    assert detail["document_type"] == "PANEL_SCHEDULE"
    assert detail["classification"]["suggestion"]["predicted_type"] == "SINGLE_LINE_DIAGRAM"
    assert detail["classification"]["suggestion"]["accepted"] is False


def test_submitting_the_same_document_type_clears_the_prediction_id(
    classification_http: dict[str, Any],
) -> None:
    project_id, revision_id, body, seeded = _accepted_document(classification_http)
    patched = client.patch(
        _doc(project_id, revision_id, body["id"]),
        json={"document_type": "SINGLE_LINE_DIAGRAM"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["document_type"] == "SINGLE_LINE_DIAGRAM"
    assert patched.json()["classification"]["suggestion"]["accepted"] is False
    assert _accepted_id(body["id"]) is None
    assert seeded["prediction_id"]


def test_omitting_document_type_keeps_the_prediction_id(
    classification_http: dict[str, Any],
) -> None:
    project_id, revision_id, body, seeded = _accepted_document(classification_http)
    patched = client.patch(_doc(project_id, revision_id, body["id"]), json={"notes": "kept"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["classification"]["suggestion"]["accepted"] is True
    assert patched.json()["notes"] == "kept"
    assert _accepted_id(body["id"]) == seeded["prediction_id"]


def test_inheritance_copies_the_prediction_id(classification_http: dict[str, Any]) -> None:
    project_id, revision_id, body, seeded = _accepted_document(classification_http)
    child = make_revision(project_id, "1")
    assert child.status_code == 201, child.text
    listed = client.get(docs_url(project_id, child.json()["id"])).json()["items"]
    assert len(listed) == 1
    copied = listed[0]
    assert copied["document"]["id"] == body["document"]["id"]
    assert copied["document_type"] == "SINGLE_LINE_DIAGRAM"
    assert copied["classification"]["suggestion"]["accepted"] is True
    assert _accepted_id(copied["id"]) == seeded["prediction_id"]
    assert _accepted_id(body["id"]) == seeded["prediction_id"]


def test_reuse_copies_the_prediction_id_unless_type_is_overridden(
    classification_http: dict[str, Any],
) -> None:
    project_id, _revision_id, body, seeded = _accepted_document(classification_http)
    plain = make_revision(project_id, "plain", based_on_revision_id=None)
    assert plain.status_code == 201, plain.text
    reused = client.post(
        f"{docs_url(project_id, plain.json()['id'])}/reuse",
        json={"source_revision_document_id": body["id"]},
    )
    assert reused.status_code == 201, reused.text
    assert reused.json()["document_type"] == "SINGLE_LINE_DIAGRAM"
    assert reused.json()["classification"]["suggestion"]["accepted"] is True
    assert _accepted_id(reused.json()["id"]) == seeded["prediction_id"]

    overridden = make_revision(project_id, "override", based_on_revision_id=None)
    assert overridden.status_code == 201, overridden.text
    changed = client.post(
        f"{docs_url(project_id, overridden.json()['id'])}/reuse",
        json={
            "source_revision_document_id": body["id"],
            "document_type": "PANEL_SCHEDULE",
        },
    )
    assert changed.status_code == 201, changed.text
    assert changed.json()["document_type"] == "PANEL_SCHEDULE"
    assert changed.json()["classification"]["suggestion"]["accepted"] is False
    assert _accepted_id(changed.json()["id"]) is None


def test_superseded_and_archived_can_read_and_cannot_accept(
    classification_http: dict[str, Any],
) -> None:
    project_id, revision_id, body, seeded = _accepted_document(classification_http)
    child = make_revision(project_id, "1")
    assert child.status_code == 201, child.text
    activated = client.post(
        f"/api/projects/{project_id}/revisions/{child.json()['id']}/activate"
    )
    assert activated.status_code == 200, activated.text

    parent_url = _doc(project_id, revision_id, body["id"], "/classification")
    readable = client.get(parent_url)
    assert readable.status_code == 200, readable.text
    assert readable.json()["suggestion"]["accepted"] is True
    rejected = client.post(
        _doc(
            project_id,
            revision_id,
            body["id"],
            f"/classification/predictions/{seeded['prediction_id']}/accept",
        )
    )
    assert (rejected.status_code, code(rejected)) == (409, "revision_read_only")

    archived = client.post(f"/api/projects/{project_id}/archive")
    assert archived.status_code == 200, archived.text
    child_items = client.get(docs_url(project_id, child.json()["id"])).json()["items"]
    child_doc = child_items[0]
    child_read = client.get(
        _doc(project_id, child.json()["id"], child_doc["id"], "/classification")
    )
    assert child_read.status_code == 200, child_read.text
    child_accept = client.post(
        _doc(
            project_id,
            child.json()["id"],
            child_doc["id"],
            f"/classification/predictions/{seeded['prediction_id']}/accept",
        )
    )
    assert (child_accept.status_code, code(child_accept)) == (409, "archived_project")


def test_removed_can_read_classification(classification_http: dict[str, Any]) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    body = upload(project_id, revision_id).json()
    processing_id = _complete_processing(body["document"]["id"])
    seeded = _add_run(body["document"]["id"], processing_id)
    removed = client.post(_doc(project_id, revision_id, body["id"], "/remove"))
    assert removed.status_code == 200, removed.text

    readable = client.get(_doc(project_id, revision_id, body["id"], "/classification"))
    assert readable.status_code == 200, readable.text
    assert readable.json()["suggestion"]["predicted_type"] == "SINGLE_LINE_DIAGRAM"
    rejected = client.post(
        _doc(
            project_id,
            revision_id,
            body["id"],
            f"/classification/predictions/{seeded['prediction_id']}/accept",
        )
    )
    assert (rejected.status_code, code(rejected)) == (409, "document_removed")


def test_reclassify_and_retry_conflict_cases(classification_http: dict[str, Any]) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    classification_http["enable"]()
    early = upload(project_id, revision_id, filename="early.pdf").json()
    too_soon = client.post(_doc(project_id, revision_id, early["id"], "/classification/reclassify"))
    assert (too_soon.status_code, code(too_soon)) == (409, "processing_not_complete")
    assert _run_count(early["document"]["id"]) == 0

    body = upload(project_id, revision_id).json()
    processing_id = _complete_processing(body["document"]["id"])
    moment = datetime.now(UTC) - timedelta(minutes=5)
    identity = f"seed-{uuid.uuid4().hex}"
    older = _add_run(
        body["document"]["id"],
        processing_id,
        status=ClassificationRunStatus.FAILED,
        error_code="PROVIDER_TIMEOUT",
        identity=identity,
        attempt_number=1,
        created_at=moment,
    )
    newer = _add_run(
        body["document"]["id"],
        processing_id,
        status=ClassificationRunStatus.FAILED,
        error_code="PROVIDER_UNAVAILABLE",
        identity=identity,
        attempt_number=2,
        created_at=moment + timedelta(seconds=2),
    )
    stale = client.post(
        _doc(project_id, revision_id, body["id"], f"/classification/runs/{older['run_id']}/retry")
    )
    assert (stale.status_code, code(stale)) == (409, "classification_not_retryable")

    missing = client.post(
        _doc(project_id, revision_id, body["id"], f"/classification/runs/{uuid.uuid4()}/retry")
    )
    assert (missing.status_code, code(missing)) == (404, "classification_run_not_found")
    foreign = client.post(
        _doc(project_id, revision_id, early["id"], f"/classification/runs/{newer['run_id']}/retry")
    )
    assert (foreign.status_code, code(foreign)) == (404, "classification_run_not_found")

    retried = client.post(
        _doc(project_id, revision_id, body["id"], f"/classification/runs/{newer['run_id']}/retry")
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["attempt"]["status"] == "PENDING"
    assert len(classification_http["enqueue"].calls) == 1

    again = client.post(
        _doc(project_id, revision_id, body["id"], f"/classification/runs/{newer['run_id']}/retry")
    )
    assert (again.status_code, code(again)) == (409, "classification_in_progress")
    assert again.json()["detail"]["run_id"] == classification_http["enqueue"].calls[0]

    fresh = upload(project_id, revision_id, filename="fresh.pdf").json()
    _complete_processing(fresh["document"]["id"])
    started = client.post(_doc(project_id, revision_id, fresh["id"], "/classification/reclassify"))
    assert started.status_code == 200, started.text
    busy = client.post(_doc(project_id, revision_id, fresh["id"], "/classification/reclassify"))
    assert (busy.status_code, code(busy)) == (409, "classification_in_progress")
    assert busy.json()["detail"]["run_id"] == classification_http["enqueue"].calls[1]
    assert len(classification_http["enqueue"].calls) == 2


def test_disabled_reclassify_and_retry_leave_manual_type(
    classification_http: dict[str, Any],
) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    body = upload(project_id, revision_id).json()
    processing_id = _complete_processing(body["document"]["id"])
    failed = _add_run(
        body["document"]["id"],
        processing_id,
        status=ClassificationRunStatus.FAILED,
        error_code="PROVIDER_TIMEOUT",
    )
    before = _run_count(body["document"]["id"])
    reclassify = client.post(
        _doc(project_id, revision_id, body["id"], "/classification/reclassify")
    )
    retry = client.post(
        _doc(project_id, revision_id, body["id"], f"/classification/runs/{failed['run_id']}/retry")
    )
    assert (reclassify.status_code, code(reclassify)) == (409, "ai_classification_disabled")
    assert (retry.status_code, code(retry)) == (409, "ai_classification_disabled")
    assert _run_count(body["document"]["id"]) == before
    assert classification_http["enqueue"].calls == []

    edited = client.patch(
        _doc(project_id, revision_id, body["id"]),
        json={"document_type": "PANEL_SCHEDULE"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["document_type"] == "PANEL_SCHEDULE"
    readable = client.get(_doc(project_id, revision_id, body["id"], "/classification"))
    assert readable.status_code == 200, readable.text
    assert readable.json()["enabled"] is False


def test_pages_withheld_until_suggestion_is_completed(
    classification_http: dict[str, Any],
) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    body = upload(project_id, revision_id).json()
    withheld = client.get(_doc(project_id, revision_id, body["id"], "/classification/pages"))
    assert (withheld.status_code, code(withheld)) == (409, "classification_not_complete")
    waiting = client.get(_doc(project_id, revision_id, body["id"], "/classification"))
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["suggestion"] is None

    processing_id = _complete_processing(body["document"]["id"])
    _add_run(body["document"]["id"], processing_id, page=True, requires_pages=True)
    pages = client.get(_doc(project_id, revision_id, body["id"], "/classification/pages"))
    assert pages.status_code == 200, pages.text
    payload = pages.json()
    assert payload["enabled"] is False
    assert payload["items"] == [
        {
            "page_number": 1,
            "predicted_type": "PANEL_SCHEDULE",
            "confidence_band": "MEDIUM",
            "confidence_score": 0.7,
            "alternatives": [],
            "rationale": None,
        }
    ]
    summary = client.get(_doc(project_id, revision_id, body["id"])).json()
    assert summary["classification"]["suggestion"]["requires_page_classification"] is True


def test_status_and_history_polls_create_no_run(classification_http: dict[str, Any]) -> None:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    body = upload(project_id, revision_id).json()
    processing_id = _complete_processing(body["document"]["id"])
    seeded = _add_run(body["document"]["id"], processing_id)
    before = _run_count(body["document"]["id"])
    calls_before = list(classification_http["enqueue"].calls)

    status = client.get(_doc(project_id, revision_id, body["id"], "/classification"))
    history = client.get(_doc(project_id, revision_id, body["id"], "/classification/runs"))
    pages = client.get(_doc(project_id, revision_id, body["id"], "/classification/pages"))
    listed = client.get(docs_url(project_id, revision_id))
    assert status.status_code == 200, status.text
    assert history.status_code == 200, history.text
    assert pages.status_code == 200, pages.text
    assert listed.status_code == 200, listed.text
    assert _run_count(body["document"]["id"]) == before
    assert classification_http["enqueue"].calls == calls_before
    run = history.json()["items"][0]
    assert run["id"] == seeded["run_id"]
    assert run["prompt_version"] == "1"
    assert "rationale" not in run
    assert "storage_key" not in history.text


def _doc(project_id: str, revision_id: str, association_id: str, suffix: str = "") -> str:
    return f"{docs_url(project_id, revision_id)}/{association_id}{suffix}"


def _accepted_document(
    classification_http: dict[str, Any],
) -> tuple[str, str, dict[str, Any], dict[str, str]]:
    project_id = classification_http["project_id"]
    revision_id = classification_http["revision_id"]
    body = upload(project_id, revision_id).json()
    processing_id = _complete_processing(body["document"]["id"])
    seeded = _add_run(body["document"]["id"], processing_id)
    accepted = client.post(
        _doc(
            project_id,
            revision_id,
            body["id"],
            f"/classification/predictions/{seeded['prediction_id']}/accept",
        )
    )
    assert accepted.status_code == 200, accepted.text
    return project_id, revision_id, body, seeded


def _complete_processing(document_id: str) -> str:
    with get_session_factory()() as session:
        run = session.scalar(
            select(DocumentProcessingRun)
            .where(DocumentProcessingRun.document_id == uuid.UUID(document_id))
            .order_by(DocumentProcessingRun.attempt_count.desc())
        )
        assert run is not None
        run.status = ProcessingRunStatus.COMPLETED
        run.pages_total = 1
        run.pages_processed = 1
        session.commit()
        return str(run.id)


def _add_run(
    document_id: str,
    processing_run_id: str,
    *,
    status: ClassificationRunStatus = ClassificationRunStatus.COMPLETED,
    identity: str | None = None,
    attempt_number: int = 1,
    predicted_type: DocumentClassification | None = DocumentClassification.SINGLE_LINE_DIAGRAM,
    error_code: str | None = None,
    created_at: datetime | None = None,
    page: bool = False,
    requires_pages: bool = False,
    rationale: str | None = None,
) -> dict[str, str]:
    with get_session_factory()() as session:
        run = DocumentClassificationRun(
            document_id=uuid.UUID(document_id),
            processing_run_id=uuid.UUID(processing_run_id),
            attempt_number=attempt_number,
            classifier_version="1",
            taxonomy_version="1",
            prompt_version="1",
            sampling_profile_version="1",
            sampling_profile_hash="profile",
            classifier_identity_hash=identity or f"seed-{uuid.uuid4().hex}",
            provider="fake",
            model="fake",
            status=status,
            requires_page_classification=(
                requires_pages if status == ClassificationRunStatus.COMPLETED else None
            ),
            pages_total=1,
            pages_classified=1 if status == ClassificationRunStatus.COMPLETED else 0,
            error_code=error_code,
            created_at=created_at or datetime.now(UTC),
        )
        session.add(run)
        session.flush()
        prediction_id = None
        page_prediction_id = None
        if predicted_type is not None:
            prediction = ClassificationPrediction(
                classification_run_id=run.id,
                document_id=run.document_id,
                scope=ClassificationScope.DOCUMENT,
                predicted_type=predicted_type,
                confidence_score=Decimal("0.95"),
                confidence_band=ConfidenceBand.HIGH,
                alternatives=[{"type": "PANEL_SCHEDULE", "score": 0.2}],
                rationale=rationale,
            )
            session.add(prediction)
            session.flush()
            prediction_id = str(prediction.id)
        if page:
            document_page = DocumentPage(
                document_id=run.document_id,
                page_number=1,
                source_width=Decimal("612"),
                source_height=Decimal("792"),
                source_unit=SourceUnit.POINTS,
                rotation_degrees=0,
            )
            session.add(document_page)
            session.flush()
            page_prediction = ClassificationPrediction(
                classification_run_id=run.id,
                document_id=run.document_id,
                scope=ClassificationScope.PAGE,
                document_page_id=document_page.id,
                predicted_type=DocumentClassification.PANEL_SCHEDULE,
                confidence_score=Decimal("0.70"),
                confidence_band=ConfidenceBand.MEDIUM,
                alternatives=[],
            )
            session.add(page_prediction)
            session.flush()
            page_prediction_id = str(page_prediction.id)
        session.commit()
        return {
            "run_id": str(run.id),
            "prediction_id": prediction_id or "",
            "page_prediction_id": page_prediction_id or "",
        }


def _run_count(document_id: str) -> int:
    with get_session_factory()() as session:
        count = session.scalar(
            select(func.count())
            .select_from(DocumentClassificationRun)
            .where(DocumentClassificationRun.document_id == uuid.UUID(document_id))
        )
        return int(count or 0)


def _accepted_id(association_id: str) -> str | None:
    with get_session_factory()() as session:
        row = session.get(RevisionDocument, uuid.UUID(association_id))
        assert row is not None
        if row.accepted_classification_prediction_id is None:
            return None
        return str(row.accepted_classification_prediction_id)
