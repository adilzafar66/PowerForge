# PowerForge Phase 5E — Revision-Scoped Engineering Model APIs

You are implementing **Phase 5E only** of PowerForge.

Phase 5A, 5B, 5C, and 5D are complete and accepted.

Phase 5E exposes the already-implemented canonical engineering model through a clean, revision-scoped FastAPI application contract.

The persistence/domain architecture is already established. Phase 5E is an **application/API phase**, not another persistence redesign.

The primary deliverables are:

- revision-scoped Equipment APIs;
- revision-scoped EquipmentAttribute APIs;
- revision-scoped ModelNode APIs;
- revision-scoped ModelConnection APIs;
- request/response schemas;
- search/filter support needed by the Phase 5F workspace;
- clean API validation/error translation;
- strict prevention of client-forged provenance/verification state;
- focused API tests;
- OpenAPI/documentation updates.

Do **not** proceed to Phase 5F or later.

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
docs/PHASE5D_HANDOFF.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
```

Inspect the accepted implementation in:

```text
packages/engineering-model/
packages/topology/
packages/persistence/

services/api/src/powerforge_api/main.py
services/api/src/powerforge_api/routers/
services/api/src/powerforge_api/schemas/
services/api/src/powerforge_api/services/engineering_model_service.py
services/api/src/powerforge_api/services/topology_service.py
services/api/src/powerforge_api/services/topology_support.py
services/api/src/powerforge_api/services/revision_writes.py
services/api/src/powerforge_api/exceptions.py
services/api/src/powerforge_api/routers/errors.py
services/api/src/powerforge_api/db_errors.py

tests/
```

Source-of-truth order:

1. this Phase 5E prompt for Phase 5E scope and clarifications;
2. `docs/specs/phase-5-engineering-model.md`;
3. ADR-007;
4. accepted Phase 5A–5D implementation/handoffs;
5. current repository conventions.

If repository reality materially conflicts with a required invariant, report the conflict rather than silently changing canonical model semantics.

---

# 2. Baseline

Start from the accepted Phase 5D implementation.

At the time this prompt was prepared:

```text
branch:
codex/phase-5d-topology-persistence

accepted head:
007427842f75051d8c5979369f89882110aa423e
```

If Phase 5D has since been merged to `main`, use the updated `main`.

Confirm the baseline contains:

```text
0009_topology_persistence

EquipmentLineage
Equipment
EquipmentAttribute

ModelNode
ModelConnection

EngineeringModelService
TopologyService

system_frequency
system_phase_count

carry_forward_model

topology lifecycle cascades
topology revision inheritance/remapping

GET /api/engineering-model/registry
```

Do not start from Phase 5C or an earlier branch.

---

# 3. Phase 5E scope

Phase 5E MUST expose the canonical model already implemented in 5A–5D.

Required public API areas:

```text
Equipment
EquipmentAttribute
ModelNode
ModelConnection
```

The existing registry endpoint remains:

```text
GET /api/engineering-model/registry
```

Phase 5E MUST NOT implement:

```text
Engineering Model frontend/workspace
React Flow
graph visualization
one-line rendering
AI extraction
Evidence
ExtractionCandidate
entity resolution
reconciliation
persistent validation findings
engineer verification workflow
ProtectionFunction/settings persistence
operating/study scenarios
ETAP/SKM/EasyPower export
report generation
containment / parent_equipment_id
new canonical persistence tables
```

---

# 4. No Phase 5E database migration

Phase 5E should require **no database migration**.

The required persistence already exists through migration:

```text
0009_topology_persistence
```

Do not add `0010` merely for API convenience.

If implementation appears to require a database schema change, stop and explain why before changing persistence.

Phase 5E should primarily change:

```text
routers
schemas
service read/query helpers where needed
error translation
tests
documentation
```

---

# 5. Preserve existing canonical semantics

Do not redesign the accepted Phase 5 model.

Preserve:

```text
ProjectRevision as snapshot root
EquipmentLineage stable physical identity
revision-scoped Equipment
relational typed EquipmentAttribute
registry-controlled keys/types
canonical units
soft lifecycle
manual = MANUAL + ENGINEER_REVIEWED
topology via ModelNode/ModelConnection
connections between nodes, never equipment
CABLE remains Equipment
revision inheritance semantics
system_frequency/system_phase_count semantics
```

Phase 5E is an interface over those rules.

---

# 6. Router organization

Keep the existing registry route clean:

```text
services/api/src/powerforge_api/routers/engineering_model.py
```

currently owns:

```text
GET /api/engineering-model/registry
```

Do not cram all revision CRUD routes into `routers/projects.py`.

Prefer a dedicated router module following repository conventions, conceptually:

```text
routers/model.py
```

or:

```text
routers/engineering_model_crud.py
```

with a revision-scoped base path:

```text
/api/projects/{project_id}/revisions/{revision_id}
```

Include it in `main.py`.

A small number of routers split by equipment/topology is also acceptable if clearer, but avoid unnecessary router proliferation.

---

# 7. Schema organization

Add dedicated request/response schemas for canonical model CRUD.

Prefer a module such as:

```text
schemas/model.py
```

or a similarly clear name.

Do not overload `schemas/projects.py`.

The existing read-only registry schemas may remain in:

```text
schemas/engineering_model.py
```

Do not duplicate the canonical registry definitions in Pydantic request schemas or frontend TypeScript.

---

# 8. Public Equipment routes

Implement:

```text
GET    /api/projects/{project_id}/revisions/{revision_id}/equipment
POST   /api/projects/{project_id}/revisions/{revision_id}/equipment

GET    /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}
PATCH  /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}

POST   /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/remove
POST   /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/restore
```

No DELETE route.

---

# 9. Equipment create request

The public create body should contain only ordinary manual-authoring fields:

```json
{
  "equipment_type": "BUS",
  "tag": "SWGR-1",
  "name": "Main Switchgear",
  "description": "..."
}
```

Required:

```text
equipment_type
```

Optional:

```text
tag
name
description
```

Use:

```text
extra = forbid
```

The request body MUST NOT accept:

```text
project_id
revision_id
lineage_id
lifecycle_status
origin
verification_state
confidence
inherited_from_equipment_id
created_at
created_by
updated_at
updated_by
removed_at
removed_by
```

Project/revision identity always comes from the URL path.

---

# 10. Equipment update request

PATCH may edit:

```text
tag
name
description
equipment_type
```

Omitted means unchanged.

Explicit null may clear:

```text
tag
name
description
```

Explicit null MUST NOT be accepted as an equipment type.

Unknown/invalid equipment types are API validation errors.

Do not allow PATCH to directly change:

```text
lifecycle_status
origin
verification_state
lineage_id
inheritance pointers
audit fields
```

Lifecycle uses the explicit remove/restore routes.

---

# 11. Equipment response

Expose enough canonical state for Phase 5F and future consumers.

At minimum return:

```text
id
project_id
revision_id
lineage_id

equipment_type
tag
name
description

lifecycle_status
origin
verification_state

inherited_from_equipment_id

created_at
created_by
updated_at
updated_by
removed_at
removed_by
```

Do not hide lineage/inheritance provenance from the canonical model API.

Do not expose SQLAlchemy internals.

Equipment attributes are available through the dedicated attribute route; do not create an enormous nested list response unless a clear repository convention already supports it.

---

# 12. Equipment list behavior

Default:

```text
lifecycle_status = ACTIVE
```

Support:

```text
search
equipment_type
lifecycle_status
```

Search should be case-insensitive and should match practical human-identifying fields such as:

```text
tag
name
description
```

Trim a blank search string to no search.

Lifecycle filtering should support:

```text
ACTIVE
REMOVED
ALL
```

A small API enum such as `ModelLifecycleFilter` is appropriate.

Do not change `LifecycleStatus` to add `ALL`; `ALL` is a query concept, not canonical persisted state.

Sort deterministically, preferably by:

```text
created_at
id
```

or another stable repository-consistent order.

---

# 13. Pagination decision

The approved Phase 5 specification says the equipment list should use repository-standard pagination.

The current repository does **not** yet have an established shared pagination abstraction.

Therefore, in Phase 5E:

- do not invent a large repository-wide pagination framework;
- do not refactor all existing list APIs;
- do not add pagination merely for architectural aesthetics.

For the current basic Phase 5F workspace, an `items` list with search/filter support is acceptable.

If the repository has gained a clear pagination convention by implementation time, reuse it.

Otherwise record bounded/paginated model listing as a future performance concern rather than creating unrelated infrastructure.

---

# 14. Equipment list service work

`EngineeringModelService.list_equipment(...)` currently supports lifecycle and equipment type filtering.

Extend its read/query behavior only as needed for:

```text
search
stable ordering
API lifecycle filter translation
```

Do not weaken:

```text
project/revision ownership
registry validation
revision mutability on writes
```

Do not load all EquipmentAttribute rows merely to return the equipment summary list.

Avoid obvious N+1 queries.

---

# 15. Equipment attribute routes

Implement:

```text
GET /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/attributes

PUT /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/attributes/{attribute_key}
```

PUT is intentional because the route represents the complete manual canonical state for one known attribute.

Do not add arbitrary attribute creation/deletion routes.

Every canonical attribute key comes from registry-v1.

---

# 16. Attribute update body

Representative body:

```json
{
  "information_state": "PRESENT",
  "value": 600,
  "unit": "V"
}
```

State-only body:

```json
{
  "information_state": "UNKNOWN"
}
```

Supported ordinary manual states remain:

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
```

Do not expose ordinary manual writes for:

```text
NOT_EXTRACTED
CONFLICTING
```

unless the accepted underlying service already deliberately supports them. It currently does not.

For:

```text
information_state = PRESENT
```

the server validates the registry type and normalizes the value/unit.

For non-PRESENT manual states:

```text
canonical typed values are cleared
```

Do not duplicate all polymorphic registry validation in Pydantic.

It is acceptable for `value` to remain a generic JSON field and for the canonical domain/service layer to decide:

```text
NUMBER
INTEGER
TEXT
ENUM
BOOLEAN
```

semantics.

---

# 17. Attribute update request security

The request MUST NOT accept:

```text
attribute_key
value_type
canonical unit metadata
origin
verification_state
confidence
inherited_from_attribute_id
equipment_id
project_id
revision_id
audit fields
```

`attribute_key` comes from the path.

The request may accept only:

```text
information_state
value
unit
```

with `unit` interpreted as the input unit, not caller-selected canonical storage unit.

Use:

```text
extra = forbid
```

---

# 18. Attribute response

Return canonical persisted state.

At minimum:

```text
id
project_id
revision_id
equipment_id

attribute_key
value_type

numeric_value
integer_value
text_value
boolean_value

unit

information_state
verification_state
origin
confidence

inherited_from_attribute_id

created_at
created_by
updated_at
updated_by
```

Preserve Decimal precision.

Do not convert engineering Decimals to binary float merely for JSON convenience.

Use typed Pydantic Decimal fields and the repository's existing serialization behavior.

The existing Phase 5C API already serializes Decimal values losslessly.

---

# 19. Attribute ordering

`GET .../attributes` must return attributes in registry display order.

The accepted `EngineeringModelService.get_equipment_attributes(...)` already does this.

Do not sort alphabetically and lose registry-defined engineering order.

---

# 20. Requirement incompleteness

An incomplete equipment model is valid canonical state.

API writes MUST NOT fail simply because Required/Critical/conditional requirements remain unsatisfied.

For example, engineers must be able to save:

```text
MISSING
UNKNOWN
NOT_EXTRACTED
```

states.

Do not introduce Phase 10 validation findings.

Do not turn requirement evaluation into a write gate.

---

# 21. Public ModelNode routes

Implement:

```text
GET    /api/projects/{project_id}/revisions/{revision_id}/nodes
POST   /api/projects/{project_id}/revisions/{revision_id}/nodes

PATCH  /api/projects/{project_id}/revisions/{revision_id}/nodes/{node_id}

POST   /api/projects/{project_id}/revisions/{revision_id}/nodes/{node_id}/remove
POST   /api/projects/{project_id}/revisions/{revision_id}/nodes/{node_id}/restore
```

No DELETE route.

A dedicated single-node GET route is not required by the approved Phase 5 contract.

Do not add extra endpoints unless current application structure clearly requires them.

---

# 22. ModelNode create request

Use one public create schema with `kind`.

Equipment terminal example:

```json
{
  "kind": "EQUIPMENT_TERMINAL",
  "equipment_id": "uuid",
  "terminal_key": "LINE",
  "label": "Line"
}
```

Electrical-node example:

```json
{
  "kind": "ELECTRICAL_NODE",
  "label": "Junction 1"
}
```

Validate request shape before calling the service:

For `EQUIPMENT_TERMINAL`:

```text
equipment_id required
terminal_key required/nonblank
```

For `ELECTRICAL_NODE`:

```text
equipment_id absent/null
terminal_key absent/null
```

The router may dispatch to:

```text
TopologyService.create_terminal(...)
TopologyService.create_electrical_node(...)
```

Do not add a third node kind.

---

# 23. ModelNode update request

PATCH may edit only:

```text
terminal_key
label
```

`terminal_key` is only valid for `EQUIPMENT_TERMINAL`.

`label` may be explicitly null to clear it.

The request MUST NOT accept:

```text
kind
equipment_id
lifecycle_status
origin
verification_state
inheritance pointer
audit fields
```

The accepted 5D design intentionally treats node kind and terminal Equipment ownership as immutable.

---

# 24. ModelNode response

At minimum expose:

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

---

# 25. ModelNode list behavior

Default:

```text
ACTIVE
```

Support lifecycle filtering:

```text
ACTIVE
REMOVED
ALL
```

No graph visualization semantics.

No coordinates.

No automatic upstream/downstream calculation.

No document/evidence fields.

A simple `items` response is sufficient for Phase 5F.

---

# 26. Public ModelConnection routes

Implement:

```text
GET    /api/projects/{project_id}/revisions/{revision_id}/connections
POST   /api/projects/{project_id}/revisions/{revision_id}/connections

PATCH  /api/projects/{project_id}/revisions/{revision_id}/connections/{connection_id}

POST   /api/projects/{project_id}/revisions/{revision_id}/connections/{connection_id}/remove
POST   /api/projects/{project_id}/revisions/{revision_id}/connections/{connection_id}/restore
```

No DELETE route.

A dedicated single-connection GET route is not required by the approved Phase 5 contract.

---

# 27. ModelConnection create request

Example:

```json
{
  "from_node_id": "uuid",
  "to_node_id": "uuid",
  "connection_kind": "ELECTRICAL",
  "direction": "UNDIRECTED",
  "phase_configuration": "ABC",
  "nominal_voltage": 600,
  "nominal_voltage_unit": "V"
}
```

Required:

```text
from_node_id
to_node_id
```

Defaults:

```text
connection_kind = ELECTRICAL
direction = UNDIRECTED
```

Optional:

```text
phase_configuration
nominal_voltage
nominal_voltage_unit
```

The request body MUST NOT accept:

```text
lifecycle_status
origin
verification_state
confidence
inherited_from_connection_id
project_id
revision_id
audit fields
```

Manual Phase 5E creation remains:

```text
MANUAL
ENGINEER_REVIEWED
confidence = null
```

---

# 28. Connection voltage request semantics

For the public API use:

```text
nominal_voltage
nominal_voltage_unit
```

The request unit is an **input unit**.

Supported compatible voltage units come from the existing unit system.

The service normalizes to:

```text
nominal_voltage_unit = "kV"
```

in persistence/response.

Examples:

```text
600 V
-> 0.6 kV

13.8 kV
-> 13.8 kV
```

Do not accept:

```text
unit without voltage
zero/negative voltage
boolean voltage
non-finite voltage
non-voltage unit
```

Do not duplicate voltage conversion logic in the router.

Call the accepted `TopologyService`.

---

# 29. ModelConnection update request

PATCH may edit:

```text
from_node_id
to_node_id
connection_kind
direction
phase_configuration
nominal_voltage
nominal_voltage_unit
```

Omitted means unchanged.

Explicit null may clear:

```text
phase_configuration
nominal_voltage
```

Clearing nominal voltage must clear the canonical unit as well.

The request must reject explicit null for nonnullable endpoint/kind/direction fields when those fields are supplied.

If `nominal_voltage_unit` is supplied without `nominal_voltage`, preserve the existing 5D rule:

```text
reject as invalid topology input
```

unless the caller is also explicitly clearing the voltage in the same request.

Do not silently reverse endpoints when direction changes.

---

# 30. ModelConnection response

At minimum expose:

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

Preserve Decimal precision for:

```text
nominal_voltage
confidence
```

---

# 31. ModelConnection list behavior

Default:

```text
ACTIVE
```

Support lifecycle filter:

```text
ACTIVE
REMOVED
ALL
```

Return deterministic order.

Do not deduplicate parallel connections.

Parallel edges are valid canonical topology.

---

# 32. Path ownership is authoritative

For every nested endpoint:

```text
project_id
revision_id
```

come from the path.

Never accept or trust them from request bodies.

For:

```text
equipment_id
node_id
connection_id
```

the service must verify that the object belongs to the path project/revision.

A UUID that exists in another revision must not be mutated through the current revision's endpoint.

---

# 33. Cross-revision topology references

When a request uses:

```text
equipment_id
from_node_id
to_node_id
```

from another revision/project:

- reject it;
- do not cross-link revisions;
- do not leak unnecessary information about unrelated objects.

Using a scoped `404` for an object not present in the path revision is acceptable and consistent with the existing services.

The database composite FKs remain the final structural defense.

---

# 34. Read/write revision lifecycle

Reads remain available for historical/superseded revisions.

Mutations use the accepted service guards.

Writable:

```text
Project ACTIVE / PAUSED
Revision DRAFT / ACTIVE
```

Read-only:

```text
Project ARCHIVED
Project CANCELLED
Revision SUPERSEDED
```

Do not reimplement mutability logic in routers.

Call the accepted services, which use:

```text
lock_writable_revision(...)
```

---

# 35. Equipment lifecycle through API

Remove:

```text
POST .../equipment/{equipment_id}/remove
```

must retain the accepted 5D atomic cascade:

```text
Equipment -> REMOVED
its terminal nodes -> REMOVED
incident active connections -> REMOVED
```

Restore:

```text
POST .../equipment/{equipment_id}/restore
```

must preserve:

```text
Equipment -> ACTIVE
its terminal nodes -> ACTIVE
old connections remain REMOVED
```

The API must not add a "restore everything" shortcut.

---

# 36. Node lifecycle through API

Remove node:

```text
node -> REMOVED
active incident connections -> REMOVED
```

Restore node:

```text
node -> ACTIVE
old connections remain REMOVED
```

For terminal nodes:

```text
parent Equipment must be ACTIVE
```

Do not change these 5D semantics in the router.

---

# 37. Connection restore through API

Restoring a connection requires:

```text
both endpoint nodes ACTIVE
distinct endpoints
valid revision ownership
active parent Equipment for active terminal endpoints
```

The accepted service already enforces this.

Do not bypass it with direct ORM mutations.

---

# 38. No client-forged provenance

This is a critical Phase 5E API invariant.

Ordinary public request bodies MUST NOT let clients directly set:

```text
origin
verification_state
confidence
inherited_from_*
created_by
updated_by
removed_by
created_at
updated_at
removed_at
lineage_id
```

Use `extra="forbid"` on manual write schemas.

A user must not be able to POST:

```json
{
  "origin": "AI_EXTRACTION",
  "verification_state": "ENGINEER_VERIFIED",
  "confidence": 0.99
}
```

through ordinary Phase 5E CRUD.

Such requests should be rejected at the request-schema boundary.

---

# 39. Actor IDs

Authentication/trustworthy user identity is not implemented through Phase 5E.

Do not accept arbitrary client-supplied actor UUIDs.

For now HTTP CRUD may call the existing services with:

```text
actor_id = None
```

unless the repository has gained a trustworthy authenticated actor mechanism by implementation time.

Do not invent a fake user identity system in Phase 5E.

---

# 40. Domain validation errors at the HTTP boundary

Before Phase 5E, many engineering model services were internal, so pure domain exceptions could safely propagate to tests/callers.

Once public HTTP endpoints exist, malformed canonical input must produce clean client errors.

Examples include:

```text
unknown equipment type
unknown attribute key
invalid ENUM value
invalid attribute type
unknown unit
incompatible unit
invalid numeric input
integer-required violation
invalid topology kind/direction
invalid voltage
```

These must not become unhandled 500 errors.

---

# 41. Engineering domain error translation

The pure domain package should remain independent of HTTP.

Do not add FastAPI exceptions to:

```text
packages/engineering-model
packages/topology
```

At the API/application boundary, translate relevant `EngineeringModelError` subclasses into a stable project/API error, conceptually:

```text
InvalidEngineeringModelInput
code = "invalid_engineering_model_input"
HTTP 422
```

Exact naming may follow repository style.

Preserve the useful domain message without exposing SQL/internal stack details.

Do not broadly catch arbitrary `Exception` and relabel server bugs as validation errors.

---

# 42. Existing API error mappings

Extend `routers/errors.py` deliberately.

Recommended semantics:

```text
404
    EquipmentNotFound
    EquipmentAttributeNotFound
    ModelNodeNotFound
    ModelConnectionNotFound

409
    EquipmentRemoved
    TopologyObjectRemoved
    EquipmentTypeChangeConflict
    existing project/revision read-only errors

422
    InvalidEquipmentAttributeState
    InvalidTopology
    invalid engineering-model input/domain validation
    existing model-inheritance/input validation errors
```

`UnexpectedIntegrityError` remains:

```text
500
```

Do not expose raw PostgreSQL error messages.

If a persisted-consistency exception clearly represents server-side corruption rather than bad client input, do not mislabel it as a successful/client-controlled condition. Follow the existing error architecture conservatively and document any ambiguity.

---

# 43. Pydantic validation errors

Normal FastAPI/Pydantic body validation may continue to use FastAPI's standard HTTP 422 structure.

Do not replace the application's global validation machinery merely to make every 422 body identical.

Domain/application errors should continue using the existing:

```json
{
  "detail": {
    "detail": "...",
    "code": "..."
  }
}
```

style produced by `http_for(...)`.

---

# 44. Extra fields

All Phase 5E mutation schemas must use:

```text
extra = forbid
```

This is particularly important because future AI/extraction and review phases will have trusted metadata fields that must not become writable simply because a client knows their names.

Test representative forged fields.

Do not maintain a giant test for every forbidden metadata field.

---

# 45. Omitted versus explicit null

Preserve PATCH semantics.

For editable nullable text fields:

```text
omitted -> unchanged
null    -> clear
```

Examples:

```text
Equipment.tag
Equipment.name
Equipment.description
ModelNode.label
ModelConnection.phase_configuration
```

For fields that cannot be null:

```text
equipment_type
from_node_id
to_node_id
connection_kind
direction
terminal_key when explicitly editing a terminal
```

explicit null must be rejected.

Use `model_fields_set` or equivalent rather than conflating omitted and explicit null.

---

# 46. Registry remains the form metadata source

Do not replicate:

```text
equipment types
attribute display names
value types
enum options
required/critical flags
canonical units
supported input units
requirements
```

inside new CRUD schemas.

The existing:

```text
GET /api/engineering-model/registry
```

remains the metadata contract Phase 5F will use to generate forms.

Phase 5E CRUD APIs carry values/state, not a second registry.

---

# 47. No requirement/completeness persistence

Do not create:

```text
ValidationFinding
CompletenessFinding
StudyReadiness row
```

or similar.

If existing pure requirement evaluators are used in a response or test, they must remain informational.

No new requirement endpoint is required for Phase 5E.

---

# 48. No combined giant engineering-model endpoint

Do not add a large endpoint such as:

```text
GET /revision/{id}/entire-model
```

that eagerly nests:

```text
all equipment
all attributes
all nodes
all connections
```

unless an approved existing spec requires it. It currently does not.

Use the focused resource APIs.

This avoids large payloads and keeps Phase 5F data loading controllable.

---

# 49. Topology list performance

Phase 5D currently uses full revision consistency validation during some topology reads.

Do not redesign topology persistence or validation in Phase 5E solely for theoretical scale.

However:

- avoid adding additional redundant full-model scans in the router;
- do not call `list_nodes` multiple times for one request;
- do not call `list_connections` multiple times for one request;
- avoid obvious N+1 Equipment lookups.

Carry the 5D bulk-validation scalability note forward to 5G unless real API profiling shows a blocker now.

Correctness remains more important than premature optimization.

---

# 50. Response construction

Prefer Pydantic `from_attributes=True` response models for direct canonical rows where appropriate.

Do not return raw ORM rows without a response model.

Do not expose relationship objects accidentally.

Do not serialize internal SQLAlchemy state.

Use explicit response models for:

```text
Equipment
EquipmentAttribute
ModelNode
ModelConnection
list wrappers
```

---

# 51. List response shape

Use repository-consistent simple wrappers:

```json
{
  "items": [...]
}
```

for:

```text
equipment
attributes
nodes
connections
```

Do not introduce a repository-wide pagination envelope in this phase.

---

# 52. HTTP status codes

Use:

```text
GET successful       -> 200
PATCH/PUT successful -> 200
remove/restore       -> 200

POST create Equipment   -> 201
POST create ModelNode   -> 201
POST create Connection  -> 201
```

Do not return 204 when the client benefits from the resulting canonical object.

---

# 53. Equipment search/filter implementation

The API must support the Phase 5F equipment list without client-side scanning of unrelated revisions.

At minimum:

```text
?search=
?equipment_type=
?lifecycle_status=
```

`equipment_type` should use the canonical key vocabulary.

Invalid equipment type filters should produce a clean 422 rather than an empty list caused by silent string comparison.

`lifecycle_status=ALL` maps to no lifecycle predicate.

---

# 54. ModelNode/Connection lifecycle query filters

Use the API query concept:

```text
ACTIVE
REMOVED
ALL
```

for both nodes and connections.

Do not change the stored `LifecycleStatus` enum.

No additional topology filter is required in Phase 5E unless Phase 5F demonstrably needs it.

---

# 55. Service reuse

Routers MUST call:

```text
EngineeringModelService
TopologyService
```

for canonical mutations.

Do not duplicate business rules in routers.

Do not directly:

```text
session.add(...)
session.delete(...)
set lifecycle flags
normalize engineering values
clone rows
```

inside route functions.

If a read/query helper is missing, extend the service narrowly.

---

# 56. Service hardening allowed in Phase 5E

Because the services are becoming public application boundaries, Phase 5E MAY make narrowly scoped changes such as:

```text
equipment search support
clean domain-error translation support
stable list ordering
small helper methods needed for response/query behavior
```

Do not reopen accepted persistence/lifecycle architecture.

Any change to 5B–5D behavior must be justified by a public API correctness requirement and called out in the handoff.

---

# 57. Equipment type change API

PATCH may change equipment type because the accepted service supports safe type change.

Preserve the 5B rules:

- compatible canonical attributes remain;
- newly applicable attributes materialize;
- untouched incompatible placeholders may disappear;
- meaningful incompatible canonical data blocks the type change.

Expose a clean conflict/error to the client.

Do not silently discard meaningful attributes.

---

# 58. Duplicate equipment tags

Duplicate tags remain allowed.

API creation/update MUST NOT impose uniqueness on:

```text
tag
```

Do not convert duplicate tag behavior into a 409.

Future deterministic validation may flag duplicates.

---

# 59. Removed objects

Default lists show ACTIVE objects.

Explicit lifecycle filtering allows removed objects to be retrieved for restore workflows.

Do not hide removed objects so completely that Phase 5F cannot restore them.

Editing a removed Equipment/Node/Connection remains blocked until restore according to accepted service behavior.

---

# 60. Revision-wide model metadata

Phase 5E does not redesign:

```text
system_frequency
system_phase_count
```

They already live on revision create/get/update APIs from Phase 5C.

Do not duplicate them onto Equipment or topology endpoints.

Do not add another engineering-model metadata endpoint unless the current revision API is demonstrably insufficient. It currently is sufficient.

---

# 61. Phase-count semantics

Preserve the accepted interpretation:

```text
system_phase_count
    = common/default model phase count

explicit Equipment.phase_count
    = may override for that Equipment
```

Do not make API writes reject a single-phase Equipment merely because:

```text
system_phase_count = 3
```

Do not force `phase_configuration` from the revision-wide value.

Persistent deterministic consistency findings remain Phase 10 work.

---

# 62. Frequency semantics

Likewise:

```text
system_frequency
```

remains revision-level metadata.

Explicit equipment frequency remains separate.

Phase 5E exposes canonical values but does not create persistent mismatch findings or overwrite explicit values.

---

# 63. OpenAPI quality

Use:

```text
response_model
summary
Query descriptions
Field descriptions
```

where they materially improve the generated API contract.

The resulting OpenAPI must clearly show:

```text
Equipment routes
Attribute routes
Node routes
Connection routes
registry route
```

and must not show Phase 5F+ endpoints.

---

# 64. No frontend changes

Phase 5F owns the Engineering Model workspace.

Do not add:

```text
frontend API clients
React components
forms
workspace tabs
model tables
attribute editor UI
topology UI
```

in Phase 5E.

If a tiny shared generated-type change is absolutely required by an existing build contract, keep it minimal and explain it, but no Phase 5F UX implementation.

---

# 65. No worker changes

Canonical CRUD is synchronous API/database work.

Do not add:

```text
Celery tasks
worker queues
background extraction
AI jobs
```

for Phase 5E.

No document-processing worker should be involved.

---

# 66. No authentication invention

Authentication/authorization remains a later prerequisite for multi-user deployment/Phase 11 unless already added independently.

Do not invent:

```text
users table
fake current engineer
X-User-ID trust
client-provided actor ID
```

in Phase 5E.

Preserve nullable audit actor IDs.

---

# 67. API tests — testing philosophy

Use focused end-to-end API tests.

Do not re-test every Phase 5B/5D SQL constraint through HTTP.

Those layers already have dedicated tests.

Phase 5E tests should prove:

```text
routing
request validation
response contracts
path scoping
service integration
manual provenance protection
unit normalization through HTTP
lifecycle behavior through HTTP
error mapping
```

Avoid operation × status × invalid-field combinatorial explosion.

---

# 68. Equipment API tests

At minimum cover:

1. create Equipment returns 201 and canonical manual defaults;
2. duplicate tags are accepted;
3. get Equipment;
4. list default ACTIVE;
5. search;
6. equipment type filter;
7. lifecycle ACTIVE/REMOVED/ALL filtering;
8. PATCH omitted-vs-null text semantics;
9. safe equipment type change through API;
10. meaningful type-change conflict surfaces cleanly;
11. remove/restore;
12. cross-revision Equipment ID is not accessible through another revision route;
13. invalid equipment type returns 422;
14. forged provenance/audit fields are rejected.

Parameterize where useful.

---

# 69. Attribute API tests

At minimum cover:

1. attributes return in registry display order;
2. PRESENT numeric update with unit conversion, e.g. `600 V -> 0.6 kV`;
3. enum update;
4. boolean update;
5. integer validation;
6. UNKNOWN/MISSING/NOT_APPLICABLE clear values;
7. invalid attribute key -> clean 404/422 according to chosen contract;
8. incompatible/unknown unit -> 422;
9. invalid enum -> 422;
10. unsupported manual state -> 422;
11. request cannot forge `origin`, `verification_state`, `confidence`, or inheritance pointer;
12. incomplete equipment remains saveable.

Do not duplicate the full unit-system test matrix.

---

# 70. Node API tests

At minimum cover:

1. create Equipment terminal;
2. create Electrical node;
3. invalid create shape -> 422;
4. list default ACTIVE and ALL/REMOVED behavior;
5. update terminal key/label;
6. body cannot change kind/equipment ownership;
7. remove node cascades incident connection removal as observable through API;
8. restore node does not restore old connections;
9. removed terminal cannot be restored while parent Equipment is removed;
10. cross-revision Equipment reference is rejected;
11. forged provenance fields rejected.

Do not re-test every raw DB constraint.

---

# 71. Connection API tests

At minimum cover:

1. create ordinary electrical/undirected connection;
2. voltage conversion through HTTP;
3. phase configuration round trip;
4. parallel connection accepted;
5. self-loop rejected;
6. cross-revision endpoint rejected;
7. PATCH endpoint/metadata update;
8. explicit null clears phase configuration/voltage where allowed;
9. unit-without-value rejected;
10. remove/restore;
11. restore rejected while endpoint inactive;
12. default ACTIVE and ALL/REMOVED list behavior;
13. forged confidence/origin/verification fields rejected.

Again, rely on Phase 5D persistence tests for low-level FK/check coverage.

---

# 72. Representative mutability API test

Do not run the complete project/revision mutability matrix independently for every route.

Use one or a few representative mutation endpoints to prove HTTP propagation of:

```text
ARCHIVED project
CANCELLED project
SUPERSEDED revision
```

and keep the accepted service-level mutability tests passing.

Reads from superseded/historical revisions should remain available.

---

# 73. Error mapping tests

Test representative mappings:

```text
404:
    missing Equipment
    missing Node/Connection

409:
    removed object edit
    read-only revision
    meaningful type-change conflict

422:
    bad equipment type
    bad attribute unit/enum/state
    invalid topology/self-loop
```

Do not test every exception subclass if the mapping table itself is directly unit-tested.

---

# 74. OpenAPI scope tests

Assert the intended Phase 5E public routes exist.

Also assert no accidental Phase 5F+ routes/actions appear.

At minimum ensure OpenAPI includes:

```text
equipment
attributes
nodes
connections
registry
```

and does not expose request fields for canonical provenance/audit state.

---

# 75. Regression requirements

Run:

```text
Phase 5A registry/unit/requirements regression
Phase 5B equipment persistence/service/constraint regression
Phase 5C revision inheritance/metadata regression
Phase 5D topology persistence/lifecycle/inheritance regression
new focused Phase 5E API tests
project/revision/document API regression

full Python suite
live integration suite against disposable PostgreSQL/MinIO

ruff check .
ruff format --check <changed Python files>
pip check
git diff --check
```

No frontend checks are required if no frontend files are changed.

Do not run destructive integration/migration tests against the development database.

---

# 76. Test count discipline

Do not optimize for raw test count.

Phase 5E should add focused API coverage, not duplicate the hundreds of already-accepted persistence/service tests.

Prefer:

```text
one representative test with several assertions
parameterized validation cases
shared fixtures
direct mapping-table unit tests
```

over dozens of near-identical route tests.

The high-value Phase 5E risks are:

```text
wrong revision ownership
forged provenance
unclean domain -> HTTP errors
incorrect PATCH null semantics
lost unit normalization
lifecycle behavior being bypassed by routers
```

Focus there.

---

# 77. Documentation updates

Update relevant current-facing docs:

```text
docs/ENGINEERING_MODEL.md
docs/TOPOLOGY.md
docs/ARCHITECTURE.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
```

Create:

```text
docs/PHASE5E_HANDOFF.md
```

Do not rewrite historical handoffs.

After implementation is actually complete, status should become:

```text
5A implemented
5B implemented
5C implemented
5D implemented
5E implemented
5F next
5G pending
```

---

# 78. PHASE5E_HANDOFF requirements

The handoff must record:

1. baseline branch/commit;
2. routers/schemas added;
3. exact public endpoints;
4. request field allowlists;
5. response contracts;
6. equipment search/filter semantics;
7. lifecycle query-filter semantics;
8. Decimal serialization behavior;
9. omitted-vs-null PATCH semantics;
10. engineering-domain error translation;
11. final HTTP error mapping;
12. path project/revision ownership behavior;
13. manual provenance protection;
14. unit normalization behavior through API;
15. lifecycle cascade behavior observable through API;
16. any service read/query helpers changed;
17. tests added;
18. exact test/lint commands and results;
19. deviations/technical debt;
20. confirmation no migration was added;
21. confirmation no frontend/Phase 5F work was added;
22. confirmation no AI/evidence/validation/export work was added.

---

# 79. Scope boundary with Phase 5F

Phase 5E provides the API contract that Phase 5F will consume.

Do not implement the workspace.

Phase 5F will later own:

```text
Documents | Engineering Model workspace switch
equipment list UI
search/filter UI
Add Equipment
equipment detail sheet/modal
registry-generated attribute forms
information-state controls
unit selectors
terminals/nodes UI
connection forms/list
remove/restore UI
read-only presentation
```

Phase 5E should make those workflows possible through APIs, but stop there.

---

# 80. Scope boundary with later phases

Do not add:

```text
Evidence links
ExtractionCandidate APIs
AI extraction actions
AI-generated equipment
AI-generated topology
entity-resolution endpoints
conflict endpoints
validation-finding endpoints
engineer-verification actions
graph visualization data/layout
study configuration endpoints
protection setting endpoints
export endpoints
```

Those belong to later phases/design gates.

---

# 81. Acceptance criteria

Phase 5E is complete only when:

- the existing registry endpoint remains intact;
- Equipment CRUD/lifecycle routes are revision-scoped and public;
- EquipmentAttribute read/update routes are revision-scoped and public;
- ModelNode create/list/update/lifecycle routes are revision-scoped and public;
- ModelConnection create/list/update/lifecycle routes are revision-scoped and public;
- path project/revision ownership is enforced;
- cross-revision nested references cannot create invalid links;
- manual request schemas forbid provenance/audit/inheritance injection;
- invalid registry/domain input becomes clean 422 rather than unhandled 500;
- not-found canonical objects produce clean 404 responses;
- lifecycle/read-only conflicts produce clean 409 responses;
- equipment list supports search/type/lifecycle filters;
- removed objects are retrievable through explicit lifecycle filtering;
- attribute values remain registry validated and unit normalized;
- attribute list remains registry ordered;
- Decimal values remain lossless;
- incomplete canonical equipment remains saveable;
- topology routes preserve 5D lifecycle cascades;
- connection voltage input normalizes to canonical kV;
- parallel connections remain allowed;
- duplicate equipment tags remain allowed;
- no direct lifecycle/provenance mutation bypass exists;
- no database migration is added;
- no frontend workspace is implemented;
- no Phase 6+ functionality leaks in;
- full relevant regression/integration checks pass.

---

# 82. End-of-task report

At completion, do **not** proceed to Phase 5F.

Report:

1. branch/base used;
2. files changed;
3. endpoint table;
4. schema/request allowlists;
5. response structures;
6. equipment search/filter behavior;
7. lifecycle filtering;
8. PATCH omitted/null behavior;
9. domain-error translation;
10. HTTP status/error mapping;
11. ownership/cross-revision behavior;
12. provenance-forging prevention;
13. unit normalization behavior;
14. lifecycle integration;
15. tests added;
16. exact commands/results;
17. technical debt/deviations;
18. confirmation no DB migration was created;
19. confirmation no frontend/AI/evidence/visualization/export scope leaked in.

If every acceptance criterion passes, finish exactly with:

```text
Phase 5E implementation is complete and ready for review.
```

Do not begin Phase 5F until instructed.
