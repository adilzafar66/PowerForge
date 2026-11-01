# UI-E — Documents workspace and evidence viewer

Implemented on `codex/ui-e-documents-workspace`, based on `main` commit `8499f07` (UI-A through UI-D plus the navigation-guard fix). The implementation is in the working tree; no UI-E commit or push has been requested yet. Only the Documents workspace, the new viewer route and the shell pieces they need changed. Equipment, Topology, UI-C pages and the backend are untouched.

## Screens and components

- **Page chrome** (`revision-page-content.tsx`, `revision-workspace.tsx`, `app-frame.tsx`). Documents gets its own stage like Equipment. The revision summary block and the Documents / Engineering Model segmented control are hidden (the sidebar provides that navigation). The top bar uses the UI-C project bar on Documents and on the viewer.
- **Header and attention bar** (`documents-ui.tsx`, `revision-documents.tsx`). Title “Documents”, the subtitle “Review, classify, and manage source documents for Rev X.”, a “Revision details” link (`view=overview`) and an “Add documents” menu with Upload or Reuse from another revision. The attention bar is computed from the loaded list (“N documents need attention…” with View issues / View review, which switch the quick view). It is hidden when nothing needs attention. On read-only revisions an amber variant shows the existing `readOnlyReason` copy and replaces the generic read-only banner in this view.
- **Document register** (`document-workspace-toolbar.tsx`, `document-list.tsx`). A card with a search box, a Filters popover with count badge, and Refresh (a real `refetch`, showing “Refreshing…” then “Up to date”). Below that come quick-view tabs with counts (All / Needs review / Issues / Removed; logic stays in `document-presentation.ts`). The table has these columns:
  - Document: icon, name, number · size · pages.
  - Confirmed type.
  - Processing: state plus a 4px progress bar.
  - AI classification: Accepted / Needs review / Failed, with suggested type and band.
  - Origin: Uploaded/Inherited plus date.
  - Overflow menu.

  A footer count line closes the card. Removed rows are muted. At ≤1100px the table scrolls horizontally inside the card (min width 860px); the scroll wrapper is `relative` so its screen-reader-only content can't widen the page at 390px.
- **Upload and reuse dialogs** (`document-upload.tsx`, `reuse-document-dialog.tsx`). A 500px dialog following the prototype. `useUploadQueue` now lives in `RevisionDocuments`, so uploads continue and report into the register after the dialog closes.
- **Inspector** (`document-inspector.tsx`). A modal side panel built on the shared `Sheet` with the same presentation as the revision edit modal: full height, 398px wide (full width at ≤650px), sliding in over the register with the dark workspace overlay. The register keeps its full width underneath. Clicking the overlay, pressing Escape, or using Close dismisses it. Workspace messages such as “Saved changes to …” also appear under the inspector header, because the overlay hides the register's message line. Sections reuse the existing panels, restyled with unchanged behavior: header (filename, size · pages · date), status and origin (with the inherited-from revision link), confirmed type, processing with retry and “View pages / evidence”, AI classification (accept, keep current, reclassify, retry, mixed page types), document metadata, and a footer with Download and Remove/Restore through `ConfirmDialog` (or a read-only chip). The entry animation is disabled under reduced motion.
- **Unsaved edits in the inspector**. The metadata and type panels report a dirty flag. If there are unsaved edits, clicking the overlay, closing, or pressing Escape opens “Discard unsaved changes?” with Keep editing and Discard changes. While dirty, the UI-D `useNavigationBlocker` also guards links, revision switching, the viewer link and browser Back/Forward.
- **Document viewer** (`document-viewer.tsx`, route `projects/[projectId]/revisions/[revisionId]/documents/[documentId]/page.tsx`). A dedicated page inside the app shell:
  - Header: overline “Revision documents / Document viewer”, title “{number} — {filename}”, the subtitle “N pages · PDF · Processed” (plus “Removed from revision” when removed), the Document / Extraction Evidence switch, the Details toggle, and a disabled “Run extraction” described as “Extraction is not available yet”.
  - Toolbar: thumbnails toggle, previous/next with “n / N”, zoom −/+ with percentage, Fit page, Fit width, a page pill (page type for mixed documents, “Native text” or “No text layer”), and the panel toggle.
  - Thumbnail rail: lazy-loaded `THUMBNAIL` artifacts, with `aria-current` on the current page.
  - Canvas: `ANALYSIS_IMAGE` sized from the page dimensions, zoom 30–280% in 15% steps, Fit page and Fit width measured with a `ResizeObserver`, pointer-drag pan and scroll. The keys `+`/`=`/`-` zoom and the arrow keys change page; both are ignored inside inputs, menus and dialogs. If the image fails (for example an expired signed URL) the URL is requested again once, and the image remounts even if the new URL is identical. A second failure shows “The page image could not be loaded.” with Try again.
  - Details panel, real data only: source classification, document metadata, viewer actions (Open original, Download, Download page text when a `NATIVE_TEXT` artifact exists), and source version (processor and profile versions from `GET …/processing`).
  - Evidence mode: an honest “Not available” state explaining that structured extraction isn't available yet, with “Show document details”. It shows no candidates, boxes or confidence values.
  - Other states: still processing (with progress), waiting to start, failed (with Retry processing), not processed, pages not ready (409), loading, no pages, and a “Document not found” page with Back to documents. Removed documents stay viewable.
- **Deleted** (all replaced by the components above): `page-viewer.tsx` (the modal viewer), `document-detail-drawer.tsx`, `document-overview.tsx` and `document-state.tsx`. Every “View pages” entry point (overflow menu, processing panel, mixed-page links) now navigates to the viewer.
- **Tokens and motion**. `design-tokens.css` gained the documents max width, inspector width and shadow, viewer panel and thumbnail widths, progress track and the evidence canvas colour. `workspace-motion.css` gained the inspector/viewer keyframes.

## URL contract

- Register selection is unchanged: `/projects/{p}/revisions/{r}?document={id}`. Opening uses `push`, closing uses `replace`, and existing deep links still open the inspector.
- Viewer: `/projects/{p}/revisions/{r}/documents/{id}?page={n}&mode=evidence`. `page` is 1-based and omitted for page 1; `mode` is omitted for document mode. Page and mode changes use `replace`, so Back leaves the viewer in one step. Entry from the register uses `guardNavigation`, so the unsaved guard applies.
- The breadcrumb reads Projects › Project › Rev › Documents › filename. “Documents” links back to the register with `?document={id}` so the row stays selected. The sidebar keeps Documents active. Switching revision from the viewer goes to that revision's Documents; `revisionHref` drops `page` and `mode`.

## Visual evidence

Prototype and production were captured in Chrome at 1440, 1024 and 390 widths. The prototype states were the register, inspector, filters, upload/reuse/remove dialogs, read-only revision, and the viewer in document mode, evidence mode, with thumbnails collapsed and with the panel closed. Paired comparisons led to these corrections:
- Long titles no longer break mid-word at 1024.
- The viewer toolbar fits at 390.
- The 390px page no longer overflows horizontally (`scrollWidth` 847 before the fix).

Reference images are in `apps/web/.visual-artifacts/ui-e/` (git-ignored).

The visual harness (`apps/web/visual/run.mjs`, `fixtures.mjs`) now serves small page images for artifact URLs. Fixtures cover complete, running, failed, inherited, review and removed documents, plus pages. New captures, each at 1440/1024/390:
- `documents-{w}-register`, `-filters`, `-add-menu`, `-upload`, `-reuse` and `-inspector`.
- `-viewer`, `-evidence` and `-viewer-processing`.
- `-thumbs-collapsed` (not at 390).
- `-readonly`.

There is also `documents-unsaved-dialog`. The obsolete drawer step now waits for the inspector and opens the remove dialog from its footer.

Regression against `main`: a baseline was captured from a `main` worktree at `.visual-artifacts/ui-e/main-suite`, then this branch was compared against it.
- Geometry or computed styles changed only in the Documents captures (`desktop-documents`, `mobile-documents`, `document-drawer`, `document-remove-dialog`), which is expected.
- The 33 new captures report “no baseline”.
- Every other page (UI-C pages, Equipment, the editor, Topology) differed only by 4–45 anti-aliasing pixels with no geometry or style change. This matches the harness noise documented in UI-D.

## Checks run

- `npx vitest run`: 25 files, 336 tests passed. New `document-viewer.test.tsx` (14 tests) covers:
  - header facts and the page URL;
  - arrow keys, zoom and fit, and the toggles;
  - expired-URL retry, including an identical re-signed URL;
  - evidence mode;
  - running, failed (with retry) and 409 states;
  - mixed page types, removed documents and not-found.

  `revision-documents.test.tsx` (56 tests) covers:
  - the modal inspector, overlay click, Escape, and the `?document` deep link;
  - the unsaved guard on overlay click, Escape, close and the viewer link;
  - workspace messages shown inside the inspector;
  - attention bar counts and View issues;
  - uploads continuing after the dialog closes;
  - read-only viewing with mutations blocked.

  `app-frame.test.tsx` covers the viewer breadcrumb and revision switch, and `workspace-navigation.test.ts` covers `documentViewerHref` and `revisionHref` dropping viewer parameters.
- `npx tsc --noEmit -p .`: passed. `npx next lint`: no warnings or errors. `npm run build`: passed (viewer route 11.7 kB).
- A Chrome flow check against the Next dev server passed all 14 steps:
  1. A row opens the inspector over the register without changing the table width, and records `?document`.
  2. Clicking the overlay closes the inspector and strips the parameter.
  3. Escape closes the inspector.
  4. The deep link reopens after a reload.
  5. With unsaved edits, an overlay click asks first, and Keep editing preserves the draft.
  6. Browser Back is guarded while the draft is unsaved.
  7. Close followed by Discard changes closes the inspector.
  8. The inspector opens the viewer with a loaded image and breadcrumb.
  9. Keyboard zoom, fit width and drag-pan work.
  10. The arrow keys and thumbnails update the page URL.
  11. Evidence mode shows the unavailable state, and Run extraction is disabled.
  12. The breadcrumb returns to the selected document, and Back reopens the viewer.
  13. A revision switch from the viewer lands on that revision's Documents.
  14. An expired image URL is re-requested once and recovers.
- `node visual/run.mjs compare` against the `main` baseline: results as described above.
- No backend tests were run because no backend code changed.

## Deliberate deviations

- Typography keeps the production font and the UI-C scale (13.5px body, 12–12.5px supporting text, weights 400–700). The viewer title uses the 29px page title instead of the prototype's 23px.
- The search placeholder lists only the fields the API searches: filename, number and description (not type).
- There are no “Prototype · illustrative data” pills, demo upload card, or simulated progress. Progress comes from `pages_processed / pages_total`.
- The top bar keeps the UI-C project-status pill pattern. The Extraction sidebar item and the “Design prototype” pill are omitted because they aren't production routes.
- Extraction is honestly unavailable. Evidence mode shows an empty state, “Run extraction” is visible but disabled, and the viewer omits “Inspect extracted data →”.
- The register footer reads “Ordered by date added” instead of “Newest first”, because the API orders by `added_at` ascending.
- The attention bar is hidden when nothing needs attention; the prototype always shows it.
- “Keep current” on a classification suggestion is a local acknowledgement only; there is no API to reject a suggestion.
- The Origin column shows Uploaded/Inherited plus date. The link to the source revision lives in the inspector rather than the table cell.
- Below 800px the viewer hides Fit page / Fit width and the header Details button (the toolbar panel toggle remains), and the side panel starts closed and overlays the canvas when opened.
- Uploads keep running after the upload dialog closes, and their progress appears in the register.
- The inspector is modal with a dark overlay, matching the revision edit modal, rather than the prototype's nonmodal panel that narrows the register. Another row can't be selected while it's open; close it first.

## Future Backend/API Requirements

| Feature | Current limitation (API examined) | Proposed addition | Priority | UI-E disposition |
| --- | --- | --- | --- | --- |
| Counts and attention summary | `GET …/documents` returns no counts. Quick-view counts and the attention bar are computed client-side from the full list | `GET …/documents/summary` → `{total, needs_review, issues, removed, processing}` | Optional; needed for large revisions | Implemented with the existing list |
| Pagination and sorting | `document_service.list_revision_documents` is unpaginated and ordered by `added_at, original_filename, id` | Cursor pagination plus `sort` (added, name, type, status) and direction | Future phase | “Ordered by date added”; no sort controls |
| Search by type | `search` uses `ilike` on filename, document number and description only | Include the confirmed-type display name, or keep type as a filter | Optional | Placeholder reflects actual fields; type remains a filter |
| Thumbnail URL signing | One signed-URL request per page artifact. Lifetime is the global `s3_signed_url_expires_seconds` | Batch endpoint (`POST …/pages/artifact-urls` with page ids and kind), returning `expires_at` per URL | Recommended for long documents | Lazy per-page requests; re-request once on image error |
| Classification “keep current” / reject | Only accept and reclassify are available; a suggestion can't be dismissed on the server | `POST …/classification/reject` (or `decision: KEEP_CURRENT`) recorded with user and time | Recommended | “Keep current” is a local acknowledgement that doesn't persist |
| Text layer for image sources | `native_text_char_count` only covers native PDF text; scanned and image sources have no text | OCR artifact (`OCR_TEXT` plus word boxes) per page | Future phase | Page pill shows “No text layer”; Download page text only when `NATIVE_TEXT` exists |
| Extraction evidence | No extraction runs, candidates, evidence regions or confidence exist (Phase 6) | Extraction run API (start/status), candidates with page regions and confidence, and links from evidence to equipment and attributes | Future phase | Evidence mode is an unavailable state; Run extraction disabled |
| Last refreshed | The list response has no server timestamp | `generated_at` on list responses (or an `ETag`) | Optional | Refresh shows “Up to date” after a successful refetch |

All proposals must stay revision-scoped, preserve document lifecycle (active and removed), and keep classification and processing server-authoritative.

## Remaining risks

- The visual harness compares at `threshold: 0` and has a pixel-noise floor. Reviewers should rely on the geometry and computed-style results and the diff images.
- The navigation guard has the same limits as UI-D. A future programmatic `router.push` that bypasses `guardNavigation` would bypass the guard, and a guarded Back/Forward re-pushes the current entry, which drops forward history. The inspector guard only covers metadata and type edits, which are its only drafts.
- Thumbnails sign one URL per page, so very long documents make many requests while scrolling the rail. This is acceptable now, but it should move to the batch endpoint above.
- Counts and attention are computed from the full list, which will get heavy for large revisions until the summary and pagination endpoints exist.

UI-F and later phases were not started.
