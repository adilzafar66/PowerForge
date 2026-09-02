"""Deterministic validation.

Phase 10 will register rules here. Phase 0 only establishes the module boundary.
This package must not call AI providers.
"""

from powerforge_validation.registry import RuleRegistry

__all__ = ["RuleRegistry"]
