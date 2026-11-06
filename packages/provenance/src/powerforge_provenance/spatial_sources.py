"""Versioned immutable source shapes. Shape validity is not committed provenance proof."""

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from powerforge_provenance.spatial_base import (
    POLICY,
    SHA256,
    ExactDecimal,
    Label,
    LocalRef,
    SpatialContract,
    TextSpan,
    bounded_json,
    identity_hash,
    revalidate,
)
from powerforge_provenance.spatial_geometry import (
    CoordinateFrame,
    Point,
    Rectangle,
    UprightTransform,
    convex_quad,
)


class PageOwner(SpatialContract):
    document_id: UUID
    processing_run_id: UUID
    document_page_id: UUID
    page_number: int = Field(ge=1, le=1000)


class OriginalDocument(SpatialContract):
    document_id: UUID
    sha256: SHA256
    size_bytes: int = Field(gt=0, le=262_144_000)
    format: Literal["pdf", "png", "jpeg", "tiff"]


class ProducerIdentity(SpatialContract):
    version: Literal["source-producer-v1"] = "source-producer-v1"
    kind: Literal["NATIVE_PDF", "OCR", "SPATIAL_LAYOUT"]
    adapter: Label
    adapter_version: Label
    engine: Label
    engine_version: Label
    build_sha256: SHA256
    # Complete material configuration/data identities live in the producer snapshot.
    configuration_sha256: SHA256

    @property
    def identity_hash(self):
        return identity_hash(self.model_dump(mode="json"))


class PageArtifactRef(SpatialContract):
    kind: Literal["PAGE_ARTIFACT"] = "PAGE_ARTIFACT"
    id: UUID
    owner: PageOwner
    role: Literal["NATIVE_TEXT", "ANALYSIS_IMAGE"]
    sha256: SHA256
    size_bytes: int = Field(ge=0, le=POLICY["max_raster_bytes"])
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def role_shape(self):
        _artifact_shape(self)
        return self


class EnrichmentArtifactRef(SpatialContract):
    kind: Literal["ENRICHMENT_ARTIFACT"] = "ENRICHMENT_ARTIFACT"
    id: UUID
    owner: PageOwner
    result_id: UUID
    producer_run_id: UUID
    producer_work_unit_id: UUID
    role: Literal[
        "NATIVE_POSITIONED_TEXT",
        "OCR_TEXT",
        "POSITIONED_READINGS",
        "NATIVE_ORIGINS",
        "SPATIAL_LAYOUT",
        "OCR_INPUT_IMAGE",
    ]
    sha256: SHA256
    size_bytes: int = Field(ge=0, le=POLICY["max_raster_bytes"])
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def role_shape(self):
        _artifact_shape(self)
        return self


def _artifact_shape(artifact):
    if artifact.role in {"ANALYSIS_IMAGE", "OCR_INPUT_IMAGE"}:
        if (
            artifact.size_bytes == 0
            or artifact.width_px is None
            or artifact.height_px is None
            or artifact.width_px * artifact.height_px > POLICY["max_raster_pixels"]
        ):
            raise ValueError("Raster descriptors require bounded nonempty pixels/bytes")
    elif artifact.width_px is not None or artifact.height_px is not None:
        raise ValueError("Non-raster artifacts cannot declare image dimensions")
    elif artifact.role not in {"NATIVE_TEXT", "NATIVE_POSITIONED_TEXT", "OCR_TEXT"} and (
        artifact.size_bytes == 0 or artifact.size_bytes > POLICY["max_manifest_bytes"]
    ):
        raise ValueError("Structured source artifact exceeds its byte bound")
    elif artifact.role in {"NATIVE_TEXT", "NATIVE_POSITIONED_TEXT", "OCR_TEXT"} and (
        artifact.size_bytes > 4 * POLICY["max_text_characters"]
    ):
        raise ValueError("Text artifact exceeds its encoded text bound")


ArtifactRef = Annotated[PageArtifactRef | EnrichmentArtifactRef, Field(discriminator="kind")]


def checked_bytes(artifact: ArtifactRef, data: bytes):
    """Check caller-supplied immutable bytes; this performs no storage/network access."""
    artifact = revalidate(artifact)
    if (
        type(data) is not bytes
        or len(data) != artifact.size_bytes
        or (hashlib.sha256(data).hexdigest() != artifact.sha256)
    ):
        raise ValueError("Source bytes differ from the selected artifact identity")
    return data


def checked_text(artifact: ArtifactRef, data: bytes):
    if artifact.role not in {"NATIVE_TEXT", "NATIVE_POSITIONED_TEXT", "OCR_TEXT"}:
        raise ValueError("Offsets require an explicit immutable text representation")
    try:
        text = checked_bytes(artifact, data).decode("utf-8")
    except UnicodeError:
        raise ValueError("Text artifact must contain valid UTF-8") from None
    if len(text) > POLICY["max_text_characters"]:
        raise ValueError("Text representation exceeds its codepoint bound")
    return text


class EngineConfidence(SpatialContract):
    value: ExactDecimal
    minimum: ExactDecimal
    maximum: ExactDecimal
    method: Label

    @model_validator(mode="after")
    def engine_scale(self):
        if not self.minimum < self.maximum or not self.minimum <= self.value <= self.maximum:
            raise ValueError("Confidence must fit its explicitly declared engine scale")
        return self


class PositionedToken(SpatialContract):
    ref: LocalRef
    raw_text: Annotated[str, Field(min_length=1, max_length=POLICY["max_reading_characters"])]
    span: TextSpan
    engine_order: int = Field(ge=0, le=1_000_000)
    source_box: Rectangle | None
    # Perimeter order, not a library's diagonal vertex ordering.
    source_quad: tuple[Point, Point, Point, Point] | None = None
    geometry_unavailable_reason: Label | None
    confidence: EngineConfidence | None = None

    @model_validator(mode="after")
    def span_and_geometry(self):
        if len(self.raw_text) != self.span.length:
            raise ValueError("Token length differs from its codepoint interval")
        if (self.source_box is None) != (self.geometry_unavailable_reason is not None):
            raise ValueError("Missing geometry needs a reason; supported geometry uses null")
        if self.source_quad is not None:
            box = self.source_box
            if (
                box is None
                or not convex_quad(self.source_quad)
                or any(
                    not box.x <= p.x <= box.right or not box.y <= p.y <= box.bottom
                    for p in self.source_quad
                )
            ):
                raise ValueError("Source quad requires distinct vertices inside its declared box")
        return self


class PositionedLine(SpatialContract):
    ref: LocalRef
    engine_order: int = Field(ge=0, le=1_000_000)
    token_refs: tuple[LocalRef, ...] = Field(min_length=1, max_length=512)
    # Original engine direction, not an inferred visual reading order.
    direction: tuple[ExactDecimal, ExactDecimal] | None = None

    @model_validator(mode="after")
    def supported_direction(self):
        if self.direction is not None and (
            self.direction == (0, 0) or any(abs(v) > 1 for v in self.direction)
        ):
            raise ValueError("Line direction must be a bounded nonzero engine vector")
        return self


class PositionedBlock(SpatialContract):
    ref: LocalRef
    engine_order: int = Field(ge=0, le=1_000_000)
    line_refs: tuple[LocalRef, ...] = Field(min_length=1, max_length=POLICY["max_lines"])


class NativePrimitive(SpatialContract):
    ref: LocalRef
    kind: Literal["SEGMENT", "QUAD"]
    points: tuple[Point, ...] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def point_shape(self):
        if len(self.points) != (2 if self.kind == "SEGMENT" else 4) or len(
            set((p.x, p.y) for p in self.points)
        ) != len(self.points):
            raise ValueError("Native primitives need distinct declared segment/quad vertices")
        if self.kind == "QUAD" and not convex_quad(self.points):
            raise ValueError("Native quad geometry must be convex and perimeter ordered")
        return self


class PositionedText(SpatialContract):
    version: Literal["positioned-text-v1"] = "positioned-text-v1"
    # The geometry artifact's external descriptor hashes this body, not itself.
    id: UUID
    owner: PageOwner
    producer: ProducerIdentity
    text_artifact: EnrichmentArtifactRef
    input_image: ArtifactRef | None
    transform: UprightTransform
    serialization: Literal["native-emission-v1", "ocr-engine-lines-v1"]
    offset_convention: Literal["UNICODE_CODEPOINT"] = "UNICODE_CODEPOINT"
    tokens: tuple[PositionedToken, ...] = Field(max_length=POLICY["max_tokens"])
    lines: tuple[PositionedLine, ...] = Field(max_length=POLICY["max_lines"])
    blocks: tuple[PositionedBlock, ...] = Field(max_length=POLICY["max_blocks"])
    native_primitives: tuple[NativePrimitive, ...] = Field(
        default=(), max_length=POLICY["max_native_primitives"]
    )

    @model_validator(mode="after")
    def source_and_membership(self):
        native = self.producer.kind == "NATIVE_PDF"
        if (
            self.producer.kind not in {"NATIVE_PDF", "OCR"}
            or self.text_artifact.owner != self.owner
        ):
            raise ValueError("Positioned text requires an owned native/OCR producer")
        if self.text_artifact.role != ("NATIVE_POSITIONED_TEXT" if native else "OCR_TEXT") or (
            self.serialization != ("native-emission-v1" if native else "ocr-engine-lines-v1")
        ):
            raise ValueError("Recognition source cannot be relabeled as another representation")
        if native:
            if self.input_image is not None or any(t.confidence is not None for t in self.tokens):
                raise ValueError("Native geometry is not OCR image recognition/confidence")
            if self.transform.source_frame.unit != "PDF_POINTS":
                raise ValueError("Native PDF geometry requires PDF points")
        else:
            image = self.input_image
            frame = self.transform.source_frame
            if (
                image is None
                or image.owner != self.owner
                or image.role not in {"ANALYSIS_IMAGE", "OCR_INPUT_IMAGE"}
                or frame.unit != "PIXELS"
                or frame.origin_x != 0
                or frame.origin_y != 0
                or (frame.width, frame.height) != (image.width_px, image.height_px)
            ):
                raise ValueError("OCR geometry requires its exact owned input image frame")
            if self.native_primitives:
                raise ValueError("OCR cannot assert native PDF vector geometry")
        token_refs = _unique(self.tokens)
        line_refs = _unique(self.lines)
        _unique(self.blocks)
        _membership(self.lines, "token_refs", token_refs)
        _membership(self.blocks, "line_refs", line_refs)
        previous_end = -1
        for token in sorted(self.tokens, key=lambda t: t.span.start):
            if token.span.start < previous_end:
                raise ValueError("Token intervals overlap in their immutable representation")
            if token.span.end > self.text_artifact.size_bytes:
                raise ValueError("Token codepoint span cannot exceed its UTF-8 byte bound")
            previous_end = token.span.end
            if token.source_box is not None:
                self.transform.map_rectangle(token.source_box)
        if len({p.ref for p in self.native_primitives}) != len(self.native_primitives):
            raise ValueError("Duplicate native primitive references")
        for primitive in self.native_primitives:
            for point in primitive.points:
                self.transform.map_point(point)
        bounded_json(self, POLICY["max_manifest_bytes"])
        return self


def _unique(items):
    refs = {i.ref for i in items}
    if len(refs) != len(items) or len({i.engine_order for i in items}) != len(items):
        raise ValueError("Duplicate source-local references or engine traversal indices")
    return refs


def _membership(items, field, available):
    used = set()
    for item in items:
        refs = getattr(item, field)
        if len(set(refs)) != len(refs) or not set(refs) <= available or used & set(refs):
            raise ValueError("Foreign, duplicate or overlapping line/block membership")
        used.update(refs)


def checked_positioned_text(representation: PositionedText, text_data: bytes):
    representation = revalidate(representation)
    text = checked_text(representation.text_artifact, text_data)
    for token in representation.tokens:
        if text[token.span.start : token.span.end] != token.raw_text:
            raise ValueError("Positioned reading differs from its exact text occurrence")
    return representation, text


class RepresentationRef(SpatialContract):
    ref: LocalRef
    text_artifact: EnrichmentArtifactRef
    geometry_artifact: EnrichmentArtifactRef
    producer_sha256: SHA256
    character_count: int = Field(ge=0, le=POLICY["max_text_characters"])
    token_count: int = Field(ge=0, le=POLICY["max_tokens"])
    line_count: int = Field(ge=0, le=POLICY["max_lines"])
    block_count: int = Field(ge=0, le=POLICY["max_blocks"])
    primitive_count: int = Field(ge=0, le=POLICY["max_native_primitives"])

    @model_validator(mode="after")
    def same_producer(self):
        text, geometry = self.text_artifact, self.geometry_artifact
        if (
            text.role not in {"NATIVE_POSITIONED_TEXT", "OCR_TEXT"}
            or geometry.role != "POSITIONED_READINGS"
            or text.id == geometry.id
            or (text.owner, text.result_id, text.producer_run_id, text.producer_work_unit_id)
            != (
                geometry.owner,
                geometry.result_id,
                geometry.producer_run_id,
                geometry.producer_work_unit_id,
            )
        ):
            raise ValueError("Representation descriptors require one exact text/geometry producer")
        if not self.character_count <= text.size_bytes <= 4 * self.character_count:
            raise ValueError("Representation character count differs from UTF-8 byte bounds")
        return self


class PreparedPage(SpatialContract):
    version: Literal["prepared-source-page-v1"] = "prepared-source-page-v1"
    id: UUID
    owner: PageOwner
    original: OriginalDocument
    producer_run_id: UUID
    producer_work_unit_id: UUID
    preparation_sha256: SHA256
    page_frame: CoordinateFrame
    base_artifacts: tuple[PageArtifactRef, ...] = Field(min_length=1, max_length=2)
    derived_images: tuple[EnrichmentArtifactRef, ...] = Field(
        default=(), max_length=POLICY["max_ocr_regions"]
    )
    representations: tuple[RepresentationRef, ...] = Field(max_length=POLICY["max_representations"])
    # Eligibility is an observable decision, not an invented percentage of text coverage.
    ocr_decision: Literal["RUN", "SKIP_NATIVE_SUFFICIENT", "EXPLICIT_SELECTION_REQUIRED"]
    ocr_reason: Label
    text_coverage: Literal["UNKNOWN"] = "UNKNOWN"
    limitations: tuple[Label, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def owned_sources(self):
        if self.original.document_id != self.owner.document_id:
            raise ValueError("Original document differs from the page owner")
        if self.page_frame.unit != ("PDF_POINTS" if self.original.format == "pdf" else "PIXELS"):
            raise ValueError("Upright page frame unit differs from the original format")
        if (
            len({a.id for a in self.base_artifacts}) != len(self.base_artifacts)
            or len({a.role for a in self.base_artifacts}) != len(self.base_artifacts)
            or any(a.owner != self.owner for a in self.base_artifacts)
        ):
            raise ValueError("Base source identities/roles must be distinct and owned")
        refs, artifacts = set(), set()
        for artifact in self.derived_images:
            if artifact.role != "OCR_INPUT_IMAGE":
                raise ValueError("Prepared derived images require the explicit OCR raster role")
        for item in self.representations:
            if item.ref in refs:
                raise ValueError("Duplicate representation alias")
            refs.add(item.ref)
        for artifact in (
            *self.derived_images,
            *(a for r in self.representations for a in (r.text_artifact, r.geometry_artifact)),
        ):
            if (
                artifact.owner != self.owner
                or artifact.result_id != self.id
                or artifact.producer_run_id != self.producer_run_id
                or artifact.producer_work_unit_id != self.producer_work_unit_id
                or artifact.id in artifacts
            ):
                raise ValueError("Prepared artifacts differ from the exact producer/page")
            artifacts.add(artifact.id)
        has_ocr = any(r.text_artifact.role == "OCR_TEXT" for r in self.representations)
        if has_ocr != (self.ocr_decision == "RUN"):
            raise ValueError("OCR selection decision differs from the published representations")
        for field, limit in (
            ("character_count", "max_text_characters"),
            ("token_count", "max_tokens"),
            ("line_count", "max_lines"),
            ("block_count", "max_blocks"),
            ("primitive_count", "max_native_primitives"),
        ):
            if sum(getattr(r, field) for r in self.representations) > POLICY[limit]:
                raise ValueError("Combined page representations exceed the declared count bound")
        if (
            sum(r.geometry_artifact.size_bytes for r in self.representations)
            > POLICY["max_manifest_bytes"]
        ):
            raise ValueError("Combined page geometry exceeds its canonical byte bound")
        bounded_json(self, POLICY["max_manifest_bytes"])
        return self

    @property
    def identity_hash(self):
        return identity_hash(self.model_dump(mode="json"))


def load_positioned_text(
    prepared: PreparedPage, alias: str, geometry_data: bytes, text_data: bytes
):
    """Validate a detached snapshot, not DB completion/lease or engine authenticity."""
    prepared = revalidate(prepared)
    descriptor = next((r for r in prepared.representations if r.ref == alias), None)
    if descriptor is None:
        raise ValueError("Representation is outside the pinned prepared manifest")
    checked_bytes(descriptor.geometry_artifact, geometry_data)
    body = PositionedText.model_validate_json(geometry_data)
    if body.producer.kind == "NATIVE_PDF" and prepared.original.format != "pdf":
        raise ValueError("Native PDF readings require the selected original PDF")
    if (
        body.id != descriptor.geometry_artifact.id
        or body.owner != prepared.owner
        or body.text_artifact != descriptor.text_artifact
        or body.producer.identity_hash != descriptor.producer_sha256
        or body.transform.target_frame != prepared.page_frame
    ):
        raise ValueError("Positioned body differs from its pinned descriptor/frame")
    if (
        isinstance(body.input_image, PageArtifactRef)
        and body.input_image not in prepared.base_artifacts
    ):
        raise ValueError("OCR image is outside the pinned processing artifacts")
    if (
        isinstance(body.input_image, EnrichmentArtifactRef)
        and body.input_image not in prepared.derived_images
    ):
        raise ValueError("Derived OCR raster differs from the prepared producer")
    body, text = checked_positioned_text(body, text_data)
    if (
        descriptor.character_count,
        descriptor.token_count,
        descriptor.line_count,
        descriptor.block_count,
        descriptor.primitive_count,
    ) != (
        len(text),
        len(body.tokens),
        len(body.lines),
        len(body.blocks),
        len(body.native_primitives),
    ):
        raise ValueError("Actual positioned counts differ from the pinned page budget")
    return body, text


class PreparationInput(SpatialContract):
    """Source/configuration identity only; this registers no executable profile."""

    version: Literal["source-preparation-input-v1"] = "source-preparation-input-v1"
    original: OriginalDocument
    processing_run_id: UUID
    selected_pages: tuple[int, ...] = Field(min_length=1, max_length=POLICY["max_pages"])
    base_artifacts: tuple[PageArtifactRef, ...] = Field(
        min_length=1, max_length=2 * POLICY["max_pages"]
    )
    expected_producers: tuple[ProducerIdentity, ...] = Field(min_length=1, max_length=2)
    selection_policy_sha256: SHA256
    raster_policy_sha256: SHA256
    limits_sha256: SHA256

    @model_validator(mode="after")
    def selected_sources(self):
        if (
            tuple(sorted(set(self.selected_pages))) != self.selected_pages
            or min(self.selected_pages) < 1
            or max(self.selected_pages) > 1000
        ):
            raise ValueError("Select distinct ascending supported source pages")
        if len({p.kind for p in self.expected_producers}) != len(self.expected_producers) or any(
            p.kind not in {"NATIVE_PDF", "OCR"} for p in self.expected_producers
        ):
            raise ValueError("Preparation requires distinct native/OCR producer identities")
        seen, page_ids = set(), {}
        for a in self.base_artifacts:
            owner = a.owner
            key = owner.page_number, a.role
            if (
                owner.document_id != self.original.document_id
                or owner.processing_run_id != self.processing_run_id
                or owner.page_number not in self.selected_pages
                or key in seen
                or owner.page_number in page_ids
                and page_ids[owner.page_number] != owner.document_page_id
            ):
                raise ValueError("Preparation sources differ from their selected document/run/page")
            seen.add(key)
            page_ids[owner.page_number] = owner.document_page_id
        if set(page_ids) != set(self.selected_pages) or len(set(page_ids.values())) != len(
            page_ids
        ):
            raise ValueError("Every selected page needs its distinct exact source identity")
        if len({a.id for a in self.base_artifacts}) != len(self.base_artifacts):
            raise ValueError("Duplicate base artifact identity")
        bounded_json(self, POLICY["max_manifest_bytes"])
        return self

    @property
    def identity_hash(self):
        return identity_hash(self.model_dump(mode="json"))
