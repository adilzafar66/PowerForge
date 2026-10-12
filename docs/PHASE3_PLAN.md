# Phase 3 implementation plan

Document processing and stable page representation. Specification: [`cursor/phase3_specs.txt`](../cursor/phase3_specs.txt). Decisions: [ADR-005](../decisions/ADR-005-document-processing-and-page-identity.md) (Accepted).

**Status:** Complete (2026-10-10). The document list carries the current processing summary, and the revision documents workspace shows that status, retry, and an inspection-only page viewer. Upload calls `ensure` after the document commit, and `document-worker` consumes the `document_processing` queue. Existing documents wait for `powerforge-backfill-processing`. Phase 4 is complete.

Delivery is a sequence of pull requests: [PHASE3_PR_PLAN.md](PHASE3_PR_PLAN.md). Implement only the current PR from that document.

## What exists today

Phase 2 is the base. `Document`, `RevisionDocument`, and the project models live in `powerforge_document_processing.models`, and storage is `powerforge_document_processing.storage` (`ObjectStorage.put` refuses to overwrite). The API imports that one mapping. Upload commits the document in `DocumentService.upload`, then calls `ensure`. The publish helper is `powerforge_document_processing.enqueue`; the API does not import `document_worker`.

`document-worker` registers the heartbeat and `document_processing.process_run`. Its image installs the shared processing library, and Compose gives it the API's `DATABASE_URL` and `S3_*` values. It listens only on `document_processing`. Extraction and validation workers stay on the default `celery` queue and do not register the processing task ([PHASE0_HANDOFF.md](PHASE0_HANDOFF.md)).

`packages/document-model` has no third-party dependencies. It owns classification, origin, status, file-validation rules, `build_storage_key`, the processing profile, and artifact keys.

The revision document list, detail, and upload responses carry the current processing summary. The workspace shows status, retry, and the page viewer for a completed run. Downloads already succeed for `REMOVED` associations and for superseded revisions. Alembic head is `0005_document_processing`. `render_pages` turns PDF, PNG, JPEG, and TIFF bytes into analysis images and thumbnails. `ProcessingService` calls it while claiming a run. The service can ensure a run, retry a failed run, and claim a pending run. Upload calls `ensure` after commit. Documents already in the database stay unprocessed until `powerforge-backfill-processing`. Pillow is used by the API's `FileInspector`, which sets `Image.MAX_IMAGE_PIXELS = None` in that process and checks dimensions from the header. A truncated JPEG or TIFF can pass upload. Phase 3 is where those files fail or render.

`cursor/phase3_specs.txt` is the implementation spec.

## Baseline (2026-10-08)

Recorded before any Phase 3 code, on the Phase 2 tree plus the untracked spec. Integration tests used a throwaway database `powerforge_phase3_baseline`, migrated from empty to `0004`, then dropped. MinIO was the Compose container already running.

| Check | Result |
| --- | --- |
| `ruff check .` | Passed |
| `pytest` (integration skipped) | 200 passed, 246 skipped |
| `RUN_INTEGRATION=1 pytest` on `powerforge_phase3_baseline` with MinIO up | 446 passed |
| `npm run lint` (`apps/web`) | No warnings or errors |
| `npx tsc --noEmit` (`apps/web`) | No errors |
| `npm test` (`apps/web`) | 172 passed (11 files) |

`npm run build` was not run. Phase 2's completion check included it; run it again when the web UI changes.

## Module plan

No Phase 3 code belongs in the request handlers or in the Celery task body beyond a call into the service.

| Piece | Where | Role |
| --- | --- | --- |
| Enums, failure codes, processing profile, profile hash, artifact key builder | `packages/document-model` | Pure. No SQLAlchemy, Celery, FastAPI, boto3, Pillow, or PyMuPDF |
| `ObjectStorage` and the existing SQLAlchemy models, including `Document` | New shared library `packages/document-processing` (`powerforge_document_processing`) | One mapping of `documents`. The API imports these; it does not keep a second `Document` class. Project and revision models move with `Document` because they share one registry |
| Processing service and PDF/image rendering | Same library | `ensure`, `retry`, `claim`, page reconciliation, artifact writes. PyMuPDF and Pillow are dependencies here |
| Celery task | `services/document-worker` | Task calls the service. Dedicated queue `document_processing`. Only this worker consumes it |
| HTTP routes and enqueue after upload | `services/api` | Depends on the shared library. Does not import rendering into the upload transaction |
| Revision documents workspace | `apps/web` | Processing column from the list payload, retry, page viewer for a completed run |

The worker image installs the shared library, `document-model`, PyMuPDF, Pillow, the database driver, and boto3. Compose gives that service the same `DATABASE_URL` and `S3_*` values as the API, including `S3_ENDPOINT_URL=http://minio:9000` and `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000`.

`ensure` and `retry` take a small enqueue port. `CeleryProcessingEnqueue` lives next to the processing service and publishes with `send_task`. Only `enqueue.py` imports Celery. A failed enqueue leaves the `PENDING` row and the `Document` in place and logs the failure.

## Behavior to implement

Follow the spec. The decisions that are easy to implement wrong are repeated here.

**Pages.** PDF page, whole PNG or JPEG, and TIFF frame map to `DocumentPage` numbers starting at 1. `source_width` and `source_height` are the upright page. `rotation_degrees` is the rotation that was applied.

**Profile.** `processor_version = "1"`, `profile_version = "engineering-default-v1"`. Hash a canonical serialization of target DPI 200, max long edge 8000, max total pixels 50_000_000, thumbnail long edge 800, analysis format PNG, thumbnail format WebP, and orientation normalization. A WebP profile writes WebP. If this Pillow build cannot write WebP, the run fails before the first page. It does not substitute PNG. Scale a decodable page down to the cap and record effective DPI for a PDF. Set Pillow's bomb ceiling to `MAX_IMAGE_PIXELS` (the Phase 2 upload cap, 600_000_000), not Pillow's library default. Undecodable input fails the run. Do not sharpen, deskew, threshold, or crop.

**Runs.** One attempt per row. Partial unique index on `(document_id, processor_version, profile_hash)` where status is `PENDING`, `RUNNING`, or `COMPLETED`. `attempt_count` is 1, 2, 3… at insert. Claim moves `PENDING` to `RUNNING` and does not change `attempt_count`. Duplicate delivery that loses the claim writes nothing.

**ensure.** No run: create attempt 1 and enqueue. Unclaimed `PENDING`: enqueue again, same row. `RUNNING` or `COMPLETED`: return it, do not enqueue. Latest `FAILED` and no live run: return it, do not enqueue. Status reads do not call `ensure`.

**retry.** Only when the current run is `FAILED`. Insert a new `PENDING` run, enqueue it, leave the failed attempt's rows and objects alone. Two concurrent retries produce one new run. Do not retry `PENDING`, `RUNNING`, or `COMPLETED`.

**Completed means complete.** Pages and artifact URLs are returned only for the `COMPLETED` run. The list and detail payloads include the current run's status, attempt, progress, and concise error. No run yet is "Not started" in the UI. The page viewer opens only for Ready. No history of older failures.

**Access.** Any `RevisionDocument` association is enough, including `REMOVED` and including a superseded revision. Retry is allowed there because it is not a revision mutation. A mismatched project, revision, association, or page is a 404.

**Text.** Store `NATIVE_TEXT` only when the extracted string is non-empty after stripping. Otherwise `native_text_char_count = 0` and no text object. No OCR.

**Storage keys.** `projects/{project_id}/documents/{document_id}/processing/{run_id}/pages/{page:04d}/analysis.png`, `thumbnail.webp`, and `native.txt` when text exists. Private. Presign like Phase 2 downloads.

**Backfill.** A bounded command calls `ensure` for documents with no run and for an unclaimed `PENDING` run. It does not retry `FAILED` and it is not invoked from API startup.

**Originals.** No processing path deletes or rewrites the Phase 2 object.

## Order

Follow [PHASE3_PR_PLAN.md](PHASE3_PR_PLAN.md). One-engineer sequence: PR-01 (docs) → PR-02 (domain) → PR-03 (extract library) → PR-04 (migration) → PR-05 (renderer) → PR-06 (service) → PR-07 (worker/enqueue/backfill) → PR-08 (APIs) → PR-09 (UI) → PR-10 (close the phase).

PR-05 can proceed in parallel with PR-03/PR-04 after PR-02. PR-07 and PR-08 can proceed in parallel after PR-06.

## Out of scope

OCR, Tesseract, cloud OCR, LLMs, vision models, automatic classification, table extraction, equipment, symbols, SLDs, topology, embeddings, evidence rows, the engineering model, reconciliation, electrical calculations, and ETAP/SKM/EasyPower. Also out of scope: a failed-attempt browser, artifact garbage collection, password entry for encrypted PDFs, and region re-rendering.

## Definition of done

The spec's section 36. In particular: Phase 0–2 tests still pass, inherited documents share one page set and one completed run, retry creates a new run, pages are hidden until `COMPLETED`, and no OCR code is added.
