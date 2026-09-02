# Document Pipeline

Document processing is asynchronous. The UI must not wait synchronously for OCR, layout analysis, or extraction.

Phase 0 establishes job infrastructure (Celery + Redis) and storage configuration. Parsing, OCR, classification, and extraction are later phases.

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

Typical API shape (Phase 2+):

```
POST /documents/{id}/process  →  { "job_id": "..." }
```

The frontend then displays staged progress (OCR, layout, classification, extraction) from job status, not from a long HTTP request.

## Ownership

**Document module** (`packages/document-model`, document APIs):

- File upload
- File metadata
- Document classification
- Document versions
- Page management
- Object storage references

It must not contain engineering model logic or electrical calculations.

**Document processing module** (`services/document-worker`):

- PDF parsing
- Page rendering
- OCR
- Text, image, layout, and table extraction

It produces **normalized document artifacts**. Original files are never overwritten.

## Object storage

Originals live in S3-compatible object storage (MinIO in local development). Access is authorized through the API using signed URLs. Storage is never publicly readable.

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
- `UNKNOWN`

Classification includes confidence. Below a configurable threshold, the document is marked for review.

Classification is Phase 4. The enum exists in the document-model package so later phases share one vocabulary.

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
