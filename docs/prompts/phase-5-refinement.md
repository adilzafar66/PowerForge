# PowerForge Phase 5 — Authoring Refinement

Implement a focused post-Phase-5G refinement before starting Phase 6.

Start from:

```text
codex/phase-5g-hardening
7067f693efe45ead37a60a98c8d57eb385b5c338
```

Create:

```text
codex/phase-5-authoring-refinement
```

Do **not** begin Phase 6.

Read the Phase 5 spec, ADR-007, Phase 5G handoff, current Engineering Model/Topology docs, and inspect the existing backend/frontend implementation before editing.

---

## Goals

Implement these four changes:

1. Nodes and Connections should use clickable tables with detail/edit modals.
2. Equipment should automatically receive its normal terminals.
3. Simplify InformationState:
   - `NOT_EXTRACTED` → `NOT_POPULATED`
   - remove `UNKNOWN`; migrate it to `MISSING`
4. Equipment editing should use one draft and one Save action for General + Attributes + Terminals.

Keep the existing Phase 5 architecture otherwise unchanged.

---

# 1. Automatic terminals

Add a code-owned terminal profile for every canonical equipment type.

Use these defaults:

```text
UTILITY_SOURCE          OUTPUT
SYNCHRONOUS_GENERATOR   OUTPUT
TWO_WINDING_TRANSFORMER PRIMARY, SECONDARY
BUS                     BUS
LV_BREAKER              INPUT, OUTPUT
HV_BREAKER              INPUT, OUTPUT
RECLOSER                INPUT, OUTPUT
OVERCURRENT_RELAY       none
FUSE                    INPUT, OUTPUT
SINGLE_THROW_SWITCH     INPUT, OUTPUT
DOUBLE_THROW_SWITCH     SOURCE_1, SOURCE_2, COMMON
CABLE                   END_A, END_B
CT                      INPUT, OUTPUT
INDUCTION_MOTOR         INPUT
STATIC_LOAD             INPUT
LUMPED_LOAD             INPUT
CAPACITOR               INPUT
REACTOR                 INPUT, OUTPUT
VFD                     INPUT, OUTPUT
UPS                     INPUT, OUTPUT
```

Creating equipment must automatically create its default terminals in the same transaction.

Normal terminals should not require manual creation.

Retain support for exceptional custom terminals such as:

```text
GROUND
NEUTRAL
```

Do not model relay functions such as 50/51/50N/51N as topology terminals.

Add a persisted way to distinguish profile-managed terminals from custom terminals, e.g.:

```text
managed_by_profile: bool
```

Profile-managed terminal keys are system controlled and cannot be manually renamed or removed while required by the equipment profile.

Custom terminals remain manually editable.

### Equipment type changes

When equipment type changes:

- preserve matching profile terminals;
- create newly required terminals;
- adopt an existing matching custom terminal where possible;
- remove obsolete profile terminals only when they have no active connections;
- reject the type change if removing a terminal would destroy active topology;
- preserve unrelated custom terminals.

Keep the operation atomic.

### Existing data

Add a migration that safely backfills default terminals for existing equipment.

If a required terminal already exists, preserve it and mark it profile-managed.

Do not change existing connection endpoints or destroy custom terminals.

Revision carry-forward must preserve the profile/custom distinction.

---

# 2. InformationState cleanup

Replace:

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
NOT_EXTRACTED
CONFLICTING
```

with:

```text
PRESENT
MISSING
NOT_APPLICABLE
NOT_POPULATED
CONFLICTING
```

Meaning:

```text
NOT_POPULATED
    No canonical value has been populated.

PRESENT
    A usable canonical value exists.

MISSING
    The value is unavailable / could not be obtained.

NOT_APPLICABLE
    The attribute does not apply.

CONFLICTING
    Unresolved candidate/source values disagree.
```

The manual UI should offer:

```text
Not populated
Present
Missing
Not applicable
```

Do not offer `CONFLICTING` as a normal manual choice.

A user must always be able to reset an attribute to `NOT_POPULATED`.

Resetting to `NOT_POPULATED` must produce:

```text
information_state = NOT_POPULATED
typed values = null
origin = null
verification_state = UNVERIFIED
confidence = null
```

`MISSING` and `NOT_APPLICABLE` remain meaningful manual states and therefore use the existing manual provenance/review semantics.

Update untouched/materialization/type-change/requirement logic accordingly.

### Migration

Create a migration that maps:

```text
NOT_EXTRACTED -> NOT_POPULATED
UNKNOWN       -> MISSING
```

The final PostgreSQL enum and Python enum should no longer contain `UNKNOWN` or `NOT_EXTRACTED`.

Registry-v1 must remain unchanged.

---

# 3. Unified Equipment editor

The Equipment detail modal/sheet should own one draft across:

```text
General
Attributes
Terminals
```

Switching tabs must preserve unsaved changes.

Remove:

```text
Save General
per-attribute Save buttons
per-terminal Save buttons
```

Use one sticky Save button in the top-right next to Close.

Save should be disabled when:

```text
nothing changed
revision is read-only
equipment is removed
save is already in progress
```

Support:

```text
Ctrl+S
Cmd+S
```

using the same Save operation.

### Unsaved close

If the editor is dirty and the user tries to close it, show:

```text
Save changes
Discard changes
Keep editing
```

A failed save keeps the editor open and preserves the draft.

---

# 4. Transactional Equipment save API

One Equipment Save should result in one backend transaction.

Add an editor endpoint or equivalent revision-scoped API that can save changed:

```text
General fields
Attributes
Custom terminals
```

together.

The frontend should submit only changed values.

The backend must validate and commit the entire draft atomically.

If any change fails:

```text
rollback everything
```

Do not implement this by calling multiple existing methods that each commit independently. Refactor shared service logic as needed.

Keep the existing fine-grained APIs for compatibility.

After save, return the fresh canonical:

```text
equipment
attributes
terminals
```

and reset the frontend draft from that response.

Preserve Phase 5G precision behavior:

```text
NUMBER  -> lossless string
INTEGER -> lossless string
```

including:

```text
9007199254740993
```

BOOLEAN `PRESENT` must still require an explicit True/False selection.

---

# 5. Nodes table

Replace the current Node cards with a table.

Suggested columns:

```text
Node
Type
Equipment / Owner
Terminal
Lifecycle
```

Rows must be clickable and open the node detail editor.

For electrical nodes, allow normal edit/remove/restore behavior.

For profile-managed terminals:

- show owning equipment and terminal role;
- indicate they are application-managed;
- do not allow terminal-key editing;
- do not allow independent removal while required by the current profile.

Custom terminals retain normal manual behavior.

Keep:

```text
Add Electrical Node
```

for non-equipment electrical nodes.

Ordinary equipment terminals should now come from the equipment profile.

---

# 6. Connections table

Replace Connection cards with a table.

Suggested columns:

```text
From
To
Type
Direction
Voltage
Phase
Lifecycle
```

Rows must be clickable and open the connection detail editor.

Retain existing connection editing, remove/restore, lifecycle and endpoint rules.

Restoring a connection still requires both endpoint nodes to be active.

Keep:

```text
Add Connection
```

---

# 7. Preserve existing architecture

Do not introduce:

```text
EngineeringModel table
Evidence
ExtractionCandidate
ExtractionRun
AI extraction
entity resolution
automatic SLD interpretation
validation/reconciliation workflows
ProtectionFunction
study configurations
graph visualization
ETAP/SKM/EasyPower integration
parent_equipment_id
```

`ProjectRevision`, `EquipmentLineage`, `Equipment`, `EquipmentAttribute`, `ModelNode`, and `ModelConnection` remain the Phase 5 foundation.

Do not modify registry-v1.

---

# 8. Testing

Reuse existing tests wherever possible and add focused coverage for the new behavior.

At minimum verify:

```text
information-state migration
NOT_POPULATED reset semantics
UNKNOWN removed

terminal profiles for all equipment types
automatic terminal creation
existing-terminal backfill
custom-terminal preservation
safe type-change reconciliation

transactional equipment save
rollback on partial failure
single frontend Save flow
unsaved-close behavior

Node table row opens editor
Connection table row opens editor

INTEGER precision remains exact
BOOLEAN still requires explicit selection
read-only behavior remains enforced
revision carry-forward remains correct
```

Avoid a large redundant combinatorial test suite.

Run the full existing backend and frontend regression suites.

Also validate migration from an empty disposable database to head and upgrade representative pre-refinement data.

---

# 9. Documentation

Update current-facing Phase 5 documentation and ADR-007 as needed to reflect:

```text
automatic terminal profiles
custom terminals as exceptional
NOT_POPULATED semantics
UNKNOWN removal
transactional Equipment editor
Node/Connection table UX
```

Do not rewrite historical Phase 5A–5G handoffs.

Create:

```text
docs/PHASE5_AUTHORING_REFINEMENT_HANDOFF.md
```

Include the final implementation decisions, migration details, tests/results, remaining debt, and final re-freeze verdict.

Current status should end as:

```text
Phase 5 complete / re-frozen
Phase 6 next / not started
```

---

# Acceptance criteria

Complete only when:

```text
NOT_EXTRACTED is gone.
UNKNOWN is gone.
NOT_POPULATED is the default empty state.

Existing data migrates safely.

Every equipment type has an explicit terminal profile.

New equipment automatically receives its normal terminals.

Profile terminals are system-managed.
Custom terminals remain possible.

Unsafe type changes cannot silently destroy topology.

Nodes use clickable tables.
Connections use clickable tables.

Equipment has one draft and one sticky top Save button.

No per-attribute or Save General buttons remain.

One Equipment Save uses one atomic backend transaction.

Dirty-close protection works.

NUMBER/INTEGER precision remains lossless.
BOOLEAN requires explicit selection.

Registry-v1 is unchanged.

No Phase 6 functionality is introduced.

Full backend/frontend/migration regression passes.
```

When complete, finish with:

```text
Phase 5 authoring refinement is complete. Phase 5 is re-frozen and ready to proceed to Phase 6.
```

Do not begin Phase 6.