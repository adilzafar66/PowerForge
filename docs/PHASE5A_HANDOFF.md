# Phase 5A implementation report

Phase 5A implementation is complete and ready for review. Work is on `codex/phase-5a-registry`; Phase 5B has not started.

## Files and architecture

The existing `packages/engineering-model/src/powerforge_engineering_model` package was extended with:

- `definitions.py`: frozen dataclasses for attributes, equipment, units, conditions, rules, state inputs, and results.
- `registry_v1.py`: complete code-owned approved metadata, including reference-only NONE notices.
- `registry.py`: public lookup, supported-input-unit, and typed value normalization functions.
- `units.py`: small deterministic Decimal conversion layer with dimension and semantic checks.
- `requirements.py`: pure conditional and unconditional completeness evaluation.
- `validation.py`: startup/test structural validation.
- `errors.py`: domain-specific lookup, value, unit, and definition errors.
- `enums.py` and `__init__.py`: canonical vocabulary and public interfaces, replacing Phase 0 placeholders.

No third-party dependency was added to the domain package. An isolated Python interpreter without site packages successfully imports and validates the registry. The application loads neither the reference JSON nor the XLSX at runtime.

The API adds `routers/engineering_model.py` and `schemas/engineering_model.py`, registers the router and validates the registry in `main.py`, and declares the engineering-model package dependency in `services/api/pyproject.toml`. No service/repository abstraction is needed for static read-only metadata.

Documentation changes are in `ENGINEERING_MODEL.md`, the package mapping in `ARCHITECTURE.md`, and `PROJECT_STATUS.md`.

## Registry, units, and requirements

Structural validation and the exact independent JSON snapshot comparison pass:

- 20 canonical equipment types.
- 296 canonical attributes, preserving all Required/Critical flags and ordering.
- 44 reference rule rows: 41 executable rows plus three NONE notices.
- 17 unit families, preserving defaults, supported inputs, and notes.

Conversions cover all reference input units. They use an isolated 34-digit half-even Decimal context, reject incompatible dimensions and unsupported units, preserve appropriate integer semantics, handle affine temperatures, and treat transformer temperature rise as a difference. Percentage and per unit remain distinct. Horsepower is permitted only for motor/VFD active-power ratings. Attribute canonical units override family defaults.

All four rule types are implemented: ANY_OF, ALL_OF, REQUIRED_IF, and ALL_OR_NONE. Conditions are typed, never parsed from English. Only PRESENT values satisfy applicable requirements. Missing selectors and missing external context return NOT_EVALUATED; false conditions return NOT_APPLICABLE. Results include grouped missing attributes and are never persisted.

`GET /api/engineering-model/registry` exposes deterministic typed metadata, conditions, and permitted input units. There are no registry write endpoints.

## Validation results and exact commands

All commands ran from the repository root on 2026-10-23.

Initial existing-domain/API regression check:

```sh
.venv/bin/pytest tests/test_domain.py tests/test_health.py -q
```

Result: 14 passed.

New Phase 5A coverage:

```sh
.venv/bin/pytest tests/test_engineering_registry.py tests/test_engineering_units.py tests/test_engineering_requirements.py tests/test_engineering_registry_api.py -q
```

Result: 176 passed. Tests cover exact snapshot equality, malformed definitions, package independence, conversion pairs and rejection cases, all approved executable rule rows, information states, external context, representative conditional groups, immutable/deterministic evaluation, and the registry HTTP/OpenAPI contract. `tests/test_domain.py` was updated to assert the new canonical taxonomy.

Full Python regression without live integrations:

```sh
.venv/bin/ruff check . && .venv/bin/pytest -q
```

Result: Ruff passed; 469 passed, 352 skipped.

Full live regression used the existing local Postgres/MinIO services and a new disposable database. The commands use the repository's documented local development credentials:

```sh
docker compose exec -T postgres createdb -U powerforge powerforge_phase5a_20261023
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5a_20261023 .venv/bin/alembic -c database/alembic.ini upgrade head && DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5a_20261023 RUN_INTEGRATION=1 .venv/bin/pytest -q
docker compose exec -T postgres dropdb -U powerforge powerforge_phase5a_20261023
```

Result: migrations through existing `0006_document_classification` succeeded; **821 passed, none skipped**. The disposable database was removed successfully. The development database was not used for the test run.

Final lint, formatting, and whitespace checks:

```sh
git diff --check && .venv/bin/ruff check . && .venv/bin/ruff format --check packages/engineering-model services/api/src/powerforge_api/main.py services/api/src/powerforge_api/routers/engineering_model.py services/api/src/powerforge_api/schemas/engineering_model.py tests/test_domain.py tests/test_engineering_registry.py tests/test_engineering_units.py tests/test_engineering_requirements.py tests/test_engineering_registry_api.py
```

Result: passed; 17 Python files already formatted. No Python static typechecker is configured in this repository, so no typecheck command was run. There are no frontend changes; frontend checks were not run. The Python runs reported existing Starlette/AnyIO and PyMuPDF/SWIG deprecation warnings.

## Repository/specification differences and remaining concerns

- The supplied prompt exists at `docs/prompts/phase-5a_codex.md` (underscore), rather than the hyphenated path in the request.
- The reference JSON is authoritative for relay `trip_output_operating_time`: its canonical unit is seconds, despite the specification/prompt's milliseconds example. No reference metadata was altered.
- NONE rows remain reference annotations, not an extra executable rule type.
- Existing Phase 0 taxonomy and information-state placeholders were superseded as required by Phase 5; repository search found no production consumers needing migration. VerificationState includes all five states defined by ADR-007 and the Phase 5 specification, including UNVERIFIED. This is foundational domain vocabulary: Phase 5B can use UNVERIFIED for newly materialized attributes without changing the enum.
- The supplied prompt, Phase 5 specification, registry artifacts, and ADR-007 were already untracked when work began. They were preserved without edits. Include these authoritative inputs when committing the implementation.
- No unresolved implementation blocker was found. Decimal conversions intentionally have finite precision; semantic context choices and absent-selector behavior are documented in `ENGINEERING_MODEL.md`.

There are no new ORM models, database migrations, revision cloning, topology persistence, engineering-model CRUD, frontend workspace, extraction, persistent findings, protection-function model, or exporters.
