"""Offline stage definitions and resource identities. Not registered for worker execution yet."""

from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel

from powerforge_engineering_model.registry_v1 import REGISTRY
from powerforge_extraction.identities import canonical_json, content_hash, identity_hash
from powerforge_extraction.observations import (
    ATTRIBUTE_SCHEMA_VERSION,
    EQUIPMENT_SCHEMA_VERSION,
    AttributeExtractionResponse,
    EquipmentRecognitionResponse,
    ObservationResponse,
)
from powerforge_extraction.registry_context import (
    CONTEXT_VERSION,
    attribute_context,
    equipment_catalog,
    registry_projection_hash,
)
from powerforge_extraction.terminology import (
    TERMINOLOGY_VERSION,
    terminology_hash,
    terminology_policy,
)

STAGE_MANIFEST_VERSION = "engineering-stage-manifest-v1"
PROMPT_VERSION = "engineering-prompts-v1"
MAX_INSTRUCTION_BYTES = 128 * 1024
StageKey = Literal["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"]


def _prompt(name: str) -> str:
    return files("powerforge_extraction").joinpath(f"prompts/{name}").read_text(encoding="utf-8")


@dataclass(frozen=True)
class RenderedInstructions:
    text: str
    context_hash: str

    @property
    def instruction_hash(self) -> str:
        return content_hash(self.text)


@dataclass(frozen=True)
class EngineeringStage:
    key: StageKey
    schema_version: str
    response_model: type[ObservationResponse]
    prompt_resource: str
    prerequisite: StageKey | None

    @property
    def template(self) -> str:
        return _prompt("engineering_common_v1.txt") + "\n" + _prompt(self.prompt_resource)

    @property
    def template_hash(self) -> str:
        return content_hash(self.template)

    @property
    def schema_hash(self) -> str:
        return identity_hash(self.response_model.model_json_schema())

    def identity(self) -> dict:
        return {
            "stage": self.key,
            "prerequisite": self.prerequisite,
            "prompt_version": PROMPT_VERSION,
            "template_hash": self.template_hash,
            "schema_version": self.schema_version,
            "schema_hash": self.schema_hash,
        }

    def render_instructions(self, equipment_types: Iterable[str] = ()) -> RenderedInstructions:
        selected = tuple(sorted(set(equipment_types)))
        if self.key == "EQUIPMENT_RECOGNITION":
            if selected:
                raise ValueError("Recognition always uses the complete equipment catalog")
            registry = equipment_catalog()
        else:
            registry = attribute_context(selected)
        policy = terminology_policy()
        policy["entries"] = [
            entry
            for entry in policy["entries"]
            if (
                entry["kind"] == "EQUIPMENT_NAME"
                if self.key == "EQUIPMENT_RECOGNITION"
                else entry["kind"] != "EQUIPMENT_NAME" and entry["equipment_type"] in selected
            )
        ]
        context = {"registry": registry, "terminology": policy}
        text = self.template + "\nApproved registry metadata and qualified terminology:\n"
        text += canonical_json(context) + "\n"
        if len(text.encode()) > MAX_INSTRUCTION_BYTES:
            raise ValueError("Rendered stage instructions exceed their versioned input bound")
        # Source bytes and upstream observations belong in separate untrusted request input.
        return RenderedInstructions(text, identity_hash(context))

    def validate_result(
        self,
        payload: object,
        *,
        available_sources: Iterable[str],
        equipment_refs: Iterable[str] = (),
    ) -> ObservationResponse:
        """Validate response shape/references, without claiming semantic or source verification."""
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        result = self.response_model.model_validate(payload)
        sources, equipment = set(available_sources), set(equipment_refs)
        if not sources <= {"native_text", "analysis_image"}:
            raise ValueError("Unsupported supplied source role")
        observations = (
            result.equipment
            if isinstance(result, EquipmentRecognitionResponse)
            else result.attributes
        )
        for observation in observations:
            if any(anchor.source_ref not in sources for anchor in observation.anchors):
                raise ValueError("Observation references an unavailable source")
            if (
                isinstance(result, AttributeExtractionResponse)
                and observation.equipment_ref is not None
                and observation.equipment_ref not in equipment
            ):
                raise ValueError("Attribute references unavailable equipment context")
        return result


STAGES = (
    EngineeringStage(
        "EQUIPMENT_RECOGNITION",
        EQUIPMENT_SCHEMA_VERSION,
        EquipmentRecognitionResponse,
        "equipment_recognition_v1.txt",
        None,
    ),
    EngineeringStage(
        "ATTRIBUTE_EXTRACTION",
        ATTRIBUTE_SCHEMA_VERSION,
        AttributeExtractionResponse,
        "attribute_extraction_v1.txt",
        "EQUIPMENT_RECOGNITION",
    ),
)


def get_engineering_stage(key: str, version: str = STAGE_MANIFEST_VERSION) -> EngineeringStage:
    if version == STAGE_MANIFEST_VERSION:
        for stage in STAGES:
            if stage.key == key:
                return stage
    raise ValueError("Unsupported engineering stage/version")


def engineering_manifest() -> dict:
    """Small hash-only identity for future profile pinning, not a production profile itself."""
    return {
        "version": STAGE_MANIFEST_VERSION,
        "registry_version": REGISTRY.registry_version,
        "context_version": CONTEXT_VERSION,
        "registry_projection_hash": registry_projection_hash(),
        "terminology_version": TERMINOLOGY_VERSION,
        "terminology_hash": terminology_hash(),
        "stages": [stage.identity() for stage in STAGES],
    }
