# ADR-002: Phase 0 technology stack

## Status

Accepted

## Date

2026-09-02

## Context

The specification names families of tools (FastAPI, PostgreSQL, S3-compatible storage, Redis plus a Python job queue) but leaves several implementation choices open. Phase 0 must pick defaults so the repository can run without blocking later phases.

## Decisions

### SQLAlchemy 2 synchronous engine

Alembic’s native workflow is synchronous. Phase 0 only needs health checks and migrations. A single sync SQLAlchemy 2 engine (psycopg v3) avoids maintaining two engines. Async can be adopted later behind the same session interface if request concurrency requires it; that change would be a new ADR.

### Celery + Redis

Celery is a well-supported Python queue with retries, failure state, and multiple worker processes. PowerForge needs at least three workers (document, extraction, validation). RQ is simpler but weaker for multiple specialized workers and operational features. Celery is the job system; Redis is the broker/result backend.

Phase 0 workers only heartbeat. They must not implement OCR or extraction.

### MinIO for local object storage

Production object storage is S3-compatible. MinIO provides that API locally so Phase 2 upload code can use one S3 client. Docker Compose runs MinIO; the API does not expose the bucket publicly.

### Domain packages as Python libraries

The engineering model, documents, extraction contracts, topology, validation, provenance, and AI interfaces are Python packages imported by the API and workers. The Next.js app talks to the REST API only. That preserves “the model does not depend on the web framework” and keeps TypeScript out of domain persistence.

### Next.js App Router

The specification requires Next.js. The App Router is the current Next.js default and is sufficient for a Phase 0 status UI. React Flow is intentionally omitted until Phase 12.

### Docker Compose as the full-stack path

PostgreSQL, Redis, MinIO, the API, workers, and the web app run via Compose so the stack matches production-shaped services. A native Windows path (local uvicorn + Next.js against Compose-backed or local PostgreSQL) is documented for development without containerizing the app processes.

## Consequences

- Changing job systems later is possible but should be an ADR; application code should enqueue through a small jobs helper, not scatter Celery APIs through domain packages.
- Sync SQLAlchemy is acceptable until measured need for async.
- Frontend packages in `/packages` are not created in Phase 0 because no shared UI domain library exists yet.
