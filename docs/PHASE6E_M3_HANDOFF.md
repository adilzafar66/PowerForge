# Phase 6E M3 — Reusable hybrid layout

**Implemented for review, 2026-11-06.** The user authorized M3 after M2. This delivery follows [the approved plan](PHASE6E_PLAN.md) and [prompt sections 12 and 17](prompts/phase-6e-prompt.md). M4 enhanced extraction and M5 representative evaluation remain pending. Stop for M3 review before M4.

## Delivered source structure

New pure document-processing modules derive `source-spatial-layout-v1` from exact successful M2 preparation manifests and their checked immutable objects. The new contract/policy/schema/algorithm/execution identities are recorded separately in `tests/fixtures/enrichment/layout_v1_identity.json`. Accepted M1/M2 source contracts and preparation identity inputs remain unchanged.

- Every reading retains exact representation/token members, source geometry and issues. Text stays in its original native/OCR artifact. An agreement needs unique one-to-one same-page overlap, compatible baseline/direction, exact characters and nearby matching context. Native is preferred within such a cluster; both members remain available. Repeated values at different locations remain different occurrences. Split/joined readings, overprints, conflicting transcriptions and unsupported alignment do not silently merge or replace characters.
- An isolated identical native/OCR overlap lacks sufficient context to establish fusion. Both readings and their ambiguous overlap survive. Independent native structure may still be used; the redundant OCR reading carries `NATIVE_PREFERRED_UNALIGNED` and is excluded from that structural assignment. This is explicit source selection, not a second independent occurrence or character verification.
- Reading order is a partial graph: short supported baseline edges and compatible table row/column edges. PDF engine order never flattens unrelated columns into one page sequence. Missing, mirrored, slanted or unsupported native direction preserves unresolved readings.
- Native table partitions require closed borders, complete or absent internal dividers and rectangular merged components. All native segment endpoints participate; incomplete borders cannot be trimmed into a falsely complete smaller grid. Each reading must fit one cell with supported direction and no conflicting ownership. Missing dividers support merged spans only when the resulting components are rectangular and columns are actually distinguished elsewhere.
- The initial borderless path requires at least three consistently aligned rows, two or three distinctly separated columns, compatible baselines, bounded row gaps and an explicit generic label header. Four-column or otherwise competing partitions remain unresolved. It does not invent sparse borderless cells.
- Column headers require explicit conservative label cues and geometrically covering, nested spans. `Voltage` over `Primary`/`Secondary` gets distinct paths when borders establish that hierarchy. Qualified/unknown labels do not silently lose qualifiers. Attribute-row tables retain cell geometry without invented column-header inheritance. Transposed/mixed engineering meaning remains downstream work.
- Separate nearby native grids retain separate cells. A caption needs a unique nearby literal `Schedule`/`Table` title cue; table-owned readings cannot become another table's caption. Notes and unrelated values stay outside the admitted partition.

Native geometry, OCR geometry and mixed geometry have separate structural-basis labels. These are conditional source relationships, not verified engineering meaning. OCR engine confidence remains raw and uncalibrated. `NO_READINGS` means the geometry has no admitted positioned reading; it does **not** verify that the printed cell is blank. Missing geometry cannot borrow a repeated value elsewhere.

`admit_layout()` independently re-derives a proposed manifest from its exact checked source bytes. Publication performs this admission again under the current execution fence. Shape validity or a supplied cell/token alias is insufficient proof. The versioned `spatial-table-context-v1` projection contains source-local cells, header paths, raw readings, original members and raw engine confidence. It explicitly marks serialized readings as **not a printed quote** and printed text as not independently verified. M4 must adapt this into the existing table reconstruction/interpretation pipeline; M3 adds no alternative candidate pipeline, model call or evidence publisher.

## Durable execution, reuse and API

The opt-in local `source-layout-v1` profile has exactly two required same-page stages: SOURCE_PREPARE then SPATIAL_LAYOUT. It reuses the existing coordinator, durable deliveries, leases, heartbeats, bounded retries, cancellation, dependency settlement and CPU admission pool/queue. No second scheduler is introduced. Source jobs cannot publish ordinary extraction candidates, tables or AI-call records. Extraction summaries/history and every existing direct extraction endpoint retain their purpose guard.

The nested preparation component has the exact accepted M2 identity. Planning discovers a successful compatible original preparation, or accepts an explicit selection covering every chosen page, and pins its result/hash before admission. A reuse stage commits a direct immutable receipt retaining the actual original producer, rather than fabricating an OCR result owned by the new run. Receipts cannot point to receipts. Layout consumes only its successfully committed same-run/page preparation stage. Retry does not select a newer result, repeat OCR or substitute missing/corrupt source objects. Changing layout rules alone can reuse an unchanged compatible preparation; changing material preparation inputs requires another preparation identity.

Forward migration **0015** adds `source_preparation_receipts` and `source_spatial_results`, composite owned-source references, fixed stage-plan/metadata guards, current-lease publication fences and immutable history. Layout completion requires committed spatial output. Original preparation and reuse cannot both be claimed by the same unit. Downgrade preserves M2 rows when no layout history exists and refuses to discard layout history. Earlier migrations are unchanged; historical 0014 tests now explicitly target 0014 rather than the moving latest head.

The existing source-enrichment prefix remains:

```text
/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/source-enrichment
```

`GET /profiles` now includes preparation-only and preparation/layout choices. Start a layout run using the existing `POST /runs`:

```json
{
  "profile_key": "source-layout-v1",
  "processing_run_id": "<completed processing run UUID>",
  "pages": [1],
  "force_ocr_pages": [],
  "mode": "ensure"
}
```

Optional `prepared_result_ids` selects exact successful original preparations for **all** selected pages. Without it, exact compatible successful preparations are discovered automatically. `ensure` remains stable after successful preparation; automatic discovery does not change the run's input identity halfway through execution. `reextract` deliberately creates new history after a terminal run. The preparation-only default and M2 workflow remain available.

Run detail includes original `results`, explicit `preparation_receipts` and `spatial_results`. A reused result identifies its true producer and `reused=true`. Its original usage remains visible, while the current run's confirmed OCR count excludes inherited invocations. New GET routes are `/runs/{run_id}/spatial-results/{result_id}` and its `/artifact` suffix. Signed artifacts verify the exact stored hash/size first. Original prepared results/artifacts can be read through a **completed receipt**, not merely through an admitted selection or an unrelated result on the same document. All reads enforce current document membership, purpose, exact run/result scope and successful producer state; GET performs no recognition.

Use the existing disabled-by-default local deployment configuration and rebuilt source worker described in the [M2 handoff](PHASE6E_M2_HANDOFF.md). M3 does not enable enrichment in the actual environment or change running application services. Hybrid native-plus-raster coverage remains UNKNOWN; scanned schedules on those pages still require explicit `force_ocr_pages`. Source preparation/layout is one backend operation here; enhanced extraction remains a separate future M4 request, consistent with the approved coherent 6F guided workflow.

## Bounds and observed improvement

V1 admits at most 4,096 selected readings, 32,768 overlap pairs, 8,192 order edges, 2,048 native segments, eight tables and 512 total cells per page; table bounds are 128 rows and 32 columns. Overflow fails explicitly without truncation. The canonical layout is bounded to 4 MiB; the downstream projection has its own 128 KiB cap. The tested 512-cell native grid is 480,220 canonical bytes and fits storage, while its deliberately long provider projection is rejected by the separate cap.

The profile retains the configured M2 bounds of at most 50 pages, three attempts, 150 total local stage admissions and one concurrent local unit. Both stages consume that shared admission budget; it is not a guarantee of three retries for every page at the largest batch size. Preparation keeps its 120-second limit; the layout profile specifies a 30-second budget and a 45-second publication deadline including fencing allowance. The shared Celery source task retains its existing 120-second soft/150-second hard outer limits; stale layout output is fenced at the earlier layout deadline. Local usage reports measured elapsed/Python CPU time and bytes; no OpenAI tokens, calibrated correctness score or invented operating cost is generated.

The exact existing 6D `positioned_schedule.pdf` and its unchanged independently authored visible-source cell/header gold are compared with the unchanged delimiter recognizer. The delimiter path abstains. The new native geometry path establishes **one 2×2 partition, four exact cell readings, and two correct data-cell/header paths**, plus the separately scoped schedule caption. Its eight readings produce a 6,189-byte manifest and 2,265-byte projection. A local illustrative preparation/derive/projection measurement took 69 ms; this is not a production latency benchmark. The old report and its conservative reliability labels remain unchanged. M3 does not claim newly mapped engineering candidates or measured production accuracy from that structural improvement.

## Actual verification and limitations

All **48 new M3 tests pass** across the final targeted verification. They cover independently drawn PDFs, the accepted 6D PDF/gold, merged and attribute-row grids, separate tables/notes/columns, repeated readings, slightly shifted native/OCR boxes, supplementary OCR, image-only geometry, actual Tesseract schedule recognition, sparse/missing geometry, conflicting/overprinted text, incomplete borders, competing partitions, qualified headers, source/geometry mutation, bounds, fixed profile identity, real publication/read/signing, reuse, missing pinned objects, retry, cancellation, immutable history and real killed-worker recovery without another OCR invocation. Fresh and published-0014 upgrade/downgrade/re-upgrade tests preserve original source/result/artifact/control rows exactly.

The final Linux infrastructure gate passed **369 tests**; its three additional legacy PNG byte-reproduction assertions differ on Linux and pass in the accepted host environment, where the complete **41-test** legacy engineering-evaluation module passes. Thus all **372 distinct selected tests** pass in their applicable environments; the Linux aggregate is not reported as an all-green run. The remaining difference is lossless PNG compression: host Pillow uses `1.3.1.zlib-ng`, while the Linux acceptance container uses `1.2.13`. Aligning Pillow to 12.3.0 alone does not make those historical compressed bytes identical. No frozen image/hash/gold was refreshed. These are existing Phase 3 re-encoding assertions, not M3 source substitution: M3 consumes and verifies the exact committed artifact bytes. Cross-platform processing-byte reproducibility remains a packaging concern to carry into M5/6G.

The targeted gate includes real PostgreSQL, private Redis, MinIO, Celery/beat, native parsing, Tesseract, source and extraction lifecycle/purpose checks, accepted profile readers and both evaluators. The final run uses explicit workspace imports and an isolated test broker; an earlier aggregate exposed stale installed-module and queue interference and was corrected. The strengthened explicit original-gold comparison was subsequently rechecked independently. The acceptance container is bounded to one CPU/1 GiB. No paid provider calls or unrelated frontend/full backend suite were run.

Five package wheels build. Direct-wheel execution reproduces new layout resources, preparation identities, all accepted v1–v4 profile/runtime wires and both complete frozen 6C/6D reports. It also derives the actual accepted PDF layout from packaged code. The rebuilt OCR worker reproduces the exact accepted Tesseract binary/data/settings identity; M1/M2 records remain unchanged. Ruff, changed-file formatting, dependency and whitespace checks pass. Temporary test workers, broker, buckets and disposable databases are cleaned up; existing development application data/services remain intact.

This initial deterministic scope deliberately leaves irregular/open grids, ambiguous header qualifiers, uncertain orientation, large competing borderless partitions and unsupported ownership unresolved. It does not establish general multi-column page reading order, arbitrary header languages, physical equipment identity, native/OCR character agreement without sufficient support, or cross-page table stitching. M4 must consume the committed structures through new versioned extraction/evidence adapters without bypassing 6C/6D conservative semantics. M5 must evaluate representative OCR/layout and downstream quality; a functional authored scan is not a production accuracy result.

## Review carry-forward requirements

The M3 review accepts the existing design and records three requirements for the next milestones:

1. Before M4 changes accepted M3 runtime inputs, preserve the exact source identities from `e642a78`. The execution identity hashes `layout_profiles.py`, `layout_service.py`, `layout_execution.py` and `layout_sources.py`; retain their accepted bytes as packaged identity data before compatible shared edits, as for 6D/M2. Retain algorithm/contract/policy inputs if changed, use successor versions for material new semantics, and verify old active M3 execution and wheel identities without updating accepted fixtures merely to accommodate edits.
2. M5 must measure how often representative electrical schedules fall outside the simple borderless detector's repeated alignment, row/column count, header and spacing assumptions. Report unsupported cases as misses/unresolved observations with explicit denominators and coverage strata. Real-document testing remains subject to authorization; authored fixtures alone do not establish real-world coverage.
3. M4 must keep structural evidence separate from recognition correctness through mapping and public evidence reads. An OCR table can have correct cells/header paths and incorrect numbers. Preserve the exact recognized source, raw confidence and recognition limits; a registry-valid mapping does not independently verify printed text. Test a plausible numeric OCR error in a structurally correct table without silently correcting the reading or upgrading its verification status.

These are M4/M5 implementation and acceptance requirements, not an M3 redesign. See the corresponding gates in [the plan](PHASE6E_PLAN.md).

M4 was subsequently authorized and delivered for review. See the [M4 handoff](PHASE6E_M4_HANDOFF.md).
