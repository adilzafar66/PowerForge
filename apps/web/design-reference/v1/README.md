# PowerForge UI/UX Prototype Package v1

Open `index.html` locally in a desktop browser for the prototype gallery. Each HTML prototype is self-contained and requires no build. All data and interactions are simulated.

## Design source of truth

1. PowerForge current `main` repository and ADR-007 / Phase 6 design govern real engineering behavior.
2. HTML prototypes provide **visual and interaction inspiration**, **not backend contracts or production implementations**.

## Interactive prototypes

| Workspace | Path | Examples |
| --- | --- | --- |
| Equipment | `prototypes/powerforge-equipment-prototype.html` | List, quick details, editor |
| Documents / evidence | `prototypes/powerforge-document-evidence-prototype.html` | Drawing canvas, zoom/pan, source highlighting |
| Project / Revisions | `prototypes/powerforge-project-revisions-prototype.html` | Project overview, revision list, metadata edit, activation |
| Projects | `prototypes/powerforge-projects-prototype.html` | Project list, creation, edit, lifecycle |
| Topology | `prototypes/powerforge-topology-prototype.html` | Nodes, terminals, connections, lifecycle |
| **UX-9 interactive states** | `prototypes/powerforge-design-system-prototype.html` | Tokens, components, query lifecycle, retry, progress, forms, toasts, motion |

## UX-9 review checklist

1. Inspect **Foundations** color and typography usage and compactness.
2. Inspect **Components** buttons, form fields, status badges, and table states.
3. Test **API & Jobs**: load, background refresh, fail/retry, empty, confirmed save, partial job/retry.
4. Test **Feedback & Forms**: validation, unsaved-change warning, save pending, toast, destructive confirmation.
5. Test **Motion & Accessibility**: keyboard tab navigation, panel motion, reduced-motion preference.

See `UX9_DESIGN_SYSTEM_SPEC.md` for implementation and acceptance criteria and `CODEX_HANDOFF.md` for domain safeguards, source hierarchy, and migration guidance. All previous files are retained unchanged except this gallery, README and additive design notes.

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
- `assets/powerforge-controls.css` / `assets/powerforge-controls.js` — shared reference source for the themed dropdown/checkbox behavior applied across all six standalone HTML prototypes.
- The previous v1.8 ZIP is preserved separately. The prototype is not an actual API client.

## UX-9.2 — Historical hover exploration (superseded)

See UX-9.3 for the approved hover colors.

## UX-9.3 — Refined dropdown background states

The custom selects now hover neutral `#F5F8FA` for unselected options, while selected options retain `#E6EEF4` blue and darken to `#D6E3ED` on hover. See `UX9_3_RELEASE_NOTES.md`.
