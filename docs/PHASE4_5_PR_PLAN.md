# Phase 4.5 — PR plan

How Phase 4.5 (document workspace UI refactor) is delivered: a sequence of small, reviewable pull requests. Work through them in order. Each one is a self-contained unit that leaves `main` green.

- Specification: [`cursor/phase4.5_specs.txt`](../cursor/phase4.5_specs.txt). Section references below (`§14`) point at it.
- No new ADR. This refactor does not change domain semantics (§40, §56).
- Phase status: [PROJECT_STATUS.md](PROJECT_STATUS.md)

This file is the delivery plan. If a PR forces a change to the plan or the spec, update this file (and the spec) in that PR and say so in the PR description.

Related work stays in one PR. Presentation precedence, needs-review, issues, and quick-view membership are one pure model. Search, quick views, the filters popover, counts, empty states, and the Add Documents menu are one way of finding and adding documents. The simplified row, the detail drawer, and every action that moves out of the table are one interaction: rows communicate state, and the drawer performs the work. Documentation and the completion audit ship after that UI is done, not before it.

## Contents

1. [Working agreements](#1-working-agreements)
2. [PR overview and tracker](#2-pr-overview-and-tracker)
3. [Dependency graph](#3-dependency-graph)
4. [PR details](#4-pr-details)
5. [Traceability: spec to PR](#5-traceability-spec-to-pr)
6. [Open decisions](#6-open-decisions)
7. [Intermediate-state compatibility](#7-intermediate-state-compatibility)
8. [Risks](#8-risks)
9. [Coverage audit and intentional exclusions](#9-coverage-audit-and-intentional-exclusions)

---

## 1. Working agreements

### Per-PR rules

1. **One PR, one purpose.** Do not pull work forward from a later PR. Do not add engineering-model UI, equipment, extraction results, topology, a generic review queue, or new backend workflow "while we're here" (§48, §52).
2. **`main` stays green and usable.** Every PR must pass the gate below. After each merge, an engineer can still upload, reuse, search, edit metadata, classify, process, view pages, download, remove, and restore. A cleaner table that hides an action until a later PR is not mergeable (§51).
3. **Branch naming:** `phase4.5/pr-NN-short-name`. Commit messages: short imperative summary; body explains why.
4. **Tests ship with the code they cover**, not in a later PR. Each PR lists its required tests. A test that asserted the old toolbar or the old columns is rewritten in the PR that removes that UI, not left failing and not left asserting a layout that no longer exists.
5. **Docs ship with behavior.** The specified-but-not-started status is already recorded in `PROJECT_STATUS.md`, `README.md`, `ARCHITECTURE.md`, `DOCUMENT_PIPELINE.md`, `DEVELOPMENT.md`, and `PHASE0_HANDOFF.md`. PR-01 changes that status from specified to in progress. PR-04 records completion, the short UI note, and the handoff. Intermediate PRs update this plan's tracker when they merge.
6. **Record deviations.** Anything that differs from the spec or from the defaults in [section 6](#6-open-decisions) goes in the PR description under "Deviations".
7. **Do not commit** `apps/web/tsconfig.tsbuildinfo`. Restore it with `git checkout -- apps/web/tsconfig.tsbuildinfo` before committing.
8. **No backend or domain change** unless a PR discovers the list payload cannot support the UI. That discovery stops the PR. Document why, keep the API change minimal, and add backend tests in that same PR (§40). The expected outcome is no API change.

### Verification gate (run before opening and before merging)

Phase 4.5 is frontend work. CI still runs the Python gate, so a PR that touches Python must run it locally. Every PR runs the web gate.

```bash
cd apps/web && npm run lint && npm test && npx tsc --noEmit
git checkout -- tsconfig.tsbuildinfo
```

PR-03 and PR-04 also run the production build:

```bash
cd apps/web && npm run build
```

PR-04, and any PR that changes Python, also runs:

```bash
source .venv/bin/activate
ruff check .
pytest

docker exec powerforge-postgres-1 psql -U powerforge -d postgres -c "CREATE DATABASE powerforge_test;"
export DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge_test
alembic -c database/alembic.ini upgrade head
RUN_INTEGRATION=1 pytest
docker exec powerforge-postgres-1 psql -U powerforge -d postgres -c "DROP DATABASE powerforge_test;"
unset DATABASE_URL
```

CI (`.github/workflows/ci.yml`) runs ruff, pytest with `RUN_INTEGRATION=1`, and the web lint, test, and build.

### PR description template

```
## Summary
## Spec sections covered
## Changes (files/modules)
## Tests added (and what they prove)
## Verification run (commands + results — only what was actually executed)
## Deviations from spec / plan
## Follow-ups / debt
```

### Sizing

XS < 50 lines, S < 300, M < 800, L > 800 (excluding generated code and lockfiles). PR-03 is expected to be L. If it grows past a reviewable diff, split only on the seam named in that PR. Do not split the drawer by section.

---

## 2. PR overview and tracker

Update the checkbox and status when a PR merges. PR-01 and PR-04 keep [PROJECT_STATUS.md](PROJECT_STATUS.md) in sync.

| PR | Title | Area | Size | Depends on | Status |
| --- | --- | --- | --- | --- | --- |
| [PR-01](#pr-01--document-presentation-state) | Document presentation state | Web | S | — | [x] |
| [PR-02](#pr-02--workspace-toolbar-quick-views-and-filters) | Workspace toolbar, quick views, and filters | Web | M | PR-01 | [x] |
| [PR-03](#pr-03--master-detail-list-and-document-drawer) | Master-detail list and document drawer | Web | L | PR-01, PR-02 | [x] |
| [PR-04](#pr-04--verification-documentation-and-phase-45-completion) | Verification, documentation, and Phase 4.5 completion | Docs | S | all | [x] |

---

## 3. Dependency graph

Each line reads "PR needs → these PRs merged first".

```
PR-01   needs  —
PR-02   needs  PR-01
PR-03   needs  PR-01, PR-02
PR-04   needs  everything
```

```
Selectors:   PR-01 ─► PR-02 ─► PR-03 ─► PR-04
                        toolbar    list + drawer    audit
```

Practical ordering: 01 → 02 → 03 → 04. There is no parallel slice. PR-03 needs the toolbar from PR-02 so it does not rebuild search, filters, or Add Documents while moving row actions.

---

## 4. PR details

### PR-01 — Document presentation state

**Status.** Done. Selectors and tests live in `apps/web/src/lib/document-presentation.ts`. The workspace UI is unchanged.

**Goal.** Put the unified list state, needs-review, issues, and quick-view membership in one tested module before any component reads them. The workspace looks unchanged. (§8–§11, §14, §42)

**Depends on.** Nothing.

**Scope.**

- New `apps/web/src/lib/document-presentation.ts`. Pure functions over the existing `RevisionDocument` type. No React, no fetch.
- `deriveDocumentPresentationState(row)` returns exactly one of:
  1. `removed` — `status === "REMOVED"`
  2. `processing_failed` — current `processing.status === "FAILED"`
  3. `processing` — current `processing.status` is `PENDING` or `RUNNING`
  4. `classification_failed` — latest `classification.attempt.status === "FAILED"` and processing is `COMPLETED`
  5. `classifying` — latest attempt is `PENDING` or `RUNNING`
  6. `needs_review` — see the rule below
  7. `not_started` — included, `processing === null`, and none of the above
  8. `ready` — none of the above
- The current processing summary is the only processing fact available. A `FAILED` current run is processing-failed. There is no older completed run in the list payload to prefer (§9, API comment on `ProcessingSummary`).
- `documentNeedsReview(row)` is true only when the row is included, `classification.suggestion` is non-null, and `suggestion.accepted` is false. Unknown + suggestion, a confirmed type that differs from the suggestion, and an unaccepted `MIXED_DOCUMENT` suggestion are all cases of that rule, not extra rules. An accepted suggestion is not needs-review, including when the confirmed type matches it. A suggestion-less row is not needs-review. A removed row is not needs-review.
- `documentHasIssue(row)` is true only for `processing_failed` and `classification_failed`. `not_started` is not an issue.
- `matchesQuickView(row, view)` for `all` | `needs_review` | `issues` | `removed`:
  - `all` — `status === "INCLUDED"`
  - `needs_review` — presentation state is `needs_review`
  - `issues` — `documentHasIssue`
  - `removed` — `status === "REMOVED"`
- Needs Review and Issues are subsets of included documents. They sit inside All. Removed is outside All. Counts are not a partition of the header total.
- `matchesAdvancedFilters(row, filters)` for document type, origin, processing status (`NONE` | `PENDING` | `RUNNING` | `COMPLETED` | `FAILED`), and classification attempt state (the existing `classificationAttemptState` values). Empty filter values match everything.
- `countQuickViews(rows)` returns `{ all, needsReview, issues, removed }` using the predicates above.
- Labels for each presentation state, including a failure subtype string (`Processing failed` / `Classification failed`) for the tooltip and the later drawer. The list still shows one dominant state.
- Update `docs/PROJECT_STATUS.md` from specified to **In progress:** Phase 4.5 (document workspace UI). **Next:** Phase 5, not started. Do not mark 4.5 complete. The spec link and this plan are already there.

**Out of scope.** Components, toolbar, drawer, CSS, API client changes, URL state, metadata-line formatting.

**Tests** (`apps/web/src/lib/document-presentation.test.ts`):

- removed wins over a failed processing run, a failed classification attempt, and an unaccepted suggestion
- processing `FAILED` is `processing_failed` even when a suggestion exists
- `PENDING` and `RUNNING` processing are `processing`, including when a suggestion is unaccepted
- classification `FAILED` with `COMPLETED` processing is `classification_failed`, and the helper still exposes the current suggestion when one exists (the state function does not drop it)
- classification `PENDING` / `RUNNING` is `classifying`
- included + suggestion + `accepted: false` is `needs_review` for Unknown, for a differing confirmed type, for a matching confirmed type, and for `MIXED_DOCUMENT`
- included + suggestion + `accepted: true` is not `needs_review`
- no suggestion is not `needs_review`
- `processing === null` on an included row with no suggestion is `not_started`, and `documentHasIssue` is false
- `COMPLETED` processing, no review condition, and no failed attempt is `ready`
- quick-view membership: a needs-review row is in All and Needs Review; an issue row is in All and Issues; a removed row is only in Removed
- advanced filters match type, origin, processing `NONE`, and classification attempt state independently
- `countQuickViews` counts the overlaps described above

**Acceptance.** Existing `revision-documents` tests still pass. The running UI is unchanged. `PROJECT_STATUS.md` says Phase 4.5 is in progress and does not say it is complete.

**Size.** S.

---

### PR-02 — Workspace toolbar, quick views, and filters

**Status.** Done. Frontend baseline before the toolbar change: 213 tests. After: 212 tests, lint clean, typecheck clean. The table columns and row actions are unchanged.

**Goal.** Replace the permanent toolbar with search, four quick views, a filters popover, and one Add Documents menu. Row columns and row actions stay as they are, so every current workflow remains on the row. (§12–§16, §44, §45, §47, §49)

**Depends on.** PR-01.

**Scope.**

- Rework the top of `RevisionDocuments` (extract `DocumentWorkspaceToolbar`, `DocumentQuickViews`, and `DocumentFiltersPopover` if that keeps the parent readable).
- Header: `Documents N`, where N is the All count defined below. Primary control: **Add Documents** with **Upload files** and **Add from another revision**. Both open the existing `DocumentUpload` and `ReuseDocumentDialog`. Do not rewrite upload queue behavior.
- One search field, same placeholder and 300ms debounce as today. The list request stays `listDocuments` with `search` set, so filename / document number / description matching stays the server's `ILIKE` behavior.
- The list request uses `status=ALL` plus the debounced search. It does not send `document_type` or `origin`. Type, origin, processing, and classification are applied in the client with `matchesAdvancedFilters`, because processing and classification are not list query parameters and the counts need the whole search result. The list is unpaginated today; do not add pagination.
- Quick views, using the existing `SegmentedControl`: **All**, **Needs Review**, **Issues**, **Removed**. Each label includes its count from `countQuickViews` after advanced filters and before the quick-view slice. Selecting a view filters with `matchesQuickView`. All does not include removed rows.
- **Filters** opens a popover (no new dependency; follow `DropdownMenu`'s keyboard and outside-click behavior). Fields: Document type, Origin, Processing state, Classification state, plus **Clear filters**. The trigger reads **Filters** or **Filters (n)** where n is the number of active advanced filters. Quick view and search do not count toward n.
- Empty copy, chosen from the active view when the filtered list is empty:
  - no documents in the revision at all, and no search or advanced filters: **No documents in this revision** and an Add Documents affordance
  - search or advanced filters exclude everything: **No documents match your search** (search) or the current no-match copy when only advanced filters are set
  - Needs Review empty: **No documents need review**
  - Issues empty: **No document issues**
  - Removed empty: **No removed documents**
- Errors from the list request stay on the list, with the existing retry. Upload and reuse errors stay on those workflows.
- Remove the always-visible type select, origin select, Included / Removed / All control, and the Uploaded / Inherited / Unclassified presets. Unclassified documents remain reachable through the type filter (`UNKNOWN`) and, when they have an unaccepted suggestion, through Needs Review.

**Out of scope.** Changing table columns, moving Accept / Retry / View pages / Download, the drawer, mixed-page placement, `?document=`.

**Tests.** Update `revision-documents.test.tsx` describes that assert the old toolbar (`filters`, `quick filters`). Add:

- Add Documents menu exposes Upload files and Add from another revision, and each opens the existing flow
- quick views filter to All (included only), Needs Review, Issues, and Removed
- counts follow the definitions in PR-01, including Needs Review and Issues sitting inside the All count, and Removed sitting outside it
- search still calls `listDocuments` with the debounced text and `status=ALL`
- filters popover sets type, origin, processing, and classification; the trigger shows the active count; Clear filters resets them
- empty copy for each view
- a row still renders the current columns and the current action buttons (regression so this PR does not strand actions)

**Acceptance.** An engineer can find documents with the new toolbar and can still run every Phase 2–4 row action from the old cells. `listDocuments` is not called per row.

**Size.** M.

---

### PR-03 — Master-detail list and document drawer

**Status.** Done. Frontend suite before this change: 212 tests. After: 209 tests, lint clean, typecheck clean, production build succeeded. The browser pass (search, quick views, filters, open a row, accept or keep current, pages, remove, restore) was not clicked; this session had no browser tools.

**Goal.** Make the table scannable and move every detailed operation into a right-side drawer and the overflow menus. This is one interaction, so the new columns and the drawer land together. (§3–§7, §17–§39, §41, §43–§46, §48–§51)

**Depends on.** PR-01, PR-02.

**Scope.**

Split `revision-documents.tsx` into focused components as the new UI is built. Prefer these names, and rename them if a nearby file already owns the concept:

| Component | Responsibility |
| --- | --- |
| `DocumentList` / `DocumentRow` | Three data columns plus overflow. The row is a keyboard-focusable control. |
| `DocumentState` | Icon and text for `deriveDocumentPresentationState`. Processing progress (`pages_processed / pages_total`) sits under Processing and Classifying. Failure subtype is in the accessible name and a tooltip, and the same text is in the drawer. |
| `DocumentOverflowMenu` | Secondary row actions. Evolves `DocumentRowActions`. |
| `DocumentDetailDrawer` | Right-side sheet. Header, close, optional More menu. |
| `DocumentOverview` | Stacks the sections below. One scrolling overview. Add an Overview / Pages / Classification tab only if mixed-page content makes the overview unreadably long. |
| `DocumentClassificationPanel` | Suggestion, confidence, rationale, accept, choose another, use suggestion, keep current, retry, reclassify, failure copy. |
| `DocumentProcessingPanel` | Complete / in progress / failed, view pages, retry processing. |
| `DocumentMetadataPanel` | Document number, description, notes, confirmed type. Uses the existing PATCH. |
| `MixedDocumentPageTypes` | Page predictions, loaded only when this section is shown. |

**List.**

- Columns are Document, Confirmed type, State, and overflow. Delete the permanent Origin, Included/Removed, Processing, AI Suggestion, Added, and Actions columns.
- Document cell: filename, then one quiet secondary line. Include only the facts that fit, in this priority: document number, file size, origin phrase, page count when `processing.pages_total` is known. Origin phrase is `Uploaded · {added date}` or `Inherited from Rev {identifier}` using `inherited_from_revision_identifier`. There is no third origin value; reuse stays Inherited. Do not print every field on every row.
- Confirmed type cell: `documentTypeLabel(document_type)`. When the type is `UNKNOWN` and a suggestion exists, a second line: `AI: {type} · {confidence}`. When the confirmed type differs from the suggestion, a second line: `AI suggests: {type}`. That difference is not an error color.
- Included is not shown. Uploaded and Inherited are not badges.
- The row click and Enter/Space open the drawer. The overflow trigger, the inherited-revision link if it remains, and any control inside the overflow stop propagation. The open row gets a selected background.
- A needs-review row does not get a Review button. Opening the row is the review action (§19).
- Narrow viewports: the table must not require a wide horizontal scroll. Collapse to a stacked row (filename, type, state, overflow) rather than keeping the desktop column widths. The drawer may use the full viewport width.

**Drawer.**

- Build the sheet in `apps/web/src/components/ui/` without a new dependency. Lucide icons already in the app: check for Ready, spinner for Processing and Classifying, warning for Needs review, alert for Failed, archive or x for Removed. State text is always present.
- Focus moves into the drawer when it opens, returns to the invoking row when it closes, and Escape closes it.
- Header: filename, file size, page count when known, document number when present, close. Actions live in the body and in More, not as a row of header buttons.
- Confirmed type, with **Change type** revealing the existing type control. Submitting `document_type` goes through `updateDocument` and therefore clears accepted AI provenance on the server. Refetch; do not treat local state as authority.
- AI section, fed by the list summary immediately and by `GET .../classification` when the drawer opens so rationale, score, and alternatives can render. Add `getClassification` to `apps/web/src/lib/documents.ts`. Do not fetch this for every row.
  - Unaccepted suggestion: suggested type, confidence band, rationale, **Accept suggestion**, **Choose another type**.
  - Accepted suggestion: accepted confirmation, no Accept button.
  - Confirmed type differs and the suggestion is unaccepted: show both, **Use AI suggestion** (accept), **Keep current** (no request).
  - Latest attempt failed while a suggestion still exists: show the suggestion, the failure, `classificationErrorLabel`, and **Retry**. The failed attempt must not hide the suggestion.
  - Latest attempt failed and no suggestion exists: failure, concise error, **Retry**.
  - Reclassify sits below the primary accept actions, or in More. It is not beside Accept.
- Processing section: complete with page count and **View pages**; in progress with `processed / total`; failed with the concise `error_message` and **Retry processing**. **View pages** opens the existing `PageViewer`. Closing the viewer leaves the same document selected and the drawer open.
- Mixed document: page breakdown in the drawer only, one row per page (range grouping is optional and not required). Opening the section calls the existing `listClassificationPages`. A page control opens the page viewer at that page. No page-level accept control. The table must not render page predictions and must not call the pages endpoint while painting rows.
- Origin: uploaded in this revision, or inherited from the revision identifier the API returns. Do not invent "Added from" as a separate provenance.
- Metadata: document number, description, notes. Editable through the existing editor behavior (`DocumentEditor` can move inside the drawer). Filename, SHA-256, storage key, file size, and MIME type stay read-only. The API already omits the storage key.
- Local errors sit on the section that failed (metadata, accept, retry). The existing list-level warning for 404/409 and read-only refresh stays.
- After a successful mutation, refetch. Do not optimistically rewrite document type, acceptance, or removal (§46).
- `?document=<revision_document_id>` on the current revision route when it is a small `useSearchParams` read/write. Refresh and deep link reopen that drawer. Browser Back closes it. If that fights the existing page, skip it in this PR and record the deviation. Do not add a document detail route.

**Menus.**

- Row overflow and drawer More show only actions that apply. Hide the rest. Destructive actions are separated.
- Possible actions: Open details (until the drawer is the details surface, this item is redundant and should be omitted), View pages, Download original, Open original when `canOpenInline`, Edit metadata, Reclassify, Retry classification, Retry processing, Remove from revision, Restore to revision.
- Download and Open keep the current signed-URL behavior in `DocumentRowActions`.
- Remove still confirms with `ConfirmDialog` and the current copy. Restore stays immediate.
- `canMutate === false` (superseded or otherwise immutable revisions): the drawer still shows metadata, AI, processing, pages, and download/open. Hide accept, change type, edit, remove, restore, retry, and reclassify. Do not hide them more aggressively than `canMutate` already does. Processing and classification belong to the document; follow the existing flag rather than inventing a stricter rule (§35).

**Out of scope.** A generic review module, new list endpoints, page-range compression, rewriting `PageViewer`, Phase 5 screens. Toolbar behavior from PR-02 stays.

**Tests.** Rewrite the row, processing-column, AI-column, download, and row-action describes in `revision-documents.test.tsx` so they assert behavior instead of the deleted columns. Cover at least:

- the table has Document, Type, and State, and does not have Origin, Processing, or Actions column headers
- secondary metadata is in the document cell; Included is absent on a normal row
- Unknown + suggestion renders the quiet AI line; a differing type renders the suggestion line
- row click opens the drawer; Escape and the close control close it; choosing another row swaps the contents; overflow click does not open the drawer
- drawer shows confirmed type, suggestion, confidence, accepted state, processing, origin, and metadata
- Accept calls `acceptClassification`; Change type / manual override calls `updateDocument`; Use AI suggestion accepts; Keep current does not call a mutation
- retry classification and reclassify call the existing functions; a failed latest attempt still shows the previous suggestion
- View pages opens the viewer; retry processing calls `retryProcessing`; progress text renders from the summary
- mixed page predictions are absent from the table; they render in the drawer after `listClassificationPages`; a page control can open the viewer at that page
- overflow contents follow state (included vs removed, failed processing, failed classification, read-only); Download remains; unavailable actions are absent
- read-only mode hides mutation controls and still offers download
- upload and reuse still work from Add Documents
- list paint does not call `listClassificationPages` or `getClassification`; the drawer does

**Acceptance.** Every capability in §51 is reachable from the drawer or a menu. The production build succeeds. Browser check when browser tools are available: open a revision, search, switch quick views, open Filters, open a row, accept or keep current, open pages, close the viewer and confirm the drawer is still on that document, remove, and restore. Record what was not clicked.

**Size.** L. If the diff cannot be reviewed in one pass, the only allowed split is:

1. **PR-03a — simplified list whose overflow still contains every action** (accept, choose type, view pages, retry processing, retry classification, reclassify, download, open, edit, remove, restore, and mixed page types reached from the menu). No drawer yet.
2. **PR-03b — drawer absorbs those workflows**, the overflow shrinks to secondary actions, and row click opens the drawer.

Do not split classification, processing, metadata, and mixed pages into separate PRs. 03b follows 03a immediately. Update this tracker if that split happens.

---

### PR-04 — Verification, documentation, and Phase 4.5 completion

**Status.** Done (2026-10-12). Merge commits: PR-01 `9f00180`, PR-02 `dcca9b7`, PR-03 `d0bfef2`. This close-out sits on `d0bfef2`. The audit found one gap: retry processing, retry classification, and reclassify were hidden on a read-only revision even though those API calls are document operations. They are shown again. Accept, change type, edit, remove, and restore stay hidden. No Python diff.

**Goal.** Prove the definition of done against the merged UI, write the short design note, and publish the handoff. No new interaction. (§54–§58)

**Depends on.** PR-01, PR-02, PR-03.

**Scope.**

- Re-read §57 and §51 against the UI. Fix only gaps where a required behavior is missing or a test claims coverage it does not have. A missing feature that is really a new idea goes in Follow-ups, not into this PR.
- Run the web gate, `npm run build`, and the Python gate. The Python diff should be empty.
- Browser pass of the flows in PR-03's acceptance list, if browser tools are available. Write down what ran and what did not.
- `docs/PROJECT_STATUS.md`: Phase 4.5 complete, with the workspace summary below. **Next:** Phase 5, not started.
- `cursor/phase4_5_document_workspace_ui.txt`: a short note, not an ADR. Record the master-detail workspace, the simplified table, the unified presentation state, AI and processing living in the drawer, actions living in overflow and the drawer, and that backend semantics did not change.
- `docs/DEVELOPMENT.md`: the revision workspace description should match the new layout (quick views, drawer, Add Documents).
- This plan: check the tracker and note the merge commits.
- PR description is the handoff, using the spec's A–U list: components, layout, columns, state rules, quick views, filters, drawer, AI placement, processing placement, mixed pages, overflow, responsive behavior, accessibility, API changes, tests, commands and results, browser verification, deviations, debt, confirmation that Phase 5 was not implemented, and a suggested commit message.

**Out of scope.** Visual redesign beyond gap fixes, URL state if PR-03 deferred it (record it as debt), Phase 5.

**Tests.** Any test added here must close a §50 gap found in the audit. Do not add a parallel suite that repeats PR-01–PR-03.

**Acceptance.** §57 is checked item by item in the PR description. Commands and browser results are only those actually run.

**Size.** S.

### Handoff (§58)

**A. Components.** Added `document-presentation.ts`, `document-workspace-toolbar.tsx`, `ui/sheet.tsx`, `document-list.tsx`, `document-state.tsx`, `document-overflow-menu.tsx`, `document-detail-drawer.tsx`, `document-overview.tsx`, `document-classification-panel.tsx`, `document-processing-panel.tsx`, `document-metadata-panel.tsx`, and `mixed-document-page-types.tsx`. Removed `document-row-actions.tsx`. `revision-documents.tsx` keeps fetch, filters, selection, and mutations. `documents.ts` gained `getClassification`. `DropdownMenu` gained an optional text trigger.

**B. Layout.** Header `Documents N`, Add Documents, search, Filters, then All / Needs Review / Issues / Removed. The list is beside a right-side drawer. Below `md` the row stacks filename, type, state, and overflow.

**C. Columns.** Document, Type, State, overflow. The document cell shows at most three of: document number, file size, origin phrase, page count. Included is not shown. Uploaded and Inherited are not badges.

**D. State.** `deriveDocumentPresentationState`: removed, processing failed, processing, classification failed, classifying, needs review, not started, ready. Needs review is included, a suggestion, and `accepted === false`. Failure subtype is in the accessible name, the tooltip, and the drawer.

**E. Quick views.** All is included documents. Needs Review and Issues sit inside that count. Removed sits outside it. Counts are taken after search and advanced filters, before the quick-view slice.

**F. Filters.** One `listDocuments` call with `status=ALL` and the debounced search. Type, origin, processing, and classification filter in the client. The trigger shows `Filters` or `Filters (n)`. Clear filters resets those four fields.

**G. Drawer.** Header is filename, size, page count, document number, More, and close. One scrolling overview: confirmed type, AI classification, processing, origin, metadata. No tabs. `?document=` on the revision route opens it; Back, Escape, and close dismiss it.

**H. AI.** The list summary paints the drawer immediately. `GET .../classification` loads rationale, score, and alternatives when the drawer opens. Accept, Choose another type, Use AI suggestion, and Keep current behave as in Phase 4. Keep current sends nothing. A failed attempt does not hide the previous suggestion. Reclassify sits below the accept actions.

**I. Processing.** Complete shows the page count and View pages. In progress shows `processed / total`. Failed shows `error_message` and Retry processing. Closing the page viewer leaves the drawer on the same document.

**J. Mixed pages.** Absent from the table. The drawer section calls `listClassificationPages` when opened, one row per page, and can open the viewer at that page. No page-level accept. No range grouping.

**K. Overflow.** View pages when processing completed; Download original always; Open original when `canOpenInline`. Edit, remove, and restore only when `canMutate` and the row is included or removed as today. Retry processing, retry classification, and reclassify follow the document and stay available on a read-only revision.

**L. Responsive.** The desktop table is four columns. Narrow viewports use a stacked row. The drawer can use the full viewport width.

**M. Accessibility.** The row is focusable and opens on Enter or Space. The drawer is a dialog; focus moves in on open and back to the row on close. Escape closes it. Overflow menus are buttons. State text is always present next to the icon.

**N. API.** No backend change. `getClassification` calls the existing `GET .../classification` route.

**O. Tests.** `document-presentation.test.ts` covers precedence, needs review, issues, and quick-view counts. `revision-documents.test.tsx` covers the toolbar, the three columns, the drawer, menus, and the read-only split. No new suite was added in this PR. The read-only tests now expect retry processing, retry classification, and reclassify, and still expect accept, change type, edit, remove, and restore to be absent.

**P. Commands.** `npm run lint`: no warnings or errors. `npm test`: 209 passed. `npx tsc --noEmit`: no errors. `npm run build`: succeeded. `ruff check .`: passed. `pytest`: 293 passed, 352 skipped. `RUN_INTEGRATION=1 pytest` on throwaway `powerforge_test` migrated to head: 645 passed. The database was dropped. `git diff` has no `services/`, `packages/`, or `database/` changes.

**Q. Browser.** Not clicked. No browser tools were available. The flows not exercised are search, quick views, Filters, open a row, accept or keep current, pages, close the viewer, remove, and restore.

**R. Deviations.** The secondary line drops page count when document number, size, and origin are all present. Open original stays in the menus. Selection uses `?document=` rather than a new route. There is one overview and no tabs. Mutations refetch the list and do not write the response over type, acceptance, or removal.

**S. Debt.** The workspace does not poll. A processing or classification run that finishes in a worker stays on the last fetched snapshot until the next list reload or a page refresh. Page-range grouping was not built. Stale `RUNNING` recovery is already recorded in `PROJECT_STATUS.md`.

**T. Phase 5.** Not implemented. No equipment, extraction, or topology UI.

**U. Suggested commit message.** Close Phase 4.5 after the workspace audit.

### Definition of done (§57)

- The list is Document, Type, State, and overflow. Origin, date, and size are on the secondary line. Included is not shown on a normal row.
- Processing and classification collapse to one presentation state. AI controls and mixed-page tables are out of the cells.
- A row opens a drawer with confirmed type, AI classification, processing, origin, and metadata.
- Previous actions remain reachable from the drawer or a menu, including document-level retry and reclassify on a read-only revision.
- Add Documents consolidates upload and reuse. Quick views are All, Needs Review, Issues, and Removed. Secondary filters sit behind Filters. Search stays visible. Overflow holds secondary actions. Removed and read-only both work.
- The list does not call `getClassification` or `listClassificationPages`. Page predictions load when the drawer section opens.
- Phase 2, 3, and 4 workflows stay on the new surfaces. Frontend lint, tests, typecheck, and the production build passed, and the Python gate passed with an empty Python diff.
- Responsive behavior is the stacked row and full-width drawer described above. It was not clicked in a browser.
- No Phase 5 functionality was added.

### Follow-ups

- Refresh the open revision workspace when a worker finishes processing or classification, without a page reload.

---

## 5. Traceability: spec to PR

| Spec | Topic | PR |
| --- | --- | --- |
| §1 | Inspect, baseline, plan before code | This plan. PR-02 records the frontend baseline in its description before the toolbar edit. PR-04 re-runs the full gate. |
| §2–§3 | Purpose and master-detail architecture | PR-03 |
| §4–§7 | List columns, document cell, confirmed type | PR-03 |
| §8–§11 | Unified state, precedence, needs review, quiet normal rows | PR-01 defines them. PR-03 renders them. |
| §12–§16 | Header, Add Documents, quick views, filters, search | PR-02 |
| §17–§19 | Row click, overflow, one prominent action | PR-03 |
| §20–§27 | Drawer, type editing, AI review, failure, processing | PR-03 |
| §28 | Page viewer preserved; drawer selection survives it | PR-03 |
| §29–§30 | Mixed pages leave the table; tabs only if needed | PR-03 |
| §31–§35 | Origin, metadata, remove/restore, download, read-only | PR-03 |
| §36–§39 | Responsive, accessibility, hierarchy, icons | PR-03 |
| §40 | No backend redesign | Every PR. PR-04 confirms the Python diff. |
| §41–§42 | Component split and pure selectors | PR-01 selectors. PR-02 toolbar components. PR-03 list and drawer components. |
| §43 | Optional `?document=` | PR-03, skippable with a recorded deviation |
| §44–§47 | Empty, error, optimistic, upload entry points | PR-02 empty/search/upload entry. PR-03 local section errors and no optimistic writes. |
| §48 | Do not build the future review module | Every PR's out-of-scope. PR-04 audit. |
| §49 | No per-row classification or page fetches | PR-02 list query. PR-03 lazy drawer fetches. |
| §50 | Required frontend tests | Mapped below. PR-04 audits gaps. |
| §51 | Capabilities that must survive | PR-02 keeps them on the old row. PR-03 moves them. PR-04 checks the list. |
| §52 | No Phase 5 | Every PR. PR-04 confirmation. |
| §53–§54 | Target end state and quality bar | PR-03 implements. PR-04 reviews. |
| §55 | Implementation order | This plan. Inspection and the written plan happen before PR-01. |
| §56 | PROJECT_STATUS and the UI note | Specified status is recorded before PR-01. PR-01 marks in progress. PR-04 completes it and writes the note. |
| §57 | Definition of done | PR-04 checklist |
| §58 | Handoff A–U | PR-04 PR description |

### Required test groups (§50)

| Group | PR |
| --- | --- |
| Simplified columns; no Origin / Processing / Actions column | PR-03 |
| Row click opens and changes the drawer; drawer closes | PR-03 |
| State precedence (removed, processing, classifying, both failures, needs review, ready) | PR-01 |
| Needs review: Unknown + suggestion, accepted, manual difference, no suggestion | PR-01 |
| Quick views and counts | PR-01 predicates, PR-02 UI |
| Filters popover, active count, clear, search | PR-02 |
| Drawer contents: type, suggestion, confidence, accepted, processing, origin, metadata | PR-03 |
| Accept, manual type, use suggestion, keep current, retry, reclassify, failed reclassify keeps the suggestion | PR-03 |
| View pages, retry processing, progress | PR-03 |
| Mixed pages absent from the table, present in the drawer, page opens the viewer | PR-03 |
| Overflow actions, remove/restore, download, hidden unavailable actions | PR-03 |
| Read-only hides mutations; viewing and download remain | PR-03 |
| Keyboard labels for drawer and menus where the current test tools can drive them | PR-03 |
| Upload, add-from-revision, metadata, page viewer, classification regression | PR-02 keeps the entry points working; PR-03 re-proves them from the new surfaces |
| Prior frontend tests rewritten only where they asserted the old presentation | PR-02 and PR-03 |

### Definition-of-done bullets (§57)

| Requirement | PR |
| --- | --- |
| List is less congested; columns are Document / Type / State / overflow | PR-03 |
| Origin, date, and size live in the secondary line | PR-03 |
| Included is not shown on normal rows | PR-03 |
| Processing and classification collapse to one presentation state | PR-01, PR-03 |
| AI controls and mixed-page tables leave the cells | PR-03 |
| Row opens a drawer containing type, AI, processing, origin, and metadata | PR-03 |
| Previous actions remain reachable | PR-02 until PR-03, then PR-03 |
| Add Documents consolidates upload and reuse | PR-02 |
| Quick views All / Needs Review / Issues / Removed | PR-02 |
| Secondary filters sit behind Filters; search stays visible | PR-02 |
| Overflow holds secondary actions | PR-03 |
| Removed and read-only work | PR-03 |
| No per-row classification or page fetch | PR-03 |
| Phase 2, 3, and 4 workflows still usable | PR-02, PR-03, PR-04 |
| Frontend tests, TypeScript, lint, production build | PR-03 build; PR-04 full gate |
| Responsive behavior is acceptable | PR-03 |
| No Phase 5 functionality | PR-04 |

---

## 6. Open decisions

Settle these in the PR named. The default is the rule to implement. A different choice is a deviation and must be written into that PR and, if it changes ongoing behavior, into this plan.

| ID | Decision | Needed by | Default |
| --- | --- | --- | --- |
| D1 | What does the list request return, and where do quick views run? | PR-02 | One `listDocuments` call with `status=ALL` and the debounced `search`. Type, origin, processing, and classification filter in the client. No new endpoint. No pagination. |
| D2 | What do the header and the pills count? | PR-02 | After search and advanced filters, before the quick-view slice. `Documents N` equals the All count (included only). Needs Review and Issues are inside that N. Removed is outside it. |
| D3 | When is a row needs-review? | PR-01 | Included, a non-null suggestion, and `suggestion.accepted === false`. Matching the suggestion without accepting it still needs review. Accepted suggestions do not. |
| D4 | Where does "never processed" sit? | PR-01 | Presentation state `not_started`. It is in All. It is not an Issue and not Needs Review. The State cell says "Not started". |
| D5 | Does selection live in the URL? | PR-03 | Yes, `?document=<revision_document_id>` on the existing revision page, if `useSearchParams` fits the current route. Otherwise skip it and record the debt. No new route. |
| D6 | Where does the AI rationale come from? | PR-03 | Lazy `GET .../classification` when the drawer opens. The list summary paints the drawer until that returns. Rows do not call it. |
| D7 | What happens to Open (inline)? | PR-03 | It stays, in the row overflow and the drawer More menu, under the same `canOpenInline` rule as today. The spec's action list names Download; Open is existing behavior and stays reachable. |
| D8 | How is a reused document described? | PR-03 | `origin === "INHERITED"` plus `inherited_from_revision_identifier`. Copy is "Inherited from Rev {id}". Do not add an "Added from" state the API does not have. |
| D9 | Drawer tabs? | PR-03 | One Overview scroll. Tabs only if the mixed-page block makes that scroll fail the quality bar, and then with no duplicated fields. |

---

## 7. Intermediate-state compatibility

What an engineer sees on the revision documents page while Phase 4.5 is only partly merged:

| After | Behavior |
| --- | --- |
| PR-01 | No visible change. New selectors are unused by the UI. |
| PR-02 | New toolbar: Add Documents, search, Filters, and All / Needs Review / Issues / Removed. The table still has the old columns and the old cell buttons, so classification, processing, download, edit, remove, and restore still happen on the row. |
| PR-03 | The target workspace. Rows are Document / Type / State / overflow. Work moves to the drawer. |
| PR-04 | Docs and audit. Behavior matches PR-03 unless the audit fixes a gap. |

PR-02 is intentionally uglier than the end state. It is mergeable because nothing the old table could do is removed. PR-03 is the point where the cell buttons disappear, and only because the drawer and overflow already expose them in that same PR.

---

## 8. Risks

| Risk | Mitigation |
| --- | --- |
| PR-03 deletes a cell action and the drawer does not gain it | §51 checklist is in the PR-03 test list. PR-02 keeps the old cells until that PR. |
| Quick-view counts disagree with the rows on screen | One selector module in PR-01. PR-02 counts the same array it filters. |
| Needs Review and Issues treated as additive with All | Tests in PR-01 and PR-02: those counts sit inside All; Removed sits outside. |
| A failed reclassify hides the last good suggestion | State precedence uses the attempt for the badge and leaves `suggestion` intact. Drawer tests assert both. |
| Filtering Needs Review by a new API would require backend work | D1 keeps it client-side on the unpaginated list. |
| Search behavior drifts | Search stays on the existing query parameter. Client code does not reimplement `ILIKE`. |
| Drawer fetch per row | Tests assert `getClassification` and `listClassificationPages` are not called while rendering the list. |
| Read-only mode hides document-level retry that the API still allows, or shows a mutation the API rejects | Follow `canMutate` exactly (D and §35). |
| PR-03 is too large to review | Only the 03a/03b seam in that PR. Do not split drawer sections apart. |
| A new dialog library or icon package lands for one sheet | Sheet and popover are local. Icons come from `lucide-react`. |
| Phase 5 UI sneaks into the drawer | Out-of-scope lists. PR-04 reads the diff for equipment, extraction, and topology. |

---

## 9. Coverage audit and intentional exclusions

**Audit.** Spec sections §1–§58, the §50 test groups, and the §57 done bullets each map to a PR in section 5. The defaults in section 6 close the spec's loose spots: client-side counts without a new endpoint, needs-review as "unaccepted suggestion", `not_started` for a null processing run, and Open remaining in the menus.

**Intentionally not covered by any PR:**

- Backend, migration, worker, provider, taxonomy, or provenance changes (§40)
- A generic review queue or the future review categories in §48
- Engineering model, equipment, attributes, extraction, topology, entity resolution, conflicts, missing-data workflows, ETAP/SKM/EasyPower (§52)
- A new document detail route
- Page-range grouping for mixed documents, unless it falls out of the drawer without extra complexity (§29)
- Optimistic mutation (§46)
- An ADR (§56)
- Playwright. UI coverage is vitest plus the PR-03/PR-04 browser pass when tools are available

Phase 4.5 answers only "where does document work happen in the revision workspace?"
