"""Native correspondence requires shared producer origins, not matching substrings."""

import pytest

from powerforge_provenance.spatial_base import TextSpan, canonical_json
from powerforge_provenance.spatial_offsets import (
    NativeEmissionTrace,
    NativeOrigin,
    NativeOriginDataset,
    OriginFragment,
    map_native_occurrence,
    match_quote,
)
from spatial_support import artifact, snapshot, uid


def traces():
    source = snapshot(text="600 V\n600 V")
    dataset = NativeOriginDataset(
        id=uid("origins"),
        owner=source.prepared.owner,
        original=source.prepared.original,
        producer=source.body.producer,
        transform=source.body.transform,
        origins=(
            NativeOrigin(ref="left", raw_text="600 V", path=(0, 0)),
            NativeOrigin(ref="right", raw_text="600 V", path=(0, 1)),
        ),
    )
    data = canonical_json(dataset.model_dump(mode="json")).encode()
    origin = artifact(source.prepared.owner, "origins", "NATIVE_ORIGINS", data)
    a = NativeEmissionTrace(
        text_artifact=source.body.text_artifact,
        origin_artifact=origin,
        fragments=(
            OriginFragment(span=TextSpan(start=0, end=5), origin_ref="left", origin_start=0),
            OriginFragment(span=TextSpan(start=6, end=11), origin_ref="right", origin_start=0),
        ),
    )
    target = artifact(source.prepared.owner, "target", "NATIVE_POSITIONED_TEXT", source.text)
    b = NativeEmissionTrace(
        text_artifact=target,
        origin_artifact=origin,
        fragments=(
            OriginFragment(span=TextSpan(start=0, end=5), origin_ref="right", origin_start=0),
            OriginFragment(span=TextSpan(start=6, end=11), origin_ref="left", origin_start=0),
        ),
    )
    return source, a, b, data


def test_repeated_equal_text_maps_by_native_origin_occurrence_not_first_match():
    source, a, b, data = traces()
    result = map_native_occurrence(
        a, source.text, TextSpan(start=0, end=5), b.text_artifact, source.text, b, origin_data=data
    )
    assert result.status == "EXACT" and result.span == TextSpan(start=6, end=11)
    assert match_quote(a.text_artifact, source.text, "600 V").status == "AMBIGUOUS"


def test_equal_page_text_without_original_native_witness_is_unproven():
    source, a, b, data = traces()
    for trace, origin in ((None, data), (b, None)):
        result = map_native_occurrence(
            a,
            source.text,
            TextSpan(start=0, end=5),
            b.text_artifact,
            source.text,
            trace,
            origin_data=origin,
        )
        assert result.status == "UNPROVEN" and result.span is None


@pytest.mark.parametrize(
    "mutation", ["origin", "owner", "text", "dataset", "foreign_origin", "span"]
)
def test_invalid_native_witness_cannot_create_offsets(mutation):
    source, a, b, data = traces()
    if mutation == "origin":
        b = b.model_copy(
            update={
                "origin_artifact": b.origin_artifact.model_copy(update={"id": uid("other-origin")})
            }
        )
        result = map_native_occurrence(
            a,
            source.text,
            TextSpan(start=0, end=5),
            b.text_artifact,
            source.text,
            b,
            origin_data=data,
        )
        assert result.status == "UNPROVEN"
        return
    if mutation == "owner":
        target = b.text_artifact.model_copy(
            update={
                "owner": b.text_artifact.owner.model_copy(
                    update={"document_page_id": uid("other-page")}
                )
            }
        )
        b = b.model_copy(update={"text_artifact": target})
    elif mutation == "text":
        source = source.__class__(source.prepared, source.body, b"600 V\n999 V", source.geometry)
    elif mutation == "dataset":
        data = data + b" "
    elif mutation == "foreign_origin":
        b = b.model_copy(
            update={
                "fragments": (
                    b.fragments[0].model_copy(update={"origin_ref": "invented"}),
                    b.fragments[1],
                )
            }
        )
    else:
        b = b.model_copy(
            update={
                "fragments": (
                    b.fragments[0].model_copy(update={"span": TextSpan(start=99, end=104)}),
                    b.fragments[1],
                )
            }
        )
    with pytest.raises(ValueError):
        map_native_occurrence(
            a,
            source.text,
            TextSpan(start=0, end=5),
            b.text_artifact,
            source.text,
            b,
            origin_data=data,
        )


def test_missing_origin_ranges_and_noncontiguous_reordered_spans_do_not_get_a_fallback():
    source, a, b, data = traces()
    b = b.model_copy(update={"fragments": (b.fragments[0],)})
    result = map_native_occurrence(
        a, source.text, TextSpan(start=0, end=5), b.text_artifact, source.text, b, origin_data=data
    )
    assert result.status == "UNPROVEN"
    source, a, b, data = traces()
    result = map_native_occurrence(
        a, source.text, TextSpan(start=0, end=11), b.text_artifact, source.text, b, origin_data=data
    )
    assert result.status == "UNPROVEN"  # newline has no shared origin witness


def test_ocr_and_native_can_never_share_a_native_offset_mapping():
    source, a, b, data = traces()
    ocr = snapshot("OCR", text="600 V\n600 V")
    with pytest.raises(ValueError, match="OCR"):
        map_native_occurrence(
            a,
            source.text,
            TextSpan(start=0, end=5),
            ocr.body.text_artifact,
            ocr.text,
            None,
            origin_data=data,
        )
    with pytest.raises(ValueError):
        NativeEmissionTrace(
            text_artifact=ocr.body.text_artifact, origin_artifact=a.origin_artifact, fragments=()
        )


def test_unicode_offsets_use_codepoints_and_do_not_normalize_text():
    source = snapshot(text="TX-α 😀\ne\u0301 / é\n4/0 AWG")
    result = match_quote(source.body.text_artifact, source.text, "😀")
    assert result.span == TextSpan(start=5, end=6)
    assert match_quote(source.body.text_artifact, source.text, "e\u0301").span == TextSpan(
        start=7, end=9
    )
    assert match_quote(source.body.text_artifact, source.text, "é").span == TextSpan(
        start=12, end=13
    )
    assert (
        match_quote(
            source.body.text_artifact, source.text, "é", within=TextSpan(start=7, end=9)
        ).status
        == "MISSING"
    )
    with pytest.raises(ValueError):
        match_quote(source.body.text_artifact, source.text, "TX", within=TextSpan(start=0, end=99))


def test_duplicate_or_overlapping_native_origins_are_invalid_even_when_text_matches():
    source, a, b, data = traces()
    with pytest.raises(ValueError, match="more than once"):
        NativeEmissionTrace(
            text_artifact=a.text_artifact,
            origin_artifact=a.origin_artifact,
            fragments=(a.fragments[0], a.fragments[1].model_copy(update={"origin_ref": "left"})),
        )
