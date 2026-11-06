"""One bounded local Tesseract subprocess; no external model credentials or corrections."""

import csv
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from decimal import Decimal
from importlib.resources import files
from io import BytesIO, StringIO
from pathlib import Path

from PIL import Image

from powerforge_ai.ocr import (
    OCRConfidence,
    OCRFailure,
    OCRFailureCode,
    OCRIdentity,
    OCRLanguage,
    OCROption,
    OCRRequest,
    OCRResponse,
    OCRSettings,
    OCRUsage,
    OCRWord,
    validate_ocr_response,
)

ADAPTER_VERSION = "tesseract-tsv-v1"
MAX_TSV_BYTES = 4 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def configuration(data_sha256):
    return OCRSettings(
        languages=(OCRLanguage(name="eng", traineddata_sha256=data_sha256),),
        options=(
            OCROption(name="oem", value="1"),
            OCROption(name="psm", value="6"),
            OCROption(name="threads", value="1"),
        ),
    )


class TesseractProvider:
    def __init__(
        self, binary="/usr/bin/tesseract", data_directory="/usr/share/tesseract-ocr/5/tessdata"
    ):
        self.binary = Path(binary).resolve()
        self.data_directory = Path(data_directory).resolve()
        try:
            version = subprocess.run(
                [str(self.binary), "--version"], capture_output=True, timeout=5, check=True
            )
            description = version.stdout + version.stderr
            if not description.startswith(b"tesseract 5.") or len(description) > 16000:
                raise ValueError("Unsupported engine")
            data = (self.data_directory / "eng.traineddata").read_bytes()
            self.settings = configuration(digest(data))
            self.identity = OCRIdentity(
                adapter_version=ADAPTER_VERSION,
                engine="tesseract",
                engine_version=description.splitlines()[0].decode(),
                build_sha256=digest(
                    self.binary.read_bytes()
                    + description
                    + files("extraction_worker").joinpath("tesseract.py").read_bytes()
                ),
                settings_sha256=self.settings.identity_hash,
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            raise OCRFailure(OCRFailureCode.ENGINE_UNAVAILABLE) from None

    def recognize(self, request: OCRRequest) -> OCRResponse:
        request = OCRRequest.model_validate(request)
        # Recheck binary/data on every invocation, not only at process startup.
        verified = TesseractProvider(str(self.binary), str(self.data_directory))
        if request.expected_identity != verified.identity or request.settings != verified.settings:
            raise OCRFailure(OCRFailureCode.ENGINE_UNAVAILABLE)
        try:
            with Image.open(BytesIO(request.image)) as image:
                if image.format != "PNG" or image.size != (request.width_px, request.height_px):
                    raise ValueError("Invalid raster")
                image.load()
        except (OSError, ValueError, Image.DecompressionBombError):
            raise OCRFailure(OCRFailureCode.INVALID_IMAGE) from None
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="powerforge-ocr-") as folder:
                source = Path(folder) / "input.png"
                source.write_bytes(request.image)
                output = Path(folder) / "words.tsv"
                error = Path(folder) / "stderr"
                # File size is polled while the child runs. No unlimited capture in RAM.
                with output.open("wb") as stdout, error.open("wb") as stderr:
                    process = subprocess.Popen(
                        [
                            str(self.binary),
                            str(source),
                            "stdout",
                            "--tessdata-dir",
                            str(self.data_directory),
                            "-l",
                            "eng",
                            "--oem",
                            "1",
                            "--psm",
                            "6",
                            "-c",
                            "tessedit_create_tsv=1",
                        ],
                        start_new_session=True,
                        stdout=stdout,
                        stderr=stderr,
                        env={**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"},
                    )
                    try:
                        deadline = started + request.timeout_seconds
                        while process.poll() is None:
                            if (
                                output.stat().st_size > MAX_TSV_BYTES
                                or error.stat().st_size > 65536
                            ):
                                raise OCRFailure(OCRFailureCode.OUTPUT_LIMIT)
                            if time.monotonic() > deadline:
                                raise OCRFailure(OCRFailureCode.TIMEOUT)
                            time.sleep(0.02)
                        if process.returncode != 0:
                            raise OCRFailure(OCRFailureCode.INVALID_OUTPUT)
                    finally:
                        if process.poll() is None:
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        process.wait()
                if output.stat().st_size > MAX_TSV_BYTES:
                    raise OCRFailure(OCRFailureCode.OUTPUT_LIMIT)
                words = parse_tsv(output.read_bytes(), request.width_px, request.height_px)
            response = OCRResponse(
                request_id=request.request_id,
                image_artifact_id=request.image_artifact_id,
                image_sha256=request.image_sha256,
                width_px=request.width_px,
                height_px=request.height_px,
                identity=self.identity,
                words=words,
                usage=OCRUsage(elapsed_ms=int((time.monotonic() - started) * 1000)),
            )
            return validate_ocr_response(request, response)
        except OCRFailure:
            raise
        except (OSError, UnicodeError, ValueError):
            raise OCRFailure(OCRFailureCode.INVALID_OUTPUT) from None


def parse_tsv(data: bytes, width: int, height: int):
    if len(data) > MAX_TSV_BYTES:
        raise OCRFailure(OCRFailureCode.OUTPUT_LIMIT)
    try:
        reader = csv.DictReader(
            StringIO(data.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE
        )
        if reader.fieldnames != [
            "level",
            "page_num",
            "block_num",
            "par_num",
            "line_num",
            "word_num",
            "left",
            "top",
            "width",
            "height",
            "conf",
            "text",
        ]:
            raise ValueError("Invalid TSV header")
        words = []
        for index, row in enumerate(reader):
            if index > 100000 or None in row or any(v is None for v in row.values()):
                raise ValueError("Invalid TSV row")
            level = int(row["level"])
            if level not in range(1, 6) or int(row["page_num"]) != 1:
                raise ValueError("Invalid TSV hierarchy")
            if level != 5:
                continue
            if min(int(row[k]) for k in ("block_num", "par_num", "line_num", "word_num")) < 1:
                raise ValueError("Invalid word hierarchy")
            if not row["text"]:
                continue
            confidence = Decimal(row["conf"])
            if not confidence.is_finite():
                raise ValueError("Invalid confidence")
            word = OCRWord(
                order=len(words),
                text=row["text"],
                left=int(row["left"]),
                top=int(row["top"]),
                width=int(row["width"]),
                height=int(row["height"]),
                block=int(row["block_num"]),
                paragraph=int(row["par_num"]),
                line=int(row["line_num"]),
                confidence=OCRConfidence(
                    value=confidence, minimum=0, maximum=100, method="TESSERACT_TSV_0_100"
                )
                if confidence >= 0
                else None,
            )
            if word.left + word.width > width or word.top + word.height > height:
                raise ValueError("Off-image OCR box")
            words.append(word)
            if len(words) > 20000:
                raise OCRFailure(OCRFailureCode.OUTPUT_LIMIT)
        return tuple(words)
    except OCRFailure:
        raise
    except (ValueError, UnicodeError, ArithmeticError, csv.Error):
        raise OCRFailure(OCRFailureCode.INVALID_OUTPUT) from None


if __name__ == "__main__":
    provider = TesseractProvider()
    print(
        json.dumps(
            {
                "identity": provider.identity.model_dump(mode="json"),
                "settings": provider.settings.model_dump(mode="json"),
            },
            sort_keys=True,
        )
    )
