# UX-9.2 — Dropdown Hover Refinement

- Added a subtle **150ms** background and label-color transition on pointer hover over custom dropdown options, using a darker muted blue-gray than the default keyboard-active tint.
- Kept the selection checkmark distinct. Pointer movement updates the active descendant; no selection changes until click/Enter.
- Disabled menu options have no hover treatment. Reduced-motion settings disable transitions.
- Applied across all six standalone HTML prototypes and their shared CSS/JS reference assets.
- Preserved approved UX v1.9 designs; no changes to Figma or production Next.js code.
