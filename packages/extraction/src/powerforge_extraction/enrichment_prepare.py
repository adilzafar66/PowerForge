"""Build one immutable page snapshot from exact supplied sources and raw engine output."""

import hashlib
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

from PIL import Image

from powerforge_ai.ocr import OCRRequest, validate_ocr_response
from powerforge_document_processing.native_spatial import eligibility, extract_native, rasterize_pdf
from powerforge_provenance.spatial_base import POLICY, TextSpan, canonical_json
from powerforge_provenance.spatial_geometry import CoordinateFrame, Rectangle, UprightTransform
from powerforge_provenance.spatial_sources import (
    EngineConfidence,
    EnrichmentArtifactRef,
    NativePrimitive,
    PositionedBlock,
    PositionedLine,
    PositionedText,
    PositionedToken,
    PreparedPage,
    ProducerIdentity,
    RepresentationRef,
    checked_bytes,
    load_positioned_text,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class PreparedOutput:
    manifest: PreparedPage
    blobs: dict
    usage: dict


def prepare_page(
    owner,
    original,
    original_bytes,
    base,
    base_bytes,
    run_id,
    unit_id,
    preparation_hash,
    profile,
    force,
    provider_factory,
    before_ocr=lambda: None,
):
    if len(original_bytes) != original.size_bytes or sha(original_bytes) != original.sha256:
        raise ValueError("Original bytes differ from pinned document")
    for artifact in base:
        checked_bytes(artifact, base_bytes[artifact.id])
    native = extract_native(original_bytes, owner.page_number) if original.format == "pdf" else None
    image = next(a for a in base if a.role == "ANALYSIS_IMAGE")
    if native:
        frame = CoordinateFrame(unit="PDF_POINTS", width=native.width, height=native.height)
    else:
        frame = CoordinateFrame(unit="PIXELS", width=image.width_px, height=image.height_px)
    for selected in base:
        if selected.role == "ANALYSIS_IMAGE":
            with Image.open(BytesIO(base_bytes[selected.id])) as decoded:
                if decoded.format != "PNG" or decoded.size != (
                    selected.width_px,
                    selected.height_px,
                ):
                    raise ValueError("Pinned analysis image dimensions/format differ")
                decoded.load()
    result_id = uuid4()
    blobs = {}
    derived = []
    descriptors = []

    def artifact(role, data, width=None, height=None):
        ref = EnrichmentArtifactRef(
            id=uuid4(),
            owner=owner,
            result_id=result_id,
            producer_run_id=run_id,
            producer_work_unit_id=unit_id,
            role=role,
            sha256=sha(data),
            size_bytes=len(data),
            width_px=width,
            height_px=height,
        )
        blobs[ref.id] = (ref, data)
        return ref

    def representation(alias, readings, producer, transform, input_image=None, primitives=()):
        # The serializer's spaces/newlines preserve engine grouping, not printed reading order.
        text = ""
        tokens = []
        lines = {}
        blocks = {}
        previous_line = None
        for index, (raw, box, line, block, direction, confidence) in enumerate(readings):
            if len(tokens) >= POLICY["max_tokens"]:
                raise ValueError("Token bound exceeded")
            if text:
                text += " " if line == previous_line else "\n"
            start = len(text)
            text += raw
            token = PositionedToken(
                ref=f"w{index}",
                raw_text=raw,
                span=TextSpan(start=start, end=len(text)),
                engine_order=index,
                source_box=Rectangle(x=box[0], y=box[1], width=box[2], height=box[3])
                if box
                else None,
                geometry_unavailable_reason="UNSUPPORTED_NATIVE_GEOMETRY" if box is None else None,
                confidence=confidence,
            )
            tokens.append(token)
            lines.setdefault(line, [[], direction, block])[0].append(token.ref)
            previous_line = line
        text_ref = artifact(
            "NATIVE_POSITIONED_TEXT" if alias == "native" else "OCR_TEXT", text.encode()
        )
        line_models = []
        for index, (_, (refs, direction, block)) in enumerate(lines.items()):
            line = PositionedLine(
                ref=f"l{index}", engine_order=index, token_refs=tuple(refs), direction=direction
            )
            line_models.append(line)
            blocks.setdefault(block, []).append(line.ref)
        body = PositionedText(
            id=uuid4(),
            owner=owner,
            producer=producer,
            text_artifact=text_ref,
            input_image=input_image,
            transform=transform,
            serialization="native-emission-v1" if alias == "native" else "ocr-engine-lines-v1",
            tokens=tuple(tokens),
            lines=tuple(line_models),
            blocks=tuple(
                PositionedBlock(ref=f"b{i}", engine_order=i, line_refs=tuple(refs))
                for i, refs in enumerate(blocks.values())
            ),
            native_primitives=primitives,
        )
        data = canonical_json(body.model_dump(mode="json")).encode()
        geometry = EnrichmentArtifactRef(
            id=body.id,
            owner=owner,
            result_id=result_id,
            producer_run_id=run_id,
            producer_work_unit_id=unit_id,
            role="POSITIONED_READINGS",
            sha256=sha(data),
            size_bytes=len(data),
        )
        blobs[geometry.id] = (geometry, data)
        descriptors.append(
            RepresentationRef(
                ref=alias,
                text_artifact=text_ref,
                geometry_artifact=geometry,
                producer_sha256=producer.identity_hash,
                character_count=len(text),
                token_count=len(tokens),
                line_count=len(line_models),
                block_count=len(blocks),
                primitive_count=len(primitives),
            )
        )

    if native:
        source_frame = CoordinateFrame(
            unit="PDF_POINTS", width=native.source_width, height=native.source_height
        )
        transform = UprightTransform(
            source_frame=source_frame,
            target_frame=frame,
            source_region=source_frame.bounds,
            target_region=frame.bounds,
            rotation_degrees=native.rotation,
        )
        producer = ProducerIdentity(
            kind="NATIVE_PDF",
            adapter="pymupdf-native",
            adapter_version="native-pymupdf-v1",
            engine="pymupdf",
            engine_version=profile.native["engine_version"],
            build_sha256=profile.native["build_sha256"],
            configuration_sha256=profile.native["rules_sha256"],
        )
        primitives = tuple(
            NativePrimitive(
                ref=f"p{i}",
                kind="SEGMENT" if len(points) == 2 else "QUAD",
                points=tuple({"x": x, "y": y} for x, y in points),
            )
            for i, points in enumerate(native.primitives)
        )
        representation(
            "native",
            [(r.text, r.box, r.line, r.block, r.direction, None) for r in native.readings],
            producer,
            transform,
            primitives=primitives,
        )
    should_ocr, reason = eligibility(native, force)
    usage = {
        "ocr_invocations": 0,
        "ocr_elapsed_ms": 0,
        "raster_pixels": 0,
        "text_coverage": "UNKNOWN",
        "eligibility_reason": reason,
        "operating_cost": None,
        "cpu_ms": None,
        "peak_memory_bytes": None,
    }
    if should_ocr:
        provider = provider_factory()
        if provider.identity != profile.ocr_identity or provider.settings != profile.ocr_settings:
            raise ValueError("Configured OCR engine/data differs from pinned profile")
        if native:
            data, width, height = rasterize_pdf(original_bytes, owner.page_number)
            input_image = artifact("OCR_INPUT_IMAGE", data, width, height)
            derived.append(input_image)
        else:
            input_image = image
            data = base_bytes[image.id]
            width = image.width_px
            height = image.height_px
        request = OCRRequest(
            request_id=uuid4(),
            image_artifact_id=input_image.id,
            image_sha256=input_image.sha256,
            image=data,
            width_px=width,
            height_px=height,
            expected_identity=profile.ocr_identity,
            settings=profile.ocr_settings,
            timeout_seconds=60,
        )
        before_ocr()
        response = validate_ocr_response(request, provider.recognize(request))
        source_frame = CoordinateFrame(unit="PIXELS", width=width, height=height)
        transform = UprightTransform(
            source_frame=source_frame,
            target_frame=frame,
            source_region=source_frame.bounds,
            target_region=frame.bounds,
        )
        readings = []
        for word in response.words:
            confidence = (
                EngineConfidence(**word.confidence.model_dump()) if word.confidence else None
            )
            readings.append(
                (
                    word.text,
                    (word.left, word.top, word.width, word.height),
                    (word.block, word.paragraph, word.line),
                    word.block,
                    None,
                    confidence,
                )
            )
        producer = ProducerIdentity(
            kind="OCR",
            adapter="tesseract-tsv",
            adapter_version=response.identity.adapter_version,
            engine=response.identity.engine,
            engine_version=response.identity.engine_version,
            build_sha256=response.identity.build_sha256,
            configuration_sha256=response.identity.settings_sha256,
        )
        representation("ocr", readings, producer, transform, input_image)
        usage.update(
            ocr_invocations=1,
            ocr_elapsed_ms=response.usage.elapsed_ms,
            raster_pixels=width * height,
        )
    manifest = PreparedPage(
        id=result_id,
        owner=owner,
        original=original,
        producer_run_id=run_id,
        producer_work_unit_id=unit_id,
        preparation_sha256=preparation_hash,
        page_frame=frame,
        base_artifacts=base,
        derived_images=tuple(derived),
        representations=tuple(descriptors),
        ocr_decision="RUN"
        if should_ocr
        else "EXPLICIT_SELECTION_REQUIRED"
        if native and native.raster_boxes
        else "SKIP_NATIVE_SUFFICIENT",
        ocr_reason=reason,
        limitations=("NO_LEGACY_NATIVE_ORIGIN_WITNESS", "PRINTED_TEXT_NOT_INDEPENDENTLY_VERIFIED"),
    )
    for descriptor in descriptors:
        load_positioned_text(
            manifest,
            descriptor.ref,
            blobs[descriptor.geometry_artifact.id][1],
            blobs[descriptor.text_artifact.id][1],
        )
    usage["bytes_written"] = sum(len(data) for _, data in blobs.values())
    return PreparedOutput(manifest, blobs, usage)
