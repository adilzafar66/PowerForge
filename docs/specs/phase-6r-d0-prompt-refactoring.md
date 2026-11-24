# Milestone D0 — Attribute Extraction Prompt and Engineering Guidance Refactoring

## 1. Objective

Continue development on `codex/phase-6r-extraction-performance`.

Refactor the Stage 2 attribute extraction prompt and engineering guidance architecture to:

- Establish a concise, structured, universal extraction prompt.
- Separate source-format-specific instructions.
- Centralize attribute definitions and interpretation guidance within registry notes.
- Introduce optional equipment-level extraction guidance.
- Eliminate redundant and conflicting instructions.
- Allow the AI to exercise engineering judgment.
- Reduce unnecessary input-token consumption and improve maintainability.

Keep this milestone independent of Milestone D's output-contract optimization and response-reliability changes.

## 2. Target architecture

Establish the following separation of responsibilities:

| Component | Responsibility |
|---|---|
| Main extraction prompt | Universal extraction instructions and response requirements |
| Source-format guidance | Interpretation of the supplied source representation |
| Equipment extraction guidance | Equipment-specific conventions and relationships between attributes |
| Registry attribute notes | Definition and interpretation of individual engineering attributes |
| Equipment descriptions | Equipment classification during Stage 1 |

Each instruction should have one authoritative location.

Do not duplicate the same engineering guidance across multiple components.

## 3. Main attribute extraction prompt

Create `attribute_extraction_core_v1.txt` in the existing extraction prompts directory using the docs/specs/phase-6r-new-prompt-draft.md

Do not independently expand this prompt or introduce equipment-specific instructions. Identify any necessary contract compatibility corrections for review before implementation.

## 4. Source-format guidance

Extract source-format-specific instructions from the existing prompts into separately maintained resources.

Use the following proposed structure:

```text
prompts/
├── attribute_extraction_core_v1.txt
└── source_guidance/
    ├── compact_page_v1.txt
    ├── compact_page_v2.txt
    ├── readable_hybrid_v1.txt
    ├── image_only_v1.txt
    └── readable_text_v1.txt
```

Each resource should explain only:

- The structure of the supplied source representation.
- Whether a page image is available.
- Interpretation of readings, coordinates, tables, and layout relationships.
- Interpretation of source conflicts and uncertainties.
- Permitted citation types and references.

Preserve all existing C2 citation-eligibility rules.

Do not duplicate universal extraction instructions or engineering guidance in these resources.

Do not modify the existing source representations.

## 5. Consolidate attribute guidance into registry notes

Currently, PowerForge maintains both:

- Attribute notes in `registry_v1.py`.
- `ATTRIBUTE_DESCRIPTIONS` in `extraction_descriptions.py`, transmitted through the `extraction_guidance` field.

These mechanisms overlap and can introduce redundant or conflicting guidance.

The intended architecture is for registry attribute notes to become the single authoritative source of attribute-level definitions and interpretation guidance.

### 5.1. Review existing guidance

Review the complete engineering registry and compare each applicable attribute's notes against `ATTRIBUTE_DESCRIPTIONS`.

Identify:

- Duplicate information.
- Conflicting instructions.
- Missing attribute definitions.
- Unnecessarily restrictive guidance.
- Equipment-specific distinctions.
- Guidance concerning relationships between multiple attributes.
- Requirement information already represented structurally in the registry.

### 5.2. Propose consolidated notes

Prepare revised registry notes that:

- Clearly define the engineering meaning of each attribute.
- Include useful interpretation guidance where necessary.
- Are specific to the applicable equipment type.
- Avoid repeating information already established by registry fields.
- Avoid repeating universal extraction instructions.
- Allow reasonable engineering interpretation.
- Remain concise and suitable for both human and AI consumption.

Move guidance concerning relationships between multiple attributes into equipment-level extraction guidance where appropriate.

Do not remove useful engineering information merely to shorten the notes.

Do not change attribute keys, types, units, enum values, requirement rules, criticality, applicability, or normalization behavior.

### 5.3. Eliminate redundant provider guidance

For the new catalog version, stop transmitting the separate `extraction_guidance` field once its useful content has been consolidated.

Do not retain an empty or null `extraction_guidance` field unnecessarily in the new provider-facing catalog.

Preserve historical catalog reconstruction and replay behavior.

Check all existing consumers of registry notes before making changes, including the registry API, frontend, validation, extraction, and documentation.

Do not remove historical resources that remain necessary for replay.

## 6. Equipment-level extraction guidance

Introduce optional equipment-specific extraction guidance, provisionally named:

`EQUIPMENT_EXTRACTION_GUIDANCE`

Maintain it within `extraction_descriptions.py` or an equivalent registry-owned engineering metadata resource.

Do not create separate text files for individual equipment types.

The intended separation is:

- `EQUIPMENT_DESCRIPTIONS`: Equipment classification guidance for Stage 1.
- `EQUIPMENT_EXTRACTION_GUIDANCE`: Equipment-specific attribute interpretation for Stage 2.
- Registry attribute notes: Individual attribute definitions and interpretation.

Equipment-level guidance should address matters such as:

- Relationships between engineering attributes.
- Common equipment-specific document conventions.
- Distinctions between easily confused parameters.
- Relevant contextual interpretation.

For example, low-voltage breaker guidance may explain the distinction between frame, trip, sensor, rating-plug, and pickup currents.

Bus guidance may explain the distinction between assembly-level ratings and individual device ratings.

These examples are illustrative, not approved final wording.

Equipment-level guidance must:

- Be optional.
- Be concise.
- Be keyed by the registry equipment type.
- Be supplied only for relevant recognized equipment types.
- Be supplied once per distinct eligible equipment type.
- Not duplicate registry notes or universal extraction instructions.

Do not write guidance for every equipment type merely for completeness.

## 7. Dynamic provider input

For the new configuration, Stage 2 should receive:

1. The revised universal extraction prompt.
2. The applicable source-format instructions.
3. The recognized equipment.
4. Applicable equipment-level extraction guidance.
5. The applicable registry attribute catalog, including consolidated notes.
6. The source material required by the selected input configuration.

Reuse the existing dynamic attribute catalog selection mechanism.

Prefer a simple equipment-guidance mapping in the provider input rather than repeating guidance for every equipment occurrence or attribute.

Do not introduce additional AI calls.

## 8. Versioning and execution integrity

Introduce a versioned experimental prompt and engineering-guidance configuration.

Reuse existing configuration and profile mechanisms where practical.

Ensure that:

- The selected prompt and guidance versions are pinned at run admission.
- Prompt resources, equipment guidance, and catalog contents participate in execution identity.
- Retries use the original pinned resources.
- Historical prompts and catalogs remain reconstructable.
- Request hashes, response audits, and publication identities remain consistent.
- Existing source and prerequisite integrity checks remain intact.
- Stage 1 recognition remains unchanged.

Inspect whether registry-note changes affect existing registry hashes or historical profile reconstruction. Propose the simplest compatible versioning strategy.

Keep the existing production configuration as the default pending evaluation.

## 9. Contract compatibility

Review the supplied main prompt against the existing Stage 2 response schema and deterministic validation rules.

Pay particular attention to:

- Required nullable fields.
- Equipment association states for extracted and inferred assertions.
- Raw-unmapped source-label requirements.
- Exact decimal representations.
- Unresolved and compound value proposals.
- Equivalent-unit representations.
- Evidence roles and eligibility.
- Existing assertion identifiers and collection limits.

Identify any ambiguity or incompatibility requiring a wording correction.

Do not modify the response schema or admission policies to accommodate the revised prompt.

## 10. Review and approval checkpoints

Before implementation, provide:

1. A concise architectural implementation plan.
2. Any necessary corrections to the supplied main prompt.
3. A comparison of existing and proposed registry notes.
4. Proposed equipment-level extraction guidance.
5. A list of removed, relocated, and consolidated engineering instructions.
6. The proposed versioning and historical-replay strategy.
7. Affected files, consumers, tests, and potential regressions.

Present engineering guidance changes for review and approval.

Do not independently finalize new engineering interpretations, revise registry semantics, or introduce additional extraction restrictions.

## 11. Testing and offline verification

Following implementation approval, add focused tests covering:

- Deterministic prompt assembly.
- Source-format guidance selection for all five input configurations.
- Dynamic selection of relevant equipment guidance.
- No repeated equipment guidance per occurrence.
- Consolidated registry notes.
- Absence of redundant extraction_guidance in the new catalog.
- Preservation of historical prompt and catalog identities.
- Profile pinning and retry consistency.
- Unchanged response schema and admission policies.
- Unchanged Stage 1 behavior.
- Existing citation eligibility and publication integrity.

Run relevant unit, PostgreSQL integration, registry API, debugger, lint, and build checks.

Produce representative assembled provider instructions and engineering catalogs for:

- Schneider panel.
- Simson Maxwell generator.
- Siemens breaker schedule.
- REX transformer.

Compare existing and revised representations in terms of readability, serialized size, estimated token consumption where supported, and duplicated guidance.

## 12. Controlled live evaluation

Prepare a controlled evaluation using the existing five pinned benchmark inputs.

Where practical, isolate the changes using the following configurations:

| Configuration | Main prompt | Engineering guidance |
|---|---|---|
| A — Baseline | Existing | Existing |
| B — Prompt candidate | Revised core and source guidance | Existing |
| C — Consolidated candidate | Revised core and source guidance | Consolidated registry notes and equipment guidance |

All configurations should use:

- `compact-page-v1` input.
- Medium reasoning.
- The same pinned recognition results and source artifacts.
- The same model, response schema, and admission policy.
- Identical timeout, service tier, and output-token ceiling.

Propose up to 15 Stage 2 calls with zero retries for the complete initial screening. Consider a smaller staged comparison if justified.

Measure:

- Input, reasoning, and visible output tokens.
- Provider latency.
- Extraction coverage.
- Engineering correctness.
- Equipment association.
- Inference correctness.
- Unsupported additional assertions.
- Evidence quality.
- Mapping and source-verification outcomes.
- Response-validation failures.

Pay particular attention to whether the revised instructions improve engineering interpretation without increasing unsupported inferences or incorrect critical mappings.

Do not execute paid provider calls without separate authorization.

## 13. Out of scope

Do not implement:

- Server-generated assertion identifiers.
- Raw-unmapped overflow corrections.
- Compact output serialization.
- Response-schema changes.
- Engineering registry structural changes.
- Mapping or normalization policy changes.
- Source-representation changes.
- Stage 1 recognition changes.
- Production evidence-localization changes.
- Reasoning-effort changes.
- Worker concurrency changes.
- Production timeout changes.
- Automatic modality selection.

These remain separate work packages.

## 14. Deliverables

Provide:

1. The revised universal main prompt.
2. Five source-format guidance resources.
3. Consolidated registry attribute notes.
4. Optional equipment-level extraction guidance.
5. A simplified provider-facing engineering catalog.
6. Versioned and deterministic prompt assembly.
7. Historical replay compatibility.
8. Automated tests and offline comparisons.
9. Representative assembled prompts and catalogs.
10. A proposed live evaluation procedure with explicit call and spending limits.

Document the results in:

`evals/phase6r/ATTRIBUTE_PROMPT_REFACTORING_EVALUATION.md`

Update the original performance specification to include the revised Milestone D0 scope.

## 15. Execution instructions

First inspect the current codebase and produce the architectural implementation plan and proposed engineering guidance changes.

Do not modify files or make paid provider calls during planning.

Keep the implementation simple. Reuse existing registry, extraction, configuration, and auditing mechanisms.

Following approval of the implementation plan and engineering guidance, implement the changes, complete automated testing, and perform offline verification.

Stop before live evaluation and request separate approval.

Do not promote any new production defaults without explicit authorization.