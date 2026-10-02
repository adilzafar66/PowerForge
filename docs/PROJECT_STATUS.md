# Project status

Living status of PowerForge phases. Update this file when a phase is specified, started, or completed. Do not treat chat history as the source of truth.

**Current implemented phase:** 1  
**Next phase:** 2 (document management) — not started

## Phase 0 — Architecture and repository setup

**Status:** Complete (2026-09-02)

Runnable skeleton: FastAPI health/readiness, PostgreSQL + Alembic (`pgcrypto`), Redis, MinIO, Celery worker heartbeats, Next.js stack status UI, CI.

Details, environment notes, and verification: [PHASE0_HANDOFF.md](PHASE0_HANDOFF.md).

## Phase 1 — Project and revision management

**Status:** Complete (2026-09-03)

Implementation spec: `cursor/PHASE1_SPECS.txt`  
Decisions: [ADR-003](../decisions/ADR-003-project-revision-model.md)

Delivered:

- `packages/project` (`powerforge_project`) — status enums and transition helper
- PostgreSQL tables `projects` and `project_revisions` (Alembic `0002_projects_and_revisions`, `0003_status_before_archive`)
- REST API under `/api/projects` and nested revisions (create/list/get/patch + pause/resume/cancel/archive/unarchive + activate)
- Web UI: `/` project list, `/projects/new`, `/projects/[id]`, revision placeholder, `/status` stack health
- Backend and frontend tests covering lifecycle, uniqueness, and concurrent activate

## Later phases

| Phase | Work | Status |
| --- | --- | --- |
| 2 | Document management | Not started |
| 3 | Document processing | Not started |
| 4 | Document classification | Not started |
| 5 | Engineering model persistence | Not started |
| 6–13 | Extraction through export | Not started |

Authentication, a users table, and project-level access control are required by the product spec and are **not** part of Phase 0 or Phase 1. `created_by` remains nullable until then.

ETAP / SKM / EasyPower integration is not part of these phases.
