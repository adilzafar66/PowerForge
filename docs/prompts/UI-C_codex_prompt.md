# PowerForge — UX-10 / UI-C: Projects & Revisions Workspaces

Implement **UI-C**, the production redesign of PowerForge's **Projects and Revisions** experience, in `adilzafar66/PowerForge`. Use a dedicated branch.

## Starting point and design references

- **Build on the completed UI-A and UI-B work.** Start from the latest `main` **after UI-B is merged**; if UI-B is still unmerged, branch from `codex/ui-b-reactive-data` (including its latest fixes) instead. Do not implement UI-C against the older UI-A-only baseline. Verify the branch before starting.
- **Primary UX reference:** the supplied **PowerForge UX Prototype Package v1**, especially `prototypes/powerforge-projects-prototype.html`, `prototypes/powerforge-project-revisions-prototype.html`, and their associated previews, `README.md`, and `CODEX_HANDOFF.md`. The v1 package has been updated and supersedes older prototype design versions.
- **Production authority:** the current React/Next.js application, TanStack Query foundation, backend contracts, and engineering lifecycle rules. The prototypes are **illustrative references, not pixel-perfect implementation instructions**. Keep the application's existing font, UI-A design system/app shell, and UI-B async/state patterns. Improve, consolidate, or omit reference elements where warranted by usability or production architecture.

## Scope and desired experience

### 1. Projects list and project creation

Redesign the Projects landing page and project creation workflow in the approved restrained Option A style. Provide a clear, responsive project register with useful search, status filtering, lifecycle badges, and direct row/keyboard navigation. Avoid redundant row-level **View** buttons when the whole row already opens the record.

Preserve creation of a project with its existing fields and the **optional initial revision**. Project number and project name are required; project number is immutable after creation. Project creation and initial-revision creation are **two distinct backend operations**: if the project succeeds but the revision fails, preserve the created project, explain the partial success, and support a revision-only retry or navigation to the saved project—never create a duplicate project on retry.

### 2. One unified Project Overview

Implement **one canonical Project Overview** for `/projects/{projectId}`, following `powerforge-projects-prototype.html#project/p1`. Do not create a second competing overview from `powerforge-project-revisions-prototype.html#overview`—that prototype's Overview destination intentionally returns to the canonical page.

**Content order matters:** project information/details and associated lifecycle/editing controls **first**; current work/active-revision access and revision history **below**. Keep the contextual **Edit** action in the Project Information card. Adapt naturally on smaller screens.

Keep the essential project data and controls from the existing app (project name, number, client, address, scope, description, engineers, lifecycle actions, active revision navigation, revision history). Use meaningful server-derived metrics where already available; omit or gracefully defer unsupported counts rather than fabricate documents/equipment/connections or add expensive requests merely to match the mockup. No extra uppercase page-path label above the heading when the App Shell breadcrumbs already provide context.

Project metadata editing must preserve dirty drafts, provide cancel/discard protection, and update the overview, project list, sidebar and breadcrumbs after confirmed saves. Handle pause/resume/cancel/archive/unarchive through existing authoritative rules with appropriate confirmation, restrictions, and feedback.

### 3. Dedicated Revisions list and revision creation

Implement a **real project-level Revisions destination**, not merely an anchor into the Project Overview. Show the project's revisions with useful search/status filters, identifiers, description, ancestry/base revision, status and updated date; selecting a row by mouse or keyboard opens its Revision Overview. **No redundant Actions/View column** for row navigation. Keep project-level navigation and the sidebar's active state correct.

Create Revision should support identifier, description, optional base revision, **independent** carry-forward choices for documents and engineering model, and optional activation on creation. Preserve the backend distinction between omitted defaults and explicit `based_on_revision_id: null` (start fresh), as well as the restrictions around activating only eligible drafts. Show clear pending, success, failure and eligibility information; never claim activation before confirmation.

### 4. Revision Overview and editing

Provide a useful **Revision Overview**, distinct from both Project Overview and the Documents/Engineering Model workspaces. Show revision identity/status, description, creation/update information, source/ancestry, available system-wide settings, and clear links to Documents, Equipment and Topology. Avoid redundant representations of the same information.

Add **Edit Revision** from the **Revision Information card** (rather than a duplicate page-header action), using the established right-side editor pattern or an equally appropriate accessible alternative. The backend already supports `PATCH /api/projects/{project_id}/revisions/{revision_id}`. Add a thin typed `updateRevision` client wrapper if not already present; **do not add a backend endpoint**. Support `identifier`, `description`, `system_frequency`, and `system_phase_count` with existing server validation. An omitted property means unchanged; explicit `null` clears an optional setting. Preserve **exact decimal strings** for frequency; require positive finite values and phase count `1`, `3`, or unset. These system settings are **manual engineering inputs**, not document-extraction results.

Revision editing must not inadvertently change lifecycle, base/ancestry, carry-forward history, documents or engineering model data. Preserve unsaved changes on background refetch, handle duplicate/invalid identifiers and permission errors, and refresh all affected revision labels (including the sidebar and ancestry labels) after confirmed saves. **Check the actual backend permission split:** descriptive revision metadata updates and changes to system-wide engineering settings have different writability rules; do not blanket-disable all metadata edits on a superseded revision if the backend permits them. Other historical engineering data remains read-only. Activation should be separately confirmed, with the previous active revision superseded only after backend success.

### 5. Navigation and UI-A/UI-B integration

Keep the UI-A sidebar, breadcrumbs, project context and revision selector coherent with the new dedicated Revisions page and Revision Overview. Choose sensible Next.js routes while maintaining compatibility with existing URLs and deep links, including `/projects/{id}?section=revisions#revisions`, revision `?view=overview`, and current Documents/Equipment/Topology query-based destinations. Switching revisions must navigate, **not activate**, a revision. Do not break selected-document/equipment links, back/forward navigation, or read-only indicators.

Use UI-B's established TanStack Query cache/invalidation and async/error conventions rather than reintroducing competing local server-state caches or manual refresh counters. Keep local search, filters, and in-progress forms stable during refresh. Preserve keyboard accessibility, mobile usability, focus handling, reduced-motion support, and meaningful empty/loading/error states.

## Boundaries

- **In scope:** production Projects list/create, unified Project Overview/edit/lifecycle, dedicated Revisions list/create, Revision Overview/edit/activate, and the necessary navigation adjustments.
- **Not in scope:** full Equipment redesign (UI-D), Documents and Drawing Viewer redesign (UI-E), Topology redesign (UI-F), UX-wide final polish (UI-G), Phase 6 extraction, new backend services, or engineering model schema changes.
- Preserve the existing backend authority for project lifecycle, revision inheritance, revision activation/permissions, and canonical engineering data. Do not import fake prototype projects, sample counts, simulated saves, or prototype-only navigation behavior.

## Completion

Deliver working, integrated screens—not just shared components or static mockups. Use appropriate focused tests and project checks for the important creation/edit/lifecycle/navigation paths and regressions, without excessive scaffolding. In the handoff, briefly describe the changed screens/routes, any design adaptations or intentional omissions, the existing API behavior used for revision edits, and the branch/commit for review.
