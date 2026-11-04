# Phase 6C M1 handoff — Observation contracts, context and prompts

**Delivered:** 2026-11-03. Branch: `codex/phase-6c-engineering-extraction`. Base: `main` at `3ffb43f8fc5082817c7be5ec3d67dc94f44319f6`, including accepted 6B commit `5042af8`.

Only M1 of [PHASE6C_PLAN.md](PHASE6C_PLAN.md) is delivered. Production extraction remains unavailable. The approved specification, ADR-008, frozen registry-v1, old handoffs, migrations and existing worker/API/provider behavior are unchanged.

## Delivered interfaces

`powerforge_extraction.observations` defines `EquipmentRecognitionResponse` and `AttributeExtractionResponse`, with separate equipment/attribute observations and `SourceAnchor`. These are provider-neutral intermediate observations, not database entities, normalized candidates or verified source facts.

- Raw labels/expressions/values/units preserve original strings and Unicode. Unknown proposed registry keys remain representable for later interpretation. Source strings never become floats or JSON numeric/boolean normalized values in this layer.
- Tags, names, mappings and equipment association can be null. Tagless and unknown equipment, meaningful standalone attributes, explicit false source expressions and integers beyond JavaScript precision are represented without forcing context.
- Every nullable field is explicitly required on the wire, with strict types and no unknown fields. Local references must be unique within each response. Ambiguous observations require a reason; clear observations use a null reason. No confidence score is invented.
- Native anchors require a `native_text` role and quote, with optional exact surrounding context. Visual anchors require `analysis_image` and null quote/prefix/suffix. Neither accepts model offsets, geometry, page/artifact UUIDs or persistence IDs. The visual reading stays in the raw observation.
- Recognition allows at most 32 observations, attributes 128; each observation has 1–8 anchors. Expressions/quotes/raw values are bounded at 2,000 characters, context at 256 per prefix/suffix, tags at 200, names at 500 and raw units at 100. Total UTF-8 response limits are 256 KiB and 512 KiB respectively. Declared overflow rejects the response; empty arrays remain valid.

`powerforge_extraction.engineering_stages.get_engineering_stage(key, version=...)` returns one of two immutable offline definitions: EQUIPMENT_RECOGNITION, or ATTRIBUTE_EXTRACTION with its recognition prerequisite. `validate_result(payload, available_sources=..., equipment_refs=...)` revalidates the complete expected schema, rejects unavailable source/equipment references and catches mutated nested containers. It does **not** verify quotations, source ownership, semantic associations or registry mappings. Those remain M2/M3 responsibilities.

`render_instructions(equipment_types=...)` composes the common and stage-specific resources with generated registry/qualified terminology context, returning text plus context/instruction hashes. Recognition always uses all 20 types; attribute context is canonicalized by selected known types, with an empty selection still supporting raw isolated observations. Source bytes and upstream observations are not arguments to this renderer; future execution must send them as separate untrusted input.

These definitions are deliberately not registered in `ExecutionProfile`, `execute_unit()` or the OpenAI adapter. The existing provider-neutral probe envelope is unchanged. M4/M5 will connect the stage schemas without changing legacy profile wire identities.

## Registry and terminology

`registry_context` derives all metadata from approved runtime registry APIs: type/attribute identifiers and labels, value types, canonical and supported input units, enums and notes. There are no copied attribute catalogs, runtime workbook/reference-file reads, requirement evaluation, conversions or inferred required/default values. The independent JSON reference is read by tests only.

All 20 types/296 definitions are covered. The complete attribute projection is 59,580 UTF-8 bytes, including supported units and the compact type catalog; the bound is 96 KiB. All-types attribute instructions are 66,417 bytes, below the 128 KiB instruction bound. These are metadata bounds, not a claim that any configured model accepts that full input. M4/M5 must enforce combined source/model/resource limits. The current stage manifest is only 1,009 bytes and fits the existing 64 KB run-configuration bound.

`terminology` provides nine scoped entries for clear LV breaker naming, transformer capacity/qualified normal impedance, breaker AF/AT, cable Cu/Al and explicitly qualified utility fault-current labels. Targets validate against registry-v1. Qualifications are explanatory policy data, not an executable English rule language or automatic coercion. M2 must independently establish source/context conditions and must preserve uncertainty when they do not hold. No normalization engine or competing registry has been added.

## Versions and compatibility

- Manifest: `engineering-stage-manifest-v1`.
- Prompts: `engineering-prompts-v1`; resources `engineering_common_v1.txt`, `equipment_recognition_v1.txt`, `attribute_extraction_v1.txt`.
- Schemas: `equipment-recognition-schema-v1`, `attribute-extraction-schema-v1`.
- Registry projection: `engineering-registry-context-v1` against `registry-v1`.
- Terminology: `engineering-terminology-v1`.

The pinned hashes/manifest are recorded in `tests/fixtures/extraction/engineering_identities_v1.json`. New engineering identities use sorted compact JSON, UTF-8, exact Unicode and SHA-256; serialization does not normalize source text. Template identity is distinct from rendered instructions/context. Equivalent reordered/deduplicated type selections render identically; different selected context changes the rendered hash. Unknown stage/version lookups fail without fallback.

The baseline `legacy_source_probe_v1.json` captures accepted 6B wire JSON/hash under explicit settings for both infrastructure profiles. The accepted probe prompt hash remains `c21236625be34dfa14acb70d2cad41addb6ef85f07300d9a72b8fb6c586910d1`, and schema hash remains `cddcfcfbc99c358fab8ce110b86e622fc2a0135716ebecba113e967a5e61e394`. Legacy serialization/hashing code is untouched.

Prompt/schema/context/policy changes must receive deliberately versioned identities and retained readers/resources before persisted execution uses them. Do not silently edit an already deployed version and substitute it into an old run. M4 will pin these identities in production configuration; M1 itself creates no runs.

## Actual verification

New M1 suite: **40 passed**. Final combined focused/regression suite: **160 passed**, five existing dependency deprecation warnings, in 1.17 seconds:

```sh
RUN_INTEGRATION=0 .venv/bin/pytest -q \
  tests/test_engineering_observations.py \
  tests/test_engineering_extraction_context.py \
  tests/test_engineering_extraction_identities.py \
  tests/test_engineering_registry.py tests/test_engineering_units.py \
  tests/test_openai_extraction.py tests/test_extraction_contracts.py --tb=short
```

Coverage includes independent registry comparison, targeted/all-type contexts and supported-unit semantics; tagged/tagless/unknown/isolated/empty response shapes; raw decimal/integer/false strings; closed schema/reference/overflow/UTF-8 bounds; repeated tags without automatic merging; canonical hashes and legacy wire snapshots; import isolation from infrastructure/vendor SDKs; and offline conversion by the installed OpenAI SDK's strict-schema helper. That helper check is not live server/schema acceptance or model-quality validation.

The extraction wheel builds using pip's isolated build environment and ships all four prompt files. A direct wheel import renders engineering context and preserves the old probe prompt hash. The first no-isolation build lacked setuptools and uv was unavailable; the isolated build completed without adding project/venv dependencies. Ruff, changed-file formatting, `pip check` and whitespace checks passed.

No database, migration, frontend, live worker or live paid API test was run for this offline-only change. The full 1,184-test integration result belongs to prior 6B verification and is not reported as an M1 test run.

## Fixtures and remaining work

`engineering_observations_v1.json` contains eight curated shape fixtures: tagged transformer, distinct breaker ratings/false, cable/integer precision, qualified/ambiguous utility fault data, tagless visual nameplate, unknown equipment/attribute, isolated Unicode/competing values, and no equipment. Future expected mappings are independently declared but **not evaluated by M1**. The visual case describes a synthetic expectation; no image/model run or accuracy measurement is claimed. The large cable run count is explicitly a synthetic precision stress case.

Next is M2 semantic mapping/normalization. M3 must independently ground quotes/values/associations, derive offsets/groups/citations and expose the approved page-level visual limitation. M4/M5 must preserve one admitted call per stage attempt, dependencies, retry/cancellation/fencing/telemetry and source/probe compatibility. M6 must measure representative and optionally authorized live-model quality. Source-only membership, no canonical writes, manual-only revision metadata and no cross-document physical identity inference remain binding throughout.
