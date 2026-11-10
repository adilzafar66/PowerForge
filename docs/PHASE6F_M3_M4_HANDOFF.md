# Phase 6F M3 and M4 execution contract

M3 and M4 share one revision-scoped operation. The single-document entry and bulk selection both review exact pages through Source, Enrichment, and Extraction. The consent transaction records the reviewed processing version, page identities, whole-page OCR overrides, profile hashes, and operation limits. OpenAI starts disabled by default. The API preview schedules no work.

## Storage and deployment

Migration `0017_extraction_operations` upgrades `0016_enriched_extraction`. It adds operations, per-document child references, and client submission keys. Apply the migration before restarting the API and extraction workers. Downgrade requires an empty operation history because the prior schema cannot retain this consent and scheduling audit. Published runs and source results retain their existing tables and identities.

Configure the same profile settings on the API and workers. A recovery task on the existing extraction queue advances operations. Run the extraction worker and scheduler plus the source-enrichment worker with a configured OCR identity. Only the execution worker needs the OpenAI credential for this workflow. The five `EXTRACTION_OPERATION_*` limits bound documents, pages, provider admissions, possible OCR attempts, and concurrently admitted documents. The admission ceiling counts worst-case attempts under the selected profile budgets. It does not estimate a dollar amount.

## State and recovery

- **Queued** operations wait for the scheduler. A document can reuse exact prepared and layout results, or run the existing two-stage layout profile for missing pages. A prepared-only result can be pinned while its layout is built.
- **Running** operations use the existing child run leases and durable delivery records. The scheduler checks revision membership and the reviewed source and profiles before admitting a new child. Both chosen remote profiles are admitted together for a document after every selected page has a valid pair of source results.
- **Completed**, **Partial**, **Blocked**, and **Failed** reflect child results. A failed local step blocks only its dependent work. Successful child results remain available.
- **Cancel operation** stops future admissions. Previously admitted runs can continue because they may be shared. Their original status and evidence remain visible.
- **Retry** appends eligible unsuccessful attempts to the existing run. Requests carry the attempt count the engineer reviewed. For newly created operation-owned OpenAI runs, an interrupted or ambiguous transport outcome after provider start requires explicit retry acknowledgement. Existing standalone run behavior is preserved. Re-extraction is a new reviewed request with separate consent.

The server revalidates a preview hash on first admission and binds a submission key to its request. Concurrent identical active intents share one operation. A removed document prevents further admissions and its child data is withheld from operation reads. Workers retain the reviewed processing version and check exact stored identities. They verify source bytes through the existing fenced execution path.

## M3 — Single-document wizard

The Documents inspector and the document viewer open the shared wizard. Source validates independent page ranges and shows the pinned processing version. Enrichment distinguishes full reuse, preparation-only reuse, and pages that need local work. Extraction defaults to Engineering and Tables. The collapsed advanced settings can narrow the request to one family. One final consent authorizes the reviewed plan, with a separate action for re-extraction. The approved Run history Re-extract action opens the same wizard with the run's pages prefilled when the processing version still matches.

The implementation centers on [StartExtractionWizard](../apps/web/src/components/start-extraction-wizard.tsx), the [operation planner](../packages/extraction/src/powerforge_extraction/operation_plan.py), and the [revision-scoped API](../services/api/src/powerforge_api/routers/extraction_operations.py). Before remote admission, the scheduler verifies all selected pages' exact image, preparation, and layout bytes outside its write transaction. It then rechecks those binding identities and membership under the admission lock. A missing pinned artifact blocks both profiles for that document.

## M4 — Bulk execution and monitoring

Selected rows, filtered eligible rows, all eligible rows, and confirmed-type scopes feed the same wizard. The operation snapshots the exact reviewed sources and retains independent child statuses. The approved View operation links open the saved record from the confirmation toast and the AI Extraction inspector section. The inspector provides step details, scoped retry, stop-scheduling cancellation, and links to exact evidence runs.

The [operation reconciler](../packages/extraction/src/powerforge_extraction/operations.py) advances the database-backed state with the existing Celery recovery task. The [operation panel](../apps/web/src/components/extraction-operation-panel.tsx) polls active records. The worker uses exact verified result references for each document, even when a different document in the operation fails.

## Verification and review status

- **Backend and transport** — 190 tests passed against disposable PostgreSQL, Redis and MinIO, including real Celery and beat with stub OpenAI and OCR adapters. Covered concurrent admission, replay, preview with OpenAI disabled, stop-scheduling cancellation, removed and foreign sources, exact-object loss and recovery, ambiguous provider outcomes, mixed-ready and forced-OCR sources, and explicit re-extraction.
- **Database** — Applied `0016 → 0017`. An empty history supported downgrade to `0016` and re-upgrade. The populated history downgrade was rejected as designed.
- **Frozen identities and evaluations** — 166 tests passed for the existing resource identities and engineering and table evaluation suites. The existing Linux PNG reproduction exception remains documented in the [Phase 6E handoff](PHASE6E_HANDOFF.md).
- **Frontend** — 352 tests passed. TypeScript, ESLint, the Next.js production build, Ruff, Compose config validation, and whitespace checks passed.
- **Visual QA** — Captured 21 actual React views with Chrome. Source, Enrichment, Comprehensive, Targeted, and operation detail were exercised at 1440, 1024, 768 and 390 px. The 1440 px Re-extract capture confirms Run history prefills the reviewed pages. Captures are under `apps/web/.visual-artifacts/phase6f-m3-m4/baseline/`. Provider availability, admission limits, reviewed page details, and operation controls use production data contracts in the UI and deterministic data in the capture fixture.

Both milestones are ready for review. The integration suite validates execution and recovery with stubs. Live OCR and OpenAI accuracy require separate evaluation.

## Manual QA

Open a processed document in Documents and choose **Start extraction**. Review pages and an optional OCR override. In Extraction, exercise Comprehensive and Targeted modes before confirming. Repeat from filtered or confirmed-type selection and inspect the skipped reasons. Follow **View operation** from the toast, reopen its URL, and check independent local and remote child statuses. Retry a blocked source or stop future scheduling. Open a compatible terminal run in **Run history** and choose **Re-extract** to review its pages before authorizing new work.
