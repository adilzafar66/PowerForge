"""One versioned extraction plan shared by provider and deterministic test transport."""

from importlib.resources import files
from typing import Literal

from pydantic import Field

from powerforge_document_processing.layout_derive import layout_rules_identity
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.phase6r_contracts import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    VERSION,
    AttributeResponse,
    RecognitionResponse,
    attribute_catalog,
    equipment_catalog,
)
from powerforge_extraction.profiles import ExecutionProfile

KEY = "phase-6r"
PROFILE_VERSION = "phase-6r-profile-v1"
STAGES = ("EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION")
RESPONSES = dict(zip(STAGES, (RecognitionResponse, AttributeResponse), strict=True))
PROMPT_VERSION = "phase-6r-stages-v2"
PROMPTS = {
    stage: files("powerforge_extraction")
    .joinpath(f"prompts/phase6r_{stage.lower()}_{'v2' if stage == STAGES[0] else 'v1'}.txt")
    .read_text(encoding="utf-8")
    for stage in STAGES
}


class Phase6RProfile(ExecutionProfile):
    provider: Literal["fake", "openai"]
    key: Literal["phase-6r"] = KEY
    version: Literal["phase-6r-profile-v1"] = PROFILE_VERSION
    execution_kind: Literal["FAKE_TEST", "UNIFIED_EXTRACTION"]
    stage: Literal["EQUIPMENT_RECOGNITION"] = "EQUIPMENT_RECOGNITION"
    input_strategy: Literal["PINNED_PAGE"] = "PINNED_PAGE"
    stages: tuple[Literal["EQUIPMENT_RECOGNITION"], Literal["ATTRIBUTE_EXTRACTION"]] = STAGES
    schema_version: Literal["phase-6r-v1"] = VERSION
    manifest: dict
    source_rules: str
    max_transport_bytes: int = Field(gt=0)

    @property
    def identity_hash(self):
        # PostgreSQL JSONB can reorder nested manifest keys on reload.
        return identity_hash(self.model_dump(mode="json"))


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


def manifest():
    # The registry projection is pinned for both stages, including attribute definitions.
    from powerforge_engineering_model.registry_v1 import REGISTRY
    from powerforge_extraction.phase6r_contracts import (
        DESCRIPTION_VERSION,
        EquipmentObservation,
        RecognitionResponse,
    )
    from powerforge_extraction.phase6r_publication import VERSION as PUBLICATION_VERSION

    catalog = equipment_catalog()
    sample = RecognitionResponse(
        version=VERSION,
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
        "version": VERSION,
        "registry_version": REGISTRY.registry_version,
        "publication_version": PUBLICATION_VERSION,
        "descriptions": DESCRIPTION_VERSION,
        "catalog_hash": identity_hash(
            [
                [item.model_dump(mode="json") for item in catalog],
                [item.model_dump(mode="json") for item in attribute_catalog(sample)],
            ]
        ),
        "prompt_hash": identity_hash(PROMPTS),
        "stages": [
            {
                "stage": stage,
                "prompt_hash": identity_hash(PROMPTS[stage]),
                "schema_hash": identity_hash(model.model_json_schema()),
                "transport_schema_hash": identity_hash(
                    structured_schema(model.model_json_schema())
                ),
            }
            for stage, model in RESPONSES.items()
        ],
    }


def phase6r_profile(settings):
    fake = settings.extraction_phase6r_fake
    record = manifest()
    return Phase6RProfile(
        provider="fake" if fake else "openai",
        model="deterministic-phase-6r-v1" if fake else settings.extraction_model,
        execution_kind="FAKE_TEST" if fake else "UNIFIED_EXTRACTION",
        prompt_version=PROMPT_VERSION,
        prompt_hash=record["prompt_hash"],
        schema_hash=identity_hash(record["stages"]),
        manifest=record,
        source_rules=layout_rules_identity(),
        max_pages=min(50, settings.extraction_max_pages),
        max_input_bytes=min(MAX_IMAGE_BYTES, settings.extraction_max_input_bytes),
        max_image_pixels=min(MAX_IMAGE_PIXELS, settings.extraction_max_image_pixels),
        max_transport_bytes=settings.extraction_engineering_max_total_input_bytes,
        max_output_tokens=settings.extraction_engineering_max_output_tokens,
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
    record = manifest()
    if (
        profile.manifest != record
        or profile.prompt_version != PROMPT_VERSION
        or profile.prompt_hash != record["prompt_hash"]
        or profile.schema_hash != identity_hash(record["stages"])
        or profile.source_rules != layout_rules_identity()
        or (profile.provider == "fake") != (profile.execution_kind == "FAKE_TEST")
    ):
        raise ValueError("Pinned Phase 6R resources do not match this installation")


def provider_available(settings, provider):
    if provider == "local":
        return settings.enrichment_enabled
    if not settings.extraction_enabled:
        return False
    if provider == "fake":
        return settings.extraction_phase6r_fake
    return (
        provider == "openai"
        and settings.extraction_external_enabled
        and not (settings.extraction_phase6r_fake or settings.enrichment_worker_only)
    )
