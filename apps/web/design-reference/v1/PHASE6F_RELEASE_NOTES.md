# PowerForge prototype v1.19.2 — Phase 6F final release

**Released:** November 9, 2026  
**Upstream baseline:** GitHub `adilzafar66/PowerForge`, `main`, `apps/web/design-reference/v1`, commit `a2e2ad222ef84d3751df6a88c58159eef73c20dc`.  
**Change scope:** Phase 6F Documents and Evidence viewer only; prior unrelated workspaces, styling assets and baseline documentation retained.

## Final design delivered

- The existing Documents register has an AI extraction column, status information in the nonmodal inspector, and Start extraction for single or multiple documents. Confirmed type and explicit PDF pages govern the batch; unaccepted AI suggestions do not.
- Removed redundant **three-dot menus from document rows**. Clicking a document row opens its inspector; existing contextual lifecycle, download and metadata controls remain in that inspector.
- Three-step **Source → Enrichment → Extraction** wizard. Enrichment readiness/reuse is displayed, missing preparation is queued automatically after one final consent, and page-specific forced OCR is an optional advanced override. No new automatic hybrid-PDF OCR policy.
- **Comprehensive extraction by default:** Engineering text and tables/schedules are included as separate provider runs. The collapsed Advanced extraction settings provides two checked toggles; either can be disabled, but not both, and the run count/consent accurately reflect Targeted or Comprehensive mode.
- **Scalable Candidates browser:** searchable and filterable source groups → focused candidate details with inline provenance, original readings and source highlighting, preserving back/search/filter state and supporting a simulated 50-group case.
- **Candidates | Run history only** in the Evidence Viewer. Table-derived engineering observations are visible alongside engineering-text candidates without merging run identities. Raw table output remains an optional collapsed technical disclosure under Run history. The rejected v1.20 linked-table/tab design is excluded.
- Existing project, revision, topology, equipment and design-system prototypes are unchanged from the verified GitHub baseline. The baseline Projects revision-activity rail was restored from GitHub `main`, not from an older exported archive.

## Contents and provenance

Modified from main: `index.html`, `README.md` (Phase 6F addendum), `prototypes/powerforge-documents-prototype.html`, `prototypes/powerforge-document-evidence-prototype.html`. Added: this final release note, `PHASE6F_DESIGN_NOTES.md`, `PHASE6F_IMPLEMENTATION_PROMPT.md`, Phase 6F preview screenshots, and focused Phase 6F QA scripts. The previous `UX*` release notes and `CODEX_HANDOFF.md` remain as originally present on GitHub `main`—they are part of the baseline, not an incremental Phase 6F changelog. No intermediate Phase 6F release notes are bundled.

## Constraints

The package contains **static interactive UX prototypes**, not a PowerForge production change. No live uploads, OpenAI processing, OCR, durable batch coordinator, AI model results, engineering acceptance or API requests are implemented. Actual costs, provenance/geometry, source eligibility and authorization require the real application. Do not implement production orchestration as browser timers.

## Review

Open the root `index.html`, inspect Documents and Document & Evidence Viewer, exercise document selection and the three-step wizard, switch Comprehensive ↔ Targeted mode, navigate Candidates source groups, inspect evidence provenance and separate Run history. See `PHASE6F_DESIGN_NOTES.md` for final behavior and `PHASE6F_IMPLEMENTATION_PROMPT.md` for Codex implementation instructions. Run the included `qa/test_phase6f_*.py` scripts in a local Playwright/Chromium environment.
