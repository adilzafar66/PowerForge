# PowerForge — UI-A: Design System & App Shell

Work in `adilzafar66/PowerForge`, starting from the latest `main`. Implement **UI-A**, the shared visual and navigation foundation for the approved PowerForge redesign. Use a dedicated branch.

## Design references

- **Primary:** The complete approved **PowerForge UX HTML Prototype Package v1** is available at design-reference/v1/. Use it as the primary visual and interaction reference for this implementation. The UI-A prompt takes precedence over historical review-status notes in the package. Pay particular attention to `design-tokens.css`, `UX9_DESIGN_SYSTEM_SPEC.md` (including the final UX-9.3 dropdown states), `CODEX_HANDOFF.md`, and the App Shell/sidebar shown throughout `prototypes/`.
- **Behavioral authority:** existing PowerForge code and API contracts, especially Phase 5 engineering-model and revision safeguards. The HTML prototypes simulate data and should not be ported wholesale.

## Deliverables

1. **Shared visual foundation.** Establish a consistent design-token and typography system and adapt the existing common UI components to the approved aesthetic: Instrument Sans, JetBrains Mono where appropriate, neutral surfaces, restrained borders, dark action blue `#24557A`, and hover blue `#193E5B`. Apply consistent button, input, card, badge, table, menu, form, and overlay styling while maintaining accessibility.
2. **Reusable custom controls.** Provide an accessible themed single-select/dropdown and checkbox system rather than browser-default-looking controls. Match the final v1.11 states: unselected option `#FFFFFF`, unselected hover/keyboard-highlight `#F5F8FA`, selected `#E6EEF4`, selected hover `#D6E3ED`; preserve selected checkmarks and the subtle 150ms transition. Support keyboard, screen readers, disabled/focus states, and reduced motion. Favor established accessible React primitives over copying the prototype JavaScript.
3. **Persistent app shell.** Implement the approved **Option A** left navigation and a restrained project/revision-aware context header, with flexible workspace width and appropriate smaller-screen behavior. Sidebar hierarchy:
   - **General:** Projects
   - **Project (when selected):** Overview; Revisions
   - **Current Revision (when available):** clickable revision label opening its overview; separate chevron opening a revision selector; Documents; Engineering Model → Equipment, Topology
   - **Footer:** System Status
   Hide future modules such as Extraction until they actually exist.
4. **Useful navigation, not mock navigation.** Active states and breadcrumbs should reflect the real URL and real project/revision identifiers. Revision switching should navigate to the selected revision. Preserve existing routes, query parameters, and working document/model destinations; where a planned destination does not yet have a dedicated screen, make the navigation functional using the current application and leave its complete redesign for UI-C–UI-F. Avoid dead links and fake data.
5. **Incremental adoption.** Make current screens usable inside the new shell, with shared styling improvements where they naturally fit, but do not migrate their full feature-specific layouts in this phase.

## Boundaries

- **Do not** redesign the complete Projects, Revisions, Equipment, Documents, or Topology workspaces yet; those are UI-C–UI-F.
- **Do not** introduce the TanStack Query/server-state overhaul, job polling, or comprehensive loading/notification infrastructure yet; those are UI-B.
- **Do not** change the backend, API semantics, canonical engineering data, revision permissions, transactional equipment editing, terminal behavior, or existing lifecycle rules.
- Maintain the agreed distinction between a quick-details inspector and a dedicated full equipment editor for UI-D; UI-A only supplies compatible shared foundations.

Use sound engineering judgment for component structure and libraries. The result should feel like a cohesive PowerForge application, not a visual overlay on the old app. Preserve existing functionality and run the appropriate project checks without introducing unnecessary test scaffolding.

When complete, provide a concise summary of changed areas, any dependencies or follow-ups intentionally deferred to UI-B/UI-C, and the branch/commit reference for review.
