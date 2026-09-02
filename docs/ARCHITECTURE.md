# Architecture

PowerForge is an engineering data extraction platform. Electrical engineers upload project documents; the system extracts structured electrical information, reconciles it across sources, and produces a centralized, traceable engineering model. The engineer remains the final authority. AI proposes information; it does not silently make engineering decisions.

This document is the entry point for implementers. Read it before changing code. Domain details live in the sibling documents listed below.

## Product objective

The application ingests electrical engineering documents and images (single-line diagrams, schedules, shop drawings, datasheets, nameplates, photographs, specifications, studies, and related sources) and produces a centralized electrical engineering model:

- Equipment, attributes, connections, and topology
- Sources, transformers, buses, panels, MCCs, switchgear, cables, motors, loads, generators, and protection devices
- Traceability from every extracted value to its source document and, where possible, page and bounding box

The system must surface low-confidence extraction, missing information, conflicts, duplicate entities, potential matches, unverified topology, and inferred information.

## Core philosophy

```
SOURCE DOCUMENTS
    → DOCUMENT PROCESSING
    → AI EXTRACTION
    → CANDIDATE DATA
    → ENTITY RESOLUTION
    → VALIDATION
    → RECONCILIATION
    → ENGINEERING MODEL
    → ENGINEER REVIEW
    → VERIFIED ENGINEERING MODEL
```

Rules that do not change:

1. The verified engineering model is the source of truth after human verification.
2. Original documents remain immutable evidence.
3. The AI extraction layer is never the source of truth.
4. The engineering model must not depend on a particular AI provider.
5. The engineering model must not depend on ETAP, SKM, EasyPower, or any other electrical analysis package.

Electrical analysis, short-circuit, coordination, arc-flash, and report generation consume the model later. They are out of scope for this application phase. See [ADR-001](../decisions/ADR-001-engineering-model-independence.md).

## High-level architecture

```
                         WEB APPLICATION
                               |
                               v
                              API
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
          PostgreSQL      Object Storage    Background Jobs
              |
              v
      CENTRAL ENGINEERING MODEL
              ^
              |
       VALIDATION / RECONCILIATION
              ^
              |
         AI EXTRACTION
              ^
              |
      DOCUMENT PROCESSING
              ^
              |
      PDFs / IMAGES / FILES
```

The web application never talks to the database, object storage, or workers directly. All application behavior goes through the API (or jobs the API enqueues).

## Module boundaries

These boundaries are mandatory. Do not place logic in an unrelated module.

| Module | Owns | Must not contain |
| --- | --- | --- |
| Project | Projects, metadata, revisions, lifecycle | AI, OCR, calculations, document parsing |
| Document | Upload, metadata, classification, versions, pages, storage refs | Engineering model, electrical calculations |
| Document processing | PDF parse, page render, OCR, text/image/layout/table extraction | Mutating the verified model |
| AI extraction | Equipment, attributes, SLD, topology candidates, relationships | Direct writes to the verified model |
| Entity resolution | Duplicate detection, match probability, merge candidates | Silent merges of low-confidence matches |
| Engineering model | Equipment, attributes, connections, topology, revisions, state | AI provider SDKs |
| Electrical topology | Graph of nodes and connections | Independent visualization database |
| Provenance | Documents, pages, bboxes, evidence, confidence, source hierarchy | Engineering calculations |
| Validation | Deterministic rules and sanity checks | LLM-based “validation” as truth |
| Reconciliation | Cross-source conflicts and source priority | Silent conflict resolution |
| Engineer review | Approve, reject, edit, merge, split, verify, audit | Auto-promoting AI values to verified |
| Visualization | Model views, interactive topology, evidence, completeness | A separate source of truth |

Package and service mapping:

- `apps/web` — visualization and all engineer-facing UI
- `services/api` — HTTP API, auth boundary, job enqueue
- `services/document-worker` — document processing jobs
- `services/extraction-worker` — AI extraction jobs
- `services/validation-worker` — deterministic validation jobs
- `packages/engineering-model` — canonical model types and contracts
- `packages/document-model` — document and page contracts
- `packages/extraction` — candidate extraction contracts
- `packages/topology` — graph contracts
- `packages/validation` — deterministic rule contracts
- `packages/provenance` — evidence contracts
- `packages/ai` — LLM / vision / OCR provider interfaces
- `packages/shared` — config, logging, identifiers shared by services

Workers and the API may depend on domain packages. Domain packages must not depend on FastAPI, Celery, Next.js, or a specific AI vendor SDK.

## Technology stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Frontend | Next.js, TypeScript, React, Tailwind CSS, shadcn/ui | React Flow is reserved for topology visualization (Phase 12) |
| API | Python, FastAPI, Pydantic | REST; Pydantic schemas are API contracts, not ORM models |
| Persistence | PostgreSQL, SQLAlchemy 2, Alembic | Hybrid relational + JSONB; queryable, not a document dump |
| Object storage | S3-compatible (MinIO locally) | Signed URLs; originals never overwritten |
| Jobs | Redis + Celery | Document processing and extraction are never synchronous HTTP |
| Document processing | PyMuPDF, pdfplumber, OpenCV, OCR abstraction | Introduced in Phase 3; not implemented in Phase 0 |
| AI | `LLMProvider`, `VisionProvider`, `OCRProvider` | Swappable; prompt-versioned; never trusted raw |

See [ADR-002](../decisions/ADR-002-phase-0-technology-stack.md) for why these Phase 0 choices were made.

## Repository structure

```
/apps/web
/services/api
/services/document-worker
/services/extraction-worker
/services/validation-worker
/packages/engineering-model
/packages/document-model
/packages/extraction
/packages/topology
/packages/validation
/packages/provenance
/packages/ai
/packages/shared
/database/migrations
/database/seeds
/docs
/decisions
/tests
```

The backend is not a monolith. Each worker is a separate process with a narrow job. Shared domain logic lives in packages, not copied into services.

## Data and safety

- Common `Equipment` concept with `equipment_type` and type-specific attributes. Do not require a disconnected schema per type, and do not store the entire model as one JSON blob.
- Attributes carry value, unit, confidence, source, page, bounding box, extraction method, and verification status.
- Missing data uses explicit states (`UNKNOWN`, `MISSING`, `NOT_APPLICABLE`, `NOT_EXTRACTED`, `LOW_CONFIDENCE`, `CONFLICTING`, `INFERRED`, `VERIFIED`), not null alone.
- Conflicts are represented and queued for the engineer. They are never silently resolved.
- Verification states are explicit: `AI_EXTRACTED` → `SYSTEM_VALIDATED` → `ENGINEER_REVIEWED` → `ENGINEER_VERIFIED`. Never silently promote AI-extracted values.

## Asynchronous processing

`POST` endpoints that start processing return a `job_id`. The UI polls or subscribes to job status. Every stage has status, job ID, timestamps, error information, and retry capability.

## Security baseline

Uploaded documents are confidential engineering information. The platform requires authentication, authorization, project-level access control, authorized object-storage access (signed URLs), encryption in transit, encryption at rest where supported, and audit logging. Object storage is never exposed without authorization.

Auth is not implemented in Phase 0. The API is bound to localhost in local development. Project-level access control begins when projects exist (Phase 1+).

## Phase 0 scope

Phase 0 establishes architecture and a runnable skeleton:

- Repository layout and coding standards
- Architecture and domain documentation
- Database connection, Alembic, and the initial schema foundation
- FastAPI health/readiness API
- Minimal Next.js UI that reports stack status
- Celery worker processes that start and heartbeat
- Local S3-compatible storage, PostgreSQL, and Redis via Docker Compose
- Basic automated tests and CI

Phase 0 does **not** implement projects, uploads, OCR, AI extraction, SLD recognition, entity resolution, review workflows, visualization of topology, ETAP/SKM/EasyPower, electrical calculations, or report generation.

## Related documents

- [ENGINEERING_MODEL.md](ENGINEERING_MODEL.md)
- [DOCUMENT_PIPELINE.md](DOCUMENT_PIPELINE.md)
- [EXTRACTION.md](EXTRACTION.md)
- [TOPOLOGY.md](TOPOLOGY.md)
- [VALIDATION.md](VALIDATION.md)
- [PROVENANCE.md](PROVENANCE.md)
- [REVIEW_WORKFLOW.md](REVIEW_WORKFLOW.md)
- [CODING_STANDARDS.md](CODING_STANDARDS.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)
