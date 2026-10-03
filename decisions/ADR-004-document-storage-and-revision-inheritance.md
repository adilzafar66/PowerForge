# ADR-004: Document storage and revision inheritance (Phase 2)

## Status

Proposed. Becomes Accepted when Phase 2 implementation is merged. Specification: `cursor/phase2_specs.txt` (version 2).

## Date

2026-10-01

## Context

Phase 1 delivered `Project` and `ProjectRevision` ([ADR-003](ADR-003-project-revision-model.md)). Phase 2 attaches engineering documents to revisions.

Engineering work is incremental: revision N+1 is usually revision N plus a few changed documents. Three obvious designs were considered and rejected:

- **A document row per revision** (`ProjectRevision` → `Document`). Creating a revision would copy every row, and probably every file, and the same file would have different identities in different revisions. Provenance could not say "this is the same artifact".
- **Physical folders** (`rev2/transformers/T1/…`). A switchgear drawing belongs to several conceptual categories; folder paths encode one. Renaming equipment or reclassifying a file would require moving objects.
- **Content-addressed global deduplication** (SHA-256 unique). Identical bytes can legitimately be separate uploads with different intent, and silently merging them hides what the engineer actually received.

Phase 2 must also leave later phases (page processing, evidence, extraction, the engineering model) a stable, immutable thing to point at.

## Decisions

### Document model

1. **`Document` is an immutable uploaded artifact.** It records project, original filename, storage key, MIME type, extension, size, SHA-256, upload time, and uploader. None of these change after upload. There is no API to replace a stored file; a different file is a new `Document`.
2. **`RevisionDocument` associates a `Document` with a `ProjectRevision`.** It carries everything that is interpretation rather than identity: document type, document number, description, notes, origin, inclusion status, and add/remove audit fields.
3. **A `Document` may be referenced by multiple revisions.** `(revision_id, document_id)` is unique, so a document appears at most once per revision.
4. **Revision-scoped metadata lives on `RevisionDocument`, not `Document`.** Revision 1 stays historically frozen even if Revision 2 classifies the same file differently.

### Revision lineage and inheritance

5. **New revisions record lineage** in `based_on_revision_id`. The base may be any revision of the same project, including a superseded one. Lineage is **immutable after creation**.
6. **New revisions may inherit document associations.** Inheritance copies the base's `INCLUDED` associations only. `REMOVED` associations are not carried forward.
7. **Physical files are never copied during inheritance.** Inherited rows point at the same `Document`. Only association rows are created.
8. **Revision-scoped metadata is copied on inheritance**; IDs and add/remove audit fields are not.
9. **Inheritance is a snapshot at creation time.** Later changes to the base's package are not propagated, and the metadata of the two revisions diverges independently. This is copy-on-write revisioning.
10. **Explicit "no base" and "no carry-forward" are both expressible.** Omitting `based_on_revision_id` defaults to the current ACTIVE revision; an explicit `null` means no base; `carry_forward_documents=false` records the base but inherits nothing.
11. **Revision creation and inheritance are one transaction**, and run before activation when `activate=true`, so the base's package is read before the base is superseded.

### Mutability

12. **Superseded revisions' document packages are frozen.** Upload, reuse, metadata edit, remove, and restore are rejected. Reading and downloading remain allowed in every status. DRAFT and ACTIVE revisions are editable, as are documents in ACTIVE and PAUSED projects; ARCHIVED and CANCELLED projects reject document changes. This reuses the Phase 1 project lifecycle check.
13. **"Frozen" covers the document package only.** Phase 1 still allows editing a superseded revision's identifier and description; that is unchanged and out of scope.
14. **Removing a document removes it from a revision, not from evidence storage.** The `Document` row and object are kept. Remove and restore are idempotent.
15. **Mutations re-check mutability after taking row locks**, so a concurrent activation, archive, or cancel cannot race an upload. A document mutation locks the project row `FOR SHARE` and then the target revision row `FOR UPDATE`; activation, archive, and cancel lock the project row `FOR UPDATE`, so they wait for in-flight mutations and later mutations see the new state. Lock order is always project row, then revision rows, and a mutation never upgrades its project lock.

### Storage

16. **Physical storage is flat and stable.** Keys are `projects/{project_uuid}/documents/{document_uuid}/original{ext}`. No filenames, revision names, equipment tags, or classifications appear in keys, so objects never move.
17. **Storage is accessed through an `ObjectStorage` abstraction** implemented with boto3 against the S3 API (MinIO locally). boto3 matches the existing `S3_*` settings and supports AWS S3 and other S3-compatible services without a rewrite. `put` never overwrites an existing key.
18. **Downloads use short-lived presigned URLs issued only through revision-scoped routes** (`…/revisions/{rid}/documents/{rdid}/download-url`). There is no unscoped `/api/documents/{id}` route, because a bare document ID carries no project context to authorize against. URLs are signed against a separate browser-reachable endpoint (`S3_PUBLIC_ENDPOINT_URL`) because the API's internal hostname is not reachable from a browser. Objects are never public and credentials never reach the browser.
19. **Duplicate content is detected, not rejected or merged.** SHA-256 is indexed per project but not unique. A duplicate upload succeeds, creates a new `Document`, and returns `duplicate_detected` with the matching IDs.
20. **Files are validated by extension and content**, and the two must agree. The server derives the MIME type from content; the browser's value is ignored. Size is enforced while streaming and files are never fully loaded into memory.

### Database integrity

21. **Same-project integrity is enforced by the database, not just the service.** `project_revisions` gets `UNIQUE (project_id, id)`; `based_on_revision_id`, `RevisionDocument.revision_id`, `.document_id`, and `.inherited_from_revision_id` use composite foreign keys including `project_id`. `RevisionDocument.project_id` is therefore **intentionally denormalized**, set by the service and never accepted from clients. A self-referencing base is blocked by a CHECK constraint. No cascading deletes exist in Phase 2.
22. **Integrity errors are mapped by constraint name.** This replaces the Phase 1 behavior that reported any `IntegrityError` as a duplicate revision identifier, which would become wrong once foreign keys and checks exist.

### Organization and scope

23. **Organization is metadata-driven.** Phase 2 offers type, origin, status, and search filters. There are no folders and no folder table. Equipment-based views wait for equipment entities.
24. **AI classification is deferred.** Document type is chosen by the engineer. `DocumentClassification` in `packages/document-model` is reused and extended with `OTHER`.
25. **Document packages/submissions are a possible future feature** (for example "Client IFC Package — 2026-09-15") representing provenance, not folders. They are not implemented in Phase 2, and nothing here prevents adding them later.
26. **An existing document can be reused in another revision of the same project** without re-uploading, through a reuse operation that creates an `INHERITED` association. This keeps one `Document` identity instead of creating duplicates when a revision started empty.

## Consequences

**Positive**

- Revision N+1 costs rows, not bytes, and the same artifact has one identity across revisions. Later phases can attach pages and evidence to `Document` and still know which revisions used it.
- Historical packages cannot be altered silently once a revision is superseded.
- Cross-project association is impossible at the database level, not merely unlikely at the service level.
- Object storage and the domain are decoupled; switching providers touches one adapter.
- Storage keys never need migration when metadata changes.

**Negative / follow-up**

- Uploaded-then-removed documents and objects orphaned by a crash between upload and commit remain in storage. There is no garbage collection in Phase 2.
- `RevisionDocument.project_id` is redundant by design and must stay consistent; the composite foreign keys enforce this.
- An ACTIVE revision's package remains editable, so evidence attached to it can change over time. Later phases must record the `Document` / `RevisionDocument` identity they used (see [PROVENANCE.md](../docs/PROVENANCE.md)).
- PDF validation is header-only (polyglot files are not detected) and images are validated structurally rather than fully decoded. Acceptable because files are never rendered or executed server-side in Phase 2; full decoding belongs to Phase 3.
- Document lists are not paginated.
- `uploaded_by`, `added_by`, and `removed_by` stay null until authentication exists, consistent with ADR-003.
- Lineage means activating a revision based on an older revision supersedes the current ACTIVE revision regardless of ancestry. Phase 1 activation rules are unchanged.

## References

- `cursor/phase2_specs.txt`
- [ADR-003](ADR-003-project-revision-model.md)
- [ADR-001](ADR-001-engineering-model-independence.md)
- `docs/ARCHITECTURE.md`, `docs/DOCUMENT_PIPELINE.md`, `docs/PROVENANCE.md`
