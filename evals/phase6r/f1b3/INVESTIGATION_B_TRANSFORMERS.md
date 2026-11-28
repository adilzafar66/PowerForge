# Investigation B · Delta and REX follow-up

The approved follow-up repeated B1 image-only, B2 simplified positioned native readings, and B3 complete positioned-only Stage 1 source on PDF page 1 of Delta and REX. The experiment used the same A3 prompt, registry catalog, schema, GPT-6 Luna settings, and matched image within each drawing. Two trials per arm and document completed without retries, refusals, timeouts, throttling, or schema failures. All twelve output digests were verified from the private audit. [Frozen request fingerprints](b-transformers-preflight.json) · [Per-attempt results](b-transformers-results.json)

Each arm recovered **4/4 expected equipment occurrences and made no extra claims**, for 100% precision, recall, and registry type accuracy on this sample. All twelve responses reported exactly one two-winding transformer. All six Delta responses preserved the tag **80T1**. All six REX responses left the tag empty, consistent with the source. None promoted the catalog number, winding options, taps, drawings, or views to independent tags or equipment. These are Stage 1 observations only. No attribute extraction or evidence-localization test was run.

- **B1** · 14,008 input tokens, 601 output tokens, median provider latency 2.26 s, estimated US$0.00125.
- **B2** · 59,214 input tokens, 566 output tokens, median 2.22 s, estimated US$0.00428.
- **B3** · 166,116 input tokens, 591 output tokens, median 2.40 s, estimated US$0.01151.

Across the twelve calls, median provider latency was **2.31 s**, with a **1.97–3.13 s** range. Usage-based cost was **US$0.01704** at Standard rates. The first pass recorded 119,651 cache-write tokens and zero reads. The second recorded 119,651 cache-read tokens and zero writes. Provider variability and cache state limit latency comparisons. B2 used **64.4% fewer input tokens** than B3 across matched calls. B1 recovered the same recognition results with the fewest input tokens. These two single-equipment pages add a transformer contrast to the Schneider and Siemens benchmark. They do not establish performance on complex transformer schedules or Stage 2 tasks.

Reproduce the export with the retained private audit:

    PYTHONPATH=evals/phase6r/f1a:evals/phase6r/f1b .venv/bin/python \
      evals/phase6r/f1b3/summarize_a.py "$F1B3_TRANSFORMER_AUDIT_DIRECTORY" \
      /tmp/f1b3-transformer-results.json --campaign b-transformers
    cmp evals/phase6r/f1b3/b-transformers-results.json /tmp/f1b3-transformer-results.json

37 focused evaluation tests passed. Production code and settings were unchanged.
