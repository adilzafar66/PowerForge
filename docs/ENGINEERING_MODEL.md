# Engineering Model

The canonical engineering model belongs to a project revision. It is independent of documents, AI providers, and analysis software. [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md) and the [Phase 5 specification](specs/phase-5-engineering-model.md) supersede the Phase 0 placeholder taxonomy, JSONB attribute proposal, and combined information/verification states previously described here.

**Implemented: Phases 5A and 5B.** `packages/engineering-model` owns the pure registry, value validation, unit normalization, and requirement evaluation, with no third-party dependencies. `packages/persistence` owns revision-scoped equipment storage; the API service layer provides internal manual authoring operations. Revision model inheritance, topology, public equipment CRUD, and the Engineering Model UI have not been implemented. See [PHASE5B_HANDOFF.md](PHASE5B_HANDOFF.md) for implementation and validation details.

## Registry ownership

`powerforge_engineering_model.registry_v1` contains immutable typed Python definitions for `registry-v1`: 20 canonical equipment types, 296 attributes, 17 unit families, and 44 requirement reference rows. Three rows are `NONE` notices for Overcurrent Relay, Fuse, and CT; the other 41 rows form executable requirement groups (ANY_OF alternatives share a rule ID).

The [approved JSON](specs/registry/PowerForge_registry-v1_reference.json) is the independent regression fixture for exact keys, labels, flags, units, enums, notes, ordering, and requirement metadata. It is not loaded by the application. The XLSX is supporting documentation only and is never parsed at runtime. Snapshot tests never regenerate the reference.

Use the public interfaces rather than inspecting registry internals:

```python
from powerforge_engineering_model import (
    get_equipment_definition,
    get_attribute_definition,
    list_equipment_definitions,
    normalize_attribute_value,
    evaluate_requirements,
    supported_input_units,
    validate_registry,
)
```

Equipment keys use the approved uppercase identifiers, such as `TWO_WINDING_TRANSFORMER` and `SYNCHRONOUS_GENERATOR`. Generic Phase 0 keys/aliases are removed. Switchgear, switchboard, panelboard, MCC, and junction box are `BUS.bus_type` choices. A fused disconnect is a `SINGLE_THROW_SWITCH` with associated `FUSE` equipment; a pure junction belongs to future topology.

`validate_registry()` runs when the API application is constructed. It rejects malformed taxonomy, attributes, units, conditions, references, and alternative groups. The snapshot test also locks exact metadata and the 20/296/44 counts. Once registry-v1 is frozen, semantic changes require a deliberate registry version and migration strategy.

## Required, Critical, and information state

Required means an attribute is unconditionally needed for a minimally useful representation. Critical means missing or incorrect information can materially affect an intended engineering study. Neither flag is derived from the other, and neither imposes database NOT NULL behavior. Incomplete equipment remains representable and can be saved.

Information states are `PRESENT`, `UNKNOWN`, `MISSING`, `NOT_APPLICABLE`, `NOT_EXTRACTED`, and `CONFLICTING`. Verification and origin are separate concepts. The old `LOW_CONFIDENCE`, `INFERRED`, and `VERIFIED` information-state placeholders are removed; no existing production caller used them.

## Units and value validation

An attribute owns its canonical unit; a family default never overrides it. `normalize_attribute_value(type, key, value, input_unit=None)` validates the value type and exact enum membership, then returns a canonical `Decimal`, `int`, `str`, or `bool`. Omitted input units mean the attribute's canonical unit. Unitless attributes reject units. Booleans are not numeric values; non-finite numbers and fractional integers are rejected.

```python
from decimal import Decimal
from powerforge_engineering_model import normalize_attribute_value

assert normalize_attribute_value("BUS", "nominal_voltage", 600, "V") == Decimal("0.6")
assert normalize_attribute_value("BUS", "electrode_gap", "0.025", "m") == Decimal("25")
assert normalize_attribute_value("CT", "rated_burden", "0.01", "kVA") == Decimal("10")
```

The small conversion layer supports every reviewed input unit, including voltage/current, three distinct power dimensions, impedance and impedance per length, length, time, frequency, speed, capacitance, inductance, percentage, temperature, and per unit. Conversion arithmetic uses an isolated 34-significant-digit, round-half-even Decimal context, independent of a caller's decimal context. Identity conversion preserves integer inputs; NUMBER attributes return Decimal and INTEGER attributes return int. Floats are accepted through their decimal string representation; decimal strings or Decimal inputs avoid prior binary floating-point rounding.

`%` and `p.u.` are distinct dimensions; there is no implicit base conversion. Mechanical horsepower uses 745.69987158227022 W/hp and is allowed only for `INDUCTION_MOTOR.rated_active_power` and `VFD.rated_active_power`. `supported_input_units()` applies that same restriction, so the API does not offer unsupported choices for static/lumped loads. The lower-level `normalize_value()` requires an explicit `UnitSemanticContext` to allow horsepower.

Temperature conversion is affine for absolute °F/°C. Transformer `temperature_rise` is a temperature difference and therefore uses scale only (18 °F rise = 10 °C rise). No engineering quantities are derived or persisted.

The specification's relay `trip_output_operating_time = ms` example differs from the exact JSON: registry-v1 stores that relay attribute in **s**. The JSON value is preserved; VFD/UPS `output_short_circuit_trip_time` stores **ms**.

Domain errors distinguish `UnknownEquipmentType`, `UnknownAttribute`, `InvalidAttributeValue`, `InvalidEnumValue`, `UnknownUnit`, `IncompatibleUnit`, and `InvalidRegistryDefinition`.

## Requirement evaluation

Conditions are typed code: `ALWAYS`, `ATTRIBUTE_EQUALS`, `ATTRIBUTE_IN`, `ANY_PRESENT`, and `EXTERNAL_CONTEXT`. Human-readable English conditions are documentation, never executable expressions.

Pass a mapping of canonical attribute keys to `AttributeState`. Values are already in canonical units. PRESENT values are validated; other states must have no value. An omitted key means unpopulated. Zero and false are populated values. Unknown keys or malformed state/value combinations raise domain errors.

```python
from powerforge_engineering_model import AttributeState, InformationState, evaluate_requirements

results = evaluate_requirements(
    "UPS",
    {"static_bypass_available": AttributeState(InformationState.PRESENT, True)},
    external_context={"UPS_INVERTER_FAULT_CURRENT": False},
)
```

The evaluator returns immutable results in deterministic order: one `REQUIRED:<attribute_key>` result per unconditional flag, then one result per rule ID. Unsatisfied results include missing attributes for each alternative, preserving the alternative grouping.

- ANY_OF requires one complete alternative; mixing incomplete alternatives does not satisfy it.
- ALL_OF and REQUIRED_IF require every listed attribute when their condition applies.
- ALL_OR_NONE becomes applicable when any group member is PRESENT; absent groups are NOT_APPLICABLE.
- Only PRESENT satisfies an applicable value requirement. NOT_APPLICABLE on an attribute does not bypass an applicable rule.
- A missing/non-PRESENT selector produces NOT_EVALUATED. An explicitly false condition produces NOT_APPLICABLE.

External context accepts strict booleans keyed by these stable rule IDs:

| Equipment | Context key |
| --- | --- |
| Synchronous Generator | `GEN_REACTANCE_BASE_POWER`, `GEN_REACTANCE_BASE_VOLTAGE` |
| Induction Motor | `MOTOR_APPARENT_POWER_BASIS` |
| VFD | `VFD_OUTPUT_FAULT_DEFINITION` |
| UPS | `UPS_INVERTER_FAULT_CURRENT` |

Omitted external context returns NOT_EVALUATED, even if the target value exists. True evaluates completeness; false returns NOT_APPLICABLE. Unknown keys and non-boolean context values are rejected to avoid silently ignoring caller mistakes. The full status vocabulary is SATISFIED, UNSATISFIED, NOT_APPLICABLE, and NOT_EVALUATED. Results are not persisted and do not block incomplete-model saves.

## Registry API

`GET /api/engineering-model/registry` returns the registry version, ordered equipment/attributes, flags, enum choices, canonical units, attribute-specific supported input units, typed conditions, requirement rows, and unit families. It has no database dependency, accepts no writes, and has a typed OpenAPI response. Future frontend forms should consume it rather than duplicate the registry in TypeScript.

## Core persistence and service boundary

Migration `0007_engineering_model_core` adds `equipment_lineages`, `equipment`, and `equipment_attributes`. The neutral `powerforge_persistence` package owns the shared SQLAlchemy Base and project/revision mappings; `powerforge_persistence.engineering` owns the three engineering mappings. Existing imports of Base/Project/ProjectRevision from document-processing remain compatibility re-exports of those same objects. Document-specific mappings stay in document-processing. The pure engineering-model package has no ORM imports.

EquipmentLineage provides stable project-owned identity. Equipment is a revision snapshot with a lineage, text equipment type, optional tag/name/description, audit fields, and ACTIVE/REMOVED lifecycle. Tags are deliberately non-unique. A revision can contain each lineage only once. Composite foreign keys enforce project/revision/lineage ownership and attribute ownership; optional inheritance references enforce the same project and forbid self-reference. Phase 5B leaves inheritance references null.

Equipment attributes use separate NUMERIC, BIGINT, TEXT, and BOOLEAN columns. PRESENT requires exactly one compatible slot; every other information state requires all slots null. ENUM uses the text slot with registry validation in the service. Confidence, when present, is between zero and one. Non-finite numerics are rejected. Equipment types, attribute keys, and canonical units are text, validated against registry-v1, rather than database enums. Five closed state/type vocabularies use PostgreSQL enums, including all five verification states starting with UNVERIFIED.

`EngineeringModelService(session)` in `powerforge_api.services.engineering_model_service` implements:

- `create_equipment`, `get_equipment`, and `list_equipment` (ACTIVE by default; filter REMOVED or pass `lifecycle_status=None` for all).
- `get_equipment_attributes`, returned in registry order.
- `update_equipment` for tag, name, description, and safe equipment-type changes.
- `set_attribute` for manual PRESENT, UNKNOWN, MISSING, or NOT_APPLICABLE edits.
- Idempotent `remove_equipment` and `restore_equipment`.

Every operation takes project and revision IDs; individual operations also take the equipment ID. Writes accept an optional actor UUID and own their transaction, including rollback on failure. Use a dedicated session per unit of work. These are internal Python interfaces, not new HTTP endpoints.

Creation atomically inserts a new lineage, equipment, and exactly the attributes defined by the selected registry type. Equipment starts ACTIVE / MANUAL / ENGINEER_REVIEWED. Every attribute starts NOT_EXTRACTED / UNVERIFIED, with null origin, confidence, inheritance, and value slots, plus the registry's exact value type and canonical unit. Required/Critical flags remain registry metadata and do not prevent creating incomplete equipment.

PRESENT writes reuse Phase 5A normalization, store only the compatible typed slot, and clear the others. State-only edits clear all values and reject supplied values or input units. Manual edits always set MANUAL / ENGINEER_REVIEWED and null confidence; callers cannot supply provenance or verification. INTEGER storage supports signed 64-bit values; engineering numerics use Decimal and unconstrained PostgreSQL NUMERIC precision/scale. Ordinary manual edits cannot set NOT_EXTRACTED or CONFLICTING.

Type changes preserve rows only when key, value type, and canonical unit match the destination; a PRESENT enum value must also be allowed there. Incompatible rows may be discarded only if still NOT_EXTRACTED / UNVERIFIED with no values, origin, confidence, or inherited-from reference. Any meaningful incompatible row rejects the entire transaction, including accompanying metadata edits. New destination attributes receive the initial defaults. No type-change conversion or inference is attempted.

Removal preserves equipment, lineage, and all attributes, while setting removal timestamp/actor. Restore clears removal metadata and preserves values. Restore removed equipment before editing it. Service writes validate the complete materialized attribute set, ownership, types, units, and values; `validate_equipment_consistency()` detects corruption without silently repairing it.

The neutral `revision_writes` guard locks project FOR SHARE, then revision FOR UPDATE, and refreshes status under those locks. ACTIVE/PAUSED projects with DRAFT/ACTIVE revisions allow writes; ARCHIVED/CANCELLED projects and SUPERSEDED revisions reject them. Reads remain available. Document writes use the same guard and retain their existing error messages. Engineering writes update revision timestamps without upgrading the shared project lock.

## Planned revision-level metadata — Phase 5C

The approved product requirement adds optional `system_frequency` and `system_phase_count` to the engineering-model snapshot rooted at ProjectRevision. They are not implemented. No separate EngineeringModel entity is implied; no Phase 5B migration or registry-v1 change is needed for this documentation update. See [ROADMAP.md](ROADMAP.md).

`system_frequency` expresses common frequency in Hz, for example 50 or 60 Hz, and is optional until known/configured. Conceptually, an explicitly PRESENT equipment frequency is the equipment-specific value; otherwise a configured system frequency supplies the effective value for applicable equipment; otherwise frequency is unavailable. This lookup does not settle override policy: the Phase 5C specification must decide whether disagreement is rejected or deterministically flagged. A mismatch must never be ignored.

`system_phase_count` expresses an optional common count, normally 1 or 3. Set it only when one count legitimately applies across relevant equipment. A meaningful single-/three-phase mixture leaves it null/absent, meaning no single system-wide assumption is asserted. Do not introduce 0, MIXED, or UNKNOWN sentinels without a later approved design. Future effective-value logic may fall back to this common count when equipment phase count is absent; explicit mismatches require validation.

Keep equipment-specific frequency and phase_count registry fields. Do not materialize model defaults into their EquipmentAttribute rows. This avoids duplicate values, mass updates, false provenance, and persistence noise. Explicit values still capture source-stated data, exceptions, mixed phase configurations, and comparisons with revision assumptions. A model-level default is not fabricated document evidence, and changing it must not silently overwrite explicit equipment values.

Phase 5C must formally specify exact persisted names, frequency numeric type, constraints, metadata inheritance/carry-forward behavior, API representation, effective-value resolution, mismatch policy, and writable-revision edit behavior. The approved requirement extends the planned 5C scope; it does not amend ADR-007 or the existing Phase 5 specification by implication. A specification supplement is required, and an ADR supplement/amendment should be assessed if architectural decisions are added.

## Future study domains

The Phase 5 physical equipment/topology model is not a complete study model. Protection functions/settings and operating/study configurations require dedicated post-core-Phase-5 design decisions before extraction or integration depends on their schemas. Phase 5 does not introduce a general ProtectionFunction persistence model. Canonical `LV_BREAKER.trip_rating` and `LV_BREAKER.long_time_pickup` remain equipment/design values and may coexist with separate future study-adjusted settings without being overwritten. These domains must not be added as arbitrary flat equipment attributes; [ROADMAP.md](ROADMAP.md) records the concepts and design gates.

## Later phases

Phase 5C has not begun. Revision creation still carries forward documents only. No equipment cloning, topology, public equipment CRUD, frontend, AI extraction, evidence/candidates/reconciliation, persisted findings, protection-function model, or exporters were added in Phase 5B. These remain separate responsibilities under ADR-007.
