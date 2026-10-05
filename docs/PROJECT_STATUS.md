# Project status

Living status of PowerForge phases. Update this file when a phase is specified, started, or completed. Do not treat chat history as the source of truth.

**Current implemented phase:** 1  
**In progress:** 2 (document management) — specified, implementation not started  
**Next after that:** 3 (document processing)

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
- PostgreSQL tables `projects` and `project_revisions` (Alembic `0002_projects_and_revisions`, `0003_status_before_archive`); Phase 2 migration `0004_documents_and_lineage` adds revision lineage, `documents`, and `revision_documents`
- REST API under `/api/projects` and nested revisions (create/list/get/patch + pause/resume/cancel/archive/unarchive + activate)
- Web UI: `/` project list, `/projects/new`, `/projects/[id]`, revision placeholder, `/status` stack health
- Backend and frontend tests covering lifecycle, uniqueness, and concurrent activate

## Phase 2 — Document management, immutable storage, revision inheritance

**Status:** In progress. Specified and documented (2026-10-01); **implementation has not started**. Do not mark this phase complete until every item in the spec's definition of done is met and the checklist below is checked.

Implementation spec: `cursor/phase2_specs.txt` (version 2)  
Delivery plan: [PHASE2_PR_PLAN.md](PHASE2_PR_PLAN.md)  
Decisions: [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md) (Proposed)

Scope:

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

### Delivery plan

Phase 2 is delivered as 16 sequenced pull requests (PR-00 to PR-15) with scope, tests, acceptance criteria, and spec traceability defined in [PHASE2_PR_PLAN.md](PHASE2_PR_PLAN.md). That document's tracker table is the single source for per-PR progress; update it when a PR merges.

| Stage | PRs |
| --- | --- |
| Housekeeping and docs | PR-00, PR-01 |
| Foundations (domain, error mapping, schema, storage, validation) | PR-02 to PR-06 |
| Revision lineage and inheritance | PR-07 |
| Document API (upload/list/get, mutations, download) | PR-08 to PR-10 |
| Frontend (Create Revision, workspace, upload, actions) | PR-11 to PR-14 |
| Hardening and completion | PR-15 |

PRs merged so far: PR-00 and PR-01 (commits `9a42b3b`, `3289937`); PR-02 lands document-domain vocabulary and pure validation; PR-03 lands constraint-name IntegrityError mapping; PR-04 adds migration `0004` and the ORM models (no service or API behavior uses them yet, rebuild the API image after pulling); PR-05 adds the new storage and upload settings, `extra` fields in JSON logs, and the `ObjectStorage` abstraction (in-memory fake and boto3 S3/MinIO implementation) with a non-fatal startup bucket check, and CI now runs MinIO; PR-06 adds streaming upload ingestion (size bound, SHA-256, spooled temp file) and the Pillow-based `FileInspector` (nothing calls them yet, rebuild the API image for `Pillow`); PR-07 records revision lineage (`based_on_revision_id`) and makes new revisions inherit the base revision's included documents in one transaction (there are no documents yet, so nothing is visible beyond the new response fields). Phase 2 is complete only when PR-15 has merged and every item in the spec's definition of done (section 36) is demonstrably met.

### Intentional deviations and debt expected from Phase 2

Record the final list here when the phase completes. Known in advance:

- Orphaned storage objects (crash between upload and commit; uploaded-then-removed documents); no garbage collection
- PDF validation is header-only; images are validated structurally, not fully decoded (a JPEG or TIFF with a valid header but truncated body is accepted; only PNG structure is walked by `verify()`)
- No pagination on document lists
- No document-level audit trail beyond added/removed fields; `uploaded_by`/`added_by`/`removed_by` stay null until authentication exists
- Phase 1 still allows editing a superseded revision's identifier and description (only the document package is frozen)
- `RevisionDocument.project_id` is intentionally denormalized to enable database-level same-project enforcement

## Next — Phase 3: Document processing

Not started and out of scope for Phase 2. Conceptually: PDF/image preprocessing, PDF page generation, page rendering, image normalization, OCR-ready artifacts, and page metadata, built on top of the immutable `Document` produced in Phase 2 and run by `services/document-worker`.

## Later phases

| Phase | Work | Status |
| --- | --- | --- |
| 2 | Document management | In progress (specified, not implemented) |
| 3 | Document processing | Not started |
| 4 | Document classification | Not started |
| 5 | Engineering model persistence | Not started |
| 6–13 | Extraction through export | Not started |

Authentication, a users table, and project-level access control are required by the product spec and are **not** part of Phase 0, Phase 1, or Phase 2. `created_by` (and Phase 2's `uploaded_by`/`added_by`/`removed_by`) remain nullable until then.

ETAP / SKM / EasyPower integration is not part of these phases.

## Technical debt

Record here so later phases do not inherit accidental behavior.

- **Constraint-specific IntegrityError mapping.** *Resolved in PR-03.* Writes go through `integrity_guard` in `db_errors.py`, which maps `exc.orig.diag.constraint_name` to a domain error. Known names today: `uq_projects_project_number` → `DuplicateProjectNumber`; `uq_project_revisions_project_id_identifier` → `DuplicateRevisionIdentifier`; `uq_project_revisions_one_active` → `RevisionNotActivatable`. Anything else becomes `UnexpectedIntegrityError` (JSON 500, code `unexpected_integrity_error`) and is logged with the constraint name and SQLSTATE only. PR-07 and PR-09 extend the same mapping.
- **Integration tests write to the configured database and never clean up.** The existing `integration` tests insert uniquely named projects into whatever `DATABASE_URL` points at. Running them against a dev database pollutes it. Use a throwaway database (see [DEVELOPMENT.md](DEVELOPMENT.md)); consider a dedicated test database fixture later.
- **Stale spec path references (fixed 2026-10-01).** Docs referred to `cursor/PHASE1_SPECS.txt`; the tracked file is `cursor/phase1_specs.txt`. The mismatched case works on macOS but breaks on case-sensitive filesystems.
