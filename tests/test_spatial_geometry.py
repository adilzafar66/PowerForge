"""Independent coordinate examples and rejection controls for the pure M1 boundary."""

from decimal import Decimal, localcontext

import pytest

from powerforge_provenance.spatial_geometry import (
    CoordinateFrame,
    NormalizedRegion,
    Rectangle,
    UprightTransform,
    normalize_rectangle,
)


@pytest.mark.parametrize(
    "rotation,mirror_x,mirror_y,expected",
    [
        (0, False, False, ("0.1", "0.2", "0.2", "0.1")),
        (0, True, False, ("0.7", "0.2", "0.2", "0.1")),
        (180, False, False, ("0.7", "0.7", "0.2", "0.1")),
        (0, False, True, ("0.1", "0.7", "0.2", "0.1")),
        (270, True, False, ("0.2", "0.1", "0.1", "0.2")),
        (90, False, False, ("0.7", "0.1", "0.1", "0.2")),
        (90, True, False, ("0.7", "0.7", "0.1", "0.2")),
        (270, False, False, ("0.2", "0.7", "0.1", "0.2")),
    ],
)
def test_eight_image_orientations_and_quarter_turn_axis_changes(
    rotation, mirror_x, mirror_y, expected
):
    source = CoordinateFrame(unit="PIXELS", width="200", height="100")
    target = CoordinateFrame(
        unit="PDF_POINTS",
        width="100" if rotation in (90, 270) else "200",
        height="200" if rotation in (90, 270) else "100",
    )
    transform = UprightTransform(
        source_frame=source,
        target_frame=target,
        source_region=source.bounds,
        target_region=target.bounds,
        rotation_degrees=rotation,
        mirror_x=mirror_x,
        mirror_y=mirror_y,
    )
    box = transform.map_rectangle(Rectangle(x="20", y="20", width="40", height="10"))
    assert (box.x, box.y, box.width, box.height) == tuple(Decimal(v) for v in expected)


def test_crop_padding_scaling_and_nonzero_pdf_origins_are_explicit():
    source = CoordinateFrame(unit="PIXELS", width="200", height="100")
    target = CoordinateFrame(unit="PDF_POINTS", width="1000", height="1000")
    transform = UprightTransform(
        source_frame=source,
        target_frame=target,
        source_region=Rectangle(x="10", y="10", width="180", height="80"),
        target_region=Rectangle(x="100", y="200", width="360", height="160"),
    )
    box = transform.map_rectangle(Rectangle(x="28", y="18", width="36", height="8"))
    assert box == NormalizedRegion(x="0.136", y="0.216", width="0.072", height="0.016")
    pdf = CoordinateFrame(
        unit="PDF_POINTS", width="200", height="100", origin_x="-10", origin_y="20"
    )
    assert normalize_rectangle(
        Rectangle(x="10", y="40", width="40", height="10"), pdf
    ) == NormalizedRegion(x="0.1", y="0.2", width="0.2", height="0.1")
    with pytest.raises(ValueError, match="crop"):
        transform.map_rectangle(Rectangle(x="0", y="18", width="36", height="8"))


@pytest.mark.parametrize(
    "changes",
    [
        {"x": "NaN"},
        {"y": "Infinity"},
        {"width": "0"},
        {"height": "-1"},
        {"x": 0.1},
        {"width": True},
        {"x": "0." + "0" * 101 + "1"},
        {"width": "1e-19"},
    ],
)
def test_invalid_or_unsupported_exact_geometry_is_not_coerced(changes):
    with pytest.raises(ValueError):
        Rectangle(**{"x": "0", "y": "0", "width": "10", "height": "10", **changes})


@pytest.mark.parametrize("rotation", [45, 360, True, 90.0, "90"])
def test_unsupported_rotation_has_no_inference_or_fallback(rotation):
    frame = CoordinateFrame(unit="PIXELS", width="100", height="100")
    with pytest.raises(ValueError):
        UprightTransform(
            source_frame=frame,
            target_frame=frame,
            source_region=frame.bounds,
            target_region=frame.bounds,
            rotation_degrees=rotation,
        )


def test_outside_page_zero_area_and_hidden_shear_are_rejected():
    frame = CoordinateFrame(unit="PIXELS", width="100", height="100")
    for box in (
        Rectangle(x="95", y="0", width="10", height="10"),
        Rectangle(x="-1", y="0", width="10", height="10"),
    ):
        with pytest.raises(ValueError, match="outside"):
            normalize_rectangle(box, frame)
    with pytest.raises(ValueError):
        NormalizedRegion(x="0.9", y="0", width="0.2", height="1")
    with pytest.raises(ValueError):
        UprightTransform(
            source_frame=frame,
            target_frame=frame,
            source_region=frame.bounds,
            target_region=frame.bounds,
            shear="0.1",
        )


def test_decimal_context_rounding_cannot_change_identity_or_make_offpage_boxes_valid():
    frame = CoordinateFrame(unit="PIXELS", width="3", height="3")
    with localcontext() as ctx:
        ctx.prec = 6
        box = normalize_rectangle(Rectangle(x="1", y="1", width="2", height="2"), frame)
    assert box == NormalizedRegion(
        x="0.333333333333", y="0.333333333333", width="0.666666666667", height="0.666666666667"
    )
    assert box.right == box.bottom == 1
