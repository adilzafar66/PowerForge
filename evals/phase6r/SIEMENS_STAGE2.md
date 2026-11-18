# Siemens Stage 2 development case

Reviewed page 1 of the local Siemens panel drawing and the already-published run
`dcab2728`. The PDF and provider bodies are kept outside the repository. This
pass made no new OpenAI requests.

## Saved run

Recognition found four low-voltage breakers (WL, CMD6, CJD6, CND6) and a bus.
Stage 2 published 11 registry proposals and 3 raw-unmapped assertions in 49.095 s.

- The branch pole counts were mapped. None of the four breaker occurrences
  had a registry `model` assertion. The identifiers already appeared in the
  recognition descriptions, so the missing cards came from Stage 2 omissions.
- Stage 2 preserved the branch amperages as raw-unmapped. The drawing states
  these amperages without identifying them as frame ratings, trip settings,
  or rating plugs. Retain the reported figures and score specific registry
  mappings only when their meaning is supported.
- Stage 2 submitted ETU745 under both `trip_unit_model` and `trip_unit_type`.
  The rows were published as unmapped for unrepresentable value form. ETU745
  itself is directly reported as the trip-unit model. Its technology is a
  separate assertion if proposed using reliable model knowledge.
- The viewer previously preferred the model-reported label as the card title
  and displayed the raw and normalized values inside expanded cards. Distinct
  registry keys sharing a source label could look like duplicates.

## Development checklist and measurements

The narrow direct checklist covers the four printed model identifiers (including
the WL family), four pole counts, the main rating plug, the main catalog number,
and the printed ETU745 trip-unit model. The saved run had matching raw/key
assertions for **7 of 11** and mapped those values correctly for **6 of 11**.
The four missing model assertions remain in the denominator. This deliberately
excludes ambiguous branch rating semantics and is limited to these fields.

Track inferences separately. ETU745 trip-unit technology is a development
proposal for independent product-reference review. Manufacturer and breaker
classification are possible inference targets where an identifiable product
family supplies reliable support. The occurrence-specific relationship must be
reviewed. Branch trip-unit type, protective settings, and the interpretation of
the bare branch amperages are abstention cases on the page alone. A missing
designation never establishes a default. The saved schema recorded no explicit
inference origin, so historical inference recall and correctness are unavailable.

The offline Siemens-style fixture uses a synthetic schedule with the four models
and ETU745. It maps and lexically verifies **5 of 5** seeded direct values.
In separate inference cases it maps **3 of 3** supported enum proposals while
keeping all three source-value states unverified. The cases cover no citation,
a context citation, and an invalid value citation. Neither negative proposal
maps (unsupported enum and foreign owner). Branch trip-unit types stay absent
when the fixture supplies no justified proposal. These are contract and
publication checks.
They do not measure new live model recall or engineering correctness. A future
authorized evaluation should count extracted and inferred assertions by
occurrence and key, measure each origin's recall and correctness against its own
reviewed reference set, and report abstentions. Context localization for an
inference is excluded from direct value-evidence metrics.
