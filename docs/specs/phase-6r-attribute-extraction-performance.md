# Phase 6R — Attribute Extraction Performance Optimization Specification

**Status:** Proposed implementation specification\
**Prepared:** 2026-11-22\
**Target repository:** `adilzafar66/PowerForge`\
**Suggested repository location:** `docs/specs/phase-6r-attribute-extraction-performance.md`\
**Scope:** Stage 2 (`ATTRIBUTE_EXTRACTION`) latency, OCR input efficiency, output efficiency, page-level throughput, observability, and related reliability.\
**Baseline inspected:** branch `phase-6r-unified-typed-value` at `63c3004090148a4dff3a0a2db110150f02fe1c7f` (2026-11-20). This is **not** a claim that this commit is the developer's current HEAD.

> **Codex instruction:** Treat this document as the desired behavior and acceptance contract, not as an assertion that file paths, branches, migrations, APIs, or feature fixes have remained unchanged. Inspect the **actual checked-out HEAD and runtime configuration** before coding. If the server-owned Stage 2 response-identity fix or other Phase 6R reliability changes have landed since the inspected baseline, preserve and build upon them. Do not revert them or create parallel legacy flows.

---

## 1. Executive decision

Improve the **existing two-call-per-page** design:

1. Stage 1 recognizes equipment.
2. Stage 2 extracts relevant registry-linked attributes and raw unmapped observations using the exact Stage 1 prerequisite.
3. PowerForge independently admits, grounds, normalizes, audits, and publishes results.

**Do not** add a third sequential AI call, replace the canonical registry, change engineering-model publication semantics, or trade source fidelity for speed. The performance work is **measurement-driven**, with reversible, individually benchmarked optimizations.

Recommended order: **P0 current-code inventory → A instrumentation → B reasoning evaluation → C OCR/context optimization → D prompt/output efficiency → E worker concurrency → F timeout/reliability → G integrated evaluation and handoff.** E may be implemented in parallel after A; evaluate each major optimization independently before combining it with others.

## 2. Problem statement and observed evidence

- Schneider panel `101235_Schneider_panel.pdf`, page 1: Stage 2 responses have taken roughly **54–90 seconds**; OCR-enabled attempts have reached the **~100-second** OpenAI request timeout.
- A documented attempt used `gpt-6-luna`, **17,944 input tokens** (**17,941 cached**), **7,273 total output tokens**, **12,462 response bytes**, and about **53.96 seconds** recorded AI-call latency. These values describe that attempt only; total output includes possible reasoning tokens and the recorded duration may include local work.
- The drawing is visually dense, has very limited usable native engineering text, and benefits from local OCR. OCR potentially adds numerous positioned readings, links, overlap/uncertainty metadata, and layout structures while the image is still sent at high detail.
- Existing default configuration (at inspected commit): `EXTRACTION_MODEL=gpt-6-luna`, `EXTRACTION_MAX_OUTPUT_TOKENS=16384`, `EXTRACTION_TIMEOUT_SECONDS=100`, `EXTRACTION_MAX_CONCURRENT_PER_RUN=2`, `EXTRACTION_MAX_CONCURRENT_GLOBAL=4`; the default worker process starts with `--concurrency=1`.
- Stage 2 receives the applicable **attribute catalog per recognized equipment type**, page image, OCR/native readings, spatial layout, and recognition result. It is instructed to inspect all relevant optional/required attributes, produce typed values and citations, and distinguish extracted vs inferred proposals.
- The previous malformed `upstream_hash` incident is a **different reliability issue**. This plan must not reintroduce model-generated trusted identities if they have already been made server-owned.

**Hypotheses (not yet proven by controlled profiling):** large output and medium reasoning dominate single-call latency; OCR increases prompt complexity and/or output/reasoning; the single-slot worker serializes tasks across pages. The design must establish causes with measurements rather than assuming the hypotheses are correct.

## 3. Goals, targets, and success definitions

### 3.1 Functional goals

- Reduce **provider-only Stage 2 latency**, especially with OCR enabled.
- Reduce **full extraction operation wall time** for multiple pages **after enrichment**, by exploiting safe cross-page parallelism.
- Preserve or improve attribute recall, type/key correctness, equipment ownership, evidence provenance, and normalization correctness.
- Keep all raw Stage 2 responses and source facts under existing audit, retention, and immutability rules.
- Provide enough telemetry to explain slow, incomplete, timed-out, and successful attempts.

### 3.2 Provisional performance targets (not promises)

| Measure | Aspirational target | Notes |
|---|---:|---|
| Successful Stage 2 median, representative pages | 30–45 s | Separate OCR-enabled and OCR-disabled populations; revise from baselines |
| Stage 2 p95 on sufficiently sampled workload | <80 s | Report sample size and confidence limits; do not compute meaningful p95 from a handful of calls |
| Representative 10-page full two-stage run | <5 min | **After enrichment**, with safe concurrency; include queue, retries, both stages, and publication |
| OCR-enabled timeout frequency | Material reduction versus baseline | Measure failures, not just successful calls |
| Engineering correctness | No confirmed wrong critical-value regression | Independently gold-scored, not inferred from `MAPPED` status |
| Attribute recall and provenance | No material loss | Define comparison thresholds before evaluating changes |

Treat these as **decision targets**, not unconditional release blockers if the measured engineering trade-offs do not justify them. Explicitly report unmet targets.

### 3.3 Definitions

- **Provider duration:** monotonic wall time surrounding the `responses.create()` attempt, including network wait, excluding request preparation, response admission and publication.
- **Stage 2 work-unit duration:** start of claimed work unit through final terminal state; record its queue time separately.
- **Page completion duration:** Stage 1 and Stage 2 plus dependencies, publication, retries, and any queue delay; source enrichment measured separately.
- **Document completion duration:** wall time for all selected pages through completed extraction, with failed/skipped pages shown; do not silently exclude failures.
- **Visible output tokens:** `output_tokens - reasoning_tokens` **only if both are provided and consistent**; otherwise null. Not equal to JSON bytes or local token estimates.
- **Quality pass:** reviewed source-grounded correctness, including matched equipment/attribute occurrences. A higher mapped percentage alone does not demonstrate correctness.

## 4. Non-negotiable design invariants

1. Stage 1 → Stage 2 dependency remains pinned to the **exact committed recognition result** and page/source identities. Server-owned identity fields, if already implemented, remain server-owned. Never auto-correct a model's arbitrary hash or accept mismatched identities by prefix.
2. The original provider response is retained unchanged under existing audit rules; the accepted domain assertion/result is stored separately with versioned identity. Avoid recording sensitive raw content in routine telemetry.
3. Preserve `EXTRACTED` vs `INFERRED`, typed `proposed_value`, source `raw_value` / `raw_label` / `raw_unit`, source `value_form`, alternate representations, and inference provenance.
4. Maintain assertion-level quarantine, conservative source-fidelity checks, equipment association, exact allowed-unit normalization, and immutable/atomic publication. **Performance is not permission to relax mapping safeguards.**
5. Never invent, silently discard, merge, or alter different equipment occurrences, conflicting ratings, qualifiers, OCR alternatives, or model identifiers.
6. Maintain original source evidence locators. Any compact visual/text presentation must have a deterministic, testable relationship to pinned original readings and offsets.
7. No hidden truncation of selected pages, OCR readings, attribute catalogs, or AI output to hit token or latency goals. If a bound is exceeded, retain an explicit diagnostic and fail/abstain safely.
8. Preserve all existing provider-call budgets, unknown-outcome handling, tenancy/authorization, storage access restrictions, retry fences, and leases.
9. Changes to model settings, prompts, transport schemas, input projections, or behavior must be included in immutable **versioned execution identity**. In-flight runs cannot silently switch policies.
10. All live OpenAI tests incur cost: **do not run paid live evaluations without explicit operator authorization and a documented call/price budget**. Offline tests and fixtures should run freely.
11. This is a development-stage system: preservation of disposable **legacy test data** is not a requirement. Reproducible clean schema creation, new-run audit integrity, and secure current data handling remain requirements.
12. Do not broaden this initiative into the separate engineering **mapping-reliability** correction (series rating, OCR grounding, rounded dimensions, descriptors, voltage conventions), other than measuring those behaviors and preventing regressions. Coordinate on shared files rather than mixing changes.

## 5. Current code inventory and required preflight (P0)

Inspect and cite exact file/line positions from checked-out HEAD before modifying code. The following paths existed at the inspected baseline; adapt only after verifying them:

| Concern | Expected files |
|---|---|
| Stage 2 prompt, model/pinned resource manifest, schema projection | `packages/extraction/src/powerforge_extraction/extraction_profile.py`, `prompts/attribute_extraction_v8.txt` |
| Request construction and compact provider view | `packages/extraction/src/powerforge_extraction/stage_execution.py` |
| Stage contracts and equipment-conditioned attribute catalog | `packages/extraction/src/powerforge_extraction/stage_contracts.py` |
| OpenAI transport and usage parsing | `services/extraction-worker/src/extraction_worker/openai_extraction.py` |
| Provider-neutral usage contracts | `packages/ai/src/powerforge_ai/extraction.py` |
| Work-unit execution, audits, publication | `packages/extraction/src/powerforge_extraction/execution.py`, `response_audit.py`, `publication.py`, `publication_records.py` |
| Coordinator/dispatch, admission, retry, timing | `packages/extraction/src/powerforge_extraction/orchestration.py` |
| OCR/native source alignment | `packages/document-processing/src/powerforge_document_processing/layout_readings.py`, `layout_derive.py` |
| Pinned enrichment preparation/sources | `packages/extraction/src/powerforge_extraction/enrichment_prepare.py`, `pinned_sources.py` |
| Runtime settings | `packages/shared/src/powerforge_shared/config.py`, `.env.example` |
| Worker runtime | `services/worker.Dockerfile`, `docker-compose.yml`, `services/extraction-worker/src/extraction_worker/celery_app.py` |
| Debugger/backend | `tools/extraction-debugger/` |
| Benchmark/gold | `evals/phase6r/` and `tests/` |

**Before implementation:**

- Confirm the actual HEAD SHA/branch, main base, schema versions, prompt versions, active OpenAI model, live server-owned identity fix, current runtime worker concurrency/replica count, and any pending mapping-reliability changes.
- Check whether the inspected branch has already merged; work on a **new clearly named performance branch** based on the intended integration base, not a stale SHA. Recommended name: `phase-6r-extraction-performance`.
- Confirm whether OCR is manually enabled, selected automatically, or sourced from a previously pinned enrichment run. Do not assume switching OCR mutates an existing immutable run.
- Confirm current database tables/types and existing instrumentation; avoid redundant migrations or parallel telemetry implementations.
- Inspect the current scheduler/celery deployment rather than assuming `--concurrency=1` applies to a customized running service.
- Produce `implementation-inventory.md` in an appropriate documentation folder or include an inventory in the first PR, noting **actual divergences from this specification**.

## 6. Milestone A — Instrumentation and reproducible baseline

**Priority:** P1 / mandatory first.\
**Purpose:** Separate network/model latency, input complexity, output generation, local validation, and queueing with minimal, safe overhead.

### A1. Time the actual boundaries

Use `time.perf_counter_ns()` or equivalent monotonic clock for elapsed duration; use timezone-aware UTC timestamps for persisted event times. Do not derive sub-second duration by subtracting wall clocks across processes.

Measure, when applicable:

- `queue_wait_ms`: enqueued/eligible to actual start (distinguish initial queue wait from per-retry wait).
- `source_load_ms`: bound source loading and verification.
- `request_build_ms`: page projection, provider-view serialization, schema/transport preflight.
- `provider_call_ms`: exact SDK network call boundary, **including failed/timeout attempts** where elapsed timing is available.
- `admission_ms`: envelope parsing, assertion admission, and quarantine.
- `localization_normalization_ms`: source evidence localization, value proposal validation, publication observation construction.
- `audit_store_ms`: retained-response write and metadata handling.
- `db_publish_ms`: fenced database stage completion/atomic publication.
- `attempt_total_ms`: work-unit execution excluding queue wait.

These phases may overlap in the implementation; **do not add them together unless the boundaries are nonoverlapping**. If only combined publication timing is feasible, name it accordingly rather than fabricating subdivisions. Record failure-stage and missing reasons where data cannot be captured.

### A2. Model usage details

Extend usage telemetry with nullable fields:

- `input_tokens`, `cached_input_tokens`, `output_tokens` (already exist, preserve semantics).
- `reasoning_tokens` from `response.usage.output_tokens_details.reasoning_tokens`, when present.
- `visible_output_tokens` derived conditionally and validated (`0 <= reasoning <= output`).
- `service_tier` if supplied by the provider; model name and effective reasoning effort.
- Provider response status (`completed`, `incomplete`, refusal, timeout, etc.) in existing bounded diagnostic taxonomy.

Do **not** equate absent values with zero. On provider timeout the response may contain no usage fields; still preserve measured elapsed time and failure class. The SDK/adapter should never print exception messages containing raw document/source data.

### A3. Input complexity summary

At the **exact serialized provider request boundary** collect structured counts and byte lengths, without copying content into telemetry:

- Request JSON/body bytes; encoded image bytes; image dimensions; image detail.
- Native vs OCR reading counts, total reading text characters, alternate reading count, uncertain/conflicting overlap count.
- Line/table/cell/order/overlap counts from layout.
- Equipment count, distinct eligible equipment-type count, registry definition count, catalog JSON bytes, recognized equipment JSON bytes.
- Page/source-context JSON bytes, prompt/instructions byte count, schema byte count; overall transport bytes.
- Profile/input/prompt/schema hashes for correlation (where already part of pinned identities).

Prefer bounded integer columns or a typed, versioned JSONB metrics object; specify maximum metrics payload size, nullability, and indexes. Do not persist arbitrary request text, model-generated reasoning content, original images, or OCR text in metrics. The existing authorized debugger can retrieve retained originals using the audited path.

### A4. Persist and display metrics

Use the existing AI-call/work-unit persistence where feasible. Add an additive migration **only if** existing storage cannot accurately express these fields. Ensure timings are available for both successful and failed attempts, including timeout and refusal, without degrading retry/lease behavior.

Add a compact **Performance** section to the existing Extraction Debugger, showing provider/local timing, token breakdown, input counts and dimensions, effective model/effort, attempt outcome, and whether timing/usage is unavailable. Show separate OCR status and source-reading counts; do not infer OCR from a single global toggle.

### A5. Baseline capture

Create a reproducible, private baseline report for:

- Schneider page with the exact selected enrichment **without OCR**;
- Schneider page with selected enrichment **with OCR**;
- at least one dense schedule, one native-text engineering page, and one diagram-heavy page;
- optional ten-page document after source enrichment.

Offline: generate and inspect provider-view request JSON locally for byte/count comparisons; validate source identities and no missing readings. Live: only after authorization, run a bounded baseline; record actual model/settings, sample size, cold/warm caching, success/failure, p50 where meaningful, latency and all token fields. **Never claim a precise p95 from an insufficient sample.**

### A6. Required tests / exit gate

- Offline unit tests for monotonic timing, nullable usage, reasoning-token arithmetic, request-byte counters, bounded metrics, and redaction.
- Mock provider tests for success, timeout, incomplete, invalid response, and absent/invalid usage subfields.
- Integration test for failed-call telemetry and DB audit/publication rollback.
- Debugger tests for null states, large counts, and restricted read access.
- Baseline report has actual counts/bytes and explicit unknowns.

**Gate A:** A reviewer can identify the timing and request-size difference between OCR-on and OCR-off attempts without guessing. Changes do not alter extraction outputs or admission policy.

## 7. Milestone B — Explicit reasoning effort and controlled selection

**Priority:** P1; implement after A.

### B1. Profile and transport contract

Introduce a **Stage 2** reasoning-effort setting, pinned within the execution profile. Suggested external configuration name: `EXTRACTION_ATTRIBUTE_REASONING_EFFORT`; supported initial variants `none`, `low`, `medium` for the currently selected model. Default remains `medium` until benchmark approval. Do not silently modify Stage 1's reasoning configuration. If independent Stage 1 configuration is subsequently needed, design it explicitly.

- Validate compatibility against the configured model/API before sending; fail early and safely on unsupported combinations.
- Store the **effective setting** in run profile, stage request identity, audit metadata, and debugger.
- In `openai_extraction.py`, pass Responses API `reasoning: {"effort": <pinned value>}` for Stage 2 and include the setting in request validation.
- Cover model SDK transport semantics using mocked HTTP tests. Avoid hardcoding an assumption that the future default will always be medium.
- If changing request schema/profile requires a version bump, update the associated manifest identities and tests atomically.

### B2. Controlled benchmark

Compare baseline `medium`, candidate `low`, and candidate `none` on the same exact pinned sources using identical image detail, prompt, output schema, and request budget. Model/SDK/service tier should remain constant per comparison where feasible.

Record: provider duration, p50 and range, reasoning/visible tokens, accepted/quarantined assertions, exact attribute and ownership matches, evidence localization, wrong critical values, omitted attributes, and incomplete/timeout counts. No special allowances for a faster run that drops material attributes.

Prefer selecting **low** if it materially lowers latency without breaking quality. Select `none` only if it satisfies the same gates; retain medium if lower effort causes mistakes or omissions. A faster but lower-quality setting is **not** an acceptable default.

### B3. Exit gate

- Mode is pinned and observable; mocked transport tests pass.
- The selected setting and supporting benchmark results are documented.
- Incomplete response frequency and assertions-per-page are not materially worse.
- No uncontrolled live calls or automatic effort downgrade on retries.

## 8. Milestone C — OCR-aware compact source context, with source fidelity

**Priority:** P1/P2 based on A baseline.\
**Purpose:** Reduce input complexity **without** removing engineering facts or turning visual citations into falsely verified text evidence.

### C1. Measure before redesign

From A, quantify the actual contribution of `page.readings`, `layout`, `readings_sources`, tables/overlaps, and catalog to bytes/tokens. Compare OCR-on/off to determine whether OCR contributes excessive reading tokens, uncertainty, or layout links. If OCR input is already small and model reasoning dominates, record that result and **do not undertake a high-risk rewrite merely for theoretical savings**.

### C2. Define a deterministic `compact-page-v2` provider view

Propose grouping **safe** contiguous readings into lines or table cells using existing source-supported geometry, engine lines, and verified reading-order links. Example provider view (illustrative; precise contract to be proposed before implementation):

```json
{
  "groups": [{
    "group_ref": "g12",
    "kind": "LINE",
    "text": "SYSTEM: 208Y/120V 3Ph 4W 60Hz",
    "members": [
      {"reading_ref": "q10", "start": 0, "end": 7},
      {"reading_ref": "q11", "start": 8, "end": 17}
    ],
    "region": null,
    "issues": []
  }]
}
```

**Illustration only:** the offsets and counts shown are not real source spans. Real offsets must be exact by construction, including separators, Unicode, punctuation, and whitespaces. Do not use the above example directly as a test fixture.

Design requirements:

- Every emitted source word/reading remains accounted for by an original pinned `reading_ref`. Preserve exact text, modality, uncertainty flags, and **every independent occurrence**.
- Group only when deterministic spatial/order evidence is strong and no contradictory/ambiguous reading fusion is introduced. Preserve ungrouped readings when uncertain.
- Never concatenate unrelated rows, columns, phases, devices, or labels into a fact that looks like one value.
- Do not collapse conflicting native/OCR readings; keep alternatives and conflict flags readable.
- Group text and offset maps must be reproducible byte-for-byte from pinned inputs; input view has its own version and hash.
- Maintain original layout table/row/column membership or an equivalent verified interpretation context. Grouping must not manufacture an equipment association.
- Apply explicit size/complexity bounds and fail with diagnostics when exceeded; no hidden clipping, sampling, or cap-based omission.

### C3. Evidence contract

**Preferred initial approach:** keep the existing Stage 2 `READING`/`QUOTE`/`VISUAL` citation types and **canonical original reading refs**. Group text is only an economical display/interpretation aid; the model can still cite individual `q` refs advertised as source members. If the proposal requires citation of a whole group, introduce a separate versioned, source-mappable citation type only after a design review; do not silently overload `READING` with group IDs.

Preserve the current evidence localizer's independent verification against pinned artifacts. An OCR-derived resolved text span is distinct from a model-reported visual region. Never upgrade `VISUAL_REPORTED` to `RESOLVED` merely because grouped text or a model quote appears plausible.

### C4. Payload reduction candidates (independently benchmark)

1. Replace repeated per-word coordinates with group-level region and selectively retained member geometry **only when exact evidence mapping is preserved**.
2. Reduce redundant layout/order representation when deterministic grouping already expresses supported relations.
3. Eliminate redundant identical native/OCR *presentation* only when proven to be the same occurrence; preserve both original witnesses in source artifacts and all uncertainty.
4. Re-express stable metadata and column names compactly; preserve meaning and reference identity.
5. Keep `high` image detail in the primary benchmark; evaluate supported alternate image detail only as a separate controlled experiment if payload analysis justifies it.
6. Preserve stable prompt/schema prefix when possible to maximize eligible caching; measure cached input tokens rather than assuming prompt-cache savings.

### C5. Tests, versioning, gate

- Property/fixture tests for round-trip source coverage, unique ref mapping, exact substring/offsets, conflicting OCR/native readings, repeated values, multiline notes, table headers, rotated/unsupported text, overlapping equipment, and missing geometry.
- Fuzz or property-based invariant checks for deterministic serialization and no source drops/duplicates.
- Pinned Schneider OCR-on/off fixtures; verify `208Y/120V`, `30kA SYMS. SCCR`, `System Ampacity: 800A`, and the enclosure dimension pairs remain present in the provider view, with correct source linkage. Do not label them mapped solely based on view presence.
- Update `ATTRIBUTE_INPUT_VERSION`, prompt instructions, profile resource hashes, and stage transport tests as required.
- Benchmark independent C-v2 vs C-v1 performance and quality; revert if no meaningful advantage or a provenance regression occurs.

**Gate C:** Compact input can be reproduced and source-grounded exactly; independent annotations confirm no material loss of value discovery, ownership, or evidence correctness. Meaningful latency/token improvement is demonstrated or C is not promoted.

### Milestone C2 — Stage 2 source modality

C2 adds opt-in readable hybrid, image-only and readable text-only configurations. V1 remains the production default and V2 the existing comparator. Offline payload and evidence replay precede a separately authorized live gate. See the [C2 specification](phase-6r-source-modality-optimization.md) and [evaluation, examples and reproduction commands](../../evals/phase6r/ATTRIBUTE_SOURCE_MODALITY_EVALUATION.md).

### Milestone D0 — Attribute prompt and engineering guidance

D0 separates the universal Stage 2 prompt, source-format guidance, equipment guidance, and registry notes. New admissions can opt into a prompt-only or consolidated candidate. Historical profiles retain their original prompt, catalog, and request digest. See the [D0 specification](phase-6r-d0-prompt-refactoring.md) and [offline evaluation](../../evals/phase6r/ATTRIBUTE_PROMPT_REFACTORING_EVALUATION.md).

## 9. Milestone D — Attribute output optimization and response reliability

The [Milestone D reliability correction](phase-6r-attribute-output-optimization.md#reliability-only-correction) carries forward server-owned assertion IDs and bounded raw-unmapped admission with the original descriptive provider fields and evidence shapes. The compact-output experiment is retained for historical replay after failing its coverage gate. `legacy-v7` remains the default. The [offline evaluation and proposed live procedure](../../evals/phase6r/ATTRIBUTE_OUTPUT_OPTIMIZATION_EVALUATION.md) document the implementation and evidence required to consider promotion.

## 10. Milestone E — Parallel page-level execution

**Priority:** P1 for multi-page throughput; independent of C/D after baseline metrics.

### E1. Configurable worker slots

The inspected default worker Docker command has `--concurrency=1`. Make the extraction worker's real process concurrency configurable **without** globally changing source-enrichment, document-processing, or unrelated workers.

Suggested deployment-level option: `EXTRACTION_WORKER_CONCURRENCY=2`. Ensure startup/Compose interpolation works in the actual image/entrypoint; prefer environment-driven startup scripts or Compose command rather than assuming shell expansion inside exec-form commands.

Initial rollout: **two worker slots**, with existing coordinator limits (`per-run=2`, `global=4`) unchanged unless profiling demonstrates a safe need. Inspect effective running process slots and replica count; report any mismatch between configuration and actual Celery capacity.

### E2. Coordinator dependency and queue safety

- Each page's Stage 2 must wait for its **own** successful committed Stage 1. Different pages are independent and may execute concurrently.
- Preserve global/per-run concurrent admission gates, provider-call budgets, authorizations, leases, heartbeat, idempotency, and response audits.
- Protect against duplicate concurrent dispatch, worker redelivery after loss, stale attempts, and conflicting publication.
- Validate DB pool capacity and storage connections for actual worker slots; avoid exceeding provider concurrency/rate limits.
- Check whether the shared queue with document classification causes head-of-line blocking. If necessary, separate queues/workers **without** breaking existing routing or adding unsafe concurrency.
- Avoid holding database transactions over remote provider calls.

### E3. Integration scenarios

Test on disposable PostgreSQL/Redis/MinIO:

- Two pages at Stage 1 concurrently; each transitions to its own Stage 2.
- One page retries while another publishes successfully.
- Out-of-order stage completion and concurrent state aggregation.
- Duplicate/redelivered task; lease expiry; interrupted worker; worker restart; delayed/unknown provider outcome.
- Rate limit and provider timeout under two active slots.
- End-to-end 10-page (or representative synthetic multi-page) workload with worker=1 vs worker=2; optionally test 4 only within safe documented limits.

**Gate E:** No duplicate publication, source mixing, or budget violation; measured multi-page throughput improvement with controlled failure and provider-rate-limit behavior.

### Implementation and verification

The extraction service alone reads `EXTRACTION_WORKER_CONCURRENCY` from Compose. It starts a prefork worker with one slot by default and accepts explicit settings from one through four. Source enrichment, classification routing, the scheduler, and other workers keep their current deployment configuration. The extraction worker still consumes both classification and extraction queues. The per-run limit remains part of each admitted run's profile, and the global coordinator default remains four.

Use real Celery subprocesses, Redis, PostgreSQL, and MinIO with a loopback-only test Responses endpoint. The test entrypoint injects a dummy API credential, disables proxy and redirect handling, and checks every destination before sending. It exercises the real transport, admission, database settlement, and audit byte storage. The isolated scratch bucket stands in for the restricted audit bucket so this test can focus on execution and publication. Existing audit access and retention tests remain separate.

Run the two-slot correctness and failure gates before measuring four slots. The three benchmark configurations are one prefork slot with per-run/global limits of 2/4, two slots with 2/4, and four slots with 4/4. Use fresh runs in every arm, with the applicable pinned limit. Keep the source snapshots, provider inputs, model settings, and response timing identical. The benchmark profile uses `compact-page-v1`, `core-catalog-v1`, `server-owned-assertions-v1`, and medium reasoning.

Measure document extraction from operation admission to terminal run, including the queue and settlement. Measure source preparation separately and reuse the prepared snapshot across all trials. Define queue wait from readiness to claim, using the page's committed recognition result to establish Stage 2 readiness. Report prefork task busy time as a share of available slot time and use request intervals recorded at the HTTP endpoint to verify actual provider overlap. Count PostgreSQL wait samples and observe per-process backend connections, heartbeat wake-up and renewal times, and the longest gap between completed reconciliation tasks. Keep existing production leases, timeouts, budgets, and routing.

On disposable services with `RUN_INTEGRATION=1`, run the gates, then run the opt-in benchmark:

```sh
pytest tests/test_extraction_parallel.py -k 'not matched_prefork_benchmark'
RUN_EXTRACTION_BENCHMARK=1 pytest -s tests/test_extraction_parallel.py -k matched_prefork_benchmark
```


### Offline benchmark results — November 25, 2026 Pacific

Three repetitions per configuration used a synthetic ten-page engineering PDF, one prefork worker replica, and a fresh Redis queue namespace per trial. Source preparation took 1.2 seconds once. Each run reused that snapshot and used the same local HTTP delays of 1.15 seconds for recognition and 2.35 seconds for attributes. All page/stage request digests matched across arms. For measurement, all arms used a six-second lease and one-second reconciliation and redispatch intervals. Production settings were untouched.

Times below are medians unless noted. Worker utilization is mean task busy time across repetitions, including reconciliation and duplicate-delivery handling. Efficiency is the speedup divided by the number of slots. Queue values are the medians of the per-trial medians.

- **One slot, per-run 2, global 4.** Three runs took 40.91, 40.90, and 40.95 seconds. Median throughput was **14.67 pages/min** at **1.00×** baseline and **100%** scaling efficiency. Peak overlap was one call and worker utilization was **95.8%**. Recognition and attribute queue waits were **5.92s** and **17.59s**. Thirty heartbeats renewed successfully. Maximum wake-up delay was 5 ms, with renewal transaction time of 21 ms typical and 73 ms maximum. The sampler observed one worker connection at peak and zero samples with a database lock wait. The longest measured reconciliation gap was 12.90s.
- **Two slots, per-run 2, global 4.** Three runs took 21.66, 21.42, and 21.47 seconds. Median throughput was **27.95 pages/min**, **1.91×** baseline at **95.3%** scaling efficiency. Peak overlap was two calls and worker utilization was **91.5%**. Recognition and attribute waits were **2.84s** and **7.82s**. Thirty heartbeats renewed successfully. Maximum wake-up delay was 5 ms, with renewal transaction time of 24 ms typical and 48 ms maximum. The sampler observed two worker connections at peak and 11 samples with a database lock wait. The longest reconciliation gap was 6.76s.
- **Four slots, per-run 4, global 4.** Three runs took 12.74, 12.67, and 12.70 seconds. Median throughput was **47.24 pages/min**, **3.22×** baseline at **80.5%** scaling efficiency. Peak overlap was four calls and worker utilization was **79.0%**. Recognition and attribute waits were **1.64s** and **2.77s**. Thirty heartbeats renewed successfully. Maximum wake-up delay was 5 ms, with renewal transaction time of 18.5 ms typical and 32 ms maximum. The sampler observed four worker connections at peak and 20 samples with a database lock wait. The longest reconciliation gap was 3.12s.

The typical renewal times above are medians of the per-trial medians. Lock counts are 100 ms PostgreSQL samples with an observed wait. The sampler also saw transient worker transactions between statements. Provider calls ran outside the claim and settlement transactions. Every observed worker connection was checked out in its originating process.

All nine runs completed, with **90 pages, 180 successful stage publications and 90 matching retained Stage 2 response digests**. There were no retries, lease denials, duplicate publications, or page/prerequisite mismatches in the timed runs. In the two-slot fault tests, Stage 2 entered the HTTP endpoint while another page was still in Stage 1, a fifth claim was refused while four units from multiple runs were active, and a 429 was retried within budget while the document made progress. The timeout and killed-worker cases preserved unknown-outcome protection. An induced short run-row lock delayed a renewal and recovered. A lock held through expiry denied stale publication, and reconciliation settled the affected attempts without a second provider dispatch.

The mixed-queue probe published a document while a test classification task held one of the two worker slots. That verifies progress with one slot free. At full occupancy, reconciliation still shares the consumer pool and waits for a slot to open. The timings above are the observed reconciliation gaps for this workload, with a one-second test cadence. The results do not require queue separation, additional database connections, or longer leases.

Verification passed 462 focused backend and integration tests on PostgreSQL, Redis, and MinIO. The nine-trial benchmark ran separately and passed. Docker smoke checks observed one and two actual worker children with both configured queues. Three additional existing OCR worker tests stopped during fixture setup on this host because the expected Linux Tesseract installation was unavailable.

**Initial deployment recommendation:** Opt in to two prefork slots with per-run/global limits of 2/4. This keeps the existing coordinator limits and uses a configuration with measured overlap, near-linear local scaling, and successful recovery under fault injection. Keep the production default at one slot. Four slots improved local throughput and lowered slot utilization. Actual provider latency, rate limits, and mixed-queue load will determine live throughput and recovery delay. Use a separately authorized live comparison before drawing a production scaling conclusion.

### Controlled live benchmark — November 25, 2026 Pacific

The live comparison used PDF pages 8–16 of a private Schneider panel drawing and the Milestone E implementation at `71bdfa7`. One local preparation pass took 7.7 seconds, including document processing and storage. The existing source policy selected native input on eight pages and local OCR on page 11, a vector-only continuation sheet. Every arm used the same prepared artifacts, a fresh operation and an isolated queue namespace. PostgreSQL, Redis, audit storage and one prefork worker replica were disposable.

The shared profile used GPT-6 Luna on the Standard tier, `compact-page-v1`, `core-catalog-v1`, `server-owned-assertions-v1`, and medium Stage 2 reasoning. All arms used a 100-second provider timeout, 30-second leases and a 15-second reconciliation cadence. The authorized matrix allowed 54 HTTP calls, up to 18 per arm, with both coordinator and client retries disabled. The browser-facing workflow and production defaults stayed as configured.

- **One slot, per-run 2, global 4.** Run `7884fc74` completed in **677.95 seconds** with **9/9** pages processed and **0.80 completed pages/min**. Peak provider overlap was **one** call and worker utilization was **97.7%**. Median readiness-to-claim wait was **107.67s** for recognition and **314.57s** for attributes. Median provider time was **31.87s** and **37.95s**, respectively. All 18 stage results published and all nine Stage 2 audits matched the received output digests.
- **Two slots, per-run 2, global 4.** Run `aad0afd6` reached terminal status in **330.00 seconds** with **8/9** pages processed and **1.45 completed pages/min**. Peak provider overlap was **two** calls and worker utilization was **91.8%**. Stage 2 on one page overlapped Stage 1 on another by 23.6 seconds. Median queue wait dropped to **29.62s** for recognition and **127.13s** for attributes. Median provider time was **29.44s** and **40.54s**, respectively. All 16 successful stage results published, and all eight Stage 2 audits matched the received output digests.
- **Four slots, per-run 4, global 4.** The two-slot correctness gate stopped the benchmark before this arm. The live four-slot timing and reliability remain unmeasured.

The two-slot run took 49% of the control's elapsed time and delivered **1.83×** as many completed pages per minute, or **91%** scaling efficiency on that measure. The two-slot operation omitted one downstream call after a prerequisite failed. Just under 7% of recognition input tokens came from cache in the control and over 99% in the two-slot arm. All nine Stage 1 request bodies matched across arms. Stage 2 bodies included each run's own committed recognition result and differed across the eight matched pages. The comparison used one run per arm in fixed order, so the elapsed ratio includes differences in cache state, model output and completed work.

All 35 transmitted calls returned HTTP 200. There were zero HTTP 429s, client timeouts, retries, lease denials or observed database lock waits. The two-slot failure on page 11 was a Stage 1 `INVALID_PROVIDER_RESPONSE`. Local validation recorded `FIELD_CONSTRAINT / string_pattern_mismatch` at `page_context_hash`, a required model-echoed field in the recognition schema. The same pinned source and recognition request completed under the control. The failed Stage 1 attempt did not publish, and its Stage 2 unit failed with `PREREQUISITE_FAILED` before dispatch. The retained diagnostic establishes a malformed field. Stage 1 has no raw output archive to inspect the returned string. Published results passed same-page ownership, prerequisite hash and attempt binding checks. No duplicate publications or audit mismatches were observed.

The 57 control and 52 two-slot heartbeat renewals took **38/113 ms** and **39/144 ms** at the median/maximum. Maximum heartbeat scheduling delays were **19 ms** and **6 ms**. At peak the worker used one and two database connections respectively, with process-local ownership confirmed. The longest gap between completed reconciliation executions was **294.42s** with one slot and **145.84s** with two. The longest reconciliation task itself took **0.49s** and **0.54s**. The control's longest gap spanned all nine recognition tasks. These measurements show that a busy extraction queue can delay recovery well beyond the scheduler cadence even while active leases renew normally.

An independent spot check used eight panel designations and 64 printed panel facts covering rated bus current, SCCR, phase count, bus material, enclosure dimensions and the compound voltage notation. Page 11 stayed in the processing denominator and supplied no additional panel designation for this checklist. Both arms found all eight designations. The control reported 64/64 checklist facts on the expected panel and the two-slot arm reported 59/64. Only four and one of those matching facts mapped, respectively. None had a precisely resolved VALUE citation. Both arms sometimes proposed system or main-lug ampacity for the bus rating, where the drawing prints a different bus rating. Those conflicting proposals stayed unmapped or invalid. In the reviewed prepared positions on three schedules, neither arm reported installed breakers. The two dashed provision positions on the first sheet were described as proposed by the control and unknown by the two-slot arm. This was a spot check with no exhaustive breaker, inference or evidence-quality recall claim.

The local admission accepted 286 control assertions and 241 two-slot assertions, including 22 inferred assertions in the two-slot arm. No assertions were quarantined or overflowed. Measured input/output token totals were **326,321 / 105,355** and **314,108 / 95,940**. Standard token rates with reported cache reads and writes put the estimated provider spend at **US$0.155** for the 35 calls. [GPT-6 Luna rates](https://developers.openai.com/api/docs/models/gpt-6-luna), [cache usage pricing](https://developers.openai.com/api/docs/guides/prompt-caching).

**Live gate status:** The run demonstrated real two-slot overlap, higher completed-page throughput and intact publication fencing. The partial two-slot outcome leaves the live gate open and the four-slot arm pending. The recognition validation failure and recovery queue delay are separate findings. This benchmark made no change to the extraction pipeline, concurrency defaults, prompts, evidence rules or timeout policies.

### Stage 1 server-owned response metadata

The new `server-owned-recognition-v1` profile uses `equipment_recognition_v4.txt` and an equipment-only provider response. The prompt drops the instruction to copy execution metadata. PowerForge verifies the pinned source and response-to-request binding, then constructs the existing internal recognition result with the server-owned version, stage and page-context hash. Publication compares the complete request digest to the dispatch receipt within the existing lease-fenced transaction. Equipment observations and their identifiers, Stage 2 prerequisite semantics and evidence handling retain their existing contracts.

Previously pinned profiles fail validation when resumed under this implementation. Completed records retain their original identities and payloads. Raw Stage 1 output retention remains a separate decision. Verification for this correction is offline, and the four-slot live arm remains pending.

The focused suite passed **268 tests** on fresh disposable PostgreSQL after `alembic -c database/alembic.ini upgrade head`, with Redis and MinIO for the prefork integration cases. The opt-in repeated throughput benchmark was skipped. The suite covered malformed and duplicate observations, server-owned envelope construction, request identity, source binding, the Stage 2 prerequisite, and lease-fenced publication. Ruff and `git diff --check` passed.

```sh
RUN_INTEGRATION=1 pytest -q -rs tests/test_extraction_stage_contracts.py \
  tests/test_openai_extraction.py tests/test_extraction_profile.py \
  tests/test_engineering_execution_profiles.py tests/test_extraction_operations.py \
  tests/test_extraction_schema.py tests/test_extraction_parallel.py
```


## 11. Milestone F — Timeouts, failure economics, and performance debugger

**Priority:** P2 / reliability integration.

### F1. Separate distinct deadlines

Review and document: OpenAI client timeout, Celery soft/hard limits, work-unit lease/heartbeat, coordinator hard deadline, dispatch delay, and operation-level timeout. Ensure their ordering makes sense with the selected provider timeout and expected publication overhead.

For controlled *diagnostic* experiments, a temporarily higher provider timeout (e.g., 150–180 s) may reveal whether an OCR-heavy response eventually completes and provide usage. **Do not adopt a longer timeout as the performance solution.** An increase in success rate from simply waiting longer is not a latency win.

### F2. Retry/unknown-outcome policy

Preserve current safeguards around billed-but-unknown remote provider outcomes. Distinguish: transient transport failure, rate limit, timeout, refusal, malformed schema, incomplete `max_output_tokens`, fatal envelope validation, and local source mismatch. Do not blindly repeat expensive deterministic failures or automatically increase reasoning, image detail, or output budget on each retry.

If an automatic retry strategy is proposed, specify strict maximum attempts, budget consequences, telemetry, and explicit tests. No new retry behavior should bypass operator authorization or overwrite an audited attempt.

### F3. Debugger integration

Use the existing Extraction Debugger rather than creating a new service. Add a readable per-attempt performance table with:

- Overall outcome and exact failure category.
- Model, stage, effective reasoning effort, image detail, source/OCR modality.
- Queue and provider duration, local phases, full attempt duration.
- Input/cached/reasoning/visible/total output tokens (with null-state clarity).
- Readings, layout, catalog and body sizes.
- Request/output SHA-256 and original retained audit access under current permissions.
- Optional side-by-side comparison of two attempts with matched source identities, clearly warning when settings or source bindings differ.

Never expose raw responses, page text, PII, or hidden model reasoning through the general performance API.

**Gate F:** Timeout/slow-call diagnoses are grounded in measured phases; retry policies remain bounded and auditable; debugger reports missing telemetry honestly.

## 12. Milestone G — Benchmark corpus, regression gate, and release

**Priority:** Mandatory final release gate.

### G1. Evaluation corpus and permissions

Create or extend `evals/phase6r/` with:

- One native-text page;
- One image-heavy single-line diagram;
- One dense breaker/device schedule;
- Schneider-style panel drawing **with** and **without** OCR;
- A representative ten-page document (can be synthetic for CI; a private authorized real document for performance acceptance).

Annotate independently of model output: equipment occurrence, source-local owner, registry key, exact source value/unit, proposals and inference status, correct normalized value where representable, qualifiers, alternate representations, evidence occurrence and confidence, and whether a fact is genuinely unsupported/ambiguous.

**Do not automatically commit the proprietary Schneider PDF or raw extracted responses to a public repository.** Keep authorized input in private test storage; use sanitized/synthetic committed fixtures with SHA-256 references when appropriate. Keep holdout documents separate from prompt tuning.

### G2. Benchmark methodology

- Freeze reference commit, source artifacts, OCR settings, model identity, service tier, prompt/schema profile, worker count, and test budget.
- Measure local offline request-size and coverage results before live API calls.
- For permitted live calls, use a fixed bounded sample with repeated attempts if budget permits; note run order, cache warm/cold status, rate limits, and date.
- Compare one variable at a time: baseline; reasoning only; compact context only; output change only; combined single-slot; combined two-slot. Optionally compare alternative supported image detail as a separate factor.
- Compute p50/p95 only when samples justify them, alongside min/max, sample count, confidence/uncertainty; count timeouts and failures in success-rate statistics, not only successful latency distributions.
- Track cost **per successful page** and **per independently correct attribute**, not merely price per call. Use measured usage and versioned pricing; keep missing usage unknown.

### G3. Quality gates

No release if any of the following is introduced relative to baseline:

- Confirmed incorrect **critical** engineering rating or setting silently mapped and published.
- Source citations misattributed to a different equipment/row, or visual-only evidence falsely upgraded to verified text.
- Lost input readings, hidden conflicting data, or incorrect dedup of distinct equipment/attributes.
- Missing/incorrect inferred-vs-extracted distinction.
- Unapproved new AI computation/rounding or unit conversion.
- Audit loss, unversioned behavior change, schema mismatch, incorrect retry identity, or duplicate publication.

For recall/coverage, define numeric tolerances on the *actual reviewed corpus before final evaluation*. With small samples, report raw counts and manually inspect every changed critical assertion. For ambiguous items, count conservative abstention separately from a wrong mapping.

### G4. Required test suites

Run, adapting to actual repo dependencies and paths:

```bash
# Core offline tests
RUN_INTEGRATION=0 python -m pytest -q -m 'not integration'

# Focused DB/worker/source tests against disposable local services
RUN_INTEGRATION=1 python -m pytest -q \
  tests/test_extraction_schema.py \
  tests/test_extraction_operations.py \
  tests/test_extraction_debugger_integration.py \
  tests/test_workers.py \
  tests/test_enrichment_ocr.py \
  tests/test_spatial_evaluation.py \
  tests/test_enrichment_execution.py \
  tests/test_enrichment_celery.py \
  tests/test_spatial_celery.py

# Provider adapter and profile contracts
python -m pytest -q tests/test_openai_extraction.py tests/test_extraction_profile.py

# Existing UI and debugger checks
npm --prefix apps/web test
npm --prefix apps/web run lint
npm --prefix apps/web run build
npm --prefix tools/extraction-debugger test
npm --prefix tools/extraction-debugger run build
```

Also run new focused tests for A–F, formatter/type checks, standalone debugger backend tests, migrations against a **clean disposable PostgreSQL 16 database**, and actual Compose worker startup checks. The exact scripts and suite counts must be verified at HEAD, not copied unquestioningly.

### G5. Deliverables and release decision

Produce `evals/phase6r/ATTRIBUTE_PERFORMANCE_RESULTS.md` (or a similarly discoverable path) containing:

1. Commits/version identities and exact configuration.
2. Before/after timing table (provider, work-unit, whole document), OCR-on/off results, number of attempts, and failure reasons.
3. Token and request-size breakdown; caching share; output reasoning share.
4. Quality comparison with gold scoring, all wrong/missing critical fields, provenance and owner accuracy.
5. Cost estimates from actual usage with missing telemetry disclosed.
6. Test suites and outcomes; skipped, deselected, known-environment failures.
7. Reproduction commands and optional private-corpus instructions.
8. Chosen defaults, rollback steps, and unresolved performance limitations.

**Gate G:** Reviewers can explain what got faster, by how much, at what cost and with what independently verified engineering accuracy. Regressions and unmet performance targets are explicit.

## 13. Versioning, migrations, and deployment rules

- Pin changes affecting outputs/identity: reasoning effort, source provider-view version, prompt file/hash, wire schema, structured schema, model name, image detail, output budget where relevant, and applicable registry catalog.
- Keep **source artifacts immutable** and preserve canonical source input hashes. Provider views can be different derived representations of the same pinned page but must have a version/hash recorded in the execution profile.
- Add typed telemetry columns or a bounded structured metrics record through a reproducible migration; never make migrations silently depend on historical test-data conversion. Development DB reset is allowed when specifically chosen, **not as a requirement for working extraction**.
- Avoid changing source/audit retention without review. Metrics must be safe for routine logs and restricted debugger read access.
- Rollout defaults conservatively: medium reasoning, original provider-view, existing image detail and budgets until benchmark gate passes; enable selected optimizations only in *new* version-pinned runs.
- Verify actual worker process count/queues in Docker Compose, and database/server resources before increasing concurrency.
- Do not deploy partially bumped prompt/schema/profile identities or alter pinned in-flight execution policy.

## 14. Milestone dependencies, delivery and review discipline

| Milestone | Depends on | Can merge after | Main measurable result |
|---|---|---|---|
| P0 inventory | actual HEAD | inventory approved | real baseline and conflict list |
| A instrumentation | P0 | tests + debugger evidence | decomposition of latency and prompt complexity |
| B reasoning | A | controlled quality benchmark | successful Stage 2 latency reduction |
| C context | A; B optional | source-roundtrip + gold + benchmark | reduced OCR input cost/latency |
| D output | A; C optional | schema tests + gold + benchmark | reduced visible output tokens/latency |
| E concurrency | A | integration and multi-page load test | higher page throughput |
| F reliability | A and relevant B–E | error/timeout/UX tests | lower wasted-call rate and clearer diagnostics |
| G acceptance | A–F selected | review and final report | verified latency, throughput, quality |

If a proposed optimization has no measurable benefit or degrades quality, **document and omit it**. A milestone may conclude with a justified “no change” outcome. Do not force all architectural ideas into production.

## 15. Codex implementation instructions

For each milestone, in its own focused implementation pass:

1. Read this spec, inspect current HEAD, and list concrete affected files, current behavior, dependencies, and source evidence before editing.
2. Propose the smallest safe changes and the exact relevant tests. Identify whether a database migration, profile version, input version, prompt version, or debugger update is necessary.
3. Implement only that milestone. Prefer working with existing contracts, persistence, audits, and UI rather than inventing parallel systems.
4. Execute relevant offline tests and any authorized integrations. **Never** initiate paid live provider calls or upload proprietary drawings without explicit budget/permission.
5. Report changed files, versions, migrations, test commands/results, benchmark metrics, limitations, and risks. Distinguish **verified** from **not executed**.
6. Commit/push only per the project's normal workflow and operator instruction; do not claim tests or live results that were not run.
7. Pause at each benchmark/quality gate for review before choosing new defaults or starting a high-risk input-format rewrite.

Suggested first request to Codex:

> Implement **P0 + Milestone A only** from `docs/specs/phase-6r-attribute-extraction-performance.md`. Inspect the current branch first, including any recent server-owned identity and mapping changes. Add safe duration/usage/request-complexity telemetry and debugger presentation without altering extraction prompts, output schema, reasoning effort, validation, concurrency, or mapping decisions. Add tests for successful, timed-out, and malformed provider responses. Produce an offline OCR-on/off payload baseline and a summary of findings. Do not make live OpenAI calls without my explicit approval.

## 16. Review questions / explicit decision gates

Codex should answer these in the milestone reports instead of assuming them:

1. Is observed 90-second latency predominantly provider generation, reasoning, local source loading, or something else?
2. Exactly how much does OCR increase request bytes, input tokens, context rows, reasoning and wall time on the same pinned Schneider page?
3. Does `low` (or `none`) reasoning retain attribute/evidence correctness, or merely produce shorter outputs and omissions?
4. Does deterministic grouped OCR context materially reduce tokens/latency compared with the existing compact page view? Can all original reading refs and ambiguous cases be reconstructed?
5. How much response time is spent on visible JSON output versus reasoning tokens?
6. Does 2-worker concurrency improve a 10-page run without increasing provider throttling, source mixing, or duplicate publishing?
7. Do timeout adjustments improve **completion without making users wait longer**? What is the measured p95 and failure rate?
8. Are release decisions based on independently reviewed engineering facts rather than the percentage of MAPPED results?

## 17. References (verify against current API documentation before coding)

- [GPT-6 Luna model reference](https://developers.openai.com/api/docs/models/gpt-6-luna) — supported reasoning efforts; `medium` default at preparation time.
- [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) — `output_tokens_details.reasoning_tokens`; reasoning/output budget behavior.
- [OpenAI latency optimization guide](https://developers.openai.com/api/docs/guides/latency-optimization) — token generation, lower reasoning, caching, parallelism, measurement.
- [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) — exact-prefix reuse and cached-token telemetry.
- Existing PowerForge Phase 6R typed-value and extraction specs under `docs/specs/`, plus `evals/phase6r/README.md` and `AGENTS.md` if present.

---

**Final instruction:** Preserve truthful engineering information and auditability. The fastest system that silently drops or misattributes electrical ratings is not an optimization. Benchmark, retain the conservative safeguards, and promote only independently verified improvements.
