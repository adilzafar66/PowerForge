"""Safe Content-Disposition header values (pure; no boto3)."""

from __future__ import annotations

from urllib.parse import quote

from powerforge_api.storage.base import DispositionType

_ALLOWED_DISPOSITIONS = ("attachment", "inline")
_FALLBACK_FILENAME = "download"


def _strip_controls(value: str) -> str:
    return "".join(ch for ch in value if ch.isprintable() or ch == " ")


def _ascii_fallback(value: str) -> str:
    out: list[str] = []
    for ch in value:
        if ch in {'"', "\\"}:
            out.append("\\" + ch)
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def build_content_disposition(filename: str, disposition: DispositionType = "attachment") -> str:
    """Build `attachment; filename="..."; filename*=UTF-8''...`.

    The quoted ASCII `filename=` is a fallback for old clients; `filename*=` carries
    the exact name percent-encoded (RFC 5987/6266). Control characters (including
    CR and LF) are removed so a filename can never inject headers.
    """
    if disposition not in _ALLOWED_DISPOSITIONS:
        raise ValueError(f"Unsupported disposition: {disposition!r}")
    cleaned = _strip_controls(filename).strip() or _FALLBACK_FILENAME
    encoded = quote(cleaned.encode("utf-8", errors="replace"), safe="")
    return f"{disposition}; filename=\"{_ascii_fallback(cleaned)}\"; filename*=UTF-8''{encoded}"
