# PowerForge Phase 6 — Evidence, Candidates & Structured Extraction

**Status:** Approved architecture and implementation specification; implementation not started  
**Version:** 1.0  
**Date:** 2026-10-27  
**Baseline:** `main` at `9dc13be02d7c3e1b447c9aab5dae9590156aa733` (Phase 5 re-frozen)  
**Companion:** `decisions/ADR-008-evidence-candidate-extraction-architecture.md`  
**Target repository path:** `docs/specs/phase-6-evidence-structured-extraction.md`

> **Normative:** MUST / MUST NOT define binding Phase 6 requirements; SHOULD defines the recommended approach. This document is design authority, not a claim that Phase 6 has been implemented. The Phase 5 engineering registry (`registry-v1`) and historical ADRs remain authoritative for the existing canonical model. ADR-008 is authoritative for Phase 6 ownership and immutability boundaries. Within these boundaries, ordinary DTO/class naming and performance-oriented implementation choices can be made by Codex.

## 1. Mission and design invariants

Phase 6 converts immutable engineering source documents into **inspectable, evidence-linked, typed or explicitly unmapped candidate observations**. It does not decide which cross-document observations belong to the same physical asset, decide conflicts, validate study readiness, or alter the engineer-authored canonical model.

```text
Document + DocumentPage + versioned processing artifacts (Phase 2–3)
     ↓ document classification / extractor selection (Phase 4)
ExtractionRun + ExtractionWorkUnit attempts (Phase 6)
     ├── Evidence (source snippets / regions / table-cell support)
     ├── SourceGroup (source-local observations belonging together)
     ├── ExtractedTable (layout-preserving table JSONB)
     ├── ExtractionCandidate ↔ CandidateEvidence
     └── ExtractionAICall (technical and usage telemetry)
     ↓
Entity resolution (Phase 7) → topology extraction (Phase 8)
→ reconciliation (Phase 9) → validation (Phase 10) → review (Phase 11)
→ study integration (Phase 13)
```

1. The immutable `Document` is the source identity; `DocumentPage` is the stable page identity. Completed source-only results MAY be reused in all revisions containing the same document, subject to input/profile compatibility and revision-document membership.
2. A `RevisionDocument` supplies **viewing/authorization context**, not separate extracted truth. References to `Document`, exact completed `DocumentProcessingRun`, and derived `PageArtifact` versions MUST remain traceable.
3. Extraction **MUST NOT** write `EquipmentLineage`, `Equipment`, `EquipmentAttribute`, `ModelNode`, `ModelConnection`, canonical verification states, or any `ProjectRevision` engineering value. No implicit promotion/acceptance.
4. **`system_frequency` and `system_phase_count` are manual-only.** Phase 6 MUST NOT propose or set revision-wide values for them. Source statements such as “60 Hz” or “3Ø” MAY be extracted as equipment-specific values when registry-mappable; otherwise retain them as raw observations without a revision-metadata target.
5. Source-local grouping does not imply a physical identity match. **No association to canonical equipment, no guessed equipment tag, and no cross-document identity inference** in Phase 6. These are Phase 7 responsibilities.
6. A tagless nameplate, a free-standing rating, or an unrecognized attribute MUST still be retainable. Do not fabricate tags or discard observations solely for missing context.
7. An `ExtractionCandidate` is not an engineer-verified fact. Confidence is a limited quality signal and cannot trigger automatic canonical writes.
8. Original documents and completed extraction outputs are immutable; reruns create versioned records. Runtime statuses of in-progress runs/attempts are mutable only through controlled state transitions.

## 2. Scope, outputs, boundaries

**Included:** PDF/PNG/JPEG/TIFF as already supported by ingestion; native PDF text, OCR and visual inputs; equipment type/tag/name mentions; registry attributes; source-local groups including unidentified equipment; single-equipment attribute tables and multi-equipment schedules; normalized values and units; unrecognized claims; page/text/region/table-cell evidence; run history, retries, recovery, telemetry; basic read-only extraction/evidence UI; evaluation.

**Excluded:** revision-wide metadata proposals; equipment-to-canonical ID inference; entity merging/splitting; SLD symbol-to-topology connectivity (Phase 8); persistent cross-source conflicts (Phase 9); deterministic study validation findings (Phase 10); acceptance/verification workflows (Phase 11); protection function/settings or operating configuration canonical models until their design gates are approved; DWG/DXF, XLSX/DOCX ingestion; graph canvas; study-tool integration and reports. Existing Phase 4 classification is reused, not redesigned.

**Extraction priorities:** correctness and supporting evidence first; retain uncertain/unmapped observations rather than inventing values; prioritize recall within that conservative interpretation; benchmark cost and latency after accuracy.

## 3. Logical persistence model

All names below are proposed stable logical entities; migration/ORM names should follow repository conventions. Use PostgreSQL FK/unique/check constraints for structural integrity; preserve project/document/revision ownership without inventing a new `EngineeringModel` table.

### 3.1 `ExtractionRun`

One deliberate full-document extraction attempt against one immutable Document and a pinned, **completed** processing run. Core properties:

- `id`, `document_id`, `processing_run_id`, optional initiating revision-document/context reference for audit/display only; no dependency on a future mutable revision model.
- `extractor_version`, `schema_version`, `registry_version` (reference snapshot), `profile_version`, `profile_hash`, `input_identity_hash` (includes document+processing/artifact identity, page selection, configured extractor stages, prompt/model/provider profile, and any permitted context fingerprint).
- `provider`, `model`, prompt/profile identities (stage-specific details may live on work attempts and AI-call rows).
- `status`, queued/started/finished timestamps, page/unit progress counters, sanitized error summary, `requested_by` nullable while authentication is deferred; optional `reextracts_run_id` for deliberate new extraction lineage.
- Readable regardless of the originating revision's current mutable state, subject to document ownership and current route membership.

Run statuses: `PENDING`, `RUNNING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED`. Completion means **all required logical units** succeeded; partial completion means some required units succeeded and others exhausted/failed. `FAILED` means no useful required units succeeded. `CANCELLED` is explicit; an execution that has already completed is not retroactively cancelled. Reattempting failed units can transition a partially completed/failed run back to RUNNING while history is retained.

### 3.2 `ExtractionWorkUnit`

One **attempt** to process a stable logical work key such as stage + page/batch key within an `ExtractionRun`. Fields: `id`, `run_id`, `unit_key`, `stage`, optional page numbers/ranges and input-artifact references, `attempt_number`, optional `retry_of_work_unit_id`, `status`, start/finish/lease/heartbeat timestamps, sanitized error metadata and output counters. Unique `(run_id, unit_key, attempt_number)`; only one pending/running attempt per logical key. Work units may cover one page, a bounded page batch, or a specialized table-stage operation.

States: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`. A successfully committed unit is immutable apart from operational bookkeeping. A retry appends a fresh attempt for an unsuccessful **logical key**, not a duplicate of an already successful one. The selected effective result of each logical key is its committed successful attempt, if any; older attempts remain queryable as history. Partial **runs** consist of successful whole units plus failed/incomplete units, rather than publishing half-written candidate sets from a failed unit.

A unit completion MUST transactionally commit validated candidates, evidence, groups/tables, and its terminal success marker. External object writes may precede DB commit; orphaned derived artifacts should be safe for later cleanup. Prevent simultaneous completion/duplicate publishes by lease/lock and database uniqueness/idempotency. Retry does not silently replace or delete outputs from other successful units.

### 3.3 `Evidence`

A stable, immutable observation of source **text or visual/table location**, bound to its provenance: `id`, producing `work_unit_id`, `document_id`, `document_page_id`, optional `page_artifact_id`, `source_kind` (`NATIVE_TEXT`, `OCR_TEXT`, `VISUAL_REGION`, `TABLE_CELL`, etc.), short verbatim `source_snippet`, optional start/end offsets into a **versioned immutable text artifact**, optional normalized upright-page rectangle(s), optional table/cell locator, extraction method and created timestamp.

- Coordinates have top-left origin, normalized `x,y,width,height ∈ [0,1]`, with rectangles inside the page bounds. Missing/uncertain geometry MUST remain null; do not invent coordinates.
- Text offsets MUST reference the exact versioned text representation and a specified character-offset convention. Do not assume PDF extraction order or OCR text layout is universal.
- Text evidence is a short exact excerpt + source page/artifact/offset or region; complete text and images remain versioned artifacts in MinIO.
- Multiple distinct evidence records MAY support one candidate; one evidence record MAY support several candidates.
- Document, page, artifact, and work-unit ownership MUST be mutually consistent. No evidence may point to a different document/page from its run.

### 3.4 `SourceGroup`

A **source-local** grouping of candidate observations plausibly describing the same instance **within a document**; not `Equipment`/`EquipmentLineage` and not a Phase 7 match. Fields: `id`, `run_id`, producing work unit or source span, stable local grouping key, optional `equipment_type_hint`, optional **actually observed** `tag_text`, optional descriptive label and grouping evidence. Groups may be tagless. Grouping can reflect a single-equipment spec table, nameplate, or one multi-equipment schedule row; where the source is genuinely ambiguous, leave a candidate ungrouped.

Groups should be run-scoped (with provenance back to contributing units), so later table/page aggregation can preserve context across work-unit boundaries. No cross-document group ID is shared in Phase 6. A group must not be equated automatically with a canonical asset.

### 3.5 `ExtractedTable`

Fields: `id`, `run_id`, producing work unit, source page(s), optional table-level Evidence references, `layout_schema_version`, `table_kind`/orientation hint, and **versioned JSONB structure** preserving title, rows, columns, headers, merged-cell metadata if discoverable, source cell IDs and source locations. Avoid a relational table for every cell. Individual facts extracted from cells MUST still be independently queryable as candidates and linked to evidence/cell identifiers.

Supported orientations include (a) **one equipment with attribute names as rows**, (b) **equipment schedules with one equipment per row**, and (c) unclassified/mixed tables. Table layout interpretation must never forcibly merge distinct rows or separate one asset's specification into unrelated equipment. Multi-page provenance is supported when the extractor can determine the continuation; otherwise preserve separately and mark uncertainty.

### 3.6 `ExtractionCandidate`

Each candidate records **an interpreted source claim, not canonical truth**. Core fields:

- `id`, producing `work_unit_id`, `run_id`, `document_id`, optional `source_group_id`, optional `equipment_mention_candidate_id` (self-reference); cross-run/ownership constraints enforced.
- `kind`: `EQUIPMENT_MENTION`, `ATTRIBUTE_VALUE`, `UNMAPPED_OBSERVATION`. Structured tables/table rows are stored by `ExtractedTable` + groups, not duplicated as untyped candidate blobs.
- Source expression (`raw_text`/`raw_value`, `raw_unit`, optional observed equipment tag), optional registry `equipment_type_key` and `attribute_key` (never arbitrary *canonical* keys), `mapping_status`: `MAPPED`, `UNMAPPED`, `INVALID`, and bounded reason/error codes/explanation.
- If mapped: `value_type` and **typed candidate slots** aligned to registry semantics (`numeric_value` NUMERIC, `integer_value` BIGINT, `text_value`, `boolean_value`, `unit`). `ENUM` uses text and is registry-validated. Nonfinite numbers are invalid. Preserve original unit/expression and normalized canonical unit separately. Don't use JS Number for INTEGER; API JSON represents NUMBER/INTEGER as strings.
- Optional model/quality confidence score `[0,1]`, confidence band and method, no assumption of calibration. Absence of a meaningful score is null, not an invented 1.0.
- Immutable provenance/created time. Optional parser diagnostics may be bounded JSONB; **core query/filter fields remain relational**.

A `MAPPED` attribute candidate requires a justified equipment type context and a valid registry-v1 attribute/type/value/unit mapping. If the type/key is ambiguous, preserve the raw observation as `UNMAPPED`, not a fabricated canonical key. `INVALID` describes detected normalization/schema failure, while preserving safe raw source content. An attribute can have `source_group_id=null` and `equipment_mention_candidate_id=null`; these are not rejection conditions. Never manufacture a corresponding Equipment mention merely to satisfy a foreign key.

Do not create `MISSING` extraction candidates merely because a document omits an attribute; absence alone is not source evidence.

### 3.7 `CandidateEvidence`

Join entity with `candidate_id`, `evidence_id`, optional support role (`PRIMARY`, `SUPPORTING`, `CONTRADICTING` where directly source grounded), and stable ordering. Enforce same-run/same-document relationship through service checks and appropriate composite FK constraints. Evidence is not required to be exclusive to one candidate. Source-grounded mapped candidates SHOULD have at least one supporting citation; unsupported candidate output should be flagged and excluded from default trusted extraction views rather than presented as sourced truth.

### 3.8 `ExtractionAICall`

Per-provider-call audit/telemetry: `work_unit_id`, provider/model identity, prompt version/hash, schema version, request correlation ID, sanitized outcome/error, start/end/duration, input/cached/output token counts where returned, optional estimated USD cost **only when derivable using a recorded pricing version/assumption**. No secrets or full images/prompts/document text in routine logs or telemetry tables.

## 4. Relationships and immutable output publication

Logical relationships:

```text
Document 1—N ExtractionRun
DocumentProcessingRun 1—N ExtractionRun
ExtractionRun 1—N ExtractionWorkUnit [attempts]
ExtractionRun 1—N SourceGroup / ExtractedTable
ExtractionWorkUnit 1—N Evidence / ExtractionCandidate / ExtractionAICall
ExtractionCandidate N—M Evidence through CandidateEvidence
ExtractionCandidate N—0/1 SourceGroup
ExtractionCandidate N—0/1 equipment mention candidate (same run)
```

An extracted item must never cite a different project/document/processing context. Since `DocumentPage` is document-scoped rather than revision-scoped, use composite ownership checks (including FKs where available) to prevent mismatched page/artifact references. Cross-revision display verifies the requested `RevisionDocument` is included in the target revision and points to the same Document. Existing objects need not be copied upon revision inheritance.

For correctness when retrying, determine **effective visible outputs by selected committed successful work-unit attempt per logical `unit_key`**. Failed/obsolete attempts remain visible in history but are not blended into current candidate lists. The read API must expose run completion/partial status and effective unit coverage with candidates. Re-extraction yields a distinct run and its own result set.

## 5. Extraction pipeline and model contracts

1. **Precondition:** a completed Phase 3 processing run for the Document, with usable immutable analysis image/native text artifacts; otherwise return a clear precondition error/queue only appropriate prerequisite processing through established behavior.
2. **Choose profile and pages:** manual default initially; optional setting-controlled auto-extraction after processing. Explicit page ranges and document selection supported. Phase 4 classification is a routing *hint*, not a confirmed-type prerequisite; `UNKNOWN`/`MIXED_DOCUMENT` can still extract. Engineers MUST be able to override the classification-suggested extraction strategy by selecting an available extraction profile.
3. **Prepare inputs:** native text where reliable, OCR for missing/unusable text where needed, image/vision for layouts and drawings. Reuse versioned artifacts, don't mutate originals. OCR must expose reusable text and coordinates when supported; OCR engine remains provider-neutral.
4. **Extract independently by document:** specialized equipment-mention, attribute, and table extractors with Pydantic structured output. Preserve tagless observations, distinguish source-local grouping from cross-document matching. Avoid one enormous project-wide prompt.
5. **Validate and normalize:** validate structured outputs; use `registry-v1` mappings and deterministic unit normalization; preserve raw observations on mapping failure or ambiguity. Candidate type/value/units must not be guessed. Do not run the Phase 10 findings system.
6. **Publish:** atomically commit each successful logical unit's evidence/groups/tables/candidates; record model/prompt/artifact provenance. Aggregate run state and telemetry.
7. **Expose:** read-only results, evidence inspection, run history and retry. No canonical writes.

Phase 6 must not consult the current canonical model to match unknown source equipment. Phase 7 may use extracted records plus the revision's model for nonbinding identity hypotheses. If a future extractor configuration uses context external to a Document, it must be explicitly fingerprinted and cannot be reused in unrelated revisions without equivalent context.

Phase 7 identity-matching targets SHOULD include both existing canonical Equipment and other extracted equipment mentions; all associations remain nonbinding hypotheses until reviewed.

## 6. Orchestration, idempotency, failure recovery

- Reuse Celery, Redis, PostgreSQL and the existing dedicated extraction worker; keep AI credentials on workers, not browser/API/document processing workers. Start with OpenAI as first concrete model provider and fake deterministic providers for tests. Provider contracts in `packages/ai` must not leak SDK types into domain/persistence.
- Prevent concurrent equivalent live runs for one `input_identity_hash` with a DB partial unique index/lock; an intentional **Re-extract** may create a new run after prior completion. An `ensure` operation may return a compatible completed result, rather than issuing a new billable call.
- A manual **Retry** targets failed/cancelled/unfinished logical units and creates new work-unit attempt rows within the existing run; a complete unit is never resent. Handle worker crashes and expired leases with requeue/failure decisions. Retries obey bounded backoff and configuration limits.
- A hard worker death must not leave a run indefinitely RUNNING. Heartbeat/lease expiration and a recoverer are required. API/UI must distinguish stale, retrying, partial, failed and cancelled states.
- **Cancel** is cooperative: stop scheduling outstanding units, let already committed successful units remain, and mark request/run terminal according to established cancellation semantics. A cancellation cannot retroactively undo a published result.
- Limit pages, image resolution, concurrency, retries and run budget. Cost is estimated when price data are known; unknown cost is shown as unknown. Budget exhaustion yields a clear partial/failed result and preserves already successful work.
- Preserve historical unsuccessful attempts with sanitized failure metadata, not raw provider responses by default. Clean orphan derived blobs opportunistically, without deleting immutable originals.

## 7. API contract (proposed, versioned)

Use the existing revision-document URL namespace:

```text
/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}
```

| Method | Subpath | Purpose |
|---|---|---|
| GET | `/extraction` | Latest applicable completed/partial suggestion and current attempt summary; no side effects |
| POST | `/extraction/runs` | Start extraction of selected document/pages/profile; idempotent equivalent-live request |
| GET | `/extraction/runs` | Paginated attempt history |
| GET | `/extraction/runs/{run_id}` | Run metadata, stage progress, work-unit effective coverage/errors |
| POST | `/extraction/runs/{run_id}/retry` | Retry only unsuccessful logical units |
| POST | `/extraction/runs/{run_id}/cancel` | Request cooperative cancellation |
| GET | `/extraction/runs/{run_id}/candidates` | Paginated/filterable candidate results, including mapping status/group and evidence summary |
| GET | `/extraction/runs/{run_id}/tables` | Paginated table summaries; detail may use a separate route |
| GET | `/extraction/evidence/{evidence_id}` | Source snippet, page locator and signed artifact reference as needed |

Prefer consistency with existing document route status and error envelopes, response model allowlists, pagination and signed artifact URL APIs. Include explicit `run_id`, source identity, completeness status, selected work-unit coverage and raw/normalized fields; do not leak MinIO keys, model API tokens, or untrusted full documents in list payloads. Extraction operations create **document-scoped derived records**, even from a read-only revision; no revision/model mutation is authorized. The requested revision-document must resolve to the same included Document; historical run access obeys project/document membership, not merely knowledge of run UUID.

## 8. Web UX

Extend the existing Documents workspace with a document-level Extraction view. Provide **Extract**, **Re-extract**, **Retry failed units**, **Cancel**, attempt history and stage/progress displays. Let users browse candidate groups (tagged/tagless), individual mapped/unmapped/invalid observations, and extracted tables; selecting a value navigates to/highlights its Evidence text/page region in the existing viewer. Label AI outputs `Extracted candidate`, not `Verified` or `Model value`. Expose uncertainty and run partiality. Keep all extracted outputs read-only. Do not add an Accept/Merge/Verify workflow in Phase 6.

## 9. Precision, security, privacy

- NUMBER as JSON decimal string; INTEGER as base-10 JSON string (including values beyond JavaScript's safe integer range); backend typed values use Decimal/int, not float. Preserve source expression and units. Boolean PRESENT must be explicit; null is not false.
- Only original immutable source documents and versioned derivative artifacts are evidence sources. No raw source files are overwritten.
- Initial deployment does not require enterprise confidentiality/compliance infrastructure, but it MUST avoid secrets and raw document dumps in logs, isolate provider keys in workers, restrict object URLs, and make external model processing configurable/explicitly enabled.
- Set reasonable input/output sizes, OCR/image bounds, request concurrency, structured response validation, and bounded error messages. Do not trust OCR or LLM text as instructions.

## 10. Testing and evaluation

Use targeted unit tests plus meaningful live-integration/HTTP/worker tests on disposable infrastructure; do not reproduce full Cartesian matrices. Required checks include:

- DB migration head from current `0010_authoring_refinement`, schema/FK ownership, numeric constraints, read-only/immutable output invariants and upgrade of existing Phase 5 data.
- Run deduplication and deliberate re-extraction; successful unit reuse; partial run; targeted retry; duplicate task delivery; late completion; stale lease recovery; cancellation; transaction rollback with no partial unit publication.
- Source-only result reuse across inherited revisions and rejection of unrelated revision/document/page access.
- Tagged and tagless equipment, isolated attributes, single-equipment attribute tables, multi-equipment schedules and ambiguous cell/group relationships.
- Valid registry normalization and exact NUMBER/INTEGER/ENUM/BOOLEAN representation; preserve `UNMAPPED` and `INVALID` raw outputs; multiple competing candidate values retained.
- Native-text snippets and offsets, OCR/vision bboxes, table-cell references, multiple evidence links and same-document ownership.
- No AI/worker path modifies canonical Equipment/Attributes/topology or revision-wide manual metadata; no engineer verification or cross-document asset matching.
- UI run status/history and candidate/evidence navigation; fake deterministic provider; live provider calls opt-in and excluded from CI.

Evaluation corpus should include real anonymized/approved documents or fixtures: digitally generated and scanned transformer specifications, nameplates, breaker schedules, cable schedules, panel schedules, mixed/unknown documents, noisy/low-resolution text and untagged assets. Evaluate equipment mention recall, attribute exactness, registry mapping/normalization, source grounding, grouping accuracy, hallucination/false-candidate rate and cost separately. Initial policy favors conservative interpretation with uncertain/unmapped retention; numerical quality targets should be set from baseline measurements, not invented in this spec.

## 11. Implementation slices and exit gates

| Slice | Main deliverable | Gate |
|---|---|---|
| **6A** | Pure contracts; extraction run/work-unit, Evidence, SourceGroup, ExtractedTable, Candidate, CandidateEvidence, AICall persistence; migration and core read APIs | DB invariants, ownership, immutable outputs and read contracts tested; no live AI |
| **6B** | Asynchronous orchestration; provider/prompt/profile identity; unit retries/recovery/idempotency/cancellation; usage telemetry | Fake-provider end-to-end reliable processing and failure recovery |
| **6C** | Equipment mention/source-group extraction; typed attribute extraction, normalization, unmapped retention | Representative text/vision engineering examples; no canonical writes |
| **6D** | Table/schedule structure and candidate/evidence linkage | Both table orientations and row/cell provenance tested |
| **6E** | OCR/layout support and hybrid native-text/vision preprocessing | Scans, native PDFs and ambiguous layouts handled conservatively |
| **6F** | Extraction/evidence UI, history, page highlighting, evaluation harness | Read-only UX and reproducible labeled evaluation |
| **6G** | Regression, clean-stack, migration/upgrade, cost/performance and accuracy hardening | Full phase acceptance and docs; Phase 6 freeze |

Slices are boundaries, not instructions to implement all at once. Avoid introducing later-phase scope through convenience code. Historical Phase 4 classification remains separate. The protection/study-configuration domain needs its dedicated later ADR before dedicated settings extraction.

## 12. Completion criteria

Phase 6 is complete only if an engineer can select an already processed PDF/image, run/re-run extraction with traceable provider/artifact/prompt identity, inspect evidence for mapped and unmapped facts (including isolated tagless values), browse single-equipment and multi-equipment tables, recover/target-retry failed work, view partial results honestly, and obtain consistent candidate history. Document-scoped results remain reusable where appropriate. No extraction operation modifies canonical model fields or manually owned revision frequency/phase-count. Full backend/frontend/migration/worker regression and a documented real-engineering-document evaluation have passed.

## 13. Repo documentation integration

Place this file at `docs/specs/phase-6-evidence-structured-extraction.md` and ADR-008 at `decisions/ADR-008-evidence-candidate-extraction-architecture.md`. When implementing 6A, update `docs/ROADMAP.md`, `docs/EXTRACTION.md`, `docs/PROVENANCE.md`, `docs/PROJECT_STATUS.md` and link ADR-008. In those older roadmap/docs, **remove the now-obsolete suggestion to extract `system_frequency` / `system_phase_count` as revision-wide candidates**, and replace the preliminary old 6A–6G scope with the approved slices above. Do not claim implementation has begun until code is delivered.
