# Engineering Model

The canonical engineering model belongs to a project revision. It is independent of documents, AI providers, and analysis software. [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md) and the [Phase 5 specification](specs/phase-5-engineering-model.md) supersede the Phase 0 placeholder taxonomy, JSONB attribute proposal, and combined information/verification states previously described here.

**Implemented: Phases 5A through 5G plus the authoring refinement.** `packages/engineering-model` owns the pure registry, value validation, unit normalization, requirement evaluation, and effective model-value semantics, with no third-party dependencies. `packages/persistence` owns revision-scoped equipment, topology storage, and revision-level engineering metadata. Public revision-scoped APIs expose manual authoring through the accepted services; revision inheritance remains transactional. Phase 5F exposes manual authoring in the revision Engineering Model workspace; see [PHASE5F_HANDOFF.md](PHASE5F_HANDOFF.md). See [PHASE5E_HANDOFF.md](PHASE5E_HANDOFF.md) for the API contract and validation details.

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

Equipment keys use the approved uppercase identifiers, such as `TWO_WINDING_TRANSFORMER` and `SYNCHRONOUS_GENERATOR`. Generic Phase 0 keys/aliases are removed. Switchgear, switchboard, panelboard, MCC, and junction box are `BUS.bus_type` choices. A fused disconnect is a `SINGLE_THROW_SWITCH` with associated `FUSE` equipment; a pure junction is a topology ELECTRICAL_NODE.

`validate_registry()` runs when the API application is constructed. It rejects malformed taxonomy, attributes, units, conditions, references, and alternative groups. The snapshot test also locks exact metadata and the 20/296/44 counts. Registry-v1 is frozen at the Phase 5G gate; semantic changes require a deliberate registry version and migration strategy.

## Required, Critical, and information state

Required means an attribute is unconditionally needed for a minimally useful representation. Critical means missing or incorrect information can materially affect an intended engineering study. Neither flag is derived from the other, and neither imposes database NOT NULL behavior. Incomplete equipment remains representable and can be saved.

Information states are `PRESENT`, `MISSING`, `NOT_APPLICABLE`, `NOT_POPULATED`, and `CONFLICTING`. Verification and origin are separate concepts. The old `LOW_CONFIDENCE`, `INFERRED`, and `VERIFIED` information-state placeholders are removed; no existing production caller used them.

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

`GET /api/engineering-model/registry` returns the registry version, ordered equipment/attributes, flags, enum choices, canonical units, attribute-specific supported input units, typed conditions, requirement rows, and unit families. It has no database dependency, accepts no writes, and has a typed OpenAPI response. Phase 5F frontend forms consume this metadata without duplicating the canonical registry in TypeScript.

## Core persistence and service boundary

Migration `0007_engineering_model_core` adds `equipment_lineages`, `equipment`, and `equipment_attributes`. The neutral `powerforge_persistence` package owns the shared SQLAlchemy Base and project/revision mappings; `powerforge_persistence.engineering` owns the three engineering mappings. Existing imports of Base/Project/ProjectRevision from document-processing remain compatibility re-exports of those same objects. Document-specific mappings stay in document-processing. The pure engineering-model package has no ORM imports.

EquipmentLineage provides stable project-owned identity. Equipment is a revision snapshot with a lineage, text equipment type, optional tag/name/description, audit fields, and ACTIVE/REMOVED lifecycle. Tags are deliberately non-unique. A revision can contain each lineage only once. Composite foreign keys enforce project/revision/lineage ownership and attribute ownership; optional inheritance references enforce the same project and forbid self-reference. New manual rows leave inheritance references null; Phase 5C cloning populates them.

Equipment attributes use separate NUMERIC, BIGINT, TEXT, and BOOLEAN columns. PRESENT requires exactly one compatible slot; every other information state requires all slots null. ENUM uses the text slot with registry validation in the service. Confidence, when present, is between zero and one. Non-finite numerics are rejected. Equipment types, attribute keys, and canonical units are text, validated against registry-v1, rather than database enums. Five closed state/type vocabularies use PostgreSQL enums, including all five verification states starting with UNVERIFIED.

`EngineeringModelService(session)` in `powerforge_api.services.engineering_model_service` implements:

- `create_equipment`, `get_equipment`, and `list_equipment` (ACTIVE by default; filter REMOVED or pass `lifecycle_status=None` for all).
- `get_equipment_attributes`, returned in registry order.
- `update_equipment` for tag, name, description, and safe equipment-type changes.
- `set_attribute` for manual PRESENT, NOT_POPULATED, MISSING, or NOT_APPLICABLE edits.
- Idempotent `remove_equipment` and `restore_equipment`.

Every operation takes project and revision IDs; individual operations also take the equipment ID. Writes accept an optional actor UUID and own their transaction, including rollback on failure. Use a dedicated session per unit of work. These are internal Python interfaces, not new HTTP endpoints.

Creation atomically inserts a new lineage, equipment, exactly the attributes defined by the selected registry type, and its code-owned profile terminals (see [TOPOLOGY.md](TOPOLOGY.md)). Equipment starts ACTIVE / MANUAL / ENGINEER_REVIEWED. Every attribute starts NOT_POPULATED / UNVERIFIED, with null origin, confidence, inheritance, and value slots, plus the registry's exact value type and canonical unit. Required/Critical flags remain registry metadata and do not prevent creating incomplete equipment.

PRESENT writes reuse Phase 5A normalization, store only the compatible typed slot, and clear the others. State-only edits clear all values and reject supplied values or input units. PRESENT, MISSING and NOT_APPLICABLE edits set MANUAL / ENGINEER_REVIEWED and null confidence. Resetting to NOT_POPULATED clears all typed slots, origin and confidence, and sets UNVERIFIED; callers cannot supply provenance or verification. INTEGER storage supports signed 64-bit values; engineering numerics use Decimal and unconstrained PostgreSQL NUMERIC precision/scale. CONFLICTING is not a manual target. NOT_POPULATED means no canonical value has been populated; MISSING means the value is unavailable or could not be obtained.

Type changes preserve rows only when key, value type, and canonical unit match the destination; a PRESENT enum value must also be allowed there. Incompatible rows may be discarded only if still NOT_POPULATED / UNVERIFIED with no values, origin, or confidence. An inheritance pointer records snapshot ancestry and does not make an empty placeholder meaningful engineering data. Any meaningful incompatible row rejects the entire transaction, including accompanying metadata edits. New destination attributes receive the initial defaults. No type-change conversion or inference is attempted.

Removal preserves equipment, lineage, and all attributes, while setting removal timestamp/actor. Restore clears removal metadata and preserves values. Restore removed equipment before editing it. Service writes validate the complete materialized attribute set, ownership, types, units, and values; `validate_equipment_consistency()` detects corruption without silently repairing it.

The neutral `revision_writes` guard locks project FOR SHARE, then revision FOR UPDATE, and refreshes status under those locks. ACTIVE/PAUSED projects with DRAFT/ACTIVE revisions allow writes; ARCHIVED/CANCELLED projects and SUPERSEDED revisions reject them. Reads remain available. Document writes use the same guard and retain their existing error messages. Engineering writes update revision timestamps without upgrading the shared project lock.

## Revision inheritance and model metadata — Phase 5C

Migration `0008_revision_model_metadata` adds optional `system_frequency` and `system_phase_count` to the engineering-model snapshot rooted at ProjectRevision. Frequency uses Python `Decimal` and PostgreSQL `NUMERIC`, is stored in canonical Hz, and must be finite and greater than zero. Common phase count is an integer restricted to 1 or 3. Null means that no revision-wide assumption is asserted. No separate EngineeringModel entity or registry-v1 change was introduced.

Revision creation accepts `carry_forward_model` independently of document carry-forward. Omitted or null resolves to true when a base revision exists and false otherwise; explicit true without a base is rejected. When enabled, omitted model metadata inherits from the selected base, explicit values override it, and explicit null clears it. With carry-forward disabled, omitted fields remain null. Writable DRAFT/ACTIVE revisions on ACTIVE/PAUSED projects may update these fields; SUPERSEDED revisions and ARCHIVED/CANCELLED projects remain read-only.

The same transaction creates the revision, inherits included documents, clones the model, applies revision metadata, and optionally activates the revision. Only ACTIVE equipment is cloned. New equipment and attribute IDs form an independent snapshot, while equipment lineage is retained and `inherited_from_*` points to the exact row in the selected base revision. Canonical values, units, states, origin, verification, and confidence are preserved. Removed equipment is excluded.

Registry evolution is conservative. Attributes newly present in registry-v1 materialize as NOT_POPULATED / UNVERIFIED with null values, origin, confidence, and inheritance pointer. Old or incompatible source attributes may be omitted only while still untouched; meaningful incompatible data rejects and rolls back the entire revision creation instead of being coerced or discarded.

`resolve_effective_model_value()` supplies the Phase 5C domain rule for applicable frequency and phase-count attributes: an explicit PRESENT equipment value wins, otherwise the revision value is used, otherwise the result is unspecified. When an explicit value differs from the revision value, the returned `mismatch` flag is true. Both values remain unchanged; Phase 5C persists no validation finding. Revision defaults are never materialized into EquipmentAttribute rows and never change their information state or provenance.

## Canonical topology — Phase 5D

Migration `0009_topology_persistence` adds ModelNode and ModelConnection in the neutral persistence layer. Nodes are EQUIPMENT_TERMINAL or ELECTRICAL_NODE; connections reference nodes, with composite ownership foreign keys and no self-loops. Parallel edges are valid. Cables and physical buses remain Equipment. The pure topology package owns the closed kind/direction enums.

The internal TopologyService supports manual node/connection creation, reads, metadata edits/rewiring, and soft lifecycle under the shared writable-revision guard. Equipment removal atomically removes terminals and incident active connections; equipment restore restores current-profile and custom terminals only; obsolete profile terminals stay removed. Node restore also leaves connections removed. Connection restore requires active same-revision endpoints. Nominal voltage uses the accepted Decimal conversion utility and canonical kV.

Model carry-forward now includes ACTIVE nodes and connections after equipment/attributes, remapping every equipment reference and endpoint into the destination. Inheritance pointers reference the actual immediate base; corrupt active topology fails the entire transaction. Revision defaults never populate topology fields, and explicit phase overrides are not rejected. See [TOPOLOGY.md](TOPOLOGY.md).

## Public model APIs — Phase 5E

The dedicated `routers/model.py` exposes resources beneath `/api/projects/{project_id}/revisions/{revision_id}`:

- Equipment: GET/POST `/equipment`, GET/PATCH `/equipment/{equipment_id}`, POST `/equipment/{equipment_id}/remove` and `/restore`.
- Attributes: GET `/equipment/{equipment_id}/attributes`, PUT `/equipment/{equipment_id}/attributes/{attribute_key}`.
- Nodes: GET/POST `/nodes`, PATCH `/nodes/{node_id}`, POST `/nodes/{node_id}/remove` and `/restore`.
- Connections: GET/POST `/connections`, PATCH `/connections/{connection_id}`, POST `/connections/{connection_id}/remove` and `/restore`.

Creates return 201; reads, edits, and lifecycle actions return 200 with explicit canonical response models. Lists return `items` wrappers. Equipment summaries include lineage/provenance and omit nested attributes. Attribute responses expose typed slots, canonical units, information/verification/origin, confidence, and inheritance/audit metadata in registry order. Decimal fields serialize as JSON strings without conversion to float. The read-only registry remains the form metadata source.

Equipment lists support case-insensitive literal substring `search` across tag/name/description, canonical `equipment_type`, and `lifecycle_status=ACTIVE|REMOVED|ALL`. Blank search is ignored. Equipment, node, and connection lists default to ACTIVE and sort by creation time then ID. ALL is only an API query concept. Lists are currently unpaginated; equipment summaries do not load attributes.

Mutation bodies reject extra fields, including forged provenance, verification, confidence, inheritance, audit actors/timestamps, and path ownership. PATCH omission keeps existing values; explicit null clears nullable text and connection voltage, but not type, endpoints, kind, direction, or terminal keys. Attribute PUT accepts PRESENT, NOT_POPULATED, MISSING, and NOT_APPLICABLE; services retain registry validation/unit normalization, including `600 V -> "0.6" kV`. State-only updates clear typed slots. Incomplete equipment remains saveable.

Services enforce same-project/revision ownership and existing mutability/locking rules. Scoped-out objects return 404, removed/read-only/type-change conflicts return 409, and invalid registry/domain/topology input returns 422. Application errors retain the standard nested detail/code envelope; schema errors use FastAPI's validation response. There is no client actor identity or verification workflow. See the [Phase 5E handoff](PHASE5E_HANDOFF.md) for exact allowlists, error mappings, and lifecycle semantics.

## Transactional equipment editor — authoring refinement

`GET /equipment/{equipment_id}/editor` returns `{equipment, attributes, terminals}`. The corresponding PATCH accepts optional `general`, keyed `attributes`, `create_terminals`, `update_terminals`, `remove_terminals` and `restore_terminals` changes. Empty requests, forged metadata, duplicate terminal operations and terminal IDs outside the edited equipment are rejected. Existing fine-grained APIs remain available.

A single writable-revision transaction applies the entire draft. Shared service methods flush under the outer unit of work without committing independently; any failure rolls back general fields, attributes, terminals and topology cascades together. Explicit resets run before type reconciliation so a reset can make an old incompatible attribute discardable; remaining attribute and terminal edits are validated against the resulting equipment type. The response contains fresh canonical values, with NUMBER/INTEGER still lossless strings.

The Equipment sheet owns one draft across General, Attributes and Terminals. Its sticky top-right Save button and Ctrl/Cmd+S invoke the same operation. No per-field or per-terminal saves remain. Save is disabled while unchanged, invalid, busy, read-only or removed. Closing a dirty sheet offers Save changes, Discard changes and Keep editing; save failure retains the sheet and draft. Browser unload also warns about unsaved changes. Lifecycle actions are disabled while the editor is dirty. Changing equipment type retains the current attribute draft until Save reconciles it; destination fields appear in the canonical response after successful Save.

Migration `0010_authoring_refinement` replaces the database enum, mapping the former NOT_EXTRACTED to NOT_POPULATED and UNKNOWN to MISSING, and backfills profile terminals. Historical handoffs and registry-v1 remain unchanged. See [PHASE5_AUTHORING_REFINEMENT_HANDOFF.md](PHASE5_AUTHORING_REFINEMENT_HANDOFF.md).

## Lossless numeric response contract — Phase 5G

Canonical `integer_value` responses are consistently base-10 JSON strings or null, including small integers: `"3"` and `"9007199254740993"`. Domain/ORM values remain Python integers and PostgreSQL BIGINT; only JSON serialization changes. `AttributeResponse` OpenAPI declares string-or-null, and the frontend response type is `string | null`. No JavaScript numeric conversion occurs before display or resubmission. Existing NUMBER/Decimal string serialization remains unchanged. Revision `system_phase_count` still uses the strictly bounded numeric vocabulary 1/3 and is not an attribute slot.

Live persistence/API tests and frontend tests using the real JSON decoder/editor cover small and unsafe-range integers, while the clean-stack HTTP/JavaScript check verifies real response resubmission. Clients of the former numeric `integer_value` response must adopt the string contract. The Phase 5F handoff's limitation is historical and resolved by this change. No new migration, registry bounds, or dependencies were required.

## Revision workspace — Phase 5F

Documents remains the default revision workspace. `?workspace=model` selects Engineering Model; `equipment=<id>` opens its detail Sheet independently of list filters. Switching workspaces clears the other workspace's detail parameter and preserves unrelated query parameters. Registry metadata loads on first model use and remains cached while the model workspace is mounted.

Equipment supports debounced server search, registry type filters, Active/Removed/All views, create, and General/Attributes/Terminals details. The unified editor PATCHes only changed fields; explicit null clears nullable text. An empty PATCH is never sent. Type-change conflicts preserve the form draft; successful changes refresh the materialized attributes.

Attribute forms follow registry order and distinguish Required, Critical, and Conditional metadata without inventing a validation workflow. ENUM choices and input units come from the registry. NUMBER and INTEGER inputs remain strings through submission, BOOLEAN requires an explicit True/False selection and sends a JSON boolean, and TEXT remains text. Unit conversion stays on the server and successful saves adopt canonical responses. PRESENT accepts a value; NOT_POPULATED/MISSING/NOT_APPLICABLE omit values and units. CONFLICTING is viewable but cannot be selected as a manual target. Attribute edits join the equipment-wide draft and preserve it on errors.

Read-only or removed objects remain viewable. Mutation controls respect revision/owner lifecycle; stale read-only responses disable further editing and refresh server state. Removal warns about terminal/connection cascades, and restoration does not silently restore connections. Provenance and verification are displayed without edit controls. See [TOPOLOGY.md](TOPOLOGY.md) and [PHASE5F_HANDOFF.md](PHASE5F_HANDOFF.md).

## Future study domains

The Phase 5 physical equipment/topology model is not a complete study model. Protection functions/settings and operating/study configurations require dedicated post-core-Phase-5 design decisions before extraction or integration depends on their schemas. Phase 5 does not introduce a general ProtectionFunction persistence model. Canonical `LV_BREAKER.trip_rating` and `LV_BREAKER.long_time_pickup` remain equipment/design values and may coexist with separate future study-adjusted settings without being overwritten. These domains must not be added as arbitrary flat equipment attributes; [ROADMAP.md](ROADMAP.md) records the concepts and design gates.

## Later phases

Phase 5 is complete and re-frozen; Phase 6 is next and has not started. See [PHASE5G_HANDOFF.md](PHASE5G_HANDOFF.md) for the completion audit. AI extraction, evidence/candidates/reconciliation, persisted findings, protection-function model, and exporters remain separate responsibilities under ADR-007.
