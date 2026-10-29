# UI-A — Design system and app shell

Implemented on `codex/ui-a-design-system-shell`, based on accepted `main` commit `3b8cf90`. Scope is limited to [UI-A](prompts/UI-A_codex_prompt.md), using [the approved local design package](../apps/web/design-reference/v1/README.md).

## Delivered

- Persistent root app frame with Option A desktop sidebar, accessible mobile navigation dialog, skip link, and real project/revision breadcrumbs. Page components publish their existing authoritative data to the shell; no additional client cache or fabricated context was added. Project changes refresh shell labels from the same state as the existing page.
- Project Overview and Revisions navigation; current revision label and separate revision switcher; Documents, Equipment and Topology destinations; System Status in the footer. Future modules remain absent.
- Semantic CSS/Tailwind tokens, existing Instrument Sans / JetBrains Mono typography, flat dark-blue actions, quieter cards, consistent field/table/menu/badge styling, visible focus, and reduced-motion rules. Transitional palette aliases keep existing workspaces usable without replacing their layouts. Small metadata text uses a darker accessible neutral instead of the reference's low-contrast tertiary color.
- Shared Radix Select with the UX-9.3 option colors, 150ms transitions, persistent checkmarks, typeahead/keyboard handling, portals, collision handling, required/disabled/invalid semantics, and native form values. Existing option definitions—including fragments, empty values and explicit boolean strings—are preserved at their call sites. All previous native select call sites use it.
- Shared themed native Checkbox preserving labels, forms, checked/disabled/required/invalid states and optional indeterminate presentation. It does not invent domain boolean values.
- Accessible portalled menus, focus-trapped edit sheets and confirmation dialogs with focus restoration. Document quick details remain nonmodal so the document list stays usable; existing equipment dirty-close/save safeguards remain authoritative.

## Route compatibility

Existing paths and old document/equipment deep links continue to work. URL parameters select the existing workspaces:

| Destination | Existing path suffix |
| --- | --- |
| Project Overview | `/projects/{projectId}` |
| Revisions | `/projects/{projectId}?section=revisions#revisions` (current revision section) |
| Revision Overview | `/projects/{projectId}/revisions/{revisionId}?view=overview` (current metadata view) |
| Documents | `/projects/{projectId}/revisions/{revisionId}` |
| Equipment | `/projects/{projectId}/revisions/{revisionId}?workspace=model&view=equipment` |
| Topology | `/projects/{projectId}/revisions/{revisionId}?workspace=model&view=topology` |

Navigation preserves unrelated query parameters. Revision switching retains the workspace but removes document/equipment IDs belonging to the previous revision. The switcher changes navigation only; it never activates a revision.

## Dependencies and validation

Added `@radix-ui/react-select` 2.4.1, `@radix-ui/react-dialog` 1.3.1 and `@radix-ui/react-dropdown-menu` 2.2.1, with lockfile updates. This Select version supports empty-valued options directly, so UI values need no domain-facing sentinels or conversions. Checkbox uses a styled native input.

Validation:

- 259 frontend tests passing, including existing canonical editing, exact-number, boolean-choice, lifecycle/read-only and dirty-draft regressions. Added control and navigation tests; native-select tests now exercise real portalled controls.
- ESLint and TypeScript checks pass.
- Production build passes.
- Read-only Chrome checks pass for dropdown colors/checkmarks, keyboard selection and Escape, focus restoration, modal focus trapping, reduced motion, mobile navigation, widths 1440/1024/768/390 and 200% CSS zoom. No application writes or browser page errors occurred. The alternate local frontend port used a browser-only CORS proxy; backend configuration was unchanged.
- Unit tests polyfill missing jsdom pointer/scroll APIs and native top-layer selector probes. jsdom cannot enter native modal/popover/fullscreen states; its `:modal` check otherwise recursively evaluates `:fullscreen`. Geometry, focus and visual behavior were additionally checked in Chrome.

## Deferred

UI-B owns the server-state/query migration, query invalidation policy, job polling and comprehensive async feedback. Current hooks and mutation refresh behavior remain in place. UI-C owns complete Projects/Revisions layouts and dedicated views; the Revisions navigation currently targets the working existing section. UI-D–F own complete Equipment/Documents/Topology redesigns, including the separate equipment quick inspector and URL-addressable full editor. UI-G integration polish is not started. Backend APIs, permissions, canonical model semantics and Phase 6 extraction are unchanged.
