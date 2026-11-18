"""Bounded diagnostics for redundant representations within one page/stage result."""

from powerforge_extraction.identities import canonical_json

VERSION = "assertion-consistency-v1"


def redundant_assertions(payload):
    """Compare exact values and reading occurrences; never deduce semantic equivalence."""
    seen = {}
    unqualified = {}
    qualified = {}
    represented = {}
    related = {}
    for item in (*payload.get("attributes", ()), *payload.get("raw_unmapped", ())):
        if item.get("origin", "EXTRACTED") != "EXTRACTED" or not item.get("equipment_ref"):
            continue
        occurrences = tuple(
            sorted(
                {
                    canonical_json({key: value for key, value in citation.items() if key != "role"})
                    for citation in item.get("evidence", ())
                    if citation.get("kind") == "READING"
                    and citation.get("role") in {"VALUE", "EQUIPMENT"}
                }
            )
        )
        if not occurrences:
            continue
        fact = (
            item["equipment_ref"],
            item.get("association"),
            item.get("raw_value"),
            item.get("raw_unit"),
            occurrences,
        )
        key = (
            fact,
            item.get("attribute_key"),
            item.get("raw_label") if "attribute_key" not in item else None,
        )
        qualifiers = tuple(sorted(item.get("qualifiers", ())))
        previous = seen.get((key, qualifiers))
        if previous is None:
            previous = unqualified.get(key) if qualifiers else qualified.get(key)
        # A raw extension is redundant only if its literal label also matches an
        # already represented registry assertion at the same exact occurrence.
        if "attribute_key" not in item:
            previous = previous or represented.get((fact, item.get("raw_label")))
        if previous:
            related[item["local_ref"]] = previous
        else:
            seen[(key, qualifiers)] = item["local_ref"]
            if qualifiers:
                qualified.setdefault(key, item["local_ref"])
            else:
                unqualified.setdefault(key, item["local_ref"])
        if "attribute_key" in item:
            represented.setdefault((fact, item.get("raw_label")), item["local_ref"])
    return related
