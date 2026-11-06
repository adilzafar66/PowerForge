# Phase 6E M2 — Native extraction, real OCR and durable source preparation

**Status:** implemented for review, 2026-11-06 (America/Vancouver), on `codex/phase-6e-ocr-layout` after M1 commit `a77d56a`. Authority: [approved plan](PHASE6E_PLAN.md), [prompt](prompts/phase-6e-prompt.md), [M1 handoff](PHASE6E_M1_HANDOFF.md). **Stop before M3.** M2 produces independently owned source readings; it does not establish table relationships, fuse native/OCR readings, publish engineering candidates or register enhanced OpenAI profiles. M3–M5 remain pending.

## Delivered implementation

`powerforge_document_processing.native_spatial` uses the existing PyMuPDF parser, pinned to **1.28.2**. It consumes the exact original PDF, preserves unsorted character/span traversal, emits separate word occurrences with boxes and line/block membership/direction, retains supported native line/rectangle primitives, and observes embedded image rectangles. Crop-relative unrotated source frames and explicit quarter-turn transforms resolve to the visible upright page. Unsupported/clipped token boxes remain null with a reason. Curves and unsupported drawing paths supply no invented geometry. Neither PDF traversal order nor a primitive envelope establishes a table or visual reading order. Table detection/admission remains M3.

`extraction_worker.tesseract.TesseractProvider` implements the M1 positioned OCR protocol with a real **Tesseract 5** subprocess and strict TSV parsing. English LSTM, OEM 1, PSM 6 and one OpenMP thread are fixed; no whitelist, spelling/number repair, segmentation search or alternate engine is added. Raw words, hierarchy, pixel boxes, engine ordering and optional 0–100 engine confidence survive unchanged. Negative/unknown confidence becomes null; it is not an engineering probability. Malformed/off-image/oversized output, invalid images and unavailable engine/data fail with safe categories. Recognition has a 60-second deadline, bounded output/stderr and a private temporary directory. Timeout/failure terminates the owned process group.

The actual adapter identity binds its source bytes, executable and version/build output; settings bind the actual language-data hash and material options. The worker rechecks the configured binary/data before each recognition request. Configuration/readiness does not prove that recognition occurred. No OpenAI credentials or external OCR service is involved.

The new `source-preparation-v1` profile has a distinct `source-preparation-profile-v1` wire format and `SOURCE_ENRICHMENT` purpose. Planning/output adapters reuse the existing `ExtractionCoordinator`, controls, append-only attempts, durable delivery, advisory admission lock, heartbeats, deadlines, bounded retries, aggregation, cancellation and recovery. There is no second scheduler/state machine. Local work is delivered to `source_enrichment`; ordinary extraction tasks cannot claim it, and local tasks cannot claim extraction units. CPU/model concurrency pools are separate. The coordinator's default dispatch remains extraction-only; production dispatch explicitly covers both purposes. An enabled enrichment scheduler also delivers recovery on the CPU queue so recovery can operate without a model worker.

Migration **0014_source_enrichment** adds immutable purpose and independent `SourceEnrichmentPageResult`, `SourceEnrichmentArtifact` and `RunSourceEnrichmentBinding` records. Existing rows default to EXTRACTION. Local run model/prompt/registry metadata is null, with purpose-aware checks; it never pretends to be an LLM invocation or a registry extraction. Existing extraction metadata remains required. Successful source artifacts/results require the authorized running local lease, exact unit/page/original/base-artifact ownership, canonical manifest hash, descriptor agreement and terminal success in the same transaction. Successful source history is immutable. Local jobs cannot publish ordinary candidates/tables/evidence or AI-call rows. The binding table establishes an immutable successful-source reference boundary; downstream extraction binding/publication is M4 work.

`enrichment_prepare`, `enrichment_execution` and `enrichment_service` verify supplied original/base bytes and emit authoritative text plus positioned JSON objects with distinct native/OCR identities. Publication independently rechecks the admitted source/configuration, canonical manifest, exact object set, checksums and token spans. Storage writes use new no-overwrite keys before the fenced DB transaction. Failed/stale transactions may leave safe unreferenced objects; no object cleanup/rewrite of historical sources is performed. Base processing runs, artifacts and mutable page metadata are not updated. Legacy Phase 3 offsets remain unproven without an original emission witness; consumers must use the new representation or null legacy offsets.

## Eligibility, coverage and limits

**Hybrid PDFs may need explicit OCR selection.** A page can contain a readable native title or annotation while its equipment schedule is an embedded scan. The initial automatic policy can prepare the native text and leave that scanned schedule unread. A `COMPLETED` preparation run means the selected policy finished; it does **not** mean every part of the page was read.

The implemented v1 policy uses observable facts:

- Explicitly selected pages receive one whole-page OCR invocation.
- Image pages and PDFs with no native readings receive OCR.
- A native representation with at least 1% literal replacement characters receives OCR; the numerator and denominator come from that representation.
- Native readings with any observed embedded image yield `EXPLICIT_SELECTION_REQUIRED` and `UNKNOWN_RASTER_CONTENT_EXPLICIT_SELECTION_REQUIRED`, unless explicitly selected for OCR. An image rectangle does not reveal whether its content is text or measure text coverage.
- Native readings without observed raster images skip automatic OCR. Sparse native annotations alone do not force it. A significant vector/unknown-content page can be explicitly selected.

Text coverage remains **UNKNOWN**. The proposed raster-area/text-coverage thresholds are not used. Logos/backgrounds and full native text over raster images are not automatically OCR'd; native titles over scanned schedules remain explicitly unresolved rather than being declared adequately covered. This initial policy trades automatic hybrid recall for observable decisions. Representative eligibility/layout/recognition evaluation remains M3/M5 work.

When a successful page result reports `ocr_decision=EXPLICIT_SELECTION_REQUIRED` and `ocr_reason=UNKNOWN_RASTER_CONTENT_EXPLICIT_SELECTION_REQUIRED`, inspect the page. If it contains a scanned schedule or other text that needs recognition, explicitly include its page number in `force_ocr_pages`. For example, to recognize page 3, submit `POST /source-enrichment/runs` under the document-scoped prefix below, replacing the processing-run placeholder with the completed run's UUID:

```json
{
  "processing_run_id": "<completed-processing-run-id>",
  "pages": [3],
  "force_ocr_pages": [3],
  "mode": "ensure"
}
```

This requests whole-page OCR, including the embedded scan, while retaining native and OCR readings separately. The explicit selection creates a different preparation target; an earlier completed result remains unchanged. Repeating the original request or retrying it with unchanged selections does not turn OCR on. Recognition errors can still occur, and text coverage remains UNKNOWN after OCR.

This release supports explicit whole-page OCR, not operator crops. It performs at most **one recognition per page/attempt**, with no fallback loops. Selected pages are explicit, distinct, ascending and capped at 50. Original bytes are capped at 250 MiB (or the lower configured extraction document limit); image raster size at 20 million pixels/32 MiB. PDFs rasterize at up to 300 DPI, downscaled to the cap with the exact upright frame retained. Image originals use the pinned upright Phase 3 analysis PNG, including TIFF frame orientation. No missing detail is invented by upscaling.

M1's aggregate text/token/line/block/primitive/JSON limits still apply without truncation. Preparation attempts have a 120-second family deadline plus the existing 15-second lease fence allowance; Celery limits are 135/150 seconds. Retry/admission caps are at most three attempts and 150 admissions per run. Per-run CPU concurrency is one; initial global CPU admission is one. The Compose CPU worker has one CPU, 1 GiB memory, 64 process slots and a 128 MiB scratch tmpfs. The observed **acceptance-container lifetime memory peak was 561,008,640 bytes** under a 1,073,741,824-byte cap; this includes test/dependency/worker subprocess work and is not a per-page OCR memory estimate.

Transient source access, OCR timeout/interruption and abandoned worker leases use bounded retries. Missing/corrupt objects, invalid readings and unavailable configured engine/data fail explicitly. Completed siblings survive partial failure and are not recognized again by retry. Cancellation fences publication; it does not claim to undo a recognition already in flight. A subsequent deliberate re-extraction creates new history. Exact completed `ensure` requests reuse existing results.

Usage distinguishes run **admissions**, **OCR requests started**, and **confirmed OCR invocations on committed results**. A request marker is persisted before entering recognition. Failed/interrupted requests may have unknown actual engine use; they are not silently counted as zero completed engine calls. Successful results report observed local OCR elapsed time, Python-process CPU time separately, bytes/pixels and actual confirmed invocations. Unmeasured child CPU/peak memory and operating cost remain null. There are no fabricated AI tokens, prices or AI-call records.

## APIs and workflow

The revision-document-scoped prefix is:

```text
/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/source-enrichment
```

It provides:

- `GET /profiles`: configured capability and explicit recognition/coverage limits.
- `GET /inputs`: read-only completed processing-run IDs and available pages, with pagination.
- `POST /runs`: explicit `processing_run_id`, `pages`, optional `force_ocr_pages`, `profile_key=source-preparation-v1` and `mode=ensure|reextract`.
- `GET /runs`, `GET /runs/{run_id}`: separate source history, attempts, successful results and local usage.
- `GET /runs/{run_id}/results/{result_id}`: exact successful manifest/identity.
- `GET /runs/{run_id}/artifacts/{artifact_id}`: successful selected artifact checksum/size and short-lived signed access, after checking its exact stored bytes.
- `POST /runs/{run_id}/retry` and `/cancel`: purpose-checked shared lifecycle mutations.

Every path enforces current included-document/project membership. Reciprocal tests use opposite-purpose IDs on the same document for run detail, candidates, tables, result/artifact reads, retry and cancellation; rejection has no signing, queue, admission or state side effects. Inherited and superseded revision access remains supported while removal revokes access. Extraction summaries/history ignore enrichment runs, and existing extraction results remain accessible. Run ancestry cannot cross purposes.

A backend caller discovers a completed processing run using `/inputs`, explicitly requests preparation, polls its source run and retrieves successful page manifests/artifacts. Enhanced extraction still requires a separate future supported M4 request. These separate backend operations must support the coherent guided 6F document/OpenAI workflow approved in the plan; M2 adds no UI or unrelated-page navigation requirement.

## Deployment and reproducibility

`docker-compose.yml` adds `source-enrichment-worker` to the existing extraction-worker package, with classification/external processing disabled and no API key. It uses the existing broker and scheduler. The shared worker Dockerfile has an explicit OCR build option and pins Debian bookworm packages **tesseract-ocr 5.3.0-2** and **tesseract-ocr-eng 1:4.1.0-2**. The tested engine reports **Tesseract 5.3.0 / Leptonica 1.82.0**. PyMuPDF 1.28.2 prevents an unintended parser major-version/learned-layout dependency change.

Pydantic is pinned to **2.13.5**, the version used by the accepted contracts. A newer container install changed Decimal JSON-schema fingerprints; the dependency was aligned instead of changing accepted fixtures. The final image reproduces M1's exact identities and contains no `pymupdf-layout`/`pymupdf4llm` package. CI installs a real local OCR binary/data; engine tests never hide missing capability with skips. The pinned Compose image remains the reproducible deployment gate, while CI records its actual engine identity.

Build and inspect the worker, then configure the API, CPU worker and scheduler with the same deployment identity:

```sh
docker compose build api source-enrichment-worker extraction-scheduler
docker compose run --rm source-enrichment-worker python -m extraction_worker.tesseract
```

Put that command's JSON output in `ENRICHMENT_OCR_CONFIGURATION` and explicitly set `ENRICHMENT_ENABLED=true` in the relevant deployment environments. No actual `.env`, existing development database or running application worker was changed by this implementation. The default remains disabled. A different architecture, binary, language data or adapter source requires its own actual identity; do not copy the recorded ARM64 build label and claim another deployment matches it.

The tested Linux/ARM64 English data digest is `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. The complete actual engine/configuration record, preparation policy/schema hashes and retained-file digests are in `tests/fixtures/enrichment/preparation_v1_environment.json`. This is an environment record, **not OCR accuracy gold**. The profile pins material engine/data/parser/contracts/rules and all execution caps. Before changing accepted M2 preparation sources in later milestones, preserve their identity inputs or add a new version; layout upgrades must not silently invalidate or relabel completed preparation.

## Historical compatibility and actual checks

Before shared edits, 15 accepted extraction source/resource inputs were preserved under packaged `runtime_resources/table_v1`. They are data, never dynamically executed. The accepted v4 runtime reader hashes those retained inputs; v1–v3 retained identities and frozen 6C/6D grounding/interpretation/prompts/evaluators/corpora/reports remain unchanged. M1's accepted source pinning now resolves changed shared files to those exact retained bytes. No accepted fixture was refreshed. Historical migration tests explicitly use their historical run mappings rather than attempting to insert M2 columns into an old schema.

**271 distinct targeted tests pass with no skips:** the combined gate passed **268 tests in 77.60 seconds**, followed by **three new resource/profile/import checks in 0.42 seconds** in the pinned container. The ten native cases were also rechecked against independently authored crop-origin coordinates/frame sizes (0.37 seconds). This includes **51 new M2 tests**. Coverage includes real native crop/rotation/column-major repeated occurrences, real PNG/TIFF OCR and hybrid rasterization, raw uncertain notation, malformed/off-image/confidence/overflow failures, corrupt PNG, engine/data mismatch and missing capability, timeout termination, immutable objects/manifests, publication mutation controls, source checksums, actual PostgreSQL/MinIO/Redis/Celery delivery, duplicate/concurrent ensure/claim, partial success and retry, worker kill/restart, stale/cancel fences, independent CPU/model pools, local output/AI-call rejection, reciprocal endpoint purpose guards, summary/history isolation, membership/inheritance, read-only source discovery, fresh/0013 upgrade/downgrade and accepted extraction claim/retry/publish/read regressions.

The authored high-resolution scan was actually read as `TX-1`, `750 kVA`, `13.8 kV`, `400 AF / 250 AT` and `4/0 AWG`. This demonstrates a functional local path, not production recognition accuracy. The deliberately uncertain `75O` TSV control remains `75O`; the application does not normalize it into `750`. No generated expected value was copied from the engine to make a test pass.

Five affected package wheels build. A fresh direct-wheel process imports the new OCR/native/preparation modules, runs the accepted positioned PDF through the real native adapter, reproduces M1 fixtures/resource/schema identities and accepted v1–v4 wires/resources, and exactly replays both frozen 6C/6D reports. The final worker image builds and reproduces those package versions/identities without external credentials. Ruff, changed-file formatting, dependency and whitespace checks pass. The broader final backend/evaluation gate remains M5; no full unrelated backend/frontend suite or paid provider call was performed for M2.

Verification logs/scripts were kept in temporary task files, not runtime dependencies. Disposable test databases, private scratch buckets, test workers/beat processes and the bounded acceptance container are cleaned up after verification. Existing application services/data are preserved.

**Stop for M2 review.** M3 must establish independently supported alignment/conflict/layout relationships and compatible preparation reuse. M4 must add enhanced extraction/evidence consumers and every corresponding purpose/ownership guard. M5 must independently evaluate recognition/layout and perform the final regression. Functional source preparation alone does not complete Phase 6E.

## M2 review — Lazy OCR provider startup

`execute_preparation()` now passes a factory to `prepare_page()`, which initializes the provider only after eligibility selects OCR. Native-only pages skip executable/data discovery and hashing. The current profile still requires configured OCR identity/settings; this correction does not add a separate native-only profile or weaken validation for OCR-selected pages.

Before these helper edits, the four accepted preparation identity inputs from commit `12cf793` were retained as packaged data under `runtime_resources/preparation_v1`. The v1 identity reader uses those exact inputs, preserving the existing rules/profile identity and compatible successful/active runs. The archives are never executed. Future material preparation changes require a successor version or explicit compatible retained-runtime strategy; do not edit the retained inputs.

Review verification: **30 focused execution/resource/real-worker tests pass with no skips in 21.99 seconds**, including two added regressions. A native-only page completes even when its provider factory would raise `OCR_ENGINE_UNAVAILABLE`; an explicitly OCR-selected page invokes that factory and retains the safe failure with no false OCR-request marker. Existing actual OCR, publication, retry and Celery/MinIO recovery cases also pass. The extraction wheel contains all four retained inputs and reproduces the exact accepted rules hash. Lint, changed-file formatting and whitespace checks pass. No accepted fixture or profile identity was refreshed, no paid call ran, and M3 remains unstarted.
