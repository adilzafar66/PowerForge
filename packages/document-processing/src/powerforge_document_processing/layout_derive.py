"""Deterministic source-supported layout derivation and versioned table projection."""

import hashlib
import re
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from importlib.resources import files

from powerforge_document_processing.layout_grid import borderless_tables, ruled_tables
from powerforge_document_processing.layout_readings import (
    align_readings,
    height,
    intersect,
    same_baseline,
    selected_readings,
)
from powerforge_provenance.layout_observations import (
    LAYOUT_POLICY,
    ReadingOrder,
    SpatialLayout,
    UnresolvedLayout,
    layout_contract_identity,
)
from powerforge_provenance.spatial_base import canonical_json, identity_hash
from powerforge_provenance.spatial_layout import EnrichmentResultRef


def layout_rules_identity():
    root = files("powerforge_document_processing")
    return identity_hash(
        {
            "contracts": layout_contract_identity(),
            "sources": {
                name: hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest()
                for name in ("layout_readings.py", "layout_grid.py", "layout_derive.py")
            },
        }
    )


def preparation_reference(prepared):
    return EnrichmentResultRef(
        id=prepared.id,
        owner=prepared.owner,
        producer_run_id=prepared.producer_run_id,
        producer_work_unit_id=prepared.producer_work_unit_id,
        result_kind="PREPARED",
        manifest_sha256=prepared.identity_hash,
        producer_sha256=prepared.preparation_sha256,
    )


def _derive(prepared, geometry, text, result_id, run_id, unit_id):
    raw, bodies = selected_readings(prepared, geometry, text)
    readings, overlaps = align_readings(raw, prepared.page_frame.width, prepared.page_frame.height)
    width, page_height = prepared.page_frame.width, prepared.page_frame.height
    tables, unresolved, excluded = ruled_tables(readings, bodies, width, page_height)
    borderless, rejected = borderless_tables(readings, excluded, width, page_height, len(tables))
    tables.extend(borderless)
    unresolved.extend(rejected)
    # A competing overlapping partition removes credit from both proposals.
    bad = set()
    for i, table in enumerate(tables):
        for j in range(i):
            other = tables[j]
            a = (table.region.x, table.region.y, table.region.right, table.region.bottom)
            b = (other.region.x, other.region.y, other.region.right, other.region.bottom)
            if intersect(a, b) > 0:
                bad.update((i, j))
    for i in sorted(bad):
        table = tables[i]
        unresolved.append(
            UnresolvedLayout(
                region=table.region,
                reason="OVERLAPPING_TABLES",
                support=tuple(dict.fromkeys(s for c in table.cells for s in c.boundary_support)),
            )
        )
    tables = [t for i, t in enumerate(tables) if i not in bad]
    if (
        len(tables) > LAYOUT_POLICY["max_tables"]
        or sum(len(t.cells) for t in tables) > LAYOUT_POLICY["max_cells"]
    ):
        raise ValueError("Aggregate table/cell layout bound exceeded")
    lookup = {r.model.ref: r for r in readings}
    edges = set()

    def order(before, after, basis):
        if before != after:
            edges.add((before, after, basis))

    local_lines = {}
    for reading in readings:
        if reading.box and reading.horizontal and not reading.model.issues:
            local_lines.setdefault(reading.engine_line, []).append(reading)
    for line in local_lines.values():
        ordered = sorted(line, key=lambda r: r.box[0])
        for a, b in zip(ordered, ordered[1:], strict=False):
            if same_baseline(a.box, b.box) and 0 <= b.box[0] - a.box[2] <= min(
                height(a.box), height(b.box)
            ) * Decimal("1.5"):
                order(a.model.ref, b.model.ref, "SAME_BASELINE")
    # Only explicit table partitions establish order across source engine lines.
    for table in tables:
        for cell in table.cells:
            values = [lookup[r] for r in cell.readings]
            for a, b in zip(values, values[1:], strict=False):
                if a.box[2] <= b.box[0] and max(a.box[1], b.box[1]) < min(a.box[3], b.box[3]):
                    order(a.model.ref, b.model.ref, "SAME_BASELINE")
        for a in table.cells:
            for b in table.cells:
                if (
                    a.row == b.row
                    and a.column + a.column_span == b.column
                    and a.readings
                    and b.readings
                ):
                    left, right = lookup[a.readings[-1]], lookup[b.readings[0]]
                    if same_baseline(left.box, right.box) and left.box[2] <= right.box[0]:
                        order(a.readings[-1], b.readings[0], "TABLE_ROW")
                if (
                    a.column == b.column
                    and a.row + a.row_span == b.row
                    and a.readings
                    and b.readings
                ):
                    if lookup[a.readings[-1]].box[3] <= lookup[b.readings[0]].box[1]:
                        order(a.readings[-1], b.readings[0], "TABLE_COLUMN")
    # Caption scoping requires a unique nearby title line containing a literal title cue.
    updated = []
    owned_readings = {r for table in tables for cell in table.cells for r in cell.readings}
    for table in tables:
        box = (
            table.region.x * width,
            table.region.y * page_height,
            table.region.right * width,
            table.region.bottom * page_height,
        )
        captions = []
        lines = {}
        for reading in readings:
            if (
                reading.model.ref not in owned_readings
                and reading.box
                and reading.horizontal
                and not reading.model.issues
                and reading.box[3] < box[1]
                and box[0] <= reading.box[0]
                and reading.box[2] <= box[2]
            ):
                lines.setdefault(reading.engine_line, []).append(reading)
        for line in lines.values():
            label = " ".join(r.text for r in sorted(line, key=lambda r: r.box[0])).lower()
            if re.search(r"\b(?:schedule|table)\b", label) is None:
                continue
            bottom = max(r.box[3] for r in line)
            h = max(height(r.box) for r in line)
            if box[1] - bottom > 2 * h:
                continue
            targets = []
            line_box = (
                min(r.box[0] for r in line),
                min(r.box[1] for r in line),
                max(r.box[2] for r in line),
                bottom,
            )
            for candidate in tables:
                bb = (
                    candidate.region.x * width,
                    candidate.region.y * page_height,
                    candidate.region.right * width,
                    candidate.region.bottom * page_height,
                )
                if bb[0] <= line_box[0] and line_box[2] <= bb[2] and 0 < bb[1] - bottom <= 2 * h:
                    targets.append(candidate.ref)
            if targets == [table.ref]:
                captions.extend(r.model.ref for r in sorted(line, key=lambda r: r.box[0]))
        updated.append(table.model_copy(update={"captions": tuple(captions)}))
    return SpatialLayout(
        id=result_id,
        owner=prepared.owner,
        producer_run_id=run_id,
        producer_work_unit_id=unit_id,
        algorithm_sha256=layout_rules_identity(),
        prepared=preparation_reference(prepared),
        readings=tuple(r.model for r in readings),
        overlaps=tuple(overlaps),
        order=tuple(ReadingOrder(before=a, after=b, basis=kind) for a, b, kind in sorted(edges)),
        tables=tuple(updated),
        unresolved=tuple(unresolved),
    )


def derive_layout(prepared, geometry, text, result_id, run_id, unit_id):
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        return _derive(prepared, geometry, text, result_id, run_id, unit_id)


def admit_layout(prepared, geometry, text, layout):
    """Recompute support, partition and header claims; a shape-valid manifest is not proof."""
    layout = SpatialLayout.model_validate(layout)
    expected = derive_layout(
        prepared, geometry, text, layout.id, layout.producer_run_id, layout.producer_work_unit_id
    )
    if expected != layout:
        raise ValueError("Layout does not reproduce from its exact pinned source geometry/readings")
    return layout


def table_context(prepared, geometry, text, layout):
    """Source-local aliases for a future 6D successor. Serialized cells are not source quotes."""
    layout = admit_layout(prepared, geometry, text, layout)
    raw, _ = selected_readings(prepared, geometry, text)
    lookup = {r.model.preferred: r for r in raw}
    clusters = {r.ref: r for r in layout.readings}
    tables = []
    for table in layout.tables:
        cells = []
        for cell in table.cells:
            cells.append(
                dict(
                    ref=cell.ref,
                    row=cell.row,
                    column=cell.column,
                    row_span=cell.row_span,
                    column_span=cell.column_span,
                    region=cell.region.model_dump(mode="json"),
                    state=cell.state,
                    header_role=cell.header_role,
                    headers=list(cell.headers),
                    readings=[
                        dict(
                            ref=ref,
                            raw_text=lookup[clusters[ref].preferred].text,
                            source_kind=lookup[clusters[ref].preferred].kind,
                            raw_engine_confidence=lookup[
                                clusters[ref].preferred
                            ].confidence.model_dump(mode="json")
                            if lookup[clusters[ref].preferred].confidence is not None
                            else None,
                            source_members=[
                                m.model_dump(mode="json") for m in clusters[ref].members
                            ],
                            issues=list(clusters[ref].issues),
                        )
                        for ref in cell.readings
                    ],
                )
            )
        tables.append(
            dict(
                ref=table.ref,
                rows=table.rows,
                columns=table.columns,
                structure_basis=table.structure_basis,
                header_basis=table.header_basis,
                cells=cells,
                captions=[
                    dict(ref=r, raw_text=lookup[clusters[r].preferred].text) for r in table.captions
                ],
            )
        )
    result = dict(
        version="spatial-table-context-v1",
        cell_text="SERIALIZED_READINGS_NOT_A_PRINTED_QUOTE",
        tables=tables,
        printed_text_independently_verified=False,
    )
    if len(canonical_json(result).encode()) > LAYOUT_POLICY["max_projection_bytes"]:
        raise ValueError("Spatial table projection exceeds its independent byte bound")
    return result
