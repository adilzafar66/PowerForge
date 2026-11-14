"""Public views of review candidates and their pinned evidence."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from powerforge_extraction.phase6r_contracts import Association, Qualification, Role, TagState
from powerforge_provenance.locations import Region

MappingStatus = Literal["MAPPED", "UNMAPPED", "INVALID"]
CandidateKind = Literal["EQUIPMENT", "ATTRIBUTE"]
GroupId = UUID | Literal["unassigned"]


class CandidateQuery(BaseModel):
    view: Literal["flat", "groups", "members"] = "flat"
    group_id: GroupId | None = None
    candidate_id: UUID | None = None
    equipment_id: UUID | None = None
    search: str | None = Field(default=None, max_length=200)
    page_id: UUID | None = None
    equipment_type: str | None = Field(default=None, max_length=96)
    mapping_status: MappingStatus | None = None
    kind: CandidateKind | None = None
    limit: int | None = Field(default=None, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=512)


class CandidateBase(BaseModel):
    id: UUID
    page_id: UUID
    attempt_id: UUID
    mapping_status: MappingStatus
    reason_code: str | None
    evidence_ids: list[UUID]
    conflict: bool


class EquipmentCandidate(CandidateBase):
    kind: Literal["EQUIPMENT"] = "EQUIPMENT"
    source_description: str
    registry_type: str | None
    tag: str | None
    tag_state: TagState
    qualification: Qualification
    raw_qualification: str | None


class NormalizedValue(BaseModel):
    type: Literal["NUMBER", "INTEGER", "TEXT", "ENUM", "BOOLEAN"]
    value: str | bool
    unit: str | None


class AttributeCandidate(CandidateBase):
    kind: Literal["ATTRIBUTE"] = "ATTRIBUTE"
    equipment_id: UUID | None
    association: Association
    raw_unmapped: bool
    raw_label: str | None
    raw_value: str
    raw_unit: str | None
    qualifiers: list[str]
    value_form: Literal["SINGLE", "RANGE", "MULTIPLE", "QUALIFIED"]
    proposed_attribute_key: str | None
    proposed_enum_value: str | None
    normalized: NormalizedValue | None


CandidateItem = Annotated[EquipmentCandidate | AttributeCandidate, Field(discriminator="kind")]


class Group(BaseModel):
    kind: Literal["EQUIPMENT", "UNASSIGNED"]
    group_id: GroupId
    label: str
    tag: str | None
    registry_type: str | None
    page_numbers: list[int]
    matching_candidate_count: int


class BrowserPage[T](BaseModel):
    items: list[T]
    total: int
    next_cursor: str | None
    previous_cursor: str | None


class MembersPage(BrowserPage[CandidateItem]):
    group: Group


class PinnedRunPage(BaseModel):
    document_id: UUID
    page_id: UUID
    page_number: int
    page_image_id: UUID
    processing_run_id: UUID
    prepared_result_id: UUID
    spatial_result_id: UUID
    prepared_manifest_hash: str
    spatial_manifest_hash: str
    preparation_producer_run_id: UUID
    layout_producer_run_id: UUID
    text_coverage: Literal["UNKNOWN"]
    printed_text_independently_verified: Literal[False] = False
    page_context_hash: str | None


class RunSources(BaseModel):
    items: list[PinnedRunPage]


class SignedArtifact(BaseModel):
    id: UUID
    sha256: str
    url: str
    expires_seconds: int


class EvidenceBase(BaseModel):
    id: UUID
    candidate_id: UUID
    role: Role
    page_id: UUID
    page_image_id: UUID
    page_image: SignedArtifact


class ResolvedEvidence(EvidenceBase):
    localization: Literal["RESOLVED"] = "RESOLVED"
    modality: Literal["NATIVE_PDF", "OCR"]
    text_artifact_id: UUID
    text_artifact: SignedArtifact
    start: int
    end: int
    quote: str
    regions: list[Region]
    source_issues: list[str]


class VisualEvidence(EvidenceBase):
    localization: Literal["VISUAL_REPORTED"] = "VISUAL_REPORTED"
    reported_text: str | None
    region: Region


class UnresolvedEvidence(EvidenceBase):
    localization: Literal["UNRESOLVED"] = "UNRESOLVED"
    reason_code: str


EvidenceItem = Annotated[
    ResolvedEvidence | VisualEvidence | UnresolvedEvidence, Field(discriminator="localization")
]
