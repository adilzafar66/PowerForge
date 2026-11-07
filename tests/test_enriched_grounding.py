"""Independent source mutations and conservative meaning under successor contracts."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest

from enriched_pure_support import fake, native_sources, table_interpretation
from powerforge_extraction.enriched_grounding import ground
from powerforge_extraction.enriched_observations import (
    EnrichedAttributeResponse,
    EnrichedEquipmentResponse,
)
from powerforge_extraction.enriched_output import convert_attributes, convert_equipment
from powerforge_extraction.enriched_tables import interpret, reconstruct
from powerforge_extraction.identities import canonical_json
from spatial_layout_support import drawn_table


def prose_pdf(lines):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    for i, line in enumerate(lines):
        page.insert_text((40, 50 + i * 35), line, fontsize=12)
    result = doc.tobytes()
    doc.close()
    return result


def test_native_schedule_reuses_existing_table_meaning_with_explicit_unverified_printed_text():
    sources = native_sources(Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes())
    output, context = reconstruct(fake(sources), sources)
    later, response = table_interpretation(sources, output)
    interpreted = interpret(response, later, context)
    assert [c.mapping_status for c in interpreted.candidates] == ["MAPPED", "MAPPED"]
    value = interpreted.candidates[1]
    assert str(value.numeric_value) == "0.6" and value.unit == "kV"
    assert value.diagnostics["printed_text_independently_verified"] is False
    assert all(
        e.location.enrichment_artifact_id and e.location.page_artifact_id is None
        for e in output.evidence
    )
    assert all(e.location.region for e in output.evidence)
    assert not interpreted.evidence  # Reuse committed reconstruction citations.


def test_prose_geometry_block_maps_and_retains_exact_separate_token_spans():
    source = native_sources(
        prose_pdf(["2-Winding Transformer TX-1", "Secondary Voltage: 600 V"]),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_equipment(fake(source), source)
    assert len(recognized.candidates) == 1 and recognized.candidates[0].mapping_status == "MAPPED"
    later = replace(
        source,
        unit_id=uuid4(),
        unit_key="ATTRIBUTE_EXTRACTION:page:000001",
        stage="ATTRIBUTE_EXTRACTION",
    )
    upstream = canonical_json(
        dict(
            equipment=[
                dict(local_ref=c.diagnostics["source_local_ref"]) for c in recognized.candidates
            ]
        )
    )
    result = convert_attributes(fake(later, upstream), later, recognized)
    assert result.candidates[0].mapping_status == "MAPPED"
    assert result.candidates[0].equipment_mention_candidate_id == recognized.candidates[0].id
    assert result.candidates[0].diagnostics["association"] == "SOURCE_GEOMETRY_BLOCK"
    assert result.candidates[0].diagnostics["text_verified"] is False
    assert all(
        e.source_snippet and e.text_end - e.text_start == len(e.source_snippet)
        for e in result.evidence
    )
    assert not {e.id for e in recognized.evidence} & {e.id for e in result.evidence}


def test_missed_tag_prefixed_competing_header_prevents_prose_attribute_association():
    source = native_sources(
        prose_pdf(
            [
                "2-Winding Transformer TX-1",
                "TX-2: Two-Winding Transformer",
                "Secondary Voltage: 600 V",
            ]
        ),
        "EQUIPMENT_RECOGNITION",
    )
    recognized = convert_equipment(fake(source), source)
    later = replace(
        source,
        unit_id=uuid4(),
        unit_key="ATTRIBUTE_EXTRACTION:page:000001",
        stage="ATTRIBUTE_EXTRACTION",
    )
    upstream = canonical_json(
        dict(
            equipment=[
                dict(local_ref=c.diagnostics["source_local_ref"]) for c in recognized.candidates
            ]
        )
    )
    result = convert_attributes(fake(later, upstream), later, recognized)
    assert result.candidates and all(c.mapping_status == "UNMAPPED" for c in result.candidates)
    assert all(c.equipment_mention_candidate_id is None for c in result.candidates)


def test_equipment_cannot_borrow_tag_outside_its_original_expression():
    source = native_sources(
        prose_pdf(["2-Winding Transformer TX-1 (reference TX-2)"]), "EQUIPMENT_RECOGNITION"
    )
    response = fake(source).model_dump()
    response["equipment"][0].update(
        raw_expression="2-Winding Transformer TX-1", observed_tag="TX-2"
    )
    output = convert_equipment(EnrichedEquipmentResponse.model_validate(response), source)
    assert not output.candidates and output.diagnostic_counts["rejected_source_fields"] == 1


def test_same_value_rows_cannot_swap_occurrences_and_keep_structural_credit():
    source = native_sources(drawn_table(nearby=True))
    response = fake(source)
    table = response.tables[0]
    values = [c for c in table.cells if c.row > 0 and c.column == 1]
    assert values[0].raw_text == values[1].raw_text
    mutated = table.model_copy(
        update={
            "cells": [
                c.model_copy(update={"anchors": values[1].anchors})
                if c.local_ref == values[0].local_ref
                else c
                for c in table.cells
            ]
        }
    )
    altered = response.model_copy(update={"tables": [mutated]})
    output, context = reconstruct(altered, source)
    assert output.tables[0].layout.metadata["structure_basis"] == "UNRESOLVED"
    later, claims = table_interpretation(source, output)
    assert all(c.mapping_status == "UNMAPPED" for c in interpret(claims, later, context).candidates)


def test_one_observation_in_multi_tag_identity_cell_cannot_establish_unique_row():
    source = native_sources(
        drawn_table(rows=[("Equipment", "Secondary (V)"), ("TX-1 / TX-2", "600")], nearby=True)
    )
    output, context = reconstruct(fake(source), source)
    later, response = table_interpretation(source, output)
    assert len(response.equipment) == 1
    result = interpret(response, later, context)
    assert all(c.mapping_status == "UNMAPPED" for c in result.candidates)


def test_unknown_aliases_and_cross_line_prose_assembly_do_not_ground():
    source = native_sources(
        prose_pdf(["2-Winding Transformer TX-1", "Secondary Voltage: 600 V"]),
        "EQUIPMENT_RECOGNITION",
    )
    observation = fake(source).equipment[0]
    unknown = observation.model_copy(
        update={
            "anchors": [observation.anchors[0].model_copy(update={"reading_refs": ["invented"]})]
        }
    )
    with pytest.raises(ValueError, match="unavailable"):
        ground(source, unknown)
    ref = next(r.model.ref for r in source.readings if r.text == "600")
    crossed = observation.model_copy(
        update={
            "anchors": [
                observation.anchors[0].model_copy(
                    update={"reading_refs": [*observation.anchors[0].reading_refs, ref]}
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="crosses"):
        ground(source, crossed)


def test_table_profile_source_aliases_cannot_be_extracted_as_prose():
    source = native_sources(
        Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes(),
        "EQUIPMENT_RECOGNITION",
    )
    title = next(r for r in source.readings if r.text == "TX-1")
    response = EnrichedEquipmentResponse.model_validate(
        dict(
            schema_version="equipment-recognition-schema-v2",
            overflowed=False,
            equipment=[
                dict(
                    local_ref="e",
                    raw_expression="TX-1",
                    observed_tag="TX-1",
                    observed_name=None,
                    proposed_equipment_type=None,
                    ambiguous=False,
                    ambiguity_reason=None,
                    anchors=[dict(source_ref="spatial_readings", reading_refs=[title.model.ref])],
                )
            ],
        )
    )
    assert not convert_equipment(response, source).candidates


def test_af_at_clauses_use_existing_exact_normalization_and_deduplicate_alternate_excerpts():
    from powerforge_extraction.enriched_observations import EnrichedInterpretationResponse

    doc = pymupdf.open(
        stream=drawn_table(rows=[("Equipment", "Rating"), ("CB-1", "400 AF / 250 AT")]),
        filetype="pdf",
    )
    doc[0].insert_text((40, 30), "Thermal Magnetic LV Breaker Schedule", fontsize=12)
    payload = doc.tobytes()
    doc.close()
    source = native_sources(payload)
    output, context = reconstruct(fake(source), source)
    later, response = table_interpretation(source, output)
    table = output.tables[0].layout.metadata["observation"]
    value = next(c for c in table["cells"] if c["row"] == 1 and c["column"] == 1)
    data = response.model_dump()
    data["attributes"] = [
        dict(
            local_ref=f"a{i}",
            table_ref="t0",
            equipment_ref="e0",
            value_cell_ref=value["local_ref"],
            label_refs=value["header_refs"],
            unit_refs=[],
            qualifier_refs=[],
            raw_expression=raw,
            source_label="Rating",
            raw_value=number,
            raw_unit=unit,
            proposed_equipment_type=None,
            proposed_attribute_key=None,
            ambiguous=False,
            ambiguity_reason=None,
        )
        for i, (raw, number, unit) in enumerate(
            (("400 AF", "400", "AF"), ("400", "400", "AF"), ("250 AT", "250", "AT"))
        )
    ]
    result = interpret(EnrichedInterpretationResponse.model_validate(data), later, context)
    attributes = [c for c in result.candidates if c.kind == "ATTRIBUTE_VALUE"]
    assert len(attributes) == 2
    assert {c.attribute_key: str(c.numeric_value) for c in attributes} == {
        "frame_rating": "400",
        "trip_rating": "250",
    }


def test_conditional_values_are_preserved_as_two_distinct_unmapped_readings():
    from powerforge_extraction.enriched_observations import EnrichedInterpretationResponse

    source = native_sources(
        drawn_table(
            rows=[("Equipment", "Secondary (V)"), ("TX-1", "600 V Normal / 480 V Standby")],
            nearby=True,
        )
    )
    output, context = reconstruct(fake(source), source)
    later, response = table_interpretation(source, output)
    value = next(
        c
        for c in output.tables[0].layout.metadata["observation"]["cells"]
        if c["row"] == 1 and c["column"] == 1
    )
    data = response.model_dump()
    data["attributes"] = [
        dict(
            local_ref=f"a{i}",
            table_ref="t0",
            equipment_ref="e0",
            value_cell_ref=value["local_ref"],
            label_refs=value["header_refs"],
            unit_refs=[],
            qualifier_refs=[],
            raw_expression=raw,
            source_label="Secondary (V)",
            raw_value=number,
            raw_unit="V",
            proposed_equipment_type=None,
            proposed_attribute_key=None,
            ambiguous=False,
            ambiguity_reason=None,
        )
        for i, (raw, number) in enumerate((("600 V Normal", "600"), ("480 V Standby", "480")))
    ]
    result = interpret(EnrichedInterpretationResponse.model_validate(data), later, context)
    values = [c for c in result.candidates if c.kind == "ATTRIBUTE_VALUE"]
    assert len(values) == 2 and all(c.mapping_status == "UNMAPPED" for c in values)
    assert {c.raw_value for c in values} == {"600", "480"}


def test_visual_tables_keep_page_grounding_and_never_gain_spatial_text_verification():
    source = native_sources(Path("evals/tables/v1/sources/positioned_schedule.pdf").read_bytes())
    response = fake(source).model_dump()
    table = response["tables"][0]
    table["spatial_table_ref"] = None
    visual = [dict(source_ref="analysis_image", reading_refs=[])]
    table["anchors"] = visual
    table["title"]["anchors"] = visual
    for cell in table["cells"]:
        cell["spatial_cell_ref"] = None
        cell["anchors"] = visual
    response = type(fake(source)).model_validate(response)
    output, context = reconstruct(response, source)
    assert output.tables[0].layout.metadata["structure_basis"] == "VISUAL_REPORTED"
    assert all(e.text_start is None and e.location.region is None for e in output.evidence)
    later, claims = table_interpretation(source, output)
    values = interpret(claims, later, context).candidates
    assert values and all(c.diagnostics["grounding_precision"] == "VISUAL_PAGE" for c in values)
    assert all(c.diagnostics["printed_text_independently_verified"] is False for c in values)


def test_a_gap_cannot_silently_remove_a_qualifier_from_a_prose_field():
    source = native_sources(
        prose_pdf(
            [
                "LV Breaker CB-1",
                "Normally Closed: Yes                          (not verified)",
            ]
        ),
        "ATTRIBUTE_EXTRACTION",
    )
    refs = [r.model.ref for r in source.readings if r.text in ("Normally", "Closed:", "Yes")]
    response = EnrichedAttributeResponse.model_validate(
        dict(
            schema_version="attribute-extraction-schema-v2",
            overflowed=False,
            attributes=[
                dict(
                    local_ref="a",
                    raw_expression="Normally Closed: Yes",
                    anchors=[dict(source_ref="spatial_readings", reading_refs=refs)],
                    equipment_ref=None,
                    source_label="Normally Closed",
                    raw_value="Yes",
                    raw_unit=None,
                    proposed_equipment_type=None,
                    proposed_attribute_key=None,
                    ambiguous=False,
                    ambiguity_reason=None,
                )
            ],
        )
    )
    admitted = ground(source, response.attributes[0])
    assert admitted.uncertain


def test_visual_attribute_cannot_borrow_a_positioned_equipment_association():
    source = native_sources(prose_pdf(["2-Winding Transformer TX-1"]), "EQUIPMENT_RECOGNITION")
    recognition = convert_equipment(fake(source), source)
    assert len(recognition.candidates) == 1
    later = replace(
        source, stage="ATTRIBUTE_EXTRACTION", unit_key="ATTRIBUTE_EXTRACTION:page:000001"
    )
    response = EnrichedAttributeResponse.model_validate(
        {
            "schema_version": "attribute-extraction-schema-v2",
            "overflowed": False,
            "attributes": [
                {
                    "local_ref": "a0",
                    "raw_expression": "Secondary Voltage: 600 V",
                    "anchors": [{"source_ref": "analysis_image", "reading_refs": []}],
                    "equipment_ref": recognition.candidates[0].diagnostics["source_local_ref"],
                    "source_label": "Secondary Voltage",
                    "raw_value": "600",
                    "raw_unit": "V",
                    "proposed_equipment_type": None,
                    "proposed_attribute_key": None,
                    "ambiguous": False,
                    "ambiguity_reason": None,
                }
            ],
        }
    )
    candidate = convert_attributes(response, later, recognition).candidates[0]
    assert candidate.mapping_status == "UNMAPPED"
    assert candidate.equipment_mention_candidate_id is None


def test_omitted_caption_cannot_hide_a_source_qualifier():
    doc = pymupdf.open(
        stream=drawn_table(
            rows=[
                ("Equipment", "Secondary (V)"),
                ("2-Winding Transformer TX-1", "600"),
            ]
        ),
        filetype="pdf",
    )
    doc[0].insert_text((40, 30), "Transformer Schedule (not verified)", fontsize=12)
    payload = doc.tobytes()
    doc.close()
    source = native_sources(payload)
    response = fake(source)
    proposal = response.tables[0].model_copy(update={"title": None})
    output, context = reconstruct(response.model_copy(update={"tables": [proposal]}), source)
    assert output.tables[0].layout.title == "Transformer Schedule (not verified)"
    later, claims = table_interpretation(source, output)
    values = interpret(claims, later, context).candidates
    assert values and all(c.mapping_status == "UNMAPPED" for c in values)
