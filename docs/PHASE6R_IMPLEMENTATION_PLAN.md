# Phase 6R implementation plan

Status: **6R-A corrections ready for review. Begin 6R-B after review of the updated artifacts.**

Prepared: 2026-11-13. Authority: `docs/specs/phase-6r-extraction-redesign.md`, including its Evidence Identification and Source Localization Contract. If this plan conflicts with that specification, the specification wins.

Baseline inspected: local `main`, commit `dea1ed3b9423dec9c1834672519e16c2853add49` (`Phase 6F prompt + design prototypes`). The local `origin/main` reference points to the same commit; this review did not refresh the remote. At review start, the only working-tree change was the untracked Phase 6R specification. No Phase 6G implementation or migration is assumed present.

Approved clarification update: **2026-11-13**. Section 8.1 records the approved decisions and is reflected throughout the contracts, milestones and tests below. These architectural choices are settled; use reasonable engineering judgment for low-level implementation details within the approved strategy. Numerical quality targets remain provisional until representative live results, corpus sizes and evaluation procedures have been reviewed; freeze final gates before held-out evaluation.

6R-A handoff on `codex/phase-6r-ai-first-redesign`. The executable wire shapes, API DTOs, migration and cutover design are in the [v1 contracts](specs/phase-6r-contracts-v1.md). See the [retirement inventory](PHASE6R_A_INVENTORY.md), [ADR-009](../decisions/ADR-009-phase-6r-unified-extraction.md) and [evaluation baseline](../evals/phase6r/README.md). B wires the contracts into the existing coordinator and implements the first three migration revisions. C requires explicit authorization for the selected live sample and budget.

6R-A verification covered 57 contract, registry and layout tests, strict TypeScript checking, Ruff, native artifact digest and annotation offset checks, and static validation of the proposed single-head migration graph. The retirement inventory covers all 68 baseline extraction modules. The migration design still requires fresh-database execution in B and D. Provider acceptance and extraction quality are measured in C and F.

## 1. Fixed architectural direction

Implement a selective replacement from current `main`, on `codex/phase-6r-ai-first-redesign` when implementation begins. Reverify the base commit and working tree at that point and record any baseline drift in the handoff. Do not merge Phase 6G wholesale.

The processing order is fixed:

1. Existing document ingestion and processing produce immutable page artifacts.
2. Local native-text/OCR preparation and spatial enrichment produce page-scoped readings, geometry, reading order, table layout hints, and pinned artifact identities.
3. AI Call 1 (`EQUIPMENT_RECOGNITION`) identifies **source-local equipment observations** and proposes registry classifications, optional tags with explicit tag states, qualifications, and supporting evidence.
4. AI Call 2 (`ATTRIBUTE_EXTRACTION`) receives the exact successful Call 1 observations and the same pinned page context; registry-linked extraction for recognized types is primary, with a secondary bounded raw-unmapped extension for meaningful unsupported attributes within scope. AI proposes permitted enum values separately from source strings and assigns ownership to a Call 1 local reference or explicitly leaves it unassigned.
5. PowerForge validates structure, references, registry applicability, cited source occurrences, units, typed values, and persistence integrity. It does not reinterpret engineering meaning or infer ownership.
6. Immutable observations, evidence, attempts, and telemetry are reviewed in the existing Documents workspace.

There is one extraction family. A normal eligible page makes two sequential AI calls. Retries may add calls; there is no table-specific model stage, hidden repair call, document-wide extraction call, entity-resolution pass, or topology inference. Source preparation/layout remain local infrastructure, not competing extraction families.

Skip Call 2 only after successful Call 1 completion with zero eligible recognized equipment types. Persist `NO_ELIGIBLE_ATTRIBUTES` with zero-call telemetry; preserve unknown observations. This is never a substitute for a failed Call 1 or a reason to invoke an extra raw-attribute call.

Unknown, tag-less, repeated, conflicting, proposed, spare, and future observations remain inspectable with their qualifications. Extraction never creates or updates canonical equipment, attributes, revision system settings, or topology. In particular, `system_frequency` and `system_phase_count` remain manual-only. Matching tags never merge observations.

The rollout resets the **entire designated application database** and initializes the replacement schema from empty. There are no old-record readers, profile aliases, importers, backfills, dual schemas, or transitional legacy UI.

## 2. Repository findings that drive the plan

These are implementation conflicts to remove, not reasons to reconsider the agreed architecture.

1. **The current source projection deliberately splits prose from tables.** `enriched_runtime.py::projection` removes table-owned readings for Engineering and supplies table layout only for the Tables profile. Its replacement must include all relevant page readings and layout hints in both calls. Merely replacing prompts would leave schedules invisible to Call 1.
2. **The current converter is a second semantic interpreter.** `enriched_output.py` imports `interpret_equipment`, `interpret_attribute`, and `TERMINOLOGY`; `scope_for` determines ownership from neighboring lines and recognized headings. `interpretation_v1.py` re-derives types, labels, qualifiers, and source fields. None of that semantic acceptance machinery belongs in 6R.
3. **Current grounding rejects valid distributed evidence.** `enriched_grounding.py::ground` normally requires one engine line and compares a synthesized rendered expression. Phase 6R instead permits separate equipment, header, label, value, unit, and qualifier citations, each resolved independently.
4. **The current visual locator cannot represent the required fallback.** `powerforge_provenance/enriched_locations.py::EnrichedLocation` rejects a region on `VISUAL_REPORTED`. Its successor must accept bounded, explicitly approximate AI regions while keeping source-derived geometry authoritative for reading citations. Update database guards, publication checks, API serializers, and viewer together.
5. **Persistence and source enrichment share foundational tables.** Source preparation/layout models reference `ExtractionRun`, `ExtractionWorkUnit`, and `OutputRecord`. Migrations `0014` and `0015` extend the lifecycle created by `0011`–`0013`. Deleting the old migrations or `models.py` without replacing these dependencies would destroy reusable enrichment.
6. **Current candidate constraints do not fit the new raw/proposed/validated split.** `models.py::ExtractionCandidate` clears the accepted attribute key and typed slots for non-mapped results. 6R must retain the original registry proposal, raw units, qualifications, and diagnostics even when mapping or normalization fails. Typed accepted fields remain separate.
7. **The operation contract is deeply dual-family.** `operation_plan.py` has `families`, profile maps, and two planned extraction runs per document. `OperationItem` has `engineering_run_id`, `tables_run_id`, and separate ownership flags. The API register, operation readers, query keys, URLs, wizard, monitor, and history all consume this split.
8. **Canonical normalization is reusable but assumes an authoring default.** `registry.py::normalize_attribute_value` interprets an omitted input unit as the canonical unit. The extraction adapter must first establish an explicit source-unit policy; calling this function with an unknown unit would manufacture certainty. Keep the authoring API's existing behavior unchanged.
9. **Registry prompt metadata needs improvement.** `equipment_catalog()` currently supplies keys and display names; `EquipmentDefinition` has no descriptive prose field. Call 1 requires concise type descriptions. Attribute context already exposes types, units, enums, and notes, but must be restricted to the recognized type set without interpreting requirement rules as source facts.
10. **Legacy behavior is embedded outside obvious extraction modules.** `spatial_evaluation.py` imports both old converters and the old table evaluator; `spatial_evaluation_legacy.py` executes the previous prose pipeline. Package data includes frozen old execution-source snapshots, and the AI transport defaults to `SOURCE_PROBE`. These must be included in retirement, not left as hidden compatibility.
11. **The viewer currently highlights one selected region.** `document-viewer.tsx::evidenceRegionStyle` and `PinnedEvidencePage` consume one region and label it grounded. Phase 6R needs multiple separate source fragments and a distinct presentation for approximate AI-reported regions.
12. **Existing evaluation numbers are synthetic.** `evals/extraction/README.md` and `evals/tables/README.md` explicitly describe scripted development corpora, not measured live OpenAI accuracy. Their sources are useful; their old scores and acceptance semantics cannot establish 6R quality.
13. **Existing cardinality limits need explicit review for unified pages.** The enriched contracts cap equipment at 32 and attributes at 128, and the source projection has a 131,072-byte bound. Reusing these without measuring dense schedules could defeat comprehensive page discovery. A must set bounded, realistic 6R capacities and explicit overflow outcomes; extra table calls or silent truncation are not remedies.

Paths in the findings above refer to `packages/extraction/src/powerforge_extraction/` unless a different package or frontend path is named.

## 3. Concrete component disposition

`KEEP` preserves behavior; `ADAPT` retains useful infrastructure but changes its 6R-facing contract; `REPLACE` removes the existing implementation in favor of the new contract; `DELETE` has no production successor. Existing filenames may be reused where that makes ownership clearer; a retained filename does not imply a retained response schema or legacy behavior.

### 3.1 Keep unrelated application and source infrastructure

- **KEEP:** `packages/project/`, canonical `packages/engineering-model/`, `packages/topology/`, `packages/validation/`, and their authoring/revision/requirements behavior. Add the approved concise, versioned, registry-owned descriptive metadata; do not change existing canonical registry keys or behavior.
- **KEEP:** `packages/document-model/`, `packages/document-classification/`, `packages/document-processing/` ingestion, rendering, `processing.py`, `models.py`, storage implementations, and `native_spatial.py`.
- **KEEP:** local geometry/layout algorithms in document processing: `layout_derive.py`, `layout_grid.py`, `layout_readings.py`. Their table detection is source layout, not extraction interpretation.
- **KEEP:** provenance primitives in `spatial_base.py`, `spatial_geometry.py`, `spatial_identity.py`, `spatial_layout.py`, `spatial_offsets.py`, `spatial_sources.py`, and `layout_observations.py`; preserve immutable source ownership, frame transformations, exact offsets, OCR confidence, and structural uncertainty.
- **KEEP:** `services/document-worker/`, `services/validation-worker/`, `extraction_worker/openai_classification.py`, `extraction_worker/tesseract.py`, and classification's separate worker behavior.
- **KEEP:** existing project/revision authorization and mutability patterns, document uploads/downloads, classification, page navigation, shared UI primitives, `styles/design-tokens.css`, and unrelated equipment/topology workspaces.
- **KEEP:** `powerforge_ai/ocr.py` and unrelated AI provider contracts. Do not delete generic document-processing backfill code simply because extraction backfills are prohibited; remove only obsolete extraction-data backfill paths if found.

### 3.2 Extraction package inventory

All names in this subsection are under `packages/extraction/src/powerforge_extraction/`.

**ADAPT — reusable lifecycle and source foundations:**

- `controls.py`: retain run budgets, lease tokens, dispatch control, provider-start markers; update configuration types and ownership constraints.
- `dependencies.py`: retain attempt selection/retry concepts; replace dependency rules with the two 6R stages and the separate local preparation/layout path.
- `enqueue.py`, `errors.py`, `identities.py`: preserve queue delivery, safe errors, canonical serialization/hashing; remove obsolete imports, profile assumptions, and historical version wording.
- `orchestration.py`, `execution.py`: retain claims, admission, cancellation, heartbeats, backoff, crash recovery, and fenced completion; replace old dispatch trees and remove table-empty-output handling and probe execution.
- `operations.py`, `operation_plan.py`, `operation_models.py`: retain revision-scoped consent, preview hashes, idempotent requests, included-document checks, operation ownership, and cancellation scope; use one unified extraction child per document plus local preparation dependencies.
- `enrichment_execution.py`, `enrichment_models.py`, `enrichment_prepare.py`, `enrichment_profiles.py`, `enrichment_service.py`: retain native/OCR behavior and explicit overrides; reconnect to the rebuilt lifecycle and version identities honestly if their execution implementation changes.
- `layout_execution.py`, `layout_models.py`, `layout_profiles.py`, `layout_service.py`, `layout_sources.py`: retain local spatial execution and exact preparation reuse; reconnect to the clean schema/profile reader without resurrecting extraction families.
- `enriched_sources.py`: retain compatible `selected_snapshot`, `bound_snapshot`, and `load_bound` behavior—exact successful producers, hash/size validation, image identity, and source I/O outside database locks. Rehome as a neutral source loader if useful.
- `registry_context.py`: retain authoritative registry lookups; replace incomplete descriptions and unrestricted projections as specified below.
- `__init__.py`: export only active contracts and infrastructure.

**REPLACE — active 6R contracts and publication:**

- `contracts.py`, `observations.py`, `enriched_contracts.py`, `enriched_observations.py`: one versioned 6R contract set; no inheritance from old Engineering/Tables response classes.
- `profiles.py`, `production_profiles.py`, `enriched_profiles.py`: one active extraction profile/manifest and a same-contract test provider; retain separately purposed local enrichment profiles. Remove all old extraction-key parsers and version branches.
- `stage_runtime.py`, `enriched_runtime.py`, `enriched_planning.py`, `enriched_input.py`: unified page planning, source projection, immutable Call 1 context, and bounded model input.
- `engineering_stages.py`, `engineering_output.py`, `enriched_output.py`: replace with the two AI stages and a thin observation converter; no vocabulary-based reclassification or deterministic association.
- `grounding.py`, `enriched_grounding.py`: replace with page-scoped reference resolution and bounded text checks. Salvage exact source lookup/geometry construction helpers only after removing one-line and engineering-scope rules.
- `models.py`, `persistence.py`, `enriched_publication.py`, `enums.py`: clean 6R observations/evidence/stage publication, reusing lifecycle structure and transaction fencing. Remove `ExtractedTable`, table output FKs, old locator alternatives, and frozen-profile guards.
- `fake.py`, `enriched_fake.py`: one 6R fake provider using the same request/response schema and dependency path as production; no old probe/engineering/table fake modes.
- `eval.py`, `evaluation.py`, `evaluation_scoring.py`: unified 6R corpus/runner/scorer. Reuse evaluation methodology only where it preserves the new denominators and independently authored gold.

**DELETE — superseded semantic and table extraction implementations:**

- `interpretation.py`, `interpretation_v1.py`, `terminology.py`: remove the deterministic semantic interpreter and alias gates. Reuse canonical unit/registry functions directly; do not copy semantic rules into a new validator.
- `engineering_sources.py`: remove the old raw-page-only extraction source path after unified enrichment binding is in place.
- `enriched_tables.py`.
- `table_stages.py`, `table_runtime.py`, `table_execution.py`, `table_profiles.py`, `table_input.py`, `table_output.py`, `table_observations.py`, `table_grounding.py`, `table_semantics.py`, `table_sources.py`, `table_layout.py`, `table_fake.py`.
- `table_eval.py`, `table_evaluation.py`, `table_evaluation_scoring.py`: replace their useful claim coverage within the unified evaluator; no separate table-extraction CLI.
- All existing extraction prompt/input files in `prompts/`: `attribute_extraction_v1.txt`, `engineering_common_v1.txt`, `enriched_v1.txt`, `equipment_recognition_v1.txt`, `openai_input_v1.json`, `source_probe_v1.txt`, `table_common_v1.txt`, `table_input_v1.json`, `table_interpretation_v1.txt`, `table_reconstruction_v1.txt`. Add explicitly versioned 6R resources instead.
- Old extraction identity archives under `runtime_resources/page_v1/`, `page_v2/`, `table_v1/`, `publication_v1/`, and `enriched_v1/`. They must not survive merely to preserve old hashes. Keep or regenerate `preparation_v1/` and `layout_v1/` only as active local-enrichment identity resources, with current version/hash validation and installed-package parity.

6R-A must turn this inventory into a checked import/consumer manifest, including dynamic imports and resource loading. 6R-E must account for every listed file as retained, replaced, or removed and identify any additional shared consumers discovered during implementation.

### 3.3 Worker, provenance, configuration, and packaging

- **ADAPT:** `powerforge_ai/extraction.py`: keep provider-neutral request/result/error/usage boundaries, remove `ProbeResult` and implicit `SOURCE_PROBE` defaults, require the explicit 6R stage/schema. Add bounded provider-call identity/diagnostics needed for audit.
- **ADAPT:** `extraction_worker/openai_extraction.py`: preserve one bounded SDK call, deployment/credential gates, `max_retries=0`, safe error categorization, and usage collection. Replace profile-dependent input selection with one 6R transport. Preserve source and model-output data as untrusted input.
- **ADAPT:** `extraction_worker/extraction_tasks.py` and relevant `celery_app.py` wiring: one extraction dispatch path, retained local enrichment and classification queues, recovery, deadlines, and cancellation.
- **REPLACE:** `powerforge_provenance/enriched_locations.py` with the 6R locator contract; retain generic `Region` geometry validation in `locations.py`. Remove old extraction-only `SourceLocation` acceptance where superseded.
- **DELETE after consumer check:** unused legacy `powerforge_provenance/evidence.py::EvidenceRef` and its export if it has no unrelated consumer; this is not a mandate to rewrite unrelated provenance contracts.
- **ADAPT:** `extraction_worker/evaluation_live.py` for unified opt-in runs. Delete `spatial_evaluation_legacy.py`; decouple `spatial_evaluation.py` from obsolete extraction replay while keeping local OCR/layout evaluation and useful `spatial_evaluation_gold.py` / `spatial_evaluation_scoring.py` behavior.
- **ADAPT:** `packages/shared/.../config.py`, `.env.example`, `docker-compose.yml`, extraction and worker `pyproject.toml`, relevant Docker/package resources and CI. Remove table-family settings, old probe/profile options, obsolete package-data patterns, and `powerforge-eval-tables`; expose one unified configuration. Do not retain environment-variable aliases for old extraction behavior.

### 3.4 API disposition and proposed resource interface

Preserve revision-document scoping under the existing extraction route prefix. The names below are a proposed 6R interface to freeze in A; they do not imply old payload compatibility.

- **ADAPT:** `routers/extraction.py`, `schemas/extraction.py`, `services/extraction_service.py`: unified summary, paginated runs, run detail/coverage/attempts, candidates, evidence detail, bound sources, retry and cancellation. Candidates represent source-local equipment and attributes; they are not canonical equipment API objects.
- **ADAPT:** `routers/extraction_operations.py` and `services/extraction_operations.py`: sources → preview → consent-bound start; operation detail/recent/retry/cancel. Remove `families`, profile maps, and `engineering`/`tables` retry branches; retry addresses a failed stage/page or resumes pending work under the pinned operation policy.
- **REPLACE internals:** `services/extraction_register.py` and `services/evidence_groups.py`: one extraction status and effective-run selection; the unified candidates endpoint exposes searchable group summaries and paginated members using persistent source-local equipment identity, plus a run-scoped unassigned bucket. See the [candidate browser contract](specs/phase-6r-contracts-v1.md#two-level-candidate-browser).
- **REPLACE:** `services/enriched_evidence.py`: return ordered, role-bearing evidence fragments with independently resolved locations, artifact identity, and signed access. Reading evidence must never launch extraction or enrichment.
- **DELETE:** `GET /runs/{run_id}/tables`, `TableList` / old table-layout responses, raw-table result readers, `family` query arguments, dual `engineering_run_id`/`tables_run_id` selection, old profile-list entries and old start payloads. If `/profiles` remains for capability metadata, it exposes only the active 6R extraction profile; no selector for old execution modes.
- **APPROVED start boundary:** operation creation is the single supported user-facing extraction start path, owning source selection, preview, consent and preparation. Remove the old direct user-facing `POST /runs` start route; internal run creation remains part of operation/runtime infrastructure, not a second public start API.
- **KEEP/ADAPT:** `routers/enrichment.py` and its service for genuine local preparation management. Preserve execution-purpose isolation and optional OCR controls; it is not a second AI extraction API.
- Retain authorization checks for every selected run, page, observation, and signed artifact; revision mutability checks for writes; pagination limits; stable safe error categories; and unavailable-artifact behavior. No default fallback to a different run or current page image when the pinned evidence is unavailable.

### 3.5 Frontend disposition

Retain the Phase 6F interaction structure and shared components. Update only extraction-related contracts, views, state, and copy.

- **REPLACE contract shapes:** `apps/web/src/lib/extraction.ts`, `extraction-operations.ts`: one run identity/status, stage attempts, equipment observations, raw/normalized attributes, evidence fragments and quality. Remove `RunFamily`, paired runs, `RawTable`, old family labels, and obsolete query parameters.
- **ADAPT:** `query-keys.ts`, relevant `query-hooks.ts`, `document-presentation.ts`, `workspace-navigation.ts`, `document-actions.ts`, and extraction consumers in `revision-documents.tsx`, `document-inspector.tsx`, `document-list.tsx`, and `document-workspace-toolbar.tsx`. Keep unrelated navigation/polling behavior. Update invalidation and deep links to one selected 6R run.
- **ADAPT:** `start-extraction-wizard.tsx`: one “AI Engineering Extraction” action; preserve page/document selection, automatic preparation, advanced OCR override, preview, consent and duplicate-submit protection. Remove family toggles and dual-run estimates.
- **ADAPT:** `extraction-operation-panel.tsx`, `document-extraction-panel.tsx`: unified progress with preparation and the two page stages visible as steps; preserve partial outcomes, retry/cancel, source availability, and read-only behavior.
- **REPLACE extraction contents, retain layout:** `extraction-evidence-panel.tsx`, `extraction-evidence-ui.tsx`: source-local equipment list including unknown/tag-less observations and explicit qualifications; owned, unassigned and bounded raw-unmapped attributes; original qualifiers, conflicting assertions, original enum source strings and AI-proposed registry enums; separate mapping/association/source-quality indicators. No automatic canonical authoring action.
- **ADAPT:** `document-viewer.tsx`: multiple exact fragment highlights; bounded approximate AI-region styling and label; page-only context for unresolved citations. Keep pinned-image loading, signed-URL refresh, rotation/zoom and keyboard navigation. Never relabel approximate coordinates as grounded/exact.
- **ADAPT:** `extraction-run-history.tsx`: only new unified runs, their two stages/attempts, local source bindings, usage/cost, and actions. Remove Engineering/Tables family sections, paired historical selections, `getRawTables`, `RawTableOutput`-style behavior and table-cell result rendering. Local preparation details may be expanded under a run rather than represented as an extraction family.
- **KEEP:** responsive drawers, shared UI primitives/tokens, document metadata/classification/editing, projects/revisions, equipment authoring, and topology screens.
- **ADAPT:** extraction-specific files in `apps/web/design-reference/v1/` and visual fixtures. Remove old extraction screens/copy; preserve unrelated design references. Do not rebuild the design system.

### 3.6 Tests and documentation

- **KEEP:** document/storage/classification, native/OCR/layout, registry/unit/requirements, canonical engineering-model, topology, project/revision, and unrelated frontend tests. Names beginning `test_engineering_` are not all extraction tests: registry, authoring, constraints, concurrency, effective values, and service tests protect retained functionality.
- **ADAPT to 6R:** generic `test_extraction_orchestration.py`, `test_extraction_recovery_fairness.py`, `test_extraction_storage_recovery.py`, `test_extraction_celery_integration.py`, `test_extraction_operations.py`, and relevant integrity tests. Preserve safety properties while replacing old fixture/profile contracts.
- **REPLACE:** old extraction-specific engineering observation/context/grounding/interpretation/publication/adapter/evaluation tests, `test_enriched_*`, `test_extraction_contracts.py`, extraction persistence/API tests, and `test_phase6f_read_api.py`. Preserve useful negative cases in the new suite; do not port expectations requiring semantic aliases, single-line grounding, or old schema hashes.
- **DELETE after replacement coverage:** old `test_table_*`, table support workers, `legacy_extraction_support.py`, obsolete engineering/extraction fixtures and old profile identity snapshots. Preserve their source fixtures and useful wrong-row/conflict tests in the unified corpus.
- **REPLACE:** migration tests for `0011`–`0017` with tests for the new graph and current integrity. Keep coverage of retained enrichment constraints; do not keep old migration IDs or upgrade-from-old-data assertions solely to make tests pass.
- **ADAPT frontend tests:** `start-extraction-wizard.test.tsx`, `document-viewer.test.tsx`, `revision-documents.test.tsx`, document-presentation/navigation/query tests, plus focused new operation/evidence/history coverage.
- **REWRITE:** `docs/ARCHITECTURE.md`, `EXTRACTION.md`, `DOCUMENT_PIPELINE.md`, `PROVENANCE.md`, `ROADMAP.md`, `PROJECT_STATUS.md`, relevant `DEVELOPMENT.md`/README instructions, and `decisions/ADR-008-evidence-candidate-extraction-architecture.md` or its explicitly superseding current ADR.
- **REMOVE superseded active material:** `docs/specs/phase-6-evidence-structured-extraction.md`, obsolete `PHASE6A_*` through `PHASE6F_*`, corresponding old extraction prompts, and any old Phase 6G material actually present when implementation starts. Redirect current links first; preserve unrelated UI/source-processing guidance by incorporating it into current docs. Git history is the historical record.

## 4. Major interfaces to freeze in 6R-A

The DTO names below describe responsibilities, not a final API schema; the approved AI stage names and `NO_ELIGIBLE_ATTRIBUTES` outcome are fixed. A must produce concrete JSON Schema/Pydantic definitions, database representations, TypeScript DTOs, bounded limits, and valid/invalid examples for each.

### 4.1 Pinned page context

`PinnedPageContext` contains document/page/processing IDs; preparation and spatial result IDs and hashes; original analysis-image descriptor and coordinate frame; reading IDs with native/OCR text and provenance; source offsets and geometry where available; modality/confidence/conflict indicators; order/alignment; and table-region/cell/header relationships as layout hints.

Reading IDs are scoped by the pinned page and enrichment version. A bare matching string or reused local reading ID from another page is never sufficient. Use existing source selection/alignment rules where compatible; expose retained alternate/conflicting readings or their conflict metadata rather than silently converting a preferred reading into semantic truth. Never filter readings because they belong to a table.

Both AI calls receive the same source-context identity and image, within explicit limits. Record coverage and failure diagnostics for oversized pages. Do not silently drop the end of a schedule, silently crop an image, or add extra extraction calls to circumvent limits. Dense-page limits must be chosen using the evaluation corpus.

### 4.2 Call 1: equipment observations

Request: pinned page context, full permitted registry type catalog with concise versioned registry-owned descriptions, observation policy, schema/prompt/profile/model/registry identities. Hash the descriptive metadata with the prompt input identity; preserve canonical keys and behavior.

Response: page reference and bounded equipment list. Each observation includes unique response-local reference, raw source description, nullable registry type proposal, optional observed tag, `PRESENT | ABSENT | UNREADABLE | AMBIGUOUS` tag state, explicit `INSTALLED | PROPOSED | FUTURE | SPARE | REFERENCE | LEGEND_ONLY | UNKNOWN` qualification with original source wording, AI uncertainty/reason where applicable, and role-bearing evidence citations. Legend-only content must not fabricate installed physical equipment or imply topology.

Validate local-reference uniqueness, page scope, bounded fields and tag-state consistency. A legal registry proposal is accepted as the AI's proposal without checking a terminology alias. Unknown/unsupported proposals cannot become mapped types; retain raw source description and proposal diagnostics. Persistent IDs distinguish separate observations even if their tags match.

Persist an immutable, ordered **validated Call 1 result**, including unmapped observations and diagnostics, independently of any UI grouping. Call 2 must not reconstruct its input from a lossy candidate projection or current database registry defaults. Bind it to the successful Call 1 work attempt and result hash.

### 4.3 Call 2: attribute observations

Request: same pinned page context; exact validated Call 1 observations; only attribute definitions for recognized types on that page. Definitions include exact keys, data types, supported units, allowed enums, and relevant notes; do not send requirement defaults as values to fill.

Response: bounded assertions with their own response-local reference, nullable Call 1 equipment reference, proposed permitted attribute key, exact raw value/unit strings, raw label and qualifiers, association certainty/reason, and evidence. Enum assertions include both the original source value string and a separate AI-proposed exact permitted registry enum value. AI owns semantic enum interpretation; PowerForge validates the proposal against the applicable attribute's permitted values without independently interpreting engineering synonyms. Simple lexical boolean conversions may occur in PowerForge while preserving raw strings. Keep distinct conflicting assertions, ranges and multiple ratings separate and faithful to source; never select an arbitrary scalar.

Check membership against the permitted per-type attribute set and the referenced observation. Do not substitute a type, infer an owner, choose the closest tag, or create a key. An explicitly unassigned assertion remains visible as `UNMAPPED`; low confidence in a valid specified owner is a separate association indicator. Attributes attached to an unmapped type cannot become registry-mapped by guessing a type in Call 2.

Include the approved bounded raw-unmapped assertion extension in the same Call 2 response. It is secondary to registry-linked extraction and preserves meaningful unsupported source attributes already within scope, with raw label/value/unit/qualifiers, evidence and a supported existing equipment reference or null, without inventing registry keys. A sets explicit count, field-size and total-output limits. Overflow fails the stage rather than silently dropping content. The extension cannot introduce unrestricted discovery, extra AI calls, deterministic semantic mapping, or bypass the zero-eligible-types skip.

### 4.4 Evidence identification versus localization

`EvidenceCitation` is an AI assertion: role such as EQUIPMENT, LABEL/HEADER, VALUE, UNIT, QUALIFIER or CONTEXT; reading reference where possible; optional verbatim fragment; or page-scoped reported visual region/text when no reading can be cited.

`ResolvedEvidenceFragment` is PowerForge's localization result: pinned source identities, modality, exact source text, offsets, source-derived region(s) where available, original AI role, localization outcome and bounded diagnostics.

Resolution rules:

1. Resolve reading references only in the exact bound page artifact set.
2. Verify ownership and source integrity before returning source text or signed URLs.
3. Where quoted text is supplied, compare against the claimed reading occurrence with bounded whitespace tolerance. Do not use document-wide numeric matching or punctuation/semantic rewriting to claim an exact quote.
4. Preserve separate fragments and coordinates. A table designation, header, and value can support one assertion without becoming a fabricated continuous sentence.
5. Enable unique, bounded, page-local verbatim quote matching against the pinned source when reading IDs are missing. Multiple matches remain unresolved; never select the first match. Keep source text offsets when available, but do not render a precise spatial highlight without source-derived coordinates. Do not use fallback to conceal a fabricated or foreign reference.
6. Validate an AI visual region against the pinned image frame and bounds; keep it explicitly `VISUAL_REPORTED`. It cannot override known source-derived reading geometry.
7. Missing/non-unique positioning produces `UNRESOLVED` page context. Missing or foreign reading references never become resolved evidence. Retain otherwise usable raw observations with unsupported citations removed and diagnostics, according to the A validation policy.

Localization is `RESOLVED | VISUAL_REPORTED | UNRESOLVED`. Text-check quality and AI association certainty remain independent. A resolved source position proves neither that OCR recognized the printed text correctly nor that the model chose the right equipment. `TEXT_VERIFIED`, if used, means matched to pinned source text—not engineer verified.

### 4.5 Validation and publication

Use separate steps with inspectable results: response admission → reference admission → source localization/checks → registry applicability → raw-value parsing → canonical unit normalization → typed/storage validation → immutable publication.

- Equipment `MAPPED`: supported registry type; equipment `UNMAPPED`: no supported type. Tag absence does not prevent mapping.
- Attribute `MAPPED`: supported applicable interpretation and valid typed normalization, with a valid specified equipment observation. Weak evidence/association certainty is recorded separately.
- Attribute `UNMAPPED`: no supported registry interpretation, establishable ownership or faithful typed normalization, including missing/ambiguous dimensional units; retain raw assertion, proposal and a specific reason.
- Attribute `INVALID`: supported interpretation exists, but value/unit/type/storage rules fail; preserve proposal and raw fields, publish no misleading normalized value.
- Malformed stage envelopes, duplicate identifiers, truncation or capacity overflow fail the stage. Otherwise valid observations survive individual citation failures with unsupported links removed and diagnostics recorded. Never guess missing references or ownership; unsupported ownership stays unassigned. Citation/reference diagnostics are not automatically invalid-unit errors.

Canonical `normalize_attribute_value`, supported-unit lookups, exact Decimal handling and integer bounds are reused behind the approved extraction boundary. Never assume dimensional source units from canonical defaults: a cited source header can establish units; missing/ambiguous units are `UNMAPPED` with a specific reason, and unsupported units under an otherwise valid interpretation may be `INVALID`. Preserve qualifiers, ranges and multiple ratings; normalize only when the supported representation preserves the assertion faithfully. Preserve raw information as unmapped when it cannot. Validate the separate AI enum proposal for membership, retaining its original source string; simple lexical boolean conversions are permitted. No local engineering synonym classifier, arbitrary scalar selection or default-value filling is introduced.

`PublicationBundle` carries observations, evidence fragments/links, stage diagnostics, immutable stage result, output hash, and source/result bindings. Preserve the existing pattern of artifact verification outside database locks followed by an atomic, lease-fenced transaction that rechecks ownership and identities. Publication idempotency is for the same logical stage result; it is not physical-equipment deduplication.

### 4.6 Execution and audit

One run per selected document/page set has page-level `EQUIPMENT_RECOGNITION` and `ATTRIBUTE_EXTRACTION` work units. Each Call 2 attempt references the exact successful Call 1 attempt and result hash from its run/page. Retry Call 2 without recalling successful Call 1; re-extraction creates a new run and new observations. A successful Call 1 with zero eligible recognized types produces an explicit `NO_ELIGIBLE_ATTRIBUTES` result and zero Call 2 provider calls; raw unknown equipment remains published. Encode this clearly in stage outcome, coverage and history without adding an AI stage.

Retain durable consent/preview identity, request idempotency, call admissions, timeouts, cancellation and stale-attempt fencing. A worker crash after provider acceptance may leave provider outcome unknown; do not promise exactly-once provider charging. Record unknown outcomes honestly and require the normal retry/budget policy for another attempt. Exactly-once committed stage publication remains the target.

Record per stage/attempt: source binding, registry/prompt/schema/profile/model identities, call identifier where available, request/result hashes, measured input/output usage, duration, failure/refusal/overflow, accepted/rejected observation counts, and localization diagnostics. Preserve bounded, access-controlled stage results and audit information; A specifies practical retention limits and access enforcement. Do not log credentials, signed URLs, unbounded responses, or hidden model reasoning. Cost estimates require measured usage and versioned pricing; otherwise report unavailable rather than zero or a fabricated estimate.

## 5. Database and migration strategy

### 5.1 Proposed clean-install graph

Keep `0001`–`0010` where they still construct the intended project/document/canonical-model schema. Replace `0011`–`0017` with a new, explicitly named 6R chain rooted at `0010_authoring_refinement`. Do not create an upgrade path from old `0017`, stamp a populated database into the new head, or import unmerged `0018`.

Suggested migration responsibilities, with exact revision IDs finalized in A:

1. Generic run/work-attempt lifecycle, execution controls, provider-call audit, and immutable stage-result records.
2. Retained local enrichment/page results/artifacts, preparation receipts, spatial results, and exact run-to-source bindings, adapted from useful `0014`/`0015` behavior.
3. 6R observation/evidence publication and ownership/immutability constraints.
4. Unified revision-scoped operations, request idempotency and child-run references.

This keeps unchanged pre-extraction application definitions while ensuring obsolete extraction tables are never created by the new chain. A single replacement baseline is an alternative only if dependency inspection shows the smaller replacement graph is impractical; it must not rewrite unrelated model behavior.

### 5.2 Required schema content

- Retain compatible concepts for runs, work attempts, execution controls, and AI-call records, with only active local-source and unified extraction purposes/stages.
- Add durable immutable stage-result storage sufficient to reproduce the exact validated Call 1 context and audit Call 2. Avoid relying on `candidate.diagnostics` as the only copy of the prerequisite contract.
- Use equipment and attribute observation identities, either explicit typed tables or rigorously constrained kinds in a unified candidate table. **Recommended:** retain the candidate storage foundation with explicit page, local-ref, tag-state, qualification, proposal, accepted mapping, owner, and independent-quality fields; freeze the precise layout in A.
- Evidence stores independent fragments/locators, source identities, original role assertions, exact/approximate localization distinctions and diagnostics. Candidate-to-evidence links preserve order and roles.
- Replace source grouping where it encoded semantic scopes. UI grouping is by the persisted equipment observation ID, with unassigned assertions independently visible.
- Operation items have a local preparation reference and one extraction reference/ownership flag. There are no `tables_run_id` or dual-family fields.
- Composite constraints protect same document, processing run, page, extraction run and stage-result ownership. A same-run but different-page equipment/evidence reference is invalid.
- Constrain allowed statuses, nullability/typed slots, tag consistency, finite numeric values, integer storage, JSON/response bounds, valid regions, unique local refs within stage/page, immutable successful results, and at most one effective successful publication per logical stage.
- Do not add uniqueness on observed tag, equipment type/rating, or physical identity.
- Do not retain `extracted_tables`, extracted-cell FKs, old table kind enums, v1/v2 extraction locator branches, historical profile guards, or compatibility triggers. Source-layout tables/cells inside local spatial artifacts remain legitimate.

### 5.3 Sequencing constraint between B and D

The specification places final clean-schema publication work in D, but B's durable fake end-to-end gate needs run, source binding, and prerequisite-result persistence already present. Resolve this by freezing the complete design in A, implementing the **minimum active execution/source/stage-result schema in B**, and completing candidate/evidence normalization/publication constraints and final clean-install verification in D.

All intermediate databases are disposable isolated test installations. B is not a deployable dual-runtime release. Never keep old profile execution to bridge the milestone gap. By D, the final migration graph must build the complete application from empty without obsolete extraction structures.

### 5.4 Destructive rollout boundary

Implementation and integration tests use explicitly isolated fresh databases. They do not reset the current development database by implication.

Before F cutover, the operator identifies and authorizes the exact host/database or fully isolated schema, environment, ownership, affected services, and full data loss. Stop API writers, schedulers, document/extraction/validation workers and queue producers; take any requested backup outside the target; drop/recreate the full designated application database including migration state; then apply the new chain and approved bootstrap records.

Projects, revisions, canonical engineering/topology rows, document metadata, extraction/source histories, operations and locally stored accounts are all removed if present. Source files must be re-uploaded or explicitly re-seeded. Never restore legacy application rows into the 6R schema.

Inventory and separately authorize PowerForge-owned object prefixes/buckets, queues, Redis keys and caches that must be cleared. Do not use a shared-bucket wipe, shared Redis flush, or broad volume deletion. Block stale workers from republishing after reset.

Recovery is either prior code plus an approved compatible full pre-reset database backup, or a fresh 6R environment/forward fix. A code-only rollback is not a recovery plan. `database/seeds/README.md` is currently only a placeholder; A must identify real bootstrap requirements rather than assuming a working seed command exists.

## 6. Milestone delivery plan

Order: **6R-A → 6R-B → 6R-C → 6R-D → 6R-E → 6R-F** under the approved implementation strategy and clarifications. Evaluation design starts in A; representative authorized real-world documents support early live validation in C; a separate held-out benchmark and cutover occur in F. Review representative live results, corpus sizes and evaluation procedures before finalizing numerical gates; freeze them before held-out evaluation. Frontend contracts are designed in A, backend read contracts stabilize in D, and production UI integration finishes in E. Each milestone ends with a handoff stating changes, tests actually run, remaining low-level details and next dependencies.

### 6R-A — Architecture, inventory, and acceptance baseline

**Dependencies:** the approved strategy and section 8.1 clarifications; verified `main` base. Authorized real sources are needed for early C validation and F evaluation, not to complete repository inventory.

**Work and deliverables:**

1. Create the implementation branch and record exact base; preserve the supplied authoritative specification.
2. Produce the final file/import/resource/API/UI disposition manifest from section 3, including dynamic imports, SQL functions/triggers, CLI entrypoints, packaged resource identities, test helpers and documentation links.
3. Freeze the two request/response contracts, evidence-role/locator contract, status/rejection policy, exact upstream-result contract, scope/size limits and registry descriptions/projections.
4. Encode the approved installed/proposed/future/spare/reference/legend-only/unknown qualifications, AI enum proposal plus raw source strings, source-supported units/qualifiers, and bounded raw-unmapped extension without adding identity or topology inference.
5. Freeze schema/clean migration responsibilities, execution-purpose boundaries, atomic publication and cancellation/retry semantics. Encode `NO_ELIGIBLE_ATTRIBUTES` and the fixed stage names explicitly.
6. Define unified API/TypeScript shapes and Documents states, including exact/approximate/unresolved evidence and unassigned/conflicting observations.
7. Create the evaluation case inventory, gold schema, metrics/denominators, provisional numerical targets and authorized-source/live-run requirements. Separate the preliminary C corpus from the held-out F benchmark and plan final gate review after preliminary live results. Capture a reproducible old-baseline report where useful before deletion, or reference the exact old commit for an isolated later comparison.
8. Write the superseding architecture ADR, destructive-reset design/runbook outline, and decision log. Make sections 4/5 concrete in executable contracts and schema design, applying section 8.1's settled decisions without reopening them.

**Focused checks:** contract examples cover every tag state, unknown/tag-less equipment, separate table/header/value citations, unassigned attributes, conflicting raw values, malformed/foreign references and bounded overflow. Trace every field through prompt → parser → DB → API → UI. Verify registry keys against code, not illustrative spec labels. Validate the proposed Alembic dependency graph on paper/static metadata and the deletion manifest against imports. No live provider or database reset is required.

**Acceptance:** no unresolved contract contradiction affecting implementation; ownership/localization/mapping are distinct; no legacy execution or Phase 7 behavior is required by any interface; approved unit/qualifier/enum, evidence fallback and failure policies are encoded with explicit limits. Provisional numerical targets and the C/F evaluation protocol are recorded; final numerical gates follow preliminary live review and precede held-out evaluation. A ends with reviewable contracts and an implementation-ready B scope, without reopening approved architectural choices.

### 6R-B — Unified profile and infrastructure adaptation

**Dependencies:** A contracts, migration design, input limits and source/registry projections.

**Work and deliverables:**

1. Introduce the independently versioned 6R manifest/schema/prompt identity and one active extraction profile. The test provider uses this same family and wire contract.
2. Implement unified pinned-page projection including prose, table-contained readings, source geometry/order, table hints, conflicts and page image. Both stages use the same context identity.
3. Adapt lifecycle, operation planning, the operation-only public start API and worker dispatch; remove old direct user-facing run starts, profile registration and schema parsing from active startup. Preserve local preparation/layout and classification purposes.
4. Implement fresh execution/source/immutable-stage-result persistence needed for durable mock runs. Use explicit dependencies on successful same-page/same-run Call 1 results.
5. Adapt consent/preview hashing, admissions, retries, cancellation, lease fencing, usage hooks and unknown-provider-outcome handling to one extraction child.
6. Port infrastructure test scenarios to the new fake provider. Begin deleting unreachable old orchestration/profile branches; dormant old implementations may exist briefly on the development branch only until their replacements land, never as supported execution modes.

**Focused tests:** single- and multi-page fake runs; complete page input including table readings and pinned image; wrong/stale source hash refusal; force-OCR selection and immutable reuse; successful Call 1 with zero eligible types produces `NO_ELIGIBLE_ATTRIBUTES`, preserves unknown equipment and makes no Call 2 call; Call 2 blocked by failed/pending/foreign Call 1; successful prerequisite reused on retry; cancellation before and after admission; duplicate deliveries/start requests; budgets and disabled external execution; source-purpose isolation; fresh schema startup; installed-package identity parity. Verify old profile keys and the direct user-facing run-start route are rejected/unavailable, and all public starts use the operation workflow.

**Acceptance:** mock end-to-end operation completes through the new stages on an isolated fresh database; no table-family dispatch occurs; successful Call 1 context is immutable and correctly bound; partial pages are reported honestly; reusable ingestion/enrichment/classification still work. B does not claim live extraction quality or final candidate-publication acceptance.

**Implementation handoff**

- The operation pins one `phase-6r` profile. Phase 6R-B enables the deterministic provider only when `EXTRACTION_PHASE6R_FAKE=true`. Both page stages use the same verified projection, with Call 2 bound to the exact successful recognition result. Run detail and operation monitoring expose the skip outcome.
- The B chain ends at `6r_0013_operations`. The schema reuses `run_source_enrichment_bindings` for page ownership and `extraction_work_units` for both the logical stage key and its attempts. Database constraints and triggers enforce binding, retry ancestry, and atomic immutable stage results.
- The fresh-install and mock workflow checks use a disposable database. Phase 6R-C owns the provider transport, semantic prompts and authorized feasibility run. Candidate and evidence publication, cursor-based browse endpoints and the remaining Documents browser cutover belong to D and E. The target database reset remains part of the rollout.

### 6R-C — AI recognition and attribute extraction

**Dependencies:** B source projection, stage runtime, durable prerequisites and transport boundary; A observation/value contracts; representative authorized real-world sources, explicit provider opt-in and a bounded live-validation budget.

**Work and deliverables:**

1. Implement Call 1 prompts and structured responses: complete source-local observation discovery, exact registry proposals, tag states, source qualifications and contextual citations.
2. Implement Call 2 prompts and responses: exact Call 1 result input, recognized-type-only attribute catalog, AI-proposed permitted enums plus original source strings, raw source values/units/qualifiers, explicit owner or unassigned state, separate conflicting assertions and the secondary raw-unmapped extension with explicit limits.
3. Replace source-probe and multiple-family branches in the provider adapter. Keep one SDK call per attempted stage and persisted retries; no hidden correction/repair model calls.
4. Handle refusal, truncation, invalid schema, overflow, unsupported keys, duplicated local refs and bad owner references according to the A contract. Never turn failed/incomplete recognition into a successful empty page.
5. Persist bounded stage diagnostics, model/call identities and usage even when parsing or downstream validation fails where available.
6. Complete a **small, explicitly authorized live OpenAI feasibility test before 6R-D begins**, through the durable two-stage runtime. Select a bounded representative development sample covering **prose, schedules and diagrams**, separate from the held-out benchmark. Record approved source/page scope, sample counts, model/profile identities and maximum calls/spend before execution. Against independently annotated expected observations, measure equipment recall, attribute accuracy (returned keys, source values and enum proposals), equipment ownership correctness, evidence quality, measured token usage and latency per page/stage. Report numerators/denominators, omissions, failed calls and unavailable telemetry; inspect qualifiers, raw-unmapped scope and source citations against pinned artifacts. These are preliminary stage-level feasibility results, not a claim that D's normalization/publication or E's UI is complete. Produce and review a compact findings report before D; retain comprehensive evaluation in F. Review representative live results, corpus sizes and evaluation procedures before finalizing numerical release gates, and freeze those gates before held-out evaluation.

**Focused tests:** mocked Responses transport and full stage execution for prose, nameplates, diagram annotations, dense/merged/borderless schedules, mixed content, unknown types, all tag states, two tag-less devices, repeated tags, spare/future/legend qualifications, conflicting readings/attributes, and unassigned ownership. Assert that Call 2 receives the exact accepted Call 1 result and only relevant attribute definitions. Verify source prompt injection remains untrusted data, schema/key controls hold, and no defaults/canonical/topology writes occur. Count provider calls; ensure no omitted equipment is recreated deterministically in Call 2.

**Additional focused checks:** AI interprets a nonliteral source enum into a permitted proposal while retaining the source string; disallowed/missing proposals never trigger local synonym inference; raw-unmapped assertions respect count/size limits, never mint keys and never add calls; early authorized live cases exercise the same stage contracts and audit path as mocks.

**Acceptance:** two-call semantics work against mocks with explicit failure diagnostics; the small authorized live OpenAI feasibility test covers prose, schedules and diagrams, and its report includes the six measurement areas above and is reviewed **before 6R-D begins**. No mandatory alias or deterministic owner/enum-synonym classifier exists; unknown/tag-less/conflicting observations survive. C is a feasibility checkpoint, not a pass/fail claim against provisional numerical performance targets. Comprehensive held-out quality remains an F gate; numerical thresholds stay provisional until representative live results, corpus sizes and evaluation procedures have been reviewed, then are frozen before that evaluation. Any missed-equipment recovery strategy beyond the agreed two calls requires a separate design decision, not a hidden C change.

### 6R-D — Thin validation, normalization, and publication

**Dependencies:** C model outputs and completed/reviewed live OpenAI feasibility report covering prose, schedules and diagrams; B immutable source/stage binding; A schema/status/unit policies. Do not begin D before the C feasibility checkpoint is complete.

**Work and deliverables:**

1. Implement fragment-level source localization, page/artifact/reference checks, bounded text matching, enabled unique page-local verbatim quote fallback, and explicitly approximate visual locators. Precise highlights require source-derived coordinates.
2. Implement registry applicability, AI enum-proposal membership validation, simple lexical boolean conversion and raw-to-typed normalization using canonical registry/unit utilities. Enforce the approved missing-unit and qualifier policies; preserve raw strings, proposal, qualifiers/ranges/multiple ratings and all independent quality dimensions without deterministic semantic reinterpretation.
3. Complete final observation/evidence schema, composite ownership constraints, immutable publication, typed storage, operation references and clean-install migration graph.
4. Replace old candidate/table publication and semantic source-scope checks; retain artifact verification, transactional fencing and idempotency protections.
5. Implement unified read APIs/serializers and evidence signing so E can consume stable endpoints. Remove old table and legacy record routes as their new consumers replace them; no compatibility fallback.

**Focused tests:** distributed label/value/nameplate citations; table designation/header/value fragments with separate coordinates; repeated `600 A` with and without a disambiguating reading ID; false combined quote; whitespace-tolerant matching without matching a different occurrence; nonexistent/foreign page/artifact/source references; missing geometry; bounded visual box versus out-of-bounds/nonfinite coordinates; OCR/native conflict indicators; unit conversion, unit omission policy, invalid dimensions, Decimal exactness, integer overflow, enum/boolean validation, qualified/range values; independent statuses/quality; conflicting attributes retained; no canonical writes. Integration tests attempt cross-page owner links, mutated source/result hashes, duplicate publication, stale leases, cancellation races and partial transaction failures. Install all migrations into an empty PostgreSQL database and inspect tables, enums, functions, constraints and Alembic head.

**Acceptance:** source-derived fragments have exact provenance; fabricated references never appear resolved; ambiguous/visual evidence is honestly labeled; supported valid values normalize correctly and invalid/unmapped raw assertions survive; the full fresh schema works with no old extraction structures/readers. Call 1 success remains available if Call 2 fails, and page completion reflects both required stages or the explicit eligibility outcome.

### 6R-E — Documents UI integration and complete legacy removal

**Dependencies:** D stable read/write/evidence APIs and publication; A approved UI state contract.

**Work and deliverables:**

1. Update wizard, register/inspector statuses, operation monitoring and extraction action for one AI Engineering Extraction workflow, preserving preparation/OCR controls and consent.
2. Update candidate browsing for source-local equipment, tag states, unmapped observations, unassigned/uncertain attributes, raw/normalized values, source qualifiers and conflicts.
3. Add ordered multi-fragment source highlights, approximate visual-region presentation and unresolved page context without changing unrelated viewer behavior.
4. Replace run history with only new 6R runs, two stages/attempts, source versions/bindings, diagnostics, usage/cost and retry/cancel. Remove old URLs/state/query keys rather than translating them into legacy views.
5. Complete dependency-ordered deletion of every superseded implementation, prompt/profile, response parser, SQL structure/guard, API route, CLI/resource, old-behavior test and extraction UI component/state. Decouple spatial evaluation before deleting its old imports.
6. Rewrite active docs, extraction prototypes and developer configuration. Run the no-legacy audit against imports, registered routes/OpenAPI, profile registry, worker startup, package contents, schema objects, UI navigation and docs.

**Focused tests:** component tests for wizard preview/consent and single action; automatic preparation and OCR override; duplicate submission; partial-page/stage failure and retry; cancellation; read-only/removed-document behavior; tag-less/unmapped/unassigned/conflicting results; each localization outcome; multiple separate highlights; unavailable/expired pinned source links; stable run selection across polling; pagination/search/filters. Fresh-database browser flow: create project/revision → upload/process → extract with test provider → inspect evidence/history → retry/cancel. Check desktop/narrow drawers and keyboard/focus behavior. Run existing unrelated frontend/authoring suites plus targeted visual comparisons using the current harness.

**Acceptance:** the complete Documents workflow works on a fresh install; no old families, extracted-table endpoint, historical compatibility tab or hidden profile remains; exact and approximate highlights are visibly distinct; source tables remain viewable as source layout. Unrelated workspaces retain their behavior and appearance. Full Python/frontend quality checks pass after deletion.

### 6R-F — Comparative evaluation, production hardening, and cutover

**Dependencies:** E's complete replacement and no-legacy audit; reviewed representative live results, corpus sizes and evaluation procedures, with final numerical gates frozen before held-out evaluation; authorized held-out source scope/model budget for live runs; separate exact-target authorization for destructive deployment.

**Work and deliverables:**

1. Finalize independently reviewed gold for equipment occurrences/type/tags/qualifications, attributes/raw and normalized values, AI enum proposals, ownership and evidence occurrences in the separate authorized held-out benchmark. Keep it distinct from the preliminary C corpus and prompt-tuning cases.
2. Evaluate actual 6R execution through normal durable orchestration, not direct SDK shortcuts. Report mock, replay and live results separately, with all failures/omissions retained in denominators.
3. Compare against the pinned previous implementation only where sources, annotations and metrics are comparable. Use an isolated old checkout and disposable database or a previously captured report; never ship the old extractor with 6R. Flag incompatible historical metrics instead of claiming a numerical improvement.
4. Measure equipment precision/recall, type/tag accuracy, attribute recall/value/key accuracy, owner accuracy and abstention, evidence validity/localization, raw preservation, latency, retries, tokens and estimated cost per page/document. Publish failure strata and source/model/profile/corpus identities.
5. Exercise real queue/worker/DB/storage recovery, timeout, duplicate delivery, cancellation, budget exhaustion, authorization, large input/output and fresh-install/bootstrap failure modes.
6. Complete and rehearse the destructive reset/restore runbook on disposable infrastructure. Execute the designated application reset only after the operator's exact-target authorization, then deploy only 6R, bootstrap, re-upload authorized smoke sources and verify Documents end to end.
7. Produce final handoff with actual acceptance results, source authorization, reset record, release/base commits, final schema head, no-legacy audit and known reviewable failure classes.

**Focused tests:** mixed prose/tables; borderless/merged schedules; repeated numbers and tags; separate mentions on multiple pages/documents remaining distinct; unknown/tag-less devices; blurry/image-only sources; OCR/native disagreement; live failures; crash before/after provider-start and before/after commit; successful Call 1 reused on attribute retry; no stale publication after cancellation/reset; stage budget accounting; unavailable source storage; clean install and bootstrap. Verify application-scoped reset guards reject missing/ambiguous targets and never touch unrelated objects/queues in the rehearsal.

**Acceptance:** agreed measured quality and operational thresholds pass, with limitations documented; actual authorized live drawings have been evaluated; the designated application database has been reset and clean-installed; all release smoke and no-legacy checks pass. Mock-only success or a runbook without the required authorized cutover does not constitute Phase 6R completion.

## 7. Evaluation and verification contract

### 7.1 Corpus and scoring

Reuse the source fixtures under `evals/extraction/v1/sources/`, `evals/tables/v1/sources/`, and `evals/spatial/v1/sources/`. Re-author gold/output recordings where prior expected rejection or table reconstruction semantics conflict with 6R. Preserve local structural/OCR accuracy measurements separately from engineering extraction accuracy.

Required strata include prose, distributed nameplates, single-line diagram observations without connectivity, mixed text/schedules, dense and merged/borderless schedules, unknown types, no-tag/unreadable/ambiguous tags, repeated mentions/numbers, proposed/spare/future/reference/legend-only/unknown qualifications, OCR/native conflict, blurry scans, visual-only evidence and multi-page source-local observations. Plan separate authorized real-world development and held-out corpora in A: use representative development documents for early C validation and reserve the held-out benchmark for F. No authorization is inferred from a historical filename or Git fixture pointer.

Gold must identify page-local source occurrences and ownership independently of model references. Match predictions one-to-one within source/page scope; distinct mentions with identical tags must not collapse. Report detection, classification, normalization, ownership and localization separately. Attribute recall includes losses caused by Call 1 omissions. Report assigned-owner precision together with ownership coverage/recall so abstention cannot create an apparently perfect system. Use numerators/denominators and per-stratum failures; empty denominators are unavailable, not 100%.

### 7.2 Accepted provisional metrics and numerical targets

The following metrics and numerical performance targets are **accepted as provisional**. They are not measured performance, C feasibility pass/fail criteria or final release thresholds. Keep them provisional until **representative live results, corpus sizes and evaluation procedures have all been reviewed**. A records the protocol, strata, sample-size plan and execution budgets; C supplies the small authorized live OpenAI feasibility report. Completing that small test alone does not finalize thresholds or establish statistical adequacy. After the combined review, record final numerical gates before running the separate comprehensive held-out F evaluation. Do not use held-out results to tune prompts or retroactively lower release thresholds. Fixed architectural/integrity requirements remain mandatory throughout.

- Deterministic contract/integrity suite: **100% pass**; zero cross-source published references, false exact highlights, duplicate committed stage results, automatic canonical writes, or legacy execution routes in covered cases.
- Live equipment observation precision **≥95%**, recall **≥90%**; registry-type accuracy on matched equipment **≥95%**. Measure tag text/state accuracy separately with a provisional **≥95%** target.
- Live supported-attribute source-assertion recall **≥90%**; key plus normalized value/unit accuracy on matched, gold-mappable assertions **≥95%**. Also report end-to-end correct attribute recall over all gold assertions, including missed equipment, rather than hiding omissions in conditional accuracy.
- Correct equipment ownership among assigned assertions **≥98%**, paired with end-to-end ownership correctness/coverage **≥90%** on gold assignable assertions; report correctly unassigned cases separately.
- Source-reference/artifact validity **100%** for published resolved fragments; correct occurrence/localization against gold **≥98%** for claims presented as resolved. Visual-reported regions and unresolved citations have separate coverage/quality reporting and cannot inflate exact-localization scores.
- Raw value/unit/qualifier preservation **100% of admitted structured assertions**; unknown and tag-less retention **100% of structurally valid admitted equipment assertions**. Model discovery omissions remain recall failures, not “preserved” successes.
- Latency, maximum per-page token spend, total evaluation cost, and acceptable variation across repeated live runs: **explicit budgets to be set in A** after source/model selection. Do not invent cost numbers without a rate basis. Report p50/p95 latency and include retries/failed calls.

Use per-stratum review and agreed minimum sample sizes; a strong aggregate must not conceal a failing schedule or tag-less cohort. Reserve the separate held-out set before prompt tuning and keep it out of C validation. Record final gate values only after reviewing representative live results, corpus sizes and evaluation procedures, and before held-out evaluation. Do not waive fixed architectural/integrity invariants or relabel a failing held-out evaluation as passing by changing its gates afterward.

### 7.3 Test execution gates

During implementation, run focused unit/component tests for each changed contract first, then relevant integration tests. The final gate includes Ruff checks/format checks, the retained plus new Python suite with PostgreSQL/Redis/MinIO and real local OCR enabled, wheel/resource checks, frontend lint/tests/type checking/production build, fresh-install migration tests, and targeted browser/visual checks.

The current CI installs Tesseract and exercises integration services; preserve that coverage. Update CI and fixture setup for the replacement migration graph. Do not satisfy a clean-install gate using an already populated developer database. No tests were run during this planning review, and no current passing-test or live-accuracy claim is made.

## 8. Approved clarifications and execution prerequisites

### 8.1 Approved architectural clarifications for 6R-A

Approved 2026-11-13. These decisions supersede the earlier recommendations and open questions. Encode them in A's concrete contracts; do not request architectural reapproval for routine implementation details.

1. **Missing units and qualified values — approved.** Never assume source units or discard qualifiers. Source-supported headers may establish units. Missing or ambiguous dimensional units retain raw information as `UNMAPPED` with a specific reason; unsupported units under an otherwise valid interpretation may be `INVALID`. Preserve ranges and multiple ratings without arbitrary scalar selection. Canonical authoring defaults remain unchanged and must not be mistaken for extraction evidence.
2. **Enum and boolean interpretation — approved with modification.** AI performs semantic interpretation and returns both the original source value string and its proposed exact permitted registry enum. PowerForge validates that proposal against the applicable allowed values; it does not independently perform engineering synonym interpretation. Simple lexical boolean conversions are permitted with raw-string preservation.
3. **Observation roles — approved.** Use explicit `INSTALLED`, `PROPOSED`, `FUTURE`, `SPARE`, `REFERENCE`, `LEGEND_ONLY` and `UNKNOWN` qualifications. Preserve source qualifications; never fabricate physical equipment from a legend or infer topology.
4. **Equipment descriptions — approved.** Add concise, versioned, registry-owned descriptive metadata for AI classification. Include it in input identity without changing existing canonical registry keys or behavior.
5. **Unknown/raw attributes — approved with modification.** Include a secondary bounded raw-unmapped assertion extension in Call 2 for meaningful unsupported attributes within scope. Set explicit output count/size limits; retain raw source information and evidence without inventing registry keys. Registry-linked extraction remains primary. No unrestricted discovery, additional AI calls or deterministic semantic mapping is permitted.
6. **No eligible attributes — approved.** Skip Call 2 only following successful Call 1 with zero eligible recognized equipment types. Persist `NO_ELIGIBLE_ATTRIBUTES` and zero-call telemetry, and preserve unknown equipment observations. Never disguise failed recognition as this outcome.
7. **Malformed versus recoverable output — approved.** Fail malformed stage envelopes, duplicated identifiers, truncation and capacity overflow. Retain otherwise valid observations when individual citations fail, with diagnostics and no invalid source links. Never guess missing references or ownership; unsupported ownership stays unassigned.
8. **Evidence fallback — approved with modification.** Pinned source reading IDs are primary. Enable unique, bounded, page-local verbatim quote matching as fallback. Ambiguous matches remain unresolved. AI-proposed visual regions remain approximate; precise highlights require source-derived coordinates. Text-only localization without geometry cannot produce an exact spatial box.
9. **APIs, traces and costs — approved.** The operation workflow is the single supported user-facing start path. AI stages are `EQUIPMENT_RECOGNITION` and `ATTRIBUTE_EXTRACTION`. Preserve bounded, access-controlled stage-result diagnostics and audit information. Cost estimates require measured usage and versioned pricing; otherwise report unavailable.
10. **Quality acceptance — accepted provisionally.** Keep section 7.2's numerical performance targets provisional until representative live results, corpus sizes and evaluation procedures have been reviewed. Complete a small explicitly authorized live OpenAI feasibility test in C, covering prose, schedules and diagrams and measuring equipment recall, attribute accuracy, ownership, evidence quality, token usage and latency; review its report before D begins. Keep the comprehensive evaluation on a separate held-out benchmark in F and freeze final numerical gates before that evaluation.

For remaining low-level details—wire field names, schema layout, reason codes, explicit bounds, simple boolean tokens, retention configuration and migration identifiers—follow the approved strategy and use reasonable engineering judgment. Do not expand scope or add unnecessary machinery. The AI-first ownership boundary, full reset, no legacy support, two-stage normal path, and Phase 7/topology exclusions remain unchanged.

### 8.2 Required later authorizations, not blockers to repository planning

- **Live validation/evaluation in C and F:** exact source/corpus authorization, provider/model configuration, explicit external-processing opt-in and spend/call budget before sending actual drawings. The approved evaluation sequence does not authorize unspecified source disclosure or spending.
- **Destructive cutover:** exact target database/environment and separately scoped object/queue cleanup before running the reset. The spec explicitly requires this in sections 13 and 19; approval of a clean-reset strategy is not approval to wipe an unidentified target.
- **Recovery:** whether a pre-reset backup is required, its external location, and whether restoration of the old environment is authorized. A backup is for rollback to compatible old code, not row import into 6R.

## 9. Implementation boundary

6R-A establishes the contracts and decisions for B. The live feasibility report remains a prerequisite for D. The C/F live sample authorization and F exact-target destructive-reset authorization are separate execution prerequisites.

The final 6R release is accepted only when the specification's completion definition is satisfied: one active unified family, normal two-call page pipeline, honest and inspectable evidence/uncertainty, source-local observations without entity/topology inference, working Documents review, full authorized database reset and clean install, measured real-source acceptance, and complete retirement of superseded runtime/schema/API/UI/docs.
