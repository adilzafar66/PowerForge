"""Bounded source-group queries over committed, cited observations."""

from sqlalchemy import Text, cast, distinct, exists, func, or_, select

from powerforge_api.schemas.extraction import EvidenceGroupList, EvidenceGroupRow
from powerforge_document_processing.models import DocumentPage
from powerforge_extraction.models import (
    CandidateEvidence,
    Evidence,
    ExtractionCandidate,
    ExtractionWorkUnit,
    SourceGroup,
)

CANDIDATE = ExtractionCandidate


def citation_pages():
    return (
        select(DocumentPage.page_number)
        .select_from(CandidateEvidence)
        .join(Evidence, Evidence.id == CandidateEvidence.evidence_id)
        .join(DocumentPage, DocumentPage.id == Evidence.document_page_id)
        .where(
            CandidateEvidence.candidate_id == CANDIDATE.id,
            CandidateEvidence.role.in_(["PRIMARY", "SUPPORTING"]),
        )
    )


def observation_filters(*, page=None, search=None, equipment_hint=None):
    conditions = []
    if page is not None:
        conditions.append(exists(citation_pages().where(DocumentPage.page_number == page)))
    if equipment_hint is not None:
        conditions.append(
            func.coalesce(SourceGroup.equipment_type_hint, CANDIDATE.equipment_type_key)
            == equipment_hint
        )
    if search:
        conditions.append(
            or_(
                *[
                    column.icontains(search, autoescape=True)
                    for column in (
                        SourceGroup.tag_text,
                        SourceGroup.label,
                        SourceGroup.equipment_type_hint,
                        CANDIDATE.observed_tag,
                        CANDIDATE.equipment_type_key,
                        CANDIDATE.attribute_key,
                        func.replace(CANDIDATE.attribute_key, "_", " "),
                        func.replace(CANDIDATE.equipment_type_key, "_", " "),
                        CANDIDATE.raw_text,
                        CANDIDATE.raw_value,
                        CANDIDATE.text_value,
                        cast(CANDIDATE.numeric_value, Text),
                        cast(CANDIDATE.integer_value, Text),
                        cast(CANDIDATE.boolean_value, Text),
                    )
                ]
            )
        )
    return conditions


def group_list(session, families, limit, offset, *, mapping_status=None, **filters):
    if not families:
        return EvidenceGroupList(items=[], total=0, limit=limit, offset=offset)
    conditions = observation_filters(**filters)
    if mapping_status is not None:
        conditions.append(CANDIDATE.mapping_status == mapping_status)
    page_query = citation_pages().correlate(CANDIDATE).lateral()
    fields = (
        CANDIDATE.run_id,
        CANDIDATE.source_group_id,
        SourceGroup.label,
        SourceGroup.tag_text,
        SourceGroup.equipment_type_hint,
    )
    query = (
        select(
            *fields,
            func.array_agg(distinct(page_query.c.page_number)).label("page_numbers"),
            func.count(distinct(CANDIDATE.id)).label("candidate_count"),
        )
        .select_from(CANDIDATE)
        .join(ExtractionWorkUnit, ExtractionWorkUnit.id == CANDIDATE.work_unit_id)
        .outerjoin(SourceGroup, SourceGroup.id == CANDIDATE.source_group_id)
        .join(page_query, page_query.c.page_number.is_not(None))
        .where(
            CANDIDATE.run_id.in_(families),
            ExtractionWorkUnit.status == "COMPLETED",
            *conditions,
        )
        .group_by(*fields)
    )
    if filters.get("page") is not None:
        query = query.where(page_query.c.page_number == filters["page"])
    grouped = query.subquery()
    total = session.scalar(select(func.count()).select_from(grouped))
    rows = session.execute(
        select(grouped)
        .order_by(
            grouped.c.source_group_id.is_(None),
            func.lower(func.coalesce(grouped.c.tag_text, grouped.c.label, "")),
            grouped.c.run_id,
            grouped.c.source_group_id,
        )
        .limit(limit)
        .offset(offset)
    ).mappings()
    return EvidenceGroupList(
        items=[
            EvidenceGroupRow(
                **{**row, "page_numbers": sorted(row["page_numbers"])},
                family=families[row["run_id"]],
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
