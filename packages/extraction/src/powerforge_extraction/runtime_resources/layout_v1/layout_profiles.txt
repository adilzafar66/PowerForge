"""The fixed SOURCE_PREPARE -> SPATIAL_LAYOUT local plan, independent of model profiles."""

import hashlib
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from powerforge_document_processing.layout_derive import layout_rules_identity
from powerforge_extraction.enrichment_profiles import (
    PreparationProfile,
    preparation_profile,
    require_preparation,
)
from powerforge_provenance.layout_observations import layout_contract_identity
from powerforge_provenance.spatial_base import identity_hash

LAYOUT_PROFILE = "source-layout-v1"


class SourceLayoutProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal["source-layout-profile-v1"] = "source-layout-profile-v1"
    key: Literal["source-layout-v1"] = LAYOUT_PROFILE
    execution_kind: Literal["SOURCE_LAYOUT"] = "SOURCE_LAYOUT"
    provider: Literal["local"] = "local"
    stages: tuple[Literal["SOURCE_PREPARE", "SPATIAL_LAYOUT"], ...] = (
        "SOURCE_PREPARE",
        "SPATIAL_LAYOUT",
    )
    preparation: PreparationProfile
    algorithm_sha256: str
    contracts: dict
    execution_sha256: str
    max_pages: int = Field(ge=1, le=50)
    max_attempts: int = Field(ge=1, le=3)
    max_calls: int = Field(ge=1, le=150)
    max_concurrent: Literal[1] = 1
    timeout_seconds: Literal[120] = 120
    layout_timeout_seconds: Literal[30] = 30
    lease_seconds: Literal[30] = 30
    backoff_seconds: int = Field(ge=0, le=300)

    @model_validator(mode="after")
    def fixed(self):
        if self.stages != ("SOURCE_PREPARE", "SPATIAL_LAYOUT") or (
            self.max_pages,
            self.max_attempts,
            self.max_calls,
            self.backoff_seconds,
        ) != (
            self.preparation.max_pages,
            self.preparation.max_attempts,
            self.preparation.max_calls,
            self.preparation.backoff_seconds,
        ):
            raise ValueError("Layout plan/admissions differ from the fixed preparation component")
        return self

    @property
    def identity_hash(self):
        return identity_hash(self.model_dump(mode="json"))


def layout_execution_identity():
    root = files("powerforge_extraction")
    return identity_hash(
        {
            name: hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest()
            for name in (
                "layout_profiles.py",
                "layout_service.py",
                "layout_execution.py",
                "layout_sources.py",
            )
        }
    )


def layout_profile(settings):
    preparation = preparation_profile(settings)
    return SourceLayoutProfile(
        preparation=preparation,
        algorithm_sha256=layout_rules_identity(),
        contracts=layout_contract_identity(),
        execution_sha256=layout_execution_identity(),
        max_pages=preparation.max_pages,
        max_attempts=preparation.max_attempts,
        max_calls=preparation.max_calls,
        backoff_seconds=preparation.backoff_seconds,
    )


def require_layout(profile):
    require_preparation(profile.preparation)
    if (
        profile.algorithm_sha256 != layout_rules_identity()
        or profile.contracts != layout_contract_identity()
        or profile.execution_sha256 != layout_execution_identity()
    ):
        raise ValueError("Pinned spatial-layout resources unavailable")
