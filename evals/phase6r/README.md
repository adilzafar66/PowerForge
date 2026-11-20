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
- Attribute records have an independent ID, expected equipment gold ID or null, key or null for raw-unmapped assertions, source label/value/unit/qualifiers, origin, typed proposal, proposed unit, value form, alternate representations, expected mapping state, optional canonical typed value/unit, and source occurrences. Inferred records identify the inference explanation and keep the proposed value separate from literal source transcription. Record the source-supported unit occurrence for dimensional values and all distinct conflicting assertions.
- Each occurrence identifies its role, source page and exact text or geometry location. Use a text artifact and code point offsets when available, otherwise use a manually annotated region or page-only expectation. Keep original text evidence distinct from any OCR transcription. Keep the expected localization class and the source occurrence separate from the engineering interpretation.

The checked-in [gold schema](gold.schema.json) supplies the shape for offline and private live annotations. Validate source identity, distinct IDs, owner references and occurrence bounds against the selected page independently of JSON shape checks. Lock the gold and split before evaluation. Resolve annotation disagreements from the source and record adjudication. Hold out whole documents and avoid reusing near-duplicate drawings across development and held-out sets.

## 6R-C feasibility checkpoint

Use a small real-world sample. Start with one authorized representative page per category of prose, schedule and diagram. Select additional pages only within the agreed page and call budget to cover meaningful omissions. Freeze the exact sample, independent annotations, model/profile and budget before execution. Run through the durable two-stage runtime. Record attempts, refusals, skips, failed pages and usage availability. Review the findings before D begins.

- Equipment recall is matched in-scope gold equipment occurrences divided by all gold equipment occurrences.
- Attribute accuracy measures the permitted key, source value and unit, typed proposal, and alternate representations on matched assertions. Score extracted and inferred assertions separately. Report correct matches over all expected attributes as well. Attribute discovery misses include equipment omissions that prevented Call 2 from seeing an owner.
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

## Typed-value offline replay

```sh
.venv/bin/pytest -q tests/test_extraction_stage_contracts.py -k gold_schedule
.venv/bin/pytest -q tests/test_extraction_publication.py -k 'siemens_style or corrected_semantic'
```

The positioned schedule replay verifies the pinned PDF digest, builds the v6
response from the gold record, and compares ownership, mapping, the normalized
value, and exact source occurrence spans. The synthetic Siemens-style replays
exercise the recorded model and pole-count assertions, inferred technology and
abstention cases, explicit and ambiguous ratings, and equivalent dimensions.
These replays verify deterministic admission and publication with reviewed
responses. Live provider extraction quality requires a separately authorized
evaluation.

### Milestone E verification

- The final execution profile pins `phase-6r-wire-v6`, Stage 2
  `phase-6r-attributes-v6`, prompt bundle `phase-6r-stages-v9` with
  `attribute_extraction_v8.txt`, publication `phase-6r-publication-v11`, and
  unit notation `source-unit-interpretation-v3`. Stage 1 schemas and prompt
  match the baseline. `registry-v1` and `compact-page-v1` are unchanged.
- A fresh PostgreSQL 16 database migrated through
  `6r_0014f_typed_value_proposals`. The integration suite verified the v6
  write guard, typed persistence, rollback, worker recovery, and audit
  enforcement. The seeded v5 migration test was outside the approved scope.
- The Linux offline run passed 1,071 tests, skipped 285 under the offline
  configuration, and deselected 353 integration-marked tests. The focused
  Linux run passed 85 tests with zero skips using disposable PostgreSQL,
  MinIO, Redis, and the worker image's Tesseract. The first host run hit
  missing Tesseract, and an initial focused Linux runner lacked Uvicorn.
  The final Linux runs resolved both environment failures.
- The debugger backend passed 11 tests, including journaled retrieval from
  disposable MinIO with restricted operator credentials. The web and debugger
  frontend suites passed 366 and 16 tests respectively. TypeScript, lint,
  both production builds, and Chrome Debugger checks at 1440, 1024, and
  390 px passed.

The broad offline and focused integration pytest runs used the Linux
source-enrichment worker image with test dependencies installed. Alembic and
the standalone debugger backend tests ran from the host virtual environment.
Point integration settings at disposable services before running these commands.

```sh
alembic -c database/alembic.ini upgrade head
RUN_INTEGRATION=0 python -m pytest -q -m 'not integration'
RUN_INTEGRATION=1 python -m pytest -q \
  tests/test_extraction_schema.py tests/test_extraction_operations.py \
  tests/test_extraction_debugger_integration.py tests/test_workers.py \
  tests/test_enrichment_ocr.py tests/test_spatial_evaluation.py \
  tests/test_enrichment_execution.py tests/test_enrichment_celery.py \
  tests/test_spatial_celery.py
PYTHONPATH=tools/extraction-debugger python -m pytest -q -rs tools/extraction-debugger/tests
npm --prefix apps/web test
npm --prefix apps/web run lint
npm --prefix apps/web run build
npm --prefix tools/extraction-debugger test
npm --prefix tools/extraction-debugger run build
```

The debugger backend command uses a retained synthetic response selected by
`EXTRACTION_DEBUGGER_TEST_ATTEMPT` for its optional MinIO test. The provider
schema projections passed local Draft 2020-12 validation and mocked
transport tests. Live OpenAI schema acceptance and extraction quality remain
unverified for v6.
