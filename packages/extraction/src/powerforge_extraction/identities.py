"""Canonical identities for new engineering resources; legacy probe hashing is unchanged."""

import hashlib
import json


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def identity_hash(value: object) -> str:
    return content_hash(canonical_json(value))
