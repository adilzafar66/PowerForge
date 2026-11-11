"""Compact provider selection with server-owned table cells and exact replay."""

import re
from typing import Literal

from pydantic import Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from powerforge_extraction.enriched_grounding import lookup, render
from powerforge_extraction.enriched_observations import (
    EnrichedCell,
    EnrichedReconstructionResponse,
    EnrichedTable,
)
from powerforge_extraction.enriched_tables import TableContext, reconstruct
from powerforge_extraction.observations import ObservationContract, ObservationResponse
from powerforge_extraction.stage_diagnostics import SourceRejection
from powerforge_extraction.table_observations import MAX_CELLS, MAX_TABLES, TableOrientation
from powerforge_provenance.spatial_base import LocalRef


class PartitionSelection(ObservationContract):
    local_ref: LocalRef
    spatial_table_ref: LocalRef
    proposed_kind: TableOrientation


class ReportedCell(EnrichedCell):
    spatial_cell_ref: None


class ReportedTable(EnrichedTable):
    spatial_table_ref: None
    cells: list[ReportedCell] = Field(min_length=1, max_length=MAX_CELLS)


class CompactReconstructionResponse(ObservationResponse):
    max_response_bytes = 1024 * 1024
    schema_version: Literal["table-reconstruction-schema-v3"]
    partitions: list[PartitionSelection] = Field(max_length=MAX_TABLES)
    reported_tables: list[ReportedTable] = Field(max_length=MAX_TABLES)

    @model_validator(mode="after")
    def bounds(self):
        tables = [*self.partitions, *self.reported_tables]
        if len(tables) > MAX_TABLES or sum(len(t.cells) for t in self.reported_tables) > MAX_CELLS:
            raise PydanticCustomError("table_response_overflow", "Table response exceeds capacity")
        if len({table.local_ref for table in tables}) != len(tables) or len(
            {table.spatial_table_ref for table in self.partitions}
        ) != len(self.partitions):
            raise PydanticCustomError("duplicate_table_alias", "Duplicate table alias")
        return self


def _anchor(refs):
    return [
        {"source_ref": "spatial_readings" if refs else "analysis_image", "reading_refs": list(refs)}
    ]


def _materialize(selection, partition, readings):
    aliases = {cell.ref: f"c{index}" for index, cell in enumerate(partition.cells)}
    kind = selection.proposed_kind
    form = (
        kind == "ATTRIBUTE_ROWS"
        and partition.columns == 2
        and all(cell.row_span == cell.column_span == 1 for cell in partition.cells)
    )
    if kind == "ATTRIBUTE_ROWS" and not form:
        kind = "UNCLASSIFIED"
    labels = {
        cell.row: aliases[cell.ref]
        for cell in partition.cells
        if form and cell.column == 0 and cell.header_role != "COLUMN" and cell.readings
    }
    top = [c for c in partition.cells if c.row == 0]
    first = next((c for c in top if c.column == 0), None)
    derive_columns = (
        kind == "EQUIPMENT_ROWS"
        and first is not None
        and len(top) == partition.columns
        and all(c.readings for c in top)
        and all(c.row_span == c.column_span == 1 for c in partition.cells)
        and not any(c.header_role == "COLUMN" for c in partition.cells)
        and render([readings[ref] for ref in first.readings]).casefold()
        in {"equipment", "device", "equipment tag", "tag"}
        and all(not re.match(r"^\s*[+\-]?\d", readings[c.readings[0]].text) for c in top)
    )
    by_column = {c.column: aliases[c.ref] for c in top} if derive_columns else {}
    cells = []
    for cell in partition.cells:
        role = "COLUMN" if cell.header_role == "COLUMN" else "NONE"
        headers = [aliases[ref] for ref in cell.headers]
        if derive_columns and cell.column_span == 1:
            if cell.row == 0:
                role = "COLUMN"
            else:
                headers = [by_column[cell.column]]
        if form and role == "NONE" and cell.row in labels:
            if cell.column == 0:
                role = "ROW"
            else:
                headers.append(labels[cell.row])
        cells.append(
            dict(
                local_ref=aliases[cell.ref],
                spatial_cell_ref=cell.ref,
                row=cell.row,
                column=cell.column,
                row_span=cell.row_span,
                column_span=cell.column_span,
                state="VALUE" if cell.readings else "BLANK",
                raw_text=render([readings[ref] for ref in cell.readings]),
                header_role=role,
                header_refs=headers,
                anchors=_anchor(cell.readings),
                ambiguous=False,
                ambiguity_reason=None,
            )
        )
    return dict(
        local_ref=selection.local_ref,
        spatial_table_ref=partition.ref,
        proposed_kind=kind,
        rows=[f"r{i}" for i in range(partition.rows)],
        columns=[f"col{i}" for i in range(partition.columns)],
        cells=cells,
        title=None,
        notes=[],
        anchors=_anchor(()),
        truncated=False,
        truncation_reason=None,
        ambiguous=False,
        ambiguity_reason=None,
    )


def reconstruct_compact(response, sources, *, trace=None):
    partitions = {item.ref: item for item in sources.layout.tables}
    if any(item.spatial_table_ref not in partitions for item in response.partitions):
        raise SourceRejection("UNAVAILABLE_SPATIAL_TABLE_ALIAS", "Unknown committed partition")
    if (
        sum(len(partitions[item.spatial_table_ref].cells) for item in response.partitions)
        + sum(len(item.cells) for item in response.reported_tables)
        > MAX_CELLS
    ):
        raise SourceRejection("MATERIALIZED_TABLE_OVERFLOW", "Selected tables exceed capacity")

    readings = lookup(sources)
    expanded = [
        _materialize(item, partitions[item.spatial_table_ref], readings)
        for item in response.partitions
    ]
    try:
        normalized = EnrichedReconstructionResponse.model_validate(
            dict(
                schema_version="table-reconstruction-schema-v2",
                overflowed=False,
                tables=[*expanded, *(item.model_dump() for item in response.reported_tables)],
            )
        )
    except ValidationError:
        raise SourceRejection(
            "INVALID_MATERIALIZED_TABLE",
            "Committed table cannot be projected into the response contract",
        ) from None
    output, context = reconstruct(
        normalized,
        sources,
        trace=trace,
        projected_tables={item["local_ref"] for item in expanded},
    )
    recipes = {
        item.local_ref: {"partition": item.model_dump(mode="json"), "reported_table": None}
        for item in response.partitions
    } | {
        item.local_ref: {"partition": None, "reported_table": item.model_dump(mode="json")}
        for item in response.reported_tables
    }
    tables = []
    for table in output.tables:
        recipe = recipes[table.layout.metadata["observation"]["local_ref"]]
        layout = table.layout.model_copy(
            update={"metadata": {**table.layout.metadata, "reconstruction_recipe_v3": recipe}}
        )
        tables.append(table.model_copy(update={"layout": layout}))
    output = output.model_copy(update={"tables": tables})
    return output, TableContext(context.tables, output)


def compact_response_from_layouts(layouts):
    recipes = [layout["metadata"]["reconstruction_recipe_v3"] for layout in layouts]
    return CompactReconstructionResponse.model_validate(
        dict(
            schema_version="table-reconstruction-schema-v3",
            overflowed=False,
            partitions=[
                recipe["partition"] for recipe in recipes if recipe["partition"] is not None
            ],
            reported_tables=[
                recipe["reported_table"]
                for recipe in recipes
                if recipe["reported_table"] is not None
            ],
        )
    )
