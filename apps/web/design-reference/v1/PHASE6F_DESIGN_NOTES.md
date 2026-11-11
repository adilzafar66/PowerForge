# PowerForge — Phase 6F final prototype design

**Approved revision:** v1.19.2 | **Source baseline:** `adilzafar66/PowerForge`, `main`, `apps/web/design-reference/v1`, commit `a2e2ad222ef84d3751df6a88c58159eef73c20dc` (2026-11-08 UTC).

These are standalone, self-contained HTML **design examples**. Their data, simulation timers, extraction results, source locations, run outcomes, success toasts and counts are synthetic. They make **no network, OCR, OpenAI or production API calls**.

## Placement and navigation

Phase 6F belongs in the existing **Documents** register and **Document & Evidence Viewer**, not in a new standalone Extraction sidebar item. Keep the approved PowerForge shell, navigation, semantic colors, input styling, and nonmodal document inspector. The document register has columns for Document, Confirmed type, Processing, AI classification, **AI extraction**, and Origin. The redundant trailing three-dot document-row action column is removed: clicking a row opens the inspector, which retains Download, Remove/Restore, metadata, processing, classification and extraction context.

## Single and bulk extraction

The register supports selecting individual eligible documents, all filtered eligible documents, or a set based on their **confirmed** classification type; an unaccepted AI suggestion cannot define a confirmed-type group. The same Start extraction workflow works from a document inspector or a bulk selection.

The guided modal consists of three steps:

1. **Source.** Review selected eligible, processed documents and edit explicit 1-based PDF page intervals for each; reject invalid ranges and removed/unready documents.
2. **Enrichment.** Present a *read-only* plan for reused and missing preparation artifacts. Missing preparation is **automatically queued after the single final Start extraction confirmation**, rather than requiring an extra manual Prepare click. Provide an optional advanced whole-page OCR override for specified selected pages; do not pretend the underlying conservative hybrid-PDF OCR eligibility logic has changed.
3. **Extraction.** Default to **Comprehensive extraction**: both independent engineering-text and table/schedule pipelines. A *collapsed* Advanced extraction settings disclosure contains exactly two initially checked choices: **Extract from engineering text** and **Extract from tables and schedules**. Either may be disabled, producing a Targeted extraction summary, but never allow both to be disabled. Update provider-run counts, plan summary and consent wording accordingly. Explicit external-processing consent is required before launch. Run identities, retries, source metadata and histories stay separate for the two extraction profiles; Comprehensive is not a new combined backend profile.

After confirmation, extraction for documents needing new preparation remains queued until its dependencies finish. One document's preparation failure blocks only its own dependent extraction jobs. The static demo simulates this; durable worker-backed multi-document orchestration is an implementation requirement, **not** provided by browser JavaScript.

## Document & Evidence Viewer

Preserve the existing Document / Extraction Evidence mode switch, original drawing viewport, zoom and page navigation. The evidence inspector has **two tabs only: Candidates and Run history**. There is **no separate Tables tab**, source-type filter or cross-linking of table-cell records into candidates. The accepted design is v1.19's scalable group browser plus v1.19.2's comprehensive extraction default, *not* rejected v1.20 table-linking.

Candidates presents source-grounded engineering observations from independent engineering-text and table/schedule runs in one **read-only** two-level browser: a searchable, filterable source-group list and a focused candidate view. The group list supports page, equipment-type-hint and mapping-status filters, incremental paging and back navigation that preserves filter/search/scroll. A synthetic **50-group preview** tests dense documents. A source-local ungrouped bucket is permitted, but it does not authorize cross-document equipment-identity matching or merging duplicate-looking candidates.

Selecting a candidate highlights its exact source span when supported by source geometry; otherwise use page-only location without fabricating coordinates. Show selected-candidate provenance inline, including original reading when it differs from normalized display, mapping status and run identity. A Source details disclosure expands text/context/limitations; Locate source only appears when the selected evidence is on another page. No permanent duplicate Selected Source Evidence footer.

Run history displays separate Engineering and Tables runs, including historical/partial outcomes, and may expose a **collapsed optional technical raw-table diagnostic**. Do not create a third top-level Tables view. The underlying table structures and data provenance remain available to the backend without implying table-cell-to-candidate links.

## Engineering boundaries

Phase 6F produces immutable source-bound observations with uncertainty and independent run/source identity. It does **not** accept candidates into the canonical model, reconcile cross-document equipment identity (Phase 7), infer topology (Phase 8), validate against other records (Phase 9), perform engineering studies (Phase 10) or add formal engineer approval (Phase 11). `system_frequency` and `system_phase_count` remain manually entered revision metadata. All true state, authorization, costs, retries, idempotency, budgets and retention are backend authoritative.

## Browser review

Open `index.html` and navigate to the Phase 6F Documents / Evidence entries. For automated static checks use `qa/test_phase6f_prototype.py`, `qa/test_phase6f_auto_enrichment.py`, `qa/test_phase6f_group_browser.py`, `qa/test_phase6f_comprehensive_default.py`, and `qa/test_phase6f_row_menu_removed.py`. The HTML works offline without a build; these tests require local Playwright/Chromium and check simulated behavior only.
