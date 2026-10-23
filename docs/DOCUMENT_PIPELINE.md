# Document Pipeline

Document processing is asynchronous. The UI must not wait synchronously for OCR, layout analysis, or extraction.

Phase 0 establishes job infrastructure (Celery + Redis) and storage configuration. Phase 2 adds synchronous upload, validation, immutable storage, and revision-scoped document management (see [Phase 2 scope](#phase-2-scope)). Phase 3 adds asynchronous page rendering and native PDF text (see [Phase 3 scope](#phase-3-scope)). Phase 4 adds AI document classification after a completed processing run (see [Phase 4 scope](#phase-4-scope)). Phase 6 will add Evidence/candidate persistence, structured extraction, and OCR/layout/table support where required. SLD interpretation remains Phase 8. See [ROADMAP.md](ROADMAP.md).

## Pipeline

The complete intended pipeline below includes planned stages; through Phase 5B, document processing/classification are implemented but Evidence/extraction are not. Native text or vision may suffice without OCR/layout. Reconciliation, validation, and review may iterate.

```
UPLOAD
    → FILE VALIDATION
    → DOCUMENT PROCESSING / PAGE GENERATION (3)
    → DOCUMENT CLASSIFICATION (4)
    → NATIVE TEXT / VISION / OCR / LAYOUT / TABLE INPUTS (6)
    → EVIDENCE + EXTRACTION RUN (6)
    → EXTRACTION CANDIDATES + SCHEMA/REGISTRY VALIDATION (6)
    → ENTITY RESOLUTION (7) / SLD TOPOLOGY CANDIDATES (8)
    → RECONCILIATION / CONFLICT MANAGEMENT (9)
    → DETERMINISTIC VALIDATION (10)
    → ENGINEER REVIEW
```

Every stage records:

- Status
- Job ID
- Timestamps
- Error information
- Retry capability

Jobs must support retries, failure state, error logging, cancellation where practical, and idempotency.

Phase 3 API:

```
GET  /api/projects/{pid}/revisions/{rid}/documents/{rdid}/processing
POST /api/projects/{pid}/revisions/{rid}/documents/{rdid}/processing/retry
GET  /api/projects/{pid}/revisions/{rid}/documents/{rdid}/pages
GET  .../pages/{page_id}/artifacts/{artifact_type}/url
```

The list and detail payloads also carry the current run's status, so the documents table does not poll once per row. Pages and artifact URLs are returned only when that run is `COMPLETED`. Upload stays synchronous and does not render pages inside the request. After commit, the API ensures a processing run and enqueues it. A failed enqueue leaves the document valid.

Phase 2 covers only `UPLOAD` and `FILE VALIDATION`, plus manual classification. It is synchronous per file and creates no jobs.

The Phase 3 UI showed Pending, Processing, Ready, and Failed for that run, and the Phase 4 UI showed the classification suggestion on the same table. Phase 4.5 (complete) moves that workspace into a master-detail layout and does not change these payloads. OCR, layout, and extraction progress belong to later stages and are not shown yet.

## Ownership

**Document module** (`packages/document-model`, document APIs):

- File upload
- Immutable `Document` artifacts and file metadata
- Revision-scoped `RevisionDocument` associations (type, number, description, notes, origin, status)
- Document classification (manual in Phase 2; AI-assisted in Phase 4)
- Page management (Phase 3)
- Object storage references

A "new version" of a document is a new `Document`, never an overwrite. Which version a revision uses is expressed by which `Document` its `RevisionDocument` associations point at.

It must not contain engineering model logic or electrical calculations.

**Document processing module** (`services/document-worker`):

- PDF parsing
- Page rendering
- Native text and image artifacts (implemented in Phase 3)
- OCR, layout, and table support where needed (planned Phase 6)

It produces **normalized document artifacts**. Original files are never overwritten.

## Object storage

Originals live in S3-compatible object storage (MinIO in local development). Access is authorized through the API using signed URLs. Storage is never publicly readable.

Application code uses an `ObjectStorage` abstraction (put, get, exists, delete, create download URL) so the provider can change without touching document logic. Keys are `projects/{project_uuid}/documents/{document_uuid}/original{ext}`; see [Phase 2 scope](#phase-2-scope).

## Phase 2 scope

Specification: `cursor/phase2_specs.txt`. Decisions: [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md). Implementation status: [PROJECT_STATUS.md](PROJECT_STATUS.md).

**Upload.** (Implemented in PR-08: `POST /api/projects/{pid}/revisions/{rid}/documents`, plus list and get endpoints.) Each API request uploads exactly one file; the UI uploads many files as independent requests (isolated failures, retries, per-file progress).

```
validate project/revision → stream (enforce size, SHA-256, spool to temp file)
  → validate content → put immutable object → lock project (shared) + revision, re-check mutability
  → insert Document + RevisionDocument(origin=UPLOADED) → commit
```

If the storage upload fails, no database rows are created. If the database step fails after the object was stored, the object is deleted on a best-effort basis and cleanup failures are logged. A crash between those steps can orphan an object; this is accepted debt (no garbage collection in Phase 2).

**Supported files.** PDF, PNG, JPEG (`.jpg`/`.jpeg`), TIFF (`.tif`/`.tiff`). Extension and detected content must agree (a JPEG named `.png` is rejected). PDFs are checked for the `%PDF-` header; images are opened and verified with Pillow and checked against a pixel limit before any decode. The MIME type is derived from content; the browser's value is ignored. Executables, renamed files, empty files, and unsupported formats are rejected. Image validation is structural: Pillow's `verify()` walks PNG chunks, but a JPEG or TIFF whose header is intact and whose body is truncated is still accepted, because pixels are not decoded until Phase 3. Uploads larger than `MAX_UPLOAD_BYTES` (default 250 MB) are rejected while streaming and are never held fully in memory.

**Duplicates.** The same SHA-256 within a project is detected and reported (`duplicate_detected`, `duplicate_document_ids`) but the upload is accepted and creates a new `Document`. SHA-256 is an integrity and warning signal, not a deduplication key.

**Revisions.** New revisions normally inherit the base revision's `INCLUDED` documents as `INHERITED` associations to the same `Document`; no files are copied. Documents can be removed from and restored to a revision, their metadata edited, and an existing project document reused in another revision (implemented in PR-09: `PATCH …/documents/{id}`, `POST …/documents/{id}/remove`, `…/restore` and `POST …/documents/reuse`). Removing never deletes the file or the `Document`. Superseded revisions' packages are read-only.

**Download.** `GET …/revisions/{rid}/documents/{rdid}/download-url` returns `{url, expires_at, filename}`: a short-lived presigned URL (default 15 minutes, `S3_SIGNED_URL_EXPIRES_SECONDS`) that sets the sanitized original filename and the stored content type. `?disposition=attachment|inline` (default `attachment`; anything else is a 422). It works for INCLUDED and REMOVED documents in every revision and project status, takes no locks, and the response is `Cache-Control: no-store`. A wrong revision or project is a 404; a signing failure is a 502 `storage_download_failed`. The URL, filename and storage key are never logged, and the API never proxies file bytes. There is no unscoped document route.

**Classification.** Manual only: the engineer sets the document type on the `RevisionDocument`. No folders, OCR, page generation, thumbnails, or AI are part of this phase.

## Classification

Initial classes:

- `SINGLE_LINE_DIAGRAM`
- `ELECTRICAL_DRAWING`
- `PANEL_SCHEDULE`
- `EQUIPMENT_SCHEDULE`
- `CABLE_SCHEDULE`
- `TRANSFORMER_SHOP_DRAWING`
- `SWITCHGEAR_SHOP_DRAWING`
- `BREAKER_DOCUMENT`
- `MOTOR_DATA`
- `FAULT_DATA`
- `SPECIFICATION`
- `EQUIPMENT_PHOTO`
- `NAMEPLATE_PHOTO`
- `STUDY_DOCUMENT`
- `OTHER` (added in Phase 2)
- `UNKNOWN` (default)
- `MIXED_DOCUMENT` (on the live enum, immediately before `OTHER`)

In Phase 2 the class is a manual choice stored on the `RevisionDocument` (revision-scoped, so the same file can be classified differently in different revisions) and has no confidence value.

Automatic classification is implemented in Phase 4. `document_classification_runs`, `classification_predictions`, and `classification_ai_calls` store the attempts, predictions, and usage. The model returns a numeric score. PowerForge derives `HIGH`, `MEDIUM`, and `LOW` from it. A score below the high threshold routes the document to page classification. It does not write `RevisionDocument.document_type` and it does not mark the document for automatic review. Only an explicit accept changes the confirmed type. An engineer can already choose Mixed Document by hand. The enum lives in the document-model package (`DocumentClassification`) so all phases share one vocabulary.

## Phase 3 scope

Specification: `cursor/phase3_specs.txt`. Decisions: [ADR-005](../decisions/ADR-005-document-processing-and-page-identity.md) (Accepted). Plan: [PHASE3_PLAN.md](PHASE3_PLAN.md). Delivery: [PHASE3_PR_PLAN.md](PHASE3_PR_PLAN.md). Complete (2026-10-10).

Phase 3 starts after upload. It does not run inside the upload request.

```
Document committed
  → ensure a processing run for (document, processor version, profile hash)
  → enqueue on the document-processing queue
  → document-worker claims the run
  → logical pages, analysis image, thumbnail, native text when present
  → COMPLETED only when the full page set and required artifacts exist
```

Processing is a property of the immutable `Document`. Revisions that point at the same file share the pages and the completed result. A run is one attempt. Retry inserts another run and keeps the failed attempt. `ensure` re-enqueues an unclaimed `PENDING` run and does not retry `FAILED`.

Page rules: one PDF page, one PNG or JPEG, or one TIFF frame is one `DocumentPage`, numbered from 1. Stored width and height are the upright page. Analysis images are PNG. Thumbnails are WebP when the stack can write it. Native text is stored only when non-empty. Images and scanned pages succeed with a zero character count and no text artifact. There is no OCR.

A decodable page larger than the profile cap (200 DPI target, 8000 px long edge, 50 million pixels) is scaled down. Input that cannot be decoded fails the run. Derived objects use `projects/{project}/documents/{document}/processing/{run}/pages/{nnnn}/` and stay private. `put` never overwrites. Existing documents are backfilled by a bounded command, not by API startup.

Routes stay revision-scoped. `REMOVED` associations and superseded revisions may read processing and may retry, because this is not a revision edit.

## Phase 4 scope

Specification: `cursor/phase4_specs.txt`. Decisions: [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Accepted). Delivery: [PHASE4_PR_PLAN.md](PHASE4_PR_PLAN.md). Complete (2026-10-12). Handoff: [PHASE4_HANDOFF.md](PHASE4_HANDOFF.md).

Phase 4 starts after a Phase 3 processing run is `COMPLETED`. It does not run inside the upload request, and it does not run on a pending, running, or failed processing run.

```
Completed Phase 3 run (current processor version and profile)
  → bounded filename, native text, and sampled thumbnails
  → document classification
  → page classification only when mixed, unknown, or below the high threshold
  → suggestion visible
  → engineer accepts, or keeps / chooses the confirmed type
```

The classification target is the current completed processing run for the active profile. Pages are `1` through that run's `pages_total`. The suggestion is the latest completed classification. The newest attempt is reported separately, so a failed reclassify does not hide the previous suggestion.

Accept sets `document_type` and `accepted_classification_prediction_id`. A manual type submission clears that id, even when the type value does not change. Creating a revision and reusing a document both copy the id with the other revision metadata.

Existing processed documents are backfilled by `powerforge-backfill-classification --limit N`. The command does not run on API startup and does not retry a failed classification.

## Phase 4.5 scope

Specification: `cursor/phase4.5_specs.txt`. Delivery: [PHASE4_5_PR_PLAN.md](PHASE4_5_PR_PLAN.md). Complete (2026-10-12). The revision workspace is the master-detail layout.

Phase 4.5 changes where the revision workspace shows document, processing, and classification state. It does not change upload, processing, classification, storage, or the list payload. Derived presentation state lives in the browser.

## Processing tools

Phase 3:

- PyMuPDF for PDF open, page render, and native text extraction
- Pillow for PNG, JPEG, and TIFF decode, orientation, and thumbnails

Not in Phase 3:

- pdfplumber, used later where tables or text layout warrant it
- OpenCV, used later where image preprocessing warrants it
- OCR behind `OCRProvider` (see [EXTRACTION.md](EXTRACTION.md))

Do not couple later OCR code to a single vendor. Do not add that code in Phase 3.

## Worker split

| Service | Phase introduced | Responsibility |
| --- | --- | --- |
| `document-worker` | 3 | Parse, render, native text, artifacts, on the `document_processing` queue. When classification is enabled it enqueues classification after a run completes. It does not call the provider |
| `extraction-worker` | 4, then 6–8 | Phase 4 classification on the `document_classification` queue. Later: structured extraction jobs |
| `validation-worker` | 10 | Deterministic validation jobs |

`document-worker` consumes `document_processing`. `extraction-worker` consumes `document_classification`. `validation-worker` stays on the default `celery` queue. None of them consume another worker's queue.

## Phase 6 boundary

Full Evidence/ExtractionCandidate persistence begins in Phase 6. Native text, OCR, vision, and table inputs cite stable Document/DocumentPage identity with normalized upright-page regions. Extraction runs retain provider/model/prompt versions, retries, and confidence at candidate/evidence granularity; see [EXTRACTION.md](EXTRACTION.md) and [PROVENANCE.md](PROVENANCE.md). Outputs remain candidates for later reconciliation/review and cannot silently overwrite canonical equipment values or revision-level `system_frequency`/`system_phase_count`.

## Artifacts

Normalized artifacts (page images, and later OCR text, layout JSON, and table extracts) are stored separately from the original file and referenced from document and page records. They are evidence inputs to extraction, not substitutes for the engineering model, and they are not themselves the evidence. Evidence points at the `Document` and the stable `DocumentPage`.

Phase 3 artifacts are the analysis image, the thumbnail, and native PDF text. They attach to `Document` through `DocumentPage` and a `DocumentProcessingRun`, not to a `RevisionDocument`, so a document inherited by many revisions is processed once. Phase 2 stores originals only.
