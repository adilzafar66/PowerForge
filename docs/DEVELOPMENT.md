# Local development

Phase 0 delivers a runnable skeleton: API health/readiness, PostgreSQL, Redis, MinIO, Celery heartbeats, and a Next.js status page.

## Prerequisites

- Python 3.12
- Node.js 22+ (LTS)
- Docker Desktop (recommended) **or** a local PostgreSQL 16+ instance

## Environment

Copy `.env.example` to `.env` in the repository root. The API and workers read `DATABASE_URL`, `REDIS_URL`, and S3 settings from the environment.

## Option A — Docker Compose (full stack)

From the repository root:

```bash
docker compose up --build
```

| Service | URL |
| --- | --- |
| Web | http://localhost:3000 |
| API health | http://localhost:8000/health |
| API ready | http://localhost:8000/ready |
| API docs | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |

The web container talks to the API at `API_INTERNAL_URL` (`http://api:8000`). The browser uses `NEXT_PUBLIC_API_URL` (`http://localhost:8000`).

Apply migrations (first run, from another shell):

```bash
docker compose exec api alembic upgrade head
```

Compose also runs `alembic upgrade head` on API startup.

## Option B — Native API + web (Windows / local Python)

Start PostgreSQL (Docker-only database is enough):

```bash
docker compose up postgres redis minio -d
```

If Docker is unavailable, install PostgreSQL locally and set `DATABASE_URL` in `.env`. Redis is required only for Celery workers; the API `/health` endpoint does not require it. `/ready` reports database (required) and Redis (optional) status.

Create a virtualenv and install the workspace:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e packages/shared -e packages/engineering-model -e packages/document-model -e packages/extraction -e packages/topology -e packages/validation -e packages/provenance -e packages/ai -e services/api
pip install -e ".[dev]"
```

If the root `[dev]` extra is not used, install test tools:

```bash
pip install -r requirements-dev.txt
```

Migrate and run:

```bash
alembic upgrade head
uvicorn powerforge_api.main:app --reload --app-dir services/api/src --port 8000
```

Web:

```bash
cd apps/web
npm install
npm run dev
```

Workers (optional, need Redis):

```bash
celery -A document_worker.celery_app worker --loglevel=info
```

(from `services/document-worker` with `PYTHONPATH` including that service’s `src`).

## Tests

```bash
ruff check .
pytest
cd apps/web && npm test
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs Ruff, Pytest (with PostgreSQL service), and the Next.js lint/test job.
