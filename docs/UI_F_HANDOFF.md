# UI-F — Topology workspace

Implemented on `codex/ui-f-topology-workspace`, based on `main` commit `3565fb5` (UI-A through UI-E). The implementation is in the working tree; no UI-F commit or push has been requested yet. Only the Topology workspace and the shell pieces it needs changed. Documents, Equipment, UI-C pages and the backend are untouched. There is no graph or SLD view.

## Screens and components

- **Page chrome** (`revision-page-content.tsx`, `revision-workspace.tsx`, `engineering-model-workspace.tsx`, `app-frame.tsx`). Topology gets its own stage, like Equipment and Documents. The revision summary, generic read-only banner, Documents / Engineering Model switch, and Equipment / Topology switch are hidden (the sidebar provides that navigation). The top bar uses the UI-C project bar.
- **Header** (`topology-ui.tsx`). Title “Topology”, the subtitle “Manage electrical nodes, equipment terminals, and their connections in {rev}.”, and a status pill: “Editable revision” or “Read-only revision”. On a read-only revision the existing `readOnlyReason` is shown as an amber notice.
- **Summary metrics**. Three cards computed from the `lifecycle_status=ALL` node and connection lists: Active nodes (electrical nodes and terminals), Active connections (current topology links), and Removed objects (history retained).
- **Engineering notice**. The prototype’s blue info copy: “Engineering topology, not a graphical SLD. …” including “An SLD visualization is planned for a later phase.”
- **Registers** (`topology-workspace.tsx`). Two stacked cards, no tabs.
  - Nodes: a 430px search box (“Search nodes or equipment…”) and a Lifecycle select (Active / Removed / All) that filters both registers and clears the selection. Header “Nodes · N”, subtitle about terminals vs standalone junctions, and “Add Electrical Node” when writable. Table columns at 29/20/18/19/14%: Node (plus “Standalone electrical junction”), Type, Equipment, Terminal (plus “Application-managed”), State. Footer count and “Click a row for details.” Empty: “No nodes match this filter.”
  - Connections: header “Connections · N”, subtitle about distinct endpoints and parallel connections, and “Add Connection”. Columns at 24/24/15/15/10/12%: From, To, Kind, Direction, Voltage (exact string plus unit), State. Phase configuration lives in the inspector.
  - Search is client-side: nodes match display name, equipment name, terminal key and label; connections match endpoint names. Rows are keyboard-activatable. Horizontal table scroll wrappers are `relative`.
- **Inspector** (`topology-inspector.tsx`). A modal `Sheet` with the same dark overlay as the Documents inspector: 344px wide (full width at ≤650px). Overlay click, Escape, or Close dismisses it. Header: “Node inspection” / “Connection inspection”, title, and state chip.
  - Node fields: Kind, Equipment, Terminal key, Label (“Not set”), Ownership. Info box is either the managed-terminal copy or the “Restoring a node does not automatically restore connections…” copy.
  - Connection fields: From, To, Kind (title case), Direction, Phase (“Not set”), Nominal voltage. Info box explains that nominal direction is endpoint order, not power flow.
  - Writable actions: Edit on active rows; Remove/Restore on non-managed nodes and on connections. Managed terminals get Edit only. Connection Restore is disabled, with a warning, until both endpoints are active.
  - Workspace messages also appear under the inspector header.
- **Editors**. 495px drawers (`TopologyEditorDrawer`) with title, “Topology · {rev}”, Cancel, and Create / Save changes.
  - Node editor (`model-node-editor.tsx`): “Add Electrical Node” / “Edit Electrical Node” / “Edit Terminal Label”. Disabled kind, owning equipment and profile-managed terminal key, with the prototype help text. Display label (max 120). Custom terminal keys stay editable.
  - Connection editor (`connection-editor-sheet.tsx`): From/To from the active-node list (including the row’s own endpoints if they are removed; the opposite endpoint is disabled). Kind, nominal direction, phase (max 80), voltage as an exact string with registry units. Inline validation: “Select two different active endpoint nodes.” and “Nominal voltage must be a positive finite number.” Server 409/422 `detail` is shown unchanged.
- **Unsaved guard**. Both editors report dirty. Cancel, Escape or overlay click while dirty opens “Discard unsaved changes?” with Keep editing and Discard changes. While dirty, `useNavigationBlocker` guards links, the revision switcher and Back/Forward.
- **Remove / restore**. `ConfirmDialog` at 470px: “Remove node?” with the active incident-connection count and “will NOT restore those connections.”; “Remove connection?” with the soft-remove copy. Restore runs immediately and reports that previous connections remain removed.
- **Read-only**. Add, Edit, Remove and Restore are hidden. Inspecting and searching still work.
- **Tokens**. `design-tokens.css` gained topology max width 1560px, inspector 344px, drawer 495px, and the notice colours.

## URL contract

- Topology: `/projects/{p}/revisions/{r}?workspace=model&view=topology`.
- Selection: `&node={id}` or `&connection={id}` (mutually exclusive). Opening uses `push`, closing uses `replace`. A missing id shows a not-found notice and a Clear selection action.
- `revisionHref` and `clearTopology` drop `node` and `connection` when switching revisions or leaving Topology. Switching to Topology still clears equipment parameters.

## Visual evidence

Prototype states were captured in Chrome at 1440, 1024 and 390 from `powerforge-topology-prototype.html`: overview, managed-terminal / standalone-node / connection inspectors, edit-connection (including validation), add-node, remove confirm, blocked restore, read-only, and empty search. The same Topology states were recaptured from this branch. Reference images are in `apps/web/.visual-artifacts/ui-f/` (git-ignored): `prototype/`, `production/`, `before/`, and `branch-suite/`.

The visual harness now covers `topology-{w}-overview`, `-node-inspector`, `-connection-inspector`, `-edit-connection`, `-add-node`, `-remove-confirm`, `-readonly` and `-empty` at 1440/1024/390, plus the existing `topology-editor` shot. Fixtures include a managed terminal, a custom terminal, a removed node, a removed connection whose restore is blocked, a parallel connection, and voltages. `run.mjs` waits for the first `LINE ↔ Main bus` text (two parallel connections share that label) and opens the Documents unsaved dialog with Close details, because the modal inspector covers the register.

This branch’s harness capture produced 125 shots. A `main` worktree at `3565fb5` produced the 82 overlapping shots through `documents-390-readonly` (the old row-click unsaved step times out under the modal inspector). PNG compare of those 82 names:

- `desktop-topology` and `mobile-topology` changed size, as expected for the new stage.
- Equipment quick-details pages grew by 19px because the new parallel-connection fixture adds a second `LINE ↔ Main bus` row. That is a fixture change, not an Equipment layout change.
- Every other overlapping Documents, Equipment and UI-C page differed by 2–79 anti-aliasing pixels, matching the harness noise documented in UI-D/UI-E.

## Checks run

- `npx vitest run`: 26 files, 341 tests passed. New `topology-workspace.test.tsx` (10 tests) covers metrics and search, the lifecycle filter clearing selection, the modal inspector and overlay close, `?node` / `?connection` deep links, managed terminals without Remove, remove cascade copy, restore gating, exact voltage strings and units, endpoint validation, the unsaved guard, and read-only. `revision-workspace.test.tsx` expects no workspace switch on Topology. `workspace-navigation.test.ts` covers dropping `node` / `connection`.
- `npx tsc --noEmit -p .`: passed. `npx next lint`: no warnings or errors. `npm run build`: passed.
- This branch `node visual/run.mjs capture`: 125 captures passed. Overlap PNG compare against the `main` worktree baseline is described above.
- A Chrome flow check against the Next dev server passed:
  1. A row opens the inspector over the register without changing the table width, and records `?node=`.
  2. Overlay click closes the inspector and strips the parameter.
  3. The deep link reopens after a reload.
  4. Cancel with unsaved edits asks first; Keep editing preserves the draft.
  5. Discard changes closes the editor.
  6. Remove opens the cascade confirmation.
  7. A revision switch from Topology drops the node id.
- No backend tests were run because no backend code changed.

## Deliberate deviations

- The inspector is a modal overlay with a dark backdrop, by user decision, rather than the prototype’s sticky 344px column. A row can’t be selected while it’s open.
- There is no “Demo:” mode select, “Design prototype · No backend” pill, `(prototype)` toast copy, or seed data.
- The connection inspector shows Kind in title case.
- Search and lifecycle filtering are client-side over the full lists.
- The top bar keeps the UI-C project-status pill pattern. The Extraction navigation is omitted.
- Typography keeps the production font and the UI-C scale (13.5px body, 12–12.5px supporting text, weights 400–700).

## Future Backend/API Requirements

| Feature | Current limitation (API examined) | Proposed addition | Priority | UI-F disposition |
| --- | --- | --- | --- | --- |
| Topology summary counts | `GET …/nodes` and `GET …/connections` return `{items}` only | `GET …/topology/summary` → `{active_nodes, active_connections, removed}` | Optional; needed for large revisions | Implemented with the existing lists |
| Search and kind filters | List query is `lifecycle_status` only | `search`, `kind`, `connection_kind` query params | Optional | Client-side search over loaded lists |
| Pagination and sorting | Unpaginated, ordered by `created_at, id` | Cursor pagination plus `sort` | Future phase | No sort controls |
| GET by id | No `GET …/nodes/{id}` or `GET …/connections/{id}` | Single-resource GETs | Recommended for deep links | Deep links scan the full lists |
| Endpoint labels | UI builds labels with `nodeLabels()` | Include `display_label` (and owner tag) on list items | Optional | Client-side labels |
| Kind / direction enums in registry | Only in OpenAPI / `powerforge_topology` enums | Add to `GET /api/engineering-model/registry` | Optional | Hardcoded Electrical / Grounding / Other and direction labels |
| Phase-configuration vocabulary | Free text after trim; no allowed values | Closed list or registry family | Future phase | Free-text field, max 80 |
| Validation report | Consistency is enforced internally; no findings API | `GET …/topology/findings` (dangling nodes, unconnected terminals) | Future phase | Not shown |
| Audit history | Responses expose latest audit fields only | History endpoint per object | Future phase | Not shown |
| Bulk remove / restore | Per-id POST only | Batch lifecycle endpoint | Future phase | One object at a time |
| Incident-connection count | Derived client-side from the full connection list | `incident_active_count` on node responses | Optional | Client-side count in the remove dialog |

All proposals must stay revision-scoped, preserve ACTIVE/REMOVED lifecycle, keep application-managed terminals profile-authoritative, and keep connection restore conservative (endpoints must be active; connections are never auto-restored).

## Remaining risks

- The visual harness compares at `threshold: 0` and has a pixel-noise floor. Reviewers should rely on geometry and computed-style results.
- The navigation guard has the same limits as UI-D/E. A future programmatic `router.push` that bypasses `guardNavigation` would bypass the guard.
- Counts, search and cascade numbers are computed from the full lists, which will get heavy for large revisions until the summary, search and pagination endpoints exist.
- Deep links require the full node/connection lists because there is no GET-by-id.

UI-G and later phases were not started.
