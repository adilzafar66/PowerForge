# PowerForge — Extraction Debugger Full Implementation

## Objective

Implement a standalone, local-only **Extraction Debugger** for PowerForge to inspect, investigate, and compare AI extraction responses.

The debugger is an internal developer/operator tool, not part of the normal PowerForge engineering workflow.

Its primary purpose is to make AI extraction failures and unexpected results easy to investigate without manually querying PostgreSQL, inspecting MinIO objects, or exporting JSON files from the command line.

Implement the complete working application, including its backend, frontend, security controls, tests, and documentation.

Work from the current `codex/phase-6r-ai-first-redesign` branch. Inspect the latest repository state before making changes.

## 1. Existing architecture and integration

PowerForge currently uses:

- Next.js/React/TypeScript for its primary web application.
- FastAPI and Python for backend services.
- PostgreSQL for extraction runs, stage results, candidates, evidence, telemetry, and audit metadata.
- MinIO/S3-compatible storage for source files and private extraction-response audits.
- A two-stage AI extraction pipeline: equipment recognition followed by attribute extraction.

Phase 6R introduced recoverable Stage 2 assertion validation and private response auditing.

Relevant existing implementations include:

- `packages/extraction/src/powerforge_extraction/attribute_admission.py`
- `packages/extraction/src/powerforge_extraction/response_audit.py`
- `packages/extraction/src/powerforge_extraction/stage_contracts.py`
- `packages/extraction/src/powerforge_extraction/stage_execution.py`
- `services/extraction-worker/src/extraction_worker/read_response_audit.py`
- `services/api/src/powerforge_api/services/extraction_service.py`
- `database/migrations/6r_0014e_response_audit.py`
- `docs/EXTRACTION.md`

Use these as the authoritative contracts.

The existing audit record contains the Stage 2 attempt identity, run and page associations, response checksum, size, expiry, assertion counts, rejected assertion positions, and sanitized diagnostics.

Original Stage 2 response bytes are retained in a private audit bucket, normally for 30 days.

Validated Stage 2 results are stored separately in `extraction_stage_results`, with candidates and evidence in their existing tables.

**Do not introduce another extraction pipeline, another response-retention mechanism, or another independent implementation of audit integrity checks.**

Reuse or appropriately refactor the existing audit retrieval code.

## 2. Application architecture

Create a new internal application within the PowerForge monorepo.

Suggested location:

`tools/extraction-debugger/`

The debugger should operate independently from the main PowerForge frontend.

### Runtime requirements

- Default address: `http://127.0.0.1:3100`.
- Start explicitly through a documented local development command.
- Do not start automatically with the ordinary PowerForge Docker Compose stack.
- Do not expose the debugger on `0.0.0.0`, a public interface, or an external domain.
- Do not route raw responses through the normal PowerForge API.
- The debugger must be usable without modifying or rebuilding the main web application.

Prefer a small Python/FastAPI backend with a React/TypeScript interface, consistent with existing repository conventions.

Use a single same-origin local application for browser requests. A lightweight frontend build is acceptable, but avoid unnecessary services, duplicated infrastructure, or a permanently running second API port.

The Python backend should own all database and object-storage access. The browser must never receive database credentials, storage credentials, or direct object-storage URLs.

Use existing libraries where practical. If a different lightweight implementation is materially simpler, justify it briefly and preserve the same operational and security requirements.

## 3. Security and operating boundaries

The debugger handles confidential engineering data and original model-generated responses. Its local-only status must not be treated as sufficient authorization.

### Required safeguards

1. Bind exclusively to `127.0.0.1`.
2. Require explicit opt-in configuration before starting.
3. Require operator authentication, using a locally supplied startup secret or similarly appropriate mechanism.
4. Keep session credentials out of URL query strings, browser local storage, and logs.
5. Use secure session handling suitable for a loopback-only application, including HttpOnly cookies and appropriate SameSite settings.
6. Enforce permitted Host and Origin values, CSRF protections for state-changing or sensitive operations, and a restrictive CORS policy.
7. Never expose private audit-storage credentials or privileged database credentials to the frontend.
8. Apply `Cache-Control: no-store` to sensitive API responses and exported response content.
9. Do not persist raw responses in browser storage or backend temporary files.
10. Do not log raw response bodies, engineering values, access secrets, or full assertion contents.
11. Render model-generated content strictly as untrusted data, never executable HTML.
12. Do not allow application access through the normal PowerForge API or public deployment configuration.

Use dedicated operator database credentials with only the permissions necessary to read diagnostic metadata and record authorized raw-response retrievals.

Use the existing private audit-reader credentials for object storage.

Do not fall back to the ordinary application database credentials, administrator credentials, or the audit writer credentials.

Document the required PostgreSQL grants and storage permissions.

The debugger must be read-only with respect to engineering and extraction data. The only permitted database writes are the existing append-only audit-access journal entries required when raw responses are retrieved.

Do not implement extraction, retry, cancellation, deletion, database modification, or audit-record editing actions.

## 4. Primary user workflow

The application should support this workflow:

1. Start the debugger locally.
2. Authenticate as an authorized operator.
3. Find an extraction run or enter a Stage 2 attempt ID.
4. Open the attempt details.
5. Inspect the execution metadata and validation summary.
6. View the exact original OpenAI output when still retained.
7. Inspect individual assertions and their validation outcomes.
8. Compare original assertions against the validated and published results.
9. Examine quarantined assertions and their errors.
10. Optionally export the exact original response.

The entire workflow should be achievable through the UI without requiring manual SQL queries or shell commands.

## 5. Run and attempt discovery

Implement a searchable, paginated list of Stage 2 attempts for which audit metadata exists.

Display useful information such as:

- Run ID and full attempt ID.
- Document/page association where available.
- Attempt number and execution timestamp.
- Stage and execution status.
- Provider/model.
- Response-validation outcome.
- Received, accepted, and quarantined assertion counts.
- Response byte size.
- Raw-output retention status and expiry.
- Provider latency and token usage when available.
- Estimated cost only when recorded by the existing telemetry.

Support locating attempts using an exact attempt UUID or run UUID.

Include practical filtering by validation outcome, execution status, and retention availability.

Use bounded database queries and cursor or equivalent reliable pagination. Avoid loading every extraction run or response into memory.

Historical attempts without Stage 2 audit records should not be incorrectly presented as having zero assertions or an empty original response.

Do not invent metadata unavailable in the current database.

## 6. Attempt overview

Selecting an attempt opens a detailed inspector.

### Summary

Display:

- Run and attempt identity.
- Page/document context.
- Execution result.
- Provider/model and available timing information.
- Received assertion count.
- Schema-valid assertion count.
- Quarantined assertion count.
- Published candidate count when available.
- Response hash, size, and retention expiry.

Differentiate the following states:

- Fully validated response.
- Partially validated response.
- Fatal response-envelope failure.
- All assertions quarantined.
- Valid empty response.
- Audit metadata available but raw response expired.
- Raw audit object unexpectedly missing.
- Raw audit integrity verification failed.
- Historical attempt without raw-output auditing.

These states must not be collapsed into a generic success/error indicator.

Counts represent **schema admission**, not engineering correctness. An accepted assertion may still become `UNMAPPED` during publication.

## 7. Original OpenAI response viewer

Provide a dedicated JSON inspector for the original Stage 2 response.

The source must be the exact response bytes already retained through the Phase 6R audit mechanism.

Do not reconstruct the original response from the validated stage payload.

### Viewer capabilities

- Formatted JSON tree.
- Expandable and collapsible objects and arrays.
- Raw-text mode preserving original text.
- Copy individual values or JSON paths.
- Search within the loaded response.
- Navigate between individual assertions.
- Preserve and display original array indices.
- Highlight schema-invalid assertions.
- Show `attributes` and `raw_unmapped` separately.
- Support extracted and inferred assertions without conflating their different schemas.

Handle both valid JSON and malformed JSON:

For parseable JSON, display the structured inspector.

For an invalid JSON response that passed transport completion but failed local JSON validation, display its original bounded text safely, along with the available fatal diagnostics. Do not pretend it contains validated assertions.

Use explicit user interaction to reveal raw output; do not automatically retrieve it when loading a run list.

### Integrity and retention

Before exposing original bytes:

1. Verify the operator is authorized.
2. Verify the audit record exists and has not expired.
3. Retrieve the object through the restricted backend.
4. Verify the stored byte length and SHA-256 digest.
5. Record the authorized retrieval through the existing audit-access journal.
6. Return the verified bytes to the browser.

Reuse the existing operator audit-read functionality rather than implementing a separate checksum or expiry policy.

The original content must not be returned when an integrity check fails.

Do not expose S3 object keys or direct signed URLs through ordinary browser responses.

## 8. Assertion inspector

Implement a dedicated assertion-level view.

This should be the central debugging feature.

For each assertion, show the original source fields where available:

- Original collection and index.
- `local_ref`.
- `equipment_ref`.
- Origin (`EXTRACTED` or `INFERRED`).
- Attribute key or original source label.
- Raw or proposed value.
- Raw and proposed units.
- Value form and qualifiers.
- Evidence citations.
- Inference explanation and source expression when applicable.

Show an easily distinguishable validation state:

**Accepted:** Passed local schema admission.

**Quarantined:** Failed assertion-level schema admission. Show the original collection/index and available sanitized errors.

**Fatal response:** The overall response was rejected before assertion-level publication.

For accepted assertions, also show their downstream publication outcome when available:

- Mapped.
- Unmapped.
- Invalid engineering value.
- Evidence unresolved.
- Relevant mapping reason codes.
- Normalized value and canonical unit where published.

Do not treat successful schema validation as proof that the AI identified the correct equipment or engineering attribute.

### Filters

Support filtering by:

- All assertions.
- Accepted.
- Quarantined.
- Mapped.
- Unmapped.
- Extracted.
- Inferred.
- Raw unmapped.

Search by local reference, attribute key, label, or value when original data is available.

The interface should support navigating dozens or hundreds of assertions without becoming cumbersome.

## 9. Original versus validated comparison

Implement a comparison view between:

**Original output:** The exact OpenAI-generated assertion arrays.

**Validated output:** The accepted Stage 2 payload stored in `extraction_stage_results`.

Where publication exists, include the corresponding candidate status and normalized value.

Present both representations side by side or through a similarly clear comparison interface.

Identify assertions that:

- Were accepted.
- Were quarantined.
- Were accepted but subsequently left unmapped.
- Have published normalized values.

Preserve original collection/index positions when correlating results.

Accepted assertions may have shifted positions because quarantined elements were excluded before publication. Therefore, never assume the validated array index equals the original response index.

Use the existing assertion references and audit positions to establish relationships deterministically.

Do not perform speculative fuzzy matching. If a reliable relationship cannot be established, label it as unavailable.

This feature is a comparison of recorded representations, not a new engineering interpretation engine.

Do not modify source assertions, perform new AI inference, or recompute normalized values.

## 10. Rejection diagnostics

Provide a clear, focused view for quarantined assertions.

Display:

- Original collection.
- Original index.
- Available local-reference identity.
- Validation category.
- Error type.
- Structured field path.
- Whether the rejection was local or response-fatal.

For example:

`attributes[24].raw_value — string_too_short`

When the raw response is available and successfully verified, allow the operator to inspect the complete original rejected assertion.

When the raw response has expired, display only the sanitized diagnostics retained in PostgreSQL.

Do not expose hashed local-reference values as though they were recoverable original references.

Preserve the original admission decisions. The debugger must not silently rerun admission or reinterpret historical results using the current schema version.

## 11. Export functionality

Provide an explicit operator-only action to export the exact retained Stage 2 response.

Requirements:

- Export the verified original bytes, not reserialized JSON.
- Preserve the original encoding.
- Use a safe, deterministic filename.
- Require an explicit user action.
- Record each export as an authorized audit retrieval.
- Disable export after expiry or integrity failure.
- Apply no-store headers and appropriate attachment handling.
- Do not write intermediate raw-response files on the server.
- Warn users that exported files contain confidential source-derived data and remain subject to the retention policy.

Retain the existing command-line export tool as an independent operator workflow.

## 12. User interface and visual design

Build a polished, practical developer interface.

Use the existing PowerForge design conventions where helpful, without coupling the debugger to the main application.

### Recommended layout

A three-area interface:

**Left — Run/attempt explorer**

Searchable list of extraction attempts, statuses, and filters.

**Center — Assertion explorer**

Validation summary, searchable assertions, original positions, and status indicators.

**Right — Details inspector**

Original assertion JSON, validation diagnostics, published values, or response comparison.

Allow the detail pane to expand for larger JSON objects.

Include:

- A compact application header identifying the environment as local diagnostics.
- Clear distinction between completed, partially validated, rejected, and expired results.
- Monospace presentation for JSON, IDs, numerical values, and error paths.
- Copy controls for useful identifiers and values.
- Expandable technical metadata.
- Keyboard-accessible controls and visible focus states.
- Appropriate loading, empty, error, and unavailable states.
- Responsive layout for smaller desktop windows.
- Light/dark appearance consistent with PowerForge conventions where practical.

Keep the interface technical and information-dense without excessive decoration.

Do not implement unrelated administrative features.

## 13. Backend API and data handling

Implement a small typed, operator-authenticated backend API to support:

- Paginated audit-attempt discovery.
- Attempt details and validation metadata.
- Associated accepted Stage 2 result and publication information.
- Explicit retrieval of original raw output.
- Original-response export.

All database queries must be parameterized and bounded.

Use the existing SQLAlchemy models and source-of-truth records.

Avoid duplicating business logic from `ExtractionReadService`, `response_audit.py`, and the existing operator audit reader.

If shared helpers need to be moved into an appropriate package to avoid awkward service dependencies, keep the refactoring narrow and preserve existing CLI behavior.

Do not create an alternative database schema for extracted assertions.

Do not add schema migrations unless an actual missing requirement makes them necessary; explain any such requirement before modifying persistence contracts.

Handle invalid identifiers, missing records, expired audits, missing objects, integrity failures, insufficient permissions, database outages, and storage outages safely.

Avoid exposing internal stack traces, SQL, storage credentials, or source contents in error responses.

## 14. Non-goals and scope restrictions

The debugger must not:

- Call OpenAI or any other model provider.
- Trigger or retry an extraction.
- Modify recognized equipment or attributes.
- Change canonical engineering-model data.
- Approve, reject, or edit engineering candidates.
- Modify stored audit records.
- Extend retention periods.
- Recover already-expired or never-retained raw responses.
- Expose original responses through the main PowerForge API.
- Create public audit download links.
- Introduce a new project authentication system.
- Implement Stage 1 raw-response retention.
- Recreate engineering validation or unit conversion in the frontend.

Stage 1 results may be shown as supporting metadata from existing validated records, but they must not be represented as original raw provider responses.

Keep the initial implementation focused on debugging the current Phase 6R Stage 2 extraction workflow.

## 15. Tests and verification

Implement meaningful tests at the appropriate levels.

### Backend tests

Verify:

- Authorization and loopback restrictions.
- Host, Origin, session and CSRF handling.
- Restricted metadata retrieval.
- Pagination and filtering.
- Attempt identity and run/page association.
- Successful original-response retrieval.
- Byte-length and SHA-256 verification.
- Retrieval journal insertion.
- Missing, expired and corrupted audit objects.
- No raw-response leakage in logs or error responses.
- No unauthorized database mutations.
- Failure behavior when credentials or audit services are unavailable.

### Assertion and comparison tests

Cover:

- Fully valid response.
- Partially valid response.
- Empty `raw_value`.
- Whitespace-only `raw_value`.
- Malformed inferred assertion.
- Malformed `local_ref`.
- Fatal duplicate references.
- Wrong upstream identity.
- Valid empty response.
- All assertions quarantined.
- Multiple quarantined assertions in both arrays.
- Accepted assertions whose indices shifted during quarantine.
- Accepted but unmapped assertions.
- Missing validated stage result after a failed attempt.
- Expired raw output with permanently readable metadata.

Reproduce the Siemens failure pattern synthetically: assertion index `24` contains an empty source value between otherwise valid assertions.

Ensure the debugger displays the original error position and accurately correlates the accepted published assertions.

### Frontend tests

Verify filtering, navigation, search, expandable JSON, diagnostics, raw-response reveal, export permissions, and expired/missing states.

Test representative narrow and wide desktop layouts.

Ensure arbitrary source strings, HTML, unusual Unicode, and long JSON values cannot cause script execution or break the interface.

### Integration tests

Use a disposable PostgreSQL database and test object storage.

Test the existing immutable audit and publication contracts without altering the working project database.

Include an optional end-to-end integration test against a properly configured local MinIO audit bucket with scoped operator credentials.

Run relevant lint, type checks, builds, backend tests and frontend tests. Report exact results and any tests that could not run.

Do not make live AI calls.

## 16. Configuration and documentation

Document the complete local workflow in a dedicated debugger README.

Include:

1. Prerequisites.
2. Installation.
3. Local startup command.
4. Required environment variables.
5. Operator database and object-storage permissions.
6. How to locate a Stage 2 attempt ID.
7. How to inspect an original response.
8. How to investigate quarantined assertions.
9. How to compare original and published results.
10. How to export an original response.
11. Retention and expiration behavior.
12. Troubleshooting unavailable or invalid audit artifacts.
13. Security boundaries and limitations.
14. How to run tests.

Provide a safe environment-variable example without secrets.

The debugger should remain an opt-in local tool and must not change the ordinary PowerForge startup workflow.

If relevant, add a concise link to the debugger documentation from `docs/EXTRACTION.md`.

## 17. Completion requirements

This is an implementation request, not a request to draft another plan.

Inspect existing contracts, resolve minor design decisions within the constraints above, and implement the complete working tool.

Keep the implementation appropriately modular but avoid overengineering.

Before considering the task complete, verify that:

- The application starts at `127.0.0.1:3100`.
- An authorized operator can browse Stage 2 audit attempts.
- An operator can inspect a verified, unexpired original response.
- A quarantined assertion can be located by its original array index.
- Original and accepted assertions can be compared correctly.
- Expired responses remain represented by their permanent metadata.
- Unauthorized access is rejected.
- Raw-response retrieval is audited.
- No existing PowerForge extraction behavior has changed.
- Relevant tests and build checks pass.

Do not run live extractions, reset the working database, or change unrelated PowerForge functionality.

### Final handoff

Provide:

- A concise architecture summary.
- The main files and modules created or modified.
- The exact startup and configuration commands.
- Security and operator-access requirements.
- Test results.
- Any remaining limitations.

The finished result should be a complete, usable local Extraction Debugger, not a prototype or a collection of disconnected UI components.