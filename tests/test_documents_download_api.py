"""Signed download URLs. Integration cases need RUN_INTEGRATION=1; the MinIO case also needs MinIO.

Shared helpers are in ``documents_support``; the ``require_db``, ``use_storage``, ``ctx`` and
``s3_scratch_storage`` fixtures are in ``conftest.py``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest

from documents_support import (
    captured_sql,
    client,
    code,
    docs_url,
    documents_of,
    make_project,
    make_revision,
    upload,
)
from file_factory import PDF, png_bytes
from powerforge_api.main import app
from powerforge_api.storage import InMemoryObjectStorage, StorageError
from powerforge_shared.config import Settings, get_settings

SECRET_NAME = "TOP-SECRET-plan.pdf"


@pytest.fixture
def expiry() -> Iterator[Callable[[int], None]]:
    def set_expiry(seconds: int) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(
            s3_signed_url_expires_seconds=seconds
        )

    yield set_expiry
    app.dependency_overrides.pop(get_settings, None)


def download(project_id: Any, revision_id: Any, revision_document_id: Any, **params: str) -> Any:
    return client.get(
        f"{docs_url(project_id, revision_id)}/{revision_document_id}/download-url", params=params
    )


def query(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlparse(url).query).items()}


@pytest.fixture
def stored(ctx: dict[str, Any]) -> dict[str, Any]:
    """Revision "0" (ACTIVE) holding one uploaded PDF named SECRET_NAME."""
    uploaded = upload(ctx["project_id"], ctx["revision_id"], PDF, SECRET_NAME)
    assert uploaded.status_code == 201, uploaded.text
    return {**ctx, "doc": uploaded.json()}


def location(s: dict[str, Any]) -> tuple[str, str, str]:
    return s["project_id"], s["revision_id"], s["doc"]["id"]


# --- the URL ------------------------------------------------------------------------


def test_url_is_scoped_to_the_documents_object_and_carries_the_stored_facts(
    stored: dict[str, Any],
) -> None:
    response = download(*location(stored))

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"url", "expires_at", "filename"}
    assert body["filename"] == SECRET_NAME
    [document] = documents_of(stored["project_id"])
    assert stored["storage"].calls_for("create_download_url") == [document.storage_key]
    assert unquote(urlparse(body["url"]).path).endswith(document.storage_key)
    params = query(body["url"])
    assert params["response-content-type"] == "application/pdf"
    assert params["response-content-disposition"].startswith("attachment;")
    assert SECRET_NAME in params["response-content-disposition"]


def test_the_browser_content_type_is_not_used_for_the_signed_content_type(
    ctx: dict[str, Any],
) -> None:
    pid, rid = ctx["project_id"], ctx["revision_id"]
    created = client.post(
        docs_url(pid, rid),
        files={"file": ("shot.png", png_bytes(), "application/x-msdownload")},
    ).json()

    url = download(pid, rid, created["id"]).json()["url"]

    assert query(url)["response-content-type"] == "image/png"


def test_attachment_is_the_default_and_inline_is_supported(stored: dict[str, Any]) -> None:
    default = query(download(*location(stored)).json()["url"])
    attachment = query(download(*location(stored), disposition="attachment").json()["url"])
    inline = query(download(*location(stored), disposition="inline").json()["url"])

    assert default["response-content-disposition"].startswith("attachment;")
    assert attachment["response-content-disposition"].startswith("attachment;")
    assert inline["response-content-disposition"].startswith("inline;")


@pytest.mark.parametrize("value", ["bogus", "INLINE", "", "inline;attachment"])
def test_an_invalid_disposition_is_rejected_before_anything_is_signed(
    stored: dict[str, Any], value: str
) -> None:
    response = download(*location(stored), disposition=value)

    assert response.status_code == 422
    assert stored["storage"].calls_for("create_download_url") == []


def test_expiry_follows_the_setting(stored: dict[str, Any], expiry: Callable[[int], None]) -> None:
    expiry(60)
    before = datetime.now(UTC)

    body = download(*location(stored)).json()

    after = datetime.now(UTC)
    assert query(body["url"])["expires"] == "60"
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert before + timedelta(seconds=60) <= expires_at <= after + timedelta(seconds=60)


def test_the_default_expiry_is_fifteen_minutes(stored: dict[str, Any]) -> None:
    assert query(download(*location(stored)).json()["url"])["expires"] == "900"


def test_the_response_is_not_cacheable(stored: dict[str, Any]) -> None:
    assert download(*location(stored)).headers["cache-control"] == "no-store"


# --- always readable ----------------------------------------------------------------


def test_a_removed_association_can_still_be_downloaded(stored: dict[str, Any]) -> None:
    pid, rid, rd = location(stored)
    assert client.post(f"{docs_url(pid, rid)}/{rd}/remove").status_code == 200

    assert download(pid, rid, rd).status_code == 200


@pytest.mark.parametrize("state", ["SUPERSEDED", "PAUSED", "CANCELLED", "ARCHIVED"])
def test_history_is_downloadable_in_every_revision_and_project_state(state: str, ctx: Any) -> None:
    pid, rev0 = ctx["project_id"], ctx["revision_id"]
    a = upload(pid, rev0, PDF, "a.pdf").json()["id"]
    if state == "SUPERSEDED":
        rev1 = make_revision(pid, "1", activate=True)
        assert rev1.status_code == 201, rev1.text
    else:
        action = {"PAUSED": "pause", "CANCELLED": "cancel", "ARCHIVED": "archive"}[state]
        assert client.post(f"/api/projects/{pid}/{action}").status_code == 200

    response = download(pid, rev0, a)

    assert response.status_code == 200, response.text
    assert ctx["storage"].calls_for("create_download_url")


# --- scoping ------------------------------------------------------------------------


def test_the_association_must_belong_to_the_given_revision(stored: dict[str, Any]) -> None:
    pid, _, rd = location(stored)
    other = make_revision(pid, "1", carry_forward_documents=False).json()["id"]

    response = download(pid, other, rd)

    assert (response.status_code, code(response)) == (404, "revision_document_not_found")
    assert stored["storage"].calls_for("create_download_url") == []


def test_another_projects_ids_never_yield_a_url(stored: dict[str, Any]) -> None:
    pid, rid, rd = location(stored)
    other_pid = make_project()
    other_rid = make_revision(other_pid, "0").json()["id"]

    same_revision_other_project = download(other_pid, rid, rd)
    other_revision_same_association = download(other_pid, other_rid, rd)
    own_revision_foreign_project_ids = download(pid, other_rid, rd)

    assert (same_revision_other_project.status_code, code(same_revision_other_project)) == (
        404,
        "revision_project_mismatch",
    )
    assert (
        other_revision_same_association.status_code,
        code(other_revision_same_association),
    ) == (404, "revision_document_not_found")
    assert (
        own_revision_foreign_project_ids.status_code,
        code(own_revision_foreign_project_ids),
    ) == (
        404,
        "revision_project_mismatch",
    )
    assert stored["storage"].calls_for("create_download_url") == []


def test_unknown_ids_are_not_found_with_the_right_codes(stored: dict[str, Any]) -> None:
    pid, rid, rd = location(stored)
    unknown = uuid.uuid4()

    assert code(download(unknown, rid, rd)) == "project_not_found"
    assert code(download(pid, unknown, rd)) == "revision_not_found"
    assert code(download(pid, rid, unknown)) == "revision_document_not_found"
    assert download(pid, rid, "not-a-uuid").status_code == 422
    assert stored["storage"].calls_for("create_download_url") == []


def test_there_is_no_unscoped_document_route(stored: dict[str, Any]) -> None:
    rd = stored["doc"]["id"]
    document_id = stored["doc"]["document"]["id"]

    for path in (
        f"/api/documents/{document_id}",
        f"/api/documents/{document_id}/download-url",
        f"/api/documents/{rd}/download-url",
        f"/api/revision-documents/{rd}/download-url",
        f"/api/projects/{stored['project_id']}/documents/{document_id}/download-url",
    ):
        assert client.get(path).status_code == 404, path

    scoped = "/api/projects/{project_id}/revisions/{revision_id}/documents"
    document_paths = [p for p in app.openapi()["paths"] if "document" in p]
    assert document_paths
    assert all(p.startswith(scoped) for p in document_paths)


def test_no_response_exposes_the_storage_key(stored: dict[str, Any]) -> None:
    pid, rid, rd = location(stored)
    [document] = documents_of(pid)

    listing = client.get(docs_url(pid, rid))
    single = client.get(f"{docs_url(pid, rid)}/{rd}")

    assert document.storage_key not in listing.text
    assert document.storage_key not in single.text
    assert "storage_key" not in listing.text + single.text


# --- a read: no writes, no locks ----------------------------------------------------


def test_issuing_a_url_writes_nothing_and_takes_no_locks(stored: dict[str, Any]) -> None:
    pid, rid, rd = location(stored)
    before = client.get(f"/api/projects/{pid}/revisions/{rid}").json()

    with captured_sql() as statements:
        assert download(pid, rid, rd).status_code == 200

    assert statements
    for statement in statements:
        normalized = " ".join(statement.upper().split())
        assert not normalized.startswith(("INSERT", "UPDATE", "DELETE")), statement
        assert "FOR UPDATE" not in normalized and "FOR SHARE" not in normalized, statement
    assert client.get(f"/api/projects/{pid}/revisions/{rid}").json() == before


# --- failure and hygiene ------------------------------------------------------------


def test_a_signing_failure_is_a_clean_502_without_sdk_details(
    stored: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    stored["storage"].fail_on(
        "create_download_url", StorageError("endpoint http://minio.internal:9000 refused")
    )

    response = download(*location(stored))

    assert (response.status_code, code(response)) == (502, "storage_download_failed")
    assert "minio.internal" not in response.text
    assert "http://" not in response.text
    errors = [r for r in caplog.records if r.getMessage() == "download url signing failed"]
    assert [r.error_class for r in errors] == ["StorageError"]
    everything = " ".join(str(v) for r in caplog.records for v in r.__dict__.values())
    assert "minio.internal" not in everything
    assert not [r for r in caplog.records if r.getMessage() == "document download url issued"]


def test_the_log_records_the_event_but_never_the_url_filename_or_key(
    stored: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    pid, rid, rd = location(stored)
    [document] = documents_of(pid)
    caplog.clear()

    body = download(pid, rid, rd, disposition="inline").json()

    issued = [r for r in caplog.records if r.getMessage() == "document download url issued"]
    assert len(issued) == 1
    record = issued[0]
    assert str(record.project_id) == pid
    assert str(record.revision_id) == rid
    assert str(record.revision_document_id) == rd
    assert str(record.document_id) == str(document.id)
    assert record.disposition == "inline"
    assert record.expires_seconds == 900
    everything = " ".join(str(v) for r in caplog.records for v in r.__dict__.values())
    for forbidden in (body["url"], SECRET_NAME, "original.pdf", document.storage_key):
        assert forbidden not in everything


def test_openapi_documents_the_download_route() -> None:
    spec = app.openapi()
    path = "/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}"
    operation = spec["paths"][f"{path}/download-url"]["get"]

    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/DownloadUrlResponse")
    assert set(spec["components"]["schemas"]["DownloadUrlResponse"]["properties"]) == {
        "url",
        "expires_at",
        "filename",
    }
    disposition = next(p for p in operation["parameters"] if p["name"] == "disposition")
    assert disposition["schema"]["enum"] == ["attachment", "inline"]
    assert disposition["schema"]["default"] == "attachment"


# --- real object storage --------------------------------------------------------------


@pytest.mark.integration
def test_the_signed_url_serves_the_bytes_from_real_object_storage(
    require_db: None,
    use_storage: Callable[[InMemoryObjectStorage], InMemoryObjectStorage],
    s3_scratch_storage: Any,
    expiry: Callable[[int], None],
) -> None:
    use_storage(s3_scratch_storage)
    expiry(60)
    pid = make_project()
    rid = make_revision(pid, "0", activate=True).json()["id"]
    created = upload(pid, rid, PDF, "Plan é.pdf")
    assert created.status_code == 201, created.text
    rd = created.json()["id"]
    [document] = documents_of(pid)

    attachment = download(pid, rid, rd, disposition="attachment").json()
    inline = download(pid, rid, rd, disposition="inline").json()

    public = get_settings().s3_public_endpoint().rstrip("/")
    assert attachment["url"].startswith(public)
    assert query(attachment["url"])["X-Amz-Expires"] == "60"
    served = httpx.get(attachment["url"])
    assert served.status_code == 200
    assert served.content == PDF
    assert served.headers["content-type"] == "application/pdf"
    assert served.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''Plan%20%C3%A9.pdf" in served.headers["content-disposition"]
    shown = httpx.get(inline["url"])
    assert shown.status_code == 200
    assert shown.headers["content-disposition"].startswith("inline;")

    unsigned = httpx.get(f"{public}/{s3_scratch_storage.bucket}/{document.storage_key}")
    assert unsigned.status_code == 403
    tampered = httpx.get(attachment["url"].replace("attachment", "inline"))
    assert tampered.status_code == 403
