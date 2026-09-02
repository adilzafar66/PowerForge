class RuleRegistry:
    """Named deterministic rules. Empty in Phase 0; Phase 10 adds executions."""

    def __init__(self) -> None:
        self._names: tuple[str, ...] = ()

    def names(self) -> tuple[str, ...]:
        return self._names
