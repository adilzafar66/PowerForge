"""Separate v5/v6 enriched profiles, with frozen legacy meaning and source identities."""

import hashlib
from importlib.resources import files
from typing import Literal

from pydantic import model_validator

from powerforge_document_processing.layout_derive import layout_rules_identity
from powerforge_extraction.enriched_observations import RESPONSES, SCHEMAS
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.interpretation import interpretation_identity
from powerforge_extraction.production_profiles import ProductionProfile, production_profile
from powerforge_extraction.table_grounding import table_identity
from powerforge_extraction.table_profiles import TableProfile, table_profile
from powerforge_provenance.enriched_locations import EnrichedLocation

ENGINEERING = "engineering-openai-enriched-v1"
TABLES = "tables-openai-enriched-v1"
ENGINEERING_TEST = "engineering-test-enriched-v1"
TABLES_TEST = "tables-test-enriched-v1"
PRODUCTION = (ENGINEERING, TABLES)
PROFILES = (*PRODUCTION, ENGINEERING_TEST, TABLES_TEST)


class EnrichedEngineeringProfile(ProductionProfile):
    key: Literal["engineering-openai-enriched-v1", "engineering-test-enriched-v1"]
    version: Literal["execution-profile-v5"] = "execution-profile-v5"
    execution_kind: Literal["FAKE_TEST", "ENGINEERING_EXTRACTION"]
    provider: Literal["openai", "fake"]
    adapter_version: Literal["enriched-responses-input-v1"] = "enriched-responses-input-v1"
    schema_version: Literal["enriched-stage-manifest-v1"] = "enriched-stage-manifest-v1"
    prompt_version: Literal["enriched-prompts-v1"] = "enriched-prompts-v1"
    source_rules: str

    @model_validator(mode="after")
    def source_family(self):
        return _family(self)


class EnrichedTableProfile(TableProfile):
    key: Literal["tables-openai-enriched-v1", "tables-test-enriched-v1"]
    version: Literal["execution-profile-v6"] = "execution-profile-v6"
    adapter_version: Literal["enriched-responses-input-v1"] = "enriched-responses-input-v1"
    schema_version: Literal["enriched-stage-manifest-v1"] = "enriched-stage-manifest-v1"
    prompt_version: Literal["enriched-prompts-v1"] = "enriched-prompts-v1"
    source_rules: str

    @model_validator(mode="after")
    def source_family(self):
        return _family(self)


def _family(profile):
    if (profile.key in PRODUCTION) != (
        profile.provider == "openai"
    ) or profile.input_strategy != "NATIVE_TEXT_AND_IMAGE":
        raise ValueError("Enhanced source strategy and synthetic/production family must match")
    return profile


def is_enriched(profile):
    return isinstance(profile, (EnrichedEngineeringProfile, EnrichedTableProfile))


def manifest():
    prompt = files("powerforge_extraction").joinpath("prompts/enriched_v1.txt").read_bytes()
    return dict(
        version="enriched-stage-manifest-v1",
        template_sha256=hashlib.sha256(prompt).hexdigest(),
        stages=[
            dict(
                stage=stage,
                schema_version=SCHEMAS[stage],
                schema_hash=identity_hash(model.model_json_schema()),
            )
            for stage, model in RESPONSES.items()
        ],
    )


def runtime_identity():
    root = files("powerforge_extraction")
    names = (
        "enriched_profiles.py",
        "enriched_observations.py",
        "enriched_contracts.py",
        "enriched_sources.py",
        "enriched_planning.py",
        "enriched_grounding.py",
        "enriched_output.py",
        "enriched_tables.py",
        "enriched_runtime.py",
        "enriched_publication.py",
        "enriched_input.py",
        "enriched_fake.py",
        "profiles.py",
        "stage_runtime.py",
        "orchestration.py",
        "execution.py",
        "persistence.py",
        "models.py",
        "enrichment_models.py",
    )
    return dict(
        version="enriched-page-runtime-v1",
        rules_hash=identity_hash(
            {name: hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest() for name in names}
        ),
        locator_schema=identity_hash(EnrichedLocation.model_json_schema()),
        locator_rules=hashlib.sha256(
            files("powerforge_provenance").joinpath("enriched_locations.py").read_bytes()
        ).hexdigest(),
    )


def enriched_profile(key, settings):
    if key not in PROFILES:
        raise ValueError("Unknown enriched extraction profile")
    table = key in (TABLES, TABLES_TEST)
    live = key in PRODUCTION
    base = (
        table_profile("tables-openai-v1", settings)
        if table
        else production_profile("engineering-openai-v1", settings)
    ).model_dump()
    record = manifest()
    base.update(
        key=key,
        version="execution-profile-v6" if table else "execution-profile-v5",
        provider="openai" if live else "fake",
        execution_kind=("TABLE_EXTRACTION" if table else "ENGINEERING_EXTRACTION")
        if live
        else "FAKE_TEST",
        model=settings.extraction_model if live else "deterministic-enriched-v1",
        adapter_version="enriched-responses-input-v1",
        adapter_hash=identity_hash(record),
        prompt_version="enriched-prompts-v1",
        schema_version=record["version"],
        manifest=record,
        prompt_hash=identity_hash(record),
        schema_hash=identity_hash(record),
        runtime=runtime_identity(),
        grounding=table_identity() if table else interpretation_identity(),
        source_rules=layout_rules_identity(),
        max_upstream_bytes=131072,
        max_pages=min(50, settings.extraction_max_pages),
        input_strategy="NATIVE_TEXT_AND_IMAGE",
        fake_scenario="success" if live else settings.extraction_fake_scenario,
    )
    if not live:
        base.update(pricing_basis=None, input_usd_per_million=None, output_usd_per_million=None)
    return (EnrichedTableProfile if table else EnrichedEngineeringProfile).model_validate(base)


def require_enriched(profile):
    record = manifest()
    if (
        profile.key not in PROFILES
        or profile.manifest != record
        or profile.runtime != runtime_identity()
        or profile.source_rules != layout_rules_identity()
        or profile.prompt_hash != identity_hash(record)
        or profile.schema_hash != identity_hash(record)
        or profile.adapter_hash != identity_hash(record)
        or profile.grounding
        != (
            table_identity()
            if isinstance(profile, EnrichedTableProfile)
            else interpretation_identity()
        )
    ):
        raise ValueError("Pinned enriched resources are unavailable")
