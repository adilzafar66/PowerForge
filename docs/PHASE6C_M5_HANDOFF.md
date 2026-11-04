# Phase 6C M5 handoff — Production OpenAI adapter and profiles

Branch: `codex/phase-6c-engineering-extraction`. Baseline: `002ed35f5aaf3e64ec715f819ce79b7921799f95` (M4). Latest `origin/main` was refreshed and is already an ancestor. Scope: M5 of [PHASE6C_PLAN.md](PHASE6C_PLAN.md). M6 corpus/evaluation and the final Phase 6C handoff remain pending. No live model quality or account access is claimed.

## Production path

The existing manual extraction API now resolves and advertises two production profiles:

- `engineering-openai-v1`: pins native text and analysis image when present; supports image-only pages.
- `engineering-openai-text-v1`: requires and pins native text, excluding image inputs.

Both identify `ENGINEERING_EXTRACTION` / `openai` and set discovery's `production_extractor=true`. This identifies the extractor, not measured accuracy or engineer verification. Both remain disabled by default. Set `EXTRACTION_ENABLED=true` and `EXTRACTION_EXTERNAL_ENABLED=true` in the API and worker to permit an explicit selection. Keep `OPENAI_API_KEY` in the worker environment. Discovery's enabled flag reflects configured controls, not verified credentials/account/model availability. The default manual profile remains `infrastructure-fake-v1`; existing infrastructure profiles remain available and explicitly non-production.

No new routes or canonical writes were added. INCLUDED revision-document membership, inherited/read-only document access, pagination, effective-unit filtering, exact typed values and evidence signing use the existing services. Run details expose the production execution kind and actual call/usage counts. Candidates remain read-only AI proposals with the existing grounding/association limitations, including page-level visual grounding; they never become verified model values.

Planning, dispatch, claim, dependency settlement, retry, cancellation, lease/recovery and publication are the unchanged M4 coordinator/execution algorithms. Each page still has recognition followed by attributes, each admitted attempt allows at most one provider call, and committed recognition is reused across attribute retries. Empty recognition still releases standalone extraction. Original selected modalities/artifacts never fall back to current metadata, another source representation or a later processing run.

## SDK adapter and input contract

`extraction_worker.openai_extraction.OpenAIExtractionProvider` now accepts a production profile from the normal worker provider factory. It consumes the trusted request's selected M1 response class, instructions, stage, named source roles and upstream context. It checks profile/schema/model/limit consistency before invoking the SDK. Unversioned engineering requests cannot silently use the legacy probe adapter.

The adapter makes one `client.responses.parse()` call with the selected Pydantic `text_format`, explicit model, timeout, output cap and reasoning effort. The client is constructed with `max_retries=0`; persisted attempts own retry. Calls use `store=false`, enable no tools and create no conversation/previous-response/background state. Analysis images are supplied as private PNG data URLs, not signed storage URLs. The selected stage response is revalidated by the adapter and again by M4 before M3 conversion and fenced 6A publication.

`prompts/openai_input_v1.json` owns the versioned source/upstream envelope labels. Native text is JSON-escaped in an explicitly untrusted user input with `source_ref=native_text`. The image has its own `source_ref=analysis_image` label and explicit page-level transcription limitation. The upstream projection occupies a separate untrusted user input and contains only the M4 response-local allowlist; it is never appended to trusted instructions. No artifact/group/database IDs or storage keys are supplied to the model. Source-embedded instructions cannot escape the JSON string or alter the supplied trusted instructions/tools; representative adversarial evaluation remains M6 work.

Refusal, incomplete output, schema/JSON validation failures, token overrun and provider failures flow through existing safe categories. Errors do not persist SDK messages, credentials, raw prompts or images in telemetry/logs. Returned valid usage is retained, including cached-input counts; missing/inconsistent usage remains unknown or fails validation. A parsing/transport exception raised inside the SDK may not expose its response usage; that uncertainty is retained rather than fabricated as zero. There are no repair calls or hidden provider retries.

The installed SDK tested here is **OpenAI Python 3.29.0**. Its actual strict-schema serialization and Pydantic response parsing run over `httpx.MockTransport` in tests. The implementation follows the official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) and [image-input guide](https://developers.openai.com/api/docs/guides/images-vision?api-mode=responses). The repository's existing default model remains `gpt-6-luna`; its documented capabilities/effort options were checked against the [official model page](https://developers.openai.com/api/docs/models/gpt-6-luna). No live call, account entitlement, current pricing or model accuracy was verified, and no model migration was performed.

## Versioned profiles and historical compatibility

Production uses `execution-profile-v3`, `engineering-page-runtime-v2` and `openai-engineering-responses-v1`. It pins the complete unchanged M1 manifest, M2 interpretation and M3 grounding identities, runtime source identity, provider input-contract hash, model/effort/image detail, source strategy, context/resource limits, retry/admission/concurrency/timeout limits and any configured pricing basis. The configuration remains below the existing 64 KB limit. `engineering_production_v1_identity.json` captures exact wire JSON/profile hashes against explicit fixture settings, independently of environment defaults.

Accepted v1 infrastructure and v2 synthetic profile serialization/hashes remain byte-identical. M4's runtime fingerprint covered the whole profiles and stage-runtime source files; registering a new reader would otherwise invalidate old active synthetic runs. Their two original identity/reader sources are therefore retained byte-for-byte under `runtime_resources/page_v1/`. The v1 identity reader uses these retained sources plus the unchanged shared execution/orchestration/dependency files. The old versioned rendering/validation paths remain supported; v2 identities use the current files and new production resources. M4's frozen identity fixture is unchanged and still passes. The archive files are identity resources, never dynamically executed/imported code.

`read_profile()` dispatches explicitly among wire versions 1, 2 and 3. Unknown versions/resources fail without substituting current behavior. Production resources have their own fingerprint and transport version. After deployment, changing shared algorithms, schemas or transport semantics requires retained compatible versioned resources/readers or an explicit unsupported-resource failure; do not relabel changed behavior with an old fingerprint. Preserve the archived M4 sources and the M1/M2/M3 fixtures.

## Limits and configuration

`.env.example` records the new production controls. Common extraction settings still pin pages (50 by default), per-artifact bytes (2,000,000), image pixels (20 million), attempts, call budget, concurrency, timeout/lease and backoff. Production additionally pins:

- `EXTRACTION_ENGINEERING_MAX_OUTPUT_TOKENS=16384` (probe default remains 1024).
- `EXTRACTION_ENGINEERING_MAX_TOTAL_INPUT_BYTES=4194304` (4 MiB across selected page inputs).
- `EXTRACTION_ENGINEERING_MAX_TEXT_CHARS=100000` (actual decoded codepoints).
- `EXTRACTION_ENGINEERING_MAX_UPSTREAM_BYTES=65536`.
- `EXTRACTION_ENGINEERING_IMAGE_DETAIL=high`.
- `EXTRACTION_ENGINEERING_REASONING_EFFORT=none`.

Trusted rendered instructions retain their versioned 128 KiB cap. Requests are bounded without silent clipping; response capacity/overflow/incomplete output is a failure, not partial publication or an engineering completeness result. Changing a material production setting changes the profile identity; changing the probe output cap does not change production output limits. Select a model/effort/detail combination supported by the chosen provider; unsupported combinations fail safely rather than changing the requested model automatically. Pricing remains unknown unless the existing explicit reviewed basis/rates are configured; no live pricing table was added.

## Verification

**1,445 backend tests passed, no skips**, including **32 new M5 cases**, with six existing dependency warnings in **231.07 seconds**. This includes every earlier registry/canonical/extraction/storage/worker and data-preserving migration regression. The focused SDK/profile/legacy orchestration suite passed 57 cases; the five new real worker/beat cases passed, including automatic/manual retry and process restart. The final full run includes the drawn image fixture and all final production settings/identity checks.

Extraction, shared settings and worker wheels build and import directly from their archives. Exact v1/v2 historical and v3 production wire/runtime identities reproduce from the wheels, including packaged retained sources and the provider input resource. Production runtime rules hash: `87ef969ca1f3194ee4568a56b2dd43f15701593a481e48e64b549fca04944775`. Ruff, changed-file formatting, dependency and whitespace checks pass. Resolved Compose configuration confirms all six new production settings reach API, worker and scheduler consistently, while API keys remain worker-only. No frontend/browser test, live model call, model-account access check or production accuracy evaluation was performed.

The new integration bootstrap is test-only and not packaged. It exports the actual Celery app/tasks and replaces only OpenAI's HTTP transport before client construction, with a required fixture credential and no socket-capable SDK fallback. PostgreSQL, Redis, MinIO, worker processes and beat are real. Audit files contain safe request identities/hashes and limits, not source dumps. Tests cover hybrid/text/image publication through API reads/signing, automatic retry after one 503, manual attribute retry after malformed output, and worker kill/restart after recognition commits. Rendering/source/upstream hashes remain identical across attribute retries, with exactly one recognition request. Interrupted calls retain unreported usage.

The image-only integration fixture contains a drawn transformer label; its model observation is scripted, not recognized by a live model. Those tests verify wiring/grounding markers and cannot establish visual recognition precision. All production-shaped outputs are from synthetic fixtures and mocked SDK transport. No paid call or live extraction accuracy measurement was performed.

Disposable project `powerforge-phase6c-m5` uses tmpfs PostgreSQL `powerforge_phase6c_m5` on 55440, Redis 56390 and MinIO 59010. Normal development services/data are untouched. Fresh migration to head 0013 succeeds without new migrations; the full suite retains prior data-preserving migration/worker regressions. Disposable services and generated build directories are removed after verification.

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:55440/powerforge_phase6c_m5 \
S3_ENDPOINT_URL=http://localhost:59010 S3_PUBLIC_ENDPOINT_URL=http://localhost:59010 \
REDIS_URL=redis://localhost:56390/0 RUN_INTEGRATION=1 \
.venv/bin/pytest -q --tb=short
```

## Next: M6

Add the independently specified representative corpus and repeatable evaluator, with denominators/matching rules for recognition, mapping, values/units, grounding, false candidates and unmapped retention. Distinguish deterministic/mock correctness from actual model quality. Any live evaluation requires separately authorized fixtures/provider access. Publish the final Phase 6C handoff only with actual outcomes and remaining limitations; M5 alone does not complete Phase 6C. Tables/OCR/layout, cross-document identity, reconciliation, UI and engineer acceptance remain later phases.
