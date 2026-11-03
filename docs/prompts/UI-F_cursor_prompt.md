# PowerForge — UI-F: Topology Workspace

## Objective

Implement **UI-F — Topology Workspace**, starting from the latest `main` branch, which includes UI-A through UI-E.

Work on a dedicated branch named `codex/ui-f-topology-workspace`.

The goal is to transform the existing Topology interface into the approved production-ready experience while preserving all existing engineering functionality, backend contracts, and data integrity safeguards.

## 1. Design references

Use the following repository references:

- `apps/web/design-reference/v1/prototypes/powerforge-topology-prototype.html` — primary visual and interaction reference.
- `apps/web/design-reference/v1/CODEX_HANDOFF.md`
- `apps/web/design-reference/v1/UX9_DESIGN_SYSTEM_SPEC.md`
- `docs/TOPOLOGY.md` — authoritative topology domain behavior.

**Visual fidelity is a primary acceptance criterion.** Match the prototype as closely as reasonably possible, including layout, spacing, typography hierarchy, colors, component styling, responsive behavior, transitions, and interactive states.

Preserve the existing PowerForge font, design tokens, Tailwind-first component architecture, and established application shell.

You have autonomy over the underlying React architecture and implementation choices, provided the approved appearance and functionality are preserved.

## 2. Topology Workspace

Implement the complete Topology experience using real revision-scoped engineering model data.

This includes:

- Topology header, summary metrics, and engineering information notice.
- Nodes and Connections registers, including search, lifecycle filtering, and relevant status information.
- Interactive row selection and contextual details inspector.
- Node and connection creation/editing interfaces.
- Remove/restore actions with appropriate confirmations and feedback.
- Loading, empty, error, read-only, and responsive states.

Maintain the distinction between equipment terminals and standalone electrical nodes. Display equipment ownership, terminal keys, connection endpoints, and relevant engineering attributes clearly.

Follow the prototype's intended interaction patterns while integrating naturally with the established UI-D/E application experience.

**This is a topology data-management workspace, not a graphical single-line diagram editor.** Do not implement graph visualization or automatic topology inference in UI-F.

## 3. Engineering functionality and safeguards

Preserve the existing Phase 5 canonical topology model and all established backend behavior.

In particular:

- Nodes and connections remain revision-scoped and server-authoritative.
- Application-managed terminals must respect equipment terminal profiles and their editing restrictions.
- Connections must use valid, distinct endpoints and preserve the existing support for parallel connections.
- Preserve connection kinds, nominal direction, phase configuration, and exact decimal voltage handling with registry-supported units.
- Respect active/removed lifecycle semantics, including cascading removal and conservative restoration.
- Do not automatically restore connections when equipment or nodes are restored.
- Honor project/revision read-only restrictions and backend validation.
- Protect unsaved edits when closing editors or navigating away.

Retain existing working capabilities even if they are not explicitly demonstrated in the prototype.

Use existing APIs and TanStack Query infrastructure. Do not duplicate engineering logic in the frontend or introduce speculative functionality.

## 4. Backend/API requirements

If any desired functionality requires an API or backend service that does not currently exist, document the gap rather than implementing new backend functionality.

Record the intended feature, current limitation, proposed backend/API addition, priority, and whether the UI feature was deferred or partially implemented.

Include these findings in `docs/UI_F_HANDOFF.md`.

## 5. Verification and handoff

Compare actual rendered UI-F screens against the approved HTML prototype at matching desktop and mobile viewport sizes. Correct meaningful visual discrepancies and document any intentional deviations.

Run relevant frontend tests, TypeScript, lint, and production build checks. Add focused regression tests covering important topology interactions and engineering safeguards.

Produce `docs/UI_F_HANDOFF.md` summarizing:

- Implemented functionality and architectural decisions.
- Visual comparison results and intentional deviations.
- Tests and verification performed.
- Future Backend/API Requirements.
- Known limitations and outstanding issues.

## Completion criteria

UI-F is complete when the Topology Workspace faithfully reflects the approved design, integrates with real backend data, supports the existing node and connection authoring workflows, and preserves all engineering data integrity guarantees.

**Scope:** UI-F only. Do not implement UI-G, graphical SLD visualization, AI-based topology extraction, new backend features, or unrelated refactoring.

Do not modify the completed UI-A through UI-E experiences except where necessary for Topology navigation or shared integration.