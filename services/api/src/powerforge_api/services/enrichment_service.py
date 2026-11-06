"""SELECT-only source history; reciprocal direct-ID purpose enforcement."""

import json

from sqlalchemy import func, select

from powerforge_api.exceptions import RevisionDocumentNotFound, StorageDownloadFailed
from powerforge_api.services.extraction_service import ExtractionReadService
from powerforge_document_processing.models import DocumentPage, DocumentProcessingRun, PageArtifact
from powerforge_document_processing.storage.base import StorageError
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.enrichment_execution import read_exact
from powerforge_extraction.enrichment_models import (
    SourceEnrichmentArtifact,
    SourceEnrichmentPageResult,
)
from powerforge_extraction.enrichment_profiles import PURPOSE
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_provenance.spatial_sources import PreparedPage


class EnrichmentReadService(ExtractionReadService):
    def _runs(self):
        return select(ExtractionRun).where(
            ExtractionRun.document_id == self.document_id,
            ExtractionRun.execution_purpose == PURPOSE,
        )

    def inputs(self, limit, offset):
        stmt = select(DocumentProcessingRun).where(
            DocumentProcessingRun.document_id == self.document_id,
            DocumentProcessingRun.status == "COMPLETED",
        )
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = list(
            self.session.scalars(
                stmt.order_by(
                    DocumentProcessingRun.created_at.desc(), DocumentProcessingRun.id.desc()
                )
                .limit(limit)
                .offset(offset)
            )
        )
        pages = {}
        if rows:
            for run_id, number in self.session.execute(
                select(PageArtifact.processing_run_id, DocumentPage.page_number)
                .join(DocumentPage, DocumentPage.id == PageArtifact.document_page_id)
                .where(
                    PageArtifact.processing_run_id.in_([r.id for r in rows]),
                    PageArtifact.artifact_type == "ANALYSIS_IMAGE",
                )
                .order_by(DocumentPage.page_number)
            ):
                pages.setdefault(run_id, []).append(number)
        return dict(
            items=[
                dict(
                    processing_run_id=r.id,
                    profile_hash=r.profile_hash,
                    created_at=r.created_at,
                    available_pages=pages.get(r.id, []),
                )
                for r in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
            max_selected_pages=50,
        )

    def run_response(self, run):
        control = self.session.get(RunExecution, run.id)
        return dict(
            id=run.id,
            document_id=run.document_id,
            processing_run_id=run.processing_run_id,
            execution_purpose=run.execution_purpose,
            profile_hash=run.profile_hash,
            status=run.status,
            selected_pages=run.selected_pages,
            created_at=run.created_at,
            finished_at=run.finished_at,
            pages_processed=run.pages_processed,
            error_code=run.error_code,
            admissions=control.calls_admitted if control else None,
            admission_budget=control.configuration["max_calls"] if control else None,
            operating_cost=None,
        )

    def history(self, limit, offset):
        stmt = self._runs()
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = self.session.scalars(
            stmt.order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return dict(
            items=[self.run_response(r) for r in rows], total=total, limit=limit, offset=offset
        )

    def detail(self, run_id):
        run = self._run(run_id)
        units = list(
            self.session.scalars(
                select(ExtractionWorkUnit)
                .where(ExtractionWorkUnit.run_id == run.id)
                .order_by(ExtractionWorkUnit.unit_key, ExtractionWorkUnit.attempt_number)
            )
        )
        results = list(
            self.session.scalars(
                select(SourceEnrichmentPageResult)
                .join(
                    ExtractionWorkUnit,
                    ExtractionWorkUnit.id == SourceEnrichmentPageResult.work_unit_id,
                )
                .where(
                    SourceEnrichmentPageResult.run_id == run.id,
                    ExtractionWorkUnit.status == "COMPLETED",
                )
                .order_by(SourceEnrichmentPageResult.document_page_id)
            )
        )
        return dict(
            run=self.run_response(run),
            attempts=[
                dict(
                    id=u.id,
                    unit_key=u.unit_key,
                    attempt_number=u.attempt_number,
                    status=u.status,
                    page_numbers=u.page_numbers,
                    started_at=u.started_at,
                    finished_at=u.finished_at,
                    error_code=u.error_code,
                    output_counts=u.output_counts,
                )
                for u in units
            ],
            results=[
                dict(
                    id=r.id,
                    document_page_id=r.document_page_id,
                    page_number=r.manifest["owner"]["page_number"],
                    work_unit_id=r.work_unit_id,
                    ocr_decision=r.manifest["ocr_decision"],
                    ocr_reason=r.manifest["ocr_reason"],
                    manifest_hash=r.manifest_hash,
                    preparation_hash=r.preparation_hash,
                    usage=r.usage,
                )
                for r in results
            ],
            confirmed_ocr_invocations=sum(r.usage.get("ocr_invocations", 0) for r in results),
            ocr_requests_started=sum(u.output_counts.get("ocr_requests_started", 0) for u in units),
        )

    def result(self, run_id, result_id):
        self._run(run_id)
        row = self.session.scalar(
            select(SourceEnrichmentPageResult)
            .join(
                ExtractionWorkUnit, ExtractionWorkUnit.id == SourceEnrichmentPageResult.work_unit_id
            )
            .where(
                SourceEnrichmentPageResult.run_id == run_id,
                SourceEnrichmentPageResult.id == result_id,
                ExtractionWorkUnit.status == "COMPLETED",
            )
        )
        if row is None:
            raise RevisionDocumentNotFound("Successful source result not found")
        manifest = PreparedPage.model_validate_json(json.dumps(row.manifest))
        if manifest.identity_hash != row.manifest_hash:
            raise RevisionDocumentNotFound("Source result identity mismatch")
        return row, manifest

    def artifact(self, run_id, artifact_id, storage, expires):
        self._run(run_id)
        row = self.session.scalar(
            select(SourceEnrichmentArtifact)
            .join(
                SourceEnrichmentPageResult,
                SourceEnrichmentPageResult.id == SourceEnrichmentArtifact.result_id,
            )
            .where(
                SourceEnrichmentArtifact.id == artifact_id,
                SourceEnrichmentPageResult.run_id == run_id,
            )
        )
        if row is None:
            raise RevisionDocumentNotFound("Source artifact not found")
        _, manifest = self.result(run_id, row.result_id)
        descriptors = [
            *manifest.derived_images,
            *(a for r in manifest.representations for a in (r.text_artifact, r.geometry_artifact)),
        ]
        descriptor = next((a for a in descriptors if a.id == row.id), None)
        if descriptor is None or (descriptor.sha256, descriptor.size_bytes, descriptor.role) != (
            row.sha256,
            row.size_bytes,
            row.role,
        ):
            raise RevisionDocumentNotFound("Source artifact identity mismatch")
        try:
            read_exact(storage, row.storage_key, row.size_bytes, row.sha256)
            url = storage.create_download_url(
                row.storage_key, str(row.id), row.mime_type, "inline", expires
            )
        except (StorageError, ValueError):
            raise StorageDownloadFailed("Source artifact unavailable") from None
        return dict(
            id=row.id,
            result_id=row.result_id,
            role=row.role,
            sha256=row.sha256,
            size_bytes=row.size_bytes,
            url=url,
            expires_seconds=expires,
        )
