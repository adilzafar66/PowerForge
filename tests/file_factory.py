"""Builders for small valid upload fixtures shared by the file and document API tests."""

from __future__ import annotations

import io
import struct
import zlib

from PIL import Image

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def png_bytes(size: tuple[int, int] = (16, 12), blue: int = 200) -> bytes:
    """A small solid PNG; vary ``blue`` to get different content (and SHA-256)."""
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, blue)).save(buf, "PNG")
    return buf.getvalue()


def jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 12), (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


def tiff_bytes(pages: int = 1) -> bytes:
    frames = [Image.new("RGB", (16, 12), (i * 40, 0, 0)) for i in range(pages)]
    buf = io.BytesIO()
    frames[0].save(buf, "TIFF", save_all=pages > 1, append_images=frames[1:])
    return buf.getvalue()


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def png_header_only(width: int, height: int) -> bytes:
    """A PNG with real dimensions in IHDR and one empty IDAT, so Pillow opens it
    (reads the header) but there is no pixel data to decode."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(b""))
    )
