"""Explicit enrichment-first admission; exact source bindings participate in ensure/retry."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from powerforge_document_processing.models import Document
from powerforge_extraction.contracts import RunInput, WorkUnitInput
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.dependencies import prerequisite, unit_key
from powerforge_extraction.enriched_profiles import enriched_profile
from powerforge_extraction.enriched_sources import selected_snapshot
from powerforge_extraction.enrichment_models import RunSourceEnrichmentBinding
from powerforge_extraction.errors import ExtractionConflict, ExtractionDisabled, ExtractionError
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.models import ExtractionRun
from powerforge_extraction.persistence import ExtractionPersistence


class EnrichmentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prepared_result_id: UUID
    spatial_result_id: UUID


def metadata(profile, stage, page, binding):
    return dict(
        prerequisite_key=prerequisite(stage, page),
        stage_manifest_version=profile.schema_version,
        stage_identity=next(s for s in profile.manifest["stages"] if s["stage"] == stage),
        source_page_id=str(binding.document_page_id),
        binding_hash=binding.binding_hash,
    )


def start_enriched(
    coordinator, document_id, revision_document_id, profile_key, pages, mode, selections
):
    session, settings = coordinator.session, coordinator.settings
    if not settings.extraction_enabled:
        raise ExtractionDisabled("Extraction is disabled")
    profile = enriched_profile(profile_key, settings)
    if profile.provider == "openai" and not settings.extraction_external_enabled:
        raise ExtractionDisabled("External extraction must be explicitly enabled")
    if mode not in ("ensure", "reextract"):
        raise ExtractionError("Unknown extraction request mode")
    document = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if document is None or document.size_bytes > settings.extraction_max_document_bytes:
        raise ExtractionError("Source document unavailable or over configured bound")
    if not selections or len(selections) > min(50, profile.max_pages):
        raise ExtractionConflict("Complete enrichment first; select one exact result pair per page")
    snapshots = []
    try:
        for selection in selections:
            item = EnrichmentSelection.model_validate(selection)
            source = selected_snapshot(session, item.prepared_result_id, item.spatial_result_id)
            if source.layout.owner.document_id != document_id:
                raise ValueError("Foreign source")
            snapshots.append(source)
    except (ValueError, KeyError):
        raise ExtractionConflict(
            "Select compatible completed enrichment for every selected page"
        ) from None
    snapshots.sort(key=lambda s: s.layout.owner.page_number)
    owners = [s.layout.owner for s in snapshots]
    chosen = [o.page_number for o in owners]
    if (
        len(set(chosen)) != len(chosen)
        or pages != chosen
        or len({o.processing_run_id for o in owners}) != 1
    ):
        raise ExtractionConflict("Bindings must cover exactly the selected pages of one base run")
    for s in snapshots:
        image = s.image
        if (
            s.layout.algorithm_sha256 != profile.source_rules
            or image.size_bytes > profile.max_input_bytes
            or image.width_px * image.height_px > profile.max_image_pixels
        ):
            raise ExtractionConflict("Enrichment is incompatible with the selected bounded profile")
    pairs = [
        dict(
            prepared=str(s.prepared.manifest.id),
            prepared_hash=s.prepared.manifest.identity_hash,
            spatial=str(s.layout.id),
            spatial_hash=s.layout.identity_hash,
        )
        for s in snapshots
    ]
    target = identity_hash(dict(profile=profile.identity_hash, pages=chosen, bindings=pairs))
    latest = session.scalar(
        select(ExtractionRun)
        .where(
            ExtractionRun.document_id == document_id,
            ExtractionRun.execution_purpose == "EXTRACTION",
            ExtractionRun.input_identity_hash == target,
        )
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        .limit(1)
    )
    if latest and (latest.status in ("PENDING", "RUNNING") or mode == "ensure"):
        return latest
    persistence = ExtractionPersistence(session)
    inputs = RunInput(
        document_id=document_id,
        processing_run_id=owners[0].processing_run_id,
        initiated_from_revision_document_id=revision_document_id,
        extractor_version="enriched-extraction-v1",
        schema_version=profile.schema_version,
        profile_version=profile.version,
        profile_hash=profile.identity_hash,
        provider=profile.provider,
        model=profile.model,
        prompt_version=profile.prompt_version,
        prompt_hash=profile.prompt_hash,
        selected_pages=chosen,
        stages=list(profile.stages),
        input_artifact_ids=[a.id for s in snapshots for a in s.prepared.manifest.base_artifacts],
        reextracts_run_id=latest.id if latest else None,
    )
    data = inputs.model_dump()
    data["input_artifact_ids"] = [str(a) for a in inputs.input_artifact_ids]
    run = ExtractionRun(**data, input_identity_hash=target, status="PENDING")
    session.add(run)
    session.flush()
    session.add(RunExecution(run_id=run.id, configuration=profile.model_dump(mode="json")))
    session.flush()
    for source, pair in zip(snapshots, pairs, strict=True):
        owner = source.layout.owner
        binding = RunSourceEnrichmentBinding(
            run_id=run.id,
            document_id=document_id,
            processing_run_id=owner.processing_run_id,
            document_page_id=owner.document_page_id,
            prepared_result_id=source.prepared.manifest.id,
            manifest_hash=source.prepared.manifest.identity_hash,
            spatial_result_id=source.layout.id,
            spatial_manifest_hash=source.layout.identity_hash,
            binding_hash=identity_hash(pair),
        )
        session.add(binding)
        session.flush()
        for stage in profile.stages:
            unit = persistence.create_work_unit(
                run.id,
                WorkUnitInput(
                    unit_key=unit_key(stage, owner.page_number),
                    stage=stage,
                    page_numbers=[owner.page_number],
                    input_artifact_ids=[a.id for a in source.prepared.manifest.base_artifacts],
                    execution_metadata=metadata(profile, stage, owner.page_number, binding),
                ),
            )
            coordinator._delivery(unit, coordinator.now())
    return run
