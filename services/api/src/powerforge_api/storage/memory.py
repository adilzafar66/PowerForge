"""In-memory ObjectStorage fake for tests, with injectable failures and call recording."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO
from urllib.parse import quote, urlencode

from powerforge_api.storage.base import (
    DispositionType,
    ObjectAlreadyExists,
    ObjectNotFound,
    ReadableStream,
    StorageError,
)
from powerforge_api.storage.disposition import build_content_disposition

OPERATIONS = ("ensure_bucket", "put", "get", "exists", "delete", "create_download_url")


@dataclass(frozen=True)
class StoredObject:
    data: bytes
    content_type: str


class InMemoryObjectStorage:
    def __init__(self, bucket: str = "memory") -> None:
        self.bucket = bucket
        self.objects: dict[str, StoredObject] = {}
        self.calls: list[tuple[str, str | None]] = []
        self._failures: dict[str, Exception] = {}

    def fail_on(self, operation: str, error: Exception | None = None) -> None:
        if operation not in OPERATIONS:
            raise ValueError(f"Unknown operation: {operation}")
        self._failures[operation] = error or StorageError("Injected storage failure")

    def clear_failures(self) -> None:
        self._failures.clear()

    def calls_for(self, operation: str) -> list[str | None]:
        return [key for name, key in self.calls if name == operation]

    def _enter(self, operation: str, key: str | None = None) -> None:
        self.calls.append((operation, key))
        failure = self._failures.get(operation)
        if failure is not None:
            raise failure

    def ensure_bucket(self) -> None:
        self._enter("ensure_bucket")

    def put(self, key: str, fileobj: BinaryIO, size: int, content_type: str) -> None:
        self._enter("put", key)
        if key in self.objects:
            raise ObjectAlreadyExists("Object already exists")
        data = fileobj.read(size + 1)
        if len(data) != size:
            raise StorageError("Object size does not match the declared size")
        self.objects[key] = StoredObject(data=data, content_type=content_type)

    def get(self, key: str) -> ReadableStream:
        self._enter("get", key)
        stored = self.objects.get(key)
        if stored is None:
            raise ObjectNotFound("Object not found")
        return BytesIO(stored.data)

    def exists(self, key: str) -> bool:
        self._enter("exists", key)
        return key in self.objects

    def delete(self, key: str) -> None:
        self._enter("delete", key)
        self.objects.pop(key, None)

    def create_download_url(
        self,
        key: str,
        filename: str,
        content_type: str,
        disposition: DispositionType,
        expires_seconds: int,
    ) -> str:
        self._enter("create_download_url", key)
        if expires_seconds <= 0:
            raise ValueError("expires_seconds must be positive")
        query = urlencode(
            {
                "expires": expires_seconds,
                "response-content-type": content_type,
                "response-content-disposition": build_content_disposition(filename, disposition),
            },
            quote_via=quote,
        )
        return f"memory://{self.bucket}/{quote(key)}?{query}"
