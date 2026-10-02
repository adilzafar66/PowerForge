# Local development

Phase 0 delivered a runnable skeleton: API health/readiness, PostgreSQL, Redis, MinIO, Celery heartbeats, and a Next.js status page.

Phase 1 adds project and revision management. Routes:

| Path | Purpose |
| --- | --- |
| `/` | Project list |
| `/projects/new` | Create project |
| `/projects/[id]` | Project detail and revisions |
| `/projects/[id]/revisions/[revisionId]` | Revision workspace placeholder |
| `/status` | Stack health (API / PostgreSQL / Redis) |

API: `http://localhost:8000/api/projects` (see OpenAPI at `/docs`).

Phase 2 (in progress; see [PROJECT_STATUS.md](PROJECT_STATUS.md)) adds document management. The revision workspace route above becomes the revision documents page, and the API gains `.../revisions/{revisionId}/documents` routes. See [Phase 2 configuration](#phase-2-configuration-document-storage).

## Prerequisites

- Python 3.12
- Node.js 22+ (LTS)
- Docker Desktop or Colima + Docker CLI (recommended) **or** a local PostgreSQL 16+ instance

If Homebrew already runs `postgresql@16` or `redis`, stop those services before Compose. They occupy the same host ports (5432 and 6379) that `docker-compose.yml` publishes.

## Environment

Copy `.env.example` to `.env` in the repository root. The API and workers read `DATABASE_URL`, `REDIS_URL`, and S3 settings from the environment.

## Phase 2 configuration (document storage)

These settings are introduced by Phase 2 and are read through `powerforge_shared.config.Settings`. Existing `S3_*` names are unchanged. Add the new ones to `.env` and `docker-compose.yml` when implementing; they have defaults for local use.

| Variable | Default | Purpose |
| --- | --- | --- |
| `S3_ENDPOINT_URL` | `http://localhost:9000` (compose: `http://minio:9000`) | Endpoint the API uses to talk to object storage (scheme included) |
| `S3_PUBLIC_ENDPOINT_URL` | falls back to `S3_ENDPOINT_URL` | Endpoint the **browser** can reach; presigned download URLs are signed against it. In Docker Compose the API reaches MinIO at `http://minio:9000`, which a browser cannot, so set this to `http://localhost:9000` |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | dev defaults | Storage credentials (never sent to the browser) |
| `S3_BUCKET`, `S3_REGION` | `powerforge`, `us-east-1` | Bucket and region |
| `S3_SIGNED_URL_EXPIRES_SECONDS` | `900` | Download URL lifetime |
| `MAX_UPLOAD_BYTES` | `262144000` (250 MB) | Per-file upload limit, enforced while streaming |
| `MAX_IMAGE_PIXELS` | `600000000` | Image dimension cap checked from the header before decode |

Notes:

- `minio-init` in `docker-compose.yml` creates the bucket (`mc mb --ignore-existing`). The API also calls an idempotent bucket check at startup so it works outside Compose. The bucket is private; do not add an anonymous policy.
- A reverse proxy in front of the API must allow request bodies at least as large as `MAX_UPLOAD_BYTES`.
- Phase 2 adds Python dependencies (`boto3`, `Pillow`, `python-multipart`) to `services/api`, `requirements-dev.txt`, and CI. After pulling, reinstall (`pip install -e services/api`) and rebuild the API image (`docker compose up --build`).
- Phase 2 adds migration `0004` (revision lineage, `documents`, `revision_documents`). Existing revisions get `based_on_revision_id = NULL`. Apply with `alembic -c database/alembic.ini upgrade head` (Compose does this on API startup).

## Option A — Docker Compose (full stack)

Docker Desktop or Colima is enough. From the repository root:

```bash
docker compose up --build
```

| Service | URL |
| --- | --- |
| Web | http://localhost:3000 (projects) |
| System status | http://localhost:3000/status |
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
pip install -e packages/shared -e packages/project -e packages/engineering-model -e packages/document-model -e packages/extraction -e packages/topology -e packages/validation -e packages/provenance -e packages/ai -e services/api
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
cd apps/web && npm run lint && npm test && npx tsc --noEmit
```

Tests marked `integration` need a live database and are skipped unless `RUN_INTEGRATION=1`. They insert uniquely named rows and **do not clean up**, so do not point them at a database you care about. Use a throwaway database in the running PostgreSQL container:

```bash
docker exec powerforge-postgres-1 psql -U powerforge -d postgres -c "CREATE DATABASE powerforge_test;"
export DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_test
alembic -c database/alembic.ini upgrade head
RUN_INTEGRATION=1 pytest
docker exec powerforge-postgres-1 psql -U powerforge -d postgres -c "DROP DATABASE powerforge_test;"
```

Phase 2 tests use an in-memory `ObjectStorage` fake, so they need no MinIO. The one real-storage test is also marked `integration` and additionally needs the Compose MinIO service running (`docker compose up minio minio-init -d`).

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs Ruff, Pytest (with PostgreSQL service), and the Next.js lint/test job.
