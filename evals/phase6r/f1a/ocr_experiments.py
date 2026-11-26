"""Bounded OCR recipes for offline comparison in F1-A2."""

import os
import subprocess
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

import pymupdf
from PIL import Image, ImageChops, ImageOps
from source_metrics import contains_center
from source_ocr import owns, selected_tiles

from extraction_worker.tesseract import MAX_TSV_BYTES, parse_tsv
from powerforge_ai.ocr import OCRResponse, OCRUsage
from powerforge_extraction.enrichment_prepare import sha
from powerforge_provenance.spatial_base import canonical_json


@dataclass(frozen=True)
class Recipe:
    dpi: int = 300
    psm: int = 6
    preprocess: str = "original"
    regions: str = "full"


SWEEP = {
    "dpi450": Recipe(dpi=450),
    "psm11": Recipe(psm=11),
    "psm3": Recipe(psm=3),
    "contrast": Recipe(preprocess="contrast"),
    "remove_lines": Recipe(preprocess="remove_lines"),
    "region_psm11": Recipe(psm=11, regions="tiles"),
    "region_450": Recipe(dpi=450, regions="tiles"),
    "region_450_sparse_lines": Recipe(
        dpi=450,
        psm=11,
        regions="tiles",
        preprocess="remove_lines",
    ),
}


def raster_at(dpi):
    def render(data, number):
        from powerforge_document_processing.native_spatial import rasterize_pdf

        if dpi == 300:
            return rasterize_pdf(data, number)
        with pymupdf.open(stream=data, filetype="pdf") as document:
            pixmap = document[number - 1].get_pixmap(dpi=dpi, alpha=False, colorspace=pymupdf.csRGB)
            if pixmap.width * pixmap.height > 20_000_000:
                raise ValueError("Experimental raster exceeds the existing raster pixel ceiling")
            png = pixmap.tobytes("png")
            return png, pixmap.width, pixmap.height

    return render


def shifted(image, size, axis):
    result = Image.new("L", image.size)
    result.paste(image, (size, 0) if axis == 0 else (0, size))
    return result


def preprocess(image, recipe):
    if recipe.preprocess == "original":
        return image
    gray = ImageOps.autocontrast(image.convert("L"), cutoff=0.3)
    if recipe.preprocess == "contrast":
        return gray
    # A directional opening identifies dark horizontal/vertical runs of at
    # least 0.32 inches. Keep all other ink from the contrast-adjusted input.
    ink = gray.point([255 if value < 128 else 0 for value in range(256)])
    length = max(2, round(recipe.dpi * 0.32))
    opening = Image.new("L", image.size)
    for axis in (0, 1):
        run = ink
        width = 1
        while width * 2 <= length:
            run = ImageChops.darker(run, shifted(run, width, axis))
            width *= 2
        if length > width:
            run = ImageChops.darker(run, shifted(run, length - width, axis))
        width = 1
        while width * 2 <= length:
            run = ImageChops.lighter(run, shifted(run, -width, axis))
            width *= 2
        if length > width:
            run = ImageChops.lighter(run, shifted(run, width - length, axis))
        opening = ImageChops.lighter(opening, run)
    return ImageChops.lighter(gray, opening)


def sparse_tiles(image, native):
    """Up to eight ink-bearing 4x4 cores with no more than two native centers."""
    w, h = image.size
    preview = image.convert("L").resize((400, 400))
    choices = []
    for row in range(4):
        for col in range(4):
            box = (col / 4, row / 4, (col + 1) / 4, (row + 1) / 4)
            occupied = sum(
                contains_center(box, word.box) and "\ufffd" not in word.text for word in native
            )
            x, y = col * 100, row * 100
            fraction = sum(preview.crop((x, y, x + 100, y + 100)).histogram()[:160]) / 10_000
            if occupied <= 2 and 0.007 <= fraction <= 0.98:
                choices.append((occupied, -fraction, row, col))
    margin = round(min(w, h) * 0.025)
    for _, _, row, col in sorted(choices)[:8]:
        x0, y0, x1, y1 = col * w // 4, row * h // 4, (col + 1) * w // 4, (row + 1) * h // 4
        yield (
            (x0, y0, x1, y1),
            (max(0, x0 - margin), max(0, y0 - margin), min(w, x1 + margin), min(h, y1 + margin)),
        )


class ExperimentOCR:
    def __init__(self, provider, recipe):
        self.provider = provider
        self.recipe = recipe
        options = tuple(
            option.model_copy(update={"value": str(recipe.psm)}) if option.name == "psm" else option
            for option in provider.settings.options
        )
        self.settings = provider.settings.model_copy(update={"options": options})
        fingerprint = canonical_json(asdict(recipe))
        self.identity = provider.identity.model_copy(
            update={
                "adapter_version": "f1a2-local-ocr-v1",
                "build_sha256": sha(
                    (
                        provider.identity.build_sha256
                        + sha(Path(__file__).read_bytes())
                        + fingerprint
                    ).encode()
                ),
                "settings_sha256": self.settings.identity_hash,
            }
        )
        self.native = ()
        self.receipts = []
        self.input = None

    def regions(self, image):
        if self.recipe.regions == "tiles":
            return selected_tiles(image)
        if self.recipe.regions == "sparse":
            return sparse_tiles(image, self.native)
        box = (0, 0, *image.size)
        return ((box, box),)

    def engine(self, data, size, timeout):
        with TemporaryDirectory(prefix="f1a2-ocr-") as folder:
            path = Path(folder)
            (path / "input.png").write_bytes(data)
            with (path / "out.tsv").open("wb") as output:
                subprocess.run(
                    [
                        str(self.provider.binary),
                        str(path / "input.png"),
                        "stdout",
                        "--tessdata-dir",
                        str(self.provider.data_directory),
                        "-l",
                        "eng",
                        "--oem",
                        "1",
                        "--psm",
                        str(self.recipe.psm),
                        "-c",
                        "tessedit_create_tsv=1",
                    ],
                    check=True,
                    timeout=timeout,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"},
                )
            if (path / "out.tsv").stat().st_size > MAX_TSV_BYTES:
                raise ValueError("Experimental OCR output exceeds the existing TSV byte ceiling")
            return parse_tsv((path / "out.tsv").read_bytes(), *size)

    def recognize(self, request):
        started = monotonic()
        self.receipts = []
        self.input = {
            "sha256": request.image_sha256,
            "width": request.width_px,
            "height": request.height_px,
            "bytes": len(request.image),
        }
        words = []
        with Image.open(BytesIO(request.image)) as image:
            for core, crop in self.regions(image):
                local = preprocess(image.crop(crop), self.recipe)
                buffer = BytesIO()
                local.save(buffer, format="PNG", dpi=(self.recipe.dpi, self.recipe.dpi))
                data = buffer.getvalue()
                remaining = request.timeout_seconds - (monotonic() - started)
                if remaining < 1:
                    raise ValueError("Experimental OCR exceeded its aggregate deadline")
                try:
                    recognized = self.engine(data, local.size, remaining)
                except subprocess.SubprocessError as exc:
                    raise ValueError(f"Experimental OCR failed: {type(exc).__name__}") from None
                blocks = {}
                kept = 0
                for word in recognized:
                    x, y = word.left + crop[0], word.top + crop[1]
                    if not owns(core, x + word.width / 2, y + word.height / 2):
                        continue
                    block = blocks.setdefault(word.block, len(blocks))
                    words.append(
                        word.model_copy(
                            update={
                                "left": x,
                                "top": y,
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
                        sha256=sha(data),
                        recognized=len(recognized),
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


def request_check(provider):
    # Reuse initial runtime identity verification for the underlying binary and language pack.
    checked = type(provider)(str(provider.binary), str(provider.data_directory))
    if checked.identity != provider.identity:
        raise ValueError("Experimental OCR runtime differs from its pinned provider")
