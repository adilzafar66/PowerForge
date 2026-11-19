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
Stage 2 considers required and optional registry attributes for every eligible
equipment occurrence. Extracted attributes retain literal transcription.
Inferred attributes retain a separate value and unit proposal, explanation,
optional basis and optional context citations. They never count as matches to
cited value text. Both origins remain review candidates.
The quality correction also preserves original expressions for derived proposals
and separate presentation labels for raw source facts. Equipment identification
has its own section. Group names follow source order and group summaries count
attributes separately from identification. Likely repeated assertions remain
accessible with their original qualifiers and evidence.
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
New runs pin the per-request OpenAI timeout from `EXTRACTION_TIMEOUT_SECONDS`,
which defaults to 100 seconds.

Use a disposable database and `alembic -c database/alembic.ini upgrade head`
for development. The replacement chain is for clean installation. Follow the
reviewed cutover runbook for an authorized deployment database reset.

The `powerforge-eval-spatial` command measures local native/OCR and layout behavior.
The held-out extraction evaluation is documented separately.

- [Extraction specification](specs/phase-6r-extraction-redesign.md)
- [Publication and API contracts](specs/phase-6r-contracts-v1.md)
- [Evaluation protocol](../evals/phase6r/README.md)

## Stage 2 response audit

Before enabling live Stage 2, provision a **private, unversioned** audit bucket
with encryption at rest where supported. Use separate worker and operator
credentials. Keep the regular API and document-storage identities scoped away
from the audit bucket. The local Compose stack gives several services MinIO
administrator credentials by default. With those defaults, provision the audit
bucket on a separate S3-compatible endpoint or replace the document-storage
credentials with scoped principals first.

- Set `EXTRACTION_RESPONSE_AUDIT_BUCKET`, `EXTRACTION_RESPONSE_AUDIT_WRITE_ACCESS_KEY`,
  and `EXTRACTION_RESPONSE_AUDIT_WRITE_SECRET_KEY` on the extraction worker.
  Set `EXTRACTION_RESPONSE_AUDIT_ENDPOINT_URL` when the audit bucket uses a
  separate endpoint. The writer needs `s3:GetLifecycleConfiguration`,
  `s3:GetBucketVersioning`, and `s3:PutObject` on the audit prefix. Restrict
  object creation to the worker and operator reads to a separate principal.
- Set `EXTRACTION_RESPONSE_AUDIT_RETENTION_DAYS` consistently on the API and
  workers. It defaults to 30 and is pinned per run. Configure an enabled
  `Expiration.Days` lifecycle rule for the matching `stage2/<days>d/` prefix.
  Keep rules for older prefixes until their objects have expired. The worker
  checks the rule before admitting Stage 2. An unavailable audit store fails
  the attempt without publishing a result. The same lifecycle expires objects
  left behind by rolled-back or cancelled attempts.
- Grant the operator database role `SELECT` on `extraction_response_audits`
  and `INSERT (work_unit_id)` on `extraction_response_audit_reads`. Give the
  operator storage principal `s3:GetObject` on the audit prefix. Enable
  object-read auditing on the storage service to cover direct operator reads.
  Use individual operator identities so the retrieve journal identifies
  the actor. Keep read credentials out of application containers.

From an operator environment with the extraction worker package installed, set
`EXTRACTION_RESPONSE_AUDIT_DATABASE_URL`, `EXTRACTION_RESPONSE_AUDIT_READ_ACCESS_KEY`
and `EXTRACTION_RESPONSE_AUDIT_READ_SECRET_KEY`, together with the audit bucket
and endpoint. Export an unexpired artifact using the Stage 2 attempt ID:

```bash
python -m extraction_worker.read_response_audit <work-unit-id> <new-private-file>
```

The command verifies length and SHA-256, records the database identity and
timestamp before releasing bytes, and creates the output file with owner-only
permissions. The application enforces expiry at retrieval. Storage lifecycle
deletion follows the provider's schedule. Keep operator exports within the same
confidentiality and retention rules.

Documents shows received, schema-valid and quarantined counts. Quarantined
assertions fail local schema validation and produce no candidates. Valid
assertions can still appear as Unmapped after engineering validation. The API
exposes sanitized details, while the exact Stage 2 output text stays in the
audit bucket. Counts and digests remain in immutable history after expiry.

For local operator inspection of retained Stage 2 responses, see the
[Extraction Debugger](../tools/extraction-debugger/README.md).
