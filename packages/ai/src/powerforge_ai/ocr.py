"""Positioned OCR protocol v1. No adapter, subprocess, vendor SDK or source publication."""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from importlib.resources import files
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

VERSION = "positioned-ocr-provider-v1"
MAX_WORDS = 20_000
MAX_PIXELS = 20_000_000
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=200)]


class OCRContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False, revalidate_instances="always"
    )


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


class OCRLanguage(OCRContract):
    name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
    traineddata_sha256: SHA256


class OCROption(OCRContract):
    name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]
    value: Annotated[str, Field(max_length=200)]


class OCRSettings(OCRContract):
    languages: tuple[OCRLanguage, ...] = Field(min_length=1, max_length=8)
    options: tuple[OCROption, ...] = Field(max_length=32)

    @model_validator(mode="after")
    def unique_names(self):
        if len({language.name for language in self.languages}) != len(self.languages) or len(
            {o.name for o in self.options}
        ) != len(self.options):
            raise ValueError("OCR language/option names must be distinct")
        return self

    @property
    def identity_hash(self):
        data = self.model_dump(mode="json")
        # Option ordering carries no meaning. Language order may affect recognition.
        data["options"] = sorted(data["options"], key=lambda o: o["name"])
        return _hash(data)


class OCRIdentity(OCRContract):
    adapter_version: Name
    engine: Name
    engine_version: Name
    build_sha256: SHA256
    settings_sha256: SHA256

    @property
    def identity_hash(self):
        return _hash(self.model_dump(mode="json"))


class OCRRequest(OCRContract):
    version: Literal["positioned-ocr-request-v1"] = "positioned-ocr-request-v1"
    request_id: UUID
    image_artifact_id: UUID
    image_sha256: SHA256
    image: bytes = Field(min_length=1, max_length=MAX_IMAGE_BYTES, repr=False, exclude=True)
    mime_type: Literal["image/png"] = "image/png"
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    expected_identity: OCRIdentity
    settings: OCRSettings
    timeout_seconds: int = Field(ge=1, le=60)

    @model_validator(mode="after")
    def pinned_input(self):
        if (
            self.width_px * self.height_px > MAX_PIXELS
            or hashlib.sha256(self.image).hexdigest() != self.image_sha256
            or self.expected_identity.settings_sha256 != self.settings.identity_hash
        ):
            raise ValueError("OCR request differs from its pinned image/settings or limits")
        return self


def _decimal(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int, Decimal))
        or len(str(value)) > 100
    ):
        raise ValueError("Engine confidence needs an exact bounded decimal")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid engine confidence") from None
    if not result.is_finite() or abs(result) > 1_000_000:
        raise ValueError("Engine confidence is nonfinite or exceeds its scale bound")
    return result


class OCRConfidence(OCRContract):
    value: Annotated[Decimal, BeforeValidator(_decimal)]
    minimum: Annotated[Decimal, BeforeValidator(_decimal)]
    maximum: Annotated[Decimal, BeforeValidator(_decimal)]
    method: Name

    @model_validator(mode="after")
    def engine_scale(self):
        if not self.minimum < self.maximum or not self.minimum <= self.value <= self.maximum:
            raise ValueError("Confidence differs from its declared engine scale")
        return self


class OCRWord(OCRContract):
    order: int = Field(ge=0, le=1_000_000)
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    block: int = Field(ge=0)
    paragraph: int = Field(ge=0)
    line: int = Field(ge=0)
    confidence: OCRConfidence | None


class OCRUsage(OCRContract):
    invocations: Literal[1] = 1
    elapsed_ms: int = Field(ge=0)
    cpu_ms: int | None = Field(default=None, ge=0)
    peak_memory_bytes: int | None = Field(default=None, ge=0)

    @field_validator("invocations", mode="before")
    @classmethod
    def actual_integer_count(cls, value):
        if type(value) is not int:
            raise ValueError("Invocation count requires an actual integer")
        return value


class OCRResponse(OCRContract):
    version: Literal["positioned-ocr-response-v1"] = "positioned-ocr-response-v1"
    request_id: UUID
    image_artifact_id: UUID
    image_sha256: SHA256
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    identity: OCRIdentity
    words: tuple[OCRWord, ...] = Field(max_length=MAX_WORDS)
    usage: OCRUsage

    @model_validator(mode="after")
    def bounded_words(self):
        if self.width_px * self.height_px > MAX_PIXELS or len({w.order for w in self.words}) != len(
            self.words
        ):
            raise ValueError("OCR output exceeds pixel bounds or duplicates engine order")
        if any(
            w.left + w.width > self.width_px or w.top + w.height > self.height_px
            for w in self.words
        ):
            raise ValueError("OCR word is outside its exact input image")
        if (
            len(json.dumps(self.model_dump(mode="json"), ensure_ascii=False).encode())
            > MAX_OUTPUT_BYTES
        ):
            raise ValueError("OCR output exceeds its byte bound")
        return self


def validate_ocr_response(request: OCRRequest, response: OCRResponse):
    # OCRRequest deliberately excludes raw pixels from dumps/log representations.
    request = OCRRequest.model_validate(request)
    response = OCRResponse.model_validate(response)
    if (
        response.request_id != request.request_id
        or response.image_artifact_id != request.image_artifact_id
        or response.image_sha256 != request.image_sha256
        or response.identity != request.expected_identity
        or (response.width_px, response.height_px) != (request.width_px, request.height_px)
    ):
        raise ValueError("OCR response differs from its exact admitted request")
    return response


class OCRFailureCode(StrEnum):
    ENGINE_UNAVAILABLE = "OCR_ENGINE_UNAVAILABLE"
    INVALID_IMAGE = "OCR_INVALID_IMAGE"
    INVALID_OUTPUT = "OCR_INVALID_OUTPUT"
    OUTPUT_LIMIT = "OCR_OUTPUT_LIMIT"
    TIMEOUT = "OCR_TIMEOUT"
    INTERRUPTED = "OCR_INTERRUPTED"


class OCRFailure(Exception):
    def __init__(self, code: OCRFailureCode):
        if not isinstance(code, OCRFailureCode):
            raise ValueError("OCR failures require a safe typed category")
        self.code = code
        super().__init__(code.value)


class PositionedOCRProvider(Protocol):
    def recognize(self, request: OCRRequest) -> OCRResponse: ...


def ocr_contract_identity():
    root = files("powerforge_ai")
    return {
        "version": VERSION,
        "rules_hash": hashlib.sha256(root.joinpath("ocr.py").read_bytes()).hexdigest(),
        "request_schema": _hash(OCRRequest.model_json_schema()),
        "response_schema": _hash(OCRResponse.model_json_schema()),
    }
