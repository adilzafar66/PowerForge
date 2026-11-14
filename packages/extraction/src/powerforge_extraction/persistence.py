"""Internal worker persistence boundary. Caller owns the outer transaction.

No scheduling, provider calls, canonical writes or independent commits. A savepoint
rolls back all output and the completion marker on any publication failure.
"""

from __future__ import annotations

import codecs
import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from powerforge_document_model import PageArtifactType, ProcessingRunStatus
from powerforge_document_processing.models import DocumentPage, DocumentProcessingRun, PageArtifact
from powerforge_document_processing.storage.base import ObjectStorage
from powerforge_extraction.contracts import (
    AICallInput,
    EvidenceInput,
    RunInput,
    WorkUnitInput,
    WorkUnitOutput,
)
from powerforge_extraction.enums import CandidateKind, ExtractionRunStatus, WorkUnitStatus
from powerforge_extraction.models import (
    CandidateEvidence,
    Evidence,
    ExtractedTable,
    ExtractionAICall,
    ExtractionCandidate,
    ExtractionRun,
    ExtractionWorkUnit,
    SourceGroup,
)

if TYPE_CHECKING:
    from powerforge_extraction.enriched_publication import VerifiedEnrichedPublication


def effective_units(run_id: UUID) -> Select[tuple[UUID]]:
    """DB uniqueness permits exactly one committed success per logical key."""
    return select(ExtractionWorkUnit.id).where(
        ExtractionWorkUnit.run_id == run_id,
        ExtractionWorkUnit.status == WorkUnitStatus.COMPLETED,
    )


class ExtractionPersistence:
    def __init__(self, session: Session, storage: ObjectStorage | None = None) -> None:
        # Complete the shared FK registry for standalone worker/service callers too.
        from importlib import import_module

        import_module("powerforge_extraction.enrichment_models")
        import_module("powerforge_extraction.layout_models")
        self.session = session
        self.storage = storage

    def create_run(self, inputs: RunInput) -> ExtractionRun:
        inputs = RunInput.model_validate(inputs.model_dump())
        processing = self.session.get(DocumentProcessingRun, inputs.processing_run_id)
        if (
            processing is None
            or processing.document_id != inputs.document_id
            or (processing.status != ProcessingRunStatus.COMPLETED)
        ):
            raise ValueError("Extraction requires compatible completed processing")
        data = inputs.model_dump(mode="json")
        # Order-insensitive artifact/stage selections produce identical active identities.
        identity = {
            k: v
            for k, v in data.items()
            if k not in {"requested_by", "reextracts_run_id", "initiated_from_revision_document_id"}
        }
        identity["input_artifact_ids"] = sorted(identity["input_artifact_ids"])
        identity["stages"] = sorted(identity["stages"])
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        row = ExtractionRun(
            **{
                **inputs.model_dump(),
                "selected_pages": data["selected_pages"],
                "stages": data["stages"],
                "input_artifact_ids": data["input_artifact_ids"],
            },
            input_identity_hash=digest,
            status=ExtractionRunStatus.PENDING,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def create_work_unit(self, run_id: UUID, inputs: WorkUnitInput) -> ExtractionWorkUnit:
        inputs = WorkUnitInput.model_validate(inputs.model_dump())
        run = self.session.scalar(
            select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
        )
        if run is None:
            raise ValueError("Extraction run not found")
        data = inputs.model_dump()
        data["input_artifact_ids"] = [str(i) for i in inputs.input_artifact_ids]
        unit = ExtractionWorkUnit(
            **data,
            run_id=run.id,
            document_id=run.document_id,
            processing_run_id=run.processing_run_id,
            status=WorkUnitStatus.PENDING,
        )
        self.session.add(unit)
        self.session.flush()
        run.units_total = self.session.scalar(
            select(func.count(func.distinct(ExtractionWorkUnit.unit_key))).where(
                ExtractionWorkUnit.run_id == run.id
            )
        )
        self.session.flush()
        return unit

    def record_ai_call(self, work_unit_id: UUID, call: AICallInput) -> ExtractionAICall:
        """Append technical telemetry even when the unit subsequently fails; no commit."""
        call = AICallInput.model_validate(call.model_dump())
        unit = self.session.get(ExtractionWorkUnit, work_unit_id)
        if unit is None or unit.status != WorkUnitStatus.RUNNING:
            raise ValueError("AI telemetry requires a running attempt")
        row = ExtractionAICall(
            **call.model_dump(exclude={"validation_diagnostics"}),
            validation_diagnostics=[
                issue.model_dump(mode="json") for issue in call.validation_diagnostics
            ],
            run_id=unit.run_id,
            document_id=unit.document_id,
            processing_run_id=unit.processing_run_id,
            work_unit_id=unit.id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def publish(
        self,
        work_unit_id: UUID,
        output: WorkUnitOutput,
        *,
        verification: VerifiedEnrichedPublication | None = None,
    ) -> None:
        from powerforge_extraction.enriched_contracts import EnrichedOutput

        # Revalidate even if a caller used model_construct or mutated a nested container.
        output = (
            EnrichedOutput if isinstance(output, EnrichedOutput) else WorkUnitOutput
        ).model_validate(output.model_dump())
        with self.session.begin_nested():
            # Consistent lock order: parent run, then producing unit.
            run_id = self.session.scalar(
                select(ExtractionWorkUnit.run_id).where(ExtractionWorkUnit.id == work_unit_id)
            )
            run = self.session.scalar(
                select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
            )
            unit = self.session.scalar(
                select(ExtractionWorkUnit)
                .where(ExtractionWorkUnit.id == work_unit_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                run is None
                or unit is None
                or run.status != ExtractionRunStatus.RUNNING
                or unit.status != WorkUnitStatus.RUNNING
            ):
                raise ValueError("Publication requires an active run and running unit")
            owner = dict(
                run_id=run.id,
                document_id=run.document_id,
                processing_run_id=run.processing_run_id,
                work_unit_id=unit.id,
            )
            enhanced = run.profile_version in {"execution-profile-v5", "execution-profile-v6"}
            if enhanced and not isinstance(output, EnrichedOutput):
                if any(
                    getattr(output, k)
                    for k in (
                        "evidence",
                        "tables",
                        "candidates",
                        "source_groups",
                        "candidate_evidence",
                    )
                ):
                    raise ValueError("Enhanced runs require explicit successor output contracts")
                output = EnrichedOutput.model_validate(output.model_dump())
            if isinstance(output, EnrichedOutput) and not enhanced:
                raise ValueError("Enhanced output requires an enhanced extraction run")
            if enhanced:
                if verification is None:
                    raise ValueError(
                        "Enhanced publication requires independent source verification"
                    )
                verification.verify(self.session, run, unit, output)
            else:
                self._validate_locations(unit, output)
            for group in output.source_groups:
                self.session.add(
                    SourceGroup(
                        **owner, **group.model_dump(mode="json", exclude={"id"}), id=group.id
                    )
                )
            for table in output.tables:
                self.session.add(
                    ExtractedTable(
                        **owner, **table.model_dump(mode="json", exclude={"id"}), id=table.id
                    )
                )
            self.session.flush()
            for evidence in output.evidence:
                data = evidence.model_dump(exclude={"location"})
                location = evidence.location
                data.update(
                    document_page_id=location.document_page_id,
                    page_artifact_id=location.page_artifact_id,
                )
                if isinstance(output, EnrichedOutput):
                    data.update(
                        enrichment_artifact_id=location.enrichment_artifact_id,
                        geometry_artifact_id=location.geometry_artifact_id,
                        source_locator=location.model_dump(mode="json"),
                    )
                if location.region is not None:
                    data.update(location.region.model_dump())
                self.session.add(Evidence(**owner, **data))
            self.session.flush()
            # Mention rows precede dependent attributes (self-reference FK).
            for candidate in sorted(
                output.candidates, key=lambda c: c.kind != CandidateKind.EQUIPMENT_MENTION
            ):
                self.session.add(ExtractionCandidate(**owner, **candidate.model_dump()))
                self.session.flush()
            for link in output.candidate_evidence:
                self.session.add(CandidateEvidence(**owner, **link.model_dump()))
            for call in output.ai_calls:
                self.session.add(ExtractionAICall(**owner, **call.model_dump()))
            self.session.flush()
            self._validate_references(run.id, unit.id, output)
            unit.output_counts = {
                name: len(getattr(output, name))
                for name in WorkUnitOutput.model_fields
                if name != "diagnostic_counts"
            }
            unit.output_counts.update(output.diagnostic_counts)
            unit.status = WorkUnitStatus.COMPLETED
            unit.finished_at = datetime.now(UTC)
            self.session.flush()
            completed = list(
                self.session.scalars(
                    select(ExtractionWorkUnit).where(
                        ExtractionWorkUnit.run_id == run.id,
                        ExtractionWorkUnit.status == WorkUnitStatus.COMPLETED,
                    )
                )
            )
            run.units_completed = len(completed)
            run.pages_processed = len({p for u in completed for p in u.page_numbers})
            self.session.flush()

    def _validate_locations(self, unit: ExtractionWorkUnit, output: WorkUnitOutput) -> None:
        locations = [e.location for e in output.evidence]
        locations += [loc for t in output.tables for loc in t.source_locations]
        locations += [c.location for t in output.tables for c in t.layout.cells if c.location]
        for loc in locations:
            page = self.session.get(DocumentPage, loc.document_page_id)
            if (
                page is None
                or page.document_id != unit.document_id
                or page.page_number not in unit.page_numbers
            ):
                raise ValueError("Source page is outside work-unit inputs")
            if loc.page_artifact_id:
                artifact = self.session.get(PageArtifact, loc.page_artifact_id)
                if (
                    artifact is None
                    or artifact.document_page_id != page.id
                    or artifact.processing_run_id != unit.processing_run_id
                    or str(artifact.id) not in unit.input_artifact_ids
                ):
                    raise ValueError("Source artifact is outside pinned inputs")
        text_lengths: dict[UUID, int] = {}
        for e in output.evidence:
            if e.text_start is not None:
                artifact = self.session.get(PageArtifact, e.location.page_artifact_id)
                if artifact.artifact_type != PageArtifactType.NATIVE_TEXT:
                    raise ValueError("Offsets require a versioned text artifact")
                if artifact.id not in text_lengths:
                    text_lengths[artifact.id] = self._text_artifact_length(artifact)
                if e.text_end > text_lengths[artifact.id]:
                    raise ValueError("Offsets exceed the pinned text artifact")

    def _text_artifact_length(self, artifact: PageArtifact) -> int:
        """Count Unicode codepoints in the exact immutable UTF-8 object, once per publish.

        Stream verification bounds memory and rejects missing, truncated or changed
        objects. Page-level character counts may describe a different processing run.
        """
        if self.storage is None:
            raise ValueError("Text-offset validation requires object storage")
        digest = hashlib.sha256()
        decoder = codecs.getincrementaldecoder("utf-8")()
        byte_count = char_count = 0
        stream = self.storage.get(artifact.storage_key)
        try:
            while chunk := stream.read(64 * 1024):
                byte_count += len(chunk)
                if byte_count > artifact.size_bytes:
                    raise ValueError("Pinned text artifact size mismatch")
                digest.update(chunk)
                char_count += len(decoder.decode(chunk))
            char_count += len(decoder.decode(b"", final=True))
        except UnicodeError:
            raise ValueError("Pinned text artifact must be valid UTF-8") from None
        finally:
            stream.close()
        if byte_count != artifact.size_bytes or digest.hexdigest() != artifact.sha256:
            raise ValueError("Pinned text artifact integrity mismatch")
        return char_count

    def _validate_references(self, run_id: UUID, unit_id: UUID, output: WorkUnitOutput) -> None:
        table_reference_cache = {}
        for item in [*output.source_groups, *output.tables]:
            for evidence_id in item.evidence_ids:
                e = self.session.get(Evidence, evidence_id)
                if (
                    e is None
                    or e.run_id != run_id
                    or (
                        e.work_unit_id != unit_id
                        and self.session.get(ExtractionWorkUnit, e.work_unit_id).status
                        != WorkUnitStatus.COMPLETED
                    )
                ):
                    raise ValueError("Grouping evidence must be committed in the same run")
        for e in output.evidence:
            self._validate_table_evidence(run_id, unit_id, e, table_reference_cache)
        for c in output.candidates:
            for model, ref in [
                (SourceGroup, c.source_group_id),
                (ExtractionCandidate, c.equipment_mention_candidate_id),
            ]:
                if ref:
                    row = self.session.get(model, ref)
                    if (
                        row is None
                        or row.run_id != run_id
                        or (
                            row.work_unit_id != unit_id
                            and self.session.get(ExtractionWorkUnit, row.work_unit_id).status
                            != WorkUnitStatus.COMPLETED
                        )
                    ):
                        raise ValueError("Candidate context must be committed in the same run")
        for link in output.candidate_evidence:
            candidate = self.session.get(ExtractionCandidate, link.candidate_id)
            evidence = self.session.get(Evidence, link.evidence_id)
            if (
                candidate is None
                or candidate.work_unit_id != unit_id
                or evidence is None
                or evidence.run_id != run_id
                or (
                    evidence.work_unit_id != unit_id
                    and self.session.get(ExtractionWorkUnit, evidence.work_unit_id).status
                    != WorkUnitStatus.COMPLETED
                )
            ):
                raise ValueError("Invalid candidate evidence ownership")
            self._validate_table_evidence(run_id, unit_id, evidence, table_reference_cache)

    def _validate_table_evidence(self, run_id: UUID, unit_id: UUID, evidence, cache: dict) -> None:
        if evidence.table_id is None:
            if evidence.source_kind == "TABLE_CELL":
                raise ValueError("Table-cell evidence requires a table/cell locator")
            return
        if ("checked", evidence.id) in cache:
            return

        def cached(model, uid):
            key = (model, uid)
            if key not in cache:
                cache[key] = self.session.get(model, uid)
            return cache[key]

        unit = cached(ExtractionWorkUnit, unit_id)
        table = cached(ExtractedTable, evidence.table_id)
        if table is not None and table.layout_schema_version == "table-layout-v2":
            from powerforge_extraction.enriched_publication import table_evidence

            table_evidence(self, run_id, unit_id, evidence)
            cache["checked", evidence.id] = True
            return
        producer = cached(ExtractionWorkUnit, table.work_unit_id) if table else None
        if (
            table is None
            or table.run_id != run_id
            or producer is None
            or (
                table.processing_run_id != unit.processing_run_id
                or producer.id != unit.id
                and producer.status != WorkUnitStatus.COMPLETED
            )
        ):
            raise ValueError("Table evidence requires an owned, committed table producer")
        if unit.stage == "TABLE_INTERPRETATION" and (
            producer.stage != "TABLE_RECONSTRUCTION"
            or producer.page_numbers != unit.page_numbers
            or set(producer.input_artifact_ids) != set(unit.input_artifact_ids)
        ):
            raise ValueError("Table interpretation requires its planned page/artifact producer")
        locations = table.source_locations
        if evidence.source_kind == "TABLE_CELL" and evidence.cell_id is None:
            raise ValueError("Table-cell evidence requires a table/cell locator")
        if evidence.cell_id is not None:
            cells = [c for c in table.layout["cells"] if c["id"] == evidence.cell_id]
            if len(cells) != 1:
                raise ValueError("Unknown source table cell")
            if cells[0].get("location") is not None:
                locations = [cells[0]["location"]]
            # A hybrid cell may explicitly cite both immutable representations.
            # These server-authored locators are rederived by the 6D context loader.
            metadata = table.layout.get("metadata", {})
            if (
                isinstance(metadata.get("producer"), dict)
                and metadata["producer"].get("version") == "table-grounding-interpretation-v1"
            ):
                locations = metadata.get("cell_source_locations", {}).get(
                    evidence.cell_id, locations
                )
        location = evidence.location if isinstance(evidence, EvidenceInput) else None
        page_id = location.document_page_id if location else evidence.document_page_id
        artifact_id = location.page_artifact_id if location else evidence.page_artifact_id
        page = cached(DocumentPage, page_id)
        if (
            page is None
            or page.page_number not in unit.page_numbers
            or (
                artifact_id is not None
                and (
                    str(artifact_id) not in unit.input_artifact_ids
                    or str(artifact_id) not in producer.input_artifact_ids
                )
            )
            or not any(
                loc["document_page_id"] == str(page_id)
                and (
                    loc.get("page_artifact_id") is None
                    or loc["page_artifact_id"] == str(artifact_id)
                )
                for loc in locations
            )
        ):
            raise ValueError("Table/cell evidence differs from pinned page/artifact ownership")
        cache["checked", evidence.id] = True
