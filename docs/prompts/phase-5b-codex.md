# PowerForge Phase 5B — Core Engineering-Model Persistence

You are implementing **Phase 5B only** of PowerForge.

Phase 5A is complete and accepted. Phase 5B introduces the persistent core canonical engineering model for:

- `EquipmentLineage`
- revision-scoped `Equipment`
- relational typed `EquipmentAttribute`
- manual service-layer authoring/editing
- attribute materialization
- soft equipment lifecycle
- safe equipment-type changes
- database/ORM integrity and migration coverage

Do **not** proceed to Phase 5C or later.

In particular, Phase 5B does **not** implement revision model carry-forward, topology persistence, the Engineering Model frontend, or the complete public CRUD API surface.

---

# 1. Authoritative inputs

Before making changes, read and understand:

```text
docs/specs/phase-5-engineering-model.md
decisions/ADR-007-canonical-engineering-model-persistence.md
docs/specs/registry/PowerForge_registry-v1_reference.json
docs/ENGINEERING_MODEL.md
docs/PHASE5A_HANDOFF.md
docs/PROJECT_STATUS.md
```

Also inspect the accepted Phase 5A implementation in:

```text
packages/engineering-model/src/powerforge_engineering_model/
```

The Phase 5A registry/domain implementation is now a frozen dependency for Phase 5B. Do not redesign it.

Source-of-truth order:

1. `docs/specs/phase-5-engineering-model.md` — Phase 5 implementation behavior.
2. ADR-007 — persistence architecture and architectural decisions.
3. `PowerForge_registry-v1_reference.json` — exact canonical registry snapshot.
4. Accepted Phase 5A typed registry implementation — executable registry contract.
5. Existing repository conventions — implementation mechanics.

If repository reality materially conflicts with the specification, do not silently weaken an invariant. Report the conflict in the final handoff.

---

# 2. Baseline / branch requirement

Phase 5B must start from the **accepted Phase 5A state**.

At the time this prompt was written, the accepted Phase 5A work exists on:

```text
codex/phase-5a-registry
```

If that work has since been merged into `main`, use the updated `main`.

Do not start Phase 5B from an older `main` that does not contain the accepted Phase 5A registry, including:

```text
VerificationState.UNVERIFIED
```

Before editing, confirm that the baseline contains:

```text
20 canonical equipment types
296 canonical attributes
44 requirement reference rows
GET /api/engineering-model/registry
VerificationState.UNVERIFIED
```

---

# 3. Inspect the repository before editing

Before implementation, inspect the existing persistence architecture and conventions, especially:

```text
packages/document-processing/src/powerforge_document_processing/models.py
services/api/src/powerforge_api/db.py
services/api/src/powerforge_api/db_errors.py
services/api/src/powerforge_api/exceptions.py
services/api/src/powerforge_api/services/revision_documents.py
services/api/src/powerforge_api/services/revision_service.py
services/api/src/powerforge_api/services/project_service.py
database/env.py
database/migrations/
tests/
```

Understand:

- the current shared SQLAlchemy `Base`;
- `Project` / `ProjectRevision` ownership;
- composite same-project foreign-key patterns;
- existing PostgreSQL enum conventions;
- constraint naming;
- `integrity_guard`;
- project/revision lock ordering;
- revision mutability rules;
- migration testing conventions;
- service transaction conventions;
- nullable audit actor behavior before authentication exists.

Then implement Phase 5B using repository conventions without broad unrelated refactoring.

---

# 4. Phase 5B scope

Phase 5B MUST deliver:

```text
EquipmentLineage persistence
Equipment persistence
EquipmentAttribute persistence

Alembic migration(s)
SQLAlchemy mappings
database integrity constraints/indexes

ValueOrigin domain enum
LifecycleStatus domain enum
any small persistence-specific enum plumbing required

manual service-layer equipment CRUD
manual service-layer attribute updates
attribute materialization from registry-v1
soft remove / restore
safe equipment type changes

revision/project ownership enforcement
revision mutability enforcement
integrity-error mapping where appropriate

unit + typed-value normalization through the Phase 5A registry
focused persistence/service tests
migration tests
documentation/handoff updates
```

Phase 5B MUST NOT implement:

```text
carry_forward_model
engineering-model revision cloning
inherited model copy logic
ModelNode
ModelConnection
topology CRUD
equipment terminals
connection endpoints
Engineering Model frontend
React Flow
AI extraction
Evidence
ExtractionCandidate
reconciliation
persistent validation findings
engineer verification workflow
parent_equipment_id
protection-function/settings model
ETAP/SKM/EasyPower exporters
study calculations
```

The existing read-only registry endpoint from Phase 5A remains in place.

---

# 5. Persistence boundary

## 5.1 Do not put the new engineering ORM models in document-processing merely because Base currently lives there

ADR-007 and the Phase 5 specification explicitly reject making engineering persistence conceptually owned by document processing.

Currently, `powerforge_document_processing.models` owns the common SQLAlchemy Base plus project/revision/document ORM mappings.

For Phase 5B:

> Establish the **smallest neutral persistence boundary** necessary for engineering-model ORM classes to share the existing metadata/Base and Project/Revision mappings without making engineering persistence a document-processing responsibility.

Codex must inspect the repository and choose the least disruptive implementation.

Acceptable characteristics include:

- a neutral shared persistence module/package;
- preserving existing document-processing imports through re-exports if needed;
- avoiding duplicate declarative Bases/metadata;
- avoiding a broad migration of unrelated document code;
- keeping worker behavior unchanged.

Do not perform an aesthetic repository-wide persistence rewrite.

The final handoff must explain the persistence-boundary choice and any compatibility re-exports.

---

# 6. Domain vocabulary additions

Phase 5A already defines:

```text
EquipmentType
AttributeValueType
InformationState
VerificationState
```

Phase 5B needs the additional canonical state enums from the Phase 5 specification.

## 6.1 LifecycleStatus

```text
ACTIVE
REMOVED
```

## 6.2 ValueOrigin

```text
MANUAL
AI_EXTRACTION
INFERRED
IMPORTED
```

These belong in the pure engineering-model domain package if they are not already present.

Do not create a second competing origin/lifecycle vocabulary in the API package.

`VerificationState` must retain:

```text
UNVERIFIED
AI_EXTRACTED
SYSTEM_VALIDATED
ENGINEER_REVIEWED
ENGINEER_VERIFIED
```

Do not remove or rename any accepted Phase 5A state.

---

# 7. Database model: EquipmentLineage

Create a persistent `equipment_lineages` entity representing stable physical identity across project revisions.

Logical fields:

```text
id
project_id
created_at
created_by
```

Requirements:

- UUID primary key using repository-standard UUID generation.
- `project_id` is required.
- lineage belongs to exactly one project.
- `created_by` is nullable UUID with no users FK until authentication exists.
- lineage contains **no revision-varying engineering data**.
- add whatever composite uniqueness is needed to support database-enforced same-project foreign keys from Equipment.
- do not add tag/type/rating/name to lineage.
- do not add entity-resolution or matching fields.
- do not hard-delete lineages through Phase 5B service APIs.

A manually created equipment item creates a new lineage in the same transaction as the equipment snapshot.

---

# 8. Database model: Equipment

Create revision-scoped `equipment`.

Logical fields:

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

## 8.1 Equipment type

`equipment_type` MUST be stored as stable text validated by registry-v1.

Do **not** use a PostgreSQL equipment-type enum.

Reason: future registry equipment additions must not require altering a PostgreSQL enum.

The stored value must be one of the Phase 5A canonical equipment keys, for example:

```text
SYNCHRONOUS_GENERATOR
LV_BREAKER
BUS
CABLE
```

Do not introduce old Phase 0 aliases.

## 8.2 Required invariants

Enforce at the database level where practical:

- equipment belongs to the same project as its revision;
- equipment belongs to the same project as its lineage;
- unique `(revision_id, lineage_id)`;
- composite uniqueness needed for child same-project/revision FKs;
- `inherited_from_equipment_id` cannot equal `id`;
- lifecycle/removal timestamps remain internally consistent.

Recommended lifecycle invariant:

```text
lifecycle_status = REMOVED  <=>  removed_at IS NOT NULL
```

`removed_by` may remain null because authentication does not yet exist.

`tag`:

- nullable;
- indexed/searchable as appropriate;
- **not unique**.

Duplicate equipment tags are intentionally allowed in Phase 5.

## 8.3 Defaults for manual creation

Manual Phase 5B equipment creation uses:

```text
lifecycle_status = ACTIVE
origin = MANUAL
verification_state = ENGINEER_REVIEWED
inherited_from_equipment_id = NULL
```

No equipment-level confidence field is introduced.

---

# 9. Database model: EquipmentAttribute

Create relational `equipment_attributes`.

Logical fields:

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

## 9.1 Identity and ownership

Enforce:

```text
UNIQUE(equipment_id, attribute_key)
```

and database ownership such that an attribute cannot reference equipment from another project/revision.

Add composite uniqueness/FKs as necessary.

`inherited_from_attribute_id` is included now for Phase 5C compatibility but remains null for manually created Phase 5B rows.

It must not reference itself.

Do not implement clone/inheritance writes in Phase 5B.

---

# 10. Typed-value invariants

The Phase 5 specification requires structural enforcement.

Supported value types:

```text
NUMBER
INTEGER
TEXT
BOOLEAN
ENUM
```

Storage mapping:

```text
NUMBER  -> numeric_value
INTEGER -> integer_value
TEXT    -> text_value
ENUM    -> text_value
BOOLEAN -> boolean_value
```

## 10.1 PRESENT rows

When:

```text
information_state = PRESENT
```

exactly one compatible typed value slot must be populated.

Examples:

```text
NUMBER:
numeric_value IS NOT NULL
integer_value IS NULL
text_value IS NULL
boolean_value IS NULL
```

```text
ENUM:
text_value IS NOT NULL
all other typed slots NULL
```

## 10.2 Non-PRESENT rows

When:

```text
information_state != PRESENT
```

all typed value columns must be null.

Implement robust database check constraints for this behavior.

Do not rely solely on application code.

## 10.3 Confidence

If `confidence` is non-null:

```text
0 <= confidence <= 1
```

Use PostgreSQL `NUMERIC`, consistent with engineering numeric persistence and current repository patterns.

Manual Phase 5B writes always set:

```text
confidence = NULL
```

## 10.4 Unit

For every materialized attribute:

```text
unit = AttributeDefinition.canonical_unit
```

If the canonical attribute is unitless:

```text
unit = NULL
```

The row stores canonical unit metadata even when the information state is not `PRESENT`.

Do not store a caller's raw input unit after normalization.

## 10.5 Value type

Persist the registry-defined canonical `value_type`.

It must match the current equipment-type registry definition.

Do not allow callers to select or override `value_type`.

---

# 11. Initial attribute materialization

When Equipment is created, Phase 5B MUST create one `EquipmentAttribute` row for **every attribute defined for that equipment type in registry-v1**.

For each untouched materialized row:

```text
attribute_key       = registry key
value_type          = registry value type
unit                = registry canonical unit
information_state   = NOT_EXTRACTED
verification_state  = UNVERIFIED
origin              = NULL
confidence          = NULL

numeric_value       = NULL
integer_value       = NULL
text_value          = NULL
boolean_value       = NULL

inherited_from_attribute_id = NULL
```

This materialization must occur in the same transaction as equipment creation.

Do not use absent rows as the normal representation of an unpopulated canonical attribute.

The number of created attributes must exactly match the equipment definition in the Phase 5A registry.

---

# 12. Database enums vs text

Follow existing repository persistence conventions for closed state vocabularies where appropriate.

However:

- `equipment_type` MUST be `TEXT`, not a PostgreSQL enum.
- `attribute_key` MUST be `TEXT`.
- canonical `unit` MUST be `TEXT`/nullable.
- do not create a database table for the registry.

For lifecycle/information/verification/origin/value-type state vocabularies, choose the smallest implementation consistent with existing PostgreSQL/SQLAlchemy enum conventions.

If PostgreSQL enums are used:

- migration labels must exactly match domain enum values;
- ORM mappings must use existing `create_type=False` style after migration creation;
- downgrade must remove Phase 5B enum types safely after dependent tables are dropped.

Explain the choice in the handoff.

---

# 13. Migration

Create the next Alembic migration after:

```text
0006_document_classification
```

Use the next repository-conventional revision identifier, expected conceptually as:

```text
0007_engineering_model_core
```

unless repository conventions dictate a slightly different slug.

Migration must create:

```text
equipment_lineages
equipment
equipment_attributes
```

plus:

- required enum types if used;
- indexes;
- unique constraints;
- composite same-project/revision FKs;
- typed-value check constraints;
- confidence constraint;
- lifecycle/removal constraint;
- self-reference protections.

Do not create topology tables.

Do not modify existing document/classification semantics.

## 13.1 Migration testing

Add migration tests consistent with existing repository migration tests.

At minimum verify:

1. fresh upgrade from empty database through head;
2. upgrade from existing `0006_document_classification` with representative existing project/revision/document data;
3. Phase 5B tables/constraints exist;
4. existing data remains intact;
5. downgrade back to `0006_document_classification` succeeds;
6. re-upgrade succeeds;
7. no engineering-model rows are synthesized from existing documents.

---

# 14. Revision/project mutability and locking

Engineering-model writes must use the **same lifecycle rules** as revision document writes:

Editable when:

```text
project = ACTIVE or PAUSED
revision = DRAFT or ACTIVE
```

Read-only when:

```text
project = ARCHIVED or CANCELLED
revision = SUPERSEDED
```

Reads remain allowed.

## 14.1 Neutral write guard

Do not make engineering-model services semantically depend on a module named `revision_documents`.

The current repository contains shared locking/mutability helpers in:

```text
services/api/src/powerforge_api/services/revision_documents.py
```

For Phase 5B, extract/reuse the **smallest neutral revision-write guard/locking abstraction** so both documents and engineering-model writes use the same rules and lock order.

Preserve existing document behavior.

Required lock order:

```text
project first
revision second
```

Engineering mutations should use the same shared-project/read lock + revision write lock behavior as existing document mutations so archive/cancel/activation cannot race model writes.

Do not introduce a second concurrency model.

Run existing document/project regression tests after this refactor.

---

# 15. Service layer

Implement revision-scoped manual engineering-model services using existing API service conventions.

A reasonable shape is one service such as:

```text
EngineeringModelService
```

or a narrowly separated Equipment/Attribute service if that better fits repository style.

Do not add a repository abstraction layer solely for architectural aesthetics.

The service must accept:

```text
project_id
revision_id
```

as ownership boundaries for all operations.

Do not trust project/revision IDs from model objects supplied by callers.

---

# 16. Equipment create

Implement service behavior equivalent to:

```text
create_equipment(
    project_id,
    revision_id,
    equipment_type,
    tag=None,
    name=None,
    description=None,
    actor_id=None,
)
```

Exact signature may follow repository conventions.

The operation must:

1. acquire the normal project/revision write locks;
2. validate revision ownership and mutability;
3. validate `equipment_type` through Phase 5A registry-v1;
4. create a new EquipmentLineage;
5. create the Equipment snapshot;
6. materialize every applicable canonical EquipmentAttribute;
7. commit atomically;
8. return the persisted equipment with access to its materialized attributes.

Any failure must roll back:

```text
lineage
equipment
attributes
```

as one unit.

No topology nodes are created.

---

# 17. Equipment reads / listing

Implement service-level reads needed to validate Phase 5B behavior.

At minimum:

```text
get_equipment(project_id, revision_id, equipment_id)
list_equipment(project_id, revision_id, ...)
get_equipment_attributes(project_id, revision_id, equipment_id)
```

Default equipment listing excludes:

```text
REMOVED
```

but the service must support explicitly retrieving/filtering removed equipment for future restore/history behavior.

It is fine to add minimal type/status/search hooks if they naturally fit the service design, but do not spend Phase 5B building the complete Phase 5E HTTP filtering/pagination contract.

Cross-project/revision access must be reported as not found/mismatch according to existing API/service conventions rather than leaking another project's object.

---

# 18. Equipment metadata update

Support manual update of:

```text
tag
name
description
equipment_type
```

Do not expose mutation of:

```text
project_id
revision_id
lineage_id
origin
verification_state
inherited_from_equipment_id
audit creation fields
```

through normal metadata updates.

Metadata writes are manual and should update:

```text
updated_at
updated_by
```

`updated_by` remains nullable until auth exists.

Changing equipment type has additional rules below.

---

# 19. Safe equipment type changes

Equipment type changes are allowed, but meaningful canonical data must never be silently destroyed.

Before changing type:

1. load old EquipmentDefinition;
2. load new EquipmentDefinition;
3. inspect every current EquipmentAttribute;
4. classify each row as preservable, safely discardable, or conflicting;
5. reject the entire type change if any conflicting row exists;
6. only after validation, mutate rows/type atomically.

## 19.1 Preserve compatible attributes

An attribute may be preserved when the same key exists in the destination type and its persisted semantics remain compatible.

At minimum compatibility requires:

```text
same attribute_key
same value_type
same canonical_unit
```

For ENUM values:

- if `PRESENT`, the existing text value must be allowed by the destination definition;
- otherwise the change is conflicting.

Required/Critical/display metadata differences do not by themselves make a persisted value incompatible.

Do not automatically convert between different canonical attributes merely because they appear conceptually similar.

## 19.2 Safely discard only untouched rows

An old attribute that is not compatible with the destination type may be physically removed only when it is still an untouched materialized placeholder:

```text
information_state = NOT_EXTRACTED
verification_state = UNVERIFIED
origin = NULL
confidence = NULL
all typed values = NULL
```

If any incompatible/old-only attribute has meaningful state, reject the type change.

Meaningful states include:

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
CONFLICTING
```

Also treat a nominal `NOT_EXTRACTED` row with non-default provenance/value metadata as non-discardable.

## 19.3 New destination attributes

For registry keys that did not exist before, materialize fresh rows as:

```text
NOT_EXTRACTED / UNVERIFIED / origin NULL
```

using destination canonical value type and unit.

## 19.4 Transaction behavior

A rejected type change must leave:

```text
equipment_type
all attributes
all values/states
```

unchanged.

Add focused tests for this.

---

# 20. Manual attribute update

Implement a manual attribute mutation service conceptually equivalent to:

```text
set_attribute(
    project_id,
    revision_id,
    equipment_id,
    attribute_key,
    information_state,
    value=None,
    input_unit=None,
    actor_id=None,
)
```

Exact signature may differ.

Use the accepted Phase 5A functions:

```text
get_attribute_definition(...)
normalize_attribute_value(...)
```

Do not duplicate type/unit/enum validation.

## 20.1 PRESENT

For:

```text
information_state = PRESENT
```

the caller must provide a value.

For numeric/integer attributes:

- accept a compatible `input_unit`;
- normalize to the registry canonical unit;
- store the normalized canonical value in the correct typed slot.

For enum/text/boolean attributes:

- use Phase 5A validation;
- do not accept a unit.

After a successful manual PRESENT update:

```text
information_state  = PRESENT
origin             = MANUAL
verification_state = ENGINEER_REVIEWED
confidence         = NULL
unit               = canonical registry unit
```

Clear all unused typed slots.

## 20.2 Manual non-value states

The manual Phase 5B mutation path should support:

```text
UNKNOWN
MISSING
NOT_APPLICABLE
```

For these states:

- no canonical value may be supplied;
- clear every typed value slot;
- retain the canonical registry `unit`;
- set `origin = MANUAL`;
- set `verification_state = ENGINEER_REVIEWED`;
- set `confidence = NULL`.

## 20.3 States not exposed as ordinary manual edits

Do not use the ordinary manual update path to manufacture:

```text
AI_EXTRACTED
SYSTEM_VALIDATED
ENGINEER_VERIFIED
AI_EXTRACTION origin
confidence
```

Also do not expose ordinary manual commands to set:

```text
CONFLICTING
```

That state belongs to later reconciliation/system workflows.

`NOT_EXTRACTED` is the system initialization state. A separate private reset helper is unnecessary unless clearly needed by the implementation.

Do not prematurely build Phase 6 write paths.

---

# 21. Soft remove / restore

Implement service methods for:

```text
remove_equipment(...)
restore_equipment(...)
```

Behavior:

## Remove

- idempotent;
- set lifecycle to `REMOVED`;
- set `removed_at`;
- set `removed_by` when actor exists;
- retain lineage;
- retain all attributes;
- do not delete canonical values.

## Restore

- idempotent;
- set lifecycle to `ACTIVE`;
- clear `removed_at`;
- clear `removed_by`;
- retain attributes unchanged.

Phase 5B has no topology tables, so do **not** implement topology cascade behavior yet.

Phase 5D will add terminal/connection lifecycle effects.

---

# 22. Inherited-from fields in Phase 5B

Include:

```text
Equipment.inherited_from_equipment_id
EquipmentAttribute.inherited_from_attribute_id
```

in schema/ORM now because they are part of the accepted persistence architecture.

For all manual Phase 5B creation:

```text
inherited_from_equipment_id = NULL
inherited_from_attribute_id = NULL
```

Do not implement model carry-forward or manually populate these links.

Phase 5C owns revision inheritance.

---

# 23. No revision-creation changes yet

Do not add:

```text
carry_forward_model
```

to `RevisionCreate` in Phase 5B.

Do not change revision creation behavior.

Do not clone model data.

Those changes are Phase 5C.

This is important: Phase 5B establishes persistence and service semantics first so Phase 5C can clone a tested model.

---

# 24. No public CRUD API yet

Phase 5B is the **core persistence/service** slice.

Do not add the complete revision-scoped HTTP equipment/attribute API yet.

Phase 5E owns the public application API surface.

The existing Phase 5A endpoint remains:

```text
GET /api/engineering-model/registry
```

If a tiny internal/test-only schema is needed for service tests, keep it minimal and do not accidentally establish a premature public contract.

Do not create frontend work in this phase.

---

# 25. Errors and integrity mapping

Follow current repository patterns.

Add explicit service/domain errors for cases equivalent to:

```text
EquipmentNotFound
EquipmentAttributeNotFound / UnknownAttribute
InvalidEquipmentType
EquipmentTypeChangeConflict
InvalidEquipmentAttributeState
```

Use existing project/revision errors for:

```text
ProjectNotFound
RevisionNotFound
RevisionReadOnly
ArchivedProject
CancelledProject
```

Do not leak raw SQLAlchemy `IntegrityError` to callers.

Map known Phase 5B database constraints through the existing `integrity_guard` mechanism where a meaningful domain error exists.

Unexpected constraints must continue to become the existing safe generic unexpected-integrity error rather than exposing database data.

Keep raw user values out of logs for integrity errors.

---

# 26. Registry/database consistency

The database does not replace registry validation.

Every service write must verify:

```text
equipment_type exists in registry-v1
attribute_key belongs to that equipment type
stored value_type matches registry
stored unit matches registry canonical unit
enum PRESENT value belongs to allowed_values
```

Add a service/helper capable of detecting structurally inconsistent persisted rows during tests.

Do not make the database parse the registry JSON.

Do not add a registry database table.

---

# 27. Required/Critical and requirement rules

Phase 5B persistence does not store:

```text
required
critical
requirement rules
requirement findings
```

on each EquipmentAttribute row.

Those remain registry metadata.

Do not denormalize them into persistence.

Do not reject equipment creation because required/conditional values are missing.

Incomplete equipment is valid and expected.

The existing Phase 5A `evaluate_requirements()` may be used in tests/read-side helpers but does not block CRUD.

---

# 28. Audit behavior

Use existing repository conventions for audit timestamps.

EquipmentLineage:

```text
created_at
created_by
```

Equipment:

```text
created_at
created_by
updated_at
updated_by
removed_at
removed_by
```

EquipmentAttribute:

```text
created_at
created_by
updated_at
updated_by
```

Actor UUIDs remain nullable with no users FK.

Do not add a full append-only audit/history table.

Do not add event sourcing.

---

# 29. Numeric persistence

Use PostgreSQL/SQLAlchemy `NUMERIC` for:

```text
numeric_value
confidence
```

The accepted Phase 5A normalization layer returns `Decimal`.

Do not coerce canonical engineering values to binary `float` before persistence.

Integer attributes use an integer column.

---

# 30. Tests required for Phase 5B

Add thorough focused tests.

## 30.1 Migration/schema tests

Test:

- upgrade from `0006_document_classification`;
- fresh upgrade to head;
- downgrade to `0006`;
- re-upgrade;
- existing document/classification data preserved;
- Phase 5B tables exist;
- required indexes/constraints exist;
- no rows auto-created from Documents.

## 30.2 Equipment creation

Test:

- creates one lineage;
- creates one equipment snapshot;
- same project/revision ownership;
- manual defaults are correct;
- exactly all registry attributes for the equipment type are materialized;
- materialized rows have exact:
  - key,
  - value_type,
  - canonical unit,
  - NOT_EXTRACTED,
  - UNVERIFIED,
  - null origin/confidence/values;
- duplicate tags are allowed;
- invalid equipment type rejected;
- transaction rollback leaves no lineage/equipment/attributes on failure.

Use more than one representative equipment type, including one with many attributes and one with enums/unitless values.

## 30.3 Typed-value constraints

At database and service levels test:

- NUMBER uses numeric slot only;
- INTEGER uses integer slot only;
- TEXT/ENUM use text only;
- BOOLEAN uses boolean only;
- PRESENT with no value rejected;
- PRESENT with multiple value slots rejected by DB;
- non-PRESENT with a value rejected by DB/service;
- confidence outside `[0,1]` rejected;
- enum invalid value rejected;
- unit mismatch rejected/normalized through service.

## 30.4 Unit normalization

Through the persistence service test representative writes such as:

```text
600 V -> 0.6 kV
0.01 kVA -> 10 VA
0.01 s -> 10 ms where registry canonical unit is ms
```

Verify the database stores the canonical value/unit.

Do not duplicate all Phase 5A unit tests.

## 30.5 Manual states

Test:

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
```

Manual state changes must result in:

```text
origin = MANUAL
verification_state = ENGINEER_REVIEWED
confidence = NULL
```

Non-PRESENT states clear typed values.

Test that ordinary manual methods cannot forge AI/verified/confidence semantics.

## 30.6 Ownership and mutability

Test:

- wrong project/revision cannot access/mutate equipment;
- DRAFT writes allowed;
- ACTIVE writes allowed;
- SUPERSEDED writes rejected;
- PAUSED project writes allowed;
- ARCHIVED project writes rejected;
- CANCELLED project writes rejected;
- lock/order behavior follows existing revision document write semantics.

Run existing project/document concurrency tests after neutralizing shared write guards.

## 30.7 Soft lifecycle

Test:

- remove is idempotent;
- attributes retained;
- default list excludes removed;
- explicit read/list can see removed;
- restore is idempotent;
- restore preserves attributes.

## 30.8 Type changes

Test at least:

1. type change with only untouched NOT_EXTRACTED incompatible fields succeeds;
2. common compatible attributes are preserved;
3. destination-only fields materialize;
4. old-only untouched fields disappear;
5. old-only PRESENT field causes conflict/rejection;
6. old-only UNKNOWN/MISSING/NOT_APPLICABLE/CONFLICTING field causes conflict/rejection;
7. value-type/unit incompatible meaningful field causes rejection;
8. PRESENT ENUM preserved only when valid for destination;
9. rejected type change is atomic;
10. registry counts/materialization remain deterministic.

## 30.9 Regression

Run:

```text
Phase 5A registry/unit/requirement/API tests
project/revision tests
document tests relevant to mutability/locks
full Python test suite
live integration suite against a disposable database
ruff
format checks
git diff --check
```

No frontend checks are required unless Codex changes frontend files, which it should not.

---

# 31. Documentation updates

Update the minimum repository documentation to reflect actual implementation.

At minimum:

```text
docs/ENGINEERING_MODEL.md
docs/PROJECT_STATUS.md
```

Create:

```text
docs/PHASE5B_HANDOFF.md
```

The handoff must include:

- files/modules changed;
- neutral persistence-boundary decision;
- migration revision;
- exact table/constraint summary;
- service operations implemented;
- type-change behavior;
- lock/mutability behavior;
- exact test commands/results;
- deviations or unresolved concerns;
- explicit confirmation that Phase 5C has not begun.

Do not rewrite ADR-007 unless implementation reveals a genuine architectural conflict.

---

# 32. Implementation quality requirements

- Preserve Phase 5A registry behavior exactly.
- Do not duplicate registry data in ORM code.
- Do not use arbitrary JSON for canonical attributes.
- Do not use a table per equipment type.
- Do not make tag unique.
- Do not create `EngineeringModel`.
- Do not store Required/Critical flags per attribute row.
- Do not derive calculated engineering quantities.
- Do not hard-delete Equipment through service APIs.
- Do not add topology.
- Do not add model carry-forward.
- Do not add AI/provider dependencies.
- Keep SQLAlchemy out of the pure Phase 5A domain registry package.
- Keep FastAPI out of the pure domain package.
- Prefer explicit named constraints.
- Preserve project/revision lock ordering.
- Keep transactions atomic.
- Use Decimal/NUMERIC for engineering numerics.
- Keep the implementation reviewable and narrowly scoped.

---

# 33. Completion criteria

Phase 5B is complete only when:

- Phase 5A remains fully passing and unchanged semantically;
- neutral persistence ownership is established without a broad unrelated refactor;
- `equipment_lineages` exists and enforces project ownership;
- `equipment` exists and is revision scoped;
- `equipment_attributes` exists with typed relational values;
- `equipment_type` is registry-validated text, not PostgreSQL enum;
- duplicate tags are allowed;
- every created Equipment materializes the exact registry attributes;
- untouched materialized attributes use NOT_EXTRACTED + UNVERIFIED;
- canonical units/value types are stored from registry-v1;
- typed-value DB constraints work;
- manual PRESENT/state updates work and normalize units;
- manual values default to MANUAL + ENGINEER_REVIEWED;
- soft remove/restore works;
- safe type changes do not destroy meaningful information;
- project/revision mutability rules are enforced;
- known integrity constraints map safely;
- migration upgrade/downgrade is tested;
- full relevant regression passes;
- no Phase 5C+ functionality has been introduced.

---

# 34. End-of-task report

At the end, do **not** proceed to Phase 5C.

Provide a concise implementation report containing:

1. branch/base used;
2. files/modules created or changed;
3. persistence-boundary/refactor decision;
4. migration revision and tables created;
5. constraints/indexes added;
6. EquipmentLineage behavior;
7. Equipment behavior;
8. EquipmentAttribute/materialization behavior;
9. manual attribute mutation behavior;
10. type-change behavior;
11. lifecycle behavior;
12. project/revision lock and mutability behavior;
13. tests added;
14. exact lint/test/migration commands and results;
15. any specification/repository differences;
16. remaining concerns/technical debt;
17. explicit confirmation that no Phase 5C+ features were added.

If every acceptance criterion passes, state exactly:

```text
Phase 5B implementation is complete and ready for review.
```

Do not begin Phase 5C until instructed.
