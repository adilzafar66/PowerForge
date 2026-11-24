# Stage 2 source modality evaluation

## Offline decision

C2.1–C2.7 use the five pinned Milestone C inputs. All 25 projections reconstructed offline. Every readable page retained every original reading ID, literal, alternate transcription, issue, and available individual box. Schneider OCR's page projection decreased from 103,919 to 51,944 bytes. The full hybrid benchmark body decreased from 635,517 to 572,748 bytes (9.9%). Text-only reached 95,526 bytes by omitting the image. Model comprehension, recall, input tokens, output tokens, cost and latency for these three new configurations await separately authorized screening. V1 remains the default.

## Source inventory and readable contract

- Engineering extraction requires literal source wording, units, qualifiers and competing transcriptions. The registry catalog supplies exact keys, applicability, definitions, types and supported units. Recognition supplies equipment descriptions, tags, qualifications, occurrence IDs and previously reported citations. The same two prerequisites are included across configurations. Image-only can therefore contain source-derived **recognition text, quotations and reading IDs**. Embedded IDs do not grant Stage 2 reading-citation eligibility.
- Association and evidence selection use occurrence IDs, page geometry, reliable order, table position, headers and captions. Readable blocks identify the source modality once. Each line contains directly addressable tuples of reading ID, literal text, and optional exact normalized [x, y, width, height]. A missing box means coordinates were unavailable. Consecutive clean readings can share a line only along unbranched pinned baseline edges of the same modality and within the same cell. Repeated identifiers and ratings retain distinct occurrences. All strings are untrusted data.
- Confirmed table rows contain cells in column order with their readings inline. Explicit spans, header IDs, caption reading IDs, and structural/header bases preserve what the source processing established. Uncertain cells point to separately presented occurrences. Unresolved partitions expose their region and basis with free readings. Source-supported order links that the lines do not express remain explicit. No new table or line is inferred from proximity.
- Conflicts within one reading appear in sparse notes linking alternate literal transcriptions to their modality. Overlap links identify separate source participants by reading ID and carry agreement, conflict or ambiguity. Damage, missing coordinates, and structural limits remain visible.
- V1 and V2 also transmit preparation identities, internal artifact metadata and geometry witnesses. Readable inputs omit those fields, detailed boundary support and indexed witness dictionaries. Original artifacts, exact transforms, upstream identities and immutable audit records continue to be verified internally.

Two excerpts from the actual Schneider OCR input follow. The first contains the label and value as three independently addressable occurrences. The second preserves the OCR spelling of the short-circuit rating. Only the surrounding blocks and unrelated lines have been omitted.

```json
{"source":"OCR","lines":[[
  ["q308","System",["0.562745098039","0.584545454545","0.049803921569","0.010606060607"]],
  ["q309","Ampacity:",["0.623529411765","0.584545454545","0.067450980392","0.010606060607"]],
  ["q310","800A",["0.703137254902","0.584545454545","0.035294117647","0.008181818182"]]
]]}
```

```json
{"source":"OCR","lines":[[
  ["q314","SOkA",["0.562745098039","0.600909090909","0.033333333334","0.008181818182"]],
  ["q315","SYMS.",["0.607058823529","0.600909090909","0.040000000000","0.008181818182"]],
  ["q316","SCCR",["0.658823529412","0.600909090909","0.036470588235","0.008181818182"]]
]]}
```

## Measured requests

Each row gives UTF-8 bytes. **Readings** includes the serialized reading section, including individual coordinates and modality. **Layout** includes the other page metadata, with inline cell readings excluded. Independently serialized sections include their own JSON delimiters. **Image** covers Base64 characters. **Body** includes the high-detail image where selected, escaped input, applicable instructions, unchanged output schema, medium effort and explicit standard service tier. The 25-byte explicit tier field accounts for the difference from the older V1/V2 offline comparison. **Coverage** counts exposed / internally available occurrences. The final column is the first 12 hex digits of the canonical provider projection SHA-256. The tool emits full digests including the comparison body identity.

| Input | Preset | Coverage | Readings | Layout | Registry | Recognition | Image | Body | Projection |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Schneider native | V1 | 123/123 | 12,839 | 4,693 | 12,187 | 4,669 | 477,164 | 533,530 | `78b47500c708` |
| Schneider native | V2 | 123/123 | 12,167 | 4,706 | 12,187 | 4,669 | 477,164 | 533,430 | `7bdbba75caa1` |
| Schneider native | Hybrid | 123/123 | 10,741 | 60 | 12,187 | 4,669 | 477,164 | 525,451 | `d786774368b2` |
| Schneider native | Image | 0/123 | 0 | 0 | 12,187 | 4,669 | 477,164 | 512,858 | `04149417d3a0` |
| Schneider native | Text | 123/123 | 10,741 | 60 | 12,187 | 4,669 | 0 | 48,229 | `3f92e53b9c85` |
| Schneider OCR | V1 | 445/445 | 45,645 | 58,262 | 12,187 | 4,479 | 477,164 | 635,517 | `4f091f0e386a` |
| Schneider OCR | V2 | 445/445 | 45,717 | 20,220 | 12,187 | 4,479 | 477,164 | 590,092 | `3328e91a92c5` |
| Schneider OCR | Hybrid | 445/445 | 39,143 | 12,791 | 12,187 | 4,479 | 477,164 | 572,748 | `6f35e8483ca8` |
| Schneider OCR | Image | 0/445 | 0 | 0 | 12,187 | 4,479 | 477,164 | 512,648 | `fa870676b3a7` |
| Schneider OCR | Text | 445/445 | 39,143 | 12,791 | 12,187 | 4,479 | 0 | 95,526 | `e1b83fb4d857` |
| Simson Maxwell | V1 | 207/207 | 21,638 | 5,979 | 8,566 | 519 | 395,312 | 454,538 | `04b79122cf58` |
| Simson Maxwell | V2 | 207/207 | 21,209 | 5,992 | 8,566 | 519 | 395,312 | 454,735 | `475974a44cd4` |
| Simson Maxwell | Hybrid | 207/207 | 18,202 | 51 | 8,566 | 519 | 395,312 | 443,424 | `89274db550e0` |
| Simson Maxwell | Image | 0/207 | 0 | 0 | 8,566 | 519 | 395,312 | 422,371 | `1383f8510ba7` |
| Simson Maxwell | Text | 207/207 | 18,202 | 51 | 8,566 | 519 | 0 | 48,054 | `5059e8b6677a` |
| Siemens | V1 | 252/252 | 26,441 | 8,985 | 12,187 | 5,292 | 382,648 | 460,487 | `882950f66069` |
| Siemens | V2 | 252/252 | 25,478 | 8,615 | 12,187 | 5,292 | 382,648 | 459,547 | `e0a7a30ec86d` |
| Siemens | Hybrid | 252/252 | 22,226 | 464 | 12,187 | 5,292 | 382,648 | 445,419 | `4c539d0c5823` |
| Siemens | Image | 0/252 | 0 | 0 | 12,187 | 5,292 | 382,648 | 419,307 | `d99e426c8bc3` |
| Siemens | Text | 252/252 | 22,226 | 464 | 12,187 | 5,292 | 0 | 62,713 | `782953f95ff4` |
| REX | V1 | 304/304 | 31,536 | 7,074 | 6,442 | 1,033 | 925,272 | 995,297 | `759fc6dd8a82` |
| REX | V2 | 304/304 | 30,749 | 7,087 | 6,442 | 1,033 | 925,272 | 995,048 | `91149ab2edcc` |
| REX | Hybrid | 304/304 | 26,577 | 57 | 6,442 | 1,033 | 925,272 | 981,173 | `a24ca2f2b707` |
| REX | Image | 0/304 | 0 | 0 | 6,442 | 1,033 | 925,272 | 950,565 | `4f4238536e7e` |
| REX | Text | 304/304 | 26,577 | 57 | 6,442 | 1,033 | 0 | 55,843 | `4d82e8cdb664` |

The Schneider OCR preferred literal text alone occupies 3,349 bytes as a JSON string list. The available exact coordinates occupy 31,151 bytes across all reading-bearing configurations. They materially affect bytes but distinguish closely spaced occurrences. Other selected Schneider OCR categories are below. Nested sections overlap and their byte counts should not be added to the full request.

| Category (bytes) | V1 | V2 | Readable hybrid |
|---|---:|---:|---:|
| Structured user text | 120,820 | 82,850 | 68,689 |
| Overlaps | 20,914 | 2,923 | 3,647 |
| Explicit order links | 5,951 | 5,951 | 2,673 |
| Reading witnesses | 29,466 | 3,127 | 0 |
| Support dictionary | 0 | 6,277 | 0 |
| Sparse notes | 0 | 0 | 6,381 |
| Top-level internal page metadata | 648 | 648 | 0 |
| Table structure | 2 | 2 | 0 |
| Instructions | 10,437 | 11,187 | 10,225 |
| Output schema | 6,341 | 6,341 | 6,341 |

There was no suitable local model tokenizer installed. The previously observed 45,309 V1 and 37,310 V2 Schneider OCR input tokens are historical provider measurements. Image byte savings do not translate directly to image-token savings. The 25,000-token goal and normal-timeout completion remain open.

## Configuration, execution and evidence

Use `EXTRACTION_ATTRIBUTE_INPUT_VERSION` on the API and worker. The admitted run pins its setting. The choices are `compact-page-v1` (default), `compact-page-v2`, `readable-hybrid-v1`, `image-only-v1`, and `readable-text-v1`. Hybrid and text use the identical `readable-page-v1` serializer. Both image-bearing experimental configurations send the original high-detail image. Text-only verifies the pinned image internally and omits the entire image content part from transport. With eligible equipment but no nonblank readable text, text-only records `NO_READABLE_SOURCE_TEXT` before provider dispatch. OCR preparation is selected independently. Stage 1 still receives its original input.

New profiles pin prompt bundle `phase-6r-source-modalities-v1`, the projection, citation policy `stage2-source-eligibility-v1`, and digest policy `responses-body-v1`. The digest binds the canonical complete provider JSON body including image, model, instructions, schema, reasoning, token limit and service tier. The unit-specific request object, correlation header, recognition hash, pinned artifacts, lease checks and transactional audit guard bind otherwise identical requests to their actual attempts. Historical profiles retain their original digest algorithm. The telemetry migration accepts v1 and v2 on the existing bounded terminal Stage 2 record. The debugger shows executed OCR alongside the modalities actually sent. Historical unavailable measurements remain unknown.

Image-only READING citations become unresolved even when their IDs exist internally. A literal QUOTE may still resolve uniquely against the pinned page text. Text-only VISUAL citations become unresolved. A text-only quotation must both resolve against a source artifact and be supported by exposed readings within one established sequence. Unsupported fragments remain visible with a reason. Eligible sibling citations and assertions still proceed through publication. Hidden evidence cannot verify values, units or mapping. The registry, assertion schema, normalization, and evidence database constraints are unchanged.

## Replay with retained responses

The `region-literal-replay-v1` experiment uses a VISUAL citation's own literal text, immutable page text, full token spans and source-derived boxes. It requires a unique occurrence wholly inside the reported region, supported order, and unambiguous transcriptions. The experimental region must cover at most one quarter of the page to count as independent spatial support. A whole-page box around a unique literal cannot pass. It preserves the original visual fragment and returns derived refs, offsets, coordinates and method only to offline evaluation. It does not write candidates or evidence. Existing page/attempt search budgets, a 64-hit cap per literal and at most 32 token regions bound the search.

| Historical comparison | Attempts | Verified retained originals | Fatal on readmission | Missing after timeout | No literal match | Overlapping equipment | Ineligible visual/value | Additional resolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Milestone B | 15 | 14 | 4 | 1 | 71 | 23 | 0 | 0 |
| Milestone C | 10 | 9 | 1 | 1 | 200 | 20 | 19 | 0 |

The last four columns count citations. The retained outputs do not establish a real-document improvement from regional matching. Controlled fixtures verify a positive match and abstention for repeated, unsupported or overlapping occurrences. Recognition references and lexical localization alone cannot establish ownership or engineering meaning.

## Reproduction

Against the authorized benchmark database and artifact storage, run from the repository root. The first three attempts verify their original dispatch digests. Siemens and REX require current-wire reprojection of verified older sources and their exact historical recognition results. No request is sent by these commands.

```sh
.venv/bin/python evals/phase6r/attribute_performance_baseline.py --compare-modalities \
  313159b7-91cd-4c08-9afe-ca1d38a94764 5635845e-11f8-4216-a881-f6793791c274 \
  81f39815-0a5a-4019-bdb2-831fd3722010
.venv/bin/python evals/phase6r/attribute_performance_baseline.py --compare-modalities --reproject \
  e3db2b1d-3948-490c-be80-c4fd60115887 b6e5b09e-3816-4ca9-a31b-69ecf8095283
.venv/bin/python evals/phase6r/region_replay.py RETAINED_STAGE_2_ATTEMPT_UUID
```

The replay command uses the source database and artifact settings plus the existing operator audit-reader environment, journals each retrieval, enforces expiry and digest verification, and emits content-free aggregate outcomes. Run it with the retained C2 attempt IDs after a separately approved comparison.

## Proposed C2.8 screening procedure (pending approval)

1. Confirm authorization for the same five source snapshots, including both Schneider preparations. Use isolated benchmark settings and a disposable run database. Admit real Stage 2 work through the existing consent, audit and budget controls. Replay the same verified Stage 1 result locally. Check the projected catalog and recognition identity for each pair.
2. Propose **at most 20 paid Stage 2 calls, zero retries and US$12 maximum total spend**. Confirm current pricing, enforce a conservative pre-call spend reservation including outstanding unknown outcomes, and stop when the remaining budget cannot cover the next call. V2 already has historical measurements. A fresh V2 call needs separate approval.
3. Rotate the four configurations across the five pages. Fix model GPT-6 Luna, medium reasoning, standard tier, output schema, token ceiling of 16,384, and admission policy. Pin `EXTRACTION_TIMEOUT_SECONDS=180` on isolated admissions and on the benchmark SDK client. The earlier private harness explicitly checked for 100 seconds and created its own SDK client with that timeout. Update both in any future benchmark runner and remove 100-second outer waits. Supply the standard tier once and check actual HTTP body identity before dispatch. Keep production at 100 seconds.
4. The SDK uses the pinned per-request timeout. The coordinator deadline runs from claim through settlement at timeout + 15 seconds (195 seconds here). The default 30-second lease has a heartbeat every 10 seconds capped by that deadline. The extraction task's soft/hard limits are 330/345 seconds. Check source loading and publication headroom plus queue allowance in benchmark monitoring. A lease expiry, cancellation, or SDK timeout is a separate outcome. A diagnostic timeout is a ceiling, not a promised 180 seconds of provider time if local work exhausts the attempt window.
5. Report per page and preset provider-only and Stage 2 wall time, completions within 100 seconds, completions after 100 through 180 seconds, timeouts, fatal or partially validated responses, usage (input/cached/reasoning/visible output), body size, and cost per success using measured usage and pinned pricing. Include all attempts and keep unknown usage explicit. Score checklist coverage and owner/type/value/unit correctness separately for extracted and inferred assertions. Identify critical errors, exact unit spelling differences, publication outcomes, resolved vs visual/unresolved evidence and correct occurrence localization. Replay the same original outputs under both localizers.
6. Review the results before any promotion. Speed or smaller bodies alone do not establish quality. Require paired repetitions with separate authorization if the screening results are inconclusive.

Historical context and engineering checklist methodology are recorded in [Milestone B](ATTRIBUTE_REASONING_EVALUATION.md) and [Milestone C](ATTRIBUTE_CONTEXT_EVALUATION.md).

## Verification results

The combined offline suite passed **395 tests** with six dependency deprecation warnings and zero skips on a private host-local PostgreSQL 16 cluster. An empty database upgraded through `6r_0014j_source_modality`. The cluster was stopped after verification. The suite includes the 180-second SDK mock, the 195-second coordinator deadline and lease heartbeat, all five admission/dispatch/audit paths, publication, historical records, and debugger backend tests.

```sh
PYTHONPATH=tools/extraction-debugger RUN_INTEGRATION=1 .venv/bin/pytest -q \
  tests/test_extraction_compact_context.py tests/test_extraction_stage_contracts.py \
  tests/test_extraction_profile.py tests/test_extraction_publication.py \
  tests/test_extraction_performance.py tests/test_openai_extraction.py \
  tests/test_workers.py tests/test_enrichment_native.py tools/extraction-debugger/tests/test_api.py \
  tests/test_extraction_operations.py tests/test_extraction_debugger_integration.py \
  tests/test_extraction_schema.py -rs
```

The optional MinIO retrieval test skipped in the unconfigured unit run. With the retained benchmark fixture selected and the restricted operator credentials configured, it **passed (1/1)**. The regional-area and hidden-reading tests also passed after the final replay guard. The debugger frontend passed **17 tests**, followed by TypeScript and the Vite production build. Ruff lint, format checks on changed Python files, and the Git whitespace check passed.

Two intermediate runs on the Docker PostgreSQL instance had intermittent failures in synchronous source-enrichment claims and one failure during settlement of an intentionally broken audit test. The failing fixture cases varied across runs. Inspection showed inconsistent database wall-clock ordering for a cancelled test unit. The exact cause was not established. Both the 51-test integration suite and the combined run passed on the independent host PostgreSQL cluster with the same migration and lease/database protections.

## C2.8 live screening

On November 24, 2026 Pacific, the approved benchmark reused the five source snapshots and replayed their pinned equipment recognition locally. It ran Stage 2 sequentially in rotated preset order through PowerForge's operation admission and worker execution, in the disposable benchmark database. Each actual HTTP body matched the offline canonical digest before transmission. The SDK sent standard-tier GPT-6 Luna requests at medium effort with the same schema, 16,384 output-token cap, and 180-second timeout. The transport allowed one send per attempt and zero retries. The maximum reservation was US$10.665336 for 20 calls under the US$12 ceiling. The reservation includes long-context rates, cache writes and a regional premium. The cost estimates below use returned token usage and standard list rates, excluding any cache-write charges absent from usage. [GPT-6 Luna pricing and context limit](https://developers.openai.com/api/docs/models/gpt-6-luna)

The validation compares accepted extracted proposals against the frozen 74-item checklist for each preset. Each item checks the registry key, owner, source magnitude and proposal unit. Inferred values receive no checklist credit. A checklist match can still be unmapped or lack source verification. Source spot-checks separately review critical ratings, equipment association, and evidence placement. The checklist is targeted and cannot establish overall precision or validate every inference.

All 20 paid calls returned usage. Eighteen published, including four partially validated attempts. Seventeen published after provider calls that completed within 100 seconds. The remaining publication took 102.15 seconds at the provider. **Total estimated cost was US$0.1065**. No provider call timed out. The Stage 2 time is claim through settlement and excludes queue wait. The cost-per-page column includes the cost of failed calls in each preset. Median provider time uses published attempts. Body sizes are the dispatched HTTP bytes, including the explicit standard tier for V1.

| Input | Preset | Outcome | Provider s | Stage 2 s | Body bytes | Input | Cached | Reasoning | Visible | Cost | Checklist |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Schneider native | V1 | Too long | 65.88 | 66.22 | 533,530 | 17,700 | 0 | 1,949 | 9,967 | $0.0077 | 0/24 |
| Schneider native | Hybrid | Completed | 31.65 | 32.02 | 525,451 | 14,924 | 0 | 2,501 | 1,981 | $0.0037 | 4/24 |
| Schneider native | Image | Partial | 102.15 | 102.55 | 512,858 | 10,362 | 0 | 3,579 | 10,627 | $0.0081 | 24/24 |
| Schneider native | Text | Completed | 54.04 | 54.41 | 48,229 | 12,039 | 0 | 3,431 | 4,101 | $0.0050 | 20/24 |
| Schneider OCR | V1 | Completed | 64.70 | 65.91 | 635,517 | 45,309 | 3,370 | 3,428 | 7,973 | $0.0099 | 14/24 |
| Schneider OCR | Hybrid | Completed | 63.05 | 64.28 | 572,748 | 31,406 | 3,325 | 3,624 | 7,172 | $0.0082 | 14/24 |
| Schneider OCR | Image | Completed | 55.21 | 56.44 | 512,648 | 10,268 | 3,277 | 2,196 | 4,672 | $0.0042 | 14/24 |
| Schneider OCR | Text | Completed | 45.24 | 46.42 | 95,526 | 28,521 | 3,331 | 3,947 | 1,533 | $0.0053 | 3/24 |
| Simson Maxwell | V1 | Partial | 34.21 | 34.93 | 454,538 | 19,965 | 3,370 | 1,757 | 3,896 | $0.0045 | 7/7 |
| Simson Maxwell | Hybrid | Completed | 48.05 | 48.80 | 443,424 | 16,233 | 3,325 | 2,122 | 6,651 | $0.0057 | 7/7 |
| Simson Maxwell | Image | Completed | 28.77 | 29.51 | 422,371 | 8,526 | 3,277 | 1,517 | 1,944 | $0.0023 | 7/7 |
| Simson Maxwell | Text | Partial | 40.43 | 41.17 | 48,054 | 13,264 | 3,331 | 2,756 | 4,118 | $0.0045 | 6/7 |
| Siemens | V1 | Completed | 44.44 | 45.10 | 460,487 | 24,809 | 3,370 | 2,575 | 5,037 | $0.0060 | 14/14 |
| Siemens | Hybrid | Duplicate reference | 62.08 | 62.63 | 445,419 | 19,868 | 3,325 | 2,808 | 8,410 | $0.0073 | 0/14 |
| Siemens | Image | Completed | 59.33 | 60.00 | 419,307 | 10,396 | 3,277 | 3,075 | 4,273 | $0.0044 | 14/14 |
| Siemens | Text | Partial | 51.51 | 52.19 | 62,713 | 16,983 | 3,331 | 2,881 | 5,542 | $0.0056 | 14/14 |
| REX | V1 | Completed | 25.57 | 29.13 | 995,297 | 24,074 | 3,370 | 1,514 | 2,379 | $0.0041 | 5/5 |
| REX | Hybrid | Completed | 26.87 | 30.48 | 981,173 | 19,303 | 3,325 | 1,552 | 2,791 | $0.0038 | 5/5 |
| REX | Image | Completed | 30.27 | 33.90 | 950,565 | 8,066 | 3,277 | 1,080 | 2,347 | $0.0022 | 4/5 |
| REX | Text | Completed | 35.53 | 39.17 | 55,843 | 16,418 | 3,331 | 2,776 | 2,506 | $0.0040 | 5/5 |

| Preset | Published | ≤100 s | >100 through 180 s | Checklist | Median provider s | Cost per published page | Resolved / visual / unresolved | Mapped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V1 | 4/5 | 4 | 0 | 40/74 | 39.33 | $0.0081 | 306 / 63 / 6 | 41 |
| Hybrid | 4/5 | 4 | 0 | 30/74 | 39.85 | $0.0072 | 241 / 48 / 8 | 25 |
| Image | 5/5 | 4 | 1 | 63/74 | 55.21 | $0.0042 | 144 / 99 / 103 | 66 |
| Text | 5/5 | 5 | 0 | 48/74 | 45.24 | $0.0049 | 291 / 0 / 74 | 49 |

### Engineering and evidence review

- **Schneider native.** V1 returned more than the allowed 16 raw-unmapped assertions, so admission rejected the entire response. Hybrid omitted the ten breaker models and ten pole counts. Image-only recovered all 24 checklist facts, with nine invalid assertions quarantined. Text-only returned all 20 breaker model/pole-count proposals correctly, drawing on the recognition context, but **zero** had resolved VALUE evidence. It missed the four bus checks. Those text-only breaker proposals scored for their correct values and owners, even though their citations remained unresolved.
- **Schneider OCR.** Hybrid reduced input tokens by 30.7% and provider time by 1.65 seconds relative to the matched V1 control. V1, hybrid and image-only all omitted the ten breaker models. Each proposed all ten correct pole counts, but nine relied on composite schedule expressions and failed deterministic source-value validation. Text-only omitted the breakers and retained the pinned OCR reading of the short-circuit rating without a numerical proposal. The raster shows 30 kA. None of the new presets equaled V2's historical 24/24 on this page. The V2 result came from an earlier, separate run.
- **Simson Maxwell.** V1, hybrid and image-only matched all seven checks. Text-only omitted armature resistance. Spot checks found the open-circuit field time constant and retained three corresponding source roles in image-only through literal quotation. The three exact resistance proposals in the fully matching runs remained qualified and unmapped.
- **Siemens.** Hybrid repeated an assertion reference and failed globally at `attributes[1].local_ref`. The other presets matched all 14 items, including distinguishing the main breaker's model and rating plug from the branch breaker models. Image-only proposed equipment-specific classifications as inferences, including the WL power breaker and the molded-case branch breakers. Their model context makes these plausible, but the checklist does not independently establish each inferred classification.
- **REX.** Image-only retained the correct 350 apparent-power magnitude but omitted the proposed kVA unit. The source identifies kVA on that row. The other presets matched all five checks. Spot checks found the 208/120 V secondary and 4.0–6.0% impedance retained as compound expressions and kept out of scalar normalization.

| Preset | Accepted extracted | Accepted inferred | Checklist matches with any resolved VALUE citation | Checklist matches mapped |
|---|---:|---:|---:|---:|
| V1 | 100 | 11 | 25/40 | 23/40 |
| Hybrid | 83 | 13 | 21/30 | 10/30 |
| Image | 152 | 11 | 30/63 | 37/63 |
| Text | 116 | 0 | 22/48 | 43/48 |

A resolved VALUE citation counts the presence of a localized source fragment. Repetitions and compound expressions still require review for the correct source occurrence and claim support. Screening used the same recognition prerequisite for each page's four attempts. The native and OCR Schneider preparations have separate recognition snapshots from the previous benchmark. OCR-vs-native differences therefore include recognition context and cannot be attributed to OCR alone.

### Audit replay and release decision

The restricted Extraction Debugger retrieved all 20 exact retained outputs. Offline replay reproduced all 18 immutable publications, including their candidate ordering, ownership, and evidence fragments, and reproduced both fatal validation outcomes. The regional replay produced zero additional matches. It recorded 165 unmatched literal/region pairs, 45 overlapping-equipment outcomes and two ineligible visual/value citations. Ordinary image-only quotation resolution yielded 144 resolved fragments across the five pages.

The first debugger replay encountered a text-only telemetry read error. Serialization omitted the absent image detail, while the reader expected the nullable field to be present. The reader now defaults that field to null. The fix leaves persisted telemetry intact. The focused backend command below passed all 20 tests, including round trips for all three new presets. The live artifacts were successfully reread after the fix with zero additional provider calls.

```sh
PYTHONPATH=tools/extraction-debugger .venv/bin/pytest -q \
  tests/test_extraction_performance.py tools/extraction-debugger/tests/test_api.py
```

**Gate C2. Retain V1 as the default.** Image-only had the best checklist score and lowest estimated cost per published page, but produced weaker grounding for the Schneider schedule and missed a material unit on REX. Its Schneider native call took longer than the production timeout. Hybrid reduced input tokens on all five pages, but the successful matched pairs had mixed latency and the Siemens attempt failed admission. Text-only published all five pages under 100 seconds, but omissions and unsupported citations on Schneider prevent promotion. A single observation per preset and page remains insufficient for a production default change. Carry the duplicate-reference and raw-unmapped overflow failures into the planned output contract work.
