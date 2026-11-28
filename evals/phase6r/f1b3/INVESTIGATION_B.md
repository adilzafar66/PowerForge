# Investigation B · Source representation approval

**Status** · Complete. Twelve approved live calls ran. Investigation C awaits review.

Use the current Schneider and Siemens PDFs, PDF page 1 only, and the exact 1700 × 2200 analysis images from A3. The manifest pins each PDF, PNG, prepared projection and exact encoded request. All arms retain A3's recognition prompt, registry catalog, strict response schema, GPT-6 Luna Standard, omitted reasoning override, high image detail, store=false, 100-second timeout and 16,384 output-token limit. No Stage 2 or evidence requirement is included. [Exact request fingerprints](b-preflight.json) · [A3 prompt and schema](a-preflight.json)

- **B1** uses the exact A3 request bytes. Four fresh calls are included in the twelve-call cap.
- **B2** adds one text input with one line per reading. The line contains the reading ID, normalized x/y/width/height, preferred text, distinct alternate transcriptions and any reading issues. Missing geometry is explicit. Source ownership, token witnesses, reading-order links and structural objects remain in the pinned preparation and are omitted from this simplified projection.
- **B3** adds the complete production Stage 1 page projection. It uses the same positioned-only preparation and retains the projection's reading, layout, ordering, uncertainty and provenance fields. Only the source page view is added, since the A3 instructions already carry the identical equipment catalog.

Schneider uses the established 300 DPI line-removal OCR recipe with 500 readings, including 97 with alternatives. The simplified projection contains positioned PS and 4.50-inch text at both provision rows. Siemens uses native text with 252 readings and no alternate transcriptions. The following are exact supplement byte counts, excluding the image and request envelope.

- **Schneider** · B1 0, B2 40,710, B3 211,857. Full request sizes 480,495 / 522,937 / 733,252 bytes.
- **Siemens** · B1 0, B2 19,100, B3 102,100. Full request sizes 385,979 / 405,897 / 507,099 bytes.

The six exact request bodies are available in the private host review directory named below. Each JSON contains the complete request including the image. The repository manifest retains hashes and sizes. Fresh offline regeneration in the network-disabled source-enrichment worker produced byte-identical B1 and B2 bodies. B3 retained identical source content and settings, with new preparation and layout ownership IDs and the corresponding regenerated hashes. Use the frozen first set for **both** live trials to hold these bytes fixed. The second set is only a repeatability check.

## Proposed authorization

Two prespecified trials per document per arm, **12 calls maximum, zero automatic retries, US$6.60 hard cap**. Run the first pass and then the reverse-order repeat for each page as listed in the manifest. Each unknown outcome consumes its slot. The conservative US$0.5332668 reservation per call totals US$6.3992016, using the same maximum-token reservation and pricing assumptions as Investigation A. Actual usage and cost will be reported with cache reads and writes itemized. The offline request sizes do not establish input tokens. [Official model pricing and context limits](https://developers.openai.com/api/docs/models/gpt-6-luna)

## Evaluation after approval

Use the corrected F1-B3 adjudication and report unique supplied matches, all reported rows, precision/recall, registry accuracy on matched supplied items, tag and ownership verdicts, and scope errors. Keep failed trials in the end-to-end denominator. Inspect returned circuit 7 and 10 claims against the original image and their exact readings, including alternative text and position. Track accessory and reference-only claims separately. Report examples where the output repeats a wrong OCR transcription, while treating other OCR influence as a hypothesis. Contrast fresh B1 with B2/B3 and use historical A3 as a secondary comparison. Two trials per arm on two development pages cannot establish generalization or isolate model variability. No production configuration changes are proposed.

Private review directory on this host:

    /Users/adilzafar/.codex/visualizations/2026/11/13/01a1d618-27e3-7bd0-b920-a8c4ae287edb/.f1b3-b-private/first

The offline harness is [investigation_b.py](investigation_b.py). Run it in the existing source-enrichment worker image with network disabled, the repository and PDF/raster directories mounted read-only, PYTHONPATH including the F1-A and F1-B evaluation directories, and a private writable output directory. The focused F1-B1 and F1-B3 suites passed 32 tests.

## Live results

All twelve requests returned HTTP 200 and passed local schema validation. There were no retries, refusals, incomplete responses, rate-limit responses or timeouts. All twelve private outputs were verified against their SHA-256 receipts before scoring. [Per-attempt results](b-results.json) · [Digest-bound adjudication](b-adjudication.json)

Each arm found **28/28 supplied occurrence opportunities** and returned 32 rows, for **100% recall and 87.5% precision**. All 28 matched observations per arm received the expected registry classification. The four extra rows per arm also used valid registry keys. There were no duplicated occurrences, additional accessories, reference-only observations, wrong tag owners or invented tags. Among the four expected tagged occurrences per arm, B1 matched three exactly and B2 and B3 matched two each. All five non-exact tags changed only the case of the lower-case “a” on Schneider.

- **Schneider** · Each arm found the panel and all eight supplied breakers in both trials. Each also reported circuits 7 and 10 as breakers in both trials. Across the six Schneider responses, that is 54 supplied matches out of 66 claims, with **12/12 prepared-space opportunities misclassified**. All six responses kept the circuit 9 ammeter subordinate or omitted it. The device families and ratings printed at the provision positions can describe the prepared spaces. The responses treated those rows as supplied despite the visually dashed symbols and the PS accessory text available in B2 and B3.
- **Siemens** · Each arm found the lineup, the WL main and the three branch devices in both trials, with no extra or missing rows. All six lineup tags matched exactly. Native readings changed neither recall nor precision. The image-only control's first response listed the main breaker before the lineup without changing its association.

### OCR and source influence

Schneider B2 and B3 both carried the PS/4.50″/FP readings near circuits 7 and 10. The PS readings had no alternate transcription or conflict marker. None of the four supplemented responses discussed those cues. These results show that supplying the text and its location did not resolve the scope error, but do not establish how the model used or weighted either input.

The same projection contained q283, which read `SOOAT/3` and was marked ambiguous, and q357, which read `SOkA` for the printed `30kA` SCCR. None of the supplemented responses repeated those strings. Where circuit 9 rating details were included, the responses preserved the printed 200 A trip indication. The SCCR is incidental to recognition and its omission cannot show that the model resolved the OCR error. No observed classification, scope or ownership error can be attributed to a reproduced OCR mistake in this sample.

### Size, latency and cost

The four matched calls per arm gave the following totals. Provider latency is client-side wall time for the call. Request and projection sizes are reported separately in the frozen manifest.

- **B1** · 14,008 input tokens, 2,525 output tokens, median 5.59 s, estimated US$0.00221.
- **B2** · 68,062 input tokens, 3,070 output tokens, median 6.29 s, estimated US$0.00613.
- **B3** · 200,904 input tokens, 3,289 output tokens, median 6.86 s, estimated US$0.01521.

B2 consumed **66.1% fewer total input tokens** than B3 for equivalent recognition results. Across all calls, the range was 3.64–8.91 s, with a median of 6.06 s and cumulative provider time of 74.38 s. Total usage-based cost was **US$0.02354**, within US$6.3992016 reserved and the approved US$6.60 cap. The first pass wrote 141,469 cache tokens and read none. The repeat read 141,469 tokens and wrote none. All requests used the same settings, but the cache state, provider variability and sample size limit latency conclusions. Historical A3 also recovered 28/28 supplied occurrences, produced four provision false positives, and matched three of four tags exactly. [Historical A3 results](a-results.json)

## Recommendation and review gate

Proceed directly to Investigation C after approval. Retain image-only as the recognition control. If a C comparison needs supplemental source text, prefer B2 over B3 because it preserved the measured recognition outcomes with fewer input tokens. The results offer no recognition-quality reason to carry the full projection forward on these pages, and do not establish that image-only will suffice for dense, scanned or other held-out documents. Revisit supplemental representations if a later error can be traced to a missing, misleading or poorly associated reading. The recurring Schneider error makes scope guidance and contract complexity better next variables to isolate. This is an experimental recommendation. Production behavior and prompts are unchanged.

## Reproduce the review

Use the retained restricted audit directory with the corrected scorer. It verifies the approved request, original provider output and digest-bound adjudication before exporting the results. The older A export also reproduced byte-for-byte after the scorer gained B support.

    PYTHONPATH=evals/phase6r/f1a:evals/phase6r/f1b .venv/bin/python \
      evals/phase6r/f1b3/summarize_a.py "$F1B3_B_AUDIT_DIRECTORY" \
      /tmp/f1b3-b-results.json --campaign b
    cmp evals/phase6r/f1b3/b-results.json /tmp/f1b3-b-results.json

The focused regression suite passed 36 tests. Ruff and whitespace checks passed. Raw requests and responses remain in private local storage.
