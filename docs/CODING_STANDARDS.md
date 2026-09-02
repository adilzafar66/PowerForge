# Coding standards

These standards apply to all PowerForge code. Prefer simple, well-defined interfaces over speculative abstraction.

## Before changing code

1. Read [ARCHITECTURE.md](ARCHITECTURE.md).
2. Read the relevant domain document.
3. Inspect existing code.
4. Determine which module owns the behavior.
5. Do not place logic in an unrelated module.

Never implement functionality outside the requested phase unless explicitly instructed. Do not create placeholder abstractions without a concrete need.

Architectural changes require: an explanation, affected modules, documentation updates, and an ADR when the decision is significant.

## Languages and versions

- Python 3.12
- TypeScript 5 (strict)
- Node.js 22+ (LTS)

## Python

- Type hints on public functions and Pydantic models.
- Ruff for lint and format (`ruff check`, `ruff format`).
- Line length 100.
- src layout for packages and services.
- Pydantic models for API contracts; never expose SQLAlchemy ORM models as response types.
- Domain packages must not import FastAPI, Celery, Next.js, or vendor AI SDKs.
- Tests go under `/tests` for API/domain and next to the web app for UI.

## TypeScript / React

- `strict` TypeScript.
- ESLint + the Next.js config.
- App Router under `apps/web`.
- Call the API with explicit DTO types that match Pydantic contracts. Do not duplicate domain persistence shapes in the client.

## Naming

- Python packages: `powerforge_*` import names (`powerforge_shared`, `powerforge_api`, …).
- REST paths: `/api/...` as specified in ARCHITECTURE.md.
- Database: snake_case tables and columns.

## Errors and logging

- Structured logging (JSON in workers and API).
- Do not swallow exceptions. Record job failures with retry context.
- User-facing errors must not leak storage keys or provider secrets.

## Security

- No secrets in git. Use `.env` (gitignored) from `.env.example`.
- Do not log document contents at info level.
- Object storage access only through authorized API flows.

## Completeness

A phase is complete when required functionality works, APIs are defined, migrations work, tests pass, errors are handled, docs are updated, module boundaries are respected, and future-phase features have not been smuggled in.
