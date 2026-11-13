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
ENGINEERING_TEST_PROFILE = "engineering-test-v1"
ENGINEERING_TEXT_TEST_PROFILE = "engineering-test-text-v1"


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


class EngineeringProfile(ExecutionProfile):
    """Separate wire format: never add defaults to the accepted v1 serialization."""

    version: Literal["execution-profile-v2"] = "execution-profile-v2"
    execution_kind: Literal["FAKE_TEST", "ENGINEERING_EXTRACTION"]
    stage: Literal["EQUIPMENT_RECOGNITION"] = "EQUIPMENT_RECOGNITION"
    stages: tuple[Literal["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"], ...] = (
        "EQUIPMENT_RECOGNITION",
        "ATTRIBUTE_EXTRACTION",
    )
    input_strategy: Literal["NATIVE_TEXT_AND_IMAGE", "NATIVE_TEXT_ONLY"]
    prompt_version: str = "engineering-prompts-v1"
    schema_version: str = "engineering-stage-manifest-v1"
    manifest: dict
    interpretation: dict
    grounding: dict
    runtime: dict
    max_total_input_bytes: int = Field(ge=1)
    max_text_chars: int = Field(ge=1)
    max_instruction_bytes: int = Field(ge=1, le=131072)
    max_upstream_bytes: int = Field(ge=1, le=131072)
    image_detail: Literal["high", "auto"] = "high"

    @model_validator(mode="after")
    def two_stages(self) -> "EngineeringProfile":
        if self.stages != ("EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"):
            raise ValueError("Unsupported engineering stage plan")
        if (self.provider == "fake") != (self.execution_kind == "FAKE_TEST"):
            raise ValueError("Synthetic and production execution must remain distinguishable")
        return self


def read_profile(configuration: dict) -> ExecutionProfile | EngineeringProfile:
    version = configuration.get("version")
    if version == "phase-6r-profile-v1":
        from powerforge_extraction.phase6r_profile import Phase6RProfile, require_profile

        profile = Phase6RProfile.model_validate_json(json.dumps(configuration))
        require_profile(profile)
        return profile
    if version == "source-layout-profile-v1":
        from powerforge_extraction.layout_profiles import SourceLayoutProfile

        return SourceLayoutProfile.model_validate_json(json.dumps(configuration))
    if version == "source-preparation-profile-v1":
        from powerforge_extraction.enrichment_profiles import PreparationProfile

        return PreparationProfile.model_validate_json(json.dumps(configuration))
    raise ValueError("Unsupported pinned execution profile version")


def engineering_profile(key: str, settings: Settings) -> EngineeringProfile:
    """M4 exposes only synthetic stage execution; production registration belongs to M5."""
    from powerforge_extraction.engineering_stages import engineering_manifest
    from powerforge_extraction.grounding import grounding_identity
    from powerforge_extraction.identities import identity_hash
    from powerforge_extraction.interpretation import interpretation_identity
    from powerforge_extraction.stage_runtime import runtime_identity

    if key not in {ENGINEERING_TEST_PROFILE, ENGINEERING_TEXT_TEST_PROFILE}:
        raise ValueError("Unknown engineering test profile")
    manifest = engineering_manifest()
    return EngineeringProfile(
        key=key,
        execution_kind="FAKE_TEST",
        provider="fake",
        model="deterministic-engineering-v1",
        input_strategy="NATIVE_TEXT_ONLY"
        if key == ENGINEERING_TEXT_TEST_PROFILE
        else "NATIVE_TEXT_AND_IMAGE",
        prompt_hash=identity_hash(manifest),
        schema_hash=identity_hash(manifest),
        manifest=manifest,
        interpretation=interpretation_identity(),
        grounding=grounding_identity(),
        runtime=runtime_identity(),
        max_pages=settings.extraction_max_pages,
        max_input_bytes=settings.extraction_max_input_bytes,
        max_total_input_bytes=4 * 1024 * 1024,
        max_image_pixels=settings.extraction_max_image_pixels,
        max_text_chars=100000,
        max_instruction_bytes=128 * 1024,
        max_upstream_bytes=64 * 1024,
        max_output_tokens=8192,
        max_attempts=settings.extraction_max_attempts,
        max_calls=settings.extraction_max_calls,
        max_concurrent=settings.extraction_max_concurrent_per_run,
        timeout_seconds=settings.extraction_timeout_seconds,
        lease_seconds=settings.extraction_lease_seconds,
        backoff_seconds=settings.extraction_backoff_seconds,
        fake_scenario=settings.extraction_fake_scenario,
    )


def resolve_profile(key: str, settings: Settings) -> ExecutionProfile:
    from powerforge_extraction.phase6r_profile import KEY, phase6r_profile

    if key != KEY:
        raise ValueError("Unknown extraction profile")
    return phase6r_profile(settings)
