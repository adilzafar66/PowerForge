# Local development

Phase 0 delivered a runnable skeleton: API health/readiness, PostgreSQL, Redis, MinIO, Celery heartbeats, and a Next.js status page.

Phase 1 adds project and revision management. Routes:

| Path | Purpose |
| --- | --- |
| `/` | Project list |
| `/projects/new` | Create project |
| `/projects/[id]` | Project detail and revisions |
| `/projects/[id]/revisions/[revisionId]` | Revision documents workspace (Phase 2) |
| `/status` | Stack health (API / PostgreSQL / Redis) |

API: `http://localhost:8000/api/projects` (see OpenAPI at `/docs`).

Phase 2 (complete; see [PROJECT_STATUS.md](PROJECT_STATUS.md)) added document management. The revision workspace route above is the revision documents page, and the API has `.../revisions/{revisionId}/documents` routes (list the routes in OpenAPI at `/docs`). See [Phase 2 configuration](#phase-2-configuration-document-storage).

## Prerequisites

- Python 3.12
- Node.js 22+ (LTS)
- Docker Desktop or Colima + Docker CLI (recommended) **or** a local PostgreSQL 16+ instance

If Homebrew already runs `postgresql@16` or `redis`, stop those services before Compose. They occupy the same host ports (5432 and 6379) that `docker-compose.yml` publishes.

## Environment

Copy `.env.example` to `.env` in the repository root. The API and workers read `DATABASE_URL`, `REDIS_URL`, and S3 settings from the environment.

## Phase 2 configuration (document storage)

These settings were introduced by Phase 2 and are read through `powerforge_shared.config.Settings`. Existing `S3_*` names are unchanged. They are already listed in `.env.example` and set for the `api` service in `docker-compose.yml`, and they have defaults for local use. `S3_SIGNED_URL_EXPIRES_SECONDS` must be between 1 and 604800; `MAX_UPLOAD_BYTES` and `MAX_IMAGE_PIXELS` must be positive. A blank `S3_PUBLIC_ENDPOINT_URL` counts as unset.

| Variable | Default | Purpose |
| --- | --- | --- |
| `S3_ENDPOINT_URL` | `http://localhost:9000` (compose: `http://minio:9000`) | Endpoint the API uses to talk to object storage (scheme included) |
| `S3_PUBLIC_ENDPOINT_URL` | falls back to `S3_ENDPOINT_URL` | Endpoint the **browser** can reach; presigned download URLs are signed against it. In Docker Compose the API reaches MinIO at `http://minio:9000`, which a browser cannot, so set this to `http://localhost:9000` |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | dev defaults | Storage credentials (never sent to the browser) |
| `S3_BUCKET`, `S3_REGION` | `powerforge`, `us-east-1` | Bucket and region |
| `S3_SIGNED_URL_EXPIRES_SECONDS` | `900` | Download URL lifetime |
| `MAX_UPLOAD_BYTES` | `262144000` (250 MB) | Per-file upload limit, enforced while streaming |
| `MAX_IMAGE_PIXELS` | `600000000` | Image dimension cap checked from the header before decode |
| `CORS_ORIGINS` | `http://localhost:3000` (`.env.example` and Compose also allow `http://127.0.0.1:3000`) | Comma-separated origins allowed to call the API from the browser. Uploads and edits go straight from the browser to the API, so it must include the origin you open the web app from |
| `NEXT_PUBLIC_MAX_UPLOAD_BYTES` (web) | `262144000` | Optional. Size hint the upload UI uses to reject oversized files early; set it to the same value as `MAX_UPLOAD_BYTES` if you change that. The API remains authoritative |

Notes:

- `minio-init` in `docker-compose.yml` creates the bucket (`mc mb --ignore-existing`). The API also calls an idempotent bucket check at startup so it works outside Compose; if storage is unreachable it logs a warning and keeps starting (uploads fail until it is back). `/ready` does not report storage. The bucket is private; do not add an anonymous policy.
- A reverse proxy in front of the API must allow request bodies at least as large as `MAX_UPLOAD_BYTES`. The API rejects requests whose `Content-Length` exceeds that limit plus 256 KiB before reading the body, but the framework still spools an accepted multipart body to a temporary file, so apply a proxy-level body limit in any shared environment.
- Upload a document from the command line (Swagger at `/docs` works too; `document_type` and the other text fields are optional):

  ```bash
  curl -F "file=@plan.pdf" -F "document_type=SINGLE_LINE_DIAGRAM" \
    http://localhost:8000/api/projects/$PROJECT_ID/revisions/$REVISION_ID/documents
  ```
- Phase 2 adds Python dependencies (`boto3`, `Pillow` and `python-multipart` for the upload endpoint) to `services/api` and `requirements-dev.txt`, which CI installs. After pulling, reinstall (`pip install -e services/api`) and rebuild the API image (`docker compose up --build`).
- Phase 2 adds migration `0004` (revision lineage, `documents`, `revision_documents`). Existing revisions get `based_on_revision_id = NULL`. Apply with `alembic -c database/alembic.ini upgrade head` (Compose does this on API startup). `tests/test_migration_0004.py` (with `RUN_INTEGRATION=1`) creates and drops its own scratch databases and runs Alembic in a subprocess, so it needs a `DATABASE_URL` whose user may `CREATE DATABASE`.

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

Most Phase 2 tests use the in-memory `ObjectStorage` fake (the `object_storage` fixture in `tests/conftest.py`), so they need no MinIO. The real-storage cases in `tests/test_storage.py` and the signed-download case in `tests/test_documents_download_api.py` (which uploads through the API and fetches the bytes through the returned URL) are marked `integration` and additionally need MinIO (`docker compose up minio minio-init -d`). They create a scratch bucket (`powerforge-test-<hex>`) and remove it at the end of the session. If MinIO is unreachable they skip locally, but fail when the `CI` environment variable is set so CI cannot skip them silently.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs Ruff, Pytest (with PostgreSQL and Redis service containers plus a MinIO container started by a `docker run` step, because service containers cannot pass MinIO's `server /data` command), and the Next.js lint/test job.
