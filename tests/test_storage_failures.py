"""Classify S3 failures at the storage boundary without making network requests."""

from io import BytesIO
from unittest.mock import Mock

import pytest
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    IncompleteReadError,
    NoCredentialsError,
    ReadTimeoutError,
    ResponseStreamingError,
)
from botocore.response import StreamingBody

from powerforge_document_processing.storage import (
    ObjectNotFound,
    StorageError,
    TransientStorageError,
)
from powerforge_document_processing.storage.s3 import S3ObjectStorage


def service_error(code, status):
    return ClientError(
        {
            "Error": {"Code": code, "Message": "PRIVATE service details"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "GetObject",
    )


@pytest.fixture
def storage(monkeypatch):
    client = Mock()
    monkeypatch.setattr(S3ObjectStorage, "_build_client", lambda *args, **kwargs: client)
    return S3ObjectStorage(
        endpoint_url="http://storage.invalid",
        public_endpoint_url=None,
        access_key="fixture",
        secret_key="fixture",
        bucket="fixture",
        region="us-east-1",
    )


@pytest.mark.parametrize(
    "error,expected",
    [
        (EndpointConnectionError(endpoint_url="http://PRIVATE.invalid"), TransientStorageError),
        (ReadTimeoutError(endpoint_url="http://PRIVATE.invalid"), TransientStorageError),
        (service_error("ServiceUnavailable", 503), TransientStorageError),
        (service_error("InternalError", 500), TransientStorageError),
        (service_error("SlowDown", 429), TransientStorageError),
        (service_error("RequestTimeout", 400), TransientStorageError),
        (service_error("AccessDenied", 403), StorageError),
        (NoCredentialsError(), StorageError),
        (service_error("NoSuchKey", 404), ObjectNotFound),
    ],
)
def test_get_classifies_transient_and_permanent_failures(storage, error, expected, caplog):
    storage._client.get_object.side_effect = error
    with pytest.raises(expected) as caught:
        storage.get("source.txt")
    assert type(caught.value) is expected
    assert "PRIVATE" not in str(caught.value)
    assert "PRIVATE" not in caplog.text
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    "error",
    [
        ReadTimeoutError(endpoint_url="http://PRIVATE.invalid"),
        IncompleteReadError(actual_bytes=2, expected_bytes=3),
        ResponseStreamingError(error=OSError("PRIVATE stream details")),
        ConnectionResetError("PRIVATE stream details"),
    ],
)
def test_streaming_transport_failure_uses_the_same_storage_contract(storage, error):
    body = Mock()
    body.read.side_effect = error
    storage._client.get_object.return_value = {"Body": body}
    stream = storage.get("source.txt")
    try:
        with pytest.raises(TransientStorageError, match="Object storage read failed") as caught:
            stream.read(1024)
        assert caught.value.__suppress_context__
        assert "PRIVATE" not in str(caught.value)
    finally:
        stream.close()
    body.read.assert_called_once_with(1024)
    body.close.assert_called_once_with()


def test_storage_stream_preserves_bounded_and_full_reads(storage):
    body = BytesIO(b"source bytes")
    storage._client.get_object.return_value = {"Body": body}
    stream = storage.get("source.txt")
    assert stream.read(6) == b"source"
    assert stream.read() == b" bytes"
    stream.close()
    assert body.closed


@pytest.mark.parametrize("explicit_size", [False, True])
def test_full_read_retains_s3_content_length_verification(storage, explicit_size):
    body = StreamingBody(BytesIO(b"short"), content_length=10)
    storage._client.get_object.return_value = {"Body": body}
    stream = storage.get("source.txt")
    try:
        with pytest.raises(TransientStorageError):
            stream.read(-1) if explicit_size else stream.read()
    finally:
        stream.close()
