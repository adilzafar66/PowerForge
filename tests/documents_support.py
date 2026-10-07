"""Shared helpers for the document API tests (no fixtures; those live in conftest.py)."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text

from file_factory import PDF
from powerforge_api.db import get_engine, get_session_factory
from powerforge_api.main import app
from powerforge_api.models import Document, RevisionDocument
from powerforge_api.storage import InMemoryObjectStorage
from powerforge_document_model import DocumentOrigin, RevisionDocumentStatus

client = TestClient(app)

OLD = datetime(2020, 1, 1, tzinfo=UTC)
JSON_TIMEOUT = 20


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
