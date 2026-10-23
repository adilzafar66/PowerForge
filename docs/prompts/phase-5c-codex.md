# PowerForge Phase 5C — Revision Model Inheritance & Revision-Level Engineering Metadata

You are implementing **Phase 5C only** of PowerForge.

Phase 5A and Phase 5B are complete and accepted.

Phase 5C introduces:

- independent engineering-model carry-forward during revision creation;
- cloning of active Equipment and EquipmentAttribute snapshots;
- lineage preservation;
- `inherited_from_*` snapshot provenance;
- revision-level engineering-model metadata:
  - `system_frequency`
  - `system_phase_count`
- inheritance/edit semantics for those metadata fields;
- transactional rollback and concurrency coverage.

Do **not** proceed to Phase 5D or later.

In particular, Phase 5C does **not** implement topology persistence, public engineering-model CRUD APIs, frontend Engineering Model UI, AI extraction, Evidence, reconciliation, validation findings, or study-tool export.

---

# 1. Authoritative inputs

Before making changes, read and understand:

```text
docs/specs/phase-5-engineering-model.md
decisions/ADR-007-canonical-engineering-model-persistence.md
docs/ENGINEERING_MODEL.md
docs/PHASE5A_HANDOFF.md
docs/PHASE5B_HANDOFF.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md          # if already created by the roadmap-doc reconciliation task
```

Also inspect the accepted Phase 5A/5B implementation in:

```text
packages/engineering-model/src/powerforge_engineering_model/
packages/persistence/src/powerforge_persistence/
services/api/src/powerforge_api/services/engineering_model_service.py
services/api/src/powerforge_api/services/revision_service.py
services/api/src/powerforge_api/services/revision_writes.py
services/api/src/powerforge_api/services/revision_documents.py
services/api/src/powerforge_api/schemas/projects.py
database/migrations/0007_engineering_model_core.py
tests/
```

Source-of-truth order:

1. this Phase 5C prompt for Phase 5C scope and the newly approved model-level metadata requirements;
2. `docs/specs/phase-5-engineering-model.md` for Phase 5 architecture/behavior;
3. ADR-007 for persistence architecture;
4. accepted Phase 5A/5B code and handoffs for repository reality;
5. registry-v1 for equipment/attribute semantics.

If repository reality materially conflicts with a required invariant, do not silently weaken the invariant. Report the conflict.

---

# 2. Baseline / branch requirement

Start from the accepted Phase 5B implementation.

At the time this prompt was prepared, Phase 5B lives on:

```text
codex/phase-5b-core-persistence
```

with head beginning:

```text
bf9c7e0
```

If Phase 5B has since been merged into `main`, use current `main`.

Before editing, confirm the baseline contains:

```text
equipment_lineages
equipment
equipment_attributes
EquipmentLineage
Equipment
EquipmentAttribute
EngineeringModelService
neutral packages/persistence
VerificationState.UNVERIFIED
LifecycleStatus
ValueOrigin
migration 0007_engineering_model_core
```

Do not start from Phase 5A or an older main.

---

# 3. Inspect repository behavior before editing

Understand the current revision-creation flow, especially:

```text
RevisionCreate
RevisionCreateResult
RevisionService.create_revision()
RevisionService._resolve_base()
RevisionService._resolve_carry_forward()
copy_included_associations()
project/revision lock ordering
activation transaction behavior
```

Also inspect:

- current migration-testing patterns;
- current response schema behavior;
- existing document carry-forward tests;
- engineering persistence constraints;
- engineering service consistency validation;
- current project/revision mutability semantics.

Phase 5C must integrate with the existing transaction rather than creating a parallel revision workflow.

---

# 4. Phase 5C scope

Phase 5C MUST deliver:

```text
carry_forward_model
independent document/model carry-forward decisions
model cloning during revision creation
EquipmentLineage preservation
new Equipment snapshot IDs
new EquipmentAttribute snapshot IDs
inherited_from_equipment_id
inherited_from_attribute_id
registry-evolution materialization
revision-level system_frequency
revision-level system_phase_count
metadata inheritance
metadata manual update service/schema support
transaction/rollback behavior
concurrency coverage
migration 0008 (or repository-conventional equivalent)
tests
documentation/handoff updates
```

Phase 5C MUST NOT implement:

```text
ModelNode
ModelConnection
topology cloning
topology CRUD
public equipment/attribute CRUD endpoints
Engineering Model frontend
React Flow
AI extraction
Evidence
ExtractionCandidate
Conflict
reconciliation
persistent validation findings
ProtectionFunction persistence
study configurations
ETAP/SKM/EasyPower integration
report generation
```

---

# 5. Preserve the architectural root

`ProjectRevision` remains the engineering-model snapshot root.

Do **not** add:

```text
EngineeringModel
EngineeringModelRevision
ModelSnapshot
```

tables/entities.

Revision-level engineering metadata belongs directly to the `ProjectRevision` snapshot unless a minimal neutral companion structure is strictly required by repository constraints.

The preferred design for Phase 5C is to add nullable columns to `project_revisions`.

Do not create a generic key/value JSON metadata blob.

---

# 6. New revision-level engineering metadata

Add these optional model-wide attributes:

```text
system_frequency
system_phase_count
```

They are properties/assumptions of the revision's engineering-model snapshot.

They are **not EquipmentAttribute rows** and must not be copied into every equipment record.

---

# 7. system_frequency semantics

Persist a revision-wide common system frequency.

Canonical semantics:

```text
name: system_frequency
type: decimal-safe numeric
canonical unit: Hz
nullable: yes
scope: ProjectRevision
```

Typical values:

```text
50
60
```

Do not artificially restrict the database to only 50/60 Hz unless an approved standard/spec already requires that. The structural rule should be:

```text
system_frequency IS NULL OR system_frequency > 0
```

Use PostgreSQL/SQLAlchemy `NUMERIC` / Python `Decimal`.

Do not use float persistence.

The stored value is always in Hz.

No separate unit column is necessary because this field has one fixed canonical unit.

---

# 8. system_phase_count semantics

Persist an optional revision-wide common phase count.

Canonical semantics:

```text
name: system_phase_count
type: integer
allowed values when present: 1 or 3
nullable: yes
scope: ProjectRevision
```

Meaning:

- `1` means a common single-phase assumption is asserted for the model;
- `3` means a common three-phase assumption is asserted for the model;
- `NULL` means no single system-wide phase-count assumption is asserted.

`NULL` is appropriate for:

- mixed single-phase/three-phase systems;
- unknown/not-yet-defined systems;
- cases where a global phase-count assumption should not be applied.

Do not introduce:

```text
0
MIXED
UNKNOWN
```

sentinel values.

Enforce at the database level:

```text
system_phase_count IS NULL OR system_phase_count IN (1, 3)
```

---

# 9. Effective-value semantics

Phase 5C must establish the **domain semantics**, but does not need to build a broad public API or Phase 10 validation system.

For equipment attributes whose canonical registry includes frequency or phase count:

## Frequency

Conceptual effective value:

```text
explicit equipment frequency PRESENT
        ↓
use explicit equipment value
else
revision.system_frequency present
        ↓
use revision-wide system frequency
else
unspecified
```

## Phase count

Conceptual effective value:

```text
explicit equipment phase_count PRESENT
        ↓
use explicit equipment value
else
revision.system_phase_count present
        ↓
use revision-wide system phase count
else
unspecified
```

Do not materialize these inherited/default values into EquipmentAttribute rows.

Do not change attribute `information_state` because a revision-level default exists.

Example:

```text
equipment.frequency = NOT_EXTRACTED
revision.system_frequency = 60 Hz
```

must remain:

```text
equipment frequency row = NOT_EXTRACTED
effective frequency = 60 Hz
```

The revision-level default is not fabricated evidence about the equipment row.

---

# 10. Explicit-value mismatch policy

Phase 5C must not silently ignore disagreement between model-wide metadata and explicit equipment values.

However, full deterministic validation findings belong to Phase 10.

For Phase 5C:

- provide a pure/helper-level consistency check or effective-value utility if useful;
- do not persist a validation finding;
- do not silently overwrite explicit equipment values;
- do not automatically rewrite system metadata.

The minimum accepted behavior is that the domain/service layer can identify a mismatch deterministically.

Examples:

```text
system_frequency = 60 Hz
equipment.frequency = PRESENT 50 Hz
=> mismatch detectable
```

```text
system_phase_count = 3
equipment.phase_count = PRESENT 1
=> mismatch detectable
```

Do not reject all model edits solely because such a mismatch exists unless the current Phase 5 specification explicitly requires blocking behavior.

Prefer:

```text
preserve both
make mismatch observable
leave enforcement/persistent findings to Phase 10
```

Document the chosen behavior clearly.

---

# 11. Migration

Create the next Alembic migration after:

```text
0007_engineering_model_core
```

Expected conceptual revision:

```text
0008_revision_model_metadata
```

or repository-conventional equivalent.

Add to `project_revisions`:

```text
system_frequency NUMERIC NULL
system_phase_count INTEGER NULL
```

Add named check constraints:

```text
system_frequency IS NULL OR system_frequency > 0
system_phase_count IS NULL OR system_phase_count IN (1,3)
```

Do not create topology tables.

Do not synthesize values for existing revisions.

Existing revisions must migrate with:

```text
system_frequency = NULL
system_phase_count = NULL
```

Downgrade must remove the new constraints/columns and return cleanly to 0007.

---

# 12. ORM mapping

Update neutral persistence `ProjectRevision` mapping.

Use:

```text
Decimal | None
int | None
```

for the two fields.

Keep project/revision mappings in the neutral persistence package.

Preserve compatibility re-exports.

Do not move engineering semantics back into document-processing.

---

# 13. RevisionCreate request

Extend revision creation with:

```text
carry_forward_model: bool | None
```

Semantics must mirror document carry-forward but remain independent.

Resolution rule:

```text
if base exists:
    omitted/null -> true
else:
    omitted/null -> false
```

Explicit:

```text
carry_forward_model = true
```

without a resolved base must be rejected.

`carry_forward_documents` and `carry_forward_model` must be independent.

Examples:

```text
documents true, model true
documents true, model false
documents false, model true
documents false, model false
```

must all be valid when a base exists.

Do not infer one from the other.

---

# 14. Revision-level metadata on creation

Extend revision creation so callers may optionally provide:

```text
system_frequency
system_phase_count
```

for the new revision.

Use explicit override semantics.

Recommended deterministic behavior:

## No base revision

If supplied:

```text
use supplied metadata
```

If omitted:

```text
NULL
```

## Base revision exists

For each metadata field independently:

### Field explicitly supplied in RevisionCreate

Use the explicit supplied value.

### Field omitted

If `carry_forward_model = true`:

```text
inherit the base revision's value
```

If `carry_forward_model = false`:

```text
NULL
```

This means revision-wide engineering metadata belongs to the model carry-forward decision.

Do not couple it to `carry_forward_documents`.

### Explicit null

Pydantic must distinguish **omitted** from **explicit null**.

If the caller explicitly supplies:

```json
{"system_frequency": null}
```

or:

```json
{"system_phase_count": null}
```

that means:

```text
clear / do not inherit this field
```

even when `carry_forward_model = true`.

Use `model_fields_set` or equivalent repository pattern.

---

# 15. Revision metadata update

Allow writable revisions to update:

```text
system_frequency
system_phase_count
```

through the existing revision metadata update path or a narrowly scoped service path consistent with repository conventions.

Do not create a full engineering-model public API in Phase 5C.

Updates must honor:

```text
ACTIVE/PAUSED project allowed
DRAFT/ACTIVE revision allowed
SUPERSEDED revision read-only
ARCHIVED/CANCELLED project read-only
```

Do not let the existing Phase 1 weakness—if any remains around superseded revision identifier/description editing—become precedent for engineering metadata.

Engineering metadata must obey current engineering/document mutability rules.

Use the existing neutral locking helpers.

---

# 16. Revision response

Expose in revision responses:

```text
system_frequency
system_phase_count
```

Also expose:

```text
inherited_model_equipment_count
```

on the create response only, analogous to `inherited_document_count`.

If repository conventions suggest a slightly different name, use a precise stable name and document it.

Do not expose giant cloned model payloads in the revision response.

---

# 17. RevisionCreateResult

Extend the internal result to report both inheritance counts:

```text
inherited_document_count
inherited_model_equipment_count
```

Do not overload one count.

---

# 18. Model clone scope

When:

```text
carry_forward_model = true
```

clone only:

```text
ACTIVE Equipment
all materialized attributes belonging to those ACTIVE Equipment rows
```

Do **not** clone:

```text
REMOVED Equipment
orphaned/corrupt rows
topology (not implemented yet)
```

Removed equipment is intentionally absent from the descendant snapshot.

Its lineage remains in `equipment_lineages` because lineage is project-level stable identity.

---

# 19. Equipment clone behavior

For every ACTIVE source Equipment in the selected base revision:

Create a destination Equipment row with:

```text
new id
same project_id
destination revision_id
same lineage_id
same equipment_type
same tag
same name
same description
same lifecycle_status = ACTIVE
same origin
same verification_state
inherited_from_equipment_id = source.id
new created_at
created_by = current actor if available / null under current auth model
new updated_at
updated_by = current actor if available / null
removed_at = NULL
removed_by = NULL
```

Important:

Inheritance does **not** change semantic origin.

Examples:

```text
source origin MANUAL -> destination origin MANUAL
source origin IMPORTED -> destination origin IMPORTED
```

Do not set origin to something like `INHERITED`.

Inheritance is represented by:

```text
inherited_from_equipment_id
```

Preserve the same `EquipmentLineage`.

Generate a new Equipment snapshot ID.

---

# 20. Attribute clone behavior

For every source EquipmentAttribute that belongs to cloned equipment:

Create a destination EquipmentAttribute with:

```text
new id
destination project_id/revision_id/equipment_id
same attribute_key
same value_type
same canonical unit
same information_state
same verification_state
same origin
same confidence
same typed canonical value
inherited_from_attribute_id = source.id
new audit timestamps/actors
```

Preserve exact Decimal values.

Do not reconvert canonical values during normal clone.

Do not reinterpret MANUAL as inherited origin.

---

# 21. Registry-evolution behavior

This is mandatory.

The destination snapshot must conform to the **current runtime registry-v1 definition** for the equipment type.

After cloning source attributes:

1. resolve the current EquipmentDefinition;
2. validate every source attribute still exists and is compatible;
3. preserve compatible source rows;
4. for any registry attribute that does not exist in the source snapshot, materialize it in the destination as a fresh untouched row.

New materialized destination-only row:

```text
information_state = NOT_EXTRACTED
verification_state = UNVERIFIED
origin = NULL
confidence = NULL
typed values = NULL
inherited_from_attribute_id = NULL
canonical unit/value_type from current registry
```

Do not mutate the source revision.

---

# 22. Registry incompatibility during clone

Do not silently coerce or discard meaningful source data if the runtime registry has changed incompatibly.

If a source attribute key still exists but:

```text
value_type changed
canonical unit changed incompatibly
PRESENT enum value is no longer valid
```

then model carry-forward must fail atomically with an explicit domain error.

Likewise, if a source snapshot contains a meaningful old-only attribute that is no longer present in the current registry, do not silently drop it.

Use a conservative rule aligned with Phase 5B type changes:

An old-only/incompatible source attribute may be omitted only if it is an untouched placeholder:

```text
NOT_EXTRACTED
UNVERIFIED
origin NULL
confidence NULL
all typed values NULL
```

Otherwise cloning fails.

This protects historical engineering information.

---

# 23. inherited_from semantic correctness

Phase 5B DB constraints enforce same-project references.

Phase 5C must enforce the stronger semantic invariant:

> Every `inherited_from_equipment_id` written by revision cloning must point to the corresponding source Equipment in the actual selected `based_on_revision_id`.

Likewise:

> Every `inherited_from_attribute_id` must point to the source attribute of that source Equipment in the selected base revision.

Tests must explicitly prove this.

Do not allow the clone service to source from arbitrary same-project revisions.

---

# 24. Independent snapshot semantics

After successful revision creation:

```text
source and destination are independent snapshots
```

Changing source later must not modify destination.

Changing destination later must not modify source.

No destination EquipmentAttribute may share the same row ID as source.

Only stable lineage is shared.

Do not create ORM relationships that cause accidental cross-revision cascade updates.

---

# 25. Transaction boundary

Revision creation + optional document inheritance + optional model inheritance + metadata creation/inheritance + optional activation must be one atomic transaction.

Conceptually:

```text
lock project/base
resolve base
resolve carry_forward_documents
resolve carry_forward_model
resolve model metadata
insert revision
copy documents if requested
copy model if requested
activate if requested
commit
```

If any step fails:

```text
no revision
no inherited documents
no cloned equipment
no cloned attributes
no partial metadata state
no activation change
```

must remain committed.

Do not commit inside the model clone helper.

The revision service owns the transaction.

---

# 26. Concurrency / locking

Reuse the existing project/revision lock ordering.

Do not invent a second concurrency model.

Revision creation already locks the project/base according to current behavior. Integrate model cloning under those locks.

The base revision's engineering model must be read consistently while cloning.

Test race behavior where appropriate, especially:

- a model mutation against the base cannot interleave into a half-snapshot clone;
- activation/archive/cancel behavior remains serialized;
- a clone sees either the before or after committed state, never a partial engineering write.

Prefer using the same revision row locking discipline that engineering mutations already use.

Do not introduce deadlock-prone inverse lock order.

---

# 27. Clone implementation location

Create a neutral model-copy helper/service in the engineering application/persistence boundary.

Reasonable examples:

```text
copy_active_engineering_model(...)
clone_revision_model(...)
```

Do not put engineering cloning into:

```text
revision_documents.py
document-processing
pure registry package
```

The helper may live alongside `EngineeringModelService` or in a small dedicated engineering inheritance module, based on repository conventions.

The helper must:

- accept source and target ProjectRevision;
- not commit;
- assume/verify the caller owns the transaction/locks;
- return cloned equipment count;
- preserve deterministic behavior.

---

# 28. Performance / implementation style

The model may contain hundreds or thousands of equipment/attribute rows.

Avoid an obviously N+1-heavy implementation when a straightforward bulk or eager-loaded approach is available.

Correctness is more important than premature optimization.

Acceptable:

- eager-load active equipment + attributes;
- deterministic Python mapping and bulk ORM insertion;
- SQL INSERT...SELECT only if semantics remain readable and registry-evolution handling is correct.

Do not optimize away registry checks.

Keep clone logic reviewable.

---

# 29. system metadata inheritance is not equipment provenance

Do not create:

```text
inherited_from_system_frequency_id
inherited_from_system_phase_count_id
```

There are no separate metadata entities.

The revision's:

```text
based_on_revision_id
```

plus resolved carry-forward semantics is sufficient provenance for these snapshot-level fields in Phase 5C.

Full audit history remains Phase 11.

---

# 30. No evidence fabrication

A revision-wide `system_frequency` or `system_phase_count` does not imply that every equipment item has an explicit sourced attribute.

Do not:

- set EquipmentAttribute origin;
- set EquipmentAttribute information_state;
- set confidence;
- create evidence links;
- mark attributes reviewed/verified

just because a system-wide metadata value exists.

Effective defaults and explicit equipment facts remain distinct.

---

# 31. Requirement evaluator interaction

Do not rewrite Phase 5A requirement rules in Phase 5C.

If an existing requirement evaluator takes only equipment attributes, leave its current behavior unless a tiny optional context bridge is clearly required.

System-level metadata may later be supplied as external context to validation/readiness logic where appropriate.

Do not silently make every missing `frequency` or `phase_count` attribute `PRESENT`.

---

# 32. Public HTTP scope

Phase 5C may extend the **existing revision create/get/update response/request schemas and routes** because those are required for:

```text
carry_forward_model
system_frequency
system_phase_count
inheritance count
```

Do not add the Phase 5E engineering-model CRUD API.

No new equipment/attribute public routes are required.

No frontend work is required in Phase 5C unless the existing revision-create UI is explicitly considered part of this subphase by the accepted Phase 5 spec.

See Section 33.

---

# 33. Revision-create UI boundary

The original Phase 5 plan placed the user-facing independent carry-forward controls in Phase 5F, while some earlier wording associated the option with 5C.

For Phase 5C:

- backend request/response semantics are mandatory;
- do not add broad Engineering Model frontend work;
- if the repository's current phase plan explicitly assigns the revision-create checkbox to 5C, implement only the minimal revision-create UI change;
- otherwise defer the UI checkbox to 5F and document the backend field now.

Do not let a small checkbox pull Phase 5F into scope.

If you defer UI, state it explicitly in the handoff.

---

# 34. Error behavior

Add explicit domain/service errors where useful, for example:

```text
ModelInheritanceConflict
InvalidSystemFrequency
InvalidSystemPhaseCount
```

Names may follow repository conventions.

Use `InvalidBaseRevision` for:

```text
carry_forward_model=true with no base
```

unless a more precise existing inheritance error is standard.

Do not expose raw SQL errors.

Clone incompatibility errors must identify enough context for developers to understand the failing equipment/attribute, but do not leak sensitive document content.

---

# 35. Revision response behavior

Revision list/get/create responses should include:

```text
system_frequency
system_phase_count
```

Create response additionally includes:

```text
inherited_document_count
inherited_model_equipment_count
```

List/get should not invent inheritance counts after the fact unless repository conventions already persist them.

Do not add a stored count column solely for response convenience.

---

# 36. Update revision mutation behavior carefully

Existing `RevisionUpdate` currently supports metadata such as identifier/description.

Add the two model metadata fields without weakening lifecycle safety.

Because engineering metadata is part of the model snapshot:

```text
system_frequency
system_phase_count
```

must be rejected on SUPERSEDED revisions and archived/cancelled projects.

If existing identifier/description behavior on superseded revisions differs, do not broaden that behavior to these new engineering fields.

Use shared revision-write guards.

If needed, separate general revision metadata update semantics internally while preserving existing external behavior.

Avoid unrelated lifecycle refactors.

---

# 37. Tests — migration

Add migration coverage for 0008.

At minimum:

1. fresh upgrade through head;
2. upgrade from 0007 with existing engineering rows;
3. existing equipment/attributes preserved exactly;
4. new revision metadata columns exist;
5. existing revisions get NULL values;
6. positive frequency accepted;
7. zero/negative frequency rejected;
8. phase count 1 accepted;
9. phase count 3 accepted;
10. other non-null phase counts rejected;
11. downgrade to 0007 succeeds;
12. re-upgrade succeeds.

---

# 38. Tests — carry_forward_model resolution

Test:

## Base exists

```text
omitted -> true
null -> true
true -> true
false -> false
```

## No base

```text
omitted -> false
null -> false
false -> false
true -> reject
```

Test independence from `carry_forward_documents`.

At minimum all four base-present combinations:

```text
docs T / model T
docs T / model F
docs F / model T
docs F / model F
```

---

# 39. Tests — metadata create/inheritance semantics

Test independently for both metadata fields.

## Base with values

With:

```text
base.system_frequency = 60
base.system_phase_count = 3
```

and model carry-forward true:

- omitted destination fields inherit;
- explicit values override;
- explicit null clears;
- document carry-forward has no effect.

With model carry-forward false:

- omitted destination fields become null;
- explicit destination values still apply.

## No base

- omitted -> null;
- explicit values -> stored;
- explicit null -> null.

Use `Decimal` equality for frequency.

---

# 40. Tests — model clone

Test:

- only ACTIVE Equipment cloned;
- REMOVED Equipment excluded;
- same `lineage_id`;
- new Equipment IDs;
- `inherited_from_equipment_id` points to actual base equipment;
- same type/tag/name/description;
- origin preserved;
- verification preserved;
- attributes receive new IDs;
- `inherited_from_attribute_id` points to actual base attribute;
- information state preserved;
- verification state preserved;
- origin preserved;
- confidence preserved;
- canonical typed values preserved exactly;
- canonical units preserved;
- canonical value_type preserved;
- destination count correct.

Use representative equipment with:

```text
NUMBER
INTEGER
TEXT
ENUM
BOOLEAN
non-PRESENT states
confidence
```

where current service/state semantics allow those source rows.

---

# 41. Tests — independent snapshots

After clone:

- mutate destination tag/value -> source unchanged;
- mutate source on a still-writable source revision where lifecycle permits -> destination unchanged;
- removing/restoring destination does not affect source;
- row IDs differ;
- lineage IDs match.

---

# 42. Tests — registry evolution

Simulate or fixture registry/source mismatch without modifying registry-v1 permanently.

Test:

1. destination registry has a new attribute absent from source:
   - destination materializes NOT_EXTRACTED / UNVERIFIED;
   - no inherited_from pointer;
   - source untouched.

2. old-only untouched source attribute:
   - may be omitted safely.

3. old-only meaningful source attribute:
   - clone rejected.

4. same key but incompatible value type:
   - meaningful -> reject.

5. same key but incompatible canonical unit:
   - meaningful -> reject.

6. PRESENT ENUM value no longer valid:
   - reject.

7. clone failure rolls back entire revision creation.

Use dependency injection/test monkeypatching around registry lookup only if current package design supports it cleanly. Do not weaken production registry immutability.

---

# 43. Tests — metadata effective values

Add pure/helper tests if an effective-value helper is implemented.

Test:

```text
explicit equipment value wins
otherwise revision default used
otherwise None/unspecified
```

Test mismatches are detectable:

```text
60 Hz system / 50 Hz equipment
3-phase system / 1-phase equipment
```

Do not persist findings.

---

# 44. Tests — transaction rollback

Inject failures at several points:

```text
after revision insert
after document inheritance
during model equipment clone
during attribute clone
during metadata processing
before activation
```

Confirm rollback leaves:

```text
no target revision
no inherited documents
no cloned equipment
no cloned attributes
original active revision status unchanged
```

Use existing fault-injection/testing patterns where available.

---

# 45. Tests — concurrency

Add targeted integration coverage for snapshot consistency.

At minimum prove:

- revision creation/model clone and engineering mutation serialize consistently on the base revision;
- no partial base write is cloned;
- archive/cancel/activation behavior remains safe;
- lock order does not invert current project -> revision discipline.

Do not overbuild concurrency infrastructure beyond what the repository already uses.

---

# 46. Regression tests

Run:

```text
Phase 5A tests
Phase 5B tests
project/revision tests
document carry-forward tests
migration tests
engineering concurrency tests
full Python regression
live integration suite against disposable DB
ruff
format checks
pip check
git diff --check
```

If frontend is unchanged, frontend checks are optional under current repository convention.

If revision-create UI is changed, run:

```text
npm run lint
npm test
npx tsc --noEmit
npm run build
```

---

# 47. Documentation updates

Update:

```text
docs/ENGINEERING_MODEL.md
docs/PROJECT_STATUS.md
docs/ARCHITECTURE.md
```

Update `docs/ROADMAP.md` if it exists.

Create:

```text
docs/PHASE5C_HANDOFF.md
```

The handoff must include:

- baseline branch/commit;
- migration revision;
- fields added to ProjectRevision;
- carry_forward_model resolution rules;
- metadata inheritance/override/null semantics;
- clone algorithm;
- registry-evolution behavior;
- transaction boundary;
- locking behavior;
- test results;
- deviations/concerns;
- explicit confirmation Phase 5D has not begun.

Do not rewrite historical Phase 5A/5B handoffs.

---

# 48. Phase 5C non-goals

Explicitly do not add:

```text
model_nodes
model_connections
topology migration
terminal registry
connection cloning
equipment API router
attribute API router
Engineering Model workspace
graph visualization
Evidence
ExtractionCandidate
AI extraction
reconciliation
persistent readiness findings
ProtectionFunction
study scenarios
ETAP/SKM/EasyPower
```

Do not add `parent_equipment_id`.

Do not modify registry-v1.

---

# 49. Completion criteria

Phase 5C is complete only when:

- Phase 5A/5B behavior remains intact;
- `system_frequency` exists on ProjectRevision as nullable canonical-Hz Decimal/NUMERIC;
- `system_phase_count` exists on ProjectRevision as nullable 1/3 integer;
- metadata DB constraints are enforced;
- `carry_forward_model` exists and is independent of document carry-forward;
- carry-forward defaults true with a base and false without one;
- true without a base is rejected;
- revision metadata inheritance follows omitted/explicit/explicit-null semantics;
- only ACTIVE equipment is cloned;
- removed equipment is excluded;
- new snapshot IDs are generated;
- equipment lineage is preserved;
- inherited_from equipment pointers reference the actual selected base revision;
- attributes are cloned with new IDs and correct source pointers;
- canonical values/states/origin/verification/confidence are preserved;
- registry-evolution destination attributes materialize safely;
- meaningful incompatible source data is never silently dropped;
- clone failure rolls back the entire revision creation transaction;
- source/destination snapshots are independent;
- model-level metadata does not mutate/materialize equipment attributes;
- effective model metadata mismatches are deterministically detectable;
- no Phase 5D+ functionality is introduced;
- full relevant regression passes.

---

# 50. End-of-task report

At the end, do **not** proceed to Phase 5D.

Report:

1. branch/base used;
2. files changed;
3. migration revision;
4. ProjectRevision metadata fields/constraints;
5. carry_forward_model rules;
6. metadata omitted/explicit/explicit-null semantics;
7. model clone algorithm;
8. lineage behavior;
9. inherited_from semantics;
10. registry-evolution behavior;
11. removed-equipment behavior;
12. transaction/rollback behavior;
13. lock/concurrency behavior;
14. effective metadata behavior;
15. tests added;
16. exact commands/results;
17. any deviations/technical debt;
18. whether revision-create UI was changed or deferred;
19. confirmation no topology/API/frontend/extraction work leaked into scope.

If every acceptance criterion passes, state exactly:

```text
Phase 5C implementation is complete and ready for review.
```

Do not begin Phase 5D until instructed.
