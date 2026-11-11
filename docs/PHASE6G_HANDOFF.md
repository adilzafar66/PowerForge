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
- The v1 source policy permits 5,096 native primitives per page. Baseline commit `dea1ed3` raised the limit from 2,048 under the existing v1 version. This changes the spatial contract identity, the preparation rules identity, and the positioned-text schema hash. The test fixtures pin the 5,096-limit identities. Preparation and layout attempts pinned to the earlier 2,048-limit identity can fail strict identity checks when executed or retried. Re-extraction admits a new run under the current policy. The manually approved increase of max_native_primitives from 2,048 to 5,096 is an explicit exception to historical source-processing identity compatibility. Existing extraction profile identities remain preserved, but preparation/layout attempts pinned to the former v1 source policy are not guaranteed to be replayable.
- This milestone used synthetic sources and mocked providers. No live OpenAI call or original drawing was processed. The original REX reconstruction failure subcause remains unknown. The full OCR, MinIO and Celery matrix was outside this verification. Three older enriched integration cases could not start with the host's missing Tesseract installation. The new native-only integration checks assert that OCR does not run.

## Verification

- **Backend, local PostgreSQL:** 64 passed across the M1 scenarios, migrations 0016–0018, historical Tables, extraction and Phase 6F reads, orchestration and Engineering recovery. The four M1 stage and migration checks passed again after simplifying trace settlement. The 0017 → 0018 test preserved completed output byte-for-byte at the record level, executed a pending legacy probe with its original profile identity, and downgraded the empty trace table. The new extraction scenarios use actual native PDF preparation/layout, in-memory object storage and mocked providers.
- **Backend, no network provider:** 263 passed and two failed in the broader targeted suite. Both failures reproduced on the clean starting commit. The source-policy follow-up updated the affected v1 expectations and both identity checks now pass. The enhanced profile identities, legacy Engineering and Tables identities, registry and normalization checks passed. A real SDK instance with a mock HTTP transport accepted valid structured output and identified an output-token-limit response even when structured parsing failed first.
- **Frontend:** 355 Vitest checks passed. Chrome rendered the real Run History components with mocked API data at 1,440 and 390 px. All four browser checks passed for expanding an empty Engineering result and the failed Table Reconstruction with its schema path.
- Ruff, frontend ESLint, TypeScript, Python dependency checks and whitespace checks passed. The four added frozen archives match their accepted bytes.

**Recommendation:** Review the M1 implementation now. The v1 source-policy change carries the historical retry limitation documented above. M2 is at the approval gate.

## M2 and M3 implementation

The successor profiles are `engineering-openai-enriched-v2` and `tables-openai-enriched-v2`. They have a distinct stage manifest, prompt, response identities and runtime hash. They use the existing v5/v6 persistence envelopes and exact source bindings. The registry, database schema and extraction navigation use their existing contracts. Existing enriched-v1 runs retain their original hashes, prompts and converters. Table Reconstruction retains its existing schema, prompt and publication checks. M4 covers reconstruction improvements.

The run API accepts either successor profile explicitly with its normal source bindings and external-processing enablement. Set `EXTRACTION_OPERATION_SEMANTIC_PROFILES=true` to offer the successor profiles in new Documents wizard previews. Existing operations still resolve the exact profile hashes consented at admission. The wizard flag defaults to false and external processing continues to require the existing opt-in.

### M2 grounding and retention

- The Engineering schema adds bounded LABEL, VALUE, UNIT, QUALIFIER, EQUIPMENT, TAG and CONTEXT parts. The server resolves each part to the original native or OCR occurrences on the bound page. Each evidence record retains its actual token text and offsets. A multi-part display expression carries no synthetic combined source span.
- Same-line order, bounded local form geometry and supported table header relationships provide distinct bases. Missing geometry, competing readings and distant fragments can leave the relationship unresolved. Page-image reports remain page-level and unverified. Grounded facts can survive as raw unmapped or invalid candidates. Unsupported reading references are rejected individually. The stage still publishes atomically.
- Engineering can see text that layout marked table-contained. Tables still uses committed reconstruction and independent row/header evidence. A failure of Tables leaves the Engineering path available. Results remain separated by producing run. Independently selected runs can report overlapping observations.

### M3 semantic interpretation

- A bound equipment description and a sufficiently informative source field can support a model-proposed registry meaning even if the legacy terminology lookup has no match. Known contradictory terminology, incompatible registry keys, ambiguous labels, essential conditions and unproved relationships block typed mapping. The server normalizes exact decimal, integer, enum and boolean values through registry-v1 and verifies units and storage bounds. Model-proposed raw values remain separate from typed results.
- The attribute stage receives the bounded registry projection even after unresolved recognition. Association uses the committed mention, supported scope, and distinct designation evidence. Explicit page designations require a single supported equipment context with no competing designation. Unassigned tags can survive as raw observations.
- Tables uses scoped equipment, cells and header paths for the same authority split. Repeated installed rows stay separate. A provisioned row does not become an installed equipment mention. Candidate diagnostics carry the parsed proposal, evidence roles, relationship basis and mapping reason.

### Review examples

- A synthetic `kVA:` / `350` form and a novel `Continuous transfer duty (kVA)` field both map to `rated_apparent_power` using separate citations, including after unmapped recognition. A separate `Primary:` / `600 Delta Volts` value normalizes to `0.6 kV` from the literal unit spelling.
- A proposed primary key for a source secondary-voltage label stays unmapped. A minimum capacity stays raw and a foreign reading alias is rejected. A distant label/value pair and an image-only report remain raw with their evidence limits.
- Synthetic title-block `80T1` and panel designation `CDP-6C` bind to a single supported mention. Competing equipment blocks page-level tag assignment. A synthetic schedule keeps two identical installed breaker rows separate and retains the provisioned count without creating equipment for it.

### Remaining verification

The regression pass reported 423 targeted backend checks and 50 checks in the PostgreSQL-backed suite, with one live Celery transport case deselected. A focused successor and legacy identity rerun passed 20 checks, and the final horizontal-form assertion passed in a 14-case offline run. Ruff, Compose configuration and whitespace checks passed.

The new cases use independently authored synthetic layouts or existing synthetic tables. Both successor profiles were exercised through the real worker, PostgreSQL publication and revision-scoped API with mocked OpenAI transport. No live OpenAI calls or original customer PDF evaluations were made. Full OCR, Celery and MinIO coverage remains open. Geometric scope is conservative on irregular columns, distant headers and nested groups. Composite or qualified fields whose representation is uncertain stay raw. M4 covers irregular reconstruction, schedule robustness and additional table response handling. M5 covers broader source annotations and integration.

**Recommendation:** Review M2 and M3 with the successor profiles opt-in. M4 is outside this change.

### Distributed transformer specification regions

`engineering-openai-enriched-v3` adds a conservative association path for a single transformer drawing with visibly titled specification or ratings sections. Section membership is bounded by its own heading and local reading layout. A section association requires separate grounded label/value evidence and corroborating primary and secondary voltage readings. Recognition can use cited winding context from a distant section to support the proposed transformer type. The candidate records the association basis and cites the section heading. Competing equipment headings or designations block the distant association. Unlabeled or ambiguous blocks can still produce detached raw observations.

New opt-in wizard previews select Engineering v3 and Tables v3. Existing consented operations resolve their original profile hashes. Engineering v2 retains its original behavior and runtime identity. No database migration is required. Verification uses a synthetic drawing with a heading, winding specifications, electrical ratings, and a title block in separate regions. The competing-transformer variant leaves the rating detached. The supplied drawings remain outside live-provider verification.


### Semantic admissibility in the v3 profiles

Engineering and Tables v3 use the model's proposed meaning when the relevant source facts and associations are grounded, the registry permits the key, deterministic normalization succeeds, and the source carries no established contradiction or unresolved ambiguity. Word count plays no role. The prompt distinguishes auxiliary load from nameplate capacity, primary from secondary voltage, trip from frame and interrupting ratings, and conditional from nominal ratings. An explicitly labeled auxiliary load proposed as rated apparent power stays raw with `ATTRIBUTE_PROPOSAL_CONFLICT`. Original observations, proposals, qualifiers, and evidence remain available for review.

PowerForge can verify source citations, recognized contradictions, registry applicability, units and values. An incorrect interpretation of an unfamiliar field may still be plausible and pass those checks, particularly when different properties share units and the source context provides no independently detectable contradiction. MAPPED means the proposal passed the extraction checks and carries no engineer verification. The v3 profiles keep the existing call count. Historical v2 profiles keep their pinned semantic behavior.

Engineering v3 can ground a label and a value inside one native-text reading. Both roles cite the original occurrence. The relationship check verifies unique literal substrings in label-before-value order and rejects competing fields or partial numbers. A combined `kVA: 350` reading and four negative variants passed in the 30-test offline semantics and historical identity suite.

Engineering v3 can associate a title-block designation with a unique panelboard when other grounded equipment observations occupy rows under an explicit branch-breaker section. The designation evidence cites the panelboard and the branch context. Competing panelboards, conflicting designations, or breakers without supported branch scope leave the distant designation unassigned. A synthetic Eaton-style regression retains `CDP-6C` on the panelboard and two distinct, untagged `GBH3020` breaker mentions. The competing-panel and missing-branch-heading variants abstain.

Engineering v3 also checks the literal suffix of a numeric reading when the model omits qualifier anchors. `MAX`, `MIN`, and unexplained trailing text preserve the raw observation as `UNMAPPED`. A verified unit suffix can still normalize. The correction changes the shared v3 runtime hash. Previously pinned v3 attempts may require re-extraction to use the corrected runtime. Legacy profile identity tests passed.

## M4 — Compact Tables reconstruction and schedule semantics

`tables-openai-enriched-v4` adds `table-reconstruction-schema-v3`. The provider returns committed partition aliases and proposed orientations, plus optional reported tables for regions without applicable partitions. `table_reconstruction_v4.py` expands each selected partition using its committed cells, spans, readings and header paths. It supports verified same-row labels in simple two-column forms and a conservative first-row header derivation for device schedules. The server records the compact recipe in table layout metadata and independently replays it before publishing and before building Interpretation input. The existing v6 run envelope and table layout storage need no migration.

The v4 Interpretation prompt uses the existing `table-interpretation-schema-v3` observation shape. The model supplies semantic proposals. The converter verifies cell and equipment scope, grounded text and qualifiers, then applies registry and normalization rules. Separate installed rows have separate equipment groups. A printed provisioned quantity stays `UNMAPPED` with reason `PROVISIONED_POSITION` and cites both the quantity and the marker. An untagged model number remains part of the source expression. The frozen Phase 5 registry continues to govern mappings. The profile's new prompts, manifests, schema and runtime are pinned. Archived runtime resources preserve the prior Tables and Engineering identities.

Reconstruction distinguishes a valid empty result from malformed JSON, missing fields, duplicate or unknown aliases and a provider output-token limit. Failure blocks only the dependent Tables Interpretation attempt. A complete empty reconstruction settles without an Interpretation call. Publication remains atomic and each attempted stage uses at most one provider call. The independently executed Engineering pipeline retains its results when Tables fails.

## M5 — Regression and compatibility handoff

The [annotated synthetic corpus and optional private-document procedure](../evals/extraction/phase6g/README.md) cover split and distributed transformer specifications, a two-column form and a breaker schedule. These stage-level comparisons use scripted responses and actual prepared source/layout. Response sizes are serialized JSON bytes, with one partition per response.

- **Engineering recognition and attributes.** The M1 split-reading reproduction kept one recognized transformer and rejected the single attribute with `CROSSES_SOURCE_LINES`. The Phase 6G semantic path retains both literal source parts and maps the scripted supported rating to 350 kVA. The distributed variant maps the uniquely corroborated rating and preserves ambiguity when a competing transformer is added.
- **Table Reconstruction.** The expanded transformer-form response used 2,139 bytes and the compact response used 183 bytes. Both returned one table with six cells. With the same expanded grid proposed as an attribute form, historical admission yields `UNRESOLVED`. v4 independently verifies the same-row label relationship as `NATIVE_GEOMETRY_SUPPORTED`. The breaker schedule used 2,669 bytes before and 183 bytes after, with one table and eight cells retained. The 82-cell regression preserves every cell while using less than one tenth of the expanded response bytes. The merged-header regression retains the same spans and header paths.
- **Table Interpretation.** The authored form proposal uses one equipment observation and one attribute observation. The exact source cells for the unfamiliar printed label and `350` support a mapped `rated_apparent_power` of 350 kVA under v4. The schedule comparison scripts three equipment and three quantity proposals. Both converters publish two distinct installed breaker mentions and retain three raw quantities. v4 leaves the two breaker tags empty and explicitly marks `18` as `PROVISIONED_POSITION`, with the printed `PROV` cell supporting it.
- **Provider and publication failures.** Mock SDK transport covers structured empty output and output-token truncation. The invalid-response regression records one call, zero published Tables results and a blocked Interpretation attempt while the independent Engineering run remains readable. Visual-only reports preserve page-level evidence without native offsets or cell regions.

All six enriched Engineering/Tables v1–v3 production profile hashes matched the starting commit `a8e0921` with the same settings. The historical source-policy exception for the 2,048-primitive v1 limit remains as documented in M1. The real broker test recovered expired Tables v3 and v4 claims through Celery and Redis. The worker appended one retry per run, retained the original profile and execution pins, published through PostgreSQL and served the exact printed `600` occurrence from signed MinIO evidence. Each run used two scripted provider calls in total.

The final targeted Linux suite passed 133 backend tests with no skips. It covered the Phase 6G regression cases, pinned extraction and spatial identities, OCR evidence, atomic publication, Phase 6F operations and historical reads. Ruff and whitespace checks passed.

Frontend verification passed 355 React/unit tests, four desktop/mobile Run History diagnostic captures and 25 Phase 6F Chrome captures covering wizard, operation, evidence and re-extraction states. Those browser runs used the repository's synthetic API fixtures.

Deterministic checks cannot discover an omitted observation or detect every semantically wrong but source-compatible model proposal. Irregular tables without a committed partition can remain visual-only, and source ambiguity can require abstention. Live OpenAI, the three supplied drawings and production quality remain unmeasured. Broad acceptance, deployment hardening and the Phase 6 freeze are tracked under 6H, followed by Phase 6.5.

**Milestone recommendation:** M4 and M5 are ready for review. The focused Phase 6G gates passed.
