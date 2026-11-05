"""The bounded page recognition -> attributes dependency, not a workflow engine."""

from collections.abc import Iterable


def unit_key(stage: str, page_number: int) -> str:
    return f"{stage}:page:{page_number:06d}"


def prerequisite(stage: str, page_number: int) -> str | None:
    if stage == "TABLE_INTERPRETATION":
        return unit_key("TABLE_RECONSTRUCTION", page_number)
    return (
        unit_key("EQUIPMENT_RECOGNITION", page_number) if stage == "ATTRIBUTE_EXTRACTION" else None
    )


def latest_units(units: Iterable) -> dict:
    latest = {}
    for unit in units:
        if (
            unit.unit_key not in latest
            or unit.attempt_number > latest[unit.unit_key].attempt_number
        ):
            latest[unit.unit_key] = unit
    return latest


def retryable_keys(units: Iterable, max_attempts: int) -> set[str]:
    latest = latest_units(units)
    eligible = {
        key
        for key, unit in latest.items()
        if unit.status in {"FAILED", "CANCELLED"} and unit.attempt_number < max_attempts
    }
    # Fixed two-stage plan: one pass excludes dependents with an exhausted upstream.
    return {
        key
        for key in eligible
        if not (parent := latest[key].execution_metadata.get("prerequisite_key"))
        or (parent in latest and (latest[parent].status == "COMPLETED" or parent in eligible))
    }
