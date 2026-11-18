"""Same source values remain distinct except for likely redundant representations."""

from powerforge_extraction.assertion_consistency import redundant_assertions
from powerforge_extraction.publication import publication_diagnostics


def fact(ref, owner="breaker-1", reading="q1", **fields):
    return (
        dict(
            local_ref=ref,
            origin="EXTRACTED",
            equipment_ref=owner,
            association="ASSERTED",
            attribute_key="trip_unit_model",
            raw_value="MODEL-X",
            raw_unit=None,
            raw_label="Trip Unit",
            value_form="SINGLE",
            qualifiers=[],
            evidence=[dict(kind="READING", role="VALUE", reading_ref=reading, quote=None)],
        )
        | fields
    )


def test_redundancy_keeps_occurrences_owners_conflicts_and_audit():
    primary = fact("original")
    repeated = fact("qualified")
    repeated.update(value_form="QUALIFIED", qualifiers=["Protection functions"])
    other_value = fact("conflicting")
    other_value["raw_value"] = "MODEL-Y"
    other_key = fact("type")
    other_key["attribute_key"] = "trip_unit_type"
    no_evidence = fact("uncited")
    no_evidence["evidence"] = []
    raw = {k: v for k, v in primary.items() if k not in {"attribute_key", "origin"}}
    raw["local_ref"] = "raw-copy"
    different_label = dict(raw, local_ref="separate-raw", raw_label="Other fact")
    payload = dict(
        attributes=[
            primary,
            repeated,
            fact("second-device", owner="breaker-2"),
            fact("different-source", reading="q2"),
            other_value,
            other_key,
            no_evidence,
        ],
        raw_unmapped=[raw, different_label],
    )
    assert redundant_assertions(payload) == {"qualified": "original", "raw-copy": "original"}
    assert len(payload["attributes"]) == 7
    diagnostics = publication_diagnostics([], redundant_assertions(payload))
    assert diagnostics[0] == {
        "ref": "qualified",
        "related_ref": "original",
        "code": "LIKELY_REDUNDANT_ASSERTION",
    }


def test_empty_unknown_or_inferred_values_do_not_establish_redundancy():
    payload = {
        "attributes": [
            fact("a", owner=None),
            fact("b", owner=None),
            fact("c", origin="INFERRED"),
            fact("d", origin="INFERRED"),
        ]
    }
    assert redundant_assertions(payload) == {}


def test_differently_qualified_facts_are_preserved():
    a = fact("hot")
    a["qualifiers"] = ["At high temperature"]
    b = fact("cold")
    b["qualifiers"] = ["At low temperature"]
    assert redundant_assertions({"attributes": [a, b]}) == {}
