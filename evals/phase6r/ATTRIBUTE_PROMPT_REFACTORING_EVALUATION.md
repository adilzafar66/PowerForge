# Phase 6R D0 attribute prompt evaluation

D0 implements the approved Stage 2 prompt and registry guidance split. New admissions can opt into either candidate with `EXTRACTION_ATTRIBUTE_PROMPT_VARIANT`. The default is `legacy`. Prompt selection and input modality are independent.

- **A — `legacy`.** Existing prompt and historical catalog, including the original notes and the separate `extraction_guidance` field.
- **B — `core-v1`.** Approved core and the selected source guide, with the same provider user input as A.
- **C — `core-catalog-v1`.** The same instructions as B, with consolidated notes and one optional `equipment_extraction_guidance` entry per eligible equipment type. The catalog omits `extraction_guidance` for every attribute.

The core owns response shape, association, inference, units, value forms and evidence roles. The applicable source guide explains the input layout and which citations are eligible. Registry notes own single-attribute definitions. Equipment guidance covers relationships and distinctions across fields. The registry API and equipment panel display the consolidated notes. Legacy extraction and prompt-only experiments reconstruct the earlier notes for the provider. Neither path changes the type system or the rules used for applicability, validation, and normalization.

## Offline comparison

All three variants used the same five pinned C2 sources with `compact-page-v1`, the same recognition results and images, GPT-6 Luna at medium effort, standard tier, and the same response schema and output ceiling. Offline checks confirmed that A and B had identical provider user input. C changed only the engineering catalog and its guidance metadata alongside the B prompt. All request bodies were serialized and hashed locally.

The assembled V1 Stage 2 instructions decreased from **10,437 to 8,162 UTF-8 bytes (21.8%)**. This includes the new source guide and required wire-compatibility wording. Table values are measured HTTP body bytes, including the image and JSON escaping. The last columns show the independently serialized attribute catalog plus the separate equipment guidance map in C. Those component counts do not include enclosing field names.

| Pinned input | A body | B body | C body | A/B attribute catalog | C attribute catalog + equipment guidance |
|---|---:|---:|---:|---:|---:|
| Schneider native | 533,530 | 531,273 | 528,542 | 12,187 | 8,758 + 813 |
| Schneider OCR | 635,517 | 633,260 | 630,529 | 12,187 | 8,758 + 813 |
| Simson Maxwell | 454,538 | 452,281 | 451,476 | 8,566 | 7,476 + 370 |
| Siemens | 460,487 | 458,230 | 455,499 | 12,187 | 8,758 + 813 |
| REX | 995,297 | 993,040 | 992,537 | 6,442 | 5,666 + 344 |

C removed all redundant guidance fields. On the two panel preparations and Siemens it replaced **36 per-attribute fields**, of which **21** were populated, with **two equipment entries**. On Simson Maxwell the corresponding counts were **29 fields**, **four** populated, and **one entry**. On REX they were **23 fields**, **two** populated, and **one entry**. Keeping the page image and source fixed limits the change in total request bytes. Provider token usage, engineering quality, and latency for B and C await live evaluation. A suitable local tokenizer was unavailable.

## Representative assembled content

The four examples below were selected from the actual offline variant C bodies. The benchmark uses the same core and compact V1 guide for each case. The quoted instruction excerpt is identical across the four requests.

> INFERRED assertions require a recognized equipment reference and ASSERTED or UNCERTAIN association.
> UNASSIGNED is available for extracted and raw-unmapped assertions. Proximity alone does not
> establish ownership. Do not create new equipment or modify the recognition result.
>
> Use READING with a supplied reading_ref, QUOTE with a verbatim page-local quotation, or VISUAL with
> an approximate upright image region. Row indices and internal source-token IDs are not reading refs.

The catalog excerpts show one actual registry row and an excerpt from the corresponding once-per-type guidance. The comparison CLI can emit the complete assembled instructions and catalogs. It omits the source page, image, and recognition text from its output.

- **Schneider panel.** `BUS.short_circuit_current_rating` has the note “Short-circuit current rating of the equipment or assembly, usually RMS symmetrical.” Equipment guidance begins “Associate assembly ratings and enclosure data with the bus assembly.”

- **Simson Maxwell generator.** `SYNCHRONOUS_GENERATOR.armature_resistance` has the note “Ra Also known as stator winding resistance”. Equipment guidance begins “Keep direct and quadrature axes, transient and subtransient quantities, and open-circuit and short-circuit time constants distinct.”

- **Siemens breaker schedule.** `LV_BREAKER.rating_plug` has the note “Current rating of the specified trip-unit plug.” Equipment guidance begins “Keep frame, sensor, rating-plug, trip and long-time pickup currents distinct.”

- **REX transformer.** `TWO_WINDING_TRANSFORMER.positive_sequence_impedance` has the note “Normal 2-winding impedance”. Equipment guidance begins “Keep primary and secondary values, nominal and tap voltages, base and fan-cooled capacity, and positive- and zero-sequence impedance distinct.”

## Pinning, compatibility, and verification

The existing manifests pin the rendered prompt hash. D0 also pins the core and source-guide hashes, the prompt variant, and the catalog and equipment-guidance identities. D0 requests use the complete-body digest for every source input, including compact V1. Legacy digests retain their previous semantics. Defaults changed after admission did not change the D0 retry's prompt, catalog, recognition prerequisite, or digest. The Stage 2 response schema and source-localization policy are the existing versions.

All **25 historical C2 modality bodies and dispatch digests** matched the frozen measurements. The restricted debugger retrieved and verified all **20 retained C2 originals**. Replay reproduced **18 publications** and both fatal admission outcomes. The extraction wheel contained the new core and all five source guides.

- **673 Python tests passed** across registry, API, requirements, units, prompt and wire contracts, provider transport, publication, and PostgreSQL integration. A fresh, disposable PostgreSQL cluster upgraded to the existing migration head. The combined test command selected integration tests explicitly and reported zero skips. A final registry, API, and profile rerun passed 70 tests, including the frozen legacy identity regression.
- **366 app frontend tests** and **17 debugger frontend tests** passed. TypeScript and both production builds passed.
- Ruff and the Git whitespace check passed. The historical audit retrieval exercised the local MinIO store with the restricted operator identity.

To reproduce the offline comparison against the authorized benchmark database and source store, run:

```sh
.venv/bin/python evals/phase6r/attribute_performance_baseline.py --compare-prompts \
  3b20893d-13db-42b9-a32e-1bd0202d3d8b \
  a70fe613-32e1-4019-8c39-f8562e5fe935 \
  da19da6d-4fd1-42f7-a391-5bd03a128dcf \
  6b5a35ad-9b9d-469e-a3b5-f34570849251 \
  900834f3-3349-4d29-b974-4abe23ec3950

```

Add `--include-guidance` to include assembled instructions and catalogs in the output. This command performs local reconstruction and verifies the original Stage 2 dispatch identity before comparing variants.

## Approved live protocol

The approved screen covered the same five pinned inputs and no more than **15 paid Stage 2 calls**, with **zero retries** and a **US$12 total ceiling**. Confirm pricing and enforce a conservative reservation before dispatch. Reuse the exact recognition results and the compact V1 source projection. Rotate A, B and C in the isolated benchmark. Pin GPT-6 Luna at medium effort, standard tier, the existing schema and the 16,384-token output ceiling. Use the same 180-second diagnostic timeout as C2 and report publication within the 100-second production window separately.

Compare B against A to isolate the prompt. Compare C against B to isolate the catalog. Report input, cached, reasoning and visible output tokens, provider and attempt time, coverage, correct ownership, unsupported assertions, inference correctness, evidence and mapping quality, and validation failures. Include failed pages in the denominators. Review critical value errors and unsupported inferences before any recommendation to change defaults.

## D0 live comparison

On November 24, 2026 Pacific, the authorized comparison reused the five C2 source snapshots and their exact pinned recognition results. The disposable benchmark admitted the extraction operations and replayed recognition locally. It dispatched the Stage 2 requests sequentially in rotated order, with one send per attempt and a 180-second diagnostic timeout. The pre-dispatch check matched every HTTP body against the offline comparison, including the common high-detail image, standard service tier, response schema, medium reasoning, and 16,384 output-token ceiling.

The reservation used the full model context, the long-context input and output rates, cache writes, and a regional premium. It allowed a conservative US$7.999002 for 15 calls under the authorized US$12 cap. Usage estimates use reported input, cached input, and total output tokens and standard list rates. [GPT-6 Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna)

The 74-item checklist per variant scores accepted extracted proposals for the specified owner, registry key, source value, and unit. Failures count in the denominator. Mapping and the presence of resolved VALUE evidence are reported separately. Spot checks review inferences and unsupported claims outside the checklist. A single response per page and variant gives screening evidence.

The consolidated Siemens call reached OpenAI and the client observed HTTP 200. The attempt lease expired before settlement and the coordinator recorded `EXTRACTION_PROVIDER_OUTCOME_UNKNOWN`. The database heartbeat had remained at the claim timestamp. The cause of the missed heartbeat was unconfirmed. The run has no committed response audit, candidate publication, usage, or provider latency. The comparison resumed only the four unsent attempt IDs. The recorded dispatch and its full conservative reservation count toward the authorized cap.

### Performance and coverage

All **15 authorized calls** were sent once. **12 published**, including three partially validated attempts. All 12 published within 100 seconds from Stage 2 claim through settlement. Fourteen calls returned usage and their estimated spend was **US$0.0916**. The Siemens lease-loss call's cost is unknown. There were zero observed provider timeouts. Stage 2 time excludes queue wait. Per-preset medians use published attempts and cost per published page divides available usage cost, including failed calls with usage, by the published-page count.

| Input | Preset | Outcome | Provider s | Stage 2 s | Body bytes | Input | Cached | Reasoning | Visible | Cost | Checklist |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Schneider native | A · Legacy | Incomplete | 89.59 | 89.93 | 533,530 | 17,700 | 0 | 6,832 | 9,552 | $0.0100 | 0/24 |
| Schneider native | B · Core | Completed | 62.31 | 62.76 | 531,273 | 17,188 | 0 | 3,052 | 7,656 | $0.0071 | 24/24 |
| Schneider native | C · Consolidated | Completed | 76.09 | 76.47 | 528,542 | 16,647 | 2,858 | 3,501 | 10,293 | $0.0083 | 24/24 |
| Schneider OCR | A · Legacy | Completed | 53.70 | 54.88 | 635,517 | 45,309 | 3,370 | 3,958 | 5,438 | $0.0089 | 14/24 |
| Schneider OCR | B · Core | Completed | 52.15 | 53.36 | 633,260 | 44,797 | 2,858 | 4,347 | 3,853 | $0.0083 | 14/24 |
| Schneider OCR | C · Consolidated | Completed | 69.74 | 71.00 | 630,529 | 44,256 | 2,858 | 4,692 | 7,553 | $0.0103 | 24/24 |
| Simson Maxwell | A · Legacy | Partial | 32.13 | 32.84 | 454,538 | 19,965 | 3,370 | 1,855 | 4,091 | $0.0047 | 6/7 |
| Simson Maxwell | B · Core | Partial | 22.17 | 22.86 | 452,281 | 19,453 | 2,858 | 1,284 | 2,481 | $0.0036 | 5/7 |
| Simson Maxwell | C · Consolidated | Completed | 48.23 | 48.93 | 451,476 | 19,264 | 2,858 | 2,434 | 6,156 | $0.0060 | 7/7 |
| Siemens | A · Legacy | Duplicate reference | 33.08 | 33.67 | 460,487 | 24,809 | 3,370 | 1,833 | 5,373 | $0.0058 | 0/14 |
| Siemens | B · Core | Partial | 41.68 | 42.32 | 458,230 | 24,297 | 0 | 3,678 | 2,792 | $0.0057 | 4/14 |
| Siemens | C · Consolidated | Lease lost | — | — | 455,499 | — | — | — | — | — | 0/14 |
| REX | A · Legacy | Completed | 29.74 | 33.27 | 995,297 | 24,074 | 0 | 2,296 | 2,624 | $0.0049 | 5/5 |
| REX | B · Core | Completed | 17.59 | 21.10 | 993,040 | 23,562 | 2,858 | 1,172 | 1,361 | $0.0034 | 5/5 |
| REX | C · Consolidated | Completed | 32.75 | 36.31 | 992,537 | 23,440 | 2,858 | 2,588 | 2,905 | $0.0048 | 5/5 |

| Preset | Published | ≤100 s | >100 through 180 s | Checklist | Median provider s | Cost per published page | Resolved / visual / unresolved | Mapped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A · Legacy | 3/5 | 3 | 0 | 25/74 | 32.13 | $0.0114 | 203 / 38 / 5 | 12 |
| B · Core | 5/5 | 5 | 0 | 52/74 | 41.68 | $0.0056 | 135 / 58 / 58 | 31 |
| C · Consolidated | 4/5 | 4 | 0 | 60/74 | 58.99 | $0.0073 | 203 / 97 / 4 | 29 |

B used **129,297 input tokens** across five calls versus A's **131,857** (**1.9% lower**). For the four inputs with recorded usage for both B and C, those totals were **105,000** and **103,607** (**1.3% lower**). The version with consolidated guidance returned more assertions on three of those four pages. Median paired provider time increased by **16.38 seconds** from B to C, while coverage rose from **48/60 to 60/60**. Across the three pages published by both A and B, B was faster in each pair and matched **24/36** against A's **25/36**. These paired comparisons use only pages with both publications. The main checklist table includes the failed pages.

### Engineering and evidence review

| Preset | Accepted extracted | Accepted inferred | Checklist matches with resolved VALUE evidence | Checklist matches mapped |
|---|---:|---:|---:|---:|
| A · Legacy | 72 | 1 | 13/25 | 8/25 |
| B · Core | 105 | 1 | 16/52 | 18/52 |
| C · Consolidated | 138 | 0 | 14/60 | 23/60 |

A resolved fragment can identify a source occurrence without establishing every part of the engineering claim. Both manufacturer inferences used contextual document branding. Those proposals were plausible for their recorded owners. The checklist gives inferences no credit and the two examples cannot establish inference precision.

- **Schneider native.** A hit the 16,384-token output ceiling. B and C matched all 24 facts, with eight of those matches mapped per candidate and zero resolved VALUE citations. B assigned some generic schedule ampere values to trip ratings. C assigned some to frame ratings. The source header gives an ampere/pole rating and does not establish either more specific meaning. Those proposals stayed invalid or unmapped in the reviewed rows.
- **Schneider OCR.** C recovered the ten breaker models omitted by A and B. C also proposed a scalar from the paired 208Y/120 V expression on both Schneider preparations. The validator rejected that scalar. Matching the breaker checklist does not capture that voltage error.
- **Simson Maxwell.** C recovered the armature-resistance row that A and B missed, and the open-circuit field time constant that B missed. The armature resistance was preserved with its source conditions and remained unmapped.
- **Siemens.** A repeated a local assertion reference at `attributes[25].local_ref` and failed admission. B published four bus checklist items. It missed all ten breaker checks and had two quarantined assertions. C had an expired lease, so its content and quality could not be scored.
- **REX.** All three matched the five checklist items. The two D0 candidates preserved the paired secondary voltage and impedance range. Their accepted 600 V primary proposals remained unmapped under the existing source-expression policy. That difference matters when comparing usable mapped output.

### Audit replay and decision

The debugger verified **13 retained originals** and reproduced **all 12 immutable publications** plus the Siemens legacy duplicate-reference rejection. Schneider native legacy and Siemens consolidated had no committed original. The experimental region matcher found **three** matches on Schneider OCR with C. Two referenced the same composite `200/3` reading for different assertions. The third localized the equipment model text `JD`. The recovery locates the literal text only. It did not establish that the composite expression describes a trip rating or that `JD` independently establishes a breaker class. The replay recorded 142 unmatched literal/region pairs, 47 overlapping-equipment outcomes and one insufficient-support result. Production evidence was not changed.

**Keep A as the default and retain both D0 variants for evaluation.** B published every page and was faster on the three jointly published pages compared with A, but missed ten Siemens breaker checks. C had the strongest coverage on the four comparable pages. It took longer than B in every paired call, produced sparse resolved VALUE evidence relative to its checklist score, and made unsupported scalar-voltage proposals the validator rejected. A paired Siemens comparison with stable lease telemetry and repeat observations on Schneider are needed before considering promotion. Preserve the output-ceiling and duplicate-reference findings for the output contract milestone.
