"""Table claim conversion using admitted structure and existing relational output contracts."""

import re
from dataclasses import replace

from powerforge_extraction import interpretation_v1 as v1
from powerforge_extraction.contracts import (
    CandidateEvidenceInput,
    CandidateInput,
    SourceGroupInput,
    WorkUnitOutput,
)
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.table_grounding import TableContext, context_from_output, identifier
from powerforge_extraction.table_observations import TableReconstructionResponse
from powerforge_extraction.table_semantics import (
    attribute_meaning,
    equipment_meaning,
    source_reading,
)
from powerforge_extraction.table_stages import get_table_stage

IDENTITY_LABELS = {"equipment", "tag", "equipment tag", "name", "equipment name", "device"}
_TAG = re.compile(r"(?<![\w-])[A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*(?![\w-])")


def headers(table, cell):
    obs = table.observation
    if obs.proposed_kind == "EQUIPMENT_ROWS":
        # Only the contiguous complete top header band can qualify a data row.
        band = set()
        for row in range(len(obs.rows)):
            occupied = {
                c
                for h in obs.cells
                if h.row <= row < h.row + h.row_span and h.header_role in {"COLUMN", "BOTH"}
                for c in range(h.column, h.column + h.column_span)
            }
            if occupied != set(range(len(obs.columns))):
                break
            band.add(row)
        return sorted(
            [
                h
                for h in obs.cells
                if h.row in band
                and h.row + h.row_span <= cell.row
                and h.column <= cell.column
                and cell.column + cell.column_span <= h.column + h.column_span
            ],
            key=lambda h: h.row,
        )
    if obs.proposed_kind == "ATTRIBUTE_ROWS":
        return sorted(
            [
                h
                for h in obs.cells
                if h.header_role in {"ROW", "BOTH"}
                and h.column + h.column_span <= cell.column
                and h.row <= cell.row
                and cell.row + cell.row_span <= h.row + h.row_span
            ],
            key=lambda h: h.column,
        )
    return []


def _identity_cells(table):
    return [
        c
        for c in table.observation.cells
        if c.state == "VALUE"
        and c.header_role == "NONE"
        and any(v1._fold(h.raw_text) in IDENTITY_LABELS for h in headers(table, c))
    ]


def _multiple_identity_entries(text):
    entries = {
        part
        for part in re.split(r"\s*(?:[/,;&]|\band\b)\s*", text.strip(), flags=re.I)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part)
    }
    return len(entries) > 1


def _scope(table, claim):
    identities = _identity_cells(table)
    cells = [
        c
        for c in identities
        if c.local_ref in claim.source_refs and claim.raw_expression in c.raw_text
    ]
    if table.basis == "UNRESOLVED" or table.observation.ambiguous or table.observation.truncated:
        return None, cells
    identity_texts = [
        c.raw_text
        for c in identities
        if table.kind == "ATTRIBUTE_ROWS" or cells and c.row == cells[0].row
    ]
    if not cells and table.observation.title:
        identity_texts = [table.observation.title.raw_text]
    # Count source tags, not model observations. This only disqualifies ownership;
    # a tag pattern never establishes an equipment type or physical identity.
    if (
        any(_multiple_identity_entries(text) for text in identity_texts)
        or len({match[0] for text in identity_texts for match in _TAG.finditer(text)}) > 1
    ):
        return None, cells
    if table.kind == "EQUIPMENT_ROWS" and len(cells) == 1 and cells[0].row_span == 1:
        return f"row:{cells[0].row}", cells
    if table.kind == "ATTRIBUTE_ROWS" and len(_identity_cells(table)) <= 1:
        if (
            cells
            or table.observation.title
            and table.observation.title.local_ref in table.scoped
            and (
                table.observation.title.local_ref in claim.source_refs
                and claim.raw_expression in table.observation.title.raw_text
            )
        ):
            return "spec", cells
    return None, cells


def _candidate(spec, key, result, table, *, equipment=False, group=None, mention=None, primary=()):
    slots = {}
    if result.value_type is not None:
        name = {
            "NUMBER": "numeric_value",
            "INTEGER": "integer_value",
            "ENUM": "text_value",
            "TEXT": "text_value",
            "BOOLEAN": "boolean_value",
        }[result.value_type]
        slots[name] = result.value
    native_evidence = [e for e in primary if e.source_snippet is not None]
    native = bool(native_evidence)
    return CandidateInput(
        id=identifier(spec, "candidate", key),
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
        diagnostics={
            "table_contract": "table-grounding-interpretation-v1",
            "table_id": str(table.table_id),
            "structure_basis": table.basis,
            "text_verified": native,
            "grounding_precision": "TEXT_OFFSETS"
            if native and all(e.text_start is not None for e in native_evidence)
            else "TEXT_PAGE"
            if native
            else "VISUAL_PAGE",
            "interpretation_limit": "VISUAL_REPORTED"
            if table.basis == "VISUAL_REPORTED"
            else "SOURCE_REPORTED",
        },
        **slots,
    )


def convert_table_interpretation(response, sources, context: TableContext) -> WorkUnitOutput:
    if context.spec != sources.spec:
        raise ValueError("Table context belongs to another pinned target")
    context = context_from_output(sources, context.output, context.reconstruction_unit_id)
    reconstruction = TableReconstructionResponse(
        schema_version="table-reconstruction-schema-v1",
        overflowed=False,
        tables=[t.observation for t in context.tables],
    )
    response = get_table_stage("TABLE_INTERPRETATION").validate_result(
        response,
        available_sources=[a.role for a in sources.spec.artifacts],
        table_context=reconstruction,
    )
    tables = {t.observation.local_ref: t for t in context.tables}
    candidates, groups, links, mentions, counts, seen = [], [], [], {}, {}, set()
    identities = {}
    for claim in response.equipment:
        scope, _ = _scope(tables[claim.table_ref], claim)
        identities.setdefault((claim.table_ref, scope), set()).add(
            (claim.raw_expression, claim.observed_tag, claim.observed_name)
        )

    def count(name):
        counts[name] = counts.get(name, 0) + 1

    def cite(candidate, primary, supporting):
        used = set()
        for role, es in (("PRIMARY", primary), ("SUPPORTING", supporting)):
            for e in es:
                if e.id not in used:
                    links.append(
                        CandidateEvidenceInput(
                            candidate_id=candidate.id,
                            evidence_id=e.id,
                            role=role,
                            position=len(used),
                        )
                    )
                    used.add(e.id)

    for claim in response.equipment:
        table = tables[claim.table_ref]
        scope, cells = _scope(table, claim)
        if not cells and not (
            table.observation.title
            and claim.raw_expression in table.observation.title.raw_text
            and table.observation.title.local_ref in claim.source_refs
        ):
            count("rejected_source_fields")
            continue
        passages, supporting = [c.raw_text for c in cells], []
        caption_conflict = False
        if table.observation.title and table.observation.title.local_ref in table.scoped:
            passages.append(table.observation.title.raw_text)
            supporting.extend(table.items[table.observation.title.local_ref])
            caption_tags = re.findall(
                r"\b[A-Za-z][A-Za-z0-9]*[-_]\d[\w-]*\b", table.observation.title.raw_text
            )
            caption_conflict = any(tag not in claim.raw_expression for tag in caption_tags)
        # Only an explicitly labelled Type column can supply a second equipment passage.
        type_uncertain = False
        for cell in table.observation.cells:
            if (
                cells
                and cell.row == cells[0].row
                and cell.header_role == "NONE"
                and any(
                    v1._fold(h.raw_text) in {"type", "equipment type", "device type"}
                    for h in headers(table, cell)
                )
            ):
                passages.append(cell.raw_text or "")
                supporting.extend(table.items[cell.local_ref])
                type_uncertain |= (
                    cell.ambiguous
                    or cell.state != "VALUE"
                    or v1._equipment_type(cell.raw_text or "") is None
                    or any(h.ambiguous for h in headers(table, cell))
                )
        result = equipment_meaning(
            claim,
            passages,
            uncertain=scope is None
            or caption_conflict
            or type_uncertain
            or len(identities[claim.table_ref, scope]) > 1
            or any(c.ambiguous for c in cells)
            or bool(table.observation.title and table.observation.title.ambiguous),
        )
        if result.rejected:
            count("rejected_source_fields")
            continue
        primary = [e for c in cells for e in table.items[c.local_ref]] or supporting
        key = f"equipment/{table.table_id}/" + identity_hash(
            [scope, claim.raw_expression, claim.observed_tag, claim.observed_name]
        )
        if key in seen:
            existing = next(
                c for c in candidates if c.id == identifier(sources.spec, "candidate", key)
            )
            previous = next(m[1] for m in mentions.values() if m[0].id == existing.id)
            if previous != result:
                result = replace(
                    result,
                    mapping_status=v1.MappingStatus.UNMAPPED,
                    equipment_type_key=None,
                    reason_code="AMBIGUOUS_OBSERVATION",
                )
            mentions[claim.local_ref] = (
                existing,
                result,
                scope,
                table,
                "\n".join([claim.raw_expression, *passages]),
            )
            continue
        seen.add(key)
        group = identifier(sources.spec, "group", key) if scope is not None else None
        candidate = _candidate(
            sources.spec, key, result, table, equipment=True, group=group, primary=primary
        )
        if group is not None:
            groups.append(
                SourceGroupInput(
                    id=group,
                    local_key=key,
                    equipment_type_hint=result.equipment_type_key,
                    tag_text=claim.observed_tag,
                    evidence_ids=list(dict.fromkeys(e.id for e in [*primary, *supporting])),
                )
            )
        candidates.append(candidate)
        cite(candidate, primary, supporting)
        mentions[claim.local_ref] = (
            candidate,
            result,
            scope,
            table,
            "\n".join([claim.raw_expression, *passages]),
        )
    for claim in response.attributes:
        table = tables[claim.table_ref]
        cell = next(c for c in table.observation.cells if c.local_ref == claim.value_cell_ref)
        hs = headers(table, cell)
        allowed = {h.local_ref for h in hs} | table.scoped
        if any(
            ref not in allowed
            for ref in [*claim.label_refs, *claim.unit_refs, *claim.qualifier_refs]
        ):
            count("rejected_source_fields")
            continue
        mention = mentions.get(claim.equipment_ref)
        reported_mention_id = str(mention[0].id) if mention else None
        expected_scope = (
            f"row:{cell.row}" if table.observation.proposed_kind == "EQUIPMENT_ROWS" else "spec"
        )
        if mention and (
            mention[2] != expected_scope
            or mention[3].table_id != table.table_id
            or cell.row_span != 1
        ):
            mention = None
        if claim.equipment_ref and mention is None:
            count("detached_associations")
        label_texts = [h.raw_text for h in hs]
        notes = [n.raw_text for n in table.observation.notes if n.local_ref in table.scoped]
        result = attribute_meaning(
            claim,
            cell,
            label_texts,
            mention[1] if mention else None,
            mention[4] if mention else "",
            uncertain=table.basis == "UNRESOLVED"
            or table.observation.ambiguous
            or table.observation.truncated
            or any(h.ambiguous or h.state != "VALUE" for h in hs),
            notes=notes,
        )
        if result.rejected:
            count("rejected_source_fields")
            continue
        # Canonical whole fields/AF-AT clauses still collapse alternate excerpts.
        # Limited readings, qualifier context and conflicting proposals stay distinct.
        key = f"attribute/{table.table_id}/" + identity_hash(
            [
                claim.value_cell_ref,
                source_reading(claim, cell).identity,
                [h.local_ref for h in hs],
                sorted(claim.qualifier_refs),
                reported_mention_id,
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        primary = table.items[cell.local_ref]
        candidate = _candidate(
            sources.spec,
            key,
            result,
            table,
            primary=primary,
            group=mention[0].source_group_id if mention else None,
            mention=mention[0].id if mention else None,
        )
        if reported_mention_id and mention is None:
            candidate.diagnostics["reported_equipment_mention_id"] = reported_mention_id
        if claim.qualifier_refs:
            candidate.diagnostics["reported_qualifier_evidence_ids"] = [
                str(e.id) for ref in sorted(claim.qualifier_refs) for e in table.items[ref]
            ]
        candidates.append(candidate)
        supporting = [e for h in hs for e in table.items[h.local_ref]]
        supporting += [e for ref in table.scoped for e in table.items[ref]]
        if mention:
            supporting += [
                e
                for link in links
                if link.candidate_id == mention[0].id
                for es in table.items.values()
                for e in es
                if e.id == link.evidence_id
            ]
        cite(candidate, primary, supporting)
    return WorkUnitOutput(
        candidates=candidates,
        source_groups=groups,
        candidate_evidence=links,
        diagnostic_counts=counts,
    )
