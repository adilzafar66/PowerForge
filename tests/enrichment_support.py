"""Real processing/OCR inputs and isolated integration settings; no model transport."""

import json
from uuid import UUID

import pytest
from sqlalchemy import select, text

from documents_support import client, upload
from extraction_worker.tesseract import TesseractProvider
from powerforge_api.db import get_session_factory
from powerforge_api.main import app
from powerforge_document_processing.models import DocumentProcessingRun
from powerforge_document_processing.processing import ProcessingService
from powerforge_extraction.enqueue import get_extraction_enqueue
from powerforge_extraction.enrichment_execution import execute_preparation
from powerforge_extraction.models import ExtractionRun
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_shared.config import Settings, get_settings
from test_enrichment_native import native_pdf


class Delivery:
    def __init__(self):
        self.ids = []
        self.sources = []

    def enqueue(self, uid):
        self.ids.append(uid)

    def enqueue_source(self, uid):
        self.sources.append(uid)

    def enqueue_document_processing(self, rid):
        pass


@pytest.fixture
def enrichment_ctx(ctx):
    provider = TesseractProvider()
    settings = Settings(
        _env_file=None,
        enrichment_enabled=True,
        extraction_backoff_seconds=0,
        enrichment_ocr_configuration=json.dumps(
            {
                "identity": provider.identity.model_dump(mode="json"),
                "settings": provider.settings.model_dump(mode="json"),
            }
        ),
        extraction_redispatch_seconds=1,
    )
    delivery = Delivery()
    factory = get_session_factory()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_extraction_enqueue] = lambda: delivery
    data = {
        **ctx,
        "factory": factory,
        "settings": settings,
        "provider": provider,
        "delivery": delivery,
    }
    try:
        yield build_source(data, native_pdf(), "source.pdf")
    finally:
        with factory.begin() as session:
            for run in session.scalars(
                select(ExtractionRun).where(
                    ExtractionRun.document_id == data["document"],
                    ExtractionRun.status.in_(["PENDING", "RUNNING"]),
                )
            ):
                ExtractionCoordinator(session, settings).cancel(
                    run.id, purpose=run.execution_purpose
                )
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_extraction_enqueue, None)


def build_source(ctx, payload, filename):
    response = upload(ctx["project_id"], ctx["revision_id"], payload, filename)
    assert response.status_code == 201, response.text
    body = response.json()
    document = UUID(body["document"]["id"])
    association = body["id"]
    with ctx["factory"]() as session:
        service = ProcessingService(session, ctx["storage"], ctx["delivery"])
        run = service.ensure_document_processing(document)
        service.claim_and_process(run.id)
        processing = session.get(DocumentProcessingRun, run.id)
        assert processing.status == "COMPLETED", processing.error_code
        processing_id = processing.id
    ctx.update(
        document=document,
        processing=processing_id,
        base=f"/api/projects/{ctx['project_id']}/revisions/{ctx['revision_id']}/documents/{association}",
    )
    return ctx


def start(ctx, **overrides):
    body = {"processing_run_id": str(ctx["processing"]), "pages": [1], **overrides}
    response = client.post(ctx["base"] + "/source-enrichment/runs", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def detail(ctx, rid):
    response = client.get(ctx["base"] + f"/source-enrichment/runs/{rid}")
    assert response.status_code == 200, response.text
    return response.json()


def execute(ctx, uid):
    return execute_preparation(
        UUID(str(uid)), ctx["factory"], ctx["storage"], ctx["settings"], lambda: ctx["provider"]
    )


def snapshot_base(ctx):
    with ctx["factory"]() as session:
        return [
            session.execute(
                text(
                    f"SELECT to_jsonb(t) FROM {table} t WHERE "
                    + (
                        "id=:d"
                        if table == "documents"
                        else (
                            "processing_run_id IN (SELECT id FROM document_processing_runs "
                            "WHERE document_id=:d)"
                        )
                        if table == "page_artifacts"
                        else "document_id=:d"
                    )
                    + " ORDER BY id"
                ),
                {"d": ctx["document"]},
            )
            .scalars()
            .all()
            for table in (
                "documents",
                "document_processing_runs",
                "document_pages",
                "page_artifacts",
            )
        ]
