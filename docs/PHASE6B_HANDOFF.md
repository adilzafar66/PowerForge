# Phase 6B handoff — Extraction orchestration and execution reliability

## Baseline and scope

Date: 2026-11-03 (America/Vancouver).
Implementation branch: `codex/phase-6b-extraction-orchestration`.
Actual base: `0acf38f14c389bf8933edc05c4c52e894b71e2d6`, refreshed `origin/main` before branching.

Authority: [Phase 6B prompt](prompts/phase-6b-prompt.md), [approved Phase 6 specification](specs/phase-6-evidence-structured-extraction.md), [ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md) and the accepted [6A handoff](PHASE6A_HANDOFF.md). Design was recorded before implementation in [PHASE6B_PLAN.md](PHASE6B_PLAN.md). Approved specifications/ADRs, migrations 0011/0012, registry-v1, canonical-model semantics and the historical 6A handoff are unchanged.

**6B is implemented.** It executes reliable infrastructure/test source probes. It does not implement production equipment recognition, attribute normalization, table interpretation, OCR, entity matching, reconciliation, engineer acceptance or extraction UI. Those remain 6C–6G/later responsibilities. The whole Phase 6 is not complete.

## Architecture and flow

`powerforge_extraction.orchestration.ExtractionCoordinator(session, settings)` owns start/reuse/re-extract, stable planning, claim/admission, heartbeats, retry, cancellation, aggregation, recovery and delivery. Its methods flush and participate in the caller's transaction. No provider call is made there. `powerforge_extraction.execution.execute_unit()` separates claim commit, verified source I/O/provider execution and fenced completion transactions. `packages/ai/.../extraction.py` owns provider-neutral request/structured-result/usage/error contracts. SDK handling lives only in `extraction_worker.openai_extraction`.

The API resolves INCLUDED RevisionDocument membership through the existing read service, including the correct project/revision/immutable Document. Start locks Document to serialize equivalent requests; it pins a completed processing run, sorted selected pages, exact native-text or analysis-image artifact IDs and the execution profile. Each page has one required stable `SOURCE_PROBE:page:NNNNNN` key. The entire plan, run configuration and delivery records commit before task notification. Classification is not a prerequisite; no canonical model is consulted or changed.

Ensure returns an equivalent active run or a compatible completed run. If no completed result exists, repeating ensure returns the compatible failed/partial/cancelled run without creating new billable work; continuing requires explicit retry or re-extraction. Explicit re-extract creates a distinct linked historical run after prior equivalent activity settles. Repeated equivalent re-extract requests while active return that active run. Profile identity covers source/profile/provider/model/prompt/schema and execution-limit choices; processing run/artifacts/pages also enter 6A's immutable identity. Source-only results remain reusable across inherited/read-only revisions containing the same Document. Existing context-fingerprinted reads stay restricted to their original compatible revision; 6B supplies no context-dependent/canonical-model extraction profile.

## Profiles, prompts and providers

GET `/extraction/profiles` advertises two versioned, explicitly non-production profiles:

- `infrastructure-fake-v1`: default manual synthetic test execution. Deterministic native-text quotes exercise the actual 6A Evidence/Candidate/CandidateEvidence publication path. Candidates carry `FAKE_TEST_OUTPUT`, an explanation and `diagnostics.synthetic=true`. Image-only/empty probes publish valid empty output rather than invented source locations.
- `infrastructure-openai-v1`: an opt-in provider/source-access probe. It requests a bounded verbatim excerpt of supplied native text, or null when only an image is available. Exact substring validation is required. It may retain source Evidence but produces no engineering candidates. COMPLETED means the named probe plan succeeded, not that production engineering extraction is available.

The owning package includes `prompts/source_probe_v1.txt`; prompt version/hash and the structured ProbeResult schema version/hash are pinned. The immutable JSON configuration additionally records input strategy, per-page partitioning, resource/retry/concurrency/timeout/lease limits, fake scenario and any pricing assumptions. Current workers refuse unsupported pinned prompt/schema hashes instead of silently using changed instructions.

`FakeExtractionProvider` supports success, empty output, transient/permanent failure, invalid response, slow execution and simulated worker interruption; tests can inject deterministic providers and delays. Real worker fake behavior comes from the pinned scenario. The OpenAI adapter uses one Responses structured parse call, explicit pinned model, output-token cap, timeout, `store=false`, no tools/conversation/background state and SDK `max_retries=0`. Persisted attempts own retries. Usage/refusal/incomplete/invalid responses and SDK error categories are validated/sanitized. Credentials are not part of profiles, requests returned to clients, control records or logs; Settings also hides the API key from repr.

Official adapter references consulted: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses) and [Responses create reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create). Mocked adapter tests make no socket calls. No live OpenAI request or account/model access verification was performed.

## Concurrency, delivery and recovery guarantees

Migration `0013_extraction_execution`, after `0012_extraction_terminal_guard`, adds:

- `extraction_run_execution`: immutable profile configuration, monotonic bounded call admissions and a preserved cancellation timestamp.
- `extraction_unit_execution`: same-run/logical-key ownership, durable available/dispatch timestamps and counters, one immutable claim token, absolute execution deadline and provider-call boundary timestamp.

Existing extraction entities/output identities are reused. Closed history/output and 0012 terminal guards are preserved. Additional triggers protect execution configuration/attempt identity and fence result/telemetry inserts plus successful unit completion for managed runs. Legacy/internal 6A runs without execution controls retain their existing trusted publication contract; all 6B API/worker paths require controls.

A claim takes a short PostgreSQL advisory admission lock, then the parent run lock, refreshes attempt/control state, enforces eligibility/global and per-run concurrency/call budget and commits a single token/lease/deadline. Duplicate deliveries do not get a second claim or issue another provider request. Network provider calls occur with no open caller DB transaction. Heartbeats use separate short transactions, check ownership and renew only up to the absolute deadline. Successful completion rechecks the current token, active run, unexpired lease and absence of cancellation, sets a transaction-local authorization token, records known technical usage and invokes 6A atomic publication. Database fencing also protects empty successful output. Stale workers cannot publish against a newer attempt.

Delivery records form a durable outbox. Initial API/worker notification happens after commit. Due PENDING rows are periodically redispatched, including a crash between commit and send, send/ack ambiguity, failed transport and enqueued-but-never-started work. Transport failures log only a class/category and preserve pending work. Redis and Celery are not authorities for committed state.

`document_extraction.reconcile` periodically settles expired RUNNING attempts as `WORKER_INTERRUPTED`, appends bounded replacements where eligible and redispatches due pending work. The dedicated Celery beat service keeps invoking it after restarts. Run/unit locks, append-only ancestry and 6A uniqueness make duplicate recovery safe. A healthy heartbeat cannot keep a hung attempt alive beyond the absolute execution deadline. Recovery requires reachable PostgreSQL and running worker/beat services; broker outages delay delivery until transport returns.

A crash immediately around a provider request can still cause an unobserved charge and a repeated request after recovery. Exactly-once external execution is not claimed. The call boundary/admission record survives; missing provider usage remains explicitly unreported/unknown. Fencing prevents competing committed results, not the physical cancellation of a request already sent to a vendor.

## Retry, cancellation and aggregate states

Transient timeout/unavailable/rate-limit/interrupted failures append fresh attempts with identical pinned logical inputs and exponential available-at backoff (capped at 300 seconds). Permanent and invalid responses settle without automatic retry. Both automatic and manual retries obey the original max attempts and admission budget; manual retry cannot reset either limit. Successful keys are never resent merely because a sibling failed.

Manual retry can resume FAILED/PARTIALLY_COMPLETED runs as RUNNING and appends only eligible unsuccessful latest attempts. It is idempotent while active. Completed/cancelled runs remain immutable: retry returns a conflict directing the user to explicit re-extraction, which creates a new linked run. This resolves the prompt's cancelled-history ambiguity without weakening the accepted 6A guards or altering old attempts.

Cancellation locks the run, persists intent, stops future eligible claims by settling all pending/running attempts as CANCELLED, flushes those statuses and only then finalizes the parent. Already committed successes remain. An in-flight provider may finish physically, but its now-cancelled token cannot publish. Repeated cancellation returns the same cancelled history; a completed run cannot be retroactively cancelled.

No parent reaches a terminal state with active required or optional work. Once execution settles, required logical-key successes determine COMPLETED, PARTIALLY_COMPLETED or FAILED; optional outcomes stay visible. Cancellation yields explicit CANCELLED after settling all attempts. Existing effective-result queries continue selecting only committed successful attempts. Run/unit history, retry ancestry, partial coverage and errors remain inspectable.

## Telemetry and resource/cost controls

Run detail includes execution/profile kind, cancellation time, admission budget/consumption, provider-call boundary count, reported/unreported calls, optional aggregate tokens and optional estimated USD cost. Attempts include retry eligibility, heartbeat/lease expiry and a stale indicator; private tokens, delivery counters/task IDs, storage keys, source payloads and credentials are not exposed.

Provider-call telemetry stores safe provider/model/prompt/schema/correlation IDs, outcomes, durations, bounded categories and returned input/cached/output tokens. A call-boundary crash/cancellation may prevent a final telemetry row because 6A history is immutable; unreported boundaries remain explicit rather than writing invented usage or zero cost. Input/pre-call failures can consume an admission without starting a provider call, reported separately from unreported provider boundaries.

Defaults are documented in `.env.example` and wired consistently to API/worker through Compose: 50 pages, 2 MB per artifact, 20 million image pixels, 250 MiB document limit, 1,024 output tokens, 3 attempts, 150 total admissions, 2 active attempts per run/4 globally, 60-second provider timeout, 30-second lease, 5-second base backoff, 30-second redispatch and 15-second recovery interval. Input objects are size/hash verified and image headers/pixels checked before provider invocation; publication retains 6A's exact UTF-8 artifact-bound offsets.

The initial approved-equivalent spending safeguard is bounded total call admissions plus input/output/attempt/time/concurrency limits. Interrupted and pre-call failed admissions are conservatively consumed. There is no strict dollar guarantee for unknown usage/prices. Optional configured input/output rates require a recorded pricing basis; estimates use Decimal and treat cached input at the configured flat input rate. Incomplete/unknown pricing stays null; no current vendor prices are invented or hard-coded. API-key repr and failure logs avoid credential/raw document dumps.

## Public API

All paths share `/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/extraction`.

- GET `/profiles`: available versioned infrastructure profiles, explicit execution kind and enablement/production status.
- POST `/runs`: strict `{profile_key, pages, mode}`; defaults to fake/ensure/all eligible pages within limits. Returns 202 RunDetail, including when compatible results are reused.
- POST `/runs/{run_id}/retry`: 202 RunDetail; optional empty action body rejects extra control fields.
- POST `/runs/{run_id}/cancel`: RunDetail; optional empty action body rejects extra fields.

All six prior GETs remain. Explicit response models expose safe operational state/usage; no GET creates/schedules work. Existing included-document/project/revision access checks and error envelopes remain. Invalid profiles/pages/resource requests return 422; unmet processing/disabled/conflicting/history/budget actions return 409; unrelated membership/run access returns 404. Read-only canonical revisions may initiate document-scoped derived work without canonical writes. Existing deferred authentication is not replaced with a fake user system.

## Operations and setup

Apply `alembic -c database/alembic.ini upgrade head`. The sole head is `0013_extraction_execution`. Build/restart the API/extraction worker and start the scheduler using normal repository deployment procedures. Compose now starts `extraction-worker` on both `document_classification,document_extraction` and adds `extraction-scheduler` for beat. Document processing/classification contracts are otherwise unchanged. No automatic extraction hook is installed.

For local CLI processes, use the same DATABASE_URL/REDIS_URL/S3 settings in API and worker, then run:

```sh
celery -A extraction_worker.celery_app worker -Q document_classification,document_extraction --concurrency=1
celery -A extraction_worker.celery_app beat --schedule=/tmp/powerforge-extraction-beat
```

With an included, already processed document, POST `{}` to `/extraction/runs` for fake/ensure, select explicit pages/profile as needed, and poll run detail/candidates/evidence. Use `{ "mode": "reextract" }` for deliberate fresh execution.

Optional OpenAI probe: deliberately enable `EXTRACTION_EXTERNAL_ENABLED=true` in API and worker, select `EXTRACTION_MODEL`, and supply OPENAI_API_KEY only at the worker boundary. Explicitly POST `{ "profile_key": "infrastructure-openai-v1" }`. Default external enablement is false. This invokes the named infrastructure source probe and does not unlock production engineering extraction. Live smoke tests remain user-initiated/opt-in and are excluded from CI.

## Actual verification

Final full backend suite: **1,157 passed, no skips**, six pre-existing dependency deprecation warnings, in 148.35 seconds. This includes **43 new Phase 6B tests** and all existing Phase 6A/classification/document-processing/canonical-model regressions. Command:

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:55437/powerforge_phase6b_final \
S3_ENDPOINT_URL=http://localhost:59007 S3_PUBLIC_ENDPOINT_URL=http://localhost:59007 \
REDIS_URL=redis://localhost:56387/0 RUN_INTEGRATION=1 \
.venv/bin/pytest -q --tb=short
```

Coverage includes start/reuse/re-extract, unknown classification/profile override, inherited/read-only/unrelated access, fake output/empty/permanent/invalid/transient behavior, no DB transaction over provider execution, concurrent duplicate claiming, backoff/exhaustion, partial retry preserving successful keys, interruption recovery and database fencing, durable notification failure/replay, heartbeats, cancellation/late response, admission budget/concurrency/input/image limits, exact known-basis cost, ungrounded quote rejection, strict API action bodies and mocked OpenAI requests/errors/usage.

The actual Celery integration cases started fresh worker and beat subprocesses over disposable Redis/PostgreSQL/MinIO, completed persisted-but-undelivered work, fetched a signed exact source artifact, then killed a running worker and verified a replacement attempt completed after scheduler recovery/restart. Temporary broker failure was additionally injected at the transport boundary; the live Redis server was not deliberately stopped. No real provider was contacted.

Fresh empty-to-head and representative 0012 upgrade/downgrade/re-upgrade checks passed, preserving source/6A tables and terminal guards. A strengthened migration check also retained a completed legacy 6A run with evidence, citations and an exact typed value (2 migration cases passed independently). Historical 0012 tests explicitly target their own revision. Editable package builds and `pip check` passed; Ruff lint/changed-file formatting, Compose `config --quiet`, OpenAPI JSON/contracts, single-head/offline 0012-to-head migration SQL and whitespace checks passed. Blank optional pricing/incomplete pricing/API-key repr were also checked directly. A supplemental provider-boundary test confirmed call-start timestamps and no open DB transaction during provider execution.

Infrastructure was isolated in Compose project `powerforge-phase6b`, using PostgreSQL 55437, Redis 56387 and MinIO 59007, tmpfs storage, scratch MinIO buckets and uniquely named scratch migration databases. The normal development database/storage volumes were not migrated or used for test writes. Disposable services are removed after validation. No frontend code changed; frontend/browser checks and a live-provider smoke test were not performed. No remote GitHub Actions pass is claimed; the previously documented MinIO image-availability issue remains separate.

## Limitations and Phase 6C extension contract

Keep beat plus workers running for automatic recovery. Notification/recovery latency follows configured intervals; a broker outage can leave truthful pending work until it returns. Default single-worker Compose concurrency is deliberately modest; PostgreSQL admission limits also apply if workers are scaled. Provider requests already sent cannot be physically recalled or guaranteed exactly once. Cancelled/completed history is never reopened; deliberate new re-extraction may repeat source work. Offset list pagination and unpaginated attempt detail retain their ordinary scaling limits.

6C should add versioned production profiles/stage plans and their provider-owned structured schemas and source-to-WorkUnitOutput converters. The current SOURCE_PROBE plan is one required unit per page; extending the stage planner/payload contract must not alter claim/delivery/retry/fencing/transaction semantics. Exclude FAKE_TEST and INFRASTRUCTURE_PROBE runs from production-engineering consumption; their completion does not establish domain extraction coverage. Preserve old profile/prompt/schema readers/hashes; do not silently reinterpret historical snapshots. Supply the pinned artifact/source context and storage interface, validate typed registry mappings/units conservatively, retain unmapped/tagless observations and call coordinator completion. Do not write canonical equipment, attributes, topology, verification or revision-wide frequency/phase count. Respect current global enablement/admission limits and original run attempt/call budgets.

6D tables, 6E OCR/layout, 6F extraction/evidence UI/evaluation and 6G hardening/freeze remain unimplemented. No material departure from the approved ownership/immutability architecture was required.
