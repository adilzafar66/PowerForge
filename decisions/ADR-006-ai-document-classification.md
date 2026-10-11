# ADR-006: AI document classification (Phase 4)

## Status

Proposed (2026-10-11). Not implemented. Specification: `cursor/phase4_specs.txt`. Delivery: [PHASE4_PR_PLAN.md](../docs/PHASE4_PR_PLAN.md).

## Date

2026-10-11 (proposed).

## Context

Phase 3 turns an immutable `Document` into stable pages, an analysis image, a thumbnail, and native PDF text when a text layer already exists ([ADR-005](ADR-005-document-processing-and-page-identity.md)). Phase 4 is the first semantic AI step. It answers what kind of engineering document this is, and, when the document is mixed or uncertain, what kind of content is on each page.

It does not extract equipment, ratings, tables, connections, single-line topology, or engineering-model entities. It does not add OCR.

The engineer already sets `RevisionDocument.document_type` by hand. That field is the confirmed classification for one revision. An automatic overwrite, including one gated on a confidence threshold, would hide the engineer's choice and make a later evaluation look better than the model is. AI output in this phase is a suggestion. Only an explicit accept changes the confirmed type.

## Decisions

1. **AI classification belongs to `Document`.** A `DocumentClassificationRun` and its predictions hang off the immutable file, not off `RevisionDocument`. Revisions that inherit or reuse that file share one machine classification. They are not classified again for the same processing run and classifier identity.

2. **The human-confirmed type remains `RevisionDocument.document_type`.** Acceptance is revision-scoped because that column is revision-scoped. Machine classification is not.

3. **AI never silently changes the confirmed type.** There is no confidence-threshold auto-accept. Accept is the only operation that sets `document_type` from a prediction, and it also sets `accepted_classification_prediction_id`. The displayed suggestion is the latest `COMPLETED` classification run for the current processing run. The newest attempt, of any status, is reported separately. A newer `PENDING`, `RUNNING`, or `FAILED` attempt does not hide that suggestion, and predictions from a failed run cannot be accepted.

4. **`MIXED_DOCUMENT` is added to the existing taxonomy.** `UNKNOWN` means there is not enough evidence. `OTHER` means the document is understood and no defined class fits. `MIXED_DOCUMENT` means several substantive classes are present. A cover, title, contents, or notes page plus one substantive class is not mixed. The taxonomy version is `document-taxonomy-v2`. The rest of the vocabulary is unchanged.

5. **Page classification is conditional.** Every run classifies the document first. Page classification runs only when the document prediction is `MIXED_DOCUMENT` or `UNKNOWN`, or when the score is below the high threshold (0.85). Confidence bands (`HIGH` / `MEDIUM` / `LOW`) are derived in PowerForge from the numeric score. The model does not return a band. The score is a routing heuristic, not a calibrated probability.

6. **Page predictions are routing suggestions.** They are visible to the engineer. Phase 4 does not add `DocumentPage.confirmed_type`, a page-approval workflow, or any other human-confirmed page type. Only a document-level prediction can be accepted onto `RevisionDocument.document_type`. A page prediction cannot be `MIXED_DOCUMENT`.

7. **A classification run references one specific `COMPLETED` processing run.** That run is the current Phase 3 run for the active `(document_id, processor_version, profile_hash)`, and only when it is `COMPLETED`. Older completed runs for a previous profile are not the classification target while a newer current run exists. The page set is `DocumentPage` rows numbered `1` through that run's `pages_total`. Native text and thumbnails come from that run's artifacts. `DocumentPage.native_text_char_count` is not the text source. A missing thumbnail on a page in that set fails the classification run as `ARTIFACT_UNAVAILABLE`.

8. **Runs and predictions are immutable historical outputs.** A failed run is not reset and reused. Its predictions may remain for debugging and are not the displayed suggestion. Reclassification inserts another run and leaves the previous run and its predictions unchanged. The partial unique index that enforces one live run is on classifier identity where status is `PENDING` or `RUNNING` only. `COMPLETED` is not part of that index, unlike Phase 3's processing-run index. A second completed run for the same identity is allowed when the engineer reclassifies.

9. **Retry creates a new run.** It is allowed only when the target run is `FAILED` and it is the newest run for that classifier identity. `retry_of_run_id` points at the failed run. `ensure` and backfill do not retry failure. If a `PENDING` or `RUNNING` run already exists for that identity, retry and reclassify insert nothing. A different classifier identity may be in flight at the same time.

10. **OpenAI is the first provider. Contracts stay vendor-neutral.** `ClassificationProvider` exposes `classify_document` and `classify_pages`. Domain and application code do not import OpenAI SDK types. The fake provider implements the same contract and is the path used by tests and local development without a key. The OpenAI adapter is the only place that knows the SDK.

11. **`gpt-6-luna` is the initial model, and the model is configuration.** The adapter uses the Responses API with Structured Outputs. The default reasoning effort is `none` and is also configuration. Chat Completions, tools, web search, file search, background responses, and conversations are not used.

12. **OpenAI requests set `store=false`.** The original PDF is not uploaded. The worker reads private thumbnail bytes through `ObjectStorage` and sends those bytes. Phase 3 thumbnails are WebP (PNG only when that is the stored artifact). The adapter sends the stored mime type and does not transcode. Document text and images are untrusted data. They cannot change the taxonomy, the instructions, or the output schema.

13. **Prompt, taxonomy, profile, provider, and model versions are persisted on every run.** The classifier identity hash covers provider, model, processing run id, classifier version, taxonomy version, prompt version, and sampling-profile hash. Editing a prompt requires a new prompt version. Sampling is deterministic: first page, last page, and evenly spaced interior pages. `RevisionDocument.document_type` is not given to the model as the expected answer.

14. **Automatic classification runs only when it is enabled.** After a Phase 3 run commits `COMPLETED`, the document worker may enqueue classification. A failed enqueue leaves that processing run `COMPLETED`. Classification can be disabled globally. Disabled mode does not require an API key, and explicit classification endpoints fail cleanly. Manual classification still works.

15. **Manual classification works whether or not AI is enabled, finished, or in agreement with the engineer.** Submitting `document_type` clears `accepted_classification_prediction_id`, even when the submitted value equals the stored type or the AI prediction. A metadata update that omits `document_type` leaves the prediction id in place. Accept is the only operation that sets that id.

16. **Lightweight usage telemetry is persisted. Monetary cost accounting is not.** Each provider call records provider, model, token counts, image count, latency, and a provider response id when one exists. Prompts, image bytes, document text, and secrets are not stored. There is no `estimated_cost_usd`, pricing table, or cost dashboard in this phase.

17. **Live-model evaluation is separate from normal CI.** The evaluation harness uses an external labeled set. Confidential documents are not committed. Automated tests use the fake provider or a mocked SDK boundary. A live OpenAI smoke run is optional and must not be claimed if it was not run.

18. **No extraction or engineering-model work is part of Phase 4.** No OCR, equipment or attribute extraction, table extraction, topology, embeddings, RAG, or ETAP/SKM/EasyPower integration.

19. **Revision inheritance and document reuse both carry acceptance provenance.** Creating a revision and reusing a document into another revision of the same project copy `accepted_classification_prediction_id` together with `document_type`, `document_number`, `description`, and `notes`. A reuse that overrides `document_type` is a manual selection and clears the prediction id. Previous revisions stay unchanged.

20. **`PROVIDER_TIMEOUT` and `CLASSIFICATION_TASK_TIMEOUT` are different failures.** `AI_CLASSIFICATION_TIMEOUT_SECONDS` bounds one provider invocation, OpenAI or fake, and that failure is `PROVIDER_TIMEOUT`. `AI_CLASSIFICATION_TASK_SOFT_TIME_LIMIT_SECONDS` bounds the whole Celery task. `SoftTimeLimitExceeded` is `CLASSIFICATION_TASK_TIMEOUT`. The hard limit is higher than the soft limit by enough time for the worker to commit `FAILED`. A single slow page batch and a long document that exhausts the worker allowance need different remediation, so the codes stay distinct. There is no stale-`RUNNING` sweeper in this phase.

## Consequences

**Positive**

- Inherited and reused documents do not spend another classification on the same file and the same classifier identity.
- An engineer can see a suggestion, accept it, or keep a different type, and the provenance of that choice survives a new revision.
- A failed reclassify does not erase the last completed suggestion.
- A later cost analysis can use the stored token counts without this phase inventing prices.

**Negative / follow-up**

- `extraction-worker` today only heartbeats. It will need PostgreSQL, object storage, the classification package, and the OpenAI SDK, and it must listen only on `document_classification`.
- The API and `document-worker` must be able to enqueue that work without importing the extraction worker or holding `OPENAI_API_KEY`.
- A worker killed without the soft time limit can leave a classification run `RUNNING`. `ensure` returns it. Backfill does not adopt it. This matches the existing Phase 3 processing-run debt.
- Page classification is all-or-nothing for a run. A failed batch fails the run, and retry repeats the work.

## Not decided here

The delivery plan's open decisions stay open until the PR that needs them: where the Celery publish helper lives, the numeric timeout defaults, the HTTP status for a disabled classification route and for page predictions before completion, the backfill and evaluation command names, worker concurrency, whether upload responses include the classification summary, and whether the SQLAlchemy mappings live next to the Phase 3 models. Proposed defaults are in [PHASE4_PR_PLAN.md](../docs/PHASE4_PR_PLAN.md). None of them are implemented.
