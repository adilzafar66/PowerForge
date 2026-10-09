# Phase 3 — PR plan

How Phase 3 (document processing and stable page representation) is delivered: a sequence of small, reviewable pull requests. Work through them in order. Each one is a self-contained unit that leaves `main` green.

- Specification: [`cursor/phase3_specs.txt`](../cursor/phase3_specs.txt). Section references below (`§18`) point at it.
- Decisions: [ADR-005](../decisions/ADR-005-document-processing-and-page-identity.md) (Proposed until PR-10)
- Conceptual plan: [PHASE3_PLAN.md](PHASE3_PLAN.md)
- Phase status: [PROJECT_STATUS.md](PROJECT_STATUS.md)

This file is the delivery plan. If a PR forces a change to the plan or the spec, update this file (and the spec) in that PR and say so in the PR description.

Related work stays in one PR. PDF, PNG, JPEG, and TIFF rendering is one pipeline. `ensure`, `retry`, and `claim` are one state machine. Worker, queue, enqueue-after-upload, and backfill are one way processing actually starts. Status, retry, and the page viewer are one revision-workspace change.

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

1. **One PR, one purpose.** Do not pull work forward from a later PR. Do not add OCR, classification, layout analysis, table extraction, evidence rows, or engineering-model code "while we're here" (§32).
2. **`main` stays green and runnable.** Every PR must pass the full gate below and must not break Phase 0–2 behavior.
3. **Branch naming:** `phase3/pr-NN-short-name`. Commit messages: short imperative summary; body explains why.
4. **Tests ship with the code they cover**, not in a later PR. Each PR lists its required tests; a PR without them is not done.
5. **Docs ship with behavior.** When a PR changes behavior the Phase 3 docs describe, it corrects those docs in the same PR. Docs written ahead of implementation (PR-01) describe the target; each PR verifies its slice and fixes drift.
6. **Record deviations.** Anything that differs from the spec goes in the PR description under "Deviations" and in the spec/ADR if it is lasting.
7. **Do not commit** `apps/web/tsconfig.tsbuildinfo` changes. Restore it with `git checkout -- apps/web/tsconfig.tsbuildinfo` before committing.

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

# Web (required from PR-09; cheap, so run always after PR-01 if the tree is dirty)
cd apps/web && npm run lint && npm test && npx tsc --noEmit
git checkout -- tsconfig.tsbuildinfo
```

CI (`.github/workflows/ci.yml`) runs the same with `RUN_INTEGRATION=1` and `npm run build`. From PR-05 onward, rendering tests that need real files stay in-process. From PR-07 onward, any test that talks to MinIO uses the existing scratch-bucket fixture.

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
| [PR-01](#pr-01--specification-adr-and-documentation) | Specification, ADR-005, docs, this plan | Docs | S | — | [x] landed in `2efaaca` |
| [PR-02](#pr-02--processing-domain-vocabulary) | Processing domain vocabulary | Domain | S | PR-01 | [x] landed in `bc9d9f4` |
| [PR-03](#pr-03--shared-processing-library-extract) | Shared library extract (models + storage) | Backend | L | PR-01 | [x] landed in `ebfd2da` |
| [PR-04](#pr-04--migration-0005-and-processing-models) | Migration `0005` and processing models | DB | M | PR-02, PR-03 | [x] landed in `69891d6` |
| [PR-05](#pr-05--page-rendering-and-artifact-production) | Page rendering and artifact production | Backend | L | PR-02 | [ ] |
| [PR-06](#pr-06--processing-service-and-run-lifecycle) | Processing service and run lifecycle | Backend | L | PR-04, PR-05 | [ ] |
| [PR-07](#pr-07--worker-queue-enqueue-and-backfill) | Worker, queue, enqueue, and backfill | Backend/Infra | M | PR-06 | [ ] |
| [PR-08](#pr-08--processing-and-page-apis) | Processing and page APIs | Backend | M | PR-06 | [ ] |
| [PR-09](#pr-09--processing-status-and-page-viewer-ui) | Processing status and page viewer UI | Web | M | PR-08 | [ ] |
| [PR-10](#pr-10--hardening-verification-and-phase-3-completion) | Hardening, verification, and Phase 3 completion | All | M | all | [ ] |

PR-07 and PR-08 are independent of each other after PR-06. PR-09 needs PR-08 (the list payload). PR-07 can merge in parallel with PR-08.

---

## 3. Dependency graph

Each line reads "PR needs → these PRs merged first".

```
PR-01   needs  —
PR-02   needs  PR-01
PR-03   needs  PR-01
PR-04   needs  PR-02, PR-03
PR-05   needs  PR-02              (can proceed in parallel with PR-03/PR-04)
PR-06   needs  PR-04, PR-05
PR-07   needs  PR-06
PR-08   needs  PR-06
PR-09   needs  PR-08
PR-10   needs  everything
```

```
Docs/domain:     PR-01 ─► PR-02 ─► PR-04 ─┐
                    └────► PR-03 ─────────┘
Render spine:    PR-02 ─► PR-05 ──────────► PR-06 ─┬─► PR-07
                                                   └─► PR-08 ─► PR-09
                                                              then PR-10
```

Practical ordering (one engineer): 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10.

If work is parallelized: PR-03 (extract) and PR-05 (renderer) can proceed after PR-02; PR-07 and PR-08 can proceed in parallel after PR-06.

---

## 4. PR details

### PR-01 — Specification, ADR, and documentation

**Status.** Done. Spec, ADR-005 (Proposed), Phase 3 documentation, and this plan are on `main` (`2efaaca`). Committed directly to `main` rather than `phase3/pr-01-specification-and-docs`.

**Goal.** Land the written design before code: spec, ADR-005 (Proposed), Phase 3 doc updates, [PHASE3_PLAN.md](PHASE3_PLAN.md), and this plan. (§1, §33, §35 steps 1–2)

**Depends on.** Nothing.

**Scope.** Documentation only. The working tree already contains these files; this PR commits them.

- New: `cursor/phase3_specs.txt`, `decisions/ADR-005-document-processing-and-page-identity.md`, `docs/PHASE3_PLAN.md`, `docs/PHASE3_PR_PLAN.md`.
- Updated: `README.md`, `docs/PROJECT_STATUS.md` (specified, not implemented; baseline 2026-10-08), `docs/ARCHITECTURE.md`, `docs/DOCUMENT_PIPELINE.md`, `docs/PROVENANCE.md`, `docs/DEVELOPMENT.md`, `docs/PHASE0_HANDOFF.md`, `docs/EXTRACTION.md`.

**Out of scope.** Any Python, TypeScript, migration, Compose, or dependency change.

**Acceptance.**
- All relative links resolve.
- No statement claims Phase 3 is implemented.
- `git diff` contains only documentation.

**Size.** S.

---

### PR-02 — Processing domain vocabulary

**Status.** Done. Processing enums, the default profile hash, artifact keys, and `NormalizedBox` landed in `bc9d9f4`. Package dependencies stay empty. ADR-005 remains Proposed.

**Goal.** Add everything Phase 3 needs that is pure and dependency-free to `packages/document-model`. (§4, §6–§8, §10, §12, §21, §22, §30)

**Depends on.** PR-01.

**Scope** (`packages/document-model/src/powerforge_document_model/`):
- Enums (stable strings; order is the future PostgreSQL enum label order):
  - `ProcessingRunStatus`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`
  - `PageArtifactType`: `ANALYSIS_IMAGE`, `THUMBNAIL`, `NATIVE_TEXT`
  - `SourceUnit`: `POINTS`, `PIXELS`
  - `ProcessingErrorCode`: the §21 set (`CORRUPT_PDF`, `PASSWORD_PROTECTED_PDF`, `IMAGE_DECODE_FAILED`, `UNSUPPORTED_SOURCE`, `PAGE_RENDER_FAILED`, `STORAGE_READ_FAILED`, `STORAGE_WRITE_FAILED`, `RESOURCE_LIMIT_EXCEEDED`, `PROCESSING_TIMEOUT`, `UNKNOWN_PROCESSING_ERROR`)
- Processing profile: `processor_version = "1"`, `profile_version = "engineering-default-v1"`, fields `target_dpi=200`, `max_long_edge_px=8000`, `max_total_pixels=50_000_000`, `thumbnail_long_edge_px=800`, analysis format PNG, thumbnail format WebP, orientation-normalization flag. Deterministic serialized representation and `profile_hash`. Changing a material field changes the hash.
- Artifact key builder: `projects/{project_id}/documents/{document_id}/processing/{run_id}/pages/{page:04d}/{filename}` for `analysis.png`, `thumbnail.webp`, `native.txt`. Rejects non-UUIDs and page numbers below 1. No filenames, revisions, or classifications in the key.
- Future page-coordinate helper types only if they stay documentation-adjacent and unused by runtime (normalized box 0–1). Do not persist boxes.
- Update `__init__.py` exports. Package `dependencies` stays `[]`.

**Out of scope.** SQLAlchemy, Celery, FastAPI, boto3, Pillow, PyMuPDF, any service, any migration.

**Tests** (`tests/test_processing_domain.py`, unit, no DB):
- enum values are stable strings
- profile hash is stable for the default profile and changes when DPI, pixel cap, or thumbnail size changes
- hash does not depend on dict key order
- artifact keys have the exact prefix and zero-padded page folder; page 0 rejected; unsupported artifact type rejected
- purity guard: no forbidden imports; `dependencies = []`

**Acceptance.** Package still has zero third-party dependencies; `ruff` clean.

**Size.** S.

---

### PR-03 — Shared processing library extract

**Status.** Done. `ObjectStorage` and the existing SQLAlchemy models landed in `packages/document-processing` (`ebfd2da`). One `Document` mapping. The worker still only heartbeats. ADR-005 remains Proposed.

**Goal.** Move `ObjectStorage` and the SQLAlchemy models both processes will load into `packages/document-processing` (`powerforge_document_processing`). The API keeps working through imports. There is one mapping of `documents`. The worker still only heartbeats. (§23, §30, ADR-005 #13)

**Depends on.** PR-01. Does not depend on PR-02; do not add processing models here.

**Scope.**
- New package `packages/document-processing` with `powerforge_document_processing`. It may depend on SQLAlchemy, boto3, `powerforge-shared`, `powerforge-project`, and `powerforge-document-model`. It must not depend on FastAPI, Celery, Pillow, or PyMuPDF.
- Move the existing `ObjectStorage` port and implementations (`base`, `memory`, `s3`, `disposition`, `factory`) out of `powerforge_api.storage`.
- Move the existing SQLAlchemy `Base` and models (`Project`, `ProjectRevision`, `Document`, `RevisionDocument`) so the worker will later load the same `Document` class. Do not add a second `Document`.
- Point `services/api` at the new imports. Thin re-exports in the old modules are allowed for one PR if they keep Phase 2 tests importing the old path; delete them in this PR if the test update is cheap.
- Install the new package from `services/api/pyproject.toml`, `requirements-dev.txt`, CI, and `services/api/Dockerfile`.
- Root `pyproject.toml`: first-party name and pytest `pythonpath` for the new package.
- Update import-cycle / AST tests that pin storage or model locations.

**Out of scope.** New tables, processing service, renderer, Celery, worker image changes, Compose S3 settings for the worker, enqueue after upload.

**Tests.**
- Existing Phase 0–2 tests pass without behavior changes.
- A small unit test that `powerforge_document_processing` does not import FastAPI, Celery, Pillow, or PyMuPDF.
- Storage contract tests still run against the moved implementations.

**Acceptance.** API image builds and boots; `/ready` still works; no user-visible change; `Document` is imported from one module.

**Size.** L (import churn). If review stalls, keep the move and drop any leftover re-export cleanup into a follow-up commit on the same branch. Do not combine this with PR-04.

---

### PR-04 — Migration `0005` and processing models

**Status.** Done. Migration `0005_document_processing` and the `DocumentPage`, `DocumentProcessingRun`, and `PageArtifact` mappings landed in `69891d6`. The tables are unused by the running app. ADR-005 remains Proposed.

**Goal.** Create the Phase 3 schema and ORM mappings. No processing behavior yet. (§4, §6, §8, §29)

**Depends on.** PR-02 (enums), PR-03 (shared `Base` and `Document`).

**Scope.**
- `database/migrations/0005_document_processing.py` (single reversible migration; never edit 0001–0004):
  - PostgreSQL enums `processing_run_status`, `page_artifact_type`, `source_unit` (created explicitly; ORM uses `create_type=False` + `values_callable`)
  - `document_pages`: columns per §4; `UNIQUE (document_id, page_number)`; FK to `documents.id`; `page_number >= 1`; `rotation_degrees IN (0, 90, 180, 270)`; index on `document_id`
  - `document_processing_runs`: columns per §6, including `attempt_count` (integer, set at insert, default 1); FK to `documents.id`; indexes on `document_id` and `(document_id, processor_version, profile_hash)`
  - partial unique index: one row per `(document_id, processor_version, profile_hash)` WHERE `status IN ('PENDING', 'RUNNING', 'COMPLETED')`
  - `page_artifacts`: columns per §8; `UNIQUE (processing_run_id, document_page_id, artifact_type)`; `UNIQUE (storage_key)`; FKs to pages and runs; indexes on `document_page_id` and `processing_run_id`
  - no `ON DELETE CASCADE`
  - `downgrade()` removes tables and enums
- ORM models in `packages/document-processing` (not in the API package): `DocumentPage`, `DocumentProcessingRun`, `PageArtifact`.
- Enum labels in the migration are hard-coded; tests assert they equal the Python enums.

**Out of scope.** Service logic, renderer, routes, worker.

**Tests.**
- `tests/test_migration_0005.py` (integration, scratch database it creates and drops):
  - upgrade on empty DB reaches `0005`; upgrade from `0004` with existing documents preserves them
  - downgrade to `0004` succeeds and re-upgrade succeeds
- `tests/test_phase3_constraints.py` (integration, raw inserts, rolled back):
  - duplicate `(document_id, page_number)` rejected
  - two `FAILED` runs for the same target insert
  - a second `PENDING`/`RUNNING`/`COMPLETED` run for the same target is rejected
  - `FAILED` plus one `PENDING` is allowed
  - duplicate `(run, page, artifact_type)` rejected
  - duplicate `storage_key` rejected
  - page_number 0 and rotation 45 rejected
  - artifact FK to a page from another document is not required at the database if we do not add that composite FK; if we do, test it

**Acceptance.** `alembic upgrade head` clean on a fresh DB and on a `0004` DB with Phase 2 data. Phase 2 tests still pass. New tables unused by the running app.

**Size.** M.

---

### PR-05 — Page rendering and artifact production

**Goal.** Turn original bytes into logical pages and artifact bytes. PDF, PNG, JPEG, and TIFF share one pipeline. No database writes. (§5, §11–§15, §21, §28)

**Depends on.** PR-02 (profile, error codes, units). Can merge before PR-03/PR-04.

**Scope.**
- Rendering implementation in `packages/document-processing` (or a submodule it owns). Dependencies: PyMuPDF, Pillow. No FastAPI, no Celery, no SQLAlchemy in this layer.
- Input: original bytes, MIME/extension, processing profile, `max_image_pixels` (Phase 2 upload ceiling).
- Output: an ordered list of page descriptions (1-based number, upright `source_width` / `source_height`, `source_unit`, `rotation_degrees`, `native_text_char_count`, analysis PNG bytes, thumbnail bytes, optional native-text string) plus recorded output pixel size and effective DPI.
- PDF: one page per PDF page; render the complete page; extract native text; whitespace-only text is empty (no text artifact later).
- PNG / JPEG: one page. Apply EXIF orientation. Do not sharpen, deskew, threshold, crop, or denoise.
- TIFF: one page per frame.
- Scale a decodable page down when the analysis image would exceed `max_long_edge_px` or `max_total_pixels`. Record effective DPI for a PDF. For an image, effective DPI is source DPI times the scale factor when known, otherwise null.
- Pillow decompression-bomb ceiling is `MAX_IMAGE_PIXELS`, not Pillow's library default. A file Phase 2 accepted must still open. Beyond that ceiling, or a file that cannot be decoded, raise `RESOURCE_LIMIT_EXCEEDED` or `IMAGE_DECODE_FAILED` / `CORRUPT_PDF` / `PASSWORD_PROTECTED_PDF` as specified. Do not expose stack traces.
- Password-protected PDFs fail cleanly. No password-entry workflow.
- Temporary files are bounded and always closed.

**Out of scope.** Persisting runs or artifacts, Celery, HTTP, OCR, pdfplumber, OpenCV.

**Tests** (`tests/test_page_rendering.py`, unit; build fixtures in-test with PyMuPDF/Pillow):
- single-page and multipage PDF; page order; page count
- native text extracted; scanned/image-only PDF has char count 0 and no text payload
- whitespace-only PDF text is empty
- rotated PDF page stores upright displayed width/height and records the applied rotation
- corrupt PDF and password-protected PDF fail with the named codes
- PNG → one page; JPEG → one page; EXIF orientation applied
- single-page TIFF; multipage TIFF → N pages
- malformed image fails with `IMAGE_DECODE_FAILED`
- analysis image and thumbnail produced for every successful page
- oversized decodable PDF/image is scaled down; output dimensions and effective DPI recorded
- decompression-bomb / over-ceiling input fails; a file within the Phase 2 ceiling still opens
- no OCR, Tesseract, or vendor OCR imports in the package

**Acceptance.** Renderer has no SQLAlchemy session and does not write storage. PyMuPDF and Pillow are dependencies of `document-processing` only (API may transitively see them after this PR; the API process must not call the renderer until PR-06).

**Size.** L. If review stalls, do not split PDF from images; they share limits, orientation, and artifact types. Split only a follow-up that adds extra fixture coverage.

---

### PR-06 — Processing service and run lifecycle

**Goal.** Orchestrate one attempt: `ensure`, `retry`, `claim`, persist pages and artifacts, complete or fail. Enqueue is a port. (§3, §6, §16–§21, §27, §30)

**Depends on.** PR-04, PR-05.

**Scope.**
- Processing service in `packages/document-processing`. The Celery task will call this. Request handlers will call this. The service does not import FastAPI or Celery.
- Enqueue port: `enqueue_document_processing(run_id) -> None`. PR-06 ships a recording fake. A failed enqueue after insert leaves the run `PENDING`, leaves the `Document` valid, and is logged. The service does not mark the run `FAILED` because the broker rejected the message.
- `ensure_document_processing(document_id)` per §17:
  - no run → insert `PENDING` with `attempt_count = 1`, enqueue, return it
  - current `PENDING` → return it and enqueue again
  - current `RUNNING` or `COMPLETED` → return it, do not enqueue
  - current `FAILED` (no live run) → return it, do not enqueue
  - concurrency-safe against the partial unique index
- `retry_failed_processing(document_id)` per §18: only when the current run is `FAILED`; insert a new `PENDING` run with `attempt_count = n + 1`; enqueue the new run; leave the failed run's rows, counters, and objects unchanged. Concurrent retries: one new `PENDING` wins; the loser returns that run. Reject retry of `PENDING`, `RUNNING`, `COMPLETED`, or "no run".
- Worker `claim_and_process(run_id)` per §19–§20:
  - atomic `PENDING` → `RUNNING`; `attempt_count` unchanged
  - duplicate claim of a non-`PENDING` run returns without writing
  - fetch original through `ObjectStorage`; never overwrite or delete it
  - reconcile `DocumentPage` rows (same identity across attempts)
  - write artifacts only under this run's prefix; persist `PageArtifact` rows; increment `pages_processed`
  - `COMPLETED` only when every page has `ANALYSIS_IMAGE` and `THUMBNAIL`, and `NATIVE_TEXT` when text is non-empty
  - any page failure → `FAILED` with a §21 code and a concise `error_message`
- Current-run helper used later by the API: live `PENDING`/`RUNNING`/`COMPLETED`, else latest `FAILED`, else none.
- Map the partial unique index through the existing `integrity_guard` to a domain error the service treats as "return the winner".
- Structured logs: run id, document id, status transitions, error code. No storage keys, no file bytes, no stack traces in user-facing messages.

**Out of scope.** Celery task body beyond a future one-liner, HTTP routes, frontend, backfill CLI, OCR.

**Tests** (`tests/test_processing_service.py` and a concurrency/integration sibling):
- `PENDING` → `RUNNING` → `COMPLETED`
- failure → `FAILED`; partial output never `COMPLETED`
- inherited/reused `Document` across three revisions: one page set, one completed run
- retry inserts a new run; failed run and its artifacts stay; new prefix; `attempt_count` + 1; new run starts at `pages_processed` 0
- `attempt_count` does not change on claim
- second claim does not write artifacts
- two simultaneous ensures create one run
- two simultaneous retries leave one new `PENDING`
- ensure of `RUNNING`/`COMPLETED` does not enqueue
- ensure of unclaimed `PENDING` enqueues again
- lost/failed enqueue leaves `Document` valid and run `PENDING`
- storage read failure → `STORAGE_READ_FAILED`; original unchanged
- artifact write failure → `STORAGE_WRITE_FAILED`; original unchanged
- original Phase 2 object bytes unchanged after any failure
- status reads are not this PR; do not add a GET route here

**Acceptance.** Service tests do not start Celery. Processing belongs to `Document`. Phase 2 upload still does not call `ensure`.

**Size.** L.

---

### PR-07 — Worker, queue, enqueue, and backfill

**Goal.** Run the service asynchronously and start processing for new and existing documents. Worker, dedicated queue, post-upload enqueue, and backfill are one operational path. (§16, §17, §24, §28)

**Depends on.** PR-06.

**Scope.**
- Dedicated Celery queue `document_processing`. Only `document-worker` consumes it. Extraction and validation workers stay on the default queue and do not register the processing task.
- Task in `services/document-worker`: load settings, storage, a DB session, call `claim_and_process`. No rendering inline.
- Enqueue implementation used by the API and backfill: `send_task` (or equivalent) to that queue by task name. The API must not import the FastAPI-free worker package if that creates a cycle; a small helper in `packages/document-processing` or `packages/shared` that knows the task name and broker URL is acceptable. The processing library still must not import Celery if the helper can live beside it; if Celery must be imported to publish, keep that import out of `packages/document-model` and out of the renderer.
- After a successful Phase 2 `Document` commit, the upload path calls `ensure`. The HTTP response is unchanged except that a run now exists. Enqueue failure is logged; the upload still succeeds.
- Worker image: install `document-processing`, `document-model`, PyMuPDF, Pillow, the database driver, boto3. Compose: same `DATABASE_URL` and `S3_*` as the API (`S3_ENDPOINT_URL=http://minio:9000`, `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000`). Worker command binds the dedicated queue. Heartbeat remains registered so existing worker tests still have a task.
- Bounded backfill command: finds documents with no compatible run, and documents whose current run is unclaimed `PENDING`; calls `ensure` for each. Does not retry `FAILED`. Does not run on API startup. Supports a limit/batch size. Document the invocation in `docs/DEVELOPMENT.md`.
- Reasonable task time limit; `PROCESSING_TIMEOUT` when it aborts the task.
- `tests/test_workers.py` still passes; add a test that the processing task is not registered on the other two apps.

**Out of scope.** HTTP page routes, frontend, OCR, automatic enqueue of the entire database.

**Tests.**
- upload (API test) creates a `PENDING` run and publishes one task to `document_processing`
- a second upload of a new file creates a new run; reuse/inherit does not create a second run for the same document
- failed enqueue: document row exists, run `PENDING`, original object present
- duplicate delivery: second `claim_and_process` is a no-op
- backfill: no-run document is ensured; unclaimed `PENDING` is re-enqueued; `FAILED` is left alone; `COMPLETED` is left alone; batch limit is honored
- worker Compose env includes S3 settings (assert in a unit/config test or a documented compose snapshot test)
- existing heartbeat tests pass

**Acceptance.** A local worker consuming `document_processing` can complete a fixture PDF end-to-end against in-memory or MinIO storage in an integration test. Other workers ignore that queue.

**Size.** M.

---

### PR-08 — Processing and page APIs

**Goal.** Revision-scoped reads and retry, plus processing summary on the existing list and detail payloads. (§25, §26 list contract, §27)

**Depends on.** PR-06. Does not require PR-07 (tests can drive the service in-process), but a completed run from PR-07 is the realistic path.

**Scope.**
- Extend `RevisionDocumentResponse` (list and detail) with a processing summary for the current run: `status`, `attempt_count`, `pages_processed`, `pages_total`, `error_code`, `error_message`. No run → a documented empty/null summary the UI treats as Not started. Do not include older failed attempts.
- Routes, nested under `/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}`:
  - `GET /processing` — current-run status, progress, attempt, profile/processor fields, failure information
  - `POST /processing/retry` — §18; response is the new run; only when current is `FAILED`
  - `GET /pages` — page metadata and artifact availability only when current run is `COMPLETED`
  - `GET /pages/{page_id}` — same rule
  - `GET /pages/{page_id}/artifacts/{artifact_type}/url` — short-lived signed URL; only when `COMPLETED`; same presign pattern as Phase 2 downloads (`S3_PUBLIC_ENDPOINT_URL`, `Cache-Control: no-store`)
- Access: any `RevisionDocument` association is enough, including `REMOVED` and including a superseded revision or a closed project. Mismatched project / revision / association / page → 404. Cross-project rejected.
- Retry is not a revision mutation. Read-only revision rules do not block it.
- `GET /processing` and list/detail must not call `ensure` and must not enqueue.
- Pages/URLs while `PENDING`, `RUNNING`, or `FAILED` do not return page rows (404 or a dedicated "not ready" code; pick one in D3 and test it). Progress while running comes from the processing payload.

**Out of scope.** Frontend, OCR, annotation, a history of old attempts.

**Tests** (`tests/test_processing_api.py`, `tests/test_pages_api.py`):
- list/detail include the summary; no run; pending; running progress; completed; failed error
- pages and artifact URLs withheld until `COMPLETED`
- signed URL works (integration, existing MinIO fixture); unsigned GET of the object is 403
- `REMOVED` association and superseded revision can read status and, once completed, pages and URLs
- those associations can retry a `FAILED` run
- retry of `PENDING`/`RUNNING`/`COMPLETED` rejected
- cross-project page access 404; page from another document 404
- status poll does not create a run or publish a task
- original download route unchanged

**Acceptance.** OpenAPI at `/docs` lists the new routes. Phase 2 document tests still pass.

**Size.** M.

---

### PR-09 — Processing status and page viewer UI

**Goal.** Show processing on the existing revision documents workspace and open an inspection-only page viewer for a completed run. Status, retry, and the viewer are one surface. (§26)

**Depends on.** PR-08.

**Scope** (`apps/web`):
- Document table gains a Processing column from the list payload. Do not issue one status request per row.
- States: Not started, Pending, Processing (`pages_processed` / `pages_total` when known), Ready, Failed.
- Failed: concise error and Retry when the retry route would accept. Retry uses the existing association, including `REMOVED` and superseded (retry is not hidden by the mutation read-only banner). After retry, the row follows the new run.
- Ready: control that opens the page viewer.
- Viewer: thumbnail grid/list, page selection, analysis image, page number, source dimensions, rendered dimensions, native-text availability. No annotation, bounding-box drawing, OCR review, equipment tagging, or failed-attempt history.
- Pending, Processing, Failed, and Not started do not show partial pages.
- Types and client helpers in `apps/web/src/lib/documents.ts` matching the PR-08 DTOs.

**Out of scope.** New routes, backend changes, Playwright, OCR UI.

**Tests** (vitest, next to the existing revision-documents tests):
- column renders each state from the list payload, including Not started
- no per-row `/processing` fetch to fill the column
- Retry visible on Failed, hidden otherwise; calls the retry route
- viewer entry only when Ready
- viewer shows page metadata and requests the analysis-image URL for the selected page
- read-only banner still hides Phase 2 mutations; Retry remains available

**Acceptance.** `npm run lint`, `npm test`, `npx tsc --noEmit`. Rebuild the web image to pick it up.

**Size.** M. If the viewer alone pushes the PR past L, keep status + retry in this PR and land the viewer as `PR-09b` on top of it. Do not split the column from Retry.

---

### PR-10 — Hardening, verification, and Phase 3 completion

**Goal.** Prove every requirement is met, correct documentation drift, and close the phase. (§31, §32, §34, §36, §37)

**Depends on.** PR-01 … PR-09.

**Scope.**
- Requirements audit: every §31 test group and every §36 bullet gets a named test or a recorded check in the PR description. Fill gaps here.
- Full-stack verification on a clean checkout: `docker compose down -v && docker compose up --build`; migrate from empty and from a `0004` volume with existing documents; backfill those documents; upload a PDF and an image; watch the row reach Ready; open the viewer; download an analysis image from the signed URL; retry a forced failure; confirm one `Document` inherited across two revisions still has one page set.
- Confirm dedicated queue: a processing task is not consumed by extraction-worker or validation-worker (compose logs or a registration test).
- Docs: re-verify Phase 3 statements in `README`, `ARCHITECTURE`, `DOCUMENT_PIPELINE`, `PROVENANCE`, `DEVELOPMENT`, `PHASE0_HANDOFF`, `PHASE3_PLAN`; finalize deviations and debt in `PROJECT_STATUS.md`.
- ADR-005 → Accepted; set date; note amendments.
- `PROJECT_STATUS.md`: Phase 0–3 complete; next phase remains Phase 4 and is not started; this plan's tracker completed.
- Scope-creep review: `git diff` against Phase 2 for OCR, Tesseract, LLM/vision calls, classification jobs, table extraction, evidence rows, equipment, ETAP/SKM/EasyPower.
- Final gate: ruff, pytest, `RUN_INTEGRATION=1` on a throwaway DB, web lint/test/tsc/build.
- Engineering handoff required by spec §37 (A–N) in the PR description. State only commands that were actually run.

**Out of scope.** Phase 4 work.

**Acceptance.** Every bullet in spec §36 is demonstrably true; CI green; ADR accepted; no OCR code in the tree.

**Size.** M (verification and docs).

---

## 5. Traceability: spec to PR

### Spec sections

| Spec § | Topic | PR(s) |
| --- | --- | --- |
| §1 | Inspect repo, baseline, plan | Done 2026-10-08; PR-01 lands the record |
| §2, §3 | Goal; processing belongs to `Document` | PR-04, PR-06, PR-10 |
| §4 | `DocumentPage` identity; upright size | PR-02, PR-04, PR-05 |
| §5 | PDF / image / TIFF page mapping | PR-05 |
| §6 | `DocumentProcessingRun`; one live run; current run | PR-04, PR-06 |
| §7 | Profile versioning and hash | PR-02, PR-05 |
| §8 | `PageArtifact` | PR-04, PR-06 |
| §9, §10 | Evidence vs derived; coordinate convention | PR-01 (docs); no bbox code |
| §11–§13 | Analysis image, limits, thumbnails | PR-05 |
| §14 | Native PDF text, no OCR | PR-05, PR-06, PR-10 |
| §15 | PyMuPDF, Pillow | PR-05 |
| §16 | Async after commit; dedicated queue | PR-07 |
| §17 | `ensure` | PR-06, PR-07 |
| §18 | Retry as a new run | PR-06, PR-08 |
| §19–§21 | Claim, completion, failure codes | PR-05, PR-06 |
| §22–§23 | Storage keys and shared `ObjectStorage` | PR-02, PR-03, PR-06 |
| §24 | Backfill | PR-07 |
| §25 | APIs and list summary | PR-08 |
| §26 | Frontend | PR-09 |
| §27 | Not a revision mutation; REMOVED / superseded | PR-08, PR-09 |
| §28 | Resource and input safety | PR-05, PR-07 |
| §29 | Migration | PR-04 |
| §30 | Module boundaries | PR-02, PR-03, PR-06, PR-07 |
| §31 | Required tests | each PR; audited in PR-10 |
| §32 | Non-goals | every PR's out-of-scope; PR-10 review |
| §33–§34 | Docs and status | PR-01, each PR, PR-10 |
| §35 | Implementation order | this plan |
| §36 | Definition of done | PR-10 |
| §37 | Final handoff | PR-10 |

### Definition-of-done bullets (§36)

| Requirement | PR(s) |
| --- | --- |
| Phase 0–2 functionality still passes | every PR (gate) |
| PDFs/images process asynchronously | PR-05, PR-06, PR-07 |
| PDFs become stable logical pages | PR-04, PR-05, PR-06 |
| PNG/JPEG become one logical page | PR-05 |
| Multipage TIFF becomes multiple logical pages | PR-05 |
| `DocumentPage` belongs to `Document` | PR-04, PR-06 |
| Inherited/reused documents reuse pages and processing | PR-06 |
| Analysis images and thumbnails generated | PR-05, PR-06 |
| Native PDF text extracted where present, omitted when empty | PR-05, PR-06 |
| No OCR | PR-05, PR-10 |
| Version/profile aware | PR-02, PR-06 |
| Concurrency-safe and idempotent | PR-06 |
| Unclaimed `PENDING` re-enqueued by ensure and backfill | PR-06, PR-07 |
| Retry inserts a new run and preserves failed artifacts | PR-06 |
| `attempt_count` fixed at insert | PR-06 |
| One `PENDING`/`RUNNING`/`COMPLETED` run per target | PR-04, PR-06 |
| Decodable oversized page scaled down | PR-05 |
| Undecodable input and bombs fail the run | PR-05, PR-06 |
| Page source dimensions are the upright page | PR-05 |
| Failures never alter the original | PR-06 |
| Pages and artifact URLs withheld until `COMPLETED` | PR-08, PR-09 |
| Document list carries processing status | PR-08, PR-09 |
| `REMOVED` and superseded can read and retry | PR-08, PR-09 |
| API and worker share `ObjectStorage` and the service | PR-03, PR-06, PR-07 |
| Dedicated document-worker queue | PR-07 |
| Failed runs can be retried | PR-06, PR-08, PR-09 |
| Derived artifacts private; signed URLs work | PR-06, PR-08 |
| Existing documents backfilled without re-upload | PR-07 |
| Frontend shows processing, including Not started | PR-09 |
| Page viewer opens only for a completed run | PR-09 |
| Coordinate convention documented | PR-01 |
| Tests, lint, type, build | every PR; PR-10 |
| ADR/docs/status updated; Phase 4 not implemented | PR-01, PR-10 |

### Required test groups (§31)

| Group | PR(s) |
| --- | --- |
| PDF (count, order, text, scanned, rotation, corrupt, password) | PR-05, completion in PR-06 |
| Images (PNG, JPEG, EXIF, TIFF, malformed) | PR-05 |
| Artifacts (analysis, thumbnail, native text rules, hashes, private, signed URL) | PR-05, PR-06, PR-08 |
| Resource control (scale-down, bomb, Phase 2 ceiling, PDF bound) | PR-05 |
| Processing state (transitions, retry-as-new-run, progress, PENDING re-enqueue, list summary) | PR-06, PR-07, PR-08 |
| Idempotency / concurrency (ensure, duplicate delivery, dedicated queue) | PR-06, PR-07 |
| Revision reuse (one document, many associations, one page set, one completed run) | PR-06 |
| Access (cross-project, page ownership, association, REMOVED, superseded) | PR-08 |
| Failure safety (storage read/write, original unchanged) | PR-06 |
| Regression (Phase 1 and 2) | every PR |

---

## 6. Open decisions

Settle these in the PR named; record the outcome in that PR's description and, if lasting, in the spec/ADR.

| ID | Decision | Needed by | Proposed default |
| --- | --- | --- | --- |
| D1 | Where does the Celery publish helper live so the API can enqueue without importing `document_worker`? | PR-07 | A small `enqueue` module next to the processing service that uses Celery `send_task` by name. `packages/document-model` and the renderer stay Celery-free. |
| D2 | Thumbnail format if the slim worker image cannot write WebP without extra system libraries. | PR-05 | Settled: Pillow can write WebP (`PIL.features.check("webp")`). Thumbnails are WebP and the artifact key stays `thumbnail.webp`. |
| D3 | HTTP response when pages or artifact URLs are requested before the current run is `COMPLETED`. | PR-08 | **409** with a dedicated code (`processing_not_complete`) rather than an empty list, so the UI cannot mistake "no pages yet" for "zero-page document". Status remains 200. |
| D4 | Backfill entry point. | PR-07 | Console script `powerforge-backfill-processing` with `--limit`. Not a FastAPI route. Not invoked from lifespan. |
| D5 | Do upload responses include the new processing summary? | PR-08 | Yes, same shape as list/detail, so the UI can show Pending without a second fetch after upload. |
| D6 | Worker concurrency. | PR-07 | Keep Compose `--concurrency=1` for Phase 3. Claim is already atomic; raising concurrency is a later tuning change. |
| D7 | Exact shared-package import name after the extract. | PR-03 | Settled: `powerforge_document_processing` in `packages/document-processing`. |

---

## 7. Intermediate-state compatibility

What a user of the running app sees while Phase 3 is only partly merged:

| After | Behavior |
| --- | --- |
| PR-01 | Docs only. App unchanged. |
| PR-02 | Unused vocabulary. App unchanged. |
| PR-03 | Rebuild the API image. Import paths change; uploads, downloads, and Phase 2 UI still work. Worker image unchanged. |
| PR-04 | Rebuild the API image. Compose API runs `alembic upgrade head` to `0005`. New tables empty. UI unchanged. |
| PR-05 | Rebuild packages that depend on `document-processing` (PyMuPDF, Pillow). Nothing calls the renderer yet. |
| PR-06 | No user-visible change. Upload still does not enqueue. |
| PR-07 | Rebuild API and document-worker images. New uploads create a `PENDING` run and the worker processes them. The UI does not show status until PR-08/PR-09. Inherited documents are processed once. Existing documents stay unprocessed until backfill. Extraction and validation workers must not be pointed at `document_processing`. |
| PR-08 | List/detail JSON gains a processing object. Old web clients ignore unknown fields. Swagger can retry and fetch page URLs. Rebuild the API image. |
| PR-09 | Web UI only: processing column, retry, page viewer. Rebuild the web image. Signed artifact URLs need `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000` under Compose, same as Phase 2 downloads. |
| PR-10 | Docs and audit only. After pulling, `docker compose down -v && docker compose up --build` if you want a clean stack. |

Never merge a PR that requires a later PR to avoid breaking existing flows. After PR-03, PR-04, PR-05, and PR-07, rebuild the affected images.

---

## 8. Risks

| Risk | Mitigation |
| --- | --- |
| Moving SQLAlchemy models breaks import cycles or Alembic `env.py` | PR-03 is extract-only; Phase 2 tests are the gate; do not add processing models in that PR |
| Partial unique index and SQLAlchemy enum labels drift from Python | Hard-coded labels in `0005`; equality tests in PR-04 |
| Retry-as-new-run races two `PENDING` rows | Partial unique index + map the constraint in PR-06 |
| Default Celery queue steals the task | Dedicated queue and consume list in PR-07; registration test on the other workers |
| Worker cannot read MinIO or Postgres | Compose S3 and `DATABASE_URL` in PR-07; integration test that the worker settings include them |
| Pillow bomb guard rejects Phase 2-legal files | Set the ceiling to `MAX_IMAGE_PIXELS` in PR-05; explicit test |
| Huge drawings exhaust worker memory | Profile caps and scale-down in PR-05; concurrency stays 1 |
| UI polls `/processing` once per row | List payload in PR-08; test in PR-09 that the column does not fetch |
| PR-03, PR-05, PR-06 grow past L | Split only along the seams named in those PRs (re-export cleanup; extra fixtures; not PDF vs images, not ensure vs retry) |
| OCR or classification slips in | Out-of-scope lists; PR-10 import/diff review |

---

## 9. Coverage audit and intentional exclusions

**Audit (2026-10-08).** Every spec section (§1–§37), every test group in spec §31, and every §36 bullet was mapped to a PR scope in section 5. Gaps found and closed in this plan: list/detail processing summary (PR-08, D5), HTTP shape when pages are not ready (D3), dedicated-queue theft (PR-07), worker S3 settings (PR-07), backfill not retrying `FAILED` (PR-07), Retry visible on read-only revisions (PR-09), no per-row status fetch (PR-09). Re-audit in PR-10 against named tests.

**Intentionally not covered by any PR** (spec §32 and recorded debt):

- OCR, Tesseract, cloud OCR, LLM calls, vision-model calls
- Automatic classification, table extraction, layout analysis
- Equipment, symbols, SLDs, topology, embeddings, RAG
- Evidence rows, engineering-model entities, reconciliation
- ETAP/SKM/EasyPower, power-system calculations, report generation
- Artifact garbage collection for failed attempts (same class as Phase 2 orphaned originals)
- A UI or API for browsing older failed attempts
- Password-entry for encrypted PDFs
- Targeted high-resolution region rendering
- Browser end-to-end (Playwright) automation: UI is covered by vitest plus the PR-10 walk-through
- Authentication and non-null `uploaded_by`

Native PDF text extraction is in PR-05/PR-06 because it reads an existing text layer. It is not OCR.
