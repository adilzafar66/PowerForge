# PowerForge — Phase 6A: Evidence and Extraction Persistence Foundation

## Objective

Implement **Phase 6A — Evidence, Extraction Candidates, and Persistence Foundation** for PowerForge.

Phase 5 is complete and frozen. The UI-A through UI-F frontend work has also been merged into `main`.

Phase 6 establishes the infrastructure needed for AI-assisted extraction of engineering information from source documents. Phase 6A is the foundational persistence and API slice, not the implementation of the AI extraction pipeline itself.

**Implementation branch:** `codex/phase-6a-extraction-persistence`

**Starting point:** Latest `main`

Your responsibilities are to:

- Establish the Phase 6 extraction domain contracts.
- Implement persistent extraction runs, work units, evidence, source groups, tables, candidates, evidence relationships, and AI-call telemetry records.
- Introduce the appropriate database migration and ORM mappings.
- Implement the core read-only extraction API.
- Establish safe internal persistence boundaries for future extraction workers.
- Enforce provenance, ownership, immutability, data precision, and revision-access requirements.
- Add focused tests and complete the Phase 6A handoff.

**Implement Phase 6A only.** Do not proceed to 6B–6G.

---

## 1. Authoritative design documents

Before implementing anything, read and understand:

1. `docs/specs/phase-6-evidence-structured-extraction.md`
2. `decisions/ADR-008-evidence-candidate-extraction-architecture.md`
3. `docs/specs/phase-5-engineering-model.md`
4. `decisions/ADR-007-canonical-engineering-model-persistence.md`
5. `docs/ENGINEERING_MODEL.md`
6. `docs/PROVENANCE.md`
7. `docs/EXTRACTION.md`
8. `docs/ARCHITECTURE.md`
9. `docs/CODING_STANDARDS.md`
10. `docs/PROJECT_STATUS.md`

The approved Phase 6 specification and ADR-008 are supplied with this task. They are not yet part of the current `main` branch.

**First, add the exact approved documents to their designated repository paths.** Preserve their approved contents, including the D5, D12, and D23 clarifications. Do not recreate them from the older roadmap or improvise an alternative architecture.

### Source-of-truth priority

1. Approved Phase 6 specification — normative requirements.
2. Accepted ADR-008 — architectural ownership and design boundaries.
3. Frozen Phase 5 model, ADR-007, and registry-v1 — existing canonical engineering semantics.
4. Existing implemented document-processing/classification contracts.
5. Repository implementation conventions.

Where an older document conflicts with the approved Phase 6 specification, update the older document rather than weakening the approved decisions.

If an actual implementation constraint conflicts materially with a normative Phase 6 requirement, identify it explicitly rather than silently changing the architecture.

---

## 2. Inspect the existing architecture

Before coding, inspect the implementations of:

- Document and RevisionDocument ownership and inheritance.
- DocumentPage, DocumentProcessingRun, and PageArtifact persistence.
- Document classification runs, predictions, history, and their API services.
- Phase 5 canonical engineering-model persistence and registry-v1.
- Shared SQLAlchemy Base, API session management, transactions, and domain errors.
- Existing Alembic migrations through `0010_authoring_refinement`.
- Existing migration, integration, and API test infrastructure.

Use the existing module boundaries and conventions.

In particular, avoid duplicating existing document or page identities, replacing the shared persistence foundation, or coupling extraction contracts to FastAPI or any AI provider SDK.

### Architectural relationship

The intended logical model is:

```text
Document
   │
   └── ExtractionRun
          │
          ├── ExtractionWorkUnit
          │      │
          │      ├── Evidence
          │      │
          │      ├── ExtractionCandidate
          │      │
          │      └── ExtractionAICall
          │
          ├── SourceGroup
          │
          └── ExtractedTable

ExtractionCandidate
          │
          └── CandidateEvidence
                     │
                     └── Evidence
```

Each ExtractionRun also references the specific completed DocumentProcessingRun and pinned inputs from which its outputs were derived.

This diagram is logical, not a prescribed ORM-class layout. Follow the approved specification for exact ownership, relationships, and constraints.

**Do not create another canonical engineering model.** All Phase 6 extraction data remains separate from Phase 5 Equipment, EquipmentAttribute, ModelNode, and ModelConnection.

---

## 3. Domain contracts and persistence

Implement the Phase 6 entities and supporting enumerations defined in Sections 3 and 4 of the approved specification.

### 3.1 ExtractionRun

An ExtractionRun represents a document-scoped extraction execution with explicitly pinned input and configuration identity.

It must retain sufficient provenance to distinguish:

- The immutable source Document.
- The exact completed processing run and relevant artifact versions.
- Extractor, schema, registry, profile, provider/model, and prompt identities.
- Selected pages and configured stages.
- Relevant context fingerprints, if context-dependent extraction is ever used.
- Execution status, progress, timing, and sanitized errors.
- Deliberate re-extraction from a previous run.

Support the approved run statuses:

`PENDING`, `RUNNING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED`.

The database model must accommodate multiple historical runs for the same document without overwriting previous results.

Equivalent active runs must be structurally protectable against duplication, while completed runs must not prevent deliberate future re-extraction.

**6A responsibility:** Define and persist these contracts and relevant integrity constraints.

**6B responsibility:** Implement actual scheduling, execution, idempotent request handling, cancellation, and recovery.

Do not implement the 6B orchestration system prematurely.

### 3.2 ExtractionWorkUnit

An ExtractionWorkUnit represents an individual attempt to execute a stable logical unit of extraction work.

Examples of logical units include:

- Equipment extraction on page 3.
- Attribute extraction on pages 4–5.
- Table extraction from a bounded group of pages.

The schema must support stable logical unit keys, attempt numbers, retry ancestry, status, execution metadata, and result ownership.

Preserve append-only attempt history.

A successful unit's output must remain available even when another unit fails.

Historical attempts are retained, but the effective result of a run must select the successfully committed attempt for each logical unit rather than combining outdated or unsuccessful attempts indiscriminately.

Implement the persistence constraints and read semantics necessary to support this behavior.

Do not build automatic retries, leases, heartbeats, or a recovery scheduler in 6A; these belong to 6B.

### 3.3 Evidence

Evidence represents what a source document actually contains, independently of the AI's interpretation.

Each evidence record must identify its immutable source and preserve appropriate provenance:

- Document and DocumentPage identity.
- Producing work unit and relevant artifact version.
- Source kind and extraction method.
- Short verbatim source snippet, when available.
- Exact text-artifact reference and offsets, when available.
- Normalized upright-page region, when known.
- Table/cell location, when applicable.

Use Phase 3's established normalized page coordinates.

**Never invent a bounding box or text location when its geometry is uncertain.**

Keep source snippets concise. Reference versioned source artifacts instead of duplicating entire pages or images inside PostgreSQL.

Cross-document or cross-run evidence ownership violations must be rejected.

### 3.4 SourceGroup

Implement SourceGroup as a source-local grouping of observations potentially describing the same equipment instance within a document.

A SourceGroup is **not** canonical Equipment or EquipmentLineage.

Example:

```text
SourceGroup: group-001
  Equipment type hint: TWO_WINDING_TRANSFORMER
  Observed tag: null

  Candidate observations:
    Rated power: 750 kVA
    Primary voltage: 12.47 kV
    Secondary voltage: 600 V
    Impedance: 5.75%
```

These observations may describe one unidentified transformer, but that grouping does not establish a physical identity match.

Source groups must support missing tags and optional equipment-type hints.

Attributes must also be allowed to exist without a SourceGroup when reliable grouping cannot be established.

Phase 7 will use these records for possible equipment matching.

### 3.5 ExtractedTable

Implement the approved structure-preserving table persistence using versioned JSONB layouts and appropriate relational ownership.

The model must support at least these two orientations:

**Example A — One equipment, attributes in rows**

| Parameter | Value |
|---|---|
| Manufacturer | ABB |
| Rated power | 750 kVA |
| Impedance | 5.75% |

**Example B — Multiple equipment, one per row**

| Tag | Type | Rating |
|---|---|---|
| TX-101 | Transformer | 750 kVA |
| TX-102 | Transformer | 500 kVA |

The persistent structure must be capable of representing headers, rows, columns, cells, source locations, and layout metadata, including more complex or mixed arrangements.

Preserve the table's layout separately from the interpreted candidate values.

Do not introduce a rigid relational entity for every individual table cell.

Do not implement table detection or AI table parsing in 6A. Those behaviors belong to 6D.

### 3.6 ExtractionCandidate

Implement independently queryable candidates representing interpretations of source information.

The approved candidate kinds are:

- `EQUIPMENT_MENTION`
- `ATTRIBUTE_VALUE`
- `UNMAPPED_OBSERVATION`

Tables are modeled through ExtractedTable and SourceGroup rather than duplicated as generic `TABLE` and `TABLE_ROW` candidate blobs.

Candidates must support:

- Source expression and original units.
- Optional equipment mention association.
- Optional source group association.
- Registry equipment type and attribute references, where justified.
- Typed candidate values and canonical units.
- Explicit mapping status and normalization diagnostics.
- Optional confidence and provenance metadata.

Support mapping statuses:

`MAPPED`, `UNMAPPED`, `INVALID`.

Preserve raw source observations even when registry mapping is impossible or ambiguous.

**Do not require an equipment tag, equipment mention, or source group simply to persist an attribute.**

Do not generate `MISSING` candidates merely because an attribute is absent from a document. Absence by itself is not evidence.

#### Precision

Follow Phase 5's exact-value conventions:

- NUMBER values use Decimal/NUMERIC persistence and JSON decimal strings.
- INTEGER values use exact integer persistence and JSON strings.
- BOOLEAN values must distinguish explicit false from missing/null.
- ENUM values use registry-controlled text representations.

Avoid floating-point conversions that could lose engineering precision.

The contract should structurally support registry-valid mappings without implementing the actual AI extraction and normalization pipeline planned for 6C.

### 3.7 CandidateEvidence

Implement a many-to-many relationship between candidates and evidence.

A candidate can be supported by several source locations, while one source passage can support multiple candidate interpretations.

Support the evidence roles defined in the approved specification, where appropriate.

Enforce that candidate-evidence relationships remain within the same extraction/document ownership context.

Source-grounded candidates should carry supporting citations. Candidates without supporting evidence must not be silently presented as verified or trusted observations.

### 3.8 ExtractionAICall

Implement persistence for technical metadata and usage telemetry associated with individual future AI calls.

The model should accommodate provider/model identification, prompt/schema versions, execution timing, outcomes, token usage, and estimated cost when the estimate has a known pricing basis.

Do not store credentials or unrestricted document contents in telemetry.

No live provider integration or API calls are required in 6A.

---

## 4. Database migration and ORM integration

Create a new Alembic migration following:

`0010_authoring_refinement`

Use an appropriate Phase 6A migration identifier, such as `0011_extraction_persistence`, consistent with repository conventions.

The migration must:

- Introduce the Phase 6 persistence entities and enumerations.
- Enforce required foreign keys, uniqueness constraints, and value constraints.
- Preserve document/page/processing-run ownership.
- Support versioned extraction runs and work-unit attempts.
- Enforce valid candidate/evidence relationships.
- Protect against invalid typed-value combinations and invalid numeric/coordinate ranges.
- Include indexes appropriate for document history, work-unit selection, candidate queries, and evidence retrieval.

Follow the repository's existing PostgreSQL and SQLAlchemy patterns.

Migration definitions must be historically stable; do not import mutable runtime registry definitions into frozen migration files.

### Ownership invariant

The following must not be possible:

```text
ExtractionRun:
  Document A
  ProcessingRun A

Evidence:
  Page belonging to Document B     INVALID

Candidate:
  ExtractionRun A
  Evidence belonging to Run B      INVALID
```

Enforce essential relational integrity at the database level wherever practical, supplemented by appropriate service-level checks for cross-record invariants that cannot be represented directly in SQL constraints.

Do not rely exclusively on frontend or API validation.

### Transactional publication boundary

Establish an internal persistence/service interface for writing the output of a completed logical work unit atomically.

Conceptually:

```text
Validated work-unit output
           │
           ▼
     DB transaction
           │
           ├── Evidence
           ├── SourceGroups
           ├── ExtractedTables
           ├── Candidates
           ├── CandidateEvidence links
           └── Work-unit completion
           │
           ▼
        COMMIT
```

If any part fails, the work-unit output and completion marker must not be partially committed.

This internal capability should be sufficient to exercise the persistence model in tests and serve as a clean foundation for the Phase 6B worker.

Do not implement external AI calls, Celery task execution, or a complete extraction orchestrator.

---

## 5. Core read-only extraction API

Implement the Phase 6A read APIs using the existing revision-document route namespace:

```text
/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}
```

The approved specification defines the complete Phase 6 API. Implement its read-only foundation in 6A:

| Method | Endpoint | Responsibility |
|---|---|---|
| GET | `/extraction` | Latest applicable extraction summary and current run information |
| GET | `/extraction/runs` | Paginated extraction history |
| GET | `/extraction/runs/{run_id}` | Run detail, statuses, and effective work-unit coverage |
| GET | `/extraction/runs/{run_id}/candidates` | Paginated/filterable effective candidates and evidence summaries |
| GET | `/extraction/runs/{run_id}/tables` | Extracted table summaries and source context |
| GET | `/extraction/evidence/{evidence_id}` | Evidence detail and source-page/artifact locator |

Include other minimal read contracts only where required by the approved specification.

### API requirements

All endpoints must:

1. Use existing project/revision/document ownership conventions.
2. Validate that the requested RevisionDocument belongs to the specified project/revision and references the relevant included Document.
3. Prevent access to results from unrelated projects, documents, pages, or runs.
4. Support viewing permitted historical extraction runs through appropriate revision-document membership.
5. Preserve complete and partial-result distinctions.
6. Return deterministic results and stable pagination.
7. Preserve exact numerical representations.
8. Use explicit Pydantic response contracts instead of returning ORM objects.
9. Follow existing API error conventions without leaking storage keys or internal secrets.
10. Perform no extraction or other side effects on GET requests.

For run candidates and tables, distinguish **effective committed results** from historical unsuccessful or superseded work-unit attempts.

Historical attempt details can remain available through run history, but must not accidentally contaminate the current candidate list.

Where evidence references an artifact, reuse established signed access mechanisms as appropriate rather than exposing private MinIO keys.

### Excluded API operations

Do not implement these endpoints yet:

- `POST /extraction/runs`
- `POST /extraction/runs/{run_id}/retry`
- `POST /extraction/runs/{run_id}/cancel`

Their execution semantics belong to Phase 6B.

It is acceptable to establish the internal persistence methods that future implementations will require. Do not expose incomplete operational functionality through public endpoints.

---

## 6. Preserve the boundaries between phases

This is a critical architectural requirement.

### Phase 6A creates infrastructure, not engineering truth

The following operations are prohibited:

- Creating or updating canonical Equipment records from extracted candidates.
- Creating or modifying EquipmentAttribute values.
- Setting canonical origin or verification state from AI outputs.
- Modifying topology nodes or connections.
- Modifying revision-wide `system_frequency` or `system_phase_count`.
- Inferring canonical equipment identity from untagged observations.
- Automatically reconciling conflicting candidate values.

For example:

```text
Document A:
  Transformer TX-101
  Rated power: 750 kVA

Document B:
  Transformer data
  Rated power: 750 kVA
  Impedance: 5.75%
  Tag: not stated

Phase 6:
  Preserve each document's evidence and candidates.
  Group observations within each source as appropriate.

Phase 7:
  Consider whether Document B describes TX-101,
  another extracted equipment mention, or another asset.

Phase 9:
  Reconcile conflicting information.

Phase 11:
  Engineer reviews and verifies applicable information.
```

Do not add speculative cross-document matching or a canonical-model linking mechanism in 6A.

The future Phase 7 design may compare extracted equipment mentions with canonical Equipment and with other extracted equipment mentions. Such matches remain hypotheses until reviewed.

---

## 7. Focused test requirements

Add meaningful tests targeting Phase 6A's own responsibilities.

Avoid a large combinatorial test suite or tests that merely repeat database-column definitions.

### A. Persistence and ownership

Verify:

- ExtractionRun references a compatible completed processing run.
- Evidence cannot reference pages or artifacts from unrelated documents or processing contexts.
- CandidateEvidence cannot link incompatible runs or documents.
- Source groups and equipment mentions can be optional.
- Tagless and isolated observations can be persisted.
- Invalid coordinates, confidence values, and typed-value combinations are rejected.
- Multiple independent source claims can coexist without deduplication.

### B. Atomic publication and history

Verify:

- A successfully published work unit exposes its complete outputs.
- A failure during publication leaves no half-published successful unit.
- One successful unit remains available when another logical unit fails.
- Historical attempts remain preserved.
- Effective-result queries select the committed successful attempt for each logical unit.
- Historical or unsuccessful outputs do not leak into current candidate lists.
- Duplicate attempt keys and prohibited concurrently active identities are rejected.

### C. Precision and data semantics

Verify:

- Large INTEGER values survive persistence and JSON serialization without precision loss.
- High-precision decimal values retain their exact representation.
- Explicit BOOLEAN false is preserved.
- `UNMAPPED` and `INVALID` observations retain their original expressions.
- Missing source attributes do not cause fabricated extraction candidates.

### D. Read API and revision access

Verify:

- Extraction results are accessible from an eligible revision that includes the source document.
- Results can be reused across revisions inheriting the same immutable Document.
- Unrelated project/revision/document access is rejected.
- Superseded/read-only revisions can inspect permitted results without mutating their canonical model.
- Pagination and relevant filters work correctly.
- Partial runs are not represented as complete.
- GET endpoints have no side effects.

### E. Migration compatibility

Verify migration from existing Phase 5 data to the new schema.

Use a disposable PostgreSQL database and the repository's established integration-test conventions.

Preserve all existing project, revision, document, classification, equipment, attribute, and topology data.

Test fresh migration to head and a representative data-preserving upgrade from `0010_authoring_refinement`.

Ensure migration downgrade does not damage pre-existing Phase 5 tables.

---

## 8. Validation and operational constraints

Run the relevant repository checks:

- Ruff lint and format checks.
- Focused Phase 6A unit tests.
- Existing relevant backend regression tests.
- Live PostgreSQL integration and migration tests.
- Full backend tests when infrastructure is available.
- API/OpenAPI contract validation.
- Dependency checks and migration consistency checks.

No frontend code changes are expected for this slice. Run frontend checks only if shared changes could affect the existing frontend.

Use isolated/disposable infrastructure for database integration tests. Do not perform destructive testing against the normal development database or its storage volumes.

The current baseline has a known Python GitHub Actions infrastructure failure involving the unavailable `minio/minio:latest` image, while frontend CI passes. Distinguish this pre-existing infrastructure failure from any Phase 6A code failures. If necessary to establish meaningful CI validation, make only a narrowly scoped infrastructure correction and document it separately; do not broaden Phase 6A into an infrastructure redesign.

Do not claim a check passed unless it was actually run successfully.

---

## 9. Documentation integration

The approved Phase 6 specification and ADR-008 must be committed to the repository under their intended paths.

Update the current-facing documentation:

- `docs/ROADMAP.md`
- `docs/EXTRACTION.md`
- `docs/PROVENANCE.md`
- `docs/PROJECT_STATUS.md`
- Relevant architecture documentation where necessary.

The existing roadmap contains outdated Phase 6 descriptions.

Replace them with the approved 6A–6G implementation sequence, including:

- 6A — Persistence and read API.
- 6B — Orchestration and provider infrastructure.
- 6C — Equipment and attribute extraction.
- 6D — Tables and schedules.
- 6E — OCR and layout.
- 6F — Extraction/evidence UI and evaluation.
- 6G — Hardening and freeze.

Explicitly remove outdated guidance proposing automatic revision-wide frequency/phase-count extraction.

Record Phase 6A as implemented only after its actual acceptance checks pass. Keep 6B–6G unimplemented.

Do not modify historical accepted ADRs or Phase 5 handoffs.

---

## 10. Final handoff

Create:

`docs/PHASE6A_HANDOFF.md`

Include:

1. The actual base commit and implementation branch.
2. Summary of implemented entities and contracts.
3. Database migration and significant integrity constraints.
4. Explanation of document/revision ownership and inherited-document access.
5. Internal atomic publication boundary.
6. Implemented read API routes and response contracts.
7. How effective work-unit attempts are selected.
8. Tests executed, with actual results.
9. Migration and live-integration verification.
10. Any intentional deviations and their rationale.
11. Known limitations or risks.
12. Explicit handoff requirements for Phase 6B.

Clearly separate completed 6A infrastructure from 6B functionality not yet implemented.

Do not mark the entire Phase 6 complete.

---

## 11. Phase 6A acceptance criteria

Phase 6A is complete when:

- [ ] The approved Phase 6 specification and ADR-008 are committed and linked.
- [ ] All eight approved logical persistence entities have appropriate contracts and storage.
- [ ] The migration works against a fresh and existing Phase 5 database.
- [ ] Source document, page, processing-run, and artifact provenance is enforceable.
- [ ] Extraction results cannot mutate the canonical engineering model.
- [ ] Tagless equipment and isolated attributes can be retained without fabricated identities.
- [ ] Typed candidates preserve raw values, mapping status, and exact numeric precision.
- [ ] Tables can be stored without losing their source structure.
- [ ] Candidate-to-evidence relationships support multiple references safely.
- [ ] Work-unit output publication is atomic.
- [ ] Historical runs/attempts are preserved and effective outputs are selected correctly.
- [ ] Core read APIs provide authorized, paginated, read-only access to extraction history and data.
- [ ] Focused migration, persistence, and API tests pass.
- [ ] Current-facing documentation and `PHASE6A_HANDOFF.md` accurately reflect the implementation.

### Final instructions

Use the approved architecture rather than redesigning it.

Prioritize **correctness, provenance, immutability, data integrity, and compatibility with the future extraction pipeline**.

You have autonomy over class organization, internal naming, query implementation, and other ordinary engineering details, provided the normative requirements and architectural boundaries are satisfied.

Do not add unnecessary abstraction layers, speculative interfaces, broad refactoring, or tests with negligible engineering value.

Do not implement Phase 6B, actual AI extraction, OCR processing, table interpretation, frontend extraction screens, entity resolution, or engineer review workflows.

**Deliver a complete, tested Phase 6A foundation suitable for review before proceeding to Phase 6B.**