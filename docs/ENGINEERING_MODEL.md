# Engineering Model

The canonical engineering model belongs to a project revision. It is independent of documents, AI providers, and analysis software. [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md) and the [Phase 5 specification](specs/phase-5-engineering-model.md) supersede the Phase 0 placeholder taxonomy, JSONB attribute proposal, and combined information/verification states previously described here.

**Implemented: Phase 5A only.** `packages/engineering-model` owns the pure registry, value validation, unit normalization, and requirement evaluation. It has no third-party dependencies. Equipment persistence, revision model inheritance, topology persistence, and the Engineering Model UI have not been implemented.

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

Required means an attribute is unconditionally needed for a minimally useful representation. Critical means missing or incorrect information can materially affect an intended engineering study. Neither flag is derived from the other, and neither imposes database NOT NULL behavior. Incomplete equipment must remain representable in later phases.

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

Omitted external context returns NOT_EVALUATED, even if the target value exists. True evaluates completeness; false returns NOT_APPLICABLE. Unknown keys and non-boolean context values are rejected to avoid silently ignoring caller mistakes. The full status vocabulary is SATISFIED, UNSATISFIED, NOT_APPLICABLE, and NOT_EVALUATED. Results are not persisted and do not block future incomplete-model saves.

## Registry API

`GET /api/engineering-model/registry` returns the registry version, ordered equipment/attributes, flags, enum choices, canonical units, attribute-specific supported input units, typed conditions, requirement rows, and unit families. It has no database dependency, accepts no writes, and has a typed OpenAPI response. Future frontend forms should consume it rather than duplicate the registry in TypeScript.

## Later phases

ADR-007 defines the future typed relational snapshot rooted at `ProjectRevision`, with stable equipment lineage and separate node/connection topology. Documents, evidence, candidates, reconciliation, and verification remain separate responsibilities. Phase 5A adds no ORM entities, migrations, model cloning, equipment/topology CRUD, frontend, AI extraction, findings tables, protection-function model, or exporters.
