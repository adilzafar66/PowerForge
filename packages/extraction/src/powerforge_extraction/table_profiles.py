"""Separate v4 table-only profiles; accepted probe/prose wire formats stay frozen."""

import json
from importlib.resources import files
from typing import Literal

from pydantic import Field, model_validator

from powerforge_extraction.identities import identity_hash
from powerforge_extraction.profiles import ExecutionProfile
from powerforge_shared.config import Settings

TABLE_OPENAI_PROFILE = "tables-openai-v1"
TABLE_OPENAI_TEXT_PROFILE = "tables-openai-text-v1"
TABLE_TEST_PROFILE = "tables-test-v1"
TABLE_TEXT_TEST_PROFILE = "tables-test-text-v1"
TABLE_PRODUCTION_PROFILES = (TABLE_OPENAI_PROFILE, TABLE_OPENAI_TEXT_PROFILE)
TABLE_PROFILES = (*TABLE_PRODUCTION_PROFILES, TABLE_TEST_PROFILE, TABLE_TEXT_TEST_PROFILE)
ADAPTER_VERSION = "table-responses-input-v1"


def table_input_contract():
    return json.loads(
        files("powerforge_extraction").joinpath("prompts/table_input_v1.json").read_text()
    )


class TableProfile(ExecutionProfile):
    version: Literal["execution-profile-v4"] = "execution-profile-v4"
    execution_kind: Literal["FAKE_TEST", "TABLE_EXTRACTION"]
    stage: Literal["TABLE_RECONSTRUCTION"] = "TABLE_RECONSTRUCTION"
    stages: tuple[Literal["TABLE_RECONSTRUCTION", "TABLE_INTERPRETATION"], ...] = (
        "TABLE_RECONSTRUCTION",
        "TABLE_INTERPRETATION",
    )
    input_strategy: Literal["NATIVE_TEXT_AND_IMAGE", "NATIVE_TEXT_ONLY"]
    prompt_version: Literal["table-prompts-v1"] = "table-prompts-v1"
    schema_version: Literal["table-stage-manifest-v1"] = "table-stage-manifest-v1"
    manifest: dict
    grounding: dict
    runtime: dict
    adapter_version: Literal["table-responses-input-v1"] = ADAPTER_VERSION
    adapter_hash: str
    max_total_input_bytes: int = Field(ge=1)
    max_text_chars: int = Field(ge=1)
    max_instruction_bytes: int = Field(ge=1, le=131072)
    max_upstream_bytes: int = Field(ge=1, le=131072)
    image_detail: Literal["high", "auto"]
    reasoning_effort: Literal["none", "low", "medium", "high"]

    @model_validator(mode="after")
    def table_plan(self):
        if self.stages != ("TABLE_RECONSTRUCTION", "TABLE_INTERPRETATION"):
            raise ValueError("Unsupported table stage plan")
        if (self.provider == "fake") != (self.execution_kind == "FAKE_TEST"):
            raise ValueError("Synthetic and production table execution must stay distinguishable")
        return self


def table_profile(key: str, settings: Settings) -> TableProfile:
    from powerforge_extraction.table_grounding import table_identity
    from powerforge_extraction.table_runtime import table_runtime_identity
    from powerforge_extraction.table_stages import table_manifest

    if key not in TABLE_PROFILES:
        raise ValueError("Unknown table extraction profile")
    live = key in TABLE_PRODUCTION_PROFILES
    manifest = table_manifest()
    return TableProfile(
        key=key,
        execution_kind="TABLE_EXTRACTION" if live else "FAKE_TEST",
        provider="openai" if live else "fake",
        model=settings.extraction_model if live else "deterministic-tables-v1",
        input_strategy="NATIVE_TEXT_ONLY"
        if key in {TABLE_OPENAI_TEXT_PROFILE, TABLE_TEXT_TEST_PROFILE}
        else "NATIVE_TEXT_AND_IMAGE",
        prompt_hash=identity_hash(manifest),
        schema_hash=identity_hash(manifest),
        manifest=manifest,
        grounding=table_identity(),
        runtime=table_runtime_identity(),
        adapter_hash=identity_hash(table_input_contract()),
        max_pages=settings.extraction_max_pages,
        max_input_bytes=settings.extraction_max_input_bytes,
        max_total_input_bytes=settings.extraction_tables_max_total_input_bytes,
        max_text_chars=settings.extraction_tables_max_text_chars,
        max_instruction_bytes=131072,
        max_upstream_bytes=settings.extraction_tables_max_upstream_bytes,
        max_image_pixels=settings.extraction_max_image_pixels,
        max_output_tokens=settings.extraction_tables_max_output_tokens,
        image_detail=settings.extraction_tables_image_detail,
        reasoning_effort=settings.extraction_tables_reasoning_effort,
        max_attempts=settings.extraction_max_attempts,
        max_calls=settings.extraction_max_calls,
        max_concurrent=settings.extraction_max_concurrent_per_run,
        timeout_seconds=settings.extraction_timeout_seconds,
        lease_seconds=settings.extraction_lease_seconds,
        backoff_seconds=settings.extraction_backoff_seconds,
        fake_scenario="success" if live else settings.extraction_fake_scenario,
        pricing_basis=settings.extraction_pricing_basis if live else None,
        input_usd_per_million=settings.extraction_input_usd_per_million if live else None,
        output_usd_per_million=settings.extraction_output_usd_per_million if live else None,
    )
