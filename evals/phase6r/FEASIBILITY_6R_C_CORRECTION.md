# Phase 6R-C correction and live rerun

## Source behavior

Delta crossed the limit of 5,096 eligible native drawing primitives during preparation. The native adapter now discards the entire optional primitive set when the first excess primitive is found and writes `NATIVE_DRAWING_PRIMITIVE_LIMIT` into the prepared manifest. Native text, source coordinates, raster, OCR eligibility, and original document identity are preserved. The layout carries the same diagnostic and no table relationships.

REX had 4,629 native primitives, within the preparation limit. Its spatial layout exceeded 64 connected grid components after the existing bounded segment analysis. The layout now retains the independently derived reading and baseline-order projection, with `NATIVE_GRID_COMPONENT_LIMIT` and no table or table-order claims. Its native geometry remains pinned in the preparation artifact. The same all-or-nothing table policy covers bounded segment, partition, support and aggregate table limits. The code never infers borderless tables from an incomplete ruled analysis. It continues to validate the exact preparation and layout hashes and reproduces the layout before either AI stage. This change adds no new grid search.

Preparation uses adapter identity `native-pymupdf-v2`. Layout uses a new algorithm identity with the `bounded-optional-tables-v2` policy marker and updated schema digest. The existing wire formats are extended through the prepared limitation list and unresolved-layout reason codes. The original layout identity fixture is retained and the new identity is pinned separately. Previous artifacts remain immutable. New runs use the revised identities and reject old algorithm pins for new execution.

## Authorized live rerun

Page 1 of the same three real-world PDFs was authorized again. The run used the revision-scoped preview and consent, durable work attempts, and the production OpenAI adapter with `gpt-6-luna`, prompt bundle `phase-6r-stages-v2`, and profile hash `600f82c64b1cee5ce1208133852c30bbc521b44f58a12cdace0b63ceec369dd1`. The approved limits were six calls, zero retries, and 2,000,000 tokens. Five calls were made. Both failures remain in the assessment. Raw content and pinned projections are kept outside the repository.

### Source capacity

- **Delta:** 348 readings, zero retained drawing primitives, zero tables, 2,200 × 1,700 PNG (316,545 bytes). Preparation took 0.68 s and layout 0.76 s. The first limit was native drawing primitives. Recognition completed and identified the transformer and its tag. The attribute response failed validation.
- **REX:** 304 readings, 4,629 retained primitives, zero tables, 2,200 × 1,700 PNG (693,952 bytes). Preparation took 2.07 s and layout 4.61 s. The first limit was grid components. Recognition failed validation, so attributes were blocked by the prerequisite.
- **Eaton:** 317 readings, 62 primitives, one supported table, 1,700 × 2,200 PNG (297,310 bytes). Preparation took 0.37 s and layout 0.75 s. Neither local capacity limit was reached. Both stages completed.

### Recognition, attributes and evidence

- **Equipment recall:** 4 of 6 original checklist occurrences across the three pages, compared with 3 of 6 in the first checkpoint. Eaton recovered both installed branch positions and the upstream breaker as a reference, with zero provision-only breaker proposals compared with 18 previously. The two branch observations cite distinct model readings and position identifiers. The panel bus was missed. Delta recovered its transformer. REX contributed no accepted observations.
- **Attributes:** 2 of 19 checklist assertions had the expected key, raw value and unit. Both were Eaton pole counts. The trip values were returned for both breakers with no unit, consistent with the visible `Trip` header having no amperage label. The original checklist expected amps, so both remain misses under that scoring rule. Phase count and the bus attributes were absent. No accepted attribute result was available for either transformer page.
- **Ownership:** 4 of 4 returned assertions matching a checklist item by key and source value had the expected source-local owner, or 4 of 19 across the full checklist. The two trip assertions count for ownership and fail the separate unit check. The identical breaker ratings use the shared schedule row. An additional upstream interrupting-rating assertion should be treated as unconfirmed because the source relationship between that rating and the referenced device is not explicit.
- **Evidence:** All 67 fragments in accepted results used existing pinned reading IDs. Fifty-eight passed reading/quote consistency, and nine had quote mismatches, all on Eaton attribute assertions. These are reference checks, separate from whether a fragment supports the claim. Position-specific citations improved on Eaton. Delta's recognition identified the tag by a pinned reading despite the omitted drawing primitives.
- **Validation failures:** Delta attributes and REX recognition both returned HTTP 200 and were rejected as `INVALID_PROVIDER_RESPONSE`. Measured output was below the 16,384-token cap in both cases. The runtime records the bounded failure category and usage. No failed body was retained, so the exact response defect could not be determined. No corrective call was made.

### Provider capacity and latency

- **Eaton recognition:** 139,755 request JSON bytes, 1,281 accepted response JSON bytes, 45,827 input and 1,088 output tokens, 13.136 s.
- **Eaton attributes:** 142,287 request JSON bytes, 7,582 accepted response JSON bytes, 46,579 input and 4,309 output tokens, 40.823 s.
- **Delta recognition:** 136,829 request JSON bytes, 837 accepted response JSON bytes, 45,002 input and 479 output tokens, 7.015 s.
- **Delta attributes:** 140,604 request JSON bytes, rejected response, 46,109 input and 5,700 output tokens, 58.995 s.
- **REX recognition:** 122,039 request JSON bytes, rejected response, 40,630 input and 784 output tokens, 11.000 s.

The measurements exclude the base64 image and transport envelope from request JSON bytes. Total use was 236,507 tokens and the conservative cost estimate was USD 0.0541 at the same uncached list rates as the initial checkpoint. Extraction workflow time was 55.44 s for Eaton, 67.45 s for Delta, and 14.68 s for REX, excluding local preparation and layout.

## Large-sheet boundary probes

- **Readings:** A synthetic 34 × 22-inch layout with 4,096 distinct native readings retained them all in the local layout. Preparation and layout took about 2.38 s and 2.55 s respectively, using the local fixture raster. At 4,097 readings, preparation still completed in about 2.40 s, then layout refused the full projection before table inference. Hybrid pages count both representations toward this bound. These probes made no provider calls.
- **Tables:** The 512-cell synthetic grid remains valid for local storage and the separate legacy table projection's byte limit rejects its oversized representation. The active 6R workflow sends the full page layout and readings subject to its own request cap. Exceeding optional table capacity produces an unresolved structure with all readings retained.
- **Raster:** The normal 200-DPI renderer produced a 14.96-megapixel raster for a sparse 22 × 17-inch sheet in 0.28 s and 29.92 megapixels for a 34 × 22-inch sheet in 0.42 s. The latter exceeds the 20-megapixel preparation/extraction ceiling before AI input. Sparse PNGs were 59,851 and 105,687 bytes respectively. Dense drawings may hit the deployed 2,000,000-byte PNG limit sooner.
- **AI envelope and cardinality:** The largest live request JSON was 142,287 bytes against 2 MiB, with a separate 4 MiB transport cap. The local response cap remains 512 KiB with up to 128 equipment observations, 512 registry assertions and 16 raw-unmapped assertions. The accepted live results stayed below these limits. The sample does not establish recall on high-cardinality sheets or legibility on genuinely large image-only drawings.
- **Region processing:** No evidence in this run requires region-based AI calls. The first observed larger-sheet limits were local raster pixels and reading count. If a larger authorized corpus establishes a detail or cardinality issue, first compare a bounded whole-page render and source-pinned detail regions within the same two stage requests. Any proposal should specify pixel and token budgets, how regions map to original page coordinates, how coverage is measured, and how the runtime rejects overflow without dropping content. No region processing was added.

## Verification

The focused host run on a fresh migrated PostgreSQL database passed 221 tests, with zero skipped. It covered recognition contracts and mocked transport, source limits, exact references, missing geometry, reproducibility, local layout and operation integration. The isolated Linux run with Tesseract, Redis and MinIO passed 72 tests, with zero skipped, including native/OCR preparation, layout, broker recovery and source resource identity. Existing small-document tests continued to pass.

Phase 6R-D remains pending review of this checkpoint.
