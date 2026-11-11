"""Role-bearing source occurrences for the successor Engineering and Tables stages."""

from typing import Literal

from pydantic import Field

from powerforge_extraction.enriched_observations import (
    RESPONSES,
    EnrichedAnchor,
    EnrichedAttribute,
    EnrichedAttributeResponse,
    EnrichedEquipment,
    EnrichedEquipmentResponse,
    EnrichedInterpretationResponse,
)
from powerforge_provenance.spatial_base import LocalRef


class EvidencePart(EnrichedAnchor):
    role: Literal["LABEL", "VALUE", "UNIT", "QUALIFIER", "EQUIPMENT", "TAG", "CONTEXT"]
    quote: str = Field(min_length=1, max_length=500)
    reading_refs: list[LocalRef] = Field(max_length=16)


class SemanticEquipment(EnrichedEquipment):
    anchors: list[EvidencePart] = Field(min_length=1, max_length=8)


class SemanticAttribute(EnrichedAttribute):
    anchors: list[EvidencePart] = Field(min_length=1, max_length=8)


class SemanticEquipmentResponse(EnrichedEquipmentResponse):
    schema_version: Literal["equipment-recognition-schema-v3"]
    equipment: list[SemanticEquipment] = Field(max_length=32)


class SemanticAttributeResponse(EnrichedAttributeResponse):
    schema_version: Literal["attribute-extraction-schema-v3"]
    attributes: list[SemanticAttribute] = Field(max_length=128)


class SemanticTableResponse(EnrichedInterpretationResponse):
    schema_version: Literal["table-interpretation-schema-v3"]


SEMANTIC_RESPONSES = {
    **RESPONSES,
    "EQUIPMENT_RECOGNITION": SemanticEquipmentResponse,
    "ATTRIBUTE_EXTRACTION": SemanticAttributeResponse,
    "TABLE_INTERPRETATION": SemanticTableResponse,
}
