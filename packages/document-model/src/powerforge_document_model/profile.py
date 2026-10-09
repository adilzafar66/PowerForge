"""Processing profile identity. Hash only fields that change derived pixels."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

PROCESSOR_VERSION = "1"
PROFILE_VERSION = "engineering-default-v1"

_MATERIAL_FIELDS = (
    "target_dpi",
    "max_long_edge_px",
    "max_total_pixels",
    "thumbnail_long_edge_px",
    "analysis_format",
    "thumbnail_format",
    "normalize_orientation",
)


def hash_material_fields(fields: Mapping[str, Any]) -> str:
    """SHA-256 of canonical JSON. Key order does not affect the digest."""
    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ProcessingProfile:
    """One processing configuration. Versions label it; the hash identifies output."""

    target_dpi: int = 200
    max_long_edge_px: int = 8000
    max_total_pixels: int = 50_000_000
    thumbnail_long_edge_px: int = 800
    analysis_format: str = "png"
    thumbnail_format: str = "webp"
    normalize_orientation: bool = True
    processor_version: str = PROCESSOR_VERSION
    profile_version: str = PROFILE_VERSION

    def material_fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _MATERIAL_FIELDS}

    @property
    def profile_hash(self) -> str:
        return hash_material_fields(self.material_fields())


DEFAULT_PROFILE = ProcessingProfile()
