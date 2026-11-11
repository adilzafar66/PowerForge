# Phase 6G M1 handoff

M1 is implemented for review on `codex/phase-6g-extraction-semantics`, based on `dea1ed3`. The [five-milestone plan](PHASE6G_PLAN.md) and [ADR-008 amendment](../decisions/ADR-008-evidence-candidate-extraction-architecture.md#phase-6g-interpretation-amendment) define the later AI-led semantics, evidence and retention changes. The M1 review is the gate for M2.

## Stage trace

Enriched Engineering and Tables attempts now record `extraction-stage-trace-v1` when they settle through the worker. The trace contains the available source binding and modality counts, a hash of the actual stage instructions, the schema version, the provider outcome, safe validation subtypes and paths, parsed observation counts, source admission and rejection counts, mapping outcomes, and committed candidate, table and evidence totals. Counts refer to the attempts and observations the stage processed. They cannot establish document completeness or printed-text accuracy.

Migration 0018 adds an append-only one-to-one table with an 8 KiB limit per trace. The worker writes it under the existing lease fence, in the same transaction as settlement and any published output. A publication rollback removes the tentative success trace and outputs. The later fenced failure settlement can record the failed publication boundary. Retries keep separate traces. Apply the migration before running the updated API and extraction workers. Downgrade to 0017 is supported while the trace table is empty.

The existing revision-document run detail route returns `attempts[].stage_trace`. The Documents evidence viewer shows it under **Run history → Attempts and source bindings**. Attempts predating 0018 have a null trace. Pending, dependency-blocked, cancelled and abruptly interrupted work can lack a settled trace and continues to use the existing attempt status, dependency reason and provider-start telemetry.

Provider failures still use the established execution error codes and retry rules. The trace distinguishes transport errors, HTTP faults, refusals, timeouts, malformed JSON, structured validation errors, missing fields, table graph and span problems, duplicate aliases, response overflow and observable truncation. If the SDK raises before yielding its parsed object, the adapter can inspect terminal status in the already-received bounded HTTP body without retaining or exporting the body. When the status is unavailable, the trace records the observed parse failure. The ordinary API and logs expose fixed reason codes and bounded sanitized validation paths. They exclude source text, images, storage keys, raw prompts, provider response bodies and SDK error messages.

## Representative outcomes

- **Synthetic split transformer rating.** The provider returned `kVA:` and `350` as a single observation with two native reading aliases. The current one-line grounder reported `CROSSES_SOURCE_LINES`. Attribute Extraction completed with one returned attribute and zero published candidates. The existing recognition mention remained mapped. This is the M1 diagnostic reproduction and the M2 grounding target.
- **Missing table response field.** The stubbed SDK response omitted `tables`. Run History shows `PARSE / MISSING_FIELD` with path `tables`. Table Interpretation remains prerequisite-blocked. The separate Engineering result remains accessible.
- **Unavailable spatial table alias.** A schema-valid reconstruction parsed one table, then failed at `GROUNDING / UNAVAILABLE_SPATIAL_TABLE_ALIAS`. A separate test injected failure after transactional table publication and verified rollback with a `PUBLICATION` trace and zero committed output. A valid empty reconstruction leaves Table Interpretation complete with `SKIPPED_EMPTY_PREREQUISITE` and no second provider call.

## Authorized local inspection

Use only in a disposable development process with direct authorized access to its database and source storage. Prepare the document and create a pending attempt using the normal workflow. Run that attempt in the same process with an injected stub provider or a separately authorized provider configuration. The capture takes no additional provider calls. For example, with the normal execution dependencies already configured:

```python
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.local_diagnostic_capture import LocalDiagnosticCapture

with LocalDiagnosticCapture(work_unit_id) as capture:
    execute_unit(work_unit_id, factory, storage, settings, provider_factory, capture=capture)
    inspection = capture.inspect()
    # Inspect this value in the local debugger. It can contain confidential source text.
```

The capture accepts one matching attempt and is process-local. It holds the exact structured source projection up to 128 KiB, the revalidated parsed response up to 1 MiB and up to 1,024 observation events. Events correlate observation aliases and proposed fields in the parsed response to final keys, reasons, reading and association bases, and IDs that are exposed only after commit. The capture expires for access after ten minutes and clears its references on context exit. Keep inspected values within the controlled process and discard any local references when finished. There is no API, production toggle or automatic export. Full provider bodies, image bytes, instructions, credentials and storage keys are excluded. Use sanitized fixtures for any shared bug report.

## Compatibility and open issues

- M1 preserves the separate execution families, registry-v1, prompt and response resources, conservative conversion, retry and publication behavior, and the Phase 6F wizard. The source-policy follow-up updated the affected v1 identity fixtures. Where diagnostics touch hashed code, the existing packaged-resource mechanism retains the accepted bytes for legacy hashes.
- The v1 source policy permits 5,096 native primitives per page. Baseline commit `dea1ed3` raised the limit from 2,048 under the existing v1 version. This changes the spatial contract identity, the preparation rules identity, and the positioned-text schema hash. The test fixtures pin the 5,096-limit identities. Preparation and layout attempts pinned to the earlier 2,048-limit identity can fail strict identity checks when executed or retried. Re-extraction admits a new run under the current policy.
- This milestone used synthetic sources and mocked providers. No live OpenAI call or original drawing was processed. The original REX reconstruction failure subcause remains unknown. The full OCR, MinIO and Celery matrix was outside this verification. Three older enriched integration cases could not start with the host's missing Tesseract installation. The new native-only integration checks assert that OCR does not run.

## Verification

- **Backend, local PostgreSQL:** 64 passed across the M1 scenarios, migrations 0016–0018, historical Tables, extraction and Phase 6F reads, orchestration and Engineering recovery. The four M1 stage and migration checks passed again after simplifying trace settlement. The 0017 → 0018 test preserved completed output byte-for-byte at the record level, executed a pending legacy probe with its original profile identity, and downgraded the empty trace table. The new extraction scenarios use actual native PDF preparation/layout, in-memory object storage and mocked providers.
- **Backend, no network provider:** 263 passed and two failed in the broader targeted suite. Both failures reproduced on the clean starting commit. The source-policy follow-up updated the affected v1 expectations and both identity checks now pass. The enhanced profile identities, legacy Engineering and Tables identities, registry and normalization checks passed. A real SDK instance with a mock HTTP transport accepted valid structured output and identified an output-token-limit response even when structured parsing failed first.
- **Frontend:** 355 Vitest checks passed. Chrome rendered the real Run History components with mocked API data at 1,440 and 390 px. All four browser checks passed for expanding an empty Engineering result and the failed Table Reconstruction with its schema path.
- Ruff, frontend ESLint, TypeScript, Python dependency checks and whitespace checks passed. The four added frozen archives match their accepted bytes.

**Recommendation:** Review the M1 implementation now. The v1 source-policy change carries the historical retry limitation documented above. M2 is at the approval gate.
