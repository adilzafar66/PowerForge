# Phase 5B implementation report

Phase 5B implementation is complete and ready for review.

Branch: `codex/phase-5b-core-persistence`, based on accepted Phase 5A commit `31d8814` from `codex/phase-5a-registry`. Origin/main did not yet contain Phase 5A when the branch was created. Phase 5C has not begun.

## Files and persistence boundary

- `packages/persistence`: new neutral `powerforge_persistence` package. `base.py` owns the one SQLAlchemy Base, `projects.py` owns the existing Project/ProjectRevision mappings, and `engineering.py` owns EquipmentLineage/Equipment/EquipmentAttribute.
- `packages/document-processing/.../models.py`: Base, Project, ProjectRevision, and their enum mappings become compatibility re-exports of the same objects. Document, processing, and classification mappings stay where they were. This avoids making engineering persistence depend on document-processing without broadly relocating existing document code.
- `packages/engineering-model/.../enums.py` and `__init__.py`: export LifecycleStatus (ACTIVE, REMOVED) and ValueOrigin (MANUAL, AI_EXTRACTION, INFERRED, IMPORTED). VerificationState retains UNVERIFIED and all four other accepted states. Registry-v1, normalization, requirement evaluation, and the registry API are unchanged.
- `database/migrations/0007_engineering_model_core.py`: explicit, reversible schema migration after `0006_document_classification`. No runtime registry dependency and no synthesis from existing documents.
- `services/api/.../services/engineering_model_service.py`: internal canonical manual authoring and consistency validation. `exceptions.py` adds equipment-specific service errors, reusing existing registry lookup/value errors and the safe integrity-error mechanism.
- `services/api/.../services/revision_writes.py`: neutral lifecycle/locking helpers. `revision_documents.py` re-exports the original helper names and retains the document-specific error message. Document/project/revision services use the neutral helpers. Revision creation and document carry-forward behavior are unchanged.
- Package dependencies, root pytest/Ruff configuration, CI, API/worker Dockerfiles, and development installation instructions include the new package. Worker installations include the pure engineering domain dependency without importing the API.
- New tests: `engineering_support.py`, `test_engineering_persistence.py`, `test_engineering_service.py`, `test_engineering_constraints.py`, `test_engineering_concurrency.py`, and `test_migration_0007.py`. Two document fault-injection hooks follow the extracted guard; historical migration 0006 tests explicitly target their own HEAD rather than the newly advancing repository head.
- Documentation: `ENGINEERING_MODEL.md`, `ARCHITECTURE.md`, `DEVELOPMENT.md`, `PROJECT_STATUS.md`, and this handoff. The supplied `prompts/phase-5b-codex.md` was initially untracked and remains unchanged.

The pure engineering-model package still has no third-party, SQLAlchemy, FastAPI, or provider dependency. Persistence depends on SQLAlchemy and the project/engineering domain packages, with no document or API import. Compatibility identity and mapper configuration are tested.

## Migration, tables, constraints, and indexes

The head is `0007_engineering_model_core`. Every table has a UUID primary key and timestamp/nullable actor audit fields. Equipment and attributes have updated audit fields; lineage has creation audit only. No users table or actor foreign key is introduced.

| Table | Identity and ownership | Checks and indexes |
| --- | --- | --- |
| `equipment_lineages` | `fk_equipment_lineages_project_id`; `uq_equipment_lineages_project_id_id` supports composite ownership | `ix_equipment_lineages_project_id` |
| `equipment` | `fk_equipment_revision` binds project/revision; `fk_equipment_lineage` binds project/lineage; `fk_equipment_inherited_from` binds project/source; `uq_equipment_revision_lineage` allows each lineage once per revision; `uq_equipment_project_id_id` and `uq_equipment_project_revision_id` support composite references | `ck_equipment_inherited_not_self`; `ck_equipment_lifecycle_removed_at`; indexes `ix_equipment_revision_lifecycle`, `ix_equipment_project_id`, `ix_equipment_lineage_id`, `ix_equipment_revision_tag`, `ix_equipment_inherited_from` |
| `equipment_attributes` | `fk_equipment_attributes_equipment` binds project/revision/equipment; `fk_equipment_attributes_inherited_from` binds project/source; `uq_equipment_attributes_key` allows one key per equipment; `uq_equipment_attributes_project_id_id` supports inheritance references | `ck_equipment_attributes_inherited_not_self`, `ck_equipment_attributes_typed_value`, `ck_equipment_attributes_confidence`, `ck_equipment_attributes_finite_numeric`; indexes `ix_equipment_attributes_project_revision`, `ix_equipment_attributes_inherited_from` |

Primary-key and unique constraints also supply PostgreSQL indexes. Tag is nullable, indexed with revision, and deliberately not unique. Inheritance columns are nullable and have no write behavior in this phase. There is no EngineeringModel root, JSON attribute blob, per-type table, topology table, or stored Required/Critical metadata.

PRESENT requires exactly one compatible typed column: NUMBER → NUMERIC, INTEGER → BIGINT, TEXT/ENUM → TEXT, BOOLEAN → BOOLEAN. All five non-PRESENT states require all typed columns null. Confidence is nullable or within [0, 1]; non-finite NUMERIC values are rejected. Removed equipment requires removed_at; active equipment requires both removal fields null.

Equipment types, attribute keys, and units use text so registry additions do not require PostgreSQL enum changes. The five closed vocabularies use migration-owned `model_lifecycle_status`, `model_value_origin`, `model_information_state`, `model_verification_state`, and `model_attribute_value_type` enums. Labels exactly match domain values; ORM enum objects use `create_type=False`. Downgrade drops the three tables in dependency order, then those five enums, preserving existing project/document/processing/classification data.

## Service behavior

`EngineeringModelService(session)` provides create/get/list equipment, registry-ordered attribute retrieval, metadata/type updates, manual attribute updates, and soft remove/restore. Operations are scoped to project/revision and, where relevant, equipment. Reads include removed equipment by ID; lists default to ACTIVE and accept REMOVED or all statuses. Returned ORM objects belong to the caller's session; mutations own commits and rollbacks, so use a dedicated session per unit of work.

Creation inserts a new project-owned lineage and revision-scoped equipment, then every attribute in its registry definition, atomically. Equipment starts ACTIVE / MANUAL / ENGINEER_REVIEWED. Every attribute starts NOT_EXTRACTED / UNVERIFIED, with canonical type/unit and null origin, confidence, values, and inheritance. Duplicate tags and incomplete required attributes are allowed.

Manual PRESENT writes call Phase 5A `normalize_attribute_value`, store the canonical result in the matching slot, and clear all others. UNKNOWN/MISSING/NOT_APPLICABLE clear values while preserving canonical type/unit. All manual attribute edits use MANUAL / ENGINEER_REVIEWED / null confidence; provenance and verification cannot be supplied as mutation arguments. NOT_EXTRACTED and CONFLICTING are not ordinary manual choices. State-only edits reject values and input units. Actor and timestamp fields update together with equipment/revision timestamps.

Type changes preserve rows with matching key, value type, and canonical unit. PRESENT enum values must also belong to the destination choices. Incompatible rows can be discarded only when NOT_EXTRACTED / UNVERIFIED, with null values, origin, confidence, and inherited-from reference. A meaningful incompatible row rejects the entire transaction, including any accompanying metadata change. Only after all checks pass are untouched incompatible rows removed and new destination rows materialized with initial defaults. Preserved rows retain identity and provenance. Delete/reinsert of an incompatible same-key row is ordered to respect immediate uniqueness.

Remove/restore is idempotent, changes lifecycle/removal audit fields, and preserves lineage and all attributes. Removed equipment must be restored before editing. No service hard-deletes equipment. `validate_equipment_consistency` checks exact materialization, ownership, registry value type/unit, and typed values, including enum membership. Every write validates the canonical record; corruption produces a service error rather than silent repair.

Known named integrity failures map to explicit equipment/state/ownership errors; unknown integrity failures retain `UnexpectedIntegrityError`. No database statement, parameter, or engineering value is exposed through these errors.

## Locks and mutability

Every mutation locks the project FOR SHARE first, then its revision FOR UPDATE, refreshing cached state under those locks. It allows ACTIVE/PAUSED projects and DRAFT/ACTIVE revisions, rejects ARCHIVED/CANCELLED projects and SUPERSEDED revisions, and rolls back on failure. Reads remain available. Archive, cancel, and activation cannot race a model write. Engineering mutations update the revision timestamp and never upgrade the shared project lock. Existing document mutability, lock order, and error messages remain unchanged.

Tests exercise all mutation entry points, the full project/revision state matrix, lock SQL ordering, and actual competing PostgreSQL sessions. Stale sessions wait for archive/cancel/supersede and then reject writes using refreshed status; archive waits while a revision mutation holds its shared project lock.

## Validation and exact commands

Commands ran from the repository root on 2026-10-23 with Python 3.12. Baseline Phase 5A validation, before implementation:

```sh
.venv/bin/pytest tests/test_domain.py tests/test_engineering_registry.py tests/test_engineering_units.py tests/test_engineering_requirements.py tests/test_engineering_registry_api.py -q
```

Result: **185 passed**.

The new editable package was installed with `.venv/bin/pip install --no-deps -e packages/persistence`. An initial no-build-isolation attempt could not find setuptools in the virtualenv; normal build isolation installed successfully.

Full regression without live integrations:

```sh
.venv/bin/pytest -q
```

Result: **473 passed, 445 skipped**. Skips are the opt-in live integration tests.

Full live regression used an isolated database and existing local PostgreSQL/MinIO services:

```sh
docker compose exec -T postgres createdb -U powerforge powerforge_phase5b_20261023
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5b_20261023 .venv/bin/alembic -c database/alembic.ini upgrade head
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5b_20261023 RUN_INTEGRATION=1 .venv/bin/pytest -q
```

Result: migration succeeded through **0007**; **918 passed, none skipped, 6 existing dependency deprecation warnings**. Final output is also captured locally in `/tmp/powerforge_phase5b_final_pytest.log`. Migration tests independently create/drop scratch databases and verify fresh upgrade, upgrade from 0006 with existing project/document/processing/classification data, zero synthesized model rows, schema/enum/constraint/index details, downgrade with model rows, preservation of earlier data, and re-upgrade.

An earlier full run exposed two old document-test patch targets after guard extraction; those hooks were corrected and the full suite passed. That run also encountered a MinIO RequestTimeTooSkewed teardown failure after a host-time jump. Host/container clocks were aligned on inspection, subsequent full storage tests and teardown passed, and the specific abandoned scratch bucket was removed. No clock workaround or test skip was added.

Final static checks:

```sh
.venv/bin/ruff check .
git diff --check
.venv/bin/pip check
.venv/bin/ruff format --check packages/persistence packages/engineering-model/src/powerforge_engineering_model/enums.py packages/engineering-model/src/powerforge_engineering_model/__init__.py packages/document-processing/src/powerforge_document_processing/models.py database/migrations/0007_engineering_model_core.py services/api/src/powerforge_api/exceptions.py services/api/src/powerforge_api/services/engineering_model_service.py services/api/src/powerforge_api/services/revision_writes.py services/api/src/powerforge_api/services/revision_documents.py services/api/src/powerforge_api/services/document_service.py services/api/src/powerforge_api/services/project_service.py services/api/src/powerforge_api/services/revision_service.py tests/engineering_support.py tests/test_engineering_persistence.py tests/test_engineering_service.py tests/test_engineering_constraints.py tests/test_engineering_concurrency.py tests/test_migration_0007.py tests/test_migration_0006.py tests/test_documents_api.py
```

Results: lint/whitespace checks pass, no broken package requirements, all 23 changed/new Python files formatted. No Python static typechecker is configured. No frontend code changed or frontend checks ran. Dockerfiles were updated but images were not rebuilt; the development stack was not restarted or migrated.

Cleanup after validation:

```sh
docker compose exec -T postgres dropdb -U powerforge powerforge_phase5b_20261023
```

The temporary database and test storage bucket were removed. The development database was not used for these tests.

## Decisions, differences, and remaining concerns

- No architectural conflict with ADR-007 or the Phase 5 specification was found. The accepted Phase 5A branch, rather than origin/main, supplies the required baseline. Reference registry files are unchanged.
- Engineering numbers use Decimal/unconstrained NUMERIC, with no fixed-scale rounding in persistence. INTEGER uses signed 64-bit BIGINT; the service rejects out-of-range integers. Phase 5A conversion precision remains as documented.
- Removed equipment must be restored before metadata/value edits, a conservative lifecycle choice. Inheritance references also require the same project; future clone behavior must use these constraints.
- Actor UUIDs remain optional until authentication exists. There is no audit-history table, pagination, engineering public API, or frontend in this scope. Direct SQL can violate registry key/unit/enum semantics; database structural checks plus service consistency validation intentionally divide those responsibilities.
- Existing requirements do not block saves and no findings are persisted. Existing test suites still require disposable databases; migration tests clean their own scratch databases.
- No unresolved Phase 5B implementation blocker remains. Deployment/build validation and the user-facing workflow belong to subsequent work.

**Phase 5C has not begun.** There is no engineering-model carry-forward, cloning, topology, public CRUD API, frontend, AI extraction, evidence/candidate reconciliation, validation findings persistence, or export work in this implementation. Revision creation still copies only documents.
