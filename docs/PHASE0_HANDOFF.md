# Phase 0 handoff

Read this before changing code. This file is the continuation context for a new agent or machine. Cursor chat history is **not** in git and will not follow a clone.

**Status:** Phase 0, Phase 1 and Phase 2 are implemented. Full-stack runtime was verified on a second machine (macOS + Colima) on 2026-09-02 (Phase 0). Phase 1 projects/revisions shipped 2026-09-03.

Living phase status: [PROJECT_STATUS.md](PROJECT_STATUS.md).

**Phase 2 (document management):** implemented; specified in `cursor/phase2_specs.txt`, decided in [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md) (Accepted), and recorded in [PROJECT_STATUS.md](PROJECT_STATUS.md). Do not start Phase 3 as a side effect of other work.

## Agent instructions

1. Read [ARCHITECTURE.md](ARCHITECTURE.md).
2. Read the relevant domain docs for the work you were asked to do.
3. Inspect existing code. Do not invent a second layout.
4. Stay inside the requested phase. Do not implement OCR, AI extraction, SLD recognition, ETAP/SKM/EasyPower, electrical calculations, or report generation.
5. Follow the phase process in `cursor/specification.txt` §36 when implementing a named phase. For Phase 1 details see `cursor/phase1_specs.txt` (complete); for Phase 2 see `cursor/phase2_specs.txt`.
6. After architectural changes: explain, list affected modules, update docs (including [PROJECT_STATUS.md](PROJECT_STATUS.md)), add an ADR if the decision is significant.

Product specification (source of truth for product scope): `cursor/specification.txt`.
Phase 1 implementation spec: `cursor/phase1_specs.txt` (implemented).  
Phase 2 implementation spec: `cursor/phase2_specs.txt` (implemented).

## Product (one paragraph)

PowerForge ingests electrical engineering documents and produces a centralized, traceable engineering model. AI proposes candidates. The engineer is the authority. Original documents are immutable evidence. The verified engineering model must not depend on a specific AI vendor or on ETAP/SKM/EasyPower.

## Repository

| Item | Value |
| --- | --- |
| GitHub | https://github.com/adilzafar66/PowerForge.git |
| Default branch | `main` |
| First published commit | `43c1ce1` (`first commit`) — this handoff may be a later commit |
| Spec | `cursor/specification.txt` |
| Phase 1 spec | `cursor/phase1_specs.txt` (implemented) |
| Phase 2 spec | `cursor/phase2_specs.txt` (implemented) |

## What Phase 0 delivered

### Documentation

- `docs/ARCHITECTURE.md` — system map, module boundaries, stack, Phase 0 vs later
- `docs/ENGINEERING_MODEL.md` — equipment concept, attributes, states, revisions
- `docs/DOCUMENT_PIPELINE.md` — async pipeline, classification vocab, workers
- `docs/EXTRACTION.md` — specialized extractors, provider abstraction, prompts
- `docs/TOPOLOGY.md` — graph model; SLD is evidence, not the database
- `docs/VALIDATION.md` — deterministic rules vs reconciliation vs review
- `docs/PROVENANCE.md` — evidence contract
- `docs/REVIEW_WORKFLOW.md` — engineer queue, conflicts, safety states
- `docs/CODING_STANDARDS.md`
- `docs/DEVELOPMENT.md` — how to run
- `docs/PROJECT_STATUS.md` — living phase status (Phase 1 complete)
- `decisions/ADR-001-engineering-model-independence.md` — **accepted**
- `decisions/ADR-002-phase-0-technology-stack.md` — **accepted**
- `decisions/ADR-003-project-revision-model.md` — **accepted** (Phase 1)

### Layout (do not collapse into a monolith)

```
apps/web                      Next.js App Router, Tailwind v4, shadcn-style Button/Card
services/api                  FastAPI health/readiness, SQLAlchemy, Alembic on startup (Docker)
services/document-worker      Celery heartbeat only
services/extraction-worker    Celery heartbeat only
services/validation-worker    Celery heartbeat only
packages/shared               Settings + JSON logging
packages/project              ProjectStatus, RevisionStatus, transitions
packages/engineering-model    EquipmentType, InformationState, VerificationState
packages/document-model       Document vocabulary (classification, origin, status, file formats), filename and storage-key rules
packages/extraction           ExtractionMethod
packages/topology             NodeKind
packages/validation           Empty RuleRegistry
packages/provenance           EvidenceRef (Pydantic contract, no tables)
packages/ai                   LLMProvider / VisionProvider / OCRProvider Protocols; no vendor SDKs
packages/ai/prompts           README only; no production prompts
database/                     Alembic; `0001_enable_extensions` (pgcrypto), `0002_projects_and_revisions`, `0003_status_before_archive`, `0004_documents_and_lineage`
.github/workflows/ci.yml      Ruff, Pytest + Postgres/Redis services, Next lint/test/build
docker-compose.yml            postgres, redis, minio, minio-init, api, web, three workers
```

Python import names use the `powerforge_*` prefix (for example `powerforge_api`, `powerforge_shared`). Workers use `document_worker`, `extraction_worker`, `validation_worker`.

### API (Phase 0 + Phase 1)

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health`, `/api/health` | Liveness. No DB. 200 `{status, service, version}` |
| GET | `/ready`, `/api/ready` | Database required. Redis optional. 503 if DB down; 200 `degraded` if Redis down; 200 `ok` if both up |
| POST/GET/PATCH | `/api/projects...` | Project and revision management (Phase 1). See OpenAPI `/docs`. |

CORS origins from `CORS_ORIGINS` (default `http://localhost:3000`). Pydantic response models; ORM is not exposed.

SQLAlchemy 2 **sync** engine, `psycopg` v3, `connect_timeout=2` so `/ready` does not hang when Postgres is absent.

### Web

- Project list at `/` (Phase 1)
- Stack status dashboard at `/status`
- Server-side fetch uses `API_INTERNAL_URL` (Docker: `http://api:8000`)
- Browser refresh uses `NEXT_PUBLIC_API_URL` (host: `http://localhost:8000`)
- `export const dynamic = "force-dynamic"` so CI `next build` does not require a live API

### Database

- `projects` and `project_revisions` (Phase 1). Equipment tables are Phase 5.
- Alembic: `database/alembic.ini`, `database/env.py`, migrations through `0002_projects_and_revisions`
- Run: `alembic -c database/alembic.ini upgrade head`
- Docker API image runs migrations on start

### Tests (verified 2026-09-02 on macOS)

- Pytest: **20 passed** with `RUN_INTEGRATION=1` (live Postgres)
- Ruff: clean (`known-first-party` configured in root `pyproject.toml`)
- Vitest: `apps/web/src/lib/health.test.ts` passed
- `next lint` and `next build` passed

Install for tests:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e packages/shared -e packages/project -e packages/engineering-model -e packages/document-model -e packages/extraction -e packages/topology -e packages/validation -e packages/provenance -e packages/ai -e services/api -e services/document-worker -e services/extraction-worker -e services/validation-worker
ruff check .
pytest
cd apps/web && npm install && npm test && npm run lint
```

Note: `docs/DEVELOPMENT.md` mentions `pip install -e ".[dev]"`; that extra is **not** defined. Use `requirements-dev.txt` plus the editable installs above. `scripts/install-dev.ps1` matches this.

## Architectural decisions to keep

Do not reverse these without an ADR:

- Engineering model has **no** AI vendor SDK and **no** ETAP/SKM/EasyPower types ([ADR-001](../decisions/ADR-001-engineering-model-independence.md)).
- Sync SQLAlchemy 2; Celery + Redis; MinIO locally; Python domain packages; Next.js App Router; Compose as the full-stack path ([ADR-002](../decisions/ADR-002-phase-0-technology-stack.md)).
- One `ProjectRevision` entity; documents and the engineering model attach to it later. No fake auth or users table in Phase 1 ([ADR-003](../decisions/ADR-003-project-revision-model.md)).
- Common `Equipment` + typed attributes; hybrid relational + JSONB; never one JSON blob for the project.
- Attribute-level provenance and confidence; explicit information states; never silently resolve conflicts; never silently promote `AI_EXTRACTED` to `ENGINEER_VERIFIED`.
- Source priority is configuration, not hard-coded universal rules.
- Workers and API may depend on domain packages. Domain packages must not depend on FastAPI, Celery, Next.js, or vendor AI SDKs.

## What was verified on the original PC (2026-09-02)

Environment: Windows 10, Python 3.12.10, **no admin**, **no Docker**, **no WSL**, **no local PostgreSQL**, **no Redis**.

Node.js LTS 24.19.0 was installed with `winget --scope user` (no elevation). After install, `node` may require a new shell so PATH includes the WinGet package directory.

Ran natively:

- API: `uvicorn powerforge_api.main:app --host 127.0.0.1 --port 8000 --app-dir services/api/src`
- Web: `apps/web` `npm run dev` on port 3000

Confirmed over HTTP:

- `GET /health` → 200 `powerforge-api` `0.1.0`
- `GET /ready` → 503 `database: unavailable`, `redis: unavailable` (correct without those services)
- `GET http://localhost:3000/` → 200; HTML showed API ok (`powerforge-api 0.1.0`) and PostgreSQL/Redis unavailable

Browser MCP was not available; UI was checked via HTTP, not click-through in a browser.

## What got blocked on the original PC (now unblocked)

These were environment gaps, not missing code. They were completed on the second machine (see below). Do **not** “unblock” by switching the engineering database to SQLite. The spec requires PostgreSQL.

| Item | Original PC | Second machine (2026-09-02) |
| --- | --- | --- |
| Docker Compose full stack | Docker Desktop not installed; install needed admin | Colima + Docker CLI via Homebrew; `docker compose up --build -d` healthy |
| PostgreSQL locally | No server | Homebrew `postgresql@16` (used for native Alembic/tests) and Compose `postgres` |
| Redis locally | Same | Homebrew `redis` and Compose `redis` |
| MinIO locally | Same | Homebrew `minio` (bucket `powerforge`) and Compose `minio` + `minio-init` |
| Celery workers actually running | Need Redis | Native `document-worker` heartbeat returned `ok`; Compose workers start and connect to Redis |
| Live Alembic against Postgres | No database | `alembic -c database/alembic.ini upgrade head` → `0001_enable_extensions`; Compose API repeats this on start |
| `RUN_INTEGRATION=1` pytest | No Postgres | 20 passed, including `test_postgres_accepts_select` |
| WSL | Not installed | N/A on macOS; not required when Colima/Docker works |

## First actions on a machine that can run Docker

```bash
git clone https://github.com/adilzafar66/PowerForge.git
cd PowerForge
cp .env.example .env   # Windows: Copy-Item .env.example .env
docker compose up --build
```

Expect:

- http://localhost:3000 — project list (Phase 1). Stack status at `/status`.
- http://localhost:8000/ready — `status: ok` if both DB and Redis are up
- http://localhost:8000/docs
- http://localhost:9001 — MinIO console (`powerforge` / `powerforge_minio`)

Then run tests (CI already does this on GitHub with service containers):

```bash
pytest
cd apps/web && npm ci && npm test && npm run lint && npm run build
```

If `/ready` is still unavailable after Compose is healthy, check API logs for `DATABASE_URL` (container must use host `postgres`, not `localhost`). Compose already overrides this for the `api` service.

## Explicitly not implemented (later phases)

| Phase | Work |
| --- | --- |
| 1 | Projects, revisions, project list at `/` — **complete** |
| 2 | Upload, object storage, document management — **complete** (a document viewer in the browser is limited to signed Open/Download links; page rendering is Phase 3) |
| 3 | PDF processing, OCR, artifacts |
| 4 | Classification + manual correction |
| 5 | Equipment entities, attributes, connections, provenance persistence |
| 6–13 | Extraction, entity resolution, SLD, reconciliation, validation rules, review UI, topology viz, export |

Auth is documented as required later. Phase 0 and Phase 1 APIs are local/open. Do not add a fake auth system or users table in Phase 1. `created_by` stays nullable until authentication exists.

## Gotchas

- `/ready` used to hang for a long TCP timeout when nothing listened on 5432. Fixed with `connect_args={"connect_timeout": 2}` in `powerforge_api.db.get_engine`.
- Web in Docker must use `API_INTERNAL_URL=http://api:8000` for server-side fetches; the browser still uses `http://localhost:8000`.
- Domain packages are vocabulary/contracts only. Phase 1 added `packages/project` (enums/schemas only) and SQLAlchemy project tables/services in `services/api`. Do not add SQLAlchemy equipment models in domain packages; equipment is Phase 5.
- Prompts go in `packages/ai/prompts/` and must be versioned when extraction exists. Do not bury prompts in random files.
- OneDrive path of the original workspace contained spaces (`OneDrive - Resa Power, LLC`). Quote paths in scripts.
- Homebrew `postgresql@16` and Compose both want host port **5432**. Homebrew `redis` and Compose both want **6379**. Stop the Homebrew services before `docker compose up`, or Compose will fail to bind. To restore the host Postgres (e.g. other local databases) after tearing down Compose: `docker compose down` then `brew services start postgresql@16`.
- Homebrew Docker needs the Compose plugin on PATH. If `docker compose` is unknown, add `cliPluginsExtraDirs: ["/opt/homebrew/lib/docker/cli-plugins"]` to `~/.docker/config.json`, or use `docker-compose`.
- Phase 0 workers share the default Celery queue `celery`. A heartbeat published by one worker can be consumed by another, which then logs `NotRegistered`. Workers are running; dedicated queues belong in a later worker-hardening change, not Phase 1.

## What was verified on the second machine (2026-09-02)

Environment: macOS 15.6 (darwin 24.6.0, arm64), Homebrew, Python 3.12.14, Node 24.16.0, Docker 29.7.2 via **Colima** (not Docker Desktop), PostgreSQL 16.15 (Homebrew, later stopped so Compose could bind 5432).

Brought up:

```bash
cp .env.example .env
docker compose up --build -d
```

Confirmed over HTTP:

| URL | Result |
| --- | --- |
| `GET http://localhost:8000/health` | 200 `powerforge-api` `0.1.0` |
| `GET http://localhost:8000/ready` | 200 `status: ok`, `database: ok`, `redis: ok` |
| `GET http://localhost:8000/docs` | 200 |
| `GET http://localhost:3000/` | 200; HTML showed **Stack ready**, API `powerforge-api 0.1.0`, PostgreSQL ok, Redis ok |
| `http://localhost:9000/minio/health/live` | 200 |
| `http://localhost:9001` | 200 MinIO console |

Also confirmed:

- Compose `minio-init` created bucket `powerforge` and exited 0
- Compose API ran `alembic upgrade head` (`0001_enable_extensions`, `pgcrypto`)
- Compose workers logged `ready` and connected to `redis://redis:6379/0`
- Native path before Compose: Alembic against Homebrew Postgres, MinIO bucket create, document-worker heartbeat `{'status': 'ok', 'worker': 'document-worker'}`, `/ready` 200 with database and Redis ok

Browser MCP was not available; the status page was checked via the rendered HTML (including the Refresh control and the three service cards). Click-through in a real browser was not performed.

## Suggested first message to a new agent

> Read `docs/PROJECT_STATUS.md`, `docs/PHASE0_HANDOFF.md`, and `docs/ARCHITECTURE.md`. Phase 0, Phase 1 and Phase 2 are done. Compose may already be running. Confirm `/ready` is ok. Do not start Phase 3 unless I ask.
