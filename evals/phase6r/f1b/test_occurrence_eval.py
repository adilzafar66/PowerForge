import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from occurrence_eval import EVALS, Observation, Page, read_gold, score
from stage1_preflight import as_request, observations_from_output

from extraction_worker.spatial_evaluation import render
from extraction_worker.tesseract import configuration
from powerforge_ai.ocr import OCRIdentity
from powerforge_extraction.provider_body import dispatch_hash


def model(data, cls):
    return cls.model_validate_json(json.dumps(data))


def breaker(key, box):
    return dict(
        id=key,
        box=box,
        note=key,
        registry_type="LV_BREAKER",
        qualification="UNKNOWN",
        tag_state="ABSENT",
        tag=None,
    )


def observed(ref, region=(), **fields):
    return model(
        dict(
            local_ref=ref,
            registry_type="LV_BREAKER",
            qualification="UNKNOWN",
            tag_state="ABSENT",
            tag=None,
            equipment_regions=region,
            resolved_equipment_fragments=bool(region) * 1,
            approximate_equipment_fragments=0,
            unresolved_equipment_fragments=0,
        )
        | fields,
        Observation,
    )


def test_identical_models_at_distinct_source_positions_are_two_occurrences():
    page = model(
        dict(
            pdf_page=1,
            frame=(100, 100),
            preparation="native",
            exceptions=[],
            occurrences=[breaker("left", (10, 10, 20, 20)), breaker("right", (30, 10, 40, 20))],
        ),
        Page,
    )
    result = score(
        page,
        (observed("a", ((0.10, 0.10, 0.20, 0.20),)), observed("b", ((0.30, 0.10, 0.40, 0.20),))),
    )
    assert result["matched"] == 2
    assert result["strict_f1"] == 1


def test_repeated_references_to_one_occurrence_count_a_duplicate_and_keep_recall():
    page = model(
        dict(
            pdf_page=1,
            frame=(100, 100),
            preparation="native",
            exceptions=[],
            occurrences=[breaker("one", (10, 10, 20, 20))],
        ),
        Page,
    )
    box = ((0.1, 0.1, 0.2, 0.2),)
    result = score(page, (observed("a", box), observed("b", box, tag_state="PRESENT", tag="x")))
    assert result["matched"] == 1
    assert result["duplicate_extras"] == 1
    assert result["strict_precision"] == 0.5
    assert result["strict_recall"] == 1
    assert result["field_accuracy_by_occurrence"]["one"]["correct_tag"] is None


def test_tag_or_type_cannot_credit_an_observation_without_a_source_position():
    page = model(
        dict(
            pdf_page=1,
            frame=(100, 100),
            preparation="native",
            exceptions=[],
            occurrences=[breaker("left", (10, 10, 20, 20))],
        ),
        Page,
    )
    result = score(page, (observed("missing-evidence"), observed("page-wide", ((0, 0, 1, 1),))))
    assert result["missing"] == ["left"]
    assert result["outcomes"] == {"UNVERIFIED_OBSERVATION": 2}


def test_provision_aggregate_and_unresolved_reference_are_distinct():
    page = model(
        dict(
            pdf_page=1,
            frame=(100, 100),
            preparation="native",
            occurrences=[],
            exceptions=[
                dict(id="provision", kind="PROVISION", box=(10, 10, 20, 20), note="empty"),
                dict(
                    id="total", kind="AGGREGATE", box=(30, 10, 40, 20), note="summary", quantity=5
                ),
                dict(id="uncertain", kind="AMBIGUOUS", box=(50, 10, 60, 20), note="uncertain"),
            ],
        ),
        Page,
    )
    result = score(
        page,
        (
            observed("provision", ((0.10, 0.10, 0.20, 0.20),), qualification="INSTALLED"),
            observed("aggregate", ((0.30, 0.10, 0.40, 0.20),)),
            observed("possible", ((0.50, 0.10, 0.60, 0.20),)),
        ),
    )
    assert result["outcomes"] == {"PROVISION": 1, "AGGREGATE": 1, "AMBIGUOUS": 1}
    assert result["pending_adjudication"] == 1
    assert result["observations"]["provision"]["provision_asserted_installed"]


def test_assembly_tag_misattribution_does_not_break_occurrence_matching():
    panel = breaker("panel", (40, 10, 50, 20)) | dict(
        registry_type="BUS", tag_state="PRESENT", tag="MDB"
    )
    page = model(
        dict(
            pdf_page=1,
            frame=(100, 100),
            preparation="native",
            exceptions=[],
            occurrences=[breaker("branch", (10, 10, 20, 20)), panel],
        ),
        Page,
    )
    result = score(
        page, (observed("branch", ((0.10, 0.10, 0.20, 0.20),), tag_state="PRESENT", tag="MDB"),)
    )
    assert result["matched"] == 1
    assert result["observations"]["branch"]["assembly_tag_on_branch"]
    assert result["missing"] == ["panel"]


def test_production_response_replay_localizes_exact_reading_and_rejects_foreign_dispatch():
    source_doc = read_gold().structural_control[0]
    path = Path(EVALS / source_doc.pdf)
    pdf = path.read_bytes()
    image = render(path, pdf, 1)
    data = "0" * 64
    options = configuration(data)
    fake = SimpleNamespace(
        settings=options,
        identity=OCRIdentity(
            adapter_version="test-v1",
            engine="tesseract",
            engine_version="5.3.0",
            build_sha256=data,
            settings_sha256=options.identity_hash,
        ),
        recognize=Mock(side_effect=AssertionError("unexpected OCR")),
    )
    wire, request, pinned = as_request(path, pdf, image, 1, "native", fake, "existing_tables")
    reading = next(item for item in wire.page.readings if item.text == "TX-1")
    raw = json.dumps(
        {
            "equipment": [
                dict(
                    local_ref="first",
                    registry_type="TWO_WINDING_TRANSFORMER",
                    qualification="UNKNOWN",
                    tag_state="PRESENT",
                    tag="TX-1",
                    raw_qualification=None,
                    source_description="Transformer TX-1",
                    evidence=[
                        dict(
                            kind="READING",
                            role="EQUIPMENT",
                            reading_ref=reading.reading_ref,
                            quote=None,
                        )
                    ],
                )
            ]
        }
    ).encode()
    result = observations_from_output(
        pinned, wire, raw, request=request, dispatched_digest=dispatch_hash(request)
    )
    assert score(source_doc.pages[0], result)["matched"] == 1
    with pytest.raises(ValueError, match="not bound"):
        observations_from_output(pinned, wire, raw, request=request, dispatched_digest=data)
