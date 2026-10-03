from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_STANDARD_RECORD_ATTRIBUTES = frozenset(
    logging.LogRecord("", logging.INFO, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}

_SENSITIVE_KEY_FRAGMENTS = (
    "secret",
    "password",
    "token",
    "credential",
    "signature",
    "authorization",
    "access_key",
    "url",
)

REDACTED = "[redacted]"


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per record, including `extra=` fields.

    Extra fields whose top-level key looks like a secret or URL are redacted so
    signed URLs and credentials cannot leak into logs by accident.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRIBUTES or key in payload:
                continue
            payload[key] = REDACTED if _is_sensitive(key) else value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
