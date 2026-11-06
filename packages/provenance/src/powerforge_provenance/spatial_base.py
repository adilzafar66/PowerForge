"""Shared strict primitives for spatial-source-v1; no processing or persistence."""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from types import MappingProxyType
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

POLICY = MappingProxyType(
    json.loads(files("powerforge_provenance").joinpath("resources/spatial_v1.json").read_text())
)
SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
LocalRef = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,63}$")]
Label = Annotated[str, Field(min_length=1, max_length=200)]


def decimal_input(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Use an exact decimal string, integer or Decimal")
    if isinstance(value, str) and len(value) > 100:
        raise ValueError("Decimal input exceeds its lexical bound")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal") from None
    if not number.is_finite():
        raise ValueError("Coordinates must be finite")
    if len(number.as_tuple().digits) > 32 or not -18 <= number.as_tuple().exponent <= 18:
        raise ValueError("Coordinate precision exceeds the supported exact representation")
    return number


ExactDecimal = Annotated[Decimal, BeforeValidator(decimal_input)]


class SpatialContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, allow_inf_nan=False, revalidate_instances="always"
    )


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def identity_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def revalidate(value):
    """Do not let model_copy(update=...) bypass validation at a resolver boundary."""
    return type(value).model_validate(value)


def bounded_json(value, maximum):
    if len(canonical_json(value.model_dump(mode="json")).encode("utf-8")) > maximum:
        raise ValueError("Spatial contract exceeds its canonical UTF-8 byte limit")


class TextSpan(SpatialContract):
    start: int = Field(ge=0, lt=POLICY["max_text_characters"])
    end: int = Field(gt=0, le=POLICY["max_text_characters"])

    @property
    def length(self):
        return self.end - self.start

    def model_post_init(self, context):
        if self.end <= self.start:
            raise ValueError("Text spans are nonempty half-open codepoint intervals")
