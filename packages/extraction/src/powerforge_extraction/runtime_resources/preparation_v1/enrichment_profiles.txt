"""Independent local profile; no registry, prompt, model or AI-call metadata."""

import hashlib
import json
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from powerforge_ai.ocr import OCRIdentity, OCRSettings
from powerforge_document_processing.native_spatial import native_identity
from powerforge_provenance.spatial_base import POLICY, identity_hash
from powerforge_provenance.spatial_identity import spatial_contract_identity

PREPARATION_PROFILE = "source-preparation-v1"
PURPOSE = "SOURCE_ENRICHMENT"


class PreparationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal["source-preparation-profile-v1"] = "source-preparation-profile-v1"
    key: Literal["source-preparation-v1"] = PREPARATION_PROFILE
    execution_kind: Literal["SOURCE_PREPARATION"] = "SOURCE_PREPARATION"
    provider: Literal["local"] = "local"
    stage: Literal["SOURCE_PREPARE"] = "SOURCE_PREPARE"
    native: dict
    ocr_identity: OCRIdentity
    ocr_settings: OCRSettings
    contracts: dict
    rules_hash: str
    max_pages: int = Field(default=50, ge=1, le=50)
    max_attempts: int = Field(default=3, ge=1, le=3)
    max_calls: int = Field(default=150, ge=1, le=150)
    max_concurrent: Literal[1] = 1
    timeout_seconds: Literal[120] = 120
    lease_seconds: Literal[30] = 30
    backoff_seconds: int = Field(default=5, ge=0, le=300)

    @property
    def identity_hash(self):
        return identity_hash(self.model_dump(mode="json"))


def preparation_rules():
    root = files("powerforge_extraction")
    return identity_hash(
        {
            name: hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest()
            for name in (
                "enrichment_profiles.py",
                "enrichment_prepare.py",
                "enrichment_execution.py",
                "enrichment_service.py",
            )
        }
        | {"policy": dict(POLICY)}
    )


def preparation_profile(settings):
    if not settings.enrichment_enabled or not settings.enrichment_ocr_configuration:
        raise ValueError("Local enrichment engine identity is not configured")
    config = json.loads(settings.enrichment_ocr_configuration)
    identity = OCRIdentity.model_validate_json(json.dumps(config["identity"]))
    options = OCRSettings.model_validate_json(json.dumps(config["settings"]))
    if identity.settings_sha256 != options.identity_hash:
        raise ValueError("Invalid pinned OCR configuration")
    return PreparationProfile(
        native=native_identity(),
        ocr_identity=identity,
        ocr_settings=options,
        contracts=spatial_contract_identity(),
        rules_hash=preparation_rules(),
        max_pages=min(50, settings.extraction_max_pages),
        max_attempts=min(3, settings.extraction_max_attempts),
        max_calls=min(150, settings.extraction_max_calls),
        backoff_seconds=settings.extraction_backoff_seconds,
    )


def require_preparation(profile):
    if (
        profile.native != native_identity()
        or profile.contracts != spatial_contract_identity()
        or profile.rules_hash != preparation_rules()
    ):
        raise ValueError("Pinned preparation resources unavailable")
