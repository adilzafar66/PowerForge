"""Constraint-name IntegrityError mapping (PR-03)."""

from __future__ import annotations

import logging
import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from powerforge_api.db import get_engine, get_session_factory
from powerforge_api.db_errors import constraint_name, integrity_guard, translate_integrity_error
from powerforge_api.exceptions import (
    DuplicateProjectNumber,
    DuplicateRevisionIdentifier,
    UnexpectedIntegrityError,
)
from powerforge_api.main import app
from powerforge_api.models import Project, ProjectRevision
from powerforge_api.services.revision_service import RevisionService
from powerforge_project import RevisionStatus

client = TestClient(app)

SENTINEL = "secret-identifier"


class _FakeDiag:
    def __init__(
        self,
        constraint_name: str | None = None,
        sqlstate: str | None = None,
    ) -> None:
        self.constraint_name = constraint_name
        self.sqlstate = sqlstate


class _FakeOrig(Exception):
    def __init__(
        self,
        constraint_name: str | None = None,
        sqlstate: str | None = "23505",
        message: str = "integrity violation",
    ) -> None:
        super().__init__(message)
        self.diag = _FakeDiag(constraint_name, sqlstate)
        self.sqlstate = sqlstate


class _OrigWithoutDiag(Exception):
    pass


def _integrity_error(
    name: str | None = "uq_example",
    *,
    sqlstate: str | None = "23505",
    message: str = "integrity violation",
    orig: Exception | None | object = ...,
) -> IntegrityError:
    if orig is ...:
        orig = _FakeOrig(name, sqlstate, message)
    return IntegrityError("INSERT INTO example", {SENTINEL: SENTINEL}, orig)


def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION") == "1"


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _detail(response) -> dict | str:
    body = response.json()
    return body.get("detail", body)


@pytest.fixture
def require_db() -> None:
    if not _integration_enabled():
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def test_constraint_name_from_diag() -> None:
    exc = _integrity_error("uq_projects_project_number")
    assert constraint_name(exc) == "uq_projects_project_number"


def test_constraint_name_missing_diag() -> None:
    exc = _integrity_error(orig=_OrigWithoutDiag("no diag"))
    assert constraint_name(exc) is None


def test_constraint_name_orig_none() -> None:
    exc = _integrity_error(orig=None)
    assert constraint_name(exc) is None


def test_constraint_name_none_on_diag() -> None:
    exc = _integrity_error(None)
    assert constraint_name(exc) is None


def test_translate_known_constraint_returns_mapped_error() -> None:
    mapped = DuplicateProjectNumber("already exists")
    result = translate_integrity_error(
        _integrity_error("uq_projects_project_number", message=SENTINEL),
        {"uq_projects_project_number": mapped},
        operation="create_project",
    )
    assert result is mapped


def test_translate_unknown_constraint_logs_name_not_user_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    result = translate_integrity_error(
        _integrity_error(
            "ck_unmapped_test",
            sqlstate="23514",
            message=f"new row violates check constraint: {SENTINEL}",
        ),
        {"uq_projects_project_number": DuplicateProjectNumber("dup")},
        operation="create_revision",
    )
    assert isinstance(result, UnexpectedIntegrityError)
    assert not isinstance(result, DuplicateRevisionIdentifier)
    assert SENTINEL not in result.message
    assert "ck_unmapped_test" in caplog.text
    assert "23514" in caplog.text
    assert "create_revision" in caplog.text
    assert SENTINEL not in caplog.text


def test_translate_missing_constraint_name_is_unexpected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    result = translate_integrity_error(
        _integrity_error(None, message=SENTINEL),
        {"uq_projects_project_number": DuplicateProjectNumber("dup")},
        operation="create_project",
    )
    assert isinstance(result, UnexpectedIntegrityError)
    assert "constraint=None" in caplog.text
    assert SENTINEL not in caplog.text


def test_integrity_guard_maps_rolls_back_and_chains() -> None:
    session = MagicMock()
    mapped = DuplicateRevisionIdentifier("dup")
    cause = _integrity_error("uq_project_revisions_project_id_identifier")
    with pytest.raises(DuplicateRevisionIdentifier) as caught:
        with integrity_guard(
            session,
            {"uq_project_revisions_project_id_identifier": mapped},
            operation="create_revision",
        ):
            raise cause
    assert caught.value is mapped
    assert caught.value.__cause__ is cause
    session.rollback.assert_called_once()


def test_integrity_guard_unknown_becomes_unexpected() -> None:
    session = MagicMock()
    cause = _integrity_error("ck_other")
    with pytest.raises(UnexpectedIntegrityError) as caught:
        with integrity_guard(session, {}, operation="create_revision"):
            raise cause
    assert caught.value.__cause__ is cause
    session.rollback.assert_called_once()


def test_integrity_guard_passes_through_other_errors() -> None:
    session = MagicMock()
    with pytest.raises(ValueError, match="nope"):
        with integrity_guard(session, {}, operation="create_revision"):
            raise ValueError("nope")
    session.rollback.assert_not_called()


@pytest.mark.integration
def test_psycopg_reports_duplicate_identifier_constraint(require_db: None) -> None:
    project_id = client.post(
        "/api/projects",
        json={"project_number": _unique("DIAG-ID"), "project_name": "Diag Identifier"},
    ).json()["id"]
    assert (
        client.post(
            f"/api/projects/{project_id}/revisions",
            json={"identifier": "A"},
        ).status_code
        == 201
    )

    session = get_session_factory()()
    try:
        session.add(
            ProjectRevision(
                project_id=uuid.UUID(project_id),
                identifier="A",
                status=RevisionStatus.DRAFT,
            )
        )
        with pytest.raises(IntegrityError) as caught:
            session.commit()
        assert constraint_name(caught.value) == "uq_project_revisions_project_id_identifier"
        session.rollback()
    finally:
        session.close()


@pytest.mark.integration
def test_psycopg_reports_one_active_constraint(require_db: None) -> None:
    project_id = client.post(
        "/api/projects",
        json={"project_number": _unique("DIAG-ACT"), "project_name": "Diag Active"},
    ).json()["id"]
    first = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "1", "activate": True},
    ).json()
    assert first["status"] == "ACTIVE"

    session = get_session_factory()()
    try:
        session.add(
            ProjectRevision(
                project_id=uuid.UUID(project_id),
                identifier="rogue",
                status=RevisionStatus.ACTIVE,
            )
        )
        with pytest.raises(IntegrityError) as caught:
            session.commit()
        assert constraint_name(caught.value) == "uq_project_revisions_one_active"
        session.rollback()
    finally:
        session.close()


@pytest.mark.integration
def test_psycopg_reports_fk_constraint(require_db: None) -> None:
    session = get_session_factory()()
    try:
        session.add(
            ProjectRevision(
                project_id=uuid.uuid4(),
                identifier="fk-test",
                status=RevisionStatus.DRAFT,
            )
        )
        with pytest.raises(IntegrityError) as caught:
            session.commit()
        assert constraint_name(caught.value) == "fk_project_revisions_project_id"
        session.rollback()
    finally:
        session.close()


@pytest.mark.integration
def test_unknown_constraint_is_not_reported_as_duplicate(
    require_db: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    project_id = client.post(
        "/api/projects",
        json={"project_number": _unique("UNK"), "project_name": "Unknown Constraint"},
    ).json()["id"]
    caplog.set_level(logging.ERROR, logger="powerforge_api.db_errors")

    def boom(self: Session, *args: object, **kwargs: object) -> None:
        raise _integrity_error(
            "ck_unmapped_test",
            sqlstate="23514",
            message=f"new row for relation project_revisions violates {SENTINEL}",
        )

    monkeypatch.setattr(Session, "flush", boom)
    response = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "X"},
    )
    assert response.status_code == 500
    detail = _detail(response)
    assert detail["code"] == "unexpected_integrity_error"
    assert SENTINEL not in response.text
    assert "duplicate" not in detail["detail"].lower()
    assert "ck_unmapped_test" in caplog.text
    assert SENTINEL not in caplog.text

    monkeypatch.undo()
    ok = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "X"},
    )
    assert ok.status_code == 201, ok.text


@pytest.mark.integration
def test_one_active_violation_maps_to_revision_not_activatable(
    require_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = client.post(
        "/api/projects",
        json={"project_number": _unique("D1"), "project_name": "One Active Mapping"},
    ).json()["id"]
    revision = client.post(
        f"/api/projects/{project_id}/revisions",
        json={"identifier": "0"},
    ).json()

    def insert_rogue(
        self: RevisionService,
        project: Project,
        revision_obj: ProjectRevision,
    ) -> None:
        self.session.add(
            ProjectRevision(
                project_id=project.id,
                identifier=_unique("rogue"),
                status=RevisionStatus.ACTIVE,
            )
        )
        self.session.flush()
        revision_obj.status = RevisionStatus.ACTIVE

    monkeypatch.setattr(RevisionService, "_activate_locked", insert_rogue)
    response = client.post(f"/api/projects/{project_id}/revisions/{revision['id']}/activate")
    assert response.status_code == 409
    assert _detail(response)["code"] == "revision_not_activatable"
