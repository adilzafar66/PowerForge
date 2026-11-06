"""Real native PDF extraction and observable eligibility; independent authored inputs."""

from io import BytesIO

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from powerforge_document_processing.native_spatial import eligibility, extract_native, rasterize_pdf


def native_pdf(rotation=0, crop=False, embedded=False):
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=400)
    page.insert_text((70, 80), "TX-1 600 V", fontsize=16)
    page.insert_text((70, 140), "TX-2 600 V", fontsize=16)
    page.insert_text((300, 80), "400 AF / 250 AT", fontsize=12)
    page.draw_rect(pymupdf.Rect(60, 50, 450, 170))
    if embedded:
        page.insert_image(pymupdf.Rect(60, 180, 450, 290), stream=scan_png())
    if crop:
        page.set_cropbox(pymupdf.Rect(30, 20, 480, 380))
    page.set_rotation(rotation)
    data = doc.tobytes()
    doc.close()
    return data


def scan_png():
    image = Image.new("RGB", (1800, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    draw.multiline_text(
        (70, 60),
        "TX-1\n750 kVA 13.8 kV\n400 AF / 250 AT\n4/0 AWG",
        font=font,
        fill="black",
        spacing=30,
    )
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("crop", [False, True])
def test_real_native_coordinates_preserve_library_occurrence_order_and_upright_transform(
    rotation, crop
):
    from powerforge_provenance.spatial_geometry import CoordinateFrame, Rectangle, UprightTransform

    data = native_pdf(rotation, crop)
    native = extract_native(data, 1)
    # Authored insertion/crop points, independent of the extracted result.
    expected_size = (450, 360) if crop else (500, 400)
    assert (float(native.source_width), float(native.source_height)) == expected_size
    assert float(native.readings[0].box[0]) == (40 if crop else 70)
    assert [r.text for r in native.readings].count("600") == 2
    assert [r.text for r in native.readings].index("TX-2") < [
        r.text for r in native.readings
    ].index("400")
    source = CoordinateFrame(
        unit="PDF_POINTS", width=native.source_width, height=native.source_height
    )
    target = CoordinateFrame(unit="PDF_POINTS", width=native.width, height=native.height)
    transform = UprightTransform(
        source_frame=source,
        target_frame=target,
        source_region=source.bounds,
        target_region=target.bounds,
        rotation_degrees=rotation,
    )
    for reading in native.readings:
        assert reading.box is not None
        x, y, w, h = reading.box
        region = transform.map_rectangle(Rectangle(x=x, y=y, width=w, height=h))
        assert 0 <= region.x < region.right <= 1 and 0 <= region.y < region.bottom <= 1
    assert native.primitives
    image, width, height = rasterize_pdf(data, 1)
    assert image.startswith(b"\x89PNG") and width * height <= 20_000_000


def test_eligibility_uses_observations_and_unknown_content_requires_selection():
    plain = extract_native(native_pdf(), 1)
    assert eligibility(plain, False) == (False, "NATIVE_READINGS_PRESENT_NO_RASTER_OBSERVED")
    hybrid = extract_native(native_pdf(embedded=True), 1)
    assert hybrid.raster_boxes
    assert eligibility(hybrid, False) == (
        False,
        "UNKNOWN_RASTER_CONTENT_EXPLICIT_SELECTION_REQUIRED",
    )
    assert eligibility(hybrid, True) == (True, "EXPLICIT_WHOLE_PAGE")
    assert eligibility(None, False) == (True, "NO_NATIVE_READINGS")
    from dataclasses import replace

    broken = replace(plain, replacement_characters=1, characters=20)
    assert eligibility(broken, False)[0] is True


def test_real_blank_native_and_invalid_pdf_are_explicit():
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    assert eligibility(extract_native(data, 1), False)[0]
    for payload, page in ((data, 2), (b"corrupted", 1)):
        with pytest.raises((ValueError, pymupdf.FileDataError)):
            extract_native(payload, page)
