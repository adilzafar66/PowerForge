import json
import logging
import sys

import pytest

from powerforge_shared.logging import REDACTED, JsonFormatter


def render(**extra: object) -> dict[str, object]:
    record = logging.LogRecord(
        name="powerforge.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_base_fields_unchanged() -> None:
    payload = render()
    assert payload["level"] == "INFO"
    assert payload["logger"] == "powerforge.test"
    assert payload["message"] == "hello world"
    assert "ts" in payload
    assert set(payload) == {"ts", "level", "logger", "message"}


def test_extra_fields_are_included() -> None:
    payload = render(project_id="p-1", storage_key="projects/p/documents/d/original.pdf", size=10)
    assert payload["project_id"] == "p-1"
    assert payload["storage_key"] == "projects/p/documents/d/original.pdf"
    assert payload["size"] == 10


def test_non_serializable_extra_is_stringified() -> None:
    payload = render(thing=object())
    assert isinstance(payload["thing"], str)


@pytest.mark.parametrize(
    "key",
    [
        "s3_secret_key",
        "password",
        "api_token",
        "credentials",
        "signature",
        "Authorization",
        "access_key",
        "download_url",
        "presigned_url",
    ],
)
def test_sensitive_keys_are_redacted(key: str) -> None:
    payload = render(**{key: "super-sensitive-value"})
    assert payload[key] == REDACTED
    assert "super-sensitive-value" not in json.dumps(payload)


def test_exception_info_is_included() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "n", logging.ERROR, __file__, 1, "failed", None, exc_info=sys.exc_info()
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exc_info"]
