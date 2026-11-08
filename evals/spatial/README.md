# Spatial extraction evaluation v1

This offline evaluator runs the production Phase 3 renderer, local Tesseract adapter, native PDF reader, preparation, layout and enhanced converters. The enhanced stages use deterministic mock observations generated from observed readings and admitted cells. The mock receives no gold labels. Its coverage depends on the source projection and its own limited observation rules. Neither its results nor the separately scripted legacy replays measure model recognition quality.

The corpus has 15 page/policy cases from five authored originals. It includes the exact positioned 6D PDF, digital and scanned schedules, a merged header, repeated voltages, irregular and sparse cable rows, qualified utility values, native/scan disagreement, default and forced OCR on the same hybrid page, a rotated PDF, a TIFF with orientation metadata, clean and degraded nameplates, multi-column prose and a drawing negative. Gold comes from the drawing instructions and visual annotation of the frozen 6D PDF. It includes printed words, upright boxes, source basis, cell occurrences, spans, header relationships and independently stated engineering meanings. All inputs are synthetic.

## Run locally

Install the development packages and the local Tesseract 5 English engine. From the repo root, using the worker container or a matching Python environment:

```sh
mkdir -p evals/spatial/private
powerforge-eval-spatial --corpus evals/spatial/v1/corpus.json \
  --output evals/spatial/private/report.json \
  --artifacts evals/spatial/private/run-1
```

`python -m extraction_worker.spatial_evaluation` is equivalent. The default binary and language directory match the Linux source worker. Use `--tesseract PATH` and `--tessdata DIRECTORY` for another supported installation. The report records the actual binary, language data, parser and material profile identities. Repeat `--case ID` to select explicit cases. For a relocated corpus, use `--source-root` to point at the directory containing the referenced spatial and frozen table inputs.

`--artifacts` takes a new directory. It retains exact originals, analysis images/native text, thumbnails, recognized text, geometry, manifests, scripted responses and converted outputs. The report records per-file sizes and SHA-256 digests. Execution IDs and timing change between runs. The reference report records one run in a pinned environment. Engine builds and artifact IDs can change the output bytes. Keep local experiments and any approved private corpora outside committed fixtures. This command only accepts the synthetic corpus designation and has no external provider option.

## How to read the report

- Word and line geometry use one-to-one matching by intersection over union before comparing text. The default IoU is 0.50 for words/lines and 0.25 for table envelopes, with sensitivity reported at 0.25, 0.50 and 0.75. The generous table envelope threshold allows a text-derived extent to differ from a visible grid. Supported partitions additionally require exact row/column counts, cell spans and occurrence ownership. Header edges are measured separately.
- OCR CER and WER use edit distance against the authored printed traversal, with whitespace collapsed. This penalizes both recognition and traversal errors. The gold denominator includes every printed word in the six OCR-evaluation cases, including omitted auto-hybrid OCR and degraded text. The hidden native text layer participates in overlap scoring without entering the printed OCR reference.
- Source selection, alignment and reading order use matched occurrences. Repeated values stay distinct. Cell ownership uses occurrence identity and row/column placement. The reference records unsupported schedules and false supported partitions even when no claim is published.
- Mock claims match by the primary source occurrence and candidate kind before comparing mapping, exact typed values, units and equipment ownership. Exact artifact evidence and agreement with printed gold are separate scores. A false-claim count includes matched claims that abstained or had a field/association mismatch and unmatched candidates. It is broader than a count of invented mapped values.
- The exact positioned PDF uses both frozen 6D replays. Two other paired cases run the frozen 6C converters on the same Phase 3 outputs using separately scripted native and visual observations. The legacy evidence policies are reported separately. The legacy visual replay can ground to the page, and the enhanced replay can ground to a precise OCR occurrence.
- The injected numeric error is a separate control. It changes one actual OCR reading after the engine returns and scores the resulting table relationships, evidence and value against the original printed gold. It is excluded from main OCR totals and timings.
- Every rate includes its numerator and denominator, with null for an empty denominator. Cases with missing OCR, unsupported layout or failed stages stay in their gold cohorts. The command records evaluation failures in the report and returns an error for invalid corpus setup or input identity. It imposes no accuracy pass threshold.

See the [reference report](v1/reference-report.json) and the [Phase 6E handoff](../../docs/PHASE6E_HANDOFF.md) for observed results and coverage limits.
