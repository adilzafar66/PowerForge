# PowerForge UX-9: Design System, Feedback, and Reactive Data Specification

**Scope:** UI/UX foundations shared by approved PowerForge workspaces. **No application code or backend contracts are changed.**
**Interactive specimen:** `prototypes/powerforge-design-system-prototype.html` (self-contained, locally simulated state).

## Design goals

- Engineering data should be easy to scan, with high density and no unnecessary decoration.
- Navigation and editing should feel predictable, with a persistent project/revision context and location-aware action buttons.
- Provide explicit states for asynchronous work: initial load, background refresh, empty, no results, recoverable error, pending mutation, success, and failed mutation.
- Do **not** imply an engineering fact has been saved or verified until the backend confirms.
- Preserve all Phase 5 domain invariants and revision mutability restrictions; Phase 6 extraction evidence remains proposals and Phase 7 owns identity inference.

## 1. Visual tokens

Design tokens should be centralized as CSS variables and reflected in Tailwind theme configuration. The prototype has semantic tokens in `design-tokens.css`; prefer semantic roles to hardcoded hex values.

| Token | Value | Purpose |
|---|---|---|
| `--pf-canvas` | `#F6F8FA` | Large page background |
| `--pf-surface` / `--pf-sidebar` | `#FFFFFF` | Cards, navigation |
| `--pf-border` | `#DBE3EA` | Quiet dividers and input boundaries |
| `--pf-soft` | `#F0F3F6` | Filter chips, table headers, nested navigation |
| `--pf-text-primary` | `#182638` | Headings and values |
| `--pf-text-secondary` | `#526477` | Secondary labels |
| `--pf-text-tertiary` | `#8597A8` | Eyebrows, less prominent metadata; check contrast on intended surfaces |
| `--pf-action` | `#24557A` | Primary action / selection |
| `--pf-action-hover` | `#193E5B` | Primary hover |
| `--pf-action-tint` | `#E6EEF4` | Active navigation, selected items |
| `--pf-positive` | `#0F766E` | Positive/active status, **with label** |
| `--pf-warning` | `#8D621D` | Review/caution, **with label** |
| `--pf-danger` | `#AA3541` | Destructive actions/error, **with label** |
| `--pf-ring` | `#4F86AF` | Visible keyboard focus outline; check resulting contrast |

Fonts: `Instrument Sans` for interface, `JetBrains Mono` for exact equipment tags and electrical numeric values when appropriate. Default body 13–14px, workbench page title ~29px, section title 17–18px, table text 12–13px. Use 4/8/12/16/24/32px spacing; 40px default controls, 48–60px register rows. Desktop sidebar 236px. Cards use quiet borders and radii (~7, 9, 12px); avoid unnecessary drop shadows. A mobile icon rail in the HTML is a **visual fallback**, not final mobile navigation behavior. A final implementation must preserve names/tooltips and wayfinding when condensed.

**Contrast:** all semantic combinations must pass a real WCAG contrast test. Tertiary text is not a safe default for body/field content. Small labels must be tested at actual device scale; never rely only on color to convey status.

## 2. Components to build or standardize

Use the existing `apps/web/src/components/ui/` library, `class-variance-authority`, `@radix-ui/react-slot`, and `lucide-react`. A small set of additional accessible primitives may be justified where the current implementation falls short. Do not introduce a large component framework just for visual polish.

- `Button`: `primary`, `secondary/outline`, `ghost`, `danger`; sizes `small`, `default`; pending/disabled, clearly visible focus; no gradients for this design direction. A page or card should generally have one strongest call to action.
- `StatusBadge`: separate lifecycle, information, verification, origin, classification, and job status domains. Each color must have a label/icon; avoid making `ACTIVE` imply engineering approval.
- `Input`, `Number/DecimalInput`, `Select`, `Checkbox`, `Textarea`, `Field`: labels, optional description, required/error indicators, explicit units. Engineering numeric values remain **strings** throughout frontend drafts; use server-owned conversion/normalization. **`Select` menus and `Checkbox` visuals must be PowerForge-themed, not platform-default.**
- `DataTable`: dense but readable header, consistent padding/hover/focus/selected state, keyboard and accessible row action, truncation/overflow handling, filter toolbar, empty/error/loading states.
- `QuickInspector`: nonmodal selection pane; list remains usable, row selection and URL query state remain stable. Do not label a nonmodal panel `aria-modal=true`.
- `EditSheet`, `ConfirmDialog`: full focus behavior (trap for modal; restore trigger; ESC unless blocked by dirty-draft guard), pending/error feedback, distinct destructive action styling.
- `Toast/Notice`: ephemeral success/error acknowledgment and persistent inline errors for actionable failures; status announced politely or assertively as appropriate.
- `Skeleton`, `Spinner`, `Progress`: skeleton on initial load only, spinner for single action pending states, progress for measurable background work. Avoid decorative full-screen spinners while usable stale data exists.
- `EmptyState`, `ErrorState`, `ReadOnlyBanner`: contextual explanatory copy and a clear next action; never show edit controls where revision/project is not writable.

## 3. Async request-state contract

Recommended production server-state layer: **TanStack Query**, version selected/installed at UI-B implementation time. Current `apps/web` does not depend on it and uses custom `useModelQuery`. Introduce one provider at the correct client boundary; migrate existing load hooks incrementally rather than adding a second competing cache. Keep server components/SSR routing where beneficial; ensure hydrated cache behavior is deliberate.

**Suggested conceptual states:**

| State | UI | Behavior |
|---|---|---|
| First load | Page/list skeleton | Preserve page shell; no blank view |
| Success | List/details | Render stable cached data |
| Background refetch | Small refreshing indicator, stale content visible | Don't erase already loaded content; don't alter draft forms |
| Initial error | Inline failure + Retry | Preserve navigation and headings |
| Refetch error | Inline warning + last successful data | Allow retry, not false “up to date” |
| Empty dataset | Helpful empty state | Offer Create if permitted |
| Filtered to zero | "No matching results" | Offer Clear filters |
| Mutation pending | Disable duplicate Save; show spinner | Keep form values; never claim success |
| Mutation success | Invalidate relevant query keys; update views from authoritative response | Toast/inline confirmation |
| Mutation failure | Preserve draft and known server data | Show backend-provided detail/field errors |

**Suggested query-key families (examples, not API contract):**

```ts
const projectKeys = {
  all: ['projects'] as const,
  detail: (projectId: string) => ['projects', projectId] as const,
  revisions: (projectId: string) => ['projects', projectId, 'revisions'] as const,
};
const revisionKeys = {
  equipment: (p: string, r: string, filters: unknown) =>
    ['projects', p, 'revisions', r, 'equipment', filters] as const,
  nodes: (p: string, r: string) => ['projects', p, 'revisions', r, 'nodes'] as const,
  connections: (p: string, r: string) => ['projects', p, 'revisions', r, 'connections'] as const,
  documents: (p: string, r: string) => ['projects', p, 'revisions', r, 'documents'] as const,
};
```

A successful **equipment editor** mutation should invalidate equipment lists/detail, terminal nodes, and connections as applicable; backend may reconcile terminals and remove obsolete ones. A successful **node/connection** mutation should invalidate topology lists and affected owner views. A project/revision metadata update should invalidate all visible project/revision headers and selectors. Document processing or classification completion should refresh relevant document rows/status/artifacts. For new extraction runs, invalidate document/run/candidate/evidence views by source and applicable revision context. Avoid global invalidation after every mutation when more specific keys suffice.

**Do not** optimistically commit canonical engineering writes, lifecycle changes, revision activation, extraction acceptance, or other consequential actions. If optimistic updates are used for low-risk UI state, they must be reversible and cannot supersede server authority.

## 4. Jobs, polling, and synchronization

- Use bounded `refetchInterval` or equivalent for `PENDING`/`RUNNING` processing, classification, or extraction runs only. Pause when terminal and not otherwise needed; respect visibility, error backoff, manual reload, and stale worker recovery.
- Favor simple polling initially; no new WebSocket/SSE backend is required by UX-9.
- The API decides job status, progress, partial completion, and retry eligibility. Preserve completed page/work-unit results on partial failure as defined in Phase 6.
- Every fetch should be scoped to stable project/revision/document/run identifiers, and stale responses must never override data from a newly selected context.
- Define a consistent default refresh policy by data type. Reference data can be relatively stale; active jobs require shorter intervals. Set interval values during implementation after measuring load, not by hardcoding speculative global intervals in the design.
- On mutation completion, invalidate/refetch the affected keys instead of `window.location.reload()`.
- Local unsaved drafts must be isolated from query-cache refresh and updated only through explicit user intent, a confirmed save, or a deliberate reset action.

## 5. Form, dialog, and navigation lifecycle

- Save is disabled for unchanged forms where appropriate and during an active submit. Validation errors stay adjacent to fields and are mirrored in an accessible summary for large forms.
- Distinguish `NOT_POPULATED` from `MISSING` and `NOT_APPLICABLE` exactly as the backend does. Do not synthesize or auto-approve information states.
- Use a single unsaved-change guard when leaving a dedicated full editor via sidebar, breadcrumbs, browser Back, quick-inspector controls, or close actions. Block accidental loss but do not trap users in impossible confirmation loops.
- Modals require `role="dialog"`/`alertdialog` as appropriate, `aria-modal`, focus trap, Escape/Cancel behavior and focus restoration. Nonmodal quick inspection is a region or complementary pane, **not** a modal.
- Revision switching should change the contextual header and query identity, cancel obsolete in-flight responses, and not copy previous revision data into the new one.
- Page-load and mutation errors need Retry/Cancel/Recovery paths; don't present raw HTTP exceptions without user-relevant explanation. For engineering validation, retain structured backend detail.

## 6. Motion & reduced motion

- Hover/press: 150ms; sidebar/panel/dialog transitions: 180–220ms; no unnecessary page-load choreography.
- Animate color, opacity, small positional movement and simple transforms. Avoid animating layout width when it makes large engineering tables jump unpredictably.
- Respect `prefers-reduced-motion: reduce`. Loading state remains clear without relying on shimmer or spin. Focus/keyboard navigation should not be blocked while animation runs.
- Toast dismissal timing must be long enough for reading, with persistent errors also provided inline where needed. Animation must not be a substitute for acknowledgment or accurate progress.

## 7. Accessibility and responsive acceptance

- All interactive controls reachable by keyboard with visible focus; tablist handles Left/Right/Home/End, disclosure and menus handle Escape appropriately; cursor-only table actions have a keyboard equivalent.
- Ensure labels and controls are associated; status is text + visual signal; errors announced with `aria-live`/`role="alert"` as appropriate.
- Recheck contrast, zoom 200%, font scaling, 1440/1024/768/390 widths, horizontal overflow, and minimum accessible target sizes.
- Contextual right panels do not obscure critical Save/Cancel controls. Preserve document viewer room for page canvas and evidence inspector.
- System Status remains a secondary utility destination. Future sections should not appear as active app navigation until their capabilities exist.

## 8. Proposed Codex implementation order (UI-A/UI-B)

1. Introduce semantic tokens and small reusable UI primitives, with baseline screenshots to catch visual regressions. Preserve existing tests and old routes while migrating.
2. Implement Option A persistent App Shell and sidebar context (Project Overview, Revisions, revision selector, Documents, Engineering Model Equipment/Topology, System Status). Maintain direct URLs to supported views.
3. Add accessible `Button`, `Badge`, `FormField`, `DataTable`, `QuickInspector`, `ConfirmDialog`, `Toast`, `Skeleton`, and `AsyncStatus` patterns with unit/component tests; integrate reduced-motion treatment.
4. Introduce server-state/query provider, select stable keys, document invalidation and retry policy; add tests demonstrating stale response rejection and protecting drafts during refetch.
5. Migrate Projects/Revisions first, then Equipment/Topology and Documents. Keep Phase 5's atomic equipment editor, exact decimal semantics, auto terminals, soft removal, and server-owned writable guards.
6. Add appropriate job polling and status handling to existing processing/classification flows; Phase 6 Extraction should use the same primitives when its API is implemented.
7. Run user-journey tests for initial loading, background refetch, failures, form errors, revision switches, interrupted saves, stale data, read-only behavior, and accessibility.

## 9. Demo limitations and review instructions

Open `prototypes/powerforge-design-system-prototype.html` directly (or via the gallery). Try:

1. **Foundations** — inspect tokens and typography.
2. **Components** — buttons, badges, editable fields and table selection specimens.
3. **API & Jobs** — Load data; Background refresh (stale data remains); Simulate failure; Retry; simulate canonical save confirmation and dependent refetch; start, partially fail, and retry a simulated job.
4. **Feedback & Forms** — edit fields; trigger inline validation; cancel a dirty draft (with confirmation); save successfully; inspect destructive confirmation and toast styles.
5. **Motion & Accessibility** — toggle the movement sample, reduced-motion preview, and use keyboard arrow keys to navigate tabs.

All state is synthetic and isolated to the HTML page. The simulation's local timers do not represent server concurrency, HTTP retries, API contract behavior, verified engineering validity or actual online/offline detection. It is a visual/interaction specification and a test target for the later production implementation.

## 10. UX-9 approval checklist

- [ ] Approve final semantic palette and information density.
- [ ] Approve primary/secondary/destructive button hierarchy.
- [ ] Approve initial skeleton vs stale-background-refresh treatment.
- [ ] Approve error, empty, partial, and retry copy.
- [ ] Approve toast + inline notice pattern.
- [ ] Approve focus and motion behavior.
- [ ] Approve UI-A/UI-B technical direction before authoring Codex implementation prompts.

## UX-9.1 — Custom Select & Checkbox refinement (2026-10-28)

**User request:** Replace the browser-native-looking dropdown menu and checkbox presentation with components matching the approved PowerForge design direction. This is a design update, **not a change to the backend API or engineering domain**.

### Select (PowerForge)

- Closed state: neutral white surface, 8px corner radius, 1px cool-gray border, dark primary text, subtle chevron; 40px minimum height.
- Open state: floating matching surface with quiet shadow, 10px radius, scrollable option list, 6px row radii; selected option has a blue-tint background, check mark, and stronger weight.
- Dark blue `--pf-action` (`#24557A`) for selected/focus indicators; no bright native OS select popups in production.
- Support mouse, touch, Tab, Arrow Up/Down, Home/End, Enter/Space, Escape, typeahead, disabled options, readable labels, screen reader role/selection state, and intelligent viewport collision/scroll handling.
- **Production recommendation:** use a maintained accessible headless primitive such as `@radix-ui/react-select` (or equivalent) rather than directly porting the demo's vanilla JS combobox. Establish single-select as reusable `Select`/`SelectItem` components with size and validation states. Portals and stacking context must work in drawers and modal overlays.
- Source of truth remains a controlled scalar/string. No change to registry enums, null semantics, validation or API representations. A select's visual menu may be custom, but engineering values stay server-authoritative.

### Checkbox (PowerForge)

- White background, 18px rounded square, neutral border, dark blue filled checked state and white check glyph; visible keyboard focus ring; soft hover.
- Support checked, unchecked, mixed/indeterminate, disabled, required, validation/error, and descriptive labels with sufficient hit area.
- **Production recommendation:** style a native `<input type="checkbox">` where suitable or use `@radix-ui/react-checkbox` for accessible composite components. Preserve click-label, form, screen reader, and keyboard behavior.
- Indeterminate is a *presentation state* and must not be submitted as a new boolean value.

### Prototype reference

- The seven HTML prototypes now include the same reusable custom-selection CSS/JS demonstration, with the canonical source in `assets/powerforge-controls.css` and `assets/powerforge-controls.js`. HTML prototypes keep the enhancement inlined so each can still open alone.
- The UX-9 prototype has a sixth **Selects & Checkboxes** tab; inspect closed/open menus, selection, focus/keyboard flows, checked/indeterminate/disabled states.
- The prototype keeps the underlying native `<select>` in the DOM for demo state and form compatibility; this is **not** a prescription for dual interactive select nodes in production. Use a well-tested accessible primitive when implementing UI-A.
- Ensure custom menus remain visible above overflow-hidden cards and in dialog/sheet contexts.
- Add browser tests for keyboard traversal, screen-reader roles/states, focus return, option selection events, required/disabled/invalid states, dropdown position at viewport edge, and clean teardown on revision/workspace changes.

## UX-9.2 — Historical hover exploration (superseded)

The hover palette used in this earlier iteration has been replaced by UX-9.3 below.

## UX-9.3 — Neutral unselected hover and persistent selected tint (2026-10-28)

This section **supersedes UX-9.2's color recommendations** for option hover and selection.

| State | Background | Text |
|---|---|---|
| Unselected, at rest | `#FFFFFF` | `#182638` |
| Unselected, pointer hover **or keyboard active** | **`#F5F8FA`** | `#182638` |
| Selected, at rest | `#E6EEF4` | `#24557A` |
| Selected, pointer hover | **`#D6E3ED`** | `#24557A` |
| Disabled | No new hover effect | Muted |

- Hover/active transitions: 150ms ease; disable under reduced motion.
- Selected state continues to show a checkmark, even when pointer moves to a different item.
- The active descendant is navigation focus, **not** the selected value; unselected keyboard focus uses the same neutral highlight as pointer hover. On initial opening, the selected option retains its resting blue tint until actually hovered.
- Do not copy the prototype dropdown JavaScript into production. Use a keyboard-accessible select primitive that preserves these distinct selected/highlighted states.

### v1.13 Documents register reference

New `prototypes/powerforge-documents-prototype.html` illustrates a complete Documents main route. It follows the same visual tokens and UX-9.3 dropdown states, uses row selection instead of redundant View buttons, retains a nonmodal inspector, and distinguishes processing outcomes and AI suggestions. All data, success states, progress, and mutations in this HTML are illustrative. Production behavior, permissions, accessibility and current application font are authoritative; Codex may improve the layout rather than copying it precisely. The previous evidence viewer remains separate.
