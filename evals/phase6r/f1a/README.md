# F1-A source coverage and preparation

## Ground truth review

Status **ground truth approved**. The fixtures cover every page in the six supplied PDFs, seven PDF pages in total. [Offline comparison and findings](REPORT.md)

F1-A2 replays the original modes with alternate-witness and geometric association scoring, then compares additional local OCR recipes under the same approved fixtures. [F1-A2 methods and findings](F1_A2_REPORT.md)

The baseline investigation found missing Panel B engineering literals, absent table structure and unresolved text evidence in the nine-page live Schneider benchmark. The Schneider file in this corpus is the single-page `schneider-panel-drawing.pdf` labeled 800a MDB. Siemens and Simson also have footer page numbers from larger documents. The fixture uses the actual PDF page index for all source bindings and retains those printed numbers for review. [Baseline investigation](../EXTRACTION_QUALITY_INVESTIGATION.md)

### How the draft was produced

The original PDFs were rendered upright and visually inspected at page scale and enlarged crops. The annotations were transcribed from those images, with bounds marked in the 1,100-pixel-wide review frame. Historical AI output, the PDF text layer, OCR, prepared readings and packed requests did not supply fixture text or geometry. The expected locations identify meaningful source regions and cells. Some identify a whole line, group, diagram or cell, so they are unsuitable as word-level localization truth without further annotation.

The review inventory contains 144 regions, 350 populated table cells across 20 structures, and 22 explicit associations. A legible diagram-only annotation may have no transcription. The REX tap numbers are separately transcribed, with uncertainty about the arrows' full spatial ordering recorded as ambiguous. The draft contains no spans scored as unreadable. Blank cells remain blank in the source and produce no expected text. General title-block, job, author, administrative and legal text fall outside the engineering text denominator. Within the engineering scope, human review should add any missing technical literals or locations before the inventory is frozen.

Review by sheet:

- **Delta, one page.** Check the 80T1 tag, provisional and standard ratings, dual primary voltage and BIL entries, the vertically merged tap positions, and the caveat distinguishing the drawing impedance from a future measured value.
- **Eaton, one page.** Check two GBH3020 diagram blocks, all 18 provision positions, the branch and main totals, the upstream model reference, and the H/W/D and minimum-gutter pairs.
- **REX, one page.** Check the voltage/load and tap/link rows, impedance range, conditional efficiency, termination cable sizes and dimension placement. The bare dimension numbers carry no unit assertion. Check the unresolved spatial ordering around the winding arrows.
- **Schneider, one page.** Check the 800a MDB designation, all 10 positions and their phase-bus connection order, the dashed glyphs and PS markings at circuits 7 and 10, and the electronic-trip markup pointing to circuit 9. Check the aggregate branch summation separately, along with the paired enclosure dimensions and the 30 kA series rating.
- **Siemens, one page.** Check the DMR-MAIN tag, Section #1 main device and ETU745 description, three Section #2 branch entries and continuation lines, filler/future notes, and repeated section dimensions.
- **Simson, two pages.** Check the frequency and per-unit section scope, saturated versus unsaturated readings, the resistance heading's unit and temperature qualifier, and the alternative bearing columns and merged overspeed value.

### Format and repeatable review

Each JSON fixture pins one PDF by SHA-256 and contains exactly one record per PDF page. Each page uses a top-left-origin pixel frame `[width, height]`. Boxes are `[left, top, right, bottom]` and normalize by dividing x by width and y by height. To compare with a different render size, normalize both first. Spaces between visually separated tokens are represented by a single space. Newlines retain meaningful separate lines. Visual glyphs such as typographic dashes, subscripts and fractions are represented as Unicode. Original numerical spelling, case, prefixes and qualifiers remain in the transcription. An ambiguous transcription can contain a legible portion or be null if only the geometry is known.

Region and table IDs are unique per page. A cell's stable address is its table ID, zero-based row and named column. `row_end` and `column_span` represent inclusive merged cells without inventing repeated data. `relations` connect two same-page annotation IDs, and their descriptions are review metadata. Region IDs and cell addresses can be referenced by future occurrence and registry expectations in separate fixtures. Keep those expectations and this source gold out of preparation and AI inputs.

Run from the repository root with the project's Python environment:

```sh
.venv/bin/python evals/phase6r/f1a/verify_ground_truth.py \
  /Users/adilzafar/Downloads/equipment-drawings \
  --overlay-dir /private/tmp/pf-f1a-overlays
.venv/bin/python -m pytest -q evals/phase6r/f1a
```

The verifier checks the closed corpus, hashes, page counts, coordinate frame, annotation IDs, table grid and relationship references. Optional overlays number each region and cell and put the index in a sibling text file. Green indicates legible, orange ambiguous, and red unreadable. Keep the PDFs and rendered overlays local. Automated checks establish structure and source identity. Human review establishes whether the transcriptions, scoped associations, and locations are correct.

## Reproduce the offline comparison

Use the PowerForge Python environment with Tesseract 5 and its English language data. The runner accepts `--tesseract` and `--tessdata` for non-default installations. The published run used the existing source worker image with networking disabled, current checkout sources mounted read-only, and no credentials. The results pin the OCR engine build, language data, preparation and layout identities, plus each PDF and fixture hash.

```sh
.venv/bin/python evals/phase6r/f1a/evaluate_sources.py \
  /Users/adilzafar/Downloads/equipment-drawings \
  /tmp/f1a-results.json --repeats 2
```

The benchmark assembles requests locally. It has no OpenAI transport, database, or published extraction output. Timing varies across runs. Compare the recorded reading fingerprints and counts to check repeatability on the same pinned runtime. [Results](results.json)

### Evaluation boundaries

Use the same pinned originals for the existing preparation baseline, native text, full-page OCR, regional OCR, and native/OCR hybrid. Pin renderer, OCR engine, language data and configuration. Select OCR regions with source-derived rules or a declared image partition. The implemented regional arm selects ink-bearing tiles without using expected boxes. Construct every variant's evaluated reading and request projection before joining it with expected annotations.

Collect readouts at native extraction, prepared source, reading construction and AI packing boundaries. At each boundary, record whether the literal is present, split, mistranscribed, missing or unsuitable for grounding. Record capability degradation and actual native text, primitive, region, raster, reading, table and packed-input sizes. This separates an optional-geometry budget from either a text or packing loss.

Use the frozen readable text inventory for recall and field transcription accuracy. Preserve case, signs, decimal places, units, prefixes and qualifiers in exact scoring. Report only explicitly defined whitespace and display-glyph equivalences separately from exact results. Report ambiguity, abstentions and text that falls outside the annotated inventory separately. Score text grounding against expected same-page regions by location precision, with schedule row/column and header-scope association as distinct measures. Count repeated source occurrences separately from duplicate readings at one occurrence. Track same-location conflicting transcriptions and which reading types supplied them.

Record preparation timings, repeated-run variation, reading count, packed bytes and local token estimates per page and variant. Estimates cannot establish provider token usage or engineering extraction quality. Compare adaptive OCR triggers on the same fixed corpus, including misses when a page supplies native text but that text does not cover the engineering content. Report the six documents individually before recommending a strategy. Any proposal to change production preparation, layout or AI inputs goes to review.
