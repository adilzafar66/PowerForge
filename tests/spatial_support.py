"""Authored detached source shapes. No OCR, PDF extraction, database or model execution."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from powerforge_provenance.spatial_base import canonical_json
from powerforge_provenance.spatial_geometry import CoordinateFrame, Rectangle, UprightTransform
from powerforge_provenance.spatial_sources import (
    EnrichmentArtifactRef,
    OriginalDocument,
    PageArtifactRef,
    PageOwner,
    PositionedBlock,
    PositionedLine,
    PositionedText,
    PositionedToken,
    PreparedPage,
    ProducerIdentity,
    RepresentationRef,
)

ROOT = Path(__file__).resolve().parents[1]


def uid(name):
    return uuid5(NAMESPACE_URL, "powerforge-spatial-contract-fixture/" + name)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def producer(kind="NATIVE_PDF"):
    return ProducerIdentity(
        kind=kind,
        adapter="authored-contract-fixture",
        adapter_version="1",
        engine="fixture-not-a-live-engine",
        engine_version="fixture-1",
        build_sha256="1" * 64,
        configuration_sha256="2" * 64,
    )


def artifact(owner, label, role, data=b"", *, image=False):
    return EnrichmentArtifactRef(
        id=uid(label),
        owner=owner,
        result_id=uid("prepared"),
        producer_run_id=uid("run"),
        producer_work_unit_id=uid("unit"),
        role=role,
        sha256=sha(data),
        size_bytes=len(data),
        width_px=1000 if image else None,
        height_px=1000 if image else None,
    )


@dataclass(frozen=True)
class SourceSnapshot:
    prepared: PreparedPage
    body: PositionedText
    text: bytes
    geometry: bytes


def snapshot(kind="NATIVE_PDF", *, text="TX-1\n600\n600", missing_geometry=False):
    owner = PageOwner(
        document_id=uid("document"),
        processing_run_id=uid("processing"),
        document_page_id=uid("page"),
        page_number=1,
    )
    # No actual processing is implied by these synthetic source descriptors.
    original_data = b"synthetic-source-contract-only:" + text.encode()
    original = OriginalDocument(
        document_id=owner.document_id,
        sha256=sha(original_data),
        size_bytes=len(original_data),
        format="pdf",
    )
    source_frame = CoordinateFrame(
        unit="PDF_POINTS" if kind == "NATIVE_PDF" else "PIXELS", width="1000", height="1000"
    )
    page_frame = CoordinateFrame(unit="PDF_POINTS", width="500", height="500")
    transform = UprightTransform(
        source_frame=source_frame,
        target_frame=page_frame,
        source_region=source_frame.bounds,
        target_region=page_frame.bounds,
    )
    image_data = b"authored-image-placeholder-not-decoded-in-M1"
    image = PageArtifactRef(
        id=uid("image"),
        owner=owner,
        role="ANALYSIS_IMAGE",
        sha256=sha(image_data),
        size_bytes=len(image_data),
        width_px=1000,
        height_px=1000,
    )
    encoded = text.encode()
    text_artifact = artifact(
        owner,
        "text-" + kind,
        "NATIVE_POSITIONED_TEXT" if kind == "NATIVE_PDF" else "OCR_TEXT",
        encoded,
    )
    tokens = []
    at = 0
    for order, word in enumerate(text.split("\n")):
        tokens.append(
            PositionedToken(
                ref=f"w{order}",
                raw_text=word,
                span={"start": at, "end": at + len(word)},
                engine_order=order,
                source_box=None
                if missing_geometry
                else Rectangle(x="100", y=str(100 + order * 100), width="100", height="20"),
                geometry_unavailable_reason="UNSUPPORTED_ORIENTATION" if missing_geometry else None,
            )
        )
        at += len(word) + 1
    lines = tuple(
        PositionedLine(ref=f"line{i}", engine_order=i, token_refs=(t.ref,))
        for i, t in enumerate(tokens)
    )
    body = PositionedText(
        id=uid("geometry-" + kind),
        owner=owner,
        producer=producer(kind),
        text_artifact=text_artifact,
        input_image=image if kind == "OCR" else None,
        transform=transform,
        serialization="native-emission-v1" if kind == "NATIVE_PDF" else "ocr-engine-lines-v1",
        tokens=tuple(tokens),
        lines=lines,
        blocks=(
            PositionedBlock(
                ref="block", engine_order=0, line_refs=tuple(line.ref for line in lines)
            ),
        ),
    )
    geometry = canonical_json(body.model_dump(mode="json")).encode()
    geometry_artifact = artifact(owner, "geometry-" + kind, "POSITIONED_READINGS", geometry)
    descriptor = RepresentationRef(
        ref="native" if kind == "NATIVE_PDF" else "ocr",
        text_artifact=text_artifact,
        geometry_artifact=geometry_artifact,
        producer_sha256=body.producer.identity_hash,
        character_count=len(text),
        token_count=len(body.tokens),
        line_count=len(body.lines),
        block_count=len(body.blocks),
        primitive_count=len(body.native_primitives),
    )
    prepared = PreparedPage(
        id=uid("prepared"),
        owner=owner,
        original=original,
        producer_run_id=uid("run"),
        producer_work_unit_id=uid("unit"),
        preparation_sha256="3" * 64,
        page_frame=page_frame,
        base_artifacts=(image,),
        representations=(descriptor,),
        ocr_decision="RUN" if kind == "OCR" else "SKIP_NATIVE_SUFFICIENT",
        ocr_reason="AUTHORED_CONTRACT_CASE",
    )
    return SourceSnapshot(prepared, body, encoded, geometry)


def replace_body(source, body):
    geometry = canonical_json(body.model_dump(mode="json")).encode()
    descriptor = source.prepared.representations[0]
    descriptor = descriptor.model_copy(
        update={
            "geometry_artifact": descriptor.geometry_artifact.model_copy(
                update={"sha256": sha(geometry), "size_bytes": len(geometry)}
            ),
            "character_count": len(source.text.decode()),
            "token_count": len(body.tokens),
            "line_count": len(body.lines),
            "block_count": len(body.blocks),
            "primitive_count": len(body.native_primitives),
        }
    )
    prepared = source.prepared.model_copy(update={"representations": (descriptor,)})
    return SourceSnapshot(prepared, body, source.text, geometry)
