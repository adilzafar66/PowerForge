"""Read the unified page candidates and sign exact, revision-scoped evidence."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import case, exists, func, literal, or_, select, tuple_
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import aliased

from powerforge_api.exceptions import RevisionDocumentNotFound, StorageDownloadFailed
from powerforge_api.schemas.extraction_publication import (
    AttributeCandidate,
    BrowserPage,
    CandidateItem,
    EquipmentCandidate,
    Group,
    MembersPage,
    NormalizedValue,
    PinnedRunPage,
    ResolvedEvidence,
    RunSources,
    SignedArtifact,
    UnresolvedEvidence,
    VisualEvidence,
)
from powerforge_api.services.extraction_cursor import decode_cursor, encode_cursor
from powerforge_document_processing.models import DocumentPage
from powerforge_document_processing.storage import StorageError
from powerforge_engineering_model.registry import list_equipment_definitions
from powerforge_extraction.assertion_consistency import redundant_assertions
from powerforge_extraction.enrichment_execution import read_exact
from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding as Binding
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.pinned_sources import selected_snapshot
from powerforge_extraction.publication_records import Candidate, Fragment
from powerforge_extraction.response_audit import ResponseAudit
from powerforge_extraction.stage_execution import StageResult

UNASSIGNED_KEY = UUID(int=0)
EQUIPMENT_NAMES = {e.key: e.display_name for e in list_equipment_definitions()}
ATTRIBUTE_NAMES = {
    (equipment.key, attribute.key): attribute.display_name
    for equipment in list_equipment_definitions()
    for attribute in equipment.attributes
}


def _equipment_order(run_id):
    return (
        select(
            Candidate.id,
            func.row_number()
            .over(
                partition_by=Candidate.registry_type,
                order_by=(DocumentPage.page_number, Candidate.ordinal, Candidate.id),
            )
            .label("occurrence"),
        )
        .join(DocumentPage, DocumentPage.id == Candidate.document_page_id)
        .where(Candidate.run_id == run_id, Candidate.kind == "EQUIPMENT")
        .subquery()
    )


def _equipment_name(tag, tag_state, registry_type, occurrence):
    if tag and tag_state == "PRESENT":
        return tag
    return f"{EQUIPMENT_NAMES.get(registry_type, 'Unknown equipment')} {occurrence}"


def _candidate(row, equipment_type, evidence_ids, occurrence, assertion, redundant_id):
    common = dict(
        id=row.id,
        page_id=row.document_page_id,
        attempt_id=row.work_unit_id,
        mapping_status=row.mapping_status,
        reason_code=row.reason_code,
        evidence_ids=evidence_ids,
        conflict=row.conflict,
    )
    if row.kind == "EQUIPMENT":
        return EquipmentCandidate(
            **common,
            source_description=row.source_description,
            display_name=_equipment_name(row.tag, row.tag_state, row.registry_type, occurrence),
            registry_type=row.registry_type,
            tag=row.tag,
            tag_state=row.tag_state,
            qualification=row.qualification,
            raw_qualification=row.raw_qualification,
        )
    normalized = None
    if row.normalized_type:
        value = {
            "NUMBER": str(row.value_number),
            "INTEGER": str(row.value_integer),
            "TEXT": row.value_text,
            "ENUM": row.value_text,
            "BOOLEAN": row.value_boolean,
        }[row.normalized_type]
        normalized = NormalizedValue(
            type=row.normalized_type, value=value, unit=row.normalized_unit
        )
    return AttributeCandidate(
        **common,
        equipment_id=row.equipment_id,
        association=row.association,
        raw_unmapped=row.raw_unmapped,
        origin=row.attribute_origin or "EXTRACTED",
        attribute_display_name=ATTRIBUTE_NAMES.get((equipment_type, row.proposed_attribute_key)),
        raw_label=row.raw_label,
        raw_value=row.raw_value,
        raw_unit=row.raw_unit,
        proposed_value=row.proposed_value,
        proposed_unit=row.proposed_unit,
        inference_explanation=row.inference_explanation,
        inference_basis=row.inference_basis,
        source_expression=assertion.get("source_expression"),
        source_display_label=assertion.get("display_label"),
        redundant_with_id=redundant_id,
        value_source_support=row.value_source_support or "UNVERIFIED",
        qualifiers=row.qualifiers or [],
        value_form=row.value_form,
        proposed_attribute_key=row.proposed_attribute_key,
        proposed_enum_value=row.proposed_enum_value,
        normalized=normalized,
    )


def _group(
    owner_id,
    description,
    tag,
    tag_state,
    registry_type,
    occurrence,
    page_numbers,
    total,
    attribute_count,
):
    return Group(
        kind="EQUIPMENT" if owner_id else "UNASSIGNED",
        group_id=owner_id if owner_id else "unassigned",
        label=_equipment_name(tag, tag_state, registry_type, occurrence)
        if owner_id
        else "Ungrouped observations",
        source_description=description,
        tag=tag,
        registry_type=registry_type,
        page_numbers=page_numbers,
        matching_candidate_count=total,
        matching_attribute_count=attribute_count,
        matching_identification_count=total - attribute_count,
    )


def _candidate_rows(run_id, query, term):
    owner = aliased(Candidate)
    group_id = case((Candidate.kind == "EQUIPMENT", Candidate.id), else_=Candidate.equipment_id)
    stmt = (
        select(
            Candidate.id.label("candidate_id"),
            group_id.label("group_id"),
            Candidate.kind,
            DocumentPage.page_number,
        )
        .select_from(Candidate)
        .join(DocumentPage, DocumentPage.id == Candidate.document_page_id)
        .outerjoin(owner, owner.id == Candidate.equipment_id)
        .where(Candidate.run_id == run_id)
    )
    if term:
        positions = _equipment_order(run_id)
        stmt = stmt.outerjoin(positions, positions.c.id == group_id)
        tag = func.coalesce(Candidate.tag, owner.tag)
        tag_state = func.coalesce(Candidate.tag_state, owner.tag_state)
        display_name = case(
            ((tag_state == "PRESENT") & tag.is_not(None), tag),
            else_=func.concat(
                case(
                    EQUIPMENT_NAMES,
                    value=func.coalesce(Candidate.registry_type, owner.registry_type),
                    else_="Unknown equipment",
                ),
                " ",
                positions.c.occurrence,
            ),
        )
        # strpos treats percent, underscores and backslashes as literal characters.
        terms = func.unnest(
            func.array_cat(Candidate.search_terms, owner.search_terms)
        ).column_valued("search_term")
        stmt = stmt.where(
            or_(
                exists(select(1).where(func.strpos(terms, term) > 0)),
                func.strpos(func.lower(display_name), term) > 0,
            )
        )
    for column, value in (
        (Candidate.kind, query.kind),
        (Candidate.mapping_status, query.mapping_status),
        (Candidate.document_page_id, query.page_id),
        (func.coalesce(Candidate.registry_type, owner.registry_type), query.equipment_type),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    return stmt


def _page(session, query, scope, limit, stmt):
    anchor = decode_cursor(query.cursor, scope, (int, UUID)) if query.cursor else None
    rows = stmt.subquery()
    keys = (rows.c.sort_page, rows.c.sort_id)
    ordering = keys
    page = select(rows)
    backwards = bool(anchor and anchor[0] == "previous")
    if anchor:
        boundary = tuple_(*keys)
        if backwards:
            page = page.where(boundary < tuple_(*anchor[1]))
            ordering = tuple(key.desc() for key in keys)
        else:
            page = page.where(boundary > tuple_(*anchor[1]))
    batch = session.execute(page.order_by(*ordering).limit(limit + 1)).all()
    extra = len(batch) > limit
    batch = batch[:limit]
    if backwards:
        batch.reverse()
    next_cursor = previous_cursor = None
    if batch:
        if backwards or extra:
            next_cursor = encode_cursor(scope, "next", (batch[-1].sort_page, batch[-1].sort_id))
        if (backwards and extra) or (anchor and not backwards):
            previous_cursor = encode_cursor(
                scope, "previous", (batch[0].sort_page, batch[0].sort_id)
            )
    return batch, {"next_cursor": next_cursor, "previous_cursor": previous_cursor}


def candidates(reader, run_id, query):
    reader._run(run_id)
    if (
        (query.view == "members") != (query.group_id is not None)
        or query.view != "members"
        and query.candidate_id is not None
        or query.view != "flat"
        and query.equipment_id is not None
    ):
        raise RevisionDocumentNotFound("Candidate view, group or selection not found")
    session = reader.session
    term = (query.search or "").strip().casefold()
    scope = identity_hash(
        dict(
            run=str(run_id),
            project=str(reader.project_id),
            revision=str(reader.revision_id),
            document=str(reader.revision_document_id),
            query={
                **query.model_dump(mode="json", exclude={"cursor", "limit", "search"}),
                "search": term,
            },
        )
    )
    limit = query.limit or (25 if query.view == "groups" else 20)
    matching = _candidate_rows(run_id, query, term).subquery()

    if query.view == "groups":
        owner = aliased(Candidate)
        counts = (
            select(
                matching.c.group_id,
                func.array_agg(
                    aggregate_order_by(matching.c.page_number.distinct(), matching.c.page_number)
                ).label("pages"),
                func.count().label("size"),
                func.count().filter(matching.c.kind == "ATTRIBUTE").label("attributes"),
                func.min(matching.c.page_number).label("first_page"),
            )
            .group_by(matching.c.group_id)
            .subquery()
        )
        positions = _equipment_order(run_id)
        stmt = (
            select(
                counts.c.group_id,
                owner.source_description,
                owner.tag,
                owner.tag_state,
                owner.registry_type,
                positions.c.occurrence,
                counts.c.pages,
                counts.c.size,
                counts.c.attributes,
                case((counts.c.group_id.is_(None), 2**31 - 1), else_=counts.c.first_page).label(
                    "sort_page"
                ),
                func.coalesce(counts.c.group_id, literal(UNASSIGNED_KEY)).label("sort_id"),
            )
            .select_from(counts)
            .outerjoin(owner, owner.id == counts.c.group_id)
            .outerjoin(positions, positions.c.id == owner.id)
        )
        total = session.scalar(select(func.count()).select_from(counts))
        batch, cursors = _page(session, query, scope, limit, stmt)
        return BrowserPage[Group](items=[_group(*row[:9]) for row in batch], total=total, **cursors)

    stmt = select(
        matching.c.candidate_id,
        matching.c.page_number.label("sort_page"),
        matching.c.candidate_id.label("sort_id"),
    )
    group_matches = None
    if query.view == "members":
        group_id = query.group_id if query.group_id != "unassigned" else None
        if group_id is None:
            group_exists = session.scalar(
                select(
                    exists().where(
                        Candidate.run_id == run_id,
                        Candidate.kind == "ATTRIBUTE",
                        Candidate.equipment_id.is_(None),
                    )
                )
            )
            if not group_exists:
                raise RevisionDocumentNotFound("Candidate group not found")
            owner = None
        else:
            owner = session.scalar(
                select(Candidate).where(
                    Candidate.run_id == run_id,
                    Candidate.id == group_id,
                    Candidate.kind == "EQUIPMENT",
                )
            )
            if owner is None:
                raise RevisionDocumentNotFound("Candidate group not found")
        group_matches = matching.c.group_id == group_id
        stmt = stmt.where(group_matches)
        if query.candidate_id is not None:
            member = session.scalar(
                select(Candidate).where(
                    Candidate.run_id == run_id, Candidate.id == query.candidate_id
                )
            )
            if (
                member is None
                or (member.id if member.kind == "EQUIPMENT" else member.equipment_id) != group_id
            ):
                raise RevisionDocumentNotFound("Candidate not found in group")
            stmt = stmt.where(matching.c.candidate_id == query.candidate_id)
    elif query.equipment_id is not None:
        stmt = stmt.where(matching.c.group_id == query.equipment_id)

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    batch, cursors = _page(session, query, scope, limit, stmt)
    items = _load_items(session, run_id, [row.candidate_id for row in batch])
    if group_matches is None:
        return BrowserPage[CandidateItem](items=items, total=total, **cursors)
    pages = session.execute(
        select(
            matching.c.page_number,
            func.count(),
            func.count().filter(matching.c.kind == "ATTRIBUTE"),
        )
        .where(group_matches)
        .group_by(matching.c.page_number)
        .order_by(matching.c.page_number)
    ).all()
    identification = _load_items(session, run_id, [owner.id])[0] if owner else None
    group = _group(
        owner.id if owner else None,
        owner.source_description if owner else None,
        owner.tag if owner else None,
        owner.tag_state if owner else None,
        owner.registry_type if owner else None,
        0,
        [page for page, _, _ in pages],
        sum(count for _, count, _ in pages),
        sum(count for _, _, count in pages),
    )
    if identification:
        group.label = identification.display_name
    return MembersPage(
        items=items, group=group, identification=identification, total=total, **cursors
    )


def _load_items(session, run_id, ids):
    if not ids:
        return []
    owner = aliased(Candidate)
    positions = _equipment_order(run_id)
    rows = {
        row.id: (row, equipment_type, occurrence)
        for row, equipment_type, occurrence in session.execute(
            select(Candidate, owner.registry_type, positions.c.occurrence)
            .outerjoin(owner, owner.id == Candidate.equipment_id)
            .outerjoin(positions, positions.c.id == Candidate.id)
            .where(Candidate.run_id == run_id, Candidate.id.in_(ids))
        )
    }
    stage_ids = {row.work_unit_id for row, _, _ in rows.values()}
    stages = {
        s.work_unit_id: s.payload
        for s in session.scalars(select(StageResult).where(StageResult.work_unit_id.in_(stage_ids)))
    }
    duplicate_refs = {key: redundant_assertions(payload) for key, payload in stages.items()}
    local_ids = {
        (row.work_unit_id, row.local_ref): row.id
        for row in session.scalars(select(Candidate).where(Candidate.work_unit_id.in_(stage_ids)))
    }
    evidence = defaultdict(list)
    for owner_id, evidence_id in session.execute(
        select(Fragment.candidate_id, Fragment.id)
        .where(Fragment.run_id == run_id, Fragment.candidate_id.in_(ids))
        .order_by(Fragment.candidate_id, Fragment.ordinal)
    ):
        evidence[owner_id].append(evidence_id)
    items = []
    for id in ids:
        row, equipment_type, occurrence = rows[id]
        payload = stages[row.work_unit_id]
        assertions = (
            payload.get("equipment", ())
            if row.kind == "EQUIPMENT"
            else (*payload.get("attributes", ()), *payload.get("raw_unmapped", ()))
        )
        primary_ref = duplicate_refs[row.work_unit_id].get(row.local_ref)
        items.append(
            _candidate(
                row,
                equipment_type,
                evidence[id],
                occurrence,
                assertions[row.ordinal],
                local_ids.get((row.work_unit_id, primary_ref)),
            )
        )
    return items


def sources(reader, run_id):
    reader._run(run_id)
    rows = reader.session.execute(
        select(Binding, DocumentPage.page_number, StageResult.page_context_hash)
        .join(DocumentPage, DocumentPage.id == Binding.document_page_id)
        .outerjoin(
            StageResult,
            (StageResult.run_id == Binding.run_id)
            & (StageResult.document_page_id == Binding.document_page_id)
            & (StageResult.stage == "EQUIPMENT_RECOGNITION"),
        )
        .where(Binding.run_id == run_id)
        .order_by(DocumentPage.page_number)
    )
    counts = {
        page_id: dict(received=received, accepted=accepted, quarantined=quarantined)
        for page_id, received, accepted, quarantined in reader.session.execute(
            select(
                ResponseAudit.document_page_id,
                ResponseAudit.received,
                ResponseAudit.accepted,
                ResponseAudit.quarantined,
            )
            .join(StageResult, StageResult.work_unit_id == ResponseAudit.work_unit_id)
            .where(ResponseAudit.run_id == run_id)
        )
    }
    pages = []
    for binding, number, context_hash in rows:
        snapshot = _snapshot(reader.session, binding)
        pages.append(
            PinnedRunPage(
                document_id=binding.document_id,
                page_id=binding.document_page_id,
                page_number=number,
                page_image_id=snapshot.image.id,
                processing_run_id=binding.processing_run_id,
                prepared_result_id=binding.prepared_result_id,
                spatial_result_id=binding.spatial_result_id,
                prepared_manifest_hash=binding.manifest_hash,
                spatial_manifest_hash=binding.spatial_manifest_hash,
                preparation_producer_run_id=snapshot.prepared.manifest.producer_run_id,
                layout_producer_run_id=snapshot.layout.producer_run_id,
                text_coverage=snapshot.prepared.manifest.text_coverage,
                page_context_hash=context_hash,
                assertion_counts=counts.get(binding.document_page_id),
            )
        )
    return RunSources(items=pages)


def _snapshot(session, binding):
    try:
        snapshot = selected_snapshot(session, binding.prepared_result_id, binding.spatial_result_id)
        if (
            snapshot.layout.owner.document_page_id != binding.document_page_id
            or snapshot.layout.owner.document_id != binding.document_id
            or snapshot.layout.owner.processing_run_id != binding.processing_run_id
            or snapshot.layout.identity_hash != binding.spatial_manifest_hash
            or snapshot.prepared.manifest.identity_hash != binding.manifest_hash
        ):
            raise ValueError("Binding identity differs")
    except ValueError:
        raise StorageDownloadFailed("Pinned page unavailable") from None
    return snapshot


def evidence(reader, evidence_id, storage, expires):
    session = reader.session
    scope = reader._runs().subquery()
    statement = (
        select(Fragment, Binding, Candidate.kind, Candidate.value_source_support)
        .join(scope, scope.c.id == Fragment.run_id)
        .join(Candidate, Candidate.id == Fragment.candidate_id)
        .join(
            Binding,
            (Binding.run_id == Fragment.run_id)
            & (Binding.document_page_id == Fragment.document_page_id),
        )
        .where(Fragment.id == evidence_id)
    )
    match = session.execute(statement).one_or_none()
    if match is None:
        raise RevisionDocumentNotFound("Evidence not found")
    row, binding, kind, value_source_support = match
    snapshot = _snapshot(session, binding)
    if snapshot.image.id != row.page_image_id:
        raise StorageDownloadFailed("Pinned evidence source unavailable")

    def signed(ref, key, mime_type):
        try:
            data = read_exact(storage, key, ref.size_bytes, ref.sha256)
            url = storage.create_download_url(key, str(ref.id), mime_type, "inline", expires)
        except (StorageError, ValueError):
            raise StorageDownloadFailed("Pinned evidence source unavailable") from None
        return SignedArtifact(id=ref.id, sha256=ref.sha256, url=url, expires_seconds=expires), data

    page_image, _ = signed(snapshot.image, snapshot.image_key, "image/png")
    common = dict(
        id=row.id,
        candidate_id=row.candidate_id,
        role=row.role,
        page_id=row.document_page_id,
        page_image_id=row.page_image_id,
        page_image=page_image,
        page_image_width=snapshot.image.width_px,
        page_image_height=snapshot.image.height_px,
        candidate_value_source_support=(value_source_support or "UNVERIFIED")
        if kind == "ATTRIBUTE"
        else None,
    )
    if row.localization == "RESOLVED":
        source = next(
            (item for item in snapshot.prepared.objects if item[0].id == row.text_artifact_id), None
        )
        if source is None:
            raise StorageDownloadFailed("Pinned evidence source unavailable")
        artifact, data = signed(*source, "text/plain; charset=utf-8")
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise StorageDownloadFailed("Pinned evidence source unavailable") from None
        if row.end > len(text) or text[row.start : row.end] != row.quote:
            raise StorageDownloadFailed("Pinned evidence source unavailable")
        return ResolvedEvidence(
            **common,
            modality=row.modality,
            text_artifact_id=row.text_artifact_id,
            text_artifact=artifact,
            start=row.start,
            end=row.end,
            quote=row.quote,
            regions=row.regions,
            source_issues=row.source_issues,
        )
    if row.localization == "VISUAL_REPORTED":
        return VisualEvidence(**common, reported_text=row.reported_text, region=row.region)
    return UnresolvedEvidence(**common, reason_code=row.reason_code)
