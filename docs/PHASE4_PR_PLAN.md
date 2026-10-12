# Phase 4 — PR plan

How Phase 4 (AI-assisted document classification) is delivered: a sequence of small, reviewable pull requests. Work through them in order. Each one is a self-contained unit that leaves `main` green.

- Specification: [`cursor/phase4_specs.txt`](../cursor/phase4_specs.txt). Section references below (`§11`) point at it.
- Decisions: [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Proposed until PR-09)
- Phase status: [PROJECT_STATUS.md](PROJECT_STATUS.md)

This file is the delivery plan. If a PR forces a change to the plan or the spec, update this file (and the spec) in that PR and say so in the PR description.

Related work stays in one PR. Taxonomy definitions, the classification profile, prompts, sampling, and provider contracts are one vocabulary. `ensure`, `retry`, `reclassify`, `claim`, document classification, and conditional page classification are one state machine. Telemetry rows are written by that same run, so they ship with it. The extraction worker, dedicated queue, OpenAI adapter, Phase 3 completion trigger, and backfill are one way classification actually starts. Status, history, accept, retry, reclassify, the list summary, and acceptance provenance are one HTTP surface. The revision-workspace classification column, review actions, mixed-page list, and retry/reclassify controls are one UI change.

## Contents

1. [Working agreements](#1-working-agreements)
2. [PR overview and tracker](#2-pr-overview-and-tracker)
3. [Dependency graph](#3-dependency-graph)
4. [PR details](#4-pr-details)
5. [Traceability: spec to PR](#5-traceability-spec-to-pr)
6. [Open decisions](#6-open-decisions)
7. [Intermediate-state compatibility](#7-intermediate-state-compatibility)
8. [Risks](#8-risks)
9. [Coverage audit and intentional exclusions](#9-coverage-audit-and-intentional-exclusions)

---

## 1. Working agreements

### Per-PR rules

1. **One PR, one purpose.** Do not pull work forward from a later PR. Do not add OCR, equipment extraction, table extraction, embeddings, RAG, cost accounting, page-level approval, automatic acceptance, or engineering-model code "while we're here" (§59).
2. **`main` stays green and runnable.** Every PR must pass the full gate below and must not break Phase 0–3 behavior.
3. **Branch naming:** `phase4/pr-NN-short-name`. Commit messages: short imperative summary; body explains why.
4. **Tests ship with the code they cover**, not in a later PR. Each PR lists its required tests; a PR without them is not done.
5. **Docs ship with behavior.** When a PR changes behavior the Phase 4 docs describe, it corrects those docs in the same PR. Docs written ahead of implementation (PR-01) describe the target; each PR verifies its slice and fixes drift.
6. **Record deviations.** Anything that differs from the spec goes in the PR description under "Deviations" and in the spec/ADR if it is lasting.
7. **Do not commit** `apps/web/tsconfig.tsbuildinfo` changes. Restore it with `git checkout -- apps/web/tsconfig.tsbuildinfo` before committing.
8. **No live OpenAI in CI or normal pytest.** Automated tests use the fake provider or a mocked SDK boundary. Do not put `OPENAI_API_KEY` in Compose, source control, the API image, `document-worker`, or `validation-worker`.

### Verification gate (run before opening and before merging)

```bash
source .venv/bin/activate
ruff check .
pytest                                         # unit tests; integration skipped

# Integration tests: ALWAYS use a throwaway database (they never clean up)
docker exec powerforge-postgres-1 psql -U powerforge -d postgres -c "CREATE DATABASE powerforge_test;"
export DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_test
alembic -c database/alembic.ini upgrade head
RUN_INTEGRATION=1 pytest
docker exec powerforge-postgres-1 psql -U powerforge -d postgres -c "DROP DATABASE powerforge_test;"
unset DATABASE_URL

# Web (required from PR-07; cheap, so run always after PR-03 if the tree is dirty)
cd apps/web && npm run lint && npm test && npx tsc --noEmit
git checkout -- tsconfig.tsbuildinfo
```

CI (`.github/workflows/ci.yml`) runs the same with `RUN_INTEGRATION=1` and `npm run build`. From PR-04 onward, classification tests use the fake provider. From PR-05 onward, OpenAI adapter tests mock the SDK and must not open a network socket. Any test that talks to MinIO uses the existing scratch-bucket fixture.

### PR description template

```
## Summary
## Spec sections / ADR decisions covered
## Changes (files/modules)
## Tests added (and what they prove)
## Verification run (commands + results — only what was actually executed)
## Deviations from spec / plan
## Follow-ups / debt
```

### Sizing

XS < 50 lines, S < 300, M < 800, L > 800 (excluding generated code and lockfiles). Anything trending past L should be split along the seam named in that PR, not by moving required tests out.

---

## 2. PR overview and tracker

Update the checkbox and status when a PR merges; keep [PROJECT_STATUS.md](PROJECT_STATUS.md) in sync.

| PR | Title | Area | Size | Depends on | Status |
| --- | --- | --- | --- | --- | --- |
| [PR-01](#pr-01--specification-adr-and-documentation) | Specification, ADR-006, docs, this plan | Docs | S | — | [x] landed in `3063120` |
| [PR-02](#pr-02--classification-contracts-profile-and-prompts) | Classification contracts, profile, and prompts | Domain | M | PR-01 | [x] landed in `e962e9e` |
| [PR-03](#pr-03--migration-0006-and-classification-models) | Migration `0006` and classification models | DB | M | PR-02 | [x] landed in `ca91cfd` |
| [PR-04](#pr-04--classification-service-and-fake-provider) | Classification service and fake provider | Backend | L | PR-02, PR-03 | [x] landed in `9d9460a` |
| [PR-05](#pr-05--worker-queue-openai-adapter-trigger-and-backfill) | Worker, queue, OpenAI adapter, trigger, and backfill | Backend/Infra | L | PR-04 | [x] landed in `3ef0ccf` |
| [PR-06](#pr-06--classification-apis-and-acceptance-provenance) | Classification APIs and acceptance provenance | Backend | L | PR-04 | [x] landed in `dfb0fc3` |
| [PR-07](#pr-07--classification-workspace-ui) | Classification workspace UI | Web | M | PR-06 | [x] landed in `938639d` |
| [PR-08](#pr-08--evaluation-harness) | Evaluation harness | Tooling | M | PR-04 | [ ] |
| [PR-09](#pr-09--hardening-verification-and-phase-4-completion) | Hardening, verification, and Phase 4 completion | All | M | all | [ ] |

PR-05, PR-06, and PR-08 are independent of each other after PR-04. PR-07 needs PR-06 (the list payload). PR-08 can merge in parallel with PR-06/PR-07.

---

## 3. Dependency graph

Each line reads "PR needs → these PRs merged first".

```
PR-01   needs  —
PR-02   needs  PR-01
PR-03   needs  PR-02
PR-04   needs  PR-02, PR-03
PR-05   needs  PR-04
PR-06   needs  PR-04
PR-07   needs  PR-06
PR-08   needs  PR-04
PR-09   needs  everything
```

```
Docs/domain:     PR-01 ─► PR-02 ─► PR-03 ─► PR-04 ─┬─► PR-05
                                                   ├─► PR-06 ─► PR-07
                                                   └─► PR-08
                                                              then PR-09
```

Practical ordering (one engineer): 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09.

If work is parallelized: PR-05 (worker), PR-06 (API), and PR-08 (eval) can proceed after PR-04; PR-07 waits for PR-06.

---

## 4. PR details

### PR-01 — Specification, ADR, and documentation

**Status.** Done. Spec, ADR-006 (Proposed), Phase 4 documentation, and this plan are on `main` (`3063120`).

**Goal.** Land the written design before code: the Phase 4 spec (already in the tree), ADR-006 (Proposed), Phase 4 doc updates, and this plan. (§1, §64, §68 steps 1–2 and 4)

**Depends on.** Nothing.

**Scope.** Documentation only.

- Already present: `cursor/phase4_specs.txt`.
- New: `decisions/ADR-006-ai-document-classification.md` (Proposed; the 20 decisions in spec §64), `docs/PHASE4_PR_PLAN.md` (this file).
- Updated: `README.md`, `docs/PROJECT_STATUS.md` (specified, not implemented; baseline recorded 2026-10-11), `docs/ARCHITECTURE.md`, `docs/DOCUMENT_PIPELINE.md`, `docs/PROVENANCE.md`, `docs/EXTRACTION.md`, `docs/DEVELOPMENT.md`, `docs/PHASE0_HANDOFF.md`.

ADR-006 must record at least the 20 numbered decisions in spec §64. It must not claim the code exists.

**Out of scope.** Any Python, TypeScript, migration, Compose, or dependency change.

**Acceptance.**
- All relative links resolve.
- No statement claims Phase 4 is implemented.
- `git diff` contains only documentation.

**Size.** S.

---

### PR-02 — Classification contracts, profile, and prompts

**Status.** Done. Provider contracts, taxonomy v2, the default profile hash, sampling, prompts, and error codes are on `main` (`e962e9e`). The live `DocumentClassification` enum is unchanged. ADR-006 remains Proposed.

**Goal.** Add the provider-neutral classification vocabulary that every later PR imports. No database writes. No OpenAI SDK. (§5, §18, §22–§28, §36 error codes, §61, §62)

**Depends on.** PR-01.

**Scope.**
- New package `packages/document-classification` (`powerforge_document_classification`). It may depend on `pydantic`, `powerforge-document-model`, and `powerforge-ai`. It must not depend on FastAPI, Celery, SQLAlchemy, boto3, Pillow, PyMuPDF, or the OpenAI SDK.
- Extend `packages/ai` with provider-neutral contracts only:
  - `ClassificationProvider` with `classify_document(...)` and `classify_pages(...)`
  - request/response models: predicted type, confidence score, alternatives (max 3), rationale, usage metadata, provider response id
  - do not expose vendor SDK types
- Versioned taxonomy definition `document-taxonomy-v2` in `packages/document-classification`, including `MIXED_DOCUMENT` and the UNKNOWN / OTHER / MIXED_DOCUMENT semantics from §5. The live `DocumentClassification` Python enum is **not** changed in this PR (that lands with the PostgreSQL value in PR-03 so existing enum-equality tests stay green).
- Classification profile: `document_image_sample_count=5`, `document_text_sample_count=20`, `max_text_chars_per_page=2000`, `page_classification_batch_size=8`, `image_artifact_type=THUMBNAIL`, `image_detail=low`, `high_confidence_threshold=0.85`, `medium_confidence_threshold=0.60`. Deterministic serialization and `sampling_profile_hash`. Changing a material field changes the hash.
- Confidence-band helper: score ≥ 0.85 → HIGH, ≥ 0.60 → MEDIUM, else LOW. The model does not return a band.
- Classifier identity hash over provider, model, `processing_run_id`, classifier version, taxonomy version, prompt version, and sampling profile hash.
- Deterministic page-sampling helpers (pure; no storage): first/last plus evenly spaced interior pages; no randomness.
- Versioned prompt files:
  - `prompts/document_classifier_v1.txt`
  - `prompts/page_classifier_v1.txt`
  - untrusted-document-content rule, UNKNOWN vs OTHER, MIXED_DOCUMENT semantics (document prompt) / MIXED_DOCUMENT prohibited (page prompt), no engineering-fact extraction
- Classification error-code enum matching §36, including `PROVIDER_TIMEOUT` and `CLASSIFICATION_TASK_TIMEOUT` as distinct values.
- Install the new package from root `pyproject.toml`, `requirements-dev.txt`, and CI. `packages/ai` stays free of the OpenAI SDK.

**Out of scope.** `MIXED_DOCUMENT` on the live `DocumentClassification` enum, Alembic, ORM models, fake provider behavior beyond the contract types, OpenAI adapter, Celery, HTTP, frontend.

**Tests** (unit, no DB):
- taxonomy definition includes every current Phase 2 class plus `MIXED_DOCUMENT`
- UNKNOWN, OTHER, and MIXED_DOCUMENT remain distinct in the definition
- page-taxonomy helper rejects `MIXED_DOCUMENT`
- profile hash is stable for the default profile and changes when sample count or thresholds change
- hash does not depend on dict key order
- identity hash changes when prompt version, taxonomy version, or `processing_run_id` changes
- sampling of N ≤ sample count returns every page; larger N includes first and last and is deterministic
- confidence bands derived correctly at 0.59 / 0.60 / 0.84 / 0.85
- prompts mention untrusted data, the taxonomy, and do not ask for ratings or topology
- `powerforge_document_classification` and `powerforge_ai` do not import FastAPI, Celery, SQLAlchemy, boto3, or `openai`

**Acceptance.** `ruff` clean. Phase 2/3 enum-equality tests still pass because the live Python enum is unchanged.

**Size.** M.

---

### PR-03 — Migration `0006` and classification models

**Status.** Done. Migration `0006_document_classification` and the unused classification mappings are on `main` (`ca91cfd`). `MIXED_DOCUMENT` is on the live enum. ADR-006 remains Proposed.

**Goal.** Persist the Phase 4 schema and add `MIXED_DOCUMENT` to the live taxonomy. No classification behavior yet. (§5, §10, §13–§16, §37, §60)

**Depends on.** PR-02.

**Scope.**
- `MIXED_DOCUMENT` on `DocumentClassification` in `packages/document-model`, immediately before `OTHER` (keep `UNKNOWN` last). Update frontend `DOCUMENT_TYPES`, labels, and the existing 16-type assertions so the manual-type dropdown can select Mixed Document. That is the only web change in this PR.
- `database/migrations/0006_document_classification.py` (single reversible migration; never edit 0001–0005):
  - `ALTER TYPE document_classification ADD VALUE 'MIXED_DOCUMENT'` before `OTHER` if the existing label order allows it; otherwise add the value and document the PostgreSQL enum-order limitation. PostgreSQL cannot remove an enum value on downgrade: `downgrade()` must drop new tables and the new column, and must document that the enum label stays (spec §60).
  - `document_classification_runs` with the §10 columns, including `classifier_identity_hash`, `retry_of_run_id`, `attempt_number`, stage, progress, and timestamps
  - composite FK so `document_id` matches the `Document` on `processing_run_id`
  - partial unique index on `classifier_identity_hash` WHERE `status IN ('PENDING', 'RUNNING')` — not Phase 3's live-run index; `COMPLETED` is excluded
  - `classification_predictions` with the §13 columns; DOCUMENT scope requires `document_page_id IS NULL`; PAGE scope requires it NOT NULL; page predictions cannot be `MIXED_DOCUMENT`; one document prediction per run; one page prediction per `(run, document_page_id)`
  - composite ownership so a page prediction's `document_page_id` belongs to the run's document
  - `classification_ai_calls` with the §37 columns; no cost or pricing fields
  - `revision_documents.accepted_classification_prediction_id` nullable; composite FK `(accepted_classification_prediction_id, document_id)` → `(classification_predictions.id, classification_predictions.document_id)` if it fits the current schema
  - indexes and checks as required; no `ON DELETE CASCADE`
- ORM mappings on the shared `Base` in `packages/document-processing` (same registry as `Document` / `DocumentProcessingRun`). `packages/document-classification` stays free of SQLAlchemy in this PR if the mappings fit cleanly next to the Phase 3 models; if they need to live in the classification package, that package may then depend on SQLAlchemy and `powerforge-document-processing`, and the API/worker keep a single mapping of each table.
- Enum labels in the migration are hard-coded; tests assert they equal the Python enums.

**Out of scope.** Service logic, provider calls, routes, worker image, acceptance behavior, copying `accepted_classification_prediction_id` on inheritance (the column is always null until PR-06).

**Tests.**
- `tests/test_migration_0006.py` (integration, scratch database it creates and drops):
  - upgrade on empty DB reaches `0006`; upgrade from `0005` with existing documents, pages, and processing runs preserves them
  - downgrade removes the new tables and column; the leftover `MIXED_DOCUMENT` enum label is documented and asserted
  - re-upgrade succeeds
- `tests/test_phase4_constraints.py` (integration, raw inserts, rolled back):
  - two `FAILED` runs for the same identity insert
  - two `COMPLETED` runs for the same identity insert
  - a second `PENDING` or `RUNNING` run for the same identity is rejected
  - `FAILED` plus one `PENDING` is allowed
  - `COMPLETED` plus one `PENDING` is allowed (reclassify)
  - document prediction requires null `document_page_id`; page prediction requires a page
  - page prediction `MIXED_DOCUMENT` rejected
  - two document predictions on one run rejected
  - two page predictions for the same `(run, page)` rejected
  - run `document_id` that disagrees with the processing run's document is rejected
  - page prediction whose page belongs to another document is rejected
  - accepted-prediction composite FK rejects a prediction from another document
  - `classification_ai_calls` has no `estimated_cost_usd` / `pricing_version` columns

**Acceptance.** `alembic upgrade head` clean on a fresh DB and on a `0005` DB with Phase 3 data. Phase 0–3 tests still pass. New tables unused by the running app. Manual type dropdown includes Mixed Document and does not yet show AI suggestions.

**Size.** M.

---

### PR-04 — Classification service and fake provider

**Status.** Done. The classification service and fake provider are on `main` (`9d9460a`). Uploads still only start Phase 3 processing. ADR-006 remains Proposed.

**Goal.** Orchestrate one classification attempt against the fake provider: assemble bounded input, run document classification, run page classification when required, persist immutable predictions and usage telemetry. Enqueue is a port. (§6–§12, §19, §24–§30, §34–§37, §44, §53, §56)

**Depends on.** PR-02, PR-03.

**Scope.**
- Classification settings on the shared settings object with safe defaults: `AI_CLASSIFICATION_ENABLED=false`, `AI_PROVIDER=fake`, model `gpt-6-luna`, reasoning effort `none`, image detail `low`, `AI_CLASSIFICATION_TIMEOUT_SECONDS`, task soft/hard time limits (soft < hard). `OPENAI_API_KEY` is optional. The API and `document-worker` must still start with no key.
- `FakeClassificationProvider` in `packages/document-classification` (or `packages/ai`) implementing the same `ClassificationProvider` contract. Deterministic scenarios for high-confidence single type, `MIXED_DOCUMENT`, UNKNOWN / low confidence, provider failure, and invalid structured output. No network. No OpenAI key.
- Input assembly in `packages/document-classification`:
  - current completed processing run only (Phase 3 `current_run` for the active profile, and only when `COMPLETED`)
  - page set `1..pages_total` of that run
  - thumbnails and native text from that run's `THUMBNAIL` / `NATIVE_TEXT` artifacts through `ObjectStorage`
  - send stored thumbnail bytes and `mime_type` (WebP, or PNG when that is what is stored)
  - character cap; missing native text is allowed
  - never include `RevisionDocument.document_type`
  - never send the original PDF
- Classification service in `packages/document-classification`. The Celery task and the API will call this. The service does not import FastAPI, Celery, or the OpenAI SDK.
- Enqueue port: `enqueue_document_classification(run_id) -> None`. This PR ships a recording fake. A failed enqueue after insert leaves the run `PENDING` and does not fail Phase 3 processing.
- `ensure_document_classification(...)` per §11: reuse compatible `COMPLETED`; return `RUNNING`; re-enqueue unclaimed `PENDING`; do not retry `FAILED`.
- `retry_failed_classification(...)` and `reclassify_document(...)` per §11: new rows; 409 `classification_in_progress` / `classification_not_retryable` as specified.
- Worker `claim_and_classify(run_id)`:
  - atomic `PENDING` → `RUNNING`
  - duplicate claim of a non-`PENDING` run returns without a provider call
  - document classification first; persist one document prediction; derive the band in-process
  - page classification when `MIXED_DOCUMENT`, `UNKNOWN`, or score < high threshold; every expected page; batches of 8; reject missing/duplicate/unexpected pages and page-level `MIXED_DOCUMENT`
  - `COMPLETED` only when the document prediction exists and, if required, every expected page has a prediction
  - persist `ClassificationAICall` rows (tokens, latency, image count, provider response id). No prompts, images, document text, or cost fields
  - invalid provider output or missing thumbnail → `FAILED` with the named code
- Disabled mode: `ensure` / retry / reclassify raise a clean `AI_CLASSIFICATION_DISABLED` and do not insert a run.
- Structured logs: run id, document id, status, error code, token counts, latency. No document text, image bytes, keys, or full prompts.

**Out of scope.** Celery task body beyond a future one-liner, OpenAI adapter, HTTP routes, frontend, evaluation CLI, changing Phase 3 processing.

**Tests** (`tests/test_classification_service.py` and a concurrency/integration sibling):
- `COMPLETED` Phase 3 run required; `PENDING`/`RUNNING`/`FAILED` processing rejected
- page set is `1..pages_total` of that run; extra `DocumentPage` rows are ignored
- native text comes from that run's artifact, not `native_text_char_count` alone
- missing thumbnail → `ARTIFACT_UNAVAILABLE`
- original PDF is never read for the provider
- `RevisionDocument.document_type` is not in the assembled input
- high-confidence single type does not classify pages
- `MIXED_DOCUMENT`, `UNKNOWN`, and below-high score do
- every required page gets one prediction; mismatch fails the run
- page prediction cannot be `MIXED_DOCUMENT`
- `PENDING` → `RUNNING` → `COMPLETED`; provider failure → `FAILED`; partial pages never `COMPLETED`
- duplicate claim does not call the provider
- compatible completed run reused; compatible running run reused; unclaimed `PENDING` re-enqueued
- `FAILED` is not auto-retried; explicit retry inserts a new run; reclassify inserts a new run while a completed run exists
- second live run for the same identity is rejected
- a different identity may be pending while another identity is in flight
- three revisions sharing one document reuse one compatible completed classification
- usage tokens and latency persisted; no prompt/image/document payload; no cost columns
- disabled mode inserts nothing
- failed-run predictions remain stored and are not the current suggestion

**Acceptance.** Service tests do not start Celery and do not import `openai`. Phase 3 upload still does not enqueue classification. Settings default keeps classification off.

**Size.** L. If review stalls, split only along this seam: input assembly + fake provider first, then the run state machine. Do not split document classification from page classification. Do not move telemetry to a later PR.

---

### PR-05 — Worker, queue, OpenAI adapter, trigger, and backfill

**Status.** Done. The classification worker, queue, OpenAI adapter, and backfill are on `main` (`3ef0ccf`). Classification stays off until enabled. There is no classification API or UI. ADR-006 remains Proposed.

**Goal.** Run the service asynchronously and start classification for new and existing processed documents. Worker, dedicated queue, OpenAI adapter, post-processing enqueue, and backfill are one operational path. (§20–§21, §31–§36, §38, §45–§46, §54, §63)

**Depends on.** PR-04.

**Scope.**
- Dedicated Celery queue `document_classification`. Only `extraction-worker` consumes it. `document-worker` and `validation-worker` do not register the classification task and do not consume that queue.
- Task in `services/extraction-worker`: load settings, storage, a DB session, call `claim_and_classify`. Soft/hard time limits from settings (soft < hard). On `SoftTimeLimitExceeded`, mark the run `FAILED` with `CLASSIFICATION_TASK_TIMEOUT` and commit before exit. A single provider call that exceeds `AI_CLASSIFICATION_TIMEOUT_SECONDS` is `PROVIDER_TIMEOUT`. Those codes stay distinct.
- `OpenAIClassificationProvider` in the extraction-worker package (not in `packages/document-model` or the classification domain modules):
  - official OpenAI Python SDK, Responses API, Structured Outputs, `store=false`, no tools, no Chat Completions, no background Responses, no conversations
  - configurable model (default `gpt-6-luna`), reasoning effort, image detail
  - image bytes from ObjectStorage as SDK image input (base64 or equivalent); use the artifact `mime_type`
  - map refusals and provider errors to the §36 codes
  - record usage metadata; do not leak Response objects past the adapter
- Enqueue implementation used by the API, `document-worker`, and backfill: `send_task` by task name. Live in `packages/document-classification` (or a sibling module), mirroring `powerforge_document_processing.enqueue`. The API and `document-worker` must not import `extraction_worker`. Only the enqueue module in the classification package may import Celery.
- After Phase 3 successfully commits `COMPLETED`, `document-worker` calls classification `ensure` when `AI_CLASSIFICATION_ENABLED=true`. It does not import the OpenAI SDK. Enqueue failure is logged; the processing run stays `COMPLETED`.
- Extraction-worker image: install `document-classification`, `document-model`, `document-processing`, `powerforge-ai`, the OpenAI SDK, the database driver, boto3. Compose: same `DATABASE_URL` and `S3_*` as the API/document-worker; `CELERY_QUEUE: document_classification`; classification settings; do not put a real API key in `docker-compose.yml`. Use env substitution / `.env`.
- Extraction worker refuses to start when enabled + `AI_PROVIDER=openai` and `OPENAI_API_KEY` is missing. Fake provider and disabled mode start without a key.
- Bounded backfill command: documents whose current processing run is `COMPLETED` and that have no compatible current classification; re-enqueue unclaimed `PENDING`; do not retry `FAILED`; do not adopt `RUNNING`; honor `--limit`. Document the invocation in `docs/DEVELOPMENT.md`.
- Heartbeat remains registered so existing worker tests still have a task.

**Out of scope.** HTTP classification routes, frontend, evaluation harness, monetary cost, changing the Phase 3 renderer.

**Tests.**
- Phase 3 completion publishes one classification task to `document_classification` when enabled
- Phase 3 failure does not enqueue classification
- enqueue failure leaves processing `COMPLETED`
- disabled mode does not enqueue after processing
- classification task is registered only on `extraction-worker`
- Compose binds only `extraction-worker` to `document_classification`
- duplicate delivery is a no-op
- backfill: missing classification is ensured; unclaimed `PENDING` is re-enqueued; `FAILED` and `RUNNING` are left alone; `COMPLETED` compatible is left alone; batch limit is honored; only the current completed processing run is considered
- OpenAI adapter tests (mocked SDK, no network): configured model, Responses API, `store=false`, Structured Outputs, image input, image detail, reasoning effort, no tools, usage mapping, refusal mapping, rate-limit/auth/timeout mapping, no provider objects returned
- provider-call timeout → `PROVIDER_TIMEOUT`; soft time limit → `CLASSIFICATION_TASK_TIMEOUT`
- worker settings include DB and S3; API/document-worker images do not gain `OPENAI_API_KEY`
- existing heartbeat tests pass

**Acceptance.** A local extraction worker consuming `document_classification` can complete a fixture through the fake provider end-to-end. Other workers ignore that queue. No real OpenAI call in CI.

**Size.** L. If review stalls, keep queue, trigger, and backfill together; land extra adapter fixtures as a follow-up commit on the same branch. Do not split the OpenAI adapter into a PR that leaves the worker unable to run.

---

### PR-06 — Classification APIs and acceptance provenance

**Status.** Done. Classification reads, accept, and provenance are on `main` (`dfb0fc3`). Classification stays off until enabled. There is no classification UI. ADR-006 remains Proposed.

**Goal.** Revision-scoped reads and mutations for classification, plus the list/detail summary and the provenance rules that first become meaningful when a prediction can be accepted. (§15–§17, §34, §39–§44, §56)

**Depends on.** PR-04. Does not require PR-05 (tests can drive the service in-process).

**Scope.**
- Extend `RevisionDocumentResponse` (list, detail, and upload) with the lightweight summary from §41:

  ```
  classification:
      enabled
      suggestion: { predicted_type, confidence_band, accepted, requires_page_classification } | null
      attempt: { status, stage, pages_total, pages_classified, error_code } | null
  ```

  `suggestion` is the latest `COMPLETED` run for the current processing run. `accepted` is prediction-id equality. `attempt` is the newest run of any status. A failed or in-flight reclassify leaves `suggestion` populated.
- Routes nested under `/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}` (exact paths may follow repository style):
  - `GET /classification` — enabled flag, suggestion, attempt, score, alternatives, rationale, page-classification availability
  - `GET /classification/runs` — history without provider input
  - `POST /classification/reclassify` — new `PENDING` run; 409 `classification_in_progress` if a live run exists for the current identity
  - `POST /classification/runs/{run_id}/retry` — §11; only the newest `FAILED` run for that identity
  - `GET /classification/pages` — page predictions from the suggestion's `COMPLETED` run only
  - `POST /classification/predictions/{prediction_id}/accept` — §15/§39
- Disabled: explicit classification endpoints return a clean `AI_CLASSIFICATION_DISABLED` (settle the status in D3). Manual metadata edit still works.
- Access: any `RevisionDocument` association may read classification, including `REMOVED`, superseded, and archived, under existing Phase 2/3 evidence rules. Accept is a metadata mutation and follows `assert_documents_mutable`. Inference, retry, and reclassify are not revision mutations.
- Provenance:
  - accept sets `document_type` and `accepted_classification_prediction_id`
  - submitting `document_type` on the existing metadata PATCH clears the prediction id even when the value is unchanged; a patch that omits `document_type` leaves it
  - `copy_included_associations` and `reuse` copy the prediction id with the other metadata; a reuse `document_type` override clears it
- GET routes must not call `ensure` and must not enqueue.
- Cross-project / cross-document accept is impossible. Page predictions cannot be accepted. Predictions from `FAILED` runs cannot be accepted.

**Out of scope.** Frontend, evaluation CLI, OpenAI calls from the API process.

**Tests** (`tests/test_classification_api.py` and updates to mutation/lineage tests):
- list/detail/upload include the summary; no N+1 classification-status fetch in the list handler
- suggestion/attempt split: completed then failed reclassify still returns the completed suggestion
- accept updates type and prediction id; cross-document and page-prediction accept rejected; failed-run accept rejected
- AI never changes `document_type` without accept
- submitting the same `document_type` clears the prediction id; omitting it does not
- inheritance copies the prediction id; reuse without override copies it; reuse with type override clears it
- superseded/archived accept rejected; those associations can still read
- `REMOVED` can read classification
- reclassify / retry 409 cases
- pages withheld unless the suggestion is `COMPLETED`
- disabled endpoints fail cleanly; manual type still works
- status poll does not create a run or publish a task
- Phase 2/3 document tests still pass

**Acceptance.** OpenAPI at `/docs` lists the new routes. Old web clients ignore the unknown `classification` field.

**Size.** L. If review stalls, do not split accept from the list summary; they share the suggestion/attempt contract. Split only extra access fixtures.

---

### PR-07 — Classification workspace UI

**Status.** Done. The revision documents workspace shows the suggestion, accept, and mixed page predictions on `main` (`938639d`). Classification stays off until enabled. ADR-006 remains Proposed.

**Goal.** Show AI classification on the existing revision documents workspace and let the engineer accept, override, retry, or reclassify. Status, review, mixed pages, and failure actions are one surface. (§47–§50)

**Depends on.** PR-06.

**Scope** (`apps/web`):
- Document table gains Confirmed Type and AI Suggestion columns from the list payload. Do not issue one classification-status request per row.
- Attempt states: Not classified, Pending, Classifying, Ready, Failed, AI disabled. A failed or in-flight reclassify keeps the previous suggestion visible.
- Ready unaccepted suggestion: predicted type, HIGH/MEDIUM/LOW, Accept, Choose another type. Do not show "94% certainty".
- Confirmed type differs from suggestion: show both; Use AI Suggestion / Keep Current. Keep Current writes nothing.
- Accept calls the accept route. Choose another type uses the existing manual editor (clears provenance on the server).
- `MIXED_DOCUMENT` suggestion: page-prediction table; clicking a page opens/selects it in the existing page viewer. No page-level approval.
- Failed attempt: concise error (keep `PROVIDER_TIMEOUT` and `CLASSIFICATION_TASK_TIMEOUT` distinguishable) and Retry. Completed suggestion: Reclassify. Disabled: short message; manual type remains.
- Types and client helpers in `apps/web/src/lib/documents.ts` matching the PR-06 DTOs.

**Out of scope.** New backend routes, Playwright, page-level confirmation, cost UI.

**Tests** (vitest, next to the existing revision-documents tests):
- column renders each attempt state from the list payload, including Not classified and AI disabled
- no per-row `/classification` fetch to fill the column
- Accept and Use AI Suggestion call the accept route
- Choose another type opens the existing editor
- Keep Current does not PATCH
- accepted checkmark uses prediction-id equality, not label equality
- failed reclassify still shows the previous suggestion
- Retry only when the attempt is Failed; Reclassify when a completed suggestion exists and no live attempt is in flight
- mixed suggestion exposes page rows and selects the page in the viewer
- read-only banner still hides Phase 2 mutations; reading classification remains available

**Acceptance.** `npm run lint`, `npm test`, `npx tsc --noEmit`. Rebuild the web image to pick it up.

**Size.** M. If the mixed-page table plus viewer wiring pushes the PR past L, keep the column, accept/override, and retry/reclassify in this PR and land the page table as `PR-07b` on top of it. Do not split the column from Accept.

---

### PR-08 — Evaluation harness

**Goal.** Measure classifier quality against an external labeled set without committing confidential documents or calling OpenAI from CI. (§51–§53, §65)

**Depends on.** PR-04. Can merge in parallel with PR-05–PR-07. Fake-provider evaluation must work without PR-05.

**Scope.**
- Eval manifest schema, example manifest, and tiny synthetic/public fixtures committed to the repo.
- CLI evaluation command that runs the classification pipeline (fake by default) and writes a report:
  - document exact-match accuracy
  - per-class precision/recall/F1
  - confusion matrix
  - top-2 accuracy
  - UNKNOWN/abstention rate
  - MIXED_DOCUMENT precision/recall
  - page accuracy for labeled pages
  - average input/output tokens
  - latency statistics
- No `estimated_cost_usd` or pricing metrics.
- `.gitignore` for real evaluation document directories. Do not commit customer/engineering PDFs.
- Document how to point the harness at an external labeled set and how to opt into a live OpenAI smoke run. Live runs stay out of CI.

**Out of scope.** Frontend, Compose changes, making CI fail on accuracy, monetary cost.

**Tests.**
- example manifest validates
- harness runs against the committed synthetic fixtures with the fake provider
- report contains the required metric keys
- ignored paths are in `.gitignore`
- CI workflow does not invoke a live-provider eval

**Acceptance.** `powerforge-eval-classification` (name settled in D8) completes on the example fixtures without `OPENAI_API_KEY`.

**Size.** M.

---

### PR-09 — Hardening, verification, and Phase 4 completion

**Goal.** Prove every requirement is met, correct documentation drift, and close the phase. (§55, §58–§59, §65–§69)

**Depends on.** PR-01 … PR-08.

**Scope.**
- Requirements audit: every §55 test group and every §67 bullet gets a named test or a recorded check in the PR description. Fill gaps here.
- Full-stack verification on a clean checkout: `docker compose down -v && docker compose up --build`; migrate from empty and from a `0005` volume with processed documents; backfill classification; upload a PDF; watch Phase 3 complete; with classification enabled and `AI_PROVIDER=fake`, watch the suggestion appear; accept; create a child revision and confirm no second classification run; reclassify and confirm the confirmed type is unchanged; retry a forced failure; confirm queue isolation; confirm AI-disabled mode; confirm private storage remains private.
- If a real OpenAI key is available, a small explicit smoke against non-confidential/synthetic documents may be recorded separately. Do not claim it if it was not run. Do not make it a CI requirement.
- Docs: re-verify Phase 4 statements in `README`, `ARCHITECTURE`, `DOCUMENT_PIPELINE`, `PROVENANCE`, `EXTRACTION`, `DEVELOPMENT`, `PHASE0_HANDOFF`; finalize deviations and debt in `PROJECT_STATUS.md`.
- ADR-006 → Accepted; set date; note amendments.
- `PROJECT_STATUS.md`: Phase 0–4 complete; next phase remains Phase 5 and is not started; this plan's tracker completed.
- Scope-creep review: `git diff` against Phase 3 for OCR, equipment extraction, tables, SLD topology, embeddings, RAG, cost accounting, ETAP/SKM/EasyPower.
- Final gate: ruff, pytest, `RUN_INTEGRATION=1` on a throwaway DB, web lint/test/tsc/build.
- Engineering handoff required by spec §69 (A–U) in the PR description. State only commands that were actually run.

**Out of scope.** Phase 5 work.

**Acceptance.** Every bullet in spec §67 is demonstrably true; CI green; ADR accepted; no OCR or extraction code in the tree.

**Size.** M (verification and docs).

---

## 5. Traceability: spec to PR

### Spec sections

| Spec § | Topic | PR(s) |
| --- | --- | --- |
| §1 | Inspect repo, baseline, plan | PR-01 lands the record |
| §2–§4 | Goal; authority model; classification belongs to `Document` | PR-03, PR-04, PR-06, PR-09 |
| §5 | Taxonomy and `MIXED_DOCUMENT` | PR-02 (definitions), PR-03 (live enum) |
| §6–§7 | Document vs page; page suggestions only | PR-04, PR-06, PR-07 |
| §8 | Pipeline | PR-04, PR-05 |
| §9 | Current completed processing run and page set | PR-04, PR-05 |
| §10–§12 | Run entity, idempotency, claim | PR-03, PR-04 |
| §13–§14 | Predictions and ownership FKs | PR-03, PR-04 |
| §15–§17 | Accept, composite FK, inheritance/reuse | PR-03 (column), PR-06 (behavior) |
| §18–§19 | Provider contracts and fake provider | PR-02, PR-04 |
| §20–§22 | OpenAI adapter, images, prompt-injection | PR-02 (prompts), PR-05 (adapter) |
| §23–§28 | Versions, schema, confidence, profile, sampling, input | PR-02, PR-04 |
| §29–§30 | Page classification and completion | PR-04 |
| §31–§33 | Worker, queue, auto trigger | PR-05 |
| §34–§36 | Disabled mode, config, failure codes | PR-04, PR-05, PR-06 |
| §37–§38 | Telemetry and data handling | PR-03, PR-04, PR-05 |
| §39–§44 | APIs, list summary, manual type, reads, reclassify | PR-06 |
| §45–§46 | Backfill and extraction-worker environment | PR-05 |
| §47–§50 | Frontend | PR-07 |
| §51–§53 | Evaluation harness and fake tests | PR-04, PR-08 |
| §54 | OpenAI adapter tests | PR-05 |
| §55 | Required tests | each PR; audited in PR-09 |
| §56–§57 | Visibility and logging | PR-04, PR-06, PR-07 |
| §58–§59 | No OCR; non-goals | every PR's out-of-scope; PR-09 review |
| §60 | Migration | PR-03 |
| §61–§63 | Packages, prompts, local experience | PR-02, PR-04, PR-05 |
| §64 | Docs and ADR | PR-01, each PR, PR-09 |
| §65–§67 | Baseline, e2e scenario, definition of done | PR-09 |
| §68 | Implementation order | this plan |
| §69 | Final handoff | PR-09 |

### Definition-of-done bullets (§67)

| Requirement | PR(s) |
| --- | --- |
| Phase 0–3 behavior still passes | every PR (gate) |
| `MIXED_DOCUMENT` exists | PR-02, PR-03 |
| Classification belongs to `Document` | PR-03, PR-04 |
| Classification references the exact completed Phase 3 run | PR-04 |
| OpenAI provider abstraction exists | PR-02, PR-05 |
| Responses API + Structured Outputs; default `gpt-6-luna`; `store=false` | PR-05 |
| No OpenAI credentials reach browser / document-worker / validation-worker | PR-04, PR-05 |
| Deterministic bounded sampling; manual type not fed to AI | PR-02, PR-04 |
| Structured results validated; bands derived in-process | PR-02, PR-04 |
| AI does not auto-change `document_type` | PR-04, PR-06 |
| Engineer can accept; manual submit clears provenance | PR-06, PR-07 |
| Provenance carries through inheritance and reuse | PR-06 |
| Mixed/uncertain documents get page classification; pages cannot be `MIXED_DOCUMENT` | PR-04, PR-07 |
| Page predictions are not human-reviewed truth | PR-06, PR-07 |
| Runs are immutable; retries create new runs; compatible completed is reused | PR-04 |
| Inherited documents are not reclassified unnecessarily | PR-04 |
| Asynchronous; isolated `document_classification` queue | PR-05 |
| Globally disableable; manual type works when disabled | PR-04, PR-06, PR-07 |
| Existing processed documents can be backfilled | PR-05 |
| Reclassification supported; failed/in-flight attempt does not hide suggestion | PR-04, PR-06, PR-07 |
| Usage telemetry persisted; no monetary cost | PR-03, PR-04 |
| Evaluation harness exists; confidential docs not committed | PR-08 |
| Normal tests use fake/mocked providers | PR-04, PR-05, PR-08 |
| UI exposes status/suggestion/confidence/accept/retry/reclassify | PR-07 |
| Mixed documents expose page predictions | PR-07 |
| No OCR, extraction, or engineering model | every PR; PR-09 |
| Docs/ADR/status updated | PR-01, PR-09 |
| `PROVIDER_TIMEOUT` and `CLASSIFICATION_TASK_TIMEOUT` stay distinct | PR-04, PR-05, PR-07 |

### Required test groups (§55)

| Group | PR(s) |
| --- | --- |
| Taxonomy | PR-02, PR-03 |
| Input assembly | PR-02, PR-04 |
| Run lifecycle | PR-04, PR-05 |
| Revision reuse | PR-04 |
| Document classification routing | PR-04 |
| Page classification | PR-04 |
| Human acceptance and provenance | PR-06 |
| Disabled mode | PR-04, PR-05, PR-06 |
| Auto trigger | PR-05 |
| Telemetry | PR-04 |
| Access | PR-06 |
| OpenAI adapter (mocked) | PR-05 |
| Evaluation harness | PR-08 |
| Frontend | PR-07 |
| Regression (Phase 0–3) | every PR |

---

## 6. Open decisions

Settle these in the PR named; record the outcome in that PR's description and, if lasting, in the spec/ADR.

| ID | Decision | Needed by | Proposed default |
| --- | --- | --- | --- |
| D1 | Where does the classification Celery publish helper live so the API and `document-worker` can enqueue without importing `extraction_worker`? | PR-05 | `powerforge_document_classification.enqueue`, using Celery `send_task` by name. Domain modules, input assembly, and the OpenAI adapter stay Celery-free except that one enqueue module. |
| D2 | Default timeout numbers. | PR-04 | `AI_CLASSIFICATION_TIMEOUT_SECONDS=60`; `AI_CLASSIFICATION_TASK_SOFT_TIME_LIMIT_SECONDS=600`; `AI_CLASSIFICATION_TASK_HARD_TIME_LIMIT_SECONDS=660`. Soft must stay below hard. |
| D3 | HTTP status when AI classification is disabled and the client calls an explicit AI route. | PR-06 | **409** `ai_classification_disabled`, matching Phase 3's "not available in this state" codes. Manual metadata routes stay 200. |
| D4 | HTTP status when page predictions are requested and there is no completed suggestion. | PR-06 | **409** `classification_not_complete`. `GET /classification` stays 200 and returns a null suggestion. |
| D5 | Backfill and eval entry points. | PR-05, PR-08 | `powerforge-backfill-classification --limit N`; `powerforge-eval-classification`. Neither is a FastAPI route or a lifespan hook. |
| D6 | Extraction-worker concurrency. | PR-05 | Compose `--concurrency=1`. Claim is already atomic; raising concurrency is a later tuning change. |
| D7 | Exact classification-package import name. | PR-02 | `powerforge_document_classification` in `packages/document-classification`. |
| D8 | Do upload responses include the classification summary? | PR-06 | Yes. Upload uses `RevisionDocumentResponse`. A new upload has a null suggestion and, if processing just enqueued classification, a `PENDING` attempt or null until the classification row exists. |
| D9 | Where do the SQLAlchemy classification mappings live? | PR-03 | Prefer `powerforge_document_processing.models` so API and both workers keep one `Base`. Move them only if that file becomes unreadable; do not create a second mapping of `documents`. |

---

## 7. Intermediate-state compatibility

What a user of the running app sees while Phase 4 is only partly merged:

| After | Behavior |
| --- | --- |
| PR-01 | Docs only. App unchanged. |
| PR-02 | Unused contracts, prompts, and helpers. App unchanged. |
| PR-03 | Rebuild the API image. Compose API runs `alembic upgrade head` to `0006`. New tables empty. Manual type dropdown includes Mixed Document. No AI suggestions. Inheritance still copies the four Phase 2 metadata fields; the new column stays null. |
| PR-04 | No user-visible change. Classification defaults to disabled. Upload and Phase 3 processing still do not enqueue classification. |
| PR-05 | Rebuild API, document-worker, and extraction-worker images. When enabled, a completed Phase 3 run queues classification. The UI does not show it until PR-06/PR-07. Existing processed documents wait for backfill. `document-worker` and `validation-worker` must not be pointed at `document_classification`. |
| PR-06 | List/detail JSON gains a `classification` object. Old web clients ignore unknown fields. Swagger can accept, retry, and reclassify. Rebuild the API image. |
| PR-07 | Suggestion column, accept/override, mixed pages, and retry/reclassify. The list suggestion includes the prediction id. Rebuild the web image and the extraction-worker image. |
| PR-08 | CLI and fixtures only. App unchanged. |
| PR-09 | Docs and audit only. After pulling, `docker compose down -v && docker compose up --build` if you want a clean stack. |

Never merge a PR that requires a later PR to avoid breaking existing flows. After PR-03, PR-05, and PR-07, rebuild the affected images.

---

## 8. Risks

| Risk | Mitigation |
| --- | --- |
| Adding `MIXED_DOCUMENT` to the Python enum before the PostgreSQL value breaks Phase 2 enum-equality tests | Change the live enum only in PR-03, in the same migration that adds the label |
| Copying Phase 3's live-run index (which includes `COMPLETED`) blocks reclassify | PR-03 index is `PENDING`/`RUNNING` only; constraint tests prove two `COMPLETED` rows insert |
| `DocumentPage` rows from an older longer processing run are classified | PR-04 uses `1..pages_total` of the referenced completed run and that run's artifacts |
| Default Celery queue steals the classification task | Dedicated queue and consume list in PR-05; registration test on the other workers |
| `document-worker` imports OpenAI or `extraction_worker` | Enqueue-by-name helper (D1); import guard tests |
| Shared `Settings` requires `OPENAI_API_KEY` and the API fails to boot | Key stays optional; only extraction-worker refuses to start when openai+enabled and the key is missing |
| A list `status` field hides a completed suggestion after a failed reclassify | Suggestion/attempt split in PR-06/PR-07; tests for that payload |
| Manual PATCH of the current type leaves false AI provenance | PR-06 clears the prediction id whenever `document_type` is present |
| Reuse drops provenance while create-revision copies it | Both copy paths are in PR-06 and tested together |
| Soft time limit recorded as `PROVIDER_TIMEOUT` | Distinct codes and tests in PR-05 |
| PR-04, PR-05, PR-06 grow past L | Split only along the seams named in those PRs |
| Live OpenAI slips into CI | Fake/mocked tests; PR-09 diff review; no key in Compose |
| OCR or extraction slips in | Out-of-scope lists; PR-09 import/diff review |

---

## 9. Coverage audit and intentional exclusions

**Audit.** Every spec section (§1–§69), every test group in spec §55, and every §67 bullet is mapped to a PR scope in section 5. Gaps found while writing this plan and closed here: suggestion/attempt list contract (PR-06), live-run index excluding `COMPLETED` (PR-03), current processing-run page set (PR-04), reuse as well as inheritance provenance (PR-06), distinct task vs provider timeouts (PR-05), optional OpenAI key on shared settings (PR-04/PR-05), frontend type list updated with the live enum (PR-03). Re-audit in PR-09 against named tests.

**Intentionally not covered by any PR** (spec §59 and recorded debt):

- OCR, Tesseract, cloud OCR
- Equipment detection, tags, ratings, nameplate fields
- Table, schedule, or cable extraction
- SLD symbol recognition or topology
- Entity matching/resolution, engineering-model persistence, conflict reconciliation
- Embeddings, vector databases, RAG
- ETAP/SKM/EasyPower, power-system calculations, study reports
- Automatic high-confidence acceptance
- Page-level engineer approval
- Stronger-model escalation or automatic high-detail image escalation
- `estimated_cost_usd`, pricing tables, cost-per-document/project/customer accounting
- A stale-`RUNNING` classification sweeper (same class as the Phase 3 processing-run debt)
- Resuming a failed page-classification run at the next batch
- Browser end-to-end (Playwright) automation: UI is covered by vitest plus the PR-09 walk-through
- Authentication and non-null `uploaded_by`

Phase 4 answers only "what kind of document/page is this?"
