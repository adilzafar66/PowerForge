# Phase 6C M4 handoff — Dependent page-stage execution

Branch: `codex/phase-6c-engineering-extraction`. Baseline: `da38d0798ef668fd7495f2975ab9c0f4299dc728`, including both M3 review corrections. Latest `origin/main` was refreshed and is already an ancestor. Scope: M4 of [PHASE6C_PLAN.md](PHASE6C_PLAN.md). M5 production OpenAI/profile registration and M6 evaluation remain pending.

## Delivered boundary

The existing coordinator and `execute_unit()` now execute the M1–M3 page stages through the same admission, lease, delivery, retry, telemetry and publication path as infrastructure probes. No alternate scheduler, entity tables, schema migration, canonical writes or public routes were introduced. Migrations 0011–0013, registry-v1, M1/M2 definitions and M3 grounding/conversion resources remain unchanged.

Two explicit synthetic profiles exercise the new path: `engineering-test-v1` selects native text plus analysis image when present (including image-only sources), and `engineering-test-text-v1` requires native text. Both report `FAKE_TEST`, use `deterministic-engineering-v1`, and mark any published candidates synthetic. They can be selected through the existing manual start contract, but are not added to profile discovery. The normal worker's synthetic stage adapter returns valid empty observations and supports the existing failure scenarios; populated engineering observations in tests are scripted fixture responses. This is infrastructure verification, not model recognition or measured accuracy.

Production `engineering-openai-v1` / `engineering-openai-text-v1` are not registered. An engineering OpenAI profile cannot fall through to the legacy probe SDK adapter: the worker explicitly rejects that combination until M5 supplies the stage-aware adapter. Existing infrastructure fake/OpenAI profiles, discovery responses, fake default and external-processing opt-in retain their behavior.

## Planning, prerequisites and terminal states

Run creation pins one completed processing run, selected pages, original artifact IDs and the complete profile before dispatch. Every page has two required logical keys: `EQUIPMENT_RECOGNITION:page:NNNNNN` and `ATTRIBUTE_EXTRACTION:page:NNNNNN`. Each unit's immutable `execution_metadata` records its stage identity and the recognition prerequisite key for its own page. Retries copy that metadata and artifact selection unchanged.

Dispatch applies a correlated database predicate before its bounded selection/limit: pending attributes without committed prerequisite success cannot occupy the notification window. Claim rechecks the prerequisite under the existing parent/admission locks before spending a call admission or taking concurrency. Broker ordering is irrelevant. Recognition success with no mentions still releases attribute extraction, which may retain standalone unmapped observations.

Aggregation first settles pending dependents as FAILED / `PREREQUISITE_FAILED` when no upstream success or active upstream attempt remains. It performs this before checking for active work and finalizing the parent, in the same transaction. A pending automatic recognition retry keeps attributes waiting. Permanent/exhausted upstream failure, budget/provider denial and expired-lease settlement all use this path. Blocked work starts no provider call and consumes no admission.

Manual retry determines eligibility before appending any history. It appends unsuccessful downstream attempts only if the upstream already succeeded or an eligible upstream retry can satisfy the prerequisite. Exhausted recognition cannot burn the remaining blocked attribute attempt history. Successful recognition is immutable and is reused when only attributes fail. Read-side `retryable` flags use the same eligibility rule. Cancellation still settles every waiting/running attempt before the terminal parent and fences late publication.

Recovery retains expiry-first ordering and additionally selects pending unsatisfiable dependencies. Healthy active runs do not consume that recovery window. A regression creates 103 active two-stage runs and verifies expired work, blocked settlement and bounded dispatch all progress past more than 100 healthy/blocked records. The dependency helper intentionally supports this fixed two-stage page plan, not arbitrary DAG scheduling.

## Source I/O and transactions

Claims snapshot verified ownership through M3 `page_spec_for_unit()` and record the unique successful prerequisite attempt ID. The snapshot includes a bounded tuple of exact artifact descriptors, rather than relying on the legacy first-artifact fields. Engineering execution verifies both selected modalities independently via M3 `load_page_sources()` after claim commit. Failed/oversized/corrupt input never falls back to another modality or to a later processing result.

Each source object is loaded once per attempt outside the metadata transaction. Recognition and attribute attempts necessarily reread their pinned page independently. The existing 6A publisher separately re-verifies pinned native text inside its publication transaction; this safeguard is preserved. After source loading, a short transaction loads and verifies completed same-run/page recognition context against those exact bytes. No provider or initial object-storage I/O holds the caller's database transaction open. Heartbeats retain their existing short independent transactions and absolute deadline cap.

The v2 profile pins per-artifact bytes, combined page bytes, actual decoded text length, instruction/upstream-context bytes, image pixels/detail and output tokens. Initial synthetic defaults are the configured 2,000,000-byte per-artifact limit, 4 MiB combined, 100,000 text codepoints, 128 KiB instructions, 64 KiB upstream context, configured 20 million pixels, `high` image detail and 8,192 output tokens. Probe output/image defaults are unchanged. Initial descriptor bounds are checked at planning; actual bytes/dimensions/text and rendered context are checked before provider start. Oversized context fails safely without truncation. M5 must choose and validate production-appropriate bounds.

## Schemas, rendering and provenance

The neutral AI contract accepts an explicitly selected Pydantic response class and has a generic `ExtractionResponse[Result]`; the default remains `ProbeResult`. No extraction/ORM/vendor imports enter the AI package. Execution revalidates the response against the exact planned stage schema, checks output-token usage, then calls the M3 converter. Malformed/overflowed responses, unavailable source references and wrong-stage results fail as `INVALID_PROVIDER_RESPONSE`, retaining valid returned usage and publishing no partial candidates.

`stage_runtime.stage_call()` renders M1 instructions using the pinned registry resources and types from the unique completed recognition output. The upstream input is a bounded, deterministic, response-local-ref-sorted allowlist of raw expressions/tags, mapped type/status and grounding precision. It is separate untrusted request data, never part of trusted instructions; database UUIDs, storage keys, group IDs and offsets are not supplied to the provider. M3 context loading remains the association/grounding authority.

The run's prompt/schema identity represents the complete stage manifest. Actual AICall rows record stage-specific schema versions and hashes of the rendered instructions. Attribute call correlation IDs record the immutable upstream attempt ID and upstream projection hash alongside the producing unit ID. Rendering is reconstructed from immutable outputs/resources, with no mutable "latest recognition" selection. The provider boundary rechecks the selected schema/instructions/upstream projection before setting its immutable started timestamp. An attribute retry reproduces the same instructions, schema, upstream projection and source bytes without resending recognition.

M4 adds `execution-profile-v2` and `engineering-page-runtime-v1`; v1 profile JSON/hashes are byte-identical to accepted 6B fixtures. `read_profile()` dispatches by stored wire version and refuses unknown versions. Engineering profiles pin M1 manifest, M2 interpretation, M3 grounding and runtime source fingerprints, plus every material execution limit. `engineering_execution_v1_identity.json` captures the runtime and both synthetic profile identities against explicit fixture settings. Unavailable resources fail before provider invocation rather than substituting current behavior. After production deployment, changed algorithms need retained versioned readers/resources; editing the v1 files is not a historical compatibility strategy.

## Publication, failures and accounting

Conversion uses the existing 6A output contract and fenced coordinator completion. Failure rolls back both successful-call telemetry and newly inserted output in that transaction; the subsequent failure transaction records only safe failed-call telemetry with known usage. A managed rollback regression verifies the recognition success survives, no attribute output/counts leak, only one failed call row remains, and manual attribute retry restores progress.

One admitted attempt permits at most one provider invocation. A two-page success makes four stage calls; an empty recognition still makes two calls for its page. Waiting dependencies make none. Transient storage access remains retryable `SOURCE_UNAVAILABLE`; corrupted source remains permanent `INVALID_SOURCE_INPUT`. Admissions before failed source loading remain admitted but have no started/reported call, consistent with 6B's honest unknown-usage accounting. Interrupted or cancelled external work retains the existing unreported-call uncertainty; recovery does not fabricate usage or zero charges.

COMPLETED describes successful planned execution, not discovery completeness, source verification or engineering accuracy. Page-level visual results retain M3's explicit limits. No OCR, tables/layout, cross-document identity, reconciliation, revision metadata proposals, frontend or engineer acceptance was added.

## Verification

**1,413 backend tests passed, no skips**, including **38 new M4 cases**, with six existing dependency warnings in **208.86 seconds**. The suite includes all earlier extraction/registry/canonical/storage/worker and data-preserving migration regressions. New cases cover prerequisite gating, two/four actual synthetic stage calls, empty recognition, exact attribute retry context and historical artifacts, exhausted/permanent upstream failures, manual retry eligibility, call budgets, lease recovery, cancellation, duplicate delivery, page/concurrency isolation, 103-run recovery/dispatch fairness, multimodal failure/no fallback, context/input limits, wrong-stage/malformed/overflowed responses, usage retention, managed publication rollback, source read counts, worker provider selection, neutral contract import isolation and byte-identical legacy profile replay.

Both AI and extraction wheels build and import directly from their wheel archives. Runtime and synthetic profile fingerprints reproduce there, as does the legacy probe prompt identity. The pinned runtime rules hash is `2c32d0eac3ddf56e31023e49bf17b2903e592e10bc4270504024bc5e7d0fa8fd`. Ruff, changed-file formatting, dependency and whitespace checks pass. Fresh empty-to-head migration succeeded on the disposable database; no new migration was needed. Generated build directories and disposable services are removed after validation. No frontend/browser test or live-model evaluation was performed. Real OpenAI request/production Celery stage integration remains M5; the full suite's existing broker/beat tests are infrastructure probes.

The disposable Compose project is `powerforge-phase6c-m4`, PostgreSQL database `powerforge_phase6c_m4` on port 55439, Redis 56389 and MinIO 59009, all with tmpfs test data. Normal development services/data are untouched. New M4 tests use real database transactions and in-memory verified source fixtures; the inherited full suite additionally exercises real S3, Redis/Celery/beat and migration checks. No paid/live provider call is authorized or performed.

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:55439/powerforge_phase6c_m4 \
S3_ENDPOINT_URL=http://localhost:59009 S3_PUBLIC_ENDPOINT_URL=http://localhost:59009 \
REDIS_URL=redis://localhost:56389/0 RUN_INTEGRATION=1 \
.venv/bin/pytest -q --tb=short
```

## Next: M5

Extend the existing OpenAI adapter to use the trusted request's selected schema, named source roles, separate untrusted upstream context, image detail and output bounds in one Responses call. Keep SDK retries disabled, safe error/usage handling, no tools, `store=false` and existing opt-in controls. Register/advertise the production profiles only with that adapter in place. Verify exact requests with mocked SDK responses and actual broker/worker/beat publication on disposable services; preserve legacy wire hashes. M6 supplies corpus/evaluation and any separately authorized live-model evidence.
