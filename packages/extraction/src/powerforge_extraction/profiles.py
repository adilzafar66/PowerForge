"""Read and validate pinned extraction and local source profiles."""

import json
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from powerforge_shared.config import Settings


class ExecutionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    version: str
    execution_kind: str
    provider: Literal["fake", "openai"]
    model: str
    stage: str
    input_strategy: str
    prompt_version: str
    prompt_hash: str
    schema_version: str
    schema_hash: str
    max_pages: int = Field(ge=1, le=1000)
    max_input_bytes: int = Field(ge=1)
    max_image_pixels: int = Field(ge=1)
    max_output_tokens: int = Field(ge=16, le=32768)
    max_attempts: int = Field(ge=1, le=10)
    max_calls: int = Field(ge=1, le=10000)
    max_concurrent: int = Field(ge=1, le=32)
    timeout_seconds: int = Field(ge=1, le=300)
    lease_seconds: int = Field(ge=3, le=600)
    backoff_seconds: int = Field(ge=0, le=300)
    fake_scenario: Literal[
        "success", "empty", "transient", "permanent", "invalid", "slow", "interrupted"
    ] = "success"
    pricing_basis: str | None = None
    input_usd_per_million: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_usd_per_million: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def pricing(self) -> "ExecutionProfile":
        rates = [self.input_usd_per_million, self.output_usd_per_million]
        if any(x is not None for x in rates) and (None in rates or not self.pricing_basis):
            raise ValueError("Pricing requires both rates and a recorded basis")
        return self


def read_profile(configuration: dict):
    version = configuration.get("version")
    if version == "phase-6r-profile-v1":
        from powerforge_extraction.extraction_profile import ExtractionProfile, require_profile

        profile = ExtractionProfile.model_validate_json(json.dumps(configuration))
        require_profile(profile)
        return profile
    if version == "source-layout-profile-v1":
        from powerforge_extraction.layout_profiles import SourceLayoutProfile

        return SourceLayoutProfile.model_validate_json(json.dumps(configuration))
    if version == "source-preparation-profile-v1":
        from powerforge_extraction.enrichment_profiles import PreparationProfile

        return PreparationProfile.model_validate_json(json.dumps(configuration))
    raise ValueError("Unsupported pinned execution profile version")


def resolve_profile(key: str, settings: Settings) -> ExecutionProfile:
    from powerforge_extraction.extraction_profile import KEY, extraction_profile

    if key != KEY:
        raise ValueError("Unknown extraction profile")
    return extraction_profile(settings)
