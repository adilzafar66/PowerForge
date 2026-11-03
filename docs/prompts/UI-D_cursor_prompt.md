# PowerForge — UI-D: Equipment Workspace

## Objective and starting point

Implement **UI-D only: the production Equipment workspace redesign**. This is a frontend implementation of an already functioning revision-scoped engineering-model workflow, **not a new engineering backend feature**.

Work on a dedicated `codex/ui-d-equipment-workspace` branch from the latest **accepted baseline that includes UI-C and the standalone frontend component/design-token refactor**. Review the current code, handoffs, API contracts, and tests before editing.

**Only UI-D is in scope.** Do not implement UI-E (Documents/viewer), UI-F (Topology workspace), UI-G, Phase 6 extraction, graph visualization, or backend/schema/registry changes. You may reuse the existing topology/terminal services strictly as required by the Equipment editor.

## Authoritative visual reference — strict fidelity

Use `apps/web/design-reference/v1/` as the visual authority, especially:

- `prototypes/powerforge-equipment-prototype.html` — the **Equipment register, nonmodal Quick Details inspector, and dedicated Full Editor**.
- The relevant `previews/` images, `README.md`, `CODEX_HANDOFF.md`, `UX9_DESIGN_SYSTEM_SPEC.md`, design tokens, shared-control references, and existing approved UI-A/UI-C patterns.

**Match the prototype as closely as practical, not just its general style.** Reproduce the screen hierarchy and order; content position and widths; register/inspector split (including responsive behavior); toolbar/table geometry; cards, rows, form groups and footer; padding/gaps; **font sizes, weights and line heights**; colors, borders, radii, shadows, icons, badges; hover/selected/focus/disabled/error/loading states; and animation/transition timing. Retain the application's established font **family**. Preserve previously approved, intentional UI-C typography and Project Overview choices on existing screens; do not restyle them for this task.

Do not independently simplify, rearrange, omit, or invent visible UI. Deviate minimally only when actual APIs/data, authorization, accessibility, or unavoidable implementation constraints require it, and record such deviations. Prototype objects, examples, simulated saves and local JavaScript interactions are **not** production data or API contracts.

Use the **accepted post-refactor Tailwind-first architecture**: reusable React components own their Tailwind classes, shared semantic tokens/variants are reused, and custom CSS remains minimal and justified. Avoid creating monolithic stylesheet/class dictionary. Do not turn this phase into an application-wide component refactor.

## Implement the Equipment workspace

### A. Equipment register

- Redesign the Equipment workspace header, contextual actions, summary/counts, list, search, equipment-type filter, Active/Removed/All lifecycle filtering, table columns/status indicators, and empty/error/loading/refresh states to closely follow the reference.
- Use real revision-scoped equipment records and registry types. Preserve search/filter state and selection while refreshing. Do not invent counts, ratings, provenance, or missing field values.
- Rows must be mouse- and keyboard-operable; selecting one opens **nonmodal Quick Details** while keeping the list, filters and scroll position usable. Preserve URL/deep-link selection and Back/Forward behavior, including the existing `equipment` query parameter.
- Preserve the existing **Add Equipment** workflow and backend validation; match relevant prototype presentation without replacing a functioning create operation with a mock.

### B. Quick Details inspector

- Implement the prototype's compact right-side inspector, correct desktop split-column widths and responsive layout. The list must remain interactive while the inspector is open.
- Show real equipment identity, type, lifecycle/verification/origin where available, key metadata and attributes, appropriate actions and a clear close path. Reuse actual data; don't fabricate attribute values or status.
- **Edit** navigates into the prototype's **dedicated, URL-addressable Full Editor**, not simply the previous modal drawer masquerading as a full editor. Keep the selected equipment and revision context. Use the existing revision-scoped URL/query infrastructure, adding a compatible editor state/route as needed; preserve existing deep links.

### C. Dedicated Full Editor

- Match the prototype's page-level editor layout, title/actions, **General / Attributes / Terminals** navigation, compact data-density, Return/Save controls, validation and responsive presentation.
- Reuse the current **unified atomic editor** (`getEquipmentEditor`, `saveEquipmentEditor`, `equipmentDraft`, `editorChanges`) so General, Attributes and Terminals form **one protected draft and one server-confirmed save**. Do not split the transaction into independent writes or lose unsaved changes on refetch/tab switches.
- Retain keyboard Save where applicable, unsaved-change confirmation for Return/close/navigation, pending state, failed-save retry, protected draft, and server-authoritative error feedback. Avoid optimistic canonical writes.
- Preserve meaningful read-only views for removed equipment and revisions/projects that cannot be edited. Use authoritative permissions rather than demo behavior.

### D. Registry-driven attributes and terminal safeguards

- Render attributes from the **actual engineering registry**, not a hardcoded subset from the prototype. Retain required/critical/conditional indicators, enum/Boolean and numeric controls, information state (including NOT_POPULATED, MISSING, NOT_APPLICABLE), notes, unit choices, provenance/verification visibility, and any currently supported metadata.
- Preserve **exact decimal and large-integer strings**, null/omitted/reset semantics and server-owned unit normalization. Do not round through JavaScript `Number` or introduce fabricated defaults.
- Preserve automatically managed terminal profiles and their editing restrictions, custom-terminal add/edit/remove/restore, equipment-type reconciliation, transactional conflicts and connected-topology safeguards. Retain lifecycle remove/restore warnings and backend-confirmed outcomes; don't automatically restore connected edges or infer topology.

## Integration boundaries

Relevant starting points (inspect actual accepted baseline before changes): `equipment-workspace.tsx`, `equipment-detail-drawer.tsx`, `equipment-general-panel.tsx`, `equipment-attributes-panel.tsx`, `equipment-terminals-panel.tsx`, `engineering-model-workspace.tsx`, `model-shared.tsx`, `lib/equipment-draft.ts`, `lib/engineering-model.ts`, `lib/workspace-navigation.ts` and related tests.

- Preserve UI-A shell, project/revision selector, breadcrumbs, UI-C pages, navigation and existing revision routes (`/projects/{projectId}/revisions/{revisionId}?workspace=model&view=equipment` plus supported equipment selection). **Selecting a revision never activates it.**
- Preserve UI-B TanStack Query and existing cache keys, invalidation, refresh, errors and request-scoping. Avoid competing server-state caches and draft clobbering on background refresh.
- Preserve Phase 5 API/domain invariants: lifecycle, revision write guards, registry-driven form semantics, immutable ownership, terminal profile/connection protections and atomic editing. No changes to backend contracts or canonical registry.
- Ensure accessible labels, keyboard navigation, focus behavior, safe draft dismissal, reduced motion and meaningful mobile behavior.
- Keep changes targeted to Equipment UI, any necessary small shared-component improvements, focused tests and a short handoff. **Do not redesign Documents or the Topology workspace** while implementing Equipment's Terminals tab.

## Backend/API gap register — document, do not implement

While implementing the prototype, **identify any required or valuable functionality that the existing APIs, backend services, data contracts, or persistence model cannot currently support**. Do not invent mock production functionality or silently omit a feature without recording the limitation. First check whether an existing endpoint/service can support it safely.

For every confirmed gap, record it in the UI-D handoff (in a dedicated **Future Backend/API Requirements** section), with:

- **User-facing feature and use case** (including which prototype interaction depends on it).
- **Current limitation** and the existing API/service examined.
- **Proposed addition**, such as an endpoint, service operation, response field, data contract or persistence change; include illustrative request/response fields where useful, but do not treat these as an approved design.
- **Priority/impact** (blocking UI-D, optional enhancement, or future-phase feature) and **dependencies/engineering implications**, including permissions, revision scope, lifecycle, atomicity, and other safeguards as applicable.
- **UI-D disposition**: implemented using an existing API, gracefully unavailable/disabled with truthful messaging, or deferred. Distinguish actual gaps from functionality deliberately reserved for later phases.

**Do not implement new backend APIs/services, migrations, or registry changes in UI-D without explicit authorization.** Keep working supported functionality intact. If a missing capability materially blocks an exact prototype interaction, implement only the truthful, safe frontend behavior currently possible and document the discrepancy for a later backend decision.

## Implementation and verification

1. **Inspect and capture the actual HTML prototype** states first (register, selected Quick Details, full editor General/Attributes/Terminals, actions and mobile). Capture stable reference screenshots at matching viewport widths, at least **1440px desktop and 390px mobile**, plus an intermediate width if the split layout changes significantly.
2. Implement register → inspector → full editor incrementally. Compare **rendered production browser screenshots against the HTML prototype** under matched viewports and meaningful states, not merely before/after source or Tailwind screenshots. Correct noticeable mismatches before finishing. If screenshots cannot be executed, explicitly report that limitation rather than claiming pixel fidelity.
3. Exercise real or deterministically mocked backend flows for add, open, edit/save, invalid input, dirty-draft protection, refetch, failed writes/retry, lifecycle and read-only permissions. Verify exact engineering numeric round trips and terminal constraints. Keep tests focused; do not add a large speculative suite.
4. Run relevant existing frontend tests, TypeScript, lint and production build. Report precisely what was run and what passed/failed. No backend/schema changes.
5. Deliver a concise handoff with modified components, route/deep-link behavior, confirmed visual comparisons, test results, intentional backend-driven deviations, and remaining risks. **Stop after UI-D**; leave UI-E and UI-F for subsequent separate prompts.

**Acceptance:** Equipment list, Quick Details and Full Editor closely match the approved prototype in appearance and interaction, while every existing engineering operation remains reliable and server-authoritative. UI-C and other workspaces remain unchanged.
