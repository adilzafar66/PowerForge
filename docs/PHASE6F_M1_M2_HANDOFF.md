# Phase 6F M1 and M2 handoff

## M1 — Documents and extraction reads

Implemented on `codex/phase-6f-extraction-ui` from `a2e2ad2`, the accepted Phase 6E M5 baseline with the M4 publication fix.

The Documents register shows AI Extraction after AI Classification. The existing inspector shows Engineering, Tables, and source-enrichment status with links to evidence and recent runs. The register uses a bounded revision-level status endpoint and keeps the latest attempt separate from the latest result compatible with the current processing version. Row selection is independent of the open inspector. Filtered, all-eligible, and confirmed-type selections report skipped rows. Confirmed type comes from revision document metadata.

The trailing row menu was removed per v1.19.2. The inspector retains page access, metadata, classification and processing actions, Download, Open original for supported formats, and Remove or Restore. Start extraction is gated pending M3. The bulk toolbar can be reviewed without creating an operation.

## M2 — Extraction Evidence and history

The existing viewer has a paginated, searchable source-group register over independent Engineering and Tables runs. Effective results are selected per family. Opening a historical run starts an explicit selection. The other family can be chosen independently in Run history. Group identity includes the producing run, and Ungrouped observations remain distinct by run. The group list and focused candidate view are URL-addressable.

Candidate evidence uses the signed image from the pinned processing version. Native and OCR regions are normalized to that image's upright frame. Page-only citations retain navigation and do not display a rectangle. Raw tables appear in a technical disclosure within the producing run's history. Recovery actions use the existing retry and cancellation semantics, with revision mutability rechecked for viewer actions and confirmation before retrying remote work.

## Backend impact

The revision status and source-group endpoints are additive. Existing candidate and run reads accept optional viewer filters, and legacy evidence can opt into a signed pinned image. The standalone extraction and source-enrichment APIs remain available. M1 and M2 require no schema migration or worker changes. Provider profiles, prompts, registry mapping, OCR policy, and stored evidence contracts are preserved.

## Verification

- **PostgreSQL** — 184 targeted tests passed on a disposable database migrated through `0016_enriched_extraction`. The suite covered the new bounded status and 52-group read queries, exact source evidence, family and revision authorization, and existing document and extraction behavior.
- **Frozen resources and evaluations** — 166 tests passed for extraction identities, source and layout resources, and the engineering and table evaluation suites. The host reproduced the frozen PNG fixtures. The prior Linux zlib reproduction exception remains documented in the [Phase 6E handoff](PHASE6E_HANDOFF.md).
- **Frontend** — 349 Vitest tests passed. TypeScript, Next lint, the production build, Ruff, and whitespace checks passed.
- **Visual QA** — 20 Chrome captures of the actual Next.js routes against the deterministic [Phase 6F fixtures](../apps/web/visual/phase6f.mjs). The register, inspector, 52-group browser, selected OCR source, and history diagnostic were exercised at 1440, 1024, 768, and 390 px. The captures are under `apps/web/.visual-artifacts/phase6f-m1-m2/baseline/`. These are interaction and visual checks using fixtures.
- **Environment limit** — The 37 enriched extraction and source-enrichment integration cases stopped during setup because this host lacks Tesseract. No paid provider calls were made.

M1 and M2 are ready for review. M3 owns the wizard, exact readiness plan and durable launch. M4 owns bulk execution and operation monitoring. The approved View operation placement belongs to those milestones.
