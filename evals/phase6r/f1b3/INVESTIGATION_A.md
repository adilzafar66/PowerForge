# Investigation A · Fundamental model capability

**Status** · Investigation A complete. The approved twelve calls ran on the pinned Schneider and Siemens pages. Investigation B awaits review.

## Why these comparisons

The older Schneider investigation traced prepared-space false positives and occurrence omissions. On the replacement Schneider sheet, F1-A found 1/81 located annotations with default preparation; F1-A2's strongest OCR recipe reached 48/81. F1-B1 varied deterministic tables using the full recognition contract. That comparison could identify admission, localization and scope defects, but could not isolate basic visual recognition from output or registry constraints. The A arms progressively introduce those constraints while keeping the image fixed. Siemens provides a representative native-text document with explicit, visually legible BOM rows and subordinate context. Both documents are tested with vision alone. [Historical traces](../EXTRACTION_QUALITY_INVESTIGATION.md) · [F1-A](../f1a/REPORT.md) · [F1-A2](../f1a/F1_A2_REPORT.md) · [Table ablation](../f1a/TABLE_ABLATION_REPORT.md) · [F1-B1 design](../f1b/REVIEW.md) · [F1-B1 results](../f1b/BASELINE.md)

## Source expectations

The original seven pages were reviewed locally against the approved PDF hashes. The [versioned fixture](recognition-gold-v1.json) overlays supplied scope and document-level configuration expectations onto the [original occurrence anchors](../f1b/occurrence-gold.json), which are digest-pinned and linked to the F1-A source boxes. The revised evaluation ignores lifecycle classifications. The fixture never enters a provider request.

- **Schneider PDF page 1** has one 800a MDB assembly and eight supplied breaker occurrences. Circuits 7 and 10 have PS markings and dashed symbols and are excluded. Schedule positions anchor each breaker. Circuits 1/2 and 3/5/6 are potential groups. Their shared schedule and quantity entries do not establish complete registry equivalence. Circuit 4 differs by rating from the other BD rows, circuit 8 differs by rating from the other QD rows, and circuit 9 has a different family and separate directed markup. Keep nine entries pending additional evidence. Six would be possible if both candidate groups were subsequently established.
- **Siemens PDF page 1** has five entries. The drawing tags the two-section lineup DMR-MAIN and lists WL, CMD6, CJD6 and CND6. ETU745 belongs to WL. The utility option, instrumentation provision and transformer connection do not establish supplied standalone equipment. Potentially ambiguous contextual claims remain reviewable.
- **Eaton** has three page-local occurrences and two expected document configurations. The separate GBH3020 positions share a complete model and one two-device specification row. The PDG23G-LFD reference is excluded. CDP-6C is the assembly designation and the explicit Panel ID Nameplate field is blank. Record CDP-6C tag proposals separately as an alternate interpretation pending review.
- **Delta and REX** each describe one transformer. Delta's 80T1 is a tag. The REX product catalog number identifies the model.
- **Simson** has two page-local anchors for one generator configuration described by a continuous product datasheet. The fixture includes the subject of the datasheet. Unselected bearing alternatives are excluded.

All six documents remain available for future approved development trials. The reserved synthetic controls remain unchanged. An independent engineering holdout has yet to be identified.

## Exact approval scope

Use PDF page 1 of the current **schneider-panel-drawing.pdf** and **siemens-panel-drawing.pdf** from the development corpus. Run the first three arms on Schneider before Siemens, then repeat each matched set in reverse arm order. Allow at most two preassigned trials per page and arm. A refusal, timeout or incomplete response consumes its slot. The second trial is independent.

- **A1** uses a natural-language list with a concise supplied-scope instruction.
- **A2** uses the same engineering objective with a strict equipment array of identification, type, and tag. Type and tag can be null. A1 to A2 changes the response format together with its companion instruction.
- **A3** adds the registry keys, display names, descriptions, and instruction to use exact keys. A2 and A3 share byte-identical response schemas. This isolates the registry instruction plus catalog as a package. A3 permits a diagnostic null type to distinguish detection from failed classification or registry fit. Local review flags nonmember keys. A production contract would apply its own eligibility rules.

All requests use GPT-6 Luna Standard, provider-default reasoning with the setting omitted, 16,384 maximum output tokens, 100 seconds per request and zero automatic retries. Use store=false, high image detail, and a whole-page 1700 × 2200 analysis raster at 200 effective DPI. The proposed calls carry no text readings, internal IDs, production instructions, citations, OCR, attributes, crops or ground truth. The exact prompt text, schema, PDF and raster fingerprints, byte lengths and wire hashes are in the [preflight manifest](a-preflight.json).

**Proposed cap** · **12 calls and US$6.60**. The conservative US$0.5332668 per-call reservation uses 1.05M input tokens at long-context base plus 30-minute cache-write rates, 16,384 output tokens at the long-context rate, and the 10% regional premium. Twelve reservations total US$6.3992016. An illustrative short-context scenario of 15,000–45,000 input and 1,000–6,000 output tokens per call gives approximately US$0.05–0.16 for twelve calls, conservatively charging base input plus cache writes. Actual tokenization and usage are unmeasured. Refresh pricing and confirm account access before dispatch. [Official GPT-6 Luna documentation](https://developers.openai.com/api/docs/models/gpt-6-luna) · [OpenAI pricing](https://developers.openai.com/api/docs/pricing)

## Scoring and custody

Assign each original response row to a pinned occurrence, exclusion, or unresolved bucket before judging the type or tag. A reviewer transcribes A1 prose into the same ledger without a second model call. Position, section or a unique source identifier can identify an occurrence. An aggregate quantity without identifiable positions remains unresolved for occurrence scoring. Record distinct matched occurrences, duplicates, provision and reference false positives, and unresolved proposals separately. Record invented equipment only when a source reviewer can substantiate the finding. Keep semantic type accuracy separate from exact A3 key compliance. Report tagged-occurrence accuracy separately from null tags. A descriptive position helps align a claim with ground truth and earns no production evidence-localization credit. Deduplication quality is outside A.

Record per-attempt provider status, schema admission, incomplete/refusal diagnostics, request and response digests, timings, input/output/reasoning tokens, cache usage and cost. Keep failed slots in end-to-end denominators. Retain bounded exact output privately and omit raw output and page images from version control. Before an approved send, reserve the exact slot and cost in a dedicated ledger bound to the approved request digest, using the F1-B1 reservation and single-dispatch checks. An unknown outcome remains reserved. The offline preflight harness has no send path. The isolated live dispatcher used the approved manifest and one shared ledger for both live passes.

## Verification

    PYTHONPATH=evals/phase6r/f1b .venv/bin/python \
      evals/phase6r/f1b3/investigation_a.py \
      /Users/adilzafar/Downloads/equipment-drawings /tmp/f1b3-preflight.json
    cmp evals/phase6r/f1b3/a-preflight.json /tmp/f1b3-preflight.json

    PYTHONPATH=evals/phase6r/f1b:evals/phase6r/f1a .venv/bin/python -m pytest -q \
      evals/phase6r/f1b3 evals/phase6r/f1b

The six distinct bodies were reproduced byte-for-byte. They range from 383,405 to 480,495 bytes. A3 adds 1,911 wire bytes of registry content per body. The harness verifies scope membership, source hashes and linked anchors across the six originals and existing controls. The focused suite passed 17 tests. This preflight provides no measured capability, provider compatibility, quality, latency or cost result.

## Live results

All **12/12** requests returned HTTP 200 and completed. All eight structured responses passed the minimal local schema. None refused, truncated, timed out, throttled, or retried. Each exact output was written to private local audit storage with a 30-day review window and verified against its receipt before scoring. The versioned export contains only bounded metadata and review outcomes. Filesystem expiry is an operator responsibility for this isolated evaluation. [Attempt metrics](a-results.json) · [Digest-bound manual adjudication](a-adjudication.json)

Each arm received four calls and correctly identified **28/28 supplied occurrences** across the two pages and two trials. These are repeated page-level opportunities, equivalent to fourteen distinct supplied occurrences. All 84 matched observations had semantically correct equipment types. We awarded no evidence-localization or final configuration credit. The optional engineering prose and incidental ratings were outside this scoring.

- **A1 · Natural language.** 28/32 output rows described supplied occurrences. Four prepared-space false positives. Three of four expected tags matched exactly.
- **A2 · Minimal schema.** 28/33 supplied, four prepared-space false positives, and one standalone ammeter from a breaker accessory. Two of four expected tags matched exactly.
- **A3 · Minimal schema plus registry.** 28/32 supplied and four prepared-space false positives. All 32 rows used permitted registry keys, including the four false positives. All 28 supplied observations received their expected registry key. Three of four expected tags matched exactly.

**Schneider.** Every trial found the assembly and all eight supplied breaker positions. Every trial also reported both prepared spaces, giving **12 false positives in 12 provision opportunities**. The source prints 200/3, QD and a PS accessory in both rows and depicts both with dashed rather than solid symbols. The natural-language repeat explicitly transcribed PS and still called both rows supplied breakers. This shows some visual information arrived but did not govern scope. It does not establish whether the model saw the dashed graphics or understood the PS notation. One A2 trial treated the ammeter in circuit 9's accessories column as standalone equipment. Four out of six responses capitalized the lower-case “a” in the assembly tag. These were case-only differences; no circuit number was promoted to a tag.

**Siemens.** Across all six trials, 30/30 supplied occurrence opportunities were recovered and there were no extra rows. The assembly tag matched exactly each time. No result promoted ETU745, the instrumentation provision, the utility option or the transformer connection into an independent device.

### Operational measurements

Provider wall time was **4.61–15.99 s per call**, median **7.67 s**, with **102.97 s** summed across the twelve sequential requests. A1/A2/A3 medians were **7.65 / 11.44 / 7.03 s**. A3 needed **383 more input tokens per call** than A2. Across both trials, the arms used **11,984 / 12,476 / 14,008 input tokens** and **3,714 / 3,281 / 2,846 output tokens**, respectively. The reasoning subsets were **2,714 / 2,092 / 1,760 tokens**. These small samples and different generated answers do not establish a speed ranking.

The first pass recorded **19,216 cache-write tokens and zero reads**. The repeat recorded **19,216 cached input tokens and zero writes**. The measured campaign totals were **38,468 input tokens and 9,841 output tokens**, for an estimated **US$0.00751826** at the global Standard rates. The estimate applies the provider-reported cache-write and cache-read breakdown. The first pass was about **US$0.00482** and the repeat **US$0.00270**. These are usage-based estimates, with no invoice reconciliation. Twelve ledger reservations total **US$6.3992016** within the approved US$6.60 cap. [Official pricing](https://developers.openai.com/api/docs/pricing) · [Prompt cache accounting](https://developers.openai.com/api/docs/guides/prompt-caching)

### Interpretation and review gate

The model demonstrated basic equipment detection and classification on both pages. Neither the minimal response structure nor the registry instruction eliminated the Schneider provision error, and neither reduced detection in this sample. The strongest confirmed deficiency is supplied-scope interpretation on the Schneider schedule. The data leave open whether better positioned source readings, different image rendering, or more explicit scope guidance would help. The exact model-facing path did not provide the F1-A2 OCR information. The same model and source raster were used throughout, so this experiment cannot separate image legibility from reasoning about the visual and textual cues.

For a separately approved Investigation B plan, use A3 as the fixed image-only control because it retains registry classification with a minimal response. Compare supplementary source representations under that same contract and track provision false positives, accessory scope and tag fidelity separately from recall. This is a two-page development result without independent holdout trials. It does not justify a production contract change, prompt rewrite, layout removal, or automated grouping.

### Live verification

The focused F1-B1 and Investigation A suites passed **22 tests**, including exact request and slot pins, repeat fencing, malformed and incomplete response retention, and cache pricing. Ruff and whitespace checks passed. Regenerating the export from the private audit verifies all twelve receipts and produces the same machine-readable results.

    PYTHONPATH=evals/phase6r/f1a:evals/phase6r/f1b .venv/bin/python \
      evals/phase6r/f1b3/summarize_a.py "$F1B3_A_AUDIT_DIRECTORY" /tmp/f1b3-a-results.json
    cmp evals/phase6r/f1b3/a-results.json /tmp/f1b3-a-results.json
