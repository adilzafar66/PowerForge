"""Document metadata edits, remove, restore and reuse. Integration cases need RUN_INTEGRATION=1.

Shared helpers are in ``documents_support``; the ``require_db``, ``use_storage`` and
``ctx`` fixtures are in ``conftest.py``.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from documents_support import (
    JSON_TIMEOUT,
    captured_sql,
    client,
    code,
    docs_url,
    documents_of,
    make_project,
    make_revision,
    set_sql,
    upload,
)
from file_factory import PDF, png_bytes
from powerforge_api.db import get_engine, get_session_factory
from powerforge_api.main import app
from powerforge_api.models import RevisionDocument
from powerforge_api.services.document_service import DocumentService
from powerforge_api.services.revision_documents import lock_project_shared
from powerforge_document_model import RevisionDocumentStatus

Op = Callable[[str, str, str, str], Any]


def op_patch(pid: str, rid: str, rd: str, _src: str) -> Any:
    return client.patch(f"{docs_url(pid, rid)}/{rd}", json={"notes": "edited"})


def op_remove(pid: str, rid: str, rd: str, _src: str) -> Any:
    return client.post(f"{docs_url(pid, rid)}/{rd}/remove")


def op_restore(pid: str, rid: str, rd: str, _src: str) -> Any:
    return client.post(f"{docs_url(pid, rid)}/{rd}/restore")


def op_reuse(pid: str, rid: str, _rd: str, src: str) -> Any:
    return client.post(f"{docs_url(pid, rid)}/reuse", json={"source_revision_document_id": src})


OPS: dict[str, tuple[Op, int]] = {
    "patch": (op_patch, 200),
    "remove": (op_remove, 200),
    "restore": (op_restore, 200),
    "reuse": (op_reuse, 201),
}


def seeded(ctx: dict[str, Any], **metadata: str) -> dict[str, Any]:
    """Upload "a.pdf" into revision "0" and add an empty DRAFT revision "1" (no carry-forward)."""
    uploaded = upload(ctx["project_id"], ctx["revision_id"], PDF, "a.pdf", **metadata)
    assert uploaded.status_code == 201, uploaded.text
    rev1 = make_revision(ctx["project_id"], "1", carry_forward_documents=False)
    assert rev1.status_code == 201, rev1.text
    return {**ctx, "a": uploaded.json(), "rev1": rev1.json()["id"]}


def listing(project_id: str, revision_id: str, **params: str) -> list[dict[str, Any]]:
    response = client.get(docs_url(project_id, revision_id), params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def snapshot(project_id: str) -> list[tuple[Any, ...]]:
    with get_session_factory()() as session:
        rows = session.scalars(
            select(RevisionDocument).where(RevisionDocument.project_id == uuid.UUID(project_id))
        ).all()
        return sorted(
            (str(r.id), str(r.revision_id), r.status.value, r.document_type.value, r.notes)
            for r in rows
        )


def document_facts(project_id: str) -> list[tuple[Any, ...]]:
    return sorted(
        (
            str(d.id),
            d.original_filename,
            d.storage_key,
            d.mime_type,
            d.file_extension,
            d.size_bytes,
            d.sha256,
            d.uploaded_at,
        )
        for d in documents_of(project_id)
    )


def db_association(revision_document_id: str) -> RevisionDocument:
    with get_session_factory()() as session:
        row = session.get(RevisionDocument, uuid.UUID(revision_document_id))
        session.expunge_all()
        assert row is not None
        return row


def matrix_scenario(state: str) -> tuple[str, str, str, str]:
    """Return (project, target revision, association in target, reuse source) for a state."""
    pid = make_project()
    rev0 = make_revision(pid, "0", activate=True).json()["id"]
    a = upload(pid, rev0, PDF, "a.pdf").json()["id"]
    rev1 = make_revision(pid, "1", carry_forward_documents=False).json()["id"]
    b = upload(pid, rev1, png_bytes(), "b.png").json()["id"]
    target, assoc, source = rev1, b, a
    if state in ("ACTIVE", "SUPERSEDED"):
        assert client.post(f"/api/projects/{pid}/revisions/{rev1}/activate").status_code == 200
    if state == "SUPERSEDED":
        target, assoc, source = rev0, a, b
    elif state == "PAUSED":
        assert client.post(f"/api/projects/{pid}/pause").status_code == 200
    elif state == "CANCELLED":
        assert client.post(f"/api/projects/{pid}/cancel").status_code == 200
    elif state == "ARCHIVED":
        assert client.post(f"/api/projects/{pid}/archive").status_code == 200
    return pid, target, assoc, source


# --- metadata ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_type", "PANEL_SCHEDULE"),
        ("document_number", "E-200"),
        ("description", "Updated description"),
        ("notes", "Updated notes"),
    ],
)
def test_each_editable_field_updates_and_nothing_else_changes(
    ctx: dict[str, Any], field: str, value: str
) -> None:
    pid = ctx["project_id"]
    created = upload(
        pid,
        ctx["revision_id"],
        document_type="SINGLE_LINE_DIAGRAM",
        document_number="E-001",
        description="d",
        notes="n",
    ).json()
    url = f"{docs_url(pid, ctx['revision_id'])}/{created['id']}"
    facts = document_facts(pid)

    response = client.patch(url, json={field: value})

    assert response.status_code == 200, response.text
    body = response.json()
    expected = {
        "document_type": "SINGLE_LINE_DIAGRAM",
        "document_number": "E-001",
        "description": "d",
        "notes": "n",
        field: value,
    }
    for name, want in expected.items():
        assert body[name] == want
    assert body["origin"] == "UPLOADED"
    assert body["status"] == "INCLUDED"
    assert body["document"] == created["document"]
    assert document_facts(pid) == facts
    assert client.get(url).json() == body


def test_omitted_fields_stay_null_clears_and_blank_becomes_null(ctx: dict[str, Any]) -> None:
    pid = ctx["project_id"]
    created = upload(
        pid, ctx["revision_id"], document_number="E-001", description="d", notes="n"
    ).json()
    url = f"{docs_url(pid, ctx['revision_id'])}/{created['id']}"

    cleared = client.patch(url, json={"notes": None}).json()
    blank = client.patch(url, json={"document_number": "   "}).json()
    untouched = client.patch(url, json={}).json()

    assert (cleared["notes"], cleared["description"], cleared["document_number"]) == (
        None,
        "d",
        "E-001",
    )
    assert (blank["document_number"], blank["description"]) == (None, "d")
    assert untouched == blank


@pytest.mark.parametrize(
    "body",
    [
        {"document_type": None},
        {"document_type": "NOT_A_TYPE"},
        {"description": "x" * 2001},
        {"document_number": "x" * 129},
        {"notes": "x" * 10001},
    ],
)
def test_invalid_metadata_values_are_rejected(ctx: dict[str, Any], body: dict[str, Any]) -> None:
    created = upload(ctx["project_id"], ctx["revision_id"], notes="keep").json()
    url = f"{docs_url(ctx['project_id'], ctx['revision_id'])}/{created['id']}"

    assert client.patch(url, json=body).status_code == 422
    assert client.get(url).json()["notes"] == "keep"


@pytest.mark.parametrize(
    "field",
    [
        "original_filename",
        "sha256",
        "storage_key",
        "size_bytes",
        "mime_type",
        "file_extension",
        "uploaded_at",
        "project_id",
        "document_id",
        "revision_id",
        "id",
        "status",
        "origin",
        "added_at",
        "removed_at",
        "inherited_from_revision_id",
        "unknown_field",
    ],
)
def test_immutable_and_unknown_fields_are_rejected_and_nothing_changes(
    ctx: dict[str, Any], field: str
) -> None:
    pid = ctx["project_id"]
    created = upload(pid, ctx["revision_id"], notes="keep").json()
    url = f"{docs_url(pid, ctx['revision_id'])}/{created['id']}"
    before, facts, rows = client.get(url).json(), document_facts(pid), snapshot(pid)

    response = client.patch(url, json={"notes": "changed", field: "tampered"})

    assert response.status_code == 422
    assert client.get(url).json() == before
    assert document_facts(pid) == facts
    assert snapshot(pid) == rows


def test_editing_a_removed_document_is_a_conflict(ctx: dict[str, Any]) -> None:
    pid = ctx["project_id"]
    created = upload(pid, ctx["revision_id"], notes="keep").json()
    url = f"{docs_url(pid, ctx['revision_id'])}/{created['id']}"
    client.post(f"{url}/remove")

    response = client.patch(url, json={"notes": "changed"})

    assert (response.status_code, code(response)) == (409, "document_removed")
    assert db_association(created["id"]).notes == "keep"
    client.post(f"{url}/restore")
    assert client.patch(url, json={"notes": "changed"}).status_code == 200


@pytest.mark.parametrize("name", ["patch", "remove", "restore"])
def test_ownership_failures_are_404(ctx: dict[str, Any], name: str) -> None:
    op, _ = OPS[name]
    pid = ctx["project_id"]
    created = upload(pid, ctx["revision_id"]).json()
    other_revision = make_revision(pid, "1", carry_forward_documents=False).json()["id"]
    foreign_project = make_project()
    foreign_revision = make_revision(foreign_project, "0").json()["id"]
    src = created["id"]

    unknown = op(pid, ctx["revision_id"], str(uuid.uuid4()), src)
    wrong_revision = op(pid, other_revision, created["id"], src)
    wrong_project = op(foreign_project, ctx["revision_id"], created["id"], src)
    mismatch = op(pid, foreign_revision, created["id"], src)
    no_project = op(str(uuid.uuid4()), ctx["revision_id"], created["id"], src)
    no_revision = op(pid, str(uuid.uuid4()), created["id"], src)

    for response, error in [
        (unknown, "revision_document_not_found"),
        (wrong_revision, "revision_document_not_found"),
        (wrong_project, "revision_project_mismatch"),
        (mismatch, "revision_project_mismatch"),
        (no_project, "project_not_found"),
        (no_revision, "revision_not_found"),
    ]:
        assert (response.status_code, code(response)) == (404, error)
    assert db_association(created["id"]).status is RevisionDocumentStatus.INCLUDED


# --- remove and restore ------------------------------------------------------------


def test_remove_keeps_the_document_and_the_stored_object(ctx: dict[str, Any]) -> None:
    pid, rid = ctx["project_id"], ctx["revision_id"]
    created = upload(pid, rid).json()
    facts, storage = document_facts(pid), ctx["storage"]
    calls_before = list(storage.calls)

    response = client.post(f"{docs_url(pid, rid)}/{created['id']}/remove")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "REMOVED"
    assert body["removed_at"] is not None
    row = db_association(created["id"])
    assert row.status is RevisionDocumentStatus.REMOVED
    assert row.removed_by is None
    assert document_facts(pid) == facts
    assert storage.calls == calls_before
    assert len(storage.objects) == 1
    assert listing(pid, rid) == []
    assert [i["id"] for i in listing(pid, rid, status="REMOVED")] == [created["id"]]


def test_remove_does_not_affect_the_same_document_in_another_revision(ctx: dict[str, Any]) -> None:
    pid, rid = ctx["project_id"], ctx["revision_id"]
    created = upload(pid, rid).json()
    child = make_revision(pid, "1").json()["id"]
    assert len(listing(pid, child)) == 1

    assert client.post(f"{docs_url(pid, rid)}/{created['id']}/remove").status_code == 200

    inherited = listing(pid, child)
    assert [i["status"] for i in inherited] == ["INCLUDED"]
    assert inherited[0]["document"]["id"] == created["document"]["id"]


def test_remove_and_restore_are_idempotent(ctx: dict[str, Any]) -> None:
    pid, rid = ctx["project_id"], ctx["revision_id"]
    created = upload(pid, rid).json()
    url = f"{docs_url(pid, rid)}/{created['id']}"

    untouched = client.post(f"{url}/restore")
    first = client.post(f"{url}/remove").json()
    time.sleep(0.05)
    second = client.post(f"{url}/remove").json()
    restored = client.post(f"{url}/restore").json()
    again = client.post(f"{url}/restore").json()

    assert untouched.status_code == 200 and untouched.json()["status"] == "INCLUDED"
    assert second["removed_at"] == first["removed_at"]
    assert (restored["status"], restored["removed_at"]) == ("INCLUDED", None)
    assert again == restored
    row = db_association(created["id"])
    assert (row.removed_at, row.removed_by) == (None, None)


# --- reuse -------------------------------------------------------------------------


def test_reuse_creates_an_inherited_association_to_the_same_document(ctx: dict[str, Any]) -> None:
    s = seeded(
        ctx,
        document_type="SPECIFICATION",
        document_number="S-1",
        description="spec",
        notes="note",
    )
    pid, storage = s["project_id"], s["storage"]
    facts, calls_before = document_facts(pid), list(storage.calls)

    response = client.post(
        f"{docs_url(pid, s['rev1'])}/reuse",
        json={"source_revision_document_id": s["a"]["id"]},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] != s["a"]["id"]
    assert body["revision_id"] == s["rev1"]
    assert body["origin"] == "INHERITED"
    assert body["status"] == "INCLUDED"
    assert body["inherited_from_revision_id"] == s["revision_id"]
    assert body["inherited_from_revision_identifier"] == "0"
    assert body["document"] == s["a"]["document"]
    assert (body["document_type"], body["document_number"]) == ("SPECIFICATION", "S-1")
    assert (body["description"], body["notes"]) == ("spec", "note")
    assert "duplicate_detected" not in body
    assert document_facts(pid) == facts
    assert storage.calls == calls_before
    assert [i["id"] for i in listing(pid, s["rev1"])] == [body["id"]]
    assert db_association(body["id"]).added_by is None


def test_reuse_overrides_replace_copied_metadata(ctx: dict[str, Any]) -> None:
    s = seeded(
        ctx, document_type="SPECIFICATION", document_number="S-1", description="d", notes="n"
    )

    body = client.post(
        f"{docs_url(s['project_id'], s['rev1'])}/reuse",
        json={
            "source_revision_document_id": s["a"]["id"],
            "document_type": "OTHER",
            "description": "new",
            "notes": None,
        },
    ).json()

    assert body["document_type"] == "OTHER"
    assert body["description"] == "new"
    assert body["notes"] is None
    assert body["document_number"] == "S-1"
    source = client.get(f"{docs_url(s['project_id'], s['revision_id'])}/{s['a']['id']}").json()
    assert source["document_type"] == "SPECIFICATION"
    assert source["description"] == "d"


@pytest.mark.parametrize(
    "extra",
    [
        {"document_type": None},
        {"status": "REMOVED"},
        {"document_id": str(uuid.uuid4())},
        {"description": "x" * 2001},
    ],
)
def test_invalid_reuse_bodies_are_rejected(ctx: dict[str, Any], extra: dict[str, Any]) -> None:
    s = seeded(ctx)
    url = f"{docs_url(s['project_id'], s['rev1'])}/reuse"

    response = client.post(url, json={"source_revision_document_id": s["a"]["id"], **extra})

    assert response.status_code == 422
    assert listing(s["project_id"], s["rev1"]) == []
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"source_revision_document_id": "nope"}).status_code == 422


def test_reuse_of_a_document_already_in_the_revision_is_a_conflict(ctx: dict[str, Any]) -> None:
    s = seeded(ctx)
    pid, rev1 = s["project_id"], s["rev1"]
    url = f"{docs_url(pid, rev1)}/reuse"
    first = client.post(url, json={"source_revision_document_id": s["a"]["id"]}).json()

    response = client.post(url, json={"source_revision_document_id": s["a"]["id"]})

    assert (response.status_code, code(response)) == (409, "document_already_in_revision")
    detail = response.json()["detail"]
    assert detail["existing_revision_document_id"] == first["id"]
    assert detail["existing_status"] == "INCLUDED"
    assert len(listing(pid, rev1, status="ALL")) == 1


def test_reuse_of_a_removed_association_tells_the_user_to_restore_it(ctx: dict[str, Any]) -> None:
    s = seeded(ctx)
    pid, rev1 = s["project_id"], s["rev1"]
    url = f"{docs_url(pid, rev1)}/reuse"
    first = client.post(url, json={"source_revision_document_id": s["a"]["id"]}).json()
    client.post(f"{docs_url(pid, rev1)}/{first['id']}/remove")

    response = client.post(url, json={"source_revision_document_id": s["a"]["id"]})

    assert (response.status_code, code(response)) == (409, "document_already_in_revision")
    detail = response.json()["detail"]
    assert "restore" in detail["detail"].lower()
    assert detail["existing_status"] == "REMOVED"
    assert detail["existing_revision_document_id"] == first["id"]
    assert len(listing(pid, rev1, status="ALL")) == 1
    restored = client.post(
        f"{docs_url(pid, rev1)}/{detail['existing_revision_document_id']}/restore"
    )
    assert restored.json()["status"] == "INCLUDED"


def test_reuse_from_a_removed_source_is_a_conflict(ctx: dict[str, Any]) -> None:
    s = seeded(ctx)
    pid = s["project_id"]
    client.post(f"{docs_url(pid, s['revision_id'])}/{s['a']['id']}/remove")

    response = client.post(
        f"{docs_url(pid, s['rev1'])}/reuse",
        json={"source_revision_document_id": s["a"]["id"]},
    )

    assert (response.status_code, code(response)) == (409, "document_removed")
    assert listing(pid, s["rev1"], status="ALL") == []


def test_reuse_with_an_unknown_source_is_404(ctx: dict[str, Any]) -> None:
    s = seeded(ctx)

    response = client.post(
        f"{docs_url(s['project_id'], s['rev1'])}/reuse",
        json={"source_revision_document_id": str(uuid.uuid4())},
    )

    assert (response.status_code, code(response)) == (404, "revision_document_not_found")


def test_reuse_from_another_project_is_rejected_at_service_and_database(
    ctx: dict[str, Any],
) -> None:
    s = seeded(ctx)
    other_project = make_project()
    other_revision = make_revision(other_project, "0", activate=True).json()["id"]
    foreign = upload(other_project, other_revision).json()

    response = client.post(
        f"{docs_url(s['project_id'], s['rev1'])}/reuse",
        json={"source_revision_document_id": foreign["id"]},
    )

    assert (response.status_code, code(response)) == (404, "cross_project_document_access")
    assert listing(s["project_id"], s["rev1"], status="ALL") == []
    with pytest.raises(IntegrityError) as caught, get_engine().begin() as connection:
        connection.execute(
            text(
                "INSERT INTO revision_documents "
                "(project_id, revision_id, document_id, origin, status, document_type) "
                "VALUES (CAST(:project AS uuid), CAST(:revision AS uuid), "
                "CAST(:document AS uuid), 'UPLOADED', 'INCLUDED', 'UNKNOWN')"
            ),
            {
                "project": s["project_id"],
                "revision": s["rev1"],
                "document": foreign["document"]["id"],
            },
        )
    assert caught.value.orig.diag.constraint_name == "fk_revision_documents_document"


def test_reuse_into_the_source_revision_is_a_conflict(ctx: dict[str, Any]) -> None:
    s = seeded(ctx)

    response = client.post(
        f"{docs_url(s['project_id'], s['revision_id'])}/reuse",
        json={"source_revision_document_id": s["a"]["id"]},
    )

    assert (response.status_code, code(response)) == (409, "document_already_in_revision")


def test_reuse_from_a_superseded_revision_is_allowed(ctx: dict[str, Any]) -> None:
    s = seeded(ctx)
    pid = s["project_id"]
    assert client.post(f"/api/projects/{pid}/revisions/{s['rev1']}/activate").status_code == 200
    rev2 = make_revision(pid, "2", carry_forward_documents=False).json()["id"]

    response = client.post(
        f"{docs_url(pid, rev2)}/reuse",
        json={"source_revision_document_id": s["a"]["id"]},
    )

    assert response.status_code == 201
    assert response.json()["inherited_from_revision_identifier"] == "0"


# --- mutability, re-check and locking ----------------------------------------------


@pytest.mark.parametrize("name", list(OPS))
@pytest.mark.parametrize(
    ("state", "error"),
    [
        ("DRAFT", None),
        ("ACTIVE", None),
        ("PAUSED", None),
        ("SUPERSEDED", "revision_read_only"),
        ("CANCELLED", "cancelled_project"),
        ("ARCHIVED", "archived_project"),
    ],
)
def test_mutability_matrix(
    require_db: None, use_storage: Any, name: str, state: str, error: str | None
) -> None:
    from powerforge_api.storage import InMemoryObjectStorage

    use_storage(InMemoryObjectStorage())
    pid, target, assoc, source = matrix_scenario(state)
    op, success = OPS[name]
    before = snapshot(pid)

    response = op(pid, target, assoc, source)

    if error is None:
        assert response.status_code == success, response.text
    else:
        assert (response.status_code, code(response)) == (409, error)
        assert snapshot(pid) == before
    assert client.get(docs_url(pid, target)).status_code == 200


@pytest.mark.parametrize("name", list(OPS))
@pytest.mark.parametrize(
    ("flip", "error"),
    [
        (
            "UPDATE project_revisions SET status = 'SUPERSEDED' WHERE id = :revision",
            "revision_read_only",
        ),
        ("UPDATE projects SET status = 'ARCHIVED' WHERE id = :project", "archived_project"),
        ("UPDATE projects SET status = 'CANCELLED' WHERE id = :project", "cancelled_project"),
    ],
)
def test_status_flipped_after_the_early_load_is_caught_under_lock(
    require_db: None,
    use_storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    flip: str,
    error: str,
) -> None:
    from powerforge_api.storage import InMemoryObjectStorage

    use_storage(InMemoryObjectStorage())
    pid, target, assoc, source = matrix_scenario("DRAFT")
    before = snapshot(pid)
    original = DocumentService._load_context

    def flipping(self: DocumentService, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        set_sql(flip, project=pid, revision=target)
        return result

    monkeypatch.setattr(DocumentService, "_load_context", flipping)
    op, _ = OPS[name]

    response = op(pid, target, assoc, source)

    assert (response.status_code, code(response)) == (409, error)
    assert snapshot(pid) == before


@pytest.mark.parametrize("name", list(OPS))
def test_every_mutation_locks_project_for_share_then_revision_for_update(
    require_db: None, use_storage: Any, name: str
) -> None:
    from powerforge_api.storage import InMemoryObjectStorage

    use_storage(InMemoryObjectStorage())
    pid, target, assoc, source = matrix_scenario("DRAFT")
    op, success = OPS[name]

    with captured_sql() as statements:
        assert op(pid, target, assoc, source).status_code == success

    share = [i for i, s in enumerate(statements) if "FROM projects" in s and "FOR SHARE" in s]
    revision_lock = [
        i for i, s in enumerate(statements) if "FROM project_revisions" in s and "FOR UPDATE" in s
    ]
    assert share and revision_lock
    assert share[0] < revision_lock[0]
    assert not any(s.lstrip().startswith("UPDATE projects") for s in statements)


def test_archive_waits_for_an_in_flight_mutation_then_blocks_the_next_one(
    ctx: dict[str, Any],
) -> None:
    pid, rid = ctx["project_id"], ctx["revision_id"]
    created = upload(pid, rid).json()
    holder = get_session_factory()()
    lock_project_shared(holder, uuid.UUID(pid))
    outcome: dict[str, Any] = {}

    def archive() -> None:
        outcome["response"] = TestClient(app).post(f"/api/projects/{pid}/archive")

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
    rejected = client.post(f"{docs_url(pid, rid)}/{created['id']}/remove")
    assert (rejected.status_code, code(rejected)) == (409, "archived_project")


# --- workflow and races ------------------------------------------------------------


def test_replacing_a_document_in_a_new_revision_leaves_the_old_one_unchanged(
    ctx: dict[str, Any],
) -> None:
    pid, rev0 = ctx["project_id"], ctx["revision_id"]
    a = upload(pid, rev0, PDF, "sld_reva.pdf").json()
    rev1 = make_revision(pid, "1").json()["id"]
    inherited = listing(pid, rev1)
    assert [i["document"]["id"] for i in inherited] == [a["document"]["id"]]
    b = upload(pid, rev1, png_bytes(), "sld_revb.png").json()

    assert client.post(f"{docs_url(pid, rev1)}/{inherited[0]['id']}/remove").status_code == 200

    assert [i["id"] for i in listing(pid, rev1)] == [b["id"]]
    assert [i["id"] for i in listing(pid, rev0)] == [a["id"]]
    assert len(documents_of(pid)) == 2


def test_two_concurrent_reuses_of_the_same_document_produce_one_row(ctx: dict[str, Any]) -> None:
    s = seeded(ctx)
    url = f"{docs_url(s['project_id'], s['rev1'])}/reuse"

    def run(_: int) -> Any:
        return TestClient(app).post(url, json={"source_revision_document_id": s["a"]["id"]})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(run, range(2), timeout=JSON_TIMEOUT))

    assert sorted(r.status_code for r in responses) == [201, 409]
    loser = next(r for r in responses if r.status_code == 409)
    assert code(loser) == "document_already_in_revision"
    assert len(listing(s["project_id"], s["rev1"], status="ALL")) == 1


def test_unique_constraint_backstop_maps_to_document_already_in_revision(
    ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    s = seeded(ctx)
    pid, rev1 = s["project_id"], s["rev1"]
    url = f"{docs_url(pid, rev1)}/reuse"
    client.post(url, json={"source_revision_document_id": s["a"]["id"]})
    monkeypatch.setattr(DocumentService, "_existing_association", lambda *_a, **_k: None)

    response = client.post(url, json={"source_revision_document_id": s["a"]["id"]})

    assert (response.status_code, code(response)) == (409, "document_already_in_revision")
    assert len(listing(pid, rev1, status="ALL")) == 1


def test_an_unrelated_constraint_failure_is_not_reported_as_already_in_revision(
    ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    s = seeded(ctx)
    monkeypatch.setattr(DocumentService, "_existing_association", lambda *_a, **_k: None)

    # Reusing into the source's own revision trips ck_..._inherited_not_self, which is
    # checked before the unique index and must stay an unexpected error.
    response = client.post(
        f"{docs_url(s['project_id'], s['revision_id'])}/reuse",
        json={"source_revision_document_id": s["a"]["id"]},
    )

    assert (response.status_code, code(response)) == (500, "unexpected_integrity_error")
    assert len(listing(s["project_id"], s["revision_id"], status="ALL")) == 1


# --- logging and API surface -------------------------------------------------------


def test_logs_report_events_without_values_filenames_or_notes(
    ctx: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    s = seeded(ctx)
    pid, rid = s["project_id"], s["revision_id"]
    url = f"{docs_url(pid, rid)}/{s['a']['id']}"
    upload(pid, rid, png_bytes(), "TOP-SECRET-name.png")
    caplog.clear()

    client.patch(url, json={"description": "SECRET-DESC", "notes": "SECRET-NOTE"})
    client.post(f"{url}/remove")
    client.post(f"{url}/remove")
    client.post(f"{url}/restore")
    client.post(f"{url}/restore")
    client.post(
        f"{docs_url(pid, s['rev1'])}/reuse",
        json={"source_revision_document_id": s["a"]["id"], "notes": "SECRET-NOTE"},
    )

    messages = [r.getMessage() for r in caplog.records]
    assert messages.count("document metadata updated") == 1
    assert messages.count("document removed") == 1
    assert messages.count("document restored") == 1
    assert messages.count("document reused") == 1
    updated = next(r for r in caplog.records if r.getMessage() == "document metadata updated")
    assert updated.changed_fields == ["description", "notes"]
    everything = " ".join(str(v) for r in caplog.records for v in r.__dict__.values())
    for forbidden in ("SECRET-DESC", "SECRET-NOTE", "TOP-SECRET", "a.pdf", "original.pdf"):
        assert forbidden not in everything


def test_openapi_lists_the_mutation_endpoints_and_forbids_extra_fields() -> None:
    spec = app.openapi()
    base = "/api/projects/{project_id}/revisions/{revision_id}/documents"
    item = f"{base}/{{revision_document_id}}"

    assert set(spec["paths"][f"{base}/reuse"]) == {"post"}
    assert set(spec["paths"][item]) == {"get", "patch"}
    assert set(spec["paths"][f"{item}/remove"]) == {"post"}
    assert set(spec["paths"][f"{item}/restore"]) == {"post"}
    schemas = spec["components"]["schemas"]
    assert schemas["RevisionDocumentUpdate"]["additionalProperties"] is False
    assert schemas["ReuseDocumentRequest"]["additionalProperties"] is False


def test_the_size_guard_applies_to_the_upload_route_only() -> None:
    from powerforge_api.routers.documents import UploadSizeGuardRoute, router

    guarded = [r for r in router.routes if isinstance(r, UploadSizeGuardRoute)]

    assert [(sorted(r.methods), r.path.endswith("/documents")) for r in guarded] == [
        (["POST"], True)
    ]
