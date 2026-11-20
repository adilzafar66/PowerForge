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
from powerforge_extraction.stage_contracts import (
    ATTRIBUTE_DESCRIPTION_VERSION,
    ATTRIBUTE_INPUT_VERSION,
    ATTRIBUTE_VERSION,
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
from powerforge_extraction.stage_execution import provider_input
from powerforge_provenance.layout_observations import ReadingOverlap, SpatialLayout
from powerforge_provenance.spatial_layout import SourceSupport
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
        version=ATTRIBUTE_VERSION,
        stage="ATTRIBUTE_EXTRACTION",
        page_context_hash=request.page_context_hash,
        page=request.page,
        registry_version=request.registry_version,
        upstream_hash=contract_hash(upstream),
        upstream=upstream,
        attribute_catalog=attribute_catalog(upstream),
        attribute_description_version=ATTRIBUTE_DESCRIPTION_VERSION,
    )


@pytest.fixture
def attribute_envelope(attribute_request):
    request = attribute_request
    reading = request.page.readings[0].reading_ref
    example = {
        "origin": "EXTRACTED",
        "local_ref": "a1",
        "equipment_ref": "equipment-0",
        "association": "ASSERTED",
        "raw_label": "Primary connection",
        "raw_value": "Star",
        "raw_unit": None,
        "qualifiers": [],
        "value_form": "SINGLE",
        "attribute_key": "primary_connection",
        "proposed_value": "WYE",
        "alternate_representations": [],
        "proposed_unit": None,
        "evidence": [
            {"kind": "READING", "role": "LABEL", "reading_ref": reading, "quote": None},
            {"kind": "QUOTE", "role": "VALUE", "quote": "Star"},
        ],
    }
    # A foreign owner is recoverable in D. Admission preserves the assertion for review.
    conflict = dict(example, local_ref="a2", equipment_ref="foreign-owner", raw_value="Delta")
    conflict["proposed_value"] = "DELTA"
    raw = {
        key: value
        for key, value in example.items()
        if key
        not in {
            "attribute_key",
            "proposed_value",
            "proposed_unit",
            "origin",
            "alternate_representations",
        }
    }
    raw.update(
        display_label=None,
        local_ref="a3",
        equipment_ref=None,
        association="UNASSIGNED",
        raw_label="Noise level",
        raw_value="45 to 50",
        raw_unit="dB",
        value_form="RANGE",
    )
    return {
        "version": ATTRIBUTE_VERSION,
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
    assert {item.required for item in attributes.attribute_catalog} == {True, False}
    payload = attribute_envelope
    result = parse_response(attributes, json.dumps(payload).encode())
    assert [(a.raw_value, a.proposed_value) for a in result.attributes] == [
        ("Star", "WYE"),
        ("Delta", "DELTA"),
    ]
    assert result.raw_unmapped[0].raw_value == "45 to 50"
    payload["upstream_hash"] = "9" * 64
    with pytest.raises(ValueError, match="prerequisite"):
        parse_response(attributes, json.dumps(payload).encode())


@pytest.mark.parametrize("recognition_request", [True], indirect=True)
def test_compact_schedule_keeps_readings_coordinates_and_layout(attribute_request):
    original = attribute_request.model_dump(mode="json")
    compact = json.loads(json.dumps(provider_input(attribute_request)))
    page = compact["page"]
    full_page = original["page"]
    assert compact["input_version"] == ATTRIBUTE_INPUT_VERSION
    for key in original.keys() - {"page"}:
        assert compact[key] == original[key]
    for key in full_page.keys() - {"readings", "layout"}:
        assert page[key] == full_page[key]

    layout = page["layout"]
    full_layout = full_page["layout"]
    assert full_layout["tables"]
    for key in full_layout.keys() - {"readings", "order"}:
        assert layout[key] == full_layout[key]
    assert "readings" not in layout
    assert [
        dict(zip(layout["order"]["columns"], row, strict=True)) for row in layout["order"]["rows"]
    ] == full_layout["order"]

    rows = page["readings"]
    actual_readings = [dict(zip(rows["columns"], row, strict=True)) for row in rows["rows"]]
    assert actual_readings == [
        {**reading, **geometry["region"], "issues": geometry["issues"]}
        for reading, geometry in zip(full_page["readings"], full_layout["readings"], strict=True)
    ]
    assert len(json.dumps(compact, separators=(",", ":"))) < len(
        json.dumps(original, separators=(",", ":"))
    )
    assert attribute_request.model_dump(mode="json") == original


def test_compact_input_preserves_alternate_and_overlapping_token_links(attribute_request):
    page = attribute_request.page
    first, second, *rest = page.layout.readings
    alternate = SourceSupport(representation_ref="ocr", kind="TOKEN", ref="w0")
    first = first.model_copy(
        update={
            "members": (alternate, first.preferred),
            "issues": ("TRANSCRIPTION_CONFLICT",),
        }
    )
    layout = page.layout.model_copy(
        update={
            "readings": (first, second.model_copy(update={"region": None}), *rest),
            "overlaps": (ReadingOverlap(left=alternate, right=second.preferred, kind="AMBIGUOUS"),),
        }
    )
    layout = SpatialLayout.model_validate_json(layout.model_dump_json())
    page = page.model_copy(
        update={
            "layout": layout,
            "layout_sha256": layout.identity_hash,
            "readings": (
                page.readings[0].model_copy(update={"alternate_texts": ("Conflicting OCR",)}),
                *page.readings[1:],
            ),
        }
    )
    context_hash = contract_hash(page)
    upstream = attribute_request.upstream.model_copy(update={"page_context_hash": context_hash})
    request = attribute_request.model_copy(
        update={
            "page": page,
            "page_context_hash": context_hash,
            "upstream": upstream,
            "upstream_hash": contract_hash(upstream),
        }
    )
    validate_request(request, expected_owner=page.owner)
    compact = provider_input(request)["page"]
    layout_json = layout.model_dump(mode="json")
    assert compact["layout"]["overlaps"] == layout_json["overlaps"]
    token_links = compact["layout"]["reading_sources"]
    for reading in (first, second):
        assert token_links[reading.ref] == {
            "members": [item.model_dump(mode="json") for item in reading.members],
            "preferred": reading.preferred.model_dump(mode="json"),
        }
    columns = compact["readings"]["columns"]
    first_row, second_row, *_ = compact["readings"]["rows"]
    assert first_row[columns.index("alternate_texts")] == ["Conflicting OCR"]
    assert first_row[columns.index("issues")] == ["TRANSCRIPTION_CONFLICT"]
    assert second_row[-4:] == [None] * 4


def test_inference_wire_has_no_transcription_and_allows_empty_evidence(
    attribute_request, attribute_envelope
):
    inference = {
        "local_ref": "proposal",
        "origin": "INFERRED",
        "equipment_ref": "equipment-0",
        "association": "ASSERTED",
        "attribute_key": "primary_connection",
        "proposed_value": "WYE",
        "proposed_unit": None,
        "inference_explanation": "The connection symbol supports this proposal.",
        "inference_basis": "DOCUMENT_CONTEXT",
        "source_expression": None,
        "evidence": [],
    }
    attribute_envelope["attributes"] = [inference]
    result = parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    assert result.attributes[0].origin == "INFERRED"
    assert "raw_value" not in result.attributes[0].model_dump()
    for field, value in (
        ("raw_label", "Invented source label"),
        ("inference_explanation", " "),
        ("equipment_ref", None),
        ("association", "UNASSIGNED"),
    ):
        attribute_envelope["attributes"] = [{**inference, field: value}]
        with pytest.raises(ValueError):
            parse_response(attribute_request, json.dumps(attribute_envelope).encode())


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
        proposed_value=None,
        raw_unit=None,
        qualifiers=["At startup"],
        value_form="QUALIFIED",
        evidence=[{"kind": "QUOTE", "role": "VALUE", "quote": "600"}],
    )
    unsupported.update(
        equipment_ref="foreign-owner",
        attribute_key="unregistered_key",
        proposed_value="UNSUPPORTED_ENUM",
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
    assert unsupported.proposed_value == "UNSUPPORTED_ENUM"


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


def test_attribute_evidence_limit_accepts_twelve_and_diagnoses_thirteen(
    attribute_request, attribute_envelope
):
    from pydantic import ValidationError

    from powerforge_extraction.response_diagnostics import validation_issues

    evidence = [
        {"kind": "READING", "role": role, "reading_ref": reading.reading_ref, "quote": None}
        for role in ("VALUE", "CONTEXT")
        for reading in attribute_request.page.readings[:6]
    ]
    assert len(evidence) == 12
    attribute_envelope["attributes"][0]["evidence"] = evidence
    result = parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    assert len(result.attributes[0].evidence) == 12
    evidence.append({"kind": "QUOTE", "role": "CONTEXT", "quote": "Schedule notes"})
    with pytest.raises(ValidationError) as error:
        parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    assert any(
        issue.category == "FIELD_CONSTRAINT"
        and issue.error_type == "too_long"
        and issue.path == ("attributes", 0, "*", "evidence")
        for issue in validation_issues(error.value)
    )


def test_visual_coordinates_keep_exact_wire_validation(attribute_request, attribute_envelope):
    from pydantic import ValidationError

    from powerforge_extraction.response_diagnostics import validation_issues

    citation = {
        "kind": "VISUAL",
        "role": "VALUE",
        "reported_text": None,
        "region": {"x": 0, "y": "0.125", "width": "0.3", "height": "0.04"},
    }
    attribute_envelope["attributes"][0]["evidence"] = [citation]
    result = parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    assert str(result.attributes[0].evidence[0].region.y) == "0.125"
    citation["region"]["y"] = 0.125
    with pytest.raises(ValidationError) as raised:
        parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    assert any(issue.path[-2:] == ("region", "y") for issue in validation_issues(raised.value))


def test_assembly_tag_response_preserves_distinct_device_ownership(recognition_request):
    envelope = recognition_envelope(recognition_request)
    envelope["equipment"][0].update(
        local_ref="assembly",
        registry_type="BUS",
        tag_state="PRESENT",
        tag="DMR-MAIN",
        evidence=[{"kind": "QUOTE", "role": "TAG", "quote": "TAG(S):[DMR-MAIN]"}],
    )
    envelope["equipment"][1].update(
        local_ref="branch", registry_type="LV_BREAKER", tag_state="ABSENT", tag=None
    )
    result = parse_response(recognition_request, json.dumps(envelope).encode())
    assert result.equipment[0].tag == "DMR-MAIN"
    assert result.equipment[0].evidence[0].quote == "TAG(S):[DMR-MAIN]"
    assert result.equipment[1].tag is None


def test_registry_guidance_explains_distinct_ratings_and_retains_registry_keys(recognition_request):
    from powerforge_engineering_model.extraction_descriptions import (
        ATTRIBUTE_DESCRIPTION_VERSION,
        ATTRIBUTE_DESCRIPTIONS,
    )
    from powerforge_engineering_model.registry import get_equipment_definition
    from powerforge_extraction.extraction_profile import extraction_profile
    from powerforge_shared.config import Settings

    envelope = recognition_envelope(recognition_request)
    envelope["equipment"][0]["registry_type"] = "BUS"
    envelope["equipment"][1]["registry_type"] = "LV_BREAKER"
    upstream = parse_response(recognition_request, json.dumps(envelope).encode())
    catalog = attribute_catalog(upstream)
    for equipment_type in ("BUS", "LV_BREAKER"):
        supplied = {a.key: a for a in catalog if a.equipment_type == equipment_type}
        registered = get_equipment_definition(equipment_type).attributes
        assert supplied.keys() == {a.key for a in registered}
        assert all(supplied[a.key].name == a.display_name for a in registered)
        assert all(supplied[a.key].required == a.required for a in registered)
    assert "Bus bracing" in ATTRIBUTE_DESCRIPTIONS["short_time_withstand_current"]
    assert "inference" in ATTRIBUTE_DESCRIPTIONS["trip_unit_type"]
    assert "UL and CSA" in ATTRIBUTE_DESCRIPTIONS["standard"]
    profile = extraction_profile(Settings(_env_file=None))
    assert profile.manifest["attribute_descriptions"] == ATTRIBUTE_DESCRIPTION_VERSION


def test_attribute_admission_quarantines_multiple_local_failures(
    attribute_request, attribute_envelope
):
    from powerforge_extraction.attribute_admission import admit_attributes

    valid = attribute_envelope["attributes"][0]
    attribute_envelope["attributes"] = [
        dict(valid, local_ref=f"valid-{index}", raw_value="0") for index in range(24)
    ] + [
        dict(valid, local_ref="empty", raw_value=""),
        dict(valid, local_ref="blank", raw_value=" \t\n"),
        dict(valid, local_ref="broken-inferred", origin="INFERRED"),
        {key: value for key, value in valid.items() if key != "local_ref"},
        dict(valid, local_ref="private malformed ref"),
        dict(valid, local_ref="valid-neighbor", raw_value=" 600 "),
    ]
    attribute_envelope["raw_unmapped"].append(
        dict(attribute_envelope["raw_unmapped"][0], local_ref="unmapped-invalid", raw_value="")
    )
    result = admit_attributes(attribute_request, json.dumps(attribute_envelope).encode())
    assert (result.received, result.accepted, len(result.rejected)) == (32, 26, 6)
    assert result.result.attributes[-1].local_ref == "valid-neighbor"
    assert result.result.attributes[-1].raw_value == " 600 "
    assert result.result.attributes[0].raw_value == "0"
    assert result.result.raw_unmapped[0].local_ref == "a3"
    assert [entry.index for entry in result.rejected] == [24, 25, 26, 27, 28, 1]
    assert [entry.local_ref for entry in result.rejected] == [
        "empty",
        "blank",
        "broken-inferred",
        None,
        None,
        "unmapped-invalid",
    ]
    assert result.rejected[0].issues[0].path == ("attributes", 24, "raw_value")
    assert "private malformed ref" not in repr(result.rejected)


@pytest.mark.parametrize("violation", ["upstream", "page", "version", "shape", "duplicate"])
def test_attribute_admission_keeps_global_integrity_fatal(
    attribute_request, attribute_envelope, violation
):
    from powerforge_extraction.attribute_admission import admit_attributes

    if violation == "duplicate":
        attribute_envelope["raw_unmapped"][0].update(local_ref="a1", raw_value="")
    elif violation == "shape":
        attribute_envelope["attributes"] = {}
    elif violation == "version":
        attribute_envelope["version"] = "phase-6r-attributes-v5"
    else:
        attribute_envelope[
            f"{violation}_hash" if violation == "upstream" else "page_context_hash"
        ] = "f" * 64
    result = admit_attributes(attribute_request, json.dumps(attribute_envelope).encode())
    assert result.result is None and result.fatal and not result.rejected
    if violation == "duplicate":
        assert result.fatal[0].error_type == "duplicate_reference"


def test_attribute_admission_distinguishes_empty_from_all_rejected(
    attribute_request, attribute_envelope
):
    from powerforge_extraction.attribute_admission import admit_attributes

    attribute_envelope.update(
        attributes=[dict(attribute_envelope["attributes"][0], raw_value="")], raw_unmapped=[]
    )
    rejected = admit_attributes(attribute_request, json.dumps(attribute_envelope).encode())
    assert (rejected.received, rejected.accepted, len(rejected.rejected)) == (1, 0, 1)
    assert rejected.result is None and rejected.fatal[0].error_type == "all_assertions_quarantined"
    attribute_envelope["attributes"] = []
    empty = admit_attributes(attribute_request, json.dumps(attribute_envelope).encode())
    assert empty.received == empty.accepted == 0 and empty.result is not None
    assert not empty.rejected and not empty.fatal


def test_attribute_admission_rejects_duplicate_json_keys(attribute_request):
    from powerforge_extraction.attribute_admission import admit_attributes

    rejected = admit_attributes(attribute_request, b'{"stage":1,"stage":2}')
    assert rejected.result is None and rejected.fatal[0].error_type == "invalid_json_structure"


@pytest.mark.parametrize(
    "key,raw,proposal,form",
    [
        ("rated_current", "015.750 A", "015.750", "SINGLE"),
        ("pole_count", "3 Pole", 3, "SINGLE"),
        ("model", "00-AB 75", "00-AB 75", "SINGLE"),
        ("drawout", "No", False, "SINGLE"),
        ("primary_connection", "Star", "WYE", "SINGLE"),
        ("rated_voltage", "400/600 V", "400/600", "MULTIPLE"),
        ("rated_voltage", "400/600 V", None, "MULTIPLE"),
    ],
)
def test_extracted_proposals_round_trip(
    attribute_request, attribute_envelope, key, raw, proposal, form
):
    from powerforge_extraction.attribute_admission import admit_attributes

    attribute_envelope["attributes"][0].update(
        attribute_key=key, raw_value=raw, proposed_value=proposal, value_form=form
    )
    admission = admit_attributes(attribute_request, json.dumps(attribute_envelope).encode())
    assert not admission.fatal and not admission.rejected
    assertion = admission.result.attributes[0]
    assert assertion.raw_value == raw
    assert assertion.proposed_value == proposal
    assert type(assertion.proposed_value) is type(proposal)
    serialized = json.loads(admission.result.model_dump_json())["attributes"][0]
    assert type(serialized["proposed_value"]) is type(proposal)
    assert "proposed_enum_value" not in serialized
    assert "proposed_value" not in admission.result.raw_unmapped[0].model_dump()


@pytest.mark.parametrize(
    "bad_fields,path",
    [
        ({"proposed_value": 3.0}, "proposed_value"),
        ({"proposed_value": []}, "proposed_value"),
        ({"proposed_value": {}}, "proposed_value"),
        ({"proposed_value": "x" * 2049}, "proposed_value"),
        ({"proposed_value": " \t"}, "proposed_value"),
        ({"proposed_enum_value": "WYE"}, "*"),
        ({"value_form": "EQUIVALENT_UNITS"}, "alternate_representations"),
        (
            {"alternate_representations": [{"value": "508", "unit": "mm"}]},
            "alternate_representations",
        ),
        (
            {
                "value_form": "EQUIVALENT_UNITS",
                "alternate_representations": [{"value": "508", "unit": "mm"}] * 5,
            },
            "alternate_representations",
        ),
        (
            {
                "value_form": "EQUIVALENT_UNITS",
                "alternate_representations": [{"value": "1/2", "unit": "mm"}],
            },
            "alternate_representations",
        ),
        (
            {
                "value_form": "EQUIVALENT_UNITS",
                "alternate_representations": [{"value": 508, "unit": "mm"}],
            },
            "alternate_representations",
        ),
        (
            {
                "value_form": "EQUIVALENT_UNITS",
                "alternate_representations": [{"value": "508", "unit": " "}],
            },
            "alternate_representations",
        ),
    ],
)
def test_v6_invalid_fields_are_quarantined(attribute_request, attribute_envelope, bad_fields, path):
    from powerforge_extraction.attribute_admission import admit_attributes

    attribute_envelope["attributes"][0].update(bad_fields)
    admission = admit_attributes(attribute_request, json.dumps(attribute_envelope).encode())
    assert (admission.received, admission.accepted, len(admission.rejected)) == (3, 2, 1)
    assert admission.result.attributes[0].local_ref == "a2"
    rejected = admission.rejected[0]
    assert (rejected.collection, rejected.index, rejected.local_ref) == ("attributes", 0, "a1")
    assert any(issue.path[:3] == ("attributes", 0, path) for issue in rejected.issues)


@pytest.mark.parametrize("field", ["proposed_value", "alternate_representations"])
def test_v6_extracted_requires_explicit_fields(attribute_request, attribute_envelope, field):
    from powerforge_extraction.attribute_admission import admit_attributes

    del attribute_envelope["attributes"][0][field]
    admission = admit_attributes(attribute_request, json.dumps(attribute_envelope).encode())
    (rejected,) = admission.rejected
    assert any(
        issue.path == ("attributes", 0, field) and issue.error_type == "missing"
        for issue in rejected.issues
    )


def test_equivalent_unit_wire_preserves_reported_values(attribute_request, attribute_envelope):
    raw = "20”(508.000mm)W"
    alternates = [{"value": "508.000", "unit": "mm"}]
    attribute_envelope["attributes"][0].update(
        attribute_key="width",
        raw_value=raw,
        raw_unit="”",
        proposed_value="20",
        proposed_unit="in",
        value_form="EQUIVALENT_UNITS",
        alternate_representations=alternates,
    )
    result = parse_response(attribute_request, json.dumps(attribute_envelope).encode())
    item = json.loads(result.model_dump_json())["attributes"][0]
    assert item["raw_value"] == raw
    assert item["alternate_representations"] == alternates


@pytest.mark.parametrize("proposal", ["0.125", 8, False])
def test_inferred_proposals_are_strict_primitives(attribute_request, attribute_envelope, proposal):
    from powerforge_extraction.attribute_admission import admit_attributes

    inferred = dict(
        origin="INFERRED",
        local_ref="inferred",
        equipment_ref="equipment-0",
        association="ASSERTED",
        attribute_key="primary_connection",
        proposed_value=proposal,
        proposed_unit=None,
        inference_explanation="Synthetic proposed registry value.",
        inference_basis=None,
        source_expression=None,
        evidence=[],
    )
    attribute_envelope["attributes"] = [
        inferred,
        dict(inferred, local_ref="null", proposed_value=None),
        dict(inferred, local_ref="float", proposed_value=3.0),
        dict(inferred, local_ref="alternate", alternate_representations=[]),
        dict(inferred, local_ref="form", value_form="EQUIVALENT_UNITS"),
    ]
    admission = admit_attributes(attribute_request, json.dumps(attribute_envelope).encode())
    assert [rejection.index for rejection in admission.rejected] == [1, 2, 3, 4]
    accepted = admission.result.attributes[0].proposed_value
    assert accepted == proposal and type(accepted) is type(proposal)


def test_fake_provider_attributes_use_v6_wire(attribute_request):
    from powerforge_ai.extraction import ExtractionRequest
    from powerforge_extraction.attribute_admission import admit_attributes
    from powerforge_extraction.extraction_profile import RESPONSES
    from powerforge_extraction.stage_execution import FakeExtractionProvider

    stage = attribute_request.stage
    request = ExtractionRequest(
        work_unit_id=uuid4(),
        unit_key=f"{stage}:page:000001",
        stage=stage,
        attempt_number=1,
        model="deterministic-phase-6r-v1",
        instructions="Offline v6 fixture",
        schema_version=attribute_request.version,
        timeout_seconds=1,
        max_output_tokens=1024,
        text=json.dumps(provider_input(attribute_request)),
        image=b"mock-png",
        image_mime_type="image/png",
        image_detail="high",
        response_model=RESPONSES[stage],
    )
    output = FakeExtractionProvider("success").execute(request)
    raw = output.result.model_dump_json().encode()
    admission = admit_attributes(attribute_request, raw)
    assert admission.result == output.result
    assert admission.result.version == "phase-6r-attributes-v6"
