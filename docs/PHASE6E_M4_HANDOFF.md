# Phase 6E M4 handoff

Implemented for review on 2026-11-07. M4 connects committed source enrichment to the existing extraction lifecycle and publishes candidates, tables and evidence. Phase 6E M5 covers representative evaluation and final release validation.

## Run enhanced extraction

Use the document scope `/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}` for these paths.

1. Start `POST /source-enrichment/runs` with `profile_key: "source-layout-v1"`, the base `processing_run_id` and explicit page numbers. Select `force_ocr_pages` for hybrid PDF pages whose embedded scan needs OCR. See the preparation policy and deployment instructions in the [M2 handoff](PHASE6E_M2_HANDOFF.md).
2. Wait for the selected page results in `GET /source-enrichment/runs/{run_id}`. For each selected page, use the spatial result ID and its `prepared_result_id`. A reused preparation result keeps its original producer.
3. Start `POST /extraction/runs` using those exact pairs. The prose profile is `engineering-openai-enriched-v1`. The table-only profile is `tables-openai-enriched-v1`. Use separate extraction runs to collect both sets of results. Both can reuse the same enrichment.
4. Use `GET /extraction/runs/{run_id}/sources` to see the pinned page pairs, manifest hashes, original producer run IDs and text coverage. Use the ordinary run, candidate, table and evidence endpoints to read the results.

Example extraction request for page 1, using placeholder IDs.

```json
{
  "profile_key": "tables-openai-enriched-v1",
  "pages": [1],
  "enrichment_bindings": [
    {
      "prepared_result_id": "f6bff73e-0645-4111-9858-c7e5bf5d70d1",
      "spatial_result_id": "35f49d86-99dc-4d47-ac9c-b264a2081efe"
    }
  ]
}
```

`GET /extraction/profiles` advertises the production profiles with `requires_enrichment`. They use the existing explicit external-extraction enablement and model configuration. Missing or incompatible pairs return HTTP 409 before model admission. Selected pages must come from one base processing run. `ensure` uses the exact profile, pages and binding identities. Retry and recovery preserve those identities even when newer source enrichment exists.

The document summary selects the latest completed or partially completed extraction across profiles. A newer table-only run can therefore become the summary after a prose run. Both sets of results remain accessible by run ID and through extraction history. Enrichment history has its own endpoints.

## Evidence and limits

Enhanced requests give the model bounded untrusted text and source aliases alongside the page image. Code establishes positions and source-local associations from the committed layout and readings. The publisher independently verifies the cited source bytes and geometry. The v2 locator keeps reading basis, geometry basis and structure basis separate. For positioned evidence, the evidence endpoint can sign the exact recognized-text artifact and the original analysis image separately. It exposes precise token spans and a supported region when available. Visual-only evidence can cite the page with no text offsets or supported region.

OCR-backed evidence retains the recognized characters and raw, uncalibrated engine confidence. A structurally supported table can still contain a misread value. `printed_text_independently_verified` remains false even when the registry maps the recognized value. Claims with unsupported qualifiers, ambiguous ownership or conflicting readings may remain unresolved or unmapped. Prose association requires an admitted source block. Prose on a page with a detected table needs positioned evidence to establish that it lies outside the table. Enhanced attribute-row association currently supports a simple unmerged two-column layout with recognized field labels.

The positioned 6D schedule projected to 1,803 bytes from a 6,189-byte layout and 5,045 bytes of source geometry. An authored 512-cell native grid produced a 629,795-byte layout and 303,458 bytes of geometry. It exceeded the provider projection bound and was rejected without truncation. Projection has an independent 128 KiB ceiling plus the configured text limit. This behavior limits extraction coverage on dense schedules.

## Migration and compatibility

Apply `0016_enriched_extraction` before deploying the updated API and extraction workers. The migration adds exact source bindings and v2 evidence ownership and publication guards. Downgrade is supported while the database contains only prior-format history. Once enhanced history exists, downgrade refuses to remove its source references.

The accepted M3 runtime files from `e642a78` are packaged as identity data. The layout execution digest remains `fda9a3cc8cd7a98743727e6bd7e38e58fd896006d0bd61c7583e6b262a8b3844`. The earlier publication source used by the M1 compatibility check is preserved the same way. The old execution profiles and v1 table/evidence readers still use their original contracts. Built wheels reproduced the v1–v4 identities, both frozen scripted reports, the accepted M1–M3 resources and all four enhanced production/test profile identities.

## Verification

- The final M4, API compatibility and migration gate passed 49 tests in 38.29 seconds on Linux ARM64. The disposable environment used PostgreSQL 16.15, Redis 7.4.11, MinIO RELEASE.2025-09-07T16-13-09Z, Python 3.12.16, PyMuPDF 1.28.2 and Tesseract 5.3.0 with Leptonica 1.82.0.
- The broader 709-case compatibility run passed 707 cases. The two failures were legacy assertions that counted the old API endpoints and profiles. Both were updated to check the additions explicitly and passed in the final gate. A separate host run passed 121 cases, including both legacy evaluation suites and their frozen resources.
- Integration tests processed actual native PDFs and scanned images. They exercised the production Responses adapter with mocked transport, exact source pairing, retries, cancellation, partial results and inherited revision access. A worker was killed during source loading. The replacement worker used the original OCR result, and the signed MinIO text returned `600` at the published offsets. The signed image also downloaded. The original preparation recorded one OCR invocation.
- A controlled recognition fault changed the recognized value of an independently authored 690 V scan to 600 V. The pipeline retained 600 V and mapped it to 0.6 kV with supported table relationships and printed-text verification explicitly false. This checks provenance handling when recognition is wrong. Production model accuracy and representative layout coverage remain unmeasured.
- Migration tests checked fresh head, preserved M3 results and a pending legacy v4 retry through upgrade, and verified the downgrade guard. Mutation tests rejected altered offsets, unsupported geometry and foreign cell support. Six wheels built and passed direct import and identity checks. Ruff, dependency and whitespace checks passed.
