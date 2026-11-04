"""Disposable engineering-stage plans and explicitly scripted, non-model observations."""

import hashlib
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from PIL import Image
from sqlalchemy import select

from engineering_grounding_support import attribute, attributes, equipment, recognition
from extraction_execution_support import execution_ctx as execution_ctx
from extraction_execution_support import start_run
from powerforge_ai.extraction import ExecutionUsage, ExtractionResponse
from powerforge_document_processing.models import DocumentProcessingRun, PageArtifact
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.profiles import ENGINEERING_TEST_PROFILE

TEXT = "2-Winding Transformer TX-1\nSecondary Voltage: 600 V"


def processing(ctx, *, native=TEXT, image=True):
    with ctx["factory"].begin() as session:
        run = DocumentProcessingRun(
            document_id=ctx["src"]["document"],
            processor_version="m4-fixture-v1",
            profile_version="m4-fixture-v1",
            profile_hash=str(uuid4()),
            status="COMPLETED",
        )
        session.add(run)
        session.flush()
        artifacts = []
        values = []
        if native is not None:
            values.append(("NATIVE_TEXT", native.encode(), "text/plain", None, None))
        if image:
            content = BytesIO()
            Image.new("RGB", (20, 20), "white").save(content, format="PNG")
            values.append(("ANALYSIS_IMAGE", content.getvalue(), "image/png", 20, 20))
        for kind, data, mime, width, height in values:
            key = f"processing/{run.id}/{kind}"
            artifact = PageArtifact(
                document_page_id=ctx["src"]["page"],
                processing_run_id=run.id,
                artifact_type=kind,
                storage_key=key,
                mime_type=mime,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                width_px=width,
                height_px=height,
            )
            ctx["storage"].put(key, BytesIO(data), len(data), mime)
            session.add(artifact)
            session.flush()
            artifacts.append(artifact.id)
        return run.id, artifacts


@pytest.fixture
def engineering_ctx(execution_ctx):
    ctx = execution_ctx
    processing(ctx)
    return ctx


def start_engineering(ctx, **body):
    return start_run(ctx, **{"profile_key": ENGINEERING_TEST_PROFILE, **body})


def attempt(ctx, rid, stage, *, number=None):
    with ctx["factory"]() as session:
        stmt = select(ExtractionWorkUnit.id).where(
            ExtractionWorkUnit.run_id == UUID(str(rid)),
            ExtractionWorkUnit.stage == stage,
        )
        if number is not None:
            stmt = stmt.where(ExtractionWorkUnit.attempt_number == number)
        return session.scalar(stmt.order_by(ExtractionWorkUnit.attempt_number.desc()))


class StageProvider:
    def __init__(self, *, visual=False, empty_recognition=False, failure=None, on_call=None):
        self.visual, self.empty_recognition = visual, empty_recognition
        self.failure, self.on_call = failure, on_call
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if self.on_call:
            self.on_call(request)
        if self.failure:
            failure = self.failure(request)
            if failure:
                raise failure
        if request.stage == "EQUIPMENT_RECOGNITION":
            result = (
                recognition()
                if self.empty_recognition
                else recognition(
                    equipment("2-Winding Transformer TX-1", tag="TX-1", visual=self.visual)
                )
            )
        else:
            result = attributes(
                attribute(
                    visual=self.visual, equipment_ref=None if self.empty_recognition else "eq1"
                )
            )
        return ExtractionResponse[request.response_model](
            result=result,
            usage=ExecutionUsage(input_tokens=20, cached_input_tokens=2, output_tokens=16),
        )
