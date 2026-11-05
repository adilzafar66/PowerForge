# Phase 6D M2 — Grounding, interpretation and publication

**Status:** M2 implemented for review; Phase 6D remains incomplete. M3 production profiles/worker orchestration and M4 table evaluation have not started. Authority: [approved plan](PHASE6D_PLAN.md), [6D prompt](prompts/phase-6d-prompt.md) and accepted [M1 contracts](PHASE6D_M1_HANDOFF.md).

## Delivered boundary

Four extraction modules implement a deterministic adapter over the existing page-source and persistence contracts:

- `table_grounding` admits reconstruction against verified, pinned `PageSources`, produces `TableInput` and evidence, and revalidates upstream snapshots against those exact bytes.
- `table_semantics` resolves structured-cell meanings through the unchanged 6C qualification/value helpers and registry-v1 normalization. It does not turn separate cell/header content into an invented native quotation.
- `table_output` converts admitted observations into source-local groups, relational equipment/attribute candidates and citations to committed reconstruction evidence.
- `table_sources` loads the completed reconstruction for the exact run, document, processing run, page, canonical reconstruction key and selected artifact set. It rejects unexpected engineering outputs in that prerequisite and rederives every stored table/evidence field before permitting interpretation.

These functions do not select a provider, schedule work, start production table runs or invoke a model. Database tests control the two units manually through the existing internal publisher. Supported production discovery, orchestration, selected schemas and provider inputs remain M3. The intended production profile is table-only, with ordinary prose extracted in a separate existing 6C run. Cross-profile latest-summary behavior and history remain unchanged; their explicit combined-profile regressions remain M3.

## Source and relationship proof

Callers use existing `page_spec_for_unit()` and `load_page_sources()` to load exact immutable artifact descriptors and verify actual object size/hash, UTF-8 and PNG dimensions. Source I/O remains outside the metadata transaction. The database loader owns no storage connection or transaction; it consumes that verified source snapshot. Publication independently rechecks pinned text integrity/offset bounds through existing storage verification, never mutable page character counts.

Native structural admission initially requires a unique, dense, contiguous tab- or pipe-delimited grid with exact row/column content, at least two columns and unit cell spans. Optional outer pipes and padding spaces are supported. Every declared native anchor must agree with the selected source occurrence. Captions are scoped only immediately before the grid, and notes immediately after it. Repeated cell values can acquire different exact codepoint offsets when the complete unique grid establishes their positions. Token matches, arbitrary whitespace, PDF reading order and an image merely being available cannot prove native relationships.

An explicitly declared table-level visual page anchor permits `VISUAL_REPORTED` structure. Cells may independently have verified native text, visual reports, or both. Otherwise structure remains `UNRESOLVED` and the persisted orientation is UNCLASSIFIED. Invalid native assertions reject the affected table even when an image was also selected; visual evidence cannot rescue fabricated text. Shape-invalid/overflowed responses fail the stage, rather than being silently truncated. Rejected source tables contribute the bounded `rejected_ungrounded` count.

Evidence locators always identify the actual page/artifact and, for cells, the table UUID and local cell ID. Native snippets retain exact verified text and server-calculated offsets when unambiguous. Visual evidence has null snippets, offsets and geometry. No model coordinates, offsets or persistent IDs are accepted. A hybrid cell can explicitly cite both representations; its additive server metadata records each authorized source location. API evidence summaries now report the actual TABLE_CELL text/visual precision, with artifact types fetched in one batch for candidate reads. Detail signing continues to use the historical artifact. Precise native cell text does not upgrade visual relationships into independently verified geometry.

## Conservative interpretation and associations

Equipment rows require a unique admitted identity cell with a complete header band. Single-equipment attribute rows require one justified equipment context or an explicitly cited, scoped equipment caption. Repeated tags in different rows/tables remain separate source-local observations. Tags/names must occur in the original equipment expression. A numeric identity cell cannot acquire equipment meaning from a caption. Competing row identities, unrelated device captions, conflicting/unknown explicit type fields, uncertainty and truncation prevent confident mapping. Type context comes only from the scoped table caption, the equipment expression and an explicit same-row Type column.

Attributes use the complete applicable header path and their actual value cell. Equipment references outside the established row/table scope are detached and retained UNMAPPED. Headers from another column cannot supply meanings/units. Scoped notes and conditional/unknown qualifiers prevent automatic mapping. Blank or entirely unreadable value cells cannot produce claims; partially readable cells retain raw uncertain observations. MIXED and UNCLASSIFIED layouts remain inspectable without forcing a conventional association or inventing missing values.

The adapter reuses registry display names, qualified 6C terminology, exact Decimal/integer/boolean/enum/text interpretation and registry unit conversion. A small equipment-qualified table alias map supports Capacity, Primary, Secondary, Frame, Trip and Material. Qualified container labels such as Breaker Ratings can support a complete merged header path; unknown parent qualifiers remain unresolved. AF/AT clauses can be distinct claims on one cell (alternate excerpts of the same clause are deduplicated), but cannot replace contradictory headers or turn a generic Rating number into a guessed attribute. Thermal-magnetic trip qualification remains required. False values and integers above JavaScript's exact integer range survive. Invalid units, out-of-range values and unsupported meanings remain INVALID/UNMAPPED as appropriate, with raw expressions retained. No defaults, revision-wide settings, physical identity or canonical writes are inferred.

Candidate diagnostics distinguish text verification, structural basis, grounding precision and the `VISUAL_REPORTED` interpretation limit. Interpretation emits no replacement layouts/evidence; its primary citation is the committed value/identity cell, with supporting header, caption, qualifier and equipment-context evidence.

## Publication and compatibility

The shared publisher now validates table/cell references on both newly emitted evidence and reused candidate citations. Referenced tables require the same run/processing ownership and a completed upstream producer, unless being atomically published by that producer. Page/cell/artifact locations and both units' selected artifacts must agree. Table interpretation specifically requires its reconstruction stage and exact page/artifact plan. Legacy coarse cell locations remain readable/usable under their original representation; 6D context revalidation prevents weakening a stored 6D cell into such a legacy locator. Publication failures roll back the whole downstream savepoint while preserving committed reconstruction output.

Existing `table-layout-v1`, relational models, migrations 0011–0013, routes and registry-v1 are unchanged. Additive bounded layout metadata contains the original strict observation, producer identity/unit, reliability, scoped references, actual native grid span, item evidence IDs and per-cell source locations. Blank/unreadable display text can be empty because the existing layout text field is non-nullable; the original null/empty distinction and state remain in metadata, and no engineering claim is manufactured.

`table-grounding-interpretation-v1` has a separately pinned identity in `tests/fixtures/extraction/table_grounding_v1_identity.json`. It hashes all four new modules plus unchanged M1 layout, 6C source and interpretation identities. Accepted M1/6C resources, profile readers, execution/runtime fingerprint inputs and evaluation fixtures are preserved. M3 must still implement retained identity resources before changing shared fingerprinted dispatch code.

## Verification and remaining limits

M2 adds **75 tests**: 58 deterministic grounding/interpretation cases and 17 real PostgreSQL publication/loader/read cases. The full backend run passed **1,635 tests, no skips**, with six existing dependency warnings in **252.54 seconds**. After the final table-only refinements (source-field deduplication, admitted orientation, hybrid text precision and AF/AT header agreement), the final focused gate passed **178 tests, no skips**, with the same six existing warnings in **8.85 seconds**. That gate includes all 79 M1 cases, all 75 final M2 cases and 24 shared persistence/engineering publication/API regressions. The broad result precedes those final new-adapter refinements; the focused result verifies the final files.

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:55442/powerforge_phase6d_m2 \
S3_ENDPOINT_URL=http://localhost:59012 S3_PUBLIC_ENDPOINT_URL=http://localhost:59012 \
REDIS_URL=redis://localhost:56392/0 RUN_INTEGRATION=1 .venv/bin/pytest -q --tb=short

# Same isolated service environment; final targeted gate:
.venv/bin/pytest -q --tb=short \
  tests/test_table_observations.py tests/test_table_stages.py \
  tests/test_table_grounding.py tests/test_table_publication.py \
  tests/test_extraction_persistence.py tests/test_engineering_publication.py \
  tests/test_extraction_api.py
```

A dedicated tmpfs PostgreSQL/Redis/MinIO Compose project was migrated fresh to head 0013 and used for these checks. The complete backend run includes real storage/worker/broker integrations with mocked provider transports. M2-specific image/native publication tests use verified immutable in-memory source objects and the real PostgreSQL boundary. Test infrastructure is removed after verification; normal development services/data are untouched.

Final extraction/API wheels build and direct imports reproduce the new grounding identity, unchanged M1 manifest, legacy v1/v2/v3 profiles and the exact complete committed 6C scripted report. The pure M2 converter imports no ORM, vendor SDK, API or task framework; the separate database loader imports SQLAlchemy intentionally. Ruff, changed-file formatting, dependency and whitespace checks pass. An initial no-build-isolation wheel attempt could not import setuptools from the workspace virtualenv; isolated builds succeeded without changing project dependencies.

The initial M2 rules hash, before the review corrections below, was `ba58d0688482185bd32f6e43417caa8bcf1bc949fb221bcc29612fd2b9884040`. Accepted M1 identities and historical 6C fixture bytes were not regenerated. New fixtures are independently authored source text and scripted observations. Image fixtures test source/provenance plumbing, not image recognition accuracy. No paid provider call, frontend change, OCR or new document ingestion format is included.

The conservative native grid recognizer intentionally does not reconstruct ordinary PDF whitespace geometry, Markdown separator rows, sparse native grids or merged native cells. Such inputs need explicit page-level visual interpretation or remain unresolved. Unknown header paths, complex mixed tables and conditional notes may reduce recall. Representative processed PDF documents and model quality remain the M4 evaluation gate; no accuracy claim follows from these deterministic tests. No complete Phase 6D production runtime is delivered until M3/M4 pass.

## M2 review — Multi-tag ownership and distinct cell readings

The ownership check now inspects the complete admitted identity cell and other identity fields on that row. Distinct tag-shaped strings or explicit lists of identifiers prevent unique row ownership even when the model emits only one equipment observation or quotes only one tag. The same conservative check applies to a single-equipment specification. Original observations/evidence survive as UNMAPPED, with no source group or accepted attribute-to-equipment association. Matching tag text does not infer an equipment type or physical identity; exact repeated entries remain supported, and case-distinct strings are not silently equated.

A shared source-reading helper now distinguishes canonical scalar fields, the supported AF/AT clauses and limited exact excerpts. Multiple conditional readings from one cell survive as separate UNMAPPED candidates, including a second value that does not start at the beginning of the cell. Their values and units must still be grounded in the actual source excerpt; invented values, numeric prefixes, borrowed values and unsupported units are rejected. Limited excerpts cannot become normalized registry values merely because their individual numbers look valid.

Deduplication retains distinct source readings, declared qualifier context and proposed equipment associations. Alternate excerpts of one ordinary scalar or one AF/AT clause still collapse, as do equivalent aliases for the same equipment mention. A wrong-row association remains detached and UNMAPPED without discarding the independently justified observation for the correct row. Detached proposals retain their reported equipment candidate ID in diagnostics, and declared qualifier evidence IDs distinguish reported contexts without accepting them as proven conditions. Primary citations still identify the original committed value cell, and visual evidence retains page-level limits.

The review adds **39 regression cases**: 35 deterministic cases and four native/visual PostgreSQL publication/API cases. The final review gate passed **409 tests, no skips**, with six existing dependency warnings in **12.18 seconds**, including all 93 M2 grounding cases and 21 M2 publication cases. Extraction/API wheel builds and direct packaged imports reproduce the updated M2 identity, unchanged M1 manifest, historical v1/v2/v3 profiles and exact full 6C scripted report. Ruff, formatting, dependency and whitespace checks pass. A fresh disposable database was migrated to head 0013; its services and generated build output were removed afterward. The full backend suite was not rerun for this localized adapter correction; the original broad M2 result above is historical. No paid provider call was made.

Using the same isolated service environment as the initial M2 gate, the final review command was:

```sh
.venv/bin/pytest -q --tb=short \
  tests/test_table_observations.py tests/test_table_stages.py \
  tests/test_table_grounding.py tests/test_table_publication.py \
  tests/test_extraction_persistence.py tests/test_engineering_publication.py \
  tests/test_extraction_api.py tests/test_engineering_grounding.py \
  tests/test_engineering_interpretation.py tests/test_engineering_interpretation_boundaries.py \
  tests/test_engineering_normalization.py tests/test_engineering_execution_profiles.py \
  tests/test_engineering_openai_profiles.py tests/test_engineering_evaluation.py
```

The pre-production M2 fingerprint is refreshed to `3458ebd06f271ab669f96629e5cf5a566cbdb8de5b28408a1d275f667e164ebe`; M1, registry-v1 and historical 6C resources/identities remain unchanged. No production table profile, migration or M3 implementation is introduced.

**Stop for M2 review before M3.**
