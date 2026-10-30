# PowerForge — UX-10 / UI-B: Reactive Data & Interaction States

Work in `adilzafar66/PowerForge` from the latest `main` (UI-A is already merged). Implement **UI-B**, the shared server-state, asynchronous feedback, and interaction-motion foundation for the redesigned PowerForge application. Use a dedicated branch.

## References and discretion

- Read `docs/UI_A_HANDOFF.md`, the existing frontend and API contracts, and the approved UX design-system guidance in `apps/web/design-reference/v1/UX9_DESIGN_SYSTEM_SPEC.md` and `CODEX_HANDOFF.md`.
- Where available, **PowerForge UX Package v1.14** supersedes older prototype references. Its screens and simulated behavior are illustrative, not implementation specifications.
- Keep the application's existing font family and UI-A shell/components. You may simplify or improve reference UI patterns where that better serves the production architecture and user experience.

## Objectives

### 1. Coherent, reactive server state

Introduce **TanStack Query** as PowerForge's shared client-side server-state layer, integrated correctly with the current Next.js App Router and existing server-rendered data. Establish consistent query identity, caching/refetch policies, and targeted invalidation across the existing workflows:

- Projects, project metadata, revisions, and their sidebar/breadcrumb context.
- Revision documents, including list/detail, processing and classification information.
- Engineering registry, equipment list/detail, topology nodes and connections, and dependent terminal data.

Replace the relevant bespoke loading/refresh patterns rather than layering a second competing source of truth over them. Preserve URL-driven workspace selection and server-side authority. On successful mutations, update or invalidate all materially affected views without requiring a manual browser refresh. In particular, equipment changes can affect terminals and connections; revision activation or metadata edits can affect multiple visible project/revision labels. Avoid broad refetches when narrower invalidation suffices.

### 2. Reliable async and mutation experiences

Implement reusable, restrained visual patterns for:

- Initial loading and skeletons; empty datasets and filtered-zero results.
- Background refetch with existing data still visible and a subtle refreshing indication.
- Initial and subsequent request failures, useful inline errors, and retry/recovery.
- Pending mutations, confirmed success, and failed saves; concise toasts or notices alongside persistent actionable errors.

Preserve local search/filter/selection state and unsaved form drafts during refetch. Late responses from a different project, revision, document, or editor selection must never replace the current context's data. A save or engineering lifecycle change is successful **only after the backend confirms it**; preserve structured validation errors and read-only handling.

### 3. Existing background-job synchronization

Use the existing APIs to keep **document processing and AI classification** status/progress current while their real runs are pending or running. Refresh affected document summaries/details as states change, and stop or reduce polling when jobs finish, views are inactive, or the application is backgrounded. Handle retry, failure, and partial results according to the existing backend semantics. Never simulate job progress or add new backend streaming infrastructure.

Build the polling/async primitives so Phase 6's future extraction workflows can reuse them, without implementing extraction functionality now.

### 4. Subtle motion and accessibility

Polish the existing UI-A components with consistent loading, feedback, and state transitions that support quick engineering work. Use restrained motion (roughly 150–220 ms where appropriate), visible focus, accessible status/error announcements, and `prefers-reduced-motion` support. Avoid distracting animations or layout shifts in dense tables and editors.

## Boundaries

- **UI-B is the shared data/interaction foundation**, not a full redesign of Projects/Revisions (UI-C), Equipment (UI-D), Documents/Viewer (UI-E), or Topology (UI-F). Do not copy prototype mock screens or sample data into production.
- Preserve all current backend contracts, project/revision permissions, engineering registry and model semantics, decimal-string precision, exact boolean/null values, terminal reconciliation, topology removal/restore behavior, URL deep links, and unsaved-change safeguards.
- Do not introduce new backend endpoints, WebSockets, SSE, extraction pipelines, or unnecessary infrastructure. Use the existing API capabilities and practical defaults.
- Apply judgment to keep the solution maintainable and proportional. Avoid redundant local caches, duplicated success messages, indiscriminate invalidation, or excessive test scaffolding.

## Completion

Deliver a functioning UI-B foundation integrated into the current application, not just shared utilities awaiting future adoption. Run relevant project checks and focused regressions for data refresh, job status, failed operations, context switching, draft preservation, and engineering safeguards. Summarize the main changes, any intentional deferrals to UI-C–UI-G, and the branch/commit for review.
