"""Typed provider contracts only: no actual recognition is implemented by M1."""

import json
from decimal import Decimal

import pytest

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
from spatial_support import sha, uid


def request_and_response():
    settings = OCRSettings(
        languages=(OCRLanguage(name="eng", traineddata_sha256="1" * 64),),
        options=(OCROption(name="page_segmentation_mode", value="3"),),
    )
    identity = OCRIdentity(
        adapter_version="fixture-1",
        engine="fixture-no-actual-OCR",
        engine_version="fixture-1",
        build_sha256="2" * 64,
        settings_sha256=settings.identity_hash,
    )
    pixels = b"synthetic-input-contract-only-not-decoded-in-M1"
    request = OCRRequest(
        request_id=uid("ocr-request"),
        image_artifact_id=uid("ocr-image"),
        image_sha256=sha(pixels),
        image=pixels,
        width_px=1000,
        height_px=1000,
        expected_identity=identity,
        settings=settings,
        timeout_seconds=60,
    )
    words = tuple(
        OCRWord(
            order=i,
            text=text,
            left=100,
            top=100 + 100 * i,
            width=200,
            height=30,
            block=1,
            paragraph=1,
            line=i,
            confidence=OCRConfidence(value="70", minimum="0", maximum="100", method="engine-raw"),
        )
        for i, text in enumerate(("TX-1", "75O", "kVA", "400 AF / 250 AT"))
    )
    result = OCRResponse(
        request_id=request.request_id,
        image_artifact_id=request.image_artifact_id,
        image_sha256=request.image_sha256,
        width_px=1000,
        height_px=1000,
        identity=identity,
        words=words,
        usage=OCRUsage(elapsed_ms=10),
    )
    return request, result


def test_raw_ocr_words_confidence_and_order_do_not_normalize_engineering_text():
    request, result = request_and_response()
    assert validate_ocr_response(request, result) == result
    assert result.words[1].text == "75O" and result.words[3].text == "400 AF / 250 AT"
    assert result.words[0].confidence.value == Decimal("70")
    assert result.words[0].confidence.maximum == 100
    assert "image" not in request.model_dump() and repr(request.image) not in repr(request)
    assert "input_tokens" not in result.model_dump()["usage"]
    empty = result.model_copy(update={"words": ()})
    assert validate_ocr_response(request, empty).words == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("image_sha256", "0" * 64),
        ("request_id", uid("foreign-request")),
        ("image_artifact_id", uid("foreign-image")),
        ("width_px", 999),
        ("identity", None),
    ],
)
def test_response_must_match_exact_image_and_admitted_provider(field, value):
    request, result = request_and_response()
    if field == "identity":
        value = result.identity.model_copy(update={"engine_version": "new"})
    with pytest.raises(ValueError):
        validate_ocr_response(request, result.model_copy(update={field: value}))


@pytest.mark.parametrize("change", [{"left": -1}, {"width": 0}, {"left": 990}, {"top": True}])
def test_invalid_or_outside_engine_boxes_are_rejected(change):
    request, result = request_and_response()
    words = (result.words[0].model_copy(update=change), *result.words[1:])
    with pytest.raises(ValueError):
        validate_ocr_response(request, result.model_copy(update={"words": words}))


def test_settings_and_language_data_are_material_but_option_key_order_is_not():
    request, result = request_and_response()
    a = OCROption(name="dictionary", value="false")
    b = OCROption(name="mode", value="3")
    settings = request.settings.model_copy(update={"options": (a, b)})
    assert settings.identity_hash == settings.model_copy(update={"options": (b, a)}).identity_hash
    changed = settings.model_copy(
        update={"languages": (OCRLanguage(name="eng", traineddata_sha256="f" * 64),)}
    )
    assert settings.identity_hash != changed.identity_hash
    with pytest.raises(ValueError):
        validate_ocr_response(request.model_copy(update={"settings": changed}), result)


def test_no_fake_confidence_unknown_negative_sentinel_or_ai_usage_fields():
    request, result = request_and_response()
    for value in ("NaN", -1, 0.95, True):
        with pytest.raises(ValueError):
            OCRConfidence(value=value, minimum="0", maximum="100", method="tesseract-scale")
    with pytest.raises(ValueError):
        OCRUsage(elapsed_ms=1, input_tokens=0)
    words = (result.words[0].model_copy(update={"confidence": None}), *result.words[1:])
    assert (
        validate_ocr_response(request, result.model_copy(update={"words": words}))
        .words[0]
        .confidence
        is None
    )
    with pytest.raises(ValueError):
        OCRResponse.model_validate_json(
            json.dumps({**result.model_dump(mode="json"), "version": "future"})
        )


def test_safe_failure_categories_do_not_expose_engine_messages_or_start_an_engine():
    failure = OCRFailure(OCRFailureCode.ENGINE_UNAVAILABLE)
    assert str(failure) == "OCR_ENGINE_UNAVAILABLE"
    with pytest.raises(ValueError):
        OCRFailure("secret engine stderr")
