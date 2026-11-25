# Milestone D attribute output evaluation

## Implementation and evaluation boundary

The opt-in `compact-assertions-v1` output contract keeps the Stage 2 v7 internal assertions and publication pipeline. It removes provider-generated assertion IDs and citation discriminators, shortens repeated field names, and omits the null quote for reading-only evidence. The provider still supplies equipment references, origins, qualifiers, typed proposals, unit alternatives, association, and evidence. Required nullable members and empty arrays remain where the strict object schema needs them. The existing provider schema projection omits unsupported constraint keywords. Local validation enforces the limits.

The server assigns `attr-<index>` and `raw-<index>` from original zero-based collection positions. It validates items independently and admits the first 16 valid raw-unmapped items out of up to 32 received. Invalid items are quarantined, including ones after the admission limit. Remaining valid raw items are recorded as overflow. The 512 registry assertion limit, 12 citations per assertion, 512 KiB response limit, and fatal JSON and envelope checks stay in place. Legacy admission retains its original ID rules and raw limit.

The profile pins the prompt and provider schema hashes, output version, identity policy, admission and expansion policies, and complete provider-body digest. The immutable audit keeps exact original bytes, counts, and overflow positions. The debugger aligns original, expanded, and published records by position. Existing data and the default `legacy-v7` are preserved. The tests exercise all five source configurations. No live compact call was made.

## Retained response baseline

The four comparable D0 consolidated pages produced **26,907 visible output tokens** and 13,215 reasoning tokens, up from **15,351 visible** and 9,855 reasoning tokens for core-only. Accepted assertions increased from 88 to 138, and exact checklist matches increased from 48/60 to 60/60. Visible output per accepted assertion grew from 174 to 195 tokens. Increased coverage explains part of the growth. The remaining increase per assertion is consistent with more detailed values, secondary claims, and citations. Provider latency for these four pages ranged from 17.6–62.3 seconds with the core-only prompt and 32.8–76.1 seconds with the consolidated prompt. The available telemetry measures usage at the whole-response level.

The 138 consolidated assertions included 117 registry-linked and 21 raw-unmapped assertions. In 74,293 minified UTF-8 bytes, property names and colons accounted for 39,978 bytes, ID members for 3,624, null and empty-array members for 7,192, value and unit members for 13,909, and evidence members for 30,322 across 304 citations. The raw-unmapped arrays took 12,629 bytes. These categories overlap. Property names and colons averaged 290 bytes per accepted assertion, ID members 26 bytes, and null and empty-array members 52 bytes. There were 124 repeated quote or reported-text occurrences beyond the first use of each distinct literal, accounting for 1,917 quoted value bytes. Repeated quotations can support different claims. There were zero byte-identical assertions after excluding IDs among those four responses, and the production redundancy heuristic flagged zero. The Siemens core-only replay retained one likely redundant assertion, and the Siemens duplicate-ID example contained one identical repeated assertion. These counts cover exact repeated structure and the existing bounded redundancy policy.

The [D0 engineering review](ATTRIBUTE_PROMPT_REFACTORING_EVALUATION.md#engineering-and-evidence-review) identified several limits this contract retains. Schneider native matched 24/24 checklist facts, with zero resolved VALUE citations and eight mapped matches. A literal composite reading such as `200/3` can support a pole count without establishing whether the ampere value is a frame or trip rating. The panel source's paired voltage could not support the model's scalar proposal. Reading-only citations are appropriate for complete readings and quotations remain available for substrings, composite values, or occurrences whose specific expression matters. The compact change does not resolve the weakest citations or change engineering mapping. Production region localization remains unchanged.

## Offline replay

The replay reconstructed dispatches from the original profiles and pinned source artifacts, checked their request digests against the audits, and retrieved seven exact originals through the restricted operator path. Measurements compare compact JSON with **minified legacy JSON** to exclude differences in whitespace. Recorded provider tokens describe only the original D0 calls. There is no supported local tokenizer estimate for the pinned model, and compact generation latency is unmeasured.

- **Schneider native, D0 consolidated** `898cee65` — 24,393 → 19,250 bytes (**21.1%**), 48 accepted.
- **Schneider OCR, D0 consolidated** `dc5933e4` — 26,451 → 20,228 bytes (**23.5%**), 54 accepted.
- **Simson Maxwell, D0 consolidated** `19e3947e` — 13,073 → 9,896 bytes (**24.3%**), 18 accepted.
- **REX, D0 consolidated** `c04aa312` — 10,376 → 7,887 bytes (**24.0%**), 18 accepted.
- **Siemens, D0 core-only** `d1184da8` — 10,375 → 7,734 bytes (**25.5%**), 18 accepted and two quarantined. This is the retained successful run for the Siemens comparison. The consolidated Siemens call lost its lease before settlement and has no auditable output.

The four consolidated responses shrank **22.9%**, from 74,293 to 57,261 bytes. All five comparable replays preserved the typed assertion content, mapping, ownership, evidence fragments, source-value support, and publication diagnostics apart from the new assertion identities. The replay did not remove any literal quotations or redundant observations.

- **Siemens, D0 legacy duplicate reference** `c7e6f3b4` — the original failed with `duplicate_reference`. Offline compact replay admitted 32 registry-linked and seven raw-unmapped assertions. This count includes independently admitted observations whose engineering quality has not been assessed.
- **Schneider native, C2 V1 raw overflow** `3b20893d` — the original failed its collection limit. Offline compact replay admitted all 52 registry-linked and 16 raw-unmapped assertions. Raw index 16 was recorded as overflow.

Run from an authorized operator environment with the applicable source and database settings, private audit reader credentials, and the output migration applied:

```sh
python evals/phase6r/attribute_output_replay.py ATTEMPT_UUID [ATTEMPT_UUID ...]
```

The report emits only attempt IDs and aggregate measurements after verifying the digests through the existing audit path. Reconstructed original bodies stay in memory. No candidates are published during replay.

## Contract example

A synthetic nameplate example with an explicitly reported equivalent unit and two kinds of reading citations uses the actual provider field names:

```json
{
  "origin": "EXTRACTED",
  "equipment": "equipment-1",
  "association": "ASSERTED",
  "key": "enclosure_width",
  "label": "Width",
  "raw": "20 in (508 mm)",
  "source_unit": "in",
  "value": "20",
  "unit": "in",
  "qualifiers": [],
  "form": "EQUIVALENT_UNITS",
  "alternates": [{"value": "508", "unit": "mm"}],
  "evidence": [
    {"role": "LABEL", "reading": "q12"},
    {"role": "VALUE", "reading": "q13", "quote": "20 in (508 mm)"}
  ]
}
```

At `attributes[3]`, the same item expands to:

```json
{
  "origin": "EXTRACTED",
  "local_ref": "attr-3",
  "equipment_ref": "equipment-1",
  "association": "ASSERTED",
  "attribute_key": "enclosure_width",
  "raw_label": "Width",
  "raw_value": "20 in (508 mm)",
  "raw_unit": "in",
  "proposed_value": "20",
  "proposed_unit": "in",
  "qualifiers": [],
  "value_form": "EQUIVALENT_UNITS",
  "alternate_representations": [{"value": "508", "unit": "mm"}],
  "evidence": [
    {"kind": "READING", "role": "LABEL", "reading_ref": "q12", "quote": null},
    {"kind": "READING", "role": "VALUE", "reading_ref": "q13", "quote": "20 in (508 mm)"}
  ]
}
```

The internal validators still check the typed value, registry applicability, ownership, citations, and consistency of the reported representations before mapping. A quote-only citation has `role` and `quote`. A visual citation has `role`, `region`, and `reported_text`. Coordinate fractions retain their exact-decimal strings.

## Verification

- Fresh PostgreSQL 16 installation and additive upgrade of the isolated benchmark database through `6r_0014k_attribute_output` succeeded. The working application database was untouched.
- The focused backend suite passed **426 tests** with PostgreSQL integration enabled and zero skips. It covered contracts, provider requests, profiles, operation and retry identity, publication rollback, schema, telemetry, and the debugger.
- The restricted MinIO audit retrieval test passed **1 test**. The offline replay independently verified the seven retained response digests.
- The web app passed **368 tests** and its production build. The debugger passed **18 tests** and its TypeScript/Vite build. Ruff lint and format checks and `git diff --check` passed.

## Proposed live screening

Request separate authorization for the five existing pinned inputs, a cap of **10 Stage 2 calls**, **zero retries**, and a **US$6 ceiling**. Run one fresh control and one candidate per page, alternating which contract goes first. Match the recognition prerequisites, source hashes, `compact-page-v1` input, `core-catalog-v1` guidance, model, standard service tier, medium reasoning, and 16,384-token output limit. Both sides may use the isolated 180-second diagnostic timeout with matching execution deadlines. Report how many settle within 100 seconds. Production settings stay at their existing timeout and defaults.

Record available usage (including cached input, reasoning, and visible output), latency, assertion admission counts, publication, heartbeat and settlement outcomes, and cost per attempted page, published page, and correct checklist match. Use the 74-item checklist and inspect unsupported or redundant extras. Keep failed calls in completion and quality denominators and distinguish lease failures from provider errors. Compare coverage, ownership, source verification, evidence eligibility, mapping, and inference separately. Confirm that the four successful consolidated pages retain their 60/60 coverage and complete the paired Siemens evaluation. The byte savings are grounds for screening. Actual token savings, latency and quality determine whether to recommend promotion.

## Live screening results — November 24, 2026 Pacific

**Keep `legacy-v7` as the production default.** The compact contract cut visible output tokens by **54.2%** and median provider latency from **53.0 to 32.8 seconds**. Direct-extraction checklist coverage fell from **73/74 to 25/74**. The result fails the engineering coverage gate.

The authorized run used the isolated benchmark database with one fresh control and one compact attempt per page. It reused the exact recognized equipment, consolidated prompt foundation, catalog, compact V1 source text, and high-detail page image. The five control body digests also matched the corresponding D0 consolidated dispatch plans. The execution order alternated by page. Both variants used GPT-6 Luna, default service tier, medium reasoning, 16,384 maximum output tokens, and a 180-second diagnostic timeout. The existing 30-second lease and heartbeat cadence remained in effect. Production has a 100-second timeout.

The preflight verified each body digest, fixed the model and service tier, and reserved a conservative US$0.5332668 per dispatch based on full context, long-context rates, cache writes, and the regional premium. The actual ledger recorded ten distinct sends, zero retries, and US$5.332668 reserved against the US$6 limit. All ten returned HTTP 200 and published within 100 seconds of claim. The longest Stage 2 run took 86.88 seconds. Every terminal attempt recorded a heartbeat after its original claim and there were no lease-denial or heartbeat warnings. The first audit-store configuration check failed before dispatch. Using the host-accessible endpoint for the same private audit store resolved it. [GPT-6 Luna pricing and context limits](https://developers.openai.com/api/docs/models/gpt-6-luna)

### Paired measurements

In each line, results are control then compact. Token counts are input, cached input, reasoning, and visible output in that order. Times are provider call and total Stage 2 time.

- **Schneider native** · `191910ab` / `508769e9` · 56.07s / 56.51s → 32.77s / 33.29s · 16,647 / 0 / 2,569 / 7,055 → 16,746 / 0 / 3,272 / 1,517 tokens · **24/24 → 4/24**.
- **Schneider OCR** · `74dc9f7c` / `54a919b9` · 85.63s / 86.88s → 48.39s / 49.62s · 44,256 / 2,858 / 5,002 / 10,099 → 44,355 / 2,957 / 3,811 / 3,933 tokens · **24/24 → 0/24**.
- **Simson Maxwell** · `a42e9000` / `87693b99` · 47.79s / 48.56s → 32.13s / 32.85s · 19,264 / 2,858 / 1,754 / 7,273 → 19,363 / 2,957 / 1,821 / 3,957 tokens · **6/7 → 2/7**.
- **Siemens** · `59b1b268` / `f033dfd8` · 52.96s / 53.66s → 59.45s / 60.15s · 23,756 / 2,858 / 3,492 / 5,464 → 23,855 / 2,957 / 4,871 / 4,434 tokens · **14/14 → 14/14**. Both outcomes settled normally. The compact call used fewer visible tokens and more reasoning tokens.
- **REX** · `421511b5` / `b18e160d` · 29.70s / 33.33s → 17.78s / 21.37s · 23,440 / 2,858 / 2,070 / 2,624 → 23,539 / 2,957 / 1,552 / 1,049 tokens · **5/5 → 5/5**.

Across all five pairs, the median paired provider-time change was **−15.7 seconds**. Visible tokens fell from 32,515 to 14,890. Reasoning tokens rose from 14,887 to 15,327. The compact arm used 495 more input tokens in total with identical source text and images. The benchmarks received 191 versus 112 assertions, accepted 190 versus 95, quarantined one versus 17, and recorded zero overflow in either variant. Visible tokens per accepted assertion fell from 171.1 to 156.7. Visible tokens per correct checklist match rose from 445.4 to 595.6. The offline 22.9% byte saving measured re-encoding with equivalent content. The live generation savings also reflect differences in which claims the model returned and how it classified them.

Standard list-rate usage estimates total **US$0.06224**, split US$0.03541 control and US$0.02683 compact. All calls reported usage. Estimated cost per attempted and per published page was US$0.00708 control and US$0.00537 compact. Estimated cost per correct checklist match rose from US$0.000485 to US$0.001073. These estimates price reported input, cached input, and total output. Billing details for cache writes were unavailable. [GPT-6 Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna)

### Engineering quality and failure diagnosis

The four pages that matched 60/60 for D0 consolidated scored **59/60** for the fresh control and **11/60** for compact. Both Siemens arms scored 14/14. Checklist scoring requires a directly extracted proposal with the expected owner, registry key, source value, and unit. Accepted coverage, mapping, and evidence were scored separately. The counts of checklist matches with a mapped candidate were 40 control and 19 compact. Matches with resolved VALUE evidence were 25 and 15. Matches with `TEXT_MATCH` were 11 per arm. No checklist match showed a mapped conflict. The production diagnostics flagged zero invalid owner references and zero likely redundancies in either arm.

- **Schneider native.** All 12 compact assertions passed validation and belonged to the bus. The model omitted the ten breaker models and ten pole counts from the original response. The 12 compact citations were approximate visual regions. The control's 24 checklist matches also had zero resolved VALUE citations, so its coverage score still overstates the strength of its evidence. The paired voltage remained outside scalar normalization.
- **Schneider OCR.** The original compact body marked all 33 assertions `INFERRED`. Two were quarantined. Of the remaining 31, 14 reproduced values that the drawing directly reports. Ten breaker model assertions were absent. The accepted inference claims generated 30 VALUE citations that were ineligible for direct-value verification. These outcomes reflect the origin selected by the model, which the expansion preserves.
- **Simson Maxwell.** The compact original contained seven registry-linked and ten raw-unmapped assertions. Five registry-linked and all ten raw-unmapped assertions were quarantined with a `reading` reference-pattern violation. All 41 malformed values in `reading` matched literal source reading text. The required field content is the pinned ID. The other 72 submitted strings had valid reference syntax and did not match an exposed reading ID. The provider-facing schema accepted a string in that field. Its projection omits the local ID pattern and has no page-specific reading allowlist. Local validation and localization preserved the boundary. The valid two assertions published.
- **Siemens and REX.** The compact contract covered both checklists. On Siemens, six additional inferences included manufacturer and trip-unit descriptions. They remained labeled as inferred with unverified source-value support. The compact Siemens scalar voltage stayed unmapped against a compound source expression. On REX, both variants preserved the paired secondary voltage and impedance range as unmapped compound observations. The compact primary connection's exact source citation allowed that enum proposal to map.
- **Evidence.** Across published assertions, the control produced 350 resolved, 73 approximate visual, and 118 unresolved fragments. Compact produced 152 resolved, 15 approximate visual, and 39 unresolved. These totals reflect the different assertion counts. The targeted review covered checklist values, paired voltage and composite ratings, inference origins, and notable citation failures. A resolved fragment alone provides no proof of engineering correctness.

The restricted debugger retrieved all ten exact originals and verified their digests and byte lengths. Local replay reproduced all ten immutable stage results and the persisted candidates and evidence, including proposal values, mapping, ownership, source support, and the pinned page identity. No live response exceeded the raw-unmapped allowance. The two historical failure cases remain the evidence for duplicate-reference and overflow recovery.

The next correction should use the retained failures to make reading-ID citations unambiguous and check that the output instructions preserve direct extraction for explicitly reported source values. Preserve the local reference checks. A single sample per input and contract establishes the observed coverage regression in this screen. It does not isolate which prompt or schema change caused the omissions and origin shift. Review a targeted correction offline before requesting another paid comparison.
