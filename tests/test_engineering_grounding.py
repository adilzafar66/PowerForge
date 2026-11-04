"""Ground actual immutable bytes and never fabricate an occurrence, qualifier or location."""

from dataclasses import replace
from decimal import Decimal
from io import BytesIO

import pytest
from pydantic import ValidationError

from engineering_grounding_support import (
    anchor,
    attribute,
    attribute_sources,
    attributes,
    equipment,
    page,
    recognition,
    test_context,
)
from powerforge_document_processing.storage import TransientStorageError
from powerforge_document_processing.storage.memory import StoredObject
from powerforge_extraction.contracts import WorkUnitOutput
from powerforge_extraction.engineering_output import convert_attributes, convert_equipment
from powerforge_extraction.grounding import (
    ground_observation,
    grounding_identity,
    load_page_sources,
)
from powerforge_extraction.observations import SourceAnchor


def test_unicode_offsets_and_complete_lines_preserve_qualifiers_and_negations():
    source, _ = page("é🙂\n2-Winding Transformer TX-1\nSecondary Voltage (not verified): 600 V")
    observation = equipment("2-Winding Transformer TX-1", tag="TX-1")
    grounded = ground_observation(observation, source)
    evidence = grounded.evidence[0]
    assert evidence.text_start == 3 and evidence.text_end == 29
    assert source.text[evidence.text_start : evidence.text_end] == evidence.source_snippet
    negative, _ = page("Not a 2-Winding Transformer TX-1")
    output = convert_equipment(recognition(observation), negative)
    assert output.candidates[0].mapping_status == "UNMAPPED"
    assert output.candidates[0].raw_text.startswith("Not a")
    # A model fragment cannot hide a qualifier elsewhere on the same real line.
    qualified, _ = page("2-Winding Transformer TX-1\nUnverified Secondary Voltage: 600 V")
    eq = convert_equipment(recognition(observation), qualified)
    attr = attribute("Secondary Voltage: 600 V")
    result = convert_attributes(
        attributes(attr), attribute_sources(qualified), test_context(qualified, eq)
    )
    assert result.candidates[0].mapping_status == "UNMAPPED"
    assert (
        result.candidates[0].source_group_id is None and result.candidates[0].numeric_value is None
    )
    assert result.evidence[0].source_snippet == "Unverified Secondary Voltage: 600 V"


def test_repeated_phrases_use_verified_context_or_keep_null_offsets_and_no_group():
    source, _ = page(
        "2-Winding Transformer TX-1\nSecondary Voltage: 600 V\n\n"
        "2-Winding Transformer TX-2\nSecondary Voltage: 600 V"
    )
    repeated = ground_observation(attribute(), source)
    assert repeated.own_span is None and repeated.evidence[0].text_start is None
    located = ground_observation(attribute(prefix="TX-2\n"), source)
    assert located.own_span[0] == source.text.rfind("Secondary Voltage")
    assert located.evidence[0].offset_convention == "UNICODE_CODEPOINT"
    eq = convert_equipment(recognition(equipment("2-Winding Transformer TX-1", tag="TX-1")), source)
    result = convert_attributes(
        attributes(attribute()), attribute_sources(source), test_context(source, eq)
    )
    assert result.candidates[0].mapping_status == "UNMAPPED"
    assert result.candidates[0].source_group_id is None
    assert result.candidates[0].diagnostics["grounding_precision"] == "TEXT_PAGE"


@pytest.mark.parametrize(
    "failure", ["absent_quote", "wrong_context", "paraphrased_claim", "invented_tag"]
)
def test_forged_claims_do_not_produce_supported_candidates_or_evidence(failure):
    source, _ = page("2-Winding Transformer TX-1")
    item = equipment("2-Winding Transformer TX-1", tag="TX-1")
    if failure == "absent_quote":
        item = item.model_copy(
            update={"anchors": [SourceAnchor.model_validate(anchor("never in source"))]}
        )
    elif failure == "wrong_context":
        item = item.model_copy(
            update={
                "anchors": [
                    SourceAnchor.model_validate(anchor(item.raw_expression, prefix="fake prefix"))
                ]
            }
        )
    elif failure == "paraphrased_claim":
        item = item.model_copy(update={"raw_expression": "Two-Winding Transformer TX-1"})
    else:
        item = item.model_copy(update={"observed_tag": "TX-999"})
    result = convert_equipment(recognition(item), source)
    assert not result.candidates and not result.evidence and not result.source_groups
    assert sum(result.diagnostic_counts.values()) == 1


def test_source_blocks_not_model_references_establish_native_association():
    source, _ = page(
        "2-Winding Transformer TX-1\nSecondary Voltage: 600 V\n\n"
        "2-Winding Transformer TX-2\nSecondary Voltage: 690 V"
    )
    eq = convert_equipment(
        recognition(
            equipment("2-Winding Transformer TX-1", tag="TX-1"),
            equipment("2-Winding Transformer TX-2", ref="eq2", tag="TX-2"),
        ),
        source,
    )
    context = test_context(source, eq)
    correct = convert_attributes(attributes(attribute()), attribute_sources(source), context)
    assert correct.candidates[0].numeric_value == Decimal("0.6")
    assert correct.candidates[0].source_group_id == eq.candidates[0].source_group_id
    wrong = convert_attributes(
        attributes(attribute(equipment_ref="eq2")), attribute_sources(source), context
    )
    assert (
        wrong.candidates[0].mapping_status == "UNMAPPED"
        and wrong.candidates[0].source_group_id is None
    )
    assert wrong.diagnostic_counts == {"detached_associations": 1}
    shared, _ = page(
        "2-Winding Transformer TX-1\n2-Winding Transformer TX-2\nSecondary Voltage: 600 V"
    )
    output = convert_equipment(
        recognition(
            equipment("2-Winding Transformer TX-1"),
            equipment("2-Winding Transformer TX-2", ref="eq2"),
        ),
        shared,
    )
    assert all(candidate.diagnostics["source_scope"] is None for candidate in output.candidates)


@pytest.mark.parametrize("field", ["observed_tag", "observed_name"])
def test_equipment_fields_cannot_be_borrowed_from_outside_the_observed_expression(field):
    source, _ = page("2-Winding Transformer TX-1 (reference TX-2)")
    item = equipment("2-Winding Transformer TX-1", tag="TX-1")
    forged = item.model_copy(update={field: "TX-2"})
    output = convert_equipment(recognition(forged), source)
    assert not output.candidates and not output.source_groups and not output.evidence
    assert output.diagnostic_counts == {"rejected_source_fields": 1}

    valid = convert_equipment(recognition(item), source)
    assert valid.candidates[0].observed_tag == "TX-1"
    assert valid.candidates[0].raw_text == source.text
    assert valid.evidence[0].source_snippet == source.text


@pytest.mark.parametrize(
    "intervening",
    [
        "TX-2: Two-Winding Transformer",
        "TX-2: 2-Winding Transformer",
        "CB-2: LV circuit breaker",
        "TX-2: Unknown equipment",
        "Unrecognized field: TX-2",
    ],
)
def test_missed_colon_headers_and_unknown_fields_do_not_extend_equipment_scope(intervening):
    source, _ = page(f"2-Winding Transformer TX-1\n{intervening}\nSecondary Voltage: 690 V")
    eq = convert_equipment(recognition(equipment("2-Winding Transformer TX-1", tag="TX-1")), source)
    assert eq.candidates[0].diagnostics["source_scope"] is None
    output = convert_attributes(
        attributes(attribute("Secondary Voltage: 690 V", value="690")),
        attribute_sources(source),
        test_context(source, eq),
    )
    candidate = output.candidates[0]
    assert candidate.mapping_status == "UNMAPPED" and candidate.numeric_value is None
    assert candidate.source_group_id is None and candidate.equipment_mention_candidate_id is None
    assert output.diagnostic_counts == {"detached_associations": 1}


@pytest.mark.parametrize(
    "field", ["Secondary Voltage: 600 V", "Secondary Voltage (V): 600", "Rated Capacity: 600 kVA"]
)
def test_recognized_attribute_labels_still_extend_equipment_scope(field):
    source, _ = page(f"2-Winding Transformer TX-1\n{field}\nSecondary Voltage: 690 V")
    eq = convert_equipment(recognition(equipment("2-Winding Transformer TX-1")), source)
    assert eq.candidates[0].diagnostics["source_scope"] is not None
    output = convert_attributes(
        attributes(attribute("Secondary Voltage: 690 V", value="690")),
        attribute_sources(source),
        test_context(source, eq),
    )
    assert output.candidates[0].mapping_status == "MAPPED"
    assert output.candidates[0].numeric_value == Decimal("0.69")
    assert output.candidates[0].source_group_id == eq.candidates[0].source_group_id


def test_tagless_groups_stable_local_keys_and_shared_evidence_do_not_merge_tags():
    source, _ = page("2-Winding Transformer\nSecondary Voltage: 600 V")
    eq = convert_equipment(recognition(equipment("2-Winding Transformer")), source)
    assert eq.source_groups[0].tag_text is None
    assert (
        eq.model_dump()
        == convert_equipment(recognition(equipment("2-Winding Transformer")), source).model_dump()
    )
    result = convert_attributes(
        attributes(attribute(), attribute(ref="a2")),
        attribute_sources(source),
        test_context(source, eq),
    )
    assert len(result.candidates) == 2 and len(result.evidence) == 1
    primary = [link.evidence_id for link in result.candidate_evidence if link.role == "PRIMARY"]
    assert len(set(primary)) == 1
    other = replace(
        source,
        spec=replace(
            source.spec, page_id=source.spec.unit_id, unit_key="EQUIPMENT_RECOGNITION:page:000002"
        ),
    )
    other_eq = convert_equipment(recognition(equipment("2-Winding Transformer")), other)
    assert other_eq.source_groups[0].local_key != eq.source_groups[0].local_key


def test_visual_page_grounding_is_explicit_without_snippets_offsets_or_geometry():
    source, _ = page(image=True)
    eq = convert_equipment(recognition(equipment("Two-Winding Transformer", visual=True)), source)
    result = convert_attributes(
        attributes(attribute(visual=True)), attribute_sources(source), test_context(source, eq)
    )
    assert result.candidates[0].mapping_status == "MAPPED" and result.candidates[
        0
    ].numeric_value == Decimal("0.6")
    assert result.candidates[0].diagnostics["text_verified"] is False
    assert result.candidates[0].diagnostics["association"] == "VISUAL_REPORTED"
    item = result.evidence[0]
    assert item.source_snippet is None and item.text_start is None and item.location.region is None


def test_hybrid_cannot_rescue_forged_native_claims_or_borrow_vision_type_context():
    source, _ = page("Secondary Voltage: 600 V", image=True)
    eq = convert_equipment(recognition(equipment("Two-Winding Transformer", visual=True)), source)
    result = convert_attributes(
        attributes(attribute()), attribute_sources(source), test_context(source, eq)
    )
    assert (
        result.candidates[0].mapping_status == "UNMAPPED"
        and result.candidates[0].source_group_id is None
    )
    forged = attribute(quote="invented source quote")
    forged = forged.model_copy(
        update={"anchors": [*forged.anchors, SourceAnchor.model_validate(anchor(visual=True))]}
    )
    output = convert_attributes(
        attributes(forged), attribute_sources(source), test_context(source, eq)
    )
    assert not output.evidence and not output.candidates


def test_pinned_artifact_integrity_bounds_and_storage_error_contract():
    source, storage = page("native source")
    storage.objects["native"] = StoredObject(b"different", "text/plain")
    with pytest.raises(ValueError, match="integrity"):
        load_page_sources(source.spec, storage)
    source, storage = page("native source")
    with pytest.raises(ValueError, match="combined"):
        load_page_sources(source.spec, storage, max_total_bytes=1)
    storage.fail_on("get", TransientStorageError("temporarily unavailable"))
    with pytest.raises(TransientStorageError):
        load_page_sources(source.spec, storage)


def test_diagnostic_counts_are_bounded_and_cannot_overwrite_output_collection_counts():
    for counts in [{"candidates": 99}, {"rejected_ungrounded": True}, {"rejected_ungrounded": -1}]:
        with pytest.raises(ValidationError):
            WorkUnitOutput(diagnostic_counts=counts)


def test_image_header_dimensions_and_pixel_limits_are_verified_against_real_bytes():
    source, storage = page(image=True)
    with pytest.raises(ValueError, match="image"):
        load_page_sources(source.spec, storage, max_image_pixels=1)
    wrong = replace(source.spec, artifacts=(replace(source.spec.artifacts[0], width=21),))
    with pytest.raises(ValueError, match="image"):
        load_page_sources(wrong, storage)


def test_source_stream_is_closed_on_transient_read_failure(monkeypatch):
    source, storage = page("native")

    class Interrupted(BytesIO):
        def read(self, size=-1):
            raise TransientStorageError("temporary read failure")

    stream = Interrupted()
    monkeypatch.setattr(storage, "get", lambda key: stream)
    with pytest.raises(TransientStorageError):
        load_page_sources(source.spec, storage)
    assert stream.closed


def test_short_nonempty_stream_reads_are_not_mistaken_for_corrupt_artifacts(monkeypatch):
    source, storage = page("Texte é and source bytes")

    class Chunked(BytesIO):
        def read(self, size=-1):
            return super().read(min(3, size))

    stream = Chunked(source.text.encode())
    monkeypatch.setattr(storage, "get", lambda key: stream)
    assert load_page_sources(source.spec, storage).text == source.text
    assert stream.closed


def test_grounding_rules_have_a_pinned_resource_identity():
    import json
    from pathlib import Path

    expected = json.loads(
        (Path(__file__).parent / "fixtures/extraction/grounding_v1_identity.json").read_text()
    )
    assert grounding_identity() == expected


def test_unrelated_real_excerpts_cannot_be_added_as_support_for_another_claim():
    source, _ = page("2-Winding Transformer TX-1\n\nSome unrelated source statement")
    item = equipment("2-Winding Transformer TX-1")
    item = item.model_copy(
        update={
            "anchors": [
                *item.anchors,
                SourceAnchor.model_validate(anchor("Some unrelated source statement")),
            ]
        }
    )
    output = convert_equipment(recognition(item), source)
    assert len(output.evidence) == 1
    assert output.evidence[0].source_snippet == "2-Winding Transformer TX-1"


def test_multiple_visual_mentions_need_an_explicit_unique_tag_to_associate():
    source, _ = page(image=True)
    output = convert_equipment(
        recognition(
            equipment("Two-Winding Transformer TX-1", tag="TX-1", visual=True),
            equipment("Two-Winding Transformer TX-10", ref="eq2", tag="TX-10", visual=True),
        ),
        source,
    )
    context = test_context(source, output)
    detached = convert_attributes(
        attributes(attribute(visual=True)), attribute_sources(source), context
    )
    assert detached.candidates[0].source_group_id is None
    false_prefix = attribute("TX-10 Secondary Voltage: 600 V", visual=True)
    detached = convert_attributes(attributes(false_prefix), attribute_sources(source), context)
    assert not detached.candidates or detached.candidates[0].source_group_id is None


def test_foreign_recognition_owner_and_missing_roles_cannot_be_used():
    source, _ = page("2-Winding Transformer\nSecondary Voltage: 600 V")
    output = convert_equipment(recognition(equipment("2-Winding Transformer")), source)
    context = test_context(source, output)
    wrong = replace(context, document_id=source.spec.unit_id)
    with pytest.raises(ValueError, match="ownership"):
        convert_attributes(attributes(attribute()), attribute_sources(source), wrong)
    with pytest.raises(ValueError, match="outside pinned"):
        source.artifact("analysis_image")
    with pytest.raises(ValueError, match="version"):
        grounding_identity("engineering-grounding-v999")


def test_ambiguous_or_missed_competing_headers_disable_native_block_association():
    source, _ = page("2-Winding Transformer TX-1\nCable C-1\nSecondary Voltage: 600 V\n\nCable C-1")
    known = equipment("2-Winding Transformer TX-1")
    ambiguous = equipment("Cable C-1", ref="eq2", proposed="CABLE")
    for response in [recognition(known), recognition(known, ambiguous)]:
        output = convert_equipment(response, source)
        assert output.candidates[0].diagnostics["source_scope"] is None


def test_compound_frame_trip_source_clauses_are_exact_but_qualifiers_are_not_hidden():
    source, _ = page("LV Breaker CB-1 thermal-magnetic\n400 AF / 250 AT")
    eq = convert_equipment(
        recognition(equipment("LV Breaker CB-1 thermal-magnetic", proposed="LV_BREAKER")), source
    )
    values = [
        attribute(
            "400 AF", label="AF", value="400", unit="AF", key="frame_rating", proposed="LV_BREAKER"
        ),
        attribute(
            "250 AT",
            ref="a2",
            label="AT",
            value="250",
            unit="AT",
            key="trip_rating",
            proposed="LV_BREAKER",
        ),
    ]
    result = convert_attributes(
        attributes(*values), attribute_sources(source), test_context(source, eq)
    )
    assert [item.numeric_value for item in result.candidates] == [Decimal("400"), Decimal("250")]
    assert [item.source_snippet for item in result.evidence] == ["400 AF", "250 AT"]
    unverified, _ = page("LV Breaker CB-1 thermal-magnetic\n400 AF / 250 AT (not verified)")
    eq = convert_equipment(
        recognition(equipment("LV Breaker CB-1 thermal-magnetic", proposed="LV_BREAKER")),
        unverified,
    )
    result = convert_attributes(
        attributes(*values), attribute_sources(unverified), test_context(unverified, eq)
    )
    assert all(
        item.mapping_status == "UNMAPPED" and item.source_group_id is None
        for item in result.candidates
    )
    assert all("not verified" in item.source_snippet for item in result.evidence)
