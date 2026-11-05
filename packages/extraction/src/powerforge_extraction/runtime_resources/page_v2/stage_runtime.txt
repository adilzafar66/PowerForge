"""Explicit versioned page-stage rendering and safe immutable upstream projection."""

from dataclasses import dataclass
from importlib.resources import files
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from powerforge_extraction.dependencies import prerequisite
from powerforge_extraction.engineering_stages import engineering_manifest, get_engineering_stage
from powerforge_extraction.grounding import grounding_identity
from powerforge_extraction.identities import canonical_json, content_hash, identity_hash
from powerforge_extraction.interpretation import interpretation_identity
from powerforge_extraction.models import ExtractionCandidate, ExtractionWorkUnit
from powerforge_extraction.profiles import EngineeringProfile

RUNTIME_VERSION = "engineering-page-runtime-v1"


def runtime_identity(version: str = RUNTIME_VERSION) -> dict:
    resources = files("powerforge_extraction")
    if version not in {RUNTIME_VERSION, "engineering-page-runtime-v2"}:
        raise ValueError("Pinned engineering runtime is unavailable")
    names = [
        "stage_runtime.py",
        "dependencies.py",
        "profiles.py",
        "orchestration.py",
        "execution.py",
    ]
    if version == "engineering-page-runtime-v2":
        names += ["production_profiles.py", "prompts/openai_input_v1.json"]

    def resource(name: str) -> str:
        # M4 rendering/claim/publication algorithms remain shared and unchanged.
        # Retain the two pre-registration identity/reader sources byte-for-byte.
        if version == RUNTIME_VERSION and name in {"profiles.py", "stage_runtime.py"}:
            return "runtime_resources/page_v1/" + name.removesuffix(".py") + ".txt"
        return name

    return {
        "version": version,
        "rules_hash": identity_hash(
            {
                name: content_hash(resources.joinpath(resource(name)).read_text(encoding="utf-8"))
                for name in names
            }
        ),
    }


def require_supported(profile: EngineeringProfile) -> None:
    manifest = engineering_manifest()
    if (
        profile.manifest != manifest
        or profile.prompt_version != "engineering-prompts-v1"
        or profile.schema_version != manifest["version"]
        or profile.prompt_hash != identity_hash(manifest)
        or profile.schema_hash != identity_hash(manifest)
        or profile.interpretation != interpretation_identity()
        or profile.grounding != grounding_identity()
        or profile.runtime != runtime_identity(profile.runtime.get("version"))
    ):
        raise ValueError("Pinned engineering resources are unavailable")
    if profile.version == "execution-profile-v3":
        from powerforge_extraction.production_profiles import require_production_supported

        require_production_supported(profile)


def planned_metadata(profile: EngineeringProfile, stage: str, number: int) -> dict:
    identity = next(item for item in profile.manifest["stages"] if item["stage"] == stage)
    return {
        "prerequisite_key": prerequisite(stage, number),
        "stage_manifest_version": profile.manifest["version"],
        "stage_identity": identity,
    }


def validate_plan(unit: ExtractionWorkUnit, profile: EngineeringProfile) -> None:
    if (
        unit.stage not in profile.stages
        or len(unit.page_numbers) != 1
        or unit.execution_metadata != planned_metadata(profile, unit.stage, unit.page_numbers[0])
    ):
        raise ValueError("Work unit differs from its pinned page-stage plan")


def successful_prerequisite(
    session: Session, unit: ExtractionWorkUnit
) -> ExtractionWorkUnit | None:
    key = unit.execution_metadata.get("prerequisite_key")
    if key is None:
        return None
    return session.scalar(
        select(ExtractionWorkUnit).where(
            ExtractionWorkUnit.run_id == unit.run_id,
            ExtractionWorkUnit.unit_key == key,
            ExtractionWorkUnit.stage == "EQUIPMENT_RECOGNITION",
            ExtractionWorkUnit.page_numbers == unit.page_numbers,
            ExtractionWorkUnit.status == "COMPLETED",
        )
    )


@dataclass(frozen=True)
class StageCall:
    response_model: type[BaseModel]
    schema_version: str
    instructions: str
    upstream_context: str | None
    upstream_unit_id: UUID | None

    @property
    def instruction_hash(self) -> str:
        return content_hash(self.instructions)

    def correlation_id(self, unit_id: UUID) -> str:
        if self.upstream_unit_id is None:
            return str(unit_id)
        return (
            f"{unit_id}/upstream:{self.upstream_unit_id}"
            f"/context:{content_hash(self.upstream_context)}"
        )


def stage_call(
    session: Session, unit: ExtractionWorkUnit, profile: EngineeringProfile
) -> StageCall:
    validate_plan(unit, profile)
    stage = get_engineering_stage(unit.stage, profile.manifest["version"])
    parent = successful_prerequisite(session, unit)
    selected, upstream = set(), None
    if unit.execution_metadata.get("prerequisite_key"):
        if parent is None:
            raise ValueError("Committed recognition context is required")
        candidates = list(
            session.scalars(
                select(ExtractionCandidate).where(ExtractionCandidate.work_unit_id == parent.id)
            )
        )
        if len(candidates) > 32:
            raise ValueError("Recognition context exceeds its bound")
        items = []
        for candidate in candidates:
            if candidate.kind != "EQUIPMENT_MENTION":
                raise ValueError("Unexpected recognition candidate kind")
            if candidate.equipment_type_key is not None:
                selected.add(candidate.equipment_type_key)
            items.append(
                {
                    "local_ref": candidate.diagnostics["source_local_ref"],
                    "raw_expression": candidate.raw_text,
                    "observed_tag": candidate.observed_tag,
                    "equipment_type": candidate.equipment_type_key,
                    "mapping_status": candidate.mapping_status,
                    "grounding_precision": candidate.diagnostics["grounding_precision"],
                }
            )
        upstream = canonical_json({"equipment": sorted(items, key=lambda item: item["local_ref"])})
        if len(upstream.encode()) > profile.max_upstream_bytes:
            raise ValueError("Recognition context exceeds the pinned input bound")
    instructions = stage.render_instructions(selected).text
    if len(instructions.encode()) > profile.max_instruction_bytes:
        raise ValueError("Instructions exceed the pinned input bound")
    return StageCall(
        stage.response_model,
        stage.schema_version,
        instructions,
        upstream,
        parent.id if parent else None,
    )
