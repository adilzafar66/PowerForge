# Stage 2 source context evaluation

## Candidate

Milestone C starts from the implemented Milestone A instrumentation and Milestone B benchmark. Medium reasoning remains the comparison setting. Schneider OCR used 45,309 input tokens in the measured v1 live calls, compared with 17,700 on the native projection.

Set `EXTRACTION_ATTRIBUTE_INPUT_VERSION=compact-page-v2` consistently on the API and workers for a controlled evaluation. New profiles pin the view version and its decoding prompt. V2 uses `attribute_extraction_v10.txt` and bundle `phase-6r-stages-v11`. V1 keeps its original prompt and remains the default. Changing the setting affects new admissions. Existing runs, including retries, use their pinned projection and instructions. The response schema, publication policy, image detail, and reasoning effort are independent of the view selection. This milestone has no database migration.

V2 packs repeated witnesses into a table of `[representation_ref, kind, ref]` rows. Overlaps, reading witnesses, cell boundaries, and unresolved structural support refer to zero-based table entries. Full cell metadata, header links, and reading-order links stay explicit.

A group is eligible only for consecutive clean readings of the same modality joined by an unbranched pinned baseline. When readings belong to a table, a group stays inside one confirmed reading cell. Overlap participants, readings with alternatives or issues, missing geometry, and multiline readings stay standalone. A group is limited to 32 members and 2,048 Unicode characters and is emitted only when it reduces the serialized reading bytes. Each member retains its exact text slice, original reading ID, and coordinates. Its half-open offsets use Unicode code points and exclude the display separators. The original evidence localizer still verifies each citation against the pinned artifacts. Integer support indices never become citation IDs.

## Offline measurements

All five inputs expanded to the exact v1 provider data, including reading order, original and alternate transcriptions, member coordinates, table boundaries, and header links. The rehearsed requests used explicit medium effort and the same image for each pair. Full body sizes include the decoding prompt, schema, JSON escaping, and Base64 image. They are UTF-8 byte counts, not provider token estimates.

- **Schneider page 1 without OCR.** All 123 readings survived. Structured text fell from 34,635 to 33,976 bytes and the full body went from 533,505 to 533,405 bytes. Twelve groups saved 672 bytes in the readings section.
- **Schneider page 1 with OCR.** All 445 readings survived. Structured text fell from 120,820 to 82,850 bytes, a 31.4% reduction. The full body fell from 635,492 to 590,067 bytes, a 7.1% reduction. Layout fell from 57,604 to 19,562 bytes. Reading-source records shrank from 29,466 to 3,127 bytes and overlap records from 20,914 to 2,923 bytes, with a 6,277-byte shared witness table. The grouping test retained standalone rows because no qualifying group saved bytes on this page. The increased reading-section size is the 72-byte member-column description.
- **Simson Maxwell PDF page 2.** The structured text fell from 36,949 to 36,533 bytes. The full body rose from 454,513 to 454,710 bytes, as the decoding prompt cost more than the reduction in this case.
- **Siemens schedule page 1.** The full body fell from 460,462 to 459,522 bytes in the current wire projection of verified historical sources.
- **REX diagram page 1.** The full body fell from 995,272 to 995,023 bytes in the current wire projection of verified historical sources.

Both Schneider projections retained the same page image. In the OCR snapshot, `q301` still reports `208Y/120V` and `q308` through `q310` retain `System Ampacity: 800A`. The original dimension pairs remain at `q330` and `q331`. The image still reads `30kA SYMS. SCCR`. The pinned OCR witness at `q314` transcribes the first token as `SOkA`, so v2 preserves that distinction alongside `q315` and `q316`. These checks establish source availability and identity. They do not establish an accepted or correctly mapped value.

## Reproduce and review

```sh
.venv/bin/python evals/phase6r/attribute_performance_baseline.py --compare-context \
  313159b7-91cd-4c08-9afe-ca1d38a94764 5635845e-11f8-4216-a881-f6793791c274 \
  81f39815-0a5a-4019-bdb2-831fd3722010
.venv/bin/python evals/phase6r/attribute_performance_baseline.py --compare-context --reproject \
  e3db2b1d-3948-490c-be80-c4fd60115887 b6e5b09e-3816-4ca9-a31b-69ecf8095283
```

The tool verifies historical dispatch digests where available and rejects any v2 round-trip difference. It emits aggregate counts, byte sizes, and hashes without source text. The two-version publication integration test injects a reading citation into the mocked response and verifies it resolves to the exact pinned quote under both profiles, even when the deployment default changes after admission.

## Live comparison

On November 22, 2026 Pacific, the approved comparison made ten GPT-6 Luna Stage 2 calls at medium effort. Each pair used identical pinned source images, recognition results, registry data, response schema, high image detail, the standard service tier, a 100-second timeout, and a 16,384-token output cap. The two view-specific decoding prompts were pinned. The order alternated by input. Work ran in the disposable benchmark database with zero retries and no paid recognition calls.

- **Schneider without OCR.** V1 completed in 97.64 seconds with 17,700 input tokens. V2 completed in 92.21 seconds with 17,579 input tokens. Both matched 24 of 24 checklist items and mapped 33 candidates. V2 proposed metric scalars from the paired dimension expressions. The existing fidelity check flagged all three as `SOURCE_VALUE_MISMATCH`. The v1 dimension proposals were also non-mapping, with `UNVERIFIED_REPRESENTATIONS`.
- **Schneider with OCR.** V1 timed out at 100.00 seconds with no returned token usage. V2 completed in 87.02 seconds with 37,310 input tokens, of which 3,504 were cached. V2 matched 24 of 24 checklist items and mapped 15 candidates. The full request shrank from 635,492 to 590,067 bytes. The 37,310 input tokens were 17.7% below the 45,309 measured for the same v1 view in the Milestone B low and none runs. That token comparison uses a historical reference because the fresh v1 call timed out.
- **Simson Maxwell.** V1 completed in 51.05 seconds with 19,965 input tokens and matched 7 of 7 checks. V2 completed in 36.18 seconds with 19,958 input tokens and matched 4 of 7. All three resistance magnitudes and owners were retained in v2. The proposals used the source ohm sign `Ω` where the registry calls for `Ω`. The exact-unit checklist counted the difference, and both versions left the qualified resistances unmapped. V2 resolved 61 citations overall versus 103 for v1, but resolved 17 value citations versus 16.
- **Siemens.** V1 completed in 59.32 seconds with 24,809 input tokens. V2 completed in 67.41 seconds with 24,572 input tokens. Both matched 14 of 14 checks. V1 mapped a protection description as a second model for the WL breaker. V2 returned the supported model without that conflict.
- **REX.** V1 completed in 38.37 seconds with 24,074 input tokens and matched 5 of 5 checks. V2 used 23,958 input tokens and returned in 44.49 seconds. Local admission rejected the response on `CROSS_FIELD / duplicate_reference` at `attributes[1].local_ref`. The original audit reports 17 received assertions and zero accepted. No Stage 2 candidates were published.

V1 and v2 each completed four of five attempts. Exact matches were 50 of 74 for v1 and 66 of 74 for v2, with failures included. The score measures accepted proposals for the expected source value, unit, registry key, and owner. Mapping, ownership certainty, and evidence were reviewed separately. On the three inputs both versions completed, v1 matched 45 of 45 checks and v2 matched 42 of 45. Median provider time on those three inputs was 59.32 seconds for v1 and 67.41 seconds for v2. Across the four non-OCR inputs with measured usage for both views, v2 reduced total input tokens by 0.6%.

The restricted debugger returned all nine retained originals with matching byte counts and hashes. Offline readmission and publication reproduced all eight completed results, including their owner links, evidence, and mapped values. The REX v2 original reproduced its fatal rejection, and the timed-out call had no original. All nine calls with returned tier reported standard. Measured usage was estimated at US$0.0609 across those nine calls from the returned input, cached input, and output counts. The timed-out call's usage and actual billing are unavailable. The screening run used one observation per view per input, so latency and response differences should be treated as observations from this run. [GPT-6 Luna list rates](https://developers.openai.com/api/docs/models/gpt-6-luna)

**Gate C. Keep v1 as the default and v2 opt-in.** The OCR pair demonstrates a meaningful reduction in context size and a completion within the deadline. The REX rejection and the mixed results on the other inputs leave the general rollout gate unmet. Preserve the REX duplicate-ID response as restricted diagnostic evidence for the structured-output reliability work.

### Verification

```sh
.venv/bin/pytest -q tests/test_extraction_compact_context.py tests/test_extraction_stage_contracts.py \
  tests/test_extraction_performance.py tests/test_extraction_profile.py tests/test_openai_extraction.py
# 150 passed

RUN_INTEGRATION=1 .venv/bin/pytest -q tests/test_extraction_operations.py \
  -k 'mocked_live_operation_persists_both_stages or provider_projection_preserves_pinned_prose'
# 3 passed, 41 deselected using a separate disposable PostgreSQL database
```
