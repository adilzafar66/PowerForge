# PowerForge

Engineering data extraction platform. Electrical engineers upload project documents; PowerForge extracts structured electrical information, reconciles it across sources, and produces a centralized, traceable engineering model. The engineer remains the final authority.

This repository is at **Phase 0**: architecture, module boundaries, and a runnable stack skeleton. It does not extract documents, call AI models, or integrate ETAP/SKM/EasyPower.

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
database/                 Alembic migrations
```
