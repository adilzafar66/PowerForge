"""Local CPU I/O outside transactions, bounded source reads and leased publication."""

import time
from io import BytesIO

from sqlalchemy import select

from powerforge_ai.extraction import ErrorCode
from powerforge_ai.ocr import OCRFailure
from powerforge_document_processing.models import Document, DocumentPage, DocumentProcessingRun
from powerforge_document_processing.storage.base import StorageError, TransientStorageError
from powerforge_extraction.enrichment_prepare import prepare_page, sha
from powerforge_extraction.enrichment_profiles import PURPOSE, require_preparation
from powerforge_extraction.enrichment_service import (
    artifact_key,
    publish_preparation,
    source_snapshot,
)
from powerforge_extraction.errors import LeaseLost
from powerforge_extraction.execution import heartbeats
from powerforge_extraction.models import ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator


def read_exact(storage, key, size, digest):
    stream = storage.get(key)
    try:
        data = bytearray()
        while len(data) <= size:
            chunk = stream.read(min(1024 * 1024, size + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        value = bytes(data)
        if len(value) != size or sha(value) != digest:
            raise ValueError("Pinned source object differs from its immutable identity")
        return value
    finally:
        stream.close()


def execute_preparation(unit_id, factory, storage, settings, provider_factory):
    with factory.begin() as session:
        claim = ExtractionCoordinator(session, settings).claim(unit_id, purpose=PURPOSE)
    if claim is None:
        return False
    try:
        with heartbeats(factory, claim, settings):
            started = time.monotonic()
            cpu = time.process_time()
            require_preparation(claim.profile)
            with factory() as session:
                unit = session.get(ExtractionWorkUnit, unit_id)
                document = session.get(Document, unit.document_id)
                processing = session.get(DocumentProcessingRun, unit.processing_run_id)
                page = session.scalar(
                    select(DocumentPage).where(
                        DocumentPage.document_id == document.id,
                        DocumentPage.page_number == unit.page_numbers[0],
                    )
                )
                owner, original, base, keys = source_snapshot(
                    session, document, processing, page, unit.input_artifact_ids
                )
                original_key = document.storage_key
                metadata = dict(unit.execution_metadata)
            original_bytes = read_exact(storage, original_key, original.size_bytes, original.sha256)
            base_bytes = {
                a.id: read_exact(storage, keys[a.id], a.size_bytes, a.sha256) for a in base
            }

            def before_ocr():
                with factory.begin() as session:
                    _, authorized, _ = ExtractionCoordinator(session, settings)._authorized(
                        claim.unit_id, claim.token
                    )
                    authorized.output_counts = {"ocr_requests_started": 1}
                    session.flush()

            output = prepare_page(
                owner,
                original,
                original_bytes,
                base,
                base_bytes,
                claim.run_id,
                claim.unit_id,
                metadata["preparation_hash"],
                claim.profile,
                metadata["force_ocr"],
                provider_factory(),
                before_ocr,
            )
            for ref, data in output.blobs.values():
                storage.put(
                    artifact_key(owner.document_id, output.manifest.id, ref.id),
                    BytesIO(data),
                    len(data),
                    "image/png"
                    if ref.role == "OCR_INPUT_IMAGE"
                    else "text/plain"
                    if ref.role in ("OCR_TEXT", "NATIVE_POSITIONED_TEXT")
                    else "application/json",
                )
            output.usage.update(
                elapsed_ms=int((time.monotonic() - started) * 1000),
                python_cpu_ms=int((time.process_time() - cpu) * 1000),
                bytes_read=len(original_bytes) + sum(map(len, base_bytes.values())),
            )
            with factory.begin() as session:
                publish_preparation(session, settings, claim, output)
    except LeaseLost:
        return False
    except Exception as exc:
        code = (
            ErrorCode.SOURCE_UNAVAILABLE.value
            if isinstance(exc, TransientStorageError)
            else exc.code.value
            if isinstance(exc, OCRFailure)
            else ErrorCode.TIMEOUT.value
            if type(exc).__name__ == "SoftTimeLimitExceeded"
            else ErrorCode.INPUT.value
            if isinstance(exc, (ValueError, OSError, StorageError, UnicodeError))
            else ErrorCode.INTERNAL.value
        )
        try:
            with factory.begin() as session:
                coordinator = ExtractionCoordinator(session, settings)
                run, unit, _ = coordinator._authorized(claim.unit_id, claim.token)
                coordinator._settle_failure(run, unit, claim.profile, code)
        except LeaseLost:
            return False
        except Exception:
            raise RuntimeError(
                "Local execution state unavailable; lease recovery required"
            ) from None
    return True
