# PowerForge UX-8 — Topology Workspace

**Version:** 1.7  
**State:** UX design prototype for review; not production implementation.

## What changed
- Added an interactive Topology workspace built around the approved Option A shell.
- Both Nodes and Connections are visible, with compact searchable/filterable tables and a shared lifecycle filter.
- Added a nonmodal quick inspector for nodes, managed terminals, and connections.
- Added right-side forms to create/edit standalone junctions and connection data.
- Added simulated removal/restoration flows that reflect Phase 5 conservative lifecycle rules.
- Added demo read-only revision mode and contextual messages.
- Kept earlier v1.6 prototypes, screenshots, and documentation unchanged except the gallery and appended handoff notes.

## Intentionally not included
- No graph editor or automated topology inference.
- No new canonical model fields or API design changes.
- No backend connection or cross-prototype synchronized data.
- No new Figma edits; approved Figma Option A is unchanged.

## Review checklist
1. Does the list-plus-inspector pattern feel right for Nodes and Connections?
2. Is having both tables on one screen preferable to separate tabs?
3. Do the edit drawers present the correct level of technical detail?
4. Are conservative removal/restoration warnings sufficiently clear?

## QA
Run `python qa/test_topology_prototype.py` with Playwright Python and system Chromium installed (the browser executable path is currently `/usr/bin/chromium`).
