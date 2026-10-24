# Phase 5E — Revision-scoped engineering-model APIs

Phase 5E is implemented and locally validated. Phase 5F has not begun. This report does not claim a commit, push, merge, or deployment.

## Baseline and changed files

Branch: `codex/phase-5e-model-apis`, based on accepted `main` / `origin/main` commit `007427842f75051d8c5979369f89882110aa423e` (Phase 5D). The authoritative Phase 5E prompt, Phase 5 specification, ADR-007, and accepted handoffs govern this implementation.

- `services/api/src/powerforge_api/routers/model.py`: dedicated revision-scoped CRUD/lifecycle router.
- `services/api/src/powerforge_api/schemas/model.py`: strict manual request schemas, canonical response schemas, list wrappers, and API-only lifecycle filter.
- API `main.py`: registers the router and updates the generated API description.
- API `exceptions.py` and `routers/errors.py`: stable engineering input error and explicit HTTP translation.
- API `services/engineering_model_service.py`: literal, case-insensitive equipment search. Existing stable ordering, registry checks, and ownership predicates remain intact.
- `tests/test_model_api.py`: focused live HTTP tests; `tests/test_model_api_contract.py`: offline OpenAPI, allowlist, and error-boundary tests.
- `tests/test_phase5c_revision_model.py`: replaces the obsolete assertion that equipment routes do not exist with a check that revision schemas do not embed equipment/attributes/topology. Existing Phase 5C metadata contract assertions remain.
- Current-facing architecture, model, topology, status, and roadmap docs; this handoff. The supplied `docs/prompts/phase-5e-codex.md` is preserved.

## Public endpoints

All paths in this table are relative to `/api/projects/{project_id}/revisions/{revision_id}`.

| Method | Path | Success response |
| --- | --- | --- |
| GET | `/equipment` | 200, equipment items |
| POST | `/equipment` | 201, Equipment |
| GET | `/equipment/{equipment_id}` | 200, Equipment, including removed state |
| PATCH | `/equipment/{equipment_id}` | 200, Equipment |
| POST | `/equipment/{equipment_id}/remove` | 200, Equipment |
| POST | `/equipment/{equipment_id}/restore` | 200, Equipment |
| GET | `/equipment/{equipment_id}/attributes` | 200, attribute items in registry order |
| PUT | `/equipment/{equipment_id}/attributes/{attribute_key}` | 200, EquipmentAttribute |
| GET | `/nodes` | 200, node items |
| POST | `/nodes` | 201, ModelNode |
| PATCH | `/nodes/{node_id}` | 200, ModelNode |
| POST | `/nodes/{node_id}/remove` | 200, ModelNode |
| POST | `/nodes/{node_id}/restore` | 200, ModelNode |
| GET | `/connections` | 200, connection items |
| POST | `/connections` | 201, ModelConnection |
| PATCH | `/connections/{connection_id}` | 200, ModelConnection |
| POST | `/connections/{connection_id}/remove` | 200, ModelConnection |
| POST | `/connections/{connection_id}/restore` | 200, ModelConnection |

`GET /api/engineering-model/registry` remains unchanged and supplies form metadata. No DELETE, single-node GET, single-connection GET, entire-model endpoint, or later-phase actions were added. Generated `/openapi.json` and `/docs` expose the resource contracts and summaries.

## Manual request allowlists

Every mutation schema uses `extra="forbid"`.

| Schema | Allowed fields |
| --- | --- |
| Equipment create | `equipment_type` (required), `tag`, `name`, `description` |
| Equipment patch | `equipment_type`, `tag`, `name`, `description` |
| Attribute PUT | `information_state` (required), generic JSON `value`, input `unit` |
| Node create | `kind` (required), `equipment_id`, `terminal_key`, `label` |
| Node patch | `terminal_key`, `label` |
| Connection create | `from_node_id`, `to_node_id` (required), `connection_kind`, `direction`, `phase_configuration`, `nominal_voltage`, input `nominal_voltage_unit` |
| Connection patch | `from_node_id`, `to_node_id`, `connection_kind`, `direction`, `phase_configuration`, `nominal_voltage`, input `nominal_voltage_unit` |
| Remove/restore | No fields; absent/null body or an empty object is accepted |

Equipment types reuse the canonical domain enum. Node shape validation requires equipment and a nonblank terminal key for EQUIPMENT_TERMINAL, and null/absent equipment and terminal key for ELECTRICAL_NODE. Kind and terminal ownership cannot be patched. Connection creation defaults to ELECTRICAL and UNDIRECTED.

Clients cannot supply project/revision identity in bodies, lineage IDs, lifecycle flags, origin, verification, confidence, inheritance pointers, or audit fields. HTTP operations leave actor IDs null; no header or fake identity is trusted. Ordinary manual writes remain MANUAL / ENGINEER_REVIEWED, with null confidence. Initial attributes remain NOT_EXTRACTED / UNVERIFIED with null origin/confidence. Inheritance and other stored provenance are readable but not directly writable.

Attribute PUT permits PRESENT, UNKNOWN, MISSING, and NOT_APPLICABLE only. Registry/domain services validate polymorphic values, enum membership, integers, and units. Non-PRESENT states clear all typed value slots; a non-null value or input unit accompanying a state-only write is rejected. Incomplete equipment remains saveable. No requirement evaluation becomes a write gate.

## Response contracts and Decimal behavior

Responses use explicit Pydantic models with `from_attributes=True`, without ORM relationship or internal-state exposure. Equipment, node, and connection responses contain identity, project/revision IDs, lifecycle, origin, verification, inheritance pointer, creation/update audit fields, and removal metadata. Equipment also includes lineage and type/tag/name/description; node includes kind/equipment/key/label; connection includes endpoints, kind, direction, phase text, voltage/unit, and confidence.

Attribute responses contain identity and ownership, key, value type, all four typed slots, canonical unit, information/verification state, origin/confidence, inheritance pointer, and creation/update audit fields. Attributes remain a separate response, not nested in equipment summaries.

All lists use `{"items": [...]}`. Decimal response fields (`numeric_value`, connection voltage, and confidence) serialize as lossless JSON strings using existing Pydantic behavior. No response conversion to binary float is introduced. Decimal strings are recommended for high-precision inputs; JSON numbers may already have undergone floating-point parsing before domain validation.

Unit normalization remains in the accepted services. Both attribute voltage and connection voltage support `600 V -> "0.6" kV`. Connection input is Decimal and rejects booleans/nonfinite values; the existing service also rejects nonpositive or incompatible-unit voltage. Omitted connection input unit means kV. Canonical attribute storage units remain registry-controlled.

## Search, filters, and PATCH semantics

Equipment search trims surrounding whitespace, treats blank as no filter, and matches a case-insensitive literal substring of tag, name, or description. SQL wildcard characters `%` and `_` are escaped. Equipment type filters validate against the canonical vocabulary; invalid filters return 422. Filters are combined within the path revision. Equipment summaries do not fetch attributes; a SQL-observation test verifies this.

Equipment, node, and connection list queries accept `lifecycle_status=ACTIVE|REMOVED|ALL`, defaulting to ACTIVE. ALL means no lifecycle predicate, not a new persisted state. Lists preserve stable `created_at, id` order; parallel connections are not deduplicated. Attributes retain registry display order.

PATCH uses `model_dump(exclude_unset=True)`: omitted fields remain unchanged. Explicit null clears equipment tag/name/description, node label, connection phase text, or connection nominal voltage (and its canonical unit). Explicit null for equipment type, terminal key, endpoints, connection kind, or direction is rejected. A supplied connection voltage-unit field, even null, requires the voltage field in the same PATCH; an explicit null voltage with omitted/null unit clears both. A non-null unit without a value is rejected. Direction changes do not swap endpoints.

## Errors, ownership, and lifecycle integration

Equipment, node, and connection PATCH schemas require at least one explicitly supplied field. An empty `{}` returns 422 before the service runs, preserving existing provenance, confidence, and audit timestamps. Explicit null on a clearable field still counts as a supplied edit. This validation belongs to the API boundary; accepted service semantics are unchanged.

`model_api_errors()` translates known domain input subclasses (unknown equipment/attribute/unit, incompatible unit, invalid attribute/enum value) into `InvalidEngineeringModelInput`, code `invalid_engineering_model_input`, preserving the useful message. Pure packages remain HTTP-independent. It does not catch arbitrary exceptions or registry-definition bugs. Services retain their existing rollback behavior.

| HTTP | Application errors |
| --- | --- |
| 404 | Missing/scoped-out Equipment, EquipmentAttribute, ModelNode, ModelConnection, project, or revision |
| 409 | Removed-object edits, inactive connection endpoints, meaningful equipment type-change conflict, archived/cancelled projects, superseded revisions |
| 422 | Invalid engineering input (including unknown attribute key), invalid attribute state, invalid topology, request/schema/query validation |
| 500 | InconsistentEquipment uses code `inconsistent_equipment` with a generic safe message; UnexpectedIntegrityError stays generic; programming/configuration errors are not relabeled as input errors |

Domain/application errors keep the existing `{"detail": {"detail": "...", "code": "..."}}` envelope. Pydantic validation retains FastAPI's usual 422 error list. Existing InvalidTopology behavior for restoring a terminal whose equipment is removed remains 422; inactive connection endpoints use TopologyObjectRemoved (409). No raw SQL or PostgreSQL error text is exposed.

The URL controls ownership. Existing services reject nested IDs or equipment/endpoints outside the path project/revision with scoped 404s and continue using composite FKs as structural protection. Mutations reuse project SHARE then revision UPDATE locks and writable-revision guards; historical reads remain available. Routers never write ORM rows directly.

Equipment remove atomically removes its terminals and incident active connections. Equipment restore restores terminals but leaves connections removed. Node remove cascades incident connection removal; node restore does not restore connections. Connection restore requires active valid endpoints. Duplicate equipment tags and parallel edges remain valid. Safe equipment type changes retain compatible attributes, materialize new attributes, and reject meaningful incompatible data. No lifecycle or inheritance algorithm was changed.

## Validation

Validation ran on 2026-10-24 using Python 3.12 and the existing local PostgreSQL/MinIO services. Live database tests used a disposable database, and storage integrations used the existing throwaway-bucket fixture. The development database was not migrated or modified.

The 24 new focused tests cover routing, response contracts and Decimal precision, search/filter behavior without attribute loading, registry ordering, safe type changes/conflicts, invalid inputs, request provenance protection, PATCH omission/null handling, path ownership, cross-revision references, lifecycle cascades/recovery, representative read-only states, domain/HTTP error mapping, and exact OpenAPI scope. Existing registry/unit/requirements, equipment persistence/service/constraint, revision inheritance/metadata, topology lifecycle/inheritance, and project/revision/document API tests remain in the full suite.

```sh
docker compose exec -T postgres createdb -U powerforge powerforge_phase5e_20261024
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5e_20261024 .venv/bin/alembic -c database/alembic.ini upgrade head
# Succeeded through existing 0009_topology_persistence; no new migration.

DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5e_20261024 RUN_INTEGRATION=1 .venv/bin/pytest tests/test_model_api.py tests/test_model_api_contract.py -q
# 24 passed, 6 existing dependency deprecation warnings, 3.22 seconds.

.venv/bin/pytest -q
# 501 passed, 547 integration tests skipped, 6 existing dependency warnings, 7.09 seconds.

DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5e_20261024 RUN_INTEGRATION=1 .venv/bin/pytest -q
# 1048 passed, no skips, 6 existing dependency warnings, 74.46 seconds.

.venv/bin/ruff check .
# All checks passed.
.venv/bin/ruff format --check services/api/src/powerforge_api/exceptions.py services/api/src/powerforge_api/main.py services/api/src/powerforge_api/routers/errors.py services/api/src/powerforge_api/routers/model.py services/api/src/powerforge_api/schemas/model.py services/api/src/powerforge_api/services/engineering_model_service.py tests/test_model_api.py tests/test_model_api_contract.py tests/test_phase5c_revision_model.py
# All 9 changed Python files formatted.
.venv/bin/pip check
# No broken requirements found.
git diff --check
# Passed.

docker compose exec -T postgres dropdb -U powerforge powerforge_phase5e_20261024
# Succeeded; disposable database removed.
```

Initial runs identified two test assumptions to correct: a newly written test referenced a nonexistent BUS frequency attribute, and a historical Phase 5C OpenAPI test forbade the now-required equipment routes. Final runs above include both corrections. No production implementation change was needed to resolve those failures. No frontend checks were run because no frontend files changed; no images were built or deployed.

## Decisions and remaining concerns

Review follow-up: empty PATCH rejection was verified with all focused API tests:

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5e_patch_20261024 RUN_INTEGRATION=1 .venv/bin/pytest tests/test_model_api.py tests/test_model_api_contract.py -q
# 29 passed, 6 existing dependency warnings, 3.29 seconds.
```

The additional cases verify pre-service rejection for all three update schemas, explicit-null acceptance, and unchanged persisted AI provenance/confidence/audit state. Ownership tests now submit legitimate edits instead of empty bodies. Ruff, changed-file formatting, and whitespace checks passed. The disposable database was initialized through 0009 and removed afterward; the full-suite results above describe the original Phase 5E validation, not a rerun for this focused schema fix.

- No architectural deviation or persistence redesign. The only service query extension is equipment search; API-only stricter unit-field presence checks distinguish omitted from explicit-null PATCH input.
- Listings remain unpaginated `items` wrappers as explicitly allowed by the Phase 5E prompt. Bounded listing/pagination is a future performance concern.
- Phase 5D bulk topology consistency scans remain; routers call each list service once. Larger-graph performance work belongs to later hardening.
- Authentication/project authorization and trustworthy actor identity remain unimplemented; nullable actor UUIDs are not authorization.
- No database migration was added: head remains `0009_topology_persistence`. No frontend, frontend client/types, worker work, or Phase 5F workspace was added. No AI/extraction, evidence, findings, review workflow, visualization, protection/study, or export functionality was added.

Phase 5F has not begun.
