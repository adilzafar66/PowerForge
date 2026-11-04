"""Opt-in production profiles and the pinned provider input contract. No SDK imports."""

import json
from importlib.resources import files
from typing import Literal

from powerforge_extraction.identities import identity_hash
from powerforge_extraction.profiles import (
    ENGINEERING_TEST_PROFILE,
    EngineeringProfile,
    engineering_profile,
)
from powerforge_shared.config import Settings

ENGINEERING_OPENAI_PROFILE = "engineering-openai-v1"
ENGINEERING_OPENAI_TEXT_PROFILE = "engineering-openai-text-v1"
PRODUCTION_PROFILES = (ENGINEERING_OPENAI_PROFILE, ENGINEERING_OPENAI_TEXT_PROFILE)
ADAPTER_VERSION = "openai-engineering-responses-v1"
PRODUCTION_RUNTIME_VERSION = "engineering-page-runtime-v2"


def input_contract() -> dict:
    return json.loads(
        files("powerforge_extraction")
        .joinpath("prompts/openai_input_v1.json")
        .read_text(encoding="utf-8")
    )


class ProductionProfile(EngineeringProfile):
    # Separate wire format preserves every existing v2 default, serialization and hash.
    version: Literal["execution-profile-v3"] = "execution-profile-v3"
    execution_kind: Literal["ENGINEERING_EXTRACTION"] = "ENGINEERING_EXTRACTION"
    provider: Literal["openai"] = "openai"
    adapter_version: Literal["openai-engineering-responses-v1"] = ADAPTER_VERSION
    adapter_hash: str
    reasoning_effort: Literal["none", "low", "medium", "high"]


def require_production_supported(profile: ProductionProfile) -> None:
    if (
        profile.runtime.get("version") != PRODUCTION_RUNTIME_VERSION
        or profile.adapter_version != ADAPTER_VERSION
        or profile.adapter_hash != identity_hash(input_contract())
    ):
        raise ValueError("Pinned production transport is unavailable")


def production_profile(key: str, settings: Settings) -> ProductionProfile:
    from powerforge_extraction.stage_runtime import runtime_identity

    if key not in PRODUCTION_PROFILES:
        raise ValueError("Unknown production extraction profile")
    base = engineering_profile(ENGINEERING_TEST_PROFILE, settings).model_dump()
    base.update(
        key=key,
        version="execution-profile-v3",
        execution_kind="ENGINEERING_EXTRACTION",
        provider="openai",
        model=settings.extraction_model,
        input_strategy="NATIVE_TEXT_ONLY"
        if key == ENGINEERING_OPENAI_TEXT_PROFILE
        else "NATIVE_TEXT_AND_IMAGE",
        runtime=runtime_identity(PRODUCTION_RUNTIME_VERSION),
        max_output_tokens=settings.extraction_engineering_max_output_tokens,
        max_total_input_bytes=settings.extraction_engineering_max_total_input_bytes,
        max_text_chars=settings.extraction_engineering_max_text_chars,
        max_upstream_bytes=settings.extraction_engineering_max_upstream_bytes,
        image_detail=settings.extraction_engineering_image_detail,
        reasoning_effort=settings.extraction_engineering_reasoning_effort,
        adapter_hash=identity_hash(input_contract()),
        fake_scenario="success",
        pricing_basis=settings.extraction_pricing_basis,
        input_usd_per_million=settings.extraction_input_usd_per_million,
        output_usd_per_million=settings.extraction_output_usd_per_million,
    )
    return ProductionProfile.model_validate(base)
