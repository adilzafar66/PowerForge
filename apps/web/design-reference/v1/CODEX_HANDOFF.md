# PowerForge UI/UX Design Handoff for Codex

## Design autonomy and non-prescriptive references (v1.12)

**Treat the prototypes as UX inspiration, not pixel-perfect deliverables or a checklist of UI widgets.** Codex has discretion to reorganize sections, refine layouts and spacing, reuse existing production components, simplify navigation, remove redundant controls, and improve the user experience when it better fits PowerForge architecture. Do not add a control merely because the prototype displays one. Keep useful functionality, not ornamental redundancy.

**Keep the font family already used by the production app.** Fonts visible in prototype HTML are example styling, not a mandate to change fonts. The source of truth for current application architecture, routing, server state, API contracts, engineering invariants and access control is the repository at implementation time.

The prototype's mock project/revision counts, status actions, cross-file links, and view transitions are illustrative only. They are not requirements to copy into production and do not override existing behavior.

## Priority and source hierarchy

1. **Engineering behavior:** The actual PowerForge repository on `main`, with Phase 5 canonical-model rules, atomic equipment editor endpoint, terminal-profile and revision protections. Existing behavior wins over any simplified mock interaction.
2. **Optional visual reference:** Figma **Option A**, [App Shell + Equipment List](https://www.figma.com/design/YEcVV661Evf26gqMgrolCk?node-id=2-34), and existing application conventions. The React application may reasonably differ.
3. **Non-prescriptive interaction references:** The HTML prototypes in `prototypes/`; their patterns and interactions may be adapted, consolidated, or simplified for the architecture.
4. **Optional token examples:** `design-tokens.css` shows a proposed palette and dimensions; prefer established project tokens when appropriate.

**Do not blindly convert the HTML into React.** Use its visual and interaction patterns to refactor the existing frontend and reusable components. Retain all backend/engineering invariants.

## Prototype files and supported interactions

| File | UI demonstrated | What to examine |
|---|---|---|
| `prototypes/powerforge-equipment-prototype.html` | Equipment list, quick details, full editor | Nonmodal browsing, selected row, editor tabs, compact attributes, Return/Save states |
| `prototypes/powerforge-document-evidence-prototype.html` | Document inspector + Phase 6 evidence browser | Thumbnail rail, zoom and pan, panel controls, grouped candidate list, page-to-evidence highlighting |
| `prototypes/powerforge-project-revisions-prototype.html` | Revision list/overview, create, edit, and activation dialogs | Cross-revision navigation, independently selected carry-forward, deliberate activation, revision metadata editor, lifecycle statuses |
| `previews/*.png` | Static review images | Visual comparison only; HTML files are interactive |

All three prototypes are self-contained and work without a build process or external dependencies. They contain original illustrative engineering SVGs and locally simulated state.

## Approved information architecture

- **General:** Projects.
- **Project:** Overview, Revisions.
- **Current Revision:** revision selector; Documents; Engineering Model → Equipment, Topology; Extraction (when implemented).
- **Footer:** System Status.
- Clicking a **revision label** opens Revision Overview. Clicking its **chevron** opens a revision switcher.
- Sidebar remains visible on desktop and adapts on smaller displays.
- Keep the current application font family; use existing token conventions where sensible. The reference action blue is `#24557A`.

## Equipment experience: must preserve

- Equipment row opens a **nonmodal Quick Details** panel without losing the list/filter state.
- Quick Details → `Edit` navigates to a **dedicated, URL-addressable Full Editor**.
- Full Editor: `General`, `Attributes`, and `Terminals` in a single draft/save transaction. Keyboard Save and unsaved-change confirmation must remain correct.
- Compact attribute rows must still support value type, units, precision, information state, notes, origin, verification, critical/required hints, enum behavior, and registry metadata. The demo covers only a subset.
- Real equipment and topology changes must preserve all Phase 5 lifecycle, inheritance, and transactional safeguards.
- Only use optimistic UI for safe/reversible operations; do not imply an engineering edit succeeded until server confirms.

## Document and Phase 6 Evidence UX: must preserve

- Source document takes center stage; source-page inspector is useful even without an extraction run.
- Thumbnail navigation, zoom ±, fit-page/width, pan/scroll, collapsible panels, keyboard accessibility.
- `Document` mode shows processing, classification, origin/version metadata. `Extraction Evidence` mode shows run status, candidate grouping, candidate states, source regions and verbatim snippets.
- Selecting a candidate jumps to its page and highlights supporting text/region; no invented geometries when evidence is page-only.
- *Document-scoped source extraction, revision-scoped visibility.* Source-local groups can be untagged; `equipment_mention_id` and source-group links may be nullable. Preserve unmapped/uncertain raw observations.
- SLD `TX-101` and an untagged specification with `750 kVA` do **not** automatically become the same physical asset. **Phase 7**, not Phase 6, handles identity inference.
- `system_frequency` and `system_phase_count` are manual-only, not Phase 6 extraction targets.
- The prototype `Run extraction` control simulates progress; Phase 6B is responsible for real orchestration and polling/status updates.
- Do not add canonical equipment mutations, review approvals, or Phase 7 matching to the Phase 6 viewer.

## Project and revision experience (new in v1.2)

- **Unified Project Overview** starts with Project Information, metadata editing and lifecycle. **Revision activity follows** (current work, active revision, status/counts and recent revision history); link to dedicated Revisions and Revision Overview. The sole overview reference lives in the Projects prototype.
- **Revisions** is a project-level destination listing revisions with search, status filters, ancestry, and lifecycle status. The sample includes Active, Draft and Superseded; production data comes from the API.
- **Revision Overview** is distinct from the project-level list and from the working Documents/Engineering Model views. Status, ancestry, inherited documents/model provenance and navigation remain discoverable.
- The current revision label in the sidebar goes to its **Revision Overview**; the adjacent chevron opens a **revision selector**. Switching revisions must update the route and project/revision context.
- **Create revision** exposes identifier, description, optional base, independent carry-forward flags for documents and canonical engineering model, and optional activation on creation. Preserve existing backend semantics and clear eligibility/readonly rules.
- **Edit Revision (refined in v1.7):** Show the pencil **Edit** button in the top-right of the **Revision Information** card header (not the page header). This opens the dedicated right-side editor. Current backend supports `PATCH /api/projects/{project_id}/revisions/{revision_id}` with `identifier`, `description`, `system_frequency`, and `system_phase_count` (see `services/api/src/powerforge_api/routers/projects.py`, `schemas/projects.py`, `revision_service.py`). The existing frontend `apps/web/src/lib/projects.ts` lacks an `updateRevision` wrapper, so add a thin typed client method; do not create a new endpoint. `RevisionUpdate` fields are optional, including explicit `null` to clear system-wide settings. Validate nonempty unique identifier, positive finite decimal frequency, and phase count of `1`, `3`, or null. `system_frequency` and `system_phase_count` are manual-only and must **not** be populated from document extraction. Preserve exact decimal strings in UI rather than lossy number formatting.
- Editing the descriptive fields does not alter lifecycle, base revision, ancestry, documents or engineering-model inheritance. A rename should refresh all affected labels (current sidebar, breadcrumbs, revision list, base revision display); the backend uses stable IDs. Show inline errors and unsaved-change protection. Only report success when the PATCH resolves, invalidate relevant project/revision queries, and never clobber local form drafts during background refresh.
- The prototype conservatively disables edits for `SUPERSEDED` historical revisions. **Backend is authoritative:** its metadata-only update path differs from the model-metadata writable-revision path; establish product policy rather than inferring that all superseded metadata mutations are forbidden by the API. Paused/archived/cancelled project restrictions still apply. System-wide engineering changes require a writable revision.
- **Activate** only when the backend allows it: an eligible newer Draft; successful activation supersedes the former active revision. Show a confirmation and meaningful pending/error state; no optimistic claim that an engineering revision has activated before the server confirms.
- Paused, archived and cancelled project mutability restrictions; historical revision read-only behavior; and revision ancestry are backend-authoritative. The demo's local state does not implement every real guardrail.
- Mock revision counts, dates, descriptions, success toasts and status changes are illustrative, **not** representations of actual client/project data.

## Recommended frontend implementation approach

1. Establish app-shell layout, route-based navigation, header, and responsive sidebar in the existing Next.js application.
2. Centralize tokens, typography, buttons, tables, overlays, accessible controls, motion duration and reduced-motion handling.
3. Introduce a server-state query layer (e.g., TanStack Query) with deterministic invalidation, loading/skeleton, background refetch and recoverable errors.
4. Migrate Equipment list → Quick Details → Full Editor incrementally; preserve draft state on refetch.
5. Build a reusable, efficient zoomable document-page surface on existing `DocumentPage`/`PageArtifact` data, with stable normalized coordinate transform and source-highlighting layer.
6. Add actual Phase 6 candidate UI only after the Phase 6 endpoints are available, reusing the viewer surface.
7. Add tests for keyboard focus, loading/error states, unsaved changes, revision read-only restrictions, evidence highlighting, multi-page navigation, and operation outcomes.

**Scope boundaries:** This handoff does **not** authorize implementing all phases at once. Work in small, independently reviewable frontend PRs. Do not rewrite the backend or alter `registry-v1` to match illustrative HTML.

## Simulation caveats

- Sample drawings, tags, ratings, processing states, and extraction candidates are mock examples. The PDF content is an original inline SVG, not a customer drawing. The screenshot fixtures and Figma design are aesthetic references, not authoritative engineering records.
- Not all nav items are wired in the local HTML; pop-up notices are intentional.
- Prototype 'Save' and 'Run extraction' do not call APIs, persist data, or create model records. Simulated progress and confidence are not calibrated signals.
- Native Figma layers for Quick Details, Full Editor and Document/Evidence viewer are still pending because the connected Figma account hit a tool-call limit.

## Links to pass Codex

- PowerForge repo: `https://github.com/adilzafar66/PowerForge`
- Approved Figma: `https://www.figma.com/design/YEcVV661Evf26gqMgrolCk?node-id=2-34`
- Add this package at a stable `docs/design/prototypes/powerforge-ux-v1.7/` path (or another agreed location) in the working branch before asking Codex to implement any slice. Point Codex to local file paths, not transient ChatGPT sandbox URLs. Adapt layouts to production rather than copying the HTML exactly.


## UX-7 — Projects List, Create & Edit (v1.7)

**Visual & interaction reference:** `prototypes/powerforge-projects-prototype.html`; screenshots in `previews/projects-list-preview.png`, `create-project-preview.png`, `edit-project-preview.png`.

### Existing implementation (verify branch before changing)
- `apps/web/src/components/project-list.tsx` — list, text search, status segmented filters.
- `apps/web/src/components/create-project-form.tsx` (or project create page; inspect actual tree) — create UI.
- `apps/web/src/components/project-detail.tsx` — project metadata editor, revisions, lifecycle operations.
- `apps/web/src/lib/projects.ts` — `ProjectCreateInput`, `ProjectUpdateInput`, status types and request helpers.
- Backend: `services/api/src/powerforge_api/routers/projects.py`, `schemas/projects.py`, `services/project_service.py`.

### API alignment (do not improvise)
- `GET /api/projects` with optional search/status; `POST /api/projects` creates ACTIVE project.
- `PATCH /api/projects/{project_id}` accepts project_name, client_name, project_address, project_scope, description, engineer_names; **project_number is immutable**.
- Project actions: `POST .../{pause|resume|cancel|archive|unarchive}`; obey state transitions and read-only project restrictions, do not infer from prototype sample data.
- `POST /api/projects/{id}/revisions` is a separate request when the user elects to create an initial revision; do not assume an atomic combined project + revision endpoint.
- Archived project's restored lifecycle status is server-authoritative; cancelled project cannot be resumed merely from UI.
- Return informative error states for duplicate project number, failed creation, failed revision creation, and invalid lifecycle transitions. If project creation succeeds but optional first revision fails, show the saved project and an actionable, retryable error—never claim both failed or silently roll back the project in the browser.

### UX requirements
- Keep left navigation, active project/revision context, scoped page headers, #24557A action blue and neutral card styling.
- Place contextual `Edit` in Project Information card, not globally next to the project title.
- Use full-width desktop list, compact filter bar, direct row navigation, and responsive table behavior.
- Create flow: required project number/name, optional client/address/scope/description/engineers; optional first revision with identifier/description and activation.
- Edit flow: unsaved-change guard; no field for immutable project number; let server validate; disable save while unchanged/in flight; show pending/success/errors; refresh dependent data after confirmed success.
- Use TanStack Query (or established project server-state strategy), query invalidation after writes, and skeletons on initial load. Keep existing content visible while refetching; avoid need for manual reload. Background refresh must never overwrite dirty forms.
- Confirm irreversible or impactful lifecycle changes, respect server-authoritative status, and show accurate update feedback.
- Respect reduced-motion and accessible focus management, labels, error announcements and keyboard dismissal.

### What is NOT production logic
- Sample project IDs/numbers and revision counts, DOM replacement, setTimeout delays, simulated saves/toasts, and cross-file links are demonstrations only. Implement in existing React components and route structure, not by embedding mock HTML verbatim.
- The Quick Details & Full Editor and Phase 6/7 architectures remain owned by their separate handoffs; this milestone is project-management UX only.


## UX v1.7 — Project/Revision Information spacing refinement

- **Project Overview / Project Information:** removed the redundant `border-top` and 15px `margin-top` on `.kv-grid`. Existing row separators remain.
- **Revision Overview / Revision Information:** added `.revision-info-body` on the correct `card-pad` container with `padding-top: 8px` instead of the shared 24px. All other card padding remains unchanged.
- This is a presentation-only adjustment: no data, lifecycle, editing, or backend behavior has changed.


---

## UX-8 addition — Topology workspace

**Prototype:** `prototypes/powerforge-topology-prototype.html`  
**Screenshots:** `previews/topology-overview-preview.png`, `previews/topology-terminal-details-preview.png`, `previews/topology-edit-connection-preview.png`.

**Purpose:** Visual and interaction reference for redesigning the existing revision-scoped Topology workspace. Do not copy mock persistence, routing or engineering semantics from the demo code into production.

**Existing source of truth:**
- `apps/web/src/components/topology-workspace.tsx`
- `apps/web/src/components/model-node-editor.tsx`
- `apps/web/src/components/connection-editor-sheet.tsx`
- `apps/web/src/components/equipment-terminals-panel.tsx`
- `apps/web/src/lib/engineering-model.ts`
- `services/api/src/powerforge_api/services/topology_service.py` and topology router
- `docs/TOPOLOGY.md` and ADR-007

**Essential behavior:**
1. Revision-scoped node and connection list views, with Active/Removed/All filtering and meaningful display labels.
2. Editable revisions allow creating standalone `ELECTRICAL_NODE` nodes (optional label) and `ModelConnection` connections. Equipment terminals are normally profile-generated; custom terminals are created through owning Equipment, not a standalone quick-add in Topology.
3. Clicking a row opens a lightweight, accessible quick inspector without losing list context. Distinct edit forms may use an accessible right-side sheet.
4. Managed terminals do not permit independent key, ownership, kind, or lifecycle changes. Editable labels are okay where supported. Custom and standalone node constraints follow the server.
5. Connection edits allow endpoints, kind (`ELECTRICAL`, `GROUNDING`, `OTHER`), direction (`UNDIRECTED`, `NOMINAL_FROM_TO`), phase text, and optional positive nominal voltage. The server normalizes voltage to kV. Production must preserve exact numeric strings and server-owned conversions; do not round through JavaScript `Number`.
6. Parallel connections allowed; no endpoint self-links. Both endpoints must be active for creation, rewiring, and restoration.
7. Removal cascades: removing a node soft-removes active incident connections; restoring that node does not automatically restore them. Restoring a connection is disabled until both endpoints are active.
8. Active/paused projects with writable draft/active revisions allow mutation per server rules; superseded revisions and cancelled/archived projects remain read-only.
9. Preserve read-only inspection, provenance/verification/inheritance metadata, API errors, mutation response handling, and existing document/model carry-forward constraints.
10. No graph canvas or Phase 8/12 topology inference/visualization is authorized by this design.

**UX-specific direction:** Use the approved Figma Option A app shell and `#24557A` action blue. The right-side inspector is nonmodal and keeps the list in view. Side sheets, row focus/keyboard access, pending indicators, confirm dialogs, toasts, and query invalidation must use the shared production UI foundation, not bespoke production HTML.

**Demo limitations:** Read-only mode, filtering, add/edit/remove/restore, and statuses are local state simulations. The demo's voltage field is a presentation example; conversion must be performed by the backend and exact decimals preserved. No actual API requests occur.

**Recommended implementation sequencing:** Align shared shell and server-state infrastructure first (UI-A/B), then implement topology in UI-F when ready. Add regression coverage for permissions, destructive cascades, failed endpoint restoration, keyboard access, data refresh, and no duplicate frontend state mutations.

---

## UX-9 — Design System and Interactive States (v1.8)

**Scope:** Foundation specification and a standalone interactive demonstration. Not yet approved; request user review before implementation. This revision adds:

- `UX9_DESIGN_SYSTEM_SPEC.md`: semantic color/type/spacing tokens, component contracts, cache/refetch/async data behavior, job polling, alerts and toast design, motion/accessibility, responsive acceptance, and preliminary UI-A/UI-B sequencing.
- `prototypes/powerforge-design-system-prototype.html`: visual reference for Foundations, Components, API & Jobs, Feedback & Forms, and Motion & Accessibility.
- `qa/test_ux9_prototype.py` and `previews/ux9-*.png`: browser interaction and screenshot evidence.

**Critical engineering and API boundaries:** Do not copy the simulated timers/jobs or in-memory array state into production. TanStack Query is **recommended**, not installed in PowerForge; the current app uses `useModelQuery` and manual mutation refresh. If adopting TanStack Query, reconcile SSR/client boundaries and incrementally migrate query state rather than maintaining competing caches. Preserve all existing model/revision safeguards, strict decimal serialization, and error codes. No canonical engineering writes should claim success before server confirmation. Never overwrite an unsaved draft during refetch. Use API contract and Phase 5 / Phase 6 specs as source of truth, not example data from HTML. The approved Option A Figma screen remains unchanged.

## UX-9.1 — Selection controls (latest direction)

- **Supersedes native select/checkbox visual styling** in all previously designed workspaces.
- See `UX9_DESIGN_SYSTEM_SPEC.md` → “UX-9.1 — Custom Select & Checkbox refinement.”
- Live examples: `prototypes/powerforge-design-system-prototype.html#controls`; open the menu and use keyboard navigation.
- Source behavior demo: `assets/powerforge-controls.css` and `assets/powerforge-controls.js`; the demo CSS/JS is inlined in standalone HTML prototypes, not production React source.
- Implement production dropdowns with a tested accessible Select primitive (recommended Radix Select), and checkbox with native styling/Radix Checkbox, using existing semantic palette and React controlled state. Preserve null/enum values and backend validation; do not port the vanilla demo machinery as-is.
- All documented permissions, edit guards, read-only behavior and engineering validation remain unchanged.

## UX-9.2 — Historical hover exploration (superseded)

Prior hover colors are replaced by the UX-9.3 rules below.

## UX-9.3 — Final dropdown option states (supersedes UX-9.2 hover colors)

- Unselected option hover **and** keyboard-active highlight: `#F5F8FA` (neutral) over 150ms.
- Selected option remains blue `#E6EEF4` even when another option receives pointer/keyboard focus. Selected option hover: darker blue `#D6E3ED`; merely opening the menu or navigating to the selected item retains the base blue tint.
- Keep disabled options unaffected; preserve checkmarks, focus-visible indication, and reduced-motion accessibility.
- Reference `assets/powerforge-controls.css` and `UX9_DESIGN_SYSTEM_SPEC.md` UX-9.3.
