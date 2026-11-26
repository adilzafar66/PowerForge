# Engineering extraction quality before Milestone F1

Offline investigation on the Phase 6R performance branch.

recover technical text and its source locations on image-heavy sheets, then address occurrence selection and compound-value representation. The Schneider runs accepted all 821 attribute assertions, while only 16 of 646 attribute VALUE fragments precisely resolved and all 821 source-value states were unverified.

## Scope and method

Baseline 8715b7a on codex/phase-6r-extraction-performance. Schneider PDF pages 8–16, runs a087111a and 3205c968. Verified 36 retained-response digests and reconstructed all 36 exact dispatched requests from pinned source artifacts. Replayed local admission and candidate projection and checked against stored results. Used the same independently reviewed 64-fact panel checklist and inspected selected schedule rows and original responses. Historical comparisons use retained Siemens, Simson and REX result exports and prior reports, with separate denominators.

## Schneider outcomes by run

| Metric | a087111a · 2 slots | 3205c968 · 4 slots |
|---|---:|---:|
| Stage 1 equipment observations | 173 | 223 |
| Stage 1 qualifications · proposed / installed / unknown | 141 / 15 / 17 | 99 / 63 / 61 |
| Exact repeated equipment payloads beyond first, excluding local_ref | 11 | 0 |
| Stage 2 received / admitted | 418 / 418 | 403 / 403 |
| Stage 2 mapped / unmapped / invalid | 81 / 214 / 123 | 71 / 184 / 148 |
| Mapped inferences · separate from reported extraction | 33 | 18 |
| Panel fact checklist · correct raw / mapped / precisely localized | 64 / 6 / 0 | 64 / 4 / 0 |
| Stage 2 VALUE fragments · resolved / total | 0 / 326 | 16 / 320 |
| Stage 2 all fragments · resolved / approximate / unresolved | 2 / 189 / 272 | 69 / 122 / 359 |
| Stage 2 quote mismatch / ambiguous quote / invalid visual region | 272 / 0 / 0 | 265 / 12 / 82 |
| Stage 2 source-value support · unverified | 418 | 403 |
| Stage 2 SOURCE_VALUE_MISMATCH · count | 123 | 148 |
| Stage 2 SOURCE_EXPRESSION_UNVERIFIED · count | 79 | 84 |
| Stage 2 UNIT_MISSING_OR_AMBIGUOUS · count | 67 | 18 |
| Stage 2 UNREPRESENTABLE_VALUE_FORM · count | 30 | 43 |
| Stage 2 UNSUPPORTED_ATTRIBUTE · count | 30 | 17 |

Source data comes from the two November 25 Pacific live benchmark runs. Row units are observations, assertions, facts or fragments as labeled. A classified equipment candidate is not an independent confirmation. Zero byte-identical Stage 2 assertions were observed after ignoring IDs. Identical structure is narrower than semantic duplication. All 821 claims resolved to an asserted same-page owner reference, while the checklist and continuation examples expose limits on engineering association.

## Source-to-publication traces

### Page 10 · Circuit 62 was a prepared space

*Confirmed recognition and qualification error*

The PDF labels row 62 PREPARED SPACE and uses a dashed symbol. On the prepared page no table structure was available. The page image carried the row. The pinned readings did not supply a reliable schedule representation.

Run 3205c968 proposed breaker-ckt-62 as LV_BREAKER / INSTALLED. Its visual citation reported “Circuit 62. QOB” and omitted the preparation label. The structurally valid assertion survived local validation and was published as a registry-classified equipment candidate with VISUAL_REPORTED evidence. The two-slot arm did not report this prepared position as installed.

**Recommended correction.** The recognition prompt already forbids provision-only observations. Add contrastive evaluation examples with adjacent solid and dashed rows and a fully visible prepared-space label. Score qualification and row identification. Keep the visual-only result visibly approximate.

Code references include prompts/equipment_recognition_v4.txt:13 · publication.py:66

### Pages 10, 11, 13–15 · Separate omissions, groups and repetition

*Confirmed output differences and schedule-grounded defects*

Page 15 Panel M has a detailed schedule with explicit breaker rows. Page 11 is a continuation with a branch summation and no row-level circuit positions.

On page 15, a087111a emitted just the bus and omitted visible breakers. 3205c968 emitted 33 breaker candidates, without establishing that all are correct. On page 10 the respective arms emitted 53 and 62 breaker candidates, yet neither gave any of those breaker IDs a registry-linked Stage 2 attribute. This omission is already present in both original Stage 2 responses. Page 11 produced no breaker candidates in the two-slot arm and eight quantity-group candidates in the four-slot arm, including a 23-position PS line. Stage 2 attached registry claims to all eight groups. The group-to-occurrence ambiguity entered in Stage 1. On page 13 the two-slot response repeated its circuit 18 candidate with a new local_ref. Ten more exact repeats beyond the first on page 14 describe unresolved positions. The payload repeats are measurable, while physical duplication is uncertain.

**Recommended correction.** Add an occurrence checklist that distinguishes per-position devices, explicit proposed devices, totals, continuation references and provisions. Evaluate attribute coverage per recognized occurrence. Preserve the distinct-reference check, and keep occupancy and physical-identity decisions in AI/review.

Code references include stage_contracts.py:388 · attribute_admission.py:111 · publication.py:97 · assertion_consistency.py:8

### Page 12 · Correct visual bus ratings stayed unmapped

*Confirmed source-modality and normalization interaction*

Panel B prints a 225 A copper bus, 200 A system/main-lug ampacity, 14 kA symmetrical SCCR, and 208Y/120 V. The relevant literals were absent from its 116 pinned readings. The page had zero detected tables and reported NATIVE_DRAWING_PRIMITIVE_LIMIT.

Both original Stage 2 responses proposed 225 A for continuous_current_rating with an approximate VALUE box. The box survived localization. Unit verification requires eligible resolved text, so 225 A remained UNIT_MISSING_OR_AMBIGUOUS. Both responses also treated the separate 200 A system or lug rating as a competing bus proposal. It remained unmapped. The 14 kA SCCR remained UNREPRESENTABLE_VALUE_FORM with the qualifier intact. The 208Y/120 expression remained unmapped when paired with the scalar 208. A bus-material proposal of COPPER carried the whole “225A RATED COPPER BUS” string and remained SOURCE_EXPRESSION_UNVERIFIED.

**Recommended correction.** Test drawing-aware text coverage and schedule association first. Clarify bus rating versus main-lug/system rating in the AI guidance. Preserve the compound voltage and qualifiers. Evaluate separately whether the registry should represent both voltage bases or an explicitly identified component with complete provenance.

Code references include native_spatial.py:176 · unit_notation.py:250 · value_proposal.py:130,266,288 · registry_v1.py:1756

### Pages 8 and 15 · Numeric verification has several distinct failure modes

*Confirmed overloaded diagnostic and source-expression mismatch*

Page 15 prints 30/3 under an AMP/P column. Page 8 prints 73 inches paired with 1854 mm. The latter metric value is a rounded counterpart of 1854.2 mm.

For page 15 pole_count the four-slot output retained 30/3 as a SINGLE raw expression and proposed the integer 3. The model selected the printed pole component, but the numeric verifier rejected the two-number expression as SOURCE_VALUE_MISMATCH. Across both runs, 252 of 271 occurrences of that reason involved pole_count, frame_rating or trip_rating. That count identifies the involved fields, with correctness of each selected component still unadjudicated. Page 8's equivalent-height assertion proposed 73 in and retained 1854 mm. In the two-slot arm “Height” was a qualifier and mapping stopped at UNREPRESENTABLE_VALUE_FORM. In the four-slot arm raw_unit was “in” while the paired source expression used an inch symbol. The equivalent-pair match compared literal spellings and returned SOURCE_VALUE_MISMATCH. It never reached the exact-equivalence check. Missing text evidence is an additional barrier.

**Recommended correction.** Separate diagnostics for a contradictory scalar, a correctly preserved but unsupported compound expression, unit-spelling disagreement and a rounded dual-unit pair. Design an explicit, bounded way to cite a component within a compound expression before changing any mapping rule. Treat rounded pairs as reviewable.

Code references include value_proposal.py:176,212,266,288 · registry_v1.py:2065,2091,2130

### Pages 8, 11 and 15 · Reading success and visual failure

*Confirmed localization causes with distinct remedies*

All nine snapshots retained image and readings, reported the primitive limit and contained zero inferred tables. Eight used native readings and page 11's 64 readings came from local OCR.

All 98 submitted READING IDs hit exposed pinned IDs across both stages and arms. Stage 2 had 537 QUOTE_MISMATCH fragments. None of those quotes appeared as a case-folded substring within an individual pinned reading. That check does not rule out visually correct transcriptions or spans across readings. Page 8 recognition's bare quote “1” was ambiguous. All 117 invalid visual fragments across both stages occurred on four-slot page 15. Every rejected box contained a component above 1, including the recognition box (142, 849, 435, 235). The contract parsed the numbers, and the localizer correctly rejected their page bounds. The pattern is consistent with pixel-like coordinates. All 16 resolved Stage 2 VALUE fragments came from OCR page 11 and none established source-value support on the panel checklist.

**Recommended correction.** Separate a visual transcription from an exact pinned quote in the guidance. Prefer the exposed reading ID on text and a bounded normalized region on image-only evidence. Test a visually unambiguous but text-absent value and an ambiguous repeated quote. Keep pixel reinterpretation and automatic coordinate repair outside the fallback.

Code references include evidence_localization.py:93,116,167,212 · stage_contracts.py:68 · spatial_geometry.py:49

## Historical comparison

### Siemens · dcab2728 and e776214a

The original source lists CMD6, CJD6 and CND6 and prints ETU745. The earlier run’s four recognized breaker models were missing as Stage 2 registry assertions. ETU745 was submitted under both model and technology keys, which are distinct claims. The later server-owned output matched 14/14 and mapped ETU745 as trip_unit_model. It quarantined one separate raw-unmapped item for the citation cap. A compound bus voltage stayed unmapped despite TEXT_MATCH on a fragment. Source matching and scalar admissibility answer separate questions.

### Simson · d998e0b5 and compact 87693b99

The compact historical result used literal reading text in an ID field and quarantined five registry-linked plus ten raw-unmapped records. A published follow-up with server-owned assertions matched 7/7 checklist facts. Its 73 IDs all matched the pinned source. It retained the reported 0.00131 Ω armature resistance as unmapped for value form. The fresh control lost that checklist item at the 12-citation limit. These are distinct contract, evidence-selection and normalization failures.

### REX · 8a9fa40d and earlier feasibility

The drawing contains a paired secondary voltage and an impedance range. The earlier pinned layout exceeded the grid-component budget while retaining 304 readings. The later server-owned result matched 5/5 checklist items. The raw secondary pair 208Y/120 was retained with a proposal-type mismatch. This is a scalar schema boundary, with a whole expression still available for review. The historical artifact is a separate page trial.

### Delta · feasibility and focused stage verification

The original 80T1 drawing labels the tag and states measured impedance may differ from the drawing. Preparation historically dropped optional geometry at the primitive limit while preserving text and the raster. The follow-up transport first rejected the extended provider schema, then accepted REX recognition under the portable schema. Delta’s next response failed exact-decimal validation on four visual coordinates. The corrected wire schema admitted 13 attribute assertions. The accepted Stage 2 response body was unavailable for claim replay, so mapping and engineering accuracy remain unverified.

See evals/phase6r/SIEMENS_STAGE2.md, ATTRIBUTE_OUTPUT_OPTIMIZATION_EVALUATION.md and FEASIBILITY_6R_C_CORRECTION.md, plus docs/PHASE6R_IMPLEMENTATION_PLAN.md:358 and :382. The later historical exports were inspected as historical contracts. Their counts are reported separately.

## Decisions for F1

1. **Source coverage.** Measure engineering literals and row anchors available in pinned native readings. Benchmark a bounded local OCR or region projection offline against the same pages. Reserve a separate approval for provider evaluation. The primitive diagnostic confirms lost optional geometry, while the cause of missing technical text is the source’s largely graphical rendering on the sampled sheets. The effect of additional OCR on these exact runs remains unmeasured.
2. **Recognition and ownership.** Annotate the complete Panel A and Panel M schedules with installed/proposed/reference/provision distinctions and contiguous circuit positions. Record actual missing occurrences and false observations. Build a separate continuation checklist for aggregate quantities.
3. **Evidence contract.** Measure reading-ID selection, textual verification and visual region validity separately. Add region-boundary and repeated-quote examples before considering a new schema. Keep approximate evidence visibly approximate.
4. **Registry and validator.** Define when a source-supported component of an AMP/P expression, qualified SCCR, voltage pair or rounded dual-unit dimension should map, and design fixtures for contradictory values. Keep trip/frame semantics separate and retain source strings. Defer policy changes until those engineering decisions are approved.
5. **Evaluation.** Score raw coverage, mapping, source-value support, evidence and ownership independently. Include Type and field-level quarantine counts. Compare variations on frozen sources and use held-out sheets before attributing changes to prompt, modality, contract or worker concurrency.

Two same-document calls per page do not identify a concurrency effect. Breaker recall, engineering ownership and inference correctness were not exhaustively annotated. The 64-fact score is panel-level raw coverage, not an accuracy estimate over all candidates. The retained data cannot show which model attention or token allocation decision produced a stage omission.

No paid calls were made. This report records investigation results only.
