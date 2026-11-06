# Project status

Living status of PowerForge phases. Update this file when a phase is specified, started, or completed. Do not treat chat history as the source of truth.

**Current implemented phase:** Phase 6C — Engineering equipment/attribute extraction and evaluation tooling (M1–M6). Live-model quality remains unverified. Phase 5 remains frozen.

**UI redesign:** UI-A, UI-B and UI-C implemented — design system/app shell, reactive data/interaction states, and Projects/Revisions workspaces. Next UI milestone: UI-D. See [UI_A_HANDOFF.md](UI_A_HANDOFF.md), [UI_B_HANDOFF.md](UI_B_HANDOFF.md), and [UI_C_HANDOFF.md](UI_C_HANDOFF.md).

UI-C visual fidelity rework follows the approved Projects/Revisions HTML layouts, including register toolbars, unified project details/revision activity, revision summary/workspaces/information, creation guidance rails, and edit sheets. Existing API/query/lifecycle safeguards remain. Validation: 291 frontend tests; desktop/mobile browser comparison; lint, TypeScript and production build. Necessary real-data and accessibility deviations are documented in the UI-C handoff.

**Current engineering work:** Phase 6E M1 pure spatial source/geometry/offset/binding contracts and typed OCR protocol implemented for review. All 92 focused tests pass with no skips; provenance/AI wheels reproduce new identities and accepted v1–v4 wires/resources plus both frozen 6C/6D reports. Actual OCR, durable enrichment and enhanced extraction remain M2–M5. See [PHASE6E_PLAN.md](PHASE6E_PLAN.md) and [PHASE6E_M1_HANDOFF.md](PHASE6E_M1_HANDOFF.md). Phase 6C/6D remain delivered with live-model quality unverified.

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

## Phase 6A — Evidence and extraction persistence foundation

**Status:** Implemented (2026-11-02). Phase 6 as a whole is not complete.

Authority: [approved Phase 6 specification](specs/phase-6-evidence-structured-extraction.md), [ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md) and [implementation prompt](prompts/phase-6a-prompt.md). Plan: [PHASE6A_PLAN.md](PHASE6A_PLAN.md). Exact boundaries, migration, contracts, commands, results and 6B handoff: [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md).

Migration `0011_extraction_persistence` adds extraction runs, append-only work-unit attempts, evidence, source-local groups, versioned structured tables, typed candidates, many-to-many citations and technical call telemetry. Composite ownership, pinned completed processing/artifacts, active identity/attempt uniqueness, immutable output and atomic successful publication protect provenance/history. Tagless and isolated observations remain valid; raw/unmapped/invalid claims and exact Decimal/INTEGER/BOOLEAN semantics are preserved. Six revision-document GET routes provide included-document/inherited/read-only access, deterministic pagination/filtering, effective successful-unit coverage and signed historical artifact references. No canonical equipment/attribute/topology/revision writes or extraction POST operations were added. Revision-wide frequency and phase count remain manual-only.

Validation after review corrections: **1,114 backend tests passed with live PostgreSQL/MinIO, no skips**, including **48 focused Phase 6A tests** and fresh/0010-upgrade/downgrade/re-upgrade migration checks. Standalone offline contract/OpenAPI suite: **16 passed**. Ruff, changed-file formatting, whitespace, editable package builds, dependency and OpenAPI checks passed. All test writes used disposable PostgreSQL/MinIO with temporary storage; the normal development database/volumes were untouched. No frontend changes or frontend/browser checks. The pre-existing remote CI MinIO image-availability issue remains separate; no remote CI pass is claimed.

Review hardening before 6B adds forward migration `0012_extraction_terminal_guard`: terminal runs cannot retain required or optional pending/running attempts. Text-offset publication verifies/counts the exact pinned UTF-8 artifact through ObjectStorage instead of mutable page metadata. The original migration is preserved. Forty-eight focused checks and all 1,114 backend tests pass, including concurrent transitions, historical-artifact bounds and 0012 fresh/upgrade/downgrade verification; exact results are recorded in the handoff.

The subsequent 6B delivery is recorded below. Production 6C extraction, 6D table interpretation, 6E OCR/layout, 6F extraction/evidence UI/evaluation and 6G hardening/freeze remain unimplemented. Historical accepted ADRs and Phase 5 handoffs were preserved.

## Phase 6B — Extraction orchestration and provider infrastructure

**Status:** Implemented (2026-11-03). Production engineering extraction remains deferred to 6C–6E; Phase 6 as a whole is not complete.

Authority: [Phase 6B prompt](prompts/phase-6b-prompt.md), approved Phase 6 specification and ADR-008. Technical design: [PHASE6B_PLAN.md](PHASE6B_PLAN.md). Contracts, setup, actual validation, reliability guarantees and 6C handoff: [PHASE6B_HANDOFF.md](PHASE6B_HANDOFF.md).

Persistent run planning, equivalent active/completed reuse, intentional re-extraction, versioned infrastructure profiles, durable Celery delivery, token-fenced claims, bounded heartbeat leases, crash/restart recovery, append-only retries, cooperative cancellation and safe usage/call-budget reporting are operational. Migration `0013_extraction_execution` preserves original 6A migrations and terminal/output immutability. Three POST actions and profile discovery extend the six existing GETs under INCLUDED revision-document membership, including inherited/read-only revisions. External OpenAI execution requires explicit enablement and worker credentials; fake probes are clearly synthetic. Production equipment/attribute/table/OCR interpretation, automatic extraction and frontend extraction UI are not implemented.

Review corrections distinguish temporary storage access/streaming failures (`SOURCE_UNAVAILABLE`, bounded automatic retry) from permanent invalid/missing source data. Recovery batches prioritize expired leases instead of repeatedly scanning healthy older active runs; settled parents still aggregate normally. Successful sibling outputs, retry ancestry, original budgets and call telemetry remain intact. No schema migration was needed for these corrections.

Validation: **1,184 backend tests passed, no skips**, with six existing dependency warnings, including **70 new Phase 6B cases** (27 for the storage/recovery review corrections). This includes actual disposable PostgreSQL/Redis/MinIO and Celery worker/beat subprocesses, persisted-but-undelivered recovery, signed source access and recovery after killing/restarting a worker. Fresh and 0012 upgrade/downgrade/re-upgrade migrations passed. Mocked OpenAI adapter tests made no real calls. Lint, changed-file formatting, dependency/package builds, Compose configuration, OpenAPI and whitespace checks passed. Normal development data/volumes were not used for test writes. No frontend changes/checks or live-provider smoke test.

## Phase 6C — Equipment and attribute extraction (M1–M6)

**Status:** M1–M6 implemented (2026-11-04); production-model accuracy remains unverified. Final delivery: [PHASE6C_HANDOFF.md](PHASE6C_HANDOFF.md). Plan: [PHASE6C_PLAN.md](PHASE6C_PLAN.md). Exact delivered contracts, identities, bounds and checks: [M1 handoff](PHASE6C_M1_HANDOFF.md), [M2 handoff](PHASE6C_M2_HANDOFF.md), [M3 handoff](PHASE6C_M3_HANDOFF.md), [M4 handoff](PHASE6C_M4_HANDOFF.md), [M5 handoff](PHASE6C_M5_HANDOFF.md).

M1 adds offline strict observation schemas for equipment/attributes and native/visual source roles, generated metadata for all 20 registry types/296 attributes, a small scoped terminology policy, versioned prompt resources and reproducible stage hashes. Tagged/tagless/unknown equipment, isolated claims, exact raw decimal/integer strings and ambiguity are representable. Registry/probe schemas, prompt hashes and profile wire identities remain unchanged.

Validation: **40 new offline tests passed; 160 focused/regression tests passed in total**, with five existing dependency warnings in the combined run. This covers independent approved-registry comparison, semantic unit metadata, bounded shapes/references/overflow, raw precision, resource hashes, pure imports and probe compatibility. The extraction wheel builds and contains all four prompt resources; direct wheel import/rendering passed. Ruff, changed-file formatting, dependency and whitespace checks passed. No database, frontend, worker or live-model run was needed or performed for M1.

No deterministic mapping/normalization, source grounding, Evidence/Candidate publication, production profiles or execution integration is delivered by M1. Its curated fixture responses include future expectations, not model accuracy measurements.

M2 adds a versioned pure interpreter that independently resolves source meanings against registry metadata and scoped terminology, checks proposed labels/values/units/types for conflicts, and delegates normalization to registry-v1. Raw observations survive meaningful ambiguity or normalization failure; fabricated source fields are rejected separately. Original precision, explicit false, isolated observations and competing values are retained without canonical writes. The interpreter requires admitted local source/equipment passages from M3; it does not establish artifact provenance or equipment association itself.

M2 validation after review: **110 M2 tests passed; 270 focused/regression tests passed in total**, with five existing dependency warnings. This includes all 20 explicit registry type names, priority-family semantic fixtures, wrong-but-valid key proposals, source-field mismatches, units/header conflicts, percent/per-unit separation, exact Decimal/INTEGER/BOOLEAN behavior, enum uncertainty, storage bounds, rule hashes and import isolation. Eight review regressions ensure nonunit parenthetical qualifiers remain unresolved instead of becoming mapped, while valid unit/full-registry labels retain their meaning. Initial M2 wheel import/rule-identity reproduction passed; final Ruff, formatting and whitespace checks passed. No database, worker, frontend or live-model test was performed for this pure offline layer. M3 grounding/grouping delivery is recorded below; no production-model accuracy is claimed.

M3 adds verified pinned artifact loading, verbatim/Unicode text grounding, explicit page-level visual grounding, conservative source-local groups and conversion to atomic 6A output. Recognition context comes from completed same-run/page outputs; model references alone do not establish native associations. Source blocks, repeated phrases, qualified fragments, explicit AF/AT clauses, shared citations and false/large typed values are covered. Bounded rejection/detachment counts commit inside the publication savepoint; read APIs expose grounding precision. No schema migration, canonical writes or production stage/provider scheduling was added.

M3 validation: **1,365 backend tests passed, no skips**, including **31 new M3 cases**, with six existing dependency warnings in 155.44 seconds. Disposable PostgreSQL/Redis/MinIO tests verify publication rollback/ownership, historical artifacts, immutable counts, exact HTTP values and source markers; the full suite also retains existing migration/worker/probe regressions. Wheel build/direct imports and rule identity, lint, formatting, dependencies and whitespace checks passed. No paid/live-model call or frontend/browser test was performed. M4 dependency execution and M5 production OpenAI/profile wiring remain pending; extraction accuracy is unmeasured.

M3 review validation: **1,375 backend tests passed, no skips**, including **41 M3 cases**, with six existing dependency warnings in 190.23 seconds. Equipment tags/names are checked against the original observed expression before full-line interpretation. Colon-line continuation requires a registry/terminology attribute label; unknown labels and missed tag-prefixed equipment headers disable block association. Ten added cases cover these corrections and valid continuations. The grounding fingerprint is refreshed before production profiles are enabled; M1/M2 and registry-v1 remain unchanged. See the [M3 review record](PHASE6C_M3_HANDOFF.md#m3-review-corrections).

M4 adds two-stage page plans, committed-prerequisite dispatch/claim gates, blocked failure settlement, dependency-aware retries/read flags and expiry-first recovery past healthy runs. The v2 profile reader pins stage/interpretation/grounding/runtime identities and multimodal limits while retaining byte-identical v1 profiles. Selected-schema execution performs verified source I/O and model I/O outside metadata transactions and uses existing atomic publication/fences. Explicit synthetic engineering profiles exercise this path; M5 production OpenAI delivery is recorded below and evaluation remains M6. See [PHASE6C_M4_HANDOFF.md](PHASE6C_M4_HANDOFF.md).

M4 validation: **1,413 backend tests passed, no skips**, including **38 new M4 cases**, with six existing dependency warnings in 208.86 seconds. Fresh migration, AI/extraction wheel builds/direct imports, runtime/profile/legacy identities, lint, formatting, dependencies and whitespace checks passed. Disposable PostgreSQL/Redis/MinIO were used and removed; normal development data were untouched. No live provider or frontend/browser test was performed. M5 delivery is recorded below; measured model quality remains M6.

M5 adds opt-in production hybrid/text OpenAI profiles, named untrusted source/upstream input envelopes, selected-schema SDK parsing, explicit production limits/effort/detail and safe usage/error handling through the existing execution path. SDK retries remain disabled and each attempt makes at most one call. Discovery identifies production separately from fake/probe execution; the default remains fake and external processing remains off. Historical v1/v2 identities are preserved with retained resources; production pins a v3 profile/v2 runtime and versioned adapter input contract. See [PHASE6C_M5_HANDOFF.md](PHASE6C_M5_HANDOFF.md).

M5 validation: **1,445 backend tests passed, no skips**, including **32 new M5 cases**, with six existing dependency warnings in 231.07 seconds. Actual OpenAI SDK transport mocks, real Celery/beat/Redis/PostgreSQL/MinIO execution, production profile/opt-in controls, source signing, transient/manual retry and worker restart pass. Wheel builds/direct imports preserve v1/v2/v3 identities; lint, formatting, dependencies, whitespace and resolved Compose configuration pass. Tests use disposable infrastructure and no live paid calls; M6 model evaluation remains outstanding.

M6 adds 15 synthetic text/image/hybrid cases with 50 independent gold claims, versioned recorded replay and source-based one-to-one scoring with explicit denominators. The committed scripted baseline publishes 48 candidates: equipment precision 14/14, recall 14/16, attribute mapping 34/34, exact value/unit correctness 24/24, UNMAPPED retention 8/8 and false candidates 0/48. Two deliberate recognition challenges cost recall. These are converter checks, not model accuracy. A separately opt-in live runner checks approved source hashes for the entire batch and uses normal admission/publication with exactly two admissions and one attempt per stage per case. See the [corpus guide](../evals/extraction/README.md).

M6 validation: **1,487 backend tests passed, no skips**, including **42 M6 cases**, with six existing dependency warnings in 249.99 seconds. The four live-runner integration cases passed again after the final diagnostic-count reporting correction. Fresh migration to head 0013, extraction/worker wheel imports and exact replay, lint, formatting, dependencies and whitespace checks pass. Disposable PostgreSQL/Redis/MinIO were used and removed; normal development data were untouched. No frontend/browser tests or live paid provider calls were performed. The [final handoff](PHASE6C_HANDOFF.md) distinguishes all-registry architectural support, four-family fixtures and zero live-model evaluation coverage.

## Phase 6D — Tables and schedules (M1–M4)

M4 adds a separate offline table evaluator/CLI and 27 synthetic cases with 27 gold tables, 146 cells and 73 claims. Source occurrence/cell matching precedes meaning/value/association scoring. Failed cases remain in explicit denominators; native literal, visual-report and structural reliability stay separate. The processed-PDF pair exposes conservative native abstention without changing gold to fit converter output. All 100 new tests pass with no skips; the new extraction wheel reproduces its entrypoint, identities and complete report. Earlier verified full/integration/package/migration/API/dependency gates are carried forward per user instruction, not rerun. The frozen 6C evaluator/baseline and M1–M3 production resources are unchanged. No live calls or measured production accuracy. Actual results/limits: [PHASE6D_HANDOFF.md](PHASE6D_HANDOFF.md).

M3 adds opt-in v4 table production profiles, fixed page-stage execution, committed context, budgeted empty-table skips and production Responses integration through the existing coordinator/worker/API. Historical runtime inputs and active-run behavior remain compatible. Cross-profile summaries and paginated historical access remain intact. Final validation: **1,754 backend tests pass, no skips**, including **71 new M3 cases**, six existing warnings in **292.16 seconds**. Extraction/worker/API wheels reproduce new v4 and unchanged historical identities plus the exact 6C scripted report. Fresh migration, lint, formatting, dependency and whitespace checks pass. No paid model call was made. Historical M3 commands and limits: [PHASE6D_M3_HANDOFF.md](PHASE6D_M3_HANDOFF.md).

M2 delivery adds exact source admission, structured-cell interpretation, committed reconstruction loading, atomic publication reference hardening and honest table-cell API precision. M2 delivery/review validation follows. The broad backend regression passed 1,635 tests with no skips; after final adapter refinements the 178-test focused gate passed, including all 75 M2 cases. Final wheel imports reproduce unchanged M1/6C identities and the exact 6C scripted report. Full commands, timing and limits are recorded in [PHASE6D_M2_HANDOFF.md](PHASE6D_M2_HANDOFF.md). M2 review now rejects multi-tag ownership independently of model observation count and retains distinct conditional readings and association proposals. Its final review gate passes 409 tests with no skips, including 39 added regressions; historical M1/6C identities and exact replay remain unchanged. M2 introduced no production profile or live accuracy measurement; M3 execution delivery follows.

**M1 status:** implemented (2026-11-05); historical offline validation follows. At M1, 6D remained incomplete. Strict offline reconstruction/interpretation schemas preserve all four orientations, sparse/blank/unreadable cells, spans, headers, uncertainty and source-local aliases. Pure inspection/reference checks create no persistence entities and establish no source/semantic proof. Versioned prompts and identities reuse all-registry metadata without changing 6C resources. Table-only ownership and separate prose runs are approved; cross-profile latest-summary/history tests remain M3.

Validation: **79 M1 offline cases pass within 340 related passing tests**, including the entirely unreadable-value-cell review correction, with two integration cases explicitly deselected and six existing dependency warnings in 2.64 seconds. A 512-cell schedule's context is 98,355 bytes within the 128 KiB bound. Extraction wheel/direct imports reproduce new resources, unchanged v1/v2/v3 profile/runtime identities and the complete 6C scripted report. Lint, formatting, dependency and whitespace checks pass. No database/provider/worker/frontend test or live paid call was performed. M2 source grounding, registry interpretation and publication are delivered in the subsequent milestone below. See [PHASE6D_M1_HANDOFF.md](PHASE6D_M1_HANDOFF.md).

## Phase 6E — OCR/layout (M1 foundation)

**M1 implemented for review (2026-11-06).** New pure contracts preserve separate native/OCR representations, immutable producer/artifact/page identities, exact Unicode occurrences and conditional shared-origin mappings. Explicit crop/scale/mirror/quarter-turn transforms and token/native-primitive support can resolve geometry while structure remains UNRESOLVED and printed text is not independently verified. Typed positioned OCR requests/results preserve raw words, engine confidence and local usage without running an engine.

Validation: **92 focused tests pass, no skips or warnings, in 0.70 seconds**. Six authored contract fixtures, a 3,708,510-byte minimal 20,000-token body, independent UTF-8 overflow rejection, pure imports and 130 accepted file hashes are checked. Built provenance/AI wheels reproduce the new resources and accepted v1–v4 identities and both full 6C/6D reports. Lint/formatting/dependency/whitespace checks pass. No actual OCR/native adapter, migration, API/worker/frontend change, infrastructure integration or paid call occurred. Enrichment-before-extraction, coherent future 6F guidance, every-path purpose separation and observable eligibility remain the approved design; M2–M5 are pending. Full details: [PHASE6E_M1_HANDOFF.md](PHASE6E_M1_HANDOFF.md).

## Later phases

Phase 5A through 5G and the authoring refinement remain complete and frozen. Phase 6A/6B and 6C M1–M6 are implemented; live-model evaluation remains outstanding; 6D M1–M4 and 6E M1 are implemented for review; actual OCR/enhanced extraction in 6E M2–M5 and 6F–6G remain pending. See [ROADMAP.md](ROADMAP.md).

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
| 6A | Evidence and extraction persistence/read APIs | Implemented (2026-11-02) |
| 6B | Orchestration, provider infrastructure and execution reliability | Implemented (2026-11-03) |
| 6C | Engineering equipment/attribute extraction | M1–M6 implemented; live quality unverified |
| 6D–6G | Tables, OCR, UI/evaluation and hardening | 6D delivered; 6E M1 contracts implemented for review; actual OCR and M2–M5/6F–6G pending; live quality unmeasured |
| 6.5 | Spreadsheet ingestion after 6G and before 7 | Deferred; unimplemented |
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
