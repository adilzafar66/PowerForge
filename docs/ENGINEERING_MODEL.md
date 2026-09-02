# Engineering Model

The engineering model is the central, queryable representation of an electrical system for a project revision. After engineer verification, it is the source of truth. Original documents remain immutable evidence. AI extraction produces candidates; it never owns the model.

This package (`packages/engineering-model`) must have **no dependency** on AI providers or electrical analysis software. See [ADR-001](../decisions/ADR-001-engineering-model-independence.md).

## Ownership

The engineering model module owns:

- Equipment entities
- Electrical attributes
- Connections and topology
- Model revisions
- Model state

It does not own document parsing, OCR, prompts, provider SDKs, or analysis calculations.

## Entity types (initial)

The model initially supports:

- `UtilitySource`
- `Generator`
- `Transformer`
- `Node`
- `Bus`
  - `Switchgear`
  - `MCC`
  - `Panelboard`
  - `Switchboard`
  - `Other`
- `Breaker`
  - `LowVoltage`
  - `HighVoltage`
- `Relay`
- `Recloser`
- `CT`
- `UPS`
- `VFD`
- `Fuse`
- `Disconnect`
- `SingleSwitch`
- `DoubleSwitch`
- `Cable`
- `Motor`
- `StaticLoad`
- `LumpedLoad`
- `Reactor`
- `Capacitor`

Additional equipment types must be addable without a disconnected schema per type.

## Common equipment concept

Do not implement each equipment type as an unrelated table with duplicated lifecycle columns.

Use a common `Equipment` concept:

| Field | Role |
| --- | --- |
| `id` | Stable identifier |
| `project_id` | Owning project |
| `revision_id` | Owning model revision |
| `equipment_type` | Discriminator |
| `tag` | Engineer-facing tag (`T1`, `CB-101`) |
| `name` | Display name |
| `description` | Free-text description |
| `status` | Lifecycle / review status |
| `attributes` | Typed attribute collection (not a single opaque blob for the whole model) |
| `provenance` | Evidence links at entity and attribute level |
| `confidence` | Not a single object-level score; see Attribute model |
| `created_at` / `updated_at` | Audit timestamps |

Type-specific properties (impedance, kVA, frame rating) live as attributes on the common entity, with relational columns for properties that must be searched and filtered.

## Persistence approach

Hybrid relational / JSONB:

**Relational** (queryable, constrained): projects, revisions, documents, pages, equipment identity, connections, evidence, reviews, conflicts, jobs, audit logs.

**JSONB** (flexible, still associated with relational rows): equipment-specific attribute payloads, AI extraction candidate payloads, model metadata, document metadata.

Do not store an entire project as one JSON document. The model must remain queryable in PostgreSQL.

Phase 0 does not create equipment tables. It establishes Alembic and documents this shape so Phase 1 (projects) and Phase 5 (equipment) can add tables without redesign.

## Attribute model

Never store only `transformer.impedance = 5.75`.

Each engineering attribute conceptually supports:

```
attribute:            impedance_percent
value:                5.75
unit:                 %
confidence:           0.96
source:               document_id
page:                 4
bounding_box:         ...
extraction_method:    AI_VISION
verification_status:  UNVERIFIED
```

The engineer must be able to ask “Where did this value come from?” and receive a precise answer.

Confidence is **per attribute**, not one score on the equipment object.

## Information states

Null is not sufficient. Distinguish:

| State | Meaning |
| --- | --- |
| `UNKNOWN` | Needed, not known |
| `MISSING` | Expected from sources but not found |
| `NOT_APPLICABLE` | Does not apply to this equipment |
| `NOT_EXTRACTED` | Pipeline has not attempted this attribute |
| `LOW_CONFIDENCE` | Extracted, below review threshold |
| `CONFLICTING` | Multiple disagreeing values |
| `INFERRED` | Derived, not directly evidenced |
| `VERIFIED` | Engineer-confirmed |

Example: a breaker may have manufacturer/model/frame `VERIFIED`, trip rating `UNKNOWN`, interrupting rating `MISSING`.

## Verification states

AI-generated information must never be presented as verified engineering information.

| State | Meaning |
| --- | --- |
| `AI_EXTRACTED` | Produced by extraction; unverified |
| `SYSTEM_VALIDATED` | Passed deterministic validation; still not engineer-verified |
| `ENGINEER_REVIEWED` | Engineer has acted; may still be unresolved |
| `ENGINEER_VERIFIED` | Engineer accepted as model truth |

Never silently promote `AI_EXTRACTED` to `ENGINEER_VERIFIED`.

## Revisions

```
Project
  Revision 1 → Engineering Model
  Revision 2 → Engineering Model
  Revision 3 → Engineering Model
```

The schema must allow detecting later: equipment added/removed, rating changes, breaker changes, topology changes, source changes. Sophisticated diffing is not required until a later phase; the data model must not prevent it.

## Topology

The electrical system is a graph of nodes and connections. Topology is independently queryable and is derived from the engineering model. The SLD is evidence and/or visualization, not the database. See [TOPOLOGY.md](TOPOLOGY.md).

## Conflicts and source priority

Conflicting values are first-class records with suggested resolution and `PENDING_ENGINEER_REVIEW`. Source priority is configuration (`equipment_type` + `attribute` + `source_type` + `priority`), not hard-coded universal rules. See [VALIDATION.md](VALIDATION.md) and [REVIEW_WORKFLOW.md](REVIEW_WORKFLOW.md).

## Independence

The engineering model schema and domain logic must remain valid if:

- The LLM vendor changes
- OCR engines change
- Prompt versions change
- No analysis software is ever integrated

Export (Phase 13) produces JSON/CSV/Excel of the model. ETAP/SKM/EasyPower adapters are explicitly out of scope.
