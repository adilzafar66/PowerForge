# UI-B — Reactive data and interaction states

Implemented on `codex/ui-b-reactive-data`, starting from `main` at `0b9069c`. Scope: [UI-B prompt](prompts/UI-B_codex_prompt.md). The local approved references extend through v1.12; no v1.14 package was available. UI-C–UI-G and Phase 6 remain unimplemented.

## Shared server state

- TanStack Query 5.105.0 owns client server state. One provider sits above the App Router shell. Server pages create request-local clients and hydrate timestamped project/revision queries; subsequent server renders can replace older cache entries. Revision headings, permissions and shell publications now read the same reactive queries. Initial server failures use recoverable errors rather than fabricated empty project lists or blanket 404s.
- Deterministic keys scope projects, revisions, registry, equipment lists/editor snapshots, nodes, connections, document lists/details, classification pages and viewer artifacts. URL workspace selection and local filters stay local. The old model refresh counter and document reload effects are removed. Selected documents remain inspectable when filtered out of the list.
- Default freshness is 30 seconds, inactive retention five minutes, with stale refetch on focus/reconnect. Registry freshness is one hour. Reads retry transient failures at most twice; ordinary 4xx errors do not retry. The existing document-list 404/409 reconciliation is bounded to one additional read. Writes never retry automatically.
- Existing mutation APIs and form pending/error handling are retained. The shared HTTP transport and XHR upload path notify the mounted provider only after a successful response is parsed. The provider applies the cache policy; no server or module-level query cache is shared between requests. Failed requests preserve structured error codes and do not claim success or invalidate canonical data as a successful write.

## Invalidation policy

| Confirmed action | Affected queries |
| --- | --- |
| Project create | Project list |
| Project metadata/lifecycle | Project list and that project's detail/permissions |
| Revision create/activate/metadata | Project list/detail, revision list and that project's revision detail labels/permissions |
| Equipment edit/lifecycle | That revision's equipment lists, affected editor, nodes and connections |
| Node edit/lifecycle | That revision's nodes, connections and owner editor snapshots |
| Connection edit/lifecycle | That revision's connections |
| Document upload/reuse/edit/lifecycle/job retry/accept | That revision's document lists and the affected document's detail queries |
| Observed processing/classification change | That document's classification detail, page classifications and viewer data |

Inactive matching queries become stale without fetching. There is no application-wide invalidation. The atomic equipment save response replaces the editor cache and draft after confirmation; an obsolete editor refetch is cancelled first. Query refresh cannot replace a dirty equipment baseline/draft. Document metadata drafts also retain their baseline, preventing unrelated refreshed fields from becoming accidental edits.

## Jobs and feedback

- Document summaries poll at three seconds while real processing/classification runs are `PENDING` or `RUNNING`. Request failures increase the interval up to 30 seconds. Polling pauses in background tabs/offline and stops when the observer unmounts or jobs finish.
- Processing commits before classification enqueue. A bounded 15-second window watches completed, classification-enabled documents with no attempt for this handoff; it does not invent a queued run. Classification detail polls only during its actual active attempt. Workers stuck in `RUNNING` remain a known backend recovery issue documented in PROJECT_STATUS; UI-B does not change their status.
- Classification stage/page counts come directly from the API. Failed attempts preserve the latest completed suggestion. Existing retry eligibility and completed-page visibility follow backend semantics.
- Shared loading/error/retry feedback keeps stale rows visible after refresh failures. Initial load skeletons, refreshing text, accessible error/success announcements, pending button semantics and restrained 180ms feedback motion respect reduced-motion preferences. Existing contextual success notices are used instead of adding duplicate global toasts.
- Failed document saves propagate to their form instead of resolving as success. Optional first-revision creation failure explicitly retains the created project and offers revision-only retry or a link to the saved project.
- Viewer page data is cached by document; signed artifact URL queries have zero stale/retention time and are not persisted. Download links still request fresh URLs on demand.

## Validation

- All 272 frontend tests pass (21 files), including invalidation scope, failed and pending writes, late revision responses, background-refresh failure/recovery, dirty equipment/document draft preservation, processing/classification polling visibility/completion, optional revision partial failure, and existing exact-number/boolean/null, terminal, topology and read-only safeguards.
- ESLint, TypeScript and the production build pass.
- Read-only Chrome checks passed for hydration without duplicate initial fetches, background failure with retained rows and Retry, existing equipment dirty-close confirmation, equipment/topology/documents navigation, portalled filters, mobile navigation and reduced motion. No API writes or browser page errors occurred. The alternate frontend port used browser-only CORS headers; backend configuration was unchanged.

## Intentional boundaries

UI-C owns project/revision layout and dedicated revision editing UI; UI-D/E/F own full equipment/document/topology redesigns. UI-G owns the final cross-workspace visual audit. Existing modal editor close/beforeunload safeguards remain; the previously reverted internal-navigation guard was not reintroduced. No backend endpoints, streaming infrastructure, extraction features, domain types or permission rules changed. No browser cache persistence or optimistic canonical writes were added.

Implementation follows TanStack's [App Router hydration guidance](https://tanstack.com/query/latest/docs/framework/react/guides/advanced-ssr). Review the implementation on `codex/ui-b-reactive-data` against its base commit `0b9069c`.
