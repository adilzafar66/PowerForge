# Phase 5G handoff — Hardening and final Phase 5 freeze

Completed and validated on 2026-10-26. **Phase 5A–5G are implemented; Phase 5 is complete, hardened and frozen. Phase 6 is next and has not started.**

## Baseline and delivery state

- Base branch: accepted `codex/phase-5f-model-workspace`.
- Exact base commit: `25b21b682ee7d4a92b94c16dd1629d949a2e9fc5` (`Updated docs for phase 5g`). This supersedes the prompt's preparation SHA and includes the explicit BOOLEAN selection fix and reconciled 243-test Phase 5F counts.
- Implementation branch: `codex/phase-5g-hardening`.
- Delivery: the Phase 5G implementation and this handoff are committed together on `codex/phase-5g-hardening`. The delivery commit is identified by `git log -1 --format=%H -- docs/PHASE5G_HANDOFF.md`; the base SHA above identifies the accepted starting point. Merging into `main` is a separate step.
- Authority: [Phase 5G prompt](prompts/phase-5g-codex.md), [Phase 5 specification](specs/phase-5-engineering-model.md), the authoritative registry-v1 JSON, and [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md).

## Corrective changes and exact contract

The correctness defect was canonical INTEGER response precision. PostgreSQL BIGINT and Python integers preserve `9007199254740993`, but the former JSON number response could round in JavaScript before the editor received it.

`AttributeResponse` now applies a JSON-only serializer to `integer_value`: every non-null integer becomes a base-10 string, and null remains null. Small values follow the same contract. Internal/domain/ORM integer values and input validation remain unchanged. No migration or arbitrary domain bounds were added.

```json
{"value_type":"INTEGER","integer_value":"9007199254740993"}
```

OpenAPI now declares `integer_value` as string-or-null. The frontend `EquipmentAttribute` type uses `string | null`; the existing generic editor retains the value as text through display, draft edits and submission. Existing NUMBER/Decimal strings, unit normalization, BOOLEAN explicit-choice guards, and manual provenance semantics remain intact. Revision `system_phase_count` is separate, remains a strict numeric 1/3 field, and does not need this attribute-slot representation.

This intentionally changes the external INTEGER response contract. Clients expecting a JSON number must adopt the consistent string representation; sending precise integer strings remains supported. No new endpoint, permission, request field or mutation authority was introduced.

The bounded performance review found one local frontend issue: each removed connection's restore check scanned all nodes. `TopologyWorkspace` now constructs an active-node ID set once per render and uses membership lookups. Eligibility and restore semantics are unchanged. No pagination, cache framework or global store was added.

## Changed files

| File | Change |
| --- | --- |
| `services/api/src/powerforge_api/schemas/model.py` | JSON-only lossless INTEGER serializer |
| `apps/web/src/lib/engineering-model.ts` | Canonical integer response type is string-or-null |
| `apps/web/src/components/topology-workspace.tsx` | Set membership for connection restore eligibility |
| `tests/test_model_api.py` | Updated small-integer response expectations; two integer round-trip cases; one HTTP snapshot/topology scenario |
| `tests/test_model_api_contract.py` | Explicit OpenAPI integer string/null contract and unchanged Decimal string/null contract |
| `apps/web/src/components/equipment-integer-roundtrip.test.tsx` | Two real JSON-decoder/editor/submission cases |
| `decisions/ADR-007-canonical-engineering-model-persistence.md` | Clarifies accepted revision metadata; corrects relay time-unit example to the authoritative registry |
| `docs/ENGINEERING_MODEL.md` | Current INTEGER contract, resolved precision debt, frozen registry/model |
| `docs/TOPOLOGY.md` | Verified topology boundary and bounded optimization |
| `docs/ARCHITECTURE.md` | Phase 5 freeze and lossless interface boundary |
| `docs/PROJECT_STATUS.md`, `docs/ROADMAP.md` | 5G implemented, Phase 5 complete/frozen, Phase 6 next/not started |
| `docs/PROVENANCE.md`, `docs/EXTRACTION.md`, `docs/VALIDATION.md` | Reconciles current implementation versus later planned workflows |
| `docs/PHASE5G_HANDOFF.md` | Audit, commands, results, debt and freeze verdict |

Historical Phase 5A–5F handoffs, registry-v1 implementation/reference, migrations, dependency manifests and lockfiles were not changed. Generated TypeScript build metadata was restored after validation.

## Requirements-to-implementation audit

Existing tests were inspected before new cases were added. The following suites provide the evidence; all were included in the passing full regression.

| Phase 5 criterion | Implementation and existing coverage relied upon | Outcome |
| --- | --- | --- |
| Exact code-owned registry, metadata, order and unit families | `registry_v1.py`, `test_engineering_registry.py::test_registry_matches_independent_approved_snapshot`, `test_engineering_registry_api.py` | Exact reference equality and deterministic API metadata; no runtime JSON/XLSX parsing |
| Deterministic normalization and requirement evaluation | Pure `units.py`, `registry.py`, `requirements.py`; `test_engineering_units.py`, `test_engineering_requirements.py` | Existing conversion, affine/semantic-unit, state and condition tests pass |
| ProjectRevision root, stable lineage and revision-scoped typed storage | `powerforge_persistence.projects/engineering`; `test_engineering_persistence.py`, `test_engineering_constraints.py`, `test_migration_0007.py` | No new aggregate; composite ownership/identity/typed-value constraints retained |
| Materialization, incomplete state and safe type changes | `EngineeringModelService`; `test_engineering_service.py` | Exact materialization, untouched defaults, meaningful-data protection, rollback and duplicate tags preserved |
| Metadata and independent carry-forward | `RevisionService`, `engineering_model_inheritance`; `test_phase5c_revision_model.py` | All four document/model combinations, defaults/explicit null, independent clones and registry-evolution failures covered |
| Snapshot isolation and transactional concurrency | `test_engineering_concurrency.py`, `test_topology_concurrency.py`, rollback cases in inheritance suites | Established project SHARE → revision UPDATE locks retained; competing-session tests pass |
| Node/connection ownership, lifecycle and clone remapping | `TopologyService`, `topology_support`, `topology_inheritance`; `test_topology_service.py`, `test_topology_constraints.py`, `test_topology_inheritance.py` | Same-revision endpoints, terminal shape, parallel edges, conservative cascades, immediate-base pointers and rollback covered |
| API ownership, mutability, allowlists and errors | `routers/model.py`, `schemas/model.py`; `test_model_api.py`, `test_model_api_contract.py` | Scoped 404s, backend read-only guards, explicit-null/omission, empty PATCH rejection, anti-forgery and sanitized consistency failures retained |
| Usable registry-driven manual UI, Documents default and deep links | `revision-workspace.test.tsx`, `model-editors.test.tsx`, existing document/project suites | Workspace navigation, filters, generic controls, units, topology and stale/read-only behavior pass |
| Lossless NUMBER and INTEGER interfaces | Existing decimal tests plus new API/frontend cases below | INTEGER defect resolved; decimal-string behavior unchanged |
| BOOLEAN requires explicit engineer choice | Existing `requires an explicit False choice for an unset boolean` regression | Preserved unchanged; state transition does not manufacture False |
| No Phase 6+ tables/workflows | Persistence/migration/router/service/frontend source audit and existing API/domain scope tests | No premature persistence or workflow introduced |
| Phase 0–4.5 regression and clean migrations | Full backend/frontend suites and existing `test_migration_0004` through `0009` coverage | Earlier behavior and data-preserving upgrade/downgrade checks pass |
| Documentation and ADR consistency | Current-facing docs and ADR-007 reviewed | Accepted architecture preserved; historical handoffs remain historical |

No material persistence or architectural conflict was found. Previously accepted unpaginated lists and deferred authentication are explicit limitations, not new exceptions introduced in 5G. The original specification's relay `trip_output_operating_time` milliseconds example conflicts with the authoritative JSON's seconds; the registry remains unchanged and ADR-007's illustrative example now states seconds. VFD/UPS output short-circuit trip time still uses milliseconds. This is a documentation correction, not a unit migration.

## New coverage and why it was necessary

Only five test cases were added:

1. Two parameterized live API cases (`3`, `9007199254740993`) manually write an INTEGER string, verify native integer storage through a fresh SQLAlchemy session, read it back through the list API, resubmit the returned value and verify state-only null behavior. Existing tests covered submission or small numeric responses, not this persistence-to-JSON boundary.
2. One HTTP carry-forward scenario creates representative precise NUMBER/INTEGER attributes, revision metadata, terminal/junction/connection topology, and a child snapshot. It checks inherited values, lineage, new IDs, endpoint remapping and source independence after child editing/removal. Existing lower-level clone/rollback tests remain the broader coverage; this closes the public API composition gap.
3. Two frontend cases use the real model request helper and real `Response.json()` decoding with JSON string payloads, then inspect the displayed editor and the actual PUT body after an edit/resubmission. These cover small and unsafe-range integers rather than only outgoing drafts. They use mocked HTTP transport, not a live browser.

The existing OpenAPI test was extended, and its former small-integer JSON number expectations were updated in the live API suite. No combinatorial expansion or new testing framework was added. The real-stack JavaScript smoke described below also consumes actual API payloads, linking live serialization to JavaScript decoding/resubmission; it is complementary to the editor component tests.

## Registry-v1 freeze

The independent snapshot mechanism compares all reference equipment/attribute metadata, enum choices, flags, notes, display order, requirement group/condition descriptions, requirement rows and unit families. The registry API test separately checks derived supported input units and typed executable conditions against the pure implementation. Existing unit tests check the supported conversions and restrictions. These mechanisms were retained instead of adding a second registry/snapshot implementation.

Confirmed totals: **20 equipment types, 296 attributes, 44 requirement reference rows (41 executable rows and 3 NONE notices), 17 unit families**. The pure package import test passes without site packages and does not read the reference JSON or XLSX at runtime.

SHA-256 at freeze:

- Reference JSON: `51db0d8845dbc4b49875ee3a2d6c876d98d0d9aa48835cfa7d0e8edacc85697e`.
- `registry_v1.py`: `d00d18252abbd8ef648e5281e29812b843f86eafcaf540ae38ca42817b339fb6`.

Both files are unchanged from the accepted baseline. Future semantic registry changes require deliberate versioning and migration planning.

## Persistence, lifecycle and scope review

Migrations 0007–0009 and neutral ORM mappings retain project/revision ownership, unique revision/lineage and equipment/attribute keys, typed slot/information-state consistency, lifecycle timestamps, same-project non-self inheritance references, terminal shape/uniqueness, endpoint ownership and self-loop prevention. No corrective migration was needed. Services still enforce the registry-specific semantics that are intentionally not encoded as database tables or arbitrary SQL checks.

Revision inheritance remains within the existing creation transaction, preserves stable lineages and semantic metadata, and remaps every cloned topology reference. Removed rows are excluded. Read-only and lifecycle protections remain backend-authoritative. No manual API can set origin, confidence, verification, actors or inheritance pointers.

The stale-code audit found no demonstrably dead Phase 5 placeholder requiring removal. Former equipment taxonomy and topology BUS placeholders had already been replaced. Document-processing Base/Project/ProjectRevision compatibility re-exports still have real callers and identity tests, so they were retained. Phase 0 provenance/extraction/validation contracts are intentional future boundaries, not new Evidence/Candidate/findings persistence, and were not deleted.

The source audit found no EngineeringModel table, containment field, Evidence/ExtractionCandidate/ExtractionRun tables, reconciliation/validation/verification workflow, graph/visualization state, protection/study configuration, vendor export structure or Phase 6 implementation. Existing classification runs are accepted Phase 4 behavior. Origin/verification/confidence vocabulary remains future-compatible metadata, not future workflow authority.

## Bounded performance review

Measured isolated database lists using fresh sessions and SQLAlchemy SELECT observation, at 1 and 25 BUS equipment snapshots, each with one terminal/connection plus one shared electrical node:

| Equipment | Resource | Returned rows | SELECTs | Loaded attributes | Observed elapsed |
| --- | --- | --- | --- | --- | --- |
| 1 | Equipment | 1 | 3 | No | 3.96 ms |
| 1 | Nodes | 2 | 5 | No | 4.40 ms |
| 1 | Connections | 1 | 5 | No | 4.35 ms |
| 25 | Equipment | 25 | 3 | No | 3.67 ms |
| 25 | Nodes | 26 | 5 | No | 4.76 ms |
| 25 | Connections | 25 | 5 | No | 4.74 ms |

These are observations, not production latency targets or a scalability certification. Query counts remain constant at these sizes; no per-row SELECT pattern was observed. Equipment summaries do not load attributes. Inheritance uses `selectinload` for attributes; topology uses bulk rows and maps. Frontend topology requests bulk equipment/nodes/connections rather than equipment per terminal. Registry data stays in the mounted workspace and existing cache/request-race tests pass.

The frontend active-node set removes the identified O(connections × nodes) repeated scan in restore checks. Unpaginated payloads, full topology consistency scans on reads/writes, and duplicate bulk topology reads across separate node/connection routes remain scaling debt. They do not justify new pagination/caching infrastructure in this bounded phase. Attribute lookup scans are bounded by the frozen registry size.

## Exact validation results

Commands ran on 2026-10-26. Backend tools use the existing `.venv`; frontend commands run from `apps/web`.

| Command | Result |
| --- | --- |
| `.venv/bin/ruff check .` | Passed |
| `.venv/bin/ruff format --check services/api/src/powerforge_api/schemas/model.py tests/test_model_api.py tests/test_model_api_contract.py` | All 3 changed Python files formatted |
| `.venv/bin/pip check` | No broken requirements |
| `.venv/bin/pytest tests/test_model_api_contract.py tests/test_engineering_registry.py tests/test_engineering_registry_api.py -q` | 38 passed, 6 existing warnings |
| `.venv/bin/pytest -q` | **506 passed, 551 skipped**, 6 existing warnings, 8.67 seconds |
| Full live command below | **1,057 passed, no skips**, 6 existing warnings, 72.12 seconds |
| `npm run lint` | Passed; no ESLint warnings/errors (existing Next lint-command deprecation notice) |
| `npm test` | **245 passed across 16 files**, 4.99 seconds |
| `npx tsc --noEmit` | Passed |
| `npm run build` | Passed; production compile, typecheck, page generation and build traces completed |
| `git diff --check` | Passed; new files also checked for whitespace |

The first OpenAPI assertion was too narrow for the existing Decimal schema's regex metadata; it was corrected to assert its string/null types without discarding that existing pattern. No production behavior was weakened. The six existing Python warnings concern Starlette/AnyIO and PyMuPDF/SWIG deprecations. Offline integration skips are reported separately and were all executed in the successful live run.

## Disposable infrastructure and migration/stack validation

A temporary resolved Compose configuration at `/tmp/powerforge-5g-compose.json` was derived from the repository Compose file with project name `powerforge-5g-validation`. It uses separate named PostgreSQL/MinIO volumes and network, localhost-only ports, fake classification and a blank OpenAI key. Ports: PostgreSQL 15432, Redis 16379, MinIO 19000/19001, API 18000, frontend 13000. Public storage/API URLs and CORS were adjusted for those ports; build contexts retained the repository paths. No application Compose defaults or development containers were changed.

```sh
docker compose -p powerforge-5g-validation -f /tmp/powerforge-5g-compose.json up --build -d
docker compose -p powerforge-5g-validation -f /tmp/powerforge-5g-compose.json exec -T postgres createdb -U powerforge powerforge_5g_tests
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:15432/powerforge_5g_tests .venv/bin/alembic -c database/alembic.ini upgrade head
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:15432/powerforge_5g_tests REDIS_URL=redis://localhost:16379/0 S3_ENDPOINT_URL=http://localhost:19000 S3_PUBLIC_ENDPOINT_URL=http://localhost:19000 RUN_INTEGRATION=1 CI=1 .venv/bin/pytest -q
```

Both the fresh application database and the separate integration database migrated from empty through **0009_topology_persistence**. The existing migration tests also ran their own scratch-database data-preserving upgrade/downgrade/re-upgrade checks. `CI=1` prevents unreachable MinIO from silently skipping storage tests; the live run had no skips. Tests used scratch buckets and the disposable database only.

Clean-stack observations:

- `/health`: status ok; `/ready`: status/database/Redis all ok.
- Fresh application database reports Alembic head `0009_topology_persistence`.
- Document, extraction and validation workers logged ready; Celery `inspect ping --timeout 3` returned three pongs.
- Frontend `/`, `/status`, project, revision Documents and model deep-link routes returned HTTP 200.
- A real HTTP scenario run with Node's JSON decoder created equipment, wrote/read/resubmitted small and large INTEGER values exactly, retained a precise NUMBER, saved explicit BOOLEAN false, created topology, cloned a child with metadata/model carry-forward, verified remapping and source independence, exercised conservative remove/restore and rejected a superseded-source edit with 409. The Documents list remained accessible.

Local run artifacts: `/tmp/powerforge-5g-{stack,migrate,live,offline,web-tests,web-build,services,cleanup}.log`, `/tmp/powerforge-5g-smoke.mjs`, `/tmp/powerforge-5g-smoke-result.json`, `/tmp/powerforge-5g-performance.py`, and `/tmp/powerforge-5g-performance.json`. They are session evidence, not committed runtime infrastructure.

Cleanup removes only this disposable project, including its test/application databases and volumes:

```sh
docker compose -p powerforge-5g-validation -f /tmp/powerforge-5g-compose.json down --volumes --remove-orphans
```

The normal `powerforge` development stack and its database/volumes were not destroyed or used for destructive testing.

## Browser validation, remaining debt and freeze verdict

**No actual browser/manual interaction tool was available.** No browser/visual smoke test or real-browser large-INTEGER display check is claimed. Frontend evidence consists of jsdom tests with real JSON decoding, full production build and server-route HTTP checks; actual API/JavaScript decoding/resubmission was additionally exercised against the clean stack. No Playwright/Cypress dependency was added.

Remaining debt: unpaginated lists and bulk topology scans; no browser end-to-end suite; component-local registry cache/drafts and no unsaved-change navigation guard; nullable actors pending authentication/authorization and full audit history; previously recorded document/classification recovery and storage cleanup concerns. These are recorded limitations, not unresolved canonical precision, revision isolation, ownership or mutability defects.

Zero runtime/frontend/infrastructure dependencies were added. No registry semantics, migration, Phase 6 functionality, general protection/study model, verification authority or visualization was introduced. Current-facing docs agree on ProjectRevision ownership, typed relational attributes, independent carry-forward, manual authoring, later evidence/validation/verification/visualization/study boundaries, and the frozen registry. Historical Phase 5A–5F handoffs remain unchanged.

**Freeze verdict:** every Phase 5 completion criterion in the requirements matrix is satisfied by the implementation and recorded checks. The canonical INTEGER correctness gap is resolved; full live regression, frontend regression and fresh migration/stack validation pass. Phase 5 is complete and frozen. Phase 6 remains unstarted and requires a separate instruction.
