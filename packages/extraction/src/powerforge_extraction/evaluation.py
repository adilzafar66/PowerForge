"""Versioned closed-corpus evaluation; no provider, ORM, commits or engineering inference."""

import hashlib
import json
from dataclasses import replace
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from powerforge_document_processing.storage import InMemoryObjectStorage
from powerforge_extraction.contracts import WorkUnitOutput
from powerforge_extraction.engineering_output import (
    MentionContext,
    RecognitionContext,
    convert_attributes,
    convert_equipment,
)
from powerforge_extraction.engineering_stages import engineering_manifest
from powerforge_extraction.grounding import (
    ArtifactSpec,
    PageSpec,
    grounding_identity,
    load_page_sources,
)
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.interpretation import interpretation_identity

EVALUATION_VERSION = "engineering-evaluation-v1"


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceFile(Label):
    role: Literal["native_text", "analysis_image"]
    path: str
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=1, le=2_000_000)
    width: int | None = None
    height: int | None = None


class ExpectedClaim(Label):
    id: str
    kind: Literal["EQUIPMENT_MENTION", "ATTRIBUTE_VALUE"]
    expression: str = Field(min_length=1, max_length=2000)
    role: Literal["native_text", "analysis_image"]
    span: list[int] | None = None
    precision: list[Literal["TEXT_OFFSETS", "TEXT_PAGE", "VISUAL_PAGE"]] = Field(min_length=1)
    status: Literal["MAPPED", "UNMAPPED", "INVALID"]
    equipment_type: str | None = None
    tag: str | None = None
    attribute_key: str | None = None
    value_type: Literal["NUMBER", "INTEGER", "TEXT", "ENUM", "BOOLEAN"] | None = None
    value: str | bool | None = None
    unit: str | None = None
    raw_value: str | None = None
    raw_unit: str | None = None
    equipment: str | None = None

    @model_validator(mode="after")
    def legal_annotation(self):
        if self.kind == "ATTRIBUTE_VALUE" and self.status == "MAPPED":
            from powerforge_engineering_model.registry import get_attribute_definition

            definition = get_attribute_definition(self.equipment_type, self.attribute_key)
            if (
                self.value_type != definition.value_type
                or self.unit != definition.canonical_unit
                or self.value is None
            ):
                raise ValueError("Gold annotation differs from registry metadata")
            if (self.value_type == "BOOLEAN") != isinstance(self.value, bool):
                raise ValueError("Gold booleans use booleans; other values use exact strings")
        elif (
            self.attribute_key is not None
            or self.value_type is not None
            or self.value is not None
            or self.unit is not None
        ):
            raise ValueError("Only mapped attribute gold has normalized fields")
        if self.span is not None and (len(self.span) != 2 or not 0 <= self.span[0] < self.span[1]):
            raise ValueError("Invalid independent source span")
        return self


class EvalCase(Label):
    id: str
    family: str
    note: str
    sources: list[SourceFile] = Field(min_length=1, max_length=2)
    expected: list[ExpectedClaim] = Field(max_length=200)

    @model_validator(mode="after")
    def references(self):
        roles = {item.role for item in self.sources}
        ids = {item.id for item in self.expected}
        if len(roles) != len(self.sources) or len(ids) != len(self.expected):
            raise ValueError("Duplicate source roles/gold claim IDs")
        for item in self.expected:
            if item.role not in roles:
                raise ValueError("Gold refers to absent source role")
            if item.equipment is not None and not any(
                e.id == item.equipment and e.kind == "EQUIPMENT_MENTION" and e.role == item.role
                for e in self.expected
            ):
                raise ValueError("Gold association must name a same-modality equipment claim")
        return self


class Corpus(Label):
    version: Literal["engineering-corpus-v1"]
    provenance: Literal["SYNTHETIC_AUTHORED"]
    cases: list[EvalCase] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({item.id for item in self.cases}) != len(self.cases):
            raise ValueError("Duplicate corpus case IDs")
        return self


def read_json(path: Path) -> dict:
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Evaluation JSON exceeds 4 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def source_bytes(root: Path, item: SourceFile) -> bytes:
    path = (root / item.path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Source must remain inside the approved corpus directory")
    if path.stat().st_size != item.size_bytes:
        raise ValueError("Corpus source size changed")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != item.sha256:
        raise ValueError("Corpus source hash changed")
    return data


def sources_for(case: EvalCase, root: Path):
    storage = InMemoryObjectStorage()
    uid = uuid5(NAMESPACE_URL, "powerforge-eval-v1/" + case.id)
    artifacts = []
    for item in case.sources:
        data = source_bytes(root, item)
        storage.put(
            item.path,
            BytesIO(data),
            len(data),
            "text/plain" if item.role == "native_text" else "image/png",
        )
        artifacts.append(
            ArtifactSpec(
                uuid5(uid, item.role),
                item.role,
                item.path,
                len(data),
                item.sha256,
                item.width,
                item.height,
            )
        )
    spec = PageSpec(
        uid,
        uuid5(uid, "recognition"),
        "EQUIPMENT_RECOGNITION:page:000001",
        "EQUIPMENT_RECOGNITION",
        uuid5(uid, "document"),
        uuid5(uid, "processing"),
        uuid5(uid, "page"),
        1,
        tuple(artifacts),
    )
    return load_page_sources(spec, storage)


def load_corpus(path: Path) -> tuple[Corpus, str]:
    corpus = Corpus.model_validate(read_json(path))
    for case in corpus.cases:
        sources = sources_for(case, path.parent)
        for gold in case.expected:
            if gold.role == "native_text":
                if gold.expression not in sources.text:
                    raise ValueError("Gold expression is absent from independently authored text")
                if gold.span is not None and sources.text[slice(*gold.span)] != gold.expression:
                    raise ValueError("Gold span disagrees with source bytes")
            elif gold.span is not None or gold.precision != ["VISUAL_PAGE"]:
                raise ValueError("Image gold must retain page-level grounding limits")
    return corpus, identity_hash(corpus.model_dump(mode="json"))


def resource_identity() -> dict:
    return {
        "manifest": identity_hash(engineering_manifest()),
        "interpretation": interpretation_identity(),
        "grounding": grounding_identity(),
    }


def evaluation_identity() -> str:
    root = files("powerforge_extraction")
    return identity_hash(
        {
            name: root.joinpath(name).read_text(encoding="utf-8")
            for name in ("evaluation.py", "evaluation_scoring.py", "eval.py")
        }
    )


def replay_context(sources, output: WorkUnitOutput) -> RecognitionContext:
    """Offline snapshot only. Live execution must use the committed-context DB loader."""
    evidence = {item.id: item for item in output.evidence}
    mentions = []
    for candidate in output.candidates:
        linked = [
            evidence[link.evidence_id]
            for link in output.candidate_evidence
            if link.candidate_id == candidate.id and link.role == "PRIMARY"
        ]
        first = linked[0]
        scope = candidate.diagnostics.get("source_scope")
        mentions.append(
            MentionContext(
                candidate.diagnostics["source_local_ref"],
                candidate.id,
                candidate.source_group_id,
                first.location.page_artifact_id,
                "native_text" if first.source_kind == "NATIVE_TEXT" else "analysis_image",
                candidate.raw_text,
                tuple(scope) if scope else None,
                candidate.observed_tag,
                tuple(item.id for item in linked),
            )
        )
    spec = sources.spec
    return RecognitionContext(
        spec.run_id,
        spec.document_id,
        spec.processing_run_id,
        spec.page_id,
        spec.unit_id,
        tuple(mentions),
    )


def replay(case: EvalCase, root: Path, recorded: dict):
    sources = sources_for(case, root)
    try:
        equipment = convert_equipment(recorded["equipment"], sources)
    except ValueError:
        return sources, [WorkUnitOutput()], ["EQUIPMENT_RECOGNITION_INVALID_RESPONSE"]
    attribute_sources = replace(
        sources,
        spec=replace(
            sources.spec,
            unit_id=uuid5(sources.spec.run_id, "attributes"),
            stage="ATTRIBUTE_EXTRACTION",
            unit_key="ATTRIBUTE_EXTRACTION:page:000001",
        ),
    )
    try:
        attributes = convert_attributes(
            recorded["attributes"], attribute_sources, replay_context(sources, equipment)
        )
    except ValueError:
        return sources, [equipment], ["ATTRIBUTE_EXTRACTION_INVALID_RESPONSE"]
    return sources, [equipment, attributes], []
