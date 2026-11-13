"""Phase 6R v1 wire shapes and admission checks. Runtime integration starts in 6R-B."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from powerforge_engineering_model.enums import EquipmentType
from powerforge_engineering_model.extraction_descriptions import (
    DESCRIPTION_VERSION,
    EQUIPMENT_DESCRIPTIONS,
)
from powerforge_engineering_model.registry import (
    get_equipment_definition,
    list_equipment_definitions,
    supported_input_units,
)
from powerforge_engineering_model.registry_v1 import REGISTRY
from powerforge_extraction.identities import canonical_json, identity_hash
from powerforge_provenance.layout_observations import SpatialLayout
from powerforge_provenance.spatial_base import ExactDecimal

VERSION = "phase-6r-v1"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000

Stage = Literal["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"]
TagState = Literal["PRESENT", "ABSENT", "UNREADABLE", "AMBIGUOUS"]
Qualification = Literal[
    "INSTALLED", "PROPOSED", "FUTURE", "SPARE", "REFERENCE", "LEGEND_ONLY", "UNKNOWN"
]
Role = Literal["EQUIPMENT", "TAG", "LABEL", "HEADER", "VALUE", "UNIT", "QUALIFIER", "CONTEXT"]
Association = Literal["ASSERTED", "UNCERTAIN", "UNASSIGNED"]
Ref = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,96}$")]
Hash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Raw = Annotated[str, StringConstraints(min_length=1, max_length=2048)]
Short = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Quote = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class ReadingCitation(Contract):
    kind: Literal["READING"]
    role: Role
    reading_ref: Ref
    quote: Quote | None


class QuoteCitation(Contract):
    kind: Literal["QUOTE"]
    role: Role
    quote: Quote


class ReportedRegion(Contract):
    x: ExactDecimal
    y: ExactDecimal
    width: ExactDecimal
    height: ExactDecimal


class VisualCitation(Contract):
    kind: Literal["VISUAL"]
    role: Role
    region: ReportedRegion
    reported_text: Quote | None


Citations = Annotated[
    tuple[ReadingCitation | QuoteCitation | VisualCitation, ...], Field(max_length=12)
]


class EquipmentObservation(Contract):
    local_ref: Ref
    source_description: Raw
    registry_type: EquipmentType | None
    tag_state: TagState
    tag: Short | None
    qualification: Qualification
    raw_qualification: Short | None
    evidence: Citations


class AttributeAssertion(Contract):
    local_ref: Ref
    equipment_ref: Ref | None
    association: Association
    raw_label: Short | None
    raw_value: Raw
    raw_unit: Short | None
    qualifiers: Annotated[tuple[Short, ...], Field(max_length=8)]
    value_form: Literal["SINGLE", "RANGE", "MULTIPLE", "QUALIFIED"]
    evidence: Citations


class RegistryAssertion(AttributeAssertion):
    attribute_key: Ref
    proposed_enum_value: Short | None


class RawUnmappedAssertion(AttributeAssertion):
    raw_label: Short


class RecognitionResponse(Contract):
    version: Literal["phase-6r-v1"]
    stage: Literal["EQUIPMENT_RECOGNITION"]
    page_context_hash: Hash
    equipment: Annotated[tuple[EquipmentObservation, ...], Field(max_length=128)]


class AttributeResponse(Contract):
    version: Literal["phase-6r-v1"]
    stage: Literal["ATTRIBUTE_EXTRACTION"]
    page_context_hash: Hash
    upstream_hash: Hash
    attributes: Annotated[tuple[RegistryAssertion, ...], Field(max_length=512)]
    raw_unmapped: Annotated[tuple[RawUnmappedAssertion, ...], Field(max_length=16)]


class ReadingText(Contract):
    reading_ref: Ref
    text: Raw
    modality: Literal["NATIVE_PDF", "OCR"]
    alternate_texts: Annotated[tuple[Raw, ...], Field(max_length=7)]


class PinnedPageContext(Contract):
    source_sha256: Hash
    page_image_id: UUID
    image_sha256: Hash
    image_bytes: int = Field(gt=0, le=MAX_IMAGE_BYTES)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    preparation_sha256: Hash
    layout_sha256: Hash
    layout: SpatialLayout
    readings: tuple[ReadingText, ...]


class EquipmentDefinitionView(Contract):
    key: EquipmentType
    name: Short
    description: Short


class AttributeDefinitionView(Contract):
    equipment_type: EquipmentType
    key: Ref
    name: Short
    value_type: Literal["NUMBER", "INTEGER", "TEXT", "BOOLEAN", "ENUM"]
    canonical_unit: Short | None
    supported_units: tuple[Short, ...]
    allowed_values: tuple[Short, ...]
    notes: Raw | None


class RecognitionRequest(Contract):
    version: Literal["phase-6r-v1"]
    stage: Literal["EQUIPMENT_RECOGNITION"]
    page_context_hash: Hash
    page: PinnedPageContext
    registry_version: str
    description_version: str
    equipment_catalog: tuple[EquipmentDefinitionView, ...]


class AttributeRequest(Contract):
    version: Literal["phase-6r-v1"]
    stage: Literal["ATTRIBUTE_EXTRACTION"]
    page_context_hash: Hash
    page: PinnedPageContext
    registry_version: str
    upstream_hash: Hash
    upstream: RecognitionResponse
    attribute_catalog: tuple[AttributeDefinitionView, ...]


class NoEligibleAttributes(Contract):
    version: Literal["phase-6r-v1"]
    stage: Literal["ATTRIBUTE_EXTRACTION"]
    outcome: Literal["NO_ELIGIBLE_ATTRIBUTES"]
    page_context_hash: Hash
    upstream_hash: Hash
    provider_calls: Literal[0]


def equipment_catalog() -> tuple[EquipmentDefinitionView, ...]:
    return tuple(
        EquipmentDefinitionView(
            key=item.key, name=item.display_name, description=EQUIPMENT_DESCRIPTIONS[item.key]
        )
        for item in sorted(list_equipment_definitions(), key=lambda item: item.key)
    )


def attribute_catalog(upstream: RecognitionResponse) -> tuple[AttributeDefinitionView, ...]:
    types = {
        item.registry_type
        for item in upstream.equipment
        if item.registry_type is not None and item.qualification != "LEGEND_ONLY"
    }
    return tuple(
        AttributeDefinitionView(
            equipment_type=key,
            key=attribute.key,
            name=attribute.display_name,
            value_type=attribute.value_type.value,
            canonical_unit=attribute.canonical_unit,
            supported_units=supported_input_units(key, attribute.key),
            allowed_values=attribute.allowed_values,
            notes=attribute.notes,
        )
        for key in sorted(types)
        for attribute in sorted(get_equipment_definition(key).attributes, key=lambda item: item.key)
    )


def contract_hash(value: Contract) -> str:
    return identity_hash(value.model_dump(mode="json"))


def validate_request(request: RecognitionRequest | AttributeRequest) -> None:
    page = request.page
    reading_refs = [item.reading_ref for item in page.readings]
    if (
        page.image_width * page.image_height > MAX_IMAGE_PIXELS
        or reading_refs != [item.ref for item in page.layout.readings]
        or any(
            len(item.alternate_texts) != len(reading.members) - 1
            for item, reading in zip(page.readings, page.layout.readings, strict=True)
        )
        or page.preparation_sha256 != page.layout.prepared.manifest_sha256
        or page.layout_sha256 != page.layout.identity_hash
        or contract_hash(page) != request.page_context_hash
        or request.registry_version != REGISTRY.registry_version
        or len(canonical_json(request.model_dump(mode="json")).encode()) > MAX_REQUEST_BYTES
    ):
        raise ValueError("Page projection, registry identity or request capacity mismatch")
    if isinstance(request, RecognitionRequest):
        if (
            request.equipment_catalog != equipment_catalog()
            or request.description_version != DESCRIPTION_VERSION
        ):
            raise ValueError("Equipment catalog mismatch")
    elif (
        request.upstream.page_context_hash != request.page_context_hash
        or contract_hash(request.upstream) != request.upstream_hash
        or not request.attribute_catalog
        or request.attribute_catalog != attribute_catalog(request.upstream)
    ):
        raise ValueError("Attribute prerequisite or catalog mismatch")


def parse_response(
    request: RecognitionRequest | AttributeRequest, payload: bytes
) -> RecognitionResponse | AttributeResponse:
    """Reject a malformed complete envelope. Worker checks provider finish status first."""
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Response capacity exceeded")
    if isinstance(request, RecognitionRequest):
        result = RecognitionResponse.model_validate_json(payload)
        refs = [item.local_ref for item in result.equipment]
        if any(
            (item.tag_state == "PRESENT" and not (item.tag or "").strip())
            or (item.tag_state in ("ABSENT", "UNREADABLE") and item.tag is not None)
            for item in result.equipment
        ):
            raise ValueError("Inconsistent equipment tag state")
    else:
        result = AttributeResponse.model_validate_json(payload)
        refs = [item.local_ref for item in (*result.attributes, *result.raw_unmapped)]
        if result.upstream_hash != request.upstream_hash:
            raise ValueError("Foreign recognition prerequisite")
    if result.page_context_hash != request.page_context_hash or len(refs) != len(set(refs)):
        raise ValueError("Foreign page context or duplicate observation reference")
    return result
