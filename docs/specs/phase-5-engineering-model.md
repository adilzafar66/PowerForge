# PowerForge Phase 5 — Canonical Engineering Model Implementation Specification

**Status:** APPROVED FOR IMPLEMENTATION  
**Specification version:** 1.0  
**Registry version:** `registry-v1`  
**Date:** 2026-10-22  
**Audience:** Codex / PowerForge maintainers  
**Companion machine-readable registry:** `PowerForge_registry-v1_reference.json`  
**Human-reviewed registry source:** `PowerForge_Phase5_Equipment_Attribute_registry-v1.xlsx`

This specification must be read together with ADR-007: Canonical Engineering Model Persistence, which is authoritative for the underlying Phase 5 persistence architecture and architectural decisions.
---

> **Approved post-5G amendment:** [Phase 5 authoring refinement](../prompts/phase-5-refinement.md) supersedes this original specification for information-state vocabulary, automatic terminal profiles, unified transactional Equipment saving, and Node/Connection table UX. Current behavior is described in [ENGINEERING_MODEL.md](../ENGINEERING_MODEL.md) and [TOPOLOGY.md](../TOPOLOGY.md). Registry-v1 remains unchanged. The original phased specification below records the accepted baseline.

## 1. Purpose

Phase 5 introduces the first persistent, revision-scoped **canonical engineering model** in PowerForge.

The engineering model must be usable before any AI extraction exists. Engineers must be able to manually create equipment, enter canonical attributes, define simple topology, create a new project revision, and carry the model forward as an independent snapshot.

Phase 5 is the foundation on which later phases will add:

- document-to-model extraction;
- candidate/evidence provenance;
- entity resolution;
- SLD topology extraction;
- reconciliation;
- engineering validation;
- engineer verification workflows;
- visualization;
- ETAP/SKM/EasyPower export;
- engineering calculations and reports.

The core architectural principle remains:

> **Documents → Evidence → Extraction Candidates → Canonical Engineering Model → Engineer Verification**

Phase 5 implements the **Canonical Engineering Model** layer only. It must not prematurely implement the later layers.

---

## 2. Normative language and source-of-truth hierarchy

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

For Phase 5 implementation:

1. **This specification is authoritative for architecture, persistence behavior, lifecycle, APIs, inheritance, and implementation boundaries.**
2. **`PowerForge_registry-v1_reference.json` is authoritative for the exact Phase 5 equipment taxonomy, attribute metadata, enum choices, Required/Critical flags, unit metadata, display order, and requirement-rule snapshot.**
3. The reviewed XLSX remains the human engineering/design artifact and contains supporting notes and research references.
4. The application **MUST NOT parse or depend on the XLSX at runtime**.
5. The implementation registry **MUST be version controlled**. It may be expressed as typed Python definitions or another static code representation consistent with the repository, but it must validate against the companion `registry-v1` reference.
6. If the specification and registry reference appear to conflict, do not silently invent a resolution. Preserve the registry metadata and the architectural behavior in this spec, then surface the conflict for review.

Once Phase 5 is implemented and frozen, changes to canonical equipment types, canonical attribute keys, units, or requirement semantics require a deliberate registry version change and migration strategy.

---

## 3. Phase 5 goals

Phase 5 MUST deliver:

- a code-owned canonical registry for the approved equipment taxonomy;
- typed canonical equipment attributes;
- deterministic unit normalization;
- revision-scoped persistent equipment;
- stable physical equipment lineage across revisions;
- soft equipment lifecycle;
- manual engineering-model authoring;
- manual topology authoring using nodes/terminals and connections;
- independent engineering-model carry-forward when a new revision is created;
- revision-scoped APIs;
- a basic Engineering Model frontend workspace;
- audit timestamps/actors;
- comprehensive tests for registry, persistence, inheritance, topology, API ownership, and UI behavior.

The model MUST remain provider-neutral and analysis-software-neutral.

---

## 4. Explicit non-goals

Phase 5 MUST NOT implement:

- AI extraction;
- OCR;
- extraction candidates;
- Evidence tables or page/bounding-box provenance;
- entity resolution;
- AI-generated topology;
- SLD interpretation;
- reconciliation/conflict workflows;
- a persistent engineering validation findings engine;
- engineer verification/review queues;
- graphical one-line visualization or React Flow;
- ETAP, SKM, or EasyPower exporters;
- fault-current calculations;
- load-flow calculations;
- motor-starting calculations;
- coordination calculations;
- arc-flash calculations;
- report generation;
- a complete protection-function/settings subsystem;
- a full immutable audit/event history;
- a separate `EngineeringModel` aggregate/table.

### 4.1 Containment is deliberately deferred

The reviewed registry notes that equipment containment may eventually warrant `parent_equipment_id` (for example, a breaker physically belonging to a switchboard). That idea was not separately approved as a locked Phase 5 decision.

**Do not add `parent_equipment_id` in Phase 5.**

Electrical topology and physical containment remain separate concepts. Containment may be introduced later through an explicit design decision.

### 4.2 Protection settings are deliberately limited

`LV_BREAKER.trip_rating` and `LV_BREAKER.long_time_pickup` remain canonical equipment/design attributes because these values are commonly fixed design information found in shop drawings or one-lines.

Phase 5 MUST NOT create a general `ProtectionFunction` model. A later protection subsystem may separately represent study-adjusted settings/functions. When that exists, canonical design/nameplate values and study-setting values must remain distinguishable rather than overwriting one another.

---

## 5. Locked Phase 5 decisions

The implementation MUST preserve these decisions:

1. Engineering model carries forward to a new revision by default when a base revision exists.
2. Model carry-forward is independent of document carry-forward.
3. Physical equipment has stable lineage across revisions.
4. Canonical equipment taxonomy is richer than the old placeholder taxonomy.
5. Only registry-defined equipment types are canonical.
6. Equipment attributes are relational rows with typed values.
7. Attribute definitions are version controlled.
8. Canonical attribute keys are registry controlled; AI must never invent arbitrary canonical keys.
9. Values are normalized to attribute-defined canonical units.
10. Information state, verification state, and value origin are independent concepts.
11. Manual values default to `ENGINEER_REVIEWED`, not `ENGINEER_VERIFIED`.
12. Equipment uses soft lifecycle `ACTIVE` / `REMOVED`.
13. Duplicate equipment tags are allowed in Phase 5.
14. Topology is persisted in Phase 5, but authored manually.
15. Connections connect model nodes/terminals, never equipment directly.
16. Physical connections may be undirected; an optional nominal direction is allowed.
17. Full Evidence persistence is deferred to Phase 6; Phase 5 must be evidence-ready.
18. `ProjectRevision` is the model snapshot root; there is no `EngineeringModel` table.
19. Phase 5 supports manual model authoring.
20. Phase 5 includes a basic usable Engineering Model workspace, not a full visual editor.
21. Model APIs are revision scoped.
22. The approved `registry-v1` covers the initial equipment/attribute scope.
23. Revision inheritance performs full model snapshot cloning while preserving lineage.
24. Engineering-model writes obey the same project/revision mutability rules as document writes.
25. Basic created/updated/removed audit actors and timestamps are stored now; full audit history is deferred.

---

## 6. Canonical equipment taxonomy

The registry contains exactly **20 canonical equipment types** and **296 canonical attribute definitions**.

| Machine key | Display type | Attributes | Unconditional Required | Critical |
|---|---|---:|---:|---:|
| `UTILITY_SOURCE` | Utility Source | 11 | 2 | 10 |
| `SYNCHRONOUS_GENERATOR` | Synchronous Generator | 29 | 10 | 21 |
| `TWO_WINDING_TRANSFORMER` | 2-Winding Transformer | 23 | 7 | 17 |
| `BUS` | Bus | 20 | 3 | 15 |
| `LV_BREAKER` | LV Breaker | 16 | 6 | 13 |
| `HV_BREAKER` | HV Breaker | 16 | 2 | 10 |
| `RECLOSER` | Recloser | 14 | 5 | 11 |
| `OVERCURRENT_RELAY` | Overcurrent Relay | 7 | 2 | 6 |
| `FUSE` | Fuse | 9 | 3 | 7 |
| `SINGLE_THROW_SWITCH` | Single-Throw Switch | 8 | 1 | 5 |
| `DOUBLE_THROW_SWITCH` | Double-Throw Switch | 16 | 1 | 8 |
| `CABLE` | Cable | 14 | 1 | 10 |
| `CT` | CT | 6 | 2 | 2 |
| `INDUCTION_MOTOR` | Induction Motor | 20 | 2 | 15 |
| `STATIC_LOAD` | Static Load | 7 | 1 | 6 |
| `LUMPED_LOAD` | Lumped Load | 9 | 2 | 6 |
| `CAPACITOR` | Capacitor | 13 | 2 | 5 |
| `REACTOR` | Reactor | 19 | 2 | 15 |
| `VFD` | VFD | 16 | 4 | 10 |
| `UPS` | UPS | 23 | 5 | 18 |

### 6.1 Taxonomy rules

- Persist canonical equipment type as a stable registry key such as `SYNCHRONOUS_GENERATOR`.
- UI labels may use human-friendly names.
- Code enum/class names may be concise, but persisted keys MUST preserve the approved meaning and remain stable.
- Do not reintroduce generic `PANEL`, `LOAD`, `SWITCH`, `BREAKER`, or `GENERATOR` placeholders.
- `SWITCHGEAR`, `SWITCHBOARD`, `PANELBOARD`, and `MCC` are represented as `BUS`, with `bus_type` carrying the physical assembly classification.
- A physical `JUNCTION_BOX` is a `BUS` subtype. A pure electrical connectivity junction is a topology `ELECTRICAL_NODE`, not equipment.
- There is no canonical `DISCONNECT` type. A non-fused disconnect is represented by `SINGLE_THROW_SWITCH`; a fused disconnect is represented by `SINGLE_THROW_SWITCH` plus `FUSE`.
- `LV_BREAKER` and `HV_BREAKER` are distinct canonical types.
- `OVERCURRENT_RELAY`, `SYNCHRONOUS_GENERATOR`, `INDUCTION_MOTOR`, and `TWO_WINDING_TRANSFORMER` intentionally describe specific equipment classes rather than generic families.

---

## 7. Registry architecture

The registry MUST live in a pure domain layer with **no SQLAlchemy, HTTP, Celery, AI-provider, or frontend dependency**.

The exact package path should follow existing repository conventions. Logically it should contain:

```text
engineering_model/
    equipment_types
    attributes
    requirements
    units
    enums
    registry
```

Do not place engineering-model domain definitions in `document-processing` merely because that package currently exposes a shared persistence base. If persistence organization needs adjustment, make only the minimal neutral refactor necessary.

### 7.1 Core registry types

Implement equivalents of:

```python
class EquipmentDefinition:
    key: EquipmentType
    display_name: str
    attributes: tuple[AttributeDefinition, ...]
    requirements: tuple[RequirementRule, ...]

class AttributeDefinition:
    key: str
    display_name: str
    value_type: AttributeValueType
    canonical_unit: str | None
    required: bool
    critical: bool
    allowed_values: tuple[str, ...]
    notes: str | None
    display_order: int

class RequirementRule:
    rule_id: str
    rule_type: RequirementRuleType
    alternatives_or_attributes: ...
    condition: RequirementCondition
    engineering_rationale: str | None

class UnitFamilyDefinition:
    family: str
    default_unit: str
    supported_input_units: tuple[str, ...]
```

The exact class names may follow repository style, but the semantics MUST remain.

### 7.2 Registry invariants

At application/test startup the registry MUST validate:

- equipment keys are unique;
- attribute keys are unique within an equipment type;
- attribute keys match `^[a-z][a-z0-9_]*$`;
- canonical keys do not encode units merely as suffixes;
- `ENUM` attributes have at least one allowed value;
- non-`ENUM` attributes do not accidentally interpret enum choices as free-form values;
- every canonical unit is known to the unit registry;
- every requirement rule references an existing equipment type;
- every requirement-rule attribute exists on that equipment type;
- every requirement alternative is internally consistent;
- display order is deterministic;
- the registry version is exactly `registry-v1` for Phase 5.

A snapshot test MUST compare the implemented registry against `PowerForge_registry-v1_reference.json` so transcription drift is detected.

### 7.3 Value types

Supported Phase 5 canonical value types:

```text
NUMBER
INTEGER
TEXT
BOOLEAN
ENUM
```

`ENUM` is stored using the text value slot but validated against its definition.

### 7.4 Required vs Critical

These meanings are normative:

**Required**
> The specific attribute is unconditionally required for a minimally useful canonical representation of that equipment type.

**Critical**
> Missing or incorrect information can materially prevent, invalidate, or significantly affect at least one intended PowerForge study/model.

Therefore:

- `Required = Yes` does **not** imply database `NOT NULL`.
- `Critical = Yes` does **not** imply write rejection.
- A conditional attribute normally has `Required = No`, even when it is Critical.
- Requirement rules express conditional and alternative completeness.
- Incomplete equipment MUST be saveable because PowerForge needs to represent `UNKNOWN`, `MISSING`, `NOT_EXTRACTED`, and `CONFLICTING` states.

Required/Critical metadata will later drive validation, extraction prioritization, and engineer review. Phase 5 may expose completeness diagnostics, but MUST NOT create the Phase 10 persistent validation engine early.

---

## 8. Requirement-rule model

Supported rule types:

```text
ANY_OF
ALL_OF
REQUIRED_IF
ALL_OR_NONE
```

Semantics:

- **ANY_OF:** at least one complete alternative is satisfied.
- **ALL_OF:** every listed attribute is required when the condition applies.
- **REQUIRED_IF:** listed attributes are required only when the condition applies.
- **ALL_OR_NONE:** if any member of the group is populated, every member must be populated.

For completeness evaluation, an attribute satisfies a value requirement only when:

```text
information_state = PRESENT
```

`UNKNOWN`, `MISSING`, `NOT_EXTRACTED`, and `CONFLICTING` do not satisfy the requirement. `NOT_APPLICABLE` is acceptable only when the rule itself is not applicable.

### 8.1 Conditions

Do not parse the human-readable condition strings from the XLSX/JSON at runtime.

Represent conditions as typed code definitions. Phase 5 needs only a small vocabulary:

```text
ALWAYS
ATTRIBUTE_EQUALS
ATTRIBUTE_IN
ANY_PRESENT
EXTERNAL_CONTEXT
```

Rules that depend on engineering intent or source context rather than another canonical attribute MUST use `EXTERNAL_CONTEXT` and return a non-failing `NOT_EVALUATED` result unless that external context is explicitly supplied.

Examples that should be treated as external-context conditions in Phase 5 include:

- generator reactance base differs from rated base;
- motor apparent-power basis is needed and not otherwise imported/derived;
- VFD output short-circuit contribution is explicitly modeled;
- UPS inverter-mode short-circuit contribution is explicitly modeled and not otherwise inferred.

Requirement evaluation MUST be a pure domain function. Do not persist requirement findings in Phase 5.

### 8.2 Approved requirement-rule snapshot

| Equipment | Rule | Type | Alt | Attributes | Condition | Rationale |
|---|---|---|---|---|---|---|
| `UTILITY_SOURCE` | `UTILITY_FAULT_DATA` | `ANY_OF` | A | `three_phase_fault_current`, `slg_fault_current`, `three_phase_x_r`, `slg_x_r` | Always for a study-ready utility short-circuit source. | Direct fault-current + X/R representation. |
| `UTILITY_SOURCE` | `UTILITY_FAULT_DATA` | `ANY_OF` | B | `positive_sequence_resistance`, `positive_sequence_reactance`, `zero_sequence_resistance`, `zero_sequence_reactance` | Always for a study-ready utility short-circuit source. | Sequence-impedance representation. |
| `SYNCHRONOUS_GENERATOR` | `GEN_REACTANCE_BASE_POWER` | `REQUIRED_IF` | — | `reactance_base_power` | Per-unit reactances are stated on a base power different from rated_apparent_power. | Needed to convert per-unit reactances to the canonical machine base. |
| `SYNCHRONOUS_GENERATOR` | `GEN_REACTANCE_BASE_VOLTAGE` | `REQUIRED_IF` | — | `reactance_base_voltage` | Per-unit reactances are stated on a base voltage different from rated_voltage. | Needed to convert per-unit reactances to the canonical machine base. |
| `SYNCHRONOUS_GENERATOR` | `GEN_GROUNDING_RESISTANCE` | `REQUIRED_IF` | — | `grounding_resistance` | grounding_configuration = RESISTANCE | Resistance-grounded neutral requires the grounding resistance. |
| `SYNCHRONOUS_GENERATOR` | `GEN_GROUNDING_REACTANCE` | `REQUIRED_IF` | — | `grounding_reactance` | grounding_configuration = REACTANCE | Reactance-grounded neutral requires the grounding reactance. |
| `TWO_WINDING_TRANSFORMER` | `XFMR_PRIMARY_GROUND_R` | `REQUIRED_IF` | — | `primary_grounding_resistance` | primary_grounding_configuration = RESISTANCE | Primary neutral resistance is required when resistance grounded. |
| `TWO_WINDING_TRANSFORMER` | `XFMR_PRIMARY_GROUND_X` | `REQUIRED_IF` | — | `primary_grounding_reactance` | primary_grounding_configuration = REACTANCE | Primary neutral reactance is required when reactance grounded. |
| `TWO_WINDING_TRANSFORMER` | `XFMR_SECONDARY_GROUND_R` | `REQUIRED_IF` | — | `secondary_grounding_resistance` | secondary_grounding_configuration = RESISTANCE | Secondary neutral resistance is required when resistance grounded. |
| `TWO_WINDING_TRANSFORMER` | `XFMR_SECONDARY_GROUND_X` | `REQUIRED_IF` | — | `secondary_grounding_reactance` | secondary_grounding_configuration = REACTANCE | Secondary neutral reactance is required when reactance grounded. |
| `TWO_WINDING_TRANSFORMER` | `XFMR_INRUSH_POINT` | `ALL_OR_NONE` | — | `inrush_current_multiplier`, `inrush_current_duration` | A single-point inrush representation is supplied. | The multiplier and its duration describe one inrush point and should be supplied together. |
| `BUS` | `BUS_SHORT_TIME_PAIR` | `ALL_OR_NONE` | — | `short_time_withstand_current`, `short_time_withstand_duration` | Either short-time withstand field is supplied. | A short-time current rating is meaningful only with its duration. |
| `BUS` | `BUS_SERIES_RATING_ISOLATION` | `REQUIRED_IF` | — | `main_protective_device_isolated` | series_rating_applicable = TRUE | Series-rated equipment evaluation needs the upstream/main protective-device relationship. |
| `LV_BREAKER` | `LV_BREAKER_THERMAL_TRIP` | `REQUIRED_IF` | — | `trip_rating` | trip_unit_type = THERMAL_MAGNETIC | Thermal-magnetic breakers use the fixed trip rating as the long-time current basis. |
| `LV_BREAKER` | `LV_BREAKER_ELECTRONIC_TRIP` | `ALL_OF` | — | `sensor_rating`, `long_time_pickup`, `trip_unit_model` | trip_unit_type = ELECTRONIC | Electronic-trip modeling needs the sensor basis, long-time pickup, and trip-unit model. rating_plug remains conditional on designs that use one. |
| `HV_BREAKER` | `HV_BREAKER_SHORT_TIME_PAIR` | `ALL_OR_NONE` | — | `short_time_withstand_current`, `short_time_withstand_duration` | Either short-time withstand field is supplied. | A short-time current rating is meaningful only with its duration. |
| `RECLOSER` | `RECLOSER_SHORT_TIME_PAIR` | `ALL_OR_NONE` | — | `short_time_withstand_current`, `short_time_withstand_duration` | Either short-time withstand field is supplied. | A short-time current rating is meaningful only with its duration. |
| `SINGLE_THROW_SWITCH` | `SWITCH_SHORT_TIME_PAIR` | `ALL_OR_NONE` | — | `short_time_withstand_current`, `short_time_withstand_duration` | Either short-time withstand field is supplied. | A short-time current rating is meaningful only with its duration. |
| `DOUBLE_THROW_SWITCH` | `DTS_SHORT_TIME_PAIR` | `ALL_OR_NONE` | — | `short_time_withstand_current`, `short_time_withstand_duration` | Either short-time withstand field is supplied. | A short-time current rating is meaningful only with its duration. |
| `DOUBLE_THROW_SWITCH` | `DTS_WITHSTAND_CLOSING_PAIR` | `ALL_OR_NONE` | — | `withstand_closing_current_rating`, `withstand_closing_duration` | Either withstand-closing field is supplied. | Withstand/closing current must be associated with its applicable duration. |
| `CABLE` | `CABLE_ELECTRICAL_DEFINITION` | `ANY_OF` | A | `conductor_material`, `conductor_size`, `core_count_per_cable`, `parallel_run_count` | Always for a study-ready cable model, in addition to length. | Physical-construction representation from which impedance can be calculated/selected. |
| `CABLE` | `CABLE_ELECTRICAL_DEFINITION` | `ANY_OF` | B | `positive_sequence_resistance`, `positive_sequence_reactance`, `zero_sequence_resistance`, `zero_sequence_reactance` | Always for a study-ready cable model, in addition to length. | Direct sequence-impedance representation. |
| `INDUCTION_MOTOR` | `MOTOR_APPARENT_POWER_BASIS` | `ANY_OF` | A | `full_load_current` | Apparent-power base is needed and is not otherwise imported/derived. | Voltage + full-load current can establish the apparent-power base. |
| `INDUCTION_MOTOR` | `MOTOR_APPARENT_POWER_BASIS` | `ANY_OF` | B | `efficiency`, `power_factor` | Apparent-power base is needed and is not otherwise imported/derived. | Rated active power + efficiency + power factor can establish the apparent-power base. |
| `STATIC_LOAD` | `STATIC_LOAD_POWER_DEFINITION` | `ANY_OF` | A | `rated_apparent_power`, `power_factor` | Always for a study-ready static load. | Apparent-power + PF representation. |
| `STATIC_LOAD` | `STATIC_LOAD_POWER_DEFINITION` | `ANY_OF` | B | `rated_active_power`, `rated_reactive_power` | Always for a study-ready static load. | Active/reactive-power representation. |
| `LUMPED_LOAD` | `LUMPED_LOAD_POWER_DEFINITION` | `ANY_OF` | A | `rated_apparent_power` | Always, in addition to the required rated_active_power. | Rated active + apparent power determines PF/reactive power. |
| `LUMPED_LOAD` | `LUMPED_LOAD_POWER_DEFINITION` | `ANY_OF` | B | `power_factor` | Always, in addition to the required rated_active_power. | Rated active power + PF determines apparent/reactive power. |
| `CAPACITOR` | `CAPACITOR_WYE_GROUNDING` | `REQUIRED_IF` | — | `neutral_grounding_type` | connection_type = WYE | A wye-connected bank must identify whether the neutral is solidly grounded, ungrounded, or otherwise not grounded. |
| `REACTOR` | `REACTOR_SHUNT_RATING` | `REQUIRED_IF` | — | `rated_reactive_power` | reactor_type = SHUNT | Shunt reactors are conventionally specified by reactive-power rating at rated voltage. |
| `REACTOR` | `REACTOR_SERIES_IMPEDANCE` | `ANY_OF` | A | `positive_sequence_impedance` | reactor_type IN {SERIES, CURRENT_LIMITING, FILTER} | Direct impedance representation. |
| `REACTOR` | `REACTOR_SERIES_IMPEDANCE` | `ANY_OF` | B | `rated_inductance` | reactor_type IN {SERIES, CURRENT_LIMITING, FILTER} | Inductance representation; impedance is frequency-dependent and can be derived when frequency is known. |
| `REACTOR` | `REACTOR_NEUTRAL_GROUNDING` | `REQUIRED_IF` | — | `neutral_grounding_impedance` | reactor_type = NEUTRAL_GROUNDING | Neutral-grounding reactors are defined by the grounding impedance. |
| `REACTOR` | `REACTOR_CONNECTION` | `REQUIRED_IF` | — | `connection_type` | reactor_type IN {SHUNT, FILTER} | Connection affects network and zero-sequence behavior. |
| `REACTOR` | `REACTOR_SHORT_TIME_PAIR` | `ALL_OR_NONE` | — | `short_time_withstand_current`, `short_time_withstand_duration` | Either short-time withstand field is supplied. | A short-time current rating is meaningful only with its duration. |
| `VFD` | `VFD_OUTPUT_FAULT_DEFINITION` | `ANY_OF` | A | `output_short_circuit_current` | Output-side VFD short-circuit contribution is explicitly modeled. | Direct output fault-current representation. |
| `VFD` | `VFD_OUTPUT_FAULT_DEFINITION` | `ANY_OF` | B | `output_short_circuit_current_multiplier` | Output-side VFD short-circuit contribution is explicitly modeled. | Multiplier representation when vendor data is expressed relative to rated output current. |
| `UPS` | `UPS_STATIC_BYPASS_INPUT` | `REQUIRED_IF` | — | `separate_bypass_input` | static_bypass_available = TRUE | Defines whether the bypass shares the rectifier input or has a separate source. |
| `UPS` | `UPS_STATIC_BYPASS_RATING` | `ALL_OF` | — | `rated_bypass_current`, `bypass_short_circuit_current_rating` | static_bypass_available = TRUE | Bypass-mode load capacity and short-circuit withstand/rating are needed when the bypass path exists. |
| `UPS` | `UPS_BYPASS_SHORT_TIME_PAIR` | `ALL_OR_NONE` | — | `bypass_short_time_withstand_current`, `bypass_short_time_withstand_duration` | Either bypass short-time withstand field is supplied. | A bypass short-time current rating is meaningful only with its duration. |
| `UPS` | `UPS_INVERTER_FAULT_CURRENT` | `REQUIRED_IF` | — | `output_short_circuit_current` | UPS inverter-mode short-circuit contribution is explicitly modeled and cannot be inferred from manufacturer/model data. | Needed to represent current-limited inverter contribution. |
| `OVERCURRENT_RELAY` | `NONE` | `NONE` | — | — | No equipment-configuration conditional requirements identified in registry-v1. | Individual Required? flags apply directly. |
| `FUSE` | `NONE` | `NONE` | — | — | No equipment-configuration conditional requirements identified in registry-v1. | Individual Required? flags apply directly. |
| `CT` | `NONE` | `NONE` | — | — | No equipment-configuration conditional requirements identified in registry-v1. | Individual Required? flags apply directly. |

`NONE` rows indicate that the equipment type has no configuration-dependent conditional group in `registry-v1`; its individual Required flags apply directly.

---

## 9. Unit normalization

Each **attribute definition owns its canonical storage unit**.

Unit families define compatibility and supported conversion inputs; a unit-family default does not override the attribute's canonical unit.

| Family | Default | Supported inputs | Notes |
|---|---|---|---|
| Voltage | `kV` | `V`, `kV`, `MV` | Attribute definition owns the canonical storage unit; this is only the family default. |
| Current | `A` | `A`, `kA` | Attribute definition owns the canonical storage unit; this is only the family default. |
| Fault current | `kA` | `A`, `kA` | Attribute definition owns the canonical storage unit; this is only the family default. |
| Apparent power | `kVA` | `VA`, `kVA`, `MVA` | VA is valid as an attribute canonical unit (e.g. CT/relay burden). |
| Active power | `kW` | `W`, `kW`, `MW`, `hp` | hp conversion is allowed only where semantically appropriate. |
| Reactive power | `kvar` | `var`, `kvar`, `Mvar` |  |
| Resistance / Reactance / Impedance | `Ω` | `mΩ`, `Ω`, `kΩ` |  |
| Impedance per length | `Ω/km` | `Ω/m`, `Ω/km`, `Ω/1000 ft` |  |
| Length | `m` | `mm`, `cm`, `m`, `km`, `in`, `ft` | An attribute may canonically store mm (e.g. electrode gap/enclosure dimensions). |
| Time | `s` | `ms`, `s` | An attribute may canonically store ms (e.g. trip/output operating time). |
| Frequency | `Hz` | `Hz` |  |
| Speed | `rpm` | `rpm` |  |
| Capacitance | `µF` | `nF`, `µF`, `mF` |  |
| Inductance | `mH` | `µH`, `mH`, `H` |  |
| Percentage | `%` | `%` |  |
| Temperature | `°C` | `°C`, `°F` |  |
| Per unit | `p.u.` | `p.u.` | Dimensionless per-unit quantity; base quantities are carried separately when needed. |

### 9.1 Rules

- Canonical numeric values MUST be stored in the attribute's canonical unit.
- API callers MAY submit any permitted compatible input unit.
- Server-side normalization is authoritative.
- Use decimal-safe arithmetic for stored numeric engineering values; do not rely on binary floating point as the persistence representation.
- Do not persist calculated engineering quantities merely because they can be derived.
- Raw source values/units from future document extraction belong in Evidence/Candidate provenance in later phases, not in Phase 5 canonical rows.
- `%` and `p.u.` MUST NOT be treated as interchangeable unless a specific attribute definition explicitly permits it.
- `hp` → `kW` is permitted only where semantically appropriate (for example motor/VFD active-power rating), not as a universal conversion for every active-power attribute.
- Affine conversions such as °F ↔ °C must be explicit and deterministic.

The frontend may offer unit selectors, but the backend MUST independently validate and normalize the submitted unit.

---

## 10. Domain state enums

### 10.1 InformationState

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
NOT_EXTRACTED
CONFLICTING
```

Meaning:

- `PRESENT`: canonical value exists.
- `UNKNOWN`: the information is explicitly unknown.
- `MISSING`: expected information is known to be missing from the available source/model context.
- `NOT_APPLICABLE`: the attribute does not apply to this equipment/configuration.
- `NOT_EXTRACTED`: no extraction/manual determination has populated the attribute yet.
- `CONFLICTING`: multiple sources/inputs disagree; canonical resolution is pending.

### 10.2 VerificationState

```text
UNVERIFIED
AI_EXTRACTED
SYSTEM_VALIDATED
ENGINEER_REVIEWED
ENGINEER_VERIFIED
```

Phase 5 manual editing defaults to `ENGINEER_REVIEWED`. The UI MUST NOT expose a general "Mark Verified" workflow in Phase 5.

### 10.3 ValueOrigin

```text
MANUAL
AI_EXTRACTION
INFERRED
IMPORTED
```

`origin` MAY be null for a materialized attribute row that remains untouched in `NOT_EXTRACTED`.

### 10.4 LifecycleStatus

```text
ACTIVE
REMOVED
```

Use this for Equipment, ModelNode, and ModelConnection.

### 10.5 Topology enums

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

---

## 11. Persistence model

`ProjectRevision` remains the aggregate/snapshot root. **Do not create an `engineering_models` table.**

Add these Phase 5 entities:

```text
equipment_lineages
equipment
equipment_attributes
model_nodes
model_connections
```

Use repository-standard ID, UUID, timestamp, actor, FK, naming, and migration conventions.

### 11.1 EquipmentLineage

Purpose: stable physical identity for an equipment item across project revisions.

Required logical fields:

```text
id
project_id
created_at
created_by
```

Rules:

- lineage belongs to exactly one project;
- lineage does not contain revision-varying tag/type/rating data;
- a new manually created equipment item creates a new lineage;
- cloning a model into a descendant revision preserves the same lineage ID;
- Phase 5 does not attempt automatic lineage/entity matching for reintroduced equipment.

### 11.2 Equipment

Required logical fields:

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

Rules:

- `equipment_type` MUST be stored as stable text validated against the registry, not a PostgreSQL enum that requires a DB enum migration for every future registry addition.
- `tag` is nullable and indexed, but NOT unique.
- enforce unique `(revision_id, lineage_id)`;
- equipment, revision, lineage, and project ownership MUST agree;
- manual creation defaults to `origin=MANUAL`, `verification_state=ENGINEER_REVIEWED`, `lifecycle_status=ACTIVE`;
- soft removal retains equipment and all attributes;
- no hard-delete public API.

### 11.3 EquipmentAttribute

Required logical fields:

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

Rules:

- unique `(equipment_id, attribute_key)`;
- the key MUST exist for the equipment's current registry type;
- `value_type` MUST equal the registry definition;
- NUMBER uses `numeric_value`;
- INTEGER uses `integer_value`;
- TEXT and ENUM use `text_value`;
- BOOLEAN uses `boolean_value`;
- when `information_state=PRESENT`, exactly one compatible typed value slot MUST be populated;
- when `information_state!=PRESENT`, all typed value slots MUST be null;
- enum values MUST match approved allowed values exactly;
- numeric rows with units store the canonical unit declared by the attribute definition;
- unitless attributes store no unit;
- `confidence`, when supplied, is bounded to `[0, 1]`;
- manual values/states use `origin=MANUAL`, `verification_state=ENGINEER_REVIEWED`, `confidence=NULL`;
- untouched materialized rows use `information_state=NOT_EXTRACTED`, `verification_state=UNVERIFIED`, `origin=NULL`, `confidence=NULL`.

### 11.4 Attribute materialization

When new equipment is created, create one `EquipmentAttribute` row for **every attribute applicable to that equipment type**, in registry display order, initialized as `NOT_EXTRACTED`.

This is intentional. It distinguishes:

- "this canonical attribute exists but has not been populated" from
- "this key is not part of the equipment registry."

Do not use absent rows as the normal representation of an unpopulated canonical attribute.

### 11.5 ModelNode

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

Rules:

For `EQUIPMENT_TERMINAL`:

```text
equipment_id != NULL
terminal_key != NULL
```

For `ELECTRICAL_NODE`:

```text
equipment_id = NULL
terminal_key = NULL
```

Additional rules:

- terminal keys are flexible strings in Phase 5; there is no terminal-definition registry yet;
- terminal keys are unique within an equipment snapshot;
- an equipment terminal must belong to equipment in the same project/revision;
- pure connectivity/junction points are `ELECTRICAL_NODE`;
- no automatic AI or document-derived terminal creation.

### 11.6 ModelConnection

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

Rules:

- endpoints MUST belong to the same project and revision as the connection;
- self-loop connections are rejected;
- parallel edges are allowed;
- `direction=UNDIRECTED` is valid and expected for ordinary physical electrical connectivity;
- `NOMINAL_FROM_TO` is descriptive, not a power-flow calculation result;
- `phase_configuration` may remain an optional text field in Phase 5; do not create a large phase-topology subsystem early;
- nominal voltage, when supplied, is normalized to canonical `kV`;
- a `CABLE` is equipment, not a connection kind. Connect cable terminal nodes to neighboring topology nodes.

### 11.7 Database ownership protection

Do not rely solely on application code for obvious cross-revision ownership errors.

Where practical with the current persistence conventions, use composite uniqueness/FK/check patterns so:

- equipment cannot reference a revision/project mismatch;
- attribute cannot reference equipment in another revision/project;
- terminal cannot reference equipment in another revision/project;
- connection endpoints cannot come from another revision/project.

Application services MUST still perform explicit ownership validation and return clean API errors.

---

## 12. Equipment creation, editing, type changes, and lifecycle

### 12.1 Create

Creating equipment MUST:

1. verify project/revision ownership;
2. verify the revision is writable under existing revision rules;
3. validate the equipment type against `registry-v1`;
4. create a new `EquipmentLineage`;
5. create the Equipment snapshot;
6. materialize all registry attributes as `NOT_EXTRACTED`;
7. commit atomically.

Do not automatically create topology terminals based only on equipment type in Phase 5.

### 12.2 Attribute update

A manual attribute PUT with a value MUST:

1. load the registry definition;
2. validate value type;
3. validate enum membership if applicable;
4. validate/convert input unit;
5. write canonical value and canonical unit;
6. set `information_state=PRESENT`;
7. set `origin=MANUAL`;
8. set `verification_state=ENGINEER_REVIEWED`;
9. set `confidence=NULL`.

A manual update to `UNKNOWN`, `MISSING`, or `NOT_APPLICABLE` MUST clear all typed value slots and still record the action as manual/engineer-reviewed.

### 12.3 Equipment type change

Equipment type changes are allowed but MUST NOT silently destroy meaningful canonical data.

Algorithm:

1. Resolve old and new EquipmentDefinitions.
2. Preserve attributes whose key, value type, and canonical semantics are compatible.
3. Materialize newly applicable attributes as `NOT_EXTRACTED`.
4. Old-only/incompatible attributes may be automatically removed only when they are still unpopulated `NOT_EXTRACTED` rows.
5. If any incompatible attribute contains a meaningful state/value (`PRESENT`, `UNKNOWN`, `MISSING`, `NOT_APPLICABLE`, or `CONFLICTING`), reject the type change with a clear conflict response.
6. Do not silently coerce incompatible units/value types.
7. Type change is a manual action and updates Equipment audit metadata.

### 12.4 Remove / restore equipment

Remove is soft.

Removing equipment MUST:

- set equipment to `REMOVED`;
- retain all attributes;
- soft-remove active equipment-terminal nodes;
- soft-remove active connections incident to those terminals.

Restoring equipment MUST:

- restore the Equipment to `ACTIVE`;
- restore its existing equipment-terminal nodes;
- **not automatically restore removed connections**.

This conservative behavior avoids silently recreating electrical connectivity.

Removed equipment is excluded from default list responses and excluded from model carry-forward.

---

## 13. Revision inheritance

### 13.1 Creation option

Revision creation gains an independent option:

```text
carry_forward_model
```

Behavior:

- when `based_on_revision_id` exists, default `carry_forward_model=true`;
- without a base revision, `carry_forward_model=false`;
- document carry-forward and model carry-forward are independent;
- changing one option must never implicitly change the other.

### 13.2 Transaction

Revision creation, document carry-forward, and engineering-model cloning must participate in the same existing revision-creation transaction to the greatest extent supported by current architecture.

If model cloning fails, do not leave a partially cloned revision/model.

Reuse the existing project/revision locking and concurrency strategy. Do not create a second independent locking model.

### 13.3 Clone algorithm

When model carry-forward is enabled:

1. select ACTIVE source Equipment snapshots;
2. clone each Equipment with a new snapshot ID;
3. preserve `lineage_id`;
4. set `inherited_from_equipment_id` to source Equipment ID;
5. clone all applicable EquipmentAttribute rows with new IDs;
6. set each `inherited_from_attribute_id`;
7. preserve information state, verification state, origin, confidence, canonical unit, and canonical value;
8. clone ACTIVE nodes;
9. remap equipment IDs for terminal nodes;
10. set `inherited_from_node_id`;
11. clone ACTIVE connections;
12. remap both node endpoints;
13. set `inherited_from_connection_id`;
14. verify no references remain to the source revision.

Removed equipment/nodes/connections are not cloned.

If the code registry has added a new applicable attribute since the source snapshot was created, materialize that new attribute in the destination as `NOT_EXTRACTED` after copying the source attributes. Do not mutate the source revision.

The destination is an independent snapshot after cloning.

---

## 14. Provenance boundary

Phase 5 is **evidence-ready**, not evidence-complete.

The inheritance fields, origin, verification state, confidence, and audit fields provide enough scaffolding for Phase 6 to attach Evidence/Candidate provenance later.

Do not add Phase 6 tables such as:

```text
Evidence
ExtractionCandidate
AttributeEvidenceLink
Conflict
```

in Phase 5.

Do not store document IDs/page IDs directly in canonical attributes as a shortcut.

---

## 15. API contract

Exact router/module placement should follow current FastAPI conventions. All model CRUD endpoints are revision scoped.

### 15.1 Registry

```text
GET /api/engineering-model/registry
```

Response includes:

- `registry_version`;
- equipment type keys/display names;
- ordered AttributeDefinitions;
- Required/Critical metadata;
- allowed enum values;
- canonical units;
- unit-family metadata;
- RequirementRules.

The frontend MUST use this metadata to generate forms instead of duplicating the registry in TypeScript.

### 15.2 Equipment

```text
GET    /api/projects/{project_id}/revisions/{revision_id}/equipment
POST   /api/projects/{project_id}/revisions/{revision_id}/equipment
GET    /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}
PATCH  /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}

POST   /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/remove
POST   /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/restore
```

List endpoint should support repository-standard pagination plus:

```text
search
equipment_type
lifecycle_status
```

Do not make tag unique.

### 15.3 Attributes

At minimum:

```text
GET /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/attributes
PUT /api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/attributes/{attribute_key}
```

Representative manual update:

```json
{
  "information_state": "PRESENT",
  "value": 600,
  "unit": "V"
}
```

For a `rated_voltage` canonical unit of `kV`, the server stores:

```json
{
  "information_state": "PRESENT",
  "numeric_value": "0.6",
  "unit": "kV",
  "origin": "MANUAL",
  "verification_state": "ENGINEER_REVIEWED",
  "confidence": null
}
```

State-only example:

```json
{
  "information_state": "UNKNOWN"
}
```

The Phase 5 public API MUST NOT allow clients to forge `AI_EXTRACTION`, confidence, or `ENGINEER_VERIFIED` through ordinary manual-edit endpoints.

### 15.4 Nodes

```text
GET    /api/projects/{project_id}/revisions/{revision_id}/nodes
POST   /api/projects/{project_id}/revisions/{revision_id}/nodes
PATCH  /api/projects/{project_id}/revisions/{revision_id}/nodes/{node_id}
POST   /api/projects/{project_id}/revisions/{revision_id}/nodes/{node_id}/remove
POST   /api/projects/{project_id}/revisions/{revision_id}/nodes/{node_id}/restore
```

### 15.5 Connections

```text
GET    /api/projects/{project_id}/revisions/{revision_id}/connections
POST   /api/projects/{project_id}/revisions/{revision_id}/connections
PATCH  /api/projects/{project_id}/revisions/{revision_id}/connections/{connection_id}
POST   /api/projects/{project_id}/revisions/{revision_id}/connections/{connection_id}/remove
POST   /api/projects/{project_id}/revisions/{revision_id}/connections/{connection_id}/restore
```

### 15.6 API ownership and errors

- Project/revision IDs come from the path, never trusted from request bodies.
- Every nested object must be checked against the path project/revision.
- Mutations on non-writable revisions return the same class of conflict/error used by existing document revision writes.
- Unknown equipment types, attribute keys, enum values, or units return validation errors.
- Cross-revision object references are rejected.
- Requirement incompleteness is **not** a CRUD validation error in Phase 5.

---

## 16. Study-readiness/completeness evaluation

Implement a pure domain evaluator that can report:

```text
SATISFIED
UNSATISFIED
NOT_APPLICABLE
NOT_EVALUATED
```

for registry requirements.

This evaluator is useful for:

- unit tests;
- UI badges/messages;
- future Phase 10 validation;
- future extraction prioritization.

It MUST NOT prevent engineers from saving incomplete equipment.

Do not persist readiness findings in Phase 5.

---

## 17. Frontend scope

Add a top-level revision workspace switch:

```text
Documents | Engineering Model
```

The Phase 5 Engineering Model UI MUST include:

- equipment list;
- search;
- type filter;
- lifecycle/status filter;
- Add Equipment;
- equipment detail modal/Sheet consistent with the existing Phase 4.5 modal interaction pattern;
- general fields (tag/name/description/type);
- registry-generated attribute editor;
- attribute information-state controls;
- input-unit selection where applicable;
- Required/Critical/Conditional indicators;
- simple terminals/nodes management;
- simple connection forms/list;
- remove/restore actions;
- read-only behavior when the revision is not writable.

The UI MUST NOT include:

- graph visualization;
- React Flow;
- one-line diagram rendering;
- AI extraction actions;
- evidence UI;
- conflict reconciliation;
- engineer verification queue;
- study calculations.

### 17.1 Attribute editor behavior

- Render attributes in registry display order.
- Do not hardcode per-equipment forms in the frontend.
- ENUM → select control.
- BOOLEAN → boolean control.
- NUMBER / INTEGER → numeric input plus compatible unit selector where applicable.
- TEXT → text input.
- Non-`PRESENT` information states hide/disable the typed value input.
- Save normalizes units server-side.
- The UI may show incomplete requirement messages, but they are informational in Phase 5.

---

## 18. Revision creation UI

When creating a revision from a base revision, expose two independent controls:

```text
Carry forward documents    [default checked]
Carry forward model        [default checked]
```

When there is no base revision, both are false/not applicable.

The UI must not imply that carrying documents automatically carries the model or vice versa.

---

## 19. Persistence/package boundaries

The engineering registry is pure domain code.

ORM models/repositories should live in the repository's neutral persistence/application structure, not inside document-processing.

If the current SQLAlchemy Base or shared persistence utilities are awkwardly located, perform only the minimum neutral refactor necessary to let document processing and engineering-model persistence share them cleanly.

Do not reorganize unrelated repository architecture during Phase 5.

Topology may be a submodule of engineering-model or a small sibling domain package according to existing monorepo conventions; do not create package boundaries merely for aesthetic reasons.

---

## 20. Migration and existing data

Phase 5 introduces new tables; there is no existing canonical engineering-model data to backfill.

Migration behavior:

- create schema and indexes;
- do not synthesize equipment from existing Documents;
- do not run AI extraction;
- existing revisions simply begin with an empty model;
- future revisions may then carry that model forward once engineers populate it.

The registry itself is not a database table and does not need a registry-row migration.

---

## 21. Security, mutability, and concurrency

- Reuse existing project authorization.
- Reuse existing revision mutability rules.
- Superseded/frozen revisions are read-only to engineering-model mutation APIs.
- Reuse existing revision/project locking during revision creation and activation.
- Do not let independent model writes bypass lifecycle rules already applied to documents.
- All clone operations are deterministic and transactional.
- No Celery worker is required for Phase 5 model CRUD or inheritance.

---

## 22. Audit behavior

Phase 5 stores basic audit metadata:

```text
created_at / created_by
updated_at / updated_by
removed_at / removed_by
```

and snapshot provenance:

```text
inherited_from_equipment_id
inherited_from_attribute_id
inherited_from_node_id
inherited_from_connection_id
```

Do not implement an append-only audit event log in Phase 5.

Inheritance does not change the semantic `origin` of a copied canonical value. For example, a manually entered value remains `MANUAL` in the descendant snapshot; inheritance is represented by `inherited_from_attribute_id`.

---

## 23. Testing requirements

### 23.1 Registry tests

Test:

- exactly 20 equipment types;
- exactly 296 attribute definitions in `registry-v1`;
- snapshot matches `PowerForge_registry-v1_reference.json`;
- unique keys;
- legal snake_case keys;
- known canonical units;
- enums have valid options;
- requirement rules reference valid keys;
- unit conversions;
- conditional rule evaluation;
- Required/Critical semantics.

### 23.2 Persistence tests

Test:

- equipment creation creates lineage;
- all applicable attributes materialize;
- typed value constraints;
- enum rejection;
- unit normalization;
- duplicate tags allowed;
- cross-project/revision references rejected;
- soft remove/restore;
- type-change preservation and rejection behavior;
- no hard-delete path.

### 23.3 Revision inheritance tests

Test:

- model carry-forward defaults true with base revision;
- model/document options are independent;
- no-base revision does not inherit;
- new IDs are generated;
- equipment lineage is preserved;
- `inherited_from_*` pointers are correct;
- canonical values/states/origins/verification are preserved;
- removed objects are excluded;
- nodes remap to cloned equipment;
- connections remap to cloned nodes;
- no destination object points back to a source-revision endpoint except explicit `inherited_from_*`;
- clone failure rolls back revision/model creation.

### 23.4 Topology tests

Test:

- terminal requires same-revision equipment;
- electrical node cannot reference equipment;
- terminal key uniqueness;
- connection endpoint ownership;
- self-loop rejection;
- parallel connection acceptance;
- undirected connection acceptance;
- nominal direction acceptance;
- cable modeled as equipment with terminals rather than connection kind;
- equipment removal cascades logical topology removal;
- equipment restore does not restore connections.

### 23.5 API tests

Test:

- project/revision scoping;
- authorization;
- frozen revision rejection;
- registry endpoint;
- search/filter/pagination;
- manual attribute normalization;
- state-only updates;
- clients cannot forge AI/verification metadata;
- remove/restore actions.

### 23.6 Frontend/regression tests

Test:

- Documents workspace remains unchanged;
- Engineering Model workspace renders;
- registry-generated forms for representative types;
- enum/boolean/numeric/text controls;
- conditional/required/critical metadata display;
- read-only revision state;
- deep-link/modal behavior follows existing routing conventions;
- revision-create controls for documents/model are independent.

All pre-existing Phase 0–4.5 tests must continue to pass.

---

## 24. Implementation sequence

Implement Phase 5 incrementally. Do not land the entire phase as one opaque change.

### Phase 5A — Registry, units, and requirement engine

Deliver:

- EquipmentType / AttributeValueType definitions;
- registry-v1 typed definitions;
- unit conversion registry;
- RequirementRule model/evaluator;
- registry snapshot validation against companion JSON;
- registry API;
- unit tests.

**Gate:** no persistence work until registry tests pass.

### Phase 5B — Core engineering-model persistence

Deliver:

- `equipment_lineages`;
- `equipment`;
- `equipment_attributes`;
- Alembic migration;
- repositories/services;
- manual equipment/attribute CRUD;
- soft lifecycle;
- type-change rules;
- tests.

**Gate:** equipment CRUD/invariants pass before inheritance/topology.

### Phase 5C — Revision inheritance

Deliver:

- `carry_forward_model`;
- revision service integration;
- full equipment/attribute snapshot cloning;
- lineage preservation;
- transaction/rollback tests;
- revision-create UI option.

### Phase 5D — Topology persistence

Deliver:

- ModelNode;
- ModelConnection;
- migrations;
- ownership invariants;
- topology CRUD;
- equipment removal cascade behavior;
- topology clone/remap;
- tests.

### Phase 5E — Application APIs

Complete/refine:

- revision-scoped equipment APIs;
- attribute APIs;
- node/connection APIs;
- registry API response contracts;
- pagination/filter behavior;
- ownership and mutability errors;
- integration tests.

If API work naturally accompanies 5B/5D, keep commits logically separated even if routes are introduced earlier.

### Phase 5F — Engineering Model frontend

Deliver:

- workspace switch;
- equipment table;
- Add Equipment;
- modal detail;
- registry-generated attributes;
- state/unit controls;
- topology forms/list;
- remove/restore;
- revision-create carry-forward controls;
- frontend tests.

### Phase 5G — Hardening and documentation

Deliver:

- full regression suite;
- integration tests;
- registry snapshot test;
- documentation/ADR reconciliation;
- cleanup of dead placeholders;
- verify no Phase 6+ features leaked into scope.

---

## 25. ADR and documentation requirements

Create/update an ADR equivalent to:

```text
ADR-007 — Canonical Engineering Model Persistence
```

It should record at minimum:

- `ProjectRevision` is the aggregate root;
- no `EngineeringModel` table;
- stable EquipmentLineage;
- revision snapshots;
- relational typed attributes;
- code-owned registry;
- canonical units;
- separate information/verification/origin states;
- soft lifecycle;
- node/connection topology;
- independent model carry-forward;
- provenance deferred to Phase 6;
- validation/review/export deferred;
- containment deferred;
- advanced protection-function model deferred.

Reconcile existing architecture docs for engineering model, topology, provenance, validation, and review so they no longer contradict this specification.

---

## 26. Codex implementation instructions

When this specification is given to Codex:

1. Inspect the repository before editing and conform to existing module, ORM, API, migration, authentication, testing, and frontend conventions.
2. Treat this specification and `PowerForge_registry-v1_reference.json` as fixed requirements.
3. Do not redesign the registry or taxonomy during implementation.
4. Do not add convenience equipment types or arbitrary attributes.
5. Do not parse the XLSX at runtime.
6. Do not add AI/extraction/evidence/reconciliation/validation-engine features.
7. Do not add `parent_equipment_id` in Phase 5.
8. Do not add a general protection-function/settings data model in Phase 5.
9. Prefer small, reviewable migrations and services over broad rewrites.
10. Implement and verify one Phase 5 sub-phase at a time.
11. Run the relevant targeted tests after each sub-phase and the full regression suite before Phase 5 is marked complete.
12. If repository reality makes a specified invariant impossible without a material architecture change, stop and report the conflict rather than silently weakening the invariant.

---

## 27. Phase 5 completion criteria

Phase 5 is complete only when all of the following are true:

- `registry-v1` is represented in version-controlled domain code and matches the companion JSON;
- unit normalization is deterministic and tested;
- equipment/attributes are revision scoped and persist correctly;
- manual engineering-model authoring works without AI;
- stable lineages survive revision carry-forward;
- document and model carry-forward are independent;
- topology nodes/connections persist and clone correctly;
- all ownership/mutability invariants are enforced;
- basic Engineering Model UI is usable;
- incomplete models can be represented without bypassing structural validation;
- no Phase 6+ tables/workflows were prematurely introduced;
- existing Phase 0–4.5 behavior remains intact;
- ADR/docs are reconciled;
- test suite passes.

At that point Phase 5 is frozen and Phase 6 may introduce structured extraction/evidence/candidates against this canonical model.

---

## Appendix A — Registry reference policy

The companion `PowerForge_registry-v1_reference.json` contains the exact reviewed attribute definitions. It is intentionally provided to make Codex implementation deterministic and to support snapshot tests.

The JSON is a **design/reference fixture**, not permission to build a runtime system that reads the XLSX. The preferred implementation remains typed/version-controlled domain definitions validated against the fixture.

The XLSX may also be committed under a documentation/specification directory for engineering review and traceability.

Suggested repository placement:

```text
docs/specs/phase-5-engineering-model.md
docs/specs/registry/PowerForge_registry-v1_reference.json
docs/specs/registry/PowerForge_Phase5_Equipment_Attribute_registry-v1.xlsx
```

---

## Appendix B — Important modeling examples

### Utility Source

A study-ready utility source may be represented by either:

```text
three_phase_fault_current
slg_fault_current
three_phase_x_r
slg_x_r
```

or:

```text
positive_sequence_resistance
positive_sequence_reactance
zero_sequence_resistance
zero_sequence_reactance
```

The individual fields remain `Required = No`; the `ANY_OF` rule expresses the engineering requirement.

### Cable

A study-ready cable requires length plus either a physical-construction representation:

```text
conductor_material
conductor_size
core_count_per_cable
parallel_run_count
```

or direct sequence impedance:

```text
positive_sequence_resistance
positive_sequence_reactance
zero_sequence_resistance
zero_sequence_reactance
```

### Static Load

A study-ready static load supports either:

```text
rated_apparent_power + power_factor
```

or:

```text
rated_active_power + rated_reactive_power
```

### Reactor

Requirements vary by reactor type. For example:

- `SHUNT` requires reactive-power rating;
- `SERIES`, `CURRENT_LIMITING`, and `FILTER` may use positive-sequence impedance or rated inductance;
- `NEUTRAL_GROUNDING` requires neutral-grounding impedance;
- connection is conditional for shunt/filter use.

### LV Breaker

`trip_rating` and `long_time_pickup` are intentionally retained as design/canonical equipment attributes:

- thermal-magnetic breaker → `trip_rating` conditional requirement;
- electronic trip breaker → sensor/long-time pickup/trip-unit model conditional group.

They are not a substitute for the future structured protection-settings model.

---

**End of Phase 5 implementation specification.**
