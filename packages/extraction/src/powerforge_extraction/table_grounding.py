"""Exact pinned table source admission and reconstruction output. No ORM/provider I/O."""

from dataclasses import dataclass, replace
from importlib.resources import files
from uuid import UUID, uuid5

from powerforge_extraction.contracts import (
    EvidenceInput,
    TableCell,
    TableInput,
    TableLayout,
    WorkUnitOutput,
)
from powerforge_extraction.grounding import PageSources, PageSpec, grounding_identity, occurrences
from powerforge_extraction.identities import content_hash, identity_hash
from powerforge_extraction.interpretation import interpretation_identity
from powerforge_extraction.table_layout import (
    CellReliability,
    TableSourceMetadata,
    inspect_layout,
    layout_identity,
)
from powerforge_extraction.table_observations import TableObservation, TableReconstructionResponse
from powerforge_extraction.table_stages import get_table_stage
from powerforge_provenance.locations import SourceLocation

VERSION = "table-grounding-interpretation-v1"


def table_identity():
    root = files("powerforge_extraction")
    return {
        "version": VERSION,
        "rules_hash": identity_hash(
            {
                name: content_hash(root.joinpath(name).read_text())
                for name in (
                    "table_grounding.py",
                    "table_semantics.py",
                    "table_output.py",
                    "table_sources.py",
                )
            }
        ),
        "layout": layout_identity(),
        "source_rules": grounding_identity(),
        "meaning_rules": interpretation_identity(),
    }


def identifier(spec: PageSpec, kind: str, ref: str) -> UUID:
    return uuid5(spec.run_id, f"{spec.unit_key}/{kind}/{ref}")


@dataclass(frozen=True)
class AdmittedTable:
    observation: TableObservation
    table_id: UUID
    kind: str
    basis: str
    scoped: frozenset[str]
    items: dict[str, tuple[EvidenceInput, ...]]


@dataclass(frozen=True)
class TableContext:
    spec: PageSpec
    reconstruction_unit_id: UUID
    tables: tuple[AdmittedTable, ...]
    output: WorkUnitOutput


def _fields(line: str, width: int):
    delimiter = "\t" if "\t" in line else "|" if "|" in line else None
    if delimiter is None:
        return None
    fields, offsets, at = line.split(delimiter), [], 0
    for part in fields:
        offsets.append(at)
        at += len(part) + 1
    if (
        delimiter == "|"
        and len(fields) == width + 2
        and not fields[0].strip()
        and not fields[-1].strip()
    ):
        fields, offsets = fields[1:-1], offsets[1:-1]
    return (fields, offsets) if len(fields) == width else None


def _positions(text, anchor, window=None):
    if window is None:
        return occurrences(text, anchor.quote, anchor.prefix, anchor.suffix)
    found, start = [], max(0, window[0])
    while (position := text.find(anchor.quote, start, window[1])) >= 0:
        end = position + len(anchor.quote)
        if (anchor.prefix is None or text.endswith(anchor.prefix, 0, position)) and (
            anchor.suffix is None or text.startswith(anchor.suffix, end)
        ):
            found.append(position)
            if len(found) == 2:
                break
        start = position + 1
    return found


def _grid(table: TableObservation, text: str):
    """Exact dense delimiter windows only. Cell token matches do not prove this grid."""
    height, width = len(table.rows), len(table.columns)
    if (
        width < 2
        or len(table.cells) != height * width
        or any(c.row_span != 1 or c.column_span != 1 or c.raw_text is None for c in table.cells)
    ):
        return None
    cells = {(c.row, c.column): c for c in table.cells}
    lines = text.splitlines(keepends=True)
    starts, at = [], 0
    for line in lines:
        starts.append(at)
        at += len(line)
    matches = []
    for first in range(len(lines) - height + 1):
        spans = {}
        for row in range(height):
            line = lines[first + row].rstrip("\r\n")
            parsed = _fields(line, width)
            if parsed is None:
                break
            fields, offsets = parsed
            for col in range(width):
                field, cell = fields[col], cells[row, col]
                if field.strip(" ") != cell.raw_text:
                    break
                left = starts[first + row] + offsets[col] + len(field) - len(field.lstrip(" "))
                spans[cell.local_ref] = (left, left + len(cell.raw_text))
            else:
                continue
            break
        else:
            scoped = set()
            top = starts[first]
            end = starts[first + height - 1] + len(lines[first + height - 1].rstrip("\r\n"))
            if table.title and first and lines[first - 1].rstrip("\r\n") == table.title.raw_text:
                scoped.add(table.title.local_ref)
                top = starts[first - 1]
                spans[table.title.local_ref] = (top, top + len(table.title.raw_text))
            following = first + height
            for note in table.notes:
                if following < len(lines) and lines[following].rstrip("\r\n") == note.raw_text:
                    scoped.add(note.local_ref)
                    spans[note.local_ref] = (
                        starts[following],
                        starts[following] + len(note.raw_text),
                    )
                    end = starts[following] + len(note.raw_text)
                    following += 1
            # Native table anchors must select this window/caption, not another occurrence.
            if all(
                any(top <= p and p + len(a.quote) <= end for p in _positions(text, a, (top, end)))
                for a in table.anchors
                if a.kind == "NATIVE_TEXT"
            ):
                matches.append((spans, frozenset(scoped), (top, end)))
                if len(matches) == 2:
                    return None
    return matches[0] if len(matches) == 1 else None


def _evidence(sources, tid, ref, anchors, raw, cell_id=None, span=None, window=None):
    result = []
    native = [a for a in anchors if a.kind == "NATIVE_TEXT"]
    for index, anchor in enumerate(anchors):
        role = anchor.source_ref
        artifact = sources.artifact(role)
        start = end = snippet = None
        if anchor.kind == "NATIVE_TEXT":
            search = (
                (max(0, span[1] - len(anchor.quote)), span[0] + len(anchor.quote))
                if span and raw
                else window
            )
            positions = _positions(sources.text or "", anchor, search)
            if not positions or raw not in (None, "") and raw not in anchor.quote:
                raise ValueError("Table source text is not in its pinned anchor")
            if span is not None and raw:
                positions = [
                    p for p in positions if p <= span[0] and span[1] <= p + len(anchor.quote)
                ]
                if not positions:
                    raise ValueError("Cell anchor selects a different source occurrence")
            snippet = anchor.quote
            if len(positions) == 1:
                start, end = positions[0], positions[0] + len(snippet)
        evidence = EvidenceInput(
            id=identifier(sources.spec, "evidence", f"{tid}/{ref}/{index}"),
            location=SourceLocation(
                document_page_id=sources.spec.page_id, page_artifact_id=artifact.id
            ),
            source_kind="TABLE_CELL"
            if cell_id is not None
            else "NATIVE_TEXT"
            if role == "native_text"
            else "VISUAL_REGION",
            extraction_method="AI_TEXT" if role == "native_text" else "AI_VISION",
            source_snippet=snippet,
            text_start=start,
            text_end=end,
            offset_convention="UNICODE_CODEPOINT" if start is not None else None,
            table_id=tid,
            cell_id=cell_id,
        )
        result.append(evidence)
    # Never use an image to rescue an invalid native anchor.
    if native:
        result.sort(key=lambda e: e.source_snippet is None)
    return tuple(result)


def convert_table_reconstruction(response, sources: PageSources) -> WorkUnitOutput:
    if sources.spec.stage != "TABLE_RECONSTRUCTION":
        raise ValueError("Reconstruction requires its planned page stage")
    response = get_table_stage(sources.spec.stage).validate_result(
        response, available_sources=[a.role for a in sources.spec.artifacts]
    )
    tables, evidence, rejected = [], [], 0
    identity = table_identity()
    for observation in response.tables:
        tid = identifier(sources.spec, "table", observation.local_ref)
        try:
            grid = _grid(observation, sources.text) if sources.text is not None else None
            visual = any(a.kind == "VISUAL_PAGE" for a in observation.anchors)
            basis = "NATIVE_DELIMITED" if grid else "VISUAL_REPORTED" if visual else "UNRESOLVED"
            spans, scoped, window = grid if grid else ({}, frozenset(), None)
            if visual and not grid:
                scoped = frozenset(
                    [n.local_ref for n in observation.notes]
                    + ([observation.title.local_ref] if observation.title else [])
                )
            items = {}
            table_evidence = _evidence(
                sources, tid, "table", observation.anchors, None, window=window
            )
            for item in [
                *observation.cells,
                *observation.notes,
                *([observation.title] if observation.title else []),
            ]:
                is_cell = hasattr(item, "state")
                items[item.local_ref] = _evidence(
                    sources,
                    tid,
                    item.local_ref,
                    item.anchors,
                    item.raw_text,
                    item.local_ref if is_cell else None,
                    spans.get(item.local_ref),
                )
            reliability = TableSourceMetadata(
                version="table-source-metadata-v1",
                structure_basis=basis,
                structure_evidence_ids=[e.id for e in table_evidence]
                if basis != "UNRESOLVED"
                else [],
                cells=[
                    CellReliability(
                        cell_ref=c.local_ref,
                        state=c.state,
                        header_role=c.header_role,
                        header_refs=list(c.header_refs),
                        text_basis="UNVERIFIED"
                        if c.raw_text in (None, "")
                        else "NATIVE_VERIFIED"
                        if any(e.source_snippet for e in items[c.local_ref])
                        else "VISUAL_REPORTED",
                        evidence_ids=[e.id for e in items[c.local_ref]],
                    )
                    for c in observation.cells
                ],
            )
            hint = inspect_layout(observation).orientation_hint
            tables.append(
                TableInput(
                    id=tid,
                    table_kind=hint if basis != "UNRESOLVED" else "UNCLASSIFIED",
                    source_locations=list(
                        {
                            e.location.page_artifact_id: e.location
                            for e in [*table_evidence, *(e for es in items.values() for e in es)]
                        }.values()
                    ),
                    evidence_ids=[e.id for e in table_evidence],
                    layout=TableLayout(
                        title=observation.title.raw_text if observation.title else None,
                        rows=observation.rows,
                        columns=observation.columns,
                        cells=[
                            TableCell(
                                id=c.local_ref,
                                row=c.row,
                                column=c.column,
                                row_span=c.row_span,
                                column_span=c.column_span,
                                text=c.raw_text or "",
                                is_header=c.header_role != "NONE",
                                location=items[c.local_ref][0].location,
                            )
                            for c in observation.cells
                        ],
                        metadata={
                            "producer": identity,
                            "producer_unit_id": str(sources.spec.unit_id),
                            "observation": observation.model_dump(mode="json"),
                            "reliability": reliability.model_dump(mode="json"),
                            "scoped_refs": sorted(scoped),
                            "native_grid_span": list(window) if window else None,
                            "item_evidence": {
                                ref: [str(e.id) for e in es] for ref, es in items.items()
                            },
                            "cell_source_locations": {
                                c.local_ref: [
                                    e.location.model_dump(mode="json") for e in items[c.local_ref]
                                ]
                                for c in observation.cells
                            },
                        },
                    ),
                )
            )
            evidence.extend(table_evidence)
            evidence.extend(e for es in items.values() for e in es)
        except ValueError:
            rejected += 1
    return WorkUnitOutput(
        tables=tables,
        evidence=evidence,
        diagnostic_counts={"rejected_ungrounded": rejected} if rejected else {},
    )


def context_from_output(
    sources: PageSources, output: WorkUnitOutput, reconstruction_unit_id: UUID
) -> TableContext:
    """Offline snapshot validation; production callers must use the committed DB loader."""
    if (
        sources.spec.stage != "TABLE_INTERPRETATION"
        or reconstruction_unit_id == sources.spec.unit_id
    ):
        raise ValueError("Table context requires its distinct reconstruction prerequisite")
    parent = replace(
        sources,
        spec=replace(
            sources.spec,
            stage="TABLE_RECONSTRUCTION",
            unit_id=reconstruction_unit_id,
            unit_key=f"TABLE_RECONSTRUCTION:page:{sources.spec.page_number:06d}",
        ),
    )
    response = TableReconstructionResponse(
        schema_version="table-reconstruction-schema-v1",
        overflowed=False,
        tables=[
            TableObservation.model_validate(t.layout.metadata["observation"]) for t in output.tables
        ],
    )
    expected = convert_table_reconstruction(response, parent)

    def keyed(items):
        return {str(i.id): i.model_dump(mode="json") for i in items}

    if (
        len(keyed(output.tables)) != len(output.tables)
        or len(keyed(output.evidence)) != len(output.evidence)
        or (
            keyed(expected.tables) != keyed(output.tables)
            or keyed(expected.evidence) != keyed(output.evidence)
        )
    ):
        raise ValueError("Stored table context differs from pinned reconstruction")
    by_evidence = {str(e.id): e for e in output.evidence}
    tables = tuple(
        AdmittedTable(
            TableObservation.model_validate(t.layout.metadata["observation"]),
            t.id,
            t.table_kind,
            t.layout.metadata["reliability"]["structure_basis"],
            frozenset(t.layout.metadata["scoped_refs"]),
            {
                ref: tuple(by_evidence[eid] for eid in ids)
                for ref, ids in t.layout.metadata["item_evidence"].items()
            },
        )
        for t in output.tables
    )
    return TableContext(sources.spec, reconstruction_unit_id, tables, output)
