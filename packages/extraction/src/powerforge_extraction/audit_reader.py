"""Shared operator-only retrieval with integrity verification and journaling."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from powerforge_document_processing.storage.base import ObjectNotFound, ObjectStorage
from powerforge_extraction.response_audit import ResponseAudit


class AuditReadError(ValueError):
    """A safe, bounded reason for denying an audit retrieval."""


def read_audit(
    engine, storage: ObjectStorage, work_unit_id: UUID, *, now: datetime | None = None
) -> bytes:
    with Session(engine) as session, session.begin():
        audit = session.get(ResponseAudit, work_unit_id)
        if audit is None:
            raise AuditReadError("not_captured")
        if audit.expires_at <= (now or datetime.now(UTC)):
            raise AuditReadError("expired")
        try:
            stream = storage.get(audit.object_key)
        except ObjectNotFound:
            raise AuditReadError("object_missing") from None
        try:
            body = stream.read(audit.output_bytes + 1)
        finally:
            stream.close()
        if len(body) != audit.output_bytes or sha256(body).hexdigest() != audit.output_sha256:
            raise AuditReadError("integrity_failed")
        session.execute(
            text("INSERT INTO extraction_response_audit_reads(work_unit_id) VALUES (:id)"),
            {"id": work_unit_id},
        )
    return body
