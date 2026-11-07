"""Successor observations cite bounded server aliases; no provider offsets or geometry."""

from typing import Literal

from pydantic import Field, model_validator

from powerforge_extraction.observations import (
    AttributeExtractionResponse,
    AttributeObservation,
    EquipmentObservation,
    EquipmentRecognitionResponse,
    ObservationContract,
)
from powerforge_extraction.table_observations import (
    TableCellObservation,
    TableInterpretationResponse,
    TableObservation,
    TableReconstructionResponse,
    TableTextObservation,
)
from powerforge_provenance.spatial_base import LocalRef


class EnrichedAnchor(ObservationContract):
    source_ref: Literal["spatial_readings", "analysis_image"]
    reading_refs: list[LocalRef] = Field(max_length=128)

    @model_validator(mode="after")
    def selected(self):
        if (self.source_ref == "spatial_readings") != bool(self.reading_refs):
            raise ValueError("Positioned anchors require exact reading aliases; images have none")
        if len(set(self.reading_refs)) != len(self.reading_refs):
            raise ValueError("Repeated source alias")
        return self


class EnrichedEquipment(EquipmentObservation):
    anchors: list[EnrichedAnchor] = Field(min_length=1, max_length=8)


class EnrichedAttribute(AttributeObservation):
    anchors: list[EnrichedAnchor] = Field(min_length=1, max_length=8)


class EnrichedEquipmentResponse(EquipmentRecognitionResponse):
    schema_version: Literal["equipment-recognition-schema-v2"]
    equipment: list[EnrichedEquipment] = Field(max_length=32)


class EnrichedAttributeResponse(AttributeExtractionResponse):
    schema_version: Literal["attribute-extraction-schema-v2"]
    attributes: list[EnrichedAttribute] = Field(max_length=128)


class EnrichedTableText(TableTextObservation):
    anchors: list[EnrichedAnchor] = Field(min_length=1, max_length=4)


class EnrichedCell(TableCellObservation):
    spatial_cell_ref: LocalRef | None
    anchors: list[EnrichedAnchor] = Field(min_length=1, max_length=4)


class EnrichedTable(TableObservation):
    spatial_table_ref: LocalRef | None
    cells: list[EnrichedCell] = Field(min_length=1, max_length=512)
    title: EnrichedTableText | None
    notes: list[EnrichedTableText] = Field(max_length=8)
    anchors: list[EnrichedAnchor] = Field(min_length=1, max_length=4)


class EnrichedReconstructionResponse(TableReconstructionResponse):
    schema_version: Literal["table-reconstruction-schema-v2"]
    tables: list[EnrichedTable] = Field(max_length=8)


class EnrichedInterpretationResponse(TableInterpretationResponse):
    schema_version: Literal["table-interpretation-schema-v2"]


RESPONSES = {
    "EQUIPMENT_RECOGNITION": EnrichedEquipmentResponse,
    "ATTRIBUTE_EXTRACTION": EnrichedAttributeResponse,
    "TABLE_RECONSTRUCTION": EnrichedReconstructionResponse,
    "TABLE_INTERPRETATION": EnrichedInterpretationResponse,
}
SCHEMAS = {
    "EQUIPMENT_RECOGNITION": "equipment-recognition-schema-v2",
    "ATTRIBUTE_EXTRACTION": "attribute-extraction-schema-v2",
    "TABLE_RECONSTRUCTION": "table-reconstruction-schema-v2",
    "TABLE_INTERPRETATION": "table-interpretation-schema-v2",
}
