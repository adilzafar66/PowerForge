# Phase 6R evaluation baseline

This is the 6R-A evaluation protocol. Section 7 of the [implementation plan](../../docs/PHASE6R_IMPLEMENTATION_PLAN.md) carries the provisional numerical targets. The historical comparison is main at `dea1ed3b9423dec9c1834672519e16c2853add49`. Reproduce its scripted reports in an isolated checkout and identify its document selections, annotation definitions and limitations. Those reports contain no comparable live benchmark. Compare only matching sources and denominators. Keep any baseline provider run separately authorized and outside the 6R runtime.

## Development fixtures

- Prose and raw values. `evals/extraction/v1/sources/transformer.txt`, `invalid_values.txt` and `qualifiers.txt`.
- Optional tags and unsupported types. `evals/extraction/v1/sources/tagless_visual.png`, `unknown_equipment.txt` and `borrowed_tag.txt`.
- Schedules and ownership. `evals/tables/v1/sources/positioned_schedule.pdf`, `wrong_row_proposal.txt`, `hierarchical_merged.png` and `conflicting_values.txt`.
- Diagrams and mixed evidence. `evals/classification/fixtures/sld-one.pdf`, `evals/spatial/v1/sources/electrical-fixtures.pdf`, `breaker-degraded.png` and `oriented-nameplate.tiff`. Confirm document/page content when assigning gold.
- Negative and ambiguity controls. `evals/extraction/v1/sources/no_equipment.txt`, `repeated_tags.txt`, `hybrid_conflict.txt` and `hybrid_conflict.png`. Include a multi-page case with repeated tags and a schedule with identical values on different rows. Assign separate observation identities.

Use the existing corpora as source and annotation leads. Independently review their expected assertions under 6R rules, particularly header-derived units, tag-less equipment and raw unmapped retention. Repository fixtures are development material. Live authorization is required before submitting any selected source to a provider.

## Gold records

Each case has a stable ID, split (`OFFLINE_DEVELOPMENT`, `LIVE_FEASIBILITY` or `HELD_OUT`), content SHA-256, source and page selection, and one or more strata. The live manifest records source authorization reference and the approved pages, model/profile, maximum calls/spend and retention. Keep customer content and restricted annotations in controlled private storage.

For each selected page, annotate all in-scope occurrences before scoring:

- Equipment records have an independent page-local ID, source description, registry type or null, source tag and tag state, qualification, and supporting occurrences.
- Attribute records have an independent ID, expected equipment gold ID or null, key or null for raw-unmapped assertions, source label/value/unit/qualifiers, expected enum proposal and optional canonical typed value/unit, expected mapping state and source occurrences. Record the source-supported unit occurrence for dimensional values and all distinct conflicting assertions.
- Each occurrence identifies its role, source page and exact text or geometry location. Use a text artifact and code point offsets when available, otherwise use a manually annotated region or page-only expectation. Keep original text evidence distinct from any OCR transcription. Keep the expected localization class and the source occurrence separate from the engineering interpretation.

The checked-in [gold schema](gold.schema.json) supplies the shape for offline and private live annotations. Validate source identity, distinct IDs, owner references and occurrence bounds against the selected page independently of JSON shape checks. Lock the gold and split before evaluation. Resolve annotation disagreements from the source and record adjudication. Hold out whole documents and avoid reusing near-duplicate drawings across development and held-out sets.

## 6R-C feasibility checkpoint

Use a small real-world sample. Start with one authorized representative page per category of prose, schedule and diagram. Select additional pages only within the agreed page and call budget to cover meaningful omissions. Freeze the exact sample, independent annotations, model/profile and budget before execution. Run through the durable two-stage runtime. Record attempts, refusals, skips, failed pages and usage availability. Review the findings before D begins.

- Equipment recall is matched in-scope gold equipment occurrences divided by all gold equipment occurrences.
- Attribute accuracy measures exact permitted key plus source value/unit and enum proposal on matched assertions. Report correct matches over all expected attributes as well. Attribute discovery misses include equipment omissions that prevented Call 2 from seeing an owner.
- Ownership measures correct source-local owners among assigned assertions and over all gold assignable assertions. Report explicit unassigned results and incorrect links separately.
- Evidence quality measures supported fragment roles and correct occurrences against gold. Report wrong occurrence, foreign, ambiguous, unresolved and approximate evidence separately. Review against pinned artifacts before D implements final localization.
- Record measured input/output tokens and elapsed provider time per attempt, total per page including retries, and elapsed page workflow time. Report counts and missing telemetry, with latency summaries suited to the small sample. Estimate cost only from measured usage and versioned rates.

Match one-to-one within page using independent source occurrences and reference identities. Break ambiguous matches using source adjudication. Do not pair assertions by tag or value alone. Report sample counts and numerators/denominators for each measure, using unavailable for an empty denominator. Failures and omitted results stay in the relevant recall denominators. The checkpoint provides feedback on feasibility and does not apply final numerical gates.

## Capacity review before live execution

The current limits are suitable starting ceilings for the small feasibility sample. The positioned schedule fits the local contracts for both requests. Keep the existing observation, citation, JSON and image caps and apply any lower deployment or provider limits. A page can exceed an aggregate byte or token cap before reaching its item caps. The schedule fixture exercises contract fit, while representative input and output headroom still needs measurement.

In C, include a schedule with representative row density, record the encoded request size, returned JSON size, observation and citation counts, image bytes and pixels, measured tokens, and the effective profile caps by stage. Record which limit prevented execution or caused overflow and keep those pages in recall reporting. Use these observations to review the initial caps and decide whether to change the versioned limits before comprehensive evaluation. Keep one page projection per stage and explicit overflow reporting.

## 6R-F comprehensive evaluation

Freeze the independent held-out benchmark, sample sizes by stratum, scoring rules and model configuration. Review representative live results, corpus sizes and evaluation procedures before finalizing thresholds. Record those thresholds before running the benchmark. Use the complete production path and report precision, recall, type/tag accuracy, exact normalized attributes, source/owner coverage and correctness, conflicts and raw preservation in addition to the C measures. Report per-stratum counts, full failures, usage, latency distributions and reproducibility. Reproduce the baseline only where the prior pipeline's scope and scoring are comparable. Held-out results are used for release assessment. Known limitations remain visible in the handoff.

There are no selected or authorized live documents recorded by 6R-A. Capture exact scope and budget with the operator before executing C or F.
