# Extraction

AI extraction proposes candidate engineering data. It does not mutate the verified engineering model.

Phase 6A adds persistence and read access under the [approved specification](specs/phase-6-evidence-structured-extraction.md) and [ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md). Validation and operational details are recorded in [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md). The canonical model remains manually authored and separate. Phase 6B makes orchestration operational; production engineering extraction remains deferred to 6C–6E, with UI/evaluation and hardening in 6F–6G. See [PHASE6B_HANDOFF.md](PHASE6B_HANDOFF.md).

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

The approved 6A–6G slices in [ROADMAP.md](ROADMAP.md) define implementation boundaries. Study-domain/protection extraction requires approved target-domain design first.

## Phase 6A persistence and reads

`powerforge_extraction.contracts` and `powerforge_provenance.locations` are provider-neutral Pydantic contracts. `powerforge_extraction.models` owns the eight extraction ORM mappings on the existing shared Base, following the classification package pattern; `powerforge_extraction.persistence.ExtractionPersistence` is the internal transaction-participating interface. Pure contract modules import no ORM, HTTP, workers or provider SDKs.

`create_run()` pins immutable inputs and computes a deterministic input identity. `create_work_unit()` appends an attempt; neither schedules work. `publish()` locks the run then unit, validates source/registry/association integrity, and writes the entire output plus success marker inside a savepoint. The caller commits or rolls back the outer transaction. No provider calls or object writes occur. `record_ai_call()` can retain technical telemetry before a failed unit terminates; telemetry is immutable and never an effective candidate result. Text-offset publication requires `ExtractionPersistence(session, storage)`: it streams the exact pinned UTF-8 artifact, verifies byte size/SHA-256 and counts Unicode codepoints once per artifact per publication. Mutable page-level text counts are not used, and unverifiable artifacts reject publication without partial output.

Migration `0011_extraction_persistence` provides composite ownership FKs, active identity/attempt uniqueness, a single successful attempt per logical key, typed value constraints and immutable output guards. Deferred publication guards prohibit candidate/evidence/group/table output from committing without successful unit completion. A retry appends to unsuccessful history; it cannot replace a successful unit. NUMBER uses Decimal/NUMERIC and INTEGER uses int/BIGINT; both serialize to JSON strings. Explicit false remains false. No candidate is fabricated for an omitted attribute. Follow-up migration `0012_extraction_terminal_guard` prevents COMPLETED, PARTIALLY_COMPLETED, FAILED or CANCELLED runs while any required or optional attempt remains PENDING/RUNNING. Callers must settle and flush attempts before finalizing the parent; migration 0011 is unchanged.

Six GET routes beneath `/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/extraction` expose summary, `/runs`, `/runs/{run_id}`, `/runs/{run_id}/candidates`, `/runs/{run_id}/tables` and `/evidence/{evidence_id}`. INCLUDED revision-document membership gates all reads, including inherited and superseded revisions. Context-dependent runs are restricted to their explicitly fingerprinted revision. Lists use bounded limit/offset pagination and deterministic timestamp/UUID ordering. Candidate filters include kind, mapping status, group, equipment type and attribute. By default only candidates with PRIMARY/SUPPORTING citations appear; `supported_only=false` also exposes explicitly unsupported observations. Phase 6B adds operational POST routes described below.

Run detail includes all historical attempts and effective successful-unit coverage; candidate/table lists include only effective results and expose partiality. Candidate responses include citations and optional source-local group metadata. Evidence resolves the exact pinned artifact through the established short-lived signing interface, including historical artifacts; raw storage keys are omitted.

## Phase 6B orchestration

[PHASE6B_PLAN.md](PHASE6B_PLAN.md) records the technical design. `ExtractionCoordinator` owns transaction-participating start/ensure/re-extract, claiming, heartbeats, retries, cancellation, aggregation, recovery and durable delivery. `execution.py` runs provider I/O outside database transactions, revalidates responses and publishes through 6A. PostgreSQL remains authoritative; Celery/Redis notifications can be lost or duplicated safely.

Migration `0013_extraction_execution` adds run configuration/admission/cancellation controls and per-attempt delivery/token controls. Snapshots pin the source-probe profile, provider/model, prompt/schema versions and hashes, per-page partitioning and limits. A short global admission lock plus run/unit row locks bounds concurrent execution. Each claim has one immutable token, lease and absolute deadline. Short heartbeat transactions cannot renew beyond that deadline. Publication checks the token/lease/cancellation and has database fencing, including for empty output. Interrupted work settles before bounded append-only retry. A periodic Celery beat reconciler recovers expired leases and re-dispatches due pending notifications, including work committed before a broker outage.

Two executable profiles are available through GET `/extraction/profiles`: `infrastructure-fake-v1` is explicitly synthetic test execution; `infrastructure-openai-v1` is an explicitly enabled source-access/structured-response probe. Neither is a production equipment, attribute, table or OCR extractor. The fake profile can retain labeled test observations supported by exact native text. The OpenAI probe retains only a verified excerpt/evidence or empty output, with no engineering candidate interpretation. UNKNOWN/MIXED classification does not prevent execution, and explicit profile selection overrides the default. Automatic post-processing extraction is not implemented; there are no surprise external calls.

POST `/extraction/runs` accepts strict `{profile_key, pages, mode}` with `mode=ensure|reextract`. Ensure deduplicates equivalent active runs and may reuse compatible completed results. If no completed result exists, repeating ensure returns the compatible failed/partial/cancelled run without creating new billable work; continuing requires explicit retry or re-extraction. Re-extract creates a new linked run after prior work settles; repeated equivalent requests while active return the active run. POST `/runs/{run_id}/retry` appends only unsuccessful keys in FAILED/PARTIALLY_COMPLETED runs, within the original attempt/call limits. Successful units are preserved. Completed/cancelled history is immutable: use explicit re-extraction for those runs. POST `/runs/{run_id}/cancel` settles active attempts before finalizing CANCELLED, retains successes and fences late responses. Repeated cancellation is safe; a completed run cannot be retroactively cancelled.

Run detail exposes profile kind, safe usage/admission counts, cancellation, retry eligibility, stale lease indicators and attempt history. Unknown tokens or prices stay null. Configured flat input/output rates require a recorded pricing basis; cached input is conservatively estimated at the configured input rate. The initial spending safeguard is a pinned provider-call admission budget plus bounded pages, input bytes, image pixels, output tokens, retries and timeouts; there is no claimed strict dollar guarantee when prices/usage are unknown. Interrupted or pre-call failed admissions consume budget rather than permitting unbounded retries. A crash around an external call may still incur a duplicate charge on recovery; unreported call boundaries remain explicit.

The existing extraction worker consumes `document_classification,document_extraction`; the new `extraction-scheduler` runs Celery beat. Both are necessary for automatic recovery. See the [6B handoff](PHASE6B_HANDOFF.md) for setup, exact guarantees, validation and the 6C extension contract.

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
