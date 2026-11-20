# PowerForge — Phase 6R Unified Typed Value Proposal Contract

## Codex Implementation Plan

**Repository:** `adilzafar66/PowerForge`  
**Baseline:** `main`, commit `e60fe171` (refresh before implementation)  
**Recommended branch:** `codex/phase-6r-unified-value-proposals`  
**Scope:** Stage 2 attribute extraction, deterministic validation, publication, persistence, read APIs, Documents UI, Extraction Debugger, and tests.

---

## 1. Objective

Replace the extracted-attribute-specific `proposed_enum_value` mechanism with a universal `proposed_value` that supports all five registry attribute types:

- NUMBER
- INTEGER
- TEXT
- BOOLEAN
- ENUM

The AI must propose a cleaned, source-faithful representation of the reported value, preferably compatible with the target registry attribute's value type. It must not perform numerical calculations, unit conversions, rounding, truncation, or unjustified semantic transformations.

Retain the original `raw_value` independently.

If an extracted value cannot be safely represented as the registry type without losing meaningful information, the AI may preserve a source-faithful unresolved expression or return `proposed_value: null`.

Support source expressions containing multiple explicitly reported representations of the same physical quantity, without allowing the AI to calculate or invent alternate representations.

PowerForge remains the authoritative validator and performs any permitted canonical unit conversions.

The implementation must not introduce another extraction stage, another AI call, a new engineering interpretation engine, or any automatic canonical-model writes.

## 2. Current Implementation and Deficiencies

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

The existing publication rules also treat non-`SINGLE` value forms as unrepresentable. Consequently, explicitly equivalent source representations such as `20”(508mm)W` cannot currently be normalized together.

This change should unify the contract and downstream handling, not simply rename one field.

## 3. Architectural Invariants

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
14. Equivalent source representations must be independently verified by PowerForge rather than accepted on the AI's authority.

**Important:** A valid registry type does not by itself establish that a proposal faithfully represents the source.

---

## 4. New Stage 2 Response Contract

### 4.1 Version

Introduce:

- Stage 2 response: `phase-6r-attributes-v6`
- Aggregate wire identity: `phase-6r-wire-v6`
- Prompt bundle: `phase-6r-stages-v9`
- Attribute prompt file: `attribute_extraction_v8.txt`
- Publication version: `phase-6r-publication-v9` (supersedes the Milestone B `v8` pin after enum and text source-fidelity review)

Keep the Stage 1 recognition contract unchanged.

Do not change unrelated registry, layout, unit-interpretation, or compact-page input versions unless their underlying implementation actually changes.

Pin all changed resources through the existing extraction profile manifest and hashes. Previously pinned incompatible work must fail admission explicitly, not silently resume under the new contract.

### 4.2 EXTRACTED Assertions

Replace `proposed_enum_value` with a unified, required-but-nullable `proposed_value` field for all registry-linked EXTRACTED assertions.

The field represents the AI's cleaned, source-faithful interpretation of `raw_value`. Where possible, it should conform to the target registry attribute's value type. Otherwise, it may preserve an unresolved source expression.

**Supported representations:**

| Registry type | Compatible proposal | Unresolved proposal |
|---|---|---|
| NUMBER | Exact decimal string | Expression string or null |
| INTEGER | JSON integer | Expression string or null |
| TEXT | JSON string | Original text or null |
| BOOLEAN | JSON boolean | Expression string or null |
| ENUM | Exact permitted enum string | Expression string or null |

JSON floating-point values are prohibited. Structural acceptance does not establish registry compatibility.

Extend `value_form` with `EQUIVALENT_UNITS` and add `alternate_representations`, a bounded collection of objects containing:

- `value`: Exact decimal string.
- `unit`: Nonblank source unit.

For `EQUIVALENT_UNITS`, `proposed_value` identifies the primary reported quantity, while `alternate_representations` preserves additional explicitly reported representations of that same quantity. Other value forms must have an empty collection.

Preserve all existing raw-source, qualifier, association, ownership, evidence, and unit fields. The original `raw_value` must never be replaced by its proposal.

Keep `raw_unmapped` assertions raw-only, without fabricated registry proposals.

Detailed fidelity, compound-expression, and equivalence requirements are defined in Section 6.2.

### 4.3 INFERRED Assertions

INFERRED assertions use the same `proposed_value` field but require a **non-null, registry-compatible primitive**.

The expected representations are:

- NUMBER: Exact decimal string.
- INTEGER: JSON integer.
- TEXT: JSON string.
- BOOLEAN: JSON boolean.
- ENUM: Exact permitted enum string.

Unresolved compound expressions are not permitted for INFERRED assertions. If one justified, registry-compatible value cannot be established, omit the inference.

Preserve the existing `inference_explanation`, `inference_basis`, `source_expression`, `proposed_unit`, ownership, association, and contextual evidence requirements.

INFERRED assertions do not contain a transcribed `raw_value` and must not use `EQUIVALENT_UNITS` or `alternate_representations`.

The distinction between EXTRACTED and INFERRED remains unchanged. Existing restrictions against speculative engineering values and unsupported inferences continue to apply.

### 4.4 Example Response Fragments

The following examples illustrate the new contract. They omit unrelated required assertion fields. Use actual registry keys and permitted enum members in implementation.

**Integer:**

```json
{
  "attribute_key": "pole_count",
  "raw_value": "3 Pole",
  "proposed_value": 3,
  "proposed_unit": null,
  "value_form": "SINGLE",
  "alternate_representations": []
}
```

**Enum:**

```json
{
  "attribute_key": "trip_unit_type",
  "raw_value": "Electronic",
  "proposed_value": "ELECTRONIC",
  "proposed_unit": null,
  "value_form": "SINGLE",
  "alternate_representations": []
}
```

**Number with an explicit unit:**

```json
{
  "attribute_key": "rated_current",
  "raw_value": "1600 A",
  "raw_unit": "A",
  "proposed_value": "1600",
  "proposed_unit": "A",
  "value_form": "SINGLE",
  "alternate_representations": []
}
```

**Compound value:**

```json
{
  "attribute_key": "rated_voltage",
  "raw_value": "400/600 V",
  "raw_unit": "V",
  "proposed_value": "400/600",
  "proposed_unit": "V",
  "value_form": "MULTIPLE",
  "alternate_representations": []
}
```

**Equivalent unit representations:**

```json
{
  "attribute_key": "width",
  "raw_value": "20”(508mm)W",
  "raw_unit": "in",
  "proposed_value": "20",
  "proposed_unit": "in",
  "value_form": "EQUIVALENT_UNITS",
  "alternate_representations": [
    {
      "value": "508",
      "unit": "mm"
    }
  ]
}
```

---

## 5. AI Prompt Requirements

Update the Stage 2 prompt to explain the distinction between source transcription, source-faithful proposals, registry compatibility, and canonical normalization.

### 5.1 Permitted Operations

The AI may:

- Identify a numeric literal within an unambiguous value expression.
- Remove clearly extraneous surrounding labels or formatting without altering the reported value.
- Match a source expression to an explicitly permitted enum.
- Interpret unequivocal affirmative/negative wording as a boolean.
- Propose the exact applicable supported source unit, using the existing unit policy.
- Preserve the original value unchanged when it already matches the registry's required type.
- Preserve a cleaned compound or unresolved expression without reducing it to a scalar.
- Recognize and transcribe multiple explicitly reported representations of the same quantity.
- Abstain by returning null when no reliable proposal is possible.

### 5.2 Prohibited Operations

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
- Generate alternate unit representations that are not explicitly present in the source.
- Treat a valid data type as proof of correct engineering interpretation.

### 5.3 Ambiguity Policy

When an extracted value cannot safely be interpreted as the registry type, the AI may preserve the source-faithful unresolved expression or return `proposed_value: null`.

Do not populate NUMBER, INTEGER, BOOLEAN, or ENUM proposals with invented or unsupported text merely to avoid null. Unresolved strings must faithfully represent the original source expression.

TEXT proposals may retain their original raw string when the text is valid for the intended attribute.

If the source value itself is meaningful but its registry attribute is not established, preserve it through the existing `raw_unmapped` mechanism rather than inventing a registry mapping.

Keep EXTRACTED and INFERRED distinct. Converting explicit `Yes` to `true` is a typed interpretation of a source value, not an inference.

Update the existing prompt instruction permitting derived scalars from compound expressions so that it does not authorize AI-side arithmetic or conversions.

---

## 6. Deterministic Proposal Validation

Implement a focused proposal-validation boundary in the extraction package, integrated with the existing publication flow.

Avoid implementing a second general-purpose engineering semantic interpreter.

### 6.1 Structural and Registry-Type Validation

PowerForge must distinguish **structural admission**, **registry compatibility**, and **source-fidelity validation**.

This section governs the first two. Source-fidelity and numerical-equivalence validation are specified in Section 6.2.

#### 6.1.1 Structural Admission

Validate responses through the existing Stage 2 Pydantic contract and assertion-level quarantine mechanism.

For EXTRACTED registry assertions:

- `proposed_value` is required but nullable.
- Permitted JSON primitives are string, integer, boolean, and null.
- JSON floating-point values, arrays, and objects are prohibited.
- `proposed_enum_value` is not accepted.
- `alternate_representations` must be a bounded collection of exact-decimal-string values and nonblank units.
- `EQUIVALENT_UNITS` requires at least one alternate representation. Other value forms require an empty collection.

For INFERRED assertions:

- `proposed_value` is required and non-null.
- Only string, integer, and boolean primitives are permitted.
- `EQUIVALENT_UNITS` and alternate representations are not permitted.

Preserve existing field constraints, capacity limits, local-reference uniqueness, evidence structures, and response-level fatal invariants.

Do not perform implicit JSON type coercion.

#### 6.1.2 Registry Compatibility

After structural admission, use the applicable registry attribute definition to validate the proposal:

| Registry type | Compatibility requirement |
|---|---|
| NUMBER | Valid finite exact-decimal string |
| INTEGER | JSON integer, excluding boolean |
| TEXT | JSON string satisfying applicable constraints |
| BOOLEAN | JSON boolean |
| ENUM | Exact member of the attribute's `allowed_values` |

Apply existing numerical magnitude, precision, integer-range, and persistence limits.

An EXTRACTED assertion may be structurally valid without being registry-compatible. Preserve such proposals and classify them according to Section 6.1.3 rather than quarantining them solely for incompatibility.

INFERRED assertions must not be published as mapped values unless their proposals satisfy the applicable registry type and all other validation requirements.

#### 6.1.3 Validation Outcomes

Maintain these distinctions:

- **MAPPED:** The proposal passes registry compatibility, source fidelity where applicable, unit validation, ownership requirements, and canonical normalization.
- **UNMAPPED:** The assertion is structurally valid but lacks a usable proposal, contains an unresolved compound expression, has insufficient verification, or cannot safely be represented by the registry type.
- **INVALID:** The proposal demonstrably contradicts its source or violates a confirmed registry constraint.
- **QUARANTINED:** The assertion violates the response schema or admission contract.

Preserve existing reason codes where applicable and add focused codes only where necessary.

One malformed assertion must not invalidate unrelated valid assertions, except under existing response-level fatal invariants.

Do not silently fall back to parsing `raw_value` when a v6 proposal is missing or invalid.

#### 6.1.4 Implementation Boundaries

Reuse the existing validation, registry, unit-normalization, publication, and audit infrastructure.

Keep schema admission, registry compatibility, source-fidelity verification, and canonical normalization logically separate.

Apply the detailed source-expression and equivalence rules in Section 6.2 without duplicating those rules here.

### 6.2 Numeric Fidelity and Source Expression Validation

PowerForge must validate AI-proposed numeric values against their original source expressions without requiring the entire `raw_value` to be a numeric literal.

The purpose of this validation is to ensure that the AI's proposal faithfully represents the reported source value, without introducing numerical transformations, omitting meaningful information, or incorrectly reducing compound expressions to a single scalar.

#### 6.2.1 General Principles

1. The AI is responsible for interpreting the structure of the source expression, identifying the intended registry attribute, separating numerical values from units and descriptive text, and proposing a cleaned value.
2. The AI must not perform arithmetic, unit conversions, rounding, truncation, interpolation, or estimation.
3. PowerForge must independently verify numerical fidelity using exact-decimal parsing and deterministic validation.
4. Source fidelity and registry compatibility must be evaluated separately. A proposal may accurately represent its source without being compatible with the registry attribute's value type.
5. The original `raw_value` must always be preserved, regardless of whether the proposal is successfully mapped.
6. A successful numerical fidelity check does not independently establish correct registry attribute selection, equipment ownership, or engineering interpretation.

#### 6.2.2 Single Numeric Values with Descriptive Expressions

A source expression may contain a single numerical value alongside units, labels, or descriptive terminology.

For example:

| Raw value | Proposed value | Proposed unit |
|---|---|---|
| `12 Sym. kA` | `"12"` | `kA` |
| `1600 A RMS` | `"1600"` | `A` |
| `3 Pole` | `3` | null |
| `Isc = 25 kA` | `"25"` | `kA` |
| `15.75 A` | `"15.75"` | `A` |

PowerForge should permit these proposals when the numerical literal is independently verifiable and the surrounding expression does not introduce ambiguity.

Meaningful descriptors such as `Sym.`, `RMS`, and other engineering classifications must remain preserved in the original source expression and associated evidence. They must not be silently discarded when they affect the interpretation or applicability of the registry attribute.

A numerical proposal can be mapped only if it also passes registry compatibility, unit validation, and any applicable semantic-consistency checks.

#### 6.2.3 Compound Expressions and Multiple Values

When a source expression contains multiple values, the AI may propose a cleaned expression that preserves all reported values without performing calculations or arbitrarily selecting one.

Example:

```json
{
  "raw_value": "400/600 V",
  "proposed_value": "400/600",
  "proposed_unit": "V",
  "value_form": "MULTIPLE"
}
```

The proposed expression is source-faithful, but `"400/600"` is not compatible with a scalar NUMBER registry attribute.

PowerForge must therefore preserve the proposal and classify the assertion as `UNMAPPED`, rather than rejecting the entire assertion or selecting one value.

The same principle applies to expressions involving ranges, multiple ratings, or calculations.

| Raw value | Permitted proposal | Scalar NUMBER mapping |
|---|---|---|
| `400/600 V` | `"400/600"` | UNMAPPED |
| `12–15 kA` | `"12–15"` | UNMAPPED |
| `3 × 500 A` | `"3 × 500"` | UNMAPPED |
| `400 A / 600 A` | `"400/600"` | UNMAPPED |

The AI must not evaluate `3 × 500` as 1500 or select one member of `400/600` without independently justified component-level interpretation.

If the document explicitly identifies separate meanings for individual components, those components may be mapped to distinct registry attributes only when the extraction contract provides sufficient source-component evidence to validate that association.

A new component-level selection mechanism is outside the scope of this contract change. Otherwise, preserve the complete expression.

A string proposal that is incompatible with a NUMBER or INTEGER registry type must not be quarantined solely because it is a compound expression. It is a valid source-faithful proposal but an unmappable scalar value.

#### 6.2.4 Multiple Equivalent Representations of the Same Quantity

Some source expressions report one physical quantity using multiple units.

For example:

`20”(508mm)W`

This expresses a dimension of 20 inches with an explicitly reported equivalent representation of 508 millimetres. The suffix `W` identifies width when supported by the drawing context.

Such expressions must be distinguished from `MULTIPLE` expressions representing independent quantities.

Use the `EQUIVALENT_UNITS` value form and `alternate_representations` structure defined in Section 4.2.

For `EQUIVALENT_UNITS`:

1. The AI identifies and transcribes each explicitly reported representation.
2. The AI must not generate alternate representations by performing its own unit conversions.
3. Every proposed representation must correspond to a complete numerical literal and unit explicitly present in the source evidence.
4. PowerForge validates each representation independently.
5. PowerForge performs deterministic unit conversions to evaluate equivalence.
6. The primary representation and alternate representations must be preserved, including their original units.
7. If the representations are equivalent, PowerForge may normalize the quantity into the registry's canonical unit.
8. If the representations conflict, the assertion must remain `UNMAPPED` with an appropriate diagnostic, such as `INCONSISTENT_REPRESENTATIONS`.
9. If equivalence cannot be established reliably, retain the complete assertion without mapping.

For example:

- `20”(508mm)W` — equivalent representations; potentially MAPPED.
- `20”(500mm)W` — inconsistent representations; UNMAPPED.

Exact unit equivalence should be accepted where supported. Approximate or rounded equivalence must follow an explicit, deterministic tolerance policy established by PowerForge. Do not introduce a general numerical tolerance or allow the AI to decide whether discrepancies are acceptable.

The dimension indicator `W` must be interpreted as source context supporting the `width` attribute, not as a unit or part of the numerical proposal.

#### 6.2.5 Numeric Fidelity Checks

For every extracted numeric proposal, PowerForge must:

1. Identify complete numerical literals within the original source expression using bounded deterministic parsing.
2. Verify that the proposed numerical values match explicitly reported source literals without changing their magnitude.
3. Verify that the proposed units preserve the source units and their scale.
4. Detect unsupported arithmetic, rounding, truncation, or unit conversion.
5. Preserve relevant descriptors, qualifiers, conditions, and alternate representations.
6. Reject arbitrary scalar selection from compound expressions.
7. Validate the proposal against the target registry value type.
8. Perform canonical unit normalization only after the preceding checks pass.

Examples of invalid proposals:

| Raw value | Invalid proposal | Reason |
|---|---|---|
| `12.75 kA` | `"13"` | Rounding |
| `2.5` | `2` | Truncation |
| `1.2 kA` | `"1200"` with unit `A` | AI-side unit conversion |
| `3 × 500 A` | `"1500"` | Arithmetic |
| `400/600 V` | `"600"` | Unsupported scalar selection |
| `20”(508mm)W` | `"508"` with unit `in` | Incorrect numerical/unit association |

The numeric parser must not select the first available number automatically or use general-purpose heuristics that discard meaningful engineering context.

#### 6.2.6 Validation Outcomes

Validation outcomes and their classifications are defined in Section 6.1.3.

Numeric fidelity and equivalence checks must produce diagnostics consistent with those classifications.

#### 6.2.7 Implementation Boundaries

The implementation must remain conservative.

Do not build a general-purpose engineering-expression interpreter or an extensive library of speculative parsing heuristics.

Use the AI for semantic recognition and source-expression interpretation, while PowerForge remains responsible for deterministic verification, registry validation, unit equivalence, and normalization.

Extend the Stage 2 contract to support `EQUIVALENT_UNITS` and `alternate_representations`. Ensure these fields are included in validation, persistence, immutable publication checks, API responses, debugger inspection, and regression tests.

The general `proposed_value` field must support source-faithful compound expressions even when they cannot be represented by the registry's scalar type.

Do not permit a source-faithful but registry-incompatible expression to become a normalized engineering value.

**Acceptance requirement:** Every mapped numeric value must be traceable to an explicitly reported source quantity, with no unverified numerical transformation performed by the AI.

### 6.3 ENUM, BOOLEAN, and TEXT Fidelity

For ENUM, enforce exact registry membership and retain source evidence. Verify an
extracted proposal against the complete raw value, ignoring surrounding whitespace and
case. For two-winding transformer primary and secondary connections, the complete source
spelling `Star` can verify an AI proposal of `WYE`. A recognized source value that
contradicts the proposal is INVALID. Other source spellings stay UNMAPPED when the
proposal cannot be verified. These checks never generate a proposal and leave inferred
enums, equipment association, and citation support under their existing policies.

For BOOLEAN, accept explicit, unambiguous source expressions under a bounded policy. Ambiguous state descriptions should remain unmapped rather than guessed.

For TEXT, allow surrounding whitespace and removal of a leading registry display name
followed by a colon, such as `Model: CMD6`. The entire remaining single-line value must
match exactly. Preserve meaningful punctuation, internal whitespace, leading zeros, and
capitalization. A demonstrably altered standalone identifier is INVALID. Other cleanup
that cannot be verified remains UNMAPPED for review.

### 6.4 Failure Behavior

Use the outcome classifications defined in Section 6.1.3.

Preserve the distinction between structurally malformed assertions, source-faithful but unmappable proposals, and demonstrably invalid proposed values.

An unavailable, ambiguous, or registry-incompatible EXTRACTED proposal must not cause the entire response to fail.

Preserve the original assertion, proposal, evidence, and diagnostic reason when mapping is unsuccessful.

### 6.5 Canonical Normalization

Once validation succeeds, pass the approved typed value and verified source unit into the existing engineering-model normalization boundary.

Do not modify the normalizer's engineering semantics.

Any allowed unit conversion is performed by PowerForge, not OpenAI.

For `EQUIVALENT_UNITS`, independently verify the alternate representations before normalizing the primary value.

Ensure the normalization process remains decimal-safe, preserves exact numerical meaning, and does not introduce rounding or integer truncation.

Extraction checks the shared engineering normalizer's result against the exact
canonical quantity. If the existing 34-digit Decimal conversion loses precision,
including for a repeating decimal, publication returns UNMAPPED with
`INEXACT_NORMALIZATION`. The source value, units, proposal, and evidence remain
available for review. For example, a temperature rise of `1 °F` is exactly
`5/9 °C` and stays unmapped, while a rise of `9 °F` maps to `5 °C`.
The shared engineering normalizer still returns its existing 34-digit result
to other callers.

Keep normalized candidate fields separate from raw and proposed fields.

---

## 7. Persistence and Migration

Introduce a new additive Alembic revision after:

`6r_0014e_response_audit`

Suggested revision:

`6r_0014f_typed_value_proposals`

Do not edit prior migrations to implement this change.

### 7.1 Typed Proposal Storage

The existing `extraction_candidates.proposed_value` is text.

Prefer converting this column to JSONB so it can preserve the actual primitive proposal type:

- Exact-decimal string for NUMBER.
- JSON integer for INTEGER.
- JSON string for TEXT and ENUM.
- JSON boolean for BOOLEAN.
- SQL NULL for an unavailable proposal.

Preserve existing historical text proposals as JSON strings through a controlled migration.
Revision `6r_0014f_typed_value_proposals` converts the candidate column in place.
It preserves SQL NULL and leaves immutable Stage 2 payloads, audit records, and
normalized candidate values as stored.

Inspect all current constraints, triggers, consumers, and ORM mappings before finalizing the conversion. If a materially safer persistence strategy is identified, document the alternative before implementing it.

Do not introduce multiple redundant columns for each proposal type.

Persist the bounded `alternate_representations` collection as structured JSONB, consistent with the existing candidate-publication architecture. Avoid a separate relational subsystem for this limited field.

### 7.2 Retire `proposed_enum_value`

Remove `proposed_enum_value` from the v6 provider contract, active domain model, and normal API presentation.

Historical v5 records must retain their original proposed enum information and remain inspectable.

If the existing database column must remain to preserve historical data, keep it as a historical-only column rather than using it for new v6 publication.

Do not delete historical values or rewrite immutable assertion payloads.

### 7.3 Database Immutability

Update the candidate shape constraints and immutable publication guards to support typed v6 proposals and `alternate_representations`.

For v6 assertions, the persisted proposal must match the corresponding immutable Stage 2 assertion exactly, including JSON primitive type.

A JSON boolean must not be interchangeable with a string containing `true`. Likewise, an integer must not be interchangeable with a decimal-looking string.

Ensure null proposal semantics are consistent between the application model and database.

For equivalent-unit expressions, preserve and validate the reported alternate representations against the immutable assertion.

Maintain the historical guard behavior for existing response versions.

Preserve exact recognition-result ownership, candidate ordinals, raw source fields, evidence, and existing mapping integrity constraints.

### 7.4 Search Projection

The existing candidate search-term builder calls string methods on proposed values.

Update it to safely generate searchable representations of supported primitive values without modifying stored proposal types.

Include alternate representations where useful and consistent with existing search bounds.
The search projection combines alternate values and units into one term so each
candidate stays within the existing seven-term limit.

Preserve search limits and deterministic query behavior.

---

## 8. Response Audit and Execution Integrity

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

The new typed field and alternate representations must be retained exactly as returned in the original response, while the validated response and published candidate preserve the correct JSON primitive representation.

Test rollback, cancellation, failed audit storage, and invalid proposals without weakening atomicity.

---

## 9. API and Documents Frontend

Update the attribute candidate read contract to expose:

- `raw_value`
- `raw_unit`
- `proposed_value`
- `proposed_unit`
- `alternate_representations`
- `value_form`
- `normalized`
- `origin`
- Mapping and diagnostic states.
- Existing evidence and ownership information.

Expose `proposed_value` using a JSON representation that preserves its logical type, with exact-decimal NUMBER values transmitted as strings.

Remove `proposed_enum_value` from the current candidate presentation, while retaining historical read support as necessary.

### 9.1 Attribute Cards

For mapped assertions, display the normalized value as the primary result.

For unmapped or invalid assertions, display the proposal when available; otherwise display the raw value.

In expanded details, distinguish clearly:

**Raw value:** Original source transcription.  
**Proposed value:** AI interpretation or cleaned expression.  
**Proposed unit:** AI's proposed source unit.  
**Alternate representations:** Additional explicitly reported representations of the same quantity.  
**Normalized value:** PowerForge-validated canonical representation.

Preserve the current distinction between identification, registry attributes, raw-unmapped facts, and inferred attributes.

Do not automatically label a proposal as verified merely because it is displayed.

### 9.2 Historical Read Compatibility

Older records should continue to render without converting their original raw values or changing their original interpretation.

Where a historical enum proposal exists, show it appropriately.
The candidate API exposes it through `proposed_value` using the original
Stage 2 assertion. The historical field remains in that assertion and in the
database for inspection.

Do not manufacture a v6 proposal for old records by replaying a new normalizer.

Avoid introducing unnecessary UI controls or changing unrelated Documents functionality.

---

## 10. Extraction Debugger

Update the standalone Extraction Debugger to understand both historical v5 responses and new v6 responses.

For v6, it must show:

1. The exact original `raw_value`.
2. The typed `proposed_value`, including null and JSON primitive type.
3. The proposed source unit.
4. The source value form.
5. The alternate reported representations, where applicable.
6. The accepted validated assertion.
7. The published normalized value, if mapped.
8. The relevant validation or mapping failure reason.
9. Original zero-based assertion position and evidence information.

Preserve original-response export and SHA-256 verified retrieval.

The assertion comparison must not coerce boolean, integer, and string values into one indistinguishable representation.

Keep historical `proposed_enum_value` visible when inspecting old raw responses.

Reuse existing diagnostic information and avoid introducing another persistence system.

---

## 11. Testing Requirements

Implement tests alongside each milestone, then execute the combined suites.

### 11.1 Contract Tests

Verify correct acceptance of all five primitive types and nullable extracted proposals.

Test wrong JSON types, JSON floats, oversized values, malformed numeric strings, incorrect enums, missing required fields, unexpected old `proposed_enum_value`, and mixed valid/invalid assertions.

Test `EQUIVALENT_UNITS`, bounded `alternate_representations`, and their required relationship to `value_form`.

Ensure one invalid assertion cannot invalidate unrelated valid assertions.

### 11.2 Numeric Fidelity Tests

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
- Descriptive expressions such as `12 Sym. kA`.
- Multiple ratings such as `400/600 V`.
- Equivalent representations such as `20”(508mm)W`.
- Conflicting representations such as `20”(500mm)W`.
- Compound expressions containing conditions such as `12 kA at 480 V`.

Verify no rounding, truncation, arithmetic, or unauthorized rescaling.

### 11.3 Registry Tests

Test every registry type against representative real registry attributes.

Include invalid enum members, boolean ambiguity, model/catalog identifier fidelity, unsupported units, and attributes with no safe proposal.

Include inferred enum, boolean, numeric, and text proposals with the appropriate provenance requirements.

### 11.4 Publication and Migration Tests

On a disposable PostgreSQL 16 database:

- Run the complete migration chain.
- Test migration of representative historical inferred values.
- Verify correct v6 typed proposal persistence.
- Verify alternate-representation storage and source fidelity.
- Test raw/proposal/normalized immutability.
- Reject mismatched JSON primitive types in immutable guards.
- Reject publication without the required response audit.
- Verify historical read behavior.
- Verify candidate searching across all five proposal types.
- Verify no existing published records are silently modified.

### 11.5 Frontend and Debugger Tests

Verify formatting and detail display for null, integer, boolean, decimal-string, enum, and text proposals.

Include compound expressions and equivalent-unit representations.

Test mapped, unmapped, invalid, quarantined, and inferred states.

Test comparison of original/validated/published representations, including historical records.

Ensure the debugger remains read-only except for its retrieval journal.

### 11.6 Extraction Evaluations

Update synthetic fixtures and the evaluation harness to support the new response schema.

Include cases based on the prior Siemens development observations:

- Directly printed breaker models.
- Pole counts embedded in model descriptions.
- Trip-unit model versus trip-unit technology.
- Explicit ratings versus ambiguous current values.
- Bus bracing versus short-circuit withstand.
- Actual source-unit spelling versus canonical units.
- Inferred enum proposals and abstentions.
- Compound voltage and current expressions.
- Equivalent dimensional representations.

Keep offline contract correctness separate from live AI extraction quality.

A successful fixture does not prove the live model consistently returns correct proposals.

---

## 12. Implementation Milestones

### Milestone A — Contract and Prompt

Implement the v6 assertion contract, typed-value rules, equivalent-unit representation fields, version pins, and new prompt.

Update fake-provider fixtures and schema tests.

**Exit criteria:** All five types are representable; nullable extracted proposals work; unresolved expressions are accepted; equivalent representations are supported; the old enum-only field is absent from v6; the OpenAI Structured Outputs schema is syntactically valid.

### Milestone B — Deterministic Validation and Publication

Implement strict type validation, source-fidelity checks, compound-expression handling, equivalent-unit verification, null handling, unit checks, normalization integration, and failure classifications.

Retain existing evidence and association semantics.

**Exit criteria:** Supported values map correctly; unsupported proposals remain reviewable; wrong magnitudes, conflicting representations, and unauthorized calculations cannot become mapped engineering values.

### Milestone C — Database and API

Apply the additive migration, typed proposal persistence, alternate-representation storage, integrity guards, search projection, historical compatibility, and read API changes.

**Exit criteria:** Migration tests, historical reads, immutable guards, and atomic audit publication pass.

### Milestone D — Documents UI and Debugger

Update presentation and comparison logic without changing unrelated layouts or workflows.

Include alternate-representation presentation and historical response inspection.

**Exit criteria:** All value types and failure states display correctly, and historical results remain inspectable.

### Milestone E — End-to-End Verification

Run the relevant Python, PostgreSQL integration, TypeScript, frontend, debugger, lint, and build checks.

Replay pinned synthetic extraction fixtures and compare expected mapping outcomes.

Review final resource identities and confirm that no legacy active-write path bypasses the new contract.

**Exit criteria:** All regression tests pass; failures and skipped tests are documented; live AI improvements are not claimed without a controlled evaluation.

---

## 13. Non-Goals

Do not:

- Redesign the equipment recognition stage.
- Change the canonical registry definitions merely to accommodate the AI output.
- Implement canonical equipment association or Phase 7 identity resolution.
- Implement automatic canonical engineering-model writes.
- Add a third AI extraction or repair call.
- Automatically repair unsupported or ambiguous engineering data.
- Introduce a general-purpose semantic reinterpretation engine.
- Implement a new general-purpose compound-expression component-selection workflow.
- Replace the evidence localization or response-audit architecture.
- Redesign the entire Documents frontend.
- Rewrite historical stage results.
- Add parallel v5/v6 execution paths for new runs.
- Run unauthorized live OpenAI extraction calls.

Historical read compatibility is required; legacy extraction execution compatibility is not.

---

## 14. Final Acceptance Criteria

Implementation is complete only when:

1. New Stage 2 EXTRACTED and INFERRED registry assertions use the same `proposed_value` field.
2. The field supports NUMBER, INTEGER, TEXT, BOOLEAN, and ENUM correctly.
3. Extracted proposals can be null or contain a source-faithful unresolved expression without losing the source assertion.
4. `proposed_enum_value` is no longer used by new extraction responses.
5. The original transcription is preserved.
6. OpenAI is explicitly prohibited from unit conversion, rounding, truncation, and arithmetic.
7. PowerForge independently validates source fidelity before allowing the proposal into the normalized engineering value.
8. Compound expressions remain reviewable without arbitrary scalar selection.
9. Explicitly equivalent source-unit representations can be validated deterministically and normalized where appropriate.
10. Conflicting or unverified representations cannot silently become mapped values.
11. Original response auditing and assertion-level quarantine continue to function.
12. The migration preserves historical data and immutable publication.
13. APIs and frontend show raw, proposed, alternate, and normalized representations distinctly.
14. The debugger correctly displays typed proposals and historical responses.
15. Version identities, tests, and documentation accurately reflect the new contract.
16. No additional AI stages or unintended engineering-model writes are introduced.

---

## 15. Codex Delivery Instructions

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
