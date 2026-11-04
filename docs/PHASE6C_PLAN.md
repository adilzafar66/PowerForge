# Phase 6C implementation plan — Engineering extraction

**Status:** M1 implemented: offline observation contracts, registry context, terminology and prompt definitions. M2–M6 remain pending; production engineering extraction is not executable yet. Delivery and checks: [M1 handoff](PHASE6C_M1_HANDOFF.md).

**Planning baseline:** `main` at `3ffb43f8fc5082817c7be5ec3d67dc94f44319f6`, including accepted 6B commit `5042af803d2863d5b49bd241c9f14f87809d6cb4` and the complete 6C prompt/additional clarifications. Refresh latest main before implementation and use `codex/phase-6c-engineering-extraction`.

Authority: [6C prompt](prompts/phase-6c-prompt.md), [approved Phase 6 specification](specs/phase-6-evidence-structured-extraction.md), [ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md), accepted [6A](PHASE6A_HANDOFF.md)/[6B](PHASE6B_HANDOFF.md) guarantees and frozen registry-v1. This plan extends those boundaries; no architectural exception is currently required.

## 1. Recommended execution structure

Use two required, explicitly planned work units per selected page:

1. **EQUIPMENT_RECOGNITION:** recognize source-local equipment mentions against the complete 20-type catalog; validate their grounding and type proposals; atomically publish equipment-mention candidates, evidence and conservative SourceGroups.
2. **ATTRIBUTE_EXTRACTION:** after that page's recognition unit succeeds, extract explicit attributes using registry metadata for the recognized equipment types and the original page inputs. Independently ground, interpret and normalize them; publish attribute/unmapped candidates and citations. Reference recognition-stage groups and mentions through the existing same-run publication contract.

Each claimed attempt permits at most one provider call. Both logical keys, dependencies and original source artifacts are planned before dispatch. There are no hidden recognition calls, per-equipment fan-out, repair calls or model-based validation calls. With no retries, an N-page production plan makes at most 2N calls; existing pinned admission limits remain the spending bound.

Recognition returning no equipment is a successful result, not a reason to skip attribute extraction. The attribute stage must still preserve standalone ratings, unknown labels and ungrouped observations. It may map an ungrouped attribute only when its own verified source context independently establishes the equipment type and attribute meaning. Missing association never requires inventing an equipment mention.

Recognition will not automatically merge repeated tags or observations on different pages. The attribute stage cannot silently create or revise recognition-stage results. If recognition misses equipment, retain meaningful standalone attributes conservatively; measure the resulting recall limitation rather than introduce an unaccounted rescue call.

**Why two stages:** registry-v1 contains 296 attribute definitions. A projection of their keys, labels, types, units, enums and notes is approximately 49 KB before source content. Recognition needs the small type catalog; attribute extraction benefits from the applicable definitions. Separate stages permit targeted context, independent measurement and retry of attributes without repeating successful recognition. The trade-off is two source-reading/model passes and a dependency gate.

**Alternatives:** a single page call is cheaper and operationally simpler, but either carries the full attribute catalog or risks excluding relevant types through speculative routing. Calls per equipment create more admissions, duplicate page input and additional failure boundaries. Neither is the initial implementation. No project-wide prompt or general workflow engine is proposed.

## 2. Contracts, prompts and reproducible identities

Add pure, versioned intermediate schemas in `packages/extraction`; they describe observations rather than database rows:

- Recognition observations: unique response-local reference, actual source expression, nullable observed tag/name, nullable proposed registry type, ambiguity indicator and bounded source anchors.
- Attribute observations: optional source-local equipment reference, original label/expression, original value string and unit expression, nullable proposed equipment/attribute keys, ambiguity indicator and source anchors. A separate normalized value supplied by the model is not authoritative.
- Anchors: a supplied source-role reference, exact quote with optional surrounding text, or a visual-page reference. The application resolves page/artifact identities. Do not request database UUIDs, trusted offsets or mandatory geometry from the model.
- Bound list sizes, strings, context and output. Reject malformed whole responses, duplicate local references and undeclared source references. A valid source observation that fails mapping is handled per observation; it must not cause loss of valid siblings. An incomplete/overflowed response is a unit failure, without half-publication.

Use composable recognition and attribute prompt resources. State source-only interpretation, no invented tags/default values, no engineering calculations, explicit uncertainty, source quotations, and refusal to follow document-embedded instructions. Keep registry context separate from untrusted source and upstream observation text. Enable no tools, browsing or arbitrary code execution. Confidence defaults to null.

Generate registry context through the existing registry APIs, including supported input units. Include exact identifiers, display names, value types, canonical units, allowed enums and relevant notes. Do not copy the registry into a manually maintained prompt catalog, parse XLSX at runtime, execute requirement rules, or treat notes such as “usually” and catalog-derived values as permission to infer missing facts.

Pin a production profile version containing the stage manifest, prompt/template and schema hashes, registry snapshot/projection renderer identity, terminology/mapping policy hashes, source strategy and all resource limits. Keep configuration within the existing 64 KB execution-control limit: store versioned identities/hashes, not repeated copies of every rendered registry catalog. Retain supported versioned resources; refuse unavailable historical versions instead of substituting current behavior.

The run's prompt/schema identity represents the complete stage manifest. Each AICall records its actual stage-specific schema and rendered-instruction hash. Attribute context is reproduced from the pinned registry renderer plus the unique immutable successful recognition attempt for the same page. Record/derive the successful upstream attempt identity consistently; retries cannot select mutable or latest-document context. Test that rendering and call identities remain identical across an attribute retry.

Extend the provider-neutral request/result envelope so execution selects an expected stage schema and revalidates that schema. Engineering schemas and converters belong to extraction; the neutral AI package must not import extraction or a vendor SDK. The worker adapter accepts the selected schema through this boundary. Use a small explicit stage-definition lookup, not arbitrary import paths or a plugin framework.

## 3. Deterministic interpretation and normalization

Treat schema validity, source grounding, semantic mapping and value normalization as separate checks. A valid proposed key plus a compatible unit is insufficient to establish a mapping.

1. Verify the relevant source expression and context before accepting model-proposed fields. Numeric values, units, tags and qualifiers must agree with the anchors. Prefer parsing the verified source lexeme to trusting an unrelated model-supplied value string.
2. Resolve equipment/attribute meanings against registry definitions. Use generated key/display-name matching plus a small versioned extraction terminology policy for clear aliases and qualified engineering shorthand. Resolve ambiguous matches conservatively; neither proximity nor a model confidence score establishes association.
3. Independently check the proposed key against that resolved meaning. For example, quoted “Secondary Voltage” cannot become `primary_voltage` merely because both accept kV. Ambiguous meaning remains UNMAPPED.
4. Establish the input unit explicitly, including a verified label/header unit where applicable, before calling `normalize_attribute_value()`. Its existing omission behavior assumes canonical units, so extraction must guard missing units before invoking it. Unitless registry fields are a different case.
5. Use the registry normalization APIs and Decimal/int values. Preserve raw strings/units, enforce existing typed slots and signed BIGINT bounds, serialize NUMBER/INTEGER as strings, retain explicit false and omit absent attributes. No float-based normalization, percent/per-unit/base conversion, new engineering bounds or duplicate conversion engine.

Required conservative interpretations include:

- Transformer capacity/winding voltages; normal two-winding impedance only with sufficiently clear source context under registry-v1 semantics. Do not manufacture zero-sequence impedance, X/R or winding connections.
- LV breaker AF/frame versus AT/trip, with device context sufficient for that distinction; no inference of sensor, plug, electronic long-time pickup or trip-unit model from those values alone.
- Cable conductor material/length/parallel-run count with their actual meanings; conductor size remains the registry TEXT representation.
- Utility three-phase versus SLG fault current/X/R only with explicit qualifiers or verified headings, without guessing a fault basis.
- Enum matching uses allowed values and unambiguous scoped terminology; unknown expressions remain unmapped. Explicit boolean expressions have a scoped interpretation, rather than treating absence as false.

**MAPPED:** source-supported meaning, known type/key, valid typed canonical representation. **UNMAPPED:** meaningful grounded claim with unresolved type/key/unit/association or unknown enum terminology. **INVALID:** grounded claim whose established interpretation cannot produce a legal typed/normalized value, including unsupported conversions or integer overflow. Preserve raw content and a bounded reason code; unmapped/invalid attributes have no normalized slots or `attribute_key`, consistent with 6A. Proposed keys may be retained as bounded diagnostics.

Reject unsupported model inventions from supported candidate publication. Retain safe aggregate rejection counts/reason categories without persisting invented facts as Evidence. Include these counts in the producing unit's existing `output_counts` in the same terminal write; do not update immutable completed units afterward. Empty valid output remains permissible and does not establish document completeness.

## 4. Grounding and source-local groups

**Native text:** verify bytes/size/hash and UTF-8 from the exact pinned artifact. Locate verbatim excerpts in that representation and compute Python Unicode-codepoint offsets. Verify label/value/unit/tag subexpressions against their source anchors. Use verified surrounding text to disambiguate repeated phrases. If an occurrence is unresolved, retain honest page/text grounding with null offsets and detach any unjustified equipment association; do not select the first occurrence arbitrarily. Only map a claim if its semantic context is still independently justified. Keep 6A publication's artifact verification and offset checks.

**Vision — user decision confirmed:** registry-valid visual observations may be MAPPED candidates with an explicit page-level visual grounding limitation. Bind them to the exact supplied analysis-image artifact. Leave unverified regions and all text offsets null. Keep model-transcribed text in the raw observation, not in Evidence as independently verified native text. Expose a stable grounding marker through safe candidate/evidence responses so consumers distinguish exact text, ambiguous page/text and page-level visual grounding. Mapping is a registry-validated AI interpretation, not proof that pixels were independently read or engineering facts verified. Automated checks cannot detect every plausible visual hallucination; representative visual/live evaluation remains necessary.

For hybrid inputs, choose evidence per observation; availability of native text does not make an image-derived transcription text-verified. Conflicting native-text and visual observations remain separate. Do not combine one modality's number with another modality's unsupported qualifier.

Create SourceGroups only for justified source-local associations. Use collision-resistant keys scoped by run, logical page/stage and source occurrence/local reference; tag text is not a grouping key. Keep separate equipment on the same page separate, allow tagless groups and leave uncertain associations null. Many candidates may share verified evidence. Attribute-stage candidates may cite committed recognition evidence/groups/mentions in the same run, as 6A already permits. Conflicting source-stated values remain individually visible.

## 5. Extending 6B while preserving its guarantees

### Stage scheduling and recovery

Pre-create both required logical keys per page, each with immutable stage metadata and pinned artifact IDs. An attribute unit's prerequisite is the recognition logical key for its own page.

- Dispatch and claim only after prerequisite success. Waiting consumes no admission and fabricates no call telemetry. Recheck under the existing run lock; broker ordering is never a dependency mechanism.
- An exhausted/permanent prerequisite failure settles its blocked downstream attempt as FAILED with a safe dependency error and no provider call. Perform this before parent aggregation in the same transaction. A pending automatic upstream retry keeps the dependent pending instead.
- Apply dependency settlement consistently after completion/failure, budget denial and expired-lease recovery. This prevents blocked PENDING units from leaving a parent permanently active. Preserve expiry-first recovery fairness; do not reintroduce the oldest-healthy-run scan.
- Manual retry appends eligible unsuccessful attempts, including blocked downstream work; it must not consume blocked attempt history when no upstream success or eligible retry can ever satisfy its prerequisite. Check dependency eligibility before appending. Successful recognition is immutable and is reused when only attributes fail.
- Cancel settles waiting and running units before the terminal parent state. Admission/concurrency locks, per-attempt tokens, leases/deadlines, transient storage retries, bounded backoff, durable delivery, telemetry and atomic 6A publication retain their authority. Do not add alternate execution paths around the coordinator.

No new candidate/entity tables or schema migration are expected. Existing run configuration, stage arrays, immutable unit metadata, source references and same-run result links can represent this bounded two-stage plan. Reproduce upstream context from the unique committed success for each prerequisite key. Preserve migrations 0011–0013; any later demonstrated need for operational storage must use a forward migration without weakening their invariants.

### Profiles and source inputs

Add explicit `ENGINEERING_EXTRACTION` profiles, provisionally `engineering-openai-v1` (native text plus analysis image when available; image-only supported) and `engineering-openai-text-v1` (requires native text). Both cover the same registry/stages. Source choice is pinned at run creation; no silent modality fallback on retry or storage failure. Keep the API's fake default and external-processing opt-in unchanged.

Replace production execution's single-artifact assumption with a bounded set of artifact descriptors. Verify each supplied artifact independently and enforce per-artifact and combined input, text/context, image-pixel and output bounds. Do not silently truncate oversized pages. Pin production vision detail/output limits separately from probe defaults. Send only the selected page and relevant upstream/registry context; load each needed artifact once per attempt, with no rereading unrelated pages. Separate worker attempts may necessarily reread/resend the page; this is the explicit two-stage cost trade-off, not a new artifact cache service.

Preserve the exact legacy profile serialization/identity, source-probe schema/prompt and fake behavior through a legacy profile reader and versioned production profile reader. Adding default fields to old profile serialization must not change its hash. Old active retries and completed reads must continue to work. Stage-specific production hashes/schema/call accounting replace probe hard-coding only on production paths.

Extend existing profile discovery, run details, usage and candidate/evidence read allowlists as needed. Keep included-document authorization and inherited/read-only revision access. Do not add extraction UI, new canonical writes, automatic extraction or revision metadata targets.

The OpenAI adapter continues to issue one bounded Responses structured call per admission with SDK retries disabled, no tools, `store=false`, safe errors and known/unknown usage handled honestly. Verify the installed SDK/schema behavior during implementation and mock all automated requests. No live paid call is authorized as part of M1.

## 6. Delivery milestones and review gates

Work through these milestones one at a time. Each should produce a focused, reviewable change with its own meaningful checks; Phase 6C is not complete until all gates are satisfied.

### M1 — Observation contracts, registry context and prompt definitions

Define bounded/versioned recognition and attribute schemas, source anchors, stage definitions, generated catalog/context projections, terminology policy and prompt resources. Establish canonical serialization/hashes and preserve the legacy probe contract. Start the representative fixture expectations here.

**Gate:** pure offline contract/context tests cover all 20 types and 296 definitions without duplicating the registry; schemas represent tagged/tagless/unknown equipment, isolated attributes and uncertainty. Registry-v1/reference files and probe hashes remain unchanged.

**Delivered:** the M1 gate passed with 40 new offline tests, 160 passing focused/regression tests in total, and built-wheel resource/import verification. Production profiles, interpretation, grounding, publication and stage execution remain pending. See [PHASE6C_M1_HANDOFF.md](PHASE6C_M1_HANDOFF.md) for identities, exact bounds and limitations.

### M2 — Deterministic semantic mapping and normalization

Implement generic metadata-based resolution, the limited scoped terminology policy, source-value checks, registry normalization and mapping-status diagnostics. Keep this independent of ORM/provider code.

**Gate:** representative transformer, LV breaker, cable and utility cases produce exact expected raw/typed values; wrong-but-valid key proposals, ambiguous impedance/ratings, missing units, unknown enums, false booleans, large integers and unsupported conversions are handled conservatively. No canonical requirements/default inference.

### M3 — Evidence, grouping and atomic output conversion

Implement exact-text grounding, repeated-phrase handling, honest visual grounding, local IDs/groups and conversion to WorkUnitOutput, including use of committed recognition context. Surface safe grounding/rejection metadata through existing publication/read boundaries.

**Gate:** Unicode offsets, duplicate phrases, forged excerpts/tags, image-only inputs, ambiguous associations, shared evidence and competing values behave correctly. Real disposable PostgreSQL publication/read checks prove ownership, same-run links and full rollback; no canonical rows are changed.

### M4 — Stage dependencies, compatibility and multimodal execution

Extend planning, dispatch, claims, aggregate/retry/recovery/cancel handling, artifact descriptors and versioned profile parsing. Use deterministic stage providers to exercise the complete production-shaped pipeline without a real model.

**Gate:** no early attribute call; upstream success survives downstream failure; blocked dependencies terminate correctly; eligible manual retry restores progress without resending successes; budget exhaustion, cancellation, duplicate delivery, restart, stale fencing and >100-run recovery remain sound. Two successful stages report two actual calls. Old profile hashes and historical behavior remain compatible.

### M5 — OpenAI adapter and production API profiles

Connect stage-specific structured parsing and prompts to the existing adapter; advertise opt-in production profiles and safe results. Pin production-appropriate resource limits and image detail without changing probes. Add actual worker/beat integration on disposable services.

**Gate:** mocked SDK tests verify the precise schema, instructions, modalities, call count, usage and safe failures; real Celery/Redis/PostgreSQL/MinIO tests publish grounded production-shaped candidates through existing APIs. No credentials/source dumps, hidden provider retries or canonical mutations.

### M6 — Representative evaluation, regression and handoff

Complete a small synthetic/anonymized text and image corpus with independently specified expected mentions, field meanings, values, status and grounding. Include clear/ambiguous/no-equipment examples and all four priority families. Provide a lightweight repeatable evaluator for recorded/mock outputs and a separately opt-in live OpenAI run on approved fixtures.

**Gate:** report equipment precision/recall, attribute mapping/value/unit correctness, grounding, false candidates and unmapped retention with explicit denominators and matching rules. Distinguish converter/mock correctness from measured live-model quality. Do not invent accuracy thresholds or claim unmeasured support. Live evaluation remains outstanding unless separately authorized and actually run.

Run the full backend regression and applicable schema/migration, dependency, formatting, lint and API checks on disposable infrastructure. The inherited 6B reference is 1,184 passing backend tests; that is prior evidence, not a result of this planning task. Update current architecture/extraction/provenance/roadmap/status documents and create PHASE6C_HANDOFF.md with actual outcomes, version evolution instructions, remaining limitations and 6D/6E extension contracts. Do not label 6C implemented in status docs before delivery.

## 7. Future phases and remaining decisions

6D can add table-oriented stage definitions and row/cell anchors using the same execution/publication path. 6E can add versioned OCR artifacts and verified region/text mappings through the bounded source descriptors and grounding layer. Neither requires bypassing accounting or treating group IDs as physical identities. General table reconstruction, OCR/layout, topology, cross-document matching, reconciliation, engineering completeness findings, UI and acceptance/verification remain out of scope.

The visual-grounding policy above was explicitly confirmed during planning. There are no unanswered architectural blockers. Concrete limits, naming and test fixtures can be finalized within the milestones using measured payload sizes and the existing bounds. A live evaluation needs separately authorized fixtures/provider access at M6; until then, actual model quality is unverified. If implementation reveals a conflict requiring changes to accepted immutability, execution guarantees or registry semantics, stop at that concrete conflict and request architectural direction.
