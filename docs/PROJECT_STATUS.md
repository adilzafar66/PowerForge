# Project status

Living status of PowerForge phases. Update this file when a phase is specified, started, or completed. Do not treat chat history as the source of truth.

**Current implemented phase:** Phase 5 authoring refinement — Phase 5 complete / re-frozen

**UI redesign:** UI-A — Design system and app shell implemented. Next UI milestone: UI-B. See [UI_A_HANDOFF.md](UI_A_HANDOFF.md).

**Next engineering phase:** Phase 6 — Evidence, candidates, and structured extraction. Not started

[ROADMAP.md](ROADMAP.md) is the canonical high-level plan for intended future scope; this file remains authoritative for implementation status.

## Phase 0 — Architecture and repository setup

**Status:** Complete (2026-09-02)

Runnable skeleton: FastAPI health/readiness, PostgreSQL + Alembic (`pgcrypto`), Redis, MinIO, Celery worker heartbeats, Next.js stack status UI, CI.

Details, environment notes, and verification: [PHASE0_HANDOFF.md](PHASE0_HANDOFF.md).

## Phase 1 — Project and revision management

**Status:** Complete (2026-09-03)

Implementation spec: `cursor/phase1_specs.txt`  
Decisions: [ADR-003](../decisions/ADR-003-project-revision-model.md)

Delivered:

- `packages/project` (`powerforge_project`) — status enums and transition helper
- PostgreSQL tables `projects` and `project_revisions` (Alembic `0002_projects_and_revisions`, `0003_status_before_archive`); Phase 2 migration `0004_documents_and_lineage` adds revision lineage, `documents`, and `revision_documents`. Alembic head is `0009_topology_persistence`, which adds the Phase 5D topology tables after Phase 5C revision metadata in `0008_revision_model_metadata` and Phase 5B equipment tables in `0007_engineering_model_core`. `0005_document_processing` adds `document_pages`, `document_processing_runs`, and `page_artifacts`. `0006_document_classification` adds `MIXED_DOCUMENT` and the classification tables.
- REST API under `/api/projects` and nested revisions (create/list/get/patch + pause/resume/cancel/archive/unarchive + activate)
- Web UI: `/` project list, `/projects/new`, `/projects/[id]`, revision placeholder, `/status` stack health
- Backend and frontend tests covering lifecycle, uniqueness, and concurrent activate

## Phase 2 — Document management, immutable storage, revision inheritance

**Status:** Complete (2026-10-06). Every item in the spec's definition of done (section 36) was checked against named tests or recorded checks in PR-15; the one thing not performed is a click-through of the web UI in a real browser (see "Verification" below).

Implementation spec: `cursor/phase2_specs.txt` (version 2)  
Delivery plan: [PHASE2_PR_PLAN.md](PHASE2_PR_PLAN.md)  
Decisions: [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md) (Accepted)

Delivered:

- `Document` (immutable uploaded artifact) and `RevisionDocument` (revision-scoped association, metadata, origin, status)
- Revision lineage (`based_on_revision_id`) and copy-on-write document inheritance with no file copies
- S3-compatible storage behind an `ObjectStorage` abstraction (boto3; MinIO in development), stable machine-oriented keys
- Validated PDF/PNG/JPEG/TIFF upload (extension and content must agree), streaming size limit, SHA-256, duplicate detection (allowed, not merged)
- Manual classification, metadata editing, remove/restore, reuse of an existing document in another revision, presigned download through revision-scoped routes
- Superseded revision packages are read-only; backend enforced
- Create-revision UI (base revision, carry-forward) and a revision documents workspace (replaces the Phase 1 revision placeholder)

Explicitly **not** in Phase 2: folders, OCR, AI or auto-classification, document pages/thumbnails/rendering, equipment/engineering model, DocumentPackage entities, ETAP/SKM/EasyPower.

### Baseline before implementation (2026-10-01)

Phase 1 code as of commit `4055d85` plus two then-uncommitted working-tree changes (a project-row lock in `RevisionService.create_revision` when `activate=true`, and a matching test in `tests/test_projects_api.py`). Those two changes are now committed in `9a42b3b`.

| Check | Result |
| --- | --- |
| `ruff check .` | Passed |
| `pytest` (integration skipped) | 23 passed, 16 skipped |
| `RUN_INTEGRATION=1 pytest` against a fresh, migrated throwaway PostgreSQL database | 39 passed |
| `npm run lint` (`apps/web`) | No warnings or errors |
| `npm test` (`apps/web`) | 11 passed |
| `npx tsc --noEmit` (`apps/web`) | No errors |

Integration tests were run against a temporary database (`powerforge_baseline`, since dropped) because the existing integration tests create rows and never clean up; running them against the dev database would add test projects to it. Do the same for Phase 2 runs.

### Delivery

Phase 2 was delivered as 16 pull requests (PR-00 to PR-15), tracked with scope, tests and spec traceability in [PHASE2_PR_PLAN.md](PHASE2_PR_PLAN.md). Work packages (all done):

- [x] PR-00, PR-01: Phase 1 lock fix; specification, ADR-004 and documentation
- [x] PR-02 to PR-06: document vocabulary and validation, constraint-name IntegrityError mapping, migration `0004` and ORM models, storage abstraction and settings, streaming ingestion and file inspection
- [x] PR-07: revision lineage and inheritance in one transaction
- [x] PR-08 to PR-10: upload/list/get, edit/remove/restore/reuse, signed downloads, and the spec section 34 end-to-end test
- [x] PR-11 to PR-14: web foundations and Create Revision, documents workspace, multi-file upload, document actions
- [x] PR-15: requirements audit, full verification, documentation correction, ADR-004 accepted

### Verification (PR-15, 2026-10-06)

| Check | Result |
| --- | --- |
| `ruff check .` | Passed |
| `pytest` (integration skipped) | 200 passed, 246 skipped |
| `RUN_INTEGRATION=1 pytest` on a fresh, migrated throwaway database with MinIO running | 446 passed |
| `npm run lint`, `npx tsc --noEmit`, `npm run build` (`apps/web`) | Clean |
| `npm test` (`apps/web`) | 172 passed (11 files) |
| Clean Compose stack (`down -v`, `up --build`) | Migrated from empty to `0004`; `/ready` ok; bucket created and private |
| Section 34 scenario over HTTP against that stack | Passed, including exactly one stored object per `Document`, read-only superseded revision, and download of a superseded revision's file through a presigned URL from `http://localhost:9000` |
| Bucket privacy | Anonymous bucket listing and object GET were refused (403) |
| CORS preflight (`PATCH`, `POST`) from `http://localhost:3000` and `http://127.0.0.1:3000` | Allowed |
| Upgrade from `0003` with data, and downgrade | Covered by `tests/test_migration_0004.py` (part of the integration run) |
| Click-through of the web UI in a real browser (signed Open/Download, drag-and-drop upload, row menu, reuse dialog) | **Not performed.** Web behavior is covered by vitest component tests and HTTP checks only |

### Intentional deviations and technical debt (final)

- Orphaned storage objects (crash between upload and commit; uploaded-then-removed documents); no garbage collection
- PDF validation is header-only; images are validated structurally, not fully decoded (a JPEG or TIFF with a valid header but truncated body is accepted; only PNG structure is walked by `verify()`)
- No pagination on document lists
- No document-level audit trail beyond added/removed fields; `uploaded_by`/`added_by`/`removed_by` stay null until authentication exists
- Phase 1 still allows editing a superseded revision's identifier and description (only the document package is frozen)
- `RevisionDocument.project_id` is intentionally denormalized to enable database-level same-project enforcement
- Document lists are not paginated; the reuse dialog loads whole lists
- Starlette spools an accepted multipart body to a temporary file before the handler runs, so a client that omits or lies about `Content-Length` (for example chunked encoding) can write a full body to temp disk before the streaming cap rejects it; apply a proxy body limit in shared environments
- The web size limit (`NEXT_PUBLIC_MAX_UPLOAD_BYTES`) is advisory because the API does not publish its limit
- No browser end-to-end automation (Playwright or similar)
- Deviations from the spec text are listed at the end of `cursor/phase2_specs.txt`

## Phase 3 — Document processing

**Status:** Complete (2026-10-10).

Specification: `cursor/phase3_specs.txt`  
Plan: [PHASE3_PLAN.md](PHASE3_PLAN.md)  
Delivery: [PHASE3_PR_PLAN.md](PHASE3_PR_PLAN.md) (PR-01 … PR-09 landed; PR-10 is this close-out)  
Decisions: [ADR-005](../decisions/ADR-005-document-processing-and-page-identity.md) (Accepted 2026-10-10)

Phase 3 turns each immutable `Document` into stable `DocumentPage` rows and derived artifacts (analysis image, thumbnail, native PDF text when the page has a text layer), asynchronously in `document-worker`. Processing belongs to `Document`, so inherited revisions share one result. A processing run is one attempt; retry inserts a new run and keeps the failed attempt. OCR, classification, and the engineering model are not part of this phase.

### Intentional deviations and technical debt

Phase 2's debt list above still applies. Phase 3 adds:

- Failed-attempt objects are left in storage. There is no garbage collection.
- There is no UI or API for browsing older failed attempts.
- Encrypted PDFs fail the run. There is no password entry.
- Upload validation stays header-only for PDFs and structural for images. Decode failures surface as a failed processing run.
- There is no Playwright suite. The page viewer is covered by vitest and by the HTTP walk-through recorded in the PR-10 notes. A click-through of the viewer in a real browser was not performed.

### Baseline before implementation (2026-10-08)

Phase 2 tree at `2c75e44`, plus the untracked Phase 3 spec. Integration tests used a throwaway database (`powerforge_phase3_baseline`, created, migrated to `0004`, then dropped) so the dev database was not polluted. MinIO was already running.

| Check | Result |
| --- | --- |
| `ruff check .` | Passed |
| `pytest` (integration skipped) | 200 passed, 246 skipped |
| `RUN_INTEGRATION=1 pytest` on the throwaway database with MinIO running | 446 passed |
| `npm run lint` (`apps/web`) | No warnings or errors |
| `npx tsc --noEmit` (`apps/web`) | No errors |
| `npm test` (`apps/web`) | 172 passed (11 files) |

`npm run build` was not run. Run it when the web UI changes.

## Phase 4 — AI document classification

**Status:** Complete (2026-10-12).

Specification: `cursor/phase4_specs.txt`  
Delivery: [PHASE4_PR_PLAN.md](PHASE4_PR_PLAN.md) (PR-01 through PR-09)  
Decisions: [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Accepted 2026-10-12)  
Handoff: [PHASE4_HANDOFF.md](PHASE4_HANDOFF.md)

Phase 4 classifies an immutable `Document` after a completed Phase 3 processing run. The AI result is a suggestion. `RevisionDocument.document_type` stays the engineer-confirmed type until an explicit accept. When classification is enabled, a completed processing run queues `document_classification` and `extraction-worker` classifies it. The OpenAI adapter is mocked in tests. Compose enables classification for the API, document worker, and extraction worker, using the fake provider. The API returns a suggestion and attempt on list, detail, and upload, and accept is the only way a suggestion becomes the confirmed type. The revision documents workspace shows that suggestion, including page predictions when the suggestion is a mixed document. `powerforge-eval-classification` scores a labeled manifest offline. CI does not run a live OpenAI evaluation.

### Close-out (2026-10-12)

The audit mapped spec §55 and §67 onto the existing classification suites. One assertion was added: a page with no native-text artifact contributes an empty excerpt. The evaluation command loads the renderer and the OpenAI adapter by module name, so the classification package still has no static import of those boundaries. A diff of the Phase 4 commits against `1ec0c71` (Phase 3 close) found no OCR, equipment or table extraction, SLD topology, embeddings, RAG, cost fields, or ETAP/SKM/EasyPower code. Compose stays on the fake provider with classification enabled.

The PR-08 acceptance line cites decision D8 for the evaluation command name. The settled name is decision D5. D8 is the upload-response summary.

| Check | Result |
| --- | --- |
| `ruff check .` | Passed |
| `pytest` (integration skipped) | 293 passed, 351 skipped |
| `RUN_INTEGRATION=1 pytest` on throwaway `powerforge_pr09` migrated to head, then dropped | 644 passed |
| Upgrade `powerforge_pr09_0005` from `0005_document_processing` with one completed processing run, then to head | Classification tables present. `powerforge_document_classification.backfill.main(["--limit", "1"])` with classification enabled inserted one run. The console script is not installed in `.venv`. Database dropped |
| `npm run lint`, `npm test`, `npx tsc --noEmit`, `npm run build` (`apps/web`) | Lint clean. 190 tests passed. Typecheck clean. Build succeeded |
| Live OpenAI evaluation | Not run. `OPENAI_API_KEY` was absent |
| `docker compose down -v && docker compose up --build -d` | Exit 0. Fresh database at `0006_document_classification` |
| Clean-stack scenario (`AI_PROVIDER=fake`, classification enabled) | Upload reached processing `COMPLETED` and a `SINGLE_LINE_DIAGRAM` suggestion. Accept set the confirmed type. A child revision inherited that document with the same one classification run. Reclassify added a second run and left the confirmed type in place. A filename containing `fail` failed with `PROVIDER_UNAVAILABLE`, and retry created a new failed run. `document-worker` consumed only `document_processing`. The unsigned object URL returned 403; the signed URL returned the PDF |

### Baseline before implementation (2026-10-11)

Phase 3 tree on `main`, plus the untracked Phase 4 spec and this delivery plan, before any Phase 4 code. Integration tests used a throwaway database (`powerforge_phase4_baseline`, created, migrated from empty to `0005_document_processing`, then dropped) so the dev database was not polluted. Postgres, Redis, and MinIO were started from the existing Compose containers for the run and were not a clean `docker compose up`.

| Check | Result |
| --- | --- |
| `ruff check .` | Passed |
| `pytest` (integration skipped) | 241 passed, 290 skipped |
| `RUN_INTEGRATION=1 pytest` on `powerforge_phase4_baseline` at `0005_document_processing`, with MinIO running | 531 passed |
| `npm run lint` (`apps/web`) | No warnings or errors |
| `npm test` (`apps/web`) | 175 passed (11 files) |
| `npx tsc --noEmit` (`apps/web`) | No errors |

`npm run build` was not run. There is no web UI change in PR-01. Run it when the classification workspace changes.

## Phase 4.5 — Document workspace UI

**Status:** Complete (2026-10-12). No ADR.

Specification: `cursor/phase4.5_specs.txt`  
Delivery: [PHASE4_5_PR_PLAN.md](PHASE4_5_PR_PLAN.md)  
UI note: `cursor/phase4_5_document_workspace_ui.txt`

The revision documents workspace is a master-detail layout. The list columns are Document, Type, and State, plus an overflow menu. The secondary line carries document number, file size, origin, and page count. Classification review, processing, metadata, and the remaining actions live in a right-side drawer. Presentation state is derived in the browser from the existing list payload. Document, revision, processing, and classification semantics stay as implemented in Phases 2–4. The engineering model is not part of this phase.

| Check | Result |
| --- | --- |
| `npm run lint` (`apps/web`) | No warnings or errors |
| `npm test` (`apps/web`) | 209 passed |
| `npx tsc --noEmit` (`apps/web`) | No errors |
| `npm run build` (`apps/web`) | Succeeded |
| `ruff check .` | Passed |
| `pytest` (integration skipped) | 293 passed, 352 skipped |
| `RUN_INTEGRATION=1 pytest` on throwaway `powerforge_test`, then dropped | 645 passed |

The revision page was not clicked in a browser. No browser tools were available in this session.

## Phase 5A — Registry, units, and requirement engine

**Status:** Implemented (2026-10-23).

Specification: [Phase 5](specs/phase-5-engineering-model.md), scoped by the
[Phase 5A prompt](prompts/phase-5a_codex.md). Decision: [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md).
Domain/API usage and semantics: [ENGINEERING_MODEL.md](ENGINEERING_MODEL.md).
Implementation and exact validation commands: [PHASE5A_HANDOFF.md](PHASE5A_HANDOFF.md).

The standard-library-only engineering-model package now owns immutable registry-v1
definitions, value normalization, and pure requirement evaluation. The independent JSON
snapshot matches all 20 equipment types, 296 attributes, 44 requirement reference rows,
and 17 unit families. Three NONE rows are annotations rather than executable rules.
The API validates the registry on construction and exposes
`GET /api/engineering-model/registry` with typed conditions and permitted input units.
No persistence, model inheritance, topology CRUD, or Engineering Model frontend was added.

Validation: 176 new Phase 5A tests passed; full Python regression passed all 821 tests
with live integrations against a disposable database, which was removed afterward.
Ruff and formatting checks passed. Python static typechecking is not configured;
no frontend changes or frontend checks were made.

## Phase 5B — Core engineering-model persistence

**Status:** Implemented (2026-10-23).

Specification: [Phase 5B prompt](prompts/phase-5b-codex.md), [Phase 5](specs/phase-5-engineering-model.md), and [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md).
Implementation, decisions, and validation: [PHASE5B_HANDOFF.md](PHASE5B_HANDOFF.md).
Usage: [ENGINEERING_MODEL.md](ENGINEERING_MODEL.md).

Migration `0007_engineering_model_core` adds project-owned equipment lineage, revision-scoped equipment, and typed canonical attributes. A neutral persistence package owns Base/project/revision/engineering mappings, with compatibility exports for existing document callers. Internal services atomically materialize registry attributes, normalize manual values, preserve meaningful data during type changes, and soft-remove/restore equipment. Document and engineering writes share project-then-revision locking and lifecycle checks.

Initial attributes use NOT_EXTRACTED / UNVERIFIED with null origin, confidence, and values. Database constraints enforce typed slots, confidence bounds, ownership, and uniqueness. Registry-v1, units, and requirement evaluation remain unchanged. Phase 5B itself added no model cloning, topology, public equipment CRUD, or frontend.

Validation: all **918 Python tests passed** with live integrations on a disposable database; **473 passed, 445 skipped** without integrations. Ruff, formatting, whitespace, and package dependency checks passed. Exact commands are recorded in the handoff. Tests cover all 20 equipment types, typed values and representative unit conversions, manual states, safe type changes and rollback, soft lifecycle, ownership, real concurrent lifecycle changes, and fresh/data-preserving upgrade/downgrade/re-upgrade.

## Phase 5C — Revision model inheritance and model metadata

**Status:** Implemented (2026-10-23).

Specification: [Phase 5C prompt](prompts/phase-5c-codex.md), [Phase 5](specs/phase-5-engineering-model.md), and [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md). Implementation, decisions, and exact validation results: [PHASE5C_HANDOFF.md](PHASE5C_HANDOFF.md).

Migration `0008_revision_model_metadata` adds nullable `system_frequency` (canonical Hz as Decimal/NUMERIC, finite and positive) and `system_phase_count` (integer 1 or 3) to ProjectRevision. Revision creation accepts `carry_forward_model` independently from document carry-forward. With a base it defaults true, clones only ACTIVE equipment into independent rows with preserved lineage and direct source pointers, and inherits omitted model metadata. Explicit values override and explicit null clears. Without a base it defaults false, and explicit true is rejected.

Clone compatibility is checked against the current immutable registry. Newly added destination attributes materialize untouched; old or incompatible untouched placeholders may be omitted; meaningful incompatible data rejects and rolls back the transaction. Revision creation, document inheritance, model inheritance, metadata, and optional activation share one transaction and the established project-then-revision lock order. The pure effective-value helper prefers explicit PRESENT equipment values, then revision defaults, and reports disagreements without mutating rows or persisting findings.

The existing revision-create UI now exposes only the independent model carry-forward checkbox. No topology, public engineering-model CRUD API, Engineering Model workspace, extraction, evidence, reconciliation, or Phase 5D work was added.

## Phase 5D — Canonical topology persistence

**Status:** Implemented (2026-10-23).

Specification: [Phase 5D prompt](prompts/phase-5d-codex.md), [Phase 5](specs/phase-5-engineering-model.md), and [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md). Implementation and exact validation commands: [PHASE5D_HANDOFF.md](PHASE5D_HANDOFF.md). Usage and lifecycle semantics: [TOPOLOGY.md](TOPOLOGY.md).

Alembic head `0009_topology_persistence` adds `model_nodes` and `model_connections`, with composite ownership, terminal uniqueness, node-shape, self-loop, canonical-voltage, confidence, lifecycle, and inheritance constraints. The pure topology package replaces the stale BUS placeholder with exactly EQUIPMENT_TERMINAL / ELECTRICAL_NODE. Connections use ELECTRICAL / GROUNDING / OTHER and UNDIRECTED / NOMINAL_FROM_TO.

Internal manual services use the established project-then-revision locks. Equipment/node removal cascades logical connection removal atomically; restoring equipment restores terminals, while restoring nodes never restores connections. Model carry-forward remaps ACTIVE topology after equipment/attributes, preserves immediate-base provenance, and rejects inconsistent active graphs atomically.

Validation: **1,024 Python tests passed** with live integrations against disposable PostgreSQL/MinIO; **496 passed, 528 skipped** offline. Ruff, changed-file formatting, dependency, and whitespace checks passed. Phase 5D itself changed no frontend files or public CRUD routes.

## Phase 5E — Revision-scoped engineering-model APIs

**Status:** Implemented (2026-10-24).

Specification: [Phase 5E prompt](prompts/phase-5e-codex.md), [Phase 5](specs/phase-5-engineering-model.md), and [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md). Exact endpoints, schemas, error mapping, and validation commands: [PHASE5E_HANDOFF.md](PHASE5E_HANDOFF.md).

The dedicated model router exposes revision-scoped Equipment, EquipmentAttribute, ModelNode, and ModelConnection APIs through the accepted services. Strict manual schemas reject forged provenance/audit/inheritance fields; response models retain canonical provenance and lossless Decimal strings. Equipment lists support literal case-insensitive search and type/lifecycle filters without fetching attributes. All resource lists use `items`; lifecycle filters support ACTIVE, REMOVED, and ALL. Attribute order remains registry-defined. Domain validation maps to clean 422 responses, ownership failures to 404, and lifecycle/read-only conflicts to 409.

The APIs preserve unit conversion, independent revision snapshots, incomplete-state saves, duplicate tags, parallel edges, safe type changes, and conservative removal/restoration cascades. No persistence migration was added; Alembic head remains `0009_topology_persistence`. No frontend or worker files changed.

Validation: **1,048 Python tests passed**, no skips, with live integrations against disposable PostgreSQL/MinIO; **501 passed, 547 skipped** offline. The 24 new focused cases cover HTTP contracts, ownership, provenance protection, PATCH semantics, units, lifecycle, error translation, search query behavior, and OpenAPI scope. Ruff, formatting, dependency, and whitespace checks passed.

## Phase 5F — Basic Engineering Model workspace UI

**Status:** Implemented (2026-10-25).

Specification: [Phase 5F prompt](prompts/phase-5f-codex.md), [Phase 5](specs/phase-5-engineering-model.md), and [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md). Implementation details and validation: [PHASE5F_HANDOFF.md](PHASE5F_HANDOFF.md).

The revision page now offers Documents (the default) and Engineering Model workspaces. Equipment supports server search/type/lifecycle filters, creation, URL-addressable details, general edits, generic registry-driven attribute editors, terminal management, and removal/restoration. Topology provides electrical-node and connection lists/forms, human endpoint labels, separate parallel connections, and explicit cascade warnings. Registry metadata is cached within the mounted model workspace. Decimal inputs remain strings, state-only attribute saves omit stale values/units, and PATCHes contain only changed fields with explicit null clears.

Read-only revisions remain viewable with mutation controls unavailable. Stale read-only errors lock local editing and refresh revision/canonical state. Existing document behavior and the shared read-only banner remain in place. No backend, API, database migration, worker, or dependency changes were needed.

Validation: frontend lint, typecheck, and production build passed; **243 frontend tests passed** across 15 files, including 30 new model tests (suite rerun 2026-10-26 after the BOOLEAN regression fix). Normal backend regression: **506 passed, 548 skipped**, with six existing warnings. Live integration and browser/manual smoke testing were not performed for this frontend-only change; no browser automation tool was available. Final Phase 5 validation is recorded below.

<a id="phase-5g--priority-review-items"></a>

## Phase 5G — Hardening and final Phase 5 freeze

**Status:** Implemented (2026-10-26). **Phase 5 is complete and frozen.** Phase 6 is next and has not started.

Specification: [Phase 5G prompt](prompts/phase-5g-codex.md). Requirements mapping, exact commands, review findings, limitations and freeze verdict: [PHASE5G_HANDOFF.md](PHASE5G_HANDOFF.md).

The INTEGER precision debt is resolved: every non-null canonical `integer_value` now serializes as a base-10 JSON string, including small values; Python/domain/BIGINT storage remains integer. Frontend response types retain strings through decoding, display and resubmission. Regression coverage includes `3` and `9007199254740993`, null/state-only behavior, OpenAPI, and HTTP snapshot cloning with typed values and remapped topology. NUMBER precision and explicit BOOLEAN selection remain intact.

The registry-v1 snapshot still matches the authoritative reference (20 types, 296 attributes, 44 requirement rows, 17 unit families). Ownership, mutability, typed persistence, transactional inheritance, independent carry-forward, lifecycle and later-phase boundaries were audited against existing tests. No migration or dependency was added. A local frontend optimization replaces repeated node scans for connection restore eligibility with a set lookup. Measured list SELECT counts stayed constant between 1 and 25 equipment rows: equipment 3, nodes 5, connections 5. Unpaginated lists and whole-revision topology validation remain documented scaling debt.

Validation: **1,057 backend tests passed with live integrations, no skips**; offline **506 passed, 551 skipped**; both reported six existing dependency warnings. **245 frontend tests passed across 16 files**; lint, typecheck, production build, Python lint/changed-file formatting, dependency and whitespace checks passed. An isolated Compose project with fresh volumes migrated from empty to `0009_topology_persistence`; API health/readiness, all three workers, frontend routes, and a real HTTP/JavaScript precision/inheritance/lifecycle scenario passed. The disposable stack was removed after validation. No browser interaction tool was available; this is not a claim of browser/visual smoke coverage.

## Phase 5 authoring refinement

**Status:** Implemented (2026-10-26). **Phase 5 complete / re-frozen. Phase 6 next / not started.**

Authority: [authoring refinement prompt](prompts/phase-5-refinement.md). Decisions, migration behavior, exact commands, validation and debt: [PHASE5_AUTHORING_REFINEMENT_HANDOFF.md](PHASE5_AUTHORING_REFINEMENT_HANDOFF.md).

All 20 equipment types now have code-owned normal terminal profiles, materialized atomically on equipment creation. Profile-managed keys cannot be renamed or independently removed; type reconciliation preserves/adopts matching terminals and rejects removal of connected roles. Custom terminals remain possible. Migration `0010_authoring_refinement` safely backfills existing equipment without changing connection endpoints and replaces attribute information states: NOT_EXTRACTED → NOT_POPULATED, UNKNOWN → MISSING. Reset to NOT_POPULATED clears values/provenance and restores UNVERIFIED. Registry-v1 is unchanged.

The Equipment sheet now owns one draft across General, Attributes and Terminals, with one sticky Save, Ctrl/Cmd+S and Save/Discard/Keep-editing close protection. One editor API call commits the entire draft atomically; failures preserve the draft and roll back all writes. Node/Connection tables open detail/edit sheets. Lossless NUMBER/INTEGER strings, explicit BOOLEAN selection and backend-authoritative read-only rules remain enforced.

Validation: **1,064 backend tests passed with live integrations, no skips**; offline **505 passed, 559 skipped**, with six existing dependency warnings. **248 frontend tests passed across 16 files**; lint, typecheck and production build passed. Python lint/changed-file formatting, dependency and whitespace checks passed. Fresh migration to head and representative pre-refinement data upgrade/downgrade/re-upgrade passed on disposable infrastructure. No actual browser interaction test was performed. No dependency or Phase 6 feature was added.

## Later phases

Phase 5A through 5G and the authoring refinement are implemented. Phase 5 is complete and re-frozen; Phase 6 is next and has not started. See [ROADMAP.md](ROADMAP.md).

| Phase | Work | Status |
| --- | --- | --- |
| 2 | Document management | Complete (2026-10-06) |
| 3 | Document processing | Complete (2026-10-10) |
| 4 | Document classification | Complete (2026-10-12) |
| 4.5 | Document workspace UI | Complete (2026-10-12) |
| 5A | Registry, units, requirement engine, registry API | Implemented |
| 5B | Core engineering-model persistence | Implemented |
| 5C | Revision model inheritance and revision-level model metadata | Implemented |
| 5D | Canonical topology persistence | Implemented |
| 5E | Revision-scoped engineering-model APIs | Implemented |
| 5F | Basic Engineering Model workspace UI | Implemented |
| 5G | Hardening, regression, documentation | Implemented |
| 5 refinement | Authoring profiles, states and transactional editor | Implemented; Phase 5 re-frozen |
| 6 | Evidence, candidates, and structured extraction | Next; not started |
| 7 | Entity resolution | Not started |
| 8 | SLD and topology extraction | Not started |
| 9 | Reconciliation and conflict management | Not started |
| 10 | Deterministic engineering validation | Not started |
| 11 | Engineer review, verification, and audit | Not started |
| 12 | Model visualization | Not started |
| 13 | Study-tool integration, automation, and reporting | Not started |

Authentication, real user identity, project authorization, and actor-backed audit records are not implemented through Phase 5G. They are a hard prerequisite/subphase for Phase 11 completion and must be pulled forward if shared/multi-user deployment is needed earlier. Existing actor UUIDs remain nullable; they are not a substitute for trustworthy audit identity.

ETAP / SKM / EasyPower adapters, study automation, results ingestion, and reporting are planned for Phase 13. Protection/settings and operating/study configurations require post-core-Phase-5 design gates before extraction/integration depends on them. None of this is implemented.

## Technical debt

Record here so later phases do not inherit accidental behavior.

- **Constraint-specific IntegrityError mapping.** *Resolved in PR-03.* Writes go through `integrity_guard` in `db_errors.py`, which maps `exc.orig.diag.constraint_name` to a domain error. Known names today: `uq_projects_project_number` → `DuplicateProjectNumber`; `uq_project_revisions_project_id_identifier` → `DuplicateRevisionIdentifier`; `uq_project_revisions_one_active` → `RevisionNotActivatable`. Anything else becomes `UnexpectedIntegrityError` (JSON 500, code `unexpected_integrity_error`) and is logged with the constraint name and SQLSTATE only. PR-07 and PR-09 extend the same mapping.
- **Integration tests write to the configured database and never clean up.** The existing `integration` tests insert uniquely named projects into whatever `DATABASE_URL` points at. Running them against a dev database pollutes it. Use a throwaway database (see [DEVELOPMENT.md](DEVELOPMENT.md)); consider a dedicated test database fixture later.
- **No recovery for a stale `RUNNING` processing run.** The Celery soft limit (600s) marks the run `FAILED` with `PROCESSING_TIMEOUT`. A worker crash, a dead host, or the hard kill (660s) does not. The row stays `RUNNING`. `ensure` and backfill leave a `RUNNING` run alone, retry rejects it, and the unique live-run index blocks another attempt, so the workspace shows Processing with no Retry until the row is edited. A live worker can still be inside the hard limit, so `ensure` should keep ignoring a fresh `RUNNING` run. Recovery belongs in a separate step: once `started_at` is older than the hard limit, mark that run `FAILED` with `PROCESSING_TIMEOUT` and leave its rows in place. The existing retry can start the next attempt.
- **No recovery for a stale `RUNNING` classification run.** The same gap exists for classification. A worker killed without the soft time limit leaves the run `RUNNING`. `ensure` returns it. Backfill does not adopt it. Page classification is all-or-nothing: a failed batch fails the run, and retry repeats the work.
- **Stale spec path references (fixed 2026-10-01).** Docs referred to `cursor/PHASE1_SPECS.txt`; the tracked file is `cursor/phase1_specs.txt`. The mismatched case works on macOS but breaks on case-sensitive filesystems.
