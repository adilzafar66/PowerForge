# PowerForge Phase 5D — Canonical Topology Persistence

You are implementing **Phase 5D only** of PowerForge.

Phase 5A, Phase 5B, and Phase 5C are complete and accepted.

Phase 5D establishes the manually authored canonical electrical-topology layer for the revision-scoped engineering model.

The primary deliverables are:

- canonical topology domain enums/contracts;
- persistent `ModelNode`;
- persistent `ModelConnection`;
- strong project/revision/equipment/endpoint ownership constraints;
- internal/manual topology authoring services;
- soft topology lifecycle;
- conservative equipment ↔ topology lifecycle behavior;
- topology cloning/remapping during revision model carry-forward;
- migration, concurrency, integrity, and regression tests.

Do **not** proceed to Phase 5E or later.

Phase 5D does **not** add the public engineering-model/topology CRUD API, the Engineering Model frontend workspace, graph visualization, AI topology extraction, Evidence, reconciliation, validation findings, protection settings, study scenarios, or exports.

---

# 1. Authoritative inputs

Before editing, read and understand:

```text
docs/specs/phase-5-engineering-model.md
decisions/ADR-007-canonical-engineering-model-persistence.md
docs/ENGINEERING_MODEL.md
docs/TOPOLOGY.md
docs/PHASE5B_HANDOFF.md
docs/PHASE5C_HANDOFF.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
```

Inspect the accepted implementation in:

```text
packages/engineering-model/src/powerforge_engineering_model/
packages/topology/
packages/persistence/src/powerforge_persistence/
services/api/src/powerforge_api/services/engineering_model_service.py
services/api/src/powerforge_api/services/engineering_model_inheritance.py
services/api/src/powerforge_api/services/revision_writes.py
services/api/src/powerforge_api/services/revision_service.py
services/api/src/powerforge_api/exceptions.py
services/api/src/powerforge_api/db_errors.py
database/migrations/0007_engineering_model_core.py
database/migrations/0008_revision_model_metadata.py
tests/
```

Source-of-truth order:

1. this Phase 5D prompt for Phase 5D scope and clarifications;
2. `docs/specs/phase-5-engineering-model.md`;
3. ADR-007;
4. accepted Phase 5A–5C code/handoffs;
5. current repository conventions.

If repository reality materially conflicts with a required invariant, stop and report the conflict rather than silently weakening the invariant.

---

# 2. Baseline

Start from the accepted Phase 5C implementation.

At the time this prompt was prepared, the accepted Phase 5C branch is:

```text
codex/phase-5c-revision-inheritance
```

with accepted head:

```text
328f10577f0f7cd2a4771bfbc73908fca4fad0e1
```

That head includes the strict `system_phase_count` validation fix.

If Phase 5C has since been merged to `main`, use the updated `main`.

Before editing, confirm the baseline contains:

```text
0008_revision_model_metadata
EquipmentLineage
Equipment
EquipmentAttribute
ProjectRevision.system_frequency
ProjectRevision.system_phase_count
carry_forward_model
copy_active_engineering_model(...)
inherited_from_equipment_id
inherited_from_attribute_id
neutral packages/persistence
shared revision-write locking
```

Do not start from Phase 5B or an earlier branch.

---

# 3. Phase 5D scope

Phase 5D MUST deliver:

```text
ModelNode persistence
ModelConnection persistence

ModelNodeKind:
    EQUIPMENT_TERMINAL
    ELECTRICAL_NODE

ConnectionKind:
    ELECTRICAL
    GROUNDING
    OTHER

ConnectionDirection:
    UNDIRECTED
    NOMINAL_FROM_TO

manual/internal topology services
soft node lifecycle
soft connection lifecycle
equipment removal -> terminal/connection soft removal
equipment restore -> terminal restore only
node removal -> incident connection soft removal
node restore -> no automatic connection restore
connection restore safety checks
topology revision cloning/remapping
topology inheritance provenance
migration 0009 or repository-conventional equivalent
database integrity constraints
service/domain errors
tests
documentation/handoff updates
```

Phase 5D MUST NOT implement:

```text
public topology HTTP CRUD routes
public equipment/attribute CRUD routes
Engineering Model workspace UI
React Flow
one-line visualization
automatic terminal generation
AI topology inference
SLD interpretation
Evidence
ExtractionCandidate
reconciliation/conflict persistence
persistent validation findings
ProtectionFunction
study operating scenarios
ETAP/SKM/EasyPower integration
engineering report generation
equipment containment / parent_equipment_id
```

---

# 4. Canonical topology principle

The database topology is canonical engineering state.

An SLD is **not** the database.

The long-term relationship remains:

```text
SLD / document evidence
        ↓
future topology candidates (Phase 8)
        ↓
review/reconciliation
        ↓
canonical ModelNode / ModelConnection
```

Phase 5D creates only the canonical manually authored target.

Do not store:

```text
document_id
document_page_id
bounding boxes
OCR text
AI rationale
```

on topology rows as provenance shortcuts.

Full evidence/candidate provenance remains Phase 6+.

---

# 5. No direct equipment-to-equipment connections

Connections MUST connect topology nodes.

Never model this:

```text
Equipment A ───────── Equipment B
```

as direct equipment foreign keys on `ModelConnection`.

Instead:

```text
Equipment A
  └─ terminal node
        │
        └─ ModelConnection
              │
              └─ terminal/electrical node
```

This is mandatory because equipment may have multiple terminals and multiple connectivity relationships.

---

# 6. Cable remains Equipment

A cable is canonical `CABLE` Equipment.

Do not introduce:

```text
CABLE connection_kind
```

The canonical representation is conceptually:

```text
upstream terminal/node
        │
   ModelConnection
        │
Cable terminal A
[CABLE Equipment]
Cable terminal B
        │
   ModelConnection
        │
downstream terminal/node
```

This preserves cable engineering attributes independently from connectivity.

---

# 7. Reconcile the stale topology placeholder

The current placeholder topology package contains a stale `NodeKind.BUS`.

That does **not** match ADR-007 or the approved Phase 5 specification.

The canonical Phase 5D node kinds are exactly:

```text
EQUIPMENT_TERMINAL
ELECTRICAL_NODE
```

There is no topology `BUS` node kind.

A physical bus/switchgear/switchboard/panelboard/MCC is canonical `BUS` Equipment with one or more `EQUIPMENT_TERMINAL` nodes.

A pure connectivity junction is `ELECTRICAL_NODE`.

Update `packages/topology` accordingly.

You may preserve a harmless Python import alias only if repository compatibility genuinely requires one, but:

- persisted values must use the approved vocabulary;
- no `BUS` node-kind semantics may remain;
- tests must assert the exact approved domain vocabulary.

Do not add additional node kinds.

---

# 8. Pure topology domain package

`packages/topology` remains infrastructure-neutral.

It MUST NOT depend on:

```text
SQLAlchemy
FastAPI
Celery
AI providers
document-processing
frontend code
```

It should own the closed topology contracts/enums.

Implement/export equivalents of:

```python
ModelNodeKind
ConnectionKind
ConnectionDirection
```

with persisted semantic values exactly equivalent to:

```text
EQUIPMENT_TERMINAL
ELECTRICAL_NODE

ELECTRICAL
GROUNDING
OTHER

UNDIRECTED
NOMINAL_FROM_TO
```

Follow repository naming conventions, but do not change these meanings.

---

# 9. Persistence location

Topology persistence belongs with the canonical engineering model in the neutral persistence layer.

Prefer:

```text
packages/persistence/src/powerforge_persistence/engineering.py
```

or a small sibling topology persistence module if that keeps the file maintainable.

Do not place topology ORM mappings in:

```text
document-processing
packages/topology
frontend
```

There must remain one shared SQLAlchemy `Base`.

If `packages/persistence` now imports topology domain enums, update package dependency metadata and build/install configuration as required.

Avoid unrelated package reorganization.

---

# 10. New tables

Create exactly the Phase 5D topology tables:

```text
model_nodes
model_connections
```

Do not create:

```text
engineering_models
terminal_definitions
topology_snapshots
containment
evidence
candidate
validation
```

tables.

---

# 11. ModelNode persistence

Required logical fields:

```text
id
project_id
revision_id

kind
equipment_id
terminal_key
label

lifecycle_status
origin
verification_state

inherited_from_node_id

created_at
created_by
updated_at
updated_by
removed_at
removed_by
```

No confidence field is required on `ModelNode` in Phase 5.

---

# 12. ModelNode kinds and shape constraints

## EQUIPMENT_TERMINAL

Must satisfy:

```text
kind = EQUIPMENT_TERMINAL
equipment_id IS NOT NULL
terminal_key IS NOT NULL
```

`terminal_key` must be a non-blank flexible string after service normalization.

There is no Phase 5 terminal-definition registry.

Examples may eventually include:

```text
PRIMARY
SECONDARY
LINE
LOAD
A
B
INPUT
OUTPUT
```

but do not restrict terminal keys to a premature enum.

## ELECTRICAL_NODE

Must satisfy:

```text
kind = ELECTRICAL_NODE
equipment_id IS NULL
terminal_key IS NULL
```

`label` remains optional.

Use `ELECTRICAL_NODE` for a pure junction/connectivity point.

---

# 13. Terminal uniqueness

A terminal key is unique within one equipment snapshot.

Enforce the equivalent of:

```text
UNIQUE (equipment_id, terminal_key)
```

for terminal rows.

Duplicate terminal keys on different equipment are allowed.

Electrical nodes have null equipment/terminal keys and must not be affected by this uniqueness rule.

---

# 14. ModelNode ownership

An equipment terminal must reference Equipment in the **same project and revision**.

Enforce this at the database level using the existing composite ownership pattern.

Do not rely solely on application code.

The topology table should carry the same denormalized:

```text
project_id
revision_id
```

ownership strategy used by EquipmentAttribute because it makes cross-revision topology corruption structurally harder.

---

# 15. ModelNode lifecycle

Use the existing:

```text
LifecycleStatus:
    ACTIVE
    REMOVED
```

Manual topology creation defaults to:

```text
lifecycle_status = ACTIVE
origin = MANUAL
verification_state = ENGINEER_REVIEWED
```

Use the same semantic `ValueOrigin` / `VerificationState` vocabulary already introduced in Phase 5B.

Do not create topology-specific copies of those enums.

Lifecycle invariants should match Equipment:

```text
ACTIVE:
    removed_at = NULL
    removed_by = NULL

REMOVED:
    removed_at IS NOT NULL
```

`removed_by` remains nullable until auth exists.

No public or service hard delete.

---

# 16. ModelNode inheritance

Add:

```text
inherited_from_node_id
```

It is nullable.

At the DB level, enforce at least same-project ownership and self-reference rejection following existing Phase 5 patterns.

At the application clone layer, enforce the stronger invariant:

> A destination node's `inherited_from_node_id` must point to the corresponding source node in the destination revision's actual selected base revision.

Do not let arbitrary same-project revisions become topology inheritance sources.

---

# 17. ModelConnection persistence

Required logical fields:

```text
id
project_id
revision_id

from_node_id
to_node_id

connection_kind
direction
phase_configuration

nominal_voltage
nominal_voltage_unit

lifecycle_status
origin
verification_state
confidence

inherited_from_connection_id

created_at
created_by
updated_at
updated_by
removed_at
removed_by
```

---

# 18. ModelConnection enum semantics

Connection kinds are exactly:

```text
ELECTRICAL
GROUNDING
OTHER
```

Directions are exactly:

```text
UNDIRECTED
NOMINAL_FROM_TO
```

`UNDIRECTED` is expected for ordinary physical connectivity.

`NOMINAL_FROM_TO` means the `from_node_id → to_node_id` ordering has descriptive engineering significance.

It is **not** a load-flow result and does not assert instantaneous real/reactive power direction.

Do not add reverse-direction or bidirectional calculation states in Phase 5D.

---

# 19. Connection endpoints

Both endpoints must:

- exist;
- belong to the same `project_id`;
- belong to the same `revision_id`;
- belong to the same project/revision as the connection.

Use composite DB foreign keys so cross-project/cross-revision endpoint references are rejected structurally.

Reject:

```text
from_node_id == to_node_id
```

with a named DB check constraint and clean service error.

Parallel edges are explicitly allowed.

Do **not** create a unique constraint on:

```text
(from_node_id, to_node_id)
```

or the unordered endpoint pair.

---

# 20. Active-endpoint semantics

An ACTIVE connection must be created/restored only when both endpoints are ACTIVE.

Application services must enforce this.

When an endpoint node is removed, incident ACTIVE connections are soft-removed in the same transaction.

Restoring a node must **not** automatically restore its old connections.

This preserves conservative connectivity semantics.

DB constraints do not need cross-row lifecycle triggers in Phase 5D; keep this invariant in the service layer and test it thoroughly.

---

# 21. phase_configuration

`phase_configuration` remains optional text in Phase 5.

Do not create a large phase-topology subsystem or enum.

Do not automatically populate it from:

```text
ProjectRevision.system_phase_count
Equipment.phase_count
```

The current revision-level `system_phase_count` is a common/default model assumption, while explicit equipment data may override it for individual equipment.

Phase 5D must not invent a topology mismatch policy.

Future validation can reason about these values.

For manual service input:

- trim surrounding whitespace;
- treat blank text as null or reject consistently with repository conventions;
- otherwise preserve the supplied engineering text.

---

# 22. nominal_voltage

When supplied, connection nominal voltage is stored canonically as:

```text
nominal_voltage: NUMERIC / Decimal
nominal_voltage_unit: "kV"
```

Input may use compatible voltage units supported by the existing unit system, e.g.:

```text
V
kV
MV
```

Use the accepted decimal-safe unit conversion utility rather than duplicating conversion logic.

The service should normalize to `kV`.

Do not use binary float persistence.

DB rules:

```text
nominal_voltage IS NULL
    -> nominal_voltage_unit IS NULL

nominal_voltage IS NOT NULL
    -> finite
    -> > 0
    -> nominal_voltage_unit = 'kV'
```

Do not add a separate unit enum for this one field.

---

# 23. Connection confidence

`confidence` is nullable Decimal/NUMERIC.

When present:

```text
0 <= confidence <= 1
finite
```

Manual connection creation/editing in Phase 5D uses:

```text
origin = MANUAL
verification_state = ENGINEER_REVIEWED
confidence = NULL
```

The ordinary manual service must not allow clients/callers to forge:

```text
AI_EXTRACTION
AI_EXTRACTED
SYSTEM_VALIDATED
ENGINEER_VERIFIED
arbitrary confidence
```

Future extraction/review workflows will have separate trusted paths.

---

# 24. Connection lifecycle and inheritance

Use:

```text
ACTIVE
REMOVED
```

with the same removal timestamp/actor invariant as Equipment/ModelNode.

Add:

```text
inherited_from_connection_id
```

DB layer:

- same-project reference at minimum;
- reject self-reference.

Clone layer:

> inherited_from_connection_id must reference the corresponding source connection in the actual selected base revision.

No hard delete.

---

# 25. PostgreSQL enums

Follow the Phase 5B pattern.

Reuse existing closed enums for:

```text
model_lifecycle_status
model_value_origin
model_verification_state
```

Create migration-owned enum types for topology closed vocabularies, conceptually:

```text
model_node_kind
model_connection_kind
model_connection_direction
```

with the exact approved labels.

Do not create a PostgreSQL enum for:

```text
terminal_key
phase_configuration
nominal_voltage_unit
```

---

# 26. Migration

Create the next migration after:

```text
0008_revision_model_metadata
```

Expected conceptual name:

```text
0009_topology_persistence
```

or repository-conventional equivalent.

The migration must:

1. create topology enum types if used;
2. create `model_nodes`;
3. create `model_connections`;
4. create named ownership FKs/checks/uniques/indexes;
5. create no topology rows for existing revisions;
6. not infer topology from Equipment;
7. not create terminals automatically;
8. downgrade cleanly by removing connection table first, then node table, then Phase 5D enum types;
9. preserve all Phase 5A–5C data on downgrade.

---

# 27. Required database constraints — ModelNode

Use named constraints consistent with repository style.

At minimum enforce:

- project/revision ownership;
- terminal equipment belongs to same project/revision;
- node kind ↔ equipment/terminal shape;
- unique terminal key within an equipment snapshot;
- inherited node cannot reference itself;
- inherited node same-project ownership;
- lifecycle/removal timestamp consistency.

Provide supporting composite unique constraints required for FKs, e.g. the equivalent of:

```text
(project_id, id)
(project_id, revision_id, id)
```

where needed.

Do not depend on globally unique UUID semantics alone when a composite FK can enforce ownership.

---

# 28. Required database constraints — ModelConnection

At minimum enforce:

- project/revision ownership;
- both endpoints belong to same project/revision;
- self-loop rejected;
- lifecycle/removal consistency;
- confidence bounded and finite;
- nominal voltage canonical-unit/value pairing;
- nominal voltage positive and finite when present;
- inherited connection cannot reference itself;
- inherited connection same-project ownership.

Parallel edges must remain legal.

---

# 29. Indexes

Add practical indexes for later Phase 5E query patterns.

At minimum consider:

```text
model_nodes(project_id, revision_id, lifecycle_status)
model_nodes(equipment_id)
model_nodes(inherited_from_node_id)

model_connections(project_id, revision_id, lifecycle_status)
model_connections(from_node_id)
model_connections(to_node_id)
model_connections(inherited_from_connection_id)
```

The terminal uniqueness constraint already provides its own supporting index.

Do not over-index speculative future graph queries.

---

# 30. Manual topology service

Implement an internal service or small set of services consistent with the existing API service layer.

A reasonable name is:

```text
TopologyService
```

This is **not** a public HTTP API in Phase 5D.

It should support internal/manual operations equivalent to:

## Nodes

```text
create equipment terminal
create electrical node
get node
list nodes
update node metadata
remove node
restore node
```

## Connections

```text
create connection
get connection
list connections
update connection
remove connection
restore connection
```

Exact method names may follow repository style.

---

# 31. Service scoping

Every topology operation is scoped by:

```text
project_id
revision_id
```

Never trust object ownership from a caller without checking.

Reads should distinguish:

```text
project not found
revision not found
node not found in revision
connection not found in revision
equipment not found in revision
```

Writes must use existing project/revision mutability and locking.

---

# 32. Mutability and lock order

Reuse:

```text
lock_writable_revision(...)
```

and the established:

```text
project FOR SHARE
    ↓
revision FOR UPDATE
```

order.

Do not create a second topology-specific lifecycle or lock hierarchy.

Writes are allowed for the same project/revision states already accepted for engineering writes:

```text
project ACTIVE / PAUSED
revision DRAFT / ACTIVE
```

Reject:

```text
project ARCHIVED
project CANCELLED
revision SUPERSEDED
```

Reads remain available.

---

# 33. Node creation behavior

## Create equipment terminal

Require:

- writable revision;
- Equipment exists in same project/revision;
- Equipment is ACTIVE;
- nonblank terminal key;
- no duplicate key on that equipment.

Create:

```text
kind = EQUIPMENT_TERMINAL
equipment_id = selected equipment
terminal_key = normalized key
label = optional
lifecycle_status = ACTIVE
origin = MANUAL
verification_state = ENGINEER_REVIEWED
inherited_from_node_id = NULL
```

Do not auto-create terminals based on equipment type.

## Create electrical node

Create:

```text
kind = ELECTRICAL_NODE
equipment_id = NULL
terminal_key = NULL
label = optional
lifecycle_status = ACTIVE
origin = MANUAL
verification_state = ENGINEER_REVIEWED
inherited_from_node_id = NULL
```

No EquipmentLineage concept is needed for electrical nodes in Phase 5.

Topology node history across revisions is represented by `inherited_from_node_id`.

---

# 34. Node update behavior

Keep node identity conservative.

For Phase 5D:

- `kind` is immutable after creation;
- terminal `equipment_id` is immutable after creation;
- a terminal's `terminal_key` may be edited subject to uniqueness/nonblank validation;
- `label` may be edited;
- electrical nodes cannot acquire an equipment or terminal key through update.

If changing equipment ownership is required later, the caller can create a new terminal and reconnect deliberately rather than silently changing a node's semantic identity.

Manual edits keep:

```text
origin = MANUAL
verification_state = ENGINEER_REVIEWED
```

for manually authored Phase 5D topology.

Do not add a general verification action.

---

# 35. Connection creation behavior

Require:

- writable revision;
- both nodes exist in same project/revision;
- both nodes are ACTIVE;
- endpoints differ;
- approved connection kind;
- approved direction;
- optional phase configuration;
- optional nominal voltage normalized to kV.

Create:

```text
lifecycle_status = ACTIVE
origin = MANUAL
verification_state = ENGINEER_REVIEWED
confidence = NULL
inherited_from_connection_id = NULL
```

Parallel connections between the same nodes are allowed.

---

# 36. Connection update behavior

Allow deliberate manual editing of:

```text
from_node_id
to_node_id
connection_kind
direction
phase_configuration
nominal_voltage
```

If endpoints are changed:

- both new endpoints must belong to the same current project/revision;
- both must be ACTIVE;
- self-loop remains forbidden.

Normalize voltage again.

Do not silently reverse endpoints because direction changes.

Do not deduplicate parallel edges.

Editing a REMOVED connection requires restore first.

---

# 37. Manual node lifecycle

## Remove node

Soft-remove the node.

In the same transaction:

- soft-remove every ACTIVE incident connection.

Do not delete anything.

## Restore node

Restore only the node.

Do **not** restore previously removed incident connections.

For an `EQUIPMENT_TERMINAL`, restoration requires its Equipment to be ACTIVE.

For an `ELECTRICAL_NODE`, no equipment condition applies.

This makes manual node lifecycle conservative in the same way as equipment lifecycle.

---

# 38. Equipment removal topology cascade

Extend the accepted `EngineeringModelService.remove_equipment(...)` transaction.

Removing Equipment MUST:

1. mark Equipment `REMOVED`;
2. retain EquipmentAttribute rows;
3. soft-remove every ACTIVE `EQUIPMENT_TERMINAL` belonging to the Equipment;
4. soft-remove every ACTIVE ModelConnection incident to those terminals.

All changes must commit atomically.

Do not hard-delete nodes/connections.

Do not alter electrical nodes merely because their neighboring equipment was removed.

Do not change topology `origin` or `verification_state` merely because lifecycle changes.

---

# 39. Equipment restore topology behavior

Extending `restore_equipment(...)`:

1. restore Equipment to ACTIVE;
2. restore its existing removed `EQUIPMENT_TERMINAL` nodes;
3. **do not automatically restore any removed connections**.

This behavior is intentionally conservative.

For Phase 5D, restoring equipment restores its existing terminal-node records. Connections must be explicitly restored/recreated after an engineer confirms connectivity.

Do not infer replacement connections.

---

# 40. Connection restore behavior

Restoring a connection is allowed only when:

- both endpoints still exist;
- both endpoints are ACTIVE;
- both endpoints are still in the same project/revision;
- the connection remains non-self-loop.

Otherwise return a clean topology-state error.

Restoration does not modify endpoint lifecycle.

---

# 41. Revision inheritance must now include topology

Phase 5C intentionally cloned only Equipment/EquipmentAttribute because topology did not yet exist.

Phase 5D MUST extend model carry-forward so the complete Phase 5D model snapshot becomes:

```text
Equipment
EquipmentAttribute
ModelNode
ModelConnection
```

when:

```text
carry_forward_model = true
```

Do not change the independent document/model carry-forward semantics established in 5C.

---

# 42. Topology clone algorithm

Extend the existing `copy_active_engineering_model(...)` path or cleanly compose a topology clone helper into it.

The revision service still owns the transaction and commit.

Required order:

```text
1. clone ACTIVE Equipment
2. clone EquipmentAttribute
3. build source_equipment_id -> destination_equipment_id mapping
4. select/clone ACTIVE ModelNode
5. remap terminal equipment_id through the equipment map
6. build source_node_id -> destination_node_id mapping
7. clone ACTIVE ModelConnection
8. remap both endpoints through node map
9. flush
```

Do not commit inside the clone helper.

---

# 43. Node clone behavior

For every ACTIVE source node:

Create a new destination node ID.

Preserve:

```text
kind
terminal_key
label
origin
verification_state
```

Set:

```text
project_id = destination project
revision_id = destination revision
lifecycle_status = ACTIVE
inherited_from_node_id = source node id
new audit timestamps/actors
removed_at = NULL
removed_by = NULL
```

For an equipment terminal:

```text
destination.equipment_id
    = destination clone of source.equipment_id
```

Never point a destination terminal at source-revision Equipment.

For an electrical node:

```text
equipment_id = NULL
terminal_key = NULL
```

---

# 44. Active terminal referencing non-cloned equipment

This indicates an inconsistent source snapshot.

If an ACTIVE source `EQUIPMENT_TERMINAL` references Equipment that was not cloned—for example because the Equipment is REMOVED—do **not** silently omit the terminal.

Fail model inheritance atomically with an explicit topology/model inheritance conflict.

A healthy canonical model should not contain an ACTIVE terminal on REMOVED equipment.

---

# 45. Connection clone behavior

Clone only ACTIVE source connections.

For each:

Preserve:

```text
connection_kind
direction
phase_configuration
nominal_voltage
nominal_voltage_unit
origin
verification_state
confidence
```

Set:

```text
new id
destination project/revision
from_node_id = remapped destination node
to_node_id = remapped destination node
lifecycle_status = ACTIVE
inherited_from_connection_id = source.id
new audit fields
removed_at = NULL
removed_by = NULL
```

No endpoint may remain pointed at a source revision.

---

# 46. Active connection referencing non-cloned node

This is also an inconsistent source snapshot.

If an ACTIVE source connection references a node that is not cloned:

- do not silently drop the connection;
- do not cross-link to the source revision;
- fail revision inheritance atomically.

Meaningful active topology must never disappear silently during carry-forward.

---

# 47. Removed topology during inheritance

Do not clone:

```text
REMOVED nodes
REMOVED connections
```

This matches removed Equipment behavior.

A REMOVED node/connection remains part of the historical source revision only.

---

# 48. Topology inheritance provenance

DB ownership constraints should prevent cross-project references.

Application clone logic must prove:

```text
destination.inherited_from_node_id
    -> source node in target.based_on_revision_id

destination.inherited_from_connection_id
    -> source connection in target.based_on_revision_id
```

Tests must explicitly verify the immediate-base relationship.

Do not source topology from arbitrary same-project historical revisions.

---

# 49. Independent snapshot semantics

After carry-forward:

- editing destination node label/key does not change source;
- editing destination connection does not change source;
- removing/restoring destination topology does not change source;
- source and destination node/connection IDs differ;
- only explicit `inherited_from_*` pointers refer back;
- terminal Equipment references use destination Equipment IDs.

This must be tested.

---

# 50. No automatic topology generation

Do not auto-create:

- a default terminal per Equipment;
- line/load terminals based on equipment type;
- bus nodes;
- cable endpoints;
- transformer winding terminals;
- source/load topology;
- connections based on tag/name/type.

Phase 5D is persistence/manual authoring only.

Automatic topology proposal belongs to Phase 8.

---

# 51. Topology consistency helper

Implement a pure/service-level consistency check sufficient to detect corrupted persisted topology when loading/mutating/cloning.

At minimum detect:

- node shape violates kind;
- terminal equipment ownership mismatch;
- terminal references removed/missing equipment when ACTIVE;
- duplicate terminal semantic state where applicable;
- connection endpoint ownership mismatch;
- self-loop;
- ACTIVE connection with REMOVED endpoint;
- noncanonical nominal voltage unit;
- invalid confidence;
- unknown enum state.

Do not create persistent validation findings.

Do not attempt Phase 10 engineering-rule validation.

This helper may complement DB constraints rather than duplicate every SQL rule.

---

# 52. Error model

Add clean domain/service errors following current conventions.

Examples may include:

```text
ModelNodeNotFound
ModelConnectionNotFound
InvalidModelNode
InvalidModelConnection
TopologyObjectRemoved
TopologyOwnershipError
```

Exact names may follow repository style.

Reuse:

```text
ModelInheritanceConflict
EquipmentNotFound
RevisionNotFound
RevisionReadOnly
ArchivedProject
CancelledProject
```

where semantically appropriate.

Map known integrity constraint names through `integrity_guard`.

Do not expose SQL statements/parameters/raw database errors.

---

# 53. Service transaction ownership

Ordinary topology mutation methods may own their commit/rollback similarly to `EngineeringModelService`.

Helpers called from:

```text
EngineeringModelService.remove_equipment()
EngineeringModelService.restore_equipment()
copy_active_engineering_model()
```

must support participation in the caller's existing transaction and MUST NOT perform an independent commit.

Avoid nested service calls that accidentally commit halfway through a larger lifecycle/inheritance operation.

Factor lifecycle/remap helpers accordingly.

---

# 54. Equipment lifecycle integration architecture

Avoid a circular service dependency.

Use a small internal topology lifecycle helper/module if needed, e.g. conceptually:

```text
soft_remove_equipment_topology(...)
restore_equipment_terminals(...)
soft_remove_incident_connections(...)
```

These helpers:

- take the existing Session;
- do not commit;
- assume caller holds writable revision lock when called from a mutation;
- update audit timestamps/actors consistently.

Do not move Equipment lifecycle ownership out of `EngineeringModelService`.

---

# 55. Revision clone return count

Keep the Phase 5C response meaning:

```text
inherited_model_equipment_count
```

continues to count inherited Equipment snapshots.

Do not silently redefine it to count nodes or connections.

Phase 5D does not need to add public:

```text
inherited_node_count
inherited_connection_count
```

unless an existing approved contract explicitly requires them.

Topology clone counts may be logged internally or included in the Phase 5D handoff/tests.

---

# 56. system_frequency / system_phase_count interaction

Do not change the accepted Phase 5C persistence/metadata behavior.

In particular:

```text
system_frequency
system_phase_count
```

remain revision-level metadata.

Do not copy them into topology rows.

Do not auto-create `phase_configuration` from `system_phase_count`.

Do not auto-create connection nominal voltage from equipment or revision metadata.

Explicit topology fields remain explicit canonical data.

---

# 57. Important phase-count clarification

The revision-level:

```text
system_phase_count
```

is a common/default model phase-count assumption.

An explicit equipment `phase_count` may legitimately override it for a specific equipment item.

Therefore Phase 5D MUST NOT treat:

```text
system_phase_count = 3
equipment.phase_count = 1
```

as inherently invalid topology.

Likewise, do not force all connection `phase_configuration` fields to match the revision default.

Future deterministic validation can apply context-specific rules.

Frequency disagreement is more likely to require later validation, but Phase 5D still does not implement that findings engine.

---

# 58. Testing philosophy

Phase 5D requires strong tests, but do **not** create a combinatorial test explosion.

Test architectural invariants at the layer that owns them.

Duplicate an invariant at another layer only when the second test protects against a materially different failure mode.

Prioritize:

```text
ownership integrity
node/connection structural integrity
equipment-topology lifecycle cascades
conservative restore behavior
revision clone/remapping
inheritance provenance
transaction rollback
snapshot independence
the new clone-vs-topology concurrency risk
```

Avoid exhaustively testing every:

```text
operation × project status × revision status × enum × invalid-value permutation
```

when shared Phase 5B/5C infrastructure already proves the underlying behavior.

Parameterization is encouraged where it improves clarity.

The goal is a focused topology suite, not test-count maximization.

---

# 59. Migration tests

Add focused integration coverage for migration 0009.

At minimum verify:

1. fresh upgrade through head;
2. upgrade from 0008 with existing projects/revisions/equipment/attributes;
3. no topology rows are synthesized;
4. ORM and migration columns/enum labels/major constraints align;
5. representative valid topology can be inserted;
6. downgrade removes Phase 5D tables/enums while preserving Phase 5A–5C data;
7. re-upgrade succeeds.

Do not write a separate migration assertion for every individual index/constraint if the ORM/schema-equivalence helper already verifies them collectively.

---

# 60. Persistence constraint tests

Use representative direct-PostgreSQL tests for the important structural invariants.

## Nodes

Must cover:

- valid equipment terminal;
- valid electrical node;
- node-kind shape enforcement;
- cross-project/revision Equipment reference rejection;
- duplicate terminal key on one Equipment rejected;
- same terminal key on different Equipment allowed;
- lifecycle/removal constraint;
- inherited-from self/ownership protection.

You do not need a separate test for every equivalent malformed column combination if one parameterized node-shape test proves the constraint comprehensively.

## Connections

Must cover:

- valid connection;
- endpoint ownership across project/revision;
- self-loop rejection;
- parallel edges allowed;
- lifecycle constraint;
- confidence bounds/finite behavior;
- nominal-voltage canonical value/unit constraint;
- inherited-from self/ownership protection.

Again, use parameterization instead of one test function per bad scalar.

---

# 61. Domain tests

Keep these small.

Assert the exact topology vocabulary:

```text
ModelNodeKind:
    EQUIPMENT_TERMINAL
    ELECTRICAL_NODE

ConnectionKind:
    ELECTRICAL
    GROUNDING
    OTHER

ConnectionDirection:
    UNDIRECTED
    NOMINAL_FROM_TO
```

Assert that stale `BUS` node-kind semantics are gone.

Add focused unit tests for any pure topology normalization helper, especially nominal-voltage normalization if Phase 5D introduces a topology-specific wrapper.

Do not duplicate the full engineering-model unit test suite.

---

# 62. Manual topology service tests

Test representative service behavior rather than every method against every lifecycle state.

## Nodes

Cover:

- create equipment terminal;
- create electrical node;
- duplicate/nonblank terminal-key behavior;
- cross-revision or removed Equipment rejection;
- update label / terminal key;
- node identity fields that are intentionally immutable;
- remove node;
- restore node;
- terminal restore requiring ACTIVE Equipment;
- list/read scoping and default ACTIVE behavior.

## Connections

Cover:

- create ordinary UNDIRECTED electrical connection;
- at least one non-default kind/direction;
- self-loop rejection;
- parallel connections;
- endpoint ownership/ACTIVE checks;
- representative nominal-voltage conversion, e.g. `600 V -> 0.6 kV`;
- update/rewire with endpoint validation;
- remove/restore;
- restore rejection with inactive endpoint;
- removed connection requiring restore before edit.

Do not test every enum value through every service method. The enum/domain tests already own closed-vocabulary coverage.

---

# 63. Shared mutability testing

Do **not** repeat the full project/revision lifecycle matrix for every topology mutation.

The shared `lock_writable_revision(...)` behavior was already thoroughly established in Phase 5B/5C.

Phase 5D should:

1. run one representative topology mutation through the full project/revision mutability matrix;
2. verify other topology mutation entry points use the same shared writable-revision guard/lock path;
3. keep existing Phase 5B/5C mutability regression tests passing.

This is sufficient unless Phase 5D introduces a genuinely different write path.

---

# 64. Lifecycle cascade tests — high priority

These are mandatory and should remain detailed.

Test Equipment removal:

```text
Equipment ACTIVE
terminal A ACTIVE
terminal B ACTIVE
incident connections ACTIVE
```

after removal:

```text
Equipment REMOVED
terminal A REMOVED
terminal B REMOVED
incident connections REMOVED
```

Unrelated:

```text
ELECTRICAL_NODE
other equipment terminals
unrelated connections
```

must remain unchanged.

Then Equipment restore:

```text
Equipment ACTIVE
its terminal nodes ACTIVE
old connections remain REMOVED
```

Also test manual node removal:

```text
node REMOVED
incident ACTIVE connections -> REMOVED
```

and node restore:

```text
node ACTIVE
connections remain REMOVED
```

These behaviors are intentionally asymmetric and must not be reduced to superficial happy-path tests.

---

# 65. Topology inheritance tests — highest priority

Create one representative source topology rich enough to exercise the graph:

```text
multiple Equipment items
equipment terminals
an ELECTRICAL_NODE
a CABLE represented as Equipment with terminals
multiple connections
parallel edge or grounding edge
nominal voltage
phase_configuration
at least one removed topology object
```

Then carry the model forward.

Verify:

- only ACTIVE nodes/connections clone;
- removed topology is excluded;
- cloned node IDs differ;
- cloned connection IDs differ;
- terminal Equipment references remap to destination Equipment;
- electrical nodes keep null Equipment;
- `inherited_from_node_id` points to the immediate-base source node;
- connection endpoints point only to destination nodes;
- `inherited_from_connection_id` points to the immediate-base source connection;
- connection metadata/provenance/confidence is preserved;
- no destination endpoint points to the source revision;
- parallel edges remain legal;
- source and destination topology are independent snapshots.

Prefer one comprehensive graph-clone test plus a small number of focused edge-case tests over many tiny clone tests.

---

# 66. Inconsistent-source and rollback tests — high priority

Test the important corruption/failure classes without enumerating every theoretical corruption.

At minimum cover:

1. ACTIVE terminal whose Equipment cannot be cloned;
2. ACTIVE connection whose endpoint node cannot be cloned;
3. clone invoked with a source that is not the target's selected base;
4. injected failure during topology clone after some target topology has been flushed.

Expected result:

```text
explicit inheritance/topology error
+
entire revision creation transaction rolls back
```

Confirm no partial:

```text
target revision
document inheritance
equipment/attributes
nodes
connections
activation change
```

remains committed.

You do not need one rollback test after every individual insertion statement if the transaction boundary is already demonstrated at strategically different stages.

---

# 67. Snapshot independence tests

Keep one focused topology independence test.

After clone, prove representative mutations on destination:

```text
node label/terminal key
connection metadata/lifecycle
```

do not modify the source, and representative source mutations do not modify the destination.

You do not need a separate independence test for every mutable field.

---

# 68. Concurrency tests

Keep concurrency coverage narrow and risk-driven.

Mandatory:

1. verify topology mutations follow the existing project → revision lock order;
2. add one real PostgreSQL test for **revision model clone vs concurrent topology mutation on the base revision**;
3. verify the clone sees a complete before/after snapshot, never a partial topology mutation;
4. keep existing Phase 5B/5C archive/cancel/supersede concurrency regression tests passing.

Do **not** add separate real-concurrency tests for:

```text
archive vs create_node
archive vs update_node
archive vs create_connection
cancel vs each operation
supersede vs each operation
```

unless implementation introduces a different lock path.

The shared locking infrastructure already owns those semantics.

---

# 68A. API scope test

A small scope guard is acceptable but optional.

If inexpensive, assert OpenAPI still contains no Phase 5E topology CRUD endpoints such as:

```text
/api/projects/{project_id}/revisions/{revision_id}/nodes
/api/projects/{project_id}/revisions/{revision_id}/connections
```

Do not build substantial tests solely to prove that unimplemented APIs remain absent.

# 69. Frontend scope

Do not add:

```text
Engineering Model workspace
topology form UI
connection editor
node editor
React Flow
one-line view
```

in Phase 5D.

The small revision-create carry-forward-model UI introduced in 5C remains unchanged.

No frontend change should be necessary unless package/API typing is incidentally affected; if so, keep it minimal and explain it.

---

# 70. Regression requirements

Run targeted and full regression.

At minimum:

```text
Phase 5A registry/unit/requirements regression
Phase 5B persistence/service/constraint/concurrency regression
Phase 5C inheritance/metadata/effective-value regression
focused Phase 5D topology domain/persistence/service/lifecycle/inheritance tests
Phase 5D migration tests
project/revision/document regression
full Python suite
live integration suite against disposable PostgreSQL/MinIO
ruff check
ruff format --check for changed Python
pip check
git diff --check
```

Do not add redundant Phase 5D tests merely to increase coverage counts. Prefer clear invariant coverage and reuse of already-proven shared guards.

If no frontend files changed, frontend checks may be omitted with an explicit note.

If frontend files change, run:

```text
npm run lint
npm test
npx tsc --noEmit
npm run build
```

Do not use the development database for destructive migration/integration tests.

---

# 71. Documentation updates

Update current/future-facing documentation as needed:

```text
docs/TOPOLOGY.md
docs/ENGINEERING_MODEL.md
docs/ARCHITECTURE.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
```

Create:

```text
docs/PHASE5D_HANDOFF.md
```

Do not rewrite historical 5A/5B/5C handoffs.

Update roadmap/status so:

```text
5A implemented
5B implemented
5C implemented
5D implemented
5E next
```

only after implementation/tests are actually complete.

---

# 72. PHASE5D_HANDOFF requirements

The handoff must record:

1. baseline branch/commit;
2. migration revision;
3. topology package enum changes, including removal of stale BUS node semantics;
4. persistence tables and fields;
5. DB constraints/indexes;
6. manual topology service behavior;
7. nominal-voltage normalization;
8. node/connection soft lifecycle;
9. equipment removal/restore cascade semantics;
10. model clone/remap algorithm;
11. inherited_from node/connection semantics;
12. removed topology inheritance behavior;
13. transaction/locking behavior;
14. tests added;
15. exact test/lint commands and results;
16. deviations/technical debt;
17. confirmation no public Phase 5E API was introduced;
18. confirmation no Phase 5F+ frontend/extraction/visualization work was introduced.

---

# 73. Scope discipline

Do not use Phase 5D as an opportunity to add:

```text
parent_equipment_id
equipment containment
terminal type registry
winding/port models
phase conductor graph model
bus-section model
source/load direction solver
graph algorithms
automatic upstream/downstream classification
protection relations
CT-to-relay relations
relay-to-breaker relations
operating scenarios
Evidence
AI extraction
visualization coordinates
x/y node layout
diagram geometry
```

Those require later design/phases.

Phase 5D is the canonical connectivity persistence foundation, not the complete electrical-study graph engine.

---

# 74. Completion criteria

Phase 5D is complete only when all of the following are true:

- topology domain enums match the approved vocabulary exactly;
- stale `NodeKind.BUS` semantics are gone;
- `model_nodes` persists terminal/electrical nodes;
- `model_connections` persists relational edges;
- no direct equipment-to-equipment connection model exists;
- cable remains Equipment;
- terminal ownership is constrained to same project/revision Equipment;
- connection endpoints are constrained to same project/revision nodes;
- self-loops are rejected;
- parallel edges are allowed;
- terminal keys are unique per Equipment;
- nominal voltage is Decimal/NUMERIC canonical kV;
- topology manual creation defaults to MANUAL + ENGINEER_REVIEWED;
- no ordinary manual path forges AI/verified provenance;
- nodes/connections use soft lifecycle;
- node removal soft-removes incident connections;
- node restore does not restore connections;
- Equipment removal soft-removes terminals and incident connections atomically;
- Equipment restore restores terminals but not old connections;
- `carry_forward_model=true` now clones active topology after Equipment/Attributes;
- terminal Equipment references remap to destination Equipment;
- connection endpoints remap to destination nodes;
- `inherited_from_node_id` and `inherited_from_connection_id` point to actual immediate-base objects;
- removed topology is excluded from carry-forward;
- inconsistent meaningful active topology causes atomic inheritance failure rather than silent data loss;
- source and descendant topology snapshots are independent;
- no public Phase 5E topology CRUD API is added;
- no frontend/AI/evidence/visualization scope leaks in;
- all relevant regression/integration tests pass.

---

# 75. End-of-task report

At completion, do **not** proceed to Phase 5E.

Report:

1. branch/base used;
2. files changed;
3. migration revision;
4. final topology enum vocabulary;
5. ModelNode schema/invariants;
6. ModelConnection schema/invariants;
7. service methods implemented;
8. lifecycle/cascade behavior;
9. voltage normalization behavior;
10. topology clone/remap behavior;
11. inheritance provenance behavior;
12. concurrency behavior;
13. tests added;
14. exact commands/results;
15. technical debt/deviations;
16. confirmation that no Phase 5E+ work leaked into scope.

If every acceptance criterion passes, finish exactly with:

```text
Phase 5D implementation is complete and ready for review.
```

Do not begin Phase 5E until instructed.
