"""Local, gold-blind OCR tiles used only by the F1-A benchmark."""

from io import BytesIO
from pathlib import Path
from time import monotonic
from uuid import uuid4

from PIL import Image

from powerforge_ai.ocr import OCRRequest, OCRResponse, OCRUsage, validate_ocr_response
from powerforge_extraction.enrichment_prepare import sha

REGIONAL_VERSION = "ink-tiles-2x3-v1"


def selected_tiles(image):
    """Take up to six ink-bearing tiles with overlap for OCR context."""
    w, h = image.size
    gray = image.convert("L")
    # A dark-background tile can carry reversed text. Blank or almost solid
    # tiles provide little useful text context either way.
    for row in range(3):
        for col in range(2):
            core = (col * w // 2, row * h // 3, (col + 1) * w // 2, (row + 1) * h // 3)
            x0, y0, x1, y1 = core
            histogram = gray.crop(core).histogram()
            fraction = sum(histogram[:160]) / ((x1 - x0) * (y1 - y0))
            if 0.002 <= fraction <= 0.98:
                margin = max(1, round(min(w, h) * 0.025))
                crop = (
                    max(0, x0 - margin),
                    max(0, y0 - margin),
                    min(w, x1 + margin),
                    min(h, y1 + margin),
                )
                yield core, crop


def owns(box, x, y):
    x0, y0, x1, y1 = box
    return x0 <= x < x1 and y0 <= y < y1


class RegionalOCR:
    def __init__(self, provider):
        self.provider = provider
        self.settings = provider.settings
        self.identity = provider.identity.model_copy(
            update={
                "adapter_version": REGIONAL_VERSION,
                "build_sha256": sha(
                    (provider.identity.build_sha256 + sha(Path(__file__).read_bytes())).encode()
                ),
            }
        )
        self.receipts = []

    def recognize(self, request):
        started = monotonic()
        self.receipts = []
        words = []
        with Image.open(BytesIO(request.image)) as image:
            for core, crop in selected_tiles(image):
                remaining = request.timeout_seconds - (monotonic() - started)
                if remaining < 1:
                    raise ValueError("Regional aggregate OCR deadline exceeded")
                buffer = BytesIO()
                image.crop(crop).save(buffer, format="PNG")
                data = buffer.getvalue()
                x, y, right, bottom = crop
                tile = OCRRequest(
                    request_id=uuid4(),
                    image_artifact_id=uuid4(),
                    image_sha256=sha(data),
                    image=data,
                    width_px=right - x,
                    height_px=bottom - y,
                    expected_identity=self.provider.identity,
                    settings=self.provider.settings,
                    timeout_seconds=int(remaining),
                )
                result = validate_ocr_response(tile, self.provider.recognize(tile))
                # Keep exactly the core owning a token's center. The halo is context only.
                owner_blocks = {}
                kept = 0
                for word in result.words:
                    left, top = word.left + x, word.top + y
                    if not owns(core, left + word.width / 2, top + word.height / 2):
                        continue
                    block = owner_blocks.setdefault(word.block, len(owner_blocks))
                    words.append(
                        word.model_copy(
                            update={
                                "left": left,
                                "top": top,
                                "order": len(words),
                                "block": len(self.receipts) * 2048 + block,
                            }
                        )
                    )
                    kept += 1
                self.receipts.append(
                    dict(
                        core=core,
                        crop=crop,
                        sha256=tile.image_sha256,
                        elapsed_ms=result.usage.elapsed_ms,
                        recognized=len(result.words),
                        kept=kept,
                    )
                )
        return OCRResponse(
            request_id=request.request_id,
            image_artifact_id=request.image_artifact_id,
            image_sha256=request.image_sha256,
            width_px=request.width_px,
            height_px=request.height_px,
            identity=self.identity,
            words=tuple(words),
            usage=OCRUsage(elapsed_ms=int((monotonic() - started) * 1000)),
        )
