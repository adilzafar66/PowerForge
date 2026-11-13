# ADR-008: Evidence, Candidate, and Structured Extraction Architecture

**Status:** Superseded for Phase 6R by [ADR-009](ADR-009-phase-6r-unified-extraction.md). Historical baseline decision.

**Date:** 2026-10-27  
**Decision owners:** PowerForge maintainers  
**Related phase:** Phase 6 — Evidence, Candidates & Structured Extraction  
**Specification:** `docs/specs/phase-6-evidence-structured-extraction.md`  
**Baseline:** Phase 5 re-frozen on `main` (`9dc13be02d7c3e1b447c9aab5dae9590156aa733`)

## Context

PowerForge already has immutable Documents, stable DocumentPages, versioned page-processing artifacts, document classification, and a revision-scoped canonical engineering model. The next step is to extract typed electrical-engineering information from drawings, photographs and schedules without confusing AI interpretations with engineer-verified model facts.

Engineering documents often contain values without unique tags, or describe the same physical device in different ways. A transformer SLD may show `TX-101 / 750 kVA`, while an untagged manufacturer drawing describes a `750 kVA` transformer with voltage and impedance. Matching the two requires cross-document reasoning and canonical-model context, which can be uncertain. Other documents use attribute-per-row tables instead of one-equipment-per-row schedules. A single prompt output cannot be treated as canonical truth, and retries must not silently replace prior evidence.

Phase 5's `ProjectRevision` is the canonical-model snapshot root (ADR-007). `Document` and `DocumentPage` are source-scoped (ADR-004/005). Phase 4 classification is an existing suggestion workflow (ADR-006). Phase 6 must integrate with these boundaries without introducing duplicate document identities, a second engineering model, provider-coupled domain types or premature review authority.

## Decision

1. **Document-scoped source-only extraction, revision-scoped access.** Completed extraction belongs to the immutable `Document` and explicitly pinned processing/artifact/model/prompt inputs. Revisions containing that same Document can inspect/reuse compatible results. `RevisionDocument` supplies membership/context, not duplicated candidates. Context-dependent extraction must include an explicit context fingerprint; default Phase 6 work does not use canonical Equipment as matching context.
2. **Separate source evidence and interpretation.** Persist `Evidence` as an immutable record of what a specific page/text/region/cell shows, and `ExtractionCandidate` as a typed or explicitly unmapped interpretation. Use `CandidateEvidence` for a many-to-many relationship; provenance belongs at individual candidate/value granularity.
3. **Preserve unidentified information.** `SourceGroup` describes observations belonging together within the source without asserting physical identity. An equipment mention and source group are both optional on attribute candidates. Preserve isolated facts and tagless equipment; never invent an equipment tag or canonical Equipment link to satisfy schema constraints.
4. **Structure-preserving tables.** Persist `ExtractedTable` in schema-versioned JSONB to retain headers/rows/columns/cells/layout, with relational, queryable candidates and links to table-cell evidence. Support both one-equipment attribute tables and multi-equipment schedules; neither is assumed to be the universal structure.
5. **Typed, registry-controlled mapping.** Use registry-v1 for recognized equipment types, attribute keys, value types and canonical units. Store raw expressions/units alongside normalized candidate slots. Keep ambiguous/unmapped/invalid observations rather than silently rejecting or coercing them. Exact decimal/integer string API representation remains mandatory.
6. **Manual-only revision-wide metadata.** `ProjectRevision.system_frequency` and `system_phase_count` are set only by manual engineering entry. Phase 6 neither generates revision-metadata proposals nor modifies these fields. A source frequency/phase statement may support an equipment-specific attribute or unmapped observation where justified.
7. **No physical identity inference in Phase 6.** Cross-document matching, linking tagless observations to TX-101 or canonical EquipmentLineage, ranking potential identity matches, and merging/splitting are Phase 7. Phase 6 does not write canonical equipment, attributes, topology or verification status.
8. **Versioned, partially recoverable runs.** `ExtractionRun` owns pinned input/configuration identity and a state machine `PENDING → RUNNING → COMPLETED | PARTIALLY_COMPLETED | FAILED | CANCELLED`. `ExtractionWorkUnit` records individually attempted stage/page/batch tasks, with stable logical keys and append-only retries. Effective results select successfully committed work-unit attempts; successful work survives failed siblings. Deliberate re-extraction creates a new run rather than overwriting old output.
9. **Atomic unit publication.** Successful work-unit candidate/evidence/table/group output and the unit completion marker commit transactionally. Failures never expose a half-published logical unit as completed. Recovery uses leases/heartbeats, bounded retries and database-backed idempotency to prevent duplicate billable active work.
10. **Provider-neutral hybrid extraction.** Reuse native PDF text where suitable, OCR/visual analysis where necessary, and specialized versioned prompts/schemas rather than one enormous project prompt. OpenAI is the first concrete AI model adapter; fake providers are required for deterministic automated tests. Use Celery/Redis/PostgreSQL/MinIO infrastructure and store `ExtractionAICall` telemetry without exposing credentials or full document content in logs.
11. **Read-only extraction presentation.** Users can initiate and inspect extraction, retry failed work, review run history, browse groupings/tables, and locate evidence on document pages. They cannot Accept/Verify/Merge candidates through Phase 6; those actions require later review and reconciliation design.
12. **Conservative early accuracy policy.** Prefer supported, explicit observations and preserve uncertainty/unmapped content. Confidence is optional and not automatically trusted or treated as proof. Use representative labeled engineering documents to evaluate false-candidate rate, completeness, normalization and grounding; adjust aggressiveness only after testing.

## Chosen logical entities

```text
Document ── ExtractionRun ── ExtractionWorkUnit (per attempt)
                              ├── Evidence
                              ├── ExtractionCandidate
                              └── ExtractionAICall
ExtractionRun ├── SourceGroup
              └── ExtractedTable (versioned JSONB layout)
ExtractionCandidate ── CandidateEvidence ── Evidence
```

Every Evidence, Candidate and table remains traceable to a specific immutable Document/Page and producing work attempt. Candidate mappings are not part of Phase 5 canonical tables. The Phase 6 specification is normative for fields, constraints, states, APIs, and slices.

## Rationale and rejected alternatives

| Alternative | Why not chosen |
|---|---|
| Save AI results directly as canonical Equipment/Attributes | Blurs suggestions and engineering authority; can overwrite manual/verified data and removes cross-document conflict history. |
| Persist extraction separately for each revision | Repeats expensive work against unchanged immutable documents and confuses document identity with revision inclusion. |
| Make every attribute reference an identified equipment mention | Loses untagged nameplate and standalone source values or forces invented equipment IDs. |
| Guess canonical equipment tags during extraction | Introduces revision-dependent identity assumptions, preventing safe reuse and bypassing Phase 7. |
| Store all candidates/evidence inside one JSON blob | Poor value-level queryability, FK integrity, deduplication and later reconciliation/review. |
| Represent every table cell as a mandatory relational row | Disproportionate schema complexity for heterogeneous engineering tables; JSONB layout plus independently queryable candidates preserves the necessary distinction. |
| Re-run the whole document on any batch error | Wasteful, loses useful successful work and increases cost. |
| Treat provider-reported confidence as a verified probability | Confidence is not reliably calibrated across providers, prompts or document styles. |
| Extract revision-wide frequency/phase-count as global proposals | A document-specific fact often is not a valid assertion about a complete power-system revision; these remain manual-only. |

## Consequences and trade-offs

**Benefits:** value-level evidence provenance, immutable AI history, clean Phase 7 entity-resolution inputs, capture of tagless observations, efficient reuse and targeted retry, and independent provider selection. Supports single- and multi-equipment tables without making JSON the canonical model.

**Costs:** additional relational entities and composite ownership checks; more careful orchestration and retry state logic; storage for historic artifacts/candidates; an extra interpretation step before observations become canonical. Phase 6 may show plausible values without knowing what equipment they belong to. This is intentional rather than a deficiency.

**Deferred:** cross-document entity matching and canonical association (7); SLD topology (8); conflict resolution (9); engineering validation findings (10); human accept/reject/verify, identity-backed audit (11); visualization (12); protection/operating-study domain and study-tool integration (separate design gates and 13). Enterprise-specific confidentiality features can be added later; baseline key isolation, bounded logging, access checks, and opt-in cloud extraction remain required.

## Compatibility and follow-through

- Do not change Phase 5 `registry-v1`, its relational canonical data structure, or ADR-007's model-snapshot ownership. Phase 6 state/outputs are separate.
- Reuse Phase 3 `DocumentPage` normalized upright geometry and versioned `PageArtifact` contract; do not replace immutable originals.
- Align with Phase 4's document-scoped extraction/classification history conventions without inheriting its unbounded stuck-RUNNING limitation.
- Update `docs/ROADMAP.md`, `docs/EXTRACTION.md` and `docs/PROVENANCE.md` when Phase 6 implementation starts, explicitly removing the now-obsolete **revision-level metadata candidate** statement. Implement via slices 6A–6G defined in the companion specification.
- **ADR accepted does not mean Phase 6 code exists.** Design is approved; Phase 6A is the next implementation step only when requested.
