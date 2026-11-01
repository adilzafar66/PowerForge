# UI-D — Equipment workspace

Implemented on `codex/ui-d-equipment-workspace`, based on accepted `main` commit `1385019` (includes UI-A/UI-B/UI-C and the frontend component/design-token refactor). The implementation is in the working tree; no UI-D commit or push has been requested yet. Only the Equipment workspace changed. Documents, Topology, UI-C pages and the backend are untouched.

## Screens and components

- **Register** (`equipment-workspace.tsx`). Prototype header (“Engineering Model / Equipment”, 29px title, revision line, Add Equipment), three summary cards, search/type/lifecycle toolbar, Equipment/Type/Status table with inset selected-row accent, count footer and hint. The register sits in a `minmax(0,1fr) 372px` split (340px at ≤1230px, stacked at ≤970px); the toolbar stacks at ≤1230px as in the prototype. Rows are buttons for mouse, Enter and Space. Add Equipment keeps the existing create sheet and backend validation.
- **Quick Details** (`equipment-quick-details.tsx`). Nonmodal right-side `<aside>`; the list, filters and scroll stay usable. Overview, key electrical information (the registry's critical attributes, falling back to required ones), topology summary (active incident connections or terminals), engineering provenance, and “Open full editor”. Escape and the close button clear the selection.
- **Full Editor** (`equipment-editor.tsx`, `use-equipment-editor.ts`). Page-level editor with Back to Equipment, title + lifecycle status, save status, always-visible Save changes, General / Attributes / Terminals tabs (arrow-key navigation), 245px Equipment information / Navigation rail, and the keyboard hint. The draft logic previously inside the drawer moved into `useEquipmentEditor`, unchanged. It reads with `getEquipmentEditor`, keeps one `equipmentDraft` across tabs, saves with `editorChanges` in a single `saveEquipmentEditor` PATCH, and uses a dirty-ref refetch guard, Cmd/Ctrl+S and a `beforeunload` warning.
- **Attributes** (`equipment-attributes-panel.tsx`). Registry-driven grid (Attribute / Value / Unit / Information state) with Required, Critical and Conditional pills, notes, conditions and an origin · verification · confidence line. Enum/Boolean values use selects; values are kept as exact strings. CONFLICTING remains read-only. Attribute tools (find, show all/required/critical/not populated) filter by server state, so typing never hides the row being edited.
- **Terminals** (`equipment-terminals-panel.tsx`). Profile-managed keys are read-only text with editable labels. Custom terminals support add/edit/remove/restore inside the same draft, with the existing connection warning.
- Shared presentational pieces live in `equipment-ui.tsx`. `equipment-detail-drawer.tsx` was deleted. New tokens: equipment widths, row hover/selected, disabled-control fill, inspector/toast shadows, and `--pf-dialog-width-wide`; `workspace-motion.css` gained the inspector entry keyframe (disabled under reduced motion).

## URL and navigation behavior

- Existing links remain valid: `?workspace=model` (Equipment), `&equipment={id}` (now opens Quick Details), `&view=topology|overview`.
- New editor state: `&equipment={id}&equipmentMode=edit&equipmentTab=general|attributes|terminals`. An unknown tab falls back to General. Selecting rows uses `replace`; opening the editor uses `push`, so browser Back returns to Quick Details. Tab changes and Return use `replace`.
- Leaving a dirty editor by any path opens **Unsaved changes**: Back to Equipment, browser Back/Forward, sidebar and breadcrumb links, the revision switcher, or project navigation. Keep editing cancels the navigation and keeps the draft. Discard changes drops the draft and continues to the intended destination. Save and leave uses the atomic editor PATCH and continues only after a successful save; on failure the dialog stays open with the server error.
- `lib/navigation-guard.ts` is active only while the editor is dirty. A document capture listener holds same-origin link clicks (modified clicks, new-tab and download links still pass through). `guardNavigation(href)` covers programmatic navigation such as the revision switcher. A `popstate` listener registered at module load runs before Next's router; it restores the editor's history entry and records the destination. Reloads and closing the tab still use the `beforeunload` warning.
- `clearEquipment` removes all three equipment parameters when switching revisions or workspaces. A deleted or missing equipment ID shows a not-found notice and clears the selection.
- In the Equipment view the Revision workspace and Equipment/Topology segmented controls are hidden (the sidebar provides that navigation), and the revision summary block is replaced by the prototype header. The read-only banner stays above the title. Save confirmation is a bottom-right “Changes saved.” toast; Topology keeps its inline message.

## Visual evidence

Prototype and production were captured in Chrome at 1440, 1024 and 390 widths. Prototype states were Register, Quick Details and editor General/Attributes/Terminals. Production also covered the unsaved-changes dialog, remove-equipment dialog and read-only editor. Paired comparisons led to corrections: aside copy length, a one-line dialog footer, and stacked toolbar controls at 1024. Matching measurements include the 236px sidebar, 47px stage insets, 372/340px inspector, 245px editor rail, table padding (17px/16px, first column 22px), tab geometry and card radii. Reference images are in `apps/web/.visual-artifacts/ui-d/` (git-ignored): `prototype/`, `before/`, and `final-suite/baseline/`.

The visual harness (`apps/web/visual/run.mjs`, `fixtures.mjs`) now covers the register, Quick Details and all three editor tabs at 1440/1024/390, plus `equipment-unsaved-dialog`, `equipment-remove-dialog` and `equipment-readonly` (68 captures). These replace the obsolete `equipment-drawer` step. Fixtures now include registry attributes, editor attributes, two profile terminals, one connection, a transformer and a removed item.

Regression against `main`: a baseline was captured from a `main` worktree, then this branch was compared using the previous fixtures. Only `desktop-equipment` and `mobile-equipment` changed in geometry or computed styles. Other pages showed 5–30 pixel differences in anti-aliasing. A `main`-vs-`main` run showed the same 8–50 pixel noise, so those differences are harness noise at `threshold: 0`, not regressions. Because the richer fixtures change Topology captures (new terminal nodes and connection), old baselines are not comparable; capture a new baseline into a fresh `VISUAL_ARTIFACTS` directory.

## Checks run

- `npx vitest run`: 24 files, 311 tests passed. Tests cover guarded link, revision-switch and browser-Back navigation, including failed and successful save-and-leave. A Chrome check against the Next dev server also exercised Back, a sidebar link, the revision switcher, project navigation with Discard, Save and leave (one PATCH), and normal history once the draft was clean. Focused coverage includes truthful metrics, nonmodal Quick Details, editor URL/tabs, Back/Forward guard, keep/discard/save-and-leave (including failed save), missing equipment links, read-only and removed messaging, single-PATCH terminal remove/restore, CONFLICTING read-only, attribute filtering without losing edits, and exact large-integer round trip.
- `npx tsc --noEmit -p .`: passed. `npx next lint`: no warnings or errors. `npm run build`: passed.
- `node visual/run.mjs capture` (fresh directory): 68 captures, no page errors or missing fixtures. Immediate `compare` against it: no geometry or style changes, only the pixel noise described above.
- No backend tests were run because no backend code changed.

## Deliberate deviations

- Typography keeps the approved UI-C scale (13.5px body, 12px supporting text, weights 400–700), so table rows are about 10px taller than the prototype.
- Search placeholder is “Search tag, name, or description…”, which is what the API searches (not type). The tag has no required asterisk because the API allows null tags.
- Lifecycle is a status field with a Remove/Restore action using the existing confirmed warnings, not an editable select. It is disabled while the draft is dirty so lifecycle changes never mix with unsaved edits.
- Metric copy is “In the working model” instead of “Available for studies” (no study eligibility exists). The prototype's “concept only” notes are replaced by truthful hints (keyboard save, provenance and unit behavior, terminal safeguards).
- Save changes is disabled until there are valid changes; the prototype always looks enabled.
- At ≤700px the attribute grid stacks value, unit and state under each attribute rather than hiding unit/state as the prototype does, so mobile editing stays possible.
- The top bar follows the UI-C Projects/Overview/Revisions bar (66px height, project name only, project status pill) and keeps the revision crumb: `Projects › North Substation › B › Equipment`. The prototype ends at the equipment tag in the editor; the crumb stays at “Equipment” there. Documents and Topology keep the previous bar. Extraction navigation and the “Design prototype” pill are omitted as non-production.
- The Quick Details topology line shows `terminal ↔ connected node label`; the prototype's phase suffix is omitted; phase configuration remains visible in the Topology workspace.

## Future Backend/API Requirements

| Feature | Current limitation (API examined) | Proposed addition | Priority | UI-D disposition |
| --- | --- | --- | --- | --- |
| Summary counts | `GET …/equipment` has no counts or pagination; the client loads `lifecycle_status=ALL` (shared with Topology) to count | `GET …/equipment/summary` → `{total, active, removed}` | Optional; needed for large revisions | Implemented with existing list |
| Quick Details topology | Editor response has `{equipment, attributes, terminals}` only; client joins revision-wide `nodes` and `connections` | Add `connections: [{terminal_id, other_node_id, other_label, kind, phase_configuration}]` to the editor GET, or an equipment-scoped topology summary | Optional enhancement | Implemented with existing lists |
| Search by type | `search` covers tag/name/description (`engineering_model_service.list_equipment`) | Include registry display name, or keep type as a filter only | Optional | Placeholder reflects actual fields |
| Large registers | List is unpaginated, ordered by creation | Cursor pagination plus sort parameters | Future phase | Deferred |
| Editor breadcrumb | No route-level equipment context in the UI-A breadcrumb provider (frontend) | None required; frontend shell change | Future UI | Deferred, shell preserved |
| Study eligibility (“Available for studies”) | No study-readiness concept or field | Server-computed readiness from requirement rules | Future phase | Truthful replacement copy |

All proposals must stay revision-scoped, honor lifecycle (ACTIVE/REMOVED), and keep the editor PATCH atomic and server-authoritative.

## Remaining risks

- The navigation guard intercepts in-app links, guarded programmatic navigation (`guardNavigation`) and browser history. A future programmatic `router.push` that bypasses `guardNavigation` would bypass the guard. A guarded Back/Forward re-pushes the editor entry, which drops any forward history.
- Metrics and topology summaries load whole revision lists; acceptable now, but heavy for large models until the endpoints above exist.
- The visual harness compares at `threshold: 0` and has a baseline pixel-noise floor; reviewers should rely on geometry/computed-style results and the diff images.

UI-E, UI-F and later phases were not started.
