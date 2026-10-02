"""Project and revision API tests. Integration cases require RUN_INTEGRATION=1."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from powerforge_api.db import get_engine, get_session_factory
from powerforge_api.main import app
from powerforge_api.models import ProjectRevision
from powerforge_project import RevisionStatus

client = TestClient(app)


def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION") == "1"


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _detail(response) -> dict | str:
    body = response.json()
    detail = body.get("detail", body)
    return detail


@pytest.fixture
def require_db() -> None:
    if not _integration_enabled():
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


@pytest.mark.integration
def test_create_and_get_project(require_db: None) -> None:
    number = _unique("P")
    create = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Alpha Hospital"},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["project_number"] == number
    assert body["status"] == "ACTIVE"
    assert body["active_revision_identifier"] is None
    assert body["engineer_names"] == []

    fetched = client.get(f"/api/projects/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["project_name"] == "Alpha Hospital"


@pytest.mark.integration
def test_duplicate_project_number_rejected(require_db: None) -> None:
    number = _unique("DUP")
    assert client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "One"},
    ).status_code == 201
    duplicate = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Two"},
    )
    assert duplicate.status_code == 409
    assert _detail(duplicate)["code"] == "duplicate_project_number"


@pytest.mark.integration
def test_patch_rejects_status_and_project_number(require_db: None) -> None:
    number = _unique("PATCH")
    created = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Meta"},
    ).json()
    project_id = created["id"]

    bad_status = client.patch(f"/api/projects/{project_id}", json={"status": "PAUSED"})
    assert bad_status.status_code == 422

    bad_number = client.patch(
        f"/api/projects/{project_id}",
        json={"project_number": "NOPE"},
    )
    assert bad_number.status_code == 422

    ok = client.patch(
        f"/api/projects/{project_id}",
        json={"project_name": "Meta Updated", "engineer_names": ["Ada", "Bob"]},
    )
    assert ok.status_code == 200
    assert ok.json()["project_name"] == "Meta Updated"
    assert ok.json()["engineer_names"] == ["Ada", "Bob"]


@pytest.mark.integration
def test_pause_resume_cancel_archive_unarchive(require_db: None) -> None:
    number = _unique("LIFE")
    project_id = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Lifecycle"},
    ).json()["id"]

    assert client.post(f"/api/projects/{project_id}/pause").json()["status"] == "PAUSED"
    assert client.post(f"/api/projects/{project_id}/resume").json()["status"] == "ACTIVE"
    assert client.post(f"/api/projects/{project_id}/cancel").json()["status"] == "CANCELLED"

    invalid = client.post(f"/api/projects/{project_id}/resume")
    assert invalid.status_code == 409

    archived = client.post(f"/api/projects/{project_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert archived.json()["archived_at"] is not None
    assert archived.json()["status_before_archive"] == "CANCELLED"

    patch = client.patch(f"/api/projects/{project_id}", json={"project_name": "Nope"})
    assert patch.status_code == 409
    assert _detail(patch)["code"] == "archived_project"

    unarchived = client.post(f"/api/projects/{project_id}/unarchive")
    assert unarchived.status_code == 200
    assert unarchived.json()["status"] == "CANCELLED"
    assert unarchived.json()["archived_at"] is None
    assert unarchived.json()["status_before_archive"] is None


@pytest.mark.integration
def test_unarchive_restores_active_and_paused(require_db: None) -> None:
    active_id = client.post(
        "/api/projects",
        json={"project_number": _unique("ARC-A"), "project_name": "Archive Active"},
    ).json()["id"]
    archived_active = client.post(f"/api/projects/{active_id}/archive")
    assert archived_active.json()["status"] == "ARCHIVED"
    assert archived_active.json()["status_before_archive"] == "ACTIVE"
    restored_active = client.post(f"/api/projects/{active_id}/unarchive")
    assert restored_active.json()["status"] == "ACTIVE"
    assert restored_active.json()["status_before_archive"] is None

    paused_id = client.post(
        "/api/projects",
        json={"project_number": _unique("ARC-P"), "project_name": "Archive Paused"},
    ).json()["id"]
    assert client.post(f"/api/projects/{paused_id}/pause").json()["status"] == "PAUSED"
    archived_paused = client.post(f"/api/projects/{paused_id}/archive")
    assert archived_paused.json()["status_before_archive"] == "PAUSED"
    restored_paused = client.post(f"/api/projects/{paused_id}/unarchive")
    assert restored_paused.json()["status"] == "PAUSED"
    assert restored_paused.json()["status_before_archive"] is None


@pytest.mark.integration
def test_list_search_and_status_filter(require_db: None) -> None:
    needle = _unique("SEARCH")
    client_needle = _unique("CLIENT")
    address_needle = _unique("ADDR")
    created = client.post(
        "/api/projects",
        json={
            "project_number": needle,
            "project_name": "Searchable Plant",
            "client_name": client_needle,
            "project_address": address_needle,
        },
    )
    assert created.status_code == 201

    listed = client.get("/api/projects", params={"search": needle})
    assert listed.status_code == 200
    assert any(item["project_number"] == needle for item in listed.json()["items"])

    by_client = client.get("/api/projects", params={"search": client_needle})
    assert by_client.status_code == 200
    assert any(item["project_number"] == needle for item in by_client.json()["items"])

    by_address = client.get("/api/projects", params={"search": address_needle})
    assert by_address.status_code == 200
    assert any(item["project_number"] == needle for item in by_address.json()["items"])

    filtered = client.get("/api/projects", params={"status": "ACTIVE", "search": needle})
    assert filtered.status_code == 200
    assert all(item["status"] == "ACTIVE" for item in filtered.json()["items"])


@pytest.mark.integration
def test_revision_create_activate_and_supersede(require_db: None) -> None:
    number = _unique("REV")
    project_id = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Revisioned"},
    ).json()["id"]

    first = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "0", "activate": True},
    )
    assert first.status_code == 201
    assert first.json()["status"] == "ACTIVE"

    second = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "1"},
    )
    assert second.status_code == 201
    assert second.json()["status"] == "DRAFT"

    activated = client.post(
        f"/api/projects/{project_id}/revisions/{second.json()['id']}/activate"
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"

    revisions = client.get(f"/api/projects/{project_id}/revisions").json()["items"]
    by_id = {item["identifier"]: item["status"] for item in revisions}
    assert by_id["0"] == "SUPERSEDED"
    assert by_id["1"] == "ACTIVE"

    project = client.get(f"/api/projects/{project_id}").json()
    assert project["active_revision_identifier"] == "1"

    # Idempotent activate
    again = client.post(
        f"/api/projects/{project_id}/revisions/{second.json()['id']}/activate"
    )
    assert again.status_code == 200
    assert again.json()["status"] == "ACTIVE"

    # Superseded cannot be re-activated
    superseded = client.post(
        f"/api/projects/{project_id}/revisions/{first.json()['id']}/activate"
    )
    assert superseded.status_code == 409
    assert _detail(superseded)["code"] == "revision_not_activatable"


@pytest.mark.integration
def test_cannot_activate_older_draft_than_current_active(require_db: None) -> None:
    number = _unique("OLD")
    project_id = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Ordering"},
    ).json()["id"]
    older = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "0"},
    ).json()
    newer = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "1", "activate": True},
    ).json()
    assert newer["status"] == "ACTIVE"
    assert older["status"] == "DRAFT"

    blocked = client.post(
        f"/api/projects/{project_id}/revisions/{older['id']}/activate"
    )
    assert blocked.status_code == 409
    assert _detail(blocked)["code"] == "revision_not_activatable"


@pytest.mark.integration
def test_duplicate_revision_identifier_rejected(require_db: None) -> None:
    number = _unique("RID")
    project_id = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Ids"},
    ).json()["id"]
    assert (
        client.post(
            f"/api/projects/{project_id}/revisions",
            json={"identifier": "A"},
        ).status_code
        == 201
    )
    duplicate = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "A"},
    )
    assert duplicate.status_code == 409

    other = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "B"},
    ).json()
    rename = client.patch(
        f"/api/projects/{project_id}/revisions/{other['id']}",
        json={"identifier": "A"},
    )
    assert rename.status_code == 409


@pytest.mark.integration
def test_cancelled_project_is_read_only(require_db: None) -> None:
    number = _unique("CAN")
    project_id = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Cancel Me"},
    ).json()["id"]
    revision = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "0"},
    ).json()

    assert client.post(f"/api/projects/{project_id}/cancel").json()["status"] == "CANCELLED"

    patch = client.patch(f"/api/projects/{project_id}", json={"project_name": "Nope"})
    assert patch.status_code == 409
    assert _detail(patch)["code"] == "cancelled_project"

    blocked_create = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "1"},
    )
    assert blocked_create.status_code == 409
    assert _detail(blocked_create)["code"] == "cancelled_project"

    blocked_activate = client.post(
        f"/api/projects/{project_id}/revisions/{revision['id']}/activate"
    )
    assert blocked_activate.status_code == 409

    # Archive is still allowed from CANCELLED.
    archived = client.post(f"/api/projects/{project_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"


@pytest.mark.integration
def test_revision_wrong_project_and_archived_guards(require_db: None) -> None:
    a = client.post(
        "/api/projects",
        json={"project_number": _unique("A"), "project_name": "A"},
    ).json()
    b = client.post(
        "/api/projects",
        json={"project_number": _unique("B"), "project_name": "B"},
    ).json()
    revision = client.post(
        f"/api/projects/{a['id']}/revisions",
        json={"identifier": "R1"},
    ).json()

    mismatch = client.get(f"/api/projects/{b['id']}/revisions/{revision['id']}")
    assert mismatch.status_code == 404

    client.post(f"/api/projects/{a['id']}/archive")
    blocked_create = client.post(
        f"/api/projects/{a['id']}/revisions",
        json={"identifier": "R2"},
    )
    assert blocked_create.status_code == 409
    blocked_activate = client.post(
        f"/api/projects/{a['id']}/revisions/{revision['id']}/activate"
    )
    assert blocked_activate.status_code == 409


@pytest.mark.integration
def test_not_found_project(require_db: None) -> None:
    missing = client.get(f"/api/projects/{uuid.uuid4()}")
    assert missing.status_code == 404


@pytest.mark.integration
def test_partial_unique_active_revision_constraint(require_db: None) -> None:
    number = _unique("UQ")
    project_id = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Constraint"},
    ).json()["id"]
    first = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "1", "activate": True},
    ).json()
    assert first["status"] == "ACTIVE"

    session = get_session_factory()()
    try:
        rogue = ProjectRevision(
            project_id=uuid.UUID(project_id),
            identifier="rogue",
            status=RevisionStatus.ACTIVE,
        )
        session.add(rogue)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()


@pytest.mark.integration
def test_concurrent_activate_leaves_one_active(require_db: None) -> None:
    number = _unique("CONC")
    project_id = client.post(
        "/api/projects",
        json={"project_number": number, "project_name": "Concurrent"},
    ).json()["id"]
    rev_a = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "A"},
    ).json()["id"]
    rev_b = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "B"},
    ).json()["id"]

    def activate(revision_id: str) -> int:
        local = TestClient(app)
        return local.post(
            f"/api/projects/{project_id}/revisions/{revision_id}/activate"
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(activate, [rev_a, rev_b]))

    assert all(code in {200, 409} for code in results)
    revisions = client.get(f"/api/projects/{project_id}/revisions").json()["items"]
    active = [item for item in revisions if item["status"] == "ACTIVE"]
    assert len(active) == 1
