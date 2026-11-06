# Architecture

PowerForge is an engineering data extraction platform. Electrical engineers upload project documents; the system extracts structured electrical information, reconciles it across sources, and produces a centralized, traceable engineering model. The engineer remains the final authority. AI proposes information; it does not silently make engineering decisions.

This document is the entry point for implementers. Read it before changing code. Domain details live in the sibling documents listed below. [ROADMAP.md](ROADMAP.md) governs high-level future scope; [PROJECT_STATUS.md](PROJECT_STATUS.md) governs implementation status.

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
    → RECONCILIATION / CONFLICT MANAGEMENT
    → DETERMINISTIC VALIDATION
    → ENGINEERING MODEL
    → ENGINEER REVIEW
    → VERIFIED ENGINEERING MODEL
```

This describes the intended product flow, not completed functionality. Reconciliation (9), validation (10), and engineer review (11) may iterate. Full Evidence/candidate persistence and extraction begin in Phase 6.

Rules that do not change:

1. The verified engineering model is the source of truth after human verification.
2. Original documents remain immutable evidence.
3. The AI extraction layer is never the source of truth.
4. The engineering model must not depend on a particular AI provider.
5. The engineering model must not depend on ETAP, SKM, EasyPower, or any other electrical analysis package.

Study-tool integration, including export/adapters, study execution/automation, results ingestion, and engineering reports, is planned for Phase 13. Short-circuit, coordination, and arc-flash studies consume the verified canonical model downstream. These capabilities are not implemented through Phase 5G. See [ADR-001](../decisions/ADR-001-engineering-model-independence.md).

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
| Document | Upload, immutable `Document` artifacts, revision-scoped `RevisionDocument` associations and metadata, classification, storage refs; pages (Phase 3) | Engineering model, electrical calculations |
| Document processing | PDF parse, page render, native text, and derived artifacts in Phase 3; OCR and layout/table extraction later | Mutating the verified model; OCR in Phase 3 |
| AI extraction | Equipment, attributes, SLD, topology candidates, relationships | Direct writes to the verified model |
| Entity resolution | Duplicate detection, match probability, merge candidates | Silent merges of low-confidence matches |
| Engineering model | Equipment, attributes, connections, topology, model snapshot on a project revision, state | AI provider SDKs; project/revision tables |
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
- `packages/project` — project/revision enums and domain schemas
- `packages/engineering-model` — pure registry-v1 definitions, units, value validation, and requirement evaluation (Phase 5A); no persistence or provider dependencies
- `packages/document-model` — document vocabulary: classification, origin and status enums, pure file-validation rules, storage-key builder, processing enums, the profile, and artifact key construction (no SQLAlchemy, FastAPI, S3 SDK, Pillow, or PyMuPDF)
- `packages/persistence` — neutral SQLAlchemy Base, project/revision mappings, and Phase 5B equipment lineage/equipment/typed-attribute mappings; no document-processing or API dependency.
- `packages/document-processing` — shared `ObjectStorage`, document-specific SQLAlchemy models (`Document`, `RevisionDocument`, `DocumentPage`, `DocumentProcessingRun`, `PageArtifact`), page rendering, and `ProcessingService`. Base/project/revision imports are compatibility re-exports from persistence. The API and `document-worker` both import it. The worker does not import FastAPI
- `packages/extraction` — pure extraction contracts plus separate shared-Base ORM and internal persistence modules; Phase 6A read services live in the API
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
| Object storage | S3-compatible (MinIO locally), accessed through an `ObjectStorage` abstraction (boto3 implementation) | Presigned URLs; originals never overwritten; stable machine-oriented keys (Phase 2) |
| Jobs | Redis + Celery | Document processing and extraction are never synchronous HTTP |
| Document processing | PyMuPDF and Pillow | Phase 3, in `powerforge_document_processing`. pdfplumber, OpenCV, and OCR stay later |
| AI | `LLMProvider`, `VisionProvider`, `OCRProvider` | Swappable; prompt-versioned; never trusted raw |

See [ADR-002](../decisions/ADR-002-phase-0-technology-stack.md) for why these Phase 0 choices were made.

## Repository structure

```
/apps/web
/services/api
/services/document-worker
/services/extraction-worker
/services/validation-worker
/packages/project
/packages/engineering-model
/packages/document-model
/packages/persistence           (neutral Base, project/revision and engineering ORM mappings)
/packages/document-processing   (storage, document ORM mappings, processing service)
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
- Phase 5B attributes carry typed values, canonical units, information/verification states, origin, and nullable confidence. Full Evidence/ExtractionCandidate persistence starts in Phase 6; document/page/bounding-box/extraction provenance belongs there, linked at attribute granularity rather than embedded in canonical attribute rows.
- Information states are `PRESENT`, `MISSING`, `NOT_APPLICABLE`, `NOT_POPULATED`, and `CONFLICTING`. Confidence and origin (including INFERRED) are separate concepts.
- Conflicts are represented and queued for the engineer. They are never silently resolved.
- Verification vocabulary is `UNVERIFIED`, `AI_EXTRACTED`, `SYSTEM_VALIDATED`, `ENGINEER_REVIEWED`, `ENGINEER_VERIFIED`. These are distinct states, not an automatic promotion pipeline. AI_EXTRACTED must never silently become ENGINEER_VERIFIED.

Phase 5C revision-level `system_frequency` (canonical Hz as Decimal/NUMERIC) and optional common `system_phase_count` (1 or 3) belong to the snapshot rooted at ProjectRevision, with no separate EngineeringModel entity. Revision creation copies ACTIVE equipment and, from Phase 5D, nodes and connections from its selected base in the same transaction as document inheritance, metadata resolution, and activation. Snapshot rows receive new IDs, retain equipment lineage, and point directly to their immediate base rows. Project then revision locking serializes the clone with model writes.

Phase 5D topology mappings live in `powerforge_persistence.topology`; `packages/topology` remains pure domain vocabulary. ModelNode is either an equipment terminal or an electrical junction, and ModelConnection joins two same-revision nodes. Composite foreign keys enforce ownership. Removing equipment removes its terminals and incident connections; restoring equipment restores terminals only. Internal topology services share the engineering/document write guard. Transaction-participating lifecycle and clone helpers never commit independently.

Phase 5E's dedicated `routers/model.py` and `schemas/model.py` expose revision-scoped equipment, attributes, nodes, and connections through those services. Request allowlists forbid client provenance/audit injection; explicit response models retain canonical provenance and serialize Decimal values losslessly. Equipment queries add literal substring search without loading attributes. The API boundary translates known engineering input failures to 422, scoped missing objects to 404, and lifecycle/read-only conflicts to 409, while leaving pure domain packages HTTP-independent. No migration, frontend, worker, or extraction work is involved. See [PHASE5E_HANDOFF.md](PHASE5E_HANDOFF.md).

Phase 5F adds `RevisionWorkspace` around the existing Documents workspace and a lazily mounted Engineering Model workspace. URL query state selects the workspace and equipment detail; local component state holds filters and form drafts. The model workspace caches the registry response, shares writability/refresh handling through a local context, and separates equipment/general/attribute/terminal views from topology lists and connection forms. `apps/web/src/lib/engineering-model.ts` provides typed requests through the existing API client. No global state/data-fetching framework or new runtime dependency is introduced.

Forms consume registry metadata, submit only allowed manual fields, preserve decimal strings, and adopt canonical service responses. Shared lifecycle warnings and stale-state handling protect accepted removal/restoration and read-only semantics. The existing revision banner stays above both workspaces. The default Documents workspace retains its prior behavior. No backend, database, graph visualization, extraction, or verification workflow changes are part of 5F. See [PHASE5F_HANDOFF.md](PHASE5F_HANDOFF.md).

Revision defaults are not copied into equipment attribute rows. For applicable fields, an explicit PRESENT equipment value takes precedence, then the revision value, then unspecified; disagreement is returned as a deterministic mismatch without overwriting either value or persisting a Phase 10 validation finding. Mixed phase systems leave the common count absent. These assumptions are not document evidence.

Protection functions/settings and operating/study configurations are separate post-core-Phase-5 canonical-domain design gates, not arbitrary equipment attributes. Dedicated decisions must precede implementation and provide targets for extraction and study integration. Canonical design/nameplate values remain distinct from study-adjusted settings; see [ROADMAP.md](ROADMAP.md).

Phase 5G freezes the completed canonical model without a migration or new aggregate. Canonical attribute INTEGER values remain Python integers/BIGINT internally and serialize consistently as JSON strings (or null); frontend types preserve those strings through reads and edits. Decimal response behavior is unchanged. The registry matches its authoritative snapshot and is frozen; future semantic changes need deliberate versioning and a migration strategy. Full live regression, fresh migration/stack checks and the bounded performance review are recorded in [PHASE5G_HANDOFF.md](PHASE5G_HANDOFF.md). Phase 6A introduces separate Evidence/Candidate persistence and read APIs; Phase 6B adds execution orchestration and provider infrastructure. See [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md).

## Asynchronous processing

`POST` endpoints that start processing return a `job_id`. The UI polls or subscribes to job status. Every stage has status, job ID, timestamps, error information, and retry capability.

## Security baseline

Uploaded documents are confidential engineering information. The platform requires authentication, authorization, project-level access control, authorized object-storage access (signed URLs), encryption in transit, encryption at rest where supported, and audit logging. Object storage is never exposed without authorization.

Auth is not implemented through Phase 5G. Authentication, user identity, project authorization, and actor-backed audit records are a hard prerequisite/subphase for Phase 11 completion; pull them forward if shared/multi-user deployment requires them earlier. Phase 2 still issues object access only through backend-authorized presigned URLs, so project-level authorization can be added at the API later without changing storage. The API is bound to localhost in local development. Do not add a fake users table or fake auth in Phase 1. `created_by` on projects and revisions is a nullable UUID with no foreign key until a users table exists. Project-level access control arrives with authentication, not merely because project rows exist. See [ADR-003](../decisions/ADR-003-project-revision-model.md).

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

## Phase 1

Phase 1 is project and revision management. Implementation followed `cursor/phase1_specs.txt` and [ADR-003](../decisions/ADR-003-project-revision-model.md). Status: [PROJECT_STATUS.md](PROJECT_STATUS.md).

Delivered:

- One `ProjectRevision` entity. Documents and the engineering model attach to it later. No separate model-revision table.
- `packages/project` (enums/schemas) + SQLAlchemy/services in `services/api`.
- UUIDs in API paths (`gen_random_uuid()`). Human-readable revision `identifier` is unique per project.
- No auto-created revision. New revisions are `DRAFT`. Activate is atomic and is the only path to `ACTIVE`.
- Project statuses `ACTIVE`, `PAUSED`, `CANCELLED`, `ARCHIVED` via `/pause`, `/resume`, `/cancel`, `/archive`, `/unarchive`. PATCH is metadata only.
- `/` is the project list. Stack status is at `/status`.

## Phase 2

Phase 2 is document management and revision inheritance. Specification: `cursor/phase2_specs.txt`. Decision record: [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md). Status: implemented and complete, see [PROJECT_STATUS.md](PROJECT_STATUS.md), which also lists the known debt.

### Two concepts, deliberately separate

```
Project
  ├── ProjectRevision (Rev 0)
  │      └── RevisionDocument ──┐
  │                             ├──► Document ──► immutable object in storage
  └── ProjectRevision (Rev 1)   │
         └── RevisionDocument ──┘   same Document, new association row
```

- **`Document`** is the immutable uploaded artifact: project, original filename, storage key, MIME type, extension, size, SHA-256, upload time. It has no revision and no editable fields.
- **`RevisionDocument`** is the inclusion and interpretation of that artifact in one revision: document type, number, description, notes, origin (`UPLOADED` or `INHERITED`), status (`INCLUDED` or `REMOVED`), and add/remove audit fields. `(revision_id, document_id)` is unique.

Revision-scoped metadata lives only on `RevisionDocument`, so a superseded revision's package stays historically frozen even when a later revision describes the same file differently.

### Lineage and inheritance

`ProjectRevision.based_on_revision_id` records which revision a revision was created from (same project only, any status, immutable after creation). When a revision is created with carry-forward enabled, the base's `INCLUDED` associations are copied as new `INHERITED` rows pointing at the **same** `Document`. No object-storage copy happens. Revision creation and inheritance are one transaction. Inheritance is a snapshot at creation time: later edits to the base are not propagated.

### Storage

- Objects live in S3-compatible storage behind an `ObjectStorage` interface; the rest of the application never calls the S3/MinIO SDK directly.
- Keys use only stable identifiers: `projects/{project_uuid}/documents/{document_uuid}/original{ext}`. No filenames, revision names, equipment tags, or classifications, so objects never move when metadata changes.
- Bucket access is private. Downloads are short-lived presigned URLs issued only through revision-scoped routes, signed against a browser-reachable endpoint (`S3_PUBLIC_ENDPOINT_URL`). Storage credentials never reach the browser.
- Bytes are never stored in PostgreSQL. One upload request carries one file; the UI uploads many files as independent requests.

### Integrity and mutability

- Same-project integrity is enforced by the database (composite foreign keys including `project_id`; `RevisionDocument.project_id` is intentionally denormalized for this), and also validated in the service layer.
- A revision's document package is editable while the revision is `DRAFT` or `ACTIVE` and the project is `ACTIVE` or `PAUSED`. It is read-only when the revision is `SUPERSEDED` or the project is `ARCHIVED` or `CANCELLED`. Reads and downloads are always allowed. Enforcement is in the backend; mutations re-check after locking the project row (shared) and the revision row, and archive, cancel, and activation take the project row exclusively, so they cannot race an in-flight upload.
- Duplicate content (same SHA-256 in a project) is detected and allowed; it is never deduplicated automatically.

### Organization

No folders. Organization is metadata-driven (document type, origin, status, search). Future virtual views (by equipment) and submission/document packages are possible later and are not designed out, but are not part of Phase 2.

### API and web surface

All document routes are nested under a revision, so a document is always reached through the revision and project that own it (a mismatched id is a 404):

| Method and path (under `/api/projects/{project_id}/revisions/{revision_id}/documents`) | Purpose |
| --- | --- |
| `POST` | Upload one file (multipart); duplicates are flagged, not rejected |
| `GET` | List with `status`, `document_type`, `origin` and `search` filters (no pagination) |
| `GET /{revision_document_id}` | One association with its `Document` facts |
| `PATCH /{revision_document_id}` | Edit type, number, description, notes (unknown or immutable fields are 422) |
| `POST /{revision_document_id}/remove`, `/restore` | Revision-level remove and restore (idempotent) |
| `POST /reuse` | Add an existing document from another revision of the same project |
| `GET /{revision_document_id}/download-url` | Short-lived signed URL (`inline` or `attachment`), allowed in any revision or project state |

Revision creation accepts `based_on_revision_id` and `carry_forward_documents`; revision responses expose lineage. Conflicts use the body `{"detail": {"detail": "...", "code": "..."}}`; `document_already_in_revision` also carries `existing_revision_document_id` and `existing_status`.

The web app (`apps/web`) shows the revision page as the documents workspace: filters and quick filter chips, uploaded vs inherited origin, signed Open and Download, multi-file upload (independent requests, three at a time), a row menu for edit, remove and restore, "Add from another revision", and a read-only banner. Mutation controls are hidden when the backend would refuse them.

### Not in Phase 2

OCR, AI or auto-classification, equipment and engineering-model entities, ETAP/SKM/EasyPower. Phase 3, below, adds document pages, rendering, and thumbnails.

## Phase 3

Phase 3 is document processing: stable logical pages and derived artifacts for an immutable `Document`. Specification: `cursor/phase3_specs.txt`. Decision record: [ADR-005](../decisions/ADR-005-document-processing-and-page-identity.md) (Accepted). Plan: [PHASE3_PLAN.md](PHASE3_PLAN.md). Delivery: [PHASE3_PR_PLAN.md](PHASE3_PR_PLAN.md). Status: complete (2026-10-10).

Processing hangs off `Document`. Revisions that share a file share one page set and one completed result. A PDF page, a PNG or JPEG, and a TIFF frame each become one `DocumentPage` (page numbers start at 1). `source_width` and `source_height` are the upright page after rotation normalization. `rotation_degrees` records the source rotation that was applied.

A `DocumentProcessingRun` is one attempt at a processing target (`document_id`, `processor_version`, `profile_hash`). Many failed attempts may exist. Only one `PENDING`, `RUNNING`, or `COMPLETED` run may exist for that target. Retry inserts a new run and leaves the failed attempt's rows and objects in place. `ensure_document_processing` creates the first run and re-enqueues an unclaimed `PENDING` run. It does not retry failure. Work runs in `document-worker` on a dedicated Celery queue, after the upload commits. A run is `COMPLETED` only when every page has its required artifacts. Pages and artifact URLs are exposed only then.

Artifacts are an analysis PNG, a thumbnail, and native PDF text when the page has a non-empty text layer. They are derived data, not the original evidence. Keys live under `processing/{run_id}/` and `put` never overwrites. There is no OCR.

The API and the worker share `packages/document-processing` for storage, the models, and the processing service. The worker does not import the FastAPI application. `packages/document-model` keeps the pure profile and key helpers.

The revision documents workspace shows Not started, Pending, Processing, Ready, and Failed from the list payload, and opens an inspection-only page viewer for a completed run.

### Not in Phase 3

OCR, automatic classification, layout or table extraction, evidence rows, equipment, and the engineering model.

## Phase 4

Phase 4 is AI-assisted document classification. Specification: `cursor/phase4_specs.txt`. Decision record: [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Accepted). Delivery: [PHASE4_PR_PLAN.md](PHASE4_PR_PLAN.md). Status: complete (2026-10-12). Handoff: [PHASE4_HANDOFF.md](PHASE4_HANDOFF.md).

Classification belongs to the immutable `Document`, so a file inherited or reused across revisions is classified once for a given processing run and classifier identity. `RevisionDocument.document_type` stays the engineer-confirmed type. An AI result is a suggestion. Nothing in this phase writes that column unless the engineer accepts the suggestion.

A run requires the current completed Phase 3 processing run. It classifies the document first. Page classification runs only when the document is mixed, unknown, or below the high confidence threshold. Page predictions are routing suggestions, not a reviewed page type. `MIXED_DOCUMENT` is a document class, not a page class.

The provider contract is vendor-neutral. The first real adapter is OpenAI (`gpt-6-luna`, Responses API, `store=false`). Tests and local Compose use a fake provider. Work runs on `extraction-worker` and a dedicated `document_classification` queue, and only when classification is enabled. Usage telemetry stores token counts and latency. It does not store prompts, document text, or a dollar cost.

### Not in Phase 4

OCR, equipment or table extraction, single-line topology, embeddings, automatic acceptance, page-level approval, and the engineering model.

## Phase 4.5

Phase 4.5 is a frontend refactor of the revision documents workspace. Specification: `cursor/phase4.5_specs.txt`. Delivery: [PHASE4_5_PR_PLAN.md](PHASE4_5_PR_PLAN.md). UI note: `cursor/phase4_5_document_workspace_ui.txt`. Status: complete (2026-10-12). There is no ADR.

The list is a master-detail workspace: Document, Type, and State, plus overflow. Presentation state is derived in the browser from the existing list payload. Classification review, processing, and metadata are in the detail drawer. Document, revision, processing, and classification semantics stay as Phases 2–4 defined them.

### Not in Phase 4.5

Backend or domain changes, a generic review queue, and the engineering model.

## Related documents

- [ROADMAP.md](ROADMAP.md) — intended future scope and design gates
- [ENGINEERING_MODEL.md](ENGINEERING_MODEL.md)
- [DOCUMENT_PIPELINE.md](DOCUMENT_PIPELINE.md)
- [EXTRACTION.md](EXTRACTION.md)
- [TOPOLOGY.md](TOPOLOGY.md)
- [VALIDATION.md](VALIDATION.md)
- [PROVENANCE.md](PROVENANCE.md)
- [REVIEW_WORKFLOW.md](REVIEW_WORKFLOW.md)
- [CODING_STANDARDS.md](CODING_STANDARDS.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)
- [PROJECT_STATUS.md](PROJECT_STATUS.md) — living phase status
- [PHASE0_HANDOFF.md](PHASE0_HANDOFF.md) — Phase 0 implementation context and environment notes
- [ADR-003](../decisions/ADR-003-project-revision-model.md) — project/revision model (Phase 1, accepted)
- [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md) — document storage and revision inheritance (Phase 2, accepted)
- [ADR-005](../decisions/ADR-005-document-processing-and-page-identity.md) — document processing and page identity (Phase 3, accepted)
- [ADR-006](../decisions/ADR-006-ai-document-classification.md) — AI document classification (Phase 4, accepted)
- [PHASE3_PLAN.md](PHASE3_PLAN.md) — Phase 3 conceptual plan
- [PHASE3_PR_PLAN.md](PHASE3_PR_PLAN.md) — Phase 3 pull-request delivery plan
- [PHASE4_PR_PLAN.md](PHASE4_PR_PLAN.md) — Phase 4 pull-request delivery plan
- [PHASE4_5_PR_PLAN.md](PHASE4_5_PR_PLAN.md) — Phase 4.5 pull-request delivery plan

### Phase 5 authoring refinement

The post-5G refinement retains the same revision aggregate and frozen registry-v1. Migration 0010 replaces legacy attribute states and adds profile-managed physical terminal roles, safely backfilled without changing connection endpoints. Equipment creation/type changes reconcile these roles atomically. The unified Equipment editor saves General, Attributes and custom terminals in one backend transaction; fine-grained endpoints remain available. Topology uses clickable tables and detail sheets. See [ENGINEERING_MODEL.md](ENGINEERING_MODEL.md), [TOPOLOGY.md](TOPOLOGY.md) and the [refinement handoff](PHASE5_AUTHORING_REFINEMENT_HANDOFF.md). Phase 6A is documented in [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md); 6B execution and 6C M1–M6 delivery are documented below and in the [final 6C handoff](PHASE6C_HANDOFF.md). Live-model quality remains unverified; 6D–6G remain pending.


## Phase 6A — Extraction persistence boundary

[ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md) and the [approved Phase 6 specification](specs/phase-6-evidence-structured-extraction.md) define document-scoped derived results with revision-document-scoped access. Eight entities retain pinned inputs, append-only work attempts, evidence, source-local groups, structured tables, typed candidates, evidence links and call telemetry. The existing SQLAlchemy Base and immutable Document/Page identities are reused. No canonical-model associations or writes are introduced; revision-wide frequency and phase count remain manual-only.

Atomic publication locks the run and producing unit and commits outputs with the success marker in the caller's transaction. DB uniqueness selects at most one successful attempt per logical key; read queries exclude all unsuccessful attempts. Technical AI-call telemetry is retained independently of success. Six explicit, paginated GET contracts provide included-document membership checks, inherited/historical access, honest coverage and exact values. Phase 6B adds scheduling, provider execution and retries/recovery/cancellation; extraction UI remains deferred to 6F. See [EXTRACTION.md](EXTRACTION.md) and [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md).


## Phase 6B — Durable execution and provider infrastructure

Migration `0013_extraction_execution` places mutable operational controls beside immutable 6A run/attempt/output history. The owning extraction package supplies versioned profiles, coordinator, delivery transport and a worker execution boundary; `packages/ai/extraction.py` supplies provider-neutral requests/results/errors/usage. Vendor SDK code remains in extraction-worker. Source-probe profiles explicitly identify test/infrastructure work and do not implement production engineering extraction.

Start/retry/cancel APIs reuse INCLUDED revision-document membership, including inherited and read-only revision access, with no canonical writes. Run creation serializes on Document; claims use a short global admission lock and consistent run/unit locking. Provider calls occur after claim commit. Tokens, expiring heartbeat leases, absolute deadlines and database publication fencing protect output; periodic Celery beat reconciliation handles expired attempts and durable pending delivery records. Duplicate notifications do not authorize duplicate provider calls. Retries append unsuccessful keys under pinned limits; cancellation settles every active attempt before a terminal parent and fences late output. Completed/cancelled history stays immutable and uses explicit new re-extraction.

The extraction worker consumes its classification queue and a separate document_extraction queue. A dedicated extraction-scheduler service runs beat; broker loss does not erase committed plans. Profiles/resources/call admission budgets are pinned, external processing is off by default and credentials stay at the worker integration boundary. The exact flow, operational guarantees, validation and known limits are recorded in [PHASE6B_HANDOFF.md](PHASE6B_HANDOFF.md).

## Phase 6C M1 — Offline engineering definitions

The extraction package now owns bounded intermediate engineering observations, composable recognition/attribute prompt resources, registry-derived context, qualified terminology data and deterministic stage/resource identities. These modules import no ORM, HTTP, task transport or vendor SDK. They do not normalize, ground, publish or execute observations. The existing AI envelope, provider adapter, coordinator, profiles, persistence and frozen registry remain unchanged. [PHASE6C_PLAN.md](PHASE6C_PLAN.md) defines the two-stage integration planned for later milestones; [PHASE6C_M1_HANDOFF.md](PHASE6C_M1_HANDOFF.md) records the delivered boundary.

## Phase 6C M2 — Pure interpretation boundary

The extraction package's versioned interpreter now resolves semantic meanings from admitted local statements and associated equipment context, checks model assertions and delegates typed normalization to the frozen engineering registry. It returns immutable mapped/unmapped/invalid interpretations or explicit source-field rejection, without constructing persistence output or performing provider/storage I/O. The rules' source hash and registry/terminology identities are reproducible in the built wheel. Artifact admission, association proof, offsets and publication remain M3; worker/profile integration remains M4–M5. See [PHASE6C_M2_HANDOFF.md](PHASE6C_M2_HANDOFF.md).

## Phase 6C M3 — Grounding and conversion boundary

The extraction package now verifies pinned source artifacts, admits local source statements, resolves text/codepoint or explicit page-level visual grounding, checks conservative source-local associations and converts accepted observations into atomic 6A output. ORM ownership/context loading is separate from storage loading and conversion; provider execution and commits remain caller-owned. Completed recognition context is immutable and same-run/page/artifact scoped. No canonical associations or writes are introduced.

Bounded diagnostic counts extend the existing successful-unit output JSON; the publisher writes counts and results before the success marker in its savepoint. Additive read precision markers use existing evidence fields and require no schema migration. Legacy profiles, manifests, provider handling, cancellation/recovery and DB fences are unchanged. Production two-stage planning and OpenAI/profile wiring remain M4–M5. [PHASE6C_M3_HANDOFF.md](PHASE6C_M3_HANDOFF.md) records actual guarantees, tests and remaining limitations.

## Phase 6C M4 — Dependent page-stage execution

The coordinator pre-plans recognition and dependent attributes for each selected page. Dispatch excludes waiting dependencies before its bounded window; claim rechecks under the run lock before admission. Aggregation settles unsatisfiable pending dependents before the parent becomes terminal, while bounded upstream retries keep them waiting. Manual retries append only satisfiable unsuccessful keys, and read-side retry flags use that same rule. Recovery prioritizes expired leases and also finds pending unsatisfiable dependencies without scanning healthy active runs. Existing cancellation, budget/concurrency locks, leases and publication fencing retain authority.

A separate v2 profile wire format pins stage/resource/runtime identities and multimodal/context limits; the legacy v1 wire/hashes remain identical. Claims carry exact page artifact descriptors and the unique committed recognition attempt. Verified page loading and provider I/O happen outside metadata transactions, with a short transaction to verify upstream context against the pinned bytes. The neutral response envelope selects a concrete Pydantic stage schema without importing extraction or SDK code. Actual stage schema/instruction hashes and upstream correlation are reproduced from immutable outputs. Synthetic stage execution is available; M5 adds the production OpenAI adapter/profile discovery below; evaluation remains M6. See [PHASE6C_M4_HANDOFF.md](PHASE6C_M4_HANDOFF.md).

## Phase 6C M5 — Opt-in production OpenAI integration

The existing worker adapter selects the trusted stage response class and makes one bounded Responses structured call, with SDK retries disabled, store=false and no tools. Named native-text, image and committed recognition projections remain separate untrusted user input; trusted instructions contain only versioned prompts/registry context. Adapter and execution revalidation precede M3 conversion and fenced atomic publication. Production hybrid/text profiles report ENGINEERING_EXTRACTION through existing discovery/detail contracts under the existing external-processing opt-in, while default fake and infrastructure probe behavior remain available.

Production v3 profiles pin a v2 runtime, provider input-contract identity, model/effort/image detail and separate context/output limits. Original M4 profile/identity reader sources are retained as packaged resources so v1/v2 historical identities and shared unchanged execution paths remain supported. Unknown resources fail without a latest-version fallback. Actual SDK requests/parsing are verified with transport mocks and real worker/beat/PostgreSQL/Redis/MinIO publication/retry/restart tests; model accuracy remains unmeasured. No new route, migration, canonical write or frontend is added. See [PHASE6C_M5_HANDOFF.md](PHASE6C_M5_HANDOFF.md).

## Phase 6C M6 — Evaluation boundary

Pure extraction-package modules load/hash a bounded synthetic corpus, replay recorded stage observations through M1–M3 and score source-matched outputs. The default CLI imports no SDK/ORM/broker execution path. Expected values are authored independently; matching excludes proposed keys/values. Reports keep failed cases, explicit denominators, source/resource/scorer identities and separate scripted versus live provenance. Visual metrics retain page-level limits.

A separate worker helper implements explicitly approved live evaluation using existing production profiles, `ExtractionCoordinator` and `execute_unit()`. It verifies exact artifact bindings for the whole batch before commit, pins two admissions and one attempt per stage, scores committed DB outputs and cancels only its own unfinished runs on interruption. It creates no alternate provider path or public API. M6 changes no production runtime resources, migrations, canonical writes or registry definitions. Its runner tests use injected providers; no live model quality has been measured. See [PHASE6C_HANDOFF.md](PHASE6C_HANDOFF.md) and the [corpus guide](../evals/extraction/README.md).

## Phase 6D M1 — Offline table observations and stage resources

The extraction package owns two independent offline definitions, TABLE_RECONSTRUCTION and dependent TABLE_INTERPRETATION. Strict observations represent all established orientations, sparse cells, explicit blank/unreadable content, hierarchical headers, spans, uncertainty and table-local aliases. Pure layout inspection/reference checks retain unverified status; they create no database entities or grounded engineering interpretations. Versioned server metadata is intended for the existing table-layout-v1 adapter in M2, not a parallel persistence model.

Three new packaged prompts and a table manifest reuse existing all-registry context and qualified terminology. No old manifest/profile/runtime resources, schemas, execution paths, models, migrations or API routes change. New table profiles remain unregistered. The approved future profile is table-only, with separate 6C prose runs; cross-profile summary/history tests remain M3. Source admission/normalization/publication remain M2, production integration M3 and representative table evaluation M4. See [PHASE6D_M1_HANDOFF.md](PHASE6D_M1_HANDOFF.md) and [PHASE6D_PLAN.md](PHASE6D_PLAN.md).

## Phase 6D M2 — Grounding, interpretation and publication

M2 adds exact pinned table admission, independent literal-text/relationship reliability, conservative structured-cell registry interpretation, source-local groups and conversion into existing tables/evidence/relational candidates. Native structure requires a unique contiguous delimiter grid; otherwise an explicit visual reading retains page-level limits or the association remains unresolved. Committed reconstruction is revalidated for the exact run/page/artifacts before interpretation. Publisher checks now reject wrong-page/artifact/cell and unfinished upstream ownership, and existing evidence reads report actual table-cell precision and sign the historical artifact.

M1/6C resources and profile/runtime identities, registry-v1, migrations and canonical models remain unchanged. M2 introduced no production table profile or worker execution; M3 integration and M4 representative table evaluation are recorded below. Table-only ownership still requires a separate 6C prose run, and latest summaries continue selecting across profiles. See [PHASE6D_M2_HANDOFF.md](PHASE6D_M2_HANDOFF.md) for actual checks, source rules and conservative coverage limits.

## Phase 6D M3 — Table execution integration

A separate v4 TableProfile uses the fixed TABLE_RECONSTRUCTION → TABLE_INTERPRETATION plan through existing admission, SQL prerequisites, delivery, leases, retry, recovery and publication. Verified source I/O and request rendering occur outside metadata transactions; the short committed-context loader and independent provider fence preserve immutable upstream ownership. The existing Responses adapter selects the table schema/envelopes explicitly. Empty interpretation retains admission/lease fencing and a skip marker without provider I/O. Accepted prose/probe runtime hashes use retained identity data, never dynamically executed archives; new table behavior has its own runtime. Existing history/summary/read contracts remain across profiles.

The table-only/prose separation and cross-profile latest-result behavior remain explicit. Real worker/SDK transport mocks verify plumbing and compatibility; M4 table evaluation is recorded below; live model accuracy remains unmeasured. See [PHASE6D_M3_HANDOFF.md](PHASE6D_M3_HANDOFF.md).

## Phase 6D M4 — Independent table evaluation

The separate offline `powerforge-eval-tables` command (`python -m powerforge_extraction.table_eval`) replays versioned reconstruction/interpretation recordings against independently authored source/table/cell/claim annotations. Source occurrences and cell coordinates select matches before proposed meanings, typed values, units or associations are scored. Reports retain missed/failed gold denominators, null empty rates, structural/header/orientation metrics, source-local association, citation/locator checks and UNMAPPED/INVALID retention. Native literal proof, visual reports and relationship reliability remain distinct. Caller-provided recording provenance cannot designate live quality. The frozen 6C evaluator and M1–M3 production resources are unchanged.

The corpus has 27 synthetic cases, 27 gold tables, 146 cells and 73 claims, including a real processed-PDF native/hybrid pair. Native abstention loses recall against the visible source gold; visual relationships retain explicit page-level limits. All 100 new tests and new extraction-wheel checks pass. At the user's request, the already verified M3 full backend/integration/migration/API/dependency checks are carried forward, not repeated. No paid model call or live accuracy measurement is claimed. See the [table corpus guide](../evals/tables/README.md) and [final handoff](PHASE6D_HANDOFF.md) for actual scores, verification evidence and remaining limits.

## Phase 6E M1 — Pure spatial source foundation

Separate versioned modules in `packages/provenance` define immutable producer/artifact/page ownership, native/OCR positioned text, token/line/block and native-primitive support, exact source occurrences, conditional native-origin correspondence and pinned prepared/spatial bindings. Pure orthogonal transforms preserve crop, scale, mirrors, quarter turns and normalized upright geometry. Missing support stays null; a resolved support envelope does not establish table/equipment ownership. M1 support resolution remains UNRESOLVED structurally and does not independently verify printed characters. Unknown OCR text coverage remains UNKNOWN.

`powerforge_ai.ocr.PositionedOCRProvider` is a typed protocol with raw image/word/box/settings identity, engine-scale confidence and local usage/failure contracts. The original generic OCR interface and all accepted 6C/6D contracts/resources stay unchanged. No engine/native adapter, production profile, API, schema migration or publisher support is enabled by M1. Existing evidence is not retrospectively upgraded. M2 must implement real processing and durable source artifacts; M3/M4 must establish actual structure and source-aware publication. Backend purpose guards on every endpoint and the future coherent 6F UI remain required.

All 92 focused tests, provenance/AI wheel checks and new resource identities pass; accepted v1–v4 wires/resources and both full frozen 6C/6D reports reproduce unchanged. No infrastructure integration or paid provider call occurred. See [PHASE6E_M1_HANDOFF.md](PHASE6E_M1_HANDOFF.md) for actual bounds/verification and [PHASE6E_PLAN.md](PHASE6E_PLAN.md) for later review gates.


## Phase 6E M2 — Durable native/OCR source preparation

The new local source-preparation profile consumes an explicitly selected completed base run/pages and produces independent immutable native/OCR text and geometry. Actual PyMuPDF 1.28.2 and Tesseract 5 adapters preserve source-local occurrences, transforms, raw readings and recognition limits. Native-plus-raster text coverage stays UNKNOWN and requires explicit whole-page OCR selection; there is no guessed coverage percentage or blanket OCR. M2 establishes neither table relationships nor engineering meaning.

Migration 0014 adds SOURCE_ENRICHMENT purpose, separate source result/artifact/binding records and purpose/lease/identity guards. Local planning/execution/publication reuse the existing durable coordinator with a dedicated CPU queue and admission pool. Source start/input discovery/history/detail/result/artifact/retry/cancel APIs enforce membership and purpose on direct IDs; ordinary extraction summaries/history ignore source jobs. Local run model/prompt/registry fields are inapplicable, and local jobs cannot publish ordinary extraction outputs or AI calls. Usage distinguishes admissions, recognition requests and confirmed engine invocations; unmeasured cost/child resources remain null.

All 271 distinct targeted checks pass, including 51 new M2 cases, real OCR/PostgreSQL/Redis/MinIO/Celery/restart and accepted extraction lifecycle/migration checks. Retained v4 source data preserves old wire/resource hashes and both frozen evaluation reports. The worker image and package wheels reproduce accepted resources; no paid calls or UI changes occurred. Deployment, actual eligibility, measured limits and remaining M3–M5 scope: [PHASE6E_M2_HANDOFF.md](PHASE6E_M2_HANDOFF.md). Stop for M2 review before M3; the backend separation still permits the approved coherent future 6F guided workflow.
