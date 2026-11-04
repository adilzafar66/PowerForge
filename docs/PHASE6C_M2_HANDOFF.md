# Phase 6C M2 handoff — Deterministic semantic interpretation

**Delivered:** 2026-11-03 on `codex/phase-6c-engineering-extraction`, following M1 commit `c548ebe8c21dcc6ce8f2058b1c77e49ffce8c6e1`. Scope: M2 of [PHASE6C_PLAN.md](PHASE6C_PLAN.md). Phase 6C remains incomplete; production extraction is not executable.

## Delivered boundary

`powerforge_extraction.interpretation` exposes:

- `interpret_equipment(EquipmentObservation, InterpretationContext, version=...)`.
- `interpret_attribute(AttributeObservation, InterpretationContext, version=...)`.
- `interpretation_identity(version=...)`.

The only supported algorithm is `engineering-interpretation-v1`, implemented in `interpretation_v1.py`. Unknown versions fail rather than silently selecting the current rules. This code depends on pure observation/registry contracts, not SQLAlchemy, HTTP, task transport, provider SDKs or object storage.

`InterpretationContext` is a bounded **admitted local statement**, optional separately associated equipment passage and native/visual source kind. It is not an artifact verifier. M3 must prove where the text came from and why the equipment passage belongs to that statement. Do not populate context with a whole page containing unrelated equipment, a model's proposed type/key, or an unverified quotation. For page-level vision, M3 must explicitly admit the reading with the agreed visual-grounding limitation; this interpreter cannot prove pixels were read correctly.

The immutable result retains raw text/value/unit, actual source tag/name where applicable, mapping status/reason, optional registry type hint and, only when mapped, attribute key, typed Python value and canonical unit. It contains no canonical/group/evidence IDs and creates no persistence output. The result's `mapping_status=None` and `rejected=True` designate inconsistent model source fields, **not** a new persisted MappingStatus. M3 must discard these claims rather than turn them into supported candidates/evidence.

## Source-qualified semantics

The interpreter checks exact asserted expressions/value lexemes and source label/unit agreement before relying on model ambiguity or type proposals. A fabricated value cannot hide in an UNMAPPED observation or borrow a number from a label such as “3-Phase.” Equipment tags use identifier boundaries, so TX-1 does not match TX-10. Tags alone do not establish a type.

Equipment meaning uses exact registry type names/keys plus the explicitly supported LV circuit-breaker terminology. All 20 registered type names follow the same resolver. Multiple, negated, alternative or explicitly uncertain categories remain unmapped. Generic “transformer” alone does not establish TWO_WINDING_TRANSFORMER, and CB-1 alone does not establish LV_BREAKER. Recognizing those broader descriptions without enough subtype context remains a meaningful unmapped observation, not a forced nearest type.

Attribute meaning is resolved independently from admitted field labels using registry keys/display names and the small qualified M1 terminology set. A valid but wrong proposed `primary_voltage` cannot override a source “Secondary Voltage.” A missing model proposal does not prevent mapping a clear source label. Incorrect model proposals remain UNMAPPED with no normalized slots. Isolated observations do not require equipment mention/group IDs; mapping requires sufficient admitted equipment-type context regardless of whether any mention was persisted.

Qualified terminology is executable only through known v1 rule IDs, not by parsing its English qualification prose or automatically trusting newly added aliases:

- Transformer capacity and ordinary two-winding/nameplate impedance use the confirmed type context. Normal-impedance shorthand is not applied to isolated, zero-sequence or alternate-base statements; no other sequence values or winding data are inferred.
- AF maps to frame rating in LV-breaker context. AT maps to trip rating only with explicit, unambiguous thermal-magnetic device context. It cannot establish sensor, plug or electronic long-time pickup values. Manufacturer/model text does not trigger catalog lookups or new inferred attributes.
- Cu/Al map only within a source-supported cable conductor-material field. The same symbols in a model identifier cannot change its field meaning.
- Utility three-phase and SLG fault-current/X/R fields remain distinct. An unqualified X/R value is not assigned a convenient fault basis.

No requirement/default population, physical asset identity, topology, study calculations or revision-wide metadata targets are added. Conflicting source-stated values remain independent observations. Source statements are not made engineer-verified by a mapped result.

## Normalization and diagnostics

All conversions delegate to `normalize_attribute_value()` and its existing registry semantic contexts. No conversion factors or alternate normalization engine are introduced.

- NUMBER uses Decimal from source strings. Original expressions remain intact; converted values follow the registry's existing Decimal context. INTEGER uses exact Python int and the existing signed BIGINT bounds; compatibility tests verify existing API string serialization beyond JavaScript's safe range.
- Explicit units in a field label/header or body are accepted. A missing unit is never supplied from the registry's canonical-unit default. Conflicting explicit units stay UNMAPPED. AF/AT/%Z retain their literal source expression while the qualified interpretation supplies A/A/% to the existing normalizer.
- Percent and per-unit are distinct; no impedance-base conversion occurs. Horsepower conversion is allowed only where the registry's equipment semantic context permits it. Temperature rise uses the registry's difference context rather than absolute-temperature conversion.
- Explicit yes/no/true/false statements produce actual bool values, including false. Missing values remain unmapped, never false. Text stays literal. Enum spelling normalization is limited to clear case/space/hyphen/underscore forms and the scoped terms; unknown, composite or question-mark values remain UNMAPPED instead of becoming OTHER/defaults.
- Locale-ambiguous comma notation remains UNMAPPED. Nonfinite/malformed numbers, fractional integers, incompatible units and nonrepresentable values remain INVALID with no normalized fields. Numeric representation checks use PostgreSQL NUMERIC/BIGINT storage capacity, not invented equipment operating limits. Physically implausible but registry-valid source values are not silently corrected; broader engineering validation remains Phase 10.

UNMAPPED/INVALID results retain meaningful raw source data, optional independently established registry type, safe constant reason codes and no `attribute_key`, `value_type`, canonical `unit` or typed value. Source-field rejection remains separate. No raw provider/registry exception messages are logged or returned as diagnostics.

The parser deliberately accepts a conservative local field grammar: labeled single statements, explicit source units and the qualified numeric-first shorthand. Arbitrary prose, fuzzy synonyms, tables, complex ranges or a whole page with mixed associations are not claimed supported. M3 must select correct local source spans, preserving unresolved content honestly rather than broadening context until something maps.

## Reproducible identities and compatibility

`tests/fixtures/extraction/interpretation_v1_identity.json` pins the algorithm version, SHA-256 of the shipped v1 rule module, registry projection hash and terminology hash. The rule hash is reproduced from source packaged in the wheel; it is not a hash of user documents. Future rule versions must retain the deployed v1 implementation/reader and pin their identity in the production profile at M4. No persisted production profiles are created by M2.

Registry-v1 and its reference artifacts are unchanged. M1 observation schemas, prompts, terminology data, stage manifest/hash fixtures and all legacy probe profiles/wire identities remain unchanged. Existing worker, API, execution accounting, persistence and migrations are untouched. No schema migration is required for this pure layer.

## Actual verification

**102 new M2 tests pass. The combined relevant offline suite passes 262 tests**, with five existing dependency deprecation warnings:

```sh
RUN_INTEGRATION=0 .venv/bin/pytest -q \
  tests/test_engineering_interpretation.py tests/test_engineering_normalization.py \
  tests/test_engineering_interpretation_boundaries.py \
  tests/test_engineering_observations.py tests/test_engineering_extraction_context.py \
  tests/test_engineering_extraction_identities.py tests/test_engineering_registry.py \
  tests/test_engineering_units.py tests/test_openai_extraction.py \
  tests/test_extraction_contracts.py --tb=short
```

Coverage includes all 20 explicit type names, source-tag boundaries/negation, all eight curated M1 fixtures, transformer normalization/impedance, breaker AF/AT/false, cable material/length/integer precision, utility fault/X/R distinctions, wrong proposals, invented source fields, units/headers, unknown enums, competing values, missing/zero values, numeric representation limits, pure imports and stable version identities. The original M1 fixtures were preserved; their independently declared expected interpretations are now exercised where applicable. The visual fixture is still synthetic text representing an admitted reading, not a real image/model evaluation.

The extraction wheel builds and directly imports the new interpreter, reproduces the pinned rule hash and renders unchanged M1 prompt resources. Ruff, formatting, dependency and whitespace checks pass. No live database, migrations, worker/beat, frontend or paid provider calls were run for this pure offline milestone. These results establish deterministic behavior, not real-model recognition accuracy or actual artifact grounding.

## Next: M3

M3 must admit exact versioned source artifacts and verified local passages, prove associations, compute Unicode offsets, handle repeated phrases, label visual grounding honestly, create source-local groups/citations and convert accepted interpretations to atomic WorkUnitOutput. Rejected claims must remain excluded; an empty valid extraction does not establish document completeness. M4–M6 still own dependent-stage scheduling, production provider/profile integration and measured evaluation. No later milestone has been implemented here.
