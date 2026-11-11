"""Celery integration app that replaces both external and OCR providers."""

import json
import os
from types import SimpleNamespace

from extraction_worker import extraction_tasks, tesseract
from extraction_worker.celery_app import celery_app as celery_app
from powerforge_ai.extraction import ExtractionResponse
from powerforge_ai.ocr import (
    OCRFailure,
    OCRFailureCode,
    OCRIdentity,
    OCRResponse,
    OCRSettings,
    OCRUsage,
    OCRWord,
)
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.enriched_observations import RESPONSES, SCHEMAS
from powerforge_extraction.table_reconstruction_v4 import CompactReconstructionResponse


class StubOCR:
    def __init__(self, *_args):
        configuration = json.loads(os.environ["ENRICHMENT_OCR_CONFIGURATION"])
        self.identity = OCRIdentity.model_validate_json(json.dumps(configuration["identity"]))
        self.settings = OCRSettings.model_validate_json(json.dumps(configuration["settings"]))

    def recognize(self, request):
        if request.width_px > 2 * request.height_px:
            raise OCRFailure(OCRFailureCode.INVALID_OUTPUT)
        return OCRResponse(
            request_id=request.request_id,
            image_artifact_id=request.image_artifact_id,
            image_sha256=request.image_sha256,
            width_px=request.width_px,
            height_px=request.height_px,
            identity=self.identity,
            words=(
                OCRWord(
                    order=0,
                    text="TX-1",
                    left=70,
                    top=80,
                    width=40,
                    height=20,
                    block=0,
                    paragraph=0,
                    line=0,
                    confidence=None,
                ),
            ),
            usage=OCRUsage(elapsed_ms=0),
        )


tesseract.TesseractProvider = StubOCR


class OperationProvider:
    def execute(self, request):
        model = request.response_model
        body = dict(schema_version=request.schema_version, overflowed=False)
        if model is CompactReconstructionResponse:
            body.update(partitions=[], reported_tables=[])
        else:
            legacy = FakeEnrichedProvider().execute(
                SimpleNamespace(
                    stage=request.stage,
                    text=request.text,
                    response_model=RESPONSES[request.stage],
                    schema_version=SCHEMAS[request.stage],
                    upstream_context=request.upstream_context,
                )
            )
            body.update(legacy.result.model_dump(mode="json", exclude={"schema_version"}))
            for item in body.get("equipment", []) + body.get("attributes", []):
                for anchor in item.get("anchors", []):
                    anchor.update(
                        role="EQUIPMENT" if request.stage == "EQUIPMENT_RECOGNITION" else "CONTEXT",
                        quote=item["raw_expression"],
                    )
        return ExtractionResponse[model](result=model.model_validate(body), usage={})


extraction_tasks.provider_for = lambda _claim: OperationProvider()
