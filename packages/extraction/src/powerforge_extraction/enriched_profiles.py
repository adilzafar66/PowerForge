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


SEMANTIC_ENGINEERING = "engineering-openai-enriched-v2"
SEMANTIC_TABLES = "tables-openai-enriched-v2"
DISTRIBUTED_ENGINEERING = "engineering-openai-enriched-v3"
SOURCE_SUPPORTED_TABLES = "tables-openai-enriched-v3"
SEMANTIC_PROFILES = (SEMANTIC_ENGINEERING, SEMANTIC_TABLES)
SEMANTIC_V3_PROFILES = (DISTRIBUTED_ENGINEERING, SOURCE_SUPPORTED_TABLES)
COMPACT_TABLES = "tables-openai-enriched-v4"
SUCCESSOR_PROFILES = (*SEMANTIC_PROFILES, *SEMANTIC_V3_PROFILES, COMPACT_TABLES)


class SemanticEngineeringProfile(EnrichedEngineeringProfile):
    key: Literal["engineering-openai-enriched-v2"]
    prompt_version: Literal["enriched-semantics-prompts-v2"] = "enriched-semantics-prompts-v2"
    schema_version: Literal["enriched-stage-manifest-v2"] = "enriched-stage-manifest-v2"


class DistributedEngineeringProfile(SemanticEngineeringProfile):
    key: Literal["engineering-openai-enriched-v3"]
    prompt_version: Literal["enriched-semantics-prompts-v3"] = "enriched-semantics-prompts-v3"
    schema_version: Literal["enriched-stage-manifest-v3"] = "enriched-stage-manifest-v3"


class SemanticTableProfile(EnrichedTableProfile):
    key: Literal["tables-openai-enriched-v2"]
    prompt_version: Literal["enriched-semantics-prompts-v2"] = "enriched-semantics-prompts-v2"
    schema_version: Literal["enriched-stage-manifest-v2"] = "enriched-stage-manifest-v2"


class SourceSupportedTableProfile(SemanticTableProfile):
    key: Literal["tables-openai-enriched-v3"]
    prompt_version: Literal["enriched-semantics-prompts-v3"] = "enriched-semantics-prompts-v3"
    schema_version: Literal["enriched-stage-manifest-v3"] = "enriched-stage-manifest-v3"


class CompactTableProfile(SourceSupportedTableProfile):
    key: Literal["tables-openai-enriched-v4"]
    prompt_version: Literal["enriched-table-prompts-v4"] = "enriched-table-prompts-v4"
    schema_version: Literal["enriched-stage-manifest-v4"] = "enriched-stage-manifest-v4"


def is_semantic(profile):
    return isinstance(profile, (SemanticEngineeringProfile, SemanticTableProfile))


def stage_models(profile):
    if isinstance(profile, CompactTableProfile):
        from powerforge_extraction.semantic_observations import SEMANTIC_RESPONSES
        from powerforge_extraction.table_reconstruction_v4 import CompactReconstructionResponse

        return {**SEMANTIC_RESPONSES, "TABLE_RECONSTRUCTION": CompactReconstructionResponse}
    if is_semantic(profile):
        from powerforge_extraction.semantic_observations import SEMANTIC_RESPONSES

        return SEMANTIC_RESPONSES
    return RESPONSES


def stage_schemas(profile):
    if not is_semantic(profile):
        return SCHEMAS
    return {
        stage: model.model_fields["schema_version"].annotation.__args__[0]
        for stage, model in stage_models(profile).items()
    }


def prompt_for(profile, stage):
    if isinstance(profile, CompactTableProfile):
        return (
            "prompts/table_reconstruction_v4.txt"
            if stage == "TABLE_RECONSTRUCTION"
            else "prompts/table_interpretation_v4.txt"
        )
    if profile.key in SEMANTIC_V3_PROFILES and stage != "TABLE_RECONSTRUCTION":
        return "prompts/enriched_semantics_v3.txt"
    if is_semantic(profile) and stage != "TABLE_RECONSTRUCTION":
        return "prompts/enriched_semantics_v2.txt"
    return "prompts/enriched_v1.txt"


def semantic_manifest(profile):
    root = files("powerforge_extraction")
    return dict(
        version=profile.schema_version,
        stages=[
            dict(
                stage=stage,
                schema_version=stage_schemas(profile)[stage],
                schema_hash=identity_hash(model.model_json_schema()),
                template_sha256=hashlib.sha256(
                    root.joinpath(prompt_for(profile, stage)).read_bytes()
                ).hexdigest(),
            )
            for stage, model in stage_models(profile).items()
        ],
    )


def semantic_runtime(profile):
    compact = isinstance(profile, CompactTableProfile)
    distributed = profile.key in SEMANTIC_V3_PROFILES
    archived_v3 = {
        "enriched_profiles.py",
        "execution.py",
        "enriched_runtime.py",
        "enriched_tables.py",
        "semantic_tables.py",
    }
    archived = {
        "semantic_output.py",
        "semantic_tables.py",
        "execution.py",
        "enriched_profiles.py",
    }
    archive = archived_v3 if distributed else archived_v3 | archived

    def resource(name):
        if compact or name not in archive:
            return name
        if not distributed and name in archived:
            return f"runtime_resources/semantics_v2/{name.removesuffix('.py')}.txt"
        return f"runtime_resources/semantics_v3/{name.removesuffix('.py')}.txt"

    root = files("powerforge_extraction")
    return {
        **runtime_identity(),
        "version": "enriched-page-runtime-v4"
        if compact
        else "enriched-page-runtime-v3"
        if distributed
        else "enriched-page-runtime-v2",
        "semantic_rules": identity_hash(
            {
                name: hashlib.sha256(root.joinpath(resource(name)).read_bytes()).hexdigest()
                for name in (
                    "semantic_observations.py",
                    "semantic_output.py",
                    "semantic_tables.py",
                    "enriched_grounding.py",
                    "enriched_output.py",
                    "enriched_tables.py",
                    "execution.py",
                    "enriched_runtime.py",
                    "enriched_input.py",
                    "enriched_profiles.py",
                    *(("table_reconstruction_v4.py", "enriched_publication.py") if compact else ()),
                )
            }
        ),
    }


def _family(profile):
    if (profile.key in (*PRODUCTION, *SUCCESSOR_PROFILES)) != (
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
    # These compatible execution and publication fixes keep admitted v5/v6 runs
    # executable. The accepted source bytes are retained as identity data only.
    retained = {
        "profiles.py",
        "enriched_input.py",
        "enriched_runtime.py",
        "enriched_grounding.py",
        "enriched_output.py",
        "enriched_tables.py",
        "enriched_profiles.py",
        "enriched_publication.py",
        "orchestration.py",
        "execution.py",
        "persistence.py",
    }
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
            {
                name: hashlib.sha256(
                    root.joinpath(
                        "runtime_resources/enriched_v1/" + name.removesuffix(".py") + ".txt"
                        if name in retained
                        else name
                    ).read_bytes()
                ).hexdigest()
                for name in names
            }
        ),
        locator_schema=identity_hash(EnrichedLocation.model_json_schema()),
        locator_rules=hashlib.sha256(
            files("powerforge_provenance").joinpath("enriched_locations.py").read_bytes()
        ).hexdigest(),
    )


def enriched_profile(key, settings):
    if key in SUCCESSOR_PROFILES:
        engineering = key in (SEMANTIC_ENGINEERING, DISTRIBUTED_ENGINEERING)
        model = (
            CompactTableProfile
            if key == COMPACT_TABLES
            else DistributedEngineeringProfile
            if key == DISTRIBUTED_ENGINEERING
            else SourceSupportedTableProfile
            if key == SOURCE_SUPPORTED_TABLES
            else SemanticEngineeringProfile
            if engineering
            else SemanticTableProfile
        )
        base = enriched_profile(ENGINEERING if engineering else TABLES, settings)
        profile = model.model_validate(
            {
                **base.model_dump(),
                "key": key,
                "schema_version": model.model_fields["schema_version"].default,
                "prompt_version": model.model_fields["prompt_version"].default,
                "max_instruction_bytes": 131072,
            }
        )
        record = semantic_manifest(profile)
        digest = identity_hash(record)
        return profile.model_copy(
            update={
                "manifest": record,
                "runtime": semantic_runtime(profile),
                "prompt_hash": digest,
                "schema_hash": digest,
                "adapter_hash": digest,
            }
        )
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
    semantic = is_semantic(profile)
    record = semantic_manifest(profile) if semantic else manifest()
    if (
        profile.key not in (*PROFILES, *SUCCESSOR_PROFILES)
        or profile.manifest != record
        or profile.runtime != (semantic_runtime(profile) if semantic else runtime_identity())
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
