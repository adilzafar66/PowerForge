# PowerForge

Engineering data extraction platform. Electrical engineers upload project documents; PowerForge extracts structured electrical information, reconciles it across sources, and produces a centralized, traceable engineering model. The engineer remains the final authority.

**Current implemented phase:** Phase 2 — Document Management (specified in [cursor/phase2_specs.txt](cursor/phase2_specs.txt), delivered via [docs/PHASE2_PR_PLAN.md](docs/PHASE2_PR_PLAN.md))  
**Next:** Phase 3 — Document Processing (not started)

Phase status lives in [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md). Do not treat this README or chat history as the source of truth.

Engineers can create projects and revisions, upload PDF and image documents to a revision (stored unchanged in S3-compatible storage, MinIO locally), classify and edit them, remove and restore them per revision, reuse a document from another revision, and have new revisions inherit the previous revision's documents without copying files; see [ADR-004](decisions/ADR-004-document-storage-and-revision-inheritance.md). The stack does not yet read, render or extract the documents, call AI models, or integrate ETAP/SKM/EasyPower. Phase 0 setup notes remain in [docs/PHASE0_HANDOFF.md](docs/PHASE0_HANDOFF.md).

When you run Compose, uploads go from the browser to the API, so `CORS_ORIGINS` must include the origin you open the web app from, and signed download links use `S3_PUBLIC_ENDPOINT_URL` (`http://localhost:9000`); see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#phase-2-configuration-document-storage).

## Quick start

**Docker Compose** (PostgreSQL, Redis, MinIO, API, workers, web):

```bash
docker compose up --build
```

- Web: http://localhost:3000
- API health: http://localhost:8000/health
- API ready: http://localhost:8000/ready
- API docs: http://localhost:8000/docs

**Native development** (Python 3.12 + Node.js 22+): see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Architecture

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Domain documents:

- [Engineering model](docs/ENGINEERING_MODEL.md)
- [Document pipeline](docs/DOCUMENT_PIPELINE.md)
- [Extraction](docs/EXTRACTION.md)
- [Topology](docs/TOPOLOGY.md)
- [Validation](docs/VALIDATION.md)
- [Provenance](docs/PROVENANCE.md)
- [Review workflow](docs/REVIEW_WORKFLOW.md)
- [Coding standards](docs/CODING_STANDARDS.md)

Decisions: [decisions/](decisions/).

## Layout

```
apps/web                  Next.js UI
services/api              FastAPI
services/document-worker  Celery (heartbeat in Phase 0)
services/extraction-worker
services/validation-worker
packages/*                Domain packages (no AI vendor SDKs in the engineering model)
cursor/                   Product and per-phase implementation specifications
database/                 Alembic migrations
```
