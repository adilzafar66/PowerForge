"""Exercise the v1 contracts against the existing native source pipeline."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from powerforge_document_processing.layout_readings import selected_readings
from powerforge_engineering_model.enums import EquipmentType
from powerforge_engineering_model.extraction_descriptions import DESCRIPTION_VERSION
from powerforge_engineering_model.registry_v1 import REGISTRY
from powerforge_extraction.phase6r_contracts import (
    MAX_REQUEST_BYTES,
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
from spatial_layout_support import derive, drawn_table, prepare_pdf, sources

FIXTURE = Path("evals/tables/v1/sources/positioned_schedule.pdf")


@pytest.fixture
def recognition_request(request):
    data = drawn_table() if getattr(request, "param", False) else FIXTURE.read_bytes()
    prepared = prepare_pdf(data)
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
        owner=prepared.manifest.owner,
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


@pytest.fixture
def attribute_request(recognition_request):
    request = recognition_request
    upstream = parse_response(request, json.dumps(recognition_envelope(request)).encode())
    return AttributeRequest(
        version=VERSION,
        stage="ATTRIBUTE_EXTRACTION",
        page_context_hash=request.page_context_hash,
        page=request.page,
        registry_version=request.registry_version,
        upstream_hash=contract_hash(upstream),
        upstream=upstream,
        attribute_catalog=attribute_catalog(upstream),
    )


@pytest.fixture
def attribute_envelope(attribute_request):
    request = attribute_request
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
    return {
        "version": VERSION,
        "stage": request.stage,
        "page_context_hash": request.page_context_hash,
        "upstream_hash": request.upstream_hash,
        "attributes": [example, conflict],
        "raw_unmapped": [raw],
    }


def test_unified_projection_and_exact_prerequisite(
    recognition_request, attribute_request, attribute_envelope
):
    request = recognition_request
    validate_request(request, expected_owner=request.page.layout.owner)
    assert set(item.key for item in request.equipment_catalog) == set(EquipmentType)
    assert len(request.model_dump_json().encode()) < MAX_REQUEST_BYTES
    attributes = attribute_request
    validate_request(attributes, expected_owner=request.page.layout.owner)
    assert {item.equipment_type for item in attributes.attribute_catalog} == {
        EquipmentType.TWO_WINDING_TRANSFORMER
    }
    definition = next(d for d in attributes.attribute_catalog if d.key == "primary_connection")
    assert "WYE" in definition.allowed_values
    payload = attribute_envelope
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
    with pytest.raises(ValueError) as error:
        parse_response(request, payload)
    if violation != "truncated":
        assert (
            error.value.issue.error_type
            == {
                "duplicate": "duplicate_reference",
                "page": "page_identity_mismatch",
                "tag": "invalid_tag_state",
                "capacity": "response_byte_limit",
            }[violation]
        )


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


@pytest.mark.parametrize("stage_fixture", ["recognition_request", "attribute_request"])
@pytest.mark.parametrize(
    "field", ["document_id", "document_page_id", "processing_run_id", "page_number"]
)
def test_request_rejects_foreign_owner_even_with_recomputed_hash(request, stage_fixture, field):
    stage_request = request.getfixturevalue(stage_fixture)
    expected_owner = stage_request.page.layout.owner
    foreign_owner = expected_owner.model_copy(
        update={field: 2 if field == "page_number" else uuid4()}
    )
    foreign_page = stage_request.page.model_copy(update={"owner": foreign_owner})
    tampered = stage_request.model_copy(
        update={"page": foreign_page, "page_context_hash": contract_hash(foreign_page)}
    )
    with pytest.raises(ValueError, match="ownership"):
        validate_request(tampered, expected_owner=expected_owner)


def test_layout_owner_must_match_the_authorized_page(recognition_request):
    owner = recognition_request.page.owner
    layout = recognition_request.page.layout.model_copy(
        update={
            "owner": owner.model_copy(update={"document_page_id": uuid4()}),
        }
    )
    page = recognition_request.page.model_copy(
        update={"layout": layout, "layout_sha256": layout.identity_hash}
    )
    tampered = recognition_request.model_copy(
        update={"page": page, "page_context_hash": contract_hash(page)}
    )
    with pytest.raises(ValueError, match="ownership"):
        validate_request(tampered, expected_owner=owner)


def test_attribute_request_rejects_recognition_from_another_page(attribute_request):
    upstream = attribute_request.upstream.model_copy(update={"page_context_hash": "9" * 64})
    tampered = attribute_request.model_copy(
        update={
            "upstream": upstream,
            "upstream_hash": contract_hash(upstream),
        }
    )
    with pytest.raises(ValueError, match="prerequisite"):
        validate_request(tampered, expected_owner=attribute_request.page.owner)


@pytest.mark.parametrize("collection", ["attributes", "raw_unmapped"])
def test_duplicate_attribute_refs_reject_entire_response(
    attribute_request, attribute_envelope, collection
):
    attribute_envelope[collection][-1]["local_ref"] = attribute_envelope["attributes"][0][
        "local_ref"
    ]
    with pytest.raises(ValueError, match="duplicate observation reference"):
        parse_response(attribute_request, json.dumps(attribute_envelope).encode())


def test_unsupported_equipment_type_rejects_enum_outside_catalog(recognition_request):
    envelope = recognition_envelope(recognition_request)
    envelope["equipment"][0]["registry_type"] = "UNSUPPORTED_ASSEMBLY"
    with pytest.raises(ValueError, match="registry_type"):
        parse_response(recognition_request, json.dumps(envelope).encode())


def test_admission_preserves_assertions_for_deferred_publication_checks(
    attribute_request, attribute_envelope
):
    missing_unit, unsupported = attribute_envelope["attributes"]
    missing_unit.update(
        attribute_key="secondary_voltage",
        raw_value="600",
        proposed_enum_value=None,
        raw_unit=None,
        qualifiers=["At startup"],
        value_form="QUALIFIED",
        evidence=[{"kind": "QUOTE", "role": "VALUE", "quote": "600"}],
    )
    unsupported.update(
        equipment_ref="foreign-owner",
        attribute_key="unregistered_key",
        proposed_enum_value="UNSUPPORTED_ENUM",
    )
    result = parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    missing_unit, unsupported = result.attributes
    assert missing_unit.raw_unit is None
    assert missing_unit.raw_value == "600"
    assert missing_unit.value_form == "QUALIFIED"
    assert missing_unit.qualifiers == ("At startup",)
    assert missing_unit.evidence[0].quote == "600"
    assert unsupported.equipment_ref == "foreign-owner"
    assert unsupported.attribute_key == "unregistered_key"
    assert unsupported.proposed_enum_value == "UNSUPPORTED_ENUM"


@pytest.mark.parametrize("recognition_request", [True], indirect=True)
def test_admission_keeps_ambiguous_quote_for_localization(attribute_request, attribute_envelope):
    assert sum(reading.text == "600" for reading in attribute_request.page.readings) == 2
    attribute_envelope["attributes"][0]["evidence"] = [
        {"kind": "QUOTE", "role": "VALUE", "quote": "600"}
    ]
    result = parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    (citation,) = result.attributes[0].evidence
    assert citation.kind == "QUOTE"
    assert citation.quote == "600"


def test_gold_schedule_references_pinned_native_source():
    case = json.loads(Path("evals/phase6r/positioned-schedule.gold.json").read_text())
    assert case["source"] == FIXTURE.as_posix()
    source = FIXTURE.read_bytes()
    assert hashlib.sha256(source).hexdigest() == case["sha256"]
    prepared = prepare_pdf(source)
    _, texts = sources(prepared)
    by_digest = {hashlib.sha256(raw).hexdigest(): raw.decode() for raw in texts.values()}
    (page,) = case["pages"]
    assert page["page_number"] == prepared.manifest.owner.page_number
    observations = page["equipment"] + page["attributes"]
    assert len({item["id"] for item in observations}) == len(observations)
    equipment_ids = {item["id"] for item in page["equipment"]}
    for attribute in page["attributes"]:
        assert attribute["equipment_id"] in equipment_ids
    for observation in observations:
        for evidence in observation["evidence"]:
            text = by_digest[evidence["text_artifact_sha256"]]
            start, end = evidence["span"]
            assert 0 <= start < end <= len(text)
            assert text[start:end] == evidence["source_text"]


def test_attribute_response_reports_upstream_identity_mismatch(
    attribute_request, attribute_envelope
):
    attribute_envelope["upstream_hash"] = "f" * 64
    with pytest.raises(ValueError, match="Foreign recognition prerequisite") as error:
        parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    assert error.value.issue.path == ("upstream_hash",)
    assert error.value.issue.error_type == "upstream_identity_mismatch"


def test_validation_diagnostics_bound_and_redact_nested_errors(recognition_request):
    from pydantic import ValidationError

    from powerforge_extraction.response_diagnostics import validation_issues

    private = "PRIVATE-PANEL-IDENTIFIER"
    payload = recognition_envelope(recognition_request)
    payload["equipment"][0].update(
        source_description=private * 256,
        registry_type=private,
        evidence=[
            {
                "kind": "READING",
                "role": "TAG",
                "reading_ref": private,
                "quote": None,
                private: private,
            }
        ],
    )
    payload.update({f"{private}-{index}": private for index in range(20)})
    with pytest.raises(ValidationError) as error:
        parse_response(recognition_request, json.dumps(payload).encode())
    issues = validation_issues(error.value)
    assert 0 < len(issues) <= 8
    assert any(issue.error_type == "string_too_long" for issue in issues)
    assert any(issue.error_type == "enum" for issue in issues)
    assert any(issue.error_type == "extra_forbidden" for issue in issues)
    assert all(private not in issue.model_dump_json() for issue in issues)
