# Milestone D — Attribute Output Optimization and Response Reliability

## Reliability-only correction

The compact contract is a historical experiment. It cut visible tokens by 54.2% and median provider latency from 53.0 to 32.8 seconds, while direct-extraction checklist coverage fell from 73/74 to 25/74. The requirements here supersede the original compact deliverable and live comparison below. Preserve `compact-assertions-v1` and its resources for historical replay. Keep `legacy-v7` as the production default.

- Add `server-owned-assertions-v1` using the original descriptive Stage 2 assertion fields, extracted and inferred variants, and explicit `kind` citation shapes. Only the provider assertion IDs and the raw-unmapped intake limit change. Reuse the internal v7 validators, registry, and publication. Stage 1 remains unchanged.
- Assign IDs from each item's original collection and zero-based position. Receive up to 32 raw-unmapped assertions, admit the first 16 valid items, quarantine invalid ones, and record valid overflow positions. Preserve existing byte, nesting, citation, and integrity limits. A provider-supplied assertion ID is quarantined. No model response repair is part of admission.
- Use the consolidated D0 prompt for evaluation. Replace its ID instruction with “PowerForge assigns assertion identifiers. Do not include `local_ref` in either response collection.” Keep the instructed limit of 16 raw-unmapped assertions and prioritize the most meaningful ones. Preserve the source-format instructions, engineering guidance, and evidence requirements.
- Pin provider schema, prompt, identity, admission, expansion, and complete request digest independently of the input and prompt presets. Extend the audit output-version constraint additively. Preserve exact retained bytes, historical identities, retries, fencing, telemetry, and debugger comparison by original position.
- Replay the five fresh Milestone D controls and the historical Siemens duplicate-reference and Schneider overflow failures offline before evaluating live. Check typed and inferred values, ownership, evidence and mapping, all five source configurations, and the existing publication and retry safeguards.
- Subject to separate approval, screen fresh paired controls and candidates on these same five inputs with at most 10 Stage 2 calls, no retries, and a proposed US$6 cap. Pair all settings with the existing 16,384-token ceiling, medium reasoning, standard tier, and the consolidated D0 guidance. A diagnostic 180-second timeout requires separate approval. Track production-window completion, heartbeat and lease outcomes, engineering coverage, evidence and mapping, assertion counts, latency and usage, and cost per correct checklist match. Coverage and structural reliability determine adoption.

See the [offline results and live procedure](../../evals/phase6r/ATTRIBUTE_OUTPUT_OPTIMIZATION_EVALUATION.md#reliability-only-correction). Further output compression is outside this correction. Milestone E addresses concurrent page extraction.

## Original Milestone D specification

## 1. Objective

Continue development on `codex/phase-6r-extraction-performance`.

Review the existing performance specification, the D0 implementation and evaluation results, and the subsequent heartbeat investigation.

Milestone D0 demonstrated that the revised main prompt with consolidated engineering guidance can significantly improve extraction coverage. However, the additional assertions increase output-token consumption and provider latency.

Milestone D should:

- Reduce unnecessary output-token generation.
- Eliminate failures caused by AI-generated assertion identifiers.
- Prevent secondary raw-unmapped observations from invalidating otherwise valid responses.
- Preserve engineering correctness, extraction coverage, and evidence quality.
- Improve completion rates and provider latency.

Use `core-catalog-v1` as the primary experimental foundation.

The guiding principle is that the AI should generate information requiring engineering interpretation, while PowerForge handles deterministic structural responsibilities.

## 2. Implementation scope

### D1 — Analyze existing provider responses

Analyze representative retained responses from the previous benchmarks, particularly D0's consolidated configuration.

Determine how much response content is attributable to:

- Repeated field names and structural metadata.
- AI-generated assertion identifiers.
- Null fields and empty collections.
- Raw and proposed engineering values.
- Evidence citations and repeated quotations.
- Duplicate or redundant observations.
- Raw-unmapped assertions.

Investigate why the consolidated D0 configuration generated substantially more output tokens than the core-only configuration.

Distinguish useful additional engineering information from unnecessary structural overhead and unsupported or redundant assertions.

Use actual retained responses and recorded usage telemetry. Distinguish serialized byte measurements from token measurements.

### D2 — Server-owned assertion identifiers

Remove the requirement for the AI to generate `local_ref` for Stage 2 assertions under the new output contract.

PowerForge should generate deterministic assertion identifiers using the response collection and original item index.

Ensure that:

- Identifiers are unique and stable during replay.
- Quarantined assertions do not change subsequent identifiers.
- Distinct source occurrences retain distinct identities.
- Equipment references remain selected by the AI.
- Historical responses retain their original identifier semantics.

Review existing identifier dependencies before implementation.

The recurring duplicate-reference failure should no longer be possible under the new output contract.

### D3 — Raw-unmapped overflow handling

Prevent bounded overflow or individually invalid items in the `raw_unmapped` collection from invalidating otherwise valid registry-linked assertions.

Implement deterministic, bounded admission that:

- Preserves independently valid assertions.
- Records overflowed and quarantined items explicitly.
- Retains original item indices and provider response content.
- Maintains hard response-size and processing limits.
- Does not silently discard information.

Review how provider-side schema constraints interact with the existing raw-unmapped allowance.

Continue rejecting malformed JSON, invalid envelopes, duplicate JSON object keys, and violations of hard resource or integrity limits.

Do not introduce automatic AI response repair or additional provider calls.

Preserve historical admission behavior for legacy responses.

### D4 — Simplify the provider-facing output contract

Based on the D1 findings, simplify the existing Stage 2 provider response contract.

Investigate opportunities to:

- Remove deterministically generated fields.
- Eliminate redundant structural constants.
- Reduce unnecessary null fields and empty collections.
- Simplify evidence representations.
- Shorten frequently repeated field names where beneficial.
- Simplify extracted, inferred, and raw-unmapped assertion structures.

Do not introduce an aggressively compressed output representation unless the measured benefits justify its complexity.

Prefer intuitive JSON objects over positional arrays.

Preserve all meaningful engineering information, including:

- Equipment association and uncertainty.
- Registry attribute identity.
- Extracted versus inferred origin.
- Raw and proposed values.
- Units and numerical precision.
- Qualifiers and value forms.
- Alternate representations.
- Inference explanations.
- Evidence and source references.

PowerForge must deterministically reconstruct the existing internal assertion representation.

Do not infer missing engineering information during structural reconstruction.

Account for the pinned model's Structured Outputs restrictions.

The internal assertion model, database representation, normalization pipeline, and frontend should remain unchanged wherever possible.

### D5 — Refine evidence generation

Reduce unnecessary evidence-generation overhead without weakening source verification.

Investigate whether the provider can use simpler citation representations where an existing reading reference sufficiently identifies the source.

PowerForge should reconstruct deterministic citation metadata wherever appropriate.

Retain literal quotations when necessary to identify compound expressions, substrings, or source occurrences. Preserve visual citations for applicable input configurations.

Review D0 evidence failures, particularly:

- Schneider native assertions with correct proposals but unresolved VALUE evidence.
- Composite breaker ratings and pole-count expressions.
- Compound voltage expressions.
- Incorrectly interpreted generic ampere ratings.
- Assertions that were accepted but could not be mapped.

Distinguish problems in AI evidence selection from limitations in deterministic localization or normalization.

Do not weaken existing evidence-eligibility, source-verification, or normalization policies to improve benchmark results.

Retain the existing citation limit unless a change is supported by the analysis and separately approved.

### D6 — Update the revised main prompt

Use `attribute_extraction_core_v1.txt` and the D0 modular prompt architecture as the foundation.

Modify the main prompt only where necessary to reflect:

- Server-owned assertion identifiers.
- The revised provider output contract.
- Simplified evidence representations.
- Updated raw-unmapped admission requirements.
- Responsibilities now handled deterministically by PowerForge.

Preserve the existing organized prompt structure.

Do not reintroduce equipment-specific guidance into the main prompt.

Do not independently expand or substantially rewrite the approved engineering instructions.

Preserve the consolidated registry notes and equipment-level guidance.

Present any substantive prompt wording changes for review before implementation.

### D7 — Versioning, auditing, and execution integrity

Introduce an independently selectable Stage 2 output version, provisionally:

`EXTRACTION_ATTRIBUTE_OUTPUT_VERSION`

The new output configuration should remain independent of the selected input representation and prompt configuration.

Ensure compatibility with all five existing input representations.

Use the consolidated D0 configuration as the primary evaluation target.

Pin the applicable:

- Provider response schema.
- Prompt resources.
- Output contract.
- Assertion identity policy.
- Admission and expansion policies.
- Request identity.

Ensure that retries use the original pinned configuration.

Preserve historical prompts, catalogs, response contracts, request identities, and replay behavior.

Use the complete provider-body digest for the new output configuration.

Retain original provider responses for auditing and expose meaningful admission and expansion diagnostics through the existing extraction debugger.

Extend telemetry to identify the output version and report received, accepted, quarantined, and overflowed assertions.

Reuse existing database and auditing infrastructure wherever possible. Avoid unnecessary abstractions or database tables.

Keep existing production defaults unchanged pending evaluation.

### D8 — Offline evaluation and regression testing

Use retained responses from the five existing benchmark inputs:

- Schneider native.
- Schneider OCR.
- Simson Maxwell.
- Siemens breaker schedule.
- REX transformer.

Evaluate the revised contract through deterministic offline transformations and replay.

Measure:

- Response-size reductions.
- Estimated token savings, where supported.
- Structural overhead per assertion.
- Semantic equivalence between existing and expanded assertions.
- Preservation of engineering values and evidence.
- Recovery of valid assertions from historical duplicate-reference and overflow failures.

Clearly distinguish hypothetical transformed responses from actual provider-generated responses.

Add regression tests covering:

- Server-generated assertion identifiers.
- Stable identities during quarantine and replay.
- Bounded raw-unmapped admission.
- Deterministic output expansion.
- Extracted, inferred, and raw-unmapped assertions.
- Typed values and equivalent-unit representations.
- Evidence eligibility across all input configurations.
- Profile pinning and request identity.
- Historical replay.
- Auditing and publication integrity.
- Hard resource limits.

Run relevant unit, PostgreSQL integration, debugger, lint, and build checks.

Provide representative examples of the actual proposed output contract and corresponding expanded internal assertions.

## 3. Controlled live evaluation

Prepare, but do not execute without separate authorization, a controlled comparison using the same five pinned benchmark inputs.

### Primary comparison

| Parameter | Control | Candidate |
|---|---|---|
| Input | compact-page-v1 | compact-page-v1 |
| Prompt foundation | core-catalog-v1 | core-catalog-v1 with necessary output-contract adjustments |
| Engineering guidance | Consolidated D0 | Consolidated D0 |
| Reasoning | Medium | Medium |
| Output contract | Existing | Optimized |
| Assertion identifiers | AI-generated | Server-generated |
| Admission policy | Existing | Improved |

Keep the model, recognition results, source artifacts, registry definitions, engineering guidance, service tier, and output-token ceiling identical.

Use the existing 16,384-token output ceiling.

Consider the previously approved 180-second diagnostic timeout for both configurations, while separately reporting completion within the existing 100-second production window.

The initial comparison should require no more than 10 Stage 2 calls with zero retries.

Use fresh paired controls rather than relying exclusively on historical D0 results.

Rotate execution order and record cached-token usage.

### Performance measurements

Report:

- Input, reasoning, and visible output tokens.
- Provider and total Stage 2 latency.
- Visible output tokens per accepted assertion.
- Received, accepted, quarantined, and overflowed assertions.
- Completion and publication rates.
- Cost per attempted and published page.
- Cost per correct checklist match.

Include failed attempts in applicable denominators.

### Engineering quality measurements

Evaluate:

- Extraction coverage.
- Correctness of engineering values and units.
- Equipment association.
- Inference correctness.
- Unsupported additional assertions.
- Duplicate observations.
- Evidence resolution.
- Mapping and independent source-verification outcomes.

Use the existing 74-item benchmark checklist, supplemented by review of assertions outside the checklist.

Do not equate a mapped candidate or resolved citation with independently verified engineering correctness.

Pay particular attention to preserving the consolidated D0 configuration's 60/60 checklist matches across its four successfully evaluated inputs.

Complete the Siemens comparison that was previously interrupted by lease expiration.

Monitor the newly implemented heartbeat diagnostics throughout evaluation. Treat any lease failure separately from provider-response or extraction-quality failures.

### Provisional targets

Aim for:

- A 30–50% reduction in visible output tokens on dense engineering drawings.
- Median Stage 2 provider latency approaching 30–45 seconds.
- Improved response completion and publication rates.
- No material regression in extraction coverage or engineering correctness.
- Elimination of duplicate assertion-reference failures under the new contract.
- Preservation of valid primary assertions during bounded raw-unmapped overflow.

These are optimization targets, not mandatory thresholds or guaranteed results.

Do not achieve token or latency reductions by omitting useful engineering attributes or necessary evidence.

Treat the initial benchmark as screening evidence, not a statistically conclusive evaluation.

Following the primary evaluation, consider testing the optimized output contract with image-only and readable-hybrid inputs using matched controls and separate approval.

## 4. Constraints

Do not change:

- Stage 1 equipment recognition.
- Consolidated D0 engineering guidance.
- Engineering registry definitions or requirement rules.
- Internal engineering model.
- Mapping and normalization policies.
- Source representations or input defaults.
- Production evidence-localization policies.
- Medium reasoning default.
- Production timeout.
- Worker concurrency.
- Lease duration, renewal cadence, or execution fencing.

Do not introduce additional AI calls, automatic response repair, or automatic modality selection.

Do not remove historical resources required for replay.

Keep the implementation focused and maintainable.

## 5. Deliverables

Provide:

1. Baseline output analysis.
2. Server-owned assertion identifiers.
3. Bounded raw-unmapped overflow handling.
4. A simplified provider-facing output contract.
5. Deterministic expansion into internal assertions.
6. Necessary adjustments to the revised main prompt.
7. Updated configuration, telemetry, auditing, and debugger support.
8. Automated tests and offline evaluation results.
9. A proposed live evaluation procedure with explicit call and spending limits.

Document the results in:

`evals/phase6r/ATTRIBUTE_OUTPUT_OPTIMIZATION_EVALUATION.md`

Update the original performance specification accordingly.

## 6. Execution instructions

First inspect the current codebase and produce an implementation plan for review.

Identify:

- Actual output optimization opportunities.
- Proposed provider response structures.
- Deterministic expansion rules.
- Necessary main prompt changes.
- Affected files and contracts.
- Architectural concerns and unnecessary complexity.
- Testing and acceptance criteria.

Provide concrete examples of existing and proposed provider assertions.

Do not modify files or make paid provider calls during planning.

Following implementation approval, complete the changes, automated testing, and offline evaluation.

Stop before paid live evaluation and request separate approval.

Do not promote new production defaults without explicit authorization.