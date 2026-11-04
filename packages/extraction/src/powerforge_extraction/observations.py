"""Versioned model observations, not persistence payloads or proof of source grounding.

All nullable fields are required on the wire for structured-output compatibility.
Unknown proposed registry identifiers remain representable for later interpretation.
"""

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from powerforge_extraction.identities import canonical_json

EQUIPMENT_SCHEMA_VERSION = "equipment-recognition-schema-v1"
ATTRIBUTE_SCHEMA_VERSION = "attribute-extraction-schema-v1"
MAX_EQUIPMENT_OBSERVATIONS = 32
MAX_ATTRIBUTE_OBSERVATIONS = 128

LocalReference = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
SourceReference = Literal["native_text", "analysis_image"]
Expression = Annotated[str, Field(min_length=1, max_length=2000)]
ProposedKey = Annotated[str, Field(min_length=1, max_length=200)]


class ObservationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @field_validator("*")
    @classmethod
    def nonblank_strings(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Observation text must not be blank")
        return value  # Preserve original spacing, Unicode and source spelling.


class SourceAnchor(ObservationContract):
    kind: Literal["NATIVE_TEXT", "VISUAL_PAGE"]
    source_ref: SourceReference
    quote: Expression | None
    prefix: Annotated[str, Field(min_length=1, max_length=256)] | None
    suffix: Annotated[str, Field(min_length=1, max_length=256)] | None

    @model_validator(mode="after")
    def source_shape(self) -> "SourceAnchor":
        if self.kind == "NATIVE_TEXT":
            if self.source_ref != "native_text" or self.quote is None:
                raise ValueError("Native anchors require native text and a verbatim quote")
        elif self.source_ref != "analysis_image" or any(
            value is not None for value in (self.quote, self.prefix, self.suffix)
        ):
            raise ValueError("Visual anchors identify the image without verified text or geometry")
        return self


class SourceObservation(ObservationContract):
    local_ref: LocalReference
    raw_expression: Expression
    anchors: list[SourceAnchor] = Field(min_length=1, max_length=8)
    ambiguous: bool
    ambiguity_reason: Annotated[str, Field(min_length=1, max_length=500)] | None

    @model_validator(mode="after")
    def uncertainty(self) -> "SourceObservation":
        if self.ambiguous != (self.ambiguity_reason is not None):
            raise ValueError("Ambiguous observations require a reason; clear ones use null")
        return self


class EquipmentObservation(SourceObservation):
    observed_tag: Annotated[str, Field(min_length=1, max_length=200)] | None
    observed_name: Annotated[str, Field(min_length=1, max_length=500)] | None
    proposed_equipment_type: ProposedKey | None


class AttributeObservation(SourceObservation):
    equipment_ref: LocalReference | None
    source_label: Expression | None
    raw_value: Expression | None
    raw_unit: Annotated[str, Field(min_length=1, max_length=100)] | None
    proposed_equipment_type: ProposedKey | None
    proposed_attribute_key: ProposedKey | None


class ObservationResponse(ObservationContract):
    max_response_bytes: ClassVar[int]
    overflowed: bool

    @model_validator(mode="after")
    def complete_bounded_response(self) -> "ObservationResponse":
        if self.overflowed:
            raise ValueError("Observation response exceeds its extraction capacity")
        if len(canonical_json(self.model_dump(mode="json")).encode()) > self.max_response_bytes:
            raise ValueError("Observation response exceeds its byte limit")
        return self


def _unique_references(observations: list[SourceObservation]) -> None:
    if len({item.local_ref for item in observations}) != len(observations):
        raise ValueError("Observation local references must be unique within the response")


class EquipmentRecognitionResponse(ObservationResponse):
    max_response_bytes = 256 * 1024
    schema_version: Literal["equipment-recognition-schema-v1"]
    equipment: list[EquipmentObservation] = Field(max_length=MAX_EQUIPMENT_OBSERVATIONS)

    @model_validator(mode="after")
    def unique_references(self) -> "EquipmentRecognitionResponse":
        _unique_references(self.equipment)
        return self


class AttributeExtractionResponse(ObservationResponse):
    max_response_bytes = 512 * 1024
    schema_version: Literal["attribute-extraction-schema-v1"]
    attributes: list[AttributeObservation] = Field(max_length=MAX_ATTRIBUTE_OBSERVATIONS)

    @model_validator(mode="after")
    def unique_references(self) -> "AttributeExtractionResponse":
        _unique_references(self.attributes)
        return self
