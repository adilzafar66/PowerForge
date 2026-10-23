# PowerForge Phase 5A — Registry, Units, and Requirement Engine

You are implementing **Phase 5A only** of PowerForge.

Do **not** proceed to Phase 5B or implement engineering-model persistence, revision inheritance, topology persistence, or the Engineering Model frontend.

## Authoritative inputs

Before making any changes, read and understand these repository files:

```text
docs/specs/phase-5-engineering-model.md
docs/specs/registry/PowerForge_registry-v1_reference.json
```

If present, the reviewed engineering workbook may also be used for human-readable context:

```text
docs/specs/registry/PowerForge_Phase5_Equipment_Attribute_registry-v1.xlsx
```

Source-of-truth hierarchy:

1. `phase-5-engineering-model.md` is authoritative for architecture and behavior.
2. `PowerForge_registry-v1_reference.json` is authoritative for the exact `registry-v1` taxonomy, attributes, Required/Critical flags, units, enum values, ordering, and requirement-rule snapshot.
3. The XLSX is supporting engineering documentation only.
4. **Do not parse or depend on the XLSX at application runtime.**

If the specification materially conflicts with the existing repository architecture, do not silently weaken the specification. Explain the conflict before making a major architectural deviation.

---

# 1. First inspect the repository

Before editing code:

1. Inspect the monorepo/package structure.
2. Identify:
   - existing shared Python/domain packages;
   - FastAPI router/service conventions;
   - Pydantic model conventions;
   - test structure;
   - existing enum/value-object patterns;
   - shared configuration patterns;
   - frontend/API client conventions only insofar as needed for the registry endpoint;
   - where neutral shared domain code belongs.
3. Read the existing architecture/ADR documents relevant to:
   - project revisions;
   - document processing;
   - engineering model;
   - topology;
   - validation.
4. Check whether a placeholder engineering-model package already exists.

Then implement Phase 5A using existing conventions wherever possible.

Do not reorganize unrelated parts of the repository.

---

# 2. Phase 5A goal

Implement the complete **pure-domain canonical equipment registry foundation** for Phase 5.

Phase 5A must deliver:

```text
Equipment taxonomy
Attribute definitions
Registry definitions
Unit families/conversion
Conditional requirement rules
Requirement evaluation
Registry self-validation
Registry snapshot validation
Read-only registry API
Tests
```

There must be **no database dependency in the registry/domain layer**.

The registry must not depend on:

```text
SQLAlchemy
Alembic
Celery
Redis
AI providers
document processing
OpenAI
HTTP
frontend code
```

The API layer may import the registry to expose it, but the registry itself must remain pure domain code.

---

# 3. Canonical equipment taxonomy

`registry-v1` contains exactly **20 equipment types**.

The persisted/machine-facing canonical keys are:

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

Do not introduce aliases as additional canonical equipment types.

In particular, do not add:

```text
GENERATOR
TRANSFORMER
BREAKER
RELAY
LOAD
SWITCH
PANEL
SWITCHGEAR
SWITCHBOARD
PANELBOARD
MCC
DISCONNECT
```

as canonical equipment types.

Important modeling decisions:

- `SWITCHGEAR`, `SWITCHBOARD`, `PANELBOARD`, and `MCC` are represented by `BUS` with `bus_type`.
- A fused disconnect is modeled using:
  - `SINGLE_THROW_SWITCH`
  - plus associated `FUSE` equipment.
- There is no canonical `DISCONNECT` equipment type.
- `JUNCTION_BOX` may exist as a BUS subtype.
- A purely electrical junction is topology, not equipment.

Use stable machine identifiers. Human-readable labels can be separate metadata.

---

# 4. Registry domain model

Implement typed domain objects equivalent to the following concepts.

Exact class/module names should follow repository conventions.

## 4.1 EquipmentDefinition

Conceptually:

```python
EquipmentDefinition(
    key=...,
    display_name=...,
    attributes=(...),
    requirements=(...),
)
```

It must expose:

- canonical equipment key;
- display name;
- deterministic ordered attributes;
- applicable RequirementRules.

---

## 4.2 AttributeDefinition

Conceptually:

```python
AttributeDefinition(
    key="rated_voltage",
    display_name="Rated Voltage",
    value_type=AttributeValueType.NUMBER,
    canonical_unit="kV",
    required=True,
    critical=True,
    allowed_values=(),
    notes=None,
    display_order=0,
)
```

Required fields:

```text
key
display_name
value_type
canonical_unit
required
critical
allowed_values
notes
display_order
```

Supported Phase 5 value types:

```text
NUMBER
INTEGER
TEXT
BOOLEAN
ENUM
```

Rules:

- `ENUM` must define allowed values.
- ENUM values are canonical stable strings.
- canonical attribute keys must match:

```regex
^[a-z][a-z0-9_]*$
```

- Attribute keys must describe engineering quantities rather than encode their units.
- Unitless attributes use `canonical_unit = null`.
- Attribute ordering must be deterministic and match `registry-v1`.

Do not simplify or redesign the attributes in the JSON reference.

---

# 5. Required and Critical semantics

These meanings are normative.

## Required

```text
The specific attribute is unconditionally required for a minimally useful
canonical representation of the equipment type.
```

`required=True` must **not** be interpreted as a future database `NOT NULL`.

Incomplete equipment is intentionally representable.

## Critical

```text
Missing or incorrect information can materially prevent, invalidate,
or significantly affect at least one intended PowerForge engineering
study/model.
```

An attribute can therefore correctly be:

```text
required = False
critical = True
```

Do not infer Critical from Required or vice versa.

Use the exact reviewed values from `PowerForge_registry-v1_reference.json`.

---

# 6. Unit system

Implement a deliberately small deterministic engineering unit-conversion layer.

Do not introduce a heavyweight external unit framework unless the repository already has an appropriate dependency and there is a strong reason to reuse it.

## 6.1 Unit-family principle

A **Unit Family** defines compatible units.

An **AttributeDefinition** owns its canonical storage unit.

The family default does not override the attribute-level canonical unit.

For example, these are valid:

```text
electrode_gap
canonical unit = mm

trip_output_operating_time
canonical unit = ms

rated_burden
canonical unit = VA

rated_apparent_power
canonical unit = kVA
```

even though their unit-family defaults may be different.

---

## 6.2 Unit families

Implement the unit families exactly from the registry reference.

They include at least:

```text
Voltage
Current
Fault current
Apparent power
Active power
Reactive power
Resistance / Reactance / Impedance
Impedance per length
Length
Time
Frequency
Speed
Capacitance
Inductance
Percentage
Temperature
Per unit
```

The JSON reference contains the exact default/supported units.

---

## 6.3 Conversion behavior

Provide a pure function/service conceptually similar to:

```python
normalize_value(
    value,
    input_unit,
    canonical_unit,
    *,
    semantic_context=None,
)
```

or another clean typed equivalent.

Requirements:

- deterministic conversions;
- Decimal-safe behavior for engineering numeric values;
- reject incompatible dimensions;
- reject unsupported units;
- preserve integers where appropriate when no unit conversion changes their semantic type;
- handle affine temperature conversion correctly;
- treat `%` and `p.u.` as different quantities unless a specific definition explicitly permits conversion;
- do not universally allow `hp` → `kW`.

`hp` → `kW` is allowed only where semantically appropriate, such as motor/VFD active-power ratings.

Do not invent derived engineering calculations beyond unit conversion.

---

# 7. Requirement-rule engine

Implement the requirement rules in `registry-v1` as first-class typed domain definitions.

Supported rule types:

```text
ANY_OF
ALL_OF
REQUIRED_IF
ALL_OR_NONE
```

## 7.1 Semantics

### ANY_OF

At least one complete alternative must be satisfied.

Example:

```text
UTILITY_SOURCE fault definition:

Alternative A:
three_phase_fault_current
slg_fault_current
three_phase_x_r
slg_x_r

OR

Alternative B:
positive_sequence_resistance
positive_sequence_reactance
zero_sequence_resistance
zero_sequence_reactance
```

### ALL_OF

When the rule applies, every listed attribute is required.

### REQUIRED_IF

The listed attributes become required when the typed condition evaluates true.

### ALL_OR_NONE

If any listed attribute is populated, all members must be populated.

---

# 8. Requirement conditions

Do **not** parse the human-readable English condition strings at runtime.

Implement typed conditions.

Phase 5A needs a small condition vocabulary equivalent to:

```text
ALWAYS
ATTRIBUTE_EQUALS
ATTRIBUTE_IN
ANY_PRESENT
EXTERNAL_CONTEXT
```

Use whatever typed representation best fits the codebase.

Examples:

```python
AttributeEquals(
    attribute="grounding_configuration",
    value="RESISTANCE",
)
```

```python
AttributeIn(
    attribute="reactor_type",
    values={"SERIES", "CURRENT_LIMITING", "FILTER"},
)
```

```python
AnyPresent(
    attributes={
        "short_time_withstand_current",
        "short_time_withstand_duration",
    },
)
```

---

## 8.1 External-context requirements

Some registry conditions depend on engineering/modeling context that cannot be inferred solely from the canonical attribute set.

Examples include:

```text
generator reactance base differs from rated base

motor apparent-power basis is needed and is not otherwise imported/derived

VFD output-side short-circuit contribution is explicitly modeled

UPS inverter-mode short-circuit contribution is explicitly modeled
```

Represent these as:

```text
EXTERNAL_CONTEXT
```

or an equivalent typed construct.

If external context is not supplied, the evaluator must return:

```text
NOT_EVALUATED
```

It must not guess whether the condition applies.

---

# 9. Requirement evaluation

Implement a pure evaluator.

The evaluator must support statuses equivalent to:

```text
SATISFIED
UNSATISFIED
NOT_APPLICABLE
NOT_EVALUATED
```

Design the input so that Phase 5 persistence can later supply attribute states without coupling this package to ORM classes.

For example, use a simple protocol/value object representing:

```text
attribute_key
information_state
value
```

or a dictionary/value-provider interface.

Do not import the future `EquipmentAttribute` ORM class into the registry package.

---

## 9.1 Information-state semantics

The future canonical model will use:

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
NOT_EXTRACTED
CONFLICTING
```

Phase 5A may define the enum now because the requirement evaluator needs it.

For satisfying requirements:

```text
PRESENT
```

satisfies a required value.

These do not satisfy a required value:

```text
UNKNOWN
MISSING
NOT_EXTRACTED
CONFLICTING
```

`NOT_APPLICABLE` only satisfies the situation when the requirement itself does not apply.

The requirement engine must remain pure domain code.

Do not persist results.

---

# 10. Registry validation

Implement a validation routine that fails loudly during tests/startup if the registry is malformed.

Validate at minimum:

- exactly 20 equipment types;
- equipment keys unique;
- canonical equipment keys stable;
- attribute keys unique within each equipment type;
- attribute keys match the required naming regex;
- all value types valid;
- ENUM definitions have allowed values;
- all canonical units are recognized;
- requirement rules reference existing equipment types;
- requirement rules reference existing attributes;
- alternative/group definitions are internally valid;
- display order is deterministic;
- registry version is `registry-v1`.

The approved registry currently contains:

```text
20 equipment types
296 canonical attribute definitions
44 requirement-rule rows
```

Tests should lock these counts unless the authoritative registry reference changes.

---

# 11. Registry snapshot test

Add a strong regression test that compares the implemented typed registry against:

```text
docs/specs/registry/PowerForge_registry-v1_reference.json
```

The test should fail if code drifts from the approved registry.

The comparison should include at least:

```text
equipment keys
display names
attribute keys
display names
value types
canonical units
Required flags
Critical flags
allowed enum values
display order
requirement rules
unit-family metadata
```

Normalize only representation differences that are intentionally non-semantic.

Do not silently regenerate the approved JSON from code during the test. The committed JSON is the reference fixture.

---

# 12. Registry API

Implement the Phase 5 registry read endpoint:

```text
GET /api/engineering-model/registry
```

Follow existing FastAPI router/service/schema conventions.

The endpoint must expose enough data for the future frontend to dynamically generate equipment forms.

Response should include:

```text
registry_version
equipment_types
attributes
required
critical
allowed_values
canonical_unit
compatible/supported input units where applicable
requirement rules
unit families
```

The response should be deterministic.

Do not expose internal Python implementation details.

Do not create write endpoints for the registry.

Do not create database tables for the registry.

---

# 13. Important registry examples that must work

## 13.1 Utility Source

The requirement engine must correctly understand:

```text
FAULT CURRENT representation
OR
SEQUENCE IMPEDANCE representation
```

as `ANY_OF`.

The individual participating fields remain:

```text
Required = No
```

even though the group itself is required for a study-ready source.

---

## 13.2 Cable

A cable requires `length` plus either:

```text
conductor_material
conductor_size
core_count_per_cable
parallel_run_count
```

or:

```text
positive_sequence_resistance
positive_sequence_reactance
zero_sequence_resistance
zero_sequence_reactance
```

Do not mark all eight fields individually required.

---

## 13.3 Static Load

Support either:

```text
rated_apparent_power + power_factor
```

or:

```text
rated_active_power + rated_reactive_power
```

---

## 13.4 Lumped Load

`rated_active_power` is unconditionally required.

In addition, the accepted power representation requires either:

```text
rated_apparent_power
```

or:

```text
power_factor
```

according to the approved registry rule.

---

## 13.5 Reactor

Conditional behavior depends on `reactor_type`.

Examples:

```text
SHUNT
→ rated_reactive_power

SERIES / CURRENT_LIMITING / FILTER
→ positive_sequence_impedance
   OR
   rated_inductance

NEUTRAL_GROUNDING
→ neutral_grounding_impedance
```

Do not flatten these into unconditional Required flags.

---

## 13.6 LV Breaker

The canonical registry intentionally contains design attributes such as:

```text
trip_rating
long_time_pickup
```

Keep them.

Do not build the future structured protection-function model in Phase 5A.

---

# 14. Public-domain/package interfaces

Design Phase 5A so Phase 5B can later use clean interfaces similar to:

```python
get_equipment_definition(equipment_type)

get_attribute_definition(
    equipment_type,
    attribute_key,
)

list_equipment_definitions()

normalize_attribute_value(
    equipment_type,
    attribute_key,
    value,
    input_unit,
)

evaluate_requirements(
    equipment_type,
    attribute_values,
    external_context=None,
)
```

Exact names may differ.

The important requirement is that callers do not need to understand registry internals.

Prefer immutable definitions where practical.

---

# 15. Errors

Use typed/domain-specific errors consistent with repository conventions.

At minimum distinguish situations equivalent to:

```text
UnknownEquipmentType
UnknownAttribute
InvalidAttributeValue
InvalidEnumValue
UnknownUnit
IncompatibleUnit
InvalidRegistryDefinition
```

Do not leak generic dictionary `KeyError`/`ValueError` behavior through application boundaries if the repository has a normal domain-error pattern.

---

# 16. Tests required for Phase 5A

Add focused unit/integration tests.

At minimum test:

## Registry

- exactly 20 equipment types;
- exactly 296 attributes;
- unique equipment keys;
- unique attribute keys per type;
- valid naming;
- deterministic ordering;
- exact snapshot match to the registry JSON;
- representative enum definitions;
- Required/Critical values preserved.

## Units

Test representative conversions:

```text
V ↔ kV
A ↔ kA
VA ↔ kVA ↔ MVA
W ↔ kW ↔ MW
var ↔ kvar ↔ Mvar
mΩ ↔ Ω ↔ kΩ
Ω/m ↔ Ω/km
mm ↔ m ↔ ft
ms ↔ s
nF ↔ µF
µH ↔ mH ↔ H
°F ↔ °C
```

Test rejection of dimensionally incompatible conversions.

Test `%` and `p.u.` remain distinct.

Test context-sensitive horsepower handling.

## Requirement rules

Test at least:

```text
UTILITY_SOURCE ANY_OF
CABLE ANY_OF
STATIC_LOAD ANY_OF
LUMPED_LOAD ANY_OF
REACTOR REQUIRED_IF / ANY_OF
BUS ALL_OR_NONE
HV_BREAKER ALL_OR_NONE
UPS conditional rules
generator grounding REQUIRED_IF
transformer grounding REQUIRED_IF
EXTERNAL_CONTEXT → NOT_EVALUATED without context
```

## Registry API

Test:

```text
GET /api/engineering-model/registry
```

and verify response is deterministic and consistent with the domain registry.

Run all existing regression tests relevant to the changed packages/API.

---

# 17. Phase 5A non-goals

Do not implement any of the following in this task:

```text
EquipmentLineage ORM
Equipment ORM
EquipmentAttribute ORM
ModelNode ORM
ModelConnection ORM
Alembic engineering-model tables
revision model cloning
carry_forward_model
engineering-model CRUD APIs
equipment creation
attribute persistence
topology CRUD
Engineering Model frontend workspace
AI extraction
Evidence
ExtractionCandidate
entity resolution
reconciliation
validation findings tables
protection-function model
parent_equipment_id
React Flow
ETAP export
SKM export
EasyPower export
engineering calculations
```

If something is useful only for one of these future phases, do not build it now unless Phase 5A explicitly needs the abstraction.

---

# 18. Implementation quality requirements

- Use existing repository typing/linting/style conventions.
- Prefer explicit typed domain models over unstructured dictionaries.
- Avoid unnecessary abstractions.
- Avoid premature extensibility beyond the already-defined future needs.
- Avoid runtime reflection over the XLSX.
- Avoid duplicate registry definitions between API/frontend/backend.
- Keep the registry deterministic.
- Keep the domain layer independently unit-testable.
- Do not introduce hidden fallback behavior for unknown attributes/types.
- Do not silently accept invalid units or enum values.

---

# 19. Documentation

Update/create the minimum documentation needed so maintainers understand:

```text
registry-v1 ownership
unit semantics
Required vs Critical
conditional requirement behavior
EXTERNAL_CONTEXT behavior
registry API
```

If `ADR-007 — Canonical Engineering Model Persistence` has not yet been created, do **not** write the complete Phase 5 ADR in this task unless the repository workflow clearly expects it now.

You may add/update the Phase 5A-specific documentation needed to explain the implemented domain layer.

Do not rewrite unrelated documentation.

---

# 20. Completion criteria

Phase 5A is complete only when:

- the full approved `registry-v1` exists as typed version-controlled domain code;
- the implementation matches the committed registry JSON snapshot;
- all 20 equipment types are represented;
- all 296 attributes are represented;
- unit-family definitions and conversions work;
- Required/Critical metadata exactly matches the reference;
- requirement rules are typed and executable;
- external-context requirements do not guess;
- registry validation passes;
- `GET /api/engineering-model/registry` works;
- targeted Phase 5A tests pass;
- relevant existing regression tests pass;
- no Phase 5B+ persistence or UI functionality has been introduced.

---

# 21. At the end of the implementation

Do not proceed to Phase 5B.

Provide a concise implementation report containing:

1. files/modules created or changed;
2. architecture choices made to fit the existing repository;
3. registry validation result;
4. confirmation of:
   - 20 equipment types;
   - 296 attributes;
   - 44 requirement-rule rows;
5. unit-conversion functionality implemented;
6. requirement-engine functionality implemented;
7. API endpoint implemented;
8. tests added;
9. exact test/lint/typecheck commands run and their results;
10. any remaining concerns or technical debt;
11. any differences between the specification and repository reality.

If all acceptance criteria pass, explicitly state:

```text
Phase 5A implementation is complete and ready for review.
```

Do not begin Phase 5B until instructed.