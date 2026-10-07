# Phase 2 — PR plan

How Phase 2 (document management, immutable storage, revision inheritance) is delivered: a sequence of small, reviewable pull requests. We work through them in order; each one is a self-contained unit that leaves `main` green.

- Specification: [`cursor/phase2_specs.txt`](../cursor/phase2_specs.txt) (version 2). Section references below (`§13`) point at it.
- Decisions: [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md)
- Phase status (source of truth for what is actually done): [PROJECT_STATUS.md](PROJECT_STATUS.md)

This file is the delivery plan. If a PR forces a change to the plan or the spec, update this file (and the spec) in that PR and say so in the PR description.

## Contents

1. [Working agreements](#1-working-agreements)
2. [PR overview and tracker](#2-pr-overview-and-tracker)
3. [Dependency graph](#3-dependency-graph)
4. [PR details](#4-pr-details)
5. [Traceability: spec to PR](#5-traceability-spec-to-pr)
6. [Open decisions](#6-open-decisions)
7. [Intermediate-state compatibility](#7-intermediate-state-compatibility)
8. [Risks](#8-risks)
9. [Coverage audit and intentional exclusions](#9-coverage-audit-and-intentional-exclusions)

---

## 1. Working agreements

### Per-PR rules

1. **One PR, one purpose.** Do not pull work forward from a later PR, and do not add Phase 3 or AI scaffolding "while we're here" (§4 non-goals).
2. **`main` stays green and runnable.** Every PR must pass the full gate below and must not leave the app in a state where a merged half-feature breaks Phase 1 behavior.
3. **Branch naming:** `phase2/pr-NN-short-name`. Commit messages: short imperative summary; body explains why.
4. **Tests ship with the code they cover**, not in a later PR. Each PR lists its required tests; a PR without them is not done.
5. **Docs ship with behavior.** When a PR changes behavior the Phase 2 docs describe, it corrects those docs in the same PR. Docs written ahead of implementation (PR-01) describe the target; each PR verifies its slice and fixes drift.
6. **Record deviations.** Anything that differs from the spec goes in the PR description under "Deviations" and in the spec/ADR if it is lasting.
7. **Do not commit** `apps/web/tsconfig.tsbuildinfo` changes (a tracked build artifact that `tsc` rewrites). Restore it with `git checkout -- apps/web/tsconfig.tsbuildinfo` before committing.

### Verification gate (run before opening and before merging)

```bash
source .venv/bin/activate
ruff check .
pytest                                         # unit tests; integration skipped

# Integration tests: ALWAYS use a throwaway database (they never clean up)
docker exec powerforge-postgres-1 psql -U powerforge -d postgres -c "CREATE DATABASE powerforge_test;"
export DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_test
alembic -c database/alembic.ini upgrade head
RUN_INTEGRATION=1 pytest
docker exec powerforge-postgres-1 psql -U powerforge -d postgres -c "DROP DATABASE powerforge_test;"
unset DATABASE_URL

# Web (any PR touching apps/web; cheap, so run always after PR-11)
cd apps/web && npm run lint && npm test && npx tsc --noEmit
git checkout -- tsconfig.tsbuildinfo
```

CI (`.github/workflows/ci.yml`) runs the same with `RUN_INTEGRATION=1` and `npm run build`. PRs that add real-MinIO tests also need a MinIO service in CI (PR-05).

### PR description template

```
## Summary
## Spec sections / ADR decisions covered
## Changes (files/modules)
## Tests added (and what they prove)
## Verification run (commands + results — only what was actually executed)
## Deviations from spec / plan
## Follow-ups / debt
```

### Sizing

XS < 50 lines, S < 300, M < 800, L > 800 (excluding generated code and lockfiles). Anything trending past L should be split.

---

## 2. PR overview and tracker

Update the checkbox and status when a PR merges; keep [PROJECT_STATUS.md](PROJECT_STATUS.md) work packages in sync.

| PR | Title | Area | Size | Depends on | Status |
| --- | --- | --- | --- | --- | --- |
| [PR-00](#pr-00--land-pending-phase-1-lock-fix) | Land pending Phase 1 lock fix | Backend | XS | — | [x] landed in `9a42b3b` (bundled with PR-01 content) |
| [PR-01](#pr-01--phase-2-specification-adr-and-documentation) | Phase 2 specification, ADR-004, docs, PR plan | Docs | S | — | [x] landed in `9a42b3b` / `3289937` |
| [PR-02](#pr-02--document-domain-vocabulary-and-pure-validation) | Document domain vocabulary and pure validation | Domain | S | — | [x] |
| [PR-03](#pr-03--constraint-name-integrityerror-mapping) | Constraint-name IntegrityError mapping | Backend | S | — | [x] |
| [PR-04](#pr-04--database-migration-0004-and-orm-models) | Migration `0004` and ORM models | DB | M | PR-02 | [x] |
| [PR-05](#pr-05--configuration-and-object-storage-abstraction) | Configuration and object-storage abstraction | Backend/Infra | M | PR-02 | [x] |
| [PR-06](#pr-06--file-ingestion-and-validation) | File ingestion and validation | Backend | M | PR-02, PR-05 | [x] |
| [PR-07](#pr-07--revision-lineage-and-document-inheritance) | Revision lineage and document inheritance | Backend | L | PR-03, PR-04 | [x] |
| [PR-08](#pr-08--document-upload-list-and-get) | Document upload, list, and get | Backend | L | PR-04, PR-05, PR-06, PR-07 | [x] |
| [PR-09](#pr-09--metadata-remove-restore-and-reuse) | Metadata, remove, restore, and reuse | Backend | M | PR-08 | [x] |
| [PR-10](#pr-10--download-urls-and-end-to-end-backend-workflow) | Download URLs and end-to-end backend workflow | Backend | M | PR-08, PR-09 | [x] |
| [PR-11](#pr-11--frontend-foundations-and-create-revision-ui) | Frontend foundations and Create Revision UI | Web | M | PR-07 | [x] |
| [PR-12](#pr-12--revision-documents-workspace-read-side) | Revision documents workspace (read side) | Web | M | PR-10, PR-11 | [x] |
| [PR-13](#pr-13--multi-file-upload-ui) | Multi-file upload UI | Web | M | PR-08, PR-12 | [x] |
| [PR-14](#pr-14--document-actions-ui) | Document actions UI | Web | M | PR-09, PR-12 | [x] |
| [PR-15](#pr-15--hardening-verification-and-phase-2-completion) | Hardening, verification, and Phase 2 completion | All | M | all | [x] |

---

## 3. Dependency graph

Each line reads "PR needs → these PRs merged first".

```
PR-00   needs  —                      (housekeeping; merge first)
PR-01   needs  —                      (housekeeping; merge first)

PR-02   needs  —
PR-03   needs  —
PR-04   needs  PR-02
PR-05   needs  PR-02
PR-06   needs  PR-02, PR-05
PR-07   needs  PR-03, PR-04
PR-08   needs  PR-04, PR-05, PR-06, PR-07
PR-09   needs  PR-08
PR-10   needs  PR-08, PR-09
PR-11   needs  PR-07
PR-12   needs  PR-10, PR-11
PR-13   needs  PR-08, PR-12
PR-14   needs  PR-09, PR-12
PR-15   needs  everything
```

```
Backend spine:   PR-02 ─► PR-04 ─► PR-07 ─► PR-08 ─► PR-09 ─► PR-10
                    └──► PR-05 ─► PR-06 ───────┘
                 PR-03 ────────────────┘ (into PR-07)

Frontend spine:  PR-07 ─► PR-11 ─► PR-12 ─┬─► PR-13
                              PR-10 ──────┘  └─► PR-14      then PR-15
```

Practical ordering (one engineer): 00 → 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 11 → 12 → 13 → 14 → 15.

If work is parallelized: PR-02, PR-03, PR-05 are independent; PR-11 can start as soon as PR-07 merges, in parallel with PR-08..PR-10; PR-13 and PR-14 are independent of each other.

---

## 4. PR details

### PR-00 — Land pending Phase 1 lock fix

**Status.** Done. These changes were committed to `main` in `9a42b3b`, in the same commit as the Phase 2 documentation (PR-01), rather than as a separate PR. Nothing further to do; the description below records what it contained.

**Goal.** Commit the two uncommitted Phase 1 changes found at baseline so the Phase 2 diff is clean.

**Depends on.** Nothing.

**Scope.**
- `services/api/src/powerforge_api/services/revision_service.py`: `create_revision` takes the project row lock (`for_update=data.activate`) so create-with-activate serializes with `activate_revision`.
- `tests/test_projects_api.py`: the matching concurrency test (create + activate leaves one ACTIVE).

**Out of scope.** Any Phase 2 behavior.

**Acceptance.** Full gate passes (baseline recorded 2026-10-01: ruff clean, 23 passed/16 skipped, 39 passed with integration). No other files change.

**Size.** XS.

---

### PR-01 — Phase 2 specification, ADR, and documentation

**Status.** Done. Spec, ADR-004, Phase 2 documentation, this plan, and the links from `README.md` and `docs/PROJECT_STATUS.md` are on `main` (`9a42b3b`, `3289937`).

**Goal.** Land the written design before code: spec v2, ADR-004 (Proposed), the Phase 2 doc updates, and this plan.

**Depends on.** Nothing (can merge alongside PR-00).

**Scope.**
- New: `cursor/phase2_specs.txt`, `decisions/ADR-004-document-storage-and-revision-inheritance.md`, `docs/PHASE2_PR_PLAN.md`.
- Updated: `README.md`, `docs/PROJECT_STATUS.md`, `docs/ARCHITECTURE.md`, `docs/DOCUMENT_PIPELINE.md`, `docs/PROVENANCE.md`, `docs/DEVELOPMENT.md`, `docs/PHASE0_HANDOFF.md`, `decisions/ADR-003-project-revision-model.md`, `cursor/specification.txt` (spec-path case fix `PHASE1_SPECS.txt` → `phase1_specs.txt`).
- `docs/PROJECT_STATUS.md` links to this plan.

**Out of scope.** Code, config, `.env.example`, `docker-compose.yml`.

**Acceptance.**
- All relative links resolve (check manually or with a link checker).
- No statement claims Phase 2 is implemented.
- `git diff` contains only documentation (plus the case-only reference fix).

**Size.** S (documentation only).

---

### PR-02 — Document domain vocabulary and pure validation

**Goal.** Extend the existing `packages/document-model` with everything the rest of Phase 2 needs that is pure and dependency-free. (§9, §11, §13, §22)

**Depends on.** Nothing.

**Scope** (`packages/document-model/src/powerforge_document_model/`):
- `enums.py`
  - Add `OTHER` to `DocumentClassification` immediately before `UNKNOWN` (keep `UNKNOWN` as the default and last member; do not rename the enum or shuffle members — order is the future PostgreSQL enum label order).
  - Add `DocumentOrigin` (`UPLOADED`, `INHERITED`), `RevisionDocumentStatus` (`INCLUDED`, `REMOVED`), and `FileFormat` (`pdf`, `png`, `jpeg`, `tiff`).
- `errors.py`: `DocumentValidationError` (`ValueError` subclass), `InvalidFilename`, `UnsupportedExtension`. PR-06 maps these to API exceptions (D3).
- `validation.py` (pure, no Pillow/SQLAlchemy/FastAPI):
  - `SUPPORTED_FORMATS` and `MIME_TYPES` (immutable)
  - `normalize_extension(filename)` (lowercase, leading dot; only the final extension counts; `""` for missing, trailing-dot, or dotfile)
  - `sanitize_filename(raw)` (basename only; strips `/`, `\`, drive prefixes, control characters, and bidi override/isolate characters; trims; truncates the stem so the total is at most 255 characters while keeping the final extension; rejects empty / `.` / `..`)
  - `looks_like_pdf(header: bytes)` (full `%PDF-` marker within first 1024 bytes)
  - `format_matches_extension(detected_format, extension)`
- `storage_key.py`: `build_storage_key(project_id: UUID, document_id: UUID, extension)` → `projects/{project}/documents/{document}/original{ext}`; rejects extensions outside the allow-list.
- Update `__init__.py` exports and the package docstring.

**Out of scope.** Pillow inspection (PR-06), any API exception types (they live in `powerforge_api`), DB, storage.

**Tests** (`tests/test_document_domain.py`, unit, no DB):
- enum values are stable strings; `OTHER` before `UNKNOWN`; original 15 values unchanged.
- `sanitize_filename`: path traversal, Windows paths, control and bidi characters, truncation keeping the extension, empty/whitespace/dot names, unicode names preserved.
- `normalize_extension`: `.PDF`, `.JpEg`, `.tif`; double extension (`a.pdf.exe` → `.exe`); no extension; trailing dot; dotfile.
- `looks_like_pdf`: header at offset 0 and 1019 (true), 1020 (false); absent; empty.
- extension/format agreement matrix (every allowed pair true; mismatches false).
- `build_storage_key`: exact format; contains no filename, revision, or classification input; unsupported extensions rejected.
- purity guard: no forbidden imports; `dependencies = []`.

**Acceptance.** Package still has zero third-party dependencies; `ruff` clean; no import of SQLAlchemy/FastAPI/boto3/Pillow anywhere in the package.

**Size.** S.

---

### PR-03 — Constraint-name IntegrityError mapping

**Goal.** Fix Phase 1 debt first, so every later constraint-related failure surfaces correctly. (§23, [PROJECT_STATUS](PROJECT_STATUS.md) technical debt)

**Depends on.** Nothing. Deliberately before the migration so it is reviewed on its own.

**Scope** (`services/api/src/powerforge_api/`):
- New `db_errors.py`: `constraint_name(exc) -> str | None` (reads `exc.orig.diag.constraint_name`, tolerant of missing attributes), `translate_integrity_error`, and `integrity_guard`.
- `UnexpectedIntegrityError` (`ProjectError`, code `unexpected_integrity_error`); `_http_for` maps it to JSON 500.
- `services/project_service.py`: `create_project` maps `uq_projects_project_number` → `DuplicateProjectNumber`.
- `services/revision_service.py`: create/update/activate map
  - `uq_project_revisions_project_id_identifier` → `DuplicateRevisionIdentifier`
  - `uq_project_revisions_one_active` → `RevisionNotActivatable` (D1, decided)
  - anything else → `UnexpectedIntegrityError` (logged at error with constraint name and SQLSTATE only; never mislabelled as a duplicate).

**Out of scope.** New Phase 2 constraints (added in the PRs that introduce them, PR-07/08/09).

**Tests** (`tests/test_integrity_error_mapping.py`):
- unit: `constraint_name` with a real-shaped psycopg error and with objects lacking `diag`.
- unit: unknown/missing constraint → `UnexpectedIntegrityError`; log contains the constraint name and SQLSTATE, not user data.
- integration: real psycopg names for identifier unique, one-active partial unique index, and project FK; unknown-constraint POST → 500 `unexpected_integrity_error`; one-active violation → 409 `revision_not_activatable`.
- existing duplicate-number, duplicate-identifier, and concurrent-activate tests still pass.

**Acceptance.** No blanket `except IntegrityError → Duplicate…` remains in the two services; existing Phase 1 behavior unchanged except D1; debt entry in `PROJECT_STATUS.md` updated to "resolved".

**Size.** S.

---

### PR-04 — Database migration 0004 and ORM models

**Goal.** Create the Phase 2 schema, with database-level same-project integrity. (§5, §7, §8, §24, ADR-004 #21)

**Depends on.** PR-02 (enums).

**Scope.**
- `database/migrations/0004_documents_and_lineage.py` (single reversible migration; never edit 0001–0003):
  - `project_revisions.based_on_revision_id` (nullable)
  - `uq_project_revisions_project_id_id` UNIQUE `(project_id, id)`
  - `fk_project_revisions_based_on` composite FK `(project_id, based_on_revision_id)` → `project_revisions (project_id, id)`; `ck_project_revisions_based_on_not_self`
  - PostgreSQL enums `document_classification`, `document_origin`, `revision_document_status` (created explicitly; ORM uses `create_type=False` + `values_callable`, matching existing style)
  - `documents` per §7: columns, `uq_documents_storage_key`, `uq_documents_project_id_id`, `ck_documents_size_positive`, indexes on `project_id` and `(project_id, sha256)`
  - `revision_documents` per §8: columns incl. denormalized `project_id`, `uq_revision_documents_revision_id_document_id`, the three composite FKs, the three CHECKs, indexes `revision_id`, `document_id`, `(revision_id, status)`, `(revision_id, document_type)`
  - no `ON DELETE CASCADE`
  - `downgrade()` removes everything in reverse (tables, enums, constraints, column)
- `services/api/src/powerforge_api/models.py`: `Document`, `RevisionDocument`, `ProjectRevision.based_on_revision_id`, enum declarations, relationships (no behavior).
- Update `powerforge-document-model` dependency in `services/api/pyproject.toml` (enums come from the domain package).

**Out of scope.** Any service/API behavior using the tables; revision schema changes (PR-07).

**Tests.**
- `tests/test_migration_0004.py` (integration, uses a scratch database it creates/drops or the throwaway DB):
  - upgrade on empty DB reaches `0004`; upgrade from `0003` with existing projects/revisions preserves them with `based_on_revision_id IS NULL`
  - downgrade to `0003` succeeds and re-upgrade succeeds
- `tests/test_phase2_constraints.py` (integration, raw ORM/SQL inserts):
  - composite FK rejects a base revision from another project
  - `ck_..._based_on_not_self` rejects self-reference
  - duplicate `(revision_id, document_id)` rejected
  - `RevisionDocument` rejects a `Document` from another project; rejects `inherited_from_revision_id` from another project; rejects revision/document project mismatch
  - CHECKs: origin ↔ `inherited_from_revision_id`; status ↔ `removed_at`; `inherited_from <> revision_id`; `size_bytes > 0`
  - `storage_key` uniqueness; `sha256` is **not** unique (two documents, same hash, both insert)
  - nullable `based_on_revision_id` / `inherited_from_revision_id` insert fine (MATCH SIMPLE)

**Implementation notes (as landed).**
- Enum labels in the migration are hard-coded (a migration must not change when the Python enum later changes); `tests/test_phase2_models.py` and `tests/test_migration_0004.py` assert they equal the Python enums.
- `downgrade()` is destructive for Phase 2 data (drops `documents` and `revision_documents`); it is meant for development databases.
- `RevisionDocument.document` and `.revision` are read-only (`viewonly`) relationships over the composite keys; writes go through the scalar columns.
- `tests/test_migration_0004.py` runs Alembic in a subprocess against a scratch database it creates and drops. `tests/test_phase2_constraints.py` rolls back its transaction, leaving no rows behind.

**Acceptance.** `alembic upgrade head` clean on fresh DB and on a `0003` DB with data; downgrade works; all Phase 1 tests still pass (the new column is nullable and unused).

**Size.** M.

---

### PR-05 — Configuration and object-storage abstraction

**Goal.** Provide settings and the storage seam, with a fake for tests and a boto3 implementation for MinIO/S3. (§10, §11 usage, §29, §34/security)

**Depends on.** PR-02 (storage-key builder).

**Scope.**
- `packages/shared/src/powerforge_shared/config.py`: add `s3_public_endpoint_url` (optional, falls back to `s3_endpoint_url`), `s3_signed_url_expires_seconds=900`, `max_upload_bytes=262_144_000`, `max_image_pixels=600_000_000`.
- `packages/shared/src/powerforge_shared/logging.py`: `JsonFormatter` includes `extra` fields (needed for structured ids in §28; currently only `message` is emitted). Never log secrets or URLs.
- `services/api/src/powerforge_api/storage/`:
  - `base.py`: `ObjectStorage` Protocol — `ensure_bucket()`, `put(key, fileobj, size, content_type)` (never overwrites), `get(key)`, `exists(key)`, `delete(key)`, `create_download_url(key, filename, content_type, disposition, expires_seconds)`; storage-layer exceptions (`ObjectAlreadyExists`, `StorageError`) that do not leak SDK messages.
  - `memory.py`: `InMemoryObjectStorage` with injectable failures (fail on put, fail on delete) and call recording (to assert "no copy occurred").
  - `s3.py`: `S3ObjectStorage` (boto3, SigV4, path-style); conditional put (`If-None-Match: *`) with an `exists()` fallback; a separate presign client built against `s3_public_endpoint_url`; `Content-Disposition` helper that emits ASCII `filename=` plus RFC 5987 `filename*=` for non-ASCII names; `ResponseContentType` from stored MIME.
  - `get_object_storage()` FastAPI dependency (overridable via `app.dependency_overrides`).
- `services/api/pyproject.toml`, `requirements-dev.txt`, CI: add `boto3`.
- `main.py` lifespan: call `ensure_bucket()` at startup; failure is logged and non-fatal ([D2](#6-open-decisions)).
- `.env.example`, `docker-compose.yml` (api service): new variables; `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000` for the api container. Verify `minio-init` sets **no** anonymous policy.
- CI: add a MinIO service so the `integration` storage test can run (or document skipping if not feasible, [D2](#6-open-decisions)).
- `tests/conftest.py`: fixtures — in-memory storage override, helper to build a project/revision.
- `pyproject.toml`: update the `integration` marker description (currently "require a running PostgreSQL instance") to also cover tests that need MinIO.

**Out of scope.** Upload logic, validation, DB writes, any router.

**Tests.**
- `tests/test_storage.py` — one **contract test suite** parametrized over the fake and (integration-marked) S3 implementation:
  - put/get round-trip; exists; delete; delete missing is a no-op or clear error (decide, document)
  - **put to an existing key is refused and original bytes preserved**
  - presigned URL contains the public host, expiry, and signs `response-content-disposition` and `response-content-type`
  - non-ASCII filename Content-Disposition encoding
- `tests/test_settings.py`: defaults and env overrides for the new settings; public endpoint falls back correctly.
- Integration (`RUN_INTEGRATION=1`, MinIO running): real put/get/exists/delete + fetch of a presigned URL returns the bytes; bucket is not anonymously readable (unsigned GET is 403).
- Logging: `extra` fields appear in JSON output; no secret fields.

**Implementation notes (as landed).**
- `/ready` is unchanged (decided: storage state shows only in the startup log and, later, as upload errors), so the web status dashboard is untouched.
- `delete` of a missing key is a no-op (D4). `get` of a missing key raises `ObjectNotFound`. Storage errors carry generic messages; only the S3 error code is logged, never SDK text, endpoints, or URLs.
- `put` does an `exists()` pre-check and also sends `If-None-Match: *`. `tests/test_storage.py` bypasses the pre-check once to prove the server itself returns 412 (MinIO `RELEASE.2025-09-07` does).
- The boto3 client sets `request_checksum_calculation` and `response_checksum_validation` to `when_required`, because boto3 1.36+ adds default checksums that S3-compatible servers may reject.
- The `Content-Disposition` builder lives in `storage/disposition.py` (pure, shared by the fake and S3 implementations) rather than in `s3.py`. `get_object_storage` is in `storage/factory.py`.
- `JsonFormatter` redacts top-level `extra` keys containing `secret`, `password`, `token`, `credential`, `signature`, `authorization`, `access_key`, or `url`.
- CI starts MinIO with a `docker run` step (service containers cannot pass `server /data`). The S3 contract cases skip locally when MinIO is unreachable and fail when `CI` is set. They use a scratch bucket that is emptied and deleted at the end of the session.
- The project/revision builder fixture from the original scope is deferred to PR-08, where it is first used. `tests/conftest.py` provides only the `object_storage` override fixture.
- D9 (throwaway-DB script) is skipped: the manual recipe and the self-cleaning migration test are enough.

**Acceptance.** App boots with and without MinIO reachable; compose stack starts and logs bucket status; no credentials in source beyond existing dev defaults; domain/service code imports only `ObjectStorage`, never boto3.

**Size.** M.

---

### PR-06 — File ingestion and validation

**Goal.** Everything that happens to an upload before the database is involved: stream, hash, bound, validate. (§13, §14, §23 error types)

**Depends on.** PR-02, PR-05 (settings).

**Scope** (`services/api/src/powerforge_api/`):
- `exceptions.py`: `UnsupportedDocumentType`, `InvalidFileContent`, `FileTooLarge` (subclass `ProjectError`, with `code`s).
- `services/file_ingest.py`: `ingest_upload(fileobj, filename, max_bytes)` — single streaming pass computing size and SHA-256 into a `SpooledTemporaryFile`; aborts as soon as `max_bytes` is exceeded (`FileTooLarge`); empty → `InvalidFileContent`; returns an object with the spooled file (rewound), size, sha256 hex, sanitized filename, normalized extension.
- `services/file_inspector.py`: `FileInspector.inspect(spooled_file, extension)` — PDF via `looks_like_pdf`; images via Pillow `Image.open` + `verify()`; reads dimensions from the header and rejects above `max_image_pixels` **before any decode**; catches `DecompressionBombError`, `UnidentifiedImageError`, truncated/invalid data → `InvalidFileContent`; enforces extension/format agreement; returns detected format and derived MIME. Multi-page TIFF accepted without inspecting pages. Never leaves the file position undefined.
- `services/api/pyproject.toml`, `requirements-dev.txt`, CI: add `Pillow`.

**Out of scope.** Multipart handling and routes (PR-08), storage `put`, DB.

**Tests** (`tests/test_file_validation.py`, unit; build PNG/JPEG/TIFF bytes with Pillow in-test):
- valid PDF, PNG, JPEG (`.jpg` and `.jpeg`), TIFF (`.tif` and `.tiff`) accepted; MIME derived from content
- unsupported extension; executable bytes renamed `.pdf`; HTML renamed `.png`; truncated image
- extension/content mismatch (JPEG named `.png`, PNG named `.pdf`)
- empty file; whitespace-only
- oversize rejected **during streaming** (use a generator/stream that would exceed memory; assert it stops early and memory is bounded — e.g. count bytes read)
- pixel cap exceeded rejected from header (craft a large-dimension header cheaply); decompression-bomb error mapped
- SHA-256 equals `hashlib.sha256(data)` on multi-chunk input; size equals bytes; file rewound for the caller
- filename sanitization applied; storage key never receives the filename
- browser-supplied content type is not an input to any decision

**Implementation notes (as landed).**
- `ingest_upload` checks the filename and extension before reading any of the body, so unsupported types cost nothing. `InvalidFilename` maps to `InvalidFileContent` and an unknown extension to `UnsupportedDocumentType` (D3). The returned `IngestedUpload` owns the spooled file; callers must `close()` it (it is also a context manager).
- Oversize is detected mid-stream: at most one chunk past `max_bytes` is read. Spooling uses `SpooledTemporaryFile` (8 MiB in memory, then disk), so memory is bounded by the spool threshold plus one chunk.
- `FileInspector` opens images with `Image.open(..., formats=[PNG, JPEG, TIFF])`: other formats fail as unidentified, and camera JPEGs are not detected as MPO. The pixel cap is checked from the header right after open, before `verify()`.
- `file_inspector.py` sets `Image.MAX_IMAGE_PIXELS = None` at import. Pillow's own guard raises above about 178M pixels, which would reject legitimate scans under our 600M default; the explicit header check replaces it. This is process-wide, but this module is the only Pillow user in the API (enforced by an AST test).
- HTTP status mapping (413, 415, 422) is not added here. It arrives with the documents router in PR-08; the new exceptions only carry `code`s.
- Known limitation (technical debt): `verify()` only walks PNG structure. A JPEG or TIFF with an intact header and a truncated body is accepted, since Phase 2 does not decode pixels. `test_known_limitation_truncated_jpeg_and_tiff_bodies_pass_header_validation` pins this so a change is noticed.
- `Pillow>=11.0` is in `services/api/pyproject.toml` and `requirements-dev.txt`. CI installs `requirements-dev.txt` and the Dockerfile installs `-e services/api`, so neither needed an edit.

**Acceptance.** Coverage of every rejection class in §13; memory use is bounded by the spool threshold, not file size (documented in the test); no filenames or content in log output.

**Size.** M.

---

### PR-07 — Revision lineage and document inheritance

**Goal.** Revisions record lineage and can inherit document associations atomically, without any upload code existing yet. (§5, §6, §17 shared helper, §18, §19, §20 metadata copy; ADR-004 #5–#11, #13)

**Depends on.** PR-03 (error mapping), PR-04 (tables).

**Scope.**
- `schemas/projects.py`
  - `RevisionCreate`: add `based_on_revision_id: UUID | None` and `carry_forward_documents: bool | None`, preserving **omitted vs explicit null** (via `model_fields_set`); keep `activate`.
  - `RevisionResponse`: add `based_on_revision_id`, `based_on_identifier`, `inherited_document_count` (create response; null/0 elsewhere as appropriate).
  - `RevisionUpdate` already `extra="forbid"`: add a test proving `based_on_revision_id` is rejected (lineage immutable).
- `exceptions.py`: `InvalidBaseRevision` (and `RevisionReadOnly` introduced here because the shared helper needs it; `DocumentAlreadyInRevision` is deferred to PR-09/08 where used).
- New shared helper module `services/revision_documents.py` (no import of `DocumentService`/`RevisionService`):
  - `assert_documents_mutable(session, project, revision)` — project lifecycle (reusing existing `ArchivedProject`/`CancelledProject` logic) then revision status (`RevisionReadOnly` for `SUPERSEDED`)
  - `lock_revision(session, revision_id)` (`FOR UPDATE`)
  - `copy_included_associations(session, base, target)` — builds INHERITED rows per §6/§20, returns count
- `services/revision_service.py`: base resolution (UUID / omitted → ACTIVE or none / explicit null), carry-forward resolution, `InvalidBaseRevision` for cross-project, self, unknown base, or `carry_forward=true` without a base; lock order project → base revision; create → flush → inherit → (optional) activate → single commit; map new constraints (`fk_project_revisions_based_on`, `ck_..._not_self` → `InvalidBaseRevision`) via the PR-03 helper; structured log `revision document inheritance completed` with count.
- `routers/projects.py`: map new errors (`InvalidBaseRevision` → 422; `RevisionReadOnly` → 409); include new response fields; `_http_for` stays the single mapping point.

**Out of scope.** Upload/list/documents routes; frontend.

**Tests** (`tests/test_revision_lineage_api.py`, integration; seed documents/associations directly via ORM since no upload exists yet):
- Spec §30 inheritance matrix: base with A INCLUDED, B INCLUDED, C REMOVED → new revision has A, B as INCLUDED/INHERITED, no C; same `document_id`s; `inherited_from_revision_id` = base; type/number/description/notes copied; new row ids and `added_at` differ; base unchanged; **storage fake records zero calls**
- `carry_forward_documents=false`: none inherited, base still recorded
- explicit `based_on_revision_id=null` with ACTIVE present: no base, no inheritance
- explicit `carry_forward_documents=true` with no base → `InvalidBaseRevision` (422)
- omitted base with ACTIVE → ACTIVE is base, carry-forward true; no ACTIVE → no base, carry-forward false
- base may be an older SUPERSEDED revision; base from another project rejected (404/422 per mapping); self-base rejected; lineage not changeable via PATCH
- `activate=true` + carry-forward: documents copied from base before base is superseded; exactly one ACTIVE afterwards
- inheriting a base that itself holds INHERITED rows → new rows reference the **immediate** base as `inherited_from_revision_id`
- atomicity: force a failure during inheritance (monkeypatch helper) → no new revision row, no partial associations
- snapshot semantics: editing base after creation does not change the child (and vice versa)
- helper unit tests: `assert_documents_mutable` matrix (revision DRAFT/ACTIVE/SUPERSEDED × project ACTIVE/PAUSED/CANCELLED/ARCHIVED)
- Phase 1 revision tests unchanged and passing; concurrent create/activate tests still pass with the new lock

**Implementation notes (as landed).**
- Every unusable base (unknown id, another project's revision) is `InvalidBaseRevision` (422), never 404. The base lookup is filtered by `project_id` inside `lock_revision`, so a foreign revision is reported as missing and its row is never locked. A self-base cannot be requested through the API (the new id is generated server-side); `ck_project_revisions_based_on_not_self` still guards it and both lineage constraints are mapped to `InvalidBaseRevision`.
- The project row is locked `FOR UPDATE` when `activate` is true or the base is not an explicit `null`, because resolving the default ACTIVE base must not race an activation. An explicit `null` without `activate` takes no lock, as before. The base revision is then locked `FOR UPDATE` (project first, then revision).
- `create_revision` returns a `RevisionCreateResult(revision, inherited_document_count)`. `inherited_document_count` is set only on the create response and is `null` on get, list, update and activate, to avoid per-row queries. `based_on_identifier` is resolved with one lookup on single-revision responses and from the already-loaded list on the list endpoint.
- Any exception during revision creation (not only `IntegrityError`) rolls the session back, so a failure inside inheritance or activation leaves neither a revision row nor partial associations.
- Inheritance is a single `INSERT ... SELECT ... RETURNING` in `copy_included_associations`; the inserted ids are counted because `rowcount` is unreliable for ORM `INSERT ... SELECT` (it reported -1).
- The project lifecycle rule (ARCHIVED and CANCELLED block writes, PAUSED does not) now lives in one function, `assert_project_modifiable`, used by `RevisionService`, `ProjectService` and `assert_documents_mutable`. The plan's `session` argument on `assert_documents_mutable` was dropped because nothing needs it.
- Not added here: the `FOR SHARE` project lock for document mutations and the `FOR UPDATE` upgrade in `archive_project` and `cancel_project` (decision D11). They landed with the first mutating endpoint in PR-08.
- `RevisionReadOnly` (409) is defined and mapped but nothing raises it until document mutations exist (PR-08).

**Acceptance.** Revision creation is a single transaction; the lock order is project → revision; no circular import between services; API docs show the new fields.

**Size.** L (largest backend PR; do not merge without the atomicity and snapshot tests).

---

### PR-08 — Document upload, list, and get

**Goal.** The first end-to-end document flow: upload one file into a revision, list, and fetch it. (§7, §8, §14–§16, §17, §21 list/upload/get, §22, §28)

**Depends on.** PR-04, PR-05, PR-06, PR-07.

**Scope.**
- `schemas/documents.py`: `DocumentSummary`, `RevisionDocumentResponse` (fields per §21), `RevisionDocumentListResponse`, `UploadResponse` (adds `duplicate_detected`, `duplicate_document_ids`); `extra="forbid"` on input schemas.
- `exceptions.py`: `RevisionDocumentNotFound`, `CrossProjectDocumentAccess`, `StorageUploadFailed`.
- `services/document_service.py` (`DocumentService`):
  - `upload(project_id, revision_id, fileobj, filename, metadata)`: validate project/revision ownership → early mutability check → `ingest_upload` → `FileInspector` → generate UUID + storage key → `storage.put` (no locks held) → open DB step: lock revision row, **re-check mutability under lock**, duplicate lookup `(project_id, sha256)`, insert `Document` + `RevisionDocument(UPLOADED, INCLUDED)` → commit
  - locking per [D11](#6-open-decisions): the DB step takes `FOR SHARE` on the project row, then `FOR UPDATE` on the revision row, then re-checks project and revision mutability; the lock helper introduced here (in `revision_documents.py`, next to `lock_revision`) is reused by every PR-09 mutation
- `services/project_service.py`: `archive_project` and `cancel_project` load the project `FOR UPDATE` before checking status, so they serialize with in-flight document mutations (D11). No behavior or response change.
  - failure handling per §15: put fails → no DB rows (`StorageUploadFailed`, no SDK text); DB/mutability failure after put → best-effort `delete`, log cleanup failure without masking the original error
  - `list_documents(…, status, document_type, origin, search)`: `status` default `INCLUDED` (`INCLUDED|REMOVED|ALL`); case-insensitive search across filename/number/description with escaped LIKE wildcards; deterministic order (`added_at`, filename)
  - `get_document(project_id, revision_id, revision_document_id)`: ownership verified through the association; mismatches → not found
  - structured logs: uploaded, duplicate detected, storage failure, DB failure, cleanup failure
- `routers/documents.py`: `GET/POST …/documents`, `GET …/documents/{revision_document_id}`; multipart form with one `file` and optional `document_type`, `document_number`, `description`, `notes`; early reject on `Content-Length` > max (untrusted optimization); register in `main.py`; HTTP mapping per §21 (413/415/422/502, plus existing 404/409).
- `uploaded_by`, `added_by` are set to `NULL` (no auth yet, consistent with ADR-003); `uploaded_at`/`added_at` are server-set.
- `main.py`: update the OpenAPI description (it still says "Phase 1: …") and keep CORS settings as-is (see CORS test below).
- `services/api/pyproject.toml`, `requirements-dev.txt`, CI: add `python-multipart`.

**Out of scope.** Metadata PATCH, remove/restore, reuse, download URL (PR-09/10); UI.

**Tests** (`tests/test_documents_api.py`, integration, using the in-memory storage override):
- upload valid PDF/PNG/JPEG/TIFF → 201; `Document` metadata persisted (filename sanitized, mime, extension, size, sha256, uploaded_at); object exists in fake storage at `projects/{pid}/documents/{did}/original{ext}`; `RevisionDocument` origin `UPLOADED`, status `INCLUDED`, type default `UNKNOWN`, optional metadata applied
- unsupported / fake-extension / mismatch / empty / oversize (small `MAX_UPLOAD_BYTES` override) → correct status codes and `code`s; **no DB rows and no storage objects** left behind for rejected files
- duplicates: identical bytes uploaded twice (same and different revisions) → both accepted, **two distinct `Document` ids**, second response has `duplicate_detected=true` with the first id; duplicates detected against documents that are only REMOVED
- ownership: unknown project/revision → 404; revision from another project → 404; revision-document id from another revision/project → 404
- mutability: DRAFT and ACTIVE allow upload; SUPERSEDED → 409 `RevisionReadOnly`; CANCELLED/ARCHIVED → 409; PAUSED allowed
- **re-check under lock**: simulate status flipping to SUPERSEDED between the early check and the locked re-check → rejected, uploaded object cleaned up
- **archive/cancel race (D11)**: simulate the project becoming ARCHIVED/CANCELLED between the early check and the locked re-check → rejected (`ArchivedProject`/`CancelledProject`), uploaded object cleaned up; assert the DB step issues `FOR SHARE` on the project before `FOR UPDATE` on the revision (for example by capturing the emitted SQL), and that two uploads to the same project do not deadlock
- `archive_project`/`cancel_project` still behave identically for existing Phase 1 tests; a best-effort concurrent test shows an archive started during an in-flight upload waits for it, and the next upload then gets 409
- invalid `document_type` form value → 422 and nothing stored; omitted → `UNKNOWN`
- CORS: a preflight `OPTIONS` for multipart `POST …/documents` from each configured origin (`http://localhost:3000`, `http://127.0.0.1:3000`) succeeds, since the browser uploads directly to the API (existing middleware; test only, unless it fails)
- storage failure on put → 502, zero DB rows
- DB failure after put (monkeypatch insert to raise) → delete attempted; delete failing is logged and original error still returned
- list: default hides REMOVED; `status=REMOVED|ALL`; `document_type`, `origin`, `search` (filename, number, description; case-insensitive; `%`/`_` treated literally); stable order
- never logs contents/secrets (capture logs)
- Phase 1 tests unchanged

**Implementation notes (as landed).**
- Upload order: ownership and early mutability check, then `session.rollback()` so no connection sits idle during the slow ingest and storage write, then `ingest_upload`, `FileInspector`, `storage.put`, then the locked DB step (`FOR SHARE` on the project, `FOR UPDATE` on the revision, mutability re-check, duplicate lookup, inserts, commit). The locked selects use `populate_existing` so a status changed by another transaction is never masked by a cached row. The session factory has `autoflush=False`, so the `Document` row is flushed explicitly before its association.
- The upload never writes to the project row (that would upgrade the shared lock, which D11 forbids); it bumps `updated_at` on the locked revision only. A test asserts no `UPDATE projects` is issued.
- `archive_project` and `cancel_project` now load the project `FOR UPDATE` first (`_get_project_for_update`); pause, resume and unarchive are unchanged. Tests show an archive waits for a simulated in-flight mutation and the next upload gets `archived_project`.
- `_http_for` moved to `routers/errors.py` (`http_for`) so both routers share one mapping; `projects.py` imports it under the old name. 413, 415, 422 and 502 use numeric codes to avoid deprecated status-constant names. `CrossProjectDocumentAccess` is mapped to 404 now but first raised in PR-09.
- The `Content-Length` guard is a custom `APIRoute` (`UploadSizeGuardRoute`), because FastAPI parses the multipart form before dependencies run. It allows `max_upload_bytes` plus 256 KiB of multipart overhead and reads settings through `dependency_overrides`, so tests can lower the limit. It is only an optimisation; `ingest_upload` enforces the real cap.
- Known limitation: Starlette spools the whole multipart body to a temporary file before the handler runs, so a client that omits or lies about `Content-Length` (for example chunked encoding) can still make the server write its full body to temp disk before the streaming cap rejects it. A true streaming cap needs a proxy limit or a custom ASGI body limiter; recorded as hardening debt for PR-15.
- `document_type` is parsed as an enum form field, so an invalid value produces FastAPI's standard 422 body (`detail` is a list), not the `{detail, code}` shape. Unknown form fields are ignored. Form text limits: number 128, description 2000, notes 10000 characters; blank strings are stored as null.
- Storage failures of any kind during `put` become `StorageUploadFailed` (502) with a fixed message; the error class is logged, the SDK text is not. Log events carry ids and counts only (never filenames, object keys or URLs): `document uploaded`, `duplicate document detected`, `object storage upload failed`, `document database step failed`, `orphan object cleanup failed`.
- `tests/file_factory.py` now holds the shared PDF/PNG/JPEG/TIFF builders (`test_file_validation.py` imports them). `tests/test_documents_api.py` adds 43 tests (38 need the database).
- Dependency added: `python-multipart` (`services/api/pyproject.toml`, `requirements-dev.txt`); CI and the API image install from those files.

**Acceptance.** An engineer can upload to a revision through the API and see it listed; failure paths leave storage and DB consistent; all routes enforce project/revision ownership.

**Size.** L (split off the list/get routes into a follow-up only if review size demands it).

---

### PR-09 — Metadata, remove, restore, and reuse

**Goal.** All remaining document mutations. (§17, §20, §21 PATCH/remove/restore/reuse, §30 mutability/remove/reuse)

**Depends on.** PR-08.

**Scope.**
- `exceptions.py`: `DocumentAlreadyInRevision`; mapping for edit-of-REMOVED conflict (reuse an existing 409 error type with a clear code, or add `DocumentRemoved`; decide in PR).
- `DocumentService` (all mutations: `assert_documents_mutable` + project `FOR SHARE` + revision `FOR UPDATE` lock via the PR-08 helper + re-check):
  - `update_metadata` — `document_type`, `document_number`, `description`, `notes` only; PATCH schema `extra="forbid"` so immutable fields (`original_filename`, `sha256`, `storage_key`, size, MIME, `uploaded_at`, `project_id`, `status`, `origin`) → 422; editing a REMOVED association → 409
  - `remove` — `status=REMOVED`, `removed_at`, `removed_by` (null for now); never touches `Document` or storage; idempotent (second call does not change `removed_at`)
  - `restore` — `INCLUDED`, clears `removed_at`/`removed_by`; idempotent
  - `reuse(source_revision_document_id, overrides)` — source must be an INCLUDED association of the same project; creates `INHERITED` association with `inherited_from_revision_id` = source revision, copies source metadata unless overridden; already associated (INCLUDED or REMOVED) → `DocumentAlreadyInRevision` (message tells the user to restore for REMOVED; see [D10](#6-open-decisions)); cross-project source → `CrossProjectDocumentAccess`
- Routes: `PATCH …/{id}`, `POST …/{id}/remove`, `POST …/{id}/restore`, `POST …/documents/reuse`; map `DocumentAlreadyInRevision` → 409.
- Race handling: the service pre-check for an existing association is not enough under concurrency, so `IntegrityError` on `uq_revision_documents_revision_id_document_id` is mapped (via the PR-03 helper) to `DocumentAlreadyInRevision`; any other unknown constraint on these paths falls through to the generic internal error (spec §23).
- Structured logs: removed, restored, reused.

**Out of scope.** Download URL (PR-10); UI.

**Tests** (`tests/test_documents_mutations_api.py`, integration):
- metadata: each editable field updates; immutable/unknown fields → 422 and unchanged; REMOVED edit → 409
- remove: sets REMOVED/`removed_at`; `Document` row and storage object still present (fake `exists`); the same document in another revision remains INCLUDED; idempotent
- restore: back to INCLUDED, `removed_at`/`removed_by` cleared; idempotent
- reuse: new INHERITED association to the same `Document` id; metadata copied/overridden; duplicate association → 409; REMOVED association → 409 with restore hint; cross-project source → rejected at service **and** (direct SQL insert) by the composite FK; REMOVED source association rejected
- **mutability matrix across all mutation endpoints**: DRAFT/ACTIVE allowed; SUPERSEDED, CANCELLED, ARCHIVED rejected; PAUSED allowed
- the workflow: replace a document in a new revision (upload B, remove inherited A) leaves the previous revision unchanged
- race: two concurrent reuse requests for the same document/revision → one succeeds, the other gets 409 `DocumentAlreadyInRevision` (not a 500 and not a duplicate row); an unrelated constraint failure is not reported as `DocumentAlreadyInRevision`

**Implementation notes (as landed).**
- One shared mutation path: `DocumentService._mutate` loads the project and revision (404s), then `_lock_for_mutation` takes the project `FOR SHARE`, the revision `FOR UPDATE`, and re-checks `assert_documents_mutable` (D11). Upload's DB step uses the same lock helper. Error order is project/revision 404, then not-mutable 409, then association 404. No mutation writes the project row.
- PATCH: omitted fields are left alone (`model_fields_set`); an explicit `null` clears `document_number`, `description` and `notes`; `document_type: null` is a 422; blank strings become null. `extra="forbid"` rejects every immutable or unknown field. An empty body on an INCLUDED row is a 200 no-op. Editing a REMOVED association is a 409 `document_removed`.
- Remove and restore are idempotent; the second call changes nothing (including `removed_at`) and logs nothing. `Document` rows and storage are never touched (tests assert no storage calls).
- Reuse looks up the source after the target lock. Order of checks: source exists (404), same project (`CrossProjectDocumentAccess`, 404), target already holds the document (409 `document_already_in_revision`, with a restore hint for REMOVED and the existing id and status in the body), source is not REMOVED (409 `document_removed`). Checking the target first means reuse into the source's own revision is a clean 409 and never reaches `ck_revision_documents_inherited_not_self`.
- The source revision is deliberately not locked, so two reuses in opposite directions cannot deadlock; a source changed just after the read only affects that snapshot. Reuse from a SUPERSEDED revision is allowed (the main use case); reuse into one is rejected.
- Because every reuse into one revision serializes on that revision's lock, the pre-check normally decides a race. The `uq_revision_documents_revision_id_document_id` mapping is the backstop; a test bypasses the pre-check to prove it, and proves that another constraint (`ck_..._inherited_not_self`) stays `unexpected_integrity_error`.
- The `Content-Length` guard from PR-08 now applies only to the upload route (`add_api_route(..., route_class_override=UploadSizeGuardRoute)`), not to JSON routes.
- `routers/errors.py` adds 409 for the two new errors and merges `existing_revision_document_id` and `existing_status` into the `DocumentAlreadyInRevision` body.
- Logs carry ids and field names only: `document metadata updated` (`changed_fields`), `document removed`, `document restored`, `document reused` (with source ids).
- Tests: `tests/test_documents_mutations_api.py`. Shared helpers moved to `tests/documents_support.py` and the `require_db`, `use_storage` and `ctx` fixtures to `tests/conftest.py` (PR-08 tests unchanged apart from the OpenAPI assertion now listing `patch`).

**Acceptance.** No endpoint can change `Document` identity fields; every mutation passes through the shared mutability check and revision lock.

**Size.** M.

---

### PR-10 — Download URLs and end-to-end backend workflow

**Goal.** Close the backend: scoped signed downloads and the exact §34 scenario as a regression test. (§21 download, §30 download, §34, §36)

**Depends on.** PR-08, PR-09.

**Scope.**
- `DocumentService.create_download_url(project_id, revision_id, revision_document_id, disposition)` → `{url, expires_at, filename}`; allowed for INCLUDED **and** REMOVED associations and in every revision/project status (read-only history); resolves the `Document` only via the association; uses `S3_SIGNED_URL_EXPIRES_SECONDS`; passes sanitized filename, stored MIME, and `disposition` (`inline|attachment`, default `attachment`) to the storage abstraction.
- Route `GET …/documents/{revision_document_id}/download-url?disposition=`; invalid disposition → 422. **No unscoped `/api/documents/{id}` route exists** (add a test that asserts 404 for such paths).
- Logging: never log the URL.

**Tests** (`tests/test_documents_download_api.py`, `tests/test_phase2_workflow.py`, integration):
- valid association → URL containing public endpoint, expiry matches setting, `response-content-disposition`/`response-content-type` signed; `inline` vs `attachment`
- REMOVED association and SUPERSEDED revision still downloadable; ARCHIVED/CANCELLED project still downloadable
- `revision_document_id` used with the wrong revision, or wrong project → 404; unscoped route 404
- real MinIO (integration): returned URL actually serves the bytes with the expected headers; the same object is not retrievable without a signature
- **End-to-end workflow test (§34):** create project P-100 → Revision 0 (no base, empty) → upload three PDFs → activate → create Revision 1 with defaults (3 inherited, same `Document` ids, zero storage copies) → upload `SLD_RevB.pdf` → remove inherited `SLD_RevA.pdf` → activate Revision 1 → Revision 0 superseded and read-only (upload/edit/remove/restore → 409; list/download OK); Revision 0's rows unchanged throughout
- Run the complete spec §30 checklist against the suite and record any gap in the PR description.

**Implementation notes (as landed).**
- `GET …/documents/{rdid}/download-url?disposition=attachment|inline` returns `{url, expires_at, filename}`. `disposition` is the storage layer's `DispositionType` literal, so anything else is a 422 before anything is signed. The response carries `Cache-Control: no-store`.
- It is a pure read: no locks, no writes, no mutability check, so it works for INCLUDED and REMOVED rows in every revision and project status. A test captures the SQL and asserts there is no `INSERT`/`UPDATE`/`DELETE` and no `FOR SHARE`/`FOR UPDATE`.
- Error order is project/revision 404, then association 404. The `Document` is reached only through the association join, which also enforces `Document.project_id == RevisionDocument.project_id`. The storage key is never in any response except inside the signed URL itself.
- A signing failure is 502 `storage_download_failed` (new `StorageDownloadFailed`), with only the error class logged. No object-exists check is made when issuing a URL (signing is local; a missing object shows up as a storage 404 on the URL).
- The backend does not block `inline` for TIFF; hiding it is a UI rule (PR-12).
- The log event `document download url issued` carries ids, `disposition` and `expires_seconds` only. The URL, filename and storage key are never logged (the JSON formatter also redacts any extra key containing `url`).
- Tests: `tests/test_documents_download_api.py` (includes a real-MinIO case that fetches the bytes through the signed URL, checks the signed headers and the `S3_PUBLIC_ENDPOINT_URL` host, and confirms an unsigned or tampered request gets 403) and `tests/test_phase2_workflow.py` (spec §34, step by step). The `s3_scratch_storage` fixture moved from `tests/test_storage.py` to `tests/conftest.py` so both suites share it.
- One gap found while mapping §30 and closed here: list ownership (`test_list_enforces_ownership`).

**Spec §30 coverage map (backend).** Every item has a named test; no open gaps.

| §30 item | Tests |
| --- | --- |
| Valid PDF/PNG/JPEG/TIFF accepted; mime from content; browser type ignored | `test_documents_api.py::test_valid_upload_stores_object_and_records`, `test_file_validation.py::test_valid_files_are_accepted_with_mime_derived_from_content`, `::test_browser_content_type_is_not_an_input`, `test_documents_download_api.py::test_the_browser_content_type_is_not_used_for_the_signed_content_type` |
| Unsupported extension, renamed executable, fake or mismatched content, empty file | `test_file_validation.py::test_unsupported_extension_is_rejected_before_the_body_is_read`, `::test_invalid_or_mismatched_content_is_rejected`, `::test_empty_file_is_rejected`, `test_documents_api.py::test_rejected_files_leave_nothing_behind` |
| Oversize (413) enforced while streaming; pixel cap | `test_documents_api.py::test_oversize_file_is_rejected_while_streaming`, `::test_file_at_the_limit_is_accepted`, `::test_oversize_content_length_is_rejected_before_the_body_is_read`, `::test_image_over_the_pixel_cap_is_rejected`, `test_file_validation.py::test_oversize_upload_stops_reading_early`, `::test_pixel_cap_is_enforced_from_the_header_without_decoding` |
| Filename sanitization | `test_document_domain.py::test_sanitize_*`, `test_file_validation.py::test_filename_is_sanitized_and_never_part_of_a_storage_key` |
| SHA-256, metadata, stable storage key, UPLOADED/INCLUDED row | `test_documents_api.py::test_valid_upload_stores_object_and_records`, `test_file_validation.py::test_hash_size_and_rewind_over_multiple_chunks`, `test_document_domain.py::test_build_storage_key_exact_format` |
| Duplicates flagged, allowed, new Document, REMOVED included | `test_documents_api.py::test_duplicate_content_is_flagged_but_never_rejected_or_merged`, `::test_duplicate_is_detected_across_revisions_and_removed_documents`, `::test_identical_content_in_another_project_is_not_a_duplicate` |
| Ownership and cross-project on every route | upload and get: `test_documents_api.py::test_ownership_failures_are_404_and_touch_no_storage`, `::test_get_returns_one_document_and_enforces_ownership`; list: `::test_list_enforces_ownership`; patch, remove, restore, reuse: the ownership and cross-project cases in `test_documents_mutations_api.py`; download: `test_documents_download_api.py::test_the_association_must_belong_to_the_given_revision`, `::test_another_projects_ids_never_yield_a_url`, `::test_unknown_ids_are_not_found_with_the_right_codes` |
| Cross-project reuse rejected; composite FKs reject direct inserts | `test_documents_mutations_api.py` (cross-project reuse and `fk_revision_documents_document`), `test_phase2_constraints.py::TestRevisionLineage`, `::TestRevisionDocuments::test_cross_project_*` |
| Lineage and inheritance matrix, snapshot, atomicity, activate with carry-forward | `test_revision_lineage_api.py` (all), `test_phase2_workflow.py` |
| Mutability matrix, PAUSED allowed, re-check under lock | `test_documents_api.py::test_draft_active_and_paused_accept_uploads`, `::test_superseded_revision_is_read_only`, `::test_cancelled_and_archived_projects_reject_uploads`, `::test_status_flipped_during_the_object_write_is_caught_under_lock`, the mutability matrix and flip tests in `test_documents_mutations_api.py`, `test_revision_documents.py::test_assert_documents_mutable_matrix` |
| Remove, restore, idempotence, edit of REMOVED, reuse conflicts | `test_documents_mutations_api.py` |
| Metadata editable; unknown or immutable fields 422 | `test_documents_mutations_api.py` (metadata cases) |
| Storage failure, DB failure after put, cleanup failure, put never overwrites | `test_documents_api.py::test_storage_failure_is_502_without_leaking_sdk_text`, `::test_database_failure_after_the_write_removes_the_object`, `::test_failed_cleanup_is_logged_and_does_not_mask_the_original_error`, `test_storage.py::TestContract::test_put_to_existing_key_is_refused_and_original_preserved`, `::TestS3Specific::test_conditional_put_header_is_enforced_by_the_server` |
| Download: URL with expiry, filename, disposition | `test_documents_download_api.py` (URL, disposition, expiry tests and the MinIO case) |
| Download: REMOVED and superseded allowed; wrong revision or project rejected | `test_documents_download_api.py::test_a_removed_association_can_still_be_downloaded`, `::test_history_is_downloadable_in_every_revision_and_project_state`, the scoping tests, `test_phase2_workflow.py` |
| URLs not logged | `test_documents_download_api.py::test_the_log_records_the_event_but_never_the_url_filename_or_key`, `test_logging.py` (redaction) |
| Error mapping: non-identifier IntegrityErrors; each §23 constraint | `test_integrity_error_mapping.py` (all), `test_revision_lineage_api.py::test_lineage_constraint_violations_map_to_invalid_base_revision`, `test_documents_mutations_api.py` (unique-constraint backstop and unrelated constraint to 500) |
| Migration: fresh, from 0003 with data, downgrade | `test_migration_0004.py` |
| Real MinIO: put/get/exists/delete and presigned retrieval | `test_storage.py` (contract run against S3, `TestS3Specific`), `test_documents_download_api.py::test_the_signed_url_serves_the_bytes_from_real_object_storage` |
| Phase 1 tests continue to pass | `test_projects_api.py`, `test_project_domain.py`, `test_domain.py`, `test_health.py` and the rest of the suite |

**Acceptance.** Backend feature-complete per spec §§5–24; OpenAPI exposes all routes with response models; every item in spec §30 (backend) maps to a named test.

**Size.** M.

---

### PR-11 — Frontend foundations and Create Revision UI

**Goal.** Types, API clients, and the revision-creation experience; show lineage. (§26, §25 client)

**Depends on.** PR-07 (API fields). Can proceed in parallel with PR-08..PR-10.

**Scope** (`apps/web/src/`):
- `lib/projects.ts`: extend `Revision` with `based_on_revision_id`, `based_on_identifier`; `RevisionCreateInput` with `based_on_revision_id?: string | null` (omit vs null preserved when serializing) and `carry_forward_documents?: boolean`; `createRevision` returns inherited count.
- `lib/documents.ts`: types (`DocumentType` union mirroring the backend enum, `DocumentOrigin`, `RevisionDocumentStatus`, `RevisionDocument`, `UploadResult`), label/format helpers (human labels per type, file size), and list/get/patch/remove/restore/reuse/download-url client functions (upload client comes in PR-13). Shared error parsing reused from `projects.ts`.
- `components/project-detail.tsx`: Create Revision UI — **Based on** select (every revision in the project, plus "None (start fresh)"), default = ACTIVE revision or None; **carry-forward** checkbox (default on when a base is selected; disabled and unchecked for None); informational note when base is not the ACTIVE revision; send explicit `null` for None and omit the key when the user leaves the default untouched; show inherited document count after creation; show "Based on Revision X" in the revision list.
- `app/projects/[projectId]/revisions/[revisionId]/page.tsx`: show lineage in the header (documents workspace arrives in PR-12).

**Out of scope.** Documents workspace, uploads.

**Tests** (vitest + testing-library, `components/projects.test.tsx` and `lib/*.test.ts`):
- `createRevision` request bodies: default (keys omitted), explicit None (`based_on_revision_id: null`, `carry_forward_documents: false`), explicit base, carry-forward unchecked
- form defaults: ACTIVE base preselected, carry-forward checked; no ACTIVE → None selected and checkbox disabled; choosing None disables/unchecks; non-ACTIVE base shows the note
- lineage text renders; existing Phase 1 UI tests unchanged and passing
- `lib/documents.ts` client functions: URL construction, error parsing (`detail.code`), type label helpers

**Implementation notes (as landed).**
- `request` and `parseError` moved from `lib/projects.ts` into `lib/api.ts` and are shared with `lib/documents.ts`. `projects.ts` still exports the `ApiError` type. `parseError` now also reads FastAPI's 422 shape (an array of `{msg}`, joined with `; `) and keeps the `existing_revision_document_id` and `existing_status` fields of a `document_already_in_revision` conflict. `apiErrorOf(err)` returns `{ status, code, detail, error }` so components do not cast.
- `Revision` has required `based_on_revision_id` and `based_on_identifier` (the API always returns them) and an optional `inherited_document_count` that is set only on the create response. The Phase 1 test fixtures gained the two required fields; no assertion changed.
- Create Revision request rule: a control the user has not touched sends nothing, so the server's defaults apply (ACTIVE base, carry forward on). Choosing a base sends `based_on_revision_id` (a UUID, or an explicit `null` for None, which also sends `carry_forward_documents: false`), even if the user re-selects the ACTIVE revision. Unchecking carry forward sends `false`. Changing the base resets carry forward to its default for that base.
- "Based on" is a native `<select>` (there is no select primitive in `components/ui`). The success message reports the carried-forward count. Lineage is shown by the shared `components/revision-lineage.tsx` in the revision list (plain text) and in the revision page header (linked to the base revision).
- `lib/documents.ts` holds the types, the 16 type labels (`UNKNOWN` is "Unclassified"), `formatFileSize`, and the list, get, patch, remove, restore, reuse and download-url clients. `updateDocument` and `reuseDocument` send only the keys the caller passes, so omitted means unchanged and `null` clears a text field. `uploadDocument` (PR-13) and `canMutate` (PR-12) are not part of this PR.

**Acceptance.** `npm run lint`, `npm test`, `npx tsc --noEmit`, `npm run build` pass; manual check against a running stack: create Revision 1 from Revision 0 shows inherited count (documents appear in the workspace after PR-12).

**Size.** M.

---

### PR-12 — Revision documents workspace (read side)

**Goal.** Replace the Phase 1 revision placeholder with a working, read-oriented documents view. (§25, §27, §12 views)

**Depends on.** PR-10 (download URLs), PR-11.

**Scope.**
- `app/projects/[projectId]/revisions/[revisionId]/page.tsx`: server component loads project and revision; renders a client `RevisionDocuments` component; remove the "Coming Soon" placeholder.
- `components/revision-documents.tsx` (+ small presentational pieces under `components/`): table of File / Type / Origin / Status / Added; search field; Type, Origin, and View (`Included | Removed | All`) filters (server-side via query params; the Type filter is the spec's "By Document Type" view); empty/loading/error states; origin badge ("Uploaded" vs "Inherited") with "Inherited from Revision X" (resolved from the revisions list); row **Open** (inline) for PDF/PNG/JPEG, **Download** for all and for TIFF (inline not offered for TIFF); fetches a fresh download URL on click (never cached/logged).
- **Read-only banner** when the revision is `SUPERSEDED` or the project is `ARCHIVED`/`CANCELLED`, stating why; compute `canMutate` in one helper (`lib/documents.ts`) so later PRs reuse it. Mutation controls arrive in PR-13/14 and must read this helper.
- Handle 409 gracefully (state changed under the user): show message, refresh.

**Out of scope.** Upload, edit, remove/restore, reuse (PR-13/14).

**Tests.**
- renders rows with correct labels, origin badges, inherited-from text; empty state
- filters/search produce the expected client calls (debounced search)
- Removed view shows removed rows; default hides them
- TIFF row offers Download but not Open
- read-only banner shown for SUPERSEDED / ARCHIVED / CANCELLED, hidden for DRAFT/ACTIVE and PAUSED; `canMutate` unit-tested across the matrix
- download action requests a URL and opens it (mock `window.open`)

**Implementation notes (as landed).**
- `lib/documents.ts` gained `readOnlyReason`, `canMutate` and `canOpenInline`. `canMutate` is true unless the revision is `SUPERSEDED` or the project is `ARCHIVED` or `CANCELLED` (PAUSED stays mutable, as in the backend); the banner and PR-13/14 controls must read it. `canOpenInline` is decided by MIME type (`image/tiff` is download only).
- "Inherited from Revision X" uses `inherited_from_revision_identifier` from the API (linked through `inherited_from_revision_id`), so no revisions-list lookup is needed.
- Documents are fetched on the client after mount, so the first load and every filter change share one path. Search is debounced by 300 ms, and a request counter drops responses that arrive out of order.
- A 404 or 409 from the list or a download shows the server message and refreshes the list once; other list errors show Retry.
- Open pre-opens a blank tab inside the click handler and sets its location when the signed URL arrives (so popup blockers do not block it), and closes the tab on failure; Download assigns the location to an attachment URL. Each click requests a fresh URL, which is never stored or logged.
- The revision page keeps its header, lineage link and metadata cards; the "Coming Soon" block is replaced by the banner and `RevisionDocuments`. Type and Origin are native selects, View is a `SegmentedControl`.

**Acceptance.** Against a running stack, a user can open a revision, see inherited vs uploaded documents (seeded through the API or Swagger), filter/search them, and open/download an original via a signed URL that works from the browser (this is the first end-to-end proof of `S3_PUBLIC_ENDPOINT_URL`).

**Size.** M.

---

### PR-13 — Multi-file upload UI

**Goal.** Drag-and-drop, multi-file upload as independent requests with per-file results. (§25 upload, §16 warnings, ADR-004 #19, #20)

**Depends on.** PR-08 (upload API), PR-12.

**Scope.**
- `lib/documents.ts`: `uploadDocument(projectId, revisionId, file, metadata, { onProgress, signal })` using `XMLHttpRequest` (for upload progress) with the shared error parsing; returns `UploadResult` including `duplicate_detected`.
- `components/document-upload.tsx`: "Upload Documents" button + drop zone (also accepts the file picker, multi-select); client pre-filter by extension and `MAX_UPLOAD_BYTES` hint (advisory — the server is authoritative); a queue with per-file state (`queued → uploading → done | failed`), progress, error message from `code`, **Retry** per file, remove-from-queue; concurrency limit 3; each file is a separate request; list refreshes as files complete; non-blocking duplicate warning ("An identical file already exists in this project.") per file; hidden/disabled when `canMutate` is false (and graceful 409 handling if the revision became read-only).
- Optional per-batch default document type applied to all files (nice-to-have; only if trivial).

**Out of scope.** Metadata editing, remove/restore.

**Tests.**
- uploading N files issues N independent requests; concurrency never exceeds 3
- mixed outcomes: success, server rejection (415/422/413), network failure → per-file states and messages; one failure does not stop others
- retry re-sends only the failed file
- duplicate warning shown for `duplicate_detected` without blocking
- progress callback updates state
- controls absent/disabled in read-only mode; 409 on upload shows read-only message and refreshes
- unsupported extension rejected client-side with a clear message (server still enforces)

**Implementation notes (as landed).**
- `uploadDocument` uses `XMLHttpRequest` with a `FormData` body (the browser sets the multipart boundary). HTTP errors go through the shared `parseError` and are thrown in the same `{ apiError, status }` shape as `request`, so `apiErrorOf` works; a network failure is status 0, and an aborted signal rejects with an `AbortError`. Only metadata keys that are provided are sent, so the server default (`UNKNOWN`) applies.
- Queue logic lives in `components/use-upload-queue.ts` (states `queued`, `uploading`, `done`, `failed`; at most 3 uploads at once; each file is its own request with its own `AbortController`; unmount aborts everything). `components/document-upload.tsx` is the drop zone, picker and queue list.
- Client validation (`validateUploadFile`: extension allow-list, empty file, size hint) is advisory. A rejected file appears in the queue as failed with its reason and no Retry, and no request is made. The size hint is `NEXT_PUBLIC_MAX_UPLOAD_BYTES` (default 250 MB, matching the API default) because the API does not expose its limit; set it to match a changed `MAX_UPLOAD_BYTES`.
- The optional per-batch document type (D8) shipped: it is captured when files are added and omitted from the request when it is Unclassified.
- A read-only 409 (`revision_read_only`, `archived_project`, `cancelled_project`) fails the file and every still-queued file without sending them, and calls `onReadOnly`. The workspace then shows the message, calls `router.refresh()` so the server recomputes the banner and `canMutate`, and reloads the list. The upload area renders only when `canMutate` is true.
- The list reloads each time a file completes. Duplicates are a non-blocking amber note on an uploaded file.

**Acceptance.** Manual check: drag 5 files (including one bad file and one duplicate) into a revision; each resolves independently; list updates; no folder UI anywhere. Verify the browser upload works from both `http://localhost:3000` and `http://127.0.0.1:3000` (CORS; no Next.js proxy is involved, so no body-size limit applies there).

**Size.** M.

---

### PR-14 — Document actions UI

**Goal.** Manual classification and the remaining revision-level actions. (§25 edit/remove/restore/reuse, §26 revision flow)

**Depends on.** PR-09 (APIs), PR-12.

**Scope.**
- `components/document-editor.tsx` (side panel or dialog): edit type (select with human labels; `UNKNOWN` shown as "Unclassified"), document number, description, notes; read-only display of immutable facts (filename, size, SHA-256, uploaded at, origin/inherited-from); disabled when `canMutate` is false or the row is REMOVED.
- Row actions: **Remove** (confirm dialog explaining it only removes the document from this revision), **Restore** (for Removed view), using the existing `confirm-dialog`, `dropdown-menu` primitives.
- `components/reuse-document-dialog.tsx`: "Add from another revision" — pick a source revision (same project), list its INCLUDED documents, multi-select, add via the reuse endpoint; documents already in this revision are shown disabled with a reason.
- Quick filter chips for the §12/§29 views: All, Uploaded, Inherited, Unclassified, Removed (mapped onto the existing query params).
- 409/404 handling consistent with PR-12/13.

**Out of scope.** Equipment grouping, folders.

**Tests.**
- editor submits only changed editable fields; immutable fields never sent; success updates the row
- remove → confirm → row leaves the default view and appears under Removed; restore reverses it
- reuse dialog: lists source documents, disables already-present ones, issues one request per selection, shows per-item failures
- controls hidden/disabled in read-only mode (SUPERSEDED, ARCHIVED, CANCELLED); allowed in PAUSED
- Unclassified chip filters to `document_type=UNKNOWN`

**Implementation notes (as landed).**
- Each row has a kebab menu next to Open and Download. An included row in a mutable revision offers Edit details and Remove from this revision; a removed row offers Restore; when `canMutate` is false the only item is View details. The menu never offers a mutation the server would refuse, but the server stays authoritative.
- `components/document-editor.tsx` is a modal. It sends only the fields the user changed (`changedFields`): text fields are trimmed and a blank one is sent as `null`, the type only when it differs, and nothing else is ever sent. Save stays disabled until something changes. The file facts (name, type, size, SHA-256, uploaded, added, origin with a link to the source revision) are display only. For a removed row or a read-only revision the same dialog opens as view-only with no Save.
- Remove asks for confirmation with the existing `ConfirmDialog`; Restore does not. Both, and Save, reload the list and show a one-line success message. The workspace status line now has three tones (success, warning, error).
- Failures share one path in the workspace: a read-only code (`isReadOnlyErrorCode`, now exported from `lib/documents.ts` and used by the upload queue too) shows the message, calls `router.refresh()` and reloads; any other 404/409 shows the message and reloads; anything else (for example a 422 on save) stays inline in the dialog.
- `components/reuse-document-dialog.tsx` ("Add from another revision", shown only when `canMutate`): pick a source revision of the same project (the current one is excluded), tick included documents, and Add. Documents already in this revision are matched by `document.id` against this revision's rows of every status and are disabled with a reason; a removed one says to restore it from the Removed view. Selections are sent one request at a time with only `source_revision_document_id`, so the server's copy of the source details is used, and each row shows Added or the server's message. If the server answers `document_already_in_revision` for a removed row, the row offers Restore using `existing_revision_document_id` from the 409 body. A read-only 409 stops the batch, marks the unsent rows as not added and goes through the workspace read-only path. Changing the source revision clears the selection.
- The quick filter chips (All, Uploaded, Inherited, Unclassified, Removed) are presets over the existing Type, Origin and View filters, not extra state: a chip is active when the filters equal its preset, clicking one keeps the typed search, and changing a dropdown by hand updates which chip is active. `SegmentedControl` gained an optional `label` (renders `role="group"`) so the View buttons can be told apart from the chips of the same name.
- No backend, migration or dependency change. The Edit PATCH goes from the browser to the API, so the same CORS origins as uploads apply.

**Acceptance.** Manual end-to-end walk-through of the §34 scenario entirely in the browser.

**Size.** M.

---

### PR-15 — Hardening, verification, and Phase 2 completion

**Goal.** Prove every requirement is met, correct documentation drift, and close the phase. (§31, §32, §36, §38)

**Depends on.** PR-00 … PR-14.

**Scope.**
- **Requirements audit:** walk spec §36 (definition of done) and §30 (tests); every bullet gets a test name or a recorded manual check in the PR description. Fill any gap with tests here.
- **Full-stack verification** on a clean checkout: `docker compose down -v && docker compose up --build`; migrate from empty and from a pre-Phase-2 volume with data; upload through the UI at `localhost:3000` and download via a presigned URL against `localhost:9000`; verify the bucket is private; run the §34 scenario manually.
- **Docs:** re-verify every Phase 2 statement in `README`, `ARCHITECTURE`, `DOCUMENT_PIPELINE`, `PROVENANCE`, `DEVELOPMENT`, `PHASE0_HANDOFF`; fix drift; finalize the "Intentional deviations and debt" list in `PROJECT_STATUS.md` (orphans, header-only PDF validation, no pagination, no audit trail, null actor columns, Phase 1 revision metadata editable when superseded, denormalized `project_id`, plus anything new).
- **ADR-004** → `Accepted`; set date; note any amendments.
- **`PROJECT_STATUS.md`:** Phase 0/1/2 complete; next phase Phase 3 described conceptually (not implemented); work-package list checked off; this plan's tracker completed.
- **Scope-creep review:** `git diff main` for Phase 3/AI/folders/equipment leakage (§4); confirm no `document_pages`, OCR, thumbnails, folder tables.
- Final gate: ruff, pytest, integration pytest on a throwaway DB (including the MinIO test), web lint/test/tsc/build.
- Produce the engineering handoff required by spec §38 (A–L) in the PR description.

**Out of scope.** Any Phase 3 work.

**Implementation notes (as landed).**
- The §30 and §36 audit found one gap (no test that no table can hold file bytes); `test_no_table_can_hold_file_content` was added. Everything else already had named tests; see the re-audit paragraph in section 9.
- Verified: `ruff`, `pytest` and `RUN_INTEGRATION=1 pytest` (including the real MinIO and migration tests) on a throwaway database, web lint, vitest, `tsc` and `next build`. A clean Compose stack (`down -v`, `up --build`) migrated from empty to `0004`, passed `/ready`, kept the bucket private (anonymous list and object GET refused), ran the §34 scenario over HTTP, served a presigned download from `localhost:9000`, and passed CORS preflights from both web origins. The `0003`-with-data upgrade and downgrade are covered by `tests/test_migration_0004.py`.
- Not done: a click-through of the web UI in a real browser (including PR-12 signed Open/Download, PR-13 drag-and-drop and PR-14 menus).
- Docs corrected: README, PHASE0_HANDOFF, ARCHITECTURE (adds the API and web surface), DEVELOPMENT (adds `CORS_ORIGINS`), PROVENANCE, the spec (deviations), ADR-004 (Accepted with amendments) and PROJECT_STATUS (Phase 2 complete, final debt list).

**Acceptance.** Every bullet in spec §36 is demonstrably true; CI green; the handoff report states only commands that were actually run.

**Size.** M (mostly verification and docs).

---

## 5. Traceability: spec to PR

### Spec sections

| Spec § | Topic | PR(s) |
| --- | --- | --- |
| §1 | Inspect repo, baseline | Done 2026-10-01 (`9a42b3b`); baseline recorded in PROJECT_STATUS |
| §3, §4 | Model principles, non-goals | PR-04 (model), PR-15 (scope review) |
| §5 | Revision lineage | PR-04, PR-07 |
| §6 | Revision creation, inheritance, atomicity | PR-07 |
| §7 | Document entity | PR-04, PR-08 |
| §8 | RevisionDocument entity | PR-04, PR-08, PR-09 |
| §9 | Document types | PR-02, PR-04 |
| §10 | Object storage abstraction | PR-05 |
| §11 | Storage keys | PR-02, PR-08 |
| §12 | No folders | PR-12, PR-14 (UI), PR-15 (review) |
| §13 | File validation | PR-02, PR-06 |
| §14 | Size and streaming | PR-05 (setting), PR-06 |
| §15 | Upload flow, failure handling | PR-08 |
| §16 | Duplicates | PR-08, PR-13 (warning) |
| §17 | Mutability | PR-07 (helper), PR-08, PR-09 |
| §18 | Concurrency / locking | PR-07, PR-08, PR-09 |
| §19 | Snapshot semantics | PR-07, PR-01 (ADR) |
| §20 | Remove / restore | PR-09 |
| §21 | API | PR-08 (list/upload/get), PR-09 (patch/remove/restore/reuse), PR-10 (download) |
| §22 | Services and domain package | PR-02, PR-07, PR-08 |
| §23 | Errors, IntegrityError mapping | PR-03, PR-06, PR-07, PR-08, PR-09 |
| §24 | Migration | PR-04 |
| §25 | Documents UI | PR-12, PR-13, PR-14 |
| §26 | Create Revision UI | PR-11 |
| §27 | Read-only UI | PR-12 (helper/banner), PR-13, PR-14 |
| §28 | Logging | PR-05 (formatter), PR-07, PR-08, PR-09 |
| §29 | Configuration | PR-05 |
| §30 | Testing | each PR; audited in PR-15 |
| §31, §32 | Documentation, status | PR-01 (drafted), each PR (drift), PR-15 (final) |
| §33, §34 | Hierarchy, workflow | PR-10 (e2e test), PR-14 (UI walk-through) |
| §36 | Definition of done | PR-15 |
| §37, §38 | Process, final report | this plan; PR-15 |

### Definition-of-done bullets (§36)

| Requirement | PR(s) |
| --- | --- |
| Phase 1 behavior still works | every PR (gate) |
| Migration applies cleanly (fresh and `0003` with data), downgrades | PR-04 |
| `Document` immutable; `RevisionDocument` revision-scoped | PR-04, PR-08, PR-09 |
| Cross-project rejected at service and database level | PR-04, PR-07, PR-08, PR-09 |
| Lineage immutable after creation | PR-07 |
| Storage through the abstraction (S3ObjectStorage with MinIO) | PR-05 |
| `put` never overwrites; bucket not public | PR-05, PR-10 (real MinIO check) |
| PDF/image uploads; content validated; extension and content agree | PR-06, PR-08 |
| SHA-256 generated; duplicates detected but allowed | PR-06, PR-08 |
| No files in PostgreSQL; stable machine-oriented keys | PR-02, PR-08 |
| Inheritance without copying objects; "no base" and "no carry-forward" supported | PR-07 |
| Atomic revision creation + inheritance, including `activate=true` | PR-07 |
| Revision metadata copied on inheritance | PR-07 |
| Existing document reusable in another revision | PR-09, PR-14 |
| Remove / restore at revision level | PR-09, PR-14 |
| Superseded packages read-only; backend enforced with re-check under lock | PR-07, PR-08, PR-09 |
| Signed downloads, revision-scoped, working from the browser in Docker | PR-05, PR-10, PR-12, PR-15 |
| Constraint-name IntegrityError mapping | PR-03, PR-07 |
| Multi-file upload as independent requests with per-file results and duplicate warnings | PR-13 |
| UI shows uploaded vs inherited, manual classification, lineage, read-only state | PR-11, PR-12, PR-14 |
| No folders / OCR / AI / pages / engineering model / analysis-tool logic | PR-15 (review) + every PR's out-of-scope list |
| Tests, lint, type checks pass | every PR; PR-15 |
| Docs updated; ADR-004; PROJECT_STATUS shows Phase 2 complete | PR-01, PR-15 |

---

## 6. Open decisions

Settle these in the PR named; record the outcome in that PR's description and, if lasting, in the spec/ADR.

| ID | Decision | Needed by | Proposed default |
| --- | --- | --- | --- |
| D1 | Which error does the "one ACTIVE revision" unique-index violation raise? Phase 1 reports it as `duplicate_revision_identifier`, which is misleading. | PR-03 | **Decided:** `RevisionNotActivatable` (409, code `revision_not_activatable`). Unmapped constraints are `UnexpectedIntegrityError` (500, `unexpected_integrity_error`). |
| D2 | If MinIO is unreachable at API startup, is that fatal? Is storage added to `/ready`? Does CI get a MinIO service? | PR-05 | **Decided in PR-05:** non-fatal (log a warning; uploads fail with `StorageUploadFailed`); `/ready` is unchanged; CI runs MinIO through a `docker run` step so the real-storage tests run there. |
| D3 | How does the pure domain package signal validation failures? | PR-02/PR-06 | **Decided in PR-02:** package-local `ValueError` subclasses (`InvalidFilename`, `UnsupportedExtension`). PR-06 maps them to `InvalidFileContent` / `UnsupportedDocumentType`. Long names are truncated (stem only, extension kept) rather than rejected. |
| D4 | Behavior when deleting a missing key in `ObjectStorage.delete`. | PR-05 | **Decided in PR-05:** idempotent no-op (cleanup paths must not raise on missing objects). |
| D5 | Exception/code for editing a REMOVED association. | PR-09 | **Decided and implemented in PR-09:** new `DocumentRemoved` (409, `document_removed`) rather than overloading another error. It is also used when the reuse source association is REMOVED. |
| D6 | Do reuse requests allow metadata overrides, or copy only? | PR-09 | **Decided and implemented in PR-09:** optional overrides, as in spec §21. A provided override replaces the copied value; an explicit `null` clears a text field. |
| D7 | Upload progress mechanism and concurrency in the UI. | PR-13 | `XMLHttpRequest`, concurrency 3, per-file retry. |
| D8 | Should the optional per-batch default document type ship? | PR-13 | Only if trivial; otherwise defer and note as follow-up. |
| D9 | Developer ergonomics: add a script that creates/migrates/drops a throwaway test DB (the manual recipe is in section 1)? | PR-05 | **Decided in PR-05:** skipped. The manual recipe in `docs/DEVELOPMENT.md` and the self-cleaning migration and storage tests cover the need. |
| D10 | Reuse of a document that already has a **REMOVED** association in the target revision. `UNIQUE (revision_id, document_id)` means the REMOVED row still occupies the slot. | PR-09 | Already reflected in PR-09 scope: reject with `DocumentAlreadyInRevision` (409) whose message tells the user to restore the existing association instead. Do not silently restore or create a second row. Confirm the UI offers a "Restore" action from that error. **Implemented in PR-09:** the 409 body also carries `existing_revision_document_id` and `existing_status`, so the UI (PR-14) can call restore without a lookup. |
| D11 | Archive/cancel do not serialize with document mutations. Spec §18 relies on activation updating revision rows, but `archive_project`/`cancel_project` take no row lock and touch no revision rows, so an upload can pass its locked re-check and commit just after the project is archived or cancelled (one extra document in a closed project). | PR-08 | **Decided:** shared project lock. Every document mutation takes `FOR SHARE` on the project row, then `FOR UPDATE` on the target revision row (lock order stays project → revision), and re-checks project and revision mutability after both locks. `archive_project` and `cancel_project` take `FOR UPDATE` on the project row before checking status. Activation already takes `FOR UPDATE`, so it also waits for in-flight mutations. Concurrent document mutations share the project lock and do not block each other. Rules that keep this deadlock-free: a document mutation never upgrades its project lock to `FOR UPDATE`, and nothing locks a revision row before its project row. Spec §18, ADR-004 #15, and the architecture and pipeline docs are updated to match. |

---

## 7. Intermediate-state compatibility

What a user of the running app sees while Phase 2 is only partly merged:

| After | Behavior |
| --- | --- |
| PR-04 | New tables exist but nothing uses them. Rebuild the API image: `models.py` now imports `powerforge_document_model` (new dependency in `services/api/pyproject.toml`), and the container runs `alembic upgrade head` at startup. |
| PR-05 | No user-visible change. Rebuild the API image (`boto3` is a new dependency). The API now checks the storage bucket at startup and logs the result; MinIO being down does not stop it from booting. New settings have local defaults; compose sets `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000`. |
| PR-06 | No user-visible change; nothing calls the new ingest and inspector code yet. Reinstall (`pip install -e services/api`) and rebuild the API image (`Pillow` is a new dependency). |
| PR-07 | Creating a revision **without** sending `based_on_revision_id` now defaults to the ACTIVE revision as base and carries forward its (currently empty) document set. Visible change: revisions record lineage, and revision responses gain `based_on_revision_id`, `based_on_identifier` and (on create only) `inherited_document_count`. Old UI keeps working. No new dependencies; rebuild the API image to pick up the code. |
| PR-08 | Documents can be uploaded only through the API (Swagger at `/docs`). Rebuild the API image (`Pillow`, `python-multipart`; `boto3` arrived in PR-05). `S3_PUBLIC_ENDPOINT_URL` is already set in `.env.example` and compose (PR-05). |
| PR-09 | Documents can now be edited (`PATCH`), removed, restored and reused in another revision, still only through the API (Swagger at `/docs`). No new dependencies or migrations; rebuild the API image to pick up the code. |
| PR-10 | Documents can be downloaded through `GET …/documents/{rdid}/download-url`, still only through the API (Swagger at `/docs`). The URL host is `S3_PUBLIC_ENDPOINT_URL`, so set it to `http://localhost:9000` under Docker Compose for the link to work from a browser. No new dependencies or migrations; rebuild the API image. |
| PR-11 | Web UI only: the Add Revision form gains Based on and Carry forward, and revisions show lineage. No backend, migration or dependency change; rebuild the web image to pick it up. |
| PR-12 | Web UI only: the revision page becomes the documents workspace (list, filter, open, download; no mutations until PR-13/14). Set `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000` under Docker Compose so signed links work from the browser; rebuild the web image. No backend, migration or dependency change. |
| PR-13 | Web UI only: upload area on the revision page (drag and drop, up to 3 uploads at once). Uploads go from the browser straight to the API, so `CORS_ORIGINS` must include the origin you open the web app from (`http://localhost:3000` and `http://127.0.0.1:3000` are set by default). Optional `NEXT_PUBLIC_MAX_UPLOAD_BYTES` for the size hint; rebuild the web image. No backend, migration or dependency change. |
| PR-14 | Web UI only: row menu (edit details, remove, restore), Add from another revision, and quick filter chips on the revision page. Edits are PATCH requests from the browser, so the existing `CORS_ORIGINS` setting applies; rebuild the web image. No backend, migration or dependency change. |
| PR-15 | Docs and one extra test only. After pulling, run `docker compose down -v && docker compose up --build` if you want a clean stack; no migration, dependency or setting changes. |

Never merge a PR that requires a later PR to avoid breaking existing flows. After PR-04 and every PR that adds dependencies, rebuild the API image (`docker compose up --build`) and re-run migrations.

---

## 8. Risks

| Risk | Mitigation |
| --- | --- |
| Composite FKs with nullable columns behave unexpectedly (MATCH SIMPLE) | Explicit tests in PR-04 for null and non-null cases |
| Alembic enum creation conflicts with ORM `create_type=False` | Mirror the existing `0002` enum approach; test fresh upgrade and downgrade |
| Deadlocks from inconsistent lock order | Single documented order (project → revision), centralised in `revision_documents.py`; document mutations take the project lock `FOR SHARE` and never upgrade it (D11); concurrency tests in PR-07/PR-08 |
| Pillow decoding large TIFFs is slow or memory-hungry | Header-only dimension check before any decode; `verify()` only; no full decode in Phase 2; pixel cap configurable |
| Large uploads exhaust memory in tests or prod | Spooled temp file; streaming hash; test asserts bounded reads |
| Presigned URLs unusable from the browser in Docker | `S3_PUBLIC_ENDPOINT_URL`; verified in PR-10 (MinIO test) and PR-15 (clean Compose stack, over HTTP); a click-through in a real browser was not performed |
| Non-ASCII filenames break `Content-Disposition` | RFC 5987 helper and test in PR-05 |
| Integration tests pollute the dev database | Always use the throwaway DB recipe; never run `RUN_INTEGRATION=1` against `powerforge` |
| Circular service dependencies | Shared helper module (PR-07); `DocumentService` and `RevisionService` never import each other; import-cycle check in review |
| PRs grow past reviewable size (PR-07, PR-08 are L) | Split along the seams noted in each PR if review stalls; do not skip the required tests to shrink |
| Scope creep toward Phase 3 (thumbnails, page counts, OCR) | Out-of-scope lists per PR; scope review in PR-15 |

---

## 9. Coverage audit and intentional exclusions

**Audit (2026-10-02).** Every spec section (§1–§38), every test group in spec §30, every bullet of the §36 definition of done, and every constraint/setting/exception name introduced by the spec were checked against the PR scopes and test lists. Gaps found and fixed in this plan: concurrent-duplicate constraint mapping (PR-09), invalid `document_type` form value and CORS preflight tests (PR-08), `uploaded_by`/`added_by` null behavior and the stale OpenAPI description (PR-08), the `integration` marker description (PR-05), and explicit mapping of the "By Document Type" view (PR-12). **Re-audit in PR-15 (2026-10-06).** Every test group in spec §30 and every §36 bullet was mapped to named tests (backend `tests/`, web `apps/web/src`) or to a manual or live check. One gap was found and closed: nothing asserted that no table can hold file bytes, so `test_no_table_can_hold_file_content` was added (and shown to fail when a binary column is added). The §34 scenario is covered by `tests/test_phase2_workflow.py` and was also run over HTTP against a clean Compose stack. Not covered by automation: a click-through in a real browser (recorded as not performed in PROJECT_STATUS).

**Intentionally not covered by any PR** (documented as debt or non-goals, spec §4 and §32):

- Document garbage collection / hard delete; orphaned-object sweeper
- Pagination of document lists
- Authentication, users, per-actor audit (`uploaded_by`/`added_by`/`removed_by` stay null)
- Full pixel decoding or polyglot-file detection (Phase 3 and beyond)
- Folders, DocumentPackage/submission entities, equipment grouping
- OCR, thumbnails, page rendering, AI classification, extraction, engineering model, ETAP/SKM/EasyPower
- Browser end-to-end (Playwright/Cypress) automation: UI behavior is covered by vitest component tests plus the manual walk-throughs in PR-12, PR-14, and PR-15

**Deliberately left to existing mechanisms rather than a PR:** operator guidance about reverse-proxy body limits (already in `docs/DEVELOPMENT.md`), and per-PR documentation upkeep (working agreement 5).
