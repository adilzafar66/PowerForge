# ADR-005: Document processing and page identity (Phase 3)

## Status

Proposed (2026-10-08). Specified, not implemented. Specification: `cursor/phase3_specs.txt`. Plan: [PHASE3_PLAN.md](../docs/PHASE3_PLAN.md). Delivery: [PHASE3_PR_PLAN.md](../docs/PHASE3_PR_PLAN.md).

## Date

2026-10-08

## Context

Phase 2 stores an immutable `Document` and shares it across revisions ([ADR-004](ADR-004-document-storage-and-revision-inheritance.md)). Nothing yet turns those bytes into pages. Later evidence has to point at a stable place in the file, not at a render that will change when DPI or library versions change.

The product spec lists OCR inside Phase 3. This phase does not. Native text already embedded in a PDF is readable without OCR. Scanned pages stay without text until a later phase. Classification, layout analysis, table extraction, and the engineering model stay later as well.

`ObjectStorage.put` never overwrites a key. A retry that reused one processing row would have to delete that attempt's objects before it could write them again. A failed cleanup would wedge the retry. Failed attempts are also useful to debug, and this system already keeps history instead of overwriting it.

The document worker cannot run that work today. `ObjectStorage` and the SQLAlchemy models live in `powerforge_api`. The worker image installs only `powerforge-shared` and the worker package, and Compose does not give it S3 settings. All three workers listen on the default Celery queue, so a processing task published there can be taken by a worker that does not implement it.

## Decisions

1. **Processing belongs to `Document`, not `RevisionDocument`.** A file inherited by several revisions is processed once. Inherited revisions see the same pages and the same completed result.
2. **`DocumentPage` is the stable logical page.** It belongs to `Document`. Identity is `(document_id, page_number)` with page numbers starting at 1. It does not depend on the processing run, DPI, or rendered pixel size. A PDF page, a PNG or JPEG, and a TIFF frame each become one page.
3. **Stored page size is the upright page.** `source_width` and `source_height` are the page as displayed after rotation normalization. `rotation_degrees` is the source rotation that was applied (`0`, `90`, `180`, or `270`). PDF units are points. Image units are pixels.
4. **Future coordinates are normalized on that upright page.** Origin is top-left. `x`, `y`, `width`, and `height` are each 0.0 to 1.0. They are not rendered pixels and not the unrotated PDF media box. Bounding boxes are not implemented in this phase.
5. **The original `Document` remains the evidence.** A `PageArtifact` is a derived convenience: an analysis PNG, a thumbnail, or native PDF text. Future provenance points at `DocumentPage`, not at a particular analysis image.
6. **A `DocumentProcessingRun` is one attempt** at a processing target `(document_id, processor_version, profile_hash)`. Retry inserts a new run. It does not reset the failed run and does not delete that attempt's rows or objects. `attempt_count` is set when the run is inserted and does not change when a worker claims it.
7. **At most one live run per target.** Many `FAILED` runs are allowed. A partial unique index allows only one run in `PENDING`, `RUNNING`, or `COMPLETED` for the same target. The current run is that live run, or the latest `FAILED` run when every attempt failed.
8. **Processing is asynchronous and profile-aware.** The upload request commits the `Document` first. Page rendering does not run inside that request. The profile is an explicit, hashed configuration (`processor_version` `1`, `profile_version` `engineering-default-v1`), not whatever PyMuPDF or Pillow happens to be installed. A decodable page that would exceed the profile pixel cap is scaled down. Input that cannot be decoded, including a decompression bomb, fails the run.
9. **`ensure_document_processing` does not retry failure.** It creates the first run, and it re-enqueues an unclaimed `PENDING` run. A `RUNNING` or `COMPLETED` run is returned as-is. A `FAILED` current run is returned as-is. Only the explicit retry operation starts the next attempt. Backfill uses the same operation and does not run on API startup.
10. **A run is `COMPLETED` only when every page and every required artifact exists.** Pages and artifact URLs are exposed only for that completed run. Progress while running comes from the processing-status payload.
11. **Native PDF text is in this phase. OCR is not.** Non-empty extracted text is stored as a `NATIVE_TEXT` artifact. A page with no text, including every image page, stores `native_text_char_count = 0` and no text artifact.
12. **Derived objects use the Phase 2 storage rules.** Keys are machine-oriented and include the run id (`…/processing/{run_id}/pages/…`). `put` never overwrites. Artifacts stay private. Signed URLs use the same revision-scoped presign pattern as originals. Failed attempts' objects are left in place. There is no garbage collection in this phase, consistent with orphaned originals from Phase 2.
13. **The API and the document worker share one library** for `ObjectStorage`, the SQLAlchemy mappings the worker must load (including `Document`, so the table is mapped once), and the processing service. The worker does not import the FastAPI application. `packages/document-model` stays free of SQLAlchemy, Celery, FastAPI, boto3, Pillow, and PyMuPDF.
14. **Processing tasks use a dedicated Celery queue** that only `document-worker` consumes. The other workers stay on the default queue.
15. **Reading and retrying processing is not a revision edit.** `INCLUDED` and `REMOVED` associations may read status, and may read pages once the run is completed, including on a superseded revision. They may retry a failed run. The document list carries the current run's status so the UI does not call the status route once per row.

## Consequences

**Positive**

- Revisions that share a file share one page identity. Later evidence can cite page 17 without caring which revision displayed it.
- Re-rendering at a different DPI creates a new profile and new artifacts. It does not rename the page.
- Retry cannot fail because an old object is in the way, and a failed attempt remains inspectable in the database and in storage.
- A lost queue message can be repaired by `ensure` or by backfill without creating a second active run.

**Negative / follow-up**

- Failed attempts leave derived objects until a later garbage collector exists.
- The API loses direct ownership of the storage port and the ORM models; both move to the shared library. Existing imports have to follow them.
- The document-worker image and its Compose environment have to gain the database driver, S3 settings, PyMuPDF, and Pillow. They do not have them today.
- OCR, classification, layout, tables, and evidence rows are still unbuilt after this phase. Scanned drawings will show pages and no text.

## Not decided here

Password entry for encrypted PDFs, artifact garbage collection, a history UI for old attempts, and any change to Phase 2 upload validation. Header-only PDF checks and structural image checks stay at upload time. Decode failures surface as a failed processing run.
