"""Pinned source/binding consistency and conservative spatial support; no lifecycle claims."""

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from powerforge_provenance.spatial_base import POLICY, TextSpan
from powerforge_provenance.spatial_geometry import NormalizedRegion
from powerforge_provenance.spatial_layout import (
    EnrichmentResultRef,
    SourceBinding,
    SourceSupport,
    SpatialPage,
    SpatialRegion,
    SpatialRelation,
    check_binding,
    resolve_region_support,
)
from powerforge_provenance.spatial_sources import (
    NativePrimitive,
    PreparationInput,
    PreparedPage,
    checked_positioned_text,
    load_positioned_text,
)
from spatial_support import producer, replace_body, snapshot, uid


def region(ref="cell", *tokens):
    return SpatialRegion(
        ref=ref,
        kind="CELL",
        region=None,
        support=tuple(
            SourceSupport(representation_ref="native", kind="TOKEN", ref=t)
            for t in (tokens or ("w1",))
        ),
    )


def result_ref(prepared):
    return EnrichmentResultRef(
        id=prepared.id,
        owner=prepared.owner,
        producer_run_id=prepared.producer_run_id,
        producer_work_unit_id=prepared.producer_work_unit_id,
        result_kind="PREPARED",
        manifest_sha256=prepared.identity_hash,
        producer_sha256=prepared.preparation_sha256,
    )


def spatial_page(prepared):
    return SpatialPage(
        id=uid("spatial"),
        owner=prepared.owner,
        producer_run_id=uid("layout-run"),
        producer_work_unit_id=uid("layout-unit"),
        producer=producer("SPATIAL_LAYOUT"),
        prepared=result_ref(prepared),
        regions=(region("left", "w1"), region("right", "w2")),
        relations=(SpatialRelation(kind="BEFORE", left="left", right="right", basis="UNRESOLVED"),),
    )


def test_exact_positioned_tokens_keep_two_equal_values_as_separate_occurrences():
    source = snapshot()
    body, text = load_positioned_text(source.prepared, "native", source.geometry, source.text)
    assert text == "TX-1\n600\n600"
    one = resolve_region_support(
        source.prepared, region("one", "w1"), {"native": source.geometry}, {"native": source.text}
    )
    two = resolve_region_support(
        source.prepared, region("two", "w2"), {"native": source.geometry}, {"native": source.text}
    )
    assert one.region == NormalizedRegion(x="0.1", y="0.2", width="0.1", height="0.02")
    assert two.region == NormalizedRegion(x="0.1", y="0.3", width="0.1", height="0.02")
    assert body.tokens[1].span != body.tokens[2].span
    assert one.structure_basis == two.structure_basis == "UNRESOLVED"
    assert one.printed_text_independently_verified is False


def test_geometry_union_does_not_establish_table_structure_or_equipment_ownership():
    source = snapshot()
    answer = resolve_region_support(
        source.prepared,
        region("wide", "w0", "w2"),
        {"native": source.geometry},
        {"native": source.text},
    )
    assert answer.region == NormalizedRegion(x="0.1", y="0.1", width="0.1", height="0.22")
    assert answer.structure_basis == "UNRESOLVED"
    with pytest.raises(ValueError):
        type(answer).model_validate_json(
            json.dumps(
                {**answer.model_dump(mode="json"), "structure_basis": "NATIVE_GEOMETRY_SUPPORTED"}
            )
        )


@pytest.mark.parametrize("kind", ["NATIVE_PDF", "OCR"])
def test_unavailable_geometry_remains_null_with_raw_reading_retained(kind):
    source = snapshot(kind, missing_geometry=True)
    alias = "native" if kind == "NATIVE_PDF" else "ocr"
    support = region().model_copy(
        update={"support": (SourceSupport(representation_ref=alias, kind="TOKEN", ref="w1"),)}
    )
    answer = resolve_region_support(
        source.prepared, support, {alias: source.geometry}, {alias: source.text}
    )
    assert answer.region is None and answer.basis == "NONE"
    assert source.body.tokens[1].raw_text == "600"


@pytest.mark.parametrize(
    "mutation", ["hash", "page", "producer", "frame", "token", "source_role", "raw_text", "span"]
)
def test_mismatched_positioned_sources_are_rejected_at_detached_loading(mutation):
    source = snapshot()
    if mutation == "hash":
        source = replace(source, geometry=source.geometry + b" ")
    elif mutation == "page":
        source = replace_body(
            source,
            source.body.model_copy(
                update={
                    "owner": source.body.owner.model_copy(
                        update={"document_page_id": uid("foreign")}
                    )
                }
            ),
        )
    elif mutation == "producer":
        source = replace_body(
            source,
            source.body.model_copy(
                update={
                    "producer": source.body.producer.model_copy(
                        update={"engine_version": "different"}
                    )
                }
            ),
        )
    elif mutation == "frame":
        transform = source.body.transform.model_copy(
            update={
                "target_frame": source.body.transform.target_frame.model_copy(
                    update={"width": Decimal("501")}
                )
            }
        )
        source = replace_body(source, source.body.model_copy(update={"transform": transform}))
    elif mutation == "token":
        source = replace_body(
            source,
            source.body.model_copy(
                update={
                    "lines": (
                        source.body.lines[0].model_copy(update={"token_refs": ("foreign",)}),
                        *source.body.lines[1:],
                    )
                }
            ),
        )
    elif mutation == "source_role":
        source = replace_body(
            source,
            source.body.model_copy(
                update={
                    "text_artifact": source.body.text_artifact.model_copy(
                        update={"role": "OCR_TEXT"}
                    )
                }
            ),
        )
    elif mutation == "raw_text":
        source = replace_body(
            source,
            source.body.model_copy(
                update={
                    "tokens": (
                        source.body.tokens[0].model_copy(update={"raw_text": "CB-1"}),
                        *source.body.tokens[1:],
                    )
                }
            ),
        )
    else:
        source = replace_body(
            source,
            source.body.model_copy(
                update={
                    "tokens": (
                        *source.body.tokens[:-1],
                        source.body.tokens[-1].model_copy(
                            update={"span": TextSpan(start=10, end=13)}
                        ),
                    )
                }
            ),
        )
    with pytest.raises(ValueError):
        load_positioned_text(source.prepared, "native", source.geometry, source.text)


def test_fabricated_foreign_or_duplicate_region_support_and_boxes_are_rejected():
    source = snapshot()
    for support in (
        (SourceSupport(representation_ref="foreign", kind="TOKEN", ref="w1"),),
        (SourceSupport(representation_ref="native", kind="TOKEN", ref="invented"),),
    ):
        with pytest.raises(ValueError):
            resolve_region_support(
                source.prepared,
                region().model_copy(update={"support": support}),
                {"native": source.geometry},
                {"native": source.text},
            )
    with pytest.raises(ValueError, match="Duplicate"):
        SpatialRegion(
            ref="x", kind="CELL", region=None, support=(region().support[0], region().support[0])
        )
    with pytest.raises(ValueError, match="differs"):
        resolve_region_support(
            source.prepared,
            region().model_copy(
                update={"region": NormalizedRegion(x="0", y="0", width="1", height="1")}
            ),
            {"native": source.geometry},
            {"native": source.text},
        )


def test_native_vector_support_can_bound_a_sparse_cell_without_inventing_text():
    source = snapshot()
    primitives = (
        NativePrimitive(
            ref="top", kind="SEGMENT", points=({"x": "100", "y": "100"}, {"x": "300", "y": "100"})
        ),
        NativePrimitive(
            ref="bottom",
            kind="SEGMENT",
            points=({"x": "100", "y": "200"}, {"x": "300", "y": "200"}),
        ),
    )
    source = replace_body(source, source.body.model_copy(update={"native_primitives": primitives}))
    support = SpatialRegion(
        ref="empty-cell",
        kind="CELL",
        region=None,
        support=tuple(
            SourceSupport(representation_ref="native", kind="NATIVE_PRIMITIVE", ref=p.ref)
            for p in primitives
        ),
    )
    answer = resolve_region_support(
        source.prepared, support, {"native": source.geometry}, {"native": source.text}
    )
    assert answer.region == NormalizedRegion(x="0.1", y="0.1", width="0.2", height="0.1")
    assert answer.structure_basis == "UNRESOLVED"
    line = support.model_copy(update={"support": (support.support[0],)})
    assert (
        resolve_region_support(
            source.prepared, line, {"native": source.geometry}, {"native": source.text}
        ).region
        is None
    )
    ocr = snapshot("OCR")
    with pytest.raises(ValueError, match="native PDF"):
        checked_positioned_text(
            ocr.body.model_copy(update={"native_primitives": primitives}), ocr.text
        )


@pytest.mark.parametrize("kind", ["BEFORE", "HEADER_FOR", "CONTAINS"])
def test_cyclic_and_foreign_spatial_relationships_are_rejected(kind):
    page = spatial_page(snapshot().prepared)
    for relations in (
        (
            SpatialRelation(kind=kind, left="left", right="right", basis="UNRESOLVED"),
            SpatialRelation(kind=kind, left="right", right="left", basis="UNRESOLVED"),
        ),
        (SpatialRelation(kind=kind, left="left", right="foreign", basis="UNRESOLVED"),),
    ):
        with pytest.raises(ValueError):
            SpatialPage.model_validate_json(
                page.model_copy(update={"relations": relations}).model_dump_json()
            )


def test_pinned_bindings_include_exact_versions_producers_and_selected_sources():
    prepared = snapshot().prepared
    spatial = spatial_page(prepared)
    spatial_ref = EnrichmentResultRef(
        id=spatial.id,
        owner=prepared.owner,
        producer_run_id=spatial.producer_run_id,
        producer_work_unit_id=spatial.producer_work_unit_id,
        result_kind="SPATIAL",
        manifest_sha256=spatial.identity_hash,
        producer_sha256=spatial.producer.identity_hash,
    )
    binding = SourceBinding(
        owner=prepared.owner,
        prepared=result_ref(prepared),
        spatial=spatial_ref,
        selected_representations=("native",),
    )
    check_binding(binding, prepared, spatial)
    for changed in (
        binding.model_copy(update={"spatial": None}),
        binding.model_copy(update={"selected_representations": ("latest",)}),
        binding.model_copy(
            update={"prepared": binding.prepared.model_copy(update={"manifest_sha256": "0" * 64})}
        ),
        binding.model_copy(
            update={
                "spatial": binding.spatial.model_copy(update={"producer_run_id": uid("foreign")})
            }
        ),
    ):
        with pytest.raises(ValueError):
            check_binding(changed, prepared, spatial)
    with pytest.raises(ValueError, match="missing"):
        check_binding(binding, prepared, None)
    with pytest.raises(ValueError):
        EnrichmentResultRef.model_validate_json(
            json.dumps({**spatial_ref.model_dump(mode="json"), "producer_purpose": "EXTRACTION"})
        )


def test_preparation_target_hash_changes_with_material_sources_or_configuration():
    source = snapshot()
    prepared = source.prepared
    inputs = PreparationInput(
        original=prepared.original,
        processing_run_id=prepared.owner.processing_run_id,
        selected_pages=(1,),
        base_artifacts=prepared.base_artifacts,
        expected_producers=(source.body.producer,),
        selection_policy_sha256="4" * 64,
        raster_policy_sha256="5" * 64,
        limits_sha256="6" * 64,
    )
    assert (
        inputs.identity_hash
        != inputs.model_copy(update={"selection_policy_sha256": "7" * 64}).identity_hash
    )
    for changed in (
        inputs.model_copy(update={"selected_pages": (1, 1)}),
        inputs.model_copy(
            update={
                "base_artifacts": (
                    prepared.base_artifacts[0].model_copy(
                        update={
                            "owner": prepared.owner.model_copy(
                                update={"processing_run_id": uid("foreign")}
                            )
                        }
                    ),
                )
            }
        ),
    ):
        with pytest.raises(ValueError):
            PreparationInput.model_validate_json(changed.model_dump_json())
    with pytest.raises(ValueError):
        PreparedPage.model_validate_json(
            json.dumps({**prepared.model_dump(mode="json"), "text_coverage": "90%"})
        )
    assert prepared.text_coverage == "UNKNOWN"


def test_mutable_model_copy_is_not_an_escape_from_bounds_versions_or_immutable_membership():
    source = snapshot()
    with pytest.raises(ValueError):
        source.body.tokens[0].raw_text = "invented"
    with pytest.raises(TypeError):
        source.body.tokens[0] = source.body.tokens[1]
    for change in (
        {"version": "positioned-text-future"},
        {"tokens": source.body.tokens * (POLICY["max_tokens"] + 1)},
    ):
        with pytest.raises(ValueError):
            checked_positioned_text(source.body.model_copy(update=change), source.text)


def test_native_quad_direction_and_crossed_or_collapsed_geometry_keep_their_meaning():
    source = snapshot()
    token = source.body.tokens[1]
    quad = (
        {"x": "100", "y": "200"},
        {"x": "200", "y": "205"},
        {"x": "195", "y": "220"},
        {"x": "100", "y": "215"},
    )
    from powerforge_provenance.spatial_sources import PositionedLine, PositionedToken

    token = PositionedToken.model_validate_json(
        json.dumps({**token.model_dump(mode="json"), "source_quad": quad})
    )
    source = replace_body(
        source,
        source.body.model_copy(
            update={"tokens": (source.body.tokens[0], token, source.body.tokens[2])}
        ),
    )
    result = resolve_region_support(
        source.prepared, region(), {"native": source.geometry}, {"native": source.text}
    )
    assert result.region == NormalizedRegion(x="0.1", y="0.2", width="0.1", height="0.02")
    line = PositionedLine(ref="vertical", engine_order=0, token_refs=("w1",), direction=("0", "1"))
    assert line.direction == (0, 1)  # preserved engine direction, not a visual order inference
    with pytest.raises(ValueError):
        PositionedLine(ref="invalid", engine_order=0, token_refs=("w1",), direction=("0", "0"))
    with pytest.raises(ValueError):
        PositionedToken.model_validate_json(
            json.dumps(
                {
                    **token.model_dump(mode="json"),
                    "source_quad": (quad[0], quad[2], quad[1], quad[3]),
                }
            )
        )


def test_hybrid_readings_keep_separate_occurrences_and_ocr_geometry_is_not_native():
    native, ocr = snapshot(), snapshot("OCR")
    prepared = PreparedPage.model_validate(
        native.prepared.model_copy(
            update={
                "representations": (
                    *native.prepared.representations,
                    *ocr.prepared.representations,
                ),
                "ocr_decision": "RUN",
            }
        )
    )
    support = SpatialRegion(
        ref="aligned-proposal",
        kind="CONTENT",
        region=None,
        support=(
            SourceSupport(representation_ref="native", kind="TOKEN", ref="w1"),
            SourceSupport(representation_ref="ocr", kind="TOKEN", ref="w1"),
        ),
    )
    answer = resolve_region_support(
        prepared,
        support,
        {"native": native.geometry, "ocr": ocr.geometry},
        {"native": native.text, "ocr": ocr.text},
    )
    assert answer.basis == "MIXED_SOURCE_GEOMETRY" and answer.structure_basis == "UNRESOLVED"
    assert len(answer.support) == 2  # no fusion or claim deduplication occurs in M1
    with pytest.raises(ValueError, match="decision"):
        PreparedPage.model_validate(
            prepared.model_copy(update={"ocr_decision": "SKIP_NATIVE_SUFFICIENT"})
        )
    with pytest.raises(ValueError):
        PreparedPage.model_validate(
            prepared.model_copy(
                update={"page_frame": prepared.page_frame.model_copy(update={"unit": "PIXELS"})}
            )
        )


def test_derived_ocr_rasters_must_be_explicit_members_of_the_prepared_snapshot():
    from spatial_support import artifact

    source = snapshot("OCR")
    image = artifact(
        source.prepared.owner, "derived-raster", "OCR_INPUT_IMAGE", b"authored-raster", image=True
    )
    source = replace_body(source, source.body.model_copy(update={"input_image": image}))
    with pytest.raises(ValueError, match="raster"):
        load_positioned_text(source.prepared, "ocr", source.geometry, source.text)
    source = replace(
        source,
        prepared=PreparedPage.model_validate(
            source.prepared.model_copy(update={"derived_images": (image,)})
        ),
    )
    assert (
        load_positioned_text(source.prepared, "ocr", source.geometry, source.text)[0].input_image
        == image
    )
    foreign = image.model_copy(update={"producer_work_unit_id": uid("foreign-image-unit")})
    with pytest.raises(ValueError, match="producer"):
        PreparedPage.model_validate(
            source.prepared.model_copy(update={"derived_images": (foreign,)})
        )


@pytest.mark.parametrize(
    "field,limit",
    [
        ("character_count", "max_text_characters"),
        ("token_count", "max_tokens"),
        ("line_count", "max_lines"),
        ("block_count", "max_blocks"),
        ("primitive_count", "max_native_primitives"),
    ],
)
def test_page_count_budget_applies_across_native_and_ocr_representations(field, limit):
    native, ocr = snapshot(), snapshot("OCR")
    descriptors = []
    for source in (native, ocr):
        descriptor = source.prepared.representations[0]
        updates = {field: POLICY[limit] // 2 + 1}
        if field == "character_count":
            updates["text_artifact"] = descriptor.text_artifact.model_copy(
                update={"size_bytes": updates[field]}
            )
        descriptors.append(type(descriptor).model_validate(descriptor.model_copy(update=updates)))
    with pytest.raises(ValueError, match="Combined page representations"):
        PreparedPage.model_validate(
            native.prepared.model_copy(
                update={"representations": tuple(descriptors), "ocr_decision": "RUN"}
            )
        )


def test_page_geometry_byte_budget_applies_across_native_and_ocr_representations():
    native, ocr = snapshot(), snapshot("OCR")
    descriptors = tuple(
        d.model_copy(
            update={
                "geometry_artifact": d.geometry_artifact.model_copy(
                    update={"size_bytes": POLICY["max_manifest_bytes"] // 2 + 1}
                )
            }
        )
        for d in (native.prepared.representations[0], ocr.prepared.representations[0])
    )
    with pytest.raises(ValueError, match="Combined page geometry"):
        PreparedPage.model_validate(
            native.prepared.model_copy(
                update={"representations": descriptors, "ocr_decision": "RUN"}
            )
        )


@pytest.mark.parametrize("field", ["character_count", "token_count", "line_count", "block_count"])
def test_underreported_manifest_counts_cannot_bypass_loaded_page_budgets(field):
    source = snapshot()
    descriptor = source.prepared.representations[0]
    prepared = PreparedPage.model_validate(
        source.prepared.model_copy(
            update={
                "representations": (
                    descriptor.model_copy(update={field: getattr(descriptor, field) - 1}),
                )
            }
        )
    )
    with pytest.raises(ValueError, match="Actual positioned counts"):
        load_positioned_text(prepared, "native", source.geometry, source.text)
