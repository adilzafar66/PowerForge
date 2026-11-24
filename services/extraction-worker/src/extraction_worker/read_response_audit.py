"""Operator export of an exact, still-retained Stage 2 audit artifact."""

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from powerforge_document_processing.storage.base import ObjectStorage, StorageError
from powerforge_document_processing.storage.s3 import S3ObjectStorage
from powerforge_extraction.audit_reader import read_audit as read_verified_audit
from powerforge_shared.config import get_settings


def read_audit(engine, storage: ObjectStorage, work_unit_id: UUID) -> bytes:
    return read_verified_audit(engine, storage, work_unit_id, now=datetime.now(UTC))


def read_operator_audit(settings, work_unit_id):
    endpoint = settings.extraction_response_audit_endpoint_url or settings.s3_endpoint_url
    if not settings.extraction_response_audit_bucket:
        raise ValueError("Missing audit bucket")
    storage = S3ObjectStorage(
        endpoint_url=endpoint,
        public_endpoint_url=None,
        access_key=os.environ["EXTRACTION_RESPONSE_AUDIT_READ_ACCESS_KEY"],
        secret_key=os.environ["EXTRACTION_RESPONSE_AUDIT_READ_SECRET_KEY"],
        bucket=settings.extraction_response_audit_bucket,
        region=settings.s3_region,
    )
    engine = create_engine(os.environ["EXTRACTION_RESPONSE_AUDIT_DATABASE_URL"])
    try:
        return read_audit(engine, storage, work_unit_id)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_unit_id", type=UUID)
    parser.add_argument("output", type=Path, help="New local file owned by the operator")
    args = parser.parse_args()
    settings = get_settings()
    try:
        body = read_operator_audit(settings, args.work_unit_id)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(body)
    except (KeyError, OSError, ValueError, SQLAlchemyError, StorageError):
        parser.exit(
            1, "Audit export failed. Check operator access, expiry, integrity and output path.\n"
        )


if __name__ == "__main__":
    main()
