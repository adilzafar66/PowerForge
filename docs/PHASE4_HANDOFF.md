# Phase 4 handoff

Close-out for AI document classification. Specification: `cursor/phase4_specs.txt` §69. Decision: [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Accepted 2026-10-12). Delivery: [PHASE4_PR_PLAN.md](PHASE4_PR_PLAN.md).

This records checks that were executed on 2026-10-12. The revision documents workspace was not clicked through in a browser. The clean-stack scenario was driven through the HTTP API on the running Compose stack.

## A. Schema and migration

Alembic head is `0006_document_classification`. It adds `MIXED_DOCUMENT` to the document classification enum and creates `document_classification_runs`, `classification_predictions`, and `classification_ai_calls`. `revision_documents.accepted_classification_prediction_id` records an accepted document prediction.

A throwaway database upgraded only to `0005_document_processing`, given one completed processing run, then upgraded to head, gained those three tables. The upgrade left the completed processing run in place.

## B. Taxonomy

`document-taxonomy-v2` adds `MIXED_DOCUMENT` to the Phase 2 vocabulary. `UNKNOWN` means there is not enough evidence. `OTHER` means the document is understood and no defined class fits. `MIXED_DOCUMENT` is a document class. Page predictions cannot use it.

## C. Provider abstraction

`ClassificationProvider` exposes `classify_document` and `classify_pages`. Domain code does not import the OpenAI SDK. `FakeClassificationProvider` is filename-driven and is what tests and Compose use. The OpenAI adapter is `extraction_worker.openai_classification.OpenAIClassificationProvider`. The evaluation command loads that adapter, and the page renderer, with `importlib` only when `--provider openai` needs them.

## D. OpenAI adapter

The adapter uses the Responses API with structured outputs, `store=false`, image detail `low`, and reasoning `none`. The configured model is `gpt-6-luna`. Tests mock the SDK. No live call was made in this close-out.

## E. Versions

- Taxonomy: `document-taxonomy-v2`
- Sampling profile: `classification-default-v1`
- Prompts: `document_classifier_v1` and `page_classifier_v1`
- Provider and model are stored on each run. Image detail is part of the profile hash. Reasoning effort is not.

## F. Sampling

Document images use 5 pages. Document text uses 20 pages. Each excerpt is capped at 2000 characters. Selection is an integer linspace that includes the first and last page when more than one page is sampled. A page with no native-text artifact contributes an empty excerpt. A missing thumbnail on a page in the completed run fails the classification as `ARTIFACT_UNAVAILABLE`.

## G. Document and page classification

Every run classifies the document first. Page classification runs when the prediction is `MIXED_DOCUMENT` or `UNKNOWN`, or when the score is below 0.85. Pages are sent in batches of 8. Bands are `HIGH` at 0.85 and above, `MEDIUM` at 0.60 and above, and `LOW` below that. The model does not return a band.

## H. Runs, idempotency, and retry

A run cites one completed processing run and one classifier identity. One `PENDING` or `RUNNING` run is allowed for that identity. `COMPLETED` is not in that unique index, so reclassify can store a second completed run. Retry is allowed only for the newest `FAILED` run and inserts a new run with `retry_of_run_id`. `ensure` and backfill do not retry a failure.

## I. Trigger and backfill

When classification is enabled, `document-worker` calls `ensure` after a processing run reaches `COMPLETED`. A processing failure does not enqueue classification. An enqueue failure leaves the processing run completed. `powerforge-backfill-classification --limit N` selects documents `ensure` would enqueue. It does not run on API startup. The console script is not installed in this checkout's `.venv`; the close-out called `powerforge_document_classification.backfill.main(["--limit", "1"])`.

## J. Acceptance and provenance

Accept is the only writer of `document_type` from a prediction, and it stores `accepted_classification_prediction_id`. A manual type submission clears that id, including when the submitted type equals the stored type. Inheritance and reuse copy the id. A reuse that supplies `document_type` clears it. A failed or in-flight reclassify leaves the latest completed suggestion visible.

## K. APIs

List, detail, and upload responses include `classification` (`enabled`, `suggestion`, `attempt`). Routes under the revision document:

| Method | Path | Result |
| --- | --- | --- |
| `GET` | `/classification` | Suggestion and attempt. Does not start a run |
| `GET` | `/classification/runs` | History without prompts, text, images, or storage keys |
| `GET` | `/classification/pages` | Page predictions. 409 `classification_not_complete` when there is no completed suggestion |
| `POST` | `/classification/reclassify` | New pending attempt. 409 `ai_classification_disabled` when classification is off |
| `POST` | `/classification/runs/{runId}/retry` | New run for the newest failed attempt |
| `POST` | `/classification/predictions/{predictionId}/accept` | Sets the confirmed type |

## L. Frontend

The revision documents workspace shows Confirmed Type and AI Suggestion from the list payload. Accept, Choose another type, Use AI Suggestion, and Keep Current follow the existing mutation rules. Keep Current writes nothing. Retry and Reclassify stay available when the revision is read-only, and they stay hidden when classification is disabled. A `MIXED_DOCUMENT` suggestion can open its page predictions. Those rows are read-only. The workspace was covered by the Vitest suite. It was not clicked in a browser during this close-out.

## M. Telemetry

`classification_ai_calls` stores input tokens, cached input tokens, output tokens, and latency. It does not store prompts, images, document text, or a dollar cost. There is no `estimated_cost_usd` column.

## N. Evaluation

`powerforge-eval-classification` scores a labeled manifest. The fake provider reads the filename and sends no image bytes. `--provider openai` is the only live path and is not invoked by CI. Example fixtures live in `evals/classification/`. `evals/classification/private/` is gitignored. The console script is not installed in `.venv`.

## O. Queues and workers

Compose sets `AI_CLASSIFICATION_ENABLED=true` and `AI_PROVIDER=fake` on `extraction-worker`, and enables classification on the API and `document-worker`. `document-worker` listens on `document_processing`. `extraction-worker` listens on `document_classification` at concurrency 1. `validation-worker` listens on `celery` and registers only its heartbeat. On the clean stack, `document-worker` logs contained no `classify_run` task.

`OPENAI_API_KEY` is substituted only into `extraction-worker`. The API, `document-worker`, and `validation-worker` do not receive it. The Settings default for classification remains off.

## P. Checks executed

| Command | Result |
| --- | --- |
| `ruff check .` | Passed |
| `pytest` (integration skipped) | 293 passed, 351 skipped |
| `DATABASE_URL=.../powerforge_pr09 alembic upgrade head`, then `RUN_INTEGRATION=1 pytest` | 644 passed. Database dropped |
| Throwaway `powerforge_pr09_0005`: upgrade to `0005_document_processing`, insert one completed processing run, upgrade to head, then `backfill.main(["--limit", "1"])` with classification enabled | Tables `document_classification_runs`, `classification_predictions`, and `classification_ai_calls` present. One classification run inserted. Database dropped |
| `apps/web`: `npm run lint && npm test && npx tsc --noEmit && npm run build` | Lint clean. 190 tests passed. Typecheck clean. Build succeeded |
| `docker compose down -v && docker compose up --build -d` | Exit 0. Compose `powerforge` database at `0006_document_classification` |
| Clean-stack HTTP scenario, `AI_PROVIDER=fake` | A PDF upload reached processing `COMPLETED` with suggestion `SINGLE_LINE_DIAGRAM` / `HIGH` while the confirmed type stayed `UNKNOWN`. Accept set the confirmed type to `SINGLE_LINE_DIAGRAM`. Child revision `1` inherited the same document and still had one classification run. Reclassify left two runs and the confirmed type unchanged. `fail-packet.pdf` failed with `PROVIDER_UNAVAILABLE`. Retry created a new run that failed the same way, and the confirmed type stayed `UNKNOWN`. The signed download URL returned the PDF. The same URL without the query string returned 403 |
| Worker logs after that scenario | `document-worker` queue `document_processing` only. `extraction-worker` queue `document_classification` only. `validation-worker` queue `celery` only |

Disabled classification was not toggled on the Compose stack. The API integration tests in the 644-passed run cover the disabled routes.

## Q. Live OpenAI

Not run. `OPENAI_API_KEY` was absent from the environment and from `.env`.

## R. Deviations

- The evaluation command loads the renderer and the OpenAI adapter by module name. A static import failed `test_classification_packages_do_not_import_frameworks_or_openai`.
- One assertion was added: a page with no native-text artifact contributes an empty excerpt.
- The PR-08 acceptance line cites decision D8 for the evaluation command name. The settled name is decision D5. D8 is the upload-response summary.
- The clean-stack scenario was the HTTP API. The workspace was not exercised in a browser.

## S. Debt

A worker killed without the soft time limit can leave a classification run `RUNNING`. `ensure` returns it. Backfill does not adopt it. Page classification is all-or-nothing: a failed batch fails the run, and retry repeats the work. Both are recorded in [PROJECT_STATUS.md](PROJECT_STATUS.md).

## T. Out of scope, confirmed absent

The Phase 4 diff from `1ec0c71` (Phase 3 close) through this branch has no OCR, equipment extraction, table extraction, single-line topology, embeddings, RAG, cost fields, or ETAP/SKM/EasyPower implementation. Phase 5 is not started.

## U. Suggested commit message

```
Close Phase 4 after the classification audit and clean-stack check.

ADR-006 is accepted, and the docs now describe classification as complete.
```
