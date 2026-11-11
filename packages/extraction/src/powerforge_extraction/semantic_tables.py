"""AI-led interpretation of separately reconstructed and committed table cells."""

import re

from powerforge_extraction import interpretation_v1 as legacy
from powerforge_extraction.contracts import SourceGroupInput
from powerforge_extraction.enriched_grounding import contains, identifier
from powerforge_extraction.enriched_output import Output, candidate
from powerforge_extraction.enums import MappingStatus
from powerforge_extraction.interpretation_v1 import Interpretation
from powerforge_extraction.semantic_output import (
    _CONDITIONAL,
    _DEVICE_CUE,
    _attribute_meaning,
    _equipment_meaning,
)

_PROVISIONED = re.compile(
    r"(?:PROV|PROVISIONED|SPARE|SPACE|RESERVED)(?:\s+(?:SPACE|POSITION))?", re.I
)


def _provisioned_rows(table):
    if table.kind != "EQUIPMENT_ROWS":
        return set()
    return {
        c.row
        for c in table.observation.cells
        if c.row_span == 1
        and c.header_role == "NONE"
        and _PROVISIONED.fullmatch((c.raw_text or "").strip())
    }


def interpret_tables(
    response, sources, context, *, trace=None, source_supported=False, compact=False
):
    """Interpret committed cells without using terminology as the mapping gate."""
    from powerforge_extraction.table_output import _scope, headers

    output = Output(sources)
    output.existing_evidence = {e.id for e in context.output.evidence}
    tables = {table.observation.local_ref: table for table in context.tables}
    mentions = {}
    physical_mentions = {}
    provisioned = (
        {ref: _provisioned_rows(table) for ref, table in tables.items()} if compact else {}
    )
    for obs in response.equipment:
        table = tables.get(obs.table_ref)
        if table is None or any(ref not in table.items for ref in obs.source_refs):
            if trace:
                trace.observe("GROUNDING_REJECTED", obs, reason="UNAVAILABLE_TABLE_SOURCE_ALIAS")
            continue
        scope, cells = _scope(table, obs)
        if compact and not cells and table.kind == "ATTRIBUTE_ROWS":
            types = [
                c
                for c in table.observation.cells
                if c.state == "VALUE"
                and c.header_role == "NONE"
                and c.raw_text
                and any(
                    h.raw_text.strip().casefold() in {"equipment type", "device type"}
                    for h in headers(table, c)
                )
            ]
            cells = [
                c
                for c in types
                if c.local_ref in obs.source_refs and contains(obs.raw_expression, c.raw_text)
            ]
            if (
                len(types) == len(cells) == 1
                and table.basis not in {"UNRESOLVED", "VISUAL_REPORTED"}
                and not (
                    table.observation.ambiguous or table.observation.truncated or cells[0].ambiguous
                )
            ):
                scope = "spec"
        if not cells and table.kind == "EQUIPMENT_ROWS":
            cells = [
                cell
                for cell in table.observation.cells
                if cell.local_ref in obs.source_refs
                and cell.state == "VALUE"
                and cell.raw_text
                and contains(obs.raw_expression, cell.raw_text)
            ]
            if (
                len(cells) == 1
                and cells[0].row_span == 1
                and cells[0].header_role == "NONE"
                and _DEVICE_CUE.search(cells[0].raw_text)
                and table.basis not in {"UNRESOLVED", "VISUAL_REPORTED"}
                and not (table.observation.ambiguous or table.observation.truncated)
            ):
                scope = f"row:{cells[0].row}"
        values = [c.raw_text for c in cells if c.raw_text]
        if table.observation.title and table.observation.title.local_ref in obs.source_refs:
            values.append(table.observation.title.raw_text)
        if not any(contains(obs.raw_expression, value) for value in values):
            if trace:
                trace.observe("GROUNDING_REJECTED", obs, reason="SOURCE_EXPRESSION_MISMATCH")
            continue
        identity_text = " ".join(values)
        title = table.observation.title
        passage = (
            " ".join([identity_text, title.raw_text])
            if (title and title.local_ref in table.scoped and not title.ambiguous)
            else identity_text
        )
        if any(c.row in provisioned.get(obs.table_ref, ()) for c in cells) or re.search(
            r"\b(?:PROV|PROVISIONED|SPARE|SPACE)\b", identity_text if compact else passage, re.I
        ):
            if trace:
                trace.observe("SOURCE_SCOPE_REJECTED", obs, reason="PROVISIONED_POSITION")
            continue
        tag = (
            obs.observed_tag
            if obs.observed_tag and contains(obs.observed_tag, identity_text)
            else None
        )
        if (
            compact
            and tag
            and not any(
                contains(tag, c.raw_text)
                and any(
                    h.raw_text.strip().casefold() in {"tag", "equipment tag", "designation"}
                    for h in headers(table, c)
                )
                for c in cells
            )
        ):
            tag = None
        key = (obs.table_ref, scope, tuple(c.local_ref for c in cells), obs.raw_expression)
        if compact and scope and key in physical_mentions:
            mentions[obs.local_ref] = physical_mentions[key]
            if trace:
                trace.observe("DUPLICATE_OBSERVATIONS", obs, reason="DUPLICATE_SOURCE_ASSERTION")
            continue
        evidence = [e for ref in obs.source_refs for e in table.items[ref]]
        result = _equipment_meaning(
            Interpretation(
                MappingStatus.UNMAPPED,
                "UNRESOLVED_SOURCE_MEANING",
                obs.raw_expression,
                observed_tag=tag if scope else None,
            ),
            obs.proposed_equipment_type,
            passage,
            obs.ambiguous or not scope or table.basis in {"UNRESOLVED", "VISUAL_REPORTED"},
        )
        group = identifier(sources, "group", obs.local_ref) if scope else None
        if trace:
            trace.phase = "CONVERSION"
        c = candidate(
            sources,
            obs.local_ref,
            result,
            evidence,
            equipment=True,
            group=group,
            diagnostics={
                "observation": obs.model_dump(mode="json"),
                "structure_basis": table.basis,
                "mapping_basis": "AI_SOURCE_SUPPORTED"
                if result.mapping_status == "MAPPED"
                else None,
            },
        )
        mentions[obs.local_ref] = (table, scope, c, passage)
        if compact and scope:
            physical_mentions[key] = mentions[obs.local_ref]
        output.candidates.append(c)
        output.cite(c, evidence)
        if group:
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
                c.mapping_status, obs, reason=c.reason_code, candidate=c, association=table.basis
            )
    for obs in response.attributes:
        table = tables.get(obs.table_ref)
        cell = (
            next((c for c in table.observation.cells if c.local_ref == obs.value_cell_ref), None)
            if table
            else None
        )
        if cell is None or not cell.raw_text or cell.state != "VALUE":
            if trace:
                trace.observe("GROUNDING_REJECTED", obs, reason="UNAVAILABLE_VALUE_CELL")
            continue
        hs = headers(table, cell)
        by_ref = {header.local_ref: header.raw_text for header in hs}
        cited = [*obs.label_refs, *obs.unit_refs, *obs.qualifier_refs]
        supported = all(ref in by_ref for ref in cited)
        labels = [by_ref[ref] for ref in obs.label_refs if ref in by_ref]
        label = obs.source_label
        label_supported = label and any(contains(label, text) for text in labels)
        raw_supported = obs.raw_value and contains(obs.raw_value, cell.raw_text)
        if raw_supported and legacy._NUMBER.fullmatch(obs.raw_value):
            raw_supported = cell.raw_text.strip() in {
                obs.raw_value,
                f"{obs.raw_value} {obs.raw_unit}",
            }
        unit = obs.raw_unit
        unit_supported = not unit or any(
            contains(unit, text)
            for text in [
                cell.raw_text,
                *(by_ref[ref] for ref in obs.unit_refs if ref in by_ref),
                *labels,
            ]
        )
        result = Interpretation(
            MappingStatus.UNMAPPED,
            "UNRESOLVED_SOURCE_MEANING",
            cell.raw_text,
            raw_value=obs.raw_value if raw_supported else cell.raw_text,
            raw_unit=unit if unit_supported else None,
        )
        is_provisioned = cell.row in provisioned.get(obs.table_ref, ())
        if is_provisioned:
            result = Interpretation(
                MappingStatus.UNMAPPED,
                "PROVISIONED_POSITION",
                cell.raw_text,
                raw_value=result.raw_value,
                raw_unit=result.raw_unit,
            )
        mention = None if is_provisioned else mentions.get(obs.equipment_ref)
        scope = f"row:{cell.row}" if table.kind == "EQUIPMENT_ROWS" else "spec"
        if mention and (mention[0] is not table or mention[1] != scope or cell.row_span != 1):
            mention = None
        passage = " ".join(
            [
                cell.raw_text,
                *(h.raw_text for h in hs),
                *(note.raw_text for note in table.observation.notes),
            ]
        )
        if (
            mention
            and supported
            and label_supported
            and unit_supported
            and raw_supported
            and not (
                obs.ambiguous
                or cell.ambiguous
                or any(h.ambiguous for h in hs)
                or table.observation.ambiguous
                or table.observation.truncated
            )
            and table.basis not in {"UNRESOLVED", "VISUAL_REPORTED"}
        ):
            kind = mention[2].equipment_type_key
            if not kind and not mention[2].diagnostics["observation"]["ambiguous"]:
                kind = _equipment_meaning(
                    result, obs.proposed_equipment_type, mention[3], False
                ).equipment_type_key
            if obs.proposed_equipment_type in (None, kind):
                result = _attribute_meaning(
                    result,
                    obs.proposed_attribute_key,
                    kind,
                    label,
                    mention[3],
                    bool(obs.qualifier_refs or _CONDITIONAL.search(passage)),
                    source_supported=source_supported,
                )
        primary = table.items[cell.local_ref]
        supporting = [e for h in hs for e in table.items[h.local_ref]]
        if is_provisioned:
            supporting.extend(
                e
                for item in table.observation.cells
                if item.row == cell.row and _PROVISIONED.fullmatch((item.raw_text or "").strip())
                for e in table.items[item.local_ref]
            )
        evidence_parts = [{"role": "VALUE", "evidence_ids": [str(e.id) for e in primary]}]
        for role, refs in (
            ("LABEL", obs.label_refs),
            ("UNIT", obs.unit_refs),
            ("QUALIFIER", obs.qualifier_refs),
            ("CONTEXT", set(by_ref) - set(cited)),
        ):
            ids = [str(e.id) for ref in sorted(refs) if ref in by_ref for e in table.items[ref]]
            if ids:
                evidence_parts.append({"role": role, "evidence_ids": ids})
        if trace:
            trace.phase = "CONVERSION"
        c = candidate(
            sources,
            obs.local_ref,
            result,
            primary,
            group=mention[2].source_group_id if mention else None,
            mention=mention[2].id if mention else None,
            diagnostics={
                "observation": obs.model_dump(mode="json"),
                "structure_basis": table.basis,
                "mapping_basis": "AI_SOURCE_SUPPORTED"
                if result.mapping_status == "MAPPED"
                else None,
                "evidence_parts": evidence_parts,
            },
        )
        output.candidates.append(c)
        output.cite(c, primary, supporting)
        if trace:
            trace.observe("GROUNDING_ADMITTED", obs)
            if obs.equipment_ref and not mention:
                trace.observe("DETACHED_ASSOCIATIONS", obs, reason="OUTSIDE_EQUIPMENT_SCOPE")
            trace.observe(
                c.mapping_status, obs, reason=c.reason_code, candidate=c, association=table.basis
            )
    return output.result()
