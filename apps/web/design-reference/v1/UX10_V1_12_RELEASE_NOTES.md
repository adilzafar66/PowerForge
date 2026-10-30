# PowerForge UX v1 — Project Overview consolidation

This update affects the standalone **design reference package only**, not PowerForge application source or Figma.

- Unified the Projects and Revisions prototype overview designs into one **Project Overview** in `prototypes/powerforge-projects-prototype.html#project/p1`. Project Information, editing, project lifecycle and summary are shown first; the current-work card, active revision details, metrics and revision history follow below.
- The Revisions prototype now links to that one overview; `#overview` redirects there for compatibility. Revisions and Revision Overview remain in the revision prototype.
- Removed redundant route-like labels above main page headings; existing app-shell breadcrumbs provide location context.
- Removed the redundant **Actions / View** column from the Revisions table. Rows remain clickable and keyboard accessible.
- Updated `README.md`, `CODEX_HANDOFF.md`, and `UX9_DESIGN_SYSTEM_SPEC.md`: the HTML prototypes are **non-prescriptive references**. Codex may improve layouts, remove redundancy and **retain the existing application font family**. Do not copy mock backend behavior.
- Existing dropdown v1.11 states, including unselected hover `#F5F8FA` and selected hover `#D6E3ED`, are unchanged.

This reference is not a production API contract.
