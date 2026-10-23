# Phase 5C implementation report

Phase 5C implements revision model inheritance and revision-level engineering metadata. Phase 5D has not begun.

## Baseline and scope

Branch: `codex/phase-5c-revision-inheritance`, based on accepted Phase 5B plus the merged roadmap documentation at commit `09a44aa` on `main`/`origin/main`.

The implementation follows [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md), the [Phase 5 specification](specs/phase-5-engineering-model.md), the accepted [Phase 5B handoff](PHASE5B_HANDOFF.md), and the Phase 5C prompt. Registry-v1 and all Phase 5A requirement/unit definitions remain unchanged.

Phase 5C changes:

- `database/migrations/0008_revision_model_metadata.py` advances Alembic head from `0007_engineering_model_core`.
- `powerforge_persistence.projects.ProjectRevision` maps the new metadata.
- `powerforge_engineering_model.effective_values` provides pure effective-value and mismatch semantics.
- `powerforge_api.services.engineering_model_inheritance` owns transactional snapshot cloning.
- The revision schemas, service, router, domain errors, and error mapping expose and enforce the new behavior.
- The existing revision-create UI adds only the independent model carry-forward checkbox and reports the model inheritance count.
- Phase 5C migration, domain, service, transaction, registry-evolution, concurrency, API, and UI tests were added or extended.

No topology persistence, public equipment CRUD API, Engineering Model workspace, AI extraction, Evidence/Candidate persistence, reconciliation, validation-finding persistence, or export behavior was added.

## Revision metadata

`ProjectRevision` now has:

| Field | Persistence | Meaning and constraint |
| --- | --- | --- |
| `system_frequency` | nullable PostgreSQL `NUMERIC` / Python `Decimal` | Canonical Hz; null or finite and greater than zero |
| `system_phase_count` | nullable PostgreSQL `INTEGER` | Null, 1, or 3 |

Named database constraints are `ck_project_revisions_system_frequency_positive` and `ck_project_revisions_system_phase_count`. Existing revisions receive null values. The migration is reversible and preserves existing engineering rows through downgrade and re-upgrade.

Both fields are accepted on revision create and patch and returned on create/list/get responses. Metadata patching uses the engineering/document mutability rules: ACTIVE or PAUSED projects with DRAFT or ACTIVE revisions are writable; SUPERSEDED revisions and ARCHIVED or CANCELLED projects are read-only.

## Carry-forward and metadata resolution

`carry_forward_model` is independent of `carry_forward_documents`:

| Selected base | Request value | Resolved behavior |
| --- | --- | --- |
| yes | omitted or null | true |
| yes | true | true |
| yes | false | false |
| no | omitted, null, or false | false |
| no | true | rejected as `invalid_base_revision` |

When model carry-forward is true, omitted `system_frequency` and `system_phase_count` inherit from the selected base. An explicitly supplied value overrides the base, and explicit null clears it. When model carry-forward is false, omitted metadata remains null while explicit values still apply. Without a base, omitted and explicit-null fields remain null and explicit valid values are stored.

`inherited_model_equipment_count` appears only on the create result, independently from `inherited_document_count`; later list/get responses return no creation count.

## Snapshot clone behavior

The clone helper receives the selected source and newly inserted target revision and does not commit. It rejects an arbitrary source that is not the target's immediate base. It selects only ACTIVE equipment and eagerly loads attributes in deterministic order.

Each destination equipment row receives a new ID, keeps the project-owned `lineage_id`, preserves type/tag/name/description/origin/verification, starts ACTIVE, and points `inherited_from_equipment_id` to the actual source row in the selected base. REMOVED equipment is excluded.

Compatible attributes receive new IDs and preserve key, value type, canonical unit, information state, verification state, origin, confidence, and the exact canonical typed value. `inherited_from_attribute_id` points to the source attribute row. Source and destination are independent snapshots: later metadata, value, remove, or restore operations on either do not mutate the other.

Registry evolution is conservative:

- a destination-only registry attribute materializes as NOT_EXTRACTED / UNVERIFIED, with null origin, confidence, value, and inheritance pointer;
- an old-only or incompatible source attribute may be omitted only when it is still an untouched placeholder;
- a meaningful old-only attribute, changed value type/unit, or invalidated PRESENT enum value raises `model_inheritance_conflict`;
- no source row is mutated and no meaningful value is coerced or silently discarded.

## Transactions and locks

Revision insert, document inheritance, model inheritance, metadata resolution, optional activation, and project timestamp update are one transaction owned by `RevisionService`. The clone helper only flushes. Any failure rolls back the target revision, document associations, equipment, attributes, metadata, and activation changes. Tests inject failures after revision/document work, during model/attribute cloning, during metadata resolution, and before activation.

Revision creation uses the existing project then revision lock order. The base revision remains locked while its model is read; engineering writers take the same project then revision order. A real competing-session test proves a clone observes a complete before-state while a model mutation waits and commits afterward. Existing archive, cancel, supersede, and activation concurrency tests continue to pass.

## Effective values

`resolve_effective_model_value()` implements the Phase 5C rule for applicable frequency and phase-count attributes:

1. an explicit PRESENT equipment value wins;
2. otherwise the revision value is used;
3. otherwise the result is unspecified.

If both values exist and differ, `mismatch` is true. Neither value is overwritten, equipment information state and provenance stay unchanged, and no Phase 10 validation finding is persisted.

## Validation

Validation ran on 2026-10-23 with Python 3.12 and the existing local Docker services. Live tests used the disposable PostgreSQL database `powerforge_phase5c_20261023`, migrated from an empty database through `0008_revision_model_metadata`.

```sh
.venv/bin/pytest -q
```

Result: **478 passed, 484 skipped, 6 dependency deprecation warnings**. Skips are opt-in live integrations.

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5c_20261023 RUN_INTEGRATION=1 .venv/bin/pytest -q
```

Result: **962 passed, none skipped, 6 dependency deprecation warnings**. This includes fresh migration, upgrade from 0007 with existing model rows, constraint, downgrade/re-upgrade, rollback, and real PostgreSQL concurrency coverage.

The disposable database was dropped after validation; the development database was not used.

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check <all changed Phase 5C Python files>
.venv/bin/pip check
git diff --check
```

Result: all Phase 5C lint, formatting, dependency, and whitespace checks pass. A repository-wide format check still reports pre-existing formatting drift in unrelated historical files; those files were left unchanged.

```sh
cd apps/web
npm run lint
npm test
npx tsc --noEmit
npm run build
```

Result: lint passed with no warnings or errors; **213 frontend tests passed**; TypeScript passed; the Next.js production build completed successfully.

## Decisions and remaining concerns

- Revision-create UI was changed because the accepted Phase 5 plan assigns its model carry-forward option to Phase 5C. The change is limited to that checkbox, request field, and count message.
- The effective-value utility is pure and caller-scoped to applicable registry attributes. Persistent findings and policy enforcement remain Phase 10 work.
- Actor IDs remain nullable because authentication and trustworthy audit identity are not implemented.
- The inherited equipment count is computed during creation and is not stored.
- No Phase 5C blocker or ADR-007 conflict remains.

**Phase 5D has not begun.**
