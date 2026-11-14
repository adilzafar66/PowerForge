"""Bound keyset cursors for scoped extraction reads."""

import base64
import json

from powerforge_api.exceptions import RevisionDocumentNotFound


def encode_cursor(scope, direction, values):
    encoded = json.dumps([scope, direction, *map(str, values)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def decode_cursor(cursor, scope, converters):
    try:
        payload = json.loads(
            base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        )
        if not isinstance(payload, list) or len(payload) < 2:
            raise ValueError
        owner, direction, *values = payload
        if (
            owner != scope
            or direction not in ("next", "previous")
            or len(values) != len(converters)
            or not all(isinstance(value, str) for value in values)
        ):
            raise ValueError
        return direction, tuple(
            convert(value) for convert, value in zip(converters, values, strict=True)
        )
    except (TypeError, ValueError, AttributeError, OverflowError):
        raise RevisionDocumentNotFound("Extraction cursor not found") from None
