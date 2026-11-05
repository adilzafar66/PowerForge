# PowerForge roadmap

This is the authoritative high-level roadmap for intended future scope. [PROJECT_STATUS.md](PROJECT_STATUS.md) remains authoritative for implementation status. Approved implementation specifications and accepted ADRs override this roadmap when a phase is formally specified; this document does not authorize implementation or claim that planned work is complete.

PowerForge keeps **Phase 0–13: fourteen primary numbered phases**. Phase 4.5 is an intentional intermediate document-workspace UX phase. Phase 6.5 defers spreadsheet ingestion until after 6G and before Phase 7. Phase 5 has slices 5A–5G. Completed phases keep their historical numbering; later phases may have internal slices and design gates without adding top-level numbers. Keep the existing Phase 0–13 numbering and use subphases/gates for newly understood work rather than adding or renumbering top-level phases.

Phases 0–4 and 4.5 are complete. **Phase 5A through Phase 5G are implemented; Phase 5 is complete and re-frozen after the authoring refinement. Phase 6A delivery and validation are recorded in [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md); Phase 6B execution is documented in [PHASE6B_HANDOFF.md](PHASE6B_HANDOFF.md). Phase 6C M1–M6 definitions, interpretation, grounding/output conversion, dependent execution, opt-in production OpenAI integration and representative evaluation tooling are delivered; live-model quality remains unverified. Phase 6D M1 offline table definitions are delivered; 6D M2–M4 and 6E–6G remain unimplemented. See the [final 6C handoff](PHASE6C_HANDOFF.md).** Later phases are planned. The accepted foundations are [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md), the [Phase 5 specification](specs/phase-5-engineering-model.md), and the [Phase 5G freeze handoff](PHASE5G_HANDOFF.md).

## Phase map

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Architecture and repository setup | Complete; unchanged |
| 1 | Project and revision management | Complete; unchanged |
| 2 | Document management and revision inheritance | Complete; unchanged |
| 3 | Document processing | Complete; unchanged |
| 4 | AI document classification | Complete; unchanged |
| 4.5 | Document workspace UX | Complete; unchanged |
| 5 | Canonical engineering model | Complete / re-frozen; 5A–5G plus authoring refinement |
| 6 | Evidence, candidates, and structured extraction | 6A/6B and 6C M1–M6 implemented; live quality unverified; 6D M1 offline only; remaining work pending |
| 6.5 | Spreadsheet ingestion after 6G and before 7 | Deferred; unimplemented |
| 7 | Entity resolution | Planned |
| 8 | SLD and topology extraction | Planned |
| 9 | Reconciliation and conflict management | Planned |
| 10 | Deterministic engineering validation | Planned |
| 11 | Engineer review, verification, and audit | Planned |
| 12 | Model visualization | Planned |
| 13 | Study-tool integration, automation, and reporting | Planned |

## Phase 5 — Canonical engineering model

Phase 5 models the physical electrical system, independently of documents, AI providers, and study-tool vendors. It is evidence-ready; full Evidence/Candidate persistence begins in Phase 6. It does not implement AI extraction, a general ProtectionFunction persistence model, or complete operating/study configurations.

| Slice | Scope | Status |
| --- | --- | --- |
| 5A | Registry, canonical units, requirement engine, registry API | Implemented |
| 5B | Core persistence: EquipmentLineage, Equipment, EquipmentAttribute | Implemented |
| 5C | Revision model inheritance, `carry_forward_model`, revision-level model metadata and its inheritance | Implemented |
| 5D | Manually authored topology persistence: ModelNode / ModelConnection | Implemented |
| 5E | Revision-scoped engineering-model APIs | Implemented |
| 5F | Basic Engineering Model workspace UI | Implemented |
| 5G | Hardening, regression, documentation | Implemented; Phase 5 frozen |

The implemented registry contains 20 canonical equipment types, 296 attributes, and 44 requirement reference rows; verification vocabulary includes UNVERIFIED. Phase 5B adds typed equipment persistence and manual services without changing registry-v1. See [ENGINEERING_MODEL.md](ENGINEERING_MODEL.md).

Phase 5D adds relational topology nodes/connections, internal manual services, conservative equipment/node/connection lifecycle, and transactional graph cloning/remapping. Cable and physical bus remain Equipment; automatic profile terminals were subsequently added by the authoring refinement. See [TOPOLOGY.md](TOPOLOGY.md).

Phase 5E exposes revision-scoped equipment, attribute, node, and connection APIs through those services, with strict request allowlists, canonical response contracts, equipment search/type filters, lifecycle filters, and clean domain-error translation. No new migration, frontend, worker, extraction, or graph visualization work was added. Unpaginated listing and bulk topology validation remain future performance concerns. See [PHASE5E_HANDOFF.md](PHASE5E_HANDOFF.md).

Phase 5F adds the revision Engineering Model workspace alongside the default Documents workspace. Registry-driven equipment/attribute forms and explicit terminal/electrical-node/connection authoring use the existing APIs. Decimal-safe inputs, lifecycle warnings, and read-only handling preserve the accepted model semantics. No graph visualization or later-phase workflow is included. See [PHASE5F_HANDOFF.md](PHASE5F_HANDOFF.md).

Phase 5G resolves INTEGER API/browser precision with consistent string responses, verifies registry-v1 and cross-layer invariants, completes full live/offline/frontend regression and isolated clean-stack validation, and freezes Phase 5. The bounded performance review retains unpaginated lists as documented scaling debt. See [PHASE5G_HANDOFF.md](PHASE5G_HANDOFF.md) for evidence and remaining limitations. The subsequent Phase 6A foundation is documented below.

The post-5G [authoring refinement](PHASE5_AUTHORING_REFINEMENT_HANDOFF.md) adds automatic terminal profiles, NOT_POPULATED/reset semantics, a transactional unified Equipment editor and clickable topology tables. It does not introduce Phase 6 functionality or alter registry-v1.

### Implemented Phase 5C extension: revision-level model metadata

`system_frequency` and `system_phase_count` are implemented on the engineering-model snapshot rooted at `ProjectRevision`. No separate EngineeringModel entity was added, and their values are not copied into EquipmentAttribute rows. Equipment-specific registry frequency and phase-count attributes remain unchanged.

| Conceptual field | Meaning |
| --- | --- |
| `system_frequency` | Optional revision-wide common frequency, canonical unit Hz; for example 50 Hz or 60 Hz. Applies to equipment for which frequency is relevant. |
| `system_phase_count` | Optional common phase count, normally 1 or 3, set only when one count legitimately applies across the relevant system. A meaningful mix of single-phase and three-phase equipment leaves it null/absent. |

Null phase count means no common assumption is asserted. Do not introduce magic values such as 0, MIXED, or UNKNOWN without a later approved design.

The effective-value helper uses an explicitly PRESENT equipment value, otherwise the configured revision value for applicable equipment, otherwise no value. An explicit disagreement is preserved and reported with a deterministic mismatch flag. Phase 5C does not persist a finding or block edits solely because a mismatch exists.

These are revision assumptions, not fabricated document evidence. Avoiding copied defaults prevents duplicated values, mass updates, false provenance, and persistence noise. Explicit equipment values remain useful for source-stated data, differing equipment, mixed phase configurations, and later consistency comparisons. Changing a model-wide assumption must not silently overwrite explicit equipment values.

Migration `0008_revision_model_metadata` stores frequency as nullable Decimal/NUMERIC canonical Hz greater than zero and phase count as nullable integer 1 or 3. `carry_forward_model` controls both ACTIVE-equipment cloning and omitted metadata inheritance independently of document inheritance. Explicit values override and explicit null clears. Metadata edits use the established writable-revision rules. See [PHASE5C_HANDOFF.md](PHASE5C_HANDOFF.md).

## Post-core-Phase-5 canonical-domain design gates

The physical registry is not a complete coordination/arc-flash study-settings model. Two extensions need dedicated architectural decisions before implementation, early enough to give Phase 6 extraction and Phase 13 integration explicit target schemas. They do not reopen completed 5A/5B or introduce new primary phase numbers.

**Protection functions and study settings:** plan structured support for 50, 51, 50N, 51N, 67; pickup settings, time dial/time multiplier, curve family, instantaneous pickup, short-time and ground-fault settings, trip-unit stages, relay setting groups, relay → breaker relationships, and CT → relay relationships. A future dedicated ADR must define this subsystem; do not flatten it into arbitrary equipment attributes. ADR-007's exclusion of a general ProtectionFunction persistence model from Phase 5 remains intact. `LV_BREAKER.trip_rating` and `LV_BREAKER.long_time_pickup` remain canonical design/nameplate attributes and may coexist with separate study-adjusted settings without being overwritten.

**Operating/study configurations:** plan for NORMAL, STANDBY, ULTIMATE, EMERGENCY, MAINTENANCE, or project-specific scenarios. These may vary source in/out-of-service state, switch/tie state, generator availability, bus configuration, and other operating-condition overrides. A dedicated design decision is required before study-tool execution/export can be considered complete. No final schema is established here.

## Phase 6 — Evidence, candidates, and structured extraction

The [approved Phase 6 specification](specs/phase-6-evidence-structured-extraction.md) and [ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md) govern this phase. Document-scoped runs pin a completed processing run, exact artifacts and extractor/profile/registry/provider/model/prompt identity. Append-only work-unit attempts publish evidence, source-local groups, structure-preserving tables and independently queryable candidates atomically. Effective results select successful committed attempts; failed units do not erase successful siblings.

Candidates preserve raw expressions, exact typed values, mapping diagnostics and many-to-many source citations. Tagless groups and isolated attributes are valid. Groups do not identify canonical physical equipment. No Phase 6 path writes canonical equipment, attributes, topology or verification states. `system_frequency` and `system_phase_count` remain manual-only revision metadata: extraction neither proposes nor sets them. Source frequency/phase statements may be retained as justified equipment-specific registry values or unmapped observations.

Approved implementation sequence:

- **6A — Persistence and read API:** eight logical entities, pure contracts, migration, atomic publication, revision-scoped read APIs and focused integrity tests. See [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md) for validation status.
- **6B — Orchestration and provider infrastructure:** scheduling, provider/prompt/profile execution, retries, leases/recovery, idempotency, cancellation and telemetry collection. Implemented with explicitly labeled infrastructure/test profiles; production extraction remains deferred. See [PHASE6B_HANDOFF.md](PHASE6B_HANDOFF.md).
- **6C — Equipment and attribute extraction:** conservative registry mapping, normalization and raw/unmapped retention. M1–M6 definitions, interpretation, grounding/output conversion, dependent execution, opt-in production profiles/adapter and synthetic evaluation tooling implemented. Live-provider evaluation has not been authorized or run; production-model quality remains unverified. See [PHASE6C_PLAN.md](PHASE6C_PLAN.md) and the [final handoff](PHASE6C_HANDOFF.md).
- **6D — Tables and schedules:** M1 offline table observation/stage/layout definitions implemented; M2–M4 source grounding, publication, production execution and evaluation pending. Separate table-only and ordinary engineering runs are the approved design. See [PHASE6D_PLAN.md](PHASE6D_PLAN.md) and the [M1 handoff](PHASE6D_M1_HANDOFF.md).
- **6E — OCR and layout:** scans and hybrid native-text/vision preparation. Unimplemented.
- **6F — Extraction/evidence UI and evaluation:** read-only browsing, history, source navigation and evaluation harness. Unimplemented.
- **6G — Hardening and freeze:** full acceptance, regression, migration, cost/performance and accuracy checks. Unimplemented.

**Phase 6.5 — Spreadsheet ingestion** is deferred until after 6G and before 7. XLSX/XLS/XLSM/CSV ingestion is not part of 6D.

The entire Phase 6 is not complete. Protection/study-domain extraction still requires separately approved target-domain design. See [EXTRACTION.md](EXTRACTION.md) and [PROVENANCE.md](PROVENANCE.md).

## Phase 7 — Entity resolution

Determine whether extracted mentions/candidates refer to the same physical equipment lineage. Signals may include tag, equipment type, manufacturer/model, ratings, voltage, document context, location, connected equipment, spatial context, and topology context.

The bridge is `ExtractionCandidate → candidate physical identity → EquipmentLineage / revision-scoped Equipment`. Outputs remain match candidates or decisions with evidence and confidence. Low-confidence matches must not silently merge equipment; AI is not the identity source of truth.

## Phase 8 — SLD and topology extraction

Produce equipment/component candidates from single-line drawings, text/component associations, terminal/connectivity candidates, topology candidates, and source-page/bounding-box evidence. Target the manually authored canonical topology established in Phase 5D. SLD interpretation is not generic OCR, and the SLD remains evidence rather than the database. See [TOPOLOGY.md](TOPOLOGY.md).

## Phase 9 — Reconciliation and conflict management

Persist cross-source conflicts and suggestions. For example, an SLD may state CB-101 is 400 A while a shop drawing and nameplate state 600 A. Retain candidate values, supporting and conflicting evidence, source-priority information, agreement/disagreement, suggested resolution, confidence/explanation, and review status. Source priority is configurable, not universally hard-coded.

A suggested canonical value does not automatically become ENGINEER_VERIFIED. Phase 9 compares candidates/evidence and preserves conflicts; Phase 11 remains human authority. The final conflict schema requires a future design decision.

## Phase 10 — Deterministic engineering validation

Check Required/Critical completeness, structured requirement rules, engineering sanity, voltage and topology consistency, duplicate tags, study readiness, and deterministic cross-model rules. Include consistency between revision-wide assumptions and explicit equipment values: `system_frequency` versus equipment frequency, and `system_phase_count` versus equipment `phase_count`.

Phase 5A's pure requirement evaluator remains the foundation; Phase 10 adds the persistent findings/rule-execution workflow under a formal specification. Validation is not an LLM treated as truth. It flags problems without silently resolving reconciliation conflicts. Phase 9 reasons about cross-source conflicts, Phase 10 applies deterministic rules, and Phase 11 records engineer decisions. These may run iteratively even though implemented sequentially. See [VALIDATION.md](VALIDATION.md).

## Phase 11 — Engineer review, verification, and audit

Provide review queues, evidence inspection, accept/reject/edit, merge/split, conflict resolution, mark-unresolved actions, engineer review, engineer verification, and full audit/history. Preserve distinct verification states: UNVERIFIED, AI_EXTRACTED, SYSTEM_VALIDATED, ENGINEER_REVIEWED, ENGINEER_VERIFIED. AI_EXTRACTED must never silently become ENGINEER_VERIFIED.

Authentication, real user identity, project authorization, and actor-backed audit records are a **hard prerequisite/subphase for Phase 11 completion**. Pull auth/authorization forward if shared or multi-user deployment is needed earlier. Nullable actor UUIDs in current persistence do not meet this requirement. Do not create a fake users table or a new top-level phase for it. See [REVIEW_WORKFLOW.md](REVIEW_WORKFLOW.md).

## Phase 12 — Model visualization

Generate interactive topology and a one-line representation from the canonical engineering model. Include equipment detail/evidence navigation, completeness/status overlays, upstream/downstream exploration, and display of revision-wide frequency/common-phase assumptions where applicable. React Flow or equivalent may be used. Visualization must not create an independent source-of-truth database.

## Phase 13 — Study-tool integration, automation, and reporting

This is a downstream consumer of the verified canonical model, extending beyond file exports:

```text
Verified Canonical Model
    → revision-wide model assumptions
    → study configuration
    → tool-neutral translation/adapters
    → ETAP / SKM / EasyPower
    → study execution / automation
    → results ingestion
    → PowerForge result representation
    → engineering report generation
```

Adapters must receive applicable system frequency and common phase count without requiring duplicated per-equipment values. The canonical model stays independent of vendor schemas; tool-specific translation belongs downstream and must not reshape the model to mirror one vendor's internal objects. Report generation belongs here unless later requirements justify a separate phase.

Proposed planning slices, not commitments to launch every tool simultaneously:

| Slice | Planning scope |
| --- | --- |
| 13A | Tool-neutral study/export adapter contracts |
| 13B | ETAP export/integration |
| 13C | SKM export/integration |
| 13D | EasyPower export/integration |
| 13E | Windows study-tool agent / desktop automation |
| 13F | Study-results ingestion |
| 13G | Engineering report generation |
| 13H | End-to-end validation and hardening |

## Cross-cutting placement

| Work | Current placement |
| --- | --- |
| System frequency / system phase count | Phase 5C revision-level metadata |
| Evidence / provenance | Phase 6 |
| OCR / table / layout extraction | Phase 6 |
| Protection/settings model | Post-core-5 design gate before extraction/integration needs it |
| Operating/study configurations | Same post-core-5 domain-extension window |
| Auth / authorization | Phase 11 prerequisite, earlier if deployment requires |
| Full audit history | Phase 11 |
| Study automation / reporting | Phase 13 |
| Testing / evaluation / observability | Continuous across relevant phases |

These do not create new primary phases, including Phase 14. Future ADRs/specifications can revise placement when implementation evidence warrants it.

## Future ADR/design gates

No ADR numbers or final schemas are assigned here. Required future decisions include:

- Protection functions / study settings: dedicated ADR before implementation.
- Operating / study configurations: dedicated design decision before complete study integration.
- Evidence + extraction candidate persistence, including traceable extraction runs.
- Conflict / reconciliation persistence.
- Authentication / authorization and audit identity.
- Study-tool adapter / agent boundary.
- Study-results representation.
