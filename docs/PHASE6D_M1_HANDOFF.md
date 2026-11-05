# Phase 6D M1 handoff — Offline table definitions

Delivered 2026-11-05 on `codex/phase-6d-tables-schedules`, created from refreshed `main` at `1b0afd11a34e35c3bb682b5af28f348f64371587`. Scope is M1 of the [approved plan](PHASE6D_PLAN.md), including its review clarifications. M2–M4 remain pending; Phase 6D is not complete.

## Delivered boundary

The extraction package now owns provider-neutral strict table observations, pure structural inspection/reference checks and two offline stage definitions: TABLE_RECONSTRUCTION followed by TABLE_INTERPRETATION. Three packaged prompt resources describe table-only observation, conservative structure, original source strings and existing-cell interpretation. There is no production profile registration, worker/provider execution, source-object admission, normalization, persistence output conversion, migration, route or UI change.

The approved ownership remains table-only. Ordinary prose extraction requires a separate existing 6C run. Existing cross-profile document summary behavior is unchanged: a newer completed/partial table run can become latest_result while earlier 6C results remain available through history. Actual same-document history/summary regressions belong to M3, not this offline milestone. Representative native-PDF reconstruction/visual-dependence evaluation remains M4.

## Contracts and layout inspection

`table_observations` defines separate reconstruction and interpretation schemas. Every nullable wire field is explicitly required; unknown properties and coercion of raw strings/indices are rejected. Response-local references identify observations, not database entities. Existing 6C SourceAnchor contracts are reused unchanged: native quotes/context or page-only visual anchors, with no model offsets/coordinates/UUID fields.

Reconstruction supports all existing orientations, sparse row/column grids, several tables, optional titles/scoped notes, merged spans, readable VALUE cells, explicit BLANK cells with empty strings, and UNREADABLE cells with null or exact partial text and an uncertainty reason. Absent slots stay absent. Source truncation has a separate reason and does not excuse response overflow. Empty page-level table lists are valid; a claimed table with no cells is invalid.

Validation enforces distinct rows/columns and table-local cell/caption/note references, nonoverlapping in-grid spans, readable header targets, axis-consistent header relationships and acyclic hierarchy. These are consistency checks on a proposed grid, not proof that the document has that structure. Interpretation cannot add or replace tables/cells; equipment and attributes reference only existing items in the selected table. Equipment references cannot cross tables. Blank cells cannot serve as attribute value cells. Unknown proposed keys, tagless equipment, detached attributes, conflicting readings and multiple claims per cell remain representable.

`table_layout.inspect_layout()` returns a revalidated sparse observation, a conservative orientation hint and server-metadata shape. An ambiguous table, or a conventional orientation with no header relationships, receives an UNCLASSIFIED hint. It does not classify engineering meanings. `observation_context()` supplies a bounded offline projection with raw content, states, header links, qualifiers and truncation; it is separate untrusted data, not trusted instructions or a committed database prerequisite.

`TableSourceMetadata`/`CellReliability` define the intended bounded server-authored metadata vocabulary for the later layout-v1 adapter: structure basis, per-cell state/header relationships, text basis and evidence IDs. M1 inspection always returns structure UNRESOLVED, text UNVERIFIED and empty evidence references. This retains the blank/unreadable distinction for future persistence conversion without inventing blank source values. Provider responses cannot assert these metadata fields. A server metadata object with evidence IDs is still only shape-valid; M2 must actually establish source ownership and verification.

No artifact is opened or verified by these modules. A source quote can be invented yet shape-valid, and a same-table equipment reference can still point at the wrong row. Tests explicitly retain those examples without claiming verification. M2 must reject or conservatively detach them after establishing real source structure and meaning. No TableInput/Evidence/Candidate entity is produced here.

## Versions, resources and bounds

- Manifest: `table-stage-manifest-v1`; prompts: `table-prompts-v1`.
- Response schemas: `table-reconstruction-schema-v1`, `table-interpretation-schema-v1`.
- Layout inspection/reference rules: `table-layout-observations-v1`.
- Server metadata: `table-source-metadata-v1`; offline projection: `table-observation-context-v1`.
- Manifest hash: `51c01f7893b53c96c501577ffd702b164679c8bb98c5057bde13a9c55ce21c82`.
- Layout/rule hash: `ac6e44cc0fc7972ebb27e2d18b899196593c044e193524753b75851f1c5d7f60`.

`tests/fixtures/extraction/table_identities_v1.json` pins exact schema/template/instruction/registry/rule identities and payload measurements. Rules cover the new observation/layout/stage sources and the unchanged reused 6C anchor contract. The established `table-layout-v1` persistence contract is unchanged; the similarly named observation rules do not introduce a second persisted table layout.

Versioned bounds are eight tables/page, 128 rows and 32 columns/table, 512 cells both per table and across the page, 64 equipment and 256 attribute observations, eight header references/cell, sixteen references/support list, four anchors/item and eight scoped notes/table. Raw cell/claim strings retain the existing 2,000-character cap. Reconstruction is capped at 1 MiB canonical UTF-8 JSON, interpretation at 512 KiB, and instructions/upstream projection at 128 KiB each. Structural count, response-byte and context-byte bounds are independent; exceeding one fails explicitly without truncating rows. Metadata evidence references are bounded separately.

Measured instructions are **8,030 bytes** for reconstruction and **66,699 bytes** for interpretation. Interpretation includes all 20 registry types/296 attributes because reconstruction has not committed mapped equipment types from which to safely select a subset. Metadata comes from existing registry APIs/qualified terminology, not a copied catalog. Registry notes do not become source facts or inferred defaults.

Eight synthetic shape fixtures cover transformer equipment rows, a single-equipment attribute table, mixed/conditional readings, flattened unclassified content, visual merged/sparse/unreadable cells, no tables, repeated tags across two tables, and cable Unicode/large-integer/text values. Maximum curated fixture sizes are 4,223 reconstruction bytes, 2,783 interpretation bytes and 2,674 context bytes. Larger generated structural probes measure **76,366 / 49,267 bytes** (response/context) for 256 cells and **152,334 / 98,355 bytes** for 512 cells. Separate tests exceed UTF-8 response and upstream limits with individually legal character counts. These measurements do not promise that a configured model can emit every allowed response within its token budget; production input/output limits and actual SDK requests are M3.

Existing v1/v2/v3 profile, runtime, registry, prompt, interpretation and grounding resources/fixtures were not changed. New profiles such as tables-openai-v1 remain unavailable. This milestone introduces no new historical reader/archive requirement because it does not modify fingerprinted shared execution files. M3 must implement the plan's retained-resource strategy before extending them.

## Actual verification

**77 new M1 offline cases passed** as part of **338 passing related tests**, with two explicitly deselected integration cases and six existing dependency warnings in **2.47 seconds**. No backend integration test or full backend regression was run for this offline-only change. The initial combined invocation named a nonexistent test file and collected no tests; the corrected final command below passed.

```sh
RUN_INTEGRATION=0 .venv/bin/pytest -q -m 'not integration' --tb=short \
  tests/test_table_observations.py tests/test_table_stages.py \
  tests/test_engineering_observations.py tests/test_engineering_extraction_context.py \
  tests/test_engineering_extraction_identities.py tests/test_engineering_interpretation.py \
  tests/test_engineering_interpretation_boundaries.py tests/test_engineering_normalization.py \
  tests/test_engineering_grounding.py tests/test_engineering_execution_profiles.py \
  tests/test_engineering_openai_profiles.py tests/test_engineering_evaluation.py \
  tests/test_extraction_contracts.py tests/test_openai_extraction.py
```

New checks cover all orientations, lossless raw round trips, sparse/blank/unreadable cells, merged and hierarchical headers, cycles/axis violations/overlaps, malformed references, unavailable roles, overflow/count/byte limits, mutated nested containers, no normalized slots/geometry/verified flags in provider schemas, and deliberate reference-valid but unverified associations. Actual OpenAI SDK **3.29.0** strict-schema conversion is exercised offline: closed objects retain all required properties. This is not live API schema acceptance or model accuracy.

The extraction wheel builds. Direct imports from the final wheel reproduce new schema/rule/prompt identities and all eight fixtures, accepted v1/v2/v3 wire/runtime identities and the exact complete 6C scripted evaluation report. Packaged prompts are present. Pure imports reject ORM, API, task, storage, image and vendor-SDK dependencies. Ruff, changed-file formatting, dependency and whitespace checks pass. Generated build output is removed after verification.

No database, migration, broker, object-storage service, provider credentials, frontend/browser test or paid/live call was needed or performed. Visual fixtures are scripted observation shapes, not actual image recognition. Native relationships are not verified by this milestone. The M1 acceptance gate is satisfied for its offline boundary; real grounding, semantic interpretation and atomic publication/read verification remain M2, orchestration/production execution M3 and measured table evaluation M4. Stop for M1 review before starting M2.
