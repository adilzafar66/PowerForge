# F1-B equipment recognition review gate

This review covers the engineering expectations, offline scoring, matched inputs and proposed provider budget. Live baseline measurements and Stage 1 corrections depend on approval. The production extraction path and approved F1-A fixtures are unchanged.

[Investigation baseline](../EXTRACTION_QUALITY_INVESTIGATION.md) · [F1-A](../f1a/REPORT.md) · [F1-A2](../f1a/F1_A2_REPORT.md) · [Table ablation](../f1a/TABLE_ABLATION_REPORT.md)

## Engineering expectations

The seven development pages contain **22 definite page-local observations and 41 exception anchors**. I visually reviewed the original PDFs before assigning expectations. The fixture pins each original and its approved source-level fixture by SHA-256. Equipment and tag anchors are linked to the existing source annotation IDs. Positions identify occurrences within the page. Repeating a model, description, tag or page-local identifier carries no cross-page identity claim.

- **Delta** · One 80T1 transformer. The nameplate is a drawing and does not establish installation. The primary and secondary winding descriptions, tap slots and two cooling ratings belong to the same equipment.
- **Eaton** · One CDP-6C proposed assembly, two proposed GBH3020 breakers separately anchored to slots 1/3/5 and 2/4/6, and one upstream PDG23G-LFD reference. Review whether the assembly Designation should be scored as its tag. The explicit Panel ID Nameplate field is blank. The drawing bears a confidentiality notice. Eighteen individual PROV positions, their quantity summary, and the 0-pole main-lugs summary have separate exclusions.
- **REX** · One proposed transformer in the approval drawing. BA350J-M/Y1/Z3 is a catalog number. The wiring options and tap positions are subordinate to that equipment.
- **Schneider** · One proposed 800a MDB assembly and eight individually supported branch breaker positions. Positions 7 and 10 are exceptions because the PS accessory and dashed symbols indicate prepared space. Circuit 9's markup is separate evidence about its trip unit. The branch summation corroborates counts while the schedule supplies occurrence identity.
- **Siemens** · One DMR-MAIN assembly, one Section #1 WL breaker and three Section #2 branch breakers. The BOM does not establish installation. ETU745 is supported as a trip unit on WL. The CT/PT provision, fillers and future extension have exclusion anchors. The utility option and dry-type transformer connection are recorded as ambiguous potential references so they cannot become definite devices or false positives by assumption.
- **Simson** · One generator-family reference on each of the two datasheet pages. S7L1D-G4 Wdg.07 identifies a model/configuration. Continuation pages, alternative bearing columns and internal components carry no additional physical asset claims.

The proposed qualification of Eaton, Schneider and REX follows their approval or quote context. Delta and Siemens use UNKNOWN where the sheet does not establish lifecycle status. Simson uses REFERENCE for manufacturer product data. These are explicit scoring decisions for human review. Equipment positions are distinct from tags, and no installed status is inferred from drawing symbols alone.

The pinned **structural control** is the repository's single-page positioned transformer schedule. A separate **synthetic holdout** uses pages 1, 3, 8 and 10 of the repository electrical fixture PDF, covering borderless layout, merged headers, a scan and a diagram with no device. These inputs are familiar to the layout regression suite and reserved from Stage 1 prompt tuning and selection. They cannot establish generalization to independently sourced engineering drawings. A real held-out outlined drawing and engineering schedules require separately provided or approved sources. The seven-page development set and the earlier Schneider concurrency pages cannot fill that role.

[Machine-readable engineering ground truth](occurrence-gold.json)

## Baseline investigation and measurement

Existing guidance already instructs the model to preserve repeated and tag-less equipment, reject bare provisions, treat an aggregate as context, and keep an assembly tag on the assembly. The prior investigation identified failures despite those instructions. On the historical Schneider corpus, circuit 62 was taken as an installed breaker, a continuation summary was promoted to quantity-group breakers in one run, and other schedules had omissions or repeated observations. [Historical trace](../EXTRACTION_QUALITY_INVESTIGATION.md)

Those findings inform the categories below. They are separate from an F1-B baseline. The replacement 800a MDB PDF's raster fingerprint differed from each of the nine earlier Schneider benchmark pages in a local comparison. No historical count has been substituted into the new denominator.

The scorer credits a location only when a source-derived reading region or a bounded reported visual region supports a unique occurrence-specific anchor. It records approximate visual support separately from exact source resolution. A whole-page citation and text similarity alone earn no match. Type, model, tag and qualification do not select the occurrence. Localized claims from multiple observations at one occurrence credit occurrence recall once and count additional duplicate claims. Disagreeing field values go to review. Observations supported only at a provision, aggregate or component are reported separately. Gold-ambiguous references are excluded from strict precision and kept in the adjudication ledger. An observation with weak evidence stays unverified until a reviewer establishes whether the claim was invented or reported without adequate support.

The signed-off benchmark will report micro precision, recall and F1, per-page error records, matched field accuracy, tag-association errors, provision and aggregate errors, duplicate count, precise and approximate evidence, and unsupported observations that a reviewer confirms. Failed attempts remain in end-to-end denominators and are also reported separately from recognition misses in admitted results. A pinned source check, prepared position/evidence availability, provider status and original audit output, Stage 1 admission, and the published candidates/evidence are distinct trace points. Stage 1 admission remains all-or-nothing. The existing Stage 2 assertion quarantine remains outside this change.

Preflight built **12 matched Stage 1 request pairs** through the production builder in a network-disabled worker. The arms agreed on source and image digests, reading IDs and coordinates, alternate texts, overlap witnesses, registry, prompt, schema, model settings and budgets. It prepared **24 bodies from 48,947 to 1,076,447 bytes**. The structural control emitted one table. The table-enabled path also emitted a table on each held-out structured page 1, 3 and 8. The empty diagram emitted none. These are preflight checks, with zero provider observations and zero evaluation results yet. [Preflight measurements](preflight.json)

## Proposed controlled evaluation and approval

Use the current server-owned Stage 1 contract and prompt with GPT-6 Luna Standard, the current Stage 1 default reasoning setting, 16,384 output tokens and 100 seconds. The evaluated arms keep source text, exact reading identities and original image fixed. Select native for five development documents. Select pinned 300 DPI full-page line-removal OCR for the text-poor Schneider page based on F1-A2. Use pinned 300 DPI OCR for the synthetic scanned holdout. Table-free preparation skips native primitives and table inference, retaining engine reading order. Confirm the current baseline and request digests again before dispatch. Keep Stage 2 provider execution out of the isolated Stage 1 benchmark.

1. **Baseline and ablation** · Seven development pages plus one clean ruled structural control. Two fresh attempts per page per arm, alternating arm order. **32 calls**. Compare paired deltas and repeated observations without treating two repeats as a generalizable accuracy estimate.
2. **Development correction** · Proceed only for a supported, actionable error. Freeze one versioned, opt-in Stage 1 correction and test it twice on seven development pages using the selected preparation arm. **Up to 14 calls**. Keep instructions, admission and publication changes attributable to measured failure modes. If a new correction requires a different call matrix, return to review.
3. **Held-out check** · Two attempts for the unmodified prompt and the frozen correction on each of four synthetic pages, with the same preparation in the pair. **Up to 16 calls**. Do not use these results to iterate the prompt. A subsequent real held-out test and Stage 2 table ablation need their own source list and authorization.

The proposed ceiling is **62 calls, zero automatic retries, US$34 maximum**. A Stage 1 planning scenario of 15,000–45,000 input and 1,000–6,000 output tokens per call gives approximately **US$0.24–0.81 total** at short-context Standard rates, conservatively adding the listed cache-write price to the input rate. This scenario is a planning assumption. Reserve **US$0.5332668 per call** using 1.05M input tokens at the long-context input and cache-write rates, 16,384 output tokens at the long-context rate and the 10% regional premium. The maximum reservation for 62 calls is **US$33.0625416**. At preflight, refresh price availability and use the more conservative applicable reservation. Record measured usage, cache state, latency and cost for each send. An unknown provider outcome consumes its reservation and cannot cause an automatic duplicate. [GPT-6 Luna official rates and context limits](https://developers.openai.com/api/docs/models/gpt-6-luna)

**Approval required** · Confirm the engineering expectations and authorize sending the seven listed development pages and five repository synthetic pages under the proposed caps. Confirm the Eaton approval drawing may be shared despite its notice, or identify an exclusion. Real held-out sources are outside this authorization. Controlled AI observations are required before claiming a recognition improvement or selecting the F1-C preparation configuration.

## Reproduce the offline checks

```sh
.venv/bin/python evals/phase6r/f1b/occurrence_eval.py \
  /Users/adilzafar/Downloads/equipment-drawings

PYTHONPATH=evals/phase6r/f1a .venv/bin/python evals/phase6r/f1b/stage1_preflight.py \
  /Users/adilzafar/Downloads/equipment-drawings /tmp/f1b-preflight.json

PYTHONPATH=evals/phase6r/f1a .venv/bin/python -m pytest -q \
  evals/phase6r/f1b evals/phase6r/f1a tests/test_spatial_layout.py \
  tests/test_extraction_compact_context.py
```

Preflight requires the local Tesseract 5 worker runtime or the explicit `--tesseract` and `--tessdata` paths. It has no live transport. It checks PDF and fixture pins and uses production serialization in memory. The retained results contain size, identity and matched-control metadata. The observation replay helper expects the operator to verify the original output bytes against the audit receipt before supplying them. Its unit test verifies exact reading localization and rejects a mismatched dispatch digest. The focused suite passed **71 tests**.
