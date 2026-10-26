# PowerForge Phase 5F — Basic Engineering Model Workspace UI

You are implementing **Phase 5F only** of PowerForge.

Phases 5A–5E are complete and accepted. Phase 5F adds the first usable browser workspace for manually authoring and reviewing the revision-scoped canonical engineering model already implemented in the backend.

Phase 5F is primarily a **frontend/UI phase**. Do not proceed to Phase 5G or Phase 6.

## 1. Authoritative inputs

Before editing, read and understand:

```text
docs/specs/phase-5-engineering-model.md
decisions/ADR-007-canonical-engineering-model-persistence.md
docs/ENGINEERING_MODEL.md
docs/TOPOLOGY.md
docs/PHASE5D_HANDOFF.md
docs/PHASE5E_HANDOFF.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
cursor/phase4_5_document_workspace_ui.txt
```

Inspect the accepted frontend patterns in:

```text
apps/web/src/app/projects/[projectId]/revisions/[revisionId]/page.tsx
apps/web/src/components/revision-documents.tsx
apps/web/src/components/document-list.tsx
apps/web/src/components/document-detail-drawer.tsx
apps/web/src/components/document-workspace-toolbar.tsx
apps/web/src/components/project-detail.tsx
apps/web/src/components/read-only-banner.tsx
apps/web/src/components/ui/
apps/web/src/lib/api.ts
apps/web/src/lib/documents.ts
apps/web/src/lib/projects.ts
apps/web/src/components/revision-documents.test.tsx
apps/web/src/components/document-editor.test.tsx
apps/web/src/components/projects.test.tsx
apps/web/src/lib/api.test.ts
```

Inspect but do not redesign the accepted Phase 5E API contract:

```text
services/api/src/powerforge_api/routers/model.py
services/api/src/powerforge_api/schemas/model.py
services/api/src/powerforge_api/routers/engineering_model.py
```

Source-of-truth order:

1. this Phase 5F prompt for Phase 5F UX clarifications and scope;
2. the approved Phase 5 specification;
3. ADR-007;
4. accepted Phase 5A–5E implementation/handoffs;
5. existing frontend interaction/design conventions.

If a genuine blocking API gap is discovered, report it rather than inventing new canonical semantics.

---

## 2. Baseline

Start from the accepted Phase 5E implementation.

```text
branch:
codex/phase-5e-model-apis

accepted head:
aed2e18fce9efcdadab04ca1d087c26d81148d64
```

This baseline includes the accepted fixes for empty PATCH rejection and sanitized `InconsistentEquipment` HTTP 500 behavior.

If Phase 5E has since been merged to `main`, use the updated `main`.

Do not start from the initial pre-fix Phase 5E commit.

---

## 3. Scope

Phase 5F MUST deliver:

```text
Documents | Engineering Model revision-workspace switch

Equipment:
    list
    search
    type filter
    lifecycle filter
    create
    detail Sheet
    general metadata/type edit
    remove/restore

Attributes:
    registry-generated editor
    information-state controls
    typed value controls
    input-unit selection
    Required/Critical/Conditional indicators

Topology:
    equipment terminal management
    electrical node management
    connection list
    connection create/edit
    remove/restore actions

Read-only behavior for non-writable revisions/projects
Focused frontend tests and full frontend validation
```

Phase 5F MUST NOT implement:

```text
graph visualization
React Flow
single-line rendering
automatic graph layout
AI extraction or AI-generated model actions
Evidence or ExtractionCandidate UI
entity resolution
conflict reconciliation
persistent validation findings
engineer verification actions
protection-function UI
operating/study scenario UI
study calculations
ETAP/SKM/EasyPower integration
report generation
authentication/users
new database schema
new canonical domain concepts
repository-wide pagination framework
```

---

## 4. No migration and normally no backend change

Database head remains:

```text
0009_topology_persistence
```

Do not add a migration.

The accepted Phase 5E endpoints are sufficient. Do not add frontend-specific endpoints such as:

```text
entire-model
bulk-attribute-write
nodes-by-equipment
graph
completeness/readiness
```

A narrowly scoped Phase 5E correctness fix is allowed only if a real bug is found during implementation; document it explicitly.

---

## 5. Preserve the existing frontend design language

Reuse the current PowerForge primitives and interaction patterns:

```text
Card
Button
Field
Input / Textarea
SearchField
SegmentedControl
Sheet
ConfirmDialog
DropdownMenu
Badge / Chip
existing typography, spacing, slate palette, responsive tables
```

Do not add a second component library or restyle unrelated pages.

Do not add React Query, Redux, Zustand, MobX, or React Flow for this phase.

Local React state/effects are sufficient and consistent with the existing app.

---

## 6. Revision workspace switch

The revision page currently renders the Documents workspace directly.

Introduce a small client workspace controller, conceptually:

```text
RevisionWorkspace
```

receiving:

```text
projectId
revisionId
canMutate
```

It exposes:

```text
Documents | Engineering Model
```

using the existing `SegmentedControl` or an equally consistent control.

The shared revision header and `ReadOnlyBanner` remain outside/above the selected workspace.

Keep `RevisionDocuments` functionally unchanged as much as possible.

---

## 7. Workspace URL behavior

Do not add a new route.

Use the existing revision URL with:

```text
no workspace query -> Documents
?workspace=model   -> Engineering Model
```

Documents remains the default for backward compatibility.

When switching to Engineering Model:

```text
set workspace=model
remove document=<id>
```

When switching back to Documents:

```text
remove workspace
remove equipment=<id>
```

Preserve unrelated query parameters.

---

## 8. Equipment deep-link behavior

Use:

```text
?workspace=model&equipment=<equipment_id>
```

for an open Equipment detail Sheet.

Opening a row sets `equipment`.
Closing the Sheet removes it.

A direct URL must be able to open a valid Equipment even if search/type/lifecycle filters currently exclude it. Use GET Equipment rather than relying only on the visible list.

A scoped-out/missing Equipment ID should be cleared cleanly with a useful non-destructive message.

---

## 9. Engineering Model subviews

Inside Engineering Model expose two compact subviews:

```text
Equipment
Topology
```

Use `SegmentedControl`.

Default:

```text
Equipment
```

Topology is list/form based only. No graph canvas.

---

## 10. Frontend model API module

Create a dedicated frontend module, conceptually:

```text
apps/web/src/lib/engineering-model.ts
```

It owns types and API functions for:

```text
registry
Equipment
EquipmentAttribute
ModelNode
ModelConnection
```

Implement equivalents of:

```text
getEngineeringRegistry

listEquipment
getEquipment
createEquipment
updateEquipment
removeEquipment
restoreEquipment

listAttributes
setAttribute

listNodes
createTerminal
createElectricalNode
updateNode
removeNode
restoreNode

listConnections
createConnection
updateConnection
removeConnection
restoreConnection
```

Use the existing `request(...)` and `apiErrorOf(...)` conventions.

Do not scatter raw fetch calls throughout components.

---

## 11. The frontend MUST NOT duplicate registry-v1

This is a critical invariant.

Do not hardcode in TypeScript:

```text
the 20 equipment types
per-type attributes
attribute display names
enum choices
canonical units
supported input units
Required/Critical metadata
requirement metadata
```

Fetch:

```text
GET /api/engineering-model/registry
```

and use it as the form source.

Frontend `equipment_type` may simply be represented as a string/key. Valid choices and labels come from the registry response.

Closed non-registry API vocabularies such as lifecycle, node kind, connection kind/direction, information state, verification state, and origin may be typed locally.

---

## 12. Registry response types

Model enough of the current response to drive forms:

```text
RegistryResponse
    registry_version
    equipment_types
    unit_families
    requirement_rules

EquipmentDefinition
    key
    display_name
    attributes
    requirements

AttributeDefinition
    key
    display_name
    value_type
    canonical_unit
    required
    critical
    allowed_values
    notes
    display_order
    requirement_group
    requirement_condition
    supported_input_units

UnitFamilyDefinition
    family
    default_unit
    supported_input_units
    notes
```

Preserve server ordering.

Load the registry once when Engineering Model is first needed and keep it in workspace state. Do not refetch it per row or per save.

On registry load failure, show a workspace error with Retry; do not break Documents.

---

## 13. Equipment toolbar

The Equipment view must include:

```text
heading/count
search
equipment type filter
lifecycle filter
Add Equipment
```

Follow the document-workspace visual language.

Recommended layout:

```text
Equipment <count>                         [Add Equipment]

[ Search equipment… ] [ Type ] [ Active | Removed | All ]
```

Adapt responsively.

---

## 14. Equipment search/filtering

Use Phase 5E server-side search.

Search covers tag/name/description and should be debounced around 300 ms, with stale-response protection like `RevisionDocuments`.

Do not load everything and implement primary search only client-side.

Type-filter options come from registry definitions:

```text
label = display_name
value = key
```

Lifecycle filter:

```text
Active
Removed
All
```

Default Active.

---

## 15. Equipment list

Use the existing responsive Card/table pattern.

Recommended columns:

```text
Equipment
Type
State
Actions
```

Primary human label:

1. tag if present;
2. otherwise name;
3. otherwise registry equipment display name.

Secondary text may show name/description as space permits.

Do not make raw UUIDs the normal primary label.

Removed rows should be subdued.

Row click and Enter/Space open the Equipment detail Sheet, following `DocumentList` accessibility behavior.

Show useful empty states for:

```text
no equipment in revision
no search matches
no results for current filters
```

When truly empty and writable, offer Add Equipment.

---

## 16. Add Equipment

Use a lightweight Sheet or existing-style modal interaction. A Sheet is preferred.

Fields:

```text
Equipment Type   required, from registry
Tag              optional
Name             optional
Description      optional
```

Do not render all attributes in the creation form.

After successful POST:

1. refresh Equipment list;
2. close create UI;
3. optionally open the created Equipment detail Sheet.

Use the returned object; do not synthesize an ID/state client-side.

Duplicate-looking tags must not be client-blocked because duplicate tags are valid in Phase 5.

---

## 17. Equipment detail Sheet

Use the existing right-side `Sheet` pattern.

It may be moderately wider than the document drawer if necessary, but remain responsive and bounded.

Header should show a human equipment label, type, lifecycle state, Close, and relevant actions.

Inside the Sheet expose:

```text
General
Attributes
Terminals
```

with `SegmentedControl` or equivalent.

Default General.

No Graph tab.

---

## 18. General editor

Editable fields:

```text
Equipment Type
Tag
Name
Description
```

Use an explicit Save button.

Track the loaded object versus draft and PATCH only changed fields.

Never send an empty PATCH.

Explicitly clearing tag/name/description must send JSON null.

Do not convert untouched blank UI strings into unintended null updates.

Equipment Type choices come from registry metadata.

---

## 19. Equipment type changes

Backend type-change behavior is authoritative.

The UI should:

- submit the selected type;
- surface a 409 type-change conflict clearly;
- preserve draft state on failure;
- never imply meaningful incompatible attributes were discarded.

After a successful type change:

```text
refresh Equipment
refresh Attributes
use the new registry EquipmentDefinition
```

Do not reimplement the backend compatibility/type-change algorithm in TypeScript.

---

## 20. Equipment lifecycle

Before removing Equipment, show a ConfirmDialog with copy equivalent to:

> Removing this equipment also removes its terminal nodes and active incident connections. Restoring the equipment restores its terminals, but does not automatically restore those connections.

This consequence must not be hidden.

Removed Equipment remains viewable. In writable revisions show Restore instead of edit controls until restored.

Do not promise or offer automatic connection restoration.

On remove/restore, refresh relevant Equipment/detail/topology state.

---

## 21. Registry-driven attribute editor

The editor MUST be generated by combining:

```text
registry EquipmentDefinition.attributes
+
GET equipment/{id}/attributes persisted rows
```

Do not create hardcoded per-type forms such as:

```text
BusForm
TransformerForm
BreakerForm
MotorForm
```

A single generic editor must support all registry types.

Render attributes in registry display order. Do not alphabetically reorder them.

---

## 22. Attribute presentation

Each attribute should show:

```text
display_name
information state
Required badge when required
Critical badge when critical
Conditional badge when conditional metadata exists
optional notes/condition hint
typed editor when state = PRESENT
unit selector when applicable
Save when writable
```

Prefer `display_name` over raw key.

Required, Critical, and Conditional are independent concepts. Do not treat Critical as Required.

Conditional indication can use `requirement_group` / `requirement_condition` and supplied registry metadata.

---

## 23. Do not recreate the full requirement evaluator in JavaScript

Phase 5A already owns deterministic requirement evaluation in Python, and 5F has no dedicated readiness endpoint.

Display registry metadata and condition/rationale text only.

Do not invent:

```text
completeness percentage
study-ready badge
model-health score
client-side full requirement engine
```

Phase 10 owns full validation/readiness workflows.

---

## 24. Manual information states

Manual saves may send only:

```text
PRESENT
UNKNOWN
MISSING
NOT_APPLICABLE
```

Persisted `NOT_EXTRACTED` or `CONFLICTING` may be displayed but must not be offered as ordinary manual save states.

Use human labels.

For non-PRESENT state:

```text
hide/disable typed value
hide/disable unit selector
send only information_state
```

Never send stale value/unit with UNKNOWN, MISSING, or NOT_APPLICABLE.

---

## 25. PRESENT controls by value type

Render from registry `value_type`:

```text
ENUM
    select from allowed_values

BOOLEAN
    explicit True/False or Yes/No control

NUMBER
    decimal-safe text input, inputMode="decimal"

INTEGER
    integer text input, inputMode="numeric"

TEXT
    normal text input
```

ENUM options come directly from registry values.

BOOLEAN must submit actual JSON booleans, not strings or 0/1.

TEXT is sent as text without technical interpretation.

---

## 26. Decimal precision is mandatory

API NUMBER values are lossless strings.

Keep NUMBER input in local state as a string and submit the trimmed string.

Do not call JavaScript `Number(...)`, `parseFloat`, or equivalent before submission.

This value must round-trip exactly through the frontend request body:

```text
0.1234567890123456789012345678901234
```

INTEGER should likewise remain text in form state and be submitted without unsafe float conversion; let the server enforce integrality.

---

## 27. Units

For NUMBER/INTEGER attributes with unit metadata, render a unit selector from:

```text
attribute.supported_input_units
```

Do not hardcode per-attribute unit lists.

Existing canonical PRESENT values load as:

```text
value input = canonical value string
unit = persisted canonical unit
```

If the engineer changes unit, do not client-convert the number. The selected unit determines how the typed number will be interpreted on save.

Server normalization remains authoritative.

After save, replace the local row with the server's canonical response.

---

## 28. Per-attribute save

Use explicit per-attribute Save.

Do not send requests on every keystroke and do not fake a bulk transaction.

Each attribute row may independently track:

```text
draft
dirty
saving
error
```

For 422, show the API detail near the row and preserve the draft.

For stale 404/409/lifecycle cases, refresh canonical state.

---

## 29. Attribute provenance display

You may show read-only metadata such as:

```text
origin
verification_state
confidence
information_state
```

Use accurate wording.

`ENGINEER_REVIEWED` is **not** `ENGINEER_VERIFIED`.

There is no Verify/Approve action in Phase 5F.

---

## 30. Terminals subview

Terminals belong in the selected Equipment Sheet.

Fetch nodes with lifecycle `ALL`, then client-filter:

```text
kind = EQUIPMENT_TERMINAL
equipment_id = selected Equipment id
```

Do not add a node-by-equipment backend endpoint.

Show:

```text
terminal_key
optional label
lifecycle state
actions
```

---

## 31. Add/edit terminal

When Equipment is ACTIVE and revision writable, allow:

```text
terminal_key   required
label          optional
```

POST with:

```text
kind = EQUIPMENT_TERMINAL
equipment_id = selected Equipment
```

Do not auto-generate terminals from equipment type.

Allow PATCH of terminal_key/label only.

Never expose kind/equipment ownership edits.

Never submit an empty PATCH.

---

## 32. Terminal remove/restore

Before removing a terminal, warn:

> Removing this terminal also removes active connections incident to it. Restoring the terminal does not automatically restore those connections.

Use ConfirmDialog.

A terminal may be restored only when the parent Equipment is ACTIVE and revision writable. If Equipment is removed, prefer telling the user to restore Equipment first rather than offering a known-invalid action.

---

## 33. Topology workspace

The Topology subview contains two list/form sections:

```text
Nodes
Connections
```

No visual graph.

When Topology becomes active, fetch:

```text
nodes
connections
equipment lifecycle ALL
```

Equipment is used to resolve human terminal labels. Avoid per-terminal Equipment GET/N+1 behavior.

Provide a shared lifecycle filter:

```text
Active
Removed
All
```

Default Active.

---

## 34. Human node labels

Do not fill endpoint selectors with bare UUIDs.

For EQUIPMENT_TERMINAL use:

```text
Equipment tag if present
else Equipment name
else registry type display name
+
terminal_key
+
optional label
```

Example:

```text
SWGR-1 · LINE
```

For ELECTRICAL_NODE use:

```text
label if present
else "Electrical node · <short id>"
```

If two nodes resolve to the same human label, append a short ID disambiguator.

---

## 35. Electrical node management

Global Topology UI creates pure electrical nodes only.

Add Electrical Node fields:

```text
label optional
```

POST `kind = ELECTRICAL_NODE`.

Terminals are created from Equipment details.

Allow editing an electrical node label only. Do not allow changing node kind.

Before node removal, warn that active incident connections will also be removed.

Node restore does not restore connections; do not imply otherwise.

After node remove/restore refresh both nodes and connections.

---

## 36. Connection list

Use a simple responsive Card/table.

Recommended columns:

```text
From
To
Kind / Direction
Voltage / Phase
State / Actions
```

Parallel connections are separate canonical objects and MUST NOT be deduplicated.

---

## 37. Add Connection

Provide an explicit form/Sheet with:

```text
From Node              required
To Node                required
Connection Kind        default ELECTRICAL
Direction              default UNDIRECTED
Phase Configuration    optional
Nominal Voltage        optional
Voltage Input Unit     optional
```

Endpoint selects use ACTIVE nodes only and human labels.

The normal UI should prevent choosing the same node for both endpoints; backend remains authoritative.

Connection kind labels:

```text
Electrical
Grounding
Other
```

Direction labels:

```text
Undirected
Nominal from → to
```

Do not describe nominal direction as calculated load-flow direction.

---

## 38. Connection voltage

Keep connection voltage as a string in frontend state.

Do not use JavaScript Number conversion.

Derive input unit choices from registry `unit_families` voltage metadata rather than hardcoding V/kV/MV.

If no voltage is entered, omit both voltage and unit.

To clear an existing voltage on PATCH, send the accepted explicit-null shape from Phase 5E.

After save, show the server-returned canonical kV value/unit.

---

## 39. Connection edit/lifecycle

Allow editing active connections:

```text
from_node_id
to_node_id
connection_kind
direction
phase_configuration
nominal_voltage
nominal_voltage_unit
```

PATCH only changed fields. Never submit `{}`.

Removed connections must be restored before edit.

Restore only if endpoints remain active; on conflict, show API message and refresh node/connection state.

Do not restore endpoints automatically.

---

## 40. No topology inference

The UI must never infer connections from:

```text
tag
equipment type
terminal name
voltage
list order
source/load role
```

Every topology change is an explicit engineer action.

---

## 41. Read-only behavior

The server-rendered revision page already computes `canMutate` from project/revision lifecycle. Reuse it.

When `canMutate = false`:

```text
hide Add Equipment
hide Save actions
hide remove/restore
hide Add Terminal
hide Add Electrical Node
hide Add Connection
render model data read-only
```

Search/filter/navigation remain usable.

The backend remains authoritative; `canMutate` is presentation state, not authorization.

---

## 42. Stale read-only state

A revision/project may become read-only after initial render.

Handle backend codes:

```text
revision_read_only
archived_project
cancelled_project
```

using the same philosophy as Documents:

1. show a warning;
2. stop offering further mutation locally;
3. `router.refresh()`;
4. reload relevant model data.

Avoid repeating failed mutation attempts from stale client state.

A small neutral extraction of shared helpers such as `canMutate`, `readOnlyReason`, or `isReadOnlyErrorCode` into a shared module is acceptable if it is minimal and existing document behavior/tests remain intact.

---

## 43. API error behavior

For 422:

```text
show detail near the relevant form
preserve draft
```

For 404/409 stale object/lifecycle errors:

```text
show warning
refresh relevant canonical state
```

For 500:

```text
show the API safe message
never expose stack traces
```

Do not relabel server consistency failures as client validation.

Use existing small inline success/warning/error message style. Do not introduce a toast framework.

---

## 44. Loading and responsiveness

Use lightweight loading states consistent with Documents:

```text
equipment table skeleton
attribute section loading
topology section loading
button saving state
```

Do not blank unrelated controls unnecessarily.

Keep the workspace usable below desktop widths. Follow DocumentList's stacked-row strategy below `md` and normal table layout on larger screens.

The existing Sheet full-width-small-screen behavior should be preserved.

---

## 45. Accessibility

At minimum:

- inputs/selects have labels;
- clickable rows are keyboard operable;
- Sheet keeps existing focus/Escape behavior;
- confirm dialogs stay modal;
- status/errors use appropriate roles;
- read-only/disabled state is semantic, not purely visual;
- segmented controls have accessible group labels;
- icon-only actions have accessible names.

---

## 46. Suggested component decomposition

Avoid one giant TSX file.

A reasonable decomposition is:

```text
revision-workspace.tsx

engineering-model-workspace.tsx
engineering-model-toolbar.tsx

equipment-list.tsx
equipment-create-sheet.tsx
equipment-detail-drawer.tsx
equipment-general-panel.tsx
equipment-attributes-panel.tsx
equipment-terminals-panel.tsx

topology-workspace.tsx
node-list.tsx
connection-list.tsx
connection-editor-sheet.tsx
```

Exact names are flexible. Keep responsibilities narrow.

Reuse existing UI primitives before adding new ones.

---

## 47. Preserve Documents and revision creation

Do not regress:

```text
document search/filters
upload/reuse
document detail drawer
classification actions
page viewer
URL document selection
read-only behavior
```

Phase 5C's independent revision creation controls already exist:

```text
Carry forward documents
Carry forward engineering model
```

Do not redesign them in Phase 5F. Keep their tests passing.

---

## 48. Revision system metadata

Phase 5F does not need a new editor for:

```text
system_frequency
system_phase_count
```

Do not add a new model-metadata endpoint or expand scope around this. These values may be displayed secondarily if useful, but editing is not a Phase 5F requirement.

---

## 49. Explicit later-phase exclusions

There must be no Phase 5F actions such as:

```text
Extract from documents
AI Fill
Generate model
Infer topology
Suggest connection
View evidence
Resolve conflict
Verify
Approve all
Study Ready
Run short circuit
Export to ETAP
```

Stored origin/verification metadata may be displayed read-only, but full Evidence begins in Phase 6, validation in Phase 10, verification authority in Phase 11, visualization in Phase 12, and study tools in Phase 13.

---

## 50. Frontend API tests

Add focused tests for `lib/engineering-model.ts` covering representative requests:

```text
registry GET

equipment list query:
    search
    equipment_type
    lifecycle_status

equipment create/update/remove/restore

attribute PUT:
    decimal string
    boolean
    state-only

nodes:
    create terminal/electrical
    update
    remove/restore

connections:
    create
    PATCH clear voltage
    remove/restore
```

Do not retest every server validation rule; Phase 5E owns backend API tests.

---

## 51. Revision workspace tests

Test at minimum:

1. Documents is default;
2. `?workspace=model` opens Engineering Model;
3. switching to model clears stale `document` selection;
4. switching to documents clears stale `equipment` selection;
5. Documents still renders normally;
6. shared read-only banner remains above either workspace.

Do not duplicate the existing document suite.

---

## 52. Equipment UI tests

Cover:

```text
registry loads
type filter options come from registry
search is debounced/server-backed
Active/Removed/All filters
Add Equipment sends registry key
duplicate-looking tags are not client-blocked
row opens detail
?equipment=id opens via GET even when filtered out
removed Equipment shows Restore rather than edit
read-only mode hides mutation controls
```

General editor tests should verify:

```text
unchanged fields are omitted
explicit cleared text -> null
successful type change refreshes attributes
409 type conflict preserves draft
empty PATCH is never sent
```

---

## 53. Registry-driven attribute tests

Use a representative mocked registry EquipmentDefinition containing:

```text
NUMBER with units
INTEGER
ENUM
BOOLEAN
TEXT
Required
Critical
Conditional
```

Verify:

- order follows registry;
- controls derive from `value_type`;
- enum choices derive from registry;
- unit choices derive from `supported_input_units`;
- Required/Critical/Conditional render independently;
- no per-equipment hardcoded form is necessary.

Add a precision regression proving this exact string reaches the request body unchanged:

```text
0.1234567890123456789012345678901234
```

State tests should verify PRESENT versus UNKNOWN/MISSING/NOT_APPLICABLE behavior and that state-only saves do not send stale values.

---

## 54. Terminal/topology UI tests

Terminal tests should cover:

```text
filter terminals to selected Equipment
add terminal
edit key/label
remove warning mentions incident connections
restore behavior
read-only controls hidden
```

Topology tests should cover representative behavior:

```text
human terminal labels
electrical-node fallback labels
add electrical node
endpoint selectors
parallel connections remain separate rows
connection create/edit
voltage remains string
voltage units derive from registry unit-family metadata
node removal refreshes connection list
remove/restore behavior
read-only mode
```

Do not reproduce Phase 5D database-constraint tests in React.

---

## 55. Stale read-only regression test

One representative test should start with `canMutate=true` but have the backend return a read-only code.

Verify:

```text
warning shown
router refresh/equivalent triggered
further mutation is treated as unavailable
model reload requested
```

Do not repeat for every action.

---

## 56. Testing philosophy

Test the new frontend contracts and frontend-specific risks, not every accepted backend invariant again.

High-value risks are:

```text
hardcoded registry forms
precision loss
wrong PATCH/null semantics
stale/read-only state
accidental provenance/verification controls
hidden topology cascade consequences
document workspace regression
```

Prefer focused representative tests and parameterization over raw test count.

---

## 57. Required validation

Mandatory frontend checks:

```sh
cd apps/web
npm run lint
npm test
npx tsc --noEmit
npm run build
```

Also run:

```sh
git diff --check
```

If no Python/backend files change, full destructive live integration is not required merely because the frontend changed. Run normal backend regression if practical:

```sh
.venv/bin/pytest -q
```

If any backend/API Python file changes, run the full relevant backend suite and live integration against a disposable PostgreSQL database.

Never run destructive integration against the development database.

---

## 58. Browser/manual smoke check

If a browser/manual environment is available, smoke-check:

```text
revision page
Documents unchanged
switch to Engineering Model
add/open/edit Equipment
edit one numeric/unit attribute
add terminal
open Topology
add electrical node
create connection
read-only revision hides mutation controls
```

If no browser/manual tool is available, state that explicitly in the handoff. Do not claim visual validation that did not occur.

---

## 59. Dependencies

Prefer zero new runtime dependencies.

Do not add React Flow, a global state library, or a data-fetching framework.

If any dependency is added, justify it in the handoff.

---

## 60. Documentation

Update current-facing docs as appropriate:

```text
docs/ENGINEERING_MODEL.md
docs/TOPOLOGY.md
docs/ARCHITECTURE.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
```

Create:

```text
docs/PHASE5F_HANDOFF.md
```

Do not rewrite historical Phase 5A–5E handoffs.

After implementation is genuinely complete:

```text
5A implemented
5B implemented
5C implemented
5D implemented
5E implemented
5F implemented
5G next
```

Phase 5 as a whole remains incomplete until 5G.

---

## 61. PHASE5F_HANDOFF requirements

Record:

1. baseline branch/commit;
2. changed frontend files;
3. workspace query/URL behavior;
4. component structure;
5. registry loading/caching approach;
6. frontend API/types added;
7. Equipment list/search/filter behavior;
8. Equipment create/detail behavior;
9. general PATCH/null semantics;
10. type-change handling;
11. attribute editor behavior by value type;
12. Decimal precision strategy;
13. unit-selection strategy;
14. Required/Critical/Conditional display;
15. information-state behavior;
16. terminal management behavior;
17. topology node/connection behavior;
18. human node-label strategy;
19. remove/restore warnings;
20. read-only/stale state behavior;
21. tests added;
22. exact lint/test/typecheck/build results;
23. backend regression result if run;
24. browser/manual smoke result or explicit lack thereof;
25. dependencies added, ideally none;
26. deviations/technical debt;
27. confirmation no migration/new API was required unless explicitly documented;
28. confirmation no graph/AI/evidence/validation/verification/study scope leaked in.

---

## 62. Phase 5G boundary

Do not begin Phase 5G.

Phase 5G owns final Phase 5 hardening, broader regression/performance review, remaining technical debt, documentation reconciliation, clean-stack validation, and final Phase 5 freeze.

Do not turn 5F into a general cleanup phase.

---

## 63. Acceptance criteria

Phase 5F is complete only when all of the following are true:

- revision page exposes `Documents | Engineering Model`;
- Documents remains default and existing functionality is preserved;
- Engineering Model loads registry metadata dynamically;
- frontend does not duplicate the canonical equipment registry;
- Equipment list supports search/type/lifecycle filtering;
- Add Equipment uses registry-provided types;
- Equipment detail Sheet supports General, Attributes, Terminals;
- Equipment edits preserve omitted-vs-null semantics;
- frontend never sends empty PATCHes;
- type-change conflicts are surfaced without silent data loss;
- removed Equipment can be viewed/restored;
- Equipment removal warns about terminal/connection cascade;
- attribute editor is generic across registry types;
- registry display order is preserved;
- Required/Critical/Conditional are distinct;
- manual states are PRESENT/UNKNOWN/MISSING/NOT_APPLICABLE;
- non-PRESENT saves do not include stale values;
- NUMBER values preserve exact decimal strings;
- INTEGER avoids unsafe floating conversion;
- BOOLEAN sends actual JSON booleans;
- ENUM choices come from registry;
- units come from registry metadata;
- server remains responsible for unit conversion;
- terminal management is explicit and Equipment-scoped;
- terminal removal warns about incident connections;
- Topology is list/form based with no graph;
- electrical nodes can be created/edited/removed/restored;
- connection endpoints use human labels;
- connections can be created/edited/removed/restored;
- parallel connections remain separate;
- connection voltage is decimal-safe;
- voltage-unit choices derive from registry unit-family metadata;
- read-only revisions are fully viewable;
- mutation controls are unavailable when read-only;
- stale read-only conflicts trigger refresh behavior;
- no provenance/verification mutation action exists;
- no AI/evidence/reconciliation/validation/study UI exists;
- no migration is added;
- no React Flow is added;
- lint/tests/typecheck/build pass.

---

## 64. End-of-task report

At completion, do **not** proceed to Phase 5G.

Report:

1. branch/base used;
2. files changed;
3. final workspace/component architecture;
4. URL/query behavior;
5. registry-driven form strategy;
6. Equipment workflows;
7. attribute behavior by value type;
8. precision/unit handling;
9. terminal workflow;
10. topology workflow;
11. read-only/stale-state behavior;
12. tests added;
13. exact frontend command results;
14. backend regression result if run;
15. browser/manual smoke result;
16. dependency changes;
17. technical debt/deviations;
18. confirmation no DB migration/new API was required;
19. confirmation no Phase 6+/visualization/study scope leaked in.

If every acceptance criterion passes, finish exactly with:

```text
Phase 5F implementation is complete and ready for review.
```

Do not begin Phase 5G until instructed.
