"""Streaming upload ingestion: bound the size, hash, and spool to a temporary file.

Runs before any database or storage work. Never logs and never sees the browser
content type. Exception messages are static so filenames and bytes cannot leak.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from types import TracebackType
from typing import BinaryIO, Self

from powerforge_api.exceptions import FileTooLarge, InvalidFileContent, UnsupportedDocumentType
from powerforge_document_model import (
    InvalidFilename,
    format_for_extension,
    normalize_extension,
    sanitize_filename,
)

DEFAULT_SPOOL_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class IngestedUpload:
    """A fully read upload. The caller owns ``file`` and must close it."""

    file: BinaryIO
    size: int
    sha256: str
    filename: str
    extension: str

    def close(self) -> None:
        self.file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def ingest_upload(
    fileobj: BinaryIO,
    filename: str,
    max_bytes: int,
    *,
    spool_max_bytes: int = DEFAULT_SPOOL_MAX_BYTES,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> IngestedUpload:
    """Read ``fileobj`` once, returning size, SHA-256 and a rewound spooled copy.

    Memory use is bounded by ``spool_max_bytes`` plus one chunk, not by file size.
    Reading stops as soon as ``max_bytes`` is exceeded.
    """
    try:
        clean_name = sanitize_filename(filename)
    except InvalidFilename:
        raise InvalidFileContent("Filename is not usable") from None

    extension = normalize_extension(clean_name)
    if format_for_extension(extension) is None:
        raise UnsupportedDocumentType(
            "Unsupported file type; supported types are PDF, PNG, JPEG and TIFF"
        )

    digest = hashlib.sha256()
    size = 0
    spool = SpooledTemporaryFile(max_size=spool_max_bytes)  # noqa: SIM115
    try:
        while chunk := fileobj.read(chunk_size):
            size += len(chunk)
            if size > max_bytes:
                raise FileTooLarge("File exceeds the maximum upload size")
            digest.update(chunk)
            spool.write(chunk)
        if size == 0:
            raise InvalidFileContent("File is empty")
        spool.seek(0)
    except BaseException:
        spool.close()
        raise

    return IngestedUpload(
        file=spool,
        size=size,
        sha256=digest.hexdigest(),
        filename=clean_name,
        extension=extension,
    )
