# AI engineering extraction

Users start extraction in Documents. The wizard selects processed pages, reviews
source preparation and provider limits, and collects explicit consent. The server
revalidates the expiring review before accepting the operation. Each document has
one extraction run and may share exact, verified source-preparation results.

## Execution

1. Prepare the page locally from the immutable original and analysis image. Keep
   native readings, request OCR when needed or forced, and derive bounded layout
   observations. Unresolved layout retains page context and source readings.
2. Recognize source-local equipment on each page against the registry catalog.
3. Extract attributes from the same pinned page using the exact successful
   recognition result. A page with no eligible equipment records a skip.
4. Localize individual citations against the pinned page. Validate applicable
   registry proposals and normalize supported values. Commit stage results,
   candidates and evidence under the worker's lease in one transaction.

The source-processing and provider queues support retry and cancellation through
the original operation. A provider call whose outcome is unknown requires explicit
acknowledgement before retry. Completed recognition stays available when
attribute extraction fails. Publication and retry keep their pinned profile,
source and prerequisite identities.

## Review

The evidence browser opens one run at a time. Grouping uses equipment observation
IDs and an unassigned bucket, with cursor pagination for groups and members.
The run history shows both AI stages, page attempts, pinned source bindings,
diagnostics, and measured usage. Cost requires measured usage and versioned pricing.

The candidate retains raw assertions, proposed keys and enum values, normalized
values where supported, and independent mapping, association and evidence states.
“Matches cited text” describes the cited fragment. Correct row, equipment ownership
and engineering interpretation require independent review.

Exact highlights come from pinned source coordinates. Model-reported regions use
an approximate style. Unresolved citations can show the pinned page. Artifact URLs
are short-lived and scoped to the included revision document.

## Local setup and evaluation

Enable `ENRICHMENT_ENABLED` for local preparation. For development set
`EXTRACTION_USE_FAKE_PROVIDER=true` on the API, extraction worker and scheduler.
Live admission additionally requires `EXTRACTION_EXTERNAL_ENABLED=true`, the
configured model, worker credentials, and consent for the selected sources.

Use a disposable database and `alembic -c database/alembic.ini upgrade head`
for development. The replacement chain is for clean installation. Follow the
reviewed cutover runbook for an authorized deployment database reset.

The `powerforge-eval-spatial` command measures local native/OCR and layout behavior.
The held-out extraction evaluation is documented separately.

- [Extraction specification](specs/phase-6r-extraction-redesign.md)
- [Publication and API contracts](specs/phase-6r-contracts-v1.md)
- [Evaluation protocol](../evals/phase6r/README.md)
