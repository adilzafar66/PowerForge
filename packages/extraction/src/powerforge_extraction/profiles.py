"""Versioned executable infrastructure profiles; production extractors arrive in 6C–6E."""

import hashlib
import json
from decimal import Decimal
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from powerforge_ai.extraction import ProbeResult
from powerforge_shared.config import Settings

PROMPT_VERSION = "source-probe-v1"
PROMPT = files("powerforge_extraction").joinpath("prompts/source_probe_v1.txt").read_text()
PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()
SCHEMA_VERSION = "source-probe-schema-v1"
SCHEMA_HASH = hashlib.sha256(
    json.dumps(ProbeResult.model_json_schema(), sort_keys=True).encode()
).hexdigest()
FAKE_PROFILE = "infrastructure-fake-v1"
OPENAI_PROFILE = "infrastructure-openai-v1"


class ExecutionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    version: str = "execution-profile-v1"
    execution_kind: Literal["FAKE_TEST", "INFRASTRUCTURE_PROBE"]
    provider: Literal["fake", "openai"]
    model: str
    stage: Literal["SOURCE_PROBE"] = "SOURCE_PROBE"
    input_strategy: Literal["NATIVE_TEXT_OR_IMAGE"] = "NATIVE_TEXT_OR_IMAGE"
    prompt_version: str = PROMPT_VERSION
    prompt_hash: str = PROMPT_HASH
    schema_version: str = SCHEMA_VERSION
    schema_hash: str = SCHEMA_HASH
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

    @property
    def identity_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def resolve_profile(key: str, settings: Settings) -> ExecutionProfile:
    if key not in {FAKE_PROFILE, OPENAI_PROFILE}:
        raise ValueError("Unknown extraction profile; production extractors are not available")
    live = key == OPENAI_PROFILE
    return ExecutionProfile(
        key=key,
        execution_kind="INFRASTRUCTURE_PROBE" if live else "FAKE_TEST",
        provider="openai" if live else "fake",
        model=settings.extraction_model if live else "deterministic-fake-v1",
        max_pages=settings.extraction_max_pages,
        max_input_bytes=settings.extraction_max_input_bytes,
        max_image_pixels=settings.extraction_max_image_pixels,
        max_output_tokens=settings.extraction_max_output_tokens,
        max_attempts=settings.extraction_max_attempts,
        max_calls=settings.extraction_max_calls,
        max_concurrent=settings.extraction_max_concurrent_per_run,
        timeout_seconds=settings.extraction_timeout_seconds,
        lease_seconds=settings.extraction_lease_seconds,
        backoff_seconds=settings.extraction_backoff_seconds,
        fake_scenario=settings.extraction_fake_scenario,
        pricing_basis=settings.extraction_pricing_basis if live else None,
        input_usd_per_million=settings.extraction_input_usd_per_million if live else None,
        output_usd_per_million=settings.extraction_output_usd_per_million if live else None,
    )
