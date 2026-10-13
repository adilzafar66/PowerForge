# PowerForge

Engineering data extraction platform. Electrical engineers upload project documents; PowerForge extracts structured electrical information, reconciles it across sources, and produces a centralized, traceable engineering model. The engineer remains the final authority.

**Current implemented phase:** Phase 4 — AI document classification (specified in [cursor/phase4_specs.txt](cursor/phase4_specs.txt), decided in [ADR-006](decisions/ADR-006-ai-document-classification.md), delivered via [docs/PHASE4_PR_PLAN.md](docs/PHASE4_PR_PLAN.md))  
**Next:** Phase 4.5 — Document workspace UI (in progress; [cursor/phase4.5_specs.txt](cursor/phase4.5_specs.txt), [docs/PHASE4_5_PR_PLAN.md](docs/PHASE4_5_PR_PLAN.md)). Phase 5 — Engineering model persistence remains not started.

Phase status lives in [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md). Do not treat this README or chat history as the source of truth.

Engineers can create projects and revisions, upload PDF and image documents to a revision (stored unchanged in S3-compatible storage, MinIO locally), classify and edit them, remove and restore them per revision, reuse a document from another revision, and have new revisions inherit the previous revision's documents without copying files; see [ADR-004](decisions/ADR-004-document-storage-and-revision-inheritance.md). Phase 3 renders each immutable document into stable pages, an analysis image, a thumbnail, and native PDF text when the page already has a text layer. Phase 4 suggests a document type after that processing completes, and an engineer accepts it or keeps the confirmed type. It does not run OCR, extract equipment, or integrate ETAP/SKM/EasyPower. Phase 0 setup notes remain in [docs/PHASE0_HANDOFF.md](docs/PHASE0_HANDOFF.md).

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
services/document-worker  Celery (`document_processing` queue)
services/extraction-worker
services/validation-worker
packages/*                Domain packages (no AI vendor SDKs in the engineering model)
cursor/                   Product and per-phase implementation specifications
database/                 Alembic migrations
```
