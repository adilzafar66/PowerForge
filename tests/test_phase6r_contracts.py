"""Exercise the v1 contracts against the existing native source pipeline."""

import json
from pathlib import Path

import pytest

from powerforge_document_processing.layout_readings import selected_readings
from powerforge_engineering_model.enums import EquipmentType
from powerforge_engineering_model.extraction_descriptions import DESCRIPTION_VERSION
from powerforge_engineering_model.registry_v1 import REGISTRY
from powerforge_extraction.phase6r_contracts import (
    MAX_RESPONSE_BYTES,
    VERSION,
    AttributeRequest,
    PinnedPageContext,
    RecognitionRequest,
    attribute_catalog,
    contract_hash,
    equipment_catalog,
    parse_response,
    validate_request,
)
from spatial_layout_support import derive, prepare_pdf, sources

FIXTURE = Path("evals/tables/v1/sources/positioned_schedule.pdf")


@pytest.fixture
def recognition_request():
    prepared = prepare_pdf(FIXTURE.read_bytes())
    layout, projection = derive(prepared)
    geometry, text = sources(prepared)
    readings, _ = selected_readings(prepared.manifest, geometry, text)
    by_support = {reading.model.preferred: reading for reading in readings}
    image = next(
        artifact
        for artifact in prepared.manifest.base_artifacts
        if artifact.role == "ANALYSIS_IMAGE"
    )
    page = PinnedPageContext(
        source_sha256=prepared.manifest.original.sha256,
        page_image_id=image.id,
        image_sha256=image.sha256,
        image_bytes=image.size_bytes,
        image_width=image.width_px,
        image_height=image.height_px,
        preparation_sha256=prepared.manifest.identity_hash,
        layout_sha256=layout.identity_hash,
        layout=layout,
        readings=tuple(
            {
                "reading_ref": reading.ref,
                "text": by_support[reading.preferred].text,
                "modality": by_support[reading.preferred].kind,
                "alternate_texts": tuple(
                    by_support[member].text
                    for member in reading.members
                    if member != reading.preferred
                ),
            }
            for reading in layout.readings
        ),
    )
    assert projection["tables"]
    return RecognitionRequest(
        version=VERSION,
        stage="EQUIPMENT_RECOGNITION",
        page_context_hash=contract_hash(page),
        page=page,
        registry_version=REGISTRY.registry_version,
        description_version=DESCRIPTION_VERSION,
        equipment_catalog=equipment_catalog(),
    )


def recognition_envelope(request):
    return {
        "version": VERSION,
        "stage": "EQUIPMENT_RECOGNITION",
        "page_context_hash": request.page_context_hash,
        "equipment": [
            {
                "local_ref": f"equipment-{index}",
                "source_description": "Transformer" if index == 0 else "Unknown assembly",
                "registry_type": "TWO_WINDING_TRANSFORMER" if index == 0 else None,
                "tag_state": state,
                "tag": tag,
                "qualification": role,
                "raw_qualification": None,
                "evidence": [],
            }
            for index, (state, tag, role) in enumerate(
                (
                    ("PRESENT", "TX-1", "INSTALLED"),
                    ("ABSENT", None, "UNKNOWN"),
                    ("UNREADABLE", None, "SPARE"),
                    ("AMBIGUOUS", "TX-?", "REFERENCE"),
                )
            )
        ],
    }


def test_unified_projection_and_exact_prerequisite(recognition_request):
    request = recognition_request
    validate_request(request)
    assert set(item.key for item in request.equipment_catalog) == set(EquipmentType)
    upstream = parse_response(request, json.dumps(recognition_envelope(request)).encode())
    attributes = AttributeRequest(
        version=VERSION,
        stage="ATTRIBUTE_EXTRACTION",
        page_context_hash=request.page_context_hash,
        page=request.page,
        registry_version=request.registry_version,
        upstream_hash=contract_hash(upstream),
        upstream=upstream,
        attribute_catalog=attribute_catalog(upstream),
    )
    validate_request(attributes)
    assert {item.equipment_type for item in attributes.attribute_catalog} == {
        EquipmentType.TWO_WINDING_TRANSFORMER
    }
    definition = next(d for d in attributes.attribute_catalog if d.key == "primary_connection")
    assert "WYE" in definition.allowed_values
    reading = request.page.readings[0].reading_ref
    example = {
        "local_ref": "a1",
        "equipment_ref": "equipment-0",
        "association": "ASSERTED",
        "raw_label": "Primary connection",
        "raw_value": "Star",
        "raw_unit": None,
        "qualifiers": [],
        "value_form": "SINGLE",
        "attribute_key": "primary_connection",
        "proposed_enum_value": "WYE",
        "evidence": [
            {"kind": "READING", "role": "LABEL", "reading_ref": reading, "quote": None},
            {"kind": "QUOTE", "role": "VALUE", "quote": "Star"},
        ],
    }
    # A foreign owner is recoverable in D. Admission preserves the assertion for review.
    conflict = dict(example, local_ref="a2", equipment_ref="foreign-owner", raw_value="Delta")
    conflict["proposed_enum_value"] = "DELTA"
    raw = {
        key: value
        for key, value in example.items()
        if key not in {"attribute_key", "proposed_enum_value"}
    }
    raw.update(
        local_ref="a3",
        equipment_ref=None,
        association="UNASSIGNED",
        raw_label="Noise level",
        raw_value="45 to 50",
        raw_unit="dB",
        value_form="RANGE",
    )
    payload = {
        "version": VERSION,
        "stage": attributes.stage,
        "page_context_hash": attributes.page_context_hash,
        "upstream_hash": attributes.upstream_hash,
        "attributes": [example, conflict],
        "raw_unmapped": [raw],
    }
    result = parse_response(attributes, json.dumps(payload).encode())
    assert [(a.raw_value, a.proposed_enum_value) for a in result.attributes] == [
        ("Star", "WYE"),
        ("Delta", "DELTA"),
    ]
    assert result.raw_unmapped[0].raw_value == "45 to 50"
    payload["upstream_hash"] = "9" * 64
    with pytest.raises(ValueError, match="prerequisite"):
        parse_response(attributes, json.dumps(payload).encode())


@pytest.mark.parametrize("violation", ["duplicate", "page", "tag", "truncated", "capacity"])
def test_bad_envelopes_fail_closed(recognition_request, violation):
    request = recognition_request
    envelope = recognition_envelope(request)
    if violation == "duplicate":
        envelope["equipment"].append(envelope["equipment"][0])
    elif violation == "page":
        envelope["page_context_hash"] = "8" * 64
    elif violation == "tag":
        envelope["equipment"][0]["tag"] = None
    payload = json.dumps(envelope).encode()
    if violation == "truncated":
        payload = payload[:-1]
    elif violation == "capacity":
        payload = b" " * (MAX_RESPONSE_BYTES + 1)
    with pytest.raises(ValueError):
        parse_response(request, payload)


def test_legend_only_and_unmapped_equipment_leave_no_eligible_catalog(recognition_request):
    request = recognition_request
    envelope = recognition_envelope(request)
    envelope["equipment"][0]["qualification"] = "LEGEND_ONLY"
    upstream = parse_response(request, json.dumps(envelope).encode())
    assert attribute_catalog(upstream) == ()
    assert len(upstream.equipment) == 4


def test_invalid_visual_bounds_are_recoverable_at_localization(recognition_request):
    request = recognition_request
    envelope = recognition_envelope(request)
    envelope["equipment"][0]["evidence"] = [
        {
            "kind": "VISUAL",
            "role": "EQUIPMENT",
            "region": {"x": "0.9", "y": "0.1", "width": "0.2", "height": "0.2"},
            "reported_text": "TX-1",
        }
    ]
    result = parse_response(request, json.dumps(envelope).encode())
    assert result.equipment[0].local_ref == "equipment-0"
    assert result.equipment[0].evidence[0].kind == "VISUAL"
