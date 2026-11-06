"""Actual native preparation of independently drawn PDFs; no expected layout from detectors."""

import json
from pathlib import Path
from uuid import uuid4

import pymupdf

from powerforge_document_processing.layout_derive import derive_layout, table_context
from powerforge_extraction.enrichment_prepare import prepare_page, sha
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_provenance.spatial_sources import OriginalDocument, PageArtifactRef, PageOwner
from powerforge_shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def drawn_table(*, ruled=True, rows=None, merged=False, nearby=False):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    if merged:
        # Authored 3x4 tile grid with a 2-column Voltage header and Equipment rowspan.
        for a, b in [
            ((30, 50), (550, 50)),
            ((30, 150), (550, 150)),
            ((30, 200), (550, 200)),
            ((30, 250), (550, 250)),
            ((210, 100), (550, 100)),
            ((30, 50), (30, 250)),
            ((210, 50), (210, 250)),
            ((380, 100), (380, 250)),
            ((550, 50), (550, 250)),
        ]:
            page.draw_line(a, b)
        for x, y, text in [
            (40, 80, "Equipment"),
            (220, 80, "Voltage"),
            (220, 130, "Primary"),
            (390, 130, "Secondary"),
            (40, 180, "TX-1"),
            (220, 180, "12470 V"),
            (390, 180, "600 V"),
            (40, 230, "TX-2"),
            (220, 230, "25000 V"),
            (390, 230, "600 V"),
        ]:
            page.insert_text((x, y), text, fontsize=12)
    else:
        rows = rows or [("Equipment", "Secondary (V)"), ("TX-1", "600"), ("TX-2", "600")]
        if ruled:
            for y in range(50, 51 + 45 * len(rows), 45):
                page.draw_line((30, y), (550, y))
            for x in (30, 270, 550):
                page.draw_line((x, 50), (x, 50 + 45 * len(rows)))
        for i, row in enumerate(rows):
            page.insert_text((40, 80 + 45 * i), row[0], fontsize=12)
            page.insert_text((280, 80 + 45 * i), row[1], fontsize=12)
    if nearby:
        page.insert_text((40, 30), "Transformer Schedule", fontsize=14)
        page.insert_text((40, 320), "Unrelated note TX-99 999 V", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def prepare_pdf(data):
    owner = PageOwner(
        document_id=uuid4(), processing_run_id=uuid4(), document_page_id=uuid4(), page_number=1
    )
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        pix = doc[0].get_pixmap()
        image = pix.tobytes("png")
        width, height = pix.width, pix.height
    original = OriginalDocument(
        document_id=owner.document_id, sha256=sha(data), size_bytes=len(data), format="pdf"
    )
    base = PageArtifactRef(
        id=uuid4(),
        owner=owner,
        role="ANALYSIS_IMAGE",
        sha256=sha(image),
        size_bytes=len(image),
        width_px=width,
        height_px=height,
    )
    configuration = json.loads(
        (ROOT / "tests/fixtures/enrichment/preparation_v1_environment.json").read_text()
    )["configuration"]
    profile = preparation_profile(
        Settings(
            _env_file=None,
            enrichment_enabled=True,
            enrichment_ocr_configuration=json.dumps(configuration),
        )
    )

    def no_ocr():
        raise AssertionError("Native fixture unexpectedly invoked OCR")

    return prepare_page(
        owner,
        original,
        data,
        (base,),
        {base.id: image},
        uuid4(),
        uuid4(),
        "0" * 64,
        profile,
        False,
        no_ocr,
    )


def sources(output):
    geometry = {
        r.ref: output.blobs[r.geometry_artifact.id][1] for r in output.manifest.representations
    }
    text = {r.ref: output.blobs[r.text_artifact.id][1] for r in output.manifest.representations}
    return geometry, text


def derive(output):
    geometry, text = sources(output)
    layout = derive_layout(output.manifest, geometry, text, uuid4(), uuid4(), uuid4())
    return layout, table_context(output.manifest, geometry, text, layout)


def alter_body(output, alias, change):
    from dataclasses import replace

    from powerforge_provenance.spatial_base import canonical_json
    from powerforge_provenance.spatial_sources import PositionedText

    descriptor = next(r for r in output.manifest.representations if r.ref == alias)
    body = PositionedText.model_validate_json(output.blobs[descriptor.geometry_artifact.id][1])
    body = PositionedText.model_validate(change(body))
    data = canonical_json(body.model_dump(mode="json")).encode()
    ref = descriptor.geometry_artifact.model_copy(
        update={"sha256": sha(data), "size_bytes": len(data)}
    )
    new_descriptor = descriptor.model_copy(
        update={
            "geometry_artifact": ref,
            "token_count": len(body.tokens),
            "line_count": len(body.lines),
            "block_count": len(body.blocks),
            "primitive_count": len(body.native_primitives),
        }
    )
    prepared = output.manifest.model_copy(
        update={
            "representations": tuple(
                new_descriptor if r.ref == alias else r for r in output.manifest.representations
            )
        }
    )
    blobs = {**output.blobs, ref.id: (ref, data)}
    return replace(output, manifest=prepared, blobs=blobs)
