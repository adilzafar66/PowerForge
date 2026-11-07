"""Explicit successor locator: recognized text, geometry and structure are separate claims."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from powerforge_provenance.locations import Region
from powerforge_provenance.spatial_base import SpatialContract
from powerforge_provenance.spatial_layout import SourceSupport
from powerforge_provenance.spatial_sources import EngineConfidence


class EnrichedLocation(SpatialContract):
    version: Literal["source-location-v2"] = "source-location-v2"
    document_page_id: UUID
    page_artifact_id: UUID | None = None
    enrichment_artifact_id: UUID | None = None
    geometry_artifact_id: UUID | None = None
    prepared_result_id: UUID
    spatial_result_id: UUID
    region: Region | None = None
    support: tuple[SourceSupport, ...] = Field(default=(), max_length=128)
    reading_basis: Literal["NATIVE_PDF", "OCR", "VISUAL_REPORTED"]
    geometry_basis: Literal["NATIVE_DOCUMENT", "OCR_ENGINE", "NONE"]
    raw_engine_confidence: EngineConfidence | None = None
    structure_basis: Literal[
        "NATIVE_GEOMETRY_SUPPORTED",
        "OCR_GEOMETRY_SUPPORTED",
        "MIXED_GEOMETRY_SUPPORTED",
        "VISUAL_REPORTED",
        "UNRESOLVED",
    ] = "UNRESOLVED"
    printed_text_independently_verified: Literal[False] = False

    @field_validator("printed_text_independently_verified", mode="before")
    @classmethod
    def boolean_marker(cls, value):
        if type(value) is not bool:
            raise ValueError("Printed-text verification requires a boolean false")
        return value

    @model_validator(mode="after")
    def authoritative_source(self):
        if self.reading_basis == "VISUAL_REPORTED":
            if (
                not self.page_artifact_id
                or self.enrichment_artifact_id
                or self.geometry_artifact_id
                or self.support
                or self.region
                or self.raw_engine_confidence is not None
            ):
                raise ValueError("Visual fallback has page-level image evidence only")
        elif (
            self.page_artifact_id
            or not self.enrichment_artifact_id
            or not self.geometry_artifact_id
            or not self.support
        ):
            raise ValueError("Recognized text needs its exact text/geometry artifacts and support")
        if type(self.printed_text_independently_verified) is not bool:
            raise ValueError("Printed-text verification must remain false")
        return self
