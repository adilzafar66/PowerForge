# Phase 5D handoff — Canonical topology persistence

Phase 5D is implemented. Phase 5E has not begun.

## Branch and baseline

- Branch: `codex/phase-5d-topology-persistence`.
- Base: accepted `main` / `origin/main`, commit `328f10577f0f7cd2a4771bfbc73908fca4fad0e1`, including Phase 5C and strict phase-count validation.
- Specification: `docs/prompts/phase-5d-codex.md`, Phase 5 specification, and ADR-007.
- This handoff records local implementation and validation; it does not claim a commit, push, deployment, or merge.

## Changed files

- `packages/topology/src/powerforge_topology/{enums,__init__}.py`: pure domain vocabulary.
- `packages/persistence/src/powerforge_persistence/topology.py`: shared-Base ORM models; `packages/persistence/pyproject.toml` and `services/worker.Dockerfile`: topology package dependency and worker installation.
- `database/migrations/0009_topology_persistence.py`: frozen, reversible schema migration after `0008_revision_model_metadata`.
- `services/api/src/powerforge_api/services/topology_service.py`: internal manual topology operations.
- `services/api/src/powerforge_api/services/topology_support.py`: consistency checks, constraint translation, and transaction-local lifecycle helpers.
- `services/api/src/powerforge_api/services/topology_inheritance.py`: topology snapshot cloning.
- Existing `engineering_model_inheritance.py`, `engineering_model_service.py`, `revision_service.py`, and API `exceptions.py`: inheritance/lifecycle integration and domain errors.
- `tests/test_topology_{domain,service,constraints,inheritance,concurrency}.py`, `tests/topology_support.py`, and `tests/test_migration_0009.py`: new coverage. `tests/test_domain.py` updates vocabulary; `tests/test_migration_0008.py` pins historical migration tests to their historical head.
- `docs/{ARCHITECTURE,ENGINEERING_MODEL,TOPOLOGY,PROJECT_STATUS,ROADMAP,PHASE5D_HANDOFF}.md`: current implementation and next-phase documentation. The supplied Phase 5D prompt remains unchanged.

## Vocabulary and storage

The final enum vocabulary is:

| Enum | Members |
| --- | --- |
| `ModelNodeKind` | `EQUIPMENT_TERMINAL`, `ELECTRICAL_NODE` |
| `ConnectionKind` | `ELECTRICAL`, `GROUNDING`, `OTHER` |
| `ConnectionDirection` | `UNDIRECTED`, `NOMINAL_FROM_TO` |

The stale `NodeKind`/`BUS` topology semantics are removed. A bus or cable remains Equipment. Connections reference nodes, never equipment directly.

Both tables store UUID identity, project/revision ownership, lifecycle, origin, verification state, creation/update actor and timestamp, and removal actor and timestamp. Defaults are ACTIVE, MANUAL, and ENGINEER_REVIEWED. Existing lifecycle/origin/verification PostgreSQL enums are reused; migration 0009 owns only its three new topology enums.

`ModelNode` adds kind, optional equipment ID, terminal key, label, and `inherited_from_node_id`. A terminal requires same-project/same-revision Equipment and a nonblank key. An electrical node requires null equipment and terminal key. Terminal keys are unique per Equipment across lifecycle states. Named composite foreign keys enforce ownership. Inheritance stays within a project and cannot reference self.

`ModelConnection` adds from/to node IDs, connection kind, direction, optional phase text, nominal voltage/unit, confidence, and `inherited_from_connection_id`. Both endpoints must belong to its project/revision. Self-loops are rejected; parallel edges are permitted. Voltage is either entirely null or finite positive NUMERIC with canonical unit `kV`; confidence is null or finite NUMERIC in [0,1]. Inheritance stays within a project and cannot reference self.

Both tables enforce removal metadata consistency: REMOVED requires a removal timestamp; ACTIVE requires null removal actor/timestamp. Indexes support project/revision/lifecycle lookup, terminal equipment lookup, connection endpoint lookup, and inheritance lookup. Migration upgrade creates no topology rows. Downgrade drops connections before nodes, then only the new enum types.

## Internal operations and lifecycle

`TopologyService` implements `create_terminal`, `create_electrical_node`, `get_node`, `list_nodes`, `update_node`, `remove_node`, `restore_node`, `create_connection`, `get_connection`, `list_connections`, `update_connection`, `remove_connection`, and `restore_connection`.

Operations validate ownership and distinguish missing project, revision, and topology objects. Manual creation/editing uses MANUAL and ENGINEER_REVIEWED; connection edits clear confidence. Callers cannot supply verification, origin, confidence, or inheritance pointers through ordinary manual methods. Node kind and equipment ownership are immutable. Optional text is trimmed, blank optional text becomes null, and terminal keys cannot be blank. Removed objects must be restored before editing.

Nominal voltage uses the existing unit normalizer and Decimal arithmetic. For example, 600 V persists as Decimal 0.6 kV. Omitted input unit defaults to kV. Nonfinite, nonpositive, boolean, incompatible-unit, empty-unit, and unit-without-value input is rejected.

| Operation | Atomic effect |
| --- | --- |
| Remove connection | Soft-remove that connection |
| Remove node | Soft-remove node and active incident connections |
| Restore node | Restore node only; terminal parent must be active |
| Remove Equipment | Soft-remove Equipment, its terminals, and their incident connections |
| Restore removed Equipment | Restore Equipment and its terminals; leave connections removed |
| Restore connection | Require distinct active endpoints and valid active terminal parents |

Lifecycle changes retain existing provenance and update audit/removal metadata. No hard-delete operation is exposed.

## Snapshot inheritance and concurrency

With `carry_forward_model=true`, revision creation clones active topology after Equipment and Attributes. Terminal equipment IDs remap through the equipment clone map; connection endpoints remap through the node clone map. Standalone electrical nodes are included. Removed nodes/connections are excluded. New UUIDs and creation/update audit fields belong to the new snapshot, while origin, verification, connection confidence, and semantic metadata are preserved. Inheritance pointers reference the actual immediate-base objects, including on second-generation clones. Source and descendant edits are independent.

Validation rejects inconsistent active source topology, missing remaps, or the wrong base revision. Such failures roll back revision creation, activation, inherited documents, Equipment, Attributes, nodes, and connections together. Existing public inheritance count semantics remain unchanged.

Topology mutations use the established project SHARE then revision UPDATE lock order. They validate consistency before and after changes and commit once. Equipment lifecycle helpers and topology inheritance flush within their caller's transaction without independent commits. No project-lock upgrade is introduced. A live PostgreSQL concurrency test pauses node removal after its connection cascade and verifies revision cloning waits, then observes the complete committed topology rather than a partial cascade.

## Validation

New coverage checks exact pure enum vocabulary, voltage normalization, service ownership and writable-revision guards, immutable ownership, rewiring, provenance, lifecycle recovery, direct PostgreSQL constraints, parallel edges, graph remapping, immediate-base pointers, descendant independence, corruption failures, injected rollback, lock order, and a concurrent clone/cascade race. Migration tests compare ORM/schema columns, types, enums, named constraints, foreign keys, and indexes, and exercise upgrade/downgrade/re-upgrade with existing equipment data preserved.

Commands and final results:

```sh
.venv/bin/pip install --no-deps -e packages/persistence
# Succeeded; refreshes editable dependency metadata.
.venv/bin/pip check
# No broken requirements found.

docker compose exec -T postgres createdb -U powerforge powerforge_phase5d_20261023
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5d_20261023 .venv/bin/alembic -c database/alembic.ini upgrade head
# Succeeded through 0009_topology_persistence.

DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_phase5d_20261023 RUN_INTEGRATION=1 .venv/bin/pytest -q
# 1024 passed, 6 existing dependency deprecation warnings, 70.34 seconds; no skips.
.venv/bin/pytest -q
# 496 passed, 528 integration tests skipped, 6 existing dependency warnings.
.venv/bin/ruff check .
# All checks passed.
git diff --check
# Passed.

docker compose exec -T postgres dropdb -U powerforge powerforge_phase5d_20261023
# Succeeded; disposable database removed after validation.
```

Ruff formatting checks also passed for the new migration, topology package, ORM, topology services, and new tests. The development database was not migrated or modified. No frontend changes were made, so frontend checks were not run. Worker images were not rebuilt or deployed.

## Limitations and scope boundary

There are no architectural deviations from the Phase 5D scope. Consistency validation currently bulk-loads the revision's topology and equipment, including on reads; larger graphs may require targeted validation and pagination later. Authentication/authorization remains a separate planned concern, as in prior phases; audit actor IDs do not constitute authorization.

No public topology CRUD routes, frontend editing, graph algorithms, inferred connectivity, evidence, AI extraction, visualization, containment, terminal registry, protection relations, or study/scenario behavior was added. Phase 5E is next and has not begun.
