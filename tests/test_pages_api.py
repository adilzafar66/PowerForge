"""Page and artifact URL routes. Integration cases need RUN_INTEGRATION=1.

The database fixture creates a database, upgrades it to head, and drops it. It does not
use the Compose development database.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import sessionmaker

from documents_support import client, code, docs_url, make_project, make_revision, upload
from file_factory import PDF
from powerforge_document_model import (
    PageArtifactType,
    ProcessingRunStatus,
    RevisionDocumentStatus,
    SourceUnit,
    build_artifact_key,
)
from powerforge_document_processing.enqueue import get_processing_enqueue
from powerforge_document_processing.models import (
    Document,
    DocumentPage,
    DocumentProcessingRun,
    PageArtifact,
    Project,
    ProjectRevision,
    RevisionDocument,
)
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_document_processing.storage.memory import InMemoryObjectStorage
from powerforge_project import ProjectStatus, RevisionStatus
from powerforge_shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = "database/alembic.ini"
ANALYSIS = b"analysis-bytes"
THUMBNAIL = b"thumbnail-bytes"


class RecordingEnqueue:
    def __init__(self) -> None:
        self.calls: list[uuid.UUID] = []

    def enqueue_document_processing(self, run_id: uuid.UUID) -> None:
        self.calls.append(run_id)


def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION") == "1"


def _alembic(url: URL, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", ALEMBIC_INI, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"
    )


@pytest.fixture(scope="module")
def scratch_engine() -> Iterator[Engine]:
    if not _integration_enabled():
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    base = make_url(get_settings().database_url)
    name = f"powerforge_pages_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    engine = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        url = base.set(database=name)
        _alembic(url, "upgrade", "head")
        engine = create_engine(url)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def api(scratch_engine: Engine):
    from powerforge_api.db import get_session
    from powerforge_api.main import app

    factory = sessionmaker(bind=scratch_engine, expire_on_commit=False)
    storage = InMemoryObjectStorage()
    enqueue = RecordingEnqueue()

    def session_override():
        bound = factory()
        try:
            yield bound
        finally:
            bound.close()

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_processing_enqueue] = lambda: enqueue
    try:
        yield factory, storage
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_object_storage, None)
        app.dependency_overrides.pop(get_processing_enqueue, None)


def _upload(filename: str = "sheet.pdf") -> tuple[str, str, str, str]:
    project_id = make_project()
    revision_id = make_revision(project_id, "0", activate=True).json()["id"]
    created = upload(project_id, revision_id, PDF, filename)
    assert created.status_code == 201, created.text
    body = created.json()
    return project_id, revision_id, body["id"], body["document"]["id"]


def _set_status(factory, document_id: str, **values: object) -> DocumentProcessingRun:
    with factory() as session:
        run = session.scalar(
            select(DocumentProcessingRun)
            .where(DocumentProcessingRun.document_id == uuid.UUID(document_id))
            .order_by(DocumentProcessingRun.attempt_count.desc())
        )
        assert run is not None
        for key, value in values.items():
            setattr(run, key, value)
        session.commit()
        session.refresh(run)
        session.expunge(run)
        return run


def _pages_url(project_id: str, revision_id: str, association_id: str) -> str:
    return f"{docs_url(project_id, revision_id)}/{association_id}/pages"


def _add_pages(
    factory,
    document_id: str,
    run_id: uuid.UUID,
    *,
    old_run_id: uuid.UUID | None = None,
):
    with factory() as session:
        document = session.get(Document, uuid.UUID(document_id))
        assert document is not None
        page = DocumentPage(
            document_id=document.id,
            page_number=1,
            source_width=Decimal("612"),
            source_height=Decimal("792"),
            source_unit=SourceUnit.POINTS,
            rotation_degrees=90,
            native_text_char_count=4,
        )
        other = DocumentPage(
            document_id=document.id,
            page_number=2,
            source_width=Decimal("100"),
            source_height=Decimal("200"),
            source_unit=SourceUnit.PIXELS,
            rotation_degrees=0,
            native_text_char_count=0,
        )
        session.add_all([page, other])
        session.flush()
        current_key = build_artifact_key(
            document.project_id,
            document.id,
            run_id,
            1,
            PageArtifactType.ANALYSIS_IMAGE,
        )
        thumb_key = build_artifact_key(
            document.project_id,
            document.id,
            run_id,
            1,
            PageArtifactType.THUMBNAIL,
        )
        session.add(
            PageArtifact(
                document_page_id=page.id,
                processing_run_id=run_id,
                artifact_type=PageArtifactType.ANALYSIS_IMAGE,
                storage_key=current_key,
                mime_type="image/png",
                size_bytes=len(ANALYSIS),
                sha256=hashlib.sha256(ANALYSIS).hexdigest(),
                width_px=1000,
                height_px=1400,
            )
        )
        session.add(
            PageArtifact(
                document_page_id=page.id,
                processing_run_id=run_id,
                artifact_type=PageArtifactType.THUMBNAIL,
                storage_key=thumb_key,
                mime_type="image/webp",
                size_bytes=len(THUMBNAIL),
                sha256=hashlib.sha256(THUMBNAIL).hexdigest(),
                width_px=400,
                height_px=560,
            )
        )
        if old_run_id is not None:
            old_key = build_artifact_key(
                document.project_id,
                document.id,
                old_run_id,
                1,
                PageArtifactType.ANALYSIS_IMAGE,
            )
            session.add(
                PageArtifact(
                    document_page_id=page.id,
                    processing_run_id=old_run_id,
                    artifact_type=PageArtifactType.ANALYSIS_IMAGE,
                    storage_key=old_key,
                    mime_type="image/x-old",
                    size_bytes=3,
                    sha256="ab" * 32,
                    width_px=1,
                    height_px=1,
                )
            )
        session.commit()
        return page.id, other.id, current_key


def test_pages_and_urls_wait_until_the_run_is_completed(api) -> None:
    factory, _storage = api
    project_id, revision_id, association_id, document_id = _upload()
    pages = _pages_url(project_id, revision_id, association_id)
    pending = client.get(pages)
    assert (pending.status_code, code(pending)) == (409, "processing_not_complete")
    one_page = client.get(f"{pages}/{uuid.uuid4()}")
    assert (one_page.status_code, code(one_page)) == (409, "processing_not_complete")

    _set_status(factory, document_id, status=ProcessingRunStatus.RUNNING, pages_total=1)
    assert code(client.get(pages)) == "processing_not_complete"
    assert (
        code(client.get(f"{pages}/{uuid.uuid4()}/artifacts/ANALYSIS_IMAGE/url"))
        == "processing_not_complete"
    )

    _set_status(
        factory,
        document_id,
        status=ProcessingRunStatus.FAILED,
        error_code="CORRUPT_PDF",
        error_message="Could not read the file",
    )
    assert code(client.get(pages)) == "processing_not_complete"


def test_completed_pages_hide_storage_keys_and_older_attempts(api) -> None:
    factory, _storage = api
    project_id, revision_id, association_id, document_id = _upload()
    failed = _set_status(
        factory,
        document_id,
        status=ProcessingRunStatus.FAILED,
        error_code="CORRUPT_PDF",
        error_message="Could not read the file",
    )
    retried = client.post(
        f"{docs_url(project_id, revision_id)}/{association_id}/processing/retry"
    )
    assert retried.status_code == 200, retried.text
    completed = _set_status(
        factory,
        document_id,
        status=ProcessingRunStatus.COMPLETED,
        pages_processed=2,
        pages_total=2,
    )
    page_id, second_id, storage_key = _add_pages(
        factory, document_id, completed.id, old_run_id=failed.id
    )

    listing = client.get(_pages_url(project_id, revision_id, association_id))
    assert listing.status_code == 200, listing.text
    body = listing.json()["items"]
    assert [page["page_number"] for page in body] == [1, 2]
    first = body[0]
    assert first["id"] == str(page_id)
    assert first["source_width"] == "612"
    assert first["source_height"] == "792"
    assert first["source_unit"] == "POINTS"
    assert first["rotation_degrees"] == 90
    assert first["native_text_char_count"] == 4
    assert first["artifacts"] == [
        {
            "artifact_type": "ANALYSIS_IMAGE",
            "mime_type": "image/png",
            "width_px": 1000,
            "height_px": 1400,
        },
        {
            "artifact_type": "THUMBNAIL",
            "mime_type": "image/webp",
            "width_px": 400,
            "height_px": 560,
        },
    ]
    assert body[1]["source_unit"] == "PIXELS"
    assert body[1]["artifacts"] == []
    assert body[1]["native_text_char_count"] == 0
    assert storage_key not in listing.text
    assert "storage_key" not in listing.text
    assert "image/x-old" not in listing.text

    single = client.get(f"{_pages_url(project_id, revision_id, association_id)}/{page_id}")
    assert single.status_code == 200
    assert single.json()["id"] == str(page_id)
    assert storage_key not in single.text
    missing = client.get(
        f"{_pages_url(project_id, revision_id, association_id)}/{page_id}/artifacts/NATIVE_TEXT/url"
    )
    assert (missing.status_code, code(missing)) == (404, "page_not_found")
    unknown = client.get(
        f"{_pages_url(project_id, revision_id, association_id)}/{page_id}/artifacts/NOT_A_TYPE/url"
    )
    assert (unknown.status_code, code(unknown)) == (404, "page_not_found")
    assert second_id


def test_a_foreign_page_or_project_is_not_found(api) -> None:
    factory, _storage = api
    project_id, revision_id, association_id, document_id = _upload()
    other_project, other_revision, other_association, other_document = _upload("other.pdf")
    completed = _set_status(factory, document_id, status=ProcessingRunStatus.COMPLETED)
    other_completed = _set_status(factory, other_document, status=ProcessingRunStatus.COMPLETED)
    page_id, _second, _key = _add_pages(factory, document_id, completed.id)
    foreign_page, _ignored, _foreign_key = _add_pages(factory, other_document, other_completed.id)

    pages = _pages_url(project_id, revision_id, association_id)
    foreign = client.get(f"{pages}/{foreign_page}")
    assert (foreign.status_code, code(foreign)) == (404, "page_not_found")
    foreign_url = client.get(f"{pages}/{foreign_page}/artifacts/ANALYSIS_IMAGE/url")
    assert (foreign_url.status_code, code(foreign_url)) == (404, "page_not_found")

    mismatched = client.get(
        f"{_pages_url(other_project, revision_id, association_id)}/{page_id}"
    )
    assert mismatched.status_code == 404
    unknown_association = client.get(f"{_pages_url(project_id, revision_id, str(uuid.uuid4()))}")
    assert code(unknown_association) == "revision_document_not_found"
    assert client.get(f"{pages}/{uuid.uuid4()}").status_code == 404
    assert other_association
    assert other_revision


def test_removed_superseded_and_archived_can_read_completed_pages(api) -> None:
    factory, _storage = api
    project_id, revision_id, association_id, document_id = _upload()
    completed = _set_status(factory, document_id, status=ProcessingRunStatus.COMPLETED)
    page_id, _second, _key = _add_pages(factory, document_id, completed.id)
    with factory() as session:
        association = session.get(RevisionDocument, uuid.UUID(association_id))
        assert association is not None
        association.status = RevisionDocumentStatus.REMOVED
        association.removed_at = datetime.now(UTC)
        project = session.get(Project, uuid.UUID(project_id))
        assert project is not None
        project.status = ProjectStatus.ARCHIVED
        revision = session.get(ProjectRevision, uuid.UUID(revision_id))
        assert revision is not None
        revision.status = RevisionStatus.SUPERSEDED
        session.commit()

    pages = _pages_url(project_id, revision_id, association_id)
    listing = client.get(pages)
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"][0]["id"] == str(page_id)
    signed = client.get(f"{pages}/{page_id}/artifacts/ANALYSIS_IMAGE/url")
    assert signed.status_code == 200, signed.text
    assert signed.json()["filename"] == "analysis.png"
    assert signed.headers["cache-control"] == "no-store"


def test_signed_artifact_url_serves_bytes_and_leaves_the_original_download(
    api,
    s3_scratch_storage,
) -> None:
    from powerforge_api.main import app

    factory, _memory = api
    app.dependency_overrides[get_object_storage] = lambda: s3_scratch_storage
    project_id, revision_id, association_id, document_id = _upload()
    original = client.get(f"{docs_url(project_id, revision_id)}/{association_id}/download-url")
    assert original.status_code == 200, original.text
    assert original.headers["cache-control"] == "no-store"
    served = httpx.get(original.json()["url"])
    assert served.status_code == 200
    assert served.content == PDF

    completed = _set_status(factory, document_id, status=ProcessingRunStatus.COMPLETED)
    page_id, _second, storage_key = _add_pages(factory, document_id, completed.id)
    s3_scratch_storage.put(storage_key, BytesIO(ANALYSIS), len(ANALYSIS), "image/png")
    thumb_key = build_artifact_key(
        uuid.UUID(project_id),
        uuid.UUID(document_id),
        completed.id,
        1,
        PageArtifactType.THUMBNAIL,
    )
    s3_scratch_storage.put(thumb_key, BytesIO(THUMBNAIL), len(THUMBNAIL), "image/webp")

    artifact = f"{_pages_url(project_id, revision_id, association_id)}/{page_id}"
    signed = client.get(f"{artifact}/artifacts/ANALYSIS_IMAGE/url")
    assert signed.status_code == 200, signed.text
    assert signed.headers["cache-control"] == "no-store"
    assert signed.json()["filename"] == "analysis.png"
    assert set(signed.json()) == {"url", "expires_at", "filename"}
    fetched = httpx.get(signed.json()["url"])
    assert fetched.status_code == 200
    assert fetched.content == ANALYSIS
    assert fetched.headers["content-type"] == "image/png"
    assert "analysis.png" in fetched.headers["content-disposition"]
    assert fetched.headers["content-disposition"].startswith("inline;")

    public = get_settings().s3_public_endpoint().rstrip("/")
    unsigned = httpx.get(f"{public}/{s3_scratch_storage.bucket}/{storage_key}")
    assert unsigned.status_code == 403
