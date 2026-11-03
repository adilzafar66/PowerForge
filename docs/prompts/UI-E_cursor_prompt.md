# PowerForge — UI-E: Documents Workspace & Evidence Viewer

## Objective

Implement **UI-E — Documents Workspace & Evidence Viewer** in PowerForge, starting from the latest `main` branch, which includes UI-A through UI-D and the frontend structural refactor.

Work on a dedicated `codex/ui-e-documents-workspace` branch.

The goal is to bring the existing Documents functionality into alignment with the approved UI/UX prototypes while preserving all established backend behavior and engineering safeguards.

## 1. Design references

Use the latest repository versions of:

- `apps/web/design-reference/v1/prototypes/powerforge-documents-prototype.html` — authoritative reference for the main Documents workspace.
- `apps/web/design-reference/v1/prototypes/powerforge-document-evidence-prototype.html` — authoritative reference for the document/page/evidence viewer.
- `apps/web/design-reference/v1/CODEX_HANDOFF.md`
- `apps/web/design-reference/v1/UX9_DESIGN_SYSTEM_SPEC.md`

**Visual fidelity is a primary acceptance criterion.** Match the prototypes as closely as reasonably possible in layout, dimensions, spacing, typography hierarchy, colors, component styling, interaction states, transitions, and responsive behavior.

Do not independently redesign, simplify, rearrange, or remove visible UI elements. Preserve PowerForge's existing font family and approved typography adjustments.

You have autonomy over React architecture, component composition, hooks, routing, data integration, and state management, provided these choices preserve the approved designs.

## 2. Documents Workspace

Implement the prototype's main Documents experience using real revision-scoped backend data.

This includes the document register, summary information, search, quick views, advanced filters, contextual actions, and nonmodal document details inspector.

Preserve and integrate all existing functionality, including:

- Uploading and reusing documents across revisions.
- Document metadata editing.
- Processing and AI classification status.
- Explicit acceptance of classification suggestions.
- Retry operations, downloading, and viewing document pages.
- Remove/restore operations and revision read-only restrictions.
- Loading, empty, error, and background-refresh states.

Selecting a document should open its nonmodal details inspector without preventing interaction with the register. Preserve deep linking and sensible navigation behavior.

## 3. Document & Evidence Viewer

Implement the dedicated viewer based on the approved evidence prototype.

Support real document pages and available artifacts, page thumbnails/navigation, zoom, fit controls, pan/scroll, and contextual information panels.

The viewer should support both document inspection and future extraction-evidence workflows.

**Important:** Phase 6 evidence and structured extraction functionality may not yet exist in the backend. Do not simulate extraction results, fabricate evidence, invent confidence scores or bounding boxes, or implement Phase 6 as part of UI-E.

Implement functionality supported by existing APIs. Where evidence functionality is unavailable, provide an appropriate honest empty/unavailable state and document the missing requirements for future implementation.

## 4. Architecture and safeguards

Use the established Tailwind-first design system, shared components, design tokens, and TanStack Query infrastructure.

Preserve existing document lifecycle, inheritance, processing, classification, provenance, permissions, and error-handling semantics.

Server responses remain authoritative. Do not copy the prototypes' mock data, simulated progress, or fake interactions into production.

Preserve existing user workflows and protect unsaved edits from accidental loss. Respect the navigation safeguards introduced during UI-D where applicable.

Keep changes focused on UI-E. Do not redesign Equipment or Topology, modify backend contracts unnecessarily, or implement later engineering phases.

## 5. Backend/API gap register

If a prototype feature requires backend functionality or an API that does not currently exist, **document the gap instead of implementing new backend functionality**.

For each gap, briefly record the intended feature, existing limitation, recommended backend/API addition, priority, and whether the UI functionality has been deferred or partially supported.

Include this register in `docs/UI_E_HANDOFF.md`.

## 6. Verification and handoff

Compare actual rendered UI-E screens against the HTML prototypes using browser screenshots at matching desktop and mobile viewport sizes. Correct meaningful visual discrepancies.

Run relevant frontend tests, TypeScript checks, lint, and the production build. Add focused regression tests for important document workflows, without unnecessary test expansion.

Provide `docs/UI_E_HANDOFF.md` summarizing:

- Implemented functionality and important architectural decisions.
- Visual comparison results and intentional deviations.
- Tests and validation performed.
- Future Backend/API Requirements.
- Known limitations or outstanding issues.

**Completion criterion:** A visually faithful, production-integrated Documents Workspace and Document Viewer that preserves existing functionality, uses real backend data, and provides a sound foundation for future evidence/extraction capabilities.

**Scope strictly excludes UI-F (Topology) and unrelated refactoring.**