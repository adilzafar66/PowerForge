# Document Pipeline

Document processing is asynchronous. The UI must not wait synchronously for OCR, layout analysis, or extraction.

Phase 0 establishes job infrastructure (Celery + Redis) and storage configuration. Phase 2 adds synchronous upload, validation, immutable storage, and revision-scoped document management (see [Phase 2 scope](#phase-2-scope)). Parsing, page rendering, OCR, AI classification, and extraction are later phases.

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

Typical API shape (Phase 3+, not part of Phase 2):

```
POST /documents/{id}/process  →  { "job_id": "..." }
```

Phase 2 covers only the first stage (`UPLOAD` and `FILE VALIDATION`) plus manual classification. It is synchronous per file and creates no jobs.

The frontend then displays staged progress (OCR, layout, classification, extraction) from job status, not from a long HTTP request.

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
- OCR
- Text, image, layout, and table extraction

It produces **normalized document artifacts**. Original files are never overwritten.

## Object storage

Originals live in S3-compatible object storage (MinIO in local development). Access is authorized through the API using signed URLs. Storage is never publicly readable.

Application code uses an `ObjectStorage` abstraction (put, get, exists, delete, create download URL) so the provider can change without touching document logic. Keys are `projects/{project_uuid}/documents/{document_uuid}/original{ext}`; see [Phase 2 scope](#phase-2-scope).

## Phase 2 scope

Specification: `cursor/phase2_specs.txt`. Decisions: [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md). Implementation status: [PROJECT_STATUS.md](PROJECT_STATUS.md).

**Upload.** Each API request uploads exactly one file; the UI uploads many files as independent requests (isolated failures, retries, per-file progress).

```
validate project/revision → stream (enforce size, SHA-256, spool to temp file)
  → validate content → put immutable object → lock project (shared) + revision, re-check mutability
  → insert Document + RevisionDocument(origin=UPLOADED) → commit
```

If the storage upload fails, no database rows are created. If the database step fails after the object was stored, the object is deleted on a best-effort basis and cleanup failures are logged. A crash between those steps can orphan an object; this is accepted debt (no garbage collection in Phase 2).

**Supported files.** PDF, PNG, JPEG (`.jpg`/`.jpeg`), TIFF (`.tif`/`.tiff`). Extension and detected content must agree (a JPEG named `.png` is rejected). PDFs are checked for the `%PDF-` header; images are opened and verified with Pillow and checked against a pixel limit before any decode. The MIME type is derived from content; the browser's value is ignored. Executables, renamed files, empty files, and unsupported formats are rejected. Image validation is structural: Pillow's `verify()` walks PNG chunks, but a JPEG or TIFF whose header is intact and whose body is truncated is still accepted, because pixels are not decoded until Phase 3. Uploads larger than `MAX_UPLOAD_BYTES` (default 250 MB) are rejected while streaming and are never held fully in memory.

**Duplicates.** The same SHA-256 within a project is detected and reported (`duplicate_detected`, `duplicate_document_ids`) but the upload is accepted and creates a new `Document`. SHA-256 is an integrity and warning signal, not a deduplication key.

**Revisions.** New revisions normally inherit the base revision's `INCLUDED` documents as `INHERITED` associations to the same `Document`; no files are copied. Documents can be removed from and restored to a revision, and an existing project document can be reused in another revision. Superseded revisions' packages are read-only.

**Download.** `GET …/revisions/{rid}/documents/{rdid}/download-url` returns a short-lived presigned URL (default 15 minutes) with the original filename and stored content type. There is no unscoped document route.

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

## Processing tools (Phase 3+)

- PyMuPDF for PDF parse and page render
- pdfplumber where tables/text layout warrant it
- OpenCV where image preprocessing warrants it
- OCR behind `OCRProvider` (see [EXTRACTION.md](EXTRACTION.md))

Do not couple processing code to a single OCR vendor.

## Worker split

| Service | Phase introduced | Responsibility |
| --- | --- | --- |
| `document-worker` | 3–4 | Parse, render, OCR, artifacts, classification jobs |
| `extraction-worker` | 6–8 | Structured extraction jobs |
| `validation-worker` | 10 | Deterministic validation jobs |

Phase 0 workers start, connect to Redis, and expose a heartbeat task. They do not process documents.

## Artifacts

Normalized artifacts (page images, OCR text, layout JSON, table extracts) are stored separately from the original file and referenced from document/page records. They are evidence inputs to extraction, not substitutes for the engineering model.

Artifacts attach to the immutable `Document`, not to a `RevisionDocument`, so a document inherited by many revisions is processed once. Phase 3 introduces them; Phase 2 stores originals only.
