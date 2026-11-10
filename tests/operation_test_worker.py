"""Celery integration app that replaces both external and OCR providers."""

import json
import os

from extraction_worker import extraction_tasks, tesseract
from extraction_worker.celery_app import celery_app as celery_app
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
extraction_tasks.provider_for = lambda _claim: FakeEnrichedProvider()
