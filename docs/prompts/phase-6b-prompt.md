# PowerForge — Phase 6B: Extraction Orchestration and AI Infrastructure

## Objective

Implement **Phase 6B — Extraction Orchestration, Provider Infrastructure, and Execution Reliability**.

Phase 6A is complete, reviewed, and merged into `main`. It establishes the extraction persistence model, immutable evidence/candidate records, work-unit publication boundaries, and read-only extraction APIs.

Phase 6B must make this foundation operational.

The goal is to enable PowerForge to initiate, schedule, execute, monitor, retry, recover, and cancel document extraction runs reliably, using provider-neutral infrastructure and the existing Celery/PostgreSQL/Redis/MinIO stack.

**Branch:** `codex/phase-6b-extraction-orchestration`

**Base:** Latest `main`, which includes accepted Phase 6A commit `0acf38f14c389bf8933edc05c4c52e894b71e2d6`.

### Primary deliverables

1. Extraction run creation and orchestration.
2. Versioned extraction profiles, prompts, schemas, and provider configuration.
3. Provider-neutral execution infrastructure, with a deterministic fake provider and OpenAI as the first real adapter.
4. Reliable asynchronous execution through Celery.
5. Work-unit claiming, leases, heartbeats, recovery, retries, and idempotency.
6. Cooperative cancellation and correct run-state aggregation.
7. Execution telemetry and configurable resource/cost safeguards.
8. Start, retry, and cancel API endpoints.
9. Meaningful end-to-end tests and Phase 6B handoff documentation.

**Implement Phase 6B only.**

This phase establishes a reliable extraction execution system. It does not yet implement the domain-specific equipment, attribute, table, or OCR extraction intelligence planned for 6C–6E.

---

## 1. Authoritative references

Before implementation, inspect and understand:

```text
docs/specs/phase-6-evidence-structured-extraction.md
decisions/ADR-008-evidence-candidate-extraction-architecture.md

docs/PHASE6A_HANDOFF.md
docs/EXTRACTION.md
docs/PROVENANCE.md
docs/ARCHITECTURE.md
docs/CODING_STANDARDS.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
```

Also inspect the existing implementations in:

```text
packages/extraction/
packages/ai/
packages/document-classification/
packages/document-processing/
packages/shared/

services/extraction-worker/
services/api/

database/migrations/
tests/
```

Pay particular attention to:

- `ExtractionPersistence` and its transactional publication semantics.
- `ExtractionRun` and `ExtractionWorkUnit` lifecycle constraints.
- Migrations `0011_extraction_persistence` and `0012_extraction_terminal_guard`.
- Existing document-processing and classification worker patterns.
- Existing provider interfaces and OpenAI classification integration.
- Document/RevisionDocument authorization and processing-artifact ownership.
- The established configuration, logging, error handling, and integration-test conventions.

### Source-of-truth hierarchy

1. Approved Phase 6 specification — normative requirements.
2. ADR-008 — architectural boundaries and decisions.
3. Accepted Phase 6A implementation — existing persistence/API contracts.
4. Frozen Phase 5 engineering model and registry-v1.
5. Existing repository conventions.

Do not silently modify approved engineering semantics to simplify orchestration.

---

## 2. Architecture ownership and implementation autonomy

You are responsible for designing the technical implementation of Phase 6B.

You may determine:

- Internal service/module boundaries.
- Orchestration and worker coordination patterns.
- Provider and execution interfaces.
- Task planning and queue organization.
- Retry/recovery implementation mechanisms.
- Appropriate supporting persistence or migrations.
- Configuration and telemetry implementation.
- Testing organization.

Prefer a maintainable design that integrates naturally with the current repository. Do not introduce an unnecessarily elaborate orchestration framework.

**Before implementation, develop a concise technical design** explaining the proposed execution flow, state transitions, provider boundaries, concurrency strategy, and recovery approach.

Record it in `docs/PHASE6B_PLAN.md`.

You may proceed with ordinary implementation decisions autonomously. However, if your design requires a material departure from the approved specification, ADR-008, or Phase 6A's immutable-history guarantees, identify that difference and obtain approval before making the architectural change.

Do not add placeholder abstractions without a clear Phase 6B responsibility.

---

## 3. Required orchestration behavior

An engineer must be able to initiate extraction on an eligible, already processed document.

The orchestration layer must:

- Resolve the source Document through valid project/revision/document membership.
- Verify that a compatible completed DocumentProcessingRun exists.
- Choose and pin the correct processing run, page artifacts, profile, stages, provider, model, prompts, and schemas.
- Validate selected pages and the availability of required inputs.
- Create a document-scoped ExtractionRun.
- Generate a stable logical work-unit plan.
- Dispatch the work asynchronously.
- Track execution progress and outcomes.
- Preserve all immutable input identities and historical records.

Extraction must operate independently for each document.

### Intended execution flow

```text
Engineer / API
      |
      v
Validate document and completed processing
      |
      v
Resolve extraction profile and pinned inputs
      |
      v
Create or reuse compatible ExtractionRun
      |
      v
Create stable ExtractionWorkUnit plan
      |
      v
Celery task scheduling
      |
      v
Worker claims a logical work unit
      |
      v
Provider-neutral execution
      |
      v
Validate returned output
      |
      v
Atomic publication through Phase 6A
      |
      v
Aggregate run status and telemetry
```

The diagram is conceptual. Choose an appropriate technical implementation.

### Run creation and reuse

Support the distinction between:

**Extract / Ensure**

An ordinary request to ensure compatible extraction exists.

If an equivalent run is already active, do not create a competing execution.

If a compatible completed result exists, it may be reused according to the approved input identity and reuse policy.

**Re-extract**

An intentional request to perform extraction again, potentially using a different configuration or the same configuration.

It must create a new historical run after the relevant prior execution has finished, rather than overwrite earlier extraction results.

No two equivalent active runs should execute concurrently.

Preserve source-only result reuse across revisions containing the same document. Context-dependent runs must remain restricted to compatible, explicitly fingerprinted contexts.

---

## 4. Extraction profiles and execution configuration

Introduce a clear, versioned extraction-profile system.

Profiles should determine relevant execution choices such as:

- Enabled extraction stages.
- Source artifact/input strategy.
- Page or batch partitioning.
- Provider and model selection.
- Prompt and structured schema identities.
- Output constraints.
- Retry and execution limits.
- Relevant resource and cost controls.

The exact fields and representation are yours to design.

A material configuration change must produce an appropriately distinguishable pinned execution identity.

Do not hard-code a single model or provider into the extraction domain.

### Profile selection

Phase 4 document classification may be used as a hint for choosing a profile, but must not be a mandatory prerequisite.

An `UNKNOWN` or `MIXED_DOCUMENT` document should still have an appropriate extraction path when a compatible profile is available.

Engineers must be able to explicitly override the suggested extraction profile by selecting another available profile.

### Manual and automatic execution

Manual extraction must work by default.

Optional automatic extraction after successful document processing may be supported through explicit configuration. It must be disabled by default unless deliberately enabled.

Automatic extraction must not create unexpected provider charges or bypass authorization, document eligibility, or configured limits.

### Scope boundary

Do not design an enormous production prompt that attempts to extract everything from every engineering document.

Phase 6B provides the infrastructure for independently versioned extractors.

The actual engineering extraction prompts, registry mapping logic, and source interpretation belong to 6C–6E.

---

## 5. Provider-neutral execution infrastructure

Extend the existing `packages/ai` provider architecture where appropriate.

The orchestration system must interact with providers through stable application-owned contracts rather than vendor-specific SDK types.

### Required providers

**Deterministic fake provider**

Implement a configurable fake provider suitable for complete end-to-end execution tests.

It should support representative outcomes including:

- Valid successful output.
- Empty but valid output.
- Temporary provider failure.
- Permanent provider failure.
- Invalid structured output.
- Slow execution or simulated worker interruption.
- Usage and cost telemetry.

A successful fake execution should exercise the actual Phase 6A persistence/publication path, not bypass it through database fixtures.

Clearly distinguish fake/test extraction from genuine AI-derived engineering results.

**OpenAI adapter**

Implement the initial real provider integration using the project's existing OpenAI infrastructure where reusable.

The adapter should support bounded structured requests, explicit model selection, validated responses, suitable timeouts, provider error classification, and usage reporting.

Keep credentials and provider-specific request handling inside the worker/integration boundary.

Do not hard-code prompts or model names into the database domain.

Real OpenAI execution must be explicitly enabled and must not run during routine automated tests.

### Important distinction

Phase 6B should establish a functional, testable provider integration and execution contract.

It should **not prematurely implement production equipment recognition, registry attribute extraction, table interpretation, or OCR pipelines**.

Where a domain-specific production stage is not yet available, do not pretend the extraction succeeded or publish fabricated observations.

Clearly identify the executable infrastructure/test profiles and the production extractor stages that will be added in later phases.

---

## 6. Reliable work-unit execution

This is the most important part of Phase 6B.

The orchestration system must remain correct under:

- Duplicate Celery task delivery.
- Concurrent worker execution.
- Provider timeouts.
- Worker crashes.
- Temporary Redis interruptions.
- Process restarts.
- API retries.
- Late provider responses.
- Partial failures.
- Cancellation during execution.

Use PostgreSQL as the authoritative source of extraction state.

Celery and Redis transport tasks; they must not independently determine whether an extraction result is committed or authoritative.

### Work-unit claiming

Workers must safely claim eligible work units.

A logical unit must not have two simultaneously authorized executions that can both publish results.

Do not hold a database transaction open for the duration of a network-based provider call.

Use an appropriate lease/ownership mechanism, with database-backed guards, so expired or superseded workers cannot publish stale results.

### Retry behavior

Retry only unsuccessful or unfinished logical work.

Successful committed work units must never be resent merely because another unit failed.

Retries must:

- Preserve existing attempt history.
- Create new attempts rather than overwrite previous ones.
- Respect retry limits and backoff.
- Distinguish transient from permanent failures.
- Reuse pinned inputs and logical unit identities.
- Prevent old and new attempts from publishing conflicting results.

### Recovery

Implement a reliable recovery mechanism for interrupted work.

A worker crash must not leave a run indefinitely in `RUNNING`.

Recovery should identify abandoned or stale work using the persisted lease/heartbeat state and safely determine whether to requeue, fail, or retry that work.

It must also account for work that was persisted but not successfully dispatched to Celery.

Do not assume task delivery is exactly once.

Where a crash occurs after an external provider request but before its completion is persisted, a repeated provider charge may be unavoidable. Ensure the system provides the strongest practical idempotency, bounded retry behavior, and truthful telemetry rather than claiming impossible exactly-once external execution.

---

## 7. Run lifecycle and cancellation

Preserve the approved lifecycle semantics.

### Run states

`PENDING`, `RUNNING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED`.

### Work-unit states

`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.

The run's aggregate state must accurately reflect the outcomes of its required logical units.

- `COMPLETED`: All required logical units succeeded.
- `PARTIALLY_COMPLETED`: Some required logical units succeeded; others remain unsuccessful after execution has settled.
- `FAILED`: No useful required units succeeded.
- `CANCELLED`: Execution was explicitly cancelled under the approved semantics.

Optional work-unit outcomes must be represented honestly without misrepresenting required-unit coverage.

### Phase 6A compatibility

Migration `0012_extraction_terminal_guard` prohibits any terminal run state while required or optional work-unit attempts are still `PENDING` or `RUNNING`.

Phase 6B must respect this guarantee.

**Before transitioning a run to a terminal state, all active work-unit attempts must be appropriately settled and persisted.**

### Cooperative cancellation

Cancellation must:

- Stop scheduling further outstanding work.
- Prevent cancelled attempts from publishing late results.
- Preserve already committed successful work.
- Avoid undoing immutable evidence or candidates.
- Settle in-flight attempts before finalizing the run.
- Report an accurate terminal outcome.

Cancellation should be safe when requested repeatedly or concurrently with worker execution.

### Retry and terminal-history compatibility

Review the interaction between Phase 6A's terminal immutability rules and Phase 6's requirement to retry unsuccessful logical work.

In particular, Phase 6A treats `CANCELLED` runs as immutable, while the broader specification contemplates retrying cancelled work.

Resolve this explicitly in the technical design, distinguishing retry within a recoverable run from deliberate new re-extraction where appropriate.

Do not silently weaken completed/cancelled history or bypass the database guards. If satisfying the approved semantics requires a material architectural change, surface it for approval.

---

## 8. Execution telemetry, resource limits, and costs

Make extraction operationally observable without turning logging into a sensitive-document archive.

Reuse the Phase 6A `ExtractionAICall` entity and run/work-unit metadata.

Track relevant information such as:

- Provider/model and versioned prompt/schema identities.
- Execution start, completion, failure, and duration.
- Stage/page progress.
- Sanitized error categories.
- Provider calls and token usage.
- Cached tokens where reported.
- Estimated cost when reliably derivable.
- Work-unit retry history and aggregate run outcomes.

### Cost controls

Provide configurable safeguards for:

- Selected document/page limits.
- Input sizes and image resolution.
- Concurrent executions.
- Work-unit retries.
- Provider timeouts.
- Per-run spending limits or approved equivalent budget controls.

Keep the controls proportionate to the current application's maturity.

Do not fabricate cost estimates when usage or pricing is unknown.

Use recorded pricing assumptions if estimating monetary costs. Prevent known budget overruns where possible and communicate uncertainty where strict cost guarantees cannot be made before an external call.

Budget exhaustion must not delete or invalidate successful work. It should produce an accurate partial or failed outcome when appropriate.

### Security

- External AI processing must be explicitly enabled.
- Keep provider credentials out of API responses, browser code, and logs.
- Do not routinely log full prompts, source documents, images, or raw provider responses.
- Use bounded and sanitized error messages.
- Treat document/OCR/model content as untrusted input.
- Preserve existing project/document access restrictions.

Enterprise-scale confidentiality infrastructure is not required at this stage.

---

## 9. Public API additions

Extend the existing revision-document extraction namespace:

```text
/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/extraction
```

Implement the approved operational endpoints:

| Method | Subpath | Responsibility |
|---|---|---|
| POST | `/runs` | Start/ensure extraction or explicitly re-extract |
| POST | `/runs/{run_id}/retry` | Retry eligible unsuccessful logical units |
| POST | `/runs/{run_id}/cancel` | Request cooperative cancellation |

Preserve the six existing GET endpoints.

The API should expose enough information for clients to distinguish:

- Active versus completed runs.
- Successful versus partially successful extraction.
- Failed and retryable work units.
- Cancellation status.
- Current and historical attempts.
- Relevant provider/usage metadata that is safe to disclose.

Use explicit validated request/response models and established error conventions.

Do not leak internal task IDs, credentials, private storage keys, or raw provider payloads unnecessarily.

Run actions must enforce project/revision/document ownership and compatibility. Creating document-scoped derived extraction data must not mutate a read-only canonical engineering revision.

Do not implement the Phase 6F frontend workspace.

---

## 10. End-to-end behavior examples

The following scenarios define expected behavior rather than implementation details.

### Scenario A — Normal execution

```text
POST Extract
    |
    v
Run PENDING
    |
    v
Work units planned
    |
    v
Run RUNNING
    |
    +---- Unit 1 ---- COMPLETED
    |
    +---- Unit 2 ---- COMPLETED
    |
    v
Run COMPLETED
```

All committed results remain associated with their producing work-unit attempts.

### Scenario B — Partial failure and retry

```text
Run RUNNING
    |
    +---- Unit A ---- COMPLETED
    |
    +---- Unit B ---- FAILED
    |
    v
Run PARTIALLY_COMPLETED
    |
    v
Retry
    |
    +---- Unit A ---- preserved
    |
    +---- Unit B attempt 2 ---- COMPLETED
    |
    v
Run COMPLETED
```

Unit A is not executed again.

Unit B's failed first attempt remains in history.

### Scenario C — Duplicate task delivery

Two workers receive the same work-unit task.

Only one may acquire valid execution ownership. The other must exit without issuing a duplicate billable provider request or publishing results.

### Scenario D — Worker crashes during execution

A worker claims a unit, begins processing, and terminates unexpectedly.

Its lease eventually becomes stale. Recovery identifies the abandoned work and safely schedules a bounded replacement attempt.

A late result from the abandoned attempt must not overwrite or compete with a newer successful attempt.

### Scenario E — Cancellation

A run contains one committed successful unit and another active unit.

Cancellation stops outstanding work, settles active attempts, preserves the successful result, and transitions the parent to a valid terminal state.

No new canonical model data is created.

---

## 11. Verification requirements

Use focused tests that exercise real behavior rather than large numbers of trivial combinations.

### A. API and run creation

Verify:

- Valid manual extraction.
- Invalid/unprocessed documents.
- Page and profile selection.
- Classification-independent execution.
- Explicit profile override.
- Equivalent active-run deduplication.
- Compatible completed-run reuse.
- Intentional re-extraction.
- Cross-project/document/revision access restrictions.
- External AI disabled by default.

### B. Worker execution

Verify:

- Fake-provider end-to-end extraction through actual persistence.
- Stable work-unit planning.
- Correct run/attempt transitions.
- Atomic publication.
- Duplicate task delivery.
- Concurrent claiming and fencing.
- Provider failures and invalid responses.
- Successful output surviving failed sibling work.

### C. Retry and recovery

Verify:

- Targeted retry without re-executing successful units.
- Retained historical attempts.
- Backoff and retry exhaustion.
- Worker interruption and expired lease recovery.
- Enqueued-but-never-started work recovery.
- Late/stale worker publication rejection.
- Recovery after service restart.

### D. Cancellation and budget controls

Verify:

- Cancellation before execution.
- Cancellation during execution.
- Repeated cancellation.
- Cancellation racing with publication.
- Required and optional units settled before terminal transitions.
- Cost/resource exhaustion and accurate partial results.

### E. Provider and telemetry

Verify:

- Fake provider contract behavior.
- OpenAI adapter request/response validation with mocked clients.
- Versioned prompt/profile identity.
- Sanitized errors and no credential leakage.
- Provider usage persisted correctly.
- Unknown monetary cost handled honestly.

Do not make real OpenAI API calls in CI.

A manually initiated live-provider smoke test may be documented separately when credentials and external processing are explicitly enabled.

### F. Regression and integration

Run:

- Focused Phase 6B tests.
- Existing Phase 6A tests.
- Relevant classification and document-processing regressions.
- Backend tests, lint, formatting, and dependency checks.
- Live disposable PostgreSQL/Redis/MinIO/Celery integration tests.
- API/OpenAPI contract checks.
- Migration tests if new schema changes are introduced.

Do not run destructive tests against normal development data.

Preserve the frozen registry-v1, Phase 5 model, and accepted Phase 6A behavior.

---

## 12. Documentation and handoff

Update the relevant current-facing documentation:

```text
docs/EXTRACTION.md
docs/PROVENANCE.md
docs/ARCHITECTURE.md
docs/ROADMAP.md
docs/PROJECT_STATUS.md
```

Create:

`docs/PHASE6B_HANDOFF.md`

Document:

1. Implemented orchestration architecture and execution flow.
2. Work-unit claiming, concurrency, idempotency, and recovery guarantees.
3. Provider abstraction and supported execution profiles.
4. Prompt/model/schema versioning.
5. Retry, cancellation, and state-transition semantics.
6. Execution telemetry and resource/cost controls.
7. Public API additions.
8. Important Phase 6A compatibility decisions and any migrations.
9. Actual tests and verification results.
10. Known limitations and operational risks.
11. Setup instructions for fake-provider validation and optional live-provider execution.
12. Requirements and integration contracts for Phase 6C.

Explicitly distinguish what is operationally implemented from future extraction intelligence.

---

## 13. Completion criteria

Phase 6B is complete when:

- [ ] An eligible document can initiate a persistent extraction run.
- [ ] Profiles and selected inputs are versioned and pinned.
- [ ] Equivalent active runs are deduplicated.
- [ ] Intentional re-extraction preserves history.
- [ ] Celery workers safely execute logical work units.
- [ ] A deterministic fake provider completes an end-to-end extraction workflow.
- [ ] OpenAI provider infrastructure is implemented behind an explicit enablement boundary.
- [ ] Work-unit results use Phase 6A atomic publication.
- [ ] Duplicate deliveries cannot create competing committed results.
- [ ] Successful work is preserved across partial failures.
- [ ] Failed work can be retried without resending successful units.
- [ ] Crashed/stale workers can be recovered without indefinite running states.
- [ ] Late or superseded workers cannot publish results.
- [ ] Cooperative cancellation works without corrupting history.
- [ ] Run states remain consistent with all required and optional work-unit states.
- [ ] Resource limits and relevant telemetry are enforced.
- [ ] Start, retry, and cancel APIs follow existing authorization and response conventions.
- [ ] Focused integration tests demonstrate the important failure and recovery scenarios.
- [ ] Documentation and `PHASE6B_HANDOFF.md` accurately reflect the implementation.

---

## Final instructions

Build a **reliable orchestration foundation that Phase 6C–6E can extend without redesigning the execution system**.

Prioritize:

1. Correctness and data integrity.
2. Recovery and idempotency.
3. Reproducibility and provenance.
4. Security and cost containment.
5. Maintainability and operational simplicity.

Avoid premature optimization, speculative features, and unnecessary abstractions.

Do not modify Phase 5 canonical engineering semantics, introduce automatic candidate acceptance, perform cross-document equipment matching, or implement downstream validation/reconciliation.

Do not implement production equipment-attribute extraction, table interpretation, advanced OCR/layout processing, or the frontend extraction workspace.

**Deliver Phase 6B on its dedicated branch, with a documented technical design, tested implementation, and clear handoff to Phase 6C.**