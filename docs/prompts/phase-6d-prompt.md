# PowerForge — Phase 6D: Tables and Schedules Extraction

## 1. Objective

Implement **Phase 6D — Tables and Schedules Extraction** on top of the completed and merged Phase 6A–6C infrastructure.

PowerForge must identify, reconstruct, interpret, and preserve engineering tables and schedules from supported PDF and image documents. The extracted structures must retain source provenance and produce independently queryable engineering candidates using the existing Phase 6 persistence and execution architecture.

Implement Phase 6D in **four reviewable milestones (M1–M4)**.

**First inspect the repository, evaluate the architectural options described below, and produce a detailed implementation plan. Do not begin M1 until that plan has been reviewed and approved.**

Use the latest `main` branch as the baseline. Propose a dedicated feature branch for Phase 6D.

## 2. Existing architecture and source of truth

Read the relevant implementation and documentation before proposing changes.

In particular:

- `docs/specs/phase-6-evidence-structured-extraction.md`
- `decisions/ADR-008-evidence-candidate-extraction-architecture.md`
- `docs/PHASE6C_PLAN.md`
- `docs/PHASE6C_HANDOFF.md`
- `docs/PHASE6A_HANDOFF.md`
- `docs/PHASE6B_HANDOFF.md`
- `docs/EXTRACTION.md`
- `docs/PROVENANCE.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`

Inspect the existing extraction contracts, persistence service, orchestration, stage definitions, execution profiles, OpenAI provider, grounding, interpretation, registry integration, and test infrastructure.

The following foundations already exist:

1. **Phase 6A:** Immutable extraction runs, work units, evidence, source groups, `ExtractedTable`, relational candidates, table-cell locators, and atomic publication.
2. **Phase 6B:** Provider execution, durable scheduling, admission budgets, retries, cancellation, leases, recovery, and telemetry.
3. **Phase 6C:** Two-stage equipment recognition and attribute extraction, registry-controlled semantic interpretation, conservative grounding, versioned production OpenAI profiles, and evaluation tooling.

Reuse these capabilities wherever appropriate. Do not build a parallel extraction system.

### Existing table contracts

Pay particular attention to:

- `TableInput`
- `TableLayout`
- `TableCell`
- `TableKind`
- `ExtractedTable`
- `EvidenceInput.table_id`
- `EvidenceInput.cell_id`
- `SourceGroup`
- `ExtractionCandidate`
- `CandidateEvidence`
- `WorkUnitOutput`

The established table orientations are:

- `EQUIPMENT_ROWS`
- `ATTRIBUTE_ROWS`
- `MIXED`
- `UNCLASSIFIED`

The existing `table-layout-v1` structure already supports rows, columns, cells, headers, spans, and source locations.

Prefer extending this established design instead of introducing another table representation.

## 3. Scope and exclusions

### In scope

Extract structured tables from existing supported documents:

- PDFs containing native text and/or rendered page images.
- PNG, JPEG, and TIFF documents processed through the existing document pipeline.
- Image-only tables interpreted through the approved visual-evidence limitations.

Support:

1. Equipment-per-row schedules.
2. Single-equipment attribute-per-row tables.
3. Mixed and irregular tables.
4. Tables whose orientation cannot be determined confidently.
5. Multiple independent tables on a page.
6. Header rows, header columns, combined header meanings, and merged cells where sufficiently supported.
7. Blank, missing, ambiguous, and conflicting cells.
8. Unit declarations in headers or labels.
9. Equipment tags, names, and type hints when actually supported by the source.
10. Source-local grouping and individual table-cell evidence.

Both textual and visual table extraction should be supported, but the reliability of their evidence must be distinguished.

### Explicitly out of scope

**Do not implement Excel ingestion or processing.**

XLSX support has been deferred to a separate **Phase 6.5**, after Phase 6G and before Phase 7.

Also exclude:

- XLS, XLSM, CSV, or other new document formats.
- New upload/processing pipelines for spreadsheets.
- OCR engines, OCR-derived text coordinates, or advanced layout preprocessing reserved for Phase 6E.
- Cross-document or canonical equipment identity resolution (Phase 7).
- SLD connectivity and topology inference (Phase 8).
- Persistent conflict reconciliation (Phase 9).
- Engineer verification or candidate acceptance (Phase 11).
- Extraction UI redesign (Phase 6F).
- Direct canonical-model writes.
- Changes to registry-v1 engineering semantics.

Phase 6D may preserve a possible multi-page continuation when supported, but should not invent connections between unrelated tables. Full document-wide table stitching and complex spatial layout reconstruction are not prerequisites for completion.

## 4. Required engineering behavior

### 4.1 Equipment-per-row schedules

Example:

| Equipment | Capacity (kVA) | Primary (kV) | Secondary (V) |
|---|---|---|---|
| TX-1 | 750 | 12.47 | 600 |
| TX-2 | 500 | 12.47 | 480 |

Expected interpretation:

- Two distinct source-local equipment observations.
- Each row's values associated only with that row's equipment.
- Column headers provide explicit attribute meaning and units.
- Registry-compatible fields become correctly typed and normalized candidates.
- Every extracted attribute retains evidence referring to its source table and cell.
- No inference that these observations match any canonical equipment records.

A repeated equipment tag does not automatically prove physical identity.

### 4.2 Attribute-per-row tables

Example:

| Parameter | Value |
|---|---|
| Equipment | TX-1 |
| Rated Capacity | 750 kVA |
| Secondary Voltage | 600 V |
| Impedance | 5.75% |

Expected interpretation:

- The table describes one source-local equipment instance when justified.
- Parameter names are interpreted using registry metadata and approved terminology.
- Attribute rows reference the same source-local equipment context where warranted.
- Raw expressions and units remain available alongside normalized values.
- The association must not be inferred solely because an arbitrary nearby cell contains an equipment-like tag.

### 4.3 Mixed or ambiguous tables

Do not assume every table uses either of the two conventional orientations.

Engineering documents may contain:

- Multiple equipment types.
- Nested or grouped headers.
- Separate ratings for normal and emergency operation.
- Ratings expressed under different conditions.
- Multiple values in one cell.
- Blank headings.
- Notes and footnotes.
- Conflicting values.
- Subtotals or descriptive rows that do not represent equipment.
- Partially visible or truncated tables.

Preserve layout and raw content even when interpretation is incomplete.

If the table orientation is uncertain, use `UNCLASSIFIED` or another existing appropriate representation instead of forcing a mapping.

Do not create equipment candidates from every row or attribute candidates from every numeric cell.

### 4.4 Semantic mapping and normalization

Reuse Phase 6C's deterministic interpretation layer and the frozen `registry-v1`.

The AI model may propose an equipment type, attribute key, unit interpretation, or relationship, but these proposals are not authoritative.

Deterministic validation must establish:

- The source actually supports the observation.
- The equipment type is justified.
- The attribute meaning is justified.
- The proposed registry mapping is valid.
- The source units and qualifiers support the interpretation.
- The normalized value complies with registry semantics.

Preserve exact Decimal, INTEGER, BOOLEAN, ENUM, TEXT, and unit behavior.

For example, `Secondary (V)` containing `600` may support a normalized value of `0.6 kV` when the equipment context and registry attribute are established.

Do not assume that any column labeled `Rating` necessarily means `rated_current`, `trip_rating`, `frame_rating`, or another specific attribute.

Preserve `UNMAPPED` and `INVALID` observations appropriately. Never invent missing values or use registry defaults as extracted source facts.

Revision-wide `system_frequency` and `system_phase_count` remain manual-only.

## 5. Table structure and evidence provenance

This is one of the most important parts of Phase 6D.

### 5.1 Preserve table structure separately from interpretation

The system must distinguish:

1. **Observed table structure:** rows, columns, headers, cells, spans, and layout.
2. **Interpreted engineering claims:** equipment mentions, attributes, values, and associations.

A table should remain inspectable even if some or all of its engineering content cannot be mapped.

Use the existing `ExtractedTable` layout and relational candidate model. Do not store all engineering interpretations exclusively inside a JSON blob.

### 5.2 Source anchoring

Every accepted table must be associated with its exact pinned document processing inputs.

For native text:

- Verify relevant text against the immutable native-text artifact.
- Use source offsets only where genuinely established.
- Do not assume PDF text extraction order perfectly reproduces visual table geometry.
- A source excerpt alone does not necessarily prove the proposed row/column relationship.

For visual extraction:

- Preserve the approved page-level visual grounding limitation.
- Do not fabricate text offsets, verified pixel coordinates, or OCR evidence.
- Model-inferred table rows and cells may be represented as unverified structural interpretations, but must not be labeled as independently verified geometry or transcription.

### 5.3 Cell references

An interpreted candidate should be traceable to the relevant table cell through the existing table/cell locator contracts.

Table and cell identities must be stable within their immutable output and must not be confused with canonical equipment identifiers.

Pay particular attention to validation when a table is published by one successful work unit and related candidates are published by a later dependent unit.

The existing persistence boundary supports same-run references to committed outputs; ensure any cross-unit table/cell association is correctly authorized, immutable, and constrained to the pinned page and source artifacts.

### 5.4 Grouping and associations

Equipment-row associations must be justified by table structure, not merely by an AI-reported equipment reference.

Preserve:

- Tagless equipment rows.
- Unassociated attributes.
- Unknown equipment types.
- Distinct source occurrences with repeated tags.
- Conflicting values rather than selecting an arbitrary winner.

Do not merge two source-local groups merely because their tags or values match.

## 6. Execution architecture and Phase 6C compatibility

Before implementing, evaluate how specialized table extraction should integrate with Phase 6C.

Phase 6C currently uses the immutable stage sequence:

`EQUIPMENT_RECOGNITION → ATTRIBUTE_EXTRACTION`

Phase 6D must not modify the meaning of already accepted Phase 6C profiles, stage manifests, runtime identities, or historical results.

### Compare architectural alternatives

Evaluate at least:

**Option A — Dedicated table-aware extraction profile**

A separate, explicitly selected table-oriented execution profile with appropriately specialized stages.

**Option B — New versioned combined engineering profile**

A new profile that incorporates table-specific work alongside the existing equipment/attribute workflow.

**Option C — Another justified design**

Only if it offers meaningful advantages in correctness, provenance, compatibility, complexity, and cost.

Compare the alternatives against:

- Duplicate equipment or attribute candidates from table and non-table extraction.
- Dependency ordering.
- Availability of committed upstream context.
- Number of model calls.
- Retry granularity.
- Partial failure behavior.
- Table reconstruction versus semantic interpretation.
- Historical profile compatibility.
- Support for documents containing both tables and ordinary text.
- Future Phase 6E OCR/layout extension.

**Recommend one design explicitly before implementing it.**

My preferred direction is to use a new versioned table-aware profile and specialized table stages rather than altering the existing Phase 6C production profiles. However, choose the final stage structure based on the above comparison.

Do not introduce a large generic workflow engine unless the present orchestration model genuinely cannot support the selected design.

### Non-negotiable execution guarantees

Preserve all existing Phase 6B/6C safeguards:

- Explicit external-processing opt-in.
- Immutable source and processing-run pins.
- Durable dispatch and dependency-gated claims.
- One provider call per admitted attempt.
- Bounded input, context, output, page, attempt, and call limits.
- Existing concurrency and timeout controls.
- No hidden SDK retries or repair calls.
- Append-only retry history.
- Reuse of completed prerequisites.
- Correct settlement of blocked work.
- Cancellation and stale-worker fencing.
- Expiry-first recovery.
- Atomic publication.
- Safe provider errors and usage accounting.
- No provider I/O while holding long-running database transactions.

Continue using the existing OpenAI Responses structured-output integration, with versioned prompts/schemas, `store=false`, no model tools, and untrusted document content separated from trusted instructions.

If new profile/runtime resources are required, create new explicit versions. Preserve existing v1/v2/v3 historical profile serialization and runtime identities. Do not silently relabel changed behavior with an old fingerprint.

## 7. Avoid duplicate extraction results

A major design concern is that Phase 6C may already recognize some equipment and attributes appearing inside tables.

Phase 6D must establish a clear policy for how table-specific observations coexist with ordinary Phase 6C observations.

Within a single table-aware extraction run:

- Avoid publishing redundant copies of the same source claim through multiple stages.
- Preserve genuinely different observations or conflicting readings.
- Do not deduplicate solely by matching equipment tags or normalized values.
- Prefer source-local table/cell identity and grounded occurrence information.
- Ensure retrying one stage cannot recreate already committed successful candidates.

Document the deduplication and source-ownership policy explicitly. Do not implement Phase 7 identity matching as a substitute.

## 8. Implementation milestones

Implement sequentially, with a review gate after each milestone.

### M1 — Table observation contracts, stage definitions, and layout interpretation

Design and implement the provider-neutral representation of table observations.

Scope:

- Versioned Pydantic observation schemas.
- Table detection and structured layout representations.
- Header, row, column, and cell relationships.
- Merged-cell and span representation when supported.
- Orientation determination or explicit uncertainty.
- Multiple tables per page.
- Source-role anchors and bounded response structures.
- Versioned prompt resources and stage identities.
- Registry-context integration where relevant.

Do not directly generate database entities from the model.

**M1 acceptance gate:**

Offline tests demonstrate that the observation contracts can represent equipment-per-row, attribute-per-row, mixed, and unclassified tables without information loss or fabricated cells.

Test table bounds, malformed structures, duplicate or invalid cell references, inconsistent spans, unavailable source roles, empty tables, and unsupported assertions.

No production provider execution or persistence integration is required yet.

### M2 — Grounding, semantic interpretation, and output conversion

Implement deterministic validation and conversion of table observations.

Scope:

- Source verification against exact pinned artifacts.
- Table structure and cell ownership checks.
- Conservative interpretation of row/column context.
- Registry mapping and normalization.
- Source-local equipment groups.
- Candidate-to-table-cell evidence links.
- Raw/unmapped/invalid retention.
- Conversion to existing `WorkUnitOutput` contracts.

Reuse Phase 6C interpretation and grounding utilities where their guarantees apply.

**M2 acceptance gate:**

Representative tables produce correct `TableInput`, `EvidenceInput`, `SourceGroupInput`, `CandidateInput`, and citation outputs.

Prove that:

- TX-1 and TX-2 values remain associated with their respective rows.
- An attribute-per-row table preserves one justified equipment context.
- Tagless and uncertain observations remain representable.
- Incorrect AI-reported cell or equipment references do not override verified source structure.
- Invalid source claims are rejected or retained with appropriately limited status.
- Mixed and conflicting readings remain distinct.
- Image-only evidence never acquires fictitious text offsets or verified geometry.

Add focused real PostgreSQL publication/read tests using disposable infrastructure, including transactional rollback and table-cell reference integrity.

Do not integrate production OpenAI execution yet.

### M3 — Production OpenAI and orchestration integration

Integrate the specialized table extraction pipeline with existing profiles, coordinator, worker, API, and source-artifact execution.

Scope:

- New versioned table-capable production profiles.
- Stage planning and dependencies.
- Trusted prompt/schema selection.
- Versioned upstream-context handling.
- Existing provider adapter integration.
- Safe retries, partial completion, and recovery.
- Atomic publication of tables and interpreted candidates.
- Existing extraction API discovery and read behavior.

Prefer the existing extraction API namespace and `GET /runs/{run_id}/tables` contract. Avoid adding routes unless a demonstrated requirement cannot be met by existing APIs.

Maintain opt-in execution and the existing fake default. Do not introduce automatic extraction upon upload.

**M3 acceptance gate:**

Mocked OpenAI SDK tests verify the actual structured request, selected schemas, inputs, usage, failure handling, and provider-call limits.

Real Celery/Redis/PostgreSQL/MinIO integration tests verify:

- Table discovery and publication.
- Correct dependent-stage ordering.
- Reuse of committed successful results during retry.
- No duplicate candidates from completed stages.
- Safe handling of stage failures, cancellation, and worker interruption.
- Correct partial-run and evidence-read behavior.
- No canonical engineering-model mutations.
- No regressions to existing Phase 6C profiles or execution.

### M4 — Evaluation, regression, and final handoff

Build a representative synthetic/anonymized table-extraction evaluation corpus with independently authored expected outputs.

Include at least:

- Transformer equipment schedule.
- LV breaker schedule distinguishing frame and trip ratings.
- Cable schedule with lengths, sizes, and units.
- Utility fault-data table.
- Single-equipment attribute-per-row specification.
- Mixed equipment and attribute tables.
- Repeated headers/tags.
- Missing or blank cells.
- Merged or hierarchical headers.
- Ambiguous equipment associations.
- Conflicting values.
- Multiple tables on one page.
- Native-text and image-only examples.
- Negative examples where apparent tabular content should not produce mapped candidates.

Where necessary, extend the Phase 6C evaluator in a versioned manner rather than altering the interpretation of its existing baseline.

Evaluate:

1. Table detection precision/recall.
2. Row/column/cell reconstruction correctness.
3. Orientation classification.
4. Equipment observation precision/recall.
5. Attribute detection and registry mapping.
6. Exact value/unit correctness.
7. Source-local association correctness.
8. Table/cell evidence correctness.
9. False or fabricated candidates.
10. UNMAPPED/INVALID retention.
11. Missing or failed-stage coverage.

Use explicit denominators and report limitations honestly.

Scripted and mocked evaluation results must not be described as measured live OpenAI accuracy.

An optional live evaluation may be provided for separately authorized fixtures, but do not make paid provider calls automatically or claim real-model quality without actual measurements.

**M4 acceptance gate:**

- Full relevant backend regression passes.
- Previously accepted Phase 6C tests and identity fixtures remain valid.
- Real database and worker integration tests pass.
- Relevant package wheels build and packaged resources reproduce their identities.
- Migration checks pass if any forward migration was necessary.
- Lint, formatting, and dependency checks pass.
- Final delivery documentation accurately records implemented behavior, test results, and remaining limitations.

## 9. Architecture and compatibility constraints

Keep the implementation focused.

1. **Registry remains authoritative.** Do not modify registry-v1 or create duplicate attribute catalogs.
2. **No canonical writes.** Tables and candidates are read-only extraction proposals.
3. **No invented physical identities.** Source groups are not canonical equipment.
4. **No fabricated evidence.** Table/cell locators must not imply unsupported verification.
5. **No historical mutation.** Previously completed runs, outputs, or profile meanings must remain unchanged.
6. **No unnecessary migrations.** Prefer the established Phase 6A persistence contracts. Add only forward migrations if a demonstrated requirement cannot be satisfied safely.
7. **No parallel execution system.** Reuse existing orchestration, provider accounting, publication, and recovery.
8. **No silent loss of observations.** Preserve uncertainty, isolated values, conflicting claims, and raw source information.
9. **No unnecessary AI calls.** Use deterministic processing when it can establish a result reliably; use the model for interpretation that requires it.
10. **No premature Phase 6E features.** Advanced OCR and independently verified visual regions remain separate.

Treat the current Phase 6 architecture specification and ADR-008 as authoritative. If a genuine incompatibility is discovered, describe the conflict and proposed resolution rather than silently changing an accepted architectural decision.

## 10. Required planning deliverable

Before beginning M1, produce `docs/PHASE6D_PLAN.md` containing:

- A concise architecture overview.
- Your evaluation of the stage/profile alternatives.
- The selected design and rationale.
- A diagram of the proposed table extraction pipeline.
- The table observation and candidate/evidence flow.
- Table versus ordinary-text extraction ownership.
- Source-local grouping and cell-reference rules.
- Historical resource/profile compatibility strategy.
- Required changes by package and service.
- Any justified database migration or API changes.
- The four milestones and their explicit acceptance gates.
- A focused testing strategy.
- Important risks, limitations, and deferred work.

Use concrete examples or diagrams where they help clarify behavior. Avoid filling the plan with trivial implementation details, arbitrary file layouts, or excessive boilerplate.

### Implementation workflow

1. Inspect the current code and approved architecture.
2. Produce the Phase 6D plan.
3. Identify any genuinely unresolved architectural decisions.
4. **Stop for plan review before implementation.**
5. After approval, implement M1–M4 sequentially, with a separate reviewable commit/branch state for each milestone.
6. At each milestone, provide a concise handoff with changed components, test results, unresolved limitations, and whether the acceptance gate is satisfied.

Do not claim tests were executed unless they actually ran.

Do not label Phase 6D completed until M4 has passed and the final handoff is delivered.

## 11. Final deliverables

By the end of Phase 6D, PowerForge should provide:

- A production-capable, explicitly selectable table/schedule extraction pathway for supported PDFs/images.
- Versioned structured table observations and interpretation.
- Source-grounded `ExtractedTable` records.
- Individually queryable equipment and attribute candidates.
- Reliable row/cell-to-candidate provenance.
- Conservative treatment of missing, uncertain, and conflicting information.
- Safe integration with the existing OpenAI provider and orchestration infrastructure.
- Backward compatibility with Phase 6C.
- Representative evaluation and integration tests.
- `docs/PHASE6D_HANDOFF.md`.
- Updated architecture, extraction, provenance, roadmap, and project-status documentation where appropriate.

**The central success criterion is not simply recognizing a table. It is preserving the source table accurately enough to extract engineering claims while maintaining correct row, equipment, attribute, value, and evidence relationships.**