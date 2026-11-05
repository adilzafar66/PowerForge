# Phase 6D M3 — Production table profiles and orchestration

**Status:** M3 implemented for review. M4 table evaluation/final acceptance has not started; Phase 6D remains incomplete. Authority: [approved plan](PHASE6D_PLAN.md), [6D prompt](prompts/phase-6d-prompt.md), [M1 contracts](PHASE6D_M1_HANDOFF.md) and the reviewed [M2 foundation](PHASE6D_M2_HANDOFF.md). Baseline: `e045b3f452202b1123fcd941784083fcf1392869` on `codex/phase-6d-tables-schedules`.

## Profiles and execution ownership

New `TableProfile` uses `execution-profile-v4` and the fixed `TABLE_RECONSTRUCTION → TABLE_INTERPRETATION` sequence. It is independent of the unchanged 6C EngineeringProfile stage tuple. Production keys are `tables-openai-v1` (native text plus analysis image when available; image-only supported) and `tables-openai-text-v1` (native text required on every selected page). Both report `TABLE_EXTRACTION`. Explicit `tables-test-v1` and `tables-test-text-v1` synthetic profiles report FAKE_TEST; their default provider emits empty observations and never claims engineering accuracy.

The existing profile discovery endpoint advertises the two new production keys alongside the two probes and two 6C production profiles. Extraction stays manually initiated, external processing remains off by default, and an omitted profile still selects infrastructure-fake-v1. API start, retry, cancel, history, tables, candidates and evidence use existing routes. No upload-triggered execution, UI change, new route, schema migration or canonical write is introduced.

Table profiles own table-contained claims and their directly scoped context. Ordinary prose requires a separate 6C engineering run. M2 remains the sole source/meaning/association authority: reconstruction commits layouts and evidence, and interpretation emits relational candidates citing those exact cells without republishing layouts or inventing combined native quotations.

## Bounded requests and committed context

The executor obtains exact pinned page descriptors and performs verified object loading outside metadata transactions. A short metadata transaction validates the selected plan and completed reconstruction, compares the claimed upstream attempt and uses the M2 loader to rederive committed source context. It then renders instructions and a detached context snapshot outside the transaction. A dedicated regression checks both source object reads and request rendering against actual session transaction events.

`committed-table-context-v1` includes only bounded local table/cell/caption/note aliases, original raw readings, admitted orientation, header/span relationships, scoped references, text reliability and structural basis. It excludes database/artifact/evidence IDs, storage keys and source hashes. The transport uses separately versioned table-source-input-v1 and table-upstream-input-v1 envelopes, explicitly marking content untrusted. Field allowlists and nested reliability validation reject foreign properties/objects. Image bytes remain private PNG data URLs with page-level visual limitations. Normal request correlation headers retain the existing work-unit identifier convention.

The existing OpenAIExtractionProvider selects the exact trusted table response model and uses the same Responses SDK parsing, disabled SDK retries, store=false, no model tools, bounded timeout/output and sanitized errors/usage. There is no separate table SDK execution loop. Reconstruction and interpretation cannot fall through to probe/prose schemas. The selected instructions/schema, pinned model/options, roles, modality, context and byte/character limits are checked before SDK I/O. The official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) was consulted; passing SDK transport mocks does not establish live model accuracy or account availability.

Before crossing the provider boundary, the coordinator independently recomputes the bounded committed projection and selected instructions in its short fencing transaction and compares them with the request. Provider I/O follows transaction commit. Correlation records include the exact reconstruction attempt and canonical context hash. The existing independent publisher text-integrity/offset verification remains in place. Table evidence retains M2's distinct literal-text, native-structure and visual-report reliability; no OCR, verified visual coordinates or physical equipment identity is added.

## Planning, retry, empty output and accounting

Both required logical units are created per page. The existing SQL dependency gate dispatches/claims interpretation only after reconstruction succeeds; waiting consumes no admission. Failed reconstruction with an eligible pending retry keeps interpretation waiting. Exhaustion or permanent failure settles blocked interpretation before aggregating the parent. Retry planning uses the existing one-level dependency algorithm. A successful reconstruction survives downstream failure and is reused by automatic/manual interpretation retries. Multiple tables share a single page request at each stage; there is no per-table fan-out, repair call or automatic ordinary-prose pass.

Empty **admitted** reconstruction permits a table-specific optimization after interpretation receives an ordinary budgeted, leased claim. The executor still loads/checks the exact prerequisite, then calls protected empty completion without constructing a provider. The coordinator rechecks profile, stage, token, deadline, active parent, absence of a started provider call and an actually empty committed projection. Normal atomic publication records `output_counts.skipped_empty_tables=1`; no provider-start marker, AI call row or fabricated zero-token usage is created. Unclaimed, nonempty, cancelled and stale attempts cannot use this path.

For P pages, normal execution needs 2P admissions and at most 2P provider calls before retries. Empty pages retain two admissions but need one call. Retrying failed attempts consumes the original pinned budget. API reported_calls/provider_calls_started and per-unit skip markers remain distinct from calls_admitted. Existing aggregate usage stays unknown when admissions exceed reported calls, including deliberate skips; this milestone does not reinterpret that conservative accounting rule. The default 150-admission budget and 50-page bound allow 100 normal admissions plus bounded retries, not unlimited retries for every page.

Global/per-run concurrency, durable notifications, backoff, leases, hard deadlines, expiry-first recovery, append-only attempts, cancellation and stale-publication fences remain shared. Aggregation still refuses terminal completion while any required or optional unit is active. Actual worker-kill/restart tests demonstrate prerequisite reuse and unreported external-call uncertainty; no exactly-once external-call claim is made.

## Limits and configuration

New table-specific settings are passed consistently to API, worker and scheduler through the shared Compose settings anchor and documented in .env.example:

- EXTRACTION_TABLES_MAX_OUTPUT_TOKENS: 32768 by default, capped at 32768.
- EXTRACTION_TABLES_MAX_TOTAL_INPUT_BYTES: 4194304; individual artifacts retain the shared 2000000-byte default.
- EXTRACTION_TABLES_MAX_TEXT_CHARS: 100000.
- EXTRACTION_TABLES_MAX_UPSTREAM_BYTES: 131072; instructions also retain the 131072-byte bound.
- EXTRACTION_TABLES_IMAGE_DETAIL: high; EXTRACTION_TABLES_REASONING_EFFORT: none.

Existing model, page/document/pixel bounds, attempts, admissions, concurrency, timeout/lease/backoff and optional recorded pricing settings are reused and pinned into the profile where material. Table-specific settings do not change accepted probe/6C profile serialization. M1's eight tables/512 total cells, 128 rows/32 columns per table, response/claim bounds and explicit overflow handling remain unchanged. Legal structural capacity is not a promise that a particular model can emit every allowed response inside its output-token budget. Input/context overflow and incomplete responses fail explicitly; nothing is silently truncated.

A measured 512-cell fixture produces **111,637 upstream bytes** and **66,699 instruction bytes**, both within their separate 131,072-byte limits. The default production v4 wire configuration is **3,679 bytes**. These are deterministic payload measurements, not model throughput or accuracy measurements.

## Historical compatibility and reads

Before editing shared fingerprinted files, all seven pre-M3 runtime inputs were copied byte-for-byte into runtime_resources/page_v2 as identity data: profiles, stage_runtime, dependencies, orchestration, execution, production_profiles and the original OpenAI input contract. The already retained page_v1 resources remain unchanged. Accepted engineering runtime v1 uses its original two page_v1 inputs plus the retained shared inputs; runtime v2 uses the retained seven-input snapshot. These archives are never dynamically executed. Existing executable prose/probe branches retain their behavior; new table branches have `table-page-runtime-v1` and their own source/resource fingerprint.

The new runtime rules hash is `d93ed430ac7e18f78e1e9f2160fc019f8fee5ed28a73580f30afd8aed77f82e5`. The new table_execution_v1_identity.json fixture pins v4 wire JSON/hashes, material settings and retained input hashes. Historical v1/v2/v3, M1/M2, registry, prose grounding/interpretation and 6C evaluation fixtures are not refreshed. Tests persist accepted pre-table configurations, then actually claim, fail, retry and publish under all three old profile versions. Resource snapshots alone are not the compatibility claim.

Document summaries keep their existing cross-profile behavior: latest_result is the newest COMPLETED/PARTIALLY_COMPLETED run, while current_run is the newest run regardless of status. A newer partial table run with committed layouts, or a successful empty table run, can become latest_result. This is not a cumulative document-wide view. Both profiles remain accessible through paginated history and each run's candidates, tables and signed historical evidence. Tests cover prose then tables, reversed order, partial/empty table results and newer pending/cancelled runs. Coverage remains per required logical unit, so committed reconstruction is inspectable while failed interpretation leaves the run incomplete.

## Verification and limits

The final full backend gate passed **1,754 tests, no skips**, including **71 new M3 cases**, with six existing dependency warnings in **292.16 seconds**. It covers actual SDK serialization/parsing, all table profile/source modes, limits and opt-in controls, dependency/budget handling, empty skips, atomic table/candidate publication, manual/automatic retry, cancellation, killed-worker recovery, multi-table no-fan-out, cross-profile summary/history and accepted pre-table active configurations.

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:55443/powerforge_phase6d_m3 \
S3_ENDPOINT_URL=http://localhost:59013 S3_PUBLIC_ENDPOINT_URL=http://localhost:59013 \
REDIS_URL=redis://localhost:56393/0 RUN_INTEGRATION=1 \
  .venv/bin/pytest -q --tb=short --maxfail=1
```

The existing discovery assertions were updated for the two additive production profiles, and the M1-only unregistered-profile assertion now checks the separate explicit v4 family. An earlier full attempt had intermittent 6C image-worker and lineage activation failures; both passed in isolation and in the final full gate. Later attempts exposed immediate-admission assumptions in the new synchronous table tests. Their helpers now wait for a planned attempt to admit or settle, while direct negative dependency assertions remain immediate. They do not retry provider calls or weaken production availability, backoff, budget, chronology or lease guards. Safe validation-category notes in the test helper retain diagnostics without source inputs. The final execution/history gate also passed all 28 cases before the full run.

Fresh migration to head 0013, extraction/worker/API wheel builds and direct wheel imports pass. The packaged v4 configuration/archive fixture, unchanged M1/M2 and v1/v2/v3 identities and exact complete 6C scripted report reproduce. All seven retained runtime inputs were compared byte-for-byte with the pre-M3 baseline. The existing OpenAPI table route generates successfully. Ruff, changed-file formatting, dependency and whitespace checks pass. No frontend/browser test or live model evaluation was performed. All provider responses in these checks are authored fixtures or actual SDK parsing over MockTransport; no paid/live provider call is authorized or made. The real integration stack uses disposable tmpfs PostgreSQL/Redis/MinIO, actual Celery worker and beat subprocesses, actual pinned artifacts and signed S3 downloads. Normal development services/data are untouched.

The conservative M2 native-grid recognizer, unknown/conditional interpretation limits and visual grounding limits remain. Representative processed PDF coverage and production model accuracy are M4 evaluation work. This milestone enables an opt-in production execution path and verifies its behavior; it does not complete Phase 6D or claim live extraction quality. The existing 6C evaluator is unchanged and is not a table scorer.

**Stop for M3 review before M4.**
