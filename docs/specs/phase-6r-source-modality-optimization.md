# Milestone C2 — AI-Facing Source Simplification and Input Modality Optimization

## 1. Context

Continue development on the `codex/phase-6r-extraction-performance` branch.

Read `docs/specs/phase-6r-attribute-extraction-performance.md`, review the existing implementation of Milestones A, B, and C, and inspect their evaluation results before making changes.

Milestone B established that reducing reasoning effort introduces unacceptable extraction-quality and reliability regressions. Therefore, `medium` must remain the default Stage 2 reasoning effort.

Milestone C established that `compact-page-v2` reduces the size of the existing source representation, particularly for OCR-heavy drawings, but does not demonstrate a consistent provider-latency improvement across representative inputs.

For the Schneider OCR-enabled drawing:

- V1 consumed 45,309 input tokens in the earlier measured calls.
- V2 consumed 37,310 input tokens.
- V1 timed out at approximately 100 seconds during the medium-reasoning comparison.
- V2 completed in approximately 87 seconds and matched all 24 source checklist items.
- V2 preserved all 445 source readings.
- Most of the payload savings came from compressing internal source-witness and layout metadata rather than simplifying the engineering text itself.

V1 remains the default, and V2 remains an opt-in experimental configuration.

These findings suggest that further optimization should focus on the information the AI actually requires, rather than losslessly compressing the complete internal source representation.

## 2. Objective

Implement and evaluate an AI-facing source representation that is:

- Easy for the model to understand.
- Efficient in input-token consumption.
- Suitable for electrical engineering drawings, equipment schedules, datasheets, and single-line diagrams.
- Directly compatible with source evidence citations.
- Independent of PowerForge's internal provenance representation.
- Deterministically generated from pinned source artifacts.

Additionally, decouple local OCR execution from the decision to send OCR data to the AI.

The central architectural principle is:

**PowerForge owns source processing, provenance, localization, and deterministic validation. The AI owns semantic interpretation, engineering attribute extraction, equipment association, and evidence selection.**

The AI should not be required to decode unnecessary internal data structures or reconstruct provenance relationships that PowerForge already knows.

## 3. Scope and architectural constraints

Milestone C2 is primarily a Stage 2 input optimization milestone.

Preserve:

- The existing two-stage extraction architecture.
- GPT-6 Luna with medium reasoning.
- The engineering registry and attribute definitions.
- The existing typed attribute assertion contract.
- Current engineering mapping and normalization policies.
- Existing source artifacts and authoritative source representations.
- Immutable response auditing.
- Run-profile pinning, request identity, execution fencing, and retry guarantees.
- Existing worker concurrency settings.

Do not implement Milestone D output compression, server-owned assertion IDs, or unrelated engineering validation corrections as part of this milestone.

Do not introduce additional AI calls into the extraction pipeline.

Keep Stage 1 behavior unchanged. For controlled Stage 2 evaluations, reuse the exact same pinned recognition result across input configurations.

## 4. Work Package C2.1 — Analyze the existing AI-facing input

Inspect the current V1 and V2 provider projections.

Identify every major category of information currently transmitted to the AI and classify it as:

1. Required for engineering extraction.
2. Required for equipment association.
3. Required for evidence selection.
4. Useful but potentially redundant.
5. Required only for PowerForge's internal processing, validation, or auditing.

Pay particular attention to:

- Native and OCR readings.
- Reading coordinates.
- Alternate transcriptions.
- Overlap relationships.
- Source-witness references.
- Table cells and headers.
- Reading-order relationships.
- Artifact identifiers and hashes.
- Source preparation and layout metadata.
- Recognition results and equipment references.
- Registry definitions and extraction guidance.

Measure the serialized size and, where a suitable tokenizer is available, estimated token contribution of each category.

Distinguish local token estimates from actual provider-reported token usage.

Document which information can be omitted or simplified without impairing engineering interpretation or evidence selection.

## 5. Work Package C2.2 — Implement a readable AI-facing source representation

Introduce a new experimental source projection, provisionally named `readable-page-v1`.

This representation must be purpose-built for AI consumption rather than being a reversible compression of V1.

### 5.1. Readable source text

Present reliably associated source readings in a natural, readable order with directly accessible citation references.

For example:

```text
[q308] System [q309] Ampacity: [q310] 800A
```

The model should not need to calculate character offsets to identify individual readings.

Each original reading reference must remain independently addressable.

Group readings only where existing pinned layout relationships establish a reliable reading sequence. Do not invent lines or combine unrelated readings based solely on proximity.

Preserve standalone readings where reliable grouping is unavailable.

### 5.2. Verified tables

Present confirmed table structures in a readable row-and-column representation.

For example:

| Circuit | Model | Current | Poles |
|---|---|---|---|
| [q101] 1 | [q102] HGL | [q103] 150A | [q104] 3 |
| [q105] 3 | [q106] HGL | [q107] 100A | [q108] 3 |

The example is illustrative; select an appropriate deterministic serialization after reviewing the existing table contracts.

Preserve:

- Source reading references.
- Row and column relationships.
- Header associations.
- Merged cells and meaningful spans.
- Units established by headers.
- Relevant table captions.
- Uncertainty and unresolved relationships.

Do not construct apparently authoritative tables from unverified layout partitions.

Where table structure is unresolved, retain the original source readings and relevant spatial context.

### 5.3. Simplified spatial context

Provide spatial information in a straightforward representation where it contributes to equipment association, reading interpretation, or evidence selection.

Prefer direct normalized bounding boxes over indirect source-witness relationships.

PowerForge must retain exact authoritative geometry internally.

Do not reduce coordinate precision or remove individual geometry if doing so would introduce ambiguity. Any proposed coordinate simplification must be independently tested.

### 5.4. Directly represent source conflicts

Communicate conflicting or uncertain transcriptions in a manner that does not require the model to traverse internal support tables.

For example:

```json
{
  "ref": "q120",
  "text": "800A",
  "alternatives": ["B00A"],
  "issue": "TRANSCRIPTION_CONFLICT"
}
```

The actual representation must preserve the distinction between alternate transcriptions of the same reading and conflicting readings from separate source occurrences.

Never silently resolve conflicting text, suppress uncertain readings, or replace OCR output with an assumed correct value.

### 5.5. Remove unnecessary internal metadata

Avoid transmitting information used exclusively for internal provenance verification, such as:

- Artifact UUIDs and storage identifiers.
- Internal cryptographic hashes.
- Source preparation manifest metadata.
- Internal source-token identifiers that are not valid citation targets.
- Indexed provenance witness tables.
- Detailed table-boundary construction evidence.
- Internal execution metadata.

Retain any semantic information conveyed by these structures that the model genuinely requires.

All authoritative information must remain available internally and continue to participate in source identity and validation.

The provider-facing projection does not need to expand into the complete V1 payload. Instead, it must preserve source coverage, citation identity, meaningful relationships, and uncertainties.

### 5.6. Simplify the source-decoding instructions

Create versioned prompt instructions appropriate for the readable representation.

The source representation should be sufficiently intuitive that the model does not require extensive instructions explaining character offsets, internal witness tables, or indirect reference structures.

Preserve existing engineering extraction instructions and safeguards.

Do not undertake general extraction-prompt optimization at this stage; that belongs to Milestone D.

## 6. Work Package C2.3 — Decouple OCR preparation from provider input

Local OCR execution and provider input selection must become independent decisions.

Running OCR must not automatically require transmitting the complete OCR representation to OpenAI.

Likewise, excluding OCR from a provider request must not delete, invalidate, or modify the internally stored OCR artifacts.

Introduce independently configurable, pinned Stage 2 input configurations.

### Configuration A — Existing baseline

- Full page image at high detail.
- Existing `compact-page-v1` source representation.
- Pinned equipment recognition result.
- Applicable registry definitions.

### Configuration B — Readable hybrid

- Full page image at high detail.
- New `readable-page-v1` source representation.
- Available native and OCR readings.
- Pinned equipment recognition result.
- Applicable registry definitions.

### Configuration C — Image only

- Full page image at high detail.
- Pinned equipment recognition result.
- Applicable registry definitions.
- No page-level native/OCR reading payload or layout representation.

Local native/OCR readings and layout artifacts remain available to PowerForge for evidence localization and verification.

The AI must not invent reading references that were not exposed in its request. It may return appropriate visual citations or literal page-local quotations under the existing citation contract.

Inspect whether the pinned recognition result contains embedded textual evidence. Document this explicitly: image-only refers to the Stage 2 page-source modality, not necessarily to the absence of all source-derived text in its recognition prerequisite.

Do not modify the recognition result between configurations.

### Configuration D — Text only

- New `readable-page-v1` source representation.
- Available native and OCR readings.
- Confirmed table structures and relevant spatial context.
- Pinned equipment recognition result.
- Applicable registry definitions.
- No page image transmitted to OpenAI.

The original page image must remain stored and pinned internally.

The model must not claim visual evidence or image inspection for a request that did not contain an image.

Do not automatically fall back to another configuration when a selected input is insufficient. Record an explicit outcome.

### Existing V2 candidate

Retain `compact-page-v2` as a separately available experimental comparator.

Avoid introducing unnecessary combinations of configuration flags. Prefer a small set of explicitly supported and validated input configurations.

## 7. Work Package C2.4 — Local evidence localization without transmitted OCR

Investigate and implement a bounded, deterministic evidence-localization candidate that can use internally stored native/OCR readings even when those readings were not sent to the AI.

For example, the AI visually identifies:

- Attribute: Continuous Current Rating.
- Raw value: `800A`.
- Proposed value: `800`.
- Proposed unit: `A`.
- Approximate page region.
- Supporting source label and equipment context.

PowerForge should investigate whether the reported literal source expression can be localized against the pinned source readings within the reported region.

First inspect and reuse the existing quotation-resolution and reading-localization mechanisms wherever possible.

### Localization requirements

A successful localization must:

- Use only the exact pinned source artifacts associated with the current page.
- Match the literal reported expression against source-supported readings.
- Respect reading order and source geometry.
- Establish a unique, sufficiently supported source occurrence.
- Preserve the original provider-reported citation.
- Retain the actual resolved reading references and source coordinates.
- Record the localization method and outcome.

Do not establish evidence merely because the proposed value exists somewhere on the page.

For repeated ratings, overlapping equipment, conflicting transcriptions, ambiguous expressions, or insufficient regional support, leave the evidence unresolved or visual-only.

Do not use fuzzy numeric matching, semantic substitution, assumed OCR corrections, or the proposed registry value alone as proof of source support.

Resolving a value does not independently prove its engineering meaning or equipment ownership. Preserve the existing requirements for label, header, equipment, unit, and qualifier evidence.

### Isolation requirement

Treat this localization extension as an independent experimental capability.

Do not silently enable it for existing extraction configurations or change existing mapping outcomes.

Evaluate the same provider responses with the original localizer and the experimental localizer using offline replay wherever possible. This separates improvements in AI extraction from improvements in deterministic evidence resolution without incurring additional provider calls.

Any persisted localization-policy change must be appropriately versioned and auditable.

## 8. Work Package C2.5 — Configuration, identity, and transport

Review and update the relevant request, profile, provider, and execution contracts.

The implementation must support the selected input modalities without weakening existing execution integrity.

Ensure that:

- Input configuration is pinned at run admission.
- Retries use the original pinned configuration.
- Provider requests contain exactly the expected modalities.
- Text-only requests genuinely omit image transmission.
- Image-only requests genuinely omit the page-source reading and layout payload.
- The same authoritative page and recognition prerequisite remain bound internally.
- Provider request hashes reflect the actual transmitted payload.
- Prompt and source-projection versions participate in execution identity.
- Existing response audits remain immutable and verifiable.
- Offline replay uses the exact applicable projection and localization-policy version.

Keep V1 as the default throughout implementation and evaluation.

Do not introduce automatic document classification or adaptive modality selection during this milestone.

## 9. Work Package C2.6 — Performance instrumentation and debugger

Extend the existing Milestone A instrumentation and Extraction Debugger as necessary to identify:

- Selected input configuration.
- Source projection version.
- Whether local OCR was executed.
- Whether OCR readings were transmitted to the provider.
- Whether native readings were transmitted.
- Whether an image was transmitted.
- Source reading count available internally.
- Source reading count exposed to the AI.
- Serialized request sizes.
- Provider-reported input, cached, reasoning, and visible output tokens.
- Provider latency.
- Evidence localization method and outcome.

Reuse existing telemetry wherever possible.

Do not create a separate debugger application or introduce unnecessary database tables.

Do not expose raw engineering source contents through unrestricted telemetry or logging.

## 10. Work Package C2.7 — Offline verification

Before making any additional paid OpenAI calls, perform offline verification using the existing five benchmark inputs:

1. Schneider panel without OCR.
2. Schneider panel with OCR.
3. Simson Maxwell.
4. Siemens schedule.
5. REX diagram.

Use the same pinned artifacts and recognition results from the previous controlled evaluations.

For each input configuration, report:

- Total serialized provider request size.
- Source-text and layout payload sizes.
- Registry and recognition payload sizes.
- Image payload size.
- Estimated token usage, where available.
- Source reading coverage.
- Citation-reference integrity.
- Preservation of meaningful layout relationships.
- Preservation of conflicts and uncertainties.
- Deterministic projection identity.

For the readable hybrid and text-only configurations, establish that all relevant source readings remain accessible and that no source occurrence has silently disappeared.

For the image-only configuration, establish that the omitted source data remains available to PowerForge internally.

Include representative sanitized examples of the actual AI-facing representations so they can be reviewed for readability and complexity.

## 11. Work Package C2.8 — Controlled live evaluation

Prepare a live comparison procedure, but do not execute paid calls without explicit approval.

Use the same five pinned benchmark inputs and compare:

| Configuration | Image | Page-source representation |
|---|---|---|
| A | High detail | V1 |
| B | High detail | Readable |
| C | High detail | None |
| D | None | Readable |

Use existing V2 benchmark results as a historical comparator. If a fresh V2 comparison is necessary, identify and justify it separately.

The initial screening would require 20 Stage 2 calls, assuming all four configurations are eligible for all five inputs.

Keep the following fixed across configurations:

- Model.
- Medium reasoning effort.
- Pinned recognition result.
- Applicable registry catalog.
- Engineering extraction instructions, except required modality-specific guidance.
- Output schema.
- Output-token ceiling.
- Provider service tier.
- Engineering mapping and normalization policies.

Use a common explicitly approved timeout. If a longer diagnostic timeout is proposed, apply it consistently across the comparison and report the effect separately from previous 100-second runs.

Do not retry failed benchmark calls within the initial sample.

Alternate configuration order where practical and record cached input tokens.

Report:

### Performance metrics

- Provider-only duration.
- Total Stage 2 duration.
- Input tokens.
- Cached input tokens.
- Reasoning tokens.
- Visible output tokens.
- Request size.
- Completion and timeout rates.
- Estimated cost per successful page.

### Engineering-quality metrics

- Exact source checklist matches.
- Attribute discovery and coverage.
- Correct equipment association.
- Numerical and unit correctness.
- Correct engineering interpretation.
- Incorrect or unsupported critical values.
- Inferred versus extracted correctness.
- Fatal response-validation failures.

### Evidence-quality metrics

- Resolved evidence.
- Visual-only evidence.
- Unresolved or conflicting evidence.
- Correct source-occurrence localization.
- Incorrect or ambiguous localization.
- Evidence resolution using internally retained OCR.

Evaluate semantic extraction quality separately from evidence resolution and final mapping outcomes.

A correctly extracted value that cannot be grounded must not be scored as equivalent to an incorrectly extracted engineering value.

Likewise, a lexical unit representation issue, such as `Ω` versus `Ω`, must be distinguishable from an incorrect unit magnitude or engineering parameter.

## 12. Performance objectives and promotion criteria

The provisional optimization objectives are:

- Reduce Schneider OCR-enabled Stage 2 input from the historical 45,309-token baseline toward 25,000 tokens or fewer.
- Reduce reasoning overhead associated with interpreting the source representation.
- Reduce provider latency without sacrificing attribute coverage.
- Complete OCR-heavy extraction within the normal operating timeout.
- Preserve or improve evidence quality.
- Avoid new engineering-semantic errors.

These are optimization targets, not guarantees.

Do not promote a configuration solely because it produces fewer tokens, completes faster, or returns fewer assertions.

A candidate must not introduce:

- New incorrect critical engineering values.
- Material attribute omissions.
- Incorrect equipment ownership.
- Silent source loss.
- Incorrect evidence localization.
- Weakened source-verification requirements.
- Unacceptable completion-rate regressions.

Use the initial live evaluation as screening evidence. A single observation per configuration and input is insufficient to establish general performance superiority. Require additional approved paired evaluations before recommending a default change when results are uncertain.

If no candidate satisfies the quality and performance gates, retain V1 as the default and document the findings.

Do not implement additional source representations indefinitely. Complete the defined experiments, report the results, and proceed to Milestone D once the input optimization findings have been reviewed.

## 13. Testing requirements

Add focused automated tests covering:

- Deterministic readable-source projection.
- Preservation of original reading references.
- Reliable line grouping.
- Verified table presentation.
- Merged-cell and header relationships.
- Conflicting and uncertain readings.
- Unicode and engineering-symbol preservation.
- Literal source text containing citation-like syntax or instructions.
- Repeated values and distinct source occurrences.
- Image-only provider transport.
- Text-only provider transport.
- Hybrid provider transport.
- Exclusion of hidden reading references from valid model-generated citation targets.
- Local quotation and region-constrained evidence resolution.
- Rejection of ambiguous or unsupported evidence localization.
- Profile pinning and retry consistency.
- Request identity and response-audit integrity.
- Offline response replay.
- Debugger telemetry and historical attempt handling.

Treat all document contents as untrusted source data, including text that resembles citation identifiers, serialization delimiters, or extraction instructions.

Run relevant Python, PostgreSQL integration, debugger backend/frontend, lint, build, and migration checks.

Report skipped tests and unresolved environmental limitations.

## 14. Out of scope

Do not implement:

- Automatic adaptive input selection by document type.
- Additional AI extraction stages or calls.
- Region-based parallel AI extraction.
- Changes to Stage 1 recognition behavior.
- Compact provider-output schemas.
- Server-generated assertion IDs.
- Raw-unmapped overflow corrections.
- General engineering semantic-validation redesign.
- Changes to engineering registry semantics.
- Worker concurrency changes.
- Unrelated frontend changes.

Record any defects discovered in these areas as separate follow-up issues.

## 15. Deliverables

Provide:

1. Implemented and tested experimental Stage 2 input configurations.
2. A documented readable-source representation contract.
3. A deterministic local evidence-localization candidate, if supported by the existing source architecture.
4. Offline payload comparisons for all five benchmark inputs.
5. Representative examples of the actual provider-facing input.
6. Updated configuration documentation and debugger support.
7. Automated regression and integration tests.
8. A controlled live evaluation procedure with explicit proposed call and spending limits.
9. A summary of architectural decisions, limitations, and unresolved issues.

Create an evaluation document at:

`evals/phase6r/ATTRIBUTE_SOURCE_MODALITY_EVALUATION.md`

Document the implementation, offline findings, reproduction commands, evaluation methodology, and eventual live results.

Update the existing performance specification to include Milestone C2 without discarding the documented Milestone C results.

## 16. Execution instructions

Implement Milestone C2 incrementally in the order specified above.

Begin by inspecting the existing source projection, provider transport, evidence localizer, and pinned execution contracts. Reuse existing mechanisms rather than creating competing architectures.

Keep changes focused, maintainable, and consistent with PowerForge's existing architecture.

Complete implementation, automated testing, and offline evaluation before requesting approval for live OpenAI calls.

Do not make paid provider calls without explicit approval of the source inputs, call budget, and spending limit.

Do not change the default input configuration, default reasoning effort, or existing production extraction behavior.

Once implementation and offline verification are complete, stop and provide the results for review before proceeding with the live evaluation or Milestone D.