# ADR-007: Canonical Engineering Model Persistence

**Status:** Accepted  
**Date:** 2026-10-22  
**Decision owners:** PowerForge maintainers  
**Related phase:** Phase 5 — Canonical Engineering Model  
**Related specification:** `docs/specs/phase-5-engineering-model.md`  
**Registry:** `registry-v1`

---

## Context

PowerForge needs a persistent canonical engineering model that can represent an electrical system independently of:

- the source documents from which information was obtained;
- any specific AI provider;
- ETAP, SKM, EasyPower, or another analysis package;
- any single project revision;
- future extraction, reconciliation, validation, and review workflows.

Earlier phases established project revisions, immutable documents, document processing, document classification, and revision inheritance.

Phase 5 introduces the first persistent engineering-model layer.

The intended long-term data flow is:

```text
Documents
    ↓
Evidence
    ↓
Extraction Candidates
    ↓
Canonical Engineering Model
    ↓
Engineer Verification
```

The engineering model must therefore be stable enough to support future AI extraction and study-tool export, while remaining fully usable through manual engineering entry before those later capabilities exist.

A number of architectural questions had to be resolved:

1. whether the engineering model should have its own aggregate/table or use `ProjectRevision` as the snapshot root;
2. how physical equipment should retain identity across revisions;
3. whether equipment attributes should be stored as JSON or relational typed rows;
4. how canonical units should be handled;
5. how unknown, missing, conflicting, and unreviewed information should be represented;
6. how electrical topology should be persisted;
7. how model carry-forward should work between project revisions;
8. where provenance, validation, review, and protection settings belong;
9. whether model data should depend on AI output or external analysis software structures.

---

## Decision

PowerForge will use `ProjectRevision` as the root of the canonical engineering-model snapshot.

There will be **no separate `EngineeringModel` table**.

The canonical model will consist of revision-scoped equipment, typed relational attributes, topology nodes, and topology connections.

The initial Phase 5 persistence model will contain:

```text
equipment_lineages
equipment
equipment_attributes
model_nodes
model_connections
```

The canonical equipment and attribute definitions will be controlled by a versioned code registry (`registry-v1`).

---

## 1. ProjectRevision is the model snapshot root

Every canonical engineering-model object belongs to a specific `ProjectRevision`.

A revision therefore represents a complete project snapshot containing, among other things:

```text
ProjectRevision
    ├── revision documents
    ├── equipment
    │   └── equipment attributes
    ├── model nodes
    └── model connections
```

No additional aggregate layer is introduced between `ProjectRevision` and engineering-model entities.

### Rationale

A separate `EngineeringModel` table would add an extra ownership layer without providing a distinct lifecycle.

The existing revision already defines:

- snapshot boundaries;
- mutability;
- inheritance;
- project ownership;
- activation/supersession;
- historical separation.

The engineering model should follow the same revision lifecycle.

---

## 2. Stable physical identity is represented by EquipmentLineage

Each physical equipment item has a stable lineage that persists across project revisions.

Conceptually:

```text
EquipmentLineage
    ├── Equipment snapshot in Revision A
    ├── Equipment snapshot in Revision B
    └── Equipment snapshot in Revision C
```

`EquipmentLineage` contains only stable project-level identity information.

It must not contain revision-specific properties such as:

- equipment tag;
- equipment type;
- rating;
- engineering attributes;
- verification state.

Those belong to the revision-scoped `Equipment` snapshot.

### Consequence

A physical breaker can retain the same lineage across revisions while its tag, rating, type, or other properties change between snapshots.

---

## 3. Equipment is revision scoped

`Equipment` represents one canonical equipment snapshot inside one revision.

At minimum it contains:

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

The combination:

```text
(revision_id, lineage_id)
```

must be unique.

Equipment tags are **not unique**.

Duplicate tags are permitted in Phase 5 and may later be flagged by validation.

---

## 4. Equipment types are registry controlled

Canonical equipment types are defined by `registry-v1`.

The initial registry contains 20 canonical equipment types:

```text
UTILITY_SOURCE
SYNCHRONOUS_GENERATOR
TWO_WINDING_TRANSFORMER
BUS
LV_BREAKER
HV_BREAKER
RECLOSER
OVERCURRENT_RELAY
FUSE
SINGLE_THROW_SWITCH
DOUBLE_THROW_SWITCH
CABLE
CT
INDUCTION_MOTOR
STATIC_LOAD
LUMPED_LOAD
CAPACITOR
REACTOR
VFD
UPS
```

Canonical equipment types are persisted as stable text keys validated by the registry.

They are **not stored as a PostgreSQL enum**.

### Rationale

The registry must be able to evolve without requiring a PostgreSQL enum migration for every future equipment-type addition.

---

## 5. Certain former equipment categories are intentionally consolidated

The following physical assemblies are represented as `BUS` plus a `bus_type` attribute:

```text
SWITCHGEAR
SWITCHBOARD
PANELBOARD
MCC
```

There is no separate canonical `DISCONNECT` equipment type.

A disconnect is represented as:

```text
SINGLE_THROW_SWITCH
```

with a separate `FUSE` where applicable.

A physical junction enclosure may be represented as a `BUS` subtype such as `JUNCTION_BOX`.

A pure electrical connectivity junction is represented by a topology node rather than equipment.

---

## 6. Equipment attributes are relational typed rows

Canonical equipment attributes are stored in `equipment_attributes`.

Attributes are not stored as one arbitrary JSON document on the Equipment row.

Each attribute row contains:

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

Supported canonical value types are:

```text
NUMBER
INTEGER
TEXT
BOOLEAN
ENUM
```

ENUM values use the text slot but are validated against the registry definition.

### Rationale

Relational typed attributes provide:

- queryability;
- validation;
- stable canonical keys;
- unit enforcement;
- provenance attachment later;
- independent attribute-level verification;
- future candidate/evidence linkage;
- better compatibility with engineering workflows than arbitrary JSON.

---

## 7. Registry-defined attributes are the only canonical attributes

Canonical attribute keys are defined by the versioned engineering registry.

The AI layer, importers, APIs, or users must not create arbitrary canonical keys.

Unknown source information may later exist as extraction candidates or evidence, but it cannot become canonical until mapped to a registry-defined attribute.

The registry defines:

- attribute key;
- display name;
- value type;
- canonical unit;
- Required flag;
- Critical flag;
- allowed enum values;
- notes;
- display order;
- conditional requirement relationships.

---

## 8. Required and Critical are distinct concepts

`Required` means:

> the attribute is unconditionally required for a minimally useful canonical representation of the equipment type.

`Critical` means:

> missing or incorrect information can materially prevent, invalidate, or significantly affect at least one intended engineering study or model.

Therefore:

```text
required = false
critical = true
```

is valid and expected.

Conditional engineering requirements are not expressed by marking every participating attribute `Required = true`.

They are represented using structured requirement rules.

---

## 9. Conditional requirement rules are first-class domain logic

The registry supports:

```text
ANY_OF
ALL_OF
REQUIRED_IF
ALL_OR_NONE
```

Examples include:

- Utility Source fault-current representation **or** sequence-impedance representation;
- Cable physical construction **or** direct sequence impedances;
- Static Load kVA + PF **or** kW + kvar;
- Reactor requirements dependent on reactor type;
- grounding parameters required only when the corresponding grounding configuration is selected.

These rules are domain validation/completeness rules.

They are not database `NOT NULL` constraints.

Incomplete equipment must remain persistable.

---

## 10. All applicable attributes are materialized

When equipment is created, PowerForge creates one `EquipmentAttribute` row for every registry-defined attribute applicable to that equipment type.

Unpopulated rows begin as:

```text
information_state = NOT_EXTRACTED
verification_state = UNVERIFIED
origin = null
confidence = null
```

### Rationale

The system must distinguish:

```text
attribute exists but has not been populated
```

from:

```text
attribute does not exist for this equipment type
```

This distinction will be important for later extraction, validation, and engineer review workflows.

---

## 11. Information state, verification state, and value origin are separate

PowerForge must not overload one status field to represent multiple concepts.

### InformationState

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
NOT_EXTRACTED
CONFLICTING
```

### VerificationState

```text
UNVERIFIED
AI_EXTRACTED
SYSTEM_VALIDATED
ENGINEER_REVIEWED
ENGINEER_VERIFIED
```

### ValueOrigin

```text
MANUAL
AI_EXTRACTION
INFERRED
IMPORTED
```

Manual Phase 5 values default to:

```text
information_state = PRESENT
origin = MANUAL
verification_state = ENGINEER_REVIEWED
confidence = null
```

Manual entry does **not** automatically mean `ENGINEER_VERIFIED`.

---

## 12. Typed-value invariants are enforced

When:

```text
information_state = PRESENT
```

exactly one value slot compatible with `value_type` must be populated.

When:

```text
information_state != PRESENT
```

all typed value slots must be null.

The registry controls which value slot is valid.

Examples:

```text
NUMBER  → numeric_value
INTEGER → integer_value
TEXT    → text_value
ENUM    → text_value
BOOLEAN → boolean_value
```

---

## 13. Canonical units belong to AttributeDefinition

Every numeric engineering attribute defines its canonical storage unit in the registry.

Unit families define compatible input units and deterministic conversions.

The unit-family default does not override the attribute-specific canonical unit.

For example:

```text
rated_voltage
→ kV

electrode_gap
→ mm

trip_output_operating_time
→ ms

rated_burden
→ VA

rated_apparent_power
→ kVA
```

Canonical values are normalized before persistence.

Raw values and source units extracted from documents will later belong to Evidence/Candidate provenance rather than the canonical attribute row.

---

## 14. Equipment uses a soft lifecycle

Equipment lifecycle is:

```text
ACTIVE
REMOVED
```

Removing equipment does not delete it.

Its attributes remain preserved.

Removed equipment is excluded from default active-model behavior and is not carried forward to a new revision.

This supports historical traceability and future review workflows.

---

## 15. Equipment type changes are allowed but must be safe

Equipment type may change inside a writable revision.

PowerForge must:

1. preserve attributes that remain semantically compatible;
2. materialize newly applicable attributes;
3. automatically discard only incompatible attributes that remain untouched `NOT_EXTRACTED`;
4. reject the type change if incompatible attributes contain meaningful information.

Meaningful information includes:

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
CONFLICTING
```

No meaningful canonical information may be silently destroyed.

---

## 16. Topology is persisted separately from equipment attributes

Electrical topology is represented using:

```text
ModelNode
ModelConnection
```

Connections never directly link equipment records.

They connect topology nodes.

### ModelNode kinds

```text
EQUIPMENT_TERMINAL
ELECTRICAL_NODE
```

An equipment terminal belongs to a specific equipment snapshot and has a flexible `terminal_key`.

An electrical node represents a junction/connectivity point and has no equipment owner.

There is no terminal-definition registry in Phase 5.

---

## 17. ModelConnection represents connectivity

A ModelConnection connects two ModelNodes.

At minimum it contains:

```text
from_node_id
to_node_id
connection_kind
direction
phase_configuration
nominal_voltage
lifecycle_status
origin
verification_state
confidence
```

Connection kinds are:

```text
ELECTRICAL
GROUNDING
OTHER
```

Directions are:

```text
UNDIRECTED
NOMINAL_FROM_TO
```

Parallel connections are allowed.

Self-loops are rejected.

A cable is canonical equipment, not a connection type.

For example:

```text
Bus terminal
    ↓ connection
Cable terminal A
[CABLE equipment]
Cable terminal B
    ↓ connection
Load terminal
```

---

## 18. Topology is manually authored in Phase 5

Phase 5 persists topology but does not infer it.

The following are deferred:

- AI topology extraction;
- SLD interpretation;
- graph visualization;
- React Flow;
- automatic terminal creation;
- automatic engineering connectivity inference.

---

## 19. Equipment removal affects topology conservatively

Removing equipment:

1. marks the equipment `REMOVED`;
2. retains all attributes;
3. soft-removes active terminal nodes belonging to it;
4. soft-removes active connections incident to those terminals.

Restoring equipment:

1. restores the equipment;
2. restores its terminal nodes;
3. does **not** automatically restore removed connections.

### Rationale

Automatically restoring electrical connections could silently recreate topology that may no longer be valid.

---

## 20. Engineering-model carry-forward is independent of document carry-forward

Revision creation gains:

```text
carry_forward_model
```

This is independent from:

```text
carry_forward_documents
```

When a new revision has a base revision:

```text
carry_forward_model = true
```

by default.

Without a base revision:

```text
carry_forward_model = false
```

Model and document carry-forward must not implicitly control one another.

---

## 21. Revision carry-forward creates independent snapshots

When model carry-forward is enabled:

1. active equipment is cloned;
2. new equipment snapshot IDs are created;
3. lineage IDs are preserved;
4. `inherited_from_equipment_id` points to the source snapshot;
5. attributes are cloned with new IDs;
6. `inherited_from_attribute_id` is populated;
7. active nodes are cloned;
8. terminal equipment references are remapped;
9. active connections are cloned;
10. connection node references are remapped;
11. `inherited_from_node_id` and `inherited_from_connection_id` are populated.

After cloning, the descendant revision is independent.

Editing the new revision must not mutate the source revision.

---

## 22. Revision cloning is transactional

Revision creation, document carry-forward, and engineering-model carry-forward must use the existing revision creation transaction and locking strategy wherever possible.

A cloning failure must not leave:

- a partially copied engineering model;
- invalid cross-revision references;
- orphaned topology;
- partially initialized revision state.

Do not introduce a second independent concurrency model specifically for engineering-model inheritance.

---

## 23. Canonical model writes obey revision mutability rules

Engineering-model writes use the same project/revision lifecycle rules as document writes.

Frozen, superseded, or otherwise read-only revisions cannot be modified through engineering-model mutation APIs.

All nested objects must belong to the project/revision identified by the request path.

Cross-project and cross-revision relationships are rejected.

---

## 24. Evidence and extraction provenance are deferred

Phase 5 is designed to be evidence-ready but does not persist full evidence provenance.

The following are deferred to Phase 6 or later:

```text
Evidence
ExtractionCandidate
AttributeEvidenceLink
page/bounding-box provenance
source-document conflict records
```

Phase 5 must not shortcut future provenance by storing document/page references directly on canonical attributes.

---

## 25. Validation findings are deferred

The registry includes Required, Critical, and conditional-requirement semantics.

Phase 5 may evaluate model completeness through pure domain functions.

However, it does not introduce the later persistent validation engine.

The following are deferred:

```text
ValidationFinding
validation rule execution history
study readiness findings table
duplicate-tag findings
engineering rule findings
```

Incomplete equipment must remain saveable.

---

## 26. Engineer review workflow is deferred

Phase 5 stores `verification_state`, including:

```text
ENGINEER_REVIEWED
ENGINEER_VERIFIED
```

but does not implement the full verification/review queue.

Manual values default to `ENGINEER_REVIEWED`.

A dedicated engineer-verification workflow will be introduced in a later phase.

---

## 27. Advanced protection settings are deferred

The Phase 5 registry intentionally includes some equipment/design protection attributes, including:

```text
LV_BREAKER.trip_rating
LV_BREAKER.long_time_pickup
```

These are canonical design attributes frequently obtained from one-lines or shop drawings.

A future structured protection subsystem may separately model:

```text
50
51
50N
51N
67
trip-unit stages
relay setting groups
study-adjusted protection settings
```

The future protection-settings model must not overwrite canonical design/nameplate data.

No general `ProtectionFunction` persistence model is introduced in Phase 5.

---

## 28. Equipment containment is deferred

Physical containment and electrical connectivity are different concepts.

Examples of possible future containment:

```text
SWGR-1
    contains MAIN breaker
    contains feeder breakers
    contains relay
```

Phase 5 does not introduce:

```text
parent_equipment_id
```

or a containment table.

This may be added later through a separate architectural decision.

Electrical topology must not be misused to represent physical containment.

---

## 29. AI is not a source of truth

The canonical engineering model is independent of AI providers.

Future AI extraction will generate candidates/evidence that may propose canonical values.

AI must never be able to:

- invent canonical equipment types;
- invent canonical attribute keys;
- bypass registry validation;
- silently overwrite engineer-reviewed canonical values.

Phase 5 must therefore remain fully functional with no AI provider configured.

---

## 30. Analysis-software independence

The canonical model must not mirror ETAP, SKM, EasyPower, or another tool's internal schema.

The registry represents engineering concepts first.

Future exporters will translate canonical equipment, attributes, and topology into software-specific models.

This separation is intentional.

---

## Consequences

### Positive consequences

This decision provides:

- clean revision snapshots;
- stable equipment identity across revisions;
- explicit canonical engineering semantics;
- queryable typed values;
- deterministic units;
- safe support for incomplete data;
- future evidence/provenance attachment points;
- future AI extraction without making AI authoritative;
- independent model inheritance;
- topology persistence independent of equipment metadata;
- a stable foundation for exporters and engineering studies.

### Costs and tradeoffs

The design introduces more rows and domain logic than a simple JSON blob.

In particular:

- every applicable equipment attribute is materialized;
- revision cloning requires ID remapping;
- topology ownership must be validated;
- conditional completeness cannot be represented solely through SQL constraints;
- future registry changes require controlled migration/backfill behavior.

These costs are accepted because traceability, engineering correctness, revision history, and future extraction/reconciliation requirements are more important than minimizing the number of tables or rows.

---

## Alternatives considered

### Alternative 1: Separate EngineeringModel table

Rejected.

`ProjectRevision` already defines the lifecycle and snapshot boundary. An additional EngineeringModel aggregate would add indirection without a separate meaningful lifecycle.

---

### Alternative 2: Store equipment attributes as JSON

Rejected as the canonical persistence model.

JSON would simplify initial storage but makes attribute-level:

- validation;
- unit enforcement;
- provenance;
- querying;
- verification;
- inheritance;
- conflict handling

substantially weaker.

Typed relational rows better support PowerForge's long-term workflow.

---

### Alternative 3: Store canonical values using arbitrary AI-generated keys

Rejected.

This would make the canonical model unstable and provider dependent.

All canonical keys must come from the registry.

---

### Alternative 4: Use PostgreSQL enums for equipment types

Rejected.

Registry evolution should not require database enum alteration for every future equipment type.

Stable text keys validated in application/domain code provide sufficient integrity while preserving extensibility.

---

### Alternative 5: Represent connections directly between equipment records

Rejected.

Electrical equipment often has multiple terminals and may participate in several independent connectivity relationships.

Node/terminal-based topology is more expressive and necessary for future one-line modeling.

---

### Alternative 6: Treat cables as topology connections only

Rejected.

Cables have substantial canonical engineering data:

- conductor size;
- material;
- cores;
- parallel runs;
- length;
- sequence impedance;
- ampacity;
- insulation;
- installation information.

Therefore cables are equipment with terminals.

---

### Alternative 7: Hard-delete removed equipment

Rejected.

PowerForge revisions and future engineering-review workflows require historical traceability.

Soft lifecycle state is used instead.

---

### Alternative 8: Couple model inheritance to document inheritance

Rejected.

Documents and engineering-model state are related but independent.

A revision may:

- carry documents without carrying a model;
- carry a model without all prior documents;
- carry both;
- carry neither.

---

### Alternative 9: Add full Evidence persistence in Phase 5

Rejected.

Evidence belongs to the extraction/provenance workflow introduced later.

Phase 5 establishes compatible canonical targets without prematurely implementing Phase 6.

---

### Alternative 10: Add full protection-function persistence now

Rejected.

Phase 5 only needs canonical equipment/design data.

Protection functions and study settings deserve their own structured subsystem rather than being prematurely forced into flat equipment attributes.

---

## Invariants

The following invariants are mandatory:

1. Every Equipment belongs to exactly one ProjectRevision.
2. Every EquipmentLineage belongs to exactly one Project.
3. `(revision_id, lineage_id)` is unique.
4. Equipment tags are not unique.
5. Every EquipmentAttribute belongs to the same project/revision as its Equipment.
6. Every canonical attribute key is valid for its equipment type.
7. Attribute value type matches the registry.
8. PRESENT attributes contain exactly one compatible value.
9. Non-PRESENT attributes contain no canonical value.
10. Canonical numeric values use the attribute-defined canonical unit.
11. Equipment type keys are registry controlled.
12. ModelNode equipment terminals reference equipment in the same revision.
13. ModelConnection endpoints belong to the same project/revision.
14. ModelConnection cannot connect a node to itself.
15. Parallel ModelConnections are allowed.
16. Removed equipment is not carried forward.
17. Model inheritance preserves lineage but creates new snapshot IDs.
18. Destination revision objects never directly reuse source revision entity IDs except lineage IDs and explicit `inherited_from_*` references.
19. Model writes cannot bypass revision mutability rules.
20. AI is never the canonical source of truth.

---

## Implementation scope

This ADR governs Phase 5 implementation work:

```text
Phase 5A — registry, units, requirement engine
Phase 5B — equipment and attribute persistence
Phase 5C — revision inheritance
Phase 5D — topology persistence
Phase 5E — application APIs
Phase 5F — Engineering Model frontend
Phase 5G — hardening and documentation
```

The detailed implementation contract is maintained in:

```text
docs/specs/phase-5-engineering-model.md
```

The approved registry snapshot is maintained in:

```text
docs/specs/registry/PowerForge_registry-v1_reference.json
```

---

## Deferred decisions

The following are explicitly not decided by this ADR:

- equipment containment model;
- general protection-function persistence;
- evidence/candidate schema;
- conflict/reconciliation model;
- persistent validation findings;
- engineer verification workflow;
- topology visualization;
- SLD extraction;
- study-specific operating scenarios;
- ETAP/SKM/EasyPower export schemas;
- full audit/event sourcing.

Each may require a later ADR.

---

## Decision outcome

PowerForge will persist the canonical engineering model as a **revision-scoped, registry-controlled, typed relational snapshot** rooted at `ProjectRevision`, with stable equipment lineage across revisions and explicit node/connection topology.

This structure becomes the canonical engineering foundation for all later extraction, reconciliation, validation, review, visualization, export, and study-generation phases.
