"""Spatial reconstruction adapter and existing conservative table semantic helpers."""

import re
from dataclasses import dataclass
from types import SimpleNamespace

from powerforge_extraction.contracts import SourceGroupInput
from powerforge_extraction.enriched_contracts import (
    EnrichedTableCell,
    EnrichedTableInput,
    EnrichedTableLayout,
)
from powerforge_extraction.enriched_grounding import ground, identifier, lookup, render
from powerforge_extraction.enriched_observations import EnrichedTableText
from powerforge_extraction.enriched_output import Output, candidate
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.stage_diagnostics import SourceRejection
from powerforge_extraction.table_output import _scope, headers
from powerforge_extraction.table_semantics import (
    attribute_meaning,
    equipment_meaning,
    source_reading,
)


@dataclass(frozen=True)
class TableContext:
    tables: tuple
    output: object


def _admit(sources, obs, *, projected_table=False):
    source = next((t for t in sources.layout.tables if t.ref == obs.spatial_table_ref), None)
    if source is None:
        if obs.spatial_table_ref is not None:
            raise SourceRejection("UNAVAILABLE_SPATIAL_TABLE_ALIAS", "Unknown spatial table alias")
        if any(p.kind == "CONFLICT" for p in sources.layout.overlaps):
            return "UNRESOLVED"
        return (
            "VISUAL_REPORTED"
            if all(a.source_ref == "analysis_image" for a in obs.anchors)
            else "UNRESOLVED"
        )
    if obs.proposed_kind == "ATTRIBUTE_ROWS" and not projected_table:
        from powerforge_extraction.enriched_output import _known_field

        if source.columns != 2 or any(c.row_span != 1 or c.column_span != 1 for c in source.cells):
            return "UNRESOLVED"
        generic = {"attribute", "parameter", "value", "unit", "units", "description"}
        for cell in obs.cells:
            original = next((c for c in source.cells if c.ref == cell.spatial_cell_ref), None)
            if original is None:
                return "UNRESOLVED"
            if original.header_role == "COLUMN":
                if (cell.raw_text or "").casefold() not in generic or cell.header_role != "COLUMN":
                    return "UNRESOLVED"
            elif cell.column == 0:
                if cell.header_role != "ROW" or not (
                    cell.raw_text
                    and (
                        cell.raw_text.casefold()
                        in {"equipment", "tag", "equipment tag", "name", "type", "equipment type"}
                        or _known_field(cell.raw_text + ": 0")
                    )
                ):
                    return "UNRESOLVED"
            elif cell.header_role != "NONE":
                return "UNRESOLVED"
    if (
        obs.ambiguous
        or obs.truncated
        or len(obs.rows) != source.rows
        or len(obs.columns) != source.columns
    ):
        return "UNRESOLVED"
    lookup_readings = lookup(sources)
    by_ref = {c.ref: c for c in source.cells}
    matched = {c.spatial_cell_ref: c for c in obs.cells}
    if len(matched) != len(obs.cells) or set(matched) != set(by_ref):
        return "UNRESOLVED"
    aliases = {ref: c.local_ref for ref, c in matched.items()}
    for ref, cell in matched.items():
        original = by_ref[ref]
        actual_refs = [r for a in cell.anchors for r in a.reading_refs]
        if (
            (cell.row, cell.column, cell.row_span, cell.column_span)
            != (original.row, original.column, original.row_span, original.column_span)
            or len(actual_refs) != len(set(actual_refs))
            or set(actual_refs) != set(original.readings)
            or original.readings
            and cell.raw_text != render([lookup_readings[r] for r in original.readings])
            or not original.readings
            and cell.state == "VALUE"
        ):
            return "UNRESOLVED"
        expected = [aliases[r] for r in original.headers]
        if obs.proposed_kind == "ATTRIBUTE_ROWS":
            # A new adapter may support explicit same-row labels from an established
            # partition; row coverage is proved, label meaning remains interpretation.
            for h in cell.header_refs:
                if projected_table and h in expected:
                    continue  # The committed column header is still applicable.
                header = next((c for c in obs.cells if c.local_ref == h), None)
                if (
                    header is None
                    or header.header_role not in ("ROW", "BOTH")
                    or header.row > cell.row
                    or header.row + header.row_span < cell.row + cell.row_span
                    or header.column + header.column_span > cell.column
                ):
                    return "UNRESOLVED"
        elif not projected_table and (
            cell.header_refs != expected
            or ((cell.header_role in ("COLUMN", "BOTH")) != (original.header_role == "COLUMN"))
        ):
            return "UNRESOLVED"
    return source.structure_basis


def reconstruct(response, sources, *, trace=None, projected_tables=frozenset()):
    if trace:
        trace.phase = "GROUNDING"
    output = Output(sources)
    tables = []
    spatial_refs = [t.spatial_table_ref for t in response.tables if t.spatial_table_ref is not None]
    if len(spatial_refs) != len(set(spatial_refs)):
        raise SourceRejection(
            "DUPLICATE_SPATIAL_TABLE", "A spatial partition cannot be reconstructed twice"
        )
    for obs in response.tables:
        if trace:
            trace.phase = "GROUNDING"
        reported = obs.model_dump(mode="json")
        source = next((t for t in sources.layout.tables if t.ref == obs.spatial_table_ref), None)
        if source and source.captions:
            caption = render([lookup(sources)[r] for r in source.captions])
            if obs.title and obs.title.raw_text not in caption:
                raise SourceRejection(
                    "SOURCE_CAPTION_MISMATCH",
                    "Reported title differs from the committed scoped caption",
                )
            used = {c.local_ref for c in obs.cells} | {n.local_ref for n in obs.notes}
            ref = obs.title.local_ref if obs.title else "source_caption"
            while ref in used:
                ref += "_"
            title = EnrichedTableText.model_validate(
                dict(
                    local_ref=ref,
                    raw_text=caption,
                    anchors=[
                        dict(source_ref="spatial_readings", reading_refs=list(source.captions))
                    ],
                    ambiguous=obs.title.ambiguous if obs.title else False,
                    ambiguity_reason=obs.title.ambiguity_reason if obs.title else None,
                )
            )
            obs = obs.model_copy(update={"title": title})
        basis = _admit(sources, obs, projected_table=obs.local_ref in projected_tables)
        tid = identifier(sources, "table", obs.local_ref)
        items, cells = {}, []
        source = next((t for t in sources.layout.tables if t.ref == obs.spatial_table_ref), None)
        aliases = lookup(sources)
        for cell in obs.cells:
            ordered_refs = None
            if basis not in ("UNRESOLVED", "VISUAL_REPORTED"):
                ordered_refs = next(
                    c.readings for c in source.cells if c.ref == cell.spatial_cell_ref
                )
            value = ground(
                sources,
                cell,
                full_line=basis in ("UNRESOLVED", "VISUAL_REPORTED"),
                table_id=tid,
                cell_id=cell.local_ref,
                structure=basis,
                ordered_refs=ordered_refs,
            )
            if cell.state == "UNREADABLE" and cell.raw_text is None and value.readings:
                raise SourceRejection(
                    "UNREADABLE_CELL_HAS_TEXT",
                    "Entirely unreadable cells cannot acquire source text",
                )
            if basis not in ("UNRESOLVED", "VISUAL_REPORTED"):
                original = next(c for c in source.cells if c.ref == cell.spatial_cell_ref)
                # Use M3's supported order, rather than font-top sorting or model alias order.
                ordered = [aliases[r] for r in original.readings]
                from powerforge_extraction.enriched_grounding import reading_evidence

                evidence = (
                    tuple(
                        reading_evidence(
                            sources, r, table_id=tid, cell_id=cell.local_ref, structure=basis
                        )
                        for r in ordered
                    )
                    or value.evidence
                )
            else:
                evidence = value.evidence
            items[cell.local_ref] = evidence
            for e in evidence:
                output.evidence[e.id] = e
            cells.append(
                EnrichedTableCell(
                    id=cell.local_ref,
                    row=cell.row,
                    column=cell.column,
                    row_span=cell.row_span,
                    column_span=cell.column_span,
                    text=cell.raw_text or "",
                    is_header=cell.header_role != "NONE",
                    location=evidence[0].location,
                )
            )
        scoped = set()
        for text in [*obs.notes, *([obs.title] if obs.title else [])]:
            admitted = ground(sources, text, full_line=True, table_id=tid, structure=basis)
            items[text.local_ref] = admitted.evidence
            output.evidence.update({e.id: e for e in admitted.evidence})
            refs = {r for a in text.anchors for r in a.reading_refs}
            if basis == "VISUAL_REPORTED" or (
                text is obs.title and source and refs == set(source.captions)
            ):
                scoped.add(text.local_ref)
        all_evidence = [e for values in items.values() for e in values]
        if not all_evidence:
            raise SourceRejection(
                "TABLE_WITHOUT_EVIDENCE", "A reconstructed table requires actual source evidence"
            )
        if trace:
            trace.observe("GROUNDING_ADMITTED", obs, reason=basis)
            trace.phase = "CONVERSION"
        table = EnrichedTableInput(
            id=tid,
            table_kind=obs.proposed_kind,
            source_locations=[all_evidence[0].location],
            evidence_ids=[e.id for e in all_evidence],
            layout=EnrichedTableLayout(
                title=obs.title.raw_text if obs.title else None,
                rows=obs.rows,
                columns=obs.columns,
                cells=cells,
                metadata=dict(
                    version="enriched-table-metadata-v1",
                    observation=obs.model_dump(mode="json"),
                    reported_observation=reported,
                    structure_basis=basis,
                    printed_text_independently_verified=False,
                    prepared_result_id=str(sources.prepared.id),
                    spatial_result_id=str(sources.layout.id),
                    cell_evidence_ids={ref: [str(e.id) for e in es] for ref, es in items.items()},
                    scoped=sorted(scoped),
                ),
            ),
        )
        if trace:
            trace.observe("RECONSTRUCTED_TABLES", obs, candidate=table)
        tables.append(
            SimpleNamespace(
                observation=obs,
                table_id=tid,
                kind=obs.proposed_kind,
                basis=basis,
                scoped=frozenset(scoped),
                items=items,
            )
        )
        output_tables = getattr(output, "tables", [])
        output.tables = [*output_tables, table]
    if trace:
        trace.phase = "CONVERSION"
    result = output.result(tables=getattr(output, "tables", []))
    return result, TableContext(tuple(tables), result)


def interpret(response, sources, context, *, trace=None):
    if trace:
        trace.phase = "GROUNDING"
    output = Output(sources)
    output.existing_evidence = {e.id for e in context.output.evidence}
    tables = {t.observation.local_ref: t for t in context.tables}
    claims = {c.local_ref: c for c in response.equipment}
    if len(claims) != len(response.equipment):
        raise ValueError("Duplicate equipment alias")
    scopes = {}
    for claim in response.equipment:
        table = tables.get(claim.table_ref)
        if table is None or any(r not in table.items for r in claim.source_refs):
            raise SourceRejection(
                "UNAVAILABLE_TABLE_SOURCE_ALIAS", "Equipment references uncommitted table/cells"
            )
        scope, _ = _scope(table, claim)
        scopes.setdefault((claim.table_ref, scope), set()).add(
            (claim.raw_expression, claim.observed_tag, claim.observed_name)
        )
    mentions, seen = {}, set()
    for claim in response.equipment:
        if trace:
            trace.phase = "GROUNDING"
        table = tables[claim.table_ref]
        scope, cells = _scope(table, claim)
        passages = [c.raw_text for c in cells]
        support = []
        caption_conflict = False
        type_uncertain = False
        if table.observation.title and table.observation.title.local_ref in table.scoped:
            passages.append(table.observation.title.raw_text)
            support.extend(table.items[table.observation.title.local_ref])
            caption_conflict = any(
                tag not in claim.raw_expression
                for tag in re.findall(
                    r"\b[A-Za-z][A-Za-z0-9]*[-_]\d[\w-]*\b", table.observation.title.raw_text
                )
            )
        if not cells and not (
            table.observation.title and table.observation.title.local_ref in claim.source_refs
        ):
            if trace:
                trace.observe("GROUNDING_REJECTED", claim, reason="UNSUPPORTED_TABLE_SCOPE")
            output.count("rejected_source_fields")
            continue
        for cell in table.observation.cells:
            if (
                cells
                and (cell.row == cells[0].row or table.kind == "ATTRIBUTE_ROWS")
                and any(
                    h.raw_text.lower() in {"type", "equipment type", "device type"}
                    for h in headers(table, cell)
                )
            ):
                passages.append(cell.raw_text or "")
                support.extend(table.items[cell.local_ref])
                from powerforge_extraction import interpretation_v1 as v1

                type_uncertain |= (
                    cell.ambiguous
                    or cell.state != "VALUE"
                    or v1._equipment_type(cell.raw_text or "") is None
                    or any(h.ambiguous for h in headers(table, cell))
                )
                type_uncertain |= any(
                    tag not in claim.raw_expression
                    for tag in re.findall(
                        r"(?<![\w-])[A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*(?![\w-])",
                        cell.raw_text or "",
                    )
                )
        if trace:
            trace.observe("GROUNDING_ADMITTED", claim)
            trace.phase = "INTERPRETATION"
        result = equipment_meaning(
            claim,
            passages,
            uncertain=scope is None
            or caption_conflict
            or type_uncertain
            or len(scopes[claim.table_ref, scope]) != 1
            or any(c.ambiguous for c in cells)
            or any(
                e.location.structure_basis == "UNRESOLVED"
                for c in cells
                for e in table.items[c.local_ref]
            )
            or bool(table.observation.title and table.observation.title.ambiguous),
        )
        if result.rejected:
            if trace:
                trace.observe("INTERPRETATION_REJECTED", claim, reason=result.reason_code)
            output.count("rejected_source_fields")
            continue
        primary = [e for c in cells for e in table.items[c.local_ref]] or support
        key = "equipment/" + identity_hash(
            [
                str(table.table_id),
                scope,
                claim.raw_expression,
                claim.observed_tag,
                claim.observed_name,
            ]
        )
        if key in seen:
            if trace:
                trace.observe("DUPLICATE_OBSERVATIONS", claim, reason="DUPLICATE_SOURCE_ASSERTION")
            mentions[claim.local_ref] = mentions[
                next(
                    k
                    for k, v in mentions.items()
                    if v[0].id == identifier(sources, "candidate", key)
                )
            ]
            continue
        seen.add(key)
        group = identifier(sources, "group", key) if scope else None
        if trace:
            trace.phase = "CONVERSION"
        c = candidate(
            sources,
            key,
            result,
            primary,
            equipment=True,
            group=group,
            diagnostics=dict(table_id=str(table.table_id), structure_basis=table.basis),
        )
        if trace:
            trace.observe(
                c.mapping_status,
                claim,
                reason=c.reason_code,
                candidate=c,
                association="TABLE_SCOPE" if c.source_group_id else "NONE",
            )
        output.candidates.append(c)
        if group:
            output.groups.append(
                SourceGroupInput(
                    id=group,
                    local_key=key,
                    equipment_type_hint=result.equipment_type_key,
                    tag_text=claim.observed_tag,
                    evidence_ids=[e.id for e in [*primary, *support]],
                )
            )
        output.cite(c, primary, support)
        mentions[claim.local_ref] = (
            c,
            result,
            scope,
            table,
            "\n".join([claim.raw_expression, *passages]),
        )
    for claim in response.attributes:
        if trace:
            trace.phase = "GROUNDING"
        table = tables.get(claim.table_ref)
        if table is None:
            raise SourceRejection(
                "UNAVAILABLE_TABLE_SOURCE_ALIAS", "Attribute references uncommitted table"
            )
        cell = next(
            (c for c in table.observation.cells if c.local_ref == claim.value_cell_ref), None
        )
        if cell is None or cell.state == "BLANK" or cell.raw_text is None:
            raise SourceRejection(
                "UNAVAILABLE_VALUE_CELL", "Attribute requires a readable committed value cell"
            )
        hs = headers(table, cell)
        if any(
            r not in {h.local_ref for h in hs} | table.scoped
            for r in [*claim.label_refs, *claim.unit_refs, *claim.qualifier_refs]
        ):
            if trace:
                trace.observe("GROUNDING_REJECTED", claim, reason="UNSUPPORTED_TABLE_SCOPE")
            output.count("rejected_source_fields")
            continue
        mention = mentions.get(claim.equipment_ref)
        reported = str(mention[0].id) if mention else None
        if claim.equipment_ref and claim.equipment_ref not in claims:
            raise SourceRejection("UNAVAILABLE_EQUIPMENT_ALIAS", "Unknown equipment alias")
        scope = f"row:{cell.row}" if table.kind == "EQUIPMENT_ROWS" else "spec"
        if mention and (
            mention[2] != scope or mention[3].table_id != table.table_id or cell.row_span != 1
        ):
            mention = None
        if reported and not mention:
            if trace:
                trace.observe("DETACHED_ASSOCIATIONS", claim, reason="OUTSIDE_EQUIPMENT_SCOPE")
            output.count("detached_associations")
        if trace:
            trace.observe("GROUNDING_ADMITTED", claim)
            trace.phase = "INTERPRETATION"
        result = attribute_meaning(
            claim,
            cell,
            [h.raw_text for h in hs],
            mention[1] if mention else None,
            mention[4] if mention else "",
            uncertain=table.basis == "UNRESOLVED"
            or table.observation.ambiguous
            or table.observation.truncated
            or any(h.ambiguous for h in hs),
            notes=[n.raw_text for n in table.observation.notes],
        )
        if result.rejected:
            if trace:
                trace.observe("INTERPRETATION_REJECTED", claim, reason=result.reason_code)
            output.count("rejected_source_fields")
            continue
        key = "attribute/" + identity_hash(
            [
                str(table.table_id),
                cell.local_ref,
                source_reading(claim, cell).identity,
                [h.local_ref for h in hs],
                sorted(claim.qualifier_refs),
                reported,
            ]
        )
        if key in seen:
            if trace:
                trace.observe("DUPLICATE_OBSERVATIONS", claim, reason="DUPLICATE_SOURCE_ASSERTION")
            continue
        seen.add(key)
        primary = table.items[cell.local_ref]
        if trace:
            trace.phase = "CONVERSION"
        c = candidate(
            sources,
            key,
            result,
            primary,
            group=mention[0].source_group_id if mention else None,
            mention=mention[0].id if mention else None,
            diagnostics=dict(table_id=str(table.table_id), structure_basis=table.basis),
        )
        if trace:
            trace.observe(
                c.mapping_status,
                claim,
                reason=c.reason_code,
                candidate=c,
                association="TABLE_SCOPE" if c.source_group_id else "NONE",
            )
        output.candidates.append(c)
        support = [e for h in hs for e in table.items[h.local_ref]]
        support += [e for ref in table.scoped for e in table.items[ref]]
        if mention:
            support += [
                e
                for es in table.items.values()
                for e in es
                for link in output.links
                if link.candidate_id == mention[0].id and link.evidence_id == e.id
            ]
        output.cite(c, primary, support)
    if trace:
        trace.phase = "CONVERSION"
    return output.result()
