"""boto3-backed ObjectStorage for MinIO and other S3-compatible services.

This is the only module in the API that imports boto3.
"""

from __future__ import annotations

import logging
from typing import BinaryIO

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from powerforge_api.storage.base import (
    DispositionType,
    ObjectAlreadyExists,
    ObjectNotFound,
    ReadableStream,
    StorageError,
)
from powerforge_api.storage.disposition import build_content_disposition

logger = logging.getLogger(__name__)

_MISSING_BUCKET_CODES = {"404", "NoSuchBucket", "NotFound"}
_MISSING_KEY_CODES = {"404", "NoSuchKey", "NotFound"}
_PRECONDITION_CODES = {"PreconditionFailed", "ConditionalRequestConflict"}
_MAX_PRESIGN_SECONDS = 604_800


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        return str(exc.response.get("Error", {}).get("Code", "unknown"))
    return type(exc).__name__


def _http_status(exc: Exception) -> int | None:
    if isinstance(exc, ClientError):
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return int(status) if status is not None else None
    return None


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        self.bucket = bucket
        self._region = region
        self._client = self._build_client(
            endpoint_url, access_key, secret_key, region, read_timeout=60, max_attempts=2
        )
        # Presigning is an offline computation. A second client is needed only because
        # SigV4 signs the Host header, so the URL must be signed for the browser's host.
        self._presign_client = self._build_client(
            public_endpoint_url or endpoint_url,
            access_key,
            secret_key,
            region,
            read_timeout=5,
            max_attempts=1,
        )

    @staticmethod
    def _build_client(
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str,
        *,
        read_timeout: int,
        max_attempts: int,
    ) -> BaseClient:
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                # boto3 >= 1.36 adds default checksums that S3-compatible servers may reject.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                connect_timeout=2,
                read_timeout=read_timeout,
                retries={"max_attempts": max_attempts, "mode": "standard"},
            ),
        )

    def _failure(self, operation: str, exc: Exception, key: str | None = None) -> StorageError:
        logger.error(
            "object storage operation failed",
            extra={"operation": operation, "error_code": _error_code(exc), "storage_key": key},
        )
        return StorageError(f"Object storage {operation} failed")

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return
        except (ClientError, BotoCoreError) as exc:
            if not (isinstance(exc, ClientError) and _error_code(exc) in _MISSING_BUCKET_CODES):
                raise self._failure("ensure_bucket", exc) from None
        try:
            kwargs: dict[str, object] = {"Bucket": self.bucket}
            if self._region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
            self._client.create_bucket(**kwargs)
        except (ClientError, BotoCoreError) as exc:
            if _error_code(exc) == "BucketAlreadyOwnedByYou":
                return
            raise self._failure("ensure_bucket", exc) from None

    def put(self, key: str, fileobj: BinaryIO, size: int, content_type: str) -> None:
        if self.exists(key):
            raise ObjectAlreadyExists("Object already exists")
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=fileobj,
                ContentLength=size,
                ContentType=content_type,
                IfNoneMatch="*",
            )
        except (ClientError, BotoCoreError) as exc:
            if _http_status(exc) == 412 or _error_code(exc) in _PRECONDITION_CODES:
                raise ObjectAlreadyExists("Object already exists") from None
            raise self._failure("put", exc, key) from None

    def get(self, key: str) -> ReadableStream:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            if isinstance(exc, ClientError) and _error_code(exc) in _MISSING_KEY_CODES:
                raise ObjectNotFound("Object not found") from None
            raise self._failure("get", exc, key) from None
        return response["Body"]

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            if isinstance(exc, ClientError) and (
                _error_code(exc) in _MISSING_KEY_CODES or _http_status(exc) == 404
            ):
                return False
            raise self._failure("exists", exc, key) from None
        return True

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            if isinstance(exc, ClientError) and _error_code(exc) in _MISSING_KEY_CODES:
                return
            raise self._failure("delete", exc, key) from None

    def create_download_url(
        self,
        key: str,
        filename: str,
        content_type: str,
        disposition: DispositionType,
        expires_seconds: int,
    ) -> str:
        if not 1 <= expires_seconds <= _MAX_PRESIGN_SECONDS:
            raise ValueError("expires_seconds must be between 1 and 604800")
        content_disposition = build_content_disposition(filename, disposition)
        try:
            return self._presign_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentDisposition": content_disposition,
                    "ResponseContentType": content_type,
                },
                ExpiresIn=expires_seconds,
                HttpMethod="GET",
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._failure("create_download_url", exc, key) from None
