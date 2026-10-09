# Document Pipeline

Document processing is asynchronous. The UI must not wait synchronously for OCR, layout analysis, or extraction.

Phase 0 establishes job infrastructure (Celery + Redis) and storage configuration. Phase 2 adds synchronous upload, validation, immutable storage, and revision-scoped document management (see [Phase 2 scope](#phase-2-scope)). Phase 3, specified and not implemented, adds asynchronous page rendering and native PDF text (see [Phase 3 scope](#phase-3-scope)). OCR, AI classification, and extraction remain later phases.

## Pipeline

```
UPLOAD
    → FILE VALIDATION
    → DOCUMENT CLASSIFICATION
    → PDF PROCESSING
    → PAGE GENERATION
    → OCR
    → LAYOUT ANALYSIS
    → AI EXTRACTION
    → CANDIDATE DATA
    → VALIDATION
    → RECONCILIATION
    → ENGINEER REVIEW
```

Every stage records:

- Status
- Job ID
- Timestamps
- Error information
- Retry capability

Jobs must support retries, failure state, error logging, cancellation where practical, and idempotency.

Typical API shape for Phase 3 (specified, not implemented):

```
GET  /api/projects/{pid}/revisions/{rid}/documents/{rdid}/processing
POST /api/projects/{pid}/revisions/{rid}/documents/{rdid}/processing/retry
GET  /api/projects/{pid}/revisions/{rid}/documents/{rdid}/pages
GET  .../pages/{page_id}/artifacts/{artifact_type}/url
```

The list and detail payloads also carry the current run's status, so the documents table does not poll once per row. Pages and artifact URLs are returned only when that run is `COMPLETED`. Upload stays synchronous and does not render pages inside the request. After commit, the API ensures a processing run and enqueues it. A failed enqueue leaves the document valid.

Phase 2 covers only `UPLOAD` and `FILE VALIDATION`, plus manual classification. It is synchronous per file and creates no jobs.

The Phase 3 UI shows Pending, Processing, Ready, and Failed for that run. OCR, layout, classification, and extraction progress belong to later stages and are not shown yet.

## Ownership

**Document module** (`packages/document-model`, document APIs):

- File upload
- Immutable `Document` artifacts and file metadata
- Revision-scoped `RevisionDocument` associations (type, number, description, notes, origin, status)
- Document classification (manual in Phase 2; AI-assisted in Phase 4)
- Page management (Phase 3, specified, not implemented)
- Object storage references

A "new version" of a document is a new `Document`, never an overwrite. Which version a revision uses is expressed by which `Document` its `RevisionDocument` associations point at.

It must not contain engineering model logic or electrical calculations.

**Document processing module** (`services/document-worker`):

- PDF parsing
- Page rendering
- OCR
- Text, image, layout, and table extraction

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

In Phase 2 the class is a manual choice stored on the `RevisionDocument` (revision-scoped, so the same file can be classified differently in different revisions) and has no confidence value.

Automatic classification is Phase 4. It will include confidence; below a configurable threshold the document is marked for review. The enum lives in the document-model package (`DocumentClassification`) so all phases share one vocabulary.

## Phase 3 scope

Specification: `cursor/phase3_specs.txt`. Decisions: [ADR-005](../decisions/ADR-005-document-processing-and-page-identity.md) (Proposed). Plan: [PHASE3_PLAN.md](PHASE3_PLAN.md). Delivery: [PHASE3_PR_PLAN.md](PHASE3_PR_PLAN.md). Not implemented.

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

## Processing tools

Phase 3 (specified, not implemented):

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
| `document-worker` | 3 | Parse, render, native text, artifacts. Heartbeat only until Phase 3 is implemented. OCR and classification jobs are later |
| `extraction-worker` | 6–8 | Structured extraction jobs |
| `validation-worker` | 10 | Deterministic validation jobs |

Phase 0 workers start, connect to Redis, and expose a heartbeat task. They do not process documents. Processing tasks will use a dedicated queue so the other workers cannot take them. Today all three workers share the default queue.

## Artifacts

Normalized artifacts (page images, and later OCR text, layout JSON, and table extracts) are stored separately from the original file and referenced from document and page records. They are evidence inputs to extraction, not substitutes for the engineering model, and they are not themselves the evidence. Evidence points at the `Document` and the stable `DocumentPage`.

Phase 3 artifacts are the analysis image, the thumbnail, and native PDF text. They attach to `Document` through `DocumentPage` and a `DocumentProcessingRun`, not to a `RevisionDocument`, so a document inherited by many revisions is processed once. Phase 2 stores originals only.
