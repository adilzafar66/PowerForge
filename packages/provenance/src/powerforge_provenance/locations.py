"""Source geometry uses normalized upright pages, never guessed pixel locations."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    x: Decimal = Field(ge=0, le=1)
    y: Decimal = Field(ge=0, le=1)
    width: Decimal = Field(gt=0, le=1)
    height: Decimal = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_page(self) -> "Region":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Region must fit inside the upright page")
        return self


class SourceLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_page_id: UUID
    page_artifact_id: UUID | None = None
    region: Region | None = None
