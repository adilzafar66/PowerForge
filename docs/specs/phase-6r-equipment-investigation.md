# PowerForge — Milestone F1-B3: Controlled Equipment Recognition Investigation

## 1. Background

Continue development on the `codex/phase-6r-extraction-performance` branch.

The F1-A investigations and F1-B1 baseline evaluation are complete. F1-B2 has established a revised equipment recognition objective and architectural requirements that supersede certain assumptions made during the original Phase 6R implementation.

Review the existing implementation and the following investigation reports before proceeding:

- `evals/phase6r/EXTRACTION_QUALITY_INVESTIGATION.md`
- `evals/phase6r/f1a/REPORT.md`
- `evals/phase6r/f1a/F1_A2_REPORT.md`
- `evals/phase6r/f1a/TABLE_ABLATION_REPORT.md`
- `evals/phase6r/f1b/REVIEW.md`
- `evals/phase6r/f1b/BASELINE.md`

The existing `occurrence-evidence-v1` prompt correction is suspended pending this investigation. Do not conduct the previously proposed candidate evaluation without reconsidering its objectives against the F1-B2 decisions.

F1-B3 is an investigation milestone. Do not implement permanent production architecture changes. Experimental implementations and isolated evaluation infrastructure are permitted.

## 2. Revised recognition objective

Identify equipment within the supplied equipment scope of a source document, classify it according to the PowerForge equipment registry, identify its equipment tag where available, and provide source locations supporting its identification.

Equipment types may be explicitly identified or inferred using engineering knowledge. Equipment that cannot be classified into a supported registry equipment type shall be excluded.

Empty provisions, unselected alternatives, reference-only equipment and equipment outside the supplied equipment scope shall not be extracted as independent equipment entries.

The final equipment extraction output shall contain only unique equipment configurations. Equipment uniqueness shall be determined exclusively by registry equipment type, equipment tag and registry-associated attribute values.

Identical equipment may be grouped where equivalence is sufficiently established. All associated source evidence shall be preserved.

Equipment with differing tags, differing registry attributes or insufficient information to establish equivalence shall remain separate.

Deduplication shall apply across all pages of an individual document. Cross-document equipment reconciliation is outside the extraction workflow.

Equipment lifecycle and qualification classifications are not required.

## 3. Binding F1-B2 architectural decisions

Document the following decisions in the repository as the governing requirements for the recognition redesign.

### B2-D01 — Unique equipment configurations

PowerForge's extraction output is a collection of unique equipment configurations, not an inventory of every physical equipment instance.

Multiple physically distinct devices may correspond to one final extraction entry when they are identical within the scope of the PowerForge registry.

### B2-D02 — Supplied equipment scope

Extract only equipment forming part of the supplied equipment scope represented by the document.

The AI is responsible for interpreting the engineering context and determining whether equipment belongs to the supplied scope.

Do not introduce deterministic engineering classification rules or manufacturer-specific scope heuristics.

### B2-D03 — Excluded equipment

Do not create independent equipment entries for:

- Empty prepared spaces and provisions.
- Unselected equipment alternatives.
- Generic equipment legends.
- External equipment mentioned only for reference or compatibility.
- Equipment outside the supplied scope.
- Equipment that cannot be classified into the registry.

Information concerning excluded equipment may still provide context for extracting attributes of supplied equipment.

For example, the upstream Eaton PDG23G-LFD breaker mentioned in the Eaton panel drawing should not be extracted as a separate equipment entry.

### B2-D04 — Remove qualification

Equipment qualification and lifecycle classification are not required.

The redesigned recognition architecture shall not require:

- `qualification`
- `raw_qualification`
- `INSTALLED`
- `PROPOSED`
- `FUTURE`
- `SPARE`
- `REFERENCE`
- `LEGEND_ONLY`
- `UNKNOWN` as an equipment qualification

This does not eliminate the requirement to distinguish actual supplied equipment from empty provisions or reference-only equipment.

That distinction is part of recognition scope, not a stored qualification.

### B2-D05 — Remove unnecessary recognition fields

The proposed minimum recognition contract shall not require:

- `source_description`
- `tag_state`
- `qualification`
- `raw_qualification`

Investigate whether these removals affect recognition quality or downstream association.

Do not retain fields solely because they were present in the previous architecture.

### B2-D06 — Minimum recognition output

Stage 1 should provide only:

- Registry equipment type.
- Equipment tag, if applicable and identifiable.
- Source location references supporting recognition.

PowerForge may assign internal identifiers for Stage 2 association.

Investigate server-owned recognition identifiers rather than requiring the AI to generate unnecessary identifiers.

Internal identifiers and provenance metadata are not additional engineering extraction requirements.

### B2-D07 — Equipment type inference

Allow the AI to identify equipment types through either:

- Explicit source information.
- Engineering inference based on source descriptions, symbols, characteristics or context.

Equipment type inference is permitted and does not require the literal registry equipment type to appear in the document.

The source information supporting the inference should be referenced.

### B2-D08 — Unsupported equipment

If the AI cannot identify an equipment type with sufficient confidence, or the identified type does not correspond to a supported registry equipment type, omit the equipment observation.

Do not produce unknown equipment candidates solely to preserve every possible source observation.

### B2-D09 — Recognition evidence

Recognition evidence exists to identify the source locations supporting the equipment type and tag.

The minimum requirements are:

- Location of the equipment type information, if explicitly stated.
- Location of the information supporting equipment type inference, if inferred.
- Location of the equipment tag, if present.

Approximate visual locations are acceptable.

A whole-page reference is acceptable when the recognition is genuinely supported by distributed page information or overall page context.

Precise quotations, exact text offsets and exact bounding boxes are not universally required for Stage 1 recognition.

Prefer more specific evidence when available, but do not reject valid recognition solely because precise text localization is unavailable.

Recognition evidence requirements are distinct from Stage 2 attribute evidence requirements. Do not weaken Stage 2 attribute grounding as part of this investigation.

### B2-D10 — Equipment uniqueness

Two equipment configurations are identical only when:

1. Their registry equipment types are identical.
2. Their equipment tags are identical, or both are absent.
3. Their registry-associated attribute sets and values are identical.

Registry-associated attributes are attributes corresponding to defined registry attributes, not merely attributes with `status = "MAPPED"`.

Attribute validation status is not itself an equipment identity criterion.

Include registry-associated inferred attributes in the comparison where their values are established.

Exclude the following from uniqueness comparisons:

- Raw unmapped attributes.
- Original source wording.
- Evidence locations.
- Citation counts.
- Source formatting.
- Validation status itself.
- Internal extraction identifiers.

Preserve raw unmapped information without allowing differences in that information to prevent otherwise identical equipment configurations from being merged.

Compare established engineering values using normalized values and units where applicable.

Unresolved, invalid or uncertain values must not be treated as proof of equivalence.

### B2-D11 — Partial attribute matches

Do not merge configurations merely because their available attributes do not conflict.

If one device contains a registry-associated attribute that is missing for another device, retain separate configurations unless shared source information or reliable engineering interpretation establishes equivalence.

Do not assume that two poorly extracted or attribute-empty devices are identical merely because their available attribute sets match.

### B2-D12 — Conflicting configurations

Keep equipment configurations separate when registry-associated attribute values differ, even when equipment tags are identical.

Different tags always establish distinct entries.

Do not resolve conflicting engineering configurations automatically.

A tagged and an untagged observation shall remain separate unless the source establishes that they describe the same equipment identity.

### B2-D13 — Document-level deduplication

Final deduplication shall occur across all pages of an individual source document.

Do not perform cross-document equipment reconciliation during extraction.

The existing page-scoped AI execution architecture should be retained for the investigation.

### B2-D14 — Evidence preservation

When identical equipment is grouped or merged, preserve all associated source locations and supporting evidence.

Early AI grouping must not cause irreversible loss of occurrence-specific information.

Where subsequent extraction reveals that grouped devices have different registry attributes, the architecture must allow them to be separated.

## 4. Investigation objectives

Determine whether the existing recognition quality problems originate primarily from:

1. Model capability.
2. Model reasoning configuration.
3. Image resolution and representation.
4. Native text and OCR source representation.
5. Registry mapping requirements.
6. Structured output complexity.
7. Prompt complexity.
8. Evidence requirements.
9. Equipment occurrence and grouping requirements.

Determine the minimum sufficient recognition contract and source representation that reliably satisfy the F1-B2 objective.

Do not assume that adding more instructions, source information or reasoning effort will improve results.

Establish conclusions through controlled comparisons.

## 5. Investigation corpus and revised ground truth

Retain the existing six-document development corpus:

- `delta-transformer-drawing.pdf`
- `eaton-panel-drawing.pdf`
- `rex-transformer-drawing.pdf`
- `schneider-panel-drawing.pdf`
- `siemens-panel-drawing.pdf`
- `simson-generator-drawing.pdf`

Preserve the original F1-A and F1-B1 fixtures and results for historical comparison.

Create versioned F1-B3 ground truth based on the revised objective.

For each document, independently establish:

- Equipment within the supplied scope.
- Equipment excluded from the supplied scope.
- Expected registry equipment types.
- Expected equipment tags.
- Source locations supporting recognition.
- Equipment occurrences potentially representing identical configurations.
- Equipment occurrences that must remain distinct.
- Registry-associated distinguishing attributes.
- Cases where equivalence cannot be established.

Remove qualification accuracy from the revised evaluation.

Reassess all previous reference-equipment expectations. Specifically, exclude the upstream PDG23G-LFD reference in the Eaton drawing.

Distinguish a document describing the equipment being supplied from a document merely mentioning external equipment for reference. Do not exclude manufacturer datasheets solely because of their document type.

### Schneider drawing

Use the Schneider drawing as a primary diagnostic case because previous investigations established:

- Most engineering lettering is represented as graphical outlines.
- Native text extraction recovers almost none of the engineering annotations.
- OCR recovers only part of the engineering information.
- Prepared spaces at circuits 7 and 10 were incorrectly recognized as breakers.
- Some correctly recognized equipment received incorrect or unresolvable evidence.
- Repeated breaker configurations provide a useful deduplication test.

The expected physical source occurrences are one panel assembly and eight specified branch breakers, excluding circuits 7 and 10.

Investigate the following potential identical-equipment groups:

- Circuits 1 and 2.
- Circuits 3, 5 and 6.

Do not assume these groups are identical until their registry-associated attributes and applicable shared source specifications have been reviewed.

Preserve both occurrence-level ground truth and unique-configuration ground truth.

### Held-out evaluation

Retain the existing synthetic controls.

Obtain independent engineering holdout documents where available, covering:

- Clean native-text schedules.
- Dense equipment schedules.
- Outlined or vector-based engineering drawings.
- Scanned equipment documents.
- Repeated equipment with identical and differing specifications.
- Reference-only equipment.
- Prepared spaces and unselected alternatives.

If suitable independent documents are unavailable, explicitly document that limitation. Synthetic holdouts shall not be presented as proof of engineering generalization.

## 6. Investigation A — Fundamental model capability

Establish whether the existing API model can correctly interpret the drawing without PowerForge's full extraction requirements.

Begin with the Schneider drawing, then extend selected experiments to representative documents from the development corpus.

Compare:

### A1 — Image and simple natural-language instruction

Supply only the original page image and a concise instruction to identify supplied equipment and its tags.

Request a natural-language response.

### A2 — Image and minimal structured output

Use the same image and recognition objective, but require a minimal structured response containing equipment identification, type and tag.

Do not require registry mapping or detailed evidence in this diagnostic arm.

### A3 — Minimal registry-mapped recognition

Use the same image and structured recognition task, adding the relevant registry equipment types and descriptions.

Determine whether registry mapping affects equipment recognition.

Evaluate equipment detection, supplied-scope interpretation and classification separately.

The purpose is to establish model capability under progressively constrained conditions, not to select an image-only production architecture.

## 7. Investigation B — AI-facing source representation

Using a fixed model, reasoning configuration, recognition objective and output contract, compare:

### B1 — Image only

Original page image without supplemental source readings.

### B2 — Image and native text

Original image with native text and corresponding source locations.

### B3 — Image and positioned native/OCR readings

Original image with the selected native/OCR preparation and positioned readings.

### B4 — Simplified positioned source representation

Supply the same underlying source information using a concise experimental representation containing only information useful for recognition.

Preserve reading identifiers, text, source locations and necessary uncertainty information.

Investigate removal of redundant metadata and repeated structural information from the AI-facing representation.

Do not remove provenance from the underlying PowerForge source records.

### B5 — Existing complete recognition input

Use the existing Stage 1 AI-facing source representation as a control, aligned to the same recognition objective where necessary.

Determine whether additional source information improves or interferes with recognition.

Specifically investigate cases where OCR text conflicts with visually readable engineering information.

Use the F1-A preparation findings as the starting point:

- Native-first source preparation.
- Conditional 300 DPI OCR.
- Experimental directional line removal where justified.
- Positioned-only layout as the preferred experimental configuration.
- Existing reading order.
- Original page image retained.

Keep deterministic table reconstruction available as a controlled comparison when it produces meaningful structure.

Do not repeat the entire F1-A offline investigation.

## 8. Investigation C — Recognition contract and prompt complexity

Compare the existing recognition requirements with progressively simplified alternatives.

### C1 — Existing recognition contract

Use the existing Stage 1 prompt and schema as the historical architectural control.

Rescore responses against the revised supplied-equipment objective where applicable.

Do not evaluate qualification accuracy as a requirement of the redesigned architecture.

### C2 — Simplified recognition contract

Use a minimal experimental contract containing:

- Registry equipment type.
- Nullable equipment tag.
- Recognition source locations.

Remove unnecessary descriptions, tag-state classifications and lifecycle fields.

Allow source locations supporting equipment type inference.

### C3 — Simplified evidence requirements

Compare the minimum recognition contract under different evidence requirements:

- Existing detailed citation requirements.
- Simplified reading and visual references.
- Justified approximate or page-level references.

Preserve the distinction between precise evidence, approximate evidence and unsupported evidence.

Determine whether strict quotation and citation requirements interfere with equipment identification.

### C4 — Concise recognition prompt

Develop a concise recognition prompt aligned with the F1-B2 objective.

The prompt should emphasize:

- Identifying supplied equipment.
- Recognizing supported registry types.
- Extracting tags.
- Excluding prepared spaces and reference-only equipment.
- Preserving relevant source locations.
- Using engineering inference where appropriate.

Do not carry forward obsolete qualification guidance.

Avoid redundant instructions, manufacturer-specific exceptions and unnecessary output requirements.

Where possible, isolate prompt changes from schema changes. Where this is not possible, explicitly report the coupled experimental variable.

## 9. Investigation D — Model configuration and image quality

Using matched source inputs and recognition contracts, investigate the effects of the following.

### D1 — Stage 1 reasoning effort

Compare the current provider-default reasoning behavior with explicitly configured reasoning levels supported by the selected model.

Test supported levels incrementally and stop escalating when further increases provide no meaningful benefit.

Record the effective requested reasoning configuration.

Measure recognition quality, latency, output tokens, reasoning tokens where reported, and cost.

### D2 — Image quality

Investigate:

- Actual page dimensions and raster dimensions.
- Effective rendering DPI.
- Image size limits.
- Provider image detail settings.
- Potential provider-side resizing.
- Readability of small text, dashed symbols and schedule rows.

Compare the current analysis image with higher-resolution or regionally enhanced visual input where supported.

If testing crops or tiles, preserve whole-page engineering context and map local evidence back to the original page coordinates.

Do not assume that improving OCR raster resolution automatically improves the image supplied to the AI.

### D3 — Model capability comparison

If meaningful recognition failures persist after simplifying the task and testing reasoning and image configuration, compare suitable alternative OpenAI API models.

Verify model availability, supported capabilities and pricing before proposing live comparisons.

Use equivalent task objectives and explicitly record model-specific settings.

Do not change the default production model during F1-B3.

## 10. Investigation E — Equipment grouping and deduplication

Determine whether equipment uniqueness should primarily be handled by AI recognition, deterministic PowerForge processing, or a hybrid approach.

This investigation may use limited experimental Stage 2 extraction to determine attribute equality. It must not become a general Stage 2 accuracy or architecture redesign.

Compare the following approaches.

### E1 — Individual recognition with deterministic deduplication

Stage 1 identifies individual supplied equipment occurrences.

Stage 2 extracts registry-associated attributes for each occurrence.

PowerForge deterministically compares the resulting configurations and merges identical entries.

### E2 — AI-driven unique equipment recognition

Stage 1 identifies equipment groups that the AI considers equivalent based on the engineering source.

Stage 2 extracts shared registry-associated attributes for each group.

Preserve all group member locations.

Determine whether AI grouping introduces incorrect merges, missed equipment configurations or overlooked distinguishing attributes.

Do not assume grouping is safe merely because equipment type, model family and trip rating match.

### E3 — Hybrid recognition and deduplication

Allow Stage 1 to group equipment when the source sufficiently establishes equivalence.

Retain all group member source locations and occurrence associations.

Stage 2 inspects the information associated with each group and separates configurations when registry-associated differences are discovered.

PowerForge performs final deterministic document-level deduplication.

Investigate the minimum Stage 1 group representation required to allow Stage 2 to detect and recover from incorrect grouping.

If reliable separation requires information unavailable under the simplified contract, report that limitation rather than introducing an irreversible grouping mechanism.

### Deduplication test cases

Include controlled cases covering:

- Identical untagged equipment.
- Identical equipment sharing a tag.
- Identical equipment with different tags.
- Same-tag equipment with conflicting registry attributes.
- Untagged equipment with differing registry attributes.
- Partially extracted equipment.
- Identical registry attributes with differing raw unmapped attributes.
- Equivalent values expressed using different units.
- Registry-associated attributes with different validation statuses.
- Registry-associated inferred attributes.
- Missing or unresolved attribute values.
- Repeated equipment across document pages.
- Grouped equipment subsequently found to differ.

Measure both incorrect merging and failure to merge.

Incorrect merging that causes loss of a distinct engineering configuration is a critical failure.

Use a representative subset for live grouping experiments and offline fixtures for deterministic comparison cases.

Do not implement production deduplication until the preferred architecture has been reviewed.

## 11. Evaluation methodology

Use a staged investigation rather than a full Cartesian product of all experimental variables.

Begin with diagnostic experiments on the Schneider drawing and a representative native-text document.

Extend promising configurations to the complete development corpus.

Validate the selected configuration against reserved holdout documents.

Where possible, vary one experimental factor at a time.

For matched comparisons, pin and record:

- Source PDF and page identity.
- Original image digest and dimensions.
- Source preparation configuration.
- Complete source-projection fingerprints.
- Reading content, identifiers and locations.
- Model identifier.
- Reasoning effort.
- Prompt version and digest.
- Provider schema version and digest.
- Output token budget.
- Timeout.
- Provider transport and relevant settings.
- Request and response audit identifiers.

Use repeated trials to distinguish consistent behavior from normal model variability.

Reuse the existing F1-B1 evaluation infrastructure, audit mechanisms and budget controls where appropriate.

Preserve historical results separately from the revised evaluation.

Do not compare old qualification-oriented metrics directly with new recognition metrics without clearly identifying the differences in ground truth and scoring methodology.

## 12. Evaluation metrics

Separate the following categories.

### Semantic recognition

- Correctly identified supplied equipment.
- Missing supplied equipment.
- Incorrectly identified equipment.
- Registry equipment classification accuracy.
- Equipment tag accuracy.
- Reference-only equipment false positives.
- Prepared-space false positives.
- Unsupported or invented equipment observations.

### Evidence quality

- Correctly associated equipment evidence.
- Correctly associated tag evidence.
- Precise resolved evidence.
- Valid approximate evidence.
- Justified page-level evidence.
- Incorrect evidence association.
- Missing or unsupported evidence.

Do not treat correct equipment recognition as a semantic recognition failure solely because evidence is imprecise.

Retain a separate strict evidence-supported recognition metric.

Do not award page-level evidence credit automatically; verify that page-level context actually supports the recognition.

### Unique-configuration quality

- Expected unique equipment configurations.
- Correctly recovered configurations.
- Missing configurations.
- Redundant configurations.
- Incorrect merges.
- Incorrect grouping.
- Successful group separation.
- Preservation of source evidence.
- Cross-page deduplication accuracy.

An individual physical occurrence and a unique equipment configuration are different evaluation units. Report both where relevant.

### Operational performance

- Provider latency.
- End-to-end latency.
- Local preparation time.
- Request size.
- Input tokens.
- Output tokens.
- Reasoning tokens where available.
- Provider cost.
- Response admission failures.
- Transport failures.
- Output truncation.
- Redundant Stage 2 extraction volume.

Qualification accuracy is not a success criterion.

## 13. Investigation execution and approval gates

### Gate 1 — Documentation and offline preflight

Complete the following before paid provider execution:

- Document all F1-B2 decisions.
- Review the existing recognition and Stage 2 handoff contracts.
- Create revised ground truth.
- Identify affected production components.
- Establish the controlled experimental matrix.
- Define evaluation metrics.
- Implement necessary experimental harnesses.
- Verify source and request fingerprints.
- Propose call counts and cost estimates.

Present the exact proposed experiments, source documents, model configurations, estimated costs and hard budget cap for approval.

The previously approved F1-B1 budget and prompt authorization do not automatically authorize this materially revised investigation.

Do not send paid provider requests before explicit approval.

### Gate 2 — Diagnostic live evaluation

After approval, conduct the initial model capability, source representation and contract complexity experiments.

Review results before expanding the experimental matrix.

Stop pursuing experimental arms that are clearly unsuitable, while preserving their results and explaining the decision.

### Gate 3 — Focused extended evaluation

Evaluate promising configurations on representative documents and the equipment grouping cases.

Conduct reasoning, image quality and alternative model investigations where justified by earlier results.

Do not perform unrelated experiments merely to exhaust the proposed budget.

### Gate 4 — Final recommendations

Present the selected experimental configuration, supporting evidence, trade-offs and proposed recognition redesign.

Do not implement the permanent redesign until F1-B3 has been reviewed and approved.

## 14. Architectural constraints

The investigation must preserve the following principles:

- AI performs engineering interpretation.
- PowerForge owns the canonical equipment and attribute registry.
- PowerForge owns internal identifiers and execution metadata wherever practical.
- PowerForge performs deterministic validation and unit normalization.
- PowerForge preserves source provenance.
- Final deduplication must follow the F1-B2 registry-based uniqueness definition.

Do not:

- Modify the production recognition architecture prematurely.
- Change production database schemas.
- Permanently remove existing recognition fields.
- Permanently remove deterministic table reconstruction.
- Change Stage 2 attribute extraction behavior.
- Weaken Stage 2 evidence validation.
- Introduce manufacturer-specific recognition heuristics.
- Introduce deterministic equipment interpretation.
- Change registry definitions.
- Implement cross-document equipment reconciliation.
- Conduct unrelated refactoring.

Experimental contracts, prompts and grouping mechanisms must remain isolated from the production extraction workflow.

Preserve existing production defaults throughout F1-B3.

## 15. Required deliverables

Create a dedicated F1-B3 evaluation directory under `evals/phase6r/`.

Deliver:

1. F1-B2 architectural decisions document.
2. Revised recognition objective.
3. Revised engineering ground truth fixtures.
4. Occurrence-level and unique-configuration expectations.
5. Existing recognition contract and downstream dependency review.
6. Controlled experimental plan and approval document.
7. Reproducible experimental harnesses.
8. Versioned experimental prompts and schemas.
9. Machine-readable experimental results.
10. Per-document recognition and evidence failure analysis.
11. Equipment grouping and deduplication analysis.
12. Cost, token and latency comparison.
13. Regression tests for experimental infrastructure.
14. Final F1-B3 investigation report.

The final report must explicitly recommend:

- The minimum sufficient Stage 1 recognition contract.
- The preferred recognition prompt.
- The preferred AI-facing source representation.
- Stage 1 reasoning configuration.
- Image preparation and detail configuration.
- Model selection.
- Recognition evidence requirements.
- Equipment grouping and deduplication strategy.
- Required Stage 2 handoff information.
- Required production changes for F1-B4.
- Remaining uncertainties and validation requirements.

Distinguish measured conclusions from architectural recommendations and unverified hypotheses.

## 16. Completion criteria

F1-B3 is complete when we have sufficient controlled experimental evidence to make an informed decision regarding the recognition redesign.

The objective is not to maximize the number of experiments or produce incremental prompt corrections.

The objective is to identify the simplest architecture that reliably recognizes supplied equipment and supports accurate extraction of unique registry-defined equipment configurations.

Run relevant regression tests, commit and push the investigation artifacts, and stop at the F1-B3 review gate.

Do not proceed to F1-B4 without approval.