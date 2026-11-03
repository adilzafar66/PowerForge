"""Shared behavioral fixtures for the orchestration slice."""

import hashlib
from io import BytesIO

import pytest
from sqlalchemy import select

from documents_support import client
from extraction_support import source, url
from powerforge_api.db import get_session_factory
from powerforge_api.main import app
from powerforge_document_processing.models import DocumentPage, PageArtifact
from powerforge_extraction.enqueue import get_extraction_enqueue
from powerforge_extraction.fake import FakeExtractionProvider
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_shared.config import Settings, get_settings


class RecordingDelivery:
    def __init__(self):
        self.ids = []
        self.fail = False

    def enqueue(self, unit_id):
        if self.fail:
            raise RuntimeError("PRIVATE credential payload must not appear in logs")
        self.ids.append(unit_id)


@pytest.fixture
def execution_ctx(ctx):
    settings = Settings(
        _env_file=None, extraction_backoff_seconds=0, extraction_redispatch_seconds=1
    )
    delivery = RecordingDelivery()
    src = source(ctx)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_extraction_enqueue] = lambda: delivery
    try:
        yield {
            **ctx,
            "src": src,
            "settings": settings,
            "delivery": delivery,
            "base": url(ctx, src),
            "factory": get_session_factory(),
        }
    finally:
        with get_session_factory().begin() as session:
            runs = session.scalars(
                select(ExtractionRun).where(
                    ExtractionRun.document_id == src["document"],
                    ExtractionRun.status.in_(["PENDING", "RUNNING"]),
                )
            ).all()
            for run in runs:
                ExtractionCoordinator(session, settings).cancel(run.id)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_extraction_enqueue, None)


def add_page(ctx, number=2):
    payload = f"Page {number}: source observation".encode()
    with ctx["factory"]() as session:
        page = DocumentPage(
            document_id=ctx["src"]["document"],
            page_number=number,
            source_width=612,
            source_height=792,
            source_unit="POINTS",
            rotation_degrees=0,
            native_text_char_count=len(payload),
        )
        session.add(page)
        session.flush()
        artifact = PageArtifact(
            document_page_id=page.id,
            processing_run_id=ctx["src"]["processing"],
            artifact_type="NATIVE_TEXT",
            storage_key=f"processing/{ctx['src']['processing']}/{number}.txt",
            mime_type="text/plain",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        ctx["storage"].put(artifact.storage_key, BytesIO(payload), len(payload), "text/plain")
        session.add(artifact)
        session.commit()


def start_run(ctx, **body):
    response = client.post(ctx["base"] + "/runs", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def units(ctx, run_id):
    from uuid import UUID

    with ctx["factory"]() as session:
        return list(
            session.scalars(
                select(ExtractionWorkUnit.id)
                .where(ExtractionWorkUnit.run_id == UUID(str(run_id)))
                .order_by(ExtractionWorkUnit.unit_key, ExtractionWorkUnit.attempt_number)
            )
        )


def execute(ctx, unit_id, provider=None):
    from powerforge_extraction.execution import execute_unit

    selected = provider or FakeExtractionProvider()
    return execute_unit(
        unit_id, ctx["factory"], ctx["storage"], ctx["settings"], lambda claim: selected
    )


def detail(ctx, run_id):
    response = client.get(ctx["base"] + f"/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def expire(ctx, unit_id):
    from datetime import timedelta

    with ctx["factory"].begin() as session:
        unit = session.get(ExtractionWorkUnit, unit_id)
        unit.lease_expires_at = ExtractionCoordinator(session, ctx["settings"]).now() - timedelta(
            seconds=1
        )
