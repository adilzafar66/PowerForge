# Phase 6D — Tables and schedules final handoff

**Status:** M1–M4 implemented for review on `codex/phase-6d-tables-schedules`, 2026-11-05 (America/Vancouver). M4 baseline: `26ece9ee9c9d340d1fb4062851701b3b175eb544`. Authority: the unchanged [6D prompt](prompts/phase-6d-prompt.md), [approved plan](PHASE6D_PLAN.md), Phase 6 specification and ADR-008. Earlier deliveries/checks are preserved in the [M1](PHASE6D_M1_HANDOFF.md), [M2](PHASE6D_M2_HANDOFF.md) and [M3](PHASE6D_M3_HANDOFF.md) handoffs.

The user explicitly requested that previously verified tests not be repeated for M4. Acceptance therefore combines the completed M3 full/integration/package gate with the new M4 checks below. This is not a claim that a new full backend run occurred. No production execution, shared runtime, schema, registry or existing evaluator source changed in M4.

## Delivered extraction behavior

Opt-in `tables-openai-v1` and `tables-openai-text-v1` profiles execute the fixed `TABLE_RECONSTRUCTION → TABLE_INTERPRETATION` page plan through the existing coordinator, worker, Responses adapter and atomic publisher. Both are table-only. Reconstruction commits bounded layouts and table/cell evidence; interpretation uses the unique committed same-run/page reconstruction to publish source-local equipment groups and relational candidates citing the immutable cells. Multiple tables share the page's two stages; there is no per-table fan-out or repair call. Empty reconstruction settles interpretation with the normal admission/lease fences and no dependent provider call.

Existing leases, expiry/recovery, cancellation, bounded retry/admissions, usage, historical signing and immutable publication continue to apply. V4 profiles pin table resources/settings independently. Packaged retained source bytes preserve accepted v1/v2/v3 identities and executable compatibility. M3 verified active older runs actually claiming, failing, retrying and publishing; this is not just a snapshot claim.

Native table relationships require a unique dense contiguous pipe/tab grid. Token matches alone cannot prove a PDF layout. Visual or hybrid observations can map registry-valid claims with an explicit page-level visual grounding limit. Literal native evidence and visually reported relationships remain separate. Unknown types, tag-prefix guesses, ambiguous row ownership, unsupported qualifiers and conditional readings do not become confident mapped associations. Multiple tags are detected in the full identity cell even when the model reports just one equipment observation. Distinct conditional values/conflicting association proposals survive deduplication; AF/AT clauses retain their established canonical handling.

Ordinary prose requires a separate existing 6C engineering run. Document summaries still select the latest completed/partially completed run across profiles, rather than merging prose/table results. A newer empty or partial table run can therefore become the document's latest result. Both sets of results remain available through run history and per-run tables, candidates and signed evidence. M3 tested these cases and newer pending/cancelled runs. Extraction creates proposals, not canonical equipment or engineer-approved facts.

## M4 evaluation delivery

New `table_evaluation.py`, `table_evaluation_scoring.py` and `table_eval.py` provide the separate `table-evaluation-v1` scorer and offline CLI, installed as `powerforge-eval-tables`. The frozen 6C scorer, entrypoint, corpus and baseline bytes remain unchanged. The new identity includes its own code and the frozen helpers it reuses; `table_evaluation_v1_identity.json` pins those inputs, corpus and M1/M2 resources without refreshing prior identities.

The [table corpus guide](../evals/tables/README.md) documents 27 independently annotated synthetic cases, 27 gold tables, 146 cells and 73 claims. The fixtures cover all requested engineering families/orientations, ambiguous/conflicting/blank/missing content, repeated tags/headers, merged hierarchical headers, unknown/tag-prefix-only contexts, negative tabular-looking content, several tables on one page and native/visual/hybrid evidence. Twenty-three native artifacts and five PNG artifacts are pinned. Two cases bind the actual processor outputs and original bytes of one positioned PDF. All material is synthetic; no customer or anonymized source is represented as authorized merely by a label.

Matching uses independent source occurrence/anchors, cell coordinates and exact grounded readings before checking meanings. Model IDs, proposed keys and normalized values do not choose matches. Scores cover table/layout/header/orientation correctness, equipment/attribute detection and mapping, exact values/units, source-local association, evidence/locator/citation correctness, duplicate/incorrect claims and UNMAPPED/INVALID retention. Native literal, visual-report and structural reliability stay separate. Missing/failed outputs retain all gold denominators, with explicit null zero-denominator rates and execution/claim coverage. There is no arbitrary accuracy threshold.

The committed scripted report publishes 68 claims against 73 gold claims, with 65 fully correct under this policy. Tables are 26/27 recalled and 26/26 precise; cells/content/spans/headers/evidence are 142/146; orientation is 25/27. Equipment precision/recall are 28/29 and 28/31; attribute detection is 39/42, mapping 37/42 and exact typed values/units 30/34. UNMAPPED retention is 6/7, INVALID 1/1, and duplicates 0/68. No mapped claim is incorrect among the 55 scripted mapped claims. Two overflow failures retain coverage of 25/27 completed cases and 51/54 planned stages.

The wrong-row proposal, mixed-orientation omission, schema failures and unresolved native PDF intentionally prevent a perfect baseline. The PDF gold retains the visible source orientation and mapped engineering meanings: native abstention loses recall instead of redefining gold to match the implementation. The hybrid case maps with native literal proof and explicitly visual relationships. This demonstrates the native-structure limitation on one controlled fixture; representative operational PDF coverage remains unmeasured.

## Actual M4 verification

**100 new tests passed, no skips**, with five existing PyMuPDF/SWIG dependency warnings in **2.46 seconds**:

```sh
.venv/bin/pytest -q tests/test_table_evaluation.py tests/test_table_evaluation_scoring.py --tb=short
```

These test all 27 cases, exact scripted replay, failure/omission denominators, null rates, identity/source/path/annotation tampering, ID renaming, exact BIGINT/Decimal/false/text/enum behavior, wrong meanings/units, swapped rows/columns, content/spans/headers/orientation/reliability, repeated occurrence offsets, wrong groups/equipment/table/cell ownership, forged locators/geometry/text, missing header citations, visual markers, raw/UNMAPPED/INVALID retention, duplicates, empty skips and offline provenance hardening. A subprocess blocks SDK/ORM/worker/broker imports while the CLI evaluates. The new PDF check reproduces the committed native/image hashes using the real renderer. PNG/PDF renderings were visually inspected, including merged and sparse layouts.

Additional new-artifact checks passed:

```sh
.venv/bin/python -m powerforge_extraction.table_eval \
  --corpus evals/tables/v1/corpus.json --output evals/tables/v1/scripted-report.json
.venv/bin/python -m pip wheel --no-deps packages/extraction \
  --wheel-dir /tmp/powerforge-phase6d-m4-wheels
.venv/bin/python /tmp/powerforge-phase6d-m4-verify-wheel.py
.venv/bin/ruff check packages/extraction/src/powerforge_extraction/table_eval.py \
  packages/extraction/src/powerforge_extraction/table_evaluation*.py tests/test_table_evaluation*.py
.venv/bin/ruff format --check packages/extraction/src/powerforge_extraction/table_eval.py \
  packages/extraction/src/powerforge_extraction/table_evaluation*.py tests/test_table_evaluation*.py
git diff --check
```

The direct wheel check imports the new modules from the wheel, checks the installed console-entrypoint metadata and reproduces M4 resource/scorer identities and the complete table report. Its script is a temporary verification artifact, not a repository dependency. The environment has no installed setuptools; an initial non-isolated wheel attempt failed before building. The normal isolated build above succeeded. Generated build directories are removed after verification.

**Carried forward at the user's request:** M3's 1,754-test full backend gate with no skips, real Celery/beat/Redis/PostgreSQL/MinIO/SDK-mock integrations, fresh migration to head 0013, extraction/worker/API wheels, historical/profile/resource identities, complete unchanged 6C replay, OpenAPI reads, dependencies and whitespace checks. The [M3 handoff](PHASE6D_M3_HANDOFF.md) records commands/timing and the final green run. These checks were not rerun for M4. New tests additionally pin unchanged frozen 6C evaluator/corpus/report bytes. M4 adds only offline code, corpus, a console script and documentation; it adds no migration or production dependency.

## Limits and next phase boundary

Scripted results measure deterministic conversion/scoring, **not live OpenAI accuracy**. No paid provider call, new database/worker integration run or frontend/browser test occurred in M4. The table command deliberately has no live flag. A table live harness remains optional and would require separately approved corpus/artifact/page bindings, bounded actual-stage budgets, the existing production coordinator/provider and provenance derived from verified execution. A recording claiming a live origin remains unverified; it cannot set the report's live-quality flag. Existing 6C live infrastructure is unchanged and does not score tables.

Visual transcriptions/relationships remain model-reported with page-level grounding; no independently verified OCR, regions or offsets are invented. Conservative native structure can reduce recall on normal positioned PDFs. The corpus is small and synthetic, with strict literal matching; it does not measure real-document prevalence, every registry type, model discovery or visual transcription quality. Large-page partitioning, multi-page stitching, cross-run identity/deduplication, physical equipment resolution, conflict resolution, canonical writes and engineer verification remain deferred.

Phase 6E OCR/layout, 6F UI/evaluation infrastructure and 6G hardening/freeze are not implemented or authorized by this milestone. XLSX/XLS/XLSM/CSV ingestion remains Phase 6.5 after 6G and before Phase 7. M4 and this final handoff satisfy the implementation gate using the explicitly approved carried-forward verification baseline; user review, commit/push and any merge remain separate steps.
