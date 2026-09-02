# Phase 0 handoff

Read this before changing code. This file is the continuation context for a new agent or machine. Cursor chat history is **not** in git and will not follow a clone.

**Status:** Phase 0 implemented in the repository. Full-stack runtime (PostgreSQL, Redis, MinIO, workers) was **not** verified on the original development PC because that machine had no admin rights and no Docker.

**Next phase:** Phase 1 (project management) only when explicitly requested. Do not start Phase 1 as a side effect of unblocking Docker.

## Agent instructions

1. Read [ARCHITECTURE.md](ARCHITECTURE.md).
2. Read the relevant domain docs for the work you were asked to do.
3. Inspect existing code. Do not invent a second layout.
4. Stay inside the requested phase. Do not implement OCR, AI extraction, SLD recognition, ETAP/SKM/EasyPower, electrical calculations, or report generation.
5. Follow the phase process in `cursor_specification.txt` §36 when implementing a named phase.
6. After architectural changes: explain, list affected modules, update docs, add an ADR if the decision is significant.

Product specification (source of truth for scope): `cursor_specification.txt` at the repo root.

## Product (one paragraph)

PowerForge ingests electrical engineering documents and produces a centralized, traceable engineering model. AI proposes candidates. The engineer is the authority. Original documents are immutable evidence. The verified engineering model must not depend on a specific AI vendor or on ETAP/SKM/EasyPower.

## Repository

| Item | Value |
| --- | --- |
| GitHub | https://github.com/adilzafar66/PowerForge.git |
| Default branch | `main` |
| First published commit | `43c1ce1` (`first commit`) — this handoff may be a later commit |
| Spec | `cursor_specification.txt` |

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
- `decisions/ADR-001-engineering-model-independence.md` — **accepted**
- `decisions/ADR-002-phase-0-technology-stack.md` — **accepted**

### Layout (do not collapse into a monolith)

```
apps/web                      Next.js App Router, Tailwind v4, shadcn-style Button/Card
services/api                  FastAPI health/readiness, SQLAlchemy, Alembic on startup (Docker)
services/document-worker      Celery heartbeat only
services/extraction-worker    Celery heartbeat only
services/validation-worker    Celery heartbeat only
packages/shared               Settings + JSON logging
packages/engineering-model    EquipmentType, InformationState, VerificationState
packages/document-model       DocumentClassification
packages/extraction           ExtractionMethod
packages/topology             NodeKind
packages/validation           Empty RuleRegistry
packages/provenance           EvidenceRef (Pydantic contract, no tables)
packages/ai                   LLMProvider / VisionProvider / OCRProvider Protocols; no vendor SDKs
packages/ai/prompts           README only; no production prompts
database/                     Alembic; revision 0001_enable_extensions (pgcrypto)
.github/workflows/ci.yml      Ruff, Pytest + Postgres/Redis services, Next lint/test/build
docker-compose.yml            postgres, redis, minio, minio-init, api, web, three workers
```

Python import names use the `powerforge_*` prefix (for example `powerforge_api`, `powerforge_shared`). Workers use `document_worker`, `extraction_worker`, `validation_worker`.

### API (Phase 0)

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health`, `/api/health` | Liveness. No DB. 200 `{status, service, version}` |
| GET | `/ready`, `/api/ready` | Database required. Redis optional. 503 if DB down; 200 `degraded` if Redis down; 200 `ok` if both up |

CORS origins from `CORS_ORIGINS` (default `http://localhost:3000`). Pydantic response models; ORM is not exposed.

SQLAlchemy 2 **sync** engine, `psycopg` v3, `connect_timeout=2` so `/ready` does not hang when Postgres is absent.

### Web (Phase 0)

- Status dashboard at `/`
- Server-side fetch uses `API_INTERNAL_URL` (Docker: `http://api:8000`)
- Browser refresh uses `NEXT_PUBLIC_API_URL` (host: `http://localhost:8000`)
- `export const dynamic = "force-dynamic"` so CI `next build` does not require a live API

### Database

- No project/equipment tables yet (those are Phase 1 and Phase 5).
- Alembic: `database/alembic.ini`, `database/env.py`, `database/migrations/0001_enable_extensions.py`
- Run: `alembic -c database/alembic.ini upgrade head`
- Docker API image runs migrations on start

### Tests (last run on the original PC)

- Pytest: 19 passed, 1 skipped (`tests/test_db_integration.py` unless `RUN_INTEGRATION=1`)
- Ruff: clean (`known-first-party` configured in root `pyproject.toml`)
- Vitest: `apps/web/src/lib/health.test.ts` passed
- `next lint` and `next build` passed

Install for tests:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e packages/shared -e packages/engineering-model -e packages/document-model -e packages/extraction -e packages/topology -e packages/validation -e packages/provenance -e packages/ai -e services/api -e services/document-worker -e services/extraction-worker -e services/validation-worker
ruff check .
pytest
cd apps/web && npm install && npm test && npm run lint
```

Note: `docs/DEVELOPMENT.md` mentions `pip install -e ".[dev]"`; that extra is **not** defined. Use `requirements-dev.txt` plus the editable installs above. `scripts/install-dev.ps1` matches this.

## Architectural decisions to keep

Do not reverse these without an ADR:

- Engineering model has **no** AI vendor SDK and **no** ETAP/SKM/EasyPower types ([ADR-001](../decisions/ADR-001-engineering-model-independence.md)).
- Sync SQLAlchemy 2; Celery + Redis; MinIO locally; Python domain packages; Next.js App Router; Compose as the full-stack path ([ADR-002](../decisions/ADR-002-phase-0-technology-stack.md)).
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

## What got blocked (environment, not missing code)

These are **not** incomplete Phase 0 features in git. Compose files, worker Dockerfiles, MinIO init, and CI Postgres/Redis services already exist.

| Blocked | Why | Unblock |
| --- | --- | --- |
| Docker Compose full stack | Docker Desktop not installed; install needs admin | Install Docker Desktop (or equivalent) with elevation, then `docker compose up --build` |
| PostgreSQL locally | No server; winget machine install needs admin | Compose `postgres` service, or install PostgreSQL 16+ |
| Redis locally | Same | Compose `redis` service |
| MinIO locally | Same | Compose `minio` + `minio-init` |
| Celery workers actually running | Need Redis | After Redis: workers start via Compose or `celery -A document_worker.celery_app worker` |
| Live Alembic against Postgres | No database | After Postgres: `alembic -c database/alembic.ini upgrade head` |
| `RUN_INTEGRATION=1` pytest | No Postgres | After Postgres: set `DATABASE_URL` and `RUN_INTEGRATION=1` |
| WSL | Not installed; `wsl --install` needs admin | Optional; not required if Docker Desktop works |

Do **not** “unblock” by switching the engineering database to SQLite. The spec requires PostgreSQL.

## First actions on a machine that can run Docker

```bash
git clone https://github.com/adilzafar66/PowerForge.git
cd PowerForge
cp .env.example .env   # Windows: Copy-Item .env.example .env
docker compose up --build
```

Expect:

- http://localhost:3000 — status page, API/Postgres/Redis ok (or degraded only if Redis failed)
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
| 1 | Projects, revisions, project dashboard |
| 2 | Upload, object storage usage, document viewer |
| 3 | PDF processing, OCR, artifacts |
| 4 | Classification + manual correction |
| 5 | Equipment entities, attributes, connections, provenance persistence |
| 6–13 | Extraction, entity resolution, SLD, reconciliation, validation rules, review UI, topology viz, export |

Auth is documented as required later. Phase 0 API is local/open. Do not add a fake auth system unless a later phase asks for it.

## Gotchas

- `/ready` used to hang for a long TCP timeout when nothing listened on 5432. Fixed with `connect_args={"connect_timeout": 2}` in `powerforge_api.db.get_engine`.
- Web in Docker must use `API_INTERNAL_URL=http://api:8000` for server-side fetches; the browser still uses `http://localhost:8000`.
- Domain packages are vocabulary/contracts only. Do not add SQLAlchemy equipment models in those packages during Phase 1 unless Phase 1 truly needs them; Phase 1 is **projects and revisions**, not equipment.
- Prompts go in `packages/ai/prompts/` and must be versioned when extraction exists. Do not bury prompts in random files.
- OneDrive path of the original workspace contained spaces (`OneDrive - Resa Power, LLC`). Quote paths in scripts.

## Suggested first message to a new agent

> Read `docs/PHASE0_HANDOFF.md` and `docs/ARCHITECTURE.md`. Phase 0 is done in the repo. This machine should have Docker. Bring up `docker compose up --build`, confirm `/ready` is ok, run tests. Do not start Phase 1 unless I ask.
