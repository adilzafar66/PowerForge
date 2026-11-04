"""Grounded observations to 6A output; no scheduling, ORM, provider calls or commits."""

import re
from dataclasses import dataclass
from uuid import UUID, uuid5

from powerforge_engineering_model.registry import list_equipment_definitions
from powerforge_engineering_model.units import UNITS
from powerforge_extraction.contracts import (
    CandidateEvidenceInput,
    CandidateInput,
    EvidenceInput,
    SourceGroupInput,
    WorkUnitOutput,
)
from powerforge_extraction.engineering_stages import get_engineering_stage
from powerforge_extraction.grounding import (
    GROUNDING_VERSION,
    GroundedObservation,
    PageSources,
    ground_observation,
    line_span,
    paragraph_span,
    rating_line,
)
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.interpretation import (
    Interpretation,
    InterpretationContext,
    interpret_attribute,
    interpret_equipment,
)
from powerforge_extraction.observations import (
    AttributeExtractionResponse,
    EquipmentRecognitionResponse,
)
from powerforge_extraction.terminology import TERMINOLOGY


def _source_block(
    sources: PageSources, admitted: GroundedObservation, grounded: dict
) -> tuple[int, int] | None:
    header = line_span(sources.text, *admitted.own_span)
    paragraph = paragraph_span(sources.text, *admitted.own_span)
    header_text = sources.text[slice(*header)]
    if header[0] != paragraph[0] or "\n" in header_text or len(header_text) > 2000:
        return None
    block = sources.text[slice(*paragraph)]
    peers = [
        item
        for item in grounded.values()
        if item
        and item.role == "native_text"
        and (
            (item.own_span is not None and paragraph[0] <= item.own_span[0] < paragraph[1])
            or (item.own_span is None and item.statement in block)
        )
    ]
    if len(peers) != 1:
        return None

    def words(value: str) -> str:
        return " ".join(re.findall(r"[^\W_]+", value.casefold()))

    def attribute_label(value: str) -> str:
        value = value.strip()
        parenthesis = re.search(r"\s*\(([^()]*)\)\s*$", value)
        if parenthesis and parenthesis[1].strip() in UNITS:
            value = value[: parenthesis.start()].strip()
        else:
            for unit in sorted(UNITS, key=len, reverse=True):
                if value.endswith(" " + unit):
                    value = value[: -len(unit)].strip()
                    break
        return words(value)

    definitions = list_equipment_definitions()
    type_names = {words(name) for item in definitions for name in (item.key, item.display_name)}
    type_names.update(
        words(name)
        for entry in TERMINOLOGY
        if entry.kind == "EQUIPMENT_NAME"
        for name in entry.expressions
    )
    attribute_labels = {
        attribute_label(name)
        for item in definitions
        for definition in item.attributes
        for name in (definition.key, definition.display_name)
    }
    attribute_labels.update(
        attribute_label(name)
        for entry in TERMINOLOGY
        if entry.kind == "ATTRIBUTE_LABEL"
        for name in entry.expressions
    )
    for line in block.splitlines()[1:]:
        if rating_line(line):
            continue
        label, separator, _ = line.partition(":")
        # A colon alone cannot distinguish a field from a missed TAG: Type header.
        # Unknown labels disable association while their observations remain retainable.
        if (
            not separator
            or words(label) in type_names
            or attribute_label(label) not in attribute_labels
        ):
            return None
    return paragraph


@dataclass(frozen=True)
class MentionContext:
    local_ref: str
    candidate_id: UUID
    group_id: UUID | None
    artifact_id: UUID
    role: str
    header: str
    scope: tuple[int, int] | None
    tag: str | None
    evidence_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class RecognitionContext:
    run_id: UUID
    document_id: UUID
    processing_run_id: UUID
    page_id: UUID
    unit_id: UUID
    mentions: tuple[MentionContext, ...]


class _Output:
    def __init__(self, sources: PageSources):
        self.sources = sources
        self.evidence: dict[UUID, EvidenceInput] = {}
        self.candidates, self.groups, self.links = [], [], []
        self.counts = {}

    def count(self, code: str) -> None:
        self.counts[code] = self.counts.get(code, 0) + 1

    def identifier(self, kind: str, reference: str) -> UUID:
        return uuid5(self.sources.spec.run_id, f"{self.sources.spec.unit_key}/{kind}/{reference}")

    def cite(self, candidate: CandidateInput, grounded: GroundedObservation) -> tuple[UUID, ...]:
        ids = []
        for item in grounded.evidence:
            key = identity_hash(item.model_dump(mode="json", exclude={"id"}))
            uid = self.identifier("evidence", key)
            self.evidence[uid] = item.model_copy(update={"id": uid})
            if uid not in ids:
                self.links.append(
                    CandidateEvidenceInput(
                        candidate_id=candidate.id, evidence_id=uid, position=len(ids)
                    )
                )
                ids.append(uid)
        return tuple(ids)

    def result(self) -> WorkUnitOutput:
        return WorkUnitOutput(
            evidence=list(self.evidence.values()),
            candidates=self.candidates,
            source_groups=self.groups,
            candidate_evidence=self.links,
            diagnostic_counts=self.counts,
        )


def _candidate(
    output: _Output,
    ref: str,
    result: Interpretation,
    grounded: GroundedObservation,
    *,
    equipment: bool,
    group_id: UUID | None = None,
    mention_id: UUID | None = None,
) -> CandidateInput:
    fields = {}
    if result.value_type is not None:
        slot = {
            "NUMBER": "numeric_value",
            "INTEGER": "integer_value",
            "TEXT": "text_value",
            "ENUM": "text_value",
            "BOOLEAN": "boolean_value",
        }[result.value_type]
        fields[slot] = result.value
    return CandidateInput(
        id=output.identifier("candidate", ref),
        kind="EQUIPMENT_MENTION" if equipment else "ATTRIBUTE_VALUE",
        mapping_status=result.mapping_status,
        raw_text=result.raw_text,
        raw_value=result.raw_value,
        raw_unit=result.raw_unit,
        observed_tag=result.observed_tag,
        equipment_type_key=result.equipment_type_key,
        attribute_key=result.attribute_key,
        value_type=result.value_type,
        unit=result.unit,
        reason_code=result.reason_code,
        source_group_id=group_id,
        equipment_mention_candidate_id=mention_id,
        diagnostics={
            "grounding_version": GROUNDING_VERSION,
            "source_local_ref": ref,
            "grounding_precision": grounded.precision,
            "text_verified": grounded.role == "native_text",
        },
        **fields,
    )


def convert_equipment(
    response: EquipmentRecognitionResponse, sources: PageSources
) -> WorkUnitOutput:
    if sources.spec.stage != "EQUIPMENT_RECOGNITION":
        raise ValueError("Equipment output requires its planned stage")
    response = get_engineering_stage(sources.spec.stage).validate_result(
        response,
        available_sources=[item.role for item in sources.spec.artifacts],
    )
    output = _Output(sources)
    grounded = {item.local_ref: ground_observation(item, sources) for item in response.equipment}
    for observation in response.equipment:
        admitted = grounded[observation.local_ref]
        if admitted is None:
            output.count("rejected_ungrounded")
            continue
        context = InterpretationContext(
            admitted.statement,
            source_kind="NATIVE_TEXT" if admitted.role == "native_text" else "VISUAL_PAGE",
        )
        # Full-line context must not lend a tag/name to a narrower model expression.
        if interpret_equipment(observation, context).rejected:
            output.count("rejected_source_fields")
            continue
        local = observation.model_copy(update={"raw_expression": admitted.statement})
        if admitted.role == "native_text" and admitted.own_span is None:
            local = local.model_copy(
                update={"ambiguous": True, "ambiguity_reason": "Source occurrence is ambiguous"}
            )
        result = interpret_equipment(local, context)
        if result.rejected:
            output.count("rejected_source_fields")
            continue
        scope, group_id = None, None
        if admitted.role == "analysis_image" or admitted.own_span is not None:
            group_id = output.identifier("group", observation.local_ref)
            if admitted.own_span is not None:
                scope = _source_block(sources, admitted, grounded)
        candidate = _candidate(
            output, observation.local_ref, result, admitted, equipment=True, group_id=group_id
        )
        evidence_ids = output.cite(candidate, admitted)
        if group_id is not None:
            candidate = candidate.model_copy(
                update={
                    "diagnostics": {
                        **candidate.diagnostics,
                        "source_scope": list(scope) if scope else None,
                    }
                }
            )
            output.groups.append(
                SourceGroupInput(
                    id=group_id,
                    local_key=f"page:{sources.spec.page_id}:"
                    + identity_hash(
                        {
                            "unit": sources.spec.unit_key,
                            "artifact": str(admitted.artifact_id),
                            "ref": observation.local_ref,
                        }
                    ),
                    equipment_type_hint=result.equipment_type_key,
                    tag_text=result.observed_tag,
                    label=(result.observed_name or result.raw_text)[:500],
                    evidence_ids=list(evidence_ids),
                )
            )
        output.candidates.append(candidate)
    return output.result()


def _association(
    reference: str | None,
    admitted: GroundedObservation,
    context: RecognitionContext | None,
    observation_text: str,
) -> MentionContext | None:
    if reference is None or context is None:
        return None
    selected = next((item for item in context.mentions if item.local_ref == reference), None)
    if (
        selected is None
        or selected.group_id is None
        or selected.role != admitted.role
        or selected.artifact_id != admitted.artifact_id
    ):
        return None
    if admitted.role == "native_text":
        if (
            admitted.own_span is not None
            and selected.scope is not None
            and (
                selected.scope[0] <= admitted.own_span[0]
                and admitted.own_span[1] <= selected.scope[1]
            )
        ):
            return selected
        return None
    peers = [
        item
        for item in context.mentions
        if item.role == "analysis_image" and item.artifact_id == admitted.artifact_id
    ]
    if len(peers) == 1:
        return selected  # Model-reported single-item visual association, never text-verified.
    if (
        selected.tag
        and re.search(r"(?<![\w/-])" + re.escape(selected.tag) + r"(?![\w/-])", observation_text)
        and sum(item.tag == selected.tag for item in peers) == 1
    ):
        return selected
    return None


def convert_attributes(
    response: AttributeExtractionResponse,
    sources: PageSources,
    context: RecognitionContext | None = None,
) -> WorkUnitOutput:
    if sources.spec.stage != "ATTRIBUTE_EXTRACTION":
        raise ValueError("Attribute output requires its planned stage")
    if context is not None and (
        (context.run_id, context.document_id, context.processing_run_id, context.page_id)
        != (
            sources.spec.run_id,
            sources.spec.document_id,
            sources.spec.processing_run_id,
            sources.spec.page_id,
        )
        or context.unit_id == sources.spec.unit_id
    ):
        raise ValueError("Recognition context is outside target unit ownership")
    response = get_engineering_stage(sources.spec.stage).validate_result(
        response,
        available_sources=[item.role for item in sources.spec.artifacts],
        equipment_refs=[item.local_ref for item in context.mentions] if context else (),
    )
    output = _Output(sources)
    for observation in response.attributes:
        admitted = ground_observation(observation, sources)
        if admitted is None:
            output.count("rejected_ungrounded")
            continue
        association = _association(
            observation.equipment_ref, admitted, context, observation.raw_expression
        )
        detached = observation.equipment_ref is not None and association is None
        changes = {"equipment_ref": None} if detached else {}
        if admitted.role == "native_text" and admitted.own_span is None:
            # Retain the repeated expression without borrowing a label/group
            # from one arbitrarily selected occurrence.
            changes.update(
                source_label=None,
                proposed_attribute_key=None,
                proposed_equipment_type=None,
                ambiguous=True,
                ambiguity_reason="Source occurrence is ambiguous",
            )
        local = observation.model_copy(update=changes)
        result = interpret_attribute(
            local,
            InterpretationContext(
                admitted.statement,
                association.header if association else None,
                "NATIVE_TEXT" if admitted.role == "native_text" else "VISUAL_PAGE",
            ),
        )
        fragment_only = False
        if result.rejected and admitted.role == "native_text" and admitted.own_span is not None:
            # A verified fragment may be meaningful even when the complete line has
            # unresolved qualifiers or several fields. Preserve it only as UNMAPPED,
            # without borrowing an equipment association or hiding the full-line evidence.
            uncertain = observation.model_copy(
                update={
                    "equipment_ref": None,
                    "ambiguous": True,
                    "ambiguity_reason": "Complete source line does not establish a clear field",
                }
            )
            fallback = interpret_attribute(
                uncertain, InterpretationContext(observation.raw_expression)
            )
            if not fallback.rejected:
                result, association, fragment_only = fallback, None, True
                detached = observation.equipment_ref is not None
        if result.rejected:
            output.count("rejected_source_fields")
            continue
        if detached:
            output.count("detached_associations")
        candidate = _candidate(
            output,
            observation.local_ref,
            result,
            admitted,
            equipment=False,
            group_id=association.group_id if association else None,
            mention_id=association.candidate_id if association else None,
        )
        candidate = candidate.model_copy(
            update={
                "diagnostics": {
                    **candidate.diagnostics,
                    "fragment_only": fragment_only,
                    "association": (
                        "VISUAL_REPORTED" if admitted.role == "analysis_image" else "SOURCE_BLOCK"
                    )
                    if association
                    else "NONE",
                }
            }
        )
        output.candidates.append(candidate)
        own_ids = output.cite(candidate, admitted)
        if association:
            for uid in association.evidence_ids:
                if uid not in own_ids:
                    output.links.append(
                        CandidateEvidenceInput(
                            candidate_id=candidate.id,
                            evidence_id=uid,
                            role="SUPPORTING",
                            position=len(output.links),
                        )
                    )
    return output.result()
