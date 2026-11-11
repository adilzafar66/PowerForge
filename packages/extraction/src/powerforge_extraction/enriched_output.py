"""Source-aware prose adapter using the frozen conservative engineering interpreter."""

import re

from powerforge_engineering_model.registry import list_equipment_definitions
from powerforge_engineering_model.units import UNITS
from powerforge_extraction.contracts import CandidateEvidenceInput, CandidateInput, SourceGroupInput
from powerforge_extraction.enriched_contracts import EnrichedOutput
from powerforge_extraction.enriched_grounding import (
    ground,
    identifier,
    line_groups,
    render,
    semantic_observation,
    table_readings,
)
from powerforge_extraction.interpretation import (
    InterpretationContext,
    interpret_attribute,
    interpret_equipment,
)
from powerforge_extraction.observations import AttributeObservation, EquipmentObservation
from powerforge_extraction.stage_diagnostics import SourceRejection
from powerforge_extraction.terminology import TERMINOLOGY


class Output:
    def __init__(self, sources):
        self.sources = sources
        self.evidence, self.groups, self.candidates, self.links, self.counts = {}, [], [], [], {}
        self.existing_evidence = set()

    def count(self, name):
        self.counts[name] = self.counts.get(name, 0) + 1

    def cite(self, candidate, primary, supporting=()):
        seen = set()
        for role, items in (("PRIMARY", primary), ("SUPPORTING", supporting)):
            for evidence in items:
                if evidence.id in seen:
                    continue
                if evidence.id not in self.existing_evidence:
                    self.evidence[evidence.id] = evidence
                self.links.append(
                    CandidateEvidenceInput(
                        candidate_id=candidate.id,
                        evidence_id=evidence.id,
                        role=role,
                        position=len(seen),
                    )
                )
                seen.add(evidence.id)

    def result(self, **extra):
        return EnrichedOutput(
            evidence=list(self.evidence.values()),
            source_groups=self.groups,
            candidates=self.candidates,
            candidate_evidence=self.links,
            diagnostic_counts=self.counts,
            **extra,
        )


def candidate(
    sources, ref, result, primary, *, equipment=False, group=None, mention=None, diagnostics=None
):
    fields = {}
    if result.value_type is not None:
        key = {
            "NUMBER": "numeric_value",
            "INTEGER": "integer_value",
            "TEXT": "text_value",
            "ENUM": "text_value",
            "BOOLEAN": "boolean_value",
        }[result.value_type]
        fields[key] = result.value
    return CandidateInput(
        id=identifier(sources, "candidate", ref),
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
        source_group_id=group,
        equipment_mention_candidate_id=mention,
        diagnostics=dict(
            source_contract="enriched-grounding-v1",
            source_local_ref=ref,
            reading_bases=sorted({e.location.reading_basis for e in primary}),
            representation_text_matched=bool(primary)
            and all(e.text_start is not None for e in primary),
            text_verified=False,
            printed_text_independently_verified=False,
            grounding_precision="TEXT_OFFSETS"
            if primary and all(e.text_start is not None for e in primary)
            else "VISUAL_PAGE",
            recognition_limit="SOURCE_READING_NOT_INDEPENDENTLY_VERIFIED",
            **(diagnostics or {}),
        ),
        **fields,
    )


def _known_field(line):
    from powerforge_extraction.grounding import rating_line

    if rating_line(line):
        return True
    label, separator, _ = line.partition(":")
    if not separator:
        return False

    def fold(value):
        parenthesis = re.search(r"\s*\(([^()]*)\)\s*$", value)
        if parenthesis and parenthesis[1].strip() in UNITS:
            value = value[: parenthesis.start()]
        return " ".join(re.findall(r"[^\W_]+", value.casefold()))

    labels = {fold(d.display_name) for e in list_equipment_definitions() for d in e.attributes}
    labels.update(
        fold(name)
        for entry in TERMINOLOGY
        if entry.kind == "ATTRIBUTE_LABEL"
        for name in entry.expressions
    )
    return fold(label) in labels


def scope_for(sources, admitted, peers):
    if (
        admitted.visual
        or admitted.uncertain
        or not admitted.readings
        or any(not r.box for r in admitted.readings)
    ):
        return ()
    lines = line_groups(sources)
    owned = table_readings(sources)
    if any(
        key[0] == admitted.line[0] and not any(r.box for r in row) for key, row in lines.items()
    ):
        return ()  # A missing position can hide a competing header in this representation.
    rows = [(key, row) for key, row in lines.items() if any(r.box for r in row)]
    rows.sort(
        key=lambda item: (
            min(r.box[1] for r in item[1] if r.box),
            min(r.box[0] for r in item[1] if r.box),
        )
    )
    index = next((i for i, (key, _) in enumerate(rows) if key == admitted.line), None)
    if index is None:
        return ()
    header = rows[index][1]
    left = min(r.box[0] for r in header)
    bottom = max(r.box[3] for r in header)
    height = max(r.box[3] - r.box[1] for r in header)
    result = []
    for key, row in rows[index + 1 :]:
        if any(
            not r.box or not r.horizontal or r.model.issues or r.model.ref in owned for r in row
        ):
            break
        top = min(r.box[1] for r in row)
        start = min(r.box[0] for r in row)
        if top < bottom or top - bottom > 4 * height or abs(start - left) > height / 2:
            break
        if key in peers or not _known_field(render(row)):
            break  # Includes missed TAG: Equipment Type and unknown competing headers.
        result.extend(r.model.ref for r in row)
        bottom = max(r.box[3] for r in row)
    return tuple(result)


def convert_equipment(response, sources, *, trace=None):
    output = Output(sources)
    admitted = {}
    owned = table_readings(sources)
    for obs in response.equipment:
        if trace:
            trace.phase = "GROUNDING"
        try:
            item = ground(sources, obs)
        except ValueError as exc:
            if trace:
                reason = exc.reason if isinstance(exc, SourceRejection) else "GROUNDING_REJECTED"
                trace.observe("GROUNDING_REJECTED", obs, reason=reason)
            output.count("rejected_ungrounded")
            continue
        if trace:
            trace.observe("GROUNDING_ADMITTED", obs)
        if (
            any(r.model.ref in owned for r in item.readings)
            or item.visual
            and sources.layout.tables
        ):
            if trace:
                trace.observe("SOURCE_SCOPE_REJECTED", obs, reason="TABLE_OWNED_SOURCE")
            output.count("rejected_source_fields")
            continue
        admitted[obs.local_ref] = item
    peers = {g.line for g in admitted.values() if g.line is not None}
    for obs in response.equipment:
        item = admitted.get(obs.local_ref)
        if item is None:
            continue
        if trace:
            trace.phase = "INTERPRETATION"
        local = semantic_observation(obs, EquipmentObservation)
        # Original expression owns its tag/name before complete line qualification.
        own = interpret_equipment(
            local, InterpretationContext(obs.raw_expression, source_kind="VISUAL_PAGE")
        )
        if own.rejected:
            if trace:
                trace.observe("INTERPRETATION_REJECTED", obs, reason=own.reason_code)
            output.count("rejected_source_fields")
            continue
        if trace:
            trace.phase = "INTERPRETATION"
        local = semantic_observation(
            obs,
            EquipmentObservation,
            raw_expression=item.statement,
            ambiguous=item.uncertain,
            ambiguity_reason="Uncertain source reading" if item.uncertain else None,
        )
        result = interpret_equipment(
            local, InterpretationContext(item.statement, source_kind="VISUAL_PAGE")
        )
        if result.rejected:
            if trace:
                trace.observe("INTERPRETATION_REJECTED", obs, reason=result.reason_code)
            output.count("rejected_source_fields")
            continue
        if trace:
            trace.phase = "CONVERSION"
        group_id = identifier(sources, "group", obs.local_ref)
        scope = scope_for(sources, item, peers)
        c = candidate(
            sources,
            obs.local_ref,
            result,
            item.evidence,
            equipment=True,
            group=group_id,
            diagnostics=dict(
                observation=obs.model_dump(mode="json"),
                scope_readings=list(scope),
                line_readings=[r.model.ref for r in item.readings],
            ),
        )
        if trace:
            trace.observe(
                c.mapping_status,
                obs,
                reason=c.reason_code,
                candidate=c,
                association=c.diagnostics.get("association"),
            )
        output.candidates.append(c)
        output.groups.append(
            SourceGroupInput(
                id=group_id,
                local_key=f"enriched/{sources.unit_key}/{obs.local_ref}",
                equipment_type_hint=result.equipment_type_key,
                tag_text=result.observed_tag,
                evidence_ids=[e.id for e in item.evidence],
            )
        )
        output.cite(c, item.evidence)
    if trace:
        trace.phase = "CONVERSION"
    return output.result()


def convert_attributes(response, sources, context, *, trace=None):
    output = Output(sources)
    output.existing_evidence = {e.id for e in context.evidence}
    mentions = {c.diagnostics["source_local_ref"]: c for c in context.candidates}
    owned = table_readings(sources)
    for obs in response.attributes:
        if trace:
            trace.phase = "GROUNDING"
        try:
            item = ground(sources, obs)
        except ValueError as exc:
            if trace:
                reason = exc.reason if isinstance(exc, SourceRejection) else "GROUNDING_REJECTED"
                trace.observe("GROUNDING_REJECTED", obs, reason=reason)
            output.count("rejected_ungrounded")
            continue
        if trace:
            trace.observe("GROUNDING_ADMITTED", obs)
        if (
            any(r.model.ref in owned for r in item.readings)
            or item.visual
            and sources.layout.tables
        ):
            if trace:
                trace.observe("SOURCE_SCOPE_REJECTED", obs, reason="TABLE_OWNED_SOURCE")
            output.count("rejected_source_fields")
            continue
        mention = mentions.get(obs.equipment_ref)
        if obs.equipment_ref and mention is None:
            raise SourceRejection(
                "UNAVAILABLE_EQUIPMENT_ALIAS",
                "Attribute references unavailable committed equipment",
            )
        if mention:
            selected = {r.model.ref for r in item.readings}
            visual = (
                item.visual
                and len(mentions) == 1
                and "VISUAL_REPORTED" in mention.diagnostics["reading_bases"]
            )
            positioned = bool(selected) and selected <= set(mention.diagnostics["scope_readings"])
            if not (visual or positioned):
                mention = None
        if obs.equipment_ref and mention is None:
            if trace:
                trace.observe("DETACHED_ASSOCIATIONS", obs, reason="OUTSIDE_EQUIPMENT_SCOPE")
            output.count("detached_associations")
        if trace:
            trace.phase = "INTERPRETATION"
        local = semantic_observation(
            obs,
            AttributeObservation,
            ambiguous=item.uncertain,
            ambiguity_reason="Uncertain source reading" if item.uncertain else None,
        )
        result = interpret_attribute(
            local,
            InterpretationContext(
                item.statement, mention.raw_text if mention else None, "VISUAL_PAGE"
            ),
        )
        if result.rejected:
            if trace:
                trace.observe("INTERPRETATION_REJECTED", obs, reason=result.reason_code)
            output.count("rejected_source_fields")
            continue
        if trace:
            trace.phase = "CONVERSION"
        c = candidate(
            sources,
            obs.local_ref,
            result,
            item.evidence,
            group=mention.source_group_id if mention else None,
            mention=mention.id if mention else None,
            diagnostics=dict(
                observation=obs.model_dump(mode="json"),
                association="SOURCE_GEOMETRY_BLOCK"
                if mention and not item.visual
                else "VISUAL_REPORTED"
                if mention
                else "NONE",
            ),
        )
        if trace:
            trace.observe(
                c.mapping_status,
                obs,
                reason=c.reason_code,
                candidate=c,
                association=c.diagnostics.get("association"),
            )
        output.candidates.append(c)
        supporting = [
            e
            for e in context.evidence
            if mention
            and any(
                link.candidate_id == mention.id and link.evidence_id == e.id
                for link in context.candidate_evidence
            )
        ]
        output.cite(c, item.evidence, supporting)
    if trace:
        trace.phase = "CONVERSION"
    return output.result()
