"""Retain bounded provider output and persist its fenced audit metadata."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from io import BytesIO
from uuid import UUID

from sqlalchemy import Integer
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from powerforge_ai.extraction import ErrorCode, ProviderFailure
from powerforge_document_processing.storage.base import ObjectStorage, StorageError
from powerforge_document_processing.storage.s3 import S3ObjectStorage
from powerforge_extraction.attribute_admission import AttributeAdmission
from powerforge_extraction.stage_contracts import MAX_RESPONSE_BYTES
from powerforge_persistence.base import Base


def audit_prefix(days: int, stage: str = "ATTRIBUTE_EXTRACTION") -> str:
    prefix = "stage1" if stage == "EQUIPMENT_RECOGNITION" else "stage2"
    return f"{prefix}/{days}d/"


def response_audit_writer(
    settings, days: int, stage: str = "ATTRIBUTE_EXTRACTION"
) -> ObjectStorage:
    bucket = settings.extraction_response_audit_bucket
    access_key = settings.extraction_response_audit_write_access_key
    secret_key = settings.extraction_response_audit_write_secret_key
    if not all((bucket, access_key, secret_key)) or (
        bucket == settings.s3_bucket or access_key == settings.s3_access_key
    ):
        raise ProviderFailure(ErrorCode.AUDIT)
    storage = S3ObjectStorage(
        endpoint_url=settings.extraction_response_audit_endpoint_url or settings.s3_endpoint_url,
        public_endpoint_url=None,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        region=settings.s3_region,
        read_timeout=4,
        max_attempts=1,
        head_before_put=False,
    )
    try:
        storage.require_expiry(audit_prefix(days, stage), days)
    except StorageError:
        raise ProviderFailure(ErrorCode.AUDIT) from None
    return storage


class ResponseAudit(Base):
    __tablename__ = "extraction_response_audits"

    work_unit_id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID]
    document_page_id: Mapped[UUID]
    stage: Mapped[str] = mapped_column(server_default="ATTRIBUTE_EXTRACTION")
    request_hash: Mapped[str]
    attribute_reasoning_effort: Mapped[str | None]
    output_version: Mapped[str | None]
    overflow_indices: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default="{}")
    object_key: Mapped[str]
    output_sha256: Mapped[str]
    output_bytes: Mapped[int]
    expires_at: Mapped[datetime]
    received: Mapped[int | None]
    accepted: Mapped[int | None]
    quarantined: Mapped[int]
    rejections: Mapped[list[dict]] = mapped_column(JSONB)
    fatal_diagnostics: Mapped[list[dict]] = mapped_column(JSONB)


@dataclass(frozen=True)
class RetainedOutput:
    key: str
    digest: str
    size: int
    expires_at: datetime


def retain_output(
    storage: ObjectStorage,
    unit_id: UUID,
    days: int,
    raw: bytes,
    now: datetime,
    stage: str = "ATTRIBUTE_EXTRACTION",
):
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderFailure(ErrorCode.AUDIT)
    digest = sha256(raw).hexdigest()
    key = f"{audit_prefix(days, stage)}{unit_id}/{digest}.json"
    try:
        storage.put(key, BytesIO(raw), len(raw), "application/json")
    except StorageError:
        raise ProviderFailure(ErrorCode.AUDIT) from None
    return RetainedOutput(key, digest, len(raw), now + timedelta(days=days))


def record_audit(
    session,
    unit,
    wire,
    retained: RetainedOutput,
    admission: AttributeAdmission | None,
    request=None,
    diagnostics=(),
):
    from powerforge_extraction.stage_execution import publication_request_hash

    effort = unit.execution_metadata.get("attribute_reasoning_effort")
    session.add(
        ResponseAudit(
            work_unit_id=unit.id,
            run_id=unit.run_id,
            document_page_id=wire.page.owner.document_page_id,
            stage=unit.stage,
            request_hash=publication_request_hash(unit, wire, request),
            attribute_reasoning_effort=effort,
            output_version=unit.execution_metadata.get("attribute_output_version"),
            overflow_indices=list(admission.overflow_indices) if admission else [],
            object_key=retained.key,
            output_sha256=retained.digest,
            output_bytes=retained.size,
            expires_at=retained.expires_at,
            received=admission.received if admission else None,
            accepted=admission.accepted if admission else None,
            quarantined=len(admission.rejected) if admission else 0,
            rejections=[
                dict(
                    collection=item.collection,
                    index=item.index,
                    local_ref_sha256=sha256(item.local_ref.encode()).hexdigest()
                    if item.local_ref is not None
                    else None,
                    issues=[issue.model_dump(mode="json") for issue in item.issues],
                )
                for item in (admission.rejected if admission else ())
            ],
            fatal_diagnostics=[
                issue.model_dump(mode="json")
                for issue in (admission.fatal if admission else diagnostics)
            ],
        )
    )
    session.flush()
