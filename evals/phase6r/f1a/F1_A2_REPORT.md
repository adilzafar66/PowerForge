# F1-A2 source preparation evaluation refinement

This offline evaluation uses the approved ground truth for the same seven pages across Delta, Eaton, REX, Schneider 800a MDB, Siemens, and Simson. Source and fixture SHA-256 values are included in the machine results. The original F1-A report and results remain the historical baseline. [F1-A report](REPORT.md)

## Revised scoring

- **Preferred** uses the text PowerForge marks as preferred at each reading position. **Available** additionally tests complete, coherent views of each alternate's source representation. A transcript can use the ordinary preferred view or a single alternate witness stream. The scorer cannot select individual alternatives across streams to manufacture a match. Two different variants in one witness slot block that stream at the slot. Exact and display-equivalent hits are counted separately. The latter keeps digits and case and folds the same display glyphs and whitespace conventions as F1-A.
- **Unambiguous** requires a matching preferred transcript without flagged overlap, a differing witness, invalid geometry, unsupported direction or native replacement characters at its supporting readings. An uncertain token blocks the span. Two equal witness texts do not introduce an ambiguity. The prepared stage has no alignment flags yet, so the unambiguous comparison applies to constructed and packed readings. OCR engine confidence is reported separately and has no role in acceptance.
- **Construction changes** compare prepared and constructed readings before request packing. The results distinguish local text retained through an alternate, an elsewhere or unlocalized match, and a loss of the coherent local transcript. A separate count of missing token witness identities detects actual omission of representation tokens. It distinguishes such omission from a change in span grouping, geometry, or competition among still-retained readings.
- **Geometric association** uses the envelope of the preferred matched readings as an anchor. The diagnostic tests nearest rightward row neighbors, downward column neighbors, above-column header candidates, and leftward label candidates. Distances, overlap and tie thresholds are fixed. It records correct, incorrect, ambiguous, missing source, missing target and no candidate. It can select a rival anywhere on the page. Gold supplies the endpoint text and evaluation scope and supplies the roles of header and label candidates. It does not supply the geometry used to predict the link. A header hit selects one of its approved ancestors, while the explicit table metric continues to score every declared header link. These are role-conditioned recovery diagnostics. Independently discovering table structure, identifying equipment, and verifying engineering ownership require separate evaluation.

The **explicit table reconstruction** scorer and the five original preparation arms are retained. Each arm is rerun under the refined scorer before any new variants are compared. The offline request builder uses the same fixed synthetic BUS prerequisite and measured provider-body serialization as F1-A. There is no provider dispatch.

## OCR experiments

Two supplementary arms retained native text and optional native geometry through the existing preparation and layout path. The first added OCR from the ink-bearing two-by-three grid. The second used a four-by-four grid and chose up to eight tiles with sufficient ink and at most two native word centers. It prioritized the lowest native count, then the highest ink fraction. Both used a halo for OCR context and assigned detections to one crop core by word center. The selective mode deliberately uses a coverage proxy. Its missed regions and false triggers remain in the evaluation.

The Schneider diagnostic held the native source and analysis image fixed while varying the OCR raster and local Tesseract recipe:

- A 300 DPI, PSM 6 control through the experimental adapter.
- 450 DPI at the same segmentation setting.
- PSM 3 automatic and PSM 11 sparse segmentation at 300 DPI.
- Grayscale autocontrast, and autocontrast with long horizontal and vertical line removal.
- Ink-bearing crops with sparse segmentation, crops at 450 DPI, and a combination of 450 DPI, sparse segmentation, cropping and line removal.

The high-resolution OCR image is rendered directly from the original PDF. The analysis image included in the constructed AI input is unchanged. Candidate recipes are ranked on Schneider by available located text, then numeric coverage, character edits and local time. The top two are rerun on the other five documents as regression checks. All parameters and crop selection rules are independent of the fixtures. Ranking on this development page cannot establish a production threshold.

The experimental projection preserves the original-document pin, full OCR-raster hash and dimensions, preprocessing recipe identity, processed-input crop hashes, crop-frame offsets, and page-local coordinates. The audit receipts in the benchmark describe experimental behavior. A deployable crop contract would need each processed input and transform to be independently retained and verified, rather than relying on the benchmark's derived page representation.

## Reproduction

Run in the PowerForge Python environment with Tesseract 5 and its English data, or use the source-worker image with networking disabled and the current source checkout mounted read-only.

```sh
.venv/bin/python evals/phase6r/f1a/evaluate_refinement.py \
  /Users/adilzafar/Downloads/equipment-drawings \
  /tmp/f1a2-results.json --repeats 2
.venv/bin/python -m pytest -q evals/phase6r/f1a
```

`--tesseract` and `--tessdata` override the Linux defaults. Per-stage CPU and wall timings exclude scoring and the shared analysis render. All OCR invocations are local. [Machine-readable results](results-a2.json)

To regenerate the corpus and document rollups:

```sh
.venv/bin/python evals/phase6r/f1a/summarize_refinement.py \
  /tmp/f1a2-results.json /tmp/f1a2-summary.json
```

The rollup keeps all evaluated pages in the coverage denominator even if a stage fails, and reports the number with measured packed size. [Document and corpus rollups](summary-a2.json)

## Results

All 140 attempts reached request packing. The two repeats agreed on reading and alternate-witness fingerprints, request sizes and failure state. There were no missing prepared token witnesses at construction. All reading views had identical coverage before and after packing. Preferred coverage reproduced the original F1-A scores on every baseline page.

### Rescored baseline and supplementary OCR

The figures below give preferred, available, and unambiguous located annotations out of 490. Exact plus display-equivalent counts are shown for the available view. Numeric coverage is out of 588. Time sums the mean of two attempts per page and packed size sums source JSON across the corpus.

- **Existing** · Preferred 371, available 371 (369 exact + 2 display-equivalent), unambiguous 371. Numeric 487, available character error 18.25%, 11.79 s and 236.4 KiB.
- **Native only** · 371 / 371 (369 + 2) / 371. Numeric 487, error 18.25%, 12.06 s and 236.4 KiB. Both native arms emitted zero OCR calls on these pages.
- **Full-page OCR only** · 210 / 210 (203 + 7) / 206. Numeric 370, error 31.74%, 14.22 s and 254.0 KiB.
- **Regional OCR only** · 256 / 256 (246 + 10) / 247. Numeric 439, error 27.56%, 18.22 s and 246.9 KiB.
- **Full-page hybrid** · 401 / 407 (405 + 2) / 333. Numeric 565, error 6.13%, 26.09 s and 862.0 KiB.
- **Regional hybrid** · 403 / 408 (405 + 3) / 335. Numeric 565, error 5.65%, 30.56 s and 861.8 KiB.
- **Selective regional hybrid** · 379 / 379 (376 + 3) / 377. Numeric 514, error 13.63%, 16.51 s and 267.8 KiB.

Under full-page hybrid, six additional annotations matched when coherent alternate witnesses were included. Three were the earlier F1-A construction losses. The REX insulation block and the Siemens Specifications and Modifications blocks had coherent alternate views. The other three were Delta tap-diagram text that formed usable spans after alignment when the alternate representation views were considered. Production alignment merges agreeing token witnesses. An alternate view can therefore restore a complete sequence without an alternative numerical interpretation. The scorer also recorded a true loss of local coherence for the Delta tap-header annotation in the line-removal arm, where it could match only as unlocalized text. Its individual prepared token witnesses were still present.

Selective OCR reduced full-page hybrid's OCR words from 1,890 to 243, identical overlapping preferred pairs from 206 to 3, cross-engine conflicts from 42 to 1, and ambiguous overlap pairs from 463 to 11. It used 22 crop invocations versus seven full-page invocations. Full regional hybrid used 42 crop invocations, added one available match, and increased duplicates from 206 to 229 and conflicts from 42 to 45. Its ambiguous overlap count was 414. Confidence below 50 occurred on 298/1,890, 205/1,869 and 50/243 OCR words for full, regional and selective hybrid, respectively. Lower OCR volume helped preserve unambiguous text. The selector recovered only six Schneider annotations, compared with 24 for unrestricted hybrid. The eight selected cores on that page fell in the top and bottom bands and missed the central engineering text. Ink density is a weak ranking signal in the presence of drafting lines, blank areas, and stamps.

### Geometric association versus explicit reconstruction

Explicit reconstruction still recovered **0/221 row pairs, 0/270 column pairs, 0/152 header links and 0/69 label/value pairs** across the approved structures. Geometry recovered many of those associations when supplied with localized endpoint text. The geometric header metric has 135 source queries because it permits any approved ancestor for each query.

- **Existing** found 124 correct row links with 2 incorrect, 210 correct column links with 6 incorrect, 77 correct headers and 64 correct label/value links.
- **Full-page hybrid** found 125 correct rows with 6 incorrect, 214 correct columns with 8 incorrect, 77 correct headers and 64 correct label/value links.
- **Selective hybrid** found 124 correct rows with 2 incorrect, 210 correct columns with 7 incorrect, 77 correct headers and 64 correct label/value links.
- **450 DPI tiled combination** found 145 correct rows with 4 incorrect, 242 correct columns with 2 incorrect, 114 correct headers and 68 correct label/value links.

There were zero geometric ties within the declared tolerance on this corpus. Synthetic tests exercise ambiguous nearest links explicitly. OCR alignment uncertainty affects a separate metric and was common. The results include the missing-source, missing-target and no-candidate counts. On Schneider, the 450 DPI tiled combination recovered 20 correct rows with 2 incorrect and 22 correct columns with zero incorrect. It still reconstructed zero explicit schedule pairs. These geometry scores describe what can be aligned within the drawing, with endpoint roles supplied for header and label scoring.

### Schneider OCR diagnosis

The original 24/81 ceiling came from source recognition and segmentation. The earlier inspection found no native PDF text in the schedule or specification blocks. The rendered lettering is consistent with outlined vector strokes. The 300 DPI PSM 6 baseline expected a fairly uniform text block on a sheet that has ruled tables, small type and dispersed notes. Changing segmentation or reducing drafting lines mattered more than enlarging the raster alone.

- **Higher resolution at unchanged PSM 6** · 31/81 available and 74/86 numeric, compared with 24 and 72 at 300 DPI. It correctly recovered the complete circuit 9 `250AS 200AT/3` string where the 300 DPI control ended at `200AT/`.
- **Automatic and sparse segmentation** · At 300 DPI, PSM 3 recovered 44/81 and 81/86 numeric. PSM 11 recovered 40/81 and 72/86 numeric. Tiled PSM 11 reached 44/81 with 69/86 numeric. Tiled 450 DPI at PSM 6 gave 34/81 and 71/86 numeric.
- **Contrast and line interference** · Autocontrast by itself held at 24/81. Directional line removal at 300 DPI reached **48/81** (46 exact + 2 display-equivalent), **82/86** numeric and **47/81** unambiguous in 3.34 s. The 450 DPI tiled, sparse, line-removal combination produced **47/81** (45 + 2), **73/86** numeric and **43/81** unambiguous in 4.72 s. The contrast-only control supports attributing the larger jump to line removal in this test. The combined recipe does not isolate interactions among its individual factors.
- **Remaining character and context failures** · The 300 DPI control, line-removal winner and 450 DPI combination all returned `SOkA` for the expected `30kA` SCCR. The line-removal winner also returned `SOOAT/3 /` in circuit 9, which the 450 DPI combination read correctly. All six enclosure dimension numerals survived in these three recipes, but quotation marks and adjacent glyphs kept the complete enclosure transcription from matching. The scorer correctly kept those misses. Review dimension tick-mark encoding if whitespace or display equivalences are revisited. No fixture was edited.

### Cross-document checks

Available coverage below follows **existing / full-page hybrid / regional hybrid / selective hybrid / 300 DPI line removal / 450 DPI tiled combination**. The numeric and unambiguous columns and timings for every recipe are in the document rollups. [Per-document metrics](summary-a2.json)

- **Delta** · 50 / 53 / 54 / 50 / 53 / 55 of 63. All retained 125/125 numeric literals. Unambiguous coverage fell to 24 with 300 DPI line removal, from 50 native and 33 full-page hybrid. The cleaner-looking crop therefore did not make Delta's transcription safer.
- **Eaton** · 82 / 82 / 82 / 82 / 82 / 82 of 83. Selective OCR made zero engine invocations and retained all 82 unambiguous matches. The two promoted recipes recovered no new text.
- **REX** · 63 / 69 / 72 / 66 / 70 / 71 of 79. Selective hybrid made five crop invocations, preserved 65 unambiguous matches and packed 46.4 KiB, compared with 57 matches and 166.2 KiB for full-page hybrid. The 450 DPI combination recovered 127/132 numeric literals versus 123 for full-page hybrid.
- **Schneider** · 1 / 24 / 24 / 6 / 48 / 47 of 81. The selective tile ranking missed the target areas. The strongest OCR recipes improved text coverage while explicit schedule reconstruction remained empty.
- **Siemens** · 38 / 40 / 39 / 38 / 40 / 38 of 40. All six arms retained 64/64 numeric literals. The 450 DPI combination lost two available matches compared with full-page hybrid, and unambiguous coverage fell from 37 to 33.
- **Simson** · 137 / 139 / 137 / 137 / 142 / 141 of 144 over two pages. All six arms retained 106/106 numeric literals. The two promoted recipes improved located text and geometric column recovery while duplicating or disputing enough material to leave only 118 and 120 unambiguous annotations, versus 137 native.

Across all pages the 300 DPI line-removal recipe reached **435/490 available** (432 exact + 3 display), **575/588 numeric**, **357/490 unambiguous**, **4.76% character error**, **27.63 s** and **1,008.7 KiB**. The 450 DPI combination reached **434/490 available** (431 + 3), **570/588 numeric**, **362/490 unambiguous**, **3.63% error**, **36.45 s** and **990.4 KiB**. The recipes produced 51 and 61 conflicts and 256 and 248 identical preferred-reading overlap pairs. A small aggregate difference masks larger sheet-level tradeoffs.

## Production recommendations and review gates

**Recommend for production design review** · Retain native readings and the original page image as the default. Treat OCR as additional evidence with its own producer, original input and region transform. Keep dissenting readings available for review and report preferred text, available witnesses, and conflicts separately. Preserve the explicit structural uncertainty already used by PowerForge. If adding operator diagnostics, report missing text, conflicting text and unresolved structure as independent capabilities.

**Require held-out evaluation before implementation** · Use the 300 DPI line-removal recipe and automatic segmentation as the next controlled candidates for line-heavy, text-poor sheets. Test clean native tables, outlined drawings, and scans separately. Compare against native-only and the existing hybrid at matched input and include small glyph fidelity, qualifier preservation and false links. Validate a source-derived region rule that avoids the observed border-and-stamp bias. Leave automated OCR selection, the default preprocessing recipe and use of geometric links in production pending those results. Production crop provenance requires a separately approved design for immutable processed crop inputs and bounded source transforms.

The seven-page development corpus cannot establish generality, OCR confidence calibration, provider latency or engineering extraction accuracy. Timing uses consecutive repeats per arm on one local runtime and excludes persistence, scheduling, scoring and the shared render. Crop selection and text matching remain sensitive to enclosure boundaries and reading order. Annotation-level numeric hits count matching digit literals in the expected area and do not validate signs, units or ownership. F1-B and production changes remain at the review gate.

## Verification

- Ground-truth verification confirmed all six original hashes and seven approved page indices. The fixture files and historical F1-A results are byte-identical to the branch baseline.
- The pinned local source-worker image ran with networking disabled and read-only PDF mounts. The recorded runtime used Tesseract 5.3.0 and PyMuPDF 1.28.2. No paid calls were made.
- Host test commands passed 46 F1-A2, native and compact-context tests and 63 F1-A2, alignment and layout tests. The first Linux regression attempt passed 95 tests and failed two existing layout cases because the container started outside the fixture root. The rerun from the checkout root passed **97 tests with zero skips** across `evals/phase6r/f1a`, `test_enrichment_ocr.py`, `test_spatial_evaluation.py`, `test_enrichment_native.py`, `test_extraction_compact_context.py`, `test_spatial_alignment.py` and `test_spatial_layout.py`.
- Lint, formatting, JSON rollup reproduction and the staged diff whitespace check passed.
