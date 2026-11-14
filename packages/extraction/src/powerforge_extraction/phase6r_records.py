"""Phase 6R publication rows. Alembic owns the composite database constraints."""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, BigInteger, Numeric, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PublicationRecord(DeclarativeBase):
    # Dormant pre-6R mappers occupy these names in the shared metadata until 6R-E.
    pass


class Candidate(PublicationRecord):
    __tablename__ = "extraction_candidates"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID]
    document_page_id: Mapped[UUID]
    work_unit_id: Mapped[UUID]
    ordinal: Mapped[int]
    kind: Mapped[str]
    local_ref: Mapped[str]
    mapping_status: Mapped[str]
    reason_code: Mapped[str | None]
    conflict: Mapped[bool] = mapped_column(default=False)
    search_terms: Mapped[list[str]] = mapped_column(ARRAY(Text))
    source_description: Mapped[str | None]
    registry_type: Mapped[str | None]
    tag: Mapped[str | None]
    tag_state: Mapped[str | None]
    qualification: Mapped[str | None]
    raw_qualification: Mapped[str | None]
    equipment_id: Mapped[UUID | None]
    equipment_work_unit_id: Mapped[UUID | None]
    association: Mapped[str | None]
    claimed_owner_ref: Mapped[str | None]
    raw_unmapped: Mapped[bool | None]
    raw_label: Mapped[str | None]
    raw_value: Mapped[str | None]
    raw_unit: Mapped[str | None]
    qualifiers: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    value_form: Mapped[str | None]
    proposed_attribute_key: Mapped[str | None]
    proposed_enum_value: Mapped[str | None]
    normalized_type: Mapped[str | None]
    normalized_unit: Mapped[str | None]
    value_number: Mapped[Decimal | None] = mapped_column(Numeric)
    value_integer: Mapped[int | None] = mapped_column(BigInteger)
    value_text: Mapped[str | None]
    value_boolean: Mapped[bool | None]


class Fragment(PublicationRecord):
    __tablename__ = "extraction_evidence"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    candidate_id: Mapped[UUID]
    run_id: Mapped[UUID]
    document_page_id: Mapped[UUID]
    work_unit_id: Mapped[UUID]
    ordinal: Mapped[int]
    page_image_id: Mapped[UUID]
    role: Mapped[str]
    localization: Mapped[str]
    modality: Mapped[str | None]
    text_artifact_id: Mapped[UUID | None]
    start: Mapped[int | None]
    end: Mapped[int | None] = mapped_column("end", quote=True)
    quote: Mapped[str | None]
    regions: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    source_issues: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    region: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    reported_text: Mapped[str | None]
    reason_code: Mapped[str | None]


def publish(session, stage, page_image_id, observations):
    owners = {}
    if stage.upstream_work_unit_id is not None and observations:
        owners = dict(
            session.execute(
                select(Candidate.local_ref, Candidate.id).where(
                    Candidate.work_unit_id == stage.upstream_work_unit_id,
                    Candidate.kind == "EQUIPMENT",
                )
            ).all()
        )
    scope = dict(
        run_id=stage.run_id,
        document_page_id=stage.document_page_id,
        work_unit_id=stage.work_unit_id,
    )
    fragments = []
    for ordinal, observation in enumerate(observations):
        fields = dict(observation.fields)
        ref = fields.pop("owner_ref", None)
        search_terms = [
            fields[key].casefold()
            for key in (
                "source_description",
                "tag",
                "proposed_attribute_key",
                "raw_label",
                "raw_value",
                "raw_unit",
            )
            if fields.get(key) is not None
        ]
        candidate = Candidate(
            search_terms=search_terms,
            id=uuid4(),
            **scope,
            ordinal=ordinal,
            **fields,
            equipment_id=owners[ref] if ref is not None else None,
            equipment_work_unit_id=stage.upstream_work_unit_id if ref is not None else None,
        )
        session.add(candidate)
        fragments.extend(
            Fragment(
                id=uuid4(),
                **scope,
                candidate_id=candidate.id,
                page_image_id=page_image_id,
                ordinal=index,
                **fragment,
            )
            for index, fragment in enumerate(observation.evidence)
        )
    session.flush()
    session.add_all(fragments)
    session.flush()
