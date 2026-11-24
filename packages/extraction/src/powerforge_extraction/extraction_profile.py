"""One versioned extraction plan shared by provider and deterministic test transport."""

from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from powerforge_document_processing.layout_derive import layout_rules_identity
from powerforge_extraction.errors import ExtractionDisabled
from powerforge_extraction.identities import content_hash, identity_hash
from powerforge_extraction.profiles import ExecutionProfile
from powerforge_extraction.stage_contracts import (
    ATTRIBUTE_INPUT_VERSION,
    LEGACY_ATTRIBUTE_INPUT_VERSION,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    AttributeProviderResponse,
    RecognitionResponse,
    attribute_catalog,
    equipment_catalog,
    stage_schema_version,
)
from powerforge_shared.config import AttributeInputVersion, AttributeReasoningEffort

KEY = "phase-6r"
PROFILE_VERSION = "phase-6r-profile-v1"
STAGES = ("EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION")
RESPONSES = dict(zip(STAGES, (RecognitionResponse, AttributeProviderResponse), strict=True))
PROMPT_VERSION = "phase-6r-stages-v10"
SCHEMA_VERSION = "phase-6r-wire-v7"
PROMPTS = {
    stage: files("powerforge_extraction")
    .joinpath(f"prompts/{filename}")
    .read_text(encoding="utf-8")
    for stage, filename in zip(
        STAGES, ("equipment_recognition_v3.txt", "attribute_extraction_v9.txt"), strict=True
    )
}

COMPACT_PROMPT_VERSION = "phase-6r-stages-v11"
COMPACT_ATTRIBUTE_PROMPT = (
    files("powerforge_extraction")
    .joinpath("prompts/attribute_extraction_v10.txt")
    .read_text(encoding="utf-8")
)


def prompt_bundle(input_version: AttributeInputVersion):
    if input_version == ATTRIBUTE_INPUT_VERSION:
        return COMPACT_PROMPT_VERSION, {**PROMPTS, STAGES[1]: COMPACT_ATTRIBUTE_PROMPT}
    if input_version == LEGACY_ATTRIBUTE_INPUT_VERSION:
        return PROMPT_VERSION, PROMPTS
    raise ValueError("Unsupported pinned Stage 2 provider view")


REASONING_POLICY_VERSION = "openai-stage2-effort-v1"
REASONING_MODEL = "gpt-6-luna"


class AttributeReasoningPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[REASONING_POLICY_VERSION] = REASONING_POLICY_VERSION
    effort: AttributeReasoningEffort


class ExtractionProfile(ExecutionProfile):
    provider: Literal["fake", "openai"]
    key: Literal["phase-6r"] = KEY
    version: Literal["phase-6r-profile-v1"] = PROFILE_VERSION
    execution_kind: Literal["FAKE_TEST", "UNIFIED_EXTRACTION"]
    stage: Literal["EQUIPMENT_RECOGNITION"] = "EQUIPMENT_RECOGNITION"
    input_strategy: Literal["PINNED_PAGE"] = "PINNED_PAGE"
    stages: tuple[Literal["EQUIPMENT_RECOGNITION"], Literal["ATTRIBUTE_EXTRACTION"]] = STAGES
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    manifest: dict
    source_rules: str
    max_transport_bytes: int = Field(gt=0)
    response_audit_retention_days: int = Field(ge=1, le=365)

    attribute_reasoning: AttributeReasoningPolicy | None = None

    @model_validator(mode="after")
    def validate_attribute_reasoning(self):
        if self.attribute_reasoning is not None and (
            self.provider != "openai" or self.model != REASONING_MODEL
        ):
            raise ValueError("Unsupported model for the pinned Stage 2 reasoning policy")
        return self

    def reasoning_effort_for(self, stage: str) -> AttributeReasoningEffort | None:
        if stage == STAGES[1] and self.attribute_reasoning is not None:
            return self.attribute_reasoning.effort
        return None

    def instructions_for(self, stage: str) -> str:
        _, prompts = prompt_bundle(self.manifest["attribute_input_version"])
        return prompts[stage]

    @property
    def identity_hash(self):
        # PostgreSQL JSONB can reorder nested manifest keys on reload.
        exclude = {"attribute_reasoning"} if self.attribute_reasoning is None else None
        return identity_hash(self.model_dump(mode="json", exclude=exclude))


def stage_request_hash(input_text: str, effort: AttributeReasoningEffort | None) -> str:
    digest = content_hash(input_text)
    if effort is None:
        return digest
    return identity_hash(
        {"version": REASONING_POLICY_VERSION, "input_sha256": digest, "reasoning_effort": effort}
    )


def structured_schema(value: dict) -> dict:
    """Project the live-tested shape. The configured model rejects the extended schema."""
    properties = {}
    for name, child in value.items():
        if name in {"properties", "$defs"}:
            properties[name] = {key: structured_schema(item) for key, item in child.items()}
        elif name in {"items"}:
            properties[name] = structured_schema(child)
        elif name == "anyOf":
            properties[name] = [structured_schema(item) for item in child]
        elif name == "const":
            properties["enum"] = [child]
        elif name in {
            "type",
            "$ref",
            "enum",
            "title",
            "description",
        }:
            properties[name] = child
    if properties.get("type") == "object":
        properties["required"] = list(properties.get("properties", ()))
        properties["additionalProperties"] = False
    return properties


def manifest(input_version: AttributeInputVersion = LEGACY_ATTRIBUTE_INPUT_VERSION):
    # The registry projection is pinned for both stages, including attribute definitions.
    from powerforge_engineering_model.registry_v1 import REGISTRY
    from powerforge_extraction.assertion_consistency import VERSION as CONSISTENCY_VERSION
    from powerforge_extraction.publication import VERSION as PUBLICATION_VERSION
    from powerforge_extraction.stage_contracts import (
        ATTRIBUTE_DESCRIPTION_VERSION,
        DESCRIPTION_VERSION,
        EquipmentObservation,
        RecognitionResponse,
    )
    from powerforge_extraction.unit_notation import VERSION as UNIT_INTERPRETATION_VERSION

    _, prompts = prompt_bundle(input_version)
    catalog = equipment_catalog()
    sample = RecognitionResponse(
        version=stage_schema_version(STAGES[0]),
        stage=STAGES[0],
        page_context_hash="0" * 64,
        equipment=tuple(
            EquipmentObservation(
                local_ref=item.key.value,
                registry_type=item.key,
                source_description=item.name,
                tag_state="ABSENT",
                tag=None,
                qualification="UNKNOWN",
                raw_qualification=None,
                evidence=(),
            )
            for item in catalog
        ),
    )
    return {
        "version": SCHEMA_VERSION,
        "registry_version": REGISTRY.registry_version,
        "publication_version": PUBLICATION_VERSION,
        "unit_interpretation_version": UNIT_INTERPRETATION_VERSION,
        "consistency_version": CONSISTENCY_VERSION,
        "descriptions": DESCRIPTION_VERSION,
        "attribute_descriptions": ATTRIBUTE_DESCRIPTION_VERSION,
        "attribute_input_version": input_version,
        "catalog_hash": identity_hash(
            [
                [item.model_dump(mode="json") for item in catalog],
                [item.model_dump(mode="json") for item in attribute_catalog(sample)],
            ]
        ),
        "prompt_hash": identity_hash(prompts),
        "stages": [
            {
                "stage": stage,
                "version": stage_schema_version(stage),
                "prompt_hash": identity_hash(prompts[stage]),
                "schema_hash": identity_hash(model.model_json_schema()),
                "transport_schema_hash": identity_hash(
                    structured_schema(model.model_json_schema())
                ),
            }
            for stage, model in RESPONSES.items()
        ],
    }


def extraction_profile(settings):
    fake = settings.extraction_use_fake_provider
    if not fake and settings.extraction_model != REASONING_MODEL:
        raise ExtractionDisabled("The configured model is unsupported for Stage 2 reasoning effort")
    input_version = settings.extraction_attribute_input_version
    record = manifest(input_version)
    prompt_version, _ = prompt_bundle(input_version)
    return ExtractionProfile(
        provider="fake" if fake else "openai",
        model="deterministic-phase-6r-v1" if fake else settings.extraction_model,
        execution_kind="FAKE_TEST" if fake else "UNIFIED_EXTRACTION",
        prompt_version=prompt_version,
        prompt_hash=record["prompt_hash"],
        schema_hash=identity_hash(record["stages"]),
        manifest=record,
        attribute_reasoning=None
        if fake
        else AttributeReasoningPolicy(effort=settings.extraction_attribute_reasoning_effort),
        source_rules=layout_rules_identity(),
        max_pages=min(50, settings.extraction_max_pages),
        max_input_bytes=min(MAX_IMAGE_BYTES, settings.extraction_max_input_bytes),
        max_image_pixels=min(MAX_IMAGE_PIXELS, settings.extraction_max_image_pixels),
        max_transport_bytes=settings.extraction_max_request_bytes,
        response_audit_retention_days=settings.extraction_response_audit_retention_days,
        max_output_tokens=settings.extraction_max_output_tokens,
        max_attempts=settings.extraction_max_attempts,
        max_calls=settings.extraction_max_calls,
        max_concurrent=settings.extraction_max_concurrent_per_run,
        timeout_seconds=settings.extraction_timeout_seconds,
        lease_seconds=settings.extraction_lease_seconds,
        backoff_seconds=settings.extraction_backoff_seconds,
        fake_scenario=settings.extraction_fake_scenario if fake else "success",
        pricing_basis=None if fake else settings.extraction_pricing_basis,
        input_usd_per_million=None if fake else settings.extraction_input_usd_per_million,
        output_usd_per_million=None if fake else settings.extraction_output_usd_per_million,
    )


def require_profile(profile):
    input_version = profile.manifest.get("attribute_input_version")
    if input_version not in {LEGACY_ATTRIBUTE_INPUT_VERSION, ATTRIBUTE_INPUT_VERSION}:
        raise ValueError("Pinned extraction resources do not match this installation")
    record = manifest(input_version)
    prompt_version, _ = prompt_bundle(input_version)
    if (
        profile.manifest != record
        or profile.prompt_version != prompt_version
        or profile.prompt_hash != record["prompt_hash"]
        or profile.schema_hash != identity_hash(record["stages"])
        or profile.source_rules != layout_rules_identity()
        or (profile.provider == "fake") != (profile.execution_kind == "FAKE_TEST")
    ):
        raise ValueError("Pinned extraction resources do not match this installation")


def provider_available(settings, provider):
    if provider == "local":
        return settings.enrichment_enabled
    if not settings.extraction_enabled:
        return False
    if provider == "fake":
        return settings.extraction_use_fake_provider
    return (
        provider == "openai"
        and settings.extraction_external_enabled
        and not (settings.extraction_use_fake_provider or settings.enrichment_worker_only)
    )
