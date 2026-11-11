"""Successor interpretation. Ground source facts first, then consider proposed meanings."""

import re
from dataclasses import replace
from decimal import Decimal, DecimalException

from powerforge_engineering_model.errors import EngineeringModelError
from powerforge_engineering_model.registry import get_attribute_definition, get_equipment_definition
from powerforge_extraction import interpretation_v1 as legacy
from powerforge_extraction.contracts import CandidateInput, SourceGroupInput
from powerforge_extraction.enriched_contracts import EnrichedEvidence
from powerforge_extraction.enriched_grounding import (
    contains,
    identifier,
    image_location,
    line_groups,
    lookup,
    reading_evidence,
    render,
)
from powerforge_extraction.enriched_output import Output, candidate
from powerforge_extraction.enums import MappingStatus
from powerforge_extraction.interpretation_v1 import Interpretation, InterpretationContext
from powerforge_extraction.stage_diagnostics import SourceRejection

_CONDITIONAL = re.compile(
    r"\b(?:provisional|estimated?|pending|minimum|maximum|range|spare|prov|series.rated|AFN)\b"
    r"|\bat\s+\d|\d\s*[–—]\s*\d|\d\s*-\s*\d",
    re.I,
)
_DEVICE_CUE = re.compile(
    r"\b(?:transformer|winding|isolation|breaker|interrupt|panelboard|switchgear|bus|cable|"
    r"motor|generator|fuse|reactor|capacitor|utility|relay|converter)\w*\b",
    re.I,
)
_DESIGNATION = re.compile(r"\b(?:tag|designation)\s*[:#-]\s*(\S+)", re.I)


# Mechanical spelling aliases for literal unit readings. The registry owns the
# dimension and conversion factors.
_UNIT_SPELLINGS = {
    "volt": "V",
    "volts": "V",
    "kilovolt": "kV",
    "kilovolts": "kV",
    "ampere": "A",
    "amperes": "A",
    "amp": "A",
    "amps": "A",
    "hertz": "Hz",
    "percent": "%",
}


def _fragments(sources, observation, readings, lines):
    parts = []
    for anchor in observation.anchors:
        if anchor.source_ref == "analysis_image":
            location = image_location(sources)
            evidence = EnrichedEvidence(
                id=identifier(sources, "visual", observation.local_ref),
                location=location,
                source_kind="VISUAL_REGION",
                extraction_method="AI_VISION",
            )
            parts.append((anchor, (), (evidence,), ()))
            continue
        refs = anchor.reading_refs
        if any(ref not in readings for ref in refs):
            raise SourceRejection("UNAVAILABLE_READING_ALIAS", "Unknown source reading")
        selected = tuple(readings[ref] for ref in refs)
        line = next((items for items in lines.values() if all(r in items for r in selected)), ())
        if (
            not line
            or not any(
                line[index : index + len(selected)] == selected for index in range(len(line))
            )
            or not contains(anchor.quote, render(selected))
        ):
            raise SourceRejection("SOURCE_EXPRESSION_MISMATCH", "Fragment differs from source")
        parts.append(
            (anchor, selected, tuple(reading_evidence(sources, r) for r in selected), line)
        )
    return parts


def _shared_reading_field(text, label_quote, value_quote):
    """Resolve unique literal substrings without inventing new source offsets."""

    def occurrences(quote):
        return list(re.finditer(r"(?<!\w)" + re.escape(quote) + r"(?!\w)", text))

    labels, values = occurrences(label_quote), occurrences(value_quote)
    if len(labels) != 1 or len(values) != 1:
        return False
    label, value = labels[0], values[0]
    if label.end() > value.start() or text[: label.start()].strip():
        return False
    between = text[label.end() : value.start()]
    trailing = text[value.end() :].strip()
    # A field delimiter or space may separate the exact fragments. A sign,
    # decimal continuation, range, or second field cannot be ignored.
    return bool(
        re.fullmatch(r"\s*(?::|=)?\s*", between)
        and (between or label_quote.endswith((":", "=")))
        and not re.search(r"[:=\d]", trailing)
        and not trailing.startswith((".", ",", "/", "+", "-", "–", "—"))
    )


def _relationship(sources, label, value, *, shared_reading=False):
    if not label[1] or not value[1]:
        return "VISUAL_REPORTED" if not label[1] and not value[1] else "UNRESOLVED"
    if label[3] == value[3]:
        if (label[0].role, value[0].role) == ("LABEL", "VALUE"):
            line = label[3]
            left, right = line.index(label[1][-1]), line.index(value[1][0])
            if shared_reading and left == right and len(label[1]) == len(value[1]) == 1:
                return (
                    "SAME_SOURCE_LINE"
                    if _shared_reading_field(line[left].text, label[0].quote, value[0].quote)
                    else "UNRESOLVED"
                )
            if left >= right or any(
                ":" in r.text or any(ch.isdigit() for ch in r.text) for r in line[left + 1 : right]
            ):
                return "UNRESOLVED"
        return "SAME_SOURCE_LINE"
    label_refs = {r.model.ref for r in label[1]}
    value_refs = {r.model.ref for r in value[1]}
    for table in sources.layout.tables:
        cells = {cell.ref: cell for cell in table.cells}
        if any(
            value_refs <= set(cell.readings)
            and any(label_refs <= set(cells[ref].readings) for ref in cell.headers)
            for cell in table.cells
        ):
            return "SOURCE_TABLE_HEADER"
    if any(r.box is None for r in (*label[1], *value[1])):
        return "UNRESOLVED"
    lx, ly, lr, lb = label[1][0].box
    vx, vy, vr, vb = value[1][0].box
    height = max(lb - ly, vb - vy)
    if not height:
        return "UNRESOLVED"
    horizontal = lr <= vx <= lr + 10 * height and abs(ly - vy) <= height / 2
    vertical = lb <= vy <= lb + 3 * height and abs(lx - vx) <= height
    if not (horizontal or vertical):
        return "UNRESOLVED"
    selected = (*label[3], *value[3])
    for reading in sources.readings:
        if reading in selected or reading.box is None:
            continue
        x, y, _, _ = reading.box
        if (horizontal and lr <= x < vx and abs(y - ly) <= height / 2) or (
            vertical and ly < y < vy and abs(x - lx) <= height
        ):
            return "UNRESOLVED"
    return "LOCAL_FORM_GEOMETRY"


def _agrees(fragment, value):
    return value is None or bool(fragment and contains(value, fragment[0].quote))


def _equipment_meaning(result, proposal, passage, uncertain):
    if (
        uncertain
        or not proposal
        or not _DEVICE_CUE.search(passage)
        or re.search(r"\b(?:possibly|maybe|not installed|provisioned|upstream)\b", passage, re.I)
    ):
        return result
    try:
        definition = get_equipment_definition(proposal)
    except EngineeringModelError:
        return result
    recognized = legacy._equipment_type(passage)
    if recognized and recognized != proposal:
        return replace(result, reason_code="EQUIPMENT_PROPOSAL_CONFLICT")
    if re.search(r"\bpanelboard\b", passage, re.I) and proposal != "BUS":
        return replace(result, reason_code="EQUIPMENT_PROPOSAL_CONFLICT")
    if re.search(r"\btransformer\b", passage, re.I) and "TRANSFORMER" not in proposal:
        return replace(result, reason_code="EQUIPMENT_PROPOSAL_CONFLICT")
    # A generic device heading cannot alone establish a specialized subtype.
    if (
        proposal == "TWO_WINDING_TRANSFORMER"
        and not recognized
        and not (
            re.search(r"\b(?:primary|input)\b", passage, re.I)
            and re.search(r"\b(?:secondary|output)\b", passage, re.I)
        )
    ):
        return result
    return replace(
        result,
        mapping_status=MappingStatus.MAPPED,
        equipment_type_key=definition.key.value,
        reason_code="AI_SUPPORTED_EQUIPMENT",
    )


def _qualified(sources, observation, passage, has_qualifier):
    if has_qualifier or _CONDITIONAL.search(passage):
        return True
    # A separate impedance note can qualify a nominal-looking nameplate cell.
    # Preserve the raw claim when the document contains a competing estimate.
    if "impedance" not in (observation.proposed_attribute_key or ""):
        return False
    return any(
        re.search(r"\b(?:impedance|IZ)\b|%Z", text, re.I) and _CONDITIONAL.search(text)
        for text in (render(row) for row in line_groups(sources).values())
    )


def _attribute_meaning(
    result, proposal, equipment, label, passage, qualified, *, source_supported=False
):
    if (
        not equipment
        or not proposal
        or not label
        or result.raw_value is None
        or label.strip(" :").casefold()
        in {"value", "rating", "amps", "volts", "description", "a", "v", "ka"}
    ):
        return result
    try:
        definition = get_attribute_definition(equipment, proposal)
    except EngineeringModelError:
        return replace(result, reason_code="REGISTRY_ATTRIBUTE_NOT_APPLICABLE")
    context = InterpretationContext(f"{label}: {result.raw_value}", passage[:2000])
    known = legacy._attribute(equipment, label.rstrip(":").strip(), context)
    if known and known.key != proposal:
        return replace(result, reason_code="ATTRIBUTE_PROPOSAL_CONFLICT")
    words = set(re.findall(r"[a-z]+", label.casefold()))
    if not source_supported:
        unit_words = set(re.findall(r"[a-z]+", (result.raw_unit or "").casefold()))
        meaningful = words - unit_words
        rating_label = (
            words == {"kva"}
            and equipment == "TWO_WINDING_TRANSFORMER"
            and proposal == "rated_apparent_power"
        )
        if (
            known is None
            and not rating_label
            and len(meaningful) < 2
            and not (meaningful & {"primary", "secondary", "trip", "frame"})
        ):
            return replace(result, reason_code="INSUFFICIENT_FIELD_CONTEXT")
    elif proposal == "rated_apparent_power" and re.search(
        r"\bauxiliary\s+(?:load|demand|consumption)\b", label, re.I
    ):
        # An explicitly identified load is a different quantity from the rating.
        return replace(result, reason_code="ATTRIBUTE_PROPOSAL_CONFLICT")
    meaning = set(proposal.casefold().split("_"))
    for first, second in (("primary", "secondary"), ("trip", "frame")):
        if (first in words and second in meaning) or (second in words and first in meaning):
            return replace(result, reason_code="ATTRIBUTE_PROPOSAL_CONFLICT")
    if qualified:
        return replace(result, reason_code="QUALIFIED_VALUE_RETAINED")
    value = result.raw_value
    unit = result.raw_unit
    kind = definition.value_type
    if (
        kind in {"NUMBER", "INTEGER"}
        and unit
        and re.search(r"(?<![\w.])" + re.escape(value) + r"(?![\w.])", result.raw_text) is None
    ):
        return result
    invalid = replace(
        result, mapping_status=MappingStatus.INVALID, reason_code="REGISTRY_NORMALIZATION_FAILED"
    )
    if kind in {"NUMBER", "INTEGER"}:
        if definition.canonical_unit and not unit:
            return replace(result, reason_code="MISSING_UNIT")
        if not legacy._NUMBER.fullmatch(value):
            return invalid
        value = Decimal(value)
        if not legacy._representable_number(value) or (
            kind == "INTEGER" and not legacy._INTEGER_MIN <= value <= legacy._INTEGER_MAX
        ):
            return invalid
    elif kind == "BOOLEAN":
        value = legacy._BOOLEAN.get(value.casefold())
    elif kind == "ENUM":
        value = legacy._enum_value(equipment, definition, value)
    if value is None:
        return invalid
    try:
        input_unit = _UNIT_SPELLINGS.get(unit.casefold(), unit) if unit else None
        normalized = legacy.normalize_attribute_value(equipment, proposal, value, input_unit)
    except (EngineeringModelError, DecimalException):
        return invalid
    if isinstance(normalized, Decimal) and not legacy._representable_number(normalized):
        return invalid
    return replace(
        result,
        mapping_status=MappingStatus.MAPPED,
        reason_code="AI_SUPPORTED_ATTRIBUTE",
        equipment_type_key=equipment,
        attribute_key=proposal,
        value_type=kind,
        value=normalized,
        unit=definition.canonical_unit,
    )


def _equipment_scope(sources, heading, observations, uncertain):
    if uncertain or not heading[1] or any(r.box is None for r in heading[1]):
        return ()
    left, top, _, bottom = heading[1][0].box
    height = bottom - top
    others = {
        ref
        for obs in observations
        for anchor in obs.anchors
        if anchor.role == "EQUIPMENT"
        for ref in anchor.reading_refs
    }
    others.difference_update(r.model.ref for r in heading[1])
    rows = sorted(
        (row for row in line_groups(sources).values() if row[0].box),
        key=lambda row: row[0].box[:2][::-1],
    )
    refs = []
    for row in rows:
        x, y, _, end = row[0].box
        if y < bottom or abs(x - left) > 2 * height:
            continue
        if y - bottom > 5 * height or y - top > 40 * height:
            break
        if any(r.model.ref in others for r in row) or (
            legacy._equipment_type(render(row)) and ":" not in render(row)
        ):
            break
        refs.extend(r.model.ref for r in row)
        bottom = end
    return tuple(refs[:128])


_SPEC_SECTION = re.compile(
    r"(?:(?:transformer|winding|electrical|technical|equipment|nameplate) )?"
    r"(?:specifications|ratings|data|characteristics)\s*[:\-]?",
    re.I,
)
_COMPETING_DEVICE = re.compile(
    r"\b(?:transformer|panelboard|breaker|switchgear|generator|motor|reactor|fuse|bus|cable)\b",
    re.I,
)
_WINDING_FIELD = re.compile(r"^(primary|secondary)(?:\s|:)", re.I)


_BRANCH_BREAKERS = re.compile(
    r"(?:installed )?branch(?: circuit)? breakers?(?: schedule)?\s*:?", re.I
)


def _branch_breaker_rows(lines):
    """Return bounded branch rows and their explicit section headings."""
    rows = sorted(
        (row for row in lines.values() if row[0].box),
        key=lambda row: (row[0].box[1], row[0].box[0]),
    )
    result = {}
    for index, heading in enumerate(rows):
        if not _BRANCH_BREAKERS.fullmatch(render(heading)) or any(r.model.issues for r in heading):
            continue
        x, y, _, bottom = heading[0].box
        height = bottom - y
        for row in rows[index + 1 : index + 33]:
            left, top, _, end = row[0].box
            if top < bottom or abs(left - x) > 2 * height:
                continue
            text = render(row)
            if (
                top - bottom > 4 * height
                or any(r.model.issues for r in row)
                or row[0].kind != heading[0].kind
                or not re.search(r"\d", text)
                or re.search(
                    r"\b(?:panelboard|transformer|PROV|provisioned|spare|designation|tag)\b",
                    text,
                    re.I,
                )
            ):
                break
            result[row[0].model.ref] = heading
            bottom = end
    return result


def _panelboard_designation(
    sources, observation, heading, observations, readings, lines, branches, tag
):
    if observation.proposed_equipment_type != "BUS" or not re.search(
        r"\bpanelboard\b", render(heading), re.I
    ):
        return ()
    designations = {
        match[1] for line in lines.values() if (match := _DESIGNATION.search(render(line)))
    }
    if designations != {tag}:
        return ()
    for line in lines.values():
        if line == heading or line[0].model.ref in branches:
            continue
        text = render(line)
        if not _BRANCH_BREAKERS.fullmatch(text) and (
            legacy._equipment_type(text) or _COMPETING_DEVICE.search(text)
        ):
            return ()
    context = {}
    for peer in observations:
        if peer is observation:
            continue
        if peer.ambiguous or peer.proposed_equipment_type not in {"LV_BREAKER", "HV_BREAKER"}:
            return ()
        try:
            parts = _fragments(sources, peer, readings, lines)
        except SourceRejection:
            return ()
        rows = [row for anchor, _, _, row in parts if anchor.role == "EQUIPMENT"]
        if len(rows) != 1 or not rows[0] or rows[0][0].model.ref not in branches:
            return ()
        row = rows[0]
        for reading in (*branches[row[0].model.ref], *row):
            context[reading.model.ref] = reading
    return tuple(context.values())[:32]


def _distributed_sections(lines, heading):
    """Bound section membership by its own heading and column."""
    if not heading or any(r.box is None or r.model.issues for r in heading):
        return ()
    rows = sorted(
        (row for row in lines.values() if row[0].box),
        key=lambda row: (row[0].box[1], row[0].box[0]),
    )
    designations = set()
    for row in rows:
        text = render(row)
        tag = _DESIGNATION.search(text)
        if tag:
            designations.add(tag[1])
        if (
            row != heading
            and _COMPETING_DEVICE.search(text)
            and not _SPEC_SECTION.fullmatch(text)
            and not _WINDING_FIELD.match(text)
        ):
            return ()
    if len(designations) > 1:
        return ()
    sections = []
    winding_sides = set()
    for index, header in enumerate(rows):
        if not _SPEC_SECTION.fullmatch(render(header)) or any(r.model.issues for r in header):
            continue
        x, y, _, bottom = header[0].box
        height = bottom - y
        members = []
        pending_winding = None
        for row in rows[index + 1 :]:
            left, top, _, end = row[0].box
            if top < bottom or not x - height <= left <= x + 18 * height:
                continue
            if top - bottom > 4 * height or _SPEC_SECTION.fullmatch(render(row)):
                break
            if any(r.model.issues or r.kind != header[0].kind for r in row):
                break
            text = render(row)
            # A new prose heading terminates the block; fields and numeric continuations belong.
            if ":" not in text and not re.search(r"\d", text):
                break
            members.extend(row)
            bottom = end
            match = _WINDING_FIELD.match(text)
            side = match[1].lower() if match else None
            voltage = re.search(r"\b\d+(?:\.\d+)?\s*(?:k?V|Volts?)\b", text, re.I)
            if voltage and (side or (pending_winding and re.match(r"^\d", text))):
                winding_sides.add(side or pending_winding)
            pending_winding = side if not voltage else None
            if len(members) >= 128:
                break
        if members:
            sections.append((header, {r.model.ref for r in members}))
    # Explicit headings alone do not connect arbitrary fields to the equipment.
    return sections if winding_sides == {"primary", "secondary"} else ()


def convert_engineering(response, sources, context=None, *, trace=None, distributed=False):
    output = Output(sources)
    mentions = {c.diagnostics["source_local_ref"]: c for c in context.candidates} if context else {}
    if context:
        output.existing_evidence = {e.id for e in context.evidence}
    equipment = context is None
    observations = response.equipment if equipment else response.attributes
    seen = set()
    readings_by_ref = lookup(sources)
    lines = line_groups(sources)
    branches = _branch_breaker_rows(lines) if equipment and distributed else {}
    for obs in observations:
        if trace:
            trace.phase = "GROUNDING"
        try:
            parts = _fragments(sources, obs, readings_by_ref, lines)
        except SourceRejection as exc:
            if trace:
                trace.observe("GROUNDING_REJECTED", obs, reason=exc.reason)
            continue
        if trace:
            trace.phase = "INTERPRETATION"
        by_role = {}
        for part in parts:
            by_role.setdefault(part[0].role, part)
        readings = [r for _, rs, _, _ in parts for r in rs]
        evidence = [e for _, _, es, _ in parts for e in es]
        uncertain = (
            obs.ambiguous
            or any(r.model.issues for r in readings)
            or any(
                sum(part[0].role == role for part in parts) > 1
                for role in ("VALUE", "LABEL", "UNIT", "TAG", "EQUIPMENT")
            )
        )
        # Keep the selected original fragments independently. This string is only display text.
        raw = " ".join(dict.fromkeys(part[0].quote for part in parts))[:2000]
        passage = "\n".join(dict.fromkeys(render(line) for _, _, _, line in parts if line)) or raw
        result = Interpretation(MappingStatus.UNMAPPED, "UNRESOLVED_SOURCE_MEANING", raw)
        basis, mention, group = "UNRESOLVED", None, None
        local_context = []
        designation_context = []
        association_basis = None
        if equipment:
            if "EQUIPMENT" not in by_role:
                if "TAG" in by_role:
                    tag_only = CandidateInput(
                        id=identifier(sources, "candidate", obs.local_ref),
                        kind="UNMAPPED_OBSERVATION",
                        mapping_status="UNMAPPED",
                        raw_text=by_role["TAG"][0].quote,
                        reason_code="UNASSIGNED_TAG",
                        diagnostics={"observation": obs.model_dump(mode="json")},
                    )
                    output.candidates.append(tag_only)
                    output.cite(tag_only, by_role["TAG"][2])
                    if trace:
                        trace.observe("GROUNDING_ADMITTED", obs)
                        trace.observe("UNMAPPED", obs, reason="UNASSIGNED_TAG", candidate=tag_only)
                continue
            tag = obs.observed_tag
            tag_part = by_role.get("TAG")
            designation = _DESIGNATION.search(render(tag_part[3])) if tag_part else None
            own = by_role["EQUIPMENT"]
            sections = (
                _distributed_sections(lines, own[3])
                if distributed
                and not uncertain
                and len(observations) == 1
                and re.search(r"\btransformer\b", render(own[3]), re.I)
                else ()
            )
            corroboration = [
                part
                for part in parts
                if part[0].role == "CONTEXT"
                and (
                    _relationship(sources, own, part) != "UNRESOLVED"
                    or (
                        part[1]
                        and any({r.model.ref for r in part[1]} <= refs for _, refs in sections)
                    )
                )
            ]
            description = " ".join(
                [render(own[3]) or own[0].quote, *(part[0].quote for part in corroboration)]
            )[:2000]
            if tag and _agrees(tag_part, tag):
                if (
                    tag_part[3]
                    and tag_part[3] == own[3]
                    and (
                        (designation and designation[1] == tag)
                        or (
                            re.fullmatch(r"[A-Za-z]{1,5}-[0-9]+", tag)
                            and own[3][0].model.ref not in branches
                            and not re.search(
                                r"\b(?:model|catalog|part|serial)\b", render(own[3]), re.I
                            )
                        )
                    )
                ):
                    basis = "SAME_SOURCE_LINE"
                elif (
                    distributed
                    and designation
                    and designation[1] == tag
                    and (
                        panel_context := _panelboard_designation(
                            sources,
                            obs,
                            own[3],
                            observations,
                            readings_by_ref,
                            lines,
                            branches,
                            tag,
                        )
                    )
                ):
                    basis = "EXPLICIT_PANELBOARD_DESIGNATION"
                    designation_context = [reading_evidence(sources, r) for r in panel_context]
                elif designation and designation[1] == tag and len(observations) == 1:
                    # Another independently recognizable equipment heading makes the tag ambiguous.
                    peers = [
                        line
                        for line in line_groups(sources).values()
                        if line != own[3]
                        and (
                            legacy._equipment_type(render(line))
                            or (_DEVICE_CUE.search(render(line)) and ":" not in render(line))
                        )
                    ]
                    designations = {
                        match[1]
                        for line in line_groups(sources).values()
                        if (match := _DESIGNATION.search(render(line)))
                    }
                    if not peers and designations == {tag}:
                        basis = "EXPLICIT_PAGE_DESIGNATION"
            result = _equipment_meaning(result, obs.proposed_equipment_type, description, uncertain)
            if basis != "UNRESOLVED" and not uncertain:
                result = replace(result, observed_tag=tag)
            else:
                basis = "UNRESOLVED"
            group = identifier(sources, "group", obs.local_ref)
        else:
            label, value = by_role.get("LABEL"), by_role.get("VALUE")
            if not value:
                continue
            if label:
                basis = _relationship(sources, label, value, shared_reading=distributed)
            unit_part = by_role.get("UNIT") or label
            unit = obs.raw_unit if _agrees(unit_part, obs.raw_unit) else None
            unit_supported = not obs.raw_unit or (
                unit
                and (unit_part is label or _relationship(sources, value, unit_part) != "UNRESOLVED")
            )
            value_exact = bool(obs.raw_value and _agrees(value, obs.raw_value))
            if obs.raw_value and legacy._NUMBER.fullmatch(obs.raw_value):
                value_exact = value[0].quote == obs.raw_value or bool(
                    unit and value[0].quote == f"{obs.raw_value} {unit}"
                )
            result = replace(
                result,
                raw_text=value[0].quote if basis == "UNRESOLVED" else raw,
                raw_value=obs.raw_value if value_exact else value[0].quote,
                raw_unit=unit if unit_supported and basis != "UNRESOLVED" else None,
            )
            mention = mentions.get(obs.equipment_ref)
            if mention:
                selected = {r.model.ref for r in value[1]}
                label_refs = {r.model.ref for r in label[1]} if label else set()
                scope = set(mention.diagnostics["scope_readings"])
                direct = bool(selected) and selected <= scope
                via_label = (
                    bool(label_refs)
                    and label_refs <= scope
                    and basis not in {"UNRESOLVED", "VISUAL_REPORTED"}
                )
                section = None
                if (
                    distributed
                    and not (direct or via_label)
                    and len(mentions) == 1
                    and selected
                    and label_refs
                    and basis not in {"UNRESOLVED", "VISUAL_REPORTED"}
                ):
                    from powerforge_extraction.semantic_observations import SemanticEquipment

                    original = SemanticEquipment.model_validate(mention.diagnostics["observation"])
                    heading = next(
                        (
                            part[3]
                            for part in _fragments(sources, original, readings_by_ref, lines)
                            if part[0].role == "EQUIPMENT"
                        ),
                        (),
                    )
                    if not original.ambiguous and re.search(
                        r"\btransformer\b", render(heading), re.I
                    ):
                        section = next(
                            (
                                header
                                for header, refs in _distributed_sections(lines, heading)
                                if selected | label_refs <= refs
                            ),
                            None,
                        )
                if section:
                    association_basis = "CORROBORATED_SPECIFICATION_SECTION"
                    local_context.extend(reading_evidence(sources, r) for r in section[:16])
                elif not (direct or via_label):
                    mention = None
            if uncertain:
                result = replace(result, reason_code="AMBIGUOUS_OBSERVATION")
            elif basis == "UNRESOLVED":
                result = replace(result, reason_code="UNRESOLVED_SOURCE_RELATIONSHIP")
            elif mention is None:
                result = replace(result, reason_code="DETACHED_SOURCE_ASSOCIATION")
            elif not unit_supported:
                result = replace(result, reason_code="SOURCE_UNIT_MISMATCH")
            if obs.equipment_ref and mention is None and trace:
                trace.observe("DETACHED_ASSOCIATIONS", obs, reason="OUTSIDE_EQUIPMENT_SCOPE")
            if (
                mention
                and label
                and not uncertain
                and basis not in {"UNRESOLVED", "VISUAL_REPORTED"}
                and unit_supported
                and value_exact
                and _agrees(label, obs.source_label)
            ):
                kind = mention.equipment_type_key or obs.proposed_equipment_type
                if not mention.equipment_type_key:
                    kind = _equipment_meaning(
                        result, kind, mention.diagnostics["description"], False
                    ).equipment_type_key
                if obs.proposed_equipment_type in (None, kind):
                    result = _attribute_meaning(
                        result,
                        obs.proposed_attribute_key,
                        kind,
                        label[0].quote,
                        mention.raw_text,
                        _qualified(sources, obs, passage, "QUALIFIER" in by_role),
                        source_supported=distributed,
                    )
            if basis not in {"UNRESOLVED", "VISUAL_REPORTED"}:
                cited_refs = {r.model.ref for r in readings}
                local_context.extend(
                    [
                        reading_evidence(sources, r)
                        for r in value[3][:16]
                        if r.model.ref not in cited_refs
                    ]
                )
            group = mention.source_group_id if mention else None
        if not equipment:
            key = (
                tuple((part[0].role, tuple(e.id for e in part[2])) for part in parts),
                obs.proposed_attribute_key,
                obs.equipment_ref,
                result.raw_value,
                result.raw_unit,
            )
            if key in seen:
                if trace:
                    trace.observe(
                        "DUPLICATE_OBSERVATIONS", obs, reason="DUPLICATE_SOURCE_ASSERTION"
                    )
                continue
            seen.add(key)
        metadata = {
            "observation": obs.model_dump(mode="json"),
            "relationship_basis": basis,
            "mapping_basis": "AI_SOURCE_SUPPORTED" if result.mapping_status == "MAPPED" else None,
            "evidence_parts": [
                {"role": anchor.role, "evidence_ids": [str(e.id) for e in citations]}
                for anchor, _, citations, _ in parts
            ],
        }
        if association_basis:
            metadata["equipment_association_basis"] = association_basis
        if designation_context:
            metadata["designation_context_evidence_ids"] = [str(e.id) for e in designation_context]
        if local_context:
            metadata["evidence_parts"].append(
                {
                    "role": "CONTEXT",
                    "evidence_ids": [str(e.id) for e in local_context],
                }
            )
        if equipment:
            metadata["description"] = description
            metadata["scope_readings"] = list(
                _equipment_scope(sources, own, observations, uncertain)
            )
        if trace:
            trace.phase = "CONVERSION"
        c = candidate(
            sources,
            obs.local_ref,
            result,
            evidence,
            equipment=equipment,
            group=group,
            mention=mention.id if mention else None,
            diagnostics=metadata,
        )
        output.candidates.append(c)
        supporting = (
            [
                e
                for e in context.evidence
                if mention
                and any(
                    link.candidate_id == mention.id and link.evidence_id == e.id
                    for link in context.candidate_evidence
                )
            ]
            if context
            else []
        )
        output.cite(c, evidence, [*designation_context, *local_context, *supporting])
        if group and equipment:
            output.groups.append(
                SourceGroupInput(
                    id=group,
                    local_key=f"semantic/{sources.unit_key}/{obs.local_ref}",
                    equipment_type_hint=result.equipment_type_key,
                    tag_text=result.observed_tag,
                    evidence_ids=list(dict.fromkeys(e.id for e in evidence)),
                )
            )
        if trace:
            trace.observe("GROUNDING_ADMITTED", obs)
            trace.observe(
                c.mapping_status,
                obs,
                reason=c.reason_code,
                candidate=c,
                association=association_basis or basis,
            )
    return output.result()


def committed_recognition(sources, rows):
    """Reuse immutable decisions, independently resolving their exact evidence parts."""
    from powerforge_extraction.semantic_observations import SemanticEquipment

    output = Output(sources)
    readings_by_ref = lookup(sources)
    lines = line_groups(sources)
    for row in rows:
        observation = SemanticEquipment.model_validate(row.diagnostics["observation"])
        fragments = _fragments(sources, observation, readings_by_ref, lines)
        actual = [
            {"role": anchor.role, "evidence_ids": [str(e.id) for e in evidence]}
            for anchor, _, evidence, _ in fragments
        ]
        if actual != row.diagnostics["evidence_parts"] or row.id != identifier(
            sources, "candidate", observation.local_ref
        ):
            raise ValueError("Committed recognition evidence differs from pinned sources")
        data = {field: getattr(row, field) for field in CandidateInput.model_fields}
        mention = CandidateInput.model_validate(data)
        output.candidates.append(mention)
        output.cite(mention, [e for _, _, evidence, _ in fragments for e in evidence])
    return output.result()
