"""Real local engine gate plus strict TSV failures. No external OCR/OpenAI calls."""

import hashlib
from uuid import uuid4

import pytest

from extraction_worker.tesseract import TesseractProvider, parse_tsv
from powerforge_ai.ocr import OCRFailure, OCRFailureCode, OCRRequest
from test_enrichment_native import scan_png

HEADER = (
    b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    b"left\ttop\twidth\theight\tconf\ttext\n"
)


def test_actual_tesseract_recognizes_engineering_notation_and_returns_its_exact_identity():
    provider = TesseractProvider()
    data = scan_png()
    request = OCRRequest(
        request_id=uuid4(),
        image_artifact_id=uuid4(),
        image_sha256=hashlib.sha256(data).hexdigest(),
        image=data,
        width_px=1800,
        height_px=600,
        expected_identity=provider.identity,
        settings=provider.settings,
        timeout_seconds=60,
    )
    result = provider.recognize(request)
    text = " ".join(w.text for w in result.words)
    assert "TX-1" in text and "750" in text and "13.8" in text
    assert "AF" in text and "AT" in text and "AWG" in text
    assert result.identity == provider.identity and result.usage.invocations == 1
    assert all(w.left + w.width <= 1800 and w.top + w.height <= 600 for w in result.words)
    print("ACTUAL_OCR", text, provider.identity.model_dump_json(), result.usage.model_dump_json())


def test_uncertain_and_unknown_engine_confidence_never_correct_raw_notation():
    words = parse_tsv(HEADER + b"5\t1\t1\t1\t1\t1\t1\t2\t30\t10\t-1\t75O\n", 100, 100)
    assert words[0].text == "75O" and words[0].confidence is None


@pytest.mark.parametrize(
    "row",
    [
        b"5\t1\t1\t1\t1\t1\t99\t2\t30\t10\t50\t750\n",
        b"5\t1\t1\t1\t1\t1\t1\t2\t30\t10\tNaN\t750\n",
        b"5\t1\t1\t1\t1\t1\t1\t2\t30\t10\t101\t750\n",
        b"5\t2\t1\t1\t1\t1\t1\t2\t30\t10\t50\t750\n",
        b"5\t1\t1\n",
        b"\xff",
    ],
)
def test_malformed_or_off_image_tsv_never_becomes_a_reading(row):
    with pytest.raises(OCRFailure) as exc:
        parse_tsv(HEADER + row, 100, 100)
    assert exc.value.code == OCRFailureCode.INVALID_OUTPUT


def test_missing_engine_or_data_and_oversized_output_fail_safely(tmp_path):
    for binary, data in (
        (str(tmp_path / "missing"), str(tmp_path)),
        ("/usr/bin/tesseract", str(tmp_path)),
    ):
        with pytest.raises(OCRFailure) as exc:
            TesseractProvider(binary, data)
        assert exc.value.code == OCRFailureCode.ENGINE_UNAVAILABLE
    with pytest.raises(OCRFailure) as exc:
        parse_tsv(b"x" * (4 * 1024 * 1024 + 1), 100, 100)
    assert exc.value.code == OCRFailureCode.OUTPUT_LIMIT


def test_timeout_terminates_the_owned_engine_process_group(monkeypatch):
    import subprocess
    import sys
    import time

    provider = TesseractProvider()
    real_popen = subprocess.Popen

    def slow_engine(args, **kwargs):
        if len(args) > 1 and args[1] != "--version":
            args = [sys.executable, "-c", "import time; time.sleep(10)"]
        return real_popen(args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", slow_engine)
    data = scan_png()
    request = OCRRequest(
        request_id=uuid4(),
        image_artifact_id=uuid4(),
        image_sha256=hashlib.sha256(data).hexdigest(),
        image=data,
        width_px=1800,
        height_px=600,
        expected_identity=provider.identity,
        settings=provider.settings,
        timeout_seconds=1,
    )
    started = time.monotonic()
    with pytest.raises(OCRFailure) as exc:
        provider.recognize(request)
    assert exc.value.code == OCRFailureCode.TIMEOUT and time.monotonic() - started < 4


def test_corrupted_png_and_engine_identity_drift_never_reach_recognition():
    provider = TesseractProvider()
    data = b"not png"
    request = OCRRequest(
        request_id=uuid4(),
        image_artifact_id=uuid4(),
        image_sha256=hashlib.sha256(data).hexdigest(),
        image=data,
        width_px=10,
        height_px=10,
        expected_identity=provider.identity,
        settings=provider.settings,
        timeout_seconds=1,
    )
    with pytest.raises(OCRFailure) as exc:
        provider.recognize(request)
    assert exc.value.code == OCRFailureCode.INVALID_IMAGE
    drift = request.model_copy(
        update={
            "expected_identity": provider.identity.model_copy(update={"build_sha256": "0" * 64})
        }
    )
    with pytest.raises(OCRFailure) as exc:
        provider.recognize(drift)
    assert exc.value.code == OCRFailureCode.ENGINE_UNAVAILABLE
