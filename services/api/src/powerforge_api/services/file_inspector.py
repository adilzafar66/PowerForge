"""Content inspection for uploaded documents (spec section 13, step 4 to 6).

This is the only module in the API allowed to import Pillow. It validates
structure and header only; pixel decoding is deferred to Phase 3.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

from powerforge_api.exceptions import InvalidFileContent, UnsupportedDocumentType
from powerforge_document_model import (
    FileFormat,
    format_for_extension,
    looks_like_pdf,
    mime_type_for,
)

# Pillow's built-in bomb guard raises above 2x this value (about 178M pixels by
# default), which would reject legitimate engineering scans under our own,
# larger MAX_IMAGE_PIXELS. FileInspector enforces the cap from the header
# instead, immediately after open and before verify() or any decode.
Image.MAX_IMAGE_PIXELS = None

_PDF_HEAD_BYTES = 1024
_PILLOW_FORMATS = {
    "PNG": FileFormat.PNG,
    "JPEG": FileFormat.JPEG,
    "TIFF": FileFormat.TIFF,
}


@dataclass(frozen=True)
class InspectionResult:
    file_format: FileFormat
    mime_type: str


class FileInspector:
    def __init__(self, max_image_pixels: int) -> None:
        self._max_image_pixels = max_image_pixels

    def inspect(self, fileobj: BinaryIO, extension: str) -> InspectionResult:
        """Validate content against the extension and derive the MIME type.

        The file position is reset to 0 on every exit path and the file is never closed.
        """
        expected = format_for_extension(extension)
        if expected is None:
            raise UnsupportedDocumentType(
                "Unsupported file type; supported types are PDF, PNG, JPEG and TIFF"
            )
        try:
            fileobj.seek(0)
            if expected is FileFormat.PDF:
                self._check_pdf(fileobj)
            else:
                self._check_image(fileobj, expected)
        finally:
            fileobj.seek(0)
        return InspectionResult(file_format=expected, mime_type=mime_type_for(expected))

    @staticmethod
    def _check_pdf(fileobj: BinaryIO) -> None:
        if not looks_like_pdf(fileobj.read(_PDF_HEAD_BYTES)):
            raise InvalidFileContent("File content is not a valid PDF")

    def _check_image(self, fileobj: BinaryIO, expected: FileFormat) -> None:
        try:
            with Image.open(fileobj, formats=list(_PILLOW_FORMATS)) as image:
                detected = _PILLOW_FORMATS.get(image.format or "")
                width, height = image.size
                if detected is None:
                    raise InvalidFileContent("File content is not a supported image")
                if width * height > self._max_image_pixels:
                    raise InvalidFileContent("Image dimensions exceed the allowed maximum")
                image.verify()
        except InvalidFileContent:
            raise
        except (
            UnidentifiedImageError,
            Image.DecompressionBombError,
            SyntaxError,
            OSError,
            ValueError,
            EOFError,
            struct.error,
        ):
            raise InvalidFileContent("File content is not a valid image") from None
        if detected is not expected:
            raise InvalidFileContent("File content does not match the file extension")
