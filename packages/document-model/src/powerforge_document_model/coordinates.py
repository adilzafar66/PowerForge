"""Normalized page coordinates for a future evidence box.

The box is on the upright logical page, origin at the top left. It is not
stored in Phase 3 and is not an evidence row.
"""

from __future__ import annotations

from dataclasses import dataclass

_FIELDS = ("x", "y", "width", "height")


@dataclass(frozen=True, slots=True)
class NormalizedBox:
    """``x``, ``y``, ``width``, and ``height`` each in ``0.0``–``1.0``."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name in _FIELDS:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
