# Phase 6F release handoff

Phase 6F integrates extraction into Documents and source review into the existing document viewer. The wizard records one consent for a reviewed selection and starts separate Engineering and Tables runs once each document has the exact required local preparation and layout. The [M1–M2 handoff](PHASE6F_M1_M2_HANDOFF.md) covers the register and evidence contracts. The [M3–M4 handoff](PHASE6F_M3_M4_HANDOFF.md) covers execution and recovery.

M5 exercises the deployed service boundaries, the schema upgrade from 0016, historical runtime identities, and the production React routes.

- Migration tests verify the existing 0017 schema, downgrade guard, retained source artifacts, and a pending v4 retry across the upgrade. The OpenAPI compatibility test checks each legacy route by path and method. [0017 migration tests](../tests/test_migration_0017.py) · [0016 migration tests](../tests/test_migration_0016.py) · [OpenAPI test](../tests/test_extraction_contracts.py)
- Browser checks exercise run-scoped history, native and OCR regions, a page-only observation, and distinct unmapped and invalid readings. The evidence browser uses a singular label when exactly one group matches. [Fixtures](../apps/web/visual/phase6f.mjs) · [Capture harness](../apps/web/visual/run.mjs) · [Evidence browser](../apps/web/src/components/extraction-evidence-panel.tsx)

## Deployment checklist

- [ ] Back up PostgreSQL and the source artifact store. Quiesce extraction scheduling and drain the extraction and enrichment queues for the upgrade. Keep the database and retained source artifacts together in the recovery plan.
- [ ] Apply `alembic -c database/alembic.ini upgrade head` with the deployment database URL. Verify that `alembic -c database/alembic.ini current` reports `0017_extraction_operations`. The Compose API entry point also upgrades before serving traffic. Deploy the API, web, extraction worker, source-enrichment worker, and extraction scheduler from the same revision.
- [ ] Confirm that the extraction worker consumes `document_extraction`, the source worker consumes `source_enrichment`, and one extraction scheduler publishes periodic recovery tasks. Check API readiness, broker connectivity, and browser access to the configured signed-object endpoint.
- [ ] Run `docker compose run --rm source-enrichment-worker python -m extraction_worker.tesseract` to get the deployed engine and language identity. With local preparation enabled, set `ENRICHMENT_ENABLED=true` and the actual `ENRICHMENT_OCR_CONFIGURATION` consistently across the API, extraction worker, source worker, and scheduler. Align extraction profile settings across those services.
- [ ] Keep `EXTRACTION_EXTERNAL_ENABLED=false` during the first smoke check. Confirm that read-only evidence still loads and that the wizard displays the deployment validation error. Enable external extraction only with deployment authorization. Give the OpenAI credential to the execution worker and verify its model configuration. Review the five `EXTRACTION_OPERATION_*` caps and the existing per-profile budgets before admitting remote work.
- [ ] Run the manual smoke checks below on an approved staging revision. Confirm that the operation is reachable after reload and that both run families retain their own status, evidence, and history. Review the deployment's access controls before exposing the API in a shared environment. Revision membership checks assume the existing trusted deployment boundary.

An empty 0017 operation history can downgrade to 0016. Once an operation exists, the migration rejects downgrade to protect consent and scheduling history. Plan to forward-fix or recover from the coordinated pre-upgrade backup. Preserve the retained audit data during recovery.

## Operator recovery

- An operation stuck in **Queued** calls for checking Celery beat, queue routing, and worker connectivity before starting another operation. Use the saved operation ID to inspect the same record after reconnecting.
- A document stuck waiting on local work calls for checking its exact preparation and layout attempts and the configured OCR identity. A missing, corrupt, or superseded pinned source can block its dependent profiles. Use a new reviewed plan when the source version changes.
- **Cancel operation** stops future admissions. Already-admitted children can finish. Other documents and profiles can retain usable results after a partial or failed attempt.
- **Retry** appends an attempt to an eligible child. A provider call with an unknown outcome can already have consumed usage. Review it and acknowledge that outcome explicitly before retrying. **Re-extract** is a separately confirmed plan for an eligible historical run.

## Manual QA routes

1. In **Documents**, open a processed row and use **AI Extraction → Start extraction**. Review an exact page range, then use the optional OCR override on one selected page. Check that the readiness view distinguishes reuse and work that will be prepared automatically. Exercise Comprehensive and each Targeted choice before consenting.
2. Repeat from the bulk selection toolbar using selected rows, current filters, and a confirmed type. Check the skipped-source explanations and that an unaccepted suggestion does not select a source for its suggested type.
3. After the approved confirmation, open **View operation**. Reload and compare local and remote child states. Exercise partial or blocked recovery and cancel future scheduling with the deterministic test setup.
4. Open **Extraction Evidence → Candidates**. Search the dense fixture, page through results, and return from a focused group with the search intact. Inspect native and OCR rectangles and a page-only citation. Reload a candidate deep link. In **Run history**, select a historical run, choose the other family independently, and open the collapsed raw table diagnostic under Tables.
5. Reopen the viewer on a read-only revision. Inspect results and run history with mutation controls absent.

## Visual review

The Chrome harness renders the React routes with deterministic HTTP fixtures. It exercises the register and inspector, all wizard steps and both plan modes, operation monitoring, the 52-group browser, source details, historical runs, and the table diagnostic at 1440, 1024, 768, and 390 px. It also captures 11 states at the exact dimensions of the supplied design previews. See the [browser commands](../apps/web/visual/README.md). Local captures and prototype comparisons are in `apps/web/.visual-artifacts/phase6f-m5/`.

The React screens retain the application shell, shared dialog and existing responsive drawers. The fixture values and document images differ from the prototype. The production wizard lists profile and admission details for the reviewed plan, so its plan panel takes more vertical space. The register displays backend-attested unavailability and the viewer pages the group list in bounded groups of 25. The approved **View operation** and **Re-extract** actions appear in the production workflow.

## Verification

- The backend gate passed 2,096 tests on Linux ARM64 with disposable PostgreSQL, Redis, MinIO and Celery workers on an internal network. `alembic -c database/alembic.ini upgrade head` reached 0017. Migration tests verified the empty rollback, the retained-consent guard and an existing v4 retry across the upgrade. Transport tests used stubbed OpenAI responses and exercised partial completion, recovery, concurrent admission, and source and revision scope.
- The macOS resource and evaluation run passed 181 tests, including the three accepted PNG byte assertions. The Linux regression excludes those same three cases due to the known zlib difference documented in the [Phase 6E handoff](PHASE6E_HANDOFF.md). The existing v1–v6 identity and frozen evaluation assertions were exercised.
- `python -m extraction_worker.spatial_evaluation --corpus evals/spatial/v1/corpus.json --output /tmp/phase6f-spatial-report.json --artifacts /tmp/phase6f-spatial-artifacts` completed all 15 authored cases with local Tesseract and scripted observations. The viewer fixtures use synthetic readings and source locators for UI checks.
- `npm test` passed all 355 frontend tests. `npm run lint`, `tsc --noEmit --incremental false`, `npm run build`, Ruff, Python dependency checks, `docker compose config -q` and whitespace checks passed.
- Chrome produced 56 Phase 6F captures and 125 cross-workspace captures with passing interaction checks. Prototype review compared layout, hierarchy and interaction at matched viewport sizes. The strict repeat comparison flagged 2–36 changed pixels in 11 Phase 6F captures. Screenshot dimensions and computed geometry matched in all 56. The comparison results and diff images are retained in the `actual` directories.

**Release decision.** The local implementation is ready for review. Live OpenAI accuracy, real-document coverage, production load, and deployment smoke checks remain open.

## Remaining Phase 6G work

- Measure OpenAI recognition, mapping, and grounding on an approved representative document set. Expand coverage of degraded scans, hybrid pages, irregular schedules, and real-document OCR and layout. The 6E spatial suite measures local preprocessing and scripted conversion on authored cases.
- Measure latency, usage, concurrency, and queue recovery under deployment load. Run restore and upgrade rehearsals using representative persisted histories. Review security and access boundaries for shared deployment.
- Resolve or explicitly retain the platform-dependent PNG byte reproduction exception before the freeze. See the [Phase 6E validation record](PHASE6E_HANDOFF.md).
