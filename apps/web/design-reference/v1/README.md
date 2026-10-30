# PowerForge UI/UX Prototype Package v1

Open `index.html` locally in a desktop browser for the prototype gallery. Each HTML prototype is self-contained and requires no build. All data and interactions are simulated.

## Design source of truth

1. The **PowerForge application repository and current working branch** are authoritative for architecture, routing and functional behavior, engineering semantics, permissions, and APIs. The prototypes are authoritative for visual design and screen layout.
2. The HTML prototypes and corresponding previews are the **primary visual and layout specifications**. Production screens should match them as closely as reasonably possible in structure, ordering, dimensions, spacing, alignment, colors, component appearance, and interaction states. Do **not** independently redesign, restyle, rearrange, add, or remove visible UI elements because a different design seems preferable or an element seems redundant. Depart from the visual reference only where required by actual backend functionality, real data, permissions, accessibility, responsiveness, or technical constraints; keep any such deviation minimal and explain it in the implementation handoff. Codex retains autonomy over underlying React/Next.js component structure, data fetching, state management, event handling, and other implementation decisions that do not change the intended appearance.
3. **Preserve the existing application font family.** Prototype fonts are illustrative; no font migration is required. Match the prototype typography hierarchy, sizing, weights, and spacing as closely as feasible with the existing fonts.

## Interactive prototypes

| Workspace | Path | Examples |
| --- | --- | --- |
| Equipment | `prototypes/powerforge-equipment-prototype.html` | List, quick details, editor |
| **Documents — main workspace** | `prototypes/powerforge-documents-prototype.html` | Document register, search/advanced filters, quick views, nonmodal document details, simulated upload/reuse, processing and classification status, revision read-only state |
| Documents / evidence | `prototypes/powerforge-document-evidence-prototype.html` | Drawing canvas, zoom/pan, source highlighting |
| Project / Revisions | `prototypes/powerforge-project-revisions-prototype.html` | Revision list and detail, metadata edit, activation |
| Projects | `prototypes/powerforge-projects-prototype.html` | Project list, **single unified Project Overview**, creation, edit, lifecycle |
| Topology | `prototypes/powerforge-topology-prototype.html` | Nodes, terminals, connections, lifecycle |
| **UX-9 interactive states** | `prototypes/powerforge-design-system-prototype.html` | Tokens, components, query lifecycle, retry, progress, forms, toasts, motion |

## UX-9 example interaction checklist

1. Inspect **Foundations** color and typography usage and compactness.
2. Inspect **Components** buttons, form fields, status badges, and table states.
3. Test **API & Jobs**: load, background refresh, fail/retry, empty, confirmed save, partial job/retry.
4. Test **Feedback & Forms**: validation, unsaved-change warning, save pending, toast, destructive confirmation.
5. Test **Motion & Accessibility**: keyboard tab navigation, panel motion, reduced-motion preference.

See `UX9_DESIGN_SYSTEM_SPEC.md` for the visual design specification and behavioral examples and `CODEX_HANDOFF.md` for visual-fidelity requirements, domain safeguards, source hierarchy, and migration guidance. The v1.13 update also adds a new standalone Documents workspace and adjusts sibling-prototype Documents navigation links.

## Preview screenshots

- `previews/ux9-foundations-preview.png`
- `previews/ux9-components-preview.png`
- `previews/ux9-async-preview.png`
- `previews/ux9-feedback-preview.png`
- `previews/ux9-mobile-preview.png`

## Testing

Run `python qa/test_ux9_prototype.py` with Python Playwright and local `/usr/bin/chromium`. Because restricted testing environments block `file://`, the QA script uses `page.set_content`. Tests operate only on isolated browser state.

## UX-9.1 visual control refinement

- `prototypes/powerforge-design-system-prototype.html#controls` — new Selects & Checkboxes interactive section.
- `assets/powerforge-controls.css` / `assets/powerforge-controls.js` — shared reference source for the themed dropdown/checkbox behavior applied across all seven standalone HTML prototypes.
- The previous v1.8 ZIP is preserved separately. The prototype is not an actual API client.

## UX-9.2 — Historical hover exploration (superseded)

See UX-9.3 for the approved hover colors.

## UX-9.3 — Refined dropdown background states

The custom selects now hover neutral `#F5F8FA` for unselected options, while selected options retain `#E6EEF4` blue and darken to `#D6E3ED` on hover. See `UX9_3_RELEASE_NOTES.md`.

## UX-10 / v1.12 — Unified Project Overview and reduced redundancy

- **One canonical Project Overview reference:** `prototypes/powerforge-projects-prototype.html#project/p1`. Project information and editing/lifecycle controls come **first**; current work, active revision, revision metrics and clickable revision history follow below. The sample counts are illustrative.
- `prototypes/powerforge-project-revisions-prototype.html#overview` redirects to the canonical Project Overview instead of presenting a second competing layout. The revision prototype remains the reference for **Revisions**, **Revision Overview**, and revision create/edit flows.
- Removed the breadcrumb-like uppercase path labels above screen headings where they simply repeated the header breadcrumbs. Contextual card labels remain.
- The Revisions table no longer contains an Actions/View column; clicking or keyboard-activating a row opens that revision.
- Codex must match the prototype spacing, layouts, visible controls, and typography hierarchy as closely as feasible; it must not omit or rearrange UI elements merely because they appear redundant. It may freely organize the underlying React components and functional code, provided the visible design remains faithful. **Preserve feature intent and server-authoritative engineering behavior** without copying prototype-specific mock implementations.
- The included HTML/JS and QA scripts are demonstration assets, not application dependencies. Do not copy local fixture data, mock save timers, fake job results, or cross-file navigation into the production app.

## UX-10 / v1.13 — Documents main workspace (new)

The prior package included a **Document & Evidence Viewer** but did not have a dedicated **Documents main page**. This release adds `prototypes/powerforge-documents-prototype.html`, using the approved application shell and providing a complete document register for a selected revision.

- Live prototype examples: search by filename/number/description; All, Needs Review, Issues, and Removed quick views; type/origin/processing/AI filters; row inspection and contextual menu; nonmodal document detail panel; metadata editing; explicit suggestion acceptance; upload/reuse dialogs; remove/restore; process retry; sample read-only revision; demo progression and reset.
- **No data is real**: filenames, counts, job progress, confidence, changes and upload/reuse actions are simulations, not PowerForge backend calls. Production must preserve actual document relationships and authorization while matching the visual design as closely as real data and functionality allow.
- The main Documents nav item in the Projects, Revisions, Equipment, Topology and Document Viewer references now links to this new main workspace where feasible. The viewer remains a separate specialized visual reference.
- UX-9.3 selected/unselected dropdown option hover styling stays the same.
