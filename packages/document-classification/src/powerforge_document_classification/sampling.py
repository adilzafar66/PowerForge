"""Deterministic page selection. No randomness."""

from __future__ import annotations


def sample_page_numbers(page_count: int, sample_count: int) -> tuple[int, ...]:
    """Return one-based page numbers to send for a document-level sample.

    When the document is no larger than the sample, every page is returned.
    Otherwise the result has ``sample_count`` pages. Integer linspace over the
    page indexes includes the first and last page when ``sample_count`` is at
    least 2. A rounding collision is filled from the lowest unused page number.
    """
    if page_count < 1:
        raise ValueError("page_count must be >= 1")
    if sample_count < 1:
        raise ValueError("sample_count must be >= 1")
    if page_count <= sample_count:
        return tuple(range(1, page_count + 1))
    if sample_count == 1:
        return (1,)

    span = page_count - 1
    chosen: list[int] = []
    seen: set[int] = set()
    for index in range(sample_count):
        zero_based = (index * span) // (sample_count - 1)
        page = zero_based + 1
        if page not in seen:
            seen.add(page)
            chosen.append(page)
    if len(chosen) < sample_count:
        for page in range(1, page_count + 1):
            if page not in seen:
                seen.add(page)
                chosen.append(page)
            if len(chosen) == sample_count:
                break
    return tuple(sorted(chosen))
