# PowerForge — Phase 6C: AI Equipment and Attribute Extraction

## Objective

Implement **Phase 6C — Engineering Equipment Recognition, Attribute Extraction, and Registry-Driven Normalization**.

Phases 6A and 6B are complete, reviewed, and merged into `main`.

Phase 6A established immutable extraction persistence, source evidence, typed candidates, grouping, and read APIs.

Phase 6B established reliable asynchronous extraction orchestration, provider integration, retries, recovery, cancellation, execution profiles, and usage telemetry.

**Phase 6C must introduce PowerForge's first real electrical engineering extraction capabilities.**

The system must recognize electrical equipment and extract engineering attributes from already processed source documents using OpenAI, validate those observations against the approved registry-v1, normalize supported values, preserve uncertainty, and publish evidence-linked extraction candidates.

The implementation must remain provider-neutral at the domain boundary, extensible across all registered equipment types, and compatible with the existing orchestration and persistence architecture.

### Repository

`adilzafar66/PowerForge`

**Branch:** `codex/phase-6c-engineering-extraction`

**Base:** Latest `main`, including accepted Phase 6B commit `5042af803d2863d5b49bd241c9f14f87809d6cb4`.

### Primary deliverables

1. Production engineering extraction profiles and versioned prompts.
2. Structured AI output contracts for equipment mentions and attributes.
3. Equipment recognition against registry-v1.
4. Registry-driven attribute identification and deterministic normalization.
5. Source-local equipment grouping, including tagless equipment.
6. Explicit handling of ambiguous, unmapped, and invalid observations.
7. Evidence-grounded conversion into the existing Phase 6A entities.
8. Integration with Phase 6B execution, provider, retry, and telemetry infrastructure.
9. Representative engineering extraction fixtures and focused evaluation tests.
10. Documentation and a Phase 6C implementation handoff.

**Implement Phase 6C only.**

---

## 1. Authoritative architecture and existing implementation

Before implementing anything, inspect:

```text
docs/specs/phase-6-evidence-structured-extraction.md
decisions/ADR-008-evidence-candidate-extraction-architecture.md

docs/PHASE6A_HANDOFF.md
docs/PHASE6B_HANDOFF.md

docs/EXTRACTION.md
docs/PROVENANCE.md
docs/ARCHITECTURE.md
docs/ROADMAP.md
docs/PROJECT_STATUS.md
```

### Registry authority

Inspect:

```text
packages/engineering-model/src/powerforge_engineering_model/
docs/specs/registry/
```

In particular, examine:

- `registry.py`
- `registry_v1.py`
- `definitions.py`
- `enums.py`
- `units.py`
- The approved registry-v1 JSON reference.

Use the existing equipment, attribute, enum, normalization, and unit-conversion APIs wherever possible.

**Do not modify registry-v1 or its engineering semantics to accommodate extraction.**

### Phase 6 implementation

Inspect the current contracts and execution boundaries in:

```text
packages/extraction/
packages/ai/
packages/provenance/

services/extraction-worker/
services/api/

database/migrations/
tests/
```

Pay particular attention to:

- `ExtractionPersistence.publish()`
- `ExtractionCoordinator`
- `execute_unit()`
- `ExecutionProfile`
- `ExtractionRequest` / `ExtractionResponse`
- `ProbeResult`
- The existing OpenAI extraction adapter.
- Source artifact selection and version pinning.
- Worker claim ownership and fencing.
- The six existing extraction GET endpoints and Phase 6B action endpoints.

The goal is to **extend this architecture**, not replace it.

### Priority of authority

1. Approved Phase 6 specification.
2. ADR-008.
3. Accepted 6A and 6B persistence/orchestration guarantees.
4. Registry-v1 and frozen Phase 5 engineering semantics.
5. Existing repository conventions.

Identify any material conflicts before making architectural changes.

---

## 2. Technical design ownership

You are responsible for choosing the technical architecture that best satisfies the approved requirements.

We have intentionally not prescribed every class, package, database relationship, prompt boundary, or internal interface.

Before implementation, inspect the repository and create a concise design document:

`docs/PHASE6C_PLAN.md`

The plan should explain:

- How equipment and attribute extraction stages will be organized.
- How registry metadata is presented to the model.
- The structured AI response contract.
- The deterministic mapping/normalization boundary.
- The evidence-grounding approach.
- How the new extraction stages integrate with Phase 6B.
- How the system will accommodate 6D table extraction and 6E OCR/layout.
- Material trade-offs and alternatives considered.

You may choose a single-pass or multistage approach, provided it meets the accuracy, grounding, reliability, and cost requirements.

For example, equipment recognition and attribute extraction could occur in one bounded model call or separate specialized stages. Make this decision based on engineering accuracy, observability, cost, and compatibility with the existing work-unit architecture.

Do not add a large framework simply to support hypothetical future capabilities.

Proceed autonomously on ordinary technical decisions.

If a change would violate an accepted architecture decision or require fundamentally changing Phase 6A/6B's persistence or execution semantics, document the conflict and request architectural approval before proceeding.

---

## 3. Intended extraction architecture

The following is a conceptual design, not a mandatory class or module structure.

```text
                  IMMUTABLE SOURCE DOCUMENT
                             |
                             v
              Completed Phase 3 Processing
                             |
                  Native Text / Page Images
                             |
                             v
                  Phase 6B Orchestration
                    Run / Work Units
                             |
                             v
             +----------------------------+
             | Phase 6C Engineering       |
             | Extraction                 |
             |                            |
             | Equipment Recognition      |
             | Attribute Recognition      |
             | Source-Local Grouping      |
             +----------------------------+
                             |
                             v
                Structured AI Observations
                             |
                             v
             +----------------------------+
             | Deterministic Validation   |
             |                            |
             | Evidence Grounding         |
             | Registry-v1 Mapping        |
             | Type/Enum Validation       |
             | Unit Normalization         |
             | Ambiguity Handling         |
             +----------------------------+
                             |
                             v
              Phase 6A Atomic Publication
                             |
            +----------------+----------------+
            |                |                |
            v                v                v
     SourceGroup       ExtractionCandidate   Evidence
                             |
                             v
                       CandidateEvidence
                             |
                             v
              INSPECTABLE EXTRACTION RESULTS
```

**The AI proposes interpretations. The application determines whether those interpretations can be safely represented as registry-mapped candidates.**

AI output must never be treated as verified engineering truth.

---

## 4. Equipment recognition

Implement equipment mention extraction against the existing 20 registry-v1 equipment types.

The architecture must be registry-driven rather than hard-coded for a handful of equipment types.

It should support all registered equipment categories through shared contracts and metadata-driven interpretation.

### Equipment recognition requirements

For a source passage or image describing equipment, identify where supportable:

- Equipment category/type.
- Explicitly observed equipment tag.
- Explicitly observed equipment name or designation.
- Source-local descriptive context.
- Supporting source evidence.
- Potential source-local grouping.

Use the exact registry-v1 equipment type identifiers when a type can be determined confidently.

Examples include:

- `TWO_WINDING_TRANSFORMER`
- `LV_BREAKER`
- `HV_BREAKER`
- `BUS`
- `CABLE`
- `UTILITY_SOURCE`
- `SYNCHRONOUS_GENERATOR`
- `INDUCTION_MOTOR`
- `FUSE`

These are examples, not an exhaustive list.

### Equipment identity boundaries

An extracted equipment mention is **not** a canonical Equipment entity.

Never:

- Assign a canonical equipment ID.
- Create an EquipmentLineage.
- Assume that identical tags across documents imply the same physical asset.
- Automatically merge equipment mentions.
- Invent equipment tags.
- Use current canonical model equipment as the source of extraction truth.

Cross-document equipment identity matching belongs to Phase 7.

### Tagless equipment

Equipment without an observed tag must still be extractable.

For example:

> 750 kVA dry-type transformer, 600 V secondary.

This describes a transformer even though no equipment tag is present.

PowerForge should be able to create an equipment mention or source-local group without inventing a designation such as `TX-001`.

The tag must remain null when absent.

### Unrecognized equipment

When a source clearly mentions equipment but the category cannot be mapped unambiguously to registry-v1, preserve the meaningful raw observation.

Do not force the equipment into the nearest available category merely to create a mapped candidate.

---

## 5. Attribute extraction

Implement attribute recognition using the attribute definitions belonging to each registry equipment type.

For recognized equipment, extract explicit engineering information such as:

- Ratings.
- Voltages and currents.
- Impedances and reactances.
- Equipment configurations.
- Manufacturer/model identifiers.
- Protection device characteristics.
- Cable characteristics.
- Other attributes defined by registry-v1.

These categories are illustrative; registry-v1 is authoritative.

### Core requirements

For every extracted attribute observation:

1. Preserve the original source expression.
2. Identify the source equipment context when justified.
3. Determine whether a registry attribute mapping is supported.
4. Preserve the observed value and unit.
5. Normalize deterministically when supported.
6. Produce the appropriate mapping status.
7. Link the candidate to actual source evidence.

Do not fabricate missing attributes or fill required fields using engineering assumptions.

### Registry-driven design

Avoid creating a manually maintained extraction mapping table that duplicates every registry attribute.

Use existing registry metadata, including:

- Equipment type.
- Attribute key and display name.
- Value type.
- Canonical unit.
- Allowed enum values.
- Notes and relevant semantic constraints.

The implementation may introduce limited, explicit extraction-specific aliases or terminology mappings where necessary.

However:

- They must be versioned or otherwise reproducible.
- They must not become an independent competing engineering registry.
- They must not change canonical attribute definitions.
- Ambiguous aliases must not force a mapping.

The system should accommodate all registry attributes without requiring new application code for each one.

We will validate the first implementation most deeply against representative equipment families.

---

## 6. Engineering example — Transformer

Consider this source:

> Transformer TX-101  
> Rated Capacity: 750 kVA  
> Primary Voltage: 12.47 kV  
> Secondary Voltage: 600 V  
> Impedance: 5.75%

PowerForge should recognize:

**Equipment mention**

```text
Equipment type: TWO_WINDING_TRANSFORMER
Observed tag:   TX-101
Source group:   Local transformer observation
```

**Candidate attributes**

| Registry attribute | Source value | Normalized value |
|---|---|---|
| `rated_apparent_power` | 750 kVA | 750 kVA |
| `primary_voltage` | 12.47 kV | 12.47 kV |
| `secondary_voltage` | 600 V | 0.6 kV |

The source's impedance value should be retained.

Registry-v1 defines `positive_sequence_impedance` in percent for a two-winding transformer. Map the observation to that attribute when its meaning is sufficiently justified by the transformer context and approved semantics; otherwise preserve it as an unmapped observation.

Do not invent a zero-sequence impedance, X/R ratio, winding connection, or any other unspecified information.

### Expected candidate behavior

Mapped attributes should use the existing Phase 6A typed slots:

- NUMBER → Decimal.
- INTEGER → Integer.
- TEXT → String.
- BOOLEAN → Boolean.
- ENUM → Approved registry value.

Normalized numerical values must retain precision.

For example, the secondary voltage should become the decimal value `"0.6"` with canonical unit `"kV"`.

Never use binary floating-point arithmetic as the authoritative normalization mechanism.

---

## 7. Engineering example — LV circuit breaker

Consider:

> CB-101 — 400 AF / 250 AT  
> Schneider Electric

The system should recognize a potential LV breaker and preserve the observed designation.

It must understand that:

- `400 AF` refers to a frame rating.
- `250 AT` refers to a trip rating when that interpretation is justified by the device context.
- Neither value automatically establishes the sensor rating, rating-plug value, or long-time pickup setting.
- The manufacturer does not establish a specific trip-unit model.

Registry-v1 includes distinct attributes such as:

```text
frame_rating
sensor_rating
rating_plug
trip_rating
long_time_pickup
trip_unit_type
trip_unit_model
```

**Do not collapse these into one generic current rating.**

The extractor should preserve the distinctions that matter for short-circuit, coordination, and arc-flash studies.

Where an interpretation depends on a manufacturer's model or trip-unit design not provided in the document, preserve uncertainty rather than inventing settings.

This principle applies to other equipment categories as well.

---

## 8. Engineering example — Ambiguous and isolated attributes

Consider a page containing:

> Impedance: 5.5%

There is no clear equipment type or surrounding association.

The system should preserve the observed impedance claim but must not automatically assume:

- It belongs to a transformer.
- It is positive-sequence impedance.
- It is zero-sequence impedance.
- It belongs to a specific equipment tag.

The candidate may remain ungrouped and unmapped.

Another example:

> Rated current: 400 A

An attribute should not be discarded merely because the equipment mention or grouping cannot be identified.

**Isolated source observations are valid extraction results.**

For ambiguous mappings, leave `attribute_key` unset and retain the original expression in the unmapped candidate.

Do not invent equipment mentions simply to satisfy relational associations.

---

## 9. Structured AI output and deterministic interpretation

Create versioned Pydantic schemas for the model's structured observations.

**Do not require the model to directly generate database entities or fully normalized Phase 6A persistence payloads.**

The AI response should describe what it believes is present in the document. Deterministic application logic should then validate, normalize, and convert that response into the existing domain model.

A conceptual intermediate representation might be:

```text
EngineeringExtractionResponse
    |
    +-- EquipmentObservations[]
    |     +-- local reference
    |     +-- observed name/tag
    |     +-- proposed equipment type
    |     +-- source anchors
    |
    +-- AttributeObservations[]
          +-- local equipment reference (optional)
          +-- source label / expression
          +-- observed value and unit
          +-- proposed registry mapping
          +-- source anchors
```

This diagram illustrates required semantics, not mandatory class names or schema nesting.

The intermediate model should be bounded, versioned, and suitable for provider structured outputs.

### Separation of responsibility

**AI responsibilities**

- Recognize relevant source observations.
- Interpret source-local terminology.
- Suggest equipment and attribute mappings.
- Identify supporting source excerpts or regions.
- Express uncertainty or ambiguity.
- Return structured observations.

**Application responsibilities**

- Validate schema and output bounds.
- Verify source references.
- Check registry keys and permitted value types.
- Normalize units and enum values.
- Reject unsupported mappings.
- Preserve raw observations on mapping failure.
- Construct SourceGroup, Candidate, Evidence and CandidateEvidence records.
- Publish through the accepted Phase 6A boundary.

The model's proposed registry mapping is not authoritative.

### Required mapping behavior

Use the existing `CandidateKind` and `MappingStatus` semantics.

**MAPPED**

A supported mapping to a known equipment type or attribute, with valid typed value and canonical unit.

**UNMAPPED**

A meaningful observed claim that cannot be mapped confidently.

**INVALID**

An observed claim whose proposed normalization or structured interpretation fails validation and should be preserved with an appropriate diagnostic.

An invalid or unmapped candidate must not contain fabricated normalized values.

An ungrounded or hallucinated model claim must not be silently converted into a supported candidate.

---

## 10. Deterministic normalization

Use the existing registry APIs, especially:

```text
get_equipment_definition(...)
get_attribute_definition(...)
supported_input_units(...)
normalize_attribute_value(...)
```

Use them as the authoritative validation and normalization boundary.

### Numeric values

Preserve:

- Original value string.
- Original unit expression.
- Canonical registry value.
- Canonical registry unit.

Use Decimal-safe normalization.

For example:

```text
Source:     600 V
Registry:   secondary_voltage
Canonical:  0.6 kV
```

No conversion may be performed unless the attribute's meaning and the unit relationship are supported.

An unspecified source unit must not be silently assumed to equal the canonical unit unless the source context makes that unit unambiguous.

### Percent and per-unit values

Treat `%` and `p.u.` according to their distinct registry unit semantics.

Do not automatically convert between them or infer an impedance base without the necessary engineering context.

### Integer values

Preserve integers exactly, including values beyond JavaScript's safe integer range.

Use the existing INTEGER serialization contract.

### Enum values

Map a source expression to a registry enum only when the intended meaning is clear.

For instance, a cable described as having a copper conductor may be mapped to the registry's `COPPER` value.

Unknown or ambiguous enums must remain unmapped rather than being coerced to a convenient allowed value.

### Boolean values

Preserve explicit false values.

Do not interpret the absence of a statement as false.

### Precision and consistency

Avoid custom parallel unit-conversion engines.

Use registry-v1's existing Decimal-safe utilities, semantic contexts, and constraints.

---

## 11. Source evidence and grounding

**Every supported production extraction candidate must be grounded in the actual source document.**

Use the existing Evidence and CandidateEvidence entities.

### Native-text evidence

Where the source contains native text:

- Identify the relevant page.
- Use a verbatim source excerpt.
- Validate that the excerpt exists in the exact pinned text artifact.
- Resolve source offsets deterministically, using the existing Unicode-codepoint convention.
- Associate the evidence with the exact versioned artifact.

Do not trust model-reported offsets without validation.

If a phrase appears multiple times, avoid arbitrarily attaching the claim to the wrong occurrence. Use verified contextual information where available; otherwise represent the less precise grounding honestly.

A plausible model-generated statement that cannot be located in the source must not be published as verified source evidence.

### Image/vision evidence

Phase 6C should support basic visual equipment and attribute recognition using the existing Phase 3 analysis-image artifacts where suitable.

For example:

- A readable transformer nameplate photograph.
- A breaker label.
- A clearly printed equipment specification.

Do not build the full OCR/layout system in this phase.

For visual evidence:

- Preserve the source page and exact image artifact.
- Use a normalized region only when it can be justified.
- Leave coordinates null when uncertain.
- Never invent text offsets for image-only evidence.
- Make page-level-only grounding distinguishable from precise text/region grounding.

Full OCR, detailed page-layout understanding, robust bounding-box extraction, and sophisticated hybrid processing remain Phase 6E responsibilities.

### Grounding failures

Make a clear distinction between:

- A supported observation with precise text evidence.
- A supported observation with only page-level visual evidence.
- An observed but ambiguous/unmapped claim.
- A provider claim that cannot be supported by source material.

A provider claim unsupported by the source should not appear as a trusted mapped result merely because it is syntactically valid.

Preserve meaningful source observations where possible, but do not persist invented engineering facts.

---

## 12. Source-local grouping

Use the existing `SourceGroup` entity to associate observations that belong together within the source document.

Examples:

- One transformer nameplate.
- One breaker specification section.
- One clearly identified cable description.
- Several attributes describing the same visible equipment.

The grouping should be conservative.

### Required behavior

- Groups may contain an observed equipment tag.
- Groups may be tagless.
- Attribute candidates may reference a source group, an equipment mention, both, or neither.
- Several claims may share evidence.
- Several claims may describe one source-local equipment group.
- Repeated tags must not automatically imply canonical physical identity.

Groups must be scoped to the extraction run.

For source-local keys, use stable and collision-resistant local identities that do not accidentally merge unrelated equipment on different pages.

### Cross-page considerations

The architecture should remain compatible with cross-page grouping in later phases, but do not implement speculative cross-document identity resolution.

If observations from separate pages cannot be associated confidently, preserve them independently.

### Competing values

If a document genuinely contains two differing values, preserve the individually supported observations.

Do not silently pick one winner.

Conflict detection and reconciliation belong to later phases.

---

## 13. Production extraction prompts

Create the first actual production engineering extraction prompts.

They should be versioned, maintainable, and stored with the extraction code or established prompt resources.

The prompts must include clear instructions about:

- Recognizing electrical equipment.
- Mapping to approved equipment types.
- Extracting source-grounded attributes.
- Recognizing engineering terminology.
- Handling unknown equipment.
- Preserving observed tags without inventing them.
- Handling ambiguity.
- Reporting observed values and units.
- Avoiding unsupported calculations and assumptions.
- Producing structured results compatible with deterministic validation.

### Prompt architecture

Prefer focused, composable prompts over one enormous static prompt containing the entire registry and every possible engineering rule.

Evaluate whether equipment recognition and attribute extraction should use:

- Separate specialized prompts/stages.
- A common prompt with targeted registry context.
- A bounded multistage workflow.

Choose the approach that offers the best balance of correctness, cost, and maintainability.

The prompt system must be capable of receiving relevant registry metadata dynamically or through a versioned representation derived from registry-v1.

**Do not maintain a second, manually copied registry of equipment attributes inside prompts.**

Prompt and schema identities must be pinned in extraction-run configuration for reproducibility.

Preserve the existing Phase 6B source-probe prompt and its historical behavior.

### Prompt injection resistance

All document text and images are untrusted source material.

Instructions embedded in uploaded drawings or documents must not override PowerForge's extraction rules.

Do not enable model tools, external browsing, or arbitrary code execution as part of the extraction prompt.

### Confidence

Do not treat model confidence as calibrated engineering certainty.

Use optional confidence metadata only if it has a clearly defined meaning.

Null is preferable to an invented or meaningless confidence score.

---

## 14. Integration with Phase 6B

Extend Phase 6B so its infrastructure supports production engineering extraction stages and output schemas.

The current system uses:

- `SOURCE_PROBE`
- `ProbeResult`
- Infrastructure-only execution profiles.

These must not remain the only possible execution types.

### Required extension

Implement an extensible execution contract that can select an appropriate stage-specific schema, prompt, provider response, and output converter.

Do so without weakening or duplicating:

- Work-unit claiming.
- Durable task delivery.
- Lease ownership and fencing.
- Cancellation.
- Retry limits.
- Concurrency limits.
- Provider-call accounting.
- Usage telemetry.
- Atomic publication.

### Provider-call accounting

Phase 6B's existing execution accounting assumes a bounded provider call per admitted unit.

If the Phase 6C design requires multiple AI calls, explicitly represent and account for them through suitable planned stages or an equivalent properly controlled mechanism.

Do not introduce hidden, unmetered provider calls.

Retries must preserve their original stage, prompt, schema, registry, artifact, and profile identities.

### Input strategy

The current probe chooses native text or an analysis image for each work unit.

Production extraction may need both modalities for a page.

Evaluate an appropriate way to support native-text and image inputs together while preserving exact artifact pinning and the existing limits.

Avoid rereading or resending unnecessary source material.

Do not silently reinterpret old source-probe runs or change their pinned profiles.

### Production profiles

Add explicitly identifiable production engineering extraction profiles.

They must be distinguishable from:

- `FAKE_TEST`
- `INFRASTRUCTURE_PROBE`

A successful infrastructure probe must never be presented as successful engineering extraction.

Preserve the previous profiles for compatibility.

### Provider integration

Use OpenAI as the initial real extraction provider.

Reuse the existing Responses structured-output adapter where possible, extending it for the production schemas.

Production engineering extraction must remain opt-in under the current external-processing controls.

Maintain provider-neutral contracts outside the integration adapter.

Ensure errors and malformed model responses flow through existing safe failure handling.

---

## 15. Engineering interpretation boundaries

Phase 6C must not become a general electrical engineering reasoning or study engine.

It should recognize what is stated in the source and normalize supported representations.

Do not automatically perform:

- Short-circuit calculations.
- Protection device coordination calculations.
- Arc-flash calculations.
- Transformer equivalent-circuit inference from incomplete data.
- Cable impedance estimation from conductor size alone.
- Manufacturer catalog lookups.
- Device curve selection based only on incomplete descriptions.
- Topology reconstruction.
- Equipment identity matching.
- Conflict resolution across documents.
- Engineering model completeness validation.
- Human verification or acceptance.

These functions either belong to future phases or require separately approved engineering rules.

### Revision-wide metadata

`system_frequency` and `system_phase_count` remain manual-only revision-level values.

Do not propose or update them through extraction.

Equipment-specific frequency and phase-count values may be extracted only when clearly attributable to an equipment-specific registry attribute.

A statement like "60 Hz" in a document must not automatically set the revision's system frequency.

---

## 16. Implementation sequence

Use the following sequence as the development plan.

### Step A — Technical architecture

Inspect the approved system and create `PHASE6C_PLAN.md`.

Settle the key design choices:

- Extraction-stage structure.
- Intermediate model schema.
- Registry-context delivery.
- Evidence-grounding strategy.
- Conversion to WorkUnitOutput.
- Provider-call accounting.
- Existing profile compatibility.

Do not over-specify minor implementation details.

### Step B — Extraction contracts and prompts

Implement versioned structured-output models and production prompts.

Ensure they can represent:

- Equipment mentions.
- Attribute observations.
- Tagless equipment.
- Isolated attributes.
- Unknown equipment types.
- Unmapped and ambiguous attributes.
- Evidence references.

### Step C — Registry mapping and normalization

Implement the deterministic interpretation layer.

Validate equipment types, attribute keys, units, value types, and enum values using registry-v1.

Preserve raw observations on failure or ambiguity.

### Step D — Evidence and grouping

Convert structured observations into Phase 6A candidates, source groups, and citations.

Enforce source-artifact and page ownership.

Do not publish unsupported model claims as sourced facts.

### Step E — Operational integration

Add production profiles and stage execution through Phase 6B.

Maintain existing claims, retries, recovery, budgets, and telemetry.

Ensure the old infrastructure probes still work.

### Step F — Verification and handoff

Run focused domain tests, representative provider tests, integration tests, and relevant regressions.

Document actual supported extraction capabilities, unresolved limitations, and the integration contract for Phase 6D.

---

## 17. Testing and evaluation

The main acceptance criterion is **engineering correctness with source grounding**, not simply that the AI returns valid JSON.

Use meaningful, representative tests rather than exhaustive combinations of every attribute and equipment type.

### A. Equipment recognition

Test:

- Clearly tagged transformer.
- Tagless transformer.
- LV breaker.
- Cable.
- Utility source.
- Multiple equipment items on one page.
- Unsupported or ambiguous equipment category.
- Document containing no electrical equipment.

### B. Attribute interpretation

Test:

- Transformer kVA and winding voltages.
- Transformer impedance ambiguity.
- LV breaker frame versus trip rating.
- Cable length, material, and parallel-run count.
- Utility fault-current and X/R terminology.
- Known enum values.
- Unrecognized enum expressions.
- Explicit false Boolean.
- Large integer precision.
- Missing or ambiguous units.
- Multiple different values for the same attribute.

Ensure these use the actual registry-v1 keys and canonical units.

### C. Grounding

Test:

- Correct native-text substring and offsets.
- Repeated source phrases.
- Non-ASCII text and Unicode offsets.
- Missing or unverifiable excerpts.
- Source page/artifact ownership.
- Image-only page evidence without invented geometry.
- Multiple candidates referencing the same evidence.
- Unsupported claims excluded from trusted mapped output.

### D. Grouping and ambiguity

Test:

- One equipment mention with multiple attributes.
- Two separate equipment items on the same page.
- Tagless source groups.
- Standalone attributes.
- Uncertain equipment association.
- No invented equipment tags.
- No cross-document identity matching.

### E. Operational compatibility

Test:

- Production profile selection.
- Exact versioned prompt/schema identity.
- Existing fake and source-probe profiles unchanged.
- Successful WorkUnitOutput publication.
- Failed structured-response validation.
- Retry without duplicated successful results.
- Cancellation and stale-worker fencing.
- Accurate call/usage accounting.
- No canonical-model mutations.

### F. OpenAI integration

Use mocked OpenAI responses to verify:

- Production prompt selection.
- Structured-output validation.
- Provider response parsing.
- Usage tracking.
- Safe error handling.
- No credentials or raw document dumps in logs.

Do not perform live paid API calls in automated tests.

### G. Representative evaluation corpus

Create or maintain a small, reproducible collection of synthetic or appropriately anonymized electrical-engineering fixtures.

Include clear and ambiguous examples.

Where practical, provide expected equipment mentions, attributes, mapping statuses, normalized values, and evidence.

The evaluation should help measure:

- Equipment recognition precision and recall.
- Attribute mapping correctness.
- Value/unit normalization correctness.
- Evidence-grounding correctness.
- False-positive or hallucinated candidate rate.
- Preservation of meaningful unmapped observations.

Do not invent arbitrary accuracy targets.

A lightweight evaluation/reporting mechanism is sufficient for 6C. The larger evaluation harness and broader corpus belong to Phase 6F.

### Live-model validation

A manually initiated, opt-in OpenAI smoke test may be performed where credentials and source-processing permission are available.

Use an approved, non-sensitive fixture.

Report model responses and observed extraction quality separately from deterministic unit-test success.

If no live test is performed, clearly state that actual production-model accuracy remains unverified.

---

## 18. Acceptance criteria

Phase 6C is complete when:

- [ ] Real engineering extraction prompts exist and are versioned.
- [ ] Production extraction profiles are distinct from infrastructure probes.
- [ ] Equipment mentions are recognized using registry-v1.
- [ ] Tagless equipment can be extracted without fabricated tags.
- [ ] Meaningful isolated attributes are preserved.
- [ ] Registry attributes can be interpreted through shared metadata-driven logic.
- [ ] Supported values are normalized deterministically using registry-v1.
- [ ] Original values and units are preserved.
- [ ] Ambiguous, unmapped, and invalid observations remain explicitly distinguishable.
- [ ] Supported candidates retain meaningful source evidence.
- [ ] No fabricated text offsets, coordinates, equipment identities, or attribute values are introduced.
- [ ] Candidate/source-group relationships are source-local and conservative.
- [ ] OpenAI structured execution works through the existing provider infrastructure.
- [ ] Additional model calls cannot bypass Phase 6B admission, retry, and telemetry controls.
- [ ] Phase 6A atomic publication and immutable history remain intact.
- [ ] Existing Phase 6B fake/source-probe execution continues to work.
- [ ] Source-only results remain document-scoped and reusable under approved revision membership.
- [ ] The system never writes canonical equipment, topology, verification states, or revision-wide system frequency/phase count.
- [ ] Representative engineering tests demonstrate correct mapping, normalization, uncertainty handling, and grounding.
- [ ] Relevant regression and migration checks pass.
- [ ] Documentation accurately describes implemented capabilities and limitations.

---

## 19. Documentation and handoff

Update relevant current-facing documentation:

```text
docs/EXTRACTION.md
docs/PROVENANCE.md
docs/ARCHITECTURE.md
docs/ROADMAP.md
docs/PROJECT_STATUS.md
```

Preserve the approved specification and ADR unless a genuine architecture change is separately approved.

Create:

`docs/PHASE6C_HANDOFF.md`

Include:

1. Implemented extraction architecture.
2. Production prompt and schema identities.
3. Registry-context and normalization strategy.
4. Supported equipment and attribute semantics.
5. Evidence-grounding rules.
6. Handling of unmapped, invalid, and ambiguous observations.
7. Source-grouping behavior.
8. Integration with Phase 6B.
9. Actual tests and evaluation findings.
10. Any live-provider verification performed.
11. Known limitations.
12. Instructions for future prompt/schema evolution.
13. The extension contract for Phase 6D and 6E.

Clearly distinguish between:

- **Architectural support for all registry-v1 types.**
- **Equipment types validated by representative fixtures.**
- **Equipment types actually evaluated against a live model.**

Do not claim production extraction accuracy that has not been measured.

---

## 20. Future-phase compatibility

Phase 6C should leave a clean extension point for:

**Phase 6D — Tables and Schedules**

Structured extraction from single-equipment attribute tables, equipment schedules, and mixed tables, with independent row/cell grounding.

**Phase 6E — OCR and Layout**

Scanned sources, OCR artifacts, text-region mapping, and advanced hybrid visual preprocessing.

**Phase 6F — UI and Evaluation**

Engineer-facing candidate/evidence inspection, source highlighting, and a more comprehensive evaluation harness.

Do not implement their full functionality now.

However, avoid design decisions that force their future implementations to bypass or rewrite the Phase 6A/6B contracts.

---

## Final instructions

**Build PowerForge's first trustworthy electrical-engineering extraction capability, not merely a demonstration of structured LLM output.**

The implementation must prioritize:

1. **Engineering correctness.**
2. **Source grounding and provenance.**
3. **Conservative handling of ambiguity.**
4. **Registry consistency and exact normalization.**
5. **Extensibility to all registry-v1 equipment types.**
6. **Preservation of accepted orchestration and persistence guarantees.**
7. **Reasonable provider cost and execution complexity.**

Do not optimize solely for returning the largest possible number of extracted attributes.

A smaller set of correct, source-supported candidates is preferable to a larger set containing unsupported engineering assumptions.

Preserve the source's meaning and uncertainty.

Use focused tests that establish behavioral correctness. Avoid repetitive trivial tests, unnecessary abstractions, and premature implementation of later phases.

Implement on the dedicated Phase 6C branch, run the relevant validation suite, and provide a detailed handoff explaining what was actually implemented, tested, and left for subsequent phases.