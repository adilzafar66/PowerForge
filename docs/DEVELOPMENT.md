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

Phase 3 processing runs on `document-worker`. New uploads enqueue a run; documents already stored wait for `powerforge-backfill-processing --limit N`. The revision documents workspace shows processing status, retry, and the page viewer ([PHASE3_PR_PLAN.md](PHASE3_PR_PLAN.md)).

Phase 4 classification runs on `extraction-worker` after Phase 3 commits a completed processing run, and only when classification is enabled. That worker listens on `document_classification`. The OpenAI adapter lives there; tests mock it and do not call OpenAI. Documents already processed wait for `powerforge-backfill-classification --limit N` ([PHASE4_PR_PLAN.md](PHASE4_PR_PLAN.md)).

Phase 4.5 (complete; `cursor/phase4.5_specs.txt`, [PHASE4_5_PR_PLAN.md](PHASE4_5_PR_PLAN.md)) is that same revision route. The page is Add Documents, search, Filters, and All / Needs Review / Issues / Removed, over a Document / Type / State list. Opening a row opens a detail drawer for type, classification, processing, origin, and metadata.

The API reads and accepts classification in process. It does not call OpenAI. List, detail, and upload responses include a `classification` object (`enabled`, `suggestion`, `attempt`). Routes under `.../documents/{revisionDocumentId}`:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/classification` | Suggestion, attempt, score, alternatives, and rationale. Does not start a run |
| `GET` | `/classification/runs` | History without prompts, text, images, storage keys, or provider payloads |
| `GET` | `/classification/pages` | Page predictions from the completed suggestion. 409 `classification_not_complete` when there is none |
| `POST` | `/classification/reclassify` | New pending attempt. 409 `ai_classification_disabled` while classification is off |
| `POST` | `/classification/runs/{runId}/retry` | Retry the newest failed run for that identity |
| `POST` | `/classification/predictions/{predictionId}/accept` | Set the confirmed type from a completed document prediction |

Reads stay available while classification is off, including removed, superseded, and archived associations. Accept and a manual type edit stay available too. Reclassify and retry are the routes that return 409 `ai_classification_disabled`. Accept is the only writer of `accepted_classification_prediction_id`. Submitting `document_type` clears that id. Creating a revision copies it; reuse copies it unless the body includes `document_type`.

## Phase 4 configuration

These fields exist on `Settings`. The code default is off (`AI_CLASSIFICATION_ENABLED` defaults to false). Compose sets it true for the API, `document-worker`, and `extraction-worker`, with `AI_PROVIDER=fake`. They stay out of `.env.example`. `extraction-worker` substitutes `OPENAI_API_KEY` from the environment; do not commit a key. A blank key counts as unset. `Settings()` constructs when the key is absent. The API, `document-worker`, and `validation-worker` start without it and do not receive the key. `extraction-worker` refuses to start when classification is enabled, `AI_PROVIDER=openai`, and the key is missing. Fake mode and disabled mode start without a key.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_CLASSIFICATION_ENABLED` | `false` | When false, `ensure`, `retry`, and `reclassify` insert nothing. Uploads still only start Phase 3 processing |
| `AI_PROVIDER` | `fake` | `fake` or `openai`. `fake` runs the workflow without a network call |
| `AI_CLASSIFICATION_MODEL` | `gpt-6-luna` | Model stored on the run and included in the classifier identity |
| `AI_CLASSIFICATION_REASONING_EFFORT` | `none` | Stored for the later adapter. Not part of the identity hash |
| `AI_CLASSIFICATION_IMAGE_DETAIL` | `low` | Copied onto the sampling profile, so a change alters `profile_hash` |
| `AI_CLASSIFICATION_TIMEOUT_SECONDS` | `60` | Bound for one provider call. Exceeding it is `PROVIDER_TIMEOUT` |
| `AI_CLASSIFICATION_TASK_SOFT_TIME_LIMIT_SECONDS` | `600` | Bound for the whole Celery task. Exceeding it is `CLASSIFICATION_TASK_TIMEOUT` |
| `AI_CLASSIFICATION_TASK_HARD_TIME_LIMIT_SECONDS` | `660` | Hard ceiling. The soft limit must be lower so the worker can mark the run failed |

Reasoning effort is not hashed. Image detail is. The soft task limit must be strictly below the hard limit.

## Prerequisites

- Python 3.12
- Node.js 22+ (LTS)
- Docker Desktop or Colima + Docker CLI (recommended) **or** a local PostgreSQL 16+ instance

If Homebrew already runs `postgresql@16` or `redis`, stop those services before Compose. They occupy the same host ports (5432 and 6379) that `docker-compose.yml` publishes.

## Environment

Copy `.env.example` to `.env` in the repository root. The API and workers read `DATABASE_URL`, `REDIS_URL`, and S3 settings from the environment.

## Phase 2 configuration (document storage)

These settings were introduced by Phase 2 and are read through `powerforge_shared.config.Settings`. Existing `S3_*` names are unchanged. They are already listed in `.env.example` and set for the `api` service in `docker-compose.yml`, and they have defaults for local use. `S3_SIGNED_URL_EXPIRES_SECONDS` must be between 1 and 604800; `MAX_UPLOAD_BYTES`, `MAX_IMAGE_PIXELS`, and `MAX_PROCESSING_PAGES` must be positive. A blank `S3_PUBLIC_ENDPOINT_URL` counts as unset.

| Variable | Default | Purpose |
| --- | --- | --- |
| `S3_ENDPOINT_URL` | `http://localhost:9000` (compose: `http://minio:9000`) | Endpoint the API uses to talk to object storage (scheme included) |
| `S3_PUBLIC_ENDPOINT_URL` | falls back to `S3_ENDPOINT_URL` | Endpoint the **browser** can reach; presigned download URLs are signed against it. In Docker Compose the API reaches MinIO at `http://minio:9000`, which a browser cannot, so set this to `http://localhost:9000` |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | dev defaults | Storage credentials (never sent to the browser) |
| `S3_BUCKET`, `S3_REGION` | `powerforge`, `us-east-1` | Bucket and region |
| `S3_SIGNED_URL_EXPIRES_SECONDS` | `900` | Download URL lifetime |
| `MAX_UPLOAD_BYTES` | `262144000` (250 MB) | Per-file upload limit, enforced while streaming |
| `MAX_IMAGE_PIXELS` | `600000000` | Image dimension cap checked from the header before decode. The document worker uses the same value when it renders |
| `MAX_PROCESSING_PAGES` | `1000` | Page ceiling. The document worker rejects a PDF or TIFF over this count before it renders the first page. It is not part of the processing profile hash |
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
pip install -e packages/shared -e packages/project -e packages/engineering-model -e packages/document-model -e packages/document-processing -e packages/document-classification -e packages/extraction -e packages/topology -e packages/validation -e packages/provenance -e packages/ai -e services/api
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

Document worker (needs Redis, Postgres, and the same `S3_*` values as the API). It listens only on `document_processing` and stays at one process:

```bash
celery -A document_worker.celery_app worker --loglevel=info -Q document_processing --concurrency=1
```

(from `services/document-worker` with `PYTHONPATH` including that service’s `src`).

Extraction worker (needs Redis, Postgres, and the same `S3_*` values as the document worker). It listens only on `document_classification` and stays at one process. Put `OPENAI_API_KEY` in this process’s environment only, and only when classification is enabled with `AI_PROVIDER=openai`:

```bash
celery -A extraction_worker.celery_app worker --loglevel=info -Q document_classification --concurrency=1
```

(from `services/extraction-worker` with `PYTHONPATH` including that service’s `src` and the classification package).

Backfill does not run when the API starts. Processing backfill enqueues documents that have no compatible run, and documents whose current run is still unclaimed `PENDING`. It does not retry `FAILED`. `--limit` is required:

```bash
powerforge-backfill-processing --limit 100
```

Classification backfill selects the oldest documents whose current processing run for the active profile is `COMPLETED`, then keeps only those `ensure` would enqueue: no compatible classification run yet, or an unclaimed compatible `PENDING` run. Compatible `COMPLETED`, `RUNNING`, and `FAILED` rows are left alone. `--limit` is required and must be at least 1. Classification must be enabled. The OpenAI key belongs only in the extraction-worker environment:

```bash
powerforge-backfill-classification --limit 100
```

Classification quality is measured offline with `powerforge-eval-classification`. It reads a labeled manifest, runs the fake provider unless you opt in, and writes a JSON report. It does not use Postgres or the API, and CI does not run it. The committed example uses tiny filename fixtures:

```bash
powerforge-eval-classification --manifest evals/classification/example-manifest.json
```

Point `--manifest` at your own labeled set under `evals/classification/private/` (that directory is gitignored). Paths in the manifest are relative to the manifest file. Each item has `expected_document_type` and optional `expected_page_types`. A live OpenAI smoke is explicit and stays out of CI. Run it from an environment that has the extraction-worker package installed, and set `OPENAI_API_KEY` only for that process:

```bash
powerforge-eval-classification --manifest evals/classification/private/manifest.json --provider openai
```

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
