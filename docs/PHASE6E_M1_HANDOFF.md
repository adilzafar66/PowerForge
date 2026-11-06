# Phase 6E M1 — Spatial source contracts and geometry

**Status:** M1 implemented for review, 2026-11-06 (America/Vancouver). Branch: `codex/phase-6e-ocr-layout`, created from `main` at `b728c350b23fa59864a0dae2e623ed6fef4205ab`, including accepted 6D M1–M4. The user's three planning clarifications were preserved on the branch. Authority: [6E prompt](prompts/phase-6e-prompt.md) and [approved plan](PHASE6E_PLAN.md). **M2–M5 are not implemented.** No production OCR, native PDF extraction adapter, database schema, API, worker task or enhanced extraction profile is added by M1.

## Delivered boundary

New modules under `powerforge_provenance` provide pure versioned spatial source shapes, strict geometry, immutable artifact/producer identities, exact text-occurrence validation, conditional native-offset correspondence and detached source-binding/support validation. `powerforge_ai.ocr` provides a separate typed positioned-OCR protocol; the existing generic `OCRProvider` and all old exports remain unchanged. Neither package gains a runtime dependency. The provenance wheel now includes `resources/spatial_v1.json` as identity data.

The modules are:

- `spatial_base`: immutable strict types, bounded exact decimal input, codepoint spans, canonical Unicode JSON identities, packaged policy and direct instance revalidation.
- `spatial_geometry`: coordinate frames/rectangles/points, explicit crop/content regions, scale, mirrors, quarter turns, normalized upright geometry, convex quads and bounded support unions.
- `spatial_sources`: original/page/artifact descriptors, producer/configuration identity, native/OCR tokens, lines, blocks, raw engine confidence, native primitives, positioned text, prepared manifests and preparation input identity.
- `spatial_offsets`: exact literal occurrence results, native origin datasets/emission witnesses and correspondence based on shared source origins rather than equal text.
- `spatial_layout`: versioned region/relation shapes, exact prepared/spatial result bindings and source support resolution. These are not table-detection or fusion algorithms.
- `spatial_identity`: source/resource fingerprints for the new contract family.
- `powerforge_ai.ocr`: immutable request/settings/language-data/build identity, raw words/boxes/hierarchy/confidence, usage, safe failure categories and `PositionedOCRProvider`. No concrete provider implementation exists yet.

Closed models reject unsupported fields/versions/roles and coercive scalar input. Collections are immutable tuples. Resolver boundaries revalidate model instances, including nested instances, rather than serializing forged `model_copy()` values first: Pydantic integer serialization can otherwise turn a boolean into an integer. No new model field changes an accepted SourceLocation, Region, observation, profile or persistence contract.

## Source identity, reliability and limits

Page ownership pins the document, completed-base-processing identity, stable page and page number. Original bytes, selected base artifacts, preparation/configuration identities, producer run/work unit/result, text artifacts and positioned bodies remain distinct. Detached loaders check actual supplied geometry/text bytes against selected hashes/sizes and validate the body/producer/frame against the manifest. Derived OCR rasters must be explicit members of the same prepared producer's snapshot. Image decoding and producer completion/authentication are M2 responsibilities; descriptor validity alone does not prove a valid image/PDF or successful source job.

Native text and OCR text cannot be relabeled as one another. OCR geometry requires the exact declared input image and its pixel frame; native PDF geometry requires PDF points and a selected original PDF. Upright target units match the original format. Native vector primitives cannot be attributed to OCR. Tokens retain exact raw spelling, source occurrence, engine order, optional box/quad and unavailable-geometry reason. Lines preserve an optional engine direction vector separately from ordering. There is no spelling correction, numeric normalization, physical identity or registry interpretation.

Confidence retains a declared engine scale/method and can be null. It is not a calibrated engineering probability. The OCR protocol binds response request/image/settings/build identity, word bounds and traversal indices; raw image bytes are excluded from request dumps and repr. Usage contains only local invocation/time/optional CPU/memory observations, not AI tokens or fabricated provider prices. Blank OCR output is representable as an empty word tuple after a real invocation; this contract does not perform that invocation.

Prepared manifests record an OCR decision/reason and literal `text_coverage=UNKNOWN`. They cannot encode a guessed percentage; OCR representations require a consistent RUN decision. **No eligibility thresholds or meaningful-text detector is implemented or frozen by M1.** M2 must establish observable eligibility rules as clarified by the user. Backend purpose separation/direct-ID endpoint enforcement also remains M2/M4 work; a typed producer-purpose field is not a substitute for those service checks.

The packaged contract limits are 50 selected pages, eight representations/page, four declared derived OCR rasters, 20 million pixels/32 MiB encoded raster, 200,000 text codepoints, 20,000 tokens, 5,000 lines, 1,000 blocks, 2,048 native primitives, 64 spatial regions, 512 relations/support references and a 4 MiB canonical UTF-8 manifest bound. Individual readings retain a 2,000-character bound. Counts and bytes are independent: legal individual counts do not excuse an overflowed full body. Prepared manifests bound aggregate character/token/line/block/primitive counts and geometry bytes across all representations on a page. Detached loading verifies every declared count against the actual pinned body and text, so underreporting cannot bypass the page budget. No truncation is performed.

A minimally populated **20,000-token** positioned body measures **3,708,510 bytes**, within 4 MiB. The six small fixture bodies range from **2,673 to 3,380 bytes**. A separate Unicode-heavy case exceeds the byte limit with legal token and character counts and is rejected. These measurements are contract payload measurements, not recognition throughput or model-context capacity. M4 must still separately bound provider projections.

## Geometry and offset semantics

Input coordinates use bounded decimal strings/integers/Decimal, rejecting floats, booleans, nonfinite or excessive-precision values. Source coordinate precision is bounded to 32 digits/18 fractional decimal places; normalized output uses 12 decimal places with half-even rounding under a controlled local Decimal context. Crop/padding, source/target frames and reflection/quarter-turn transforms are explicit. Negative PDF frame origins are supported. Off-page, degenerate, crossed/unsupported geometry is rejected rather than clamped or padded into a plausible location. Quads use perimeter ordering; an adapter must translate a library's vertex ordering explicitly.

Supported token/primitive references resolve to their actual transformed support envelope. A degenerate segment cannot invent a positive-area region; missing token geometry remains null. A union may enclose separated readings, but **never establishes table, row, equipment or semantic ownership**. The M1 resolution always returns `structure_basis=UNRESOLVED` and `printed_text_independently_verified=false`. Relation metadata vocabulary includes future supported/visual/unresolved bases, but shape acceptance is not proof of those assertions; actual admission belongs to M3/M4.

Literal matching verifies exact selected UTF-8 bytes and Unicode-codepoint occurrences. Repeated matches return AMBIGUOUS unless a selected source interval identifies one occurrence. This is not geometric correspondence. Conditional native mapping requires consistent traces into the same immutable native-origin dataset, exact artifact ownership/hashes, source-origin ranges/content and a contiguous matching target interval. Reordered equal readings map through their distinct origin identity, not the first substring. OCR cannot supply offsets into native artifacts.

**Existing Phase 3 text has no original native-origin witness.** Equal page text or a newly sorted extraction must not manufacture one retrospectively. Without the appropriate producer witness, mapping remains UNPROVEN and consumers must cite their own versioned positioned text or keep legacy offsets null. The pure trace checker validates supplied witness consistency; it cannot independently authenticate the PDF engine, original producer, storage availability, access or committed success. Those checks remain mandatory at M2/M4 boundaries.

## Resources and historical compatibility

New contract family: `spatial-source-contracts-v1`; spatial rules hash **`93bd7d7b3d9a908bb1e87d8126280303206afbe5f9be92ff38c05864c9381b6d`**. New protocol family: `positioned-ocr-provider-v1`; OCR rules hash **`15b084ee9c583ffee330d4cf7f2f2851f8e7c54f87ef3f5b19bb8e1c75d524e1`**. Policy, request/response and selected nested schema hashes plus payload measurements are pinned in `tests/fixtures/enrichment/spatial_v1_identity.json`.

Six independently authored contract cases cover native repeated values, uncertain OCR notation, Unicode, unavailable geometry, merged/sparse native support and the existing 6D native text/PDF reference. The native reference retains real source hashes with explicitly authored rounded geometry constants; it is not output from a new extraction adapter or an accuracy benchmark. Placeholder raster descriptors test shape/provenance consistency and are not claimed to be decoded PNGs. No OCR/PDF processing ran to generate gold expected values.

The new identity fixture also pins **130 accepted source/resource/fixture files** from 6C/6D and the prior AI/provenance contracts, including both unchanged evaluators and their corpora/reports. No accepted fixture is refreshed. All existing extraction/grounding/interpretation/profile/runtime source bytes stay unchanged, so M1 needs no retained-runtime archive. **Before M2 edits shared runtime files, implement the plan's explicit v4 retained-source identity strategy.** Do not use M1's additions as permission to update old profile hashes or change historical behavior.

## Actual verification

**92 focused tests passed, no skips or warnings, in 0.70 seconds:**

```sh
.venv/bin/pytest -q tests/test_spatial_geometry.py tests/test_spatial_offsets.py \
  tests/test_spatial_sources.py tests/test_spatial_resources.py tests/test_ocr_contracts.py --tb=short
```

They cover eight image orientations, crop/padding/scaling/nonzero PDF origins, Unicode/combining characters, repeated and missing/ambiguous occurrences, missing/inconsistent native witnesses, OCR/native separation, invalid/off-page/nonfinite/swapped/crossed geometry, engine direction, foreign producer/page/artifact/frame/token references, null geometry, native/OCR hybrid support, sparse native primitives, cyclic headers/order/containment, explicit derived raster selection, exact bindings and no fallback to current results, material settings/data identities, raw uncertain OCR text/confidence, safe failure categories, independent count/byte bounds, aggregate native/OCR page budgets, rejection of underreported descriptor counts and package/resource/schema identities. A subprocess blocks ORM, processing, image/PDF libraries, registry, task and vendor SDK imports while loading the new contracts.

Provenance and AI wheels build with isolated build dependencies. A fresh Python process directly imports the new modules from those wheel archives, reproduces their packaged policy/source/schema identities and loads all six detached fixtures. In the same wheel context, accepted v1/v2/v3/v4 profile wires/hashes/resources and both complete 6C/6D scripted reports reproduce exactly; future source/enhanced profiles remain unregistered.

```sh
.venv/bin/python -m pip wheel --no-deps packages/provenance packages/ai \
  --wheel-dir /tmp/powerforge-phase6e-m1-wheels
.venv/bin/python /tmp/powerforge-phase6e-m1-verify-wheels.py
.venv/bin/ruff check packages/provenance/src/powerforge_provenance/spatial_*.py \
  packages/ai/src/powerforge_ai/ocr.py tests/spatial_support.py \
  tests/test_spatial_*.py tests/test_ocr_contracts.py
.venv/bin/ruff format --check packages/provenance/src/powerforge_provenance/spatial_*.py \
  packages/ai/src/powerforge_ai/ocr.py tests/spatial_support.py \
  tests/test_spatial_*.py tests/test_ocr_contracts.py
.venv/bin/python -m pip check
git diff --check
```

The wheel-check script is a temporary verification artifact, not a repository runtime dependency. Lint, formatting, dependency and whitespace checks pass. Generated build output is removed. No database, migration, Celery/Redis/MinIO integration, frontend/browser test, actual native adapter/OCR execution, dependency installation into the application environment or paid provider call was performed. Existing backend/integration results remain historical evidence, not a new full regression run. M1's compatibility claim is byte/identity/wire/report preservation; real old active-run lifecycle regression belongs to M2/M4 when shared execution changes.

**Stop for M1 review before M2.** The next milestone must implement actual PyMuPDF/Tesseract adapters, independently versioned durable artifacts, local execution purpose and CPU scheduling, observable eligibility, real integration/deployment tests and purpose checks on every read/mutation path. The approved backend enrichment-before-extraction ordering must remain compatible with a coherent future guided 6F UI. M1 does not provide functional OCR or complete Phase 6E.
