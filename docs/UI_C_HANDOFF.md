# UI-C — Projects and Revisions workspaces

Implemented on `codex/ui-c-projects-revisions`, based on accepted `main` commit `7135345` (includes UI-A/UI-B). Implementation is currently in the working tree; no UI-C commit or push has been requested yet.

## Screens and navigation

- Projects retains useful search/status filters and authoritative lifecycle badges. Rows support mouse and Enter/Space navigation as well as real project links; narrow screens scroll the register within its card. Project creation retains all fields and its optional initial revision. A failed initial revision preserves the saved project and supports revision-only retry, without creating duplicates. Cancel/back actions protect an unsaved creation form.
- `/projects/{id}` is the canonical Project Overview. Project Information and lifecycle controls come first, followed by current active work and revision history. Edit lives in the information card and opens a right-side modal editor. Pause/resume/cancel/archive/unarchive retain confirmed backend actions. Paused projects correctly remain editable; archived/cancelled projects are read-only.
- `/projects/{id}/revisions` is a dedicated searchable/filterable register with description, ancestry, status and updated date. Rows open Revision Overview through real links; there is no redundant Actions/View column. Legacy `?section=revisions#revisions` URLs redirect here. Sidebar selection and breadcrumbs reflect the destination.
- Revision Overview remains at `/projects/{id}/revisions/{revisionId}?view=overview`. It shows revision information, lineage, manual system settings and lifecycle, with direct Documents/Equipment/Topology links. Existing query-based workspace and selected-object URLs remain compatible. The revision selector navigates without activating; from project pages it opens Revision Overview.
- New revision opens the right-side creation form from the dedicated Revisions register. Omitted backend defaults remain distinct from an explicit null base. Document and model carry-forward choices remain independent. Optional activation requires confirmation before submission; inherited counts are shown only from the confirmed creation response.

## Editing and authority

`updateRevision` is a thin typed client wrapper for the existing `PATCH /api/projects/{project_id}/revisions/{revision_id}` endpoint. It sends only changed fields. Explicit null clears description/frequency/phase; unchanged fields are omitted. Frequency stays a decimal string throughout validation and submission, without conversion through JavaScript Number. It must be positive with finite decimal syntax; phase is 1, 3 or unset. Server validation remains authoritative.

Backend permission split is preserved: superseded revisions allow identifier/description edits in modifiable projects, but their system engineering settings remain read-only. Active/paused projects are modifiable; archived/cancelled projects are not. Metadata editing does not submit lifecycle, lineage, carry-forward, document or model fields.

Project/revision editors hold independent baseline/draft snapshots, survive background refetch, preserve failed submissions, guard cancel/Escape/outside dismissal with discard confirmation, and protect browser unload while dirty or pending. Modal editing uses UI-A focus handling. The previously reverted global internal-navigation guard was not reintroduced.

All server data stays in UI-B's TanStack Query cache. Confirmed writes update the appropriate visible data and use the established write invalidation to refresh affected project/revision labels, sidebar, lists and ancestry. Revision editing additionally refreshes the scoped revision/project label queries. No canonical write is optimistic. Only a draft newer than the active revision is offered activation; activation failure retains the previous active state.

## Visual fidelity rework

The updated v1 README, CODEX_HANDOFF and UX9 design specification make the HTML prototypes the visual authority. The initial UI-C layout has been replaced to follow that direction.

- White page-header bands, 66px breadcrumb bars, 27px titles, prototype content insets, 12px card radii, compact controls and title-case dotted status badges.
- Project Overview follows the unified reference: metadata strip; Project details with information/lifecycle/summary columns; Revision activity with current work, compact revision history and the active-revision rail. The right rail is 310px with a 20px gutter.
- Revision Overview follows the reference's 330px right rail: summary first, workspace rows second, information third; history and carry-forward cards at right. System settings are in Revision Information, not a separate invented card.
- Registers use the prototype's in-card search/filter toolbar, status tabs, compact table typography and count footer. The revision register combines description and lineage in one column. The project register retains its trailing navigation chevron.
- Project creation uses the reference's identity, scope, team and first-revision cards alongside a 296px guidance rail. Revision/project editors use 500px/540px sheets with matching headings, helper notes, compact fields, close controls and fixed footers.
- Scoped CSS reproduces 150ms hover/press transitions, 190ms content entry, 180ms overlays and 230ms drawer entry. Reduced motion disables these effects. UI-A's Radix selects retain the approved option states and keyboard behavior; editor autofocus now targets the first enabled input.

### Rendered comparison

Read-only Chrome screenshots were captured at 1440×1000 and 390×844, with animation completion before comparison. Reviewed production Projects, Project Overview, Create Project, Revisions, Revision Overview and both edit sheets against the corresponding HTML/previews. Corrected the initial column structure, header placement, card spacing, line heights, status density, drawer dimensions and overlay tint. Prototype and production desktop content begin at x=284; project rails use 310px and revision rails 330px. Existing application fonts are retained.

### Necessary deviations

- Real records determine descriptions, dates, ancestry, revision counts and row counts. No sample projects or synthetic values were imported.
- The summary metric slots remain in their reference positions but show an em dash because revision metadata does not supply document/equipment/connection totals. Carry-forward choices show “Not recorded” for based revisions, or “Not inherited” without a base; the API does not persist those individual choices in the revision response. Explanatory text replaces the prototype-only notes.
- Prototype demo labels/footer, fake progress and extraction navigation are omitted because those are not production features. Working workspace navigation, query-based deep links and real pending/error feedback remain.
- Actual permissions take precedence over the prototype's blanket historical lock: superseded descriptive metadata stays editable, engineering settings stay read-only. Activation and project lifecycle remain server-confirmed.
- UI-A's labelled mobile navigation dialog is retained instead of the prototype's icon-only fallback rail. Tables scroll within their cards to keep real fields available on narrow screens. This preserves accessible wayfinding and the existing mobile shell.
- Native production icons and the retained application fonts can differ slightly from the prototype's inline SVG/font rendering. Layout and visual hierarchy otherwise follow the reference rather than an independent redesign.

## Shared UI patterns

UI-C's repeated colors, typography, spacing, radii, control sizes, layout dimensions and motion values now live in `apps/web/src/styles/workspace-tokens.css`, reusing UI-A tokens where values match. Scoped workspace CSS consumes these tokens without changing their approved values.

`components/ui/workspace-patterns.tsx` provides reusable cards/card bodies, semantic detail lists, form sections, checkbox fields, drawer headers and action footers. Project/revision pages and forms share these presentation components; callers retain formatting, draft state, validation, permissions and mutation behavior.

The cleanup's read-only before/after Chrome comparison covered nine desktop/mobile page and drawer views. All measured geometry was identical; three screenshots were pixel-identical. Remaining screenshot differences reflected live project status changing from Paused to Active between captures, including status counts and lifecycle actions. The comparison made no application writes and reported no page errors.

## Validation

- 291 frontend tests pass across 22 files. Coverage includes exact decimal submissions and explicit clears, omitted unchanged fields, duplicate/permission failures, superseded permission split, draft preservation/discard, project lifecycle, optional-first-revision partial success, independent inheritance choices, confirmed creation/activation, failed activation, dedicated navigation and revision filters.
- Read-only Chrome checks passed at desktop and 390px mobile widths: keyboard project/revision links, legacy redirect, mouse/keyboard status selection, editor discard and retained draft, workspace/back navigation, mobile shell, reduced motion and no viewport overflow. No application data was written and no runtime page errors occurred.
- ESLint, TypeScript validation and the Next.js production build pass. The build includes the new dedicated Revisions route.

No backend, schema, extraction or later UI phase was implemented.
