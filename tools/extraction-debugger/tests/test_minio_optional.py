"""Opt-in test against an authorized, still-retained audit test fixture."""

import os
from uuid import UUID

import pytest
from sqlalchemy import create_engine

from powerforge_document_processing.storage.s3 import S3ObjectStorage
from powerforge_extraction.audit_reader import read_audit
from powerforge_shared.config import get_settings


def test_configured_minio_retrieval():
    fixture = os.environ.get("EXTRACTION_DEBUGGER_TEST_ATTEMPT")
    if not fixture:
        pytest.skip("No explicitly selected MinIO audit test fixture")
    engine = create_engine(
        os.environ["EXTRACTION_RESPONSE_AUDIT_DATABASE_URL"], hide_parameters=True
    )
    storage = S3ObjectStorage(
        endpoint_url=os.environ["EXTRACTION_RESPONSE_AUDIT_ENDPOINT_URL"],
        public_endpoint_url=None,
        access_key=os.environ["EXTRACTION_RESPONSE_AUDIT_READ_ACCESS_KEY"],
        secret_key=os.environ["EXTRACTION_RESPONSE_AUDIT_READ_SECRET_KEY"],
        bucket=os.environ["EXTRACTION_RESPONSE_AUDIT_BUCKET"],
        region=get_settings().s3_region,
    )
    try:
        assert read_audit(engine, storage, UUID(fixture))
    finally:
        engine.dispose()
