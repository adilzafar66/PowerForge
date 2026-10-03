"""Object-storage port. Services depend on this module only, never on boto3."""

from __future__ import annotations

from typing import BinaryIO, Literal, Protocol

DispositionType = Literal["attachment", "inline"]


class StorageError(Exception):
    """Storage failure. The message is generic and never carries SDK text."""


class ObjectAlreadyExists(StorageError):
    """put() refused to overwrite an existing key."""


class ObjectNotFound(StorageError):
    """The requested key does not exist."""


class ReadableStream(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...

    def close(self) -> None: ...


class ObjectStorage(Protocol):
    def ensure_bucket(self) -> None:
        """Create the bucket if missing. Idempotent. Never sets a public policy."""

    def put(self, key: str, fileobj: BinaryIO, size: int, content_type: str) -> None:
        """Store `size` bytes read from the current position of `fileobj`.

        Raises ObjectAlreadyExists instead of overwriting an existing key.
        """

    def get(self, key: str) -> ReadableStream:
        """Return a readable stream. Raises ObjectNotFound for a missing key."""

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Delete a key. Deleting a missing key is a no-op."""

    def create_download_url(
        self,
        key: str,
        filename: str,
        content_type: str,
        disposition: DispositionType,
        expires_seconds: int,
    ) -> str:
        """Return a short-lived URL a browser can use to fetch the object."""
