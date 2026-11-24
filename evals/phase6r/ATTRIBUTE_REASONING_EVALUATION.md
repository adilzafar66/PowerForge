# Stage 2 reasoning evaluation

New OpenAI runs pin `medium` by default. `EXTRACTION_ATTRIBUTE_REASONING_EFFORT` also accepts `low` and `none` with GPT-6 Luna. Set it consistently on the API and workers. Change the setting before admitting a new run. Existing work units and retries use the effort in their original run profile. A reviewed operation that has yet to admit its extraction run requires a new review when its profile changes.

## Offline verification

```sh
.venv/bin/python evals/phase6r/attribute_performance_baseline.py --compare-efforts \
  313159b7-91cd-4c08-9afe-ca1d38a94764 5635845e-11f8-4216-a881-f6793791c274
```

The script uses the pinned recognition result, source representations, and original page image. It verifies the stored dispatch and proves the three assembled bodies differ only in `reasoning.effort`. It emits byte counts and digests without source content. For historical Siemens and REX inputs, use `--reproject` and identify those samples as projections using the current contract.

The offline check passed for all five inputs. It matched the historical dispatch digests for both Schneider variants and the Simson Maxwell page. Siemens and REX used verified historical sources reprojected through the current wire contract. For Schneider, the explicit medium/low/none requests measured 533,505/533,502/533,503 bytes without OCR and 635,492/635,489/635,490 bytes with OCR. The three-byte spread reflects the effort label length.

## Controlled live comparison

Require approval for exact private inputs and provider call and spend limits. Select the same native and OCR Schneider inputs, a dense schedule, native engineering text, and a diagram-heavy page. Freeze each page's recognition result and source artifact identities across the variants. Use the existing Stage 2 adapter, local admission, evidence verification, normalization and authorized retention against those fixtures. Record one reviewed medium baseline and paired low and none samples per page before any repeat. Vary the order of the three settings across pages. Keep the model, input, image detail, prompt, response schema, token ceiling, timeout and provider options fixed. Record the SDK version and any provider-reported service tier difference. Count incomplete calls and timeouts as outcomes. Keep retries outside the sample.

Capture provider wall time and range, p50 with sample size, cached input and total input tokens, total output, reasoning and visible output tokens, accepted and quarantined indices, and provider and admission failures. Compare independently annotated attribute values, types, equipment ownership, evidence occurrences and omitted critical facts. Report unresolved evidence and visual-only evidence separately from verified readings. Use the authorized debugger to access original output. Keep grading records and raw sources private.

Before running paid comparisons, agree on decision thresholds for latency, incomplete-response frequency, omissions and per-attribute correctness. A confirmed new wrong critical value or lost provenance disqualifies a lower-effort setting. Recommend a promotion only after paired evidence supports it. The implementation leaves the default at medium.

## Live screening result

On November 22, 2026 Pacific, the approved pilot dispatched 15 Stage 2 calls using GPT-6 Luna at standard service tier, with one attempt per effort on each of five pinned inputs. The recorded recognition result and provider-visible page input were identical within each triplet. All 14 available originals were verified through the restricted debugger with journaled reads.

- **Medium** completed 4/5, with a median successful provider call of 45.6 s (41.1–84.4 s). It matched 50/74 source checklist items.
- **Low** completed 4/5, with a median successful provider call of 21.7 s (18.3–28.0 s). It matched 30/74 checklist items. Median provider time was 46.4% lower on the three pages completed by both medium and low.
- **None** completed 2/5, with a median successful provider call of 23.5 s (21.2–25.9 s). It matched 19/74 checklist items.

Schneider with OCR used 45,309 measured input tokens for the low and none calls, up from 17,700 without OCR. Its medium call timed out. Low matched only four of 24 OCR Schneider checks. The native Schneider low and none responses both exceeded the 16-item raw-unmapped limit, as did none on the OCR variant. None also returned duplicate assertion identifiers on REX. On the generator page, none mapped the transient time constant to the open-circuit field. Low and none both proposed additional unsupported open-circuit mappings.

The protected checklist is a screening sample with one attempt per page and effort. Failures count in the checklist denominator. The timed-out call supplied no usage. The standard-rate estimate for the other 14 calls was US$0.0683 from returned token counts. Maintain the medium default. This sample gives a reason to continue testing latency improvements that preserve coverage and engineering semantics.
