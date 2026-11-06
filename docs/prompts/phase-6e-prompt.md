# PowerForge — Phase 6E: OCR and Advanced Layout Processing

## 1. Objective

Implement **Phase 6E — OCR, Advanced Layout Processing, and Hybrid Native-Text/Vision Preprocessing** for PowerForge.

Phase 6E builds upon the completed Phase 6A–6D extraction architecture. Its goal is to improve extraction from scanned PDFs, digitally generated PDFs with unreliable text order, engineering schedules, specifications, nameplates, equipment drawings, and other visually structured documents.

The central requirement is to provide **reusable, versioned, spatially grounded source information** that the existing engineering and table extractors can consume.

Phase 6E must improve the ability to determine:

- What text is present on a page.
- Where that text is located.
- Which text belongs to the same line, block, table, row, column, or other source-local region.
- Whether a reading came from native PDF text, OCR, or model-based visual interpretation.
- Whether a spatial relationship is established by source geometry or is merely inferred.
- How extracted values relate to specific, immutable source artifacts.

The system must distinguish **source text recognition, spatial evidence, structural interpretation, and engineering meaning**.

OCR output is an observation produced by a recognition engine. Even when its position is established from the OCR engine's output, the recognized characters are not independently verified ground truth. Likewise, native PDF text and its coordinates do not automatically establish the semantic relationships between equipment and values.

Phase 6E must improve extraction capability without weakening these distinctions.

### Important workflow instruction

**First inspect the repository and produce `docs/PHASE6E_PLAN.md`. Stop for review and approval before implementing M1.**

Use the five milestone boundaries below unless repository inspection demonstrates a concrete reason to revise them. Document any proposed changes rather than silently changing the scope.

---

## 2. Repository baseline and governing documentation

Inspect the latest accepted implementation of Phases 6A–6D.

At the time this request was prepared, the complete Phase 6D implementation was on:

`codex/phase-6d-tables-schedules`

The `main` branch had not yet incorporated that implementation.

Before starting, inspect the current repository state. Prefer the latest accepted baseline containing the full Phase 6D M1–M4 implementation. Do not accidentally branch from an older `main` that lacks Phase 6D.

Review these documents:

- `docs/specs/phase-6-evidence-structured-extraction.md`
- `decisions/ADR-008-evidence-candidate-extraction-architecture.md`
- `docs/PHASE6C_HANDOFF.md`
- `docs/PHASE6D_PLAN.md`
- `docs/PHASE6D_HANDOFF.md`
- `docs/PHASE6D_M1_HANDOFF.md` through `docs/PHASE6D_M3_HANDOFF.md`
- `docs/EXTRACTION.md`
- `docs/PROVENANCE.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/PROJECT_STATUS.md`
- Relevant Phase 3 processing specifications, implementation, and ADR-005.

Inspect the relevant implementation rather than relying only on the handoff descriptions.

Particularly important existing areas include:

- `packages/document-model`
- `packages/document-processing`
- `packages/provenance`
- `packages/ai`
- `packages/extraction`
- `services/document-worker`
- `services/extraction-worker`
- Existing document, extraction, processing, and evidence API services.
- Phase 6C/6D source loading, grounding, publication, runtime identities, stage planning, and evaluation infrastructure.

Reuse existing infrastructure wherever appropriate.

### Existing architectural boundaries

Phases 6C and 6D already provide:

- Immutable extraction runs and work units.
- Pinned source artifact identities.
- Native-text and image inputs.
- Versioned prompts, schemas, and execution profiles.
- Source-grounded equipment and attribute candidates.
- Table reconstruction and interpretation.
- Atomic publication and immutable history.
- Bounded OpenAI execution.
- Durable dependency/retry/cancellation handling.
- Offline evaluation infrastructure.

Phase 6E must extend these capabilities rather than replace them.

---

## 3. Scope and exclusions

### In scope

1. Spatial extraction of native PDF text.
2. OCR of scanned/image-based source pages.
3. A provider-neutral representation of OCR and positioned document text.
4. Versioned, reusable text/layout artifacts and source provenance.
5. Word, line, block, and applicable table-region geometry.
6. Conservative reading-order and layout reconstruction.
7. Hybrid native-text, OCR, and image preprocessing.
8. Spatial evidence resolution and source-region grounding.
9. Improvements to Phase 6C and 6D extraction using new versioned configurations.
10. Targeted handling of complex electrical schedules, merged headers, and irregular table layouts.
11. Reproducible evaluation and integration testing.

### Out of scope

Do not implement:

- Spreadsheet ingestion (reserved for Phase 6.5, after 6G).
- The Phase 6F extraction UI, review workspace, or general evaluation dashboard.
- Phase 7 definitive equipment identity resolution.
- Phase 8 electrical topology inference.
- Phase 9 cross-document conflict resolution.
- Phase 10 engineering validation.
- Phase 11 engineer acceptance or verification.
- Canonical engineering-model updates.
- Complete multi-page table stitching.
- A general-purpose document-understanding platform unrelated to engineering extraction.
- Unbounded AI/OCR retries, image enhancement, or recursive processing.

Simple source-local references may be preserved, but do not merge physical equipment identities or create topology.

The frozen `registry-v1` must remain unchanged.

Revision-wide `system_frequency` and `system_phase_count` remain manually authored metadata. Do not infer or write them through extraction.

---

## 4. Target architecture

The conceptual processing flow should be:

```text
Immutable Document
        |
        v
Phase 3 Document Processing
        |
        +-- Native PDF Text
        |
        +-- Analysis Image
        |
        +-- Stable Page Identity
        |
        v
Phase 6E Source Enrichment
        |
        +-- Native Text Geometry
        |
        +-- OCR Text + Positioned Tokens
        |
        +-- Spatial Layout Information
        |
        +-- Source/Region Reliability
        |
        v
Versioned Enriched Source Context
        |
        +----------------------------+
        |                            |
        v                            v
Phase 6C                    Phase 6D
Engineering Extraction      Table Extraction
        |                            |
        v                            v
Evidence + Candidates       Tables + Cell Evidence
        |                            |
        +-------------+--------------+
                      |
                      v
            Immutable Extraction Results
```

This is a conceptual diagram, not a mandate to introduce a new service or database entity for every box.

### Architectural recommendation

Prefer **a reusable, versioned source-enrichment boundary** over embedding OCR directly inside every engineering extraction stage.

An OCR result or spatial layout should be reusable by compatible extraction profiles without unnecessarily repeating recognition work.

However, Codex must evaluate the appropriate persistence and execution architecture before implementation.

Compare at least:

**Option A — Extend Phase 3 processing.** Add versioned OCR/layout artifacts through a new compatible processing configuration.

**Option B — Independent enrichment pipeline.** A durable processing/enrichment run consumes immutable Phase 3 artifacts and produces separately versioned spatial resources.

**Option C — Extraction-stage enrichment.** Each new extraction run prepares its own OCR/layout inputs.

Compare these options for provenance, historical compatibility, reuse, performance, storage, worker scheduling, retries, cost, and schema complexity.

My default preference is Option B, provided the implementation can reuse the existing infrastructure rather than creating a redundant orchestration framework.

Document the choice and its consequences in `docs/PHASE6E_PLAN.md`.

---

## 5. Native PDF spatial extraction

For digitally generated PDFs, Phase 6E should use positional information available directly from the PDF whenever reliable.

The existing project uses PyMuPDF. Evaluate its native word/block/character geometry and table-detection capabilities before introducing another PDF parsing dependency.

The implementation should support, where possible:

- Positioned words, text spans, lines, and blocks.
- Source-native text identities and exact text offsets where provable.
- Page-level reading order.
- Multi-column text.
- Table boundaries and column alignment.
- Horizontal and vertical text relationships.
- Text aligned into visually meaningful rows or columns even when the PDF's native extraction order is incorrect.
- Repeated labels, tags, and numeric values.
- Appropriate handling of PDF rotation and upright-page coordinates.

**Do not assume that the order returned by a PDF library is the actual visual reading order.**

Do not infer an exact character-offset correspondence between two independently produced text representations unless it has been demonstrated.

For example, the native `Page.get_text("text")` output used by Phase 3 might not have the same order as a new geometry-aware extraction. A positional word can only receive an offset into the existing native text artifact when that correspondence is established.

Otherwise retain its own versioned representation and appropriate source coordinates.

### Native table reconstruction

Phase 6D deliberately requires an unambiguous contiguous pipe/tab structure before claiming `NATIVE_DELIMITED` table relationships.

Phase 6E should investigate whether reliable native geometry can establish additional row/column relationships in positioned PDFs.

For example, a PDF might visually contain:

```text
Equipment      Capacity      Primary      Secondary
TX-1           750 kVA       12.47 kV     600 V
TX-2           500 kVA       25 kV        480 V
```

But its native text artifact might contain all the equipment tags first, followed by capacity and voltage values.

If positioned words, column alignment, and other appropriate geometric evidence establish the table relationships, Phase 6E should make those relationships available to the table extractor.

Do not declare a structure verified merely because tokens happen to have plausible positions. Define explicit acceptance and ambiguity rules.

When structure is uncertain, retain the positioned observations and use an uncertain/visual-reported interpretation rather than asserting an unsupported relationship.

---

## 6. OCR provider and execution

Implement an actual functional OCR path for image-based documents, not only an abstract interface and synthetic tests.

### OCR provider selection

Investigate the existing `OCRProvider` abstraction in `packages/ai`.

Compare viable local OCR solutions, including Tesseract, against other appropriate alternatives. Consider recognition accuracy, positional output, deployment requirements, resource consumption, licensing, extensibility, and engineering notation.

Prefer a practical provider-neutral abstraction with one real adapter rather than implementing several OCR engines prematurely.

Local OCR is preferable when suitable because it can reduce recurring external costs and avoid transmitting private documents to another service.

Any external OCR service must be explicitly enabled, with clear processing and cost controls.

### OCR output

OCR should produce a versioned structured result containing appropriate information such as:

- Exact recognized text.
- Positioned words/tokens and lines.
- Source image/artifact identity.
- Pixel geometry and normalized upright-page geometry.
- Explicit recognition ordering.
- Optional engine-reported confidence, when available.
- Engine/version/settings identity.
- Recognition failures and limitations.
- Text representation and character-offset convention.

Choose the minimum sufficient contracts and avoid redundant copies of large textual data.

OCR confidence must not be treated as a calibrated probability of engineering correctness.

### Engineering text requirements

Test OCR against notation that occurs in power-system studies:

- Equipment tags such as `TX-1`, `CB-2`, `MSB-1`, and `MCC-3`.
- Voltages such as `12.47 kV`, `600 V`, and `480Y/277 V`.
- Transformer capacities and impedance percentages.
- Breaker ratings such as `400 AF / 250 AT`.
- Fault-current and X/R values.
- Cable sizes such as `4/0 AWG` and `350 kcmil`.
- Decimal points, negative signs, fractions, superscripts, and special characters where relevant.

Pay particular attention to character confusions such as `0/O`, `1/I/l`, `5/S`, missing decimal points, and incorrect unit characters.

Do not silently correct uncertain OCR readings into plausible engineering values.

An OCR reading of `12.47 kV` must not become `1247 kV` simply because an OCR engine missed a decimal point.

Preserve raw readings and uncertainty for downstream interpretation.

---

## 7. Hybrid source selection and fusion

Support three distinct source situations:

1. **Native PDF:** reliable native text, potentially with useful PDF geometry.
2. **Scanned/image source:** OCR text and OCR-reported word geometry, supported by the original image.
3. **Hybrid PDF:** a mixture of native text, embedded scanned content, irregular text layers, and visual content.

Use a conservative source-selection policy based on observable properties.

Do not automatically OCR every page if native content is already sufficient, but do not assume that the existence of a text layer means it is usable.

A document may contain some native text while important equipment schedules exist only as embedded images.

Define a bounded policy for OCR eligibility, including absent native text, poor coverage, text corruption, or specific unresolved regions when supported.

### Source fusion rules

Native, OCR, and AI-visual readings must maintain separate identities.

Avoid double-counting the same physical source text as two independent equipment observations simply because it appears in native text and OCR output.

Also avoid incorrectly merging two occurrences of the same value.

For example:

```text
TX-1: 600 V
TX-2: 600 V
```

The two `600 V` occurrences must remain distinguishable by source location and context.

Define rules for:

- Overlapping native and OCR text.
- Repeated values at different locations.
- Disagreement between native and OCR readings.
- Incomplete native text with supplementary OCR.
- Reading-order conflicts.
- Region-level source selection.
- Uncertain alignment.
- Source priority and conflict retention.

Do not silently replace a native value with an OCR value, or vice versa.

Where source representations disagree, retain their individual evidence and record the uncertainty.

---

## 8. Spatial geometry and evidence provenance

This section is a critical acceptance requirement.

Phase 6E must preserve the distinction between:

**Text authenticity:** What exact reading exists in a particular immutable text representation.

**Geometric provenance:** Where a token or region is located on an upright source page.

**Structural relationships:** Whether two readings actually occupy the same row, column, table, field, or equipment context.

**Engineering interpretation:** What the reading means according to registry-v1.

These are different claims and must not be conflated.

### Coordinate system

Use the established PowerForge source-location convention:

- Upright page after rotation normalization.
- Top-left origin.
- Normalized `x`, `y`, `width`, and `height`.
- Coordinates within the page bounds.

Ensure correct transforms between PDF page points, raster image pixels, OCR coordinates, and normalized page geometry.

Explicitly handle scaling, rotation, and image orientation.

Include negative tests for off-page boxes, invalid dimensions, incorrect rotation, swapped coordinates, and unsupported geometry.

### Evidence requirements

An OCR-backed text citation must reference the exact versioned OCR text representation whose characters and offsets it uses.

An image-region citation must reference a valid source image/page and a region supported by the selected source processing result.

Do not put OCR offsets into a native-text artifact.

Do not retrofit new bounding boxes or OCR text onto immutable Phase 6C/6D evidence from historical runs.

If a claim has no provable positional support, retain null geometry.

If an OCR engine reports a word box, preserve that as an OCR-derived location, not independently verified ground truth for the printed characters.

If a spatial process derives a region by combining several tokens, record or deterministically reconstruct the underlying support.

Use existing `Evidence`, `SourceLocation`, `CandidateEvidence`, and table/cell provenance wherever compatible.

New provenance contracts must be appropriately versioned.

### Persistence constraints

Inspect the current `PageArtifactType` enum, `PageArtifact` uniqueness rules, immutable processing-run model, and extraction evidence validation before designing OCR storage.

In particular, the current extraction publisher restricts text offsets to native-text artifacts. A new OCR text representation requires an explicit compatible validation path; it cannot simply be relabeled as native text.

Introduce migrations only when existing contracts cannot faithfully represent the required artifacts and ownership.

Any new persistence model should preserve immutable producer identities, storage object hashes, page ownership, and historical access.

---

## 9. Layout interpretation and table support

Phase 6E should provide useful structure to the downstream Phase 6D table extractor without rewriting its engineering interpretation architecture.

Support spatial reasoning for:

- Ordinary equipment schedules.
- Single-equipment specification tables.
- Multiple tables on a page.
- Tables without visible grid lines.
- Merged and hierarchical headers.
- Mixed row/column orientation.
- Sparse, blank, and unreadable cells.
- Text that visually belongs to a row or column but is ordered differently in native text.
- Tables with nearby titles, legends, footnotes, or unrelated text.
- Irregular, partially scanned, or mixed native/OCR layouts.

### Structure reliability

Define a source-backed distinction between:

- Independently established native document geometry.
- OCR-derived text and geometry.
- Deterministically supported structural relationships.
- Model-reported visual structure.
- Unresolved structure.

A positioned source token by itself is not proof of a table relationship.

Where table geometry is supported, retain the geometric evidence behind that conclusion.

Where confidence is insufficient, preserve the original cells/observations and mark structure uncertain.

Do not fabricate missing cells, infer missing units, or silently fill blank schedule fields.

### Compatibility with 6D

Reuse `ExtractedTable`, `TableLayout`, `TableCell`, `CandidateEvidence`, and existing source-local candidate relationships whenever suitable.

New table interpretation must still respect M2's:

- Conservative equipment associations.
- Multiple-tag ambiguity handling.
- Distinct readings within one cell.
- AF/AT clause handling.
- Exact registry normalization.
- Source-local rather than physical equipment identity.
- Immutable committed reconstruction prerequisites.

New spatial evidence must not bypass these checks.

Avoid creating an alternative, parallel table-extraction system.

---

## 10. Integration with Phases 6C and 6D

Phase 6E is not complete merely because OCR files can be generated.

The resulting text and layout information must be usable by the existing extraction system through a supported, versioned integration path.

### Versioning

Preserve accepted Phase 6C and 6D profile/runtime identities and behavior.

Do not alter the meaning of existing `engineering-openai-v1`, `tables-openai-v1`, or previously accepted test profiles.

If enhanced extraction requires different inputs, source roles, prompts, grounding rules, or processing semantics, introduce clearly versioned successor profiles and resources.

Do not simply update old identity hashes.

### Source selection

A new enriched extraction configuration must pin the exact source-enrichment result, including producer version, selected page, source artifacts, and material settings.

Retries must reuse the pinned compatible source results rather than silently consuming newer OCR output.

If an expected source artifact is missing, incompatible, or corrupt, fail explicitly according to the selected profile's documented requirements.

Do not silently substitute current processing results or unrelated page artifacts.

### Execution architecture

Reuse the existing extraction coordinator, worker infrastructure, durable stage dependencies, admissions, retries, cancellation, lease fencing, telemetry, and atomic publication.

If OCR preprocessing requires its own durable execution lifecycle, use the narrowest compatible design. Avoid introducing an unnecessary general-purpose scheduler.

Preserve:

- Explicit opt-in external processing.
- No automatic paid execution on document upload.
- Bounded CPU, memory, image and page processing.
- Bounded provider calls, timeouts, and retries.
- Correct failure/partial-result semantics.
- Immutable successful outputs.
- Stale-worker protection.
- Accurate resource and usage accounting.
- Safe handling of unknown costs.

Locally performed OCR must not generate fabricated OpenAI token counts.

### Compatibility with the existing response schemas

Evaluate whether the existing Phase 6C/6D model observation schemas can consume spatial context through new versioned adapters, or whether limited new schema versions are justified.

Preserve the conservative semantic interpretation rules.

New inputs may improve what the model can recognize and associate, but they must not cause its proposed geometry, equipment identities, or source text to become trusted merely because the model reported them.

Do not reimplement the entire Phase 6C/6D pipeline.

---

## 11. Examples of required behavior

### Example A — Scanned transformer nameplate

An image contains:

```text
TRANSFORMER TX-1
750 kVA
12,470 V / 600 V
Z = 5.75%
```

Expected:

- OCR provides recognized text and source-location information.
- Readings retain OCR provenance.
- Exact raw values remain available.
- Engineering interpretation can propose transformer attributes.
- Incorrect or uncertain OCR characters are not silently normalized.
- The equipment tag and attribute relationships are not given greater certainty than their source evidence supports.

### Example B — Positioned PDF equipment schedule

A PDF visually contains:

| Equipment | Rating | Voltage |
|---|---|---|
| CB-1 | 400 AF / 250 AT | 600 V |
| CB-2 | 600 AF / 400 AT | 600 V |

The native-text extraction returns column-major text.

Expected:

- Native spatial processing recovers positioned readings where possible.
- A supported geometry-based interpretation can establish separate equipment rows.
- Frame and trip readings remain distinct.
- Source text offsets are exact only when correspondence to the immutable text representation has been established.
- If row ownership remains ambiguous, the observations are preserved without confident associations.

### Example C — Hybrid drawing

A PDF contains ordinary native annotations and an embedded scanned equipment schedule.

Expected:

- Native annotations and scanned content retain separate source identities.
- OCR is applied only where justified by the selected policy.
- Overlapping readings are not indiscriminately duplicated.
- Resulting candidate evidence identifies the actual source representations.

### Example D — Ambiguous OCR

An OCR engine returns:

```text
TX-1 — 75O kVA
```

where the final character may be the letter `O` or digit `0`.

Expected:

- Preserve the OCR reading.
- Do not automatically convert `75O` into `750`.
- Retain uncertainty and avoid unjustified mapped numeric values.

### Example E — Merged headers

A schedule has a top-level `Voltage` header spanning two columns labeled `Primary` and `Secondary`.

Expected:

- Preserve the header hierarchy where geometry supports it.
- Do not assign a primary voltage to the secondary-voltage attribute.
- If the parent-child relationship is unresolved, preserve the observation without a guessed mapping.

### Example F — Repeated values

Two equipment rows both contain `600 V`.

Expected:

- The two values retain distinct source occurrences.
- A citation to one row cannot establish ownership over the other.
- Reprocessing or retrying does not merge the two observations.

---

## 12. Milestones and acceptance gates

### M1 — Contracts, geometry, and source identity

Deliver the pure contracts and foundational spatial utilities needed for OCR/layout support.

Include:

- Versioned source-enrichment contracts.
- Source-role and provider identity definitions.
- Positioned token/line/block representations.
- Coordinate normalization.
- OCR reading and native-position reliability vocabulary.
- Source occurrence and offset mapping.
- Bounded validation.
- Synthetic/native fixture contracts.
- Packaging and resource identity tests.

**Acceptance gate:**

Test coordinate transforms, rotations, repeated strings, exact source references, Unicode offsets, invalid geometry, unsupported roles, missing/ambiguous mappings, and version compatibility.

Do not introduce production OCR execution prematurely. Establish correct provenance contracts first.

### M2 — Native layout extraction, OCR, and durable artifacts

Deliver the actual preprocessing capability.

Include:

- Native PDF spatial extraction.
- One working OCR provider adapter.
- OCR eligibility and page/source selection.
- Durable versioned enrichment results.
- Immutable derived artifacts and hashes.
- Appropriate scheduling, retry, and resource bounds.
- Stable source/text/geometry relationships.
- Exact retrieval of previously completed enrichment results.

**Acceptance gate:**

Use actual generated PDFs and image fixtures, including scanned content.

Verify OCR output, positional data, artifact integrity, source ownership, versioning, retry safety, cancellation, and failure recovery.

Prove that completed Phase 3 runs and artifacts remain unchanged.

### M3 — Hybrid layout and geometry-aware table reconstruction

Deliver conservative, reusable spatial interpretation.

Include:

- Native/OCR overlap handling.
- Reading-order and spatial grouping.
- Evidence-backed table-region detection.
- Row/column reconstruction when supported.
- Merged/hierarchical header relationships.
- Uncertainty/ambiguity handling.
- Versioned integration contracts for Phase 6D.

**Acceptance gate:**

Demonstrate improvement over the original delimiter-only native table recognizer on positioned PDFs.

Test incorrect row/column alignment, repeated values, mixed source representations, competing tables, irrelevant nearby text, and ambiguous headers.

Ensure unsupported geometry cannot establish false equipment ownership.

### M4 — Extraction integration and evidence publication

Integrate the new enrichment capabilities into supported, opt-in extraction execution.

Include:

- New versioned enhanced extraction profiles where required.
- Exact pinned enrichment-context loading.
- Bounded provider inputs.
- OCR/region-aware source grounding.
- Integration with Phase 6C and 6D candidate/table conversion.
- Evidence persistence and public read compatibility.
- Existing extraction lifecycle guarantees.
- Historical profile/resource compatibility.

**Acceptance gate:**

Real disposable PostgreSQL/Redis/MinIO/Celery integration tests must cover source processing, enhanced extraction, table publication, cross-unit evidence, cancellation, retries, worker recovery, old active runs, and signed historical evidence.

Use mocked model transport for automated tests.

No candidate or table may publish fabricated source offsets, geometry, or an unsupported equipment relationship.

### M5 — Evaluation, regression, and final handoff

Deliver independent evaluation, final compatibility checks, and Phase 6E documentation.

Extend the evaluation system with suitable spatial/OCR measures rather than modifying the frozen 6C/6D evaluation policies.

The evaluation should cover:

- OCR character/word correctness.
- Engineering tag and value transcription.
- Native/OCR source selection.
- Word/line/region geometry.
- Reading order.
- Table detection and structural reconstruction.
- Header relationships.
- Equipment/value source-local association.
- Exact normalized values and units.
- Source evidence correctness.
- False claims and uncertain observation retention.
- Processing latency, memory, storage and provider costs where measurable.

Compare new supported enriched processing against the existing Phase 6C/6D behavior on equivalent documents.

Separate the effects of preprocessing, model recognition, and deterministic conversion.

**Acceptance gate:**

Complete relevant backend, worker, API, package, migration, and resource compatibility checks.

Document actual test execution, measured results, limitations, and any work deferred to 6F/6G.

Do not claim live OpenAI or real-world accuracy based on synthetic scripted observations.

---

## 13. Evaluation corpus requirements

Reuse existing Phase 6C/6D evaluation fixtures when suitable, but add independently annotated spatial/OCR cases.

Include representative samples of:

- Digitally generated PDF schedules.
- Scanned PDF schedules.
- Scanned transformer and breaker nameplates.
- Cable and utility-source schedules.
- Multi-column electrical specifications.
- Mixed native/image PDFs.
- Rotated pages.
- Low-resolution and noisy images.
- Missing or uncertain OCR characters.
- Merged and hierarchical table headers.
- Tables without visible grid borders.
- Negative examples and non-tabular drawing annotations.

At minimum, include the positioned PDF fixture introduced in Phase 6D and measure whether new source geometry reduces its existing native-only reconstruction limitation.

Use independently authored gold labels rather than extracting expected answers from the implementation.

Retain separate precision/recall denominators, source provenance, and explicit handling of missed/failed cases.

Do not manipulate ground truth to match conservative implementation output.

Real approved engineering documents may be used only when authorized and appropriately handled. No paid external model/OCR calls should occur without explicit authorization.

---

## 14. Historical compatibility and engineering safeguards

These requirements apply across every milestone.

1. Preserve accepted Phase 6C and 6D profile and runtime identities, serialized contracts, and previous results.
2. Never change an accepted resource identity merely by updating a stored test fixture.
3. Introduce new identities when new semantics require them.
4. Keep earlier runs readable and, where supported, executable with their original pinned configuration.
5. Never upgrade previously published page-level visual evidence to OCR text or spatial evidence retrospectively.
6. Preserve exact text and artifact hashes; reject mismatched provenance.
7. Avoid fabricating OCR confidence, text coordinates, missing table content, or source relationships.
8. Preserve `UNMAPPED` and `INVALID` candidates and raw observations.
9. Do not change canonical Equipment, EquipmentAttribute, topology, or revision-wide metadata.
10. Keep OCR execution independent of registry normalization and physical equipment identity resolution.
11. Preserve source-local repeated occurrences.
12. Keep external document/provider data untrusted, bounded, and excluded from routine logs.
13. Avoid unnecessarily repeating OCR or spatial preprocessing during downstream retries.
14. Do not automatically merge 6C and 6D results or change cross-profile summary semantics.
15. Do not add spreadsheet support, engineering review workflows, or topology inference.

An implementation that increases recall by silently weakening provenance or association checks is not acceptable.

---

## 15. Testing and verification

Prioritize meaningful tests that address source-grounding correctness and compatibility.

Avoid large numbers of trivial tests that repeat the same implementation details.

Important scenarios include:

- OCR recognition of plausible electrical notation.
- Corrupt or unsupported image inputs.
- OCR/text disagreements.
- Incorrect source artifact association.
- Incorrect rotation or coordinate normalization.
- Unavailable OCR engine or failed preprocessing.
- Repeated text in multiple page regions.
- Missing or mismatched text-offset sources.
- Incorrect native reading order.
- Incorrect table column/row reconstruction.
- Unrelated nearby labels or captions.
- Mixed native/OCR content.
- Incomplete OCR or model results.
- Large-page and memory bounds.
- Idempotent preprocessing and retry.
- Stale-worker and cancellation fencing.
- Exact evidence publication.
- No canonical model mutation.
- Historical compatibility with accepted profiles.
- Wheel/package resource availability.

Use real disposable infrastructure for tests requiring persistence, queues, or object storage.

Use actual PDF/image processing implementations in appropriate fixture tests rather than mocking the very OCR/layout logic under evaluation.

Mocks remain appropriate for paid AI services and controlled failure simulation.

Do not make paid OpenAI calls in automated CI tests.

---

## 16. Planning document requirements

Before coding, create:

`docs/PHASE6E_PLAN.md`

The document must include:

### A. Architecture

Explain the selected enrichment architecture and its relationship to Phase 3, 6C, and 6D.

Provide a concise pipeline diagram.

### B. Alternatives

Compare the architectural options in Section 4.

Also document the chosen native geometry extraction and OCR provider strategies, including deployment implications.

### C. Contracts

Specify:

- New source artifact representations.
- Versioned OCR/layout data structures.
- Coordinate and offset semantics.
- Source reliability levels.
- Producer and content identities.
- Downstream source-binding interfaces.

### D. Persistence and execution

Identify exactly which existing tables, workers, service functions, and APIs can be reused.

If new migrations or durable run/artifact entities are justified, explain the invariant they serve and why existing ones are insufficient.

### E. Extraction integration

Describe how Phase 6C and Phase 6D will consume new sources without changing their accepted historical behavior.

Identify the required new profiles, resources, and grounding changes.

### F. Five milestones

For each milestone, include:

- Objective.
- Scope.
- Deliverables.
- Dependencies.
- Acceptance criteria.
- Test strategy.
- Principal risks.

Do not arbitrarily split milestones into excessive implementation subtasks.

### G. Evaluation

Document the proposed corpus, baseline comparisons, metrics, and planned accuracy limitations.

### H. Open decisions

Highlight any material design questions that cannot be resolved from the approved specification or existing implementation.

Provide a recommended choice and rationale for each rather than asking open-ended questions.

---

## 17. Implementation workflow

1. Inspect the latest accepted baseline containing Phase 6D M1–M4.
2. Compare architectural options.
3. Produce `docs/PHASE6E_PLAN.md`.
4. Summarize important design choices, compatibility implications, risks, and milestone boundaries.
5. **STOP and request review/approval before writing Phase 6E implementation code.**

After approval:

- Implement milestones sequentially.
- Keep each milestone on a reviewable branch/commit state.
- Provide an appropriate handoff describing implementation and actual verification.
- Do not begin the next milestone until the previous review gate has been approved.
- Preserve all accepted historical resource identities unless an explicit versioning decision has been approved.
- Run full relevant regression at the final milestone, with targeted checks at intermediate milestones.

Do not present unexecuted tests as passing.

Do not claim functionality beyond the scope actually implemented.

---

## 18. Final deliverables and definition of success

At completion, Phase 6E should deliver:

1. Reusable versioned spatial document preprocessing.
2. Functional OCR processing for supported image-based documents.
3. Native PDF text geometry.
4. Hybrid native/OCR source context with explicit uncertainty.
5. Improved geometry-aware table reconstruction where justified.
6. Compatible enhanced engineering/table extraction.
7. Precise, defensible text and region evidence.
8. Durable artifact identities, retries, and immutable results.
9. Independent OCR/layout evaluation.
10. Full regression and compatibility verification.
11. `docs/PHASE6E_HANDOFF.md` and updated architecture/status documentation.

### Success criterion

**PowerForge must be able to transform supported scanned or spatially complex documents into better source-grounded engineering observations while retaining an explicit distinction between what was read, where it was found, how its spatial relationships were established, and what engineering meaning was inferred.**

The implementation should improve the capability of the existing extraction architecture—not bypass its provenance protections.

Phase 6E is complete only when actual OCR/layout processing and its downstream integration are demonstrated, not merely when new schemas and scripted observations pass.

**Start with repository inspection and the planning document. Do not implement M1 until the plan is reviewed.**