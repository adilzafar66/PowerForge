"""ObjectStorage contract tests: the in-memory fake and (integration) real MinIO/S3.

The S3 cases need RUN_INTEGRATION=1 and a reachable MinIO. When MinIO is unreachable they
skip locally and fail under CI, so a broken CI service cannot hide behind a silent skip.
"""

from __future__ import annotations

import io
import uuid

import httpx
import pytest
from botocore.exceptions import ClientError

from powerforge_api.storage import (
    InMemoryObjectStorage,
    ObjectAlreadyExists,
    ObjectNotFound,
    ObjectStorage,
    StorageError,
)
from powerforge_api.storage.s3 import S3ObjectStorage
from powerforge_shared.config import get_settings

PDF = b"%PDF-1.7\nbody"


def new_key(extension: str = ".pdf") -> str:
    return f"projects/{uuid.uuid4()}/documents/{uuid.uuid4()}/original{extension}"


@pytest.fixture(params=["memory", pytest.param("s3", marks=pytest.mark.integration)])
def storage(request: pytest.FixtureRequest) -> ObjectStorage:
    if request.param == "memory":
        return InMemoryObjectStorage()
    return request.getfixturevalue("s3_scratch_storage")


def read_all(storage: ObjectStorage, key: str) -> bytes:
    stream = storage.get(key)
    try:
        return stream.read()
    finally:
        stream.close()


def put(storage: ObjectStorage, key: str, data: bytes = PDF) -> None:
    storage.put(key, io.BytesIO(data), len(data), "application/pdf")


class TestContract:
    def test_ensure_bucket_is_idempotent(self, storage: ObjectStorage) -> None:
        storage.ensure_bucket()
        storage.ensure_bucket()

    def test_put_get_round_trip(self, storage: ObjectStorage) -> None:
        key = new_key()
        put(storage, key)
        assert read_all(storage, key) == PDF

    def test_exists(self, storage: ObjectStorage) -> None:
        key = new_key()
        assert storage.exists(key) is False
        put(storage, key)
        assert storage.exists(key) is True

    def test_get_missing_raises_not_found(self, storage: ObjectStorage) -> None:
        with pytest.raises(ObjectNotFound):
            storage.get(new_key())

    def test_delete_removes_object(self, storage: ObjectStorage) -> None:
        key = new_key()
        put(storage, key)
        storage.delete(key)
        assert storage.exists(key) is False

    def test_delete_missing_is_a_no_op(self, storage: ObjectStorage) -> None:
        storage.delete(new_key())

    def test_put_to_existing_key_is_refused_and_original_preserved(
        self, storage: ObjectStorage
    ) -> None:
        key = new_key()
        put(storage, key, b"original bytes")
        with pytest.raises(ObjectAlreadyExists):
            put(storage, key, b"replacement bytes")
        assert read_all(storage, key) == b"original bytes"

    def test_put_reads_from_current_position(self, storage: ObjectStorage) -> None:
        key = new_key()
        buffer = io.BytesIO(b"skip-me" + PDF)
        buffer.seek(len(b"skip-me"))
        storage.put(key, buffer, len(PDF), "application/pdf")
        assert read_all(storage, key) == PDF

    def test_download_url_is_issued_for_a_key(self, storage: ObjectStorage) -> None:
        key = new_key()
        url = storage.create_download_url(key, "Plan.pdf", "application/pdf", "attachment", 900)
        assert key in url
        assert "900" in url


class TestInMemoryFake:
    def test_records_calls_in_order(self) -> None:
        fake = InMemoryObjectStorage()
        key = new_key()
        put(fake, key)
        fake.exists(key)
        fake.delete(key)
        assert [name for name, _ in fake.calls] == ["put", "exists", "delete"]
        assert fake.calls_for("put") == [key]

    def test_no_copy_can_be_asserted(self) -> None:
        fake = InMemoryObjectStorage()
        assert fake.calls_for("put") == []

    @pytest.mark.parametrize(
        "operation", ["ensure_bucket", "put", "get", "exists", "delete", "create_download_url"]
    )
    def test_injected_failure_per_operation(self, operation: str) -> None:
        fake = InMemoryObjectStorage()
        key = new_key()
        put(fake, key)
        fake.fail_on(operation)
        calls = {
            "ensure_bucket": lambda: fake.ensure_bucket(),
            "put": lambda: put(fake, new_key()),
            "get": lambda: fake.get(key),
            "exists": lambda: fake.exists(key),
            "delete": lambda: fake.delete(key),
            "create_download_url": lambda: fake.create_download_url(
                key, "a.pdf", "application/pdf", "attachment", 60
            ),
        }
        with pytest.raises(StorageError):
            calls[operation]()
        fake.clear_failures()
        calls["exists"]()

    def test_failed_put_stores_nothing(self) -> None:
        fake = InMemoryObjectStorage()
        key = new_key()
        fake.fail_on("put")
        with pytest.raises(StorageError):
            put(fake, key)
        assert key not in fake.objects

    def test_custom_failure_is_raised(self) -> None:
        fake = InMemoryObjectStorage()
        fake.fail_on("delete", RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            fake.delete(new_key())

    def test_unknown_operation_rejected(self) -> None:
        with pytest.raises(ValueError):
            InMemoryObjectStorage().fail_on("explode")

    def test_size_mismatch_is_rejected(self) -> None:
        fake = InMemoryObjectStorage()
        with pytest.raises(StorageError):
            fake.put(new_key(), io.BytesIO(b"abc"), 5, "application/pdf")
        with pytest.raises(StorageError):
            fake.put(new_key(), io.BytesIO(b"abcdef"), 5, "application/pdf")

    def test_download_url_embeds_expiry_type_and_disposition(self) -> None:
        url = InMemoryObjectStorage().create_download_url(
            "k/original.pdf", "Plan é.pdf", "application/pdf", "inline", 120
        )
        assert "expires=120" in url
        assert "response-content-type=application%2Fpdf" in url
        assert "inline" in url
        assert "filename%2A%3DUTF-8" in url

    def test_non_positive_expiry_rejected(self) -> None:
        with pytest.raises(ValueError):
            InMemoryObjectStorage().create_download_url(
                "k", "a.pdf", "application/pdf", "attachment", 0
            )


@pytest.mark.integration
class TestS3Specific:
    def test_conditional_put_header_is_enforced_by_the_server(
        self, s3_scratch_storage: S3ObjectStorage
    ) -> None:
        """Bypass the exists() pre-check to prove the server itself refuses overwrites."""
        key = new_key()
        put(s3_scratch_storage, key, b"first")
        with pytest.raises(ClientError) as caught:
            s3_scratch_storage._client.put_object(
                Bucket=s3_scratch_storage.bucket,
                Key=key,
                Body=b"second",
                ContentLength=6,
                IfNoneMatch="*",
            )
        assert caught.value.response["ResponseMetadata"]["HTTPStatusCode"] == 412
        assert read_all(s3_scratch_storage, key) == b"first"

    def test_content_type_is_stored(self, s3_scratch_storage: S3ObjectStorage) -> None:
        key = new_key()
        s3_scratch_storage.put(key, io.BytesIO(b"png"), 3, "image/png")
        head = s3_scratch_storage._client.head_object(Bucket=s3_scratch_storage.bucket, Key=key)
        assert head["ContentType"] == "image/png"

    def test_presigned_url_serves_bytes_with_signed_headers(
        self, s3_scratch_storage: S3ObjectStorage
    ) -> None:
        key = new_key()
        put(s3_scratch_storage, key)
        url = s3_scratch_storage.create_download_url(
            key, "Plan é.pdf", "application/pdf", "attachment", 60
        )
        response = httpx.get(url)
        assert response.status_code == 200
        assert response.content == PDF
        assert response.headers["content-type"] == "application/pdf"
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment;")
        assert "filename*=UTF-8''Plan%20%C3%A9.pdf" in disposition

    def test_tampering_with_a_signed_header_is_rejected(
        self, s3_scratch_storage: S3ObjectStorage
    ) -> None:
        key = new_key()
        put(s3_scratch_storage, key)
        url = s3_scratch_storage.create_download_url(
            key, "Plan.pdf", "application/pdf", "attachment", 60
        )
        tampered = url.replace("attachment", "inline")
        assert httpx.get(tampered).status_code == 403

    def test_object_is_not_anonymously_readable(self, s3_scratch_storage: S3ObjectStorage) -> None:
        key = new_key()
        put(s3_scratch_storage, key)
        endpoint = get_settings().s3_public_endpoint().rstrip("/")
        response = httpx.get(f"{endpoint}/{s3_scratch_storage.bucket}/{key}")
        assert response.status_code == 403
