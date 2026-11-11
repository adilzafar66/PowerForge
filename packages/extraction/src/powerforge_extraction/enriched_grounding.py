"""Resolve server-owned occurrences and exact evidence; serialized cells are not quotes."""

import re
from dataclasses import dataclass
from uuid import uuid5

from powerforge_extraction.enriched_contracts import EnrichedEvidence
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.stage_diagnostics import SourceRejection
from powerforge_provenance.enriched_locations import EnrichedLocation
from powerforge_provenance.locations import Region


def identifier(sources, kind, ref):
    return uuid5(sources.run_id, f"{sources.unit_key}/{kind}/{ref}")


def lookup(sources):
    return {r.model.ref: r for r in sources.readings}


def line_groups(sources):
    lines = {}
    for reading in sources.readings:
        if "NATIVE_PREFERRED_UNALIGNED" not in reading.model.issues:
            lines.setdefault(reading.engine_line, []).append(reading)
    edges = {(e.before, e.after) for e in sources.layout.order if e.basis == "SAME_BASELINE"}
    groups = {}
    for key, values in lines.items():
        current = []
        ordered = sorted(values, key=lambda r: (r.box[0] if r.box else 0, r.engine_order))
        for reading in ordered:
            if current and (
                key[1] is None or (current[-1].model.ref, reading.model.ref) not in edges
            ):
                groups[(*key, current[0].model.ref)] = tuple(current)
                current = []
            current.append(reading)
        if current:
            groups[(*key, current[0].model.ref)] = tuple(current)
    return groups


def render(readings):
    return " ".join(r.text for r in readings)


def contains(expression, text):
    return bool(re.search(r"(?<!\w)" + re.escape(expression) + r"(?!\w)", text))


def image_location(sources, structure="VISUAL_REPORTED"):
    return EnrichedLocation(
        document_page_id=sources.prepared.owner.document_page_id,
        page_artifact_id=sources.snapshot.image.id,
        prepared_result_id=sources.prepared.id,
        spatial_result_id=sources.layout.id,
        reading_basis="VISUAL_REPORTED",
        geometry_basis="NONE",
        structure_basis=structure,
    )


def reading_evidence(sources, reading, *, table_id=None, cell_id=None, structure="UNRESOLVED"):
    support = reading.model.preferred
    body = sources.bodies[support.representation_ref]
    token = next(t for t in body.tokens if t.ref == support.ref)
    descriptor = next(
        d for d in sources.prepared.representations if d.ref == support.representation_ref
    )
    region = reading.model.region
    loc = EnrichedLocation(
        document_page_id=sources.prepared.owner.document_page_id,
        enrichment_artifact_id=descriptor.text_artifact.id,
        geometry_artifact_id=descriptor.geometry_artifact.id,
        prepared_result_id=sources.prepared.id,
        spatial_result_id=sources.layout.id,
        region=Region.model_validate(region.model_dump()) if region else None,
        support=(support,),
        raw_engine_confidence=token.confidence,
        reading_basis=body.producer.kind,
        geometry_basis=("NATIVE_DOCUMENT" if body.producer.kind == "NATIVE_PDF" else "OCR_ENGINE")
        if region
        else "NONE",
        structure_basis=structure,
    )
    key = identity_hash(
        dict(
            locator=loc.model_dump(mode="json"), token=token.ref, table=str(table_id), cell=cell_id
        )
    )
    return EnrichedEvidence(
        id=identifier(sources, "evidence", key),
        location=loc,
        source_kind="TABLE_CELL"
        if cell_id
        else "OCR_TEXT"
        if body.producer.kind == "OCR"
        else "NATIVE_TEXT",
        extraction_method="AI_TEXT",
        source_snippet=token.raw_text,
        text_start=token.span.start,
        text_end=token.span.end,
        offset_convention="UNICODE_CODEPOINT",
        table_id=table_id,
        cell_id=cell_id,
    )


@dataclass(frozen=True)
class Grounded:
    statement: str
    readings: tuple
    evidence: tuple
    uncertain: bool
    visual: bool
    line: tuple | None


def ground(
    sources,
    observation,
    *,
    full_line=True,
    table_id=None,
    cell_id=None,
    structure="UNRESOLVED",
    ordered_refs=None,
):
    selected = []
    by_ref = lookup(sources)
    for anchor in observation.anchors:
        for ref in anchor.reading_refs:
            if ref not in by_ref or "NATIVE_PREFERRED_UNALIGNED" in by_ref[ref].model.issues:
                raise SourceRejection(
                    "UNAVAILABLE_READING_ALIAS",
                    "Observation references unavailable source readings",
                )
            if ref not in selected:
                selected.append(ref)
    if not selected:
        if not all(a.source_ref == "analysis_image" for a in observation.anchors):
            raise SourceRejection("NO_ADMITTED_SOURCE", "No admitted source")
        item = EnrichedEvidence(
            id=identifier(
                sources, "visual-evidence", identity_hash(observation.model_dump(mode="json"))
            ),
            location=image_location(sources, structure),
            source_kind="TABLE_CELL" if cell_id else "VISUAL_REGION",
            extraction_method="AI_VISION",
            table_id=table_id,
            cell_id=cell_id,
        )
        raw = getattr(observation, "raw_expression", getattr(observation, "raw_text", None))
        return Grounded(
            raw or "",
            (),
            (item,),
            observation.ambiguous or any(p.kind == "CONFLICT" for p in sources.layout.overlaps),
            True,
            None,
        )
    readings = [by_ref[ref] for ref in selected]
    # Geometry proves in-cell order only in an admitted table. Prose anchors stay in one
    # actual engine line; arbitrary aliases cannot assemble a fabricated source sentence.
    lines = {r.engine_line for r in readings}
    if full_line and len(lines) != 1:
        raise SourceRejection("CROSSES_SOURCE_LINES", "Prose anchor crosses unproved source lines")
    readings.sort(key=lambda r: ((r.box[1] if r.box else 0), (r.box[0] if r.box else 0)))
    if len(lines) == 1:
        readings.sort(key=lambda r: (r.box[0] if r.box else 0, r.engine_order))
    if ordered_refs is not None:
        if set(ordered_refs) != set(selected):
            raise SourceRejection(
                "CELL_READING_MISMATCH", "Reading ownership differs from the supported cell"
            )
        readings = [by_ref[r] for r in ordered_refs]
    raw = getattr(observation, "raw_expression", getattr(observation, "raw_text", None))
    if raw is not None and raw and not contains(raw, render(readings)):
        raise SourceRejection(
            "SOURCE_EXPRESSION_MISMATCH",
            "Original expression is not supported by its selected occurrences",
        )
    line = next(iter(lines)) if len(lines) == 1 else None
    incomplete_line = False
    if full_line:
        all_groups = line_groups(sources)
        groups = [
            (key, row)
            for key, row in all_groups.items()
            if set(selected) <= {r.model.ref for r in row}
        ]
        if len(groups) != 1:
            raise SourceRejection(
                "READING_ORDER_GAP", "Prose anchor crosses unsupported reading-order gaps"
            )
        line, row = groups[0]
        readings = list(row)
        incomplete_line = line[1] is None or sum(key[:2] == line[:2] for key in all_groups) != 1
    evidence = tuple(
        reading_evidence(sources, r, table_id=table_id, cell_id=cell_id, structure=structure)
        for r in readings
    )
    return Grounded(
        render(readings),
        tuple(readings),
        evidence,
        observation.ambiguous or incomplete_line or any(r.model.issues for r in readings),
        False,
        line,
    )


def semantic_observation(observation, model, **updates):
    # Only adapt the frozen interpreter's source-independent shape. Its visual anchor
    # is not evidence, a provider input or an assertion that OCR is native/verified.
    data = observation.model_dump()
    data.pop("spatial_cell_ref", None)
    data["anchors"] = [
        dict(kind="VISUAL_PAGE", source_ref="analysis_image", quote=None, prefix=None, suffix=None)
    ]
    data.update(updates)
    return model.model_validate(data)


def table_readings(sources):
    return {r for t in sources.layout.tables for c in t.cells for r in c.readings} | {
        r for t in sources.layout.tables for r in t.captions
    }
