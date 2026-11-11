# Extraction

AI extraction proposes candidate engineering data. It does not mutate the verified engineering model.

Phase 6A adds persistence and read access under the [approved specification](specs/phase-6-evidence-structured-extraction.md) and [ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md). Validation and operational details are recorded in [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md). The canonical model remains manually authored and separate. Phase 6B makes orchestration operational. Phase 6C M1–M6 provide opt-in production engineering extraction and representative evaluation tooling; live-model quality remains unverified. Phase 6D M1–M4 add table definitions, source grounding, interpretation/publication, opt-in production execution and independent table evaluation; later OCR/UI/hardening remain pending. See [PHASE6B_HANDOFF.md](PHASE6B_HANDOFF.md), the [final 6C handoff](PHASE6C_HANDOFF.md) and the [final 6D handoff](PHASE6D_HANDOFF.md).

## Principles

- Do not use one enormous prompt for an entire project.
- Use specialized extractors with explicit input/output contracts.
- Validate all model output against Pydantic schemas. Never trust raw LLM output.
- Store provider, model, model version, prompt version, and timestamp with extraction metadata.
- Application domain logic must not import vendor SDKs.

## Pipeline

```
Document / DocumentPage
    → native text / OCR / visual / table inputs
    → Evidence
    → ExtractionRun
    → ExtractionCandidate
    → schema + canonical-registry validation
    → candidate records for later entity resolution / reconciliation
```

This is a conceptual traceability flow, not a frozen persistence schema. AI output remains an evidence-linked candidate. Phase 6 owns run metadata, provider/model/prompt versions, retry/versioning semantics, equipment/attribute and schedule/table extraction, OCR/layout where needed, and extraction evaluation/hardening. Candidate keys, types, and units must map to the canonical registry. Confidence is recorded at candidate/evidence level; regions use normalized upright DocumentPage coordinates, as defined in [PROVENANCE.md](PROVENANCE.md).

Candidates proceed to entity resolution (7), reconciliation/conflict management (9), deterministic validation (10), and engineer review (11). They never silently overwrite canonical values or become engineer-verified truth. `system_frequency` and `system_phase_count` are manual-only. Phase 6 neither proposes nor writes revision-wide settings. Source frequency or phase statements may become justified equipment-specific candidates or raw unmapped observations.

The approved 6A–6H slices in [ROADMAP.md](ROADMAP.md) define implementation boundaries. Study-domain/protection extraction requires approved target-domain design first.

## Phase 6A persistence and reads

`powerforge_extraction.contracts` and `powerforge_provenance.locations` are provider-neutral Pydantic contracts. `powerforge_extraction.models` owns the eight extraction ORM mappings on the existing shared Base, following the classification package pattern; `powerforge_extraction.persistence.ExtractionPersistence` is the internal transaction-participating interface. Pure contract modules import no ORM, HTTP, workers or provider SDKs.

`create_run()` pins immutable inputs and computes a deterministic input identity. `create_work_unit()` appends an attempt; neither schedules work. `publish()` locks the run then unit, validates source/registry/association integrity, and writes the entire output plus success marker inside a savepoint. The caller commits or rolls back the outer transaction. No provider calls or object writes occur. `record_ai_call()` can retain technical telemetry before a failed unit terminates; telemetry is immutable and never an effective candidate result. Text-offset publication requires `ExtractionPersistence(session, storage)`: it streams the exact pinned UTF-8 artifact, verifies byte size/SHA-256 and counts Unicode codepoints once per artifact per publication. Mutable page-level text counts are not used, and unverifiable artifacts reject publication without partial output.

Migration `0011_extraction_persistence` provides composite ownership FKs, active identity/attempt uniqueness, a single successful attempt per logical key, typed value constraints and immutable output guards. Deferred publication guards prohibit candidate/evidence/group/table output from committing without successful unit completion. A retry appends to unsuccessful history; it cannot replace a successful unit. NUMBER uses Decimal/NUMERIC and INTEGER uses int/BIGINT; both serialize to JSON strings. Explicit false remains false. No candidate is fabricated for an omitted attribute. Follow-up migration `0012_extraction_terminal_guard` prevents COMPLETED, PARTIALLY_COMPLETED, FAILED or CANCELLED runs while any required or optional attempt remains PENDING/RUNNING. Callers must settle and flush attempts before finalizing the parent; migration 0011 is unchanged.

Six GET routes beneath `/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/extraction` expose summary, `/runs`, `/runs/{run_id}`, `/runs/{run_id}/candidates`, `/runs/{run_id}/tables` and `/evidence/{evidence_id}`. INCLUDED revision-document membership gates all reads, including inherited and superseded revisions. Context-dependent runs are restricted to their explicitly fingerprinted revision. Lists use bounded limit/offset pagination and deterministic timestamp/UUID ordering. Candidate filters include kind, mapping status, group, equipment type and attribute. By default only candidates with PRIMARY/SUPPORTING citations appear; `supported_only=false` also exposes explicitly unsupported observations. Phase 6B adds operational POST routes described below.

Run detail includes all historical attempts and effective successful-unit coverage; candidate/table lists include only effective results and expose partiality. Candidate responses include citations and optional source-local group metadata. Evidence resolves the exact pinned artifact through the established short-lived signing interface, including historical artifacts; raw storage keys are omitted.

## Phase 6B orchestration

[PHASE6B_PLAN.md](PHASE6B_PLAN.md) records the technical design. `ExtractionCoordinator` owns transaction-participating start/ensure/re-extract, claiming, heartbeats, retries, cancellation, aggregation, recovery and durable delivery. `execution.py` runs provider I/O outside database transactions, revalidates responses and publishes through 6A. PostgreSQL remains authoritative; Celery/Redis notifications can be lost or duplicated safely.

Migration `0013_extraction_execution` adds run configuration/admission/cancellation controls and per-attempt delivery/token controls. Snapshots pin the source-probe profile, provider/model, prompt/schema versions and hashes, per-page partitioning and limits. A short global admission lock plus run/unit row locks bounds concurrent execution. Each claim has one immutable token, lease and absolute deadline. Short heartbeat transactions cannot renew beyond that deadline. Publication checks the token/lease/cancellation and has database fencing, including for empty output. Interrupted work settles before bounded append-only retry. A periodic Celery beat reconciler recovers expired leases and re-dispatches due pending notifications, including work committed before a broker outage.

Recovery batches select runs with expired leases in expiry order, then active parents with only settled work needing aggregation. Healthy active runs do not occupy the recovery window. Temporary object-storage connection, service or streaming-read failures are classified as `SOURCE_UNAVAILABLE` and use the existing bounded retry/backoff and admission budget, including failures during evidence publication. Missing, corrupt, invalid UTF-8 or otherwise invalid source inputs retain permanent `INVALID_SOURCE_INPUT` treatment; access-denied/configuration failures do not automatically retry. Only actual provider calls produce call telemetry.

Two executable profiles are available through GET `/extraction/profiles`: `infrastructure-fake-v1` is explicitly synthetic test execution; `infrastructure-openai-v1` is an explicitly enabled source-access/structured-response probe. Neither is a production equipment, attribute, table or OCR extractor. The fake profile can retain labeled test observations supported by exact native text. The OpenAI probe retains only a verified excerpt/evidence or empty output, with no engineering candidate interpretation. UNKNOWN/MIXED classification does not prevent execution, and explicit profile selection overrides the default. Automatic post-processing extraction is not implemented; there are no surprise external calls.

POST `/extraction/runs` accepts strict `{profile_key, pages, mode}` with `mode=ensure|reextract`. Ensure deduplicates equivalent active runs and may reuse compatible completed results. If no completed result exists, repeating ensure returns the compatible failed/partial/cancelled run without creating new billable work; continuing requires explicit retry or re-extraction. Re-extract creates a new linked run after prior work settles; repeated equivalent requests while active return the active run. POST `/runs/{run_id}/retry` appends only unsuccessful keys in FAILED/PARTIALLY_COMPLETED runs, within the original attempt/call limits. Successful units are preserved. Completed/cancelled history is immutable: use explicit re-extraction for those runs. POST `/runs/{run_id}/cancel` settles active attempts before finalizing CANCELLED, retains successes and fences late responses. Repeated cancellation is safe; a completed run cannot be retroactively cancelled.

Run detail exposes profile kind, safe usage/admission counts, cancellation, retry eligibility, stale lease indicators and attempt history. Unknown tokens or prices stay null. Configured flat input/output rates require a recorded pricing basis; cached input is conservatively estimated at the configured input rate. The initial spending safeguard is a pinned provider-call admission budget plus bounded pages, input bytes, image pixels, output tokens, retries and timeouts; there is no claimed strict dollar guarantee when prices/usage are unknown. Interrupted or pre-call failed admissions consume budget rather than permitting unbounded retries. A crash around an external call may still incur a duplicate charge on recovery; unreported call boundaries remain explicit.

The existing extraction worker consumes `document_classification,document_extraction`; the new `extraction-scheduler` runs Celery beat. Both are necessary for automatic recovery. See the [6B handoff](PHASE6B_HANDOFF.md) for setup, exact guarantees, validation and the 6C extension contract.

## Phase 6C M1 — Observation and prompt definitions

The [6C plan](PHASE6C_PLAN.md) is being delivered in milestones. M1 adds offline, provider-neutral recognition/attribute observation schemas, role-based source anchors, registry-derived context for all 20 types/296 attributes, a small qualified terminology policy, versioned composable prompts and canonical stage/resource hashes. Unknown proposed mappings, tagless equipment and standalone attributes remain representable. Response-shape/reference validation does not establish source grounding or mapping correctness.

These definitions are not connected to the worker or public production profiles. Existing fake/probe execution, profile identities and registry-v1 remain unchanged. M2 supplies interpretation and M3 supplies grounding/output conversion below; execution integration is M4–M5 and measured evaluation M6. No live model accuracy is claimed. See [PHASE6C_M1_HANDOFF.md](PHASE6C_M1_HANDOFF.md).

## Phase 6C M2 — Deterministic interpretation

`powerforge_extraction.interpretation` accepts M1 observations plus admitted local source/equipment passages. It checks asserted fields against the statement, derives type/attribute meanings from registry labels/keys and explicitly qualified terminology, checks model proposals for conflicts, and uses registry normalization with Decimal/int values. Missing/ambiguous context or units and unknown enums remain UNMAPPED; failed normalization remains INVALID with raw data and no normalized slots. Fabricated source fields are rejected separately and must not become candidates. Source label/header units are allowed when explicit; registry default units are never inferred for extraction.

The frozen v1 rules have their own reproducible identity. Parenthetical suffixes are removed only for recognized units; other qualifiers remain part of the meaning and cannot be erased by punctuation folding. Unresolved qualified labels remain UNMAPPED, while exact full registry display labels remain supported. Units on unitless fields must pass registry validation. This layer does not admit artifacts, verify pixels, create evidence/groups/candidates, schedule work or mutate canonical data. M3 must supply proven local context and preserve page-level visual limitations. Lexical interpretation deliberately leaves unsupported synonyms, uncertain associations and complex notation unresolved. See [PHASE6C_M2_HANDOFF.md](PHASE6C_M2_HANDOFF.md).

## Phase 6C M3 — Source grounding and publication conversion

`engineering_sources` snapshots source ownership from immutable run/unit inputs and loads recognition context only from completed same-run/page units. `grounding` verifies bounded artifact bytes/hash/UTF-8 or PNG metadata, resolves verbatim text occurrences and codepoint offsets, and preserves page-level visual limitations. `engineering_output` converts accepted observations through M2 into SourceGroup/Candidate/Evidence/CandidateEvidence payloads for the existing atomic publisher. There are no provider or scheduling calls in this path.

Native interpretation retains the complete verified line, with a narrow explicit AF/AT-pair grammar for source clauses. Unresolved repeated occurrences stay page/text-level and lose guessed associations. Native equipment associations require an unambiguous structural source block; a model reference alone is insufficient. Visual context is restricted to the same exact image and conservative local references, with `VISUAL_PAGE`/`VISUAL_REPORTED` metadata and no invented snippet, offsets or region. Verified fragments in unresolved full-line context may survive only as detached UNMAPPED observations with the full-line evidence.

`WorkUnitOutput.diagnostic_counts` adds closed, bounded counts for ungrounded/source-field rejections and detached associations. Publication merges them into the existing `output_counts` before the success marker, inside the same savepoint; failed publication exposes neither partial results nor counts. Evidence list/detail responses now include `grounding_precision`. Exact typed values, shared/cross-unit citations, source-local tags and immutable successes retain the 6A guarantees. See [PHASE6C_M3_HANDOFF.md](PHASE6C_M3_HANDOFF.md). M4 adds synthetic dependent-stage execution below; production OpenAI profiles remain M5.

## Specialized extractors

| Extractor | Role |
| --- | --- |
| `DocumentClassifier` | Document type + confidence |
| `EquipmentExtractor` | Equipment mentions and types |
| `AttributeExtractor` | Typed attributes with units |
| `TableExtractor` | Schedules and tabular sources |
| `SLDExtractor` | Symbols, text, components on SLDs |
| `TopologyExtractor` | Connection candidates |
| `EntityMatcher` | Duplicate / same-physical-entity candidates |

Each extractor has a versioned prompt (or equivalent artifact) and a Pydantic output schema.

## Provider abstraction

`packages/ai` defines:

- `LLMProvider`
- `VisionProvider`
- `OCRProvider`
- `EmbeddingProvider` (only if required later)

Conceptual contract:

```
extract_structured(input, schema, context) -> structured_result
```

The engineering application does not care which vendor produced the result. Swapping OpenAI, Anthropic, Gemini, or an on-prem model must not change the engineering model.

## Prompt versioning

Future extraction prompts are planned under `packages/ai/prompts/` (version-controlled). Do not bury large prompts inside random application files.

Examples:

- `equipment_extraction_v1`
- `equipment_extraction_v2`
- `sld_extraction_v1`

The prompt version is stored with the extraction result for reproducibility.

Phase 0 created that directory and a README. The implemented Phase 4 classification prompts live in their owning classification package, as described below.

## SLD extraction

SLD interpretation is not ordinary OCR. Planned pipeline (Phase 8):

```
SLD PAGE
    → IMAGE PREPROCESSING
    → SYMBOL / COMPONENT DETECTION
    → TEXT DETECTION
    → TEXT-COMPONENT ASSOCIATION
    → EQUIPMENT IDENTIFICATION
    → CONNECTION DETECTION
    → TOPOLOGY CANDIDATE
    → VALIDATION
    → ENGINEER REVIEW
```

Preserve the original image and source-page evidence, with regions normalized to the upright DocumentPage. Phase 8 produces component, terminal/connectivity, and topology candidates targeting Phase 5D ModelNode/ModelConnection semantics. The SLD is not the database.

## Entity resolution

Entity resolution is a first-class module (Phase 7). Signals include tag similarity, type, location, connected equipment, manufacturer, model, rating, voltage, document context, spatial proximity, and surrounding topology.

Planned outputs retain candidate identity, match confidence, supporting evidence, and conflicting evidence; exact contracts require a formal specification. The bridge is ExtractionCandidate → candidate physical identity → EquipmentLineage / revision-scoped Equipment. Do not automatically merge low-confidence matches.

## Phase 4 classification

Specified in `cursor/phase4_specs.txt` and [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Accepted). Complete (2026-10-12).

Phase 4 is the `DocumentClassifier` row above and nothing else in that table. It chooses a document class, and sometimes a page class, from the existing taxonomy plus `MIXED_DOCUMENT`. It does not extract equipment, attributes, tables, or topology.

The provider contract stays vendor-neutral (`ClassificationProvider`). OpenAI is the first adapter, in `extraction_worker.openai_classification`. Tests and local Compose use a fake provider. Classification prompts live in `powerforge_document_classification` (`document_classifier_v1` and `page_classifier_v1`). They are not under `packages/ai/prompts/`.

## Out of scope until named phases

- Phase 3: document processing renders pages and reads native PDF text. It does not call `OCRProvider` or any classifier
- Phase 4: classification is complete. Equipment, table, and SLD extractors stay in their own later phases
- Phase 6: Evidence/candidate persistence and structured equipment/attribute/table extraction, with OCR/layout support as needed
- Phase 7: entity resolution
- Phase 8: SLD extraction
- Phase 9: reconciliation and persistent conflict management; Phase 11 retains human decision/verification authority

## Phase 6C M4 — Stage execution

Each selected page now has required EQUIPMENT_RECOGNITION and ATTRIBUTE_EXTRACTION keys with immutable prerequisite metadata. Waiting attributes cannot dispatch or claim an admission before committed recognition success. Empty recognition still releases attributes. Permanent/exhausted upstream failure settles blocked attributes with PREREQUISITE_FAILED before aggregation; pending automatic retries keep them waiting. Manual retry eligibility includes satisfiable blocked downstream work and reuses successful recognition. Expiry-first recovery also settles historical unsatisfiable pending dependencies.

The v2 profile reader pins all stage, interpretation, grounding and runtime identities plus multimodal/context limits; v1 serialization and probe hashes are unchanged. Engineering attempts verify their original selected text/image descriptors, build bounded registry/upstream context and revalidate the selected stage schema before M3 conversion and fenced publication. Each attempt allows one provider call; actual schema/rendered-instruction and upstream context identities remain reproducible across retry. No fallback to current artifacts or another modality occurs after failure.

Manual synthetic profiles engineering-test-v1 and engineering-test-text-v1 report FAKE_TEST, mark any candidates synthetic and use empty stage responses in the normal worker; tests inject populated observations. M5 adds production profile discovery and its stage-aware adapter below. There are no new routes, canonical writes, migrations or UI changes. [PHASE6C_M4_HANDOFF.md](PHASE6C_M4_HANDOFF.md) records tests, source limits and the M5 boundary.

## Phase 6C M5 — Production profiles and OpenAI adapter

The existing manual start endpoint now accepts engineering-openai-v1 (selected native text plus analysis image, including image-only pages) and engineering-openai-text-v1 (requires native text). Both advertise ENGINEERING_EXTRACTION and production_extractor=true. External processing remains off by default and requires explicit API/worker enablement; the default profile remains infrastructure-fake-v1. Discovery reports configured enablement, not account/model/credential verification. No automatic extraction or new route/UI is introduced.

The adapter uses the selected Pydantic stage schema in one Responses parse call with explicit model, timeout/output cap and reasoning effort, SDK retries disabled, store=false and no tools. Versioned source-role envelopes keep document text/images and upstream observations separate from trusted instructions. Safe failure handling preserves known usage and leaves unavailable usage unknown. v3 production profiles pin transport/runtime/resources and all limits, independently of probe output defaults; packaged original reader resources preserve the existing v1/v2 wire identities. Compose and .env.example forward production settings consistently, with the API key remaining worker-only.

Real SDK transport-mock tests and actual worker/beat/Redis/PostgreSQL/MinIO tests cover grounded API publication/signing, transient/manual retries, usage and process restart without resending recognition. Native offsets and visual page-level limits retain M3 semantics; synthetic fixtures do not establish live-model accuracy. [PHASE6C_M5_HANDOFF.md](PHASE6C_M5_HANDOFF.md) records actual checks/configuration. M6 evaluation is described below.

## Phase 6C M6 — Reproducible evaluation

The [corpus guide](../evals/extraction/README.md) defines 15 synthetic single-page cases with 50 independently specified claims, source hashes, exact values/units, statuses and expected associations. Run `.venv/bin/python -m powerforge_extraction.eval --corpus evals/extraction/v1/corpus.json` for offline M1–M3 replay. The installed command is `powerforge-eval-extraction`. It needs no provider, database or broker and reproduces the committed scripted report.

Matching uses literal source expressions and modality/occurrence, never proposed keys/values or model reference IDs. Metrics include explicit numerators/denominators for equipment precision/recall, mapping, typed values/units, raw and unmapped/invalid retention, grounding, association/group separation and false candidates. Missing/failed predictions remain in gold denominators; empty denominators are null. Exact matching is deliberately conservative. Visual grounding measures honest page/artifact location, not pixel/text verification. Scripted results are converter checks, not measured production-model quality.

Live evaluation is separately opt-in with `--live`, an approved canonical corpus digest, exact preprocessed Document bindings and a total call bound. The worker helper validates the entire selected batch before committing, then uses existing coordinator/claims and atomic publication. Each fixture pins two admissions and one attempt per stage; no retry/repair can exceed that envelope. Timeout/interruption cancels only its unfinished runs. See the guide for setup/commands; no live evaluation was run during this delivery. The [final handoff](PHASE6C_HANDOFF.md) records actual tests and the 6D/6E extension contract.

## Phase 6D M1 — Offline table definitions

`table_observations`, `table_layout` and `table_stages` define strict reconstruction/interpretation responses, sparse grids, explicit blank/unreadable cells, headers/spans, scoped references, conservative orientation hints and versioned prompts/registry context. Pure inspection marks text UNVERIFIED and structure UNRESOLVED. Reference validity does not prove source occurrence, row ownership or engineering mapping. No table profile is registered and no artifact, candidate or table is published by M1.

The approved future profile is table-only; ordinary prose needs a separate 6C run. Existing latest-result summaries are across profiles, not a merged view; earlier results remain in run history. The planned M3 gate verifies both sets remain accessible. Native table relationships need stronger proof than matching text tokens; representative PDF/visual-dependence evaluation remains M4. See [PHASE6D_PLAN.md](PHASE6D_PLAN.md) and the [M1 handoff](PHASE6D_M1_HANDOFF.md) for delivered bounds/checks and pending work. Spreadsheet ingestion is deferred to 6.5 after 6H and before 7.

## Phase 6D M2 — Grounding, interpretation and publication

M2 adds exact pinned table admission, independent literal-text/relationship reliability, conservative structured-cell registry interpretation, source-local groups and conversion into existing tables/evidence/relational candidates. Native structure requires a unique contiguous delimiter grid; otherwise an explicit visual reading retains page-level limits or the association remains unresolved. Committed reconstruction is revalidated for the exact run/page/artifacts before interpretation. Publisher checks now reject wrong-page/artifact/cell and unfinished upstream ownership, and existing evidence reads report actual table-cell precision and sign the historical artifact.

M1/6C resources and profile/runtime identities, registry-v1, migrations and canonical models remain unchanged. M2 introduced no production table profile or worker execution; M3 integration and M4 representative table evaluation are recorded below. Table-only ownership still requires a separate 6C prose run, and latest summaries continue selecting across profiles. See [PHASE6D_M2_HANDOFF.md](PHASE6D_M2_HANDOFF.md) for actual checks, source rules and conservative coverage limits.

## Phase 6D M3 — Opt-in table execution

Select tables-openai-v1 or tables-openai-text-v1 through the existing profile/start API. Both are table-only; ordinary prose needs a separate 6C engineering run. The existing fake default and external-processing opt-in remain. A v4 profile pins the table manifest, reviewed M2 rules, table runtime/input contract and material limits. Two required page stages commit reconstruction before interpreting its exact cells. Multiple tables share the same two calls; interpretation retry reuses the completed reconstruction. New table-specific settings are documented in .env.example and shared by API/worker/scheduler.

An admitted empty interpretation completes with a fenced skipped_empty_tables marker and no provider call. It still consumes its ordinary admission; aggregate usage remains conservatively unknown when not every admission has a reported call. Existing table/candidate/evidence/history APIs and signing remain. A newer completed/partial/empty table run can become latest_result across profiles; older prose results remain in paginated run history. Current_run still includes newer non-result states.

Historical v1/v2/v3 profiles and 6C behavior are preserved with retained source identity data plus active-run compatibility tests. M3 adds no UI, migration, canonical write or table evaluator. M4 table evaluation is recorded below; production model accuracy is unmeasured. See [PHASE6D_M3_HANDOFF.md](PHASE6D_M3_HANDOFF.md).

## Phase 6D M4 — Independent table evaluation

The separate offline `powerforge-eval-tables` command (`python -m powerforge_extraction.table_eval`) replays versioned reconstruction/interpretation recordings against independently authored source/table/cell/claim annotations. Source occurrences and cell coordinates select matches before proposed meanings, typed values, units or associations are scored. Reports retain missed/failed gold denominators, null empty rates, structural/header/orientation metrics, source-local association, citation/locator checks and UNMAPPED/INVALID retention. Native literal proof, visual reports and relationship reliability remain distinct. Caller-provided recording provenance cannot designate live quality. The frozen 6C evaluator and M1–M3 production resources are unchanged.

The corpus has 27 synthetic cases, 27 gold tables, 146 cells and 73 claims, including a real processed-PDF native/hybrid pair. Native abstention loses recall against the visible source gold; visual relationships retain explicit page-level limits. All 100 new tests and new extraction-wheel checks pass. At the user's request, the already verified M3 full backend/integration/migration/API/dependency checks are carried forward, not repeated. No paid model call or live accuracy measurement is claimed. See the [table corpus guide](../evals/tables/README.md) and [final handoff](PHASE6D_HANDOFF.md) for actual scores, verification evidence and remaining limits.

## Phase 6E M1 — Pure spatial source foundation

Separate versioned modules in `packages/provenance` define immutable producer/artifact/page ownership, native/OCR positioned text, token/line/block and native-primitive support, exact source occurrences, conditional native-origin correspondence and pinned prepared/spatial bindings. Pure orthogonal transforms preserve crop, scale, mirrors, quarter turns and normalized upright geometry. Missing support stays null; a resolved support envelope does not establish table/equipment ownership. M1 support resolution remains UNRESOLVED structurally and does not independently verify printed characters. Unknown OCR text coverage remains UNKNOWN.

`powerforge_ai.ocr.PositionedOCRProvider` is a typed protocol with raw image/word/box/settings identity, engine-scale confidence and local usage/failure contracts. The original generic OCR interface and all accepted 6C/6D contracts/resources stay unchanged. No engine/native adapter, production profile, API, schema migration or publisher support is enabled by M1. Existing evidence is not retrospectively upgraded. M2 must implement real processing and durable source artifacts; M3/M4 must establish actual structure and source-aware publication. Backend purpose guards on every endpoint and the future coherent 6F UI remain required.

All 92 focused tests, provenance/AI wheel checks and new resource identities pass; accepted v1–v4 wires/resources and both full frozen 6C/6D reports reproduce unchanged. No infrastructure integration or paid provider call occurred. See [PHASE6E_M1_HANDOFF.md](PHASE6E_M1_HANDOFF.md) for actual bounds/verification and [PHASE6E_PLAN.md](PHASE6E_PLAN.md) for later review gates.


## Phase 6E M2 — Durable native/OCR source preparation

The new local source-preparation profile consumes an explicitly selected completed base run/pages and produces independent immutable native/OCR text and geometry. Actual PyMuPDF 1.28.2 and Tesseract 5 adapters preserve source-local occurrences, transforms, raw readings and recognition limits. Native-plus-raster text coverage stays UNKNOWN and requires explicit whole-page OCR selection; there is no guessed coverage percentage or blanket OCR. M2 establishes neither table relationships nor engineering meaning.

Migration 0014 adds SOURCE_ENRICHMENT purpose, separate source result/artifact/binding records and purpose/lease/identity guards. Local planning/execution/publication reuse the existing durable coordinator with a dedicated CPU queue and admission pool. Source start/input discovery/history/detail/result/artifact/retry/cancel APIs enforce membership and purpose on direct IDs; ordinary extraction summaries/history ignore source jobs. Local run model/prompt/registry fields are inapplicable, and local jobs cannot publish ordinary extraction outputs or AI calls. Usage distinguishes admissions, recognition requests and confirmed engine invocations; unmeasured cost/child resources remain null.

All 271 distinct targeted checks pass, including 51 new M2 cases, real OCR/PostgreSQL/Redis/MinIO/Celery/restart and accepted extraction lifecycle/migration checks. Retained v4 source data preserves old wire/resource hashes and both frozen evaluation reports. The worker image and package wheels reproduce accepted resources; no paid calls or UI changes occurred. Deployment, actual eligibility, measured limits and remaining M3–M5 scope: [PHASE6E_M2_HANDOFF.md](PHASE6E_M2_HANDOFF.md). M3 was subsequently authorized and is recorded below; the backend separation still permits the approved coherent future 6F guided workflow.


## Phase 6E M3 — Reusable geometry-supported layout

The explicit local `source-layout-v1` profile commits SOURCE_PREPARE then SPATIAL_LAYOUT on the existing coordinator/CPU queue. Compatible completed preparations are pinned before admission and reused through immutable direct receipts preserving their actual producer; layout retry never repeats recognition. Migration 0015 adds separate immutable layout results and reuse receipts with owned-source, stage, lease and completion guards. Source history/detail expose the original preparation, receipt and spatial result; new scoped spatial manifest/artifact reads remain separate from extraction endpoints.

Versioned pure document-processing algorithms retain exact native/OCR occurrences, contextual overlap agreements/conflicts, partial reading order and unresolved geometry. Closed native borders support partitions/merged spans; a stricter repeated-alignment path supports simple borderless schedules. Header relationships require actual column coverage plus conservative explicit label cues. OCR geometry remains OCR-derived; serialized cell readings are not printed quotes, missing readings are not verified blanks, and layout supplies no engineering ownership or meaning.

The original positioned 6D PDF gains four supported cells and two header paths over its unchanged delimiter-only baseline. Real OCR, retry and killed-worker recovery are exercised. Accepted M1/M2 and 6C/6D identities/reports remain unchanged. M4 must add the enhanced extraction/evidence adapter; M5 owns representative accuracy evaluation. See [PHASE6E_M3_HANDOFF.md](PHASE6E_M3_HANDOFF.md) for exact rules, limits and verification. Stop for M3 review.


## Phase 6G M1 — Stage diagnostics

Run detail includes an optional `stage_trace` per enhanced attempt. It reports the last execution boundary, provider outcome, parsed observation totals, admitted and rejected source observations, semantic decisions and committed output counts. An empty completed stage may have returned observations that failed source checks. A table response that fails structured validation reports a safe subtype and bounded schema paths. A parsed response that refers to unowned source aliases reports a grounding failure.

Migration 0018 adds an append-only trace record. The existing attempt fence and transaction govern both the trace and settlement. Prior attempts have no trace. Run History uses existing revision and document access. See the [Phase 6G handoff](PHASE6G_HANDOFF.md) for the local developer capture, confidentiality boundaries and verification.

## Phase 6G M4–M5 — Compact Tables reconstruction

With the semantic profiles opt-in enabled, the Documents wizard offers Engineering v3 and Tables v4 for their respective extraction families. Tables v4 asks the model to select committed partition aliases and propose their orientation. The server materializes the selected cells, exact reading evidence, spans and header relationships. Unstructured reported tables use the existing page-level evidence rules. Reported visual cells carry no verified native text offsets or cell coordinates.

Tables Interpretation uses the committed reconstruction. The model proposes meaning and the converter checks the cited cell, association, qualifications, registry compatibility and normalization. Distinct installed rows retain distinct equipment mentions. A grounded provisioned quantity remains an unmapped observation with its marker cited. Candidates still require engineer review.

Existing Tables and Engineering profiles remain addressable with their historical identities. The v4 recipe is stored in the existing table layout metadata and independently replayed against the bound source before publication and interpretation. See the [Phase 6G handoff](PHASE6G_HANDOFF.md) and [evaluation procedure](../evals/extraction/phase6g/README.md).
