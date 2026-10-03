"""Offline S3ObjectStorage behaviour: presigning is local, so no MinIO is needed."""

from __future__ import annotations

import io
import logging
from urllib.parse import parse_qs, urlsplit

import pytest

from powerforge_api.storage import StorageError
from powerforge_api.storage.s3 import S3ObjectStorage

SECRET = "super-secret-key-value"
KEY = "projects/p/documents/d/original.pdf"


def make_storage(
    endpoint: str = "http://minio:9000", public: str | None = "http://localhost:9000"
) -> S3ObjectStorage:
    return S3ObjectStorage(
        endpoint_url=endpoint,
        public_endpoint_url=public,
        access_key="access-id",
        secret_key=SECRET,
        bucket="bucket",
        region="us-east-1",
    )


def presign(storage: S3ObjectStorage, expires: int = 900) -> tuple[str, dict[str, list[str]]]:
    url = storage.create_download_url(KEY, "Plan é.pdf", "application/pdf", "attachment", expires)
    return url, parse_qs(urlsplit(url).query)


def test_url_uses_public_host_and_path_style() -> None:
    url, _ = presign(make_storage())
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == "http://localhost:9000"
    assert parts.path == f"/bucket/{KEY}"


def test_url_falls_back_to_internal_host_without_public_endpoint() -> None:
    url, _ = presign(make_storage(public=None))
    assert url.startswith("http://minio:9000/bucket/")


def test_url_is_sigv4_with_expiry_and_signed_host() -> None:
    _, query = presign(make_storage(), expires=900)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Expires"] == ["900"]
    assert query["X-Amz-SignedHeaders"] == ["host"]


def test_response_headers_are_part_of_the_signed_query() -> None:
    _, query = presign(make_storage())
    assert query["response-content-type"] == ["application/pdf"]
    disposition = query["response-content-disposition"][0]
    assert disposition.startswith("attachment; filename=")
    assert "filename*=UTF-8''Plan%20%C3%A9.pdf" in disposition


def test_url_never_contains_the_secret_key() -> None:
    url, _ = presign(make_storage())
    assert SECRET not in url


def test_expiry_is_bounded() -> None:
    storage = make_storage()
    for bad in (0, -5, 604_801):
        with pytest.raises(ValueError):
            storage.create_download_url(KEY, "a.pdf", "application/pdf", "attachment", bad)


def test_unsupported_disposition_is_rejected() -> None:
    with pytest.raises(ValueError):
        make_storage().create_download_url(
            KEY,
            "a.pdf",
            "application/pdf",
            "form-data",  # type: ignore[arg-type]
            60,
        )


def test_unreachable_endpoint_raises_generic_storage_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = make_storage(endpoint="http://127.0.0.1:1", public=None)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(StorageError) as caught:
            storage.exists(KEY)
        with pytest.raises(StorageError):
            storage.put(KEY, io.BytesIO(b"x"), 1, "application/pdf")
    message = str(caught.value)
    assert "127.0.0.1" not in message
    assert "Could not connect" not in message
    assert caught.value.__cause__ is None
    logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert "operation" in logged
    assert SECRET not in logged
