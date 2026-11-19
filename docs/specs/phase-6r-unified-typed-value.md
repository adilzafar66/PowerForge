# PowerForge — Phase 6R Unified Typed Value Proposal Contract

## Codex Implementation Plan

**Repository:** `adilzafar66/PowerForge`  
**Baseline:** `main`, commit `e60fe171` (refresh before implementation)  
**Recommended branch:** `codex/phase-6r-unified-value-proposals`  
**Scope:** Stage 2 attribute extraction, deterministic validation, publication, persistence, read APIs, Documents UI, Extraction Debugger, and tests.

### 1. Objective

Replace the extracted-attribute-specific `proposed_enum_value` mechanism with a universal `proposed_value` that supports all five registry attribute types:

- NUMBER
- INTEGER
- TEXT
- BOOLEAN
- ENUM

The AI must propose a value representing the same source fact in a format compatible with the target registry attribute. It must not perform numerical calculations, unit conversions, rounding, truncation, or unjustified semantic transformations.

Retain the original `raw_value` independently. If an extracted value is ambiguous or cannot be safely represented as the registry type, the AI must return `proposed_value: null`.

PowerForge remains the authoritative validator and performs any permitted canonical unit conversions.

The implementation must not introduce another extraction stage, another AI call, a new engineering interpretation engine, or any automatic canonical-model writes.

### 2. Current implementation and deficiencies

The current Stage 2 contract, `phase-6r-attributes-v5`, defines:

**EXTRACTED:**
- `raw_value`: required string
- `proposed_enum_value`: optional string
- `proposed_unit`: optional string
- No `proposed_value`

**INFERRED:**
- `proposed_value`: required string
- `proposed_unit`: optional string
- No `raw_value`

The existing `publication.py::_value()` uses the original source string to parse numeric, integer, and boolean extracted values. Enum attributes use the separate AI proposal.

Therefore, a raw expression such as `3 Pole` may be semantically unambiguous but cannot be mapped by the present numeric parser.

The database already has a text-based `proposed_value` column for inferred candidates and a separate `proposed_enum_value` column.

This change should unify the contract and downstream handling, not simply rename one field.

### 3. Architectural invariants

Preserve all of the following:

1. Stage 1 equipment recognition remains unchanged.
2. Stage 2 continues to receive the pinned page context, recognition output, and applicable registry catalog.
3. No additional OpenAI calls are introduced.
4. `raw_value` remains a literal source transcription for EXTRACTED assertions.
5. `proposed_value` is a proposal, not an authoritative engineering value.
6. `normalized_value` is determined only by PowerForge.
7. The AI never converts a value into the registry's canonical engineering unit.
8. Exact decimal precision must be preserved. Never process engineering numbers through binary floating-point arithmetic.
9. Do not change ownership, evidence localization, source-value-support semantics, or attribute-origin classifications.
10. Ambiguous values, ranges, qualifiers, and multiple values must be preserved without arbitrary scalar selection.
11. Existing Stage 2 assertion-level quarantine and exact original-response auditing must remain intact.
12. Historical immutable stage results and candidates must remain readable without rewriting them.
13. Extraction does not update the canonical engineering model.

**Important:** A valid registry type does not by itself establish that a proposal faithfully represents the source.

---

## 4. New Stage 2 response contract

### 4.1 Version

Introduce:

- Stage 2 response: `phase-6r-attributes-v6`
- Aggregate wire identity: `phase-6r-wire-v6`
- Prompt bundle: `phase-6r-stages-v9`
- Attribute prompt file: `attribute_extraction_v8.txt`
- Publication version: `phase-6r-publication-v8`

Keep the Stage 1 recognition contract unchanged.

Do not change the compact page input, registry version, or unit-interpretation version unless an actual change to those contracts is necessary.

Pin all changed resources through the existing extraction profile manifest and hashes. Previously pinned incompatible work must fail admission explicitly, not silently resume under the new contract.

### 4.2 EXTRACTED assertions

Remove `proposed_enum_value` and add the required but nullable field `proposed_value`.

The field must contain one primitive value or null, corresponding to the applicable registry type.

| Registry type | Proposed JSON representation |
|---|---|
| NUMBER | Exact decimal string |
| INTEGER | JSON integer |
| TEXT | JSON string |
| BOOLEAN | JSON boolean |
| ENUM | Exact allowed enum string |
| Unresolved | JSON null |

Do not use JSON floating-point values for NUMBER. Do not accept JSON floats as INTEGER, and do not coerce a JSON boolean into an integer.

All EXTRACTED assertions retain the existing `raw_label`, `raw_value`, `raw_unit`, `proposed_unit`, `qualifiers`, `value_form`, `evidence`, association, ownership, and registry-key fields.

For `raw_unmapped`, retain the existing raw-only contract. Do not fabricate a registry proposal where no supported registry key exists.

### 4.3 INFERRED assertions

Use the same typed `proposed_value` representation for INFERRED assertions, with one important difference: it must be non-null.

An inference without one justified, concrete proposed value should be omitted.

Preserve `inference_explanation`, `inference_basis`, `source_expression`, and the existing inference evidence policy.

Do not generate inferred numeric values by performing arithmetic on source expressions. The previous prompt's provision for derived scalar interpretations must be reconciled with this new no-calculation policy.

Contextual inferences, such as identifying an electronic trip unit from reliable product-model knowledge, remain allowed when justified.

### 4.4 Example response fragments

The following are illustrative assertion fragments, not complete wire responses.

**Integer:**

```json
{
  "origin": "EXTRACTED",
  "attribute_key": "pole_count",
  "raw_value": "3 Pole",
  "proposed_value": 3,
  "raw_unit": null,
  "proposed_unit": null,
  "value_form": "SINGLE"
}
```

**Enum:**

```json
{
  "origin": "EXTRACTED",
  "attribute_key": "primary_connection",
  "raw_value": "Wye",
  "proposed_value": "WYE",
  "raw_unit": null,
  "proposed_unit": null,
  "value_form": "SINGLE"
}
```

**Number with an explicit unit:**

```json
{
  "origin": "EXTRACTED",
  "attribute_key": "rated_current",
  "raw_value": "1600 A",
  "raw_unit": "A",
  "proposed_value": "1600",
  "proposed_unit": "A",
  "value_form": "SINGLE"
}
```

**Ambiguous number:**

```json
{
  "origin": "EXTRACTED",
  "attribute_key": "rated_current",
  "raw_value": "400/600 A",
  "raw_unit": "A",
  "proposed_value": null,
  "proposed_unit": "A",
  "value_form": "MULTIPLE"
}
```

Use actual registry keys and allowed enum values in the implementation and tests.

---

## 5. AI prompt requirements

Update the Stage 2 prompt to explain the distinction between source transcription, typed proposal, and canonical normalization.

### 5.1 Permitted operations

The AI may:

- Identify a numeric literal within an unambiguous value expression.
- Remove clearly extraneous surrounding labels or formatting without altering the reported value.
- Match a source expression to an explicitly permitted enum.
- Interpret unequivocal affirmative/negative wording as a boolean.
- Propose the exact applicable supported source unit, using the existing unit policy.
- Preserve the original value unchanged when it already matches the registry's required type.
- Abstain by returning null.

The AI must prefer retaining the source numeric representation wherever possible.

### 5.2 Prohibited operations

The AI must not:

- Convert A to kA, V to kV, hp to kW, or any other unit.
- Multiply, divide, add, subtract, or otherwise calculate a numeric value.
- Round, truncate, interpolate, approximate, or estimate.
- Choose an arbitrary value from a range or list.
- Apply defaults based on typical engineering practice.
- Infer missing equipment settings or ratings.
- Change model numbers, catalog numbers, equipment tags, or identifiers.
- Substitute a related but different engineering attribute.
- Produce an enum that is not one of the registry's permitted members.
- Treat a valid data type as proof of correct engineering interpretation.

### 5.3 Ambiguity policy

When an extracted value cannot safely be interpreted as the registry type, return `proposed_value: null`.

Do not populate a NUMBER, INTEGER, BOOLEAN, or ENUM proposal with arbitrary text merely to avoid null.

TEXT proposals may retain their original raw string when the text is valid for the intended attribute.

If the source value itself is meaningful but its registry attribute is not established, preserve it through the existing `raw_unmapped` mechanism rather than inventing a registry mapping.

Keep `EXTRACTED` and `INFERRED` semantically distinct. Converting an explicit `Yes` to `true` is a typed interpretation of a source value, not an inference.

---

## 6. Deterministic proposal validation

Implement a focused proposal-validation boundary in the extraction package, integrated with the existing publication flow.

Avoid implementing a second general-purpose engineering semantic interpreter.

### 6.1 Structural validation

Use the local registry catalog to establish the expected value type.

Validate the proposed JSON primitive strictly:

| Registry type | Required checks |
|---|---|
| NUMBER | String, valid exact decimal grammar, finite, within existing numeric bounds |
| INTEGER | JSON integer, excluding boolean, within existing numeric bounds |
| TEXT | String satisfying applicable length/type requirements |
| BOOLEAN | JSON true or false |
| ENUM | String exactly matching a permitted registry member |

For an EXTRACTED assertion, null is valid at the response-schema level and means no typed proposal.

A non-null value of the wrong type must not silently be coerced.

Preserve assertion-level schema quarantine for structural defects and distinguish those defects from engineering mapping failures.

### 6.2 Numeric fidelity

For EXTRACTED numeric and integer proposals, verify that the proposed number represents the same source quantity.

Use exact decimal comparison and a bounded, deterministic literal-extraction policy.

Examples:

| Raw | Proposed | Expected result |
|---|---|---|
| `3 Pole` | `3` | Eligible for mapping if source and attribute checks pass |
| `1600 A` | `"1600"` | Eligible for mapping if unit checks pass |
| `15.75 A` | `"16"` | Reject proposal as source-inconsistent |
| `2.5` | `2` | Reject; no truncation |
| `1.2 kA` | `"1200"` with unit A | Reject as an AI-side conversion |
| `400/600 A` | `"600"` | Do not select a scalar |
| `3 × 500 A` | `"1500"` | Reject as a calculated value |

The deterministic parser must never simply select the first number from an arbitrary source string.

Support a bounded set of unambiguous literal forms. If a value cannot be validated reliably using those rules, retain it as unmapped.

Do not introduce a broad grammar that guesses engineering semantics.

Maintain separate unit validation. A proposal must be faithful both to the source numeric literal and to the source unit and its scale.

### 6.3 ENUM, BOOLEAN, and TEXT fidelity

For ENUM, enforce exact registry membership and retain source evidence. Keep semantic equivalence conservative: an enum's membership does not prove its association or meaning.

For BOOLEAN, accept explicit, unambiguous source expressions under a bounded policy. Ambiguous state descriptions should remain unmapped rather than guessed.

For TEXT, permit minimal, justified cleanup. Preserve meaningful punctuation, whitespace within identifiers, leading zeros, capitalization, and model/catalog identifiers when material.

Do not let generic string cleanup alter engineering identifiers.

### 6.4 Failure behavior

Maintain the distinction between:

- **Schema quarantine:** Invalid wire structure, unsupported primitive, unexpected fields, or other assertion-contract violations.
- **UNMAPPED:** Structurally valid assertion with no usable proposal, ambiguous value, unresolved units, unsupported value form, or unverified value fidelity.
- **INVALID:** An explicit proposal that violates applicable registry constraints or other existing invalid-value rules.
- **MAPPED:** A proposal that passes the applicable validation and normalization requirements.

Introduce focused reason codes for missing or source-inconsistent proposals where current reason codes are insufficient. Preserve existing reason-code behavior where it still applies.

A null proposal must not cause the entire response to fail.

For v6, do not silently bypass an absent or invalid proposal by parsing `raw_value` through the old extracted-attribute fallback.

### 6.5 Canonical normalization

Once validation succeeds, pass the approved typed value and verified source unit into the existing engineering-model normalization boundary.

Do not modify the normalizer's authoring semantics.

Any allowed unit conversion is performed by PowerForge, not OpenAI.

Ensure the normalization process remains decimal-safe, preserves exact numerical meaning, and does not introduce rounding or integer truncation.

Keep normalized candidate fields separate from raw and proposed fields.

---

## 7. Persistence and migration

Introduce a new additive Alembic revision after:

`6r_0014e_response_audit`

Suggested revision:

`6r_0014f_typed_value_proposals`

Do not edit prior migrations to implement this change.

### 7.1 Typed proposal storage

The existing `extraction_candidates.proposed_value` is text.

Prefer converting this column to JSONB so it can preserve the actual primitive proposal type:

- Exact-decimal string for NUMBER
- JSON integer for INTEGER
- JSON string for TEXT and ENUM
- JSON boolean for BOOLEAN
- SQL NULL for an unavailable proposal

Preserve existing historical text proposals as JSON strings through a controlled migration.

Inspect all current constraints, triggers, consumers, and ORM mappings before finalizing the conversion. If a materially safer persistence strategy is identified, document the alternative before implementing it.

Do not introduce multiple redundant columns for each proposal type.

### 7.2 Retire `proposed_enum_value`

Remove `proposed_enum_value` from the v6 provider contract, active domain model, and normal API presentation.

Historical v5 records must retain their original proposed enum information and remain inspectable.

If the existing database column must remain to preserve historical data, keep it as a historical-only column rather than using it for new v6 publication.

Do not delete historical values or rewrite immutable assertion payloads.

### 7.3 Database immutability

Update the candidate shape constraints and immutable publication guards to support typed v6 proposals.

For v6 assertions, the persisted proposal must match the corresponding immutable Stage 2 assertion exactly, including JSON primitive type.

A JSON boolean must not be interchangeable with a string containing `true`. Likewise, an integer must not be interchangeable with a decimal-looking string.

Ensure null proposal semantics are consistent between the application model and database.

Maintain the historical guard behavior for existing response versions.

Preserve exact recognition-result ownership, candidate ordinals, raw source fields, evidence, and existing mapping integrity constraints.

### 7.4 Search projection

The existing candidate search-term builder calls string methods on proposed values.

Update it to safely generate searchable representations of supported primitive values without modifying stored proposal types.

Preserve search limits and deterministic query behavior.

---

## 8. Response audit and execution integrity

Extend the existing audit-required publication guard to cover the new Stage 2 response version.

For v6, all existing requirements must remain intact:

- Exact original response-byte retention.
- SHA-256 and size verification.
- Immutable audit metadata.
- Received, accepted, and quarantined counts.
- Assertion-level quarantine with original positions.
- Atomic publication and audit linkage.
- Existing worker lease and execution fencing.
- Retrieval journaling and retention enforcement.

Do not create another audit system.

The new typed field must be retained exactly as returned in the original response, while the validated response and published candidate preserve the correct JSON primitive representation.

Test rollback, cancellation, failed audit storage, and invalid proposals without weakening atomicity.

---

## 9. API and Documents frontend

Update the attribute candidate read contract to expose:

- `raw_value`
- `raw_unit`
- `proposed_value`
- `proposed_unit`
- `normalized`
- `origin`
- Mapping and diagnostic states
- Existing evidence and ownership information

Expose `proposed_value` using a JSON representation that preserves its logical type, with exact-decimal NUMBER values transmitted as strings.

Remove `proposed_enum_value` from the current candidate presentation, while retaining historical read support as necessary.

### 9.1 Attribute cards

For mapped assertions, display the normalized value as the primary result.

For unmapped assertions, display the proposal when available; otherwise display the raw value.

In expanded details, distinguish clearly:

**Raw value:** Original source transcription  
**Proposed value:** AI interpretation in the target registry type  
**Normalized value:** PowerForge-validated canonical representation

Preserve the current distinction between identification, registry attributes, raw-unmapped facts, and inferred attributes.

Do not automatically label a proposal as verified merely because it is displayed.

### 9.2 Historical read compatibility

Older records should continue to render without converting their original raw values or changing their original interpretation.

Where a historical enum proposal exists, show it appropriately. Do not manufacture a v6 proposal for old records by replaying a new normalizer.

Avoid introducing unnecessary UI controls or changing unrelated Documents functionality.

---

## 10. Extraction Debugger

Update the standalone Extraction Debugger to understand both historical v5 responses and new v6 responses.

For v6, it must show:

1. The exact original `raw_value`.
2. The typed `proposed_value`, including null and JSON primitive type.
3. The accepted validated assertion.
4. The published normalized value, if mapped.
5. The relevant validation or mapping failure reason.
6. Original zero-based assertion position and evidence information.

Preserve original-response export and SHA-256 verified retrieval.

The assertion comparison must not coerce boolean, integer, and string values into one indistinguishable representation.

Keep historical `proposed_enum_value` visible when inspecting old raw responses.

Reuse existing diagnostic information and avoid introducing another persistence system.

---

## 11. Testing requirements

Implement tests alongside each milestone, then execute the combined suites.

### 11.1 Contract tests

Verify correct acceptance of all five primitive types and nullable extracted proposals.

Test wrong JSON types, JSON floats, oversized values, malformed numeric strings, incorrect enums, missing required fields, unexpected old `proposed_enum_value`, and mixed valid/invalid assertions.

Ensure one invalid assertion cannot invalidate unrelated valid assertions.

### 11.2 Numeric fidelity tests

Use exact-decimal fixtures covering:

- Integer and fractional literals.
- Numeric literals with source units.
- Leading and trailing zeros.
- Positive and negative values.
- Scientific notation where the existing parser supports it.
- Very large and high-precision numbers.
- Explicit source quantities versus changed magnitudes.
- Invalid integer conversion.
- Ranges, multiple values, and qualifiers.
- Ambiguous separators and compound expressions.
- Explicit unit prefixes and scale differences.
- Numeric values embedded in model identifiers.

Verify no rounding, truncation, arithmetic, or unauthorized rescaling.

### 11.3 Registry tests

Test every registry type against representative real registry attributes.

Include invalid enum members, boolean ambiguity, model/catalog identifier fidelity, unsupported units, and attributes with no safe proposal.

### 11.4 Publication and migration tests

On a disposable PostgreSQL 16 database:

- Run the complete migration chain.
- Test migration of representative historical inferred values.
- Verify correct v6 typed proposal persistence.
- Test raw/proposal/normalized immutability.
- Reject mismatched JSON primitive types in immutable guards.
- Reject publication without the required response audit.
- Verify historical read behavior.
- Verify candidate searching across all five proposal types.
- Verify no existing published records are silently modified.

### 11.5 Frontend and debugger tests

Verify formatting and detail display for null, integer, boolean, decimal-string, enum, and text proposals.

Test mapped, unmapped, invalid, quarantined, and inferred states.

Test comparison of original/validated/published representations, including historical records.

Ensure the debugger remains read-only except for its retrieval journal.

### 11.6 Extraction evaluations

Update synthetic fixtures and the evaluation harness to support the new response schema.

Include cases based on the prior Siemens development observations:

- Directly printed breaker models.
- Pole counts embedded in model descriptions.
- Trip-unit model versus trip-unit technology.
- Explicit ratings versus ambiguous current values.
- Bus bracing versus short-circuit withstand.
- Actual source-unit spelling versus canonical units.
- Inferred enum proposals and abstentions.

Keep offline contract correctness separate from live AI extraction quality.

A successful fixture does not prove the live model consistently returns correct proposals.

---

## 12. Implementation milestones

### Milestone A — Contract and prompt

Implement the v6 assertion contract, typed-value rules, version pins, and new prompt.

Update fake-provider fixtures and schema tests.

**Exit criteria:** All five types are representable; nullable extracted proposals work; old enum-only field is absent from v6; OpenAI Structured Outputs schema is syntactically valid.

### Milestone B — Deterministic validation and publication

Implement strict type validation, source-fidelity checks, null handling, unit checks, normalization integration, and failure classifications.

Retain existing evidence and association semantics.

**Exit criteria:** Supported values map correctly; unsupported proposals remain reviewable; wrong magnitudes and unauthorized calculations cannot become mapped values.

### Milestone C — Database and API

Apply the additive migration, typed proposal persistence, integrity guards, search projection, historical compatibility, and read API changes.

**Exit criteria:** Migration tests, historical reads, immutable guards, and atomic audit publication pass.

### Milestone D — Documents UI and Debugger

Update presentation and comparison logic without changing unrelated layouts or workflows.

**Exit criteria:** All value types and failure states display correctly, and historical results remain inspectable.

### Milestone E — End-to-end verification

Run the relevant Python, PostgreSQL integration, TypeScript, frontend, debugger, lint, and build checks.

Replay pinned synthetic extraction fixtures and compare expected mapping outcomes.

Review final resource identities and confirm that no legacy active-write path bypasses the new contract.

**Exit criteria:** All regression tests pass; failures and skipped tests are documented; live AI improvements are not claimed without a controlled evaluation.

---

## 13. Non-goals

Do not:

- Redesign the equipment recognition stage.
- Change the canonical registry definitions merely to accommodate the AI output.
- Implement canonical equipment association or Phase 7 identity resolution.
- Implement automatic canonical engineering-model writes.
- Add a third AI extraction or repair call.
- Automatically repair unsupported or ambiguous engineering data.
- Introduce a general-purpose semantic reinterpretation engine.
- Replace the evidence localization or response-audit architecture.
- Redesign the entire Documents frontend.
- Rewrite historical stage results.
- Add parallel v5/v6 execution paths for new runs.
- Run unauthorized live OpenAI extraction calls.

Historical read compatibility is required; legacy extraction execution compatibility is not.

---

## 14. Final acceptance criteria

Implementation is complete only when:

1. New Stage 2 EXTRACTED and INFERRED registry assertions use the same `proposed_value` field.
2. The field supports NUMBER, INTEGER, TEXT, BOOLEAN, and ENUM correctly.
3. Extracted proposals can be null without losing the source assertion.
4. `proposed_enum_value` is no longer used by new extraction responses.
5. The original transcription is preserved.
6. OpenAI is explicitly prohibited from unit conversion, arithmetic, rounding, and truncation.
7. PowerForge validates numeric fidelity and source-unit equivalence before normalization.
8. Unsupported or ambiguous proposals cannot silently become mapped values.
9. Original response auditing and assertion-level quarantine continue to function.
10. The migration preserves historical data and immutable publication.
11. APIs and frontend show raw, proposed, and normalized values distinctly.
12. The debugger correctly displays typed proposals and historical responses.
13. Version identities, tests, and documentation accurately reflect the new contract.
14. No additional AI stages or unintended engineering-model writes are introduced.

## 15. Codex delivery instructions

Before editing, inspect the current `main` branch and identify any changes since the stated baseline.

Produce a short implementation inventory showing affected modules, migration and version dependencies, and relevant tests.

Implement in the milestone order above. Use existing PowerForge abstractions wherever possible and avoid unrelated refactors.

Resolve low-level implementation decisions independently when they follow the stated invariants. Do not silently relax numeric fidelity, source evidence, audit integrity, or database immutability to simplify implementation.

After implementation, provide:

- A summary of changes by milestone.
- New and unchanged version identities.
- Migration details and historical compatibility behavior.
- Test commands and actual results.
- Any remaining edge cases or known limitations.
- A precise statement of what has and has not been verified using live OpenAI responses.

Do not perform unapproved database resets, deployment changes, or paid live provider calls.

**Deliver a complete, tested contract change that fits the existing Phase 6R architecture.**
