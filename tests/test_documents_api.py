"""Document upload, list and get API. Integration cases need RUN_INTEGRATION=1.

Object storage is always the in-memory fake. Every test installs its own instance
through ``use_storage``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text

from file_factory import PDF, jpeg_bytes, png_bytes, png_header_only, tiff_bytes
from powerforge_api.db import get_engine, get_session_factory
from powerforge_api.main import app, create_app
from powerforge_api.models import Document, RevisionDocument
from powerforge_api.routers.documents import MULTIPART_OVERHEAD_BYTES
from powerforge_api.services import document_service
from powerforge_api.services.document_service import _like_pattern
from powerforge_api.services.revision_documents import lock_project_shared
from powerforge_api.storage import InMemoryObjectStorage
from powerforge_api.storage.base import StorageError
from powerforge_api.storage.factory import get_object_storage
from powerforge_document_model import DocumentOrigin, RevisionDocumentStatus
from powerforge_shared.config import Settings, get_settings

client = TestClient(app)

OLD = datetime(2020, 1, 1, tzinfo=UTC)
JSON_TIMEOUT = 20


@pytest.fixture
def require_db() -> None:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


@pytest.fixture
def use_storage() -> Iterator[Callable[[InMemoryObjectStorage], InMemoryObjectStorage]]:
    def install(storage: InMemoryObjectStorage) -> InMemoryObjectStorage:
        app.dependency_overrides[get_object_storage] = lambda: storage
        return storage

    yield install
    app.dependency_overrides.pop(get_object_storage, None)


@pytest.fixture
def upload_limit() -> Iterator[Callable[[int], None]]:
    def set_limit(max_upload_bytes: int) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(max_upload_bytes=max_upload_bytes)

    yield set_limit
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def ctx(require_db: None, use_storage: Any) -> dict[str, Any]:
    """A fresh project with ACTIVE revision "0" and a clean in-memory storage."""
    storage = use_storage(InMemoryObjectStorage())
    project_id = make_project()
    revision = make_revision(project_id, "0", activate=True).json()
    return {"project_id": project_id, "revision_id": revision["id"], "storage": storage}


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def make_project() -> str:
    response = client.post(
        "/api/projects",
        json={"project_number": _unique("DOC"), "project_name": "Documents"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_revision(project_id: str, identifier: str, **body: Any) -> Any:
    return client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": identifier, **body},
    )


def docs_url(project_id: object, revision_id: object) -> str:
    return f"/api/projects/{project_id}/revisions/{revision_id}/documents"


def upload(
    project_id: object,
    revision_id: object,
    data: bytes = PDF,
    filename: str = "plan.pdf",
    *,
    http: TestClient = client,
    **form: str,
) -> Any:
    return http.post(
        docs_url(project_id, revision_id),
        files={"file": (filename, data, "application/octet-stream")},
        data=form,
    )


def code(response: Any) -> str:
    return response.json()["detail"]["code"]


def documents_of(project_id: str) -> list[Document]:
    with get_session_factory()() as session:
        rows = session.scalars(
            select(Document).where(Document.project_id == uuid.UUID(project_id))
        ).all()
        session.expunge_all()
        return list(rows)


def association_total(revision_id: str) -> int:
    with get_session_factory()() as session:
        return session.scalar(
            select(func.count())
            .select_from(RevisionDocument)
            .where(RevisionDocument.revision_id == uuid.UUID(revision_id))
        )


def nothing_stored(ctx: dict[str, Any]) -> None:
    assert documents_of(ctx["project_id"]) == []
    assert association_total(ctx["revision_id"]) == 0
    assert ctx["storage"].objects == {}


def seed_association(
    project_id: str,
    revision_id: str,
    *,
    status: RevisionDocumentStatus = RevisionDocumentStatus.INCLUDED,
    filename: str = "seeded.pdf",
    sha256: str = "0" * 64,
    added_at: datetime = OLD,
) -> uuid.UUID:
    with get_session_factory()() as session:
        document_id = uuid.uuid4()
        session.add(
            Document(
                id=document_id,
                project_id=uuid.UUID(project_id),
                original_filename=filename,
                storage_key=f"projects/{project_id}/documents/{document_id}/original.pdf",
                mime_type="application/pdf",
                file_extension=".pdf",
                size_bytes=10,
                sha256=sha256,
            )
        )
        session.flush()
        link = RevisionDocument(
            project_id=uuid.UUID(project_id),
            revision_id=uuid.UUID(revision_id),
            document_id=document_id,
            origin=DocumentOrigin.UPLOADED,
            status=status,
            removed_at=OLD if status is RevisionDocumentStatus.REMOVED else None,
            added_at=added_at,
        )
        session.add(link)
        session.commit()
        return link.id


def set_sql(statement: str, **params: Any) -> None:
    with get_engine().begin() as connection:
        connection.execute(text(statement), params)


@contextmanager
def captured_sql() -> Iterator[list[str]]:
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


class HookedStorage(InMemoryObjectStorage):
    """Runs ``hook`` inside ``put``, i.e. between the early check and the locked step."""

    def __init__(self, hook: Callable[[], None]) -> None:
        super().__init__()
        self.hook = hook

    def put(self, key: str, fileobj: Any, size: int, content_type: str) -> None:
        self.hook()
        super().put(key, fileobj, size, content_type)


# --- valid uploads -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "filename", "mime"),
    [
        (PDF, "plan.pdf", "application/pdf"),
        (png_bytes(), "scan.png", "image/png"),
        (jpeg_bytes(), "photo.jpg", "image/jpeg"),
        (tiff_bytes(), "scan.TIF", "image/tiff"),
    ],
)
def test_valid_upload_stores_object_and_records(
    ctx: dict[str, Any], data: bytes, filename: str, mime: str
) -> None:
    response = upload(ctx["project_id"], ctx["revision_id"], data, filename)

    assert response.status_code == 201, response.text
    body = response.json()
    document = body["document"]
    extension = "." + filename.rsplit(".", 1)[1].lower()
    assert document["original_filename"] == filename
    assert document["mime_type"] == mime
    assert document["file_extension"] == extension
    assert document["size_bytes"] == len(data)
    assert document["sha256"] == hashlib.sha256(data).hexdigest()
    assert body["revision_id"] == ctx["revision_id"]
    assert body["origin"] == "UPLOADED"
    assert body["status"] == "INCLUDED"
    assert body["document_type"] == "UNKNOWN"
    assert body["inherited_from_revision_id"] is None
    assert body["inherited_from_revision_identifier"] is None
    assert body["removed_at"] is None
    assert body["duplicate_detected"] is False
    assert body["duplicate_document_ids"] == []
    assert "storage_key" not in document
    assert "uploaded_by" not in document

    key = f"projects/{ctx['project_id']}/documents/{document['id']}/original{extension}"
    stored = ctx["storage"].objects[key]
    assert stored.data == data
    assert stored.content_type == mime
    rows = documents_of(ctx["project_id"])
    assert [row.storage_key for row in rows] == [key]
    assert rows[0].uploaded_by is None


def test_metadata_is_stored_and_blank_values_become_null(ctx: dict[str, Any]) -> None:
    full = upload(
        ctx["project_id"],
        ctx["revision_id"],
        document_type="SINGLE_LINE_DIAGRAM",
        document_number="  E-001  ",
        description="Main one-line",
        notes="Rev B markups",
    ).json()
    blank = upload(
        ctx["project_id"],
        ctx["revision_id"],
        PDF + b"\n%second",
        document_number="   ",
        description="",
    ).json()

    assert full["document_type"] == "SINGLE_LINE_DIAGRAM"
    assert full["document_number"] == "E-001"
    assert full["description"] == "Main one-line"
    assert full["notes"] == "Rev B markups"
    assert blank["document_type"] == "UNKNOWN"
    assert blank["document_number"] is None
    assert blank["description"] is None
    assert blank["notes"] is None


def test_invalid_metadata_is_rejected_without_storing_anything(ctx: dict[str, Any]) -> None:
    bad_type = upload(ctx["project_id"], ctx["revision_id"], document_type="NOT_A_TYPE")
    too_long = upload(ctx["project_id"], ctx["revision_id"], description="x" * 2001)
    no_file = client.post(docs_url(ctx["project_id"], ctx["revision_id"]), data={"notes": "n"})

    assert bad_type.status_code == 422
    assert too_long.status_code == 422
    assert no_file.status_code == 422
    assert ctx["storage"].calls == []
    nothing_stored(ctx)


# --- rejected files ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "filename", "status_code", "error"),
    [
        (b"hello", "notes.txt", 415, "unsupported_document_type"),
        (b"MZ\x90\x00" + b"\x00" * 100, "setup.pdf", 422, "invalid_file_content"),
        (jpeg_bytes(), "wrong.png", 422, "invalid_file_content"),
        (PDF, "wrong.png", 422, "invalid_file_content"),
        (b"", "empty.pdf", 422, "invalid_file_content"),
    ],
)
def test_rejected_files_leave_nothing_behind(
    ctx: dict[str, Any], data: bytes, filename: str, status_code: int, error: str
) -> None:
    response = upload(ctx["project_id"], ctx["revision_id"], data, filename)

    assert response.status_code == status_code, response.text
    assert code(response) == error
    assert ctx["storage"].calls == []
    nothing_stored(ctx)


def test_image_over_the_pixel_cap_is_rejected(ctx: dict[str, Any]) -> None:
    response = upload(
        ctx["project_id"], ctx["revision_id"], png_header_only(30000, 30000), "huge.png"
    )

    assert response.status_code == 422
    assert code(response) == "invalid_file_content"
    nothing_stored(ctx)


def test_oversize_file_is_rejected_while_streaming(
    ctx: dict[str, Any], upload_limit: Callable[[int], None]
) -> None:
    upload_limit(1024)

    response = upload(ctx["project_id"], ctx["revision_id"], PDF + b"0" * 2048, "big.pdf")

    assert response.status_code == 413
    assert code(response) == "file_too_large"
    assert ctx["storage"].calls == []
    nothing_stored(ctx)


def test_file_at_the_limit_is_accepted(
    ctx: dict[str, Any], upload_limit: Callable[[int], None]
) -> None:
    upload_limit(len(PDF))

    assert upload(ctx["project_id"], ctx["revision_id"]).status_code == 201


def test_oversize_content_length_is_rejected_before_the_body_is_read(
    upload_limit: Callable[[int], None], use_storage: Any
) -> None:
    upload_limit(1024)
    storage = use_storage(InMemoryObjectStorage())
    # Unknown ids and no file part: only the header guard can produce a 413 here.
    response = client.post(
        docs_url(uuid.uuid4(), uuid.uuid4()),
        content=b"",
        headers={
            "content-type": "multipart/form-data; boundary=x",
            "content-length": str(1024 + MULTIPART_OVERHEAD_BYTES + 1),
        },
    )

    assert response.status_code == 413
    assert code(response) == "file_too_large"
    assert storage.calls == []


# --- duplicates --------------------------------------------------------------------


def test_duplicate_content_is_flagged_but_never_rejected_or_merged(ctx: dict[str, Any]) -> None:
    first = upload(ctx["project_id"], ctx["revision_id"], filename="a.pdf").json()
    second = upload(ctx["project_id"], ctx["revision_id"], filename="b.pdf")

    assert second.status_code == 201
    body = second.json()
    assert body["duplicate_detected"] is True
    assert body["duplicate_document_ids"] == [first["document"]["id"]]
    assert body["document"]["id"] != first["document"]["id"]
    assert len(ctx["storage"].objects) == 2
    assert len(documents_of(ctx["project_id"])) == 2


def test_duplicate_is_detected_across_revisions_and_removed_documents(ctx: dict[str, Any]) -> None:
    sha = hashlib.sha256(PDF).hexdigest()
    seed_association(
        ctx["project_id"],
        ctx["revision_id"],
        status=RevisionDocumentStatus.REMOVED,
        sha256=sha,
    )
    other = make_revision(ctx["project_id"], "1").json()["id"]

    response = upload(ctx["project_id"], other)

    assert response.status_code == 201
    assert response.json()["duplicate_detected"] is True
    assert len(response.json()["duplicate_document_ids"]) == 1


def test_identical_content_in_another_project_is_not_a_duplicate(ctx: dict[str, Any]) -> None:
    upload(ctx["project_id"], ctx["revision_id"])
    other_project = make_project()
    other_revision = make_revision(other_project, "0").json()["id"]

    response = upload(other_project, other_revision)

    assert response.status_code == 201
    assert response.json()["duplicate_detected"] is False


# --- ownership and mutability ------------------------------------------------------


def test_ownership_failures_are_404_and_touch_no_storage(ctx: dict[str, Any]) -> None:
    other_project = make_project()
    other_revision = make_revision(other_project, "0").json()["id"]

    unknown_project = upload(uuid.uuid4(), ctx["revision_id"])
    unknown_revision = upload(ctx["project_id"], uuid.uuid4())
    foreign_revision = upload(ctx["project_id"], other_revision)

    assert (unknown_project.status_code, code(unknown_project)) == (404, "project_not_found")
    assert (unknown_revision.status_code, code(unknown_revision)) == (404, "revision_not_found")
    assert (foreign_revision.status_code, code(foreign_revision)) == (
        404,
        "revision_project_mismatch",
    )
    assert ctx["storage"].calls == []
    assert documents_of(other_project) == []


def test_draft_active_and_paused_accept_uploads(ctx: dict[str, Any]) -> None:
    draft = make_revision(ctx["project_id"], "1").json()["id"]

    assert upload(ctx["project_id"], draft).status_code == 201
    assert upload(ctx["project_id"], ctx["revision_id"], png_bytes(), "a.png").status_code == 201

    client.post(f"/api/projects/{ctx['project_id']}/pause")
    assert upload(ctx["project_id"], ctx["revision_id"], jpeg_bytes(), "b.jpg").status_code == 201


def test_superseded_revision_is_read_only(ctx: dict[str, Any]) -> None:
    assert make_revision(ctx["project_id"], "1", activate=True).status_code == 201

    response = upload(ctx["project_id"], ctx["revision_id"])

    assert (response.status_code, code(response)) == (409, "revision_read_only")
    assert ctx["storage"].calls == []
    nothing_stored(ctx)


@pytest.mark.parametrize(
    ("action", "error"),
    [("cancel", "cancelled_project"), ("archive", "archived_project")],
)
def test_cancelled_and_archived_projects_reject_uploads(
    ctx: dict[str, Any], action: str, error: str
) -> None:
    assert client.post(f"/api/projects/{ctx['project_id']}/{action}").status_code == 200

    response = upload(ctx["project_id"], ctx["revision_id"])

    assert (response.status_code, code(response)) == (409, error)
    assert ctx["storage"].calls == []
    nothing_stored(ctx)


def test_status_flipped_during_the_object_write_is_caught_under_lock(
    require_db: None, use_storage: Any
) -> None:
    project_id = make_project()
    revision_id = make_revision(project_id, "0", activate=True).json()["id"]
    flips = [
        (
            "UPDATE project_revisions SET status = 'SUPERSEDED' WHERE id = :id",
            revision_id,
            "revision_read_only",
        ),
        ("UPDATE projects SET status = 'ARCHIVED' WHERE id = :id", project_id, "archived_project"),
        (
            "UPDATE projects SET status = 'CANCELLED' WHERE id = :id",
            project_id,
            "cancelled_project",
        ),
    ]
    for statement, target, expected in flips:
        # Reset state between flips.
        set_sql("UPDATE projects SET status = 'ACTIVE' WHERE id = :id", id=project_id)
        set_sql("UPDATE project_revisions SET status = 'ACTIVE' WHERE id = :id", id=revision_id)
        storage = use_storage(HookedStorage(lambda s=statement, t=target: set_sql(s, id=t)))

        response = upload(project_id, revision_id, filename=f"{expected}.pdf")

        assert (response.status_code, code(response)) == (409, expected)
        assert len(storage.calls_for("put")) == 1
        assert len(storage.calls_for("delete")) == 1
        assert storage.objects == {}
    assert documents_of(project_id) == []


# --- locking (D11) -----------------------------------------------------------------


def test_upload_locks_project_for_share_before_revision_for_update(ctx: dict[str, Any]) -> None:
    with captured_sql() as statements:
        assert upload(ctx["project_id"], ctx["revision_id"]).status_code == 201

    share = [i for i, s in enumerate(statements) if "FROM projects" in s and "FOR SHARE" in s]
    revision_update = [
        i for i, s in enumerate(statements) if "FROM project_revisions" in s and "FOR UPDATE" in s
    ]
    assert share and revision_update
    assert share[0] < revision_update[0]
    assert not any(re.search(r"FROM projects\b.*FOR UPDATE", s, re.S) for s in statements)
    assert not any(s.lstrip().startswith("UPDATE projects") for s in statements)


@pytest.mark.parametrize("action", ["archive", "cancel"])
def test_archive_and_cancel_lock_the_project_before_changing_it(
    ctx: dict[str, Any], action: str
) -> None:
    with captured_sql() as statements:
        assert client.post(f"/api/projects/{ctx['project_id']}/{action}").status_code == 200

    locked = [i for i, s in enumerate(statements) if "FROM projects" in s and "FOR UPDATE" in s]
    updated = [i for i, s in enumerate(statements) if s.lstrip().startswith("UPDATE projects")]
    assert locked and updated
    assert locked[0] < updated[0]


def test_concurrent_uploads_to_one_revision_do_not_deadlock(ctx: dict[str, Any]) -> None:
    payloads = [png_bytes(blue=i * 10) for i in range(4)]

    def run(data: bytes) -> int:
        return upload(
            ctx["project_id"], ctx["revision_id"], data, "c.png", http=TestClient(app)
        ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, payloads, timeout=JSON_TIMEOUT))

    assert results == [201] * 4
    assert association_total(ctx["revision_id"]) == 4


def test_archive_waits_for_an_in_flight_document_mutation(ctx: dict[str, Any]) -> None:
    holder = get_session_factory()()
    lock_project_shared(holder, uuid.UUID(ctx["project_id"]))
    outcome: dict[str, Any] = {}

    def archive() -> None:
        outcome["response"] = TestClient(app).post(f"/api/projects/{ctx['project_id']}/archive")

    thread = threading.Thread(target=archive)
    thread.start()
    try:
        time.sleep(0.7)
        assert thread.is_alive(), "archive must wait for the in-flight mutation's project lock"
    finally:
        holder.commit()
        holder.close()
    thread.join(JSON_TIMEOUT)

    assert outcome["response"].status_code == 200
    rejected = upload(ctx["project_id"], ctx["revision_id"])
    assert (rejected.status_code, code(rejected)) == (409, "archived_project")


# --- failures ----------------------------------------------------------------------


def test_storage_failure_is_502_without_leaking_sdk_text(ctx: dict[str, Any]) -> None:
    ctx["storage"].fail_on("put", StorageError("https://minio.internal:9000 secret-access-key"))

    response = upload(ctx["project_id"], ctx["revision_id"])

    assert response.status_code == 502
    assert code(response) == "storage_upload_failed"
    assert "minio" not in response.text
    assert "secret" not in response.text
    assert ctx["storage"].calls_for("delete") == []
    nothing_stored(ctx)


def test_database_failure_after_the_write_removes_the_object(
    ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("database exploded")

    monkeypatch.setattr(document_service, "lock_revision", boom)

    response = upload(
        ctx["project_id"], ctx["revision_id"], http=TestClient(app, raise_server_exceptions=False)
    )

    assert response.status_code == 500
    assert len(ctx["storage"].calls_for("put")) == 1
    assert len(ctx["storage"].calls_for("delete")) == 1
    nothing_stored(ctx)


def test_failed_cleanup_is_logged_and_does_not_mask_the_original_error(
    ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("database exploded")

    monkeypatch.setattr(document_service, "lock_revision", boom)
    ctx["storage"].fail_on("delete", StorageError("cannot delete"))

    response = upload(
        ctx["project_id"], ctx["revision_id"], http=TestClient(app, raise_server_exceptions=False)
    )

    assert response.status_code == 500
    messages = [r.getMessage() for r in caplog.records]
    assert "orphan object cleanup failed" in messages
    assert "document database step failed" in messages
    assert documents_of(ctx["project_id"]) == []


# --- list and get ------------------------------------------------------------------


def test_list_hides_removed_by_default_and_filters_by_status(ctx: dict[str, Any]) -> None:
    kept = upload(ctx["project_id"], ctx["revision_id"], filename="kept.pdf").json()
    seed_association(
        ctx["project_id"],
        ctx["revision_id"],
        status=RevisionDocumentStatus.REMOVED,
        filename="gone.pdf",
    )
    url = docs_url(ctx["project_id"], ctx["revision_id"])

    default = client.get(url).json()["items"]
    removed = client.get(url, params={"status": "REMOVED"}).json()["items"]
    everything = client.get(url, params={"status": "ALL"}).json()["items"]

    assert [item["id"] for item in default] == [kept["id"]]
    assert [item["document"]["original_filename"] for item in removed] == ["gone.pdf"]
    assert removed[0]["status"] == "REMOVED"
    assert removed[0]["removed_at"] is not None
    assert len(everything) == 2


def test_list_filters_by_type_origin_and_search(ctx: dict[str, Any]) -> None:
    pid, rid = ctx["project_id"], ctx["revision_id"]
    upload(
        pid, rid, filename="Main-Panel.pdf", document_type="PANEL_SCHEDULE", document_number="P-100"
    )
    upload(pid, rid, png_bytes(), "photo.png", document_type="EQUIPMENT_PHOTO", description="Gear")
    upload(pid, rid, jpeg_bytes(), "rate.jpg", description="50% rated")
    upload(pid, rid, tiff_bytes(), "snake_case.tif", description="axb")
    url = docs_url(pid, rid)

    def names(**params: str) -> list[str]:
        items = client.get(url, params=params).json()["items"]
        return sorted(item["document"]["original_filename"] for item in items)

    assert names(document_type="PANEL_SCHEDULE") == ["Main-Panel.pdf"]
    assert names(origin="UPLOADED") != []
    assert names(origin="INHERITED") == []
    assert names(search="panel") == ["Main-Panel.pdf"]
    assert names(search="p-100") == ["Main-Panel.pdf"]
    assert names(search="GEAR") == ["photo.png"]
    assert names(search="50%") == ["rate.jpg"]
    assert names(search="e_c") == ["snake_case.tif"]
    assert names(search="a_b") == []
    assert names(search="%") == ["rate.jpg"]
    assert names(search="\\") == []
    assert names(search="  ") == names()
    assert client.get(url, params={"document_type": "NOPE"}).status_code == 422
    assert client.get(url, params={"status": "NOPE"}).status_code == 422


def test_list_order_is_added_at_then_filename(ctx: dict[str, Any]) -> None:
    pid, rid = ctx["project_id"], ctx["revision_id"]
    seed_association(pid, rid, filename="b.pdf", added_at=OLD)
    seed_association(pid, rid, filename="a.pdf", added_at=OLD)
    seed_association(pid, rid, filename="0-oldest.pdf", added_at=datetime(2019, 1, 1, tzinfo=UTC))
    later = upload(pid, rid, filename="z-new.pdf").json()

    items = client.get(docs_url(pid, rid)).json()["items"]

    assert [i["document"]["original_filename"] for i in items] == [
        "0-oldest.pdf",
        "a.pdf",
        "b.pdf",
        "z-new.pdf",
    ]
    assert items[-1]["id"] == later["id"]


def test_inherited_documents_report_their_source_revision(ctx: dict[str, Any]) -> None:
    pid = ctx["project_id"]
    upload(pid, ctx["revision_id"], filename="a.pdf", document_type="SPECIFICATION")
    upload(pid, ctx["revision_id"], png_bytes(), "b.png")
    created = make_revision(pid, "1").json()
    assert created["inherited_document_count"] == 2

    url = docs_url(pid, created["id"])
    items = client.get(url).json()["items"]

    assert len(items) == 2
    assert {i["origin"] for i in items} == {"INHERITED"}
    assert {i["inherited_from_revision_identifier"] for i in items} == {"0"}
    assert {i["inherited_from_revision_id"] for i in items} == {ctx["revision_id"]}
    assert client.get(url, params={"origin": "UPLOADED"}).json()["items"] == []

    fresh = upload(pid, created["id"], tiff_bytes(), "c.tif").json()
    uploaded = client.get(url, params={"origin": "UPLOADED"}).json()["items"]
    assert [i["id"] for i in uploaded] == [fresh["id"]]
    assert len(client.get(docs_url(pid, ctx["revision_id"])).json()["items"]) == 2


def test_get_returns_one_document_and_enforces_ownership(ctx: dict[str, Any]) -> None:
    pid, rid = ctx["project_id"], ctx["revision_id"]
    created = upload(pid, rid, document_number="E-9").json()
    other_revision = make_revision(pid, "1").json()["id"]
    other_project = make_project()
    foreign_revision = make_revision(other_project, "0").json()["id"]

    ok = client.get(f"{docs_url(pid, rid)}/{created['id']}")
    wrong_revision = client.get(f"{docs_url(pid, other_revision)}/{created['id']}")
    wrong_project = client.get(f"{docs_url(other_project, rid)}/{created['id']}")
    mismatch = client.get(f"{docs_url(pid, foreign_revision)}/{created['id']}")
    unknown = client.get(f"{docs_url(pid, rid)}/{uuid.uuid4()}")
    unknown_project = client.get(f"{docs_url(uuid.uuid4(), rid)}/{created['id']}")

    assert ok.status_code == 200
    assert ok.json()["document_number"] == "E-9"
    assert "duplicate_detected" not in ok.json()
    for response, error in [
        (wrong_revision, "revision_document_not_found"),
        (wrong_project, "revision_project_mismatch"),
        (mismatch, "revision_project_mismatch"),
        (unknown, "revision_document_not_found"),
        (unknown_project, "project_not_found"),
    ]:
        assert (response.status_code, code(response)) == (404, error)


def test_reads_work_in_archived_projects(ctx: dict[str, Any]) -> None:
    created = upload(ctx["project_id"], ctx["revision_id"]).json()
    client.post(f"/api/projects/{ctx['project_id']}/archive")

    listing = client.get(docs_url(ctx["project_id"], ctx["revision_id"]))
    single = client.get(f"{docs_url(ctx['project_id'], ctx['revision_id'])}/{created['id']}")

    assert listing.status_code == 200 and len(listing.json()["items"]) == 1
    assert single.status_code == 200


# --- logging -----------------------------------------------------------------------


def test_logs_describe_events_without_filenames_keys_or_secrets(
    ctx: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    name = "TOP-SECRET-plan.pdf"
    upload(ctx["project_id"], ctx["revision_id"], filename=name)
    upload(ctx["project_id"], ctx["revision_id"], filename=name)
    ctx["storage"].fail_on("put", StorageError("https://minio.internal secret-access-key"))
    upload(ctx["project_id"], ctx["revision_id"], png_bytes(), "TOP-SECRET-photo.png")

    messages = [r.getMessage() for r in caplog.records]
    assert messages.count("document uploaded") == 2
    assert "duplicate document detected" in messages
    assert "object storage upload failed" in messages
    everything = " ".join(
        str(value) for record in caplog.records for value in record.__dict__.values()
    )
    for forbidden in (
        "TOP-SECRET",
        "original.pdf",
        "original.png",
        "minio.internal",
        "secret-access",
    ):
        assert forbidden not in everything


# --- no database needed ------------------------------------------------------------


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
def test_cors_preflight_allows_multipart_upload_from_the_web_app(
    origin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    get_settings.cache_clear()
    try:
        web_api = TestClient(create_app())
    finally:
        get_settings.cache_clear()

    response = web_api.options(
        docs_url(uuid.uuid4(), uuid.uuid4()),
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]


def test_openapi_lists_the_document_endpoints() -> None:
    paths = app.openapi()["paths"]
    collection = paths["/api/projects/{project_id}/revisions/{revision_id}/documents"]
    item = paths[
        "/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}"
    ]

    assert set(collection) == {"get", "post"}
    assert set(item) == {"get"}
    assert "multipart/form-data" in collection["post"]["requestBody"]["content"]


def test_search_pattern_escapes_like_wildcards() -> None:
    assert _like_pattern(" a%b_c\\d ") == "%a\\%b\\_c\\\\d%"
