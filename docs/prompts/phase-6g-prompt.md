# PowerForge — Phase 6G: AI-Led Extraction Semantics, Grounding & Candidate Retention

**Codex implementation assignment — revised AI-first semantic interpretation policy (v2)**  
**Date:** 2026-11-10  
**Repository:** `adilzafar66/PowerForge`  
**Delivery:** Five reviewable milestones (M1–M5), with design/contract decisions documented before implementation

---

## 0. Mission and the revised phase boundary

Implement **Phase 6G** as a targeted improvement to the **existing Phase 6C/6D/6E/6F engineering-document extraction architecture**. It must solve real extraction failures caused by inadequate multi-reading grounding, conservative semantic mapping, lost raw observations, insufficient source-local equipment/tag context, and brittle table reconstruction/response handling.

The desired outcome is that PowerForge can extract source-supported observations from manufacturer drawings, transformer nameplates, panelboard submittals, and electrical equipment schedules; **let OpenAI act as the primary interpreter of equipment meaning, attributes, value expressions, qualifications, and source-local associations**; validate and normalize its proposals through source evidence and the existing registry; retain useful observations when mapping or association is uncertain; and explain where any information was rejected or lost. This is a substantive change of *semantic authority*, not permission for an AI model to invent values or establish engineer-verified truth.

**Change of roadmap:** The original Phase 6G — broad acceptance, regression, live-model accuracy benchmarking, production performance/cost/load/recovery validation, release hardening and final Phase 6 freeze — is explicitly deferred to **Phase 6H**. Phase 6G is **not** the Phase 6 freeze. Update the roadmap and implementation-status documents accordingly. The deferred spreadsheet phase **6.5** should follow **6H** and precede Phase 7 (retain the existing numbering; don't add or renumber top-level phases). Phase 6H should retain the original obligations and documented limitations, rather than silently discarding them.

**Critical constraint: preserve TWO separate extraction families.** Do **not** merge Engineering and Tables into a unified model call or shared extraction family. Keep:

```
Source processing → exact local preparation/OCR/spatial layout
     ├── Engineering: EQUIPMENT_RECOGNITION → ATTRIBUTE_EXTRACTION
     └── Tables:      TABLE_RECONSTRUCTION  → TABLE_INTERPRETATION
     → source grounding → semantic mapping → normalized candidates/evidence
```

Preserve the Documents-integrated Phase 6F UI, three-step start wizard, automatic preparation, independently selected families/runs, Candidates + Run History evidence viewer, single/bulk operations, retries and existing execution semantics. Improve the implementation behind these contracts rather than redesigning the product.

### Core outcome principles

1. **AI is the primary semantic interpreter, not merely a suggestion generator.** OpenAI interprets source-local equipment classification, manufacturer-specific attribute meaning, raw values/units and compound expressions, important conditions/qualifiers, and relationships among equipment, tags, labels and values. These remain **proposals** until validated; neither extraction output nor the model's confidence is engineer verification.
2. **Semantic proposals are affirmative evidence, not merely vetoes.** `proposed_equipment_type` and `proposed_attribute_key` can establish registry meaning when the cited document context sufficiently supports them, even if no hardcoded alias or independent deterministic semantic parser agrees. The registry's mere acceptance of a key is insufficient. Deterministic terminology rules may supply a high-precision corroboration signal, but MUST NOT be an exclusive gate.
3. **PowerForge owns verifiable constraints, not an exhaustive competing semantic interpreter.** The server checks source identity, evidence/provenance, absence of contradicted or fabricated claims, registry compatibility, type/value/units, essential qualifiers, and permitted normalization. Where semantics cannot be objectively settled by those checks, it abstains to `UNMAPPED` instead of silently rejecting a supported observation or claiming to have independently proved the model's understanding.
4. **Preserve supported raw data.** A source-supported observation should normally survive as `MAPPED`, `UNMAPPED` or `INVALID` even if classification, association or normalization cannot be completed. Do not manufacture evidence to retain it.
5. **Verify provenance rigorously.** Model-supplied aliases are not database IDs, verified geometry, literal offsets or independent OCR truth. All source text, regions, ownership and relations need explicit evidence/provenance semantics.
6. **Mechanical normalization is deterministic.** Registry membership, value type, exact decimal/integer handling, canonical unit conversions, enum/boolean validation and representability remain server-owned.
7. **Do not infer physical identity.** Source-local tag/mention/specification relationships are in Phase 6G; cross-document physical entity resolution stays in Phase 7. No canonical model writes.
8. **Retain immutable history.** New behavior requires versioned resources/profiles and a compatibility strategy, not silent mutation of the accepted v1–v6 profile/runtime meanings or historical runs.

---

## 1. Baseline, required repository inspection, and implementation approach

Use the latest completed Phase 6F implementation as the starting point. At prompt authoring, `main` did not yet contain Phase 6F and `codex/phase-6f-extraction-ui` was ahead of `main`; **verify the current branch/merge state** when starting. Prefer a new `codex/phase-6g-extraction-semantics` branch from the merged 6F baseline; otherwise explicitly document and use the reviewed Phase 6F tip, and reconcile with `main` once it is merged. Do not assume the old base commit is current.

Read the actual source before designing replacements, particularly:

- `docs/ROADMAP.md`, `docs/PROJECT_STATUS.md`, `docs/EXTRACTION.md`, `docs/PROVENANCE.md`;
- `docs/specs/phase-6-evidence-structured-extraction.md`, `decisions/ADR-008-evidence-candidate-extraction-architecture.md`, and the frozen Phase 5 registry/ADR;
- `docs/PHASE6C_HANDOFF.md`, `docs/PHASE6D_HANDOFF.md`, `docs/PHASE6E_HANDOFF.md`, `docs/PHASE6F_HANDOFF.md` and the 6F implementation prompt;
- `packages/extraction/src/powerforge_extraction/{enriched_observations,enriched_input,enriched_runtime,enriched_grounding,enriched_output,enriched_tables,enriched_publication,enriched_profiles,interpretation_v1,table_semantics,registry_context,operation_plan,operations}.py`;
- associated source preparation/layout, Pydantic contracts, persistence, AI adapter/worker, API reads and `apps/web/src/components/{extraction-evidence-panel,extraction-run-history,start-extraction-wizard}.tsx`;
- current frozen identity fixtures and evaluation/test harnesses under `tests/` and `evals/`.

**Before implementation**, produce a concise but substantive `docs/PHASE6G_PLAN.md` covering current failure points, proposed contracts, **an explicit AI-first semantic authority/admissibility policy (including examples that pass without deterministic alias recognition and examples that must abstain)**, risk/compatibility analysis, migration impact, stage/response versioning, diagnostic retention/security, milestone plan and the decisions that genuinely need approval. Update or add a focused architecture decision record if the change to semantic mapping authority materially amends accepted ADR-008; do not invent an ADR number without checking the repository. Don't alter approved Phase 5 contracts or registry-v1 merely to make examples pass.

Use targeted, meaningful tests; avoid trivial implementation prescriptions or large speculative frameworks. Implement in five reviewable milestones with clear handoffs/checkpoints. The user may review each milestone independently.

---

## 2. Phase 6G scope — required changes

### 2.1 End-to-end extraction diagnostics and loss accounting

The current failure case can report a successful Engineering recognition run but zero useful attribute candidates, while the independent Table Reconstruction run reports only broad `INVALID_PROVIDER_RESPONSE`. An engineer must be able to determine **which stage rejected what and why**.

Implement a bounded stage-level diagnostic trace that distinguishes:

1. Pinned source and preparation/layout identity (document/page/profile/attempt, without leaking storage keys).
2. Source coverage and input modality: native text, OCR, visual image, known layout structures, conflicting or unavailable readings.
3. Provider stage outcome: attempted/not attempted, success, refusal, timeout, incomplete/truncated, output-limit, transport error, schema/parse failure, unsupported source references, etc.; retain the distinction between **provider response invalidity** and **later output-conversion failure**.
4. Counts of provider-returned equipment/attribute/table observations, if parsing succeeds.
5. Counts and stable reason codes for grounding successes/failures; semantic mapped/unmapped/invalid results; detached/uncertain associations; duplicate or rejected source assertions; publication successes/failures.
6. For diagnostics, preserve model **proposed keys vs final keys**, mapping basis, reason codes, source anchor/relationship basis and qualified raw values. Avoid conflating executed/COMPLETED with extracted-complete or engineer-approved.

Support an opt-in, access-controlled way for developers to inspect **the exact versioned structured source projection, safe prompt/profile identities, and the model's parsed observations before conversion**, and correlate these to persisted candidates. When full provider payloads are needed for debugging an invalid response, require an explicit development-only/safely restricted capture mechanism with size/retention bounds, redaction/export controls and a documented confidentiality policy. No routine raw prompts, customer text/images, credentials or complete model responses in application logs/telemetry. No source object keys, raw SDK error bodies or secrets in normal APIs. The system must remain diagnosable even if the SDK cannot expose a parseable response.

Show useful reason/detail summaries in existing run-history and/or candidate diagnostics views **without adding a standalone Extraction workspace or changing the approved 6F navigation**. No large UI redesign. Allow analysis of an empty-candidate completed stage and a failed stage, both through durable records and testable APIs. Ensure revision membership/authorization and immutable historical source access rules remain enforced.

### 2.2 Multi-reading, multi-line and spatial key/value evidence

Current source fields such as `kVA:` and `350`, or `Primary:` and `600 Delta Volts`, can reside in separate PDF text runs. A single literal statement or line is not always the complete key/value expression. The implementation must ground **individual reading occurrences** and their asserted relationship independently.

Design a versioned provider-neutral source observation/evidence representation (modify the successor enriched schemas or introduce a compatible new variant) supporting:

- Multiple native/OCR reading aliases with explicit evidence roles such as label, value, unit, qualifier, tag/identity and supporting context; names are illustrative, not mandated.
- Label and value in the same line, different lines, separate text blocks, horizontal or vertical forms, multi-column layouts and true table cells/header relationships.
- Multiple source quotes/offsets/regions for one candidate; never forge a single concatenated source snippet or text offset that does not exist verbatim.
- Exact original characters and versioned artifacts. Native/OCR representation and text confidence/uncertainty must remain visible; OCR correctness cannot be inferred from literal matches to OCR output.
- A **source relationship basis** distinguishing verified local geometry/structure, explicit textual designation, image-reported layout and unresolved/inferred association. Do not mislabel a model-inferred link as geometrically proven.
- Bounded layout-based relation checks, reading-order/column constraints, competing labels, nested groups and ambiguity detection. Don't allow arbitrary aliases on distant or unrelated pages to be glued into a fabricated statement.
- Image/page-level observations when text is missing, clearly marked as visual reports with no fabricated quote, offset or bounding box.
- Mixed native/OCR conflicts, repeated values, missing positions and unaligned native readings. Retain discrepancies rather than choosing a plausible electrical number.

Use the **already pinned** prepared/spatial snapshot and alias ownership checks. Validate evidence in the existing fenced/atomic publication path, outside long-held DB locks for source bytes. Respect existing immutability, input budgets and profile identity semantics. Avoid any new default OCR policy: the Phase 6F explicit whole-page OCR override stays as approved.

### 2.3 Source-supported raw observation retention

Decouple the act of **observing** a source field from the later act of **successfully mapping it**.

- A grounded raw equipment mention or value/label pair must not be silently dropped solely because its registry key, equipment type or equipment association is unresolved. Use existing candidate `UNMAPPED`, `INVALID`, optional mention/group relationships and `UNMAPPED_OBSERVATION` facilities wherever suitable; introduce only minimal schema extensions if necessary.
- Preserve `raw_text`, separate `raw_value` and `raw_unit` when supported, exact evidence roles, model proposals, **AI-interpreted source field meaning and supported qualifiers**, ambiguity, reason codes and the source relationship's limits. Provider-interpreted values must remain distinguishable from exact printed/OCR readings and from server-normalized values.
- Record safe diagnostics for ungrounded/model-fabricated observations, schema-invalid payloads and forbidden cross-source associations. Do **not** publish them as trusted source-supported candidates merely for higher candidate counts.
- A malformed single observation should not necessarily erase other independently valid observations if per-observation rejection is compatible with the already validated stage/schema and atomic publication rules. Failed work units must never publish partial, uncommitted result sets. Explicitly document the separation between per-observation rejection and stage-level failure.
- Never create synthetic missing-value candidates, invented tags, unsupported engineering values or fabricated evidence. Existing successful results remain immutable; retries and re-extraction preserve versioned history.

### 2.4 AI-first semantic interpretation and registry mapping, with deterministic safeguards

**This is the central Phase 6G design decision.** Current `interpretation_v1.py` and `table_semantics.py` first derive equipment/attribute meaning from narrow deterministic vocabulary, and use `proposed_equipment_type` / `proposed_attribute_key` chiefly to reject disagreements. The revised implementation MUST reverse that semantic authority for **new, explicitly versioned enriched profiles**, while leaving frozen legacy behavior intact.

**Authority split (normative):**

- **OpenAI is the primary interpreter of source-local engineering meaning.** Give it meaningful responsibility for equipment classification, recognition of manufacturer-specific field labels and abbreviations, attribute-to-registry mapping, transcription/interpretation of the observed value and units, compound field decomposition, units or conditions carried by headings/adjacent labels, operating-condition qualifiers, and source-local equipment/tag/attribute association.
- **PowerForge is the authority for verifiable constraints.** Validate immutable source ownership and exact anchors, required corroborating context, registry membership/type applicability, structure/relationship evidence, contradictions, ambiguity, exact numeric/typed normalization, canonical units, bounded outputs, publication, and status. Do not treat a model's free-text assertion, confidence or mere use of an existing registry key as proof of semantic support.
- **Deterministic vocabulary is a *positive signal*, never an obligatory second interpretation.** Known labels can be resolved directly and conflicts can trigger abstention, but an otherwise sufficiently supported AI mapping must NOT be downgraded solely because `_attribute()`, `_equipment_type()`, `_field()`, `_known_field()` or an alias table could not independently derive the same meaning. Replace or bypass such gating in the new versioned interpretation path. Do not casually edit or unfreeze those existing v1 functions.
- **The server must not pretend to prove meaning from schema validity alone.** Establish a documented, testable *source-support/admissibility policy* that allows affirmative AI interpretations when anchored to a coherent equipment/field context and without contradictory source cues. When material ambiguity remains (e.g. ambiguous heading, competing equipment, uncertain unit, provisional versus nominal, unknown role), abstain or preserve a raw `UNMAPPED` observation. Provenance integrity, semantic plausibility, and engineer verification are different claims.

**Required implementation behavior:**

1. **Equipment types:** Permit a source-supported model-proposed canonical equipment type even when the literal source heading uses a different manufacturer term or only indicates a broader class. Check the complete *source-local* equipment description and corroborating attributes. If the proposed subtype is not actually justified, retain a broader/unmapped mention rather than inventing specificity. A tag prefix or model number alone is never sufficient.
2. **Attribute keys:** Accept a model-proposed registry attribute when the cited label/value and equipment context substantiate that meaning, its key belongs to the proposed/established registry equipment type, and no material qualifier contradicts it. No exact lexicon/synonym match is required. Conversely, a registry-valid but contextually incorrect key is not automatically admitted.
3. **Raw values and units:** Let OpenAI identify which printed/OCR fragments represent the label, value, unit, conditions and associated equipment. Ground those fragments separately. It may interpret a source expression (including values split across runs); it MUST NOT invent a missing digit, rating, unit, relationship or source quote. Preserve the exact raw readings and model-interpreted structure separately, including conflicts between image, OCR and native text.
4. **Compound/qualified expressions:** OpenAI may propose multiple *separately supported* semantic components (e.g. primary/secondary voltage, connection designation, normal/provisional capacity, tap positions, conditions). The server checks that each component is justified and that registry representation does not lose required qualifiers. No automatic arbitrary arithmetic, engineering-default substitution, range midpoint, guessed measured value or promotion of a provisional/estimated rating into unconditional nominal truth.
5. **Source-local association:** Permit AI-proposed field-to-equipment and explicit title-block tag association based on the whole relevant source-local drawing context. Independently check actual tag occurrence, section/page scope, competing equipment, ambiguous containers and source evidence; do not require visual proximity or literal co-occurrence on one text line. Preserve detached attributes and unassigned tags where insufficiently supported.
6. **Deterministic normalization remains definitive:** Validate registry key/type membership and use the frozen registry normalizer for `NUMBER`, `INTEGER`, `TEXT`, `ENUM`, `BOOLEAN`, `Decimal`, BIGINT, canonical unit conversions and representability. An AI-proposed normalized value must not replace server-computed normalization. Never accept type-incompatible, unknown-key or unit-incompatible mappings.
7. **Decision outcomes:**
   - `MAPPED` — source-supported interpretation, valid type/key relationship and deterministically representable normalized value.
   - `UNMAPPED` — source-supported observation but unresolved meaning, equipment context, qualifiers or representation.
   - `INVALID` — supported meaning but invalid/unrepresentable typed value under existing registry rules.
   - Rejected / quarantined diagnostic — forged, unsupported or schema-invalid *source assertion*, not a silently erased candidate or a trustworthy observation.
   Preserve original expressions and evidence for supported `UNMAPPED`/`INVALID` outputs. Do not create new canonical verification statuses.
8. **Explanations and auditability:** Persist/return bounded structured decision details sufficient to distinguish an AI-supported mapping, a deterministic-terminology mapping, an ambiguity-driven abstention, and a rejected contradiction; retain the proposed key/type, eventual key/type, reason code, qualifying source anchors and source-support basis. Use short decision codes/brief descriptions, not a request for private chain-of-thought or unbounded model reasoning. Never manufacture numerical confidence.
9. **Avoid an upstream starvation loop:** Currently the attribute-stage registry context is narrowed to equipment types already deterministically `MAPPED` by Recognition. A correctly recognized but previously `UNMAPPED` transformer heading can therefore leave Attribute Extraction without transformer definitions. New profiles MUST preserve enough bounded, trustworthy registry context for the attribute stage to propose supported keys even when prior equipment *mapping* is unresolved. Design an explicit bounded fallback (e.g. relevant supported candidates plus safe registry context), without asserting a subtype as fact or violating prompt/token budgets. Do not make deterministic recognition success a hidden prerequisite to attribute observation.
10. **Respect call boundaries:** Do not add per-attribute model-normalization calls, silent repair calls or a new provider family by default. Use existing Engineering recognition → attribute and Tables reconstruction → interpretation calls with new versioned prompts/schemas/context where justified. Additional calls require measured evidence and explicit approval.

**Source support policy MUST distinguish these examples:**

- `kVA:` plus separately positioned `350`, on a clearly identified transformer, may map to existing rated-apparent-power attributes despite no exact source-label alias, if the server can admit the relation and unit.
- `Frequency: 60 Hz` may map to an **equipment-specific** field, never revision-wide `system_frequency`.
- `Primary: 600 Delta Volts` and `Secondary: 208 Y/120 Volts` may yield source-supported voltage/connection components only when their separate semantics are justified; preserve the full original expressions.
- `12470 X 24940` is not permission to invent an unconditional single primary voltage. Report the compound source designation, qualified interpretation and any safely representable parts.
- `Impedance: 4.0–6.0%` remains a range, not an inferred midpoint or measured impedance. `IZ 6.70% at 170°C at 2000 kVA` must retain estimated/nameplate-test caveats from its drawing.
- Breaker `20 A` trip, `100` listed amps and `50 kAIC` are separate source meanings; do not invent settings or treat a series-rated assembly as an independently verified device rating.
- An unlabeled isolated `250 A`, a fabricated nameplate value, or a plausible registry key with contradictory headers must NOT become `MAPPED` simply because OpenAI proposed it.

**This is not unbounded AI authority.** OpenAI determines the *proposed semantic interpretation*. PowerForge determines whether the specific source evidence and deterministic constraints warrant publication of that interpretation. Preserve conservative abstention on genuinely unresolved meaning, but do not force all valid AI interpretations through another narrow deterministic vocabulary parser.

### 2.5 Better contextual equipment recognition and source-local tag association

An equipment drawing's identifying heading, nameplate specifications and explicit tag often appear in different page regions. Extend the existing **Engineering EQUIPMENT_RECOGNITION → ATTRIBUTE_EXTRACTION** stage contract to use corroborating **source-local** context rather than only the heading text's narrow terminology.

Required behavior:

- Treat OpenAI as the **primary source-local equipment classifier**: use headings, descriptions, nameplate form context, primary/secondary attributes, diagrams and model-proposed type together. Validate against the existing registry and actual corroborating source evidence, **without requiring an independent `_equipment_type()` lexical match**. If the source only supports a general class, do not promote a more specific registry type without justification.
- Recognize explicitly printed tags (`TAG: 80T1`, `DESIGNATION CDP-6C`) from title blocks, nameplates and related source regions, even if distant from the main specification block.
- Distinguish explicit observed tag text from inferred identity. A manufacturer catalog/model, PO, drawing number, project name, serial or unrelated upstream-device reference is **not** automatically the equipment tag.
- Establish source-local associations only when document/page scope is supported: single-equipment drawing with no competing equipment; row-specific tag in a multi-equipment schedule; explicit textual reference; proven geometry/section scope. The model's claim that two distant objects belong together is not independent evidence.
- On multi-equipment pages, competing headings or ambiguous title blocks, preserve unassigned/tagless mentions and detached attributes instead of assigning the same tag to all equipment.
- Preserve distinct equipment instances even when same model/rating repeats. Parent/source-local containment information (e.g. breakers shown inside a panelboard) may be retained as **source relation hints**, but must not generate canonical topology, physical-equipment identity or unsupported cross-run database foreign keys.
- Do not break the existing separate Engineering/Table run families. The two families may independently report their own source-local groups; any unified read-only presentation must preserve each original run/candidate's ownership rather than merging them into a fabricated shared identity.
- Do not add `Equipment`, `EquipmentAttribute`, `EquipmentLineage`, `ModelNode` or `ModelConnection` writes. No auto-accept or engineer-verified status.

For panelboards/switchboards/MCC/switchgear, respect the **actual existing canonical registry representation** (the current design consolidates these under Bus; verify the registry's exact key) rather than inventing a new `PANELBOARD` equipment type. Likewise use the actual LV/HV breaker registry types where justified.

### 2.6 Engineering and Tables must both produce useful observations

Preserve separate profile selection and execution. Improve their **existing internal** behavior:

- Engineering should retain source-supported relevant engineering observations even when a line is marked as table-contained or structured as a key/value form, while keeping intentional ownership/duplicate policy clear. Don't blindly have both families publish identical values; preserve provenance of truly distinct observations. A failure of Tables must not, merely by a preprocessing classification heuristic, erase all relevant Engineering observations from a form or nameplate.
- Tables should keep structured rows, columns, cells, spans and header paths **where demonstrably supported**. In the Table Interpretation stage, **OpenAI is also the primary interpreter of semantic field meaning and equipment/attribute mapping**; do not retain a separate deterministic-header-alias gate that vetoes otherwise supported proposals. Spatial table structure remains independently validated. Ambiguous structure must remain `UNRESOLVED`/visual-report rather than falsely proven.
- A table reconstruction failure must not be reinterpreted as proof of no engineering data. Document run status and missing dependency independently. Table Interpretation should run only after a valid committed reconstruction, per the existing safety contract.
- Single-equipment attribute-per-row forms and multi-equipment schedules both must work. Repeated item/model rows, blank/provisioned spaces, installed counts, qualifiers, multiple operating conditions and conditional headers must retain distinctions.
- Source-derived individual values can remain supported observations even when exact table row/column ownership is unresolved, provided evidence and limits are recorded. Never invent a row-to-equipment association.

Do not introduce an all-purpose unified extraction workflow, extra standing provider family, merged two-family run or hidden cross-family dependence.

### 2.7 Table Reconstruction `INVALID_PROVIDER_RESPONSE` diagnosis and reliability

In the example REX drawing, `TABLE_RECONSTRUCTION` recorded `INVALID_PROVIDER_RESPONSE` and `TABLE_INTERPRETATION` did not execute. Implement actionable failure classification **before** adding expensive retry/repair behavior:

- Differentiate structured SDK parse/schema errors, missing required fields, invalid alias/cell/header graph, bounded-response overflow, token-limit truncation/incomplete response, refusal, source-alias mismatch, conversion/grounding rejection and infrastructure/provider faults whenever technically observable.
- Log bounded, sanitized validation paths, schema/stage/profile versions and stable reason codes. Avoid leaking raw SDK error strings or customer document contents in production.
- Examine current reconstruction response schema complexity against real PDF layouts. Improve the **new versioned** response contract and/or stage instructions only when supported by regression evidence; avoid making an unsupported spatial table look verified merely to achieve schema success.
- Add deterministic tests for missing fields, invalid refs, bad cell spans, cycles, duplicate table aliases, empty valid tables, incomplete responses and an irregular/long table.
- Preserve retry budgets, no implicit repair call, no unbounded model resubmission and no publication from invalid stage output. Successful prior stages/runs remain immutable and inspectable.
- Do not claim the cause of the REX failure from `INVALID_PROVIDER_RESPONSE` alone. Demonstrate the actual subcause with diagnostic data if available; otherwise state what can/cannot be determined.

### 2.8 Native/OCR/visual modality fidelity

Retain source-kind separation and ambiguity from Phase 6E. Specifically:

- A native text quote can have verifiable literal offsets in its immutable text artifact; OCR text may match the OCR artifact while still be a recognition error; image-only readings may have page-level, not character-level proof.
- Preserve contradictory readings or conflicting source values. Do not overwrite `350` with a visually plausible different number or combine different conditions into one rating.
- Maintain exact artifact hash/size and geometry validation. Don't invent rectangles or assign arbitrary repeated occurrence offsets.
- Keep explicit OCR override behavior and current source preparation; no generalized new OCR engine, automatic per-page OCR selection redesign, or full provider-driven page image reading pipeline in 6G.

---

## 3. Illustrative contract shapes (not frozen names)

Codex must propose precise versioned Pydantic contracts consistent with existing `Enriched*` response schemas and the publisher. These examples explain **semantics**; they are not mandated wire formats and omit fields.

### 3.1 Multi-reading field observation

```json
{
  "raw_expression": "kVA: 350",
  "source_label": "kVA:",
  "raw_value": "350",
  "raw_unit": "kVA",
  "proposed_equipment_type": "TWO_WINDING_TRANSFORMER",
  "proposed_attribute_key": "rated_apparent_power",
  "evidence_parts": [
    { "role": "LABEL", "source_ref": "spatial_readings", "reading_refs": ["r_label"] },
    { "role": "VALUE", "source_ref": "spatial_readings", "reading_refs": ["r_value"] }
  ],
  "relationship_basis": "SOURCE_LAYOUT_SUPPORTED"
}
```

The literal `"kVA: 350"` **must not** be stored as a verbatim source span if it does not literally occur in any immutable source artifact. In that situation it is a logical display expression backed by **two separate citations**, with separate raw source fragments, offsets/geometry where available. The model cannot assign itself a verified `SOURCE_LAYOUT_SUPPORTED` status; the server determines or downgrades that basis from admitted source evidence. Field names/enum values are illustrative only.

### 3.2 Semantic mapping decision

```text
Model proposes (equipment type, attribute key, raw value/unit)
    ↓ validate registry membership and type/attribute applicability
    ↓ verify source-owned text/visual anchors and source-local field relationship
    ↓ treat AI interpretation as primary; admit with contextual source corroboration
    ↓ check contradictions, qualifications and competing interpretations (no alias-only gate)
    ├── unsupported/fabricated source assertion → REJECTED (diagnostic; no candidate)
    ├── source-supported but uncertain meaning → UNMAPPED (retain raw candidate)
    ├── meaning established but invalid/unrepresentable value → INVALID (retain raw candidate)
    └── meaning and representable value established → MAPPED
         ↓ deterministic exact value/unit normalization
```

Only `MAPPED` receives the corresponding typed/canonical value slots, and those slots are **computed by PowerForge, not copied from an AI-proposed normalized answer**. Raw source readings, AI-proposed interpretation, original values and source qualifiers remain independently available regardless of status. Decision diagnostics must say whether the mapping was accepted on AI-supported semantics, confirmed via deterministic terminology, abstained for ambiguity, or rejected for contradicted/unsupported source evidence.

### 3.3 Source-local association without physical identity

```text
One document/page:
  title block: TAG: 80T1
  main nameplate: DELTA DRY-TYPE TRANSFORMER
  2000 kVA ANN, 2667 kVA provisional AFN, voltage and tap specifications
    ↓ strong one-equipment drawing scope + explicit tag evidence
  source-local equipment mention, observed_tag = 80T1
  attribute candidates with separate evidence, qualifiers and source-local group

This is NOT an Equipment.id, cross-document match or canonical model update.
```

---

## 4. Mandatory example-based acceptance cases

Use the three user-supplied documents **only where explicitly available and authorized**. They contain manufacturer and project/customer details; do **not** commit the original PDFs, full raw page content or customer identifying data to the repository by default. Build **independently authored, sanitized synthetic regression fixtures** modeled on the source structures, plus a separate opt-in local evaluation using the actual supplied PDFs when permitted. If Codex cannot access these PDFs, do not claim to have run their tests; implement from the described cases and request them for a later authorized local run. Do not redefine gold labels to fit the current interpreter.

### Case A — REX transformer approval drawing, one page

Source characteristics: one dry-type three-phase isolation transformer, catalogue `BA350J-M/Y1/Z3`, 350 kVA, 600 V delta primary, 208Y/120 V secondary, 60 Hz, aluminum coils, 2.5% primary taps (two FCAN and two FCBN), 4.0–6.0% impedance **range**, 10 kV BIL, 220 °C insulation class, 150 °C rise, 99.05% minimum efficiency at 35% loading, tap schedule/terminal details. PDF separates `kVA:` from `350` and other labels/values across text runs.

Required:

- Identify the source-supported transformer mention and type; **no invented equipment tag**.
- Support multiple reading citations for the rating fields; **positively accept a justified AI-proposed mapping** for `kVA:` + `350` and other unambiguous registry-supported attributes even when deterministic alias lookup fails, while PowerForge computes the typed/canonical normalization.
- Preserve all relevant unmappable values and qualifiers, particularly the impedance range; do not collapse the range into an invented nominal impedance.
- Do not require an attribute to be on the same literal line as its label, require exact synonyms, or require prior deterministic equipment classification before OpenAI can propose a supported field. Test the failure mode in which Recognition stores an `UNMAPPED` transformer mention yet Attribute Extraction still gets bounded registry context sufficient to interpret its ratings.
- Inspect differences between model observations, grounded claims, accepted candidates and the table reconstruction outcome. An invalid table response cannot silently masquerade as a valid empty result.

### Case B — DELTA transformer nameplate drawing, one page

Source characteristics: explicit `TAG: 80T1` in the lower title block; one DELTA dry-type transformer nameplate in a different region; 2000 kVA ANN, **provisional** 2667 kVA AFN, primary `12470 X 24940` V, secondary `600Y/346`, 3 phase, 60 Hz, 6.70% `IZ` at 170 °C on 2000 kVA base; source explicitly states this impedance is an **estimate** pending production nameplate test. It also contains tap/voltage/current schedules, BIL and weight fields.

Required:

- Recognize `80T1` as the explicitly **observed** tag of the one transformer, justified by source-local drawing scope, with title-block tag evidence.
- Let OpenAI interpret the equipment's normal ANN and provisional AFN capacities as **different qualified source observations**; keep them distinct and do not overwrite the normal rating with the provisional rating. Accept justified semantic mappings absent a deterministic wording alias, but never drop the conditions to force a scalar registry field.
- Preserve compound primary/secondary voltage designations, tap positions and impedance estimation/test qualifiers. Map to existing registry fields **only where representable without loss of essential context**.
- Never call `80T1` a canonical Equipment identity or infer its match to another document.
- Negative test: similar page with two transformers and one ambiguous title-block tag must **not** tag both devices.

### Case C — Eaton distribution panelboard customer approval drawing, one page

Source characteristics: Eaton PRL2X panelboard, title-block **DESIGNATION `CDP-6C`**, 600Y/347 V three-phase four-wire service, 225 A aluminum bus, 225 A neutral, 50 kA AIC **series-rated** short-circuit rating, Main Lugs Only (MLO), enclosure `SPRINKLERPROOF`, upstream protective-device reference `PDG23G-LFD`, two installed `GBH3020` three-pole breakers (20 A Trip, `GBH` Frame, `100` in `Amps` column, 50 kAIC), and 18 one-pole `PROV` positions. Includes form-like general specifications, schedule and panel image.

Required:

- Recognize source-local panel designation `CDP-6C` and its existing **Bus**-based canonical registry representation; do not introduce a new Panelboard registry entity.
- Preserve the separate panel ratings, `SERIES_RATED` qualification, MLO configuration and upstream-protection reference without inventing an internal main breaker or asserting an unsupported electrical connection.
- Recognize **two installed, distinct** GBH3020 devices even though model/rating data match; retain independent position/quantity evidence.
- Have OpenAI interpret the schedule's headers, repeated devices, and rating roles as the primary semantic proposal; **validate** the distinction between 20 A trip, `GBH` frame, `100` listed amps, and 50 kAIC against source context. The `100` column should not silently become a particular breaker frame/trip setting without support; do not require an exact deterministic column-header synonym to recognize a semantically justified role.
- `PROV` rows are **provisioned spaces**, not 18 installed circuit breakers. Preserve the raw schedule facts; don't generate synthetic equipment.
- Preserve panelboard/branch-device source context where justified, without canonical topology or an invented cross-run FK.
- Negative test: an explicit designation on a multi-panel schedule must not be assigned to unrelated panels.

### Cross-cutting positive and negative fixtures

- Native/OCR disagreement on a numeric rating; visually plausible but unsupported value; missing text/geometry; repeat occurrence/ambiguous alias; false unit; ambiguous `AF` versus `AT`; mixed text/table form; merged header; invalid table header cycle; truncated provider response; invalid observation alias; unknown registry key; proposed key in wrong equipment type; **novel but contextually unambiguous manufacturer label that MUST map with AI-first semantics despite failed alias lookup**; **registry-valid but source-contradicted AI proposal that MUST abstain/reject**; **recognition `UNMAPPED` but later attribute proposals still receive valid registry context**; single `250 A` with no label/equipment; qualified `%Z`, temperature and base; enum/boolean and exact large integer/decimal values; same model repeated as two distinct installed devices; empty but valid page.
- Correctly report observations that exist in provider output but cannot be source-grounded, without publishing them as valid candidates.
- Assert that a `COMPLETED` stage with zero candidates can still be diagnosed and never implies extraction completeness.

Acceptance measures should distinguish raw provider observation count, grounded observation count, final candidate count, mapping/normalization accuracy, association correctness, unsupported mapped claims and rejected/lost information. Do **not** tune only for candidate count.

---

## 5. Engineering compatibility, security and resource constraints

These boundaries are **non-negotiable**:

1. **Preserve frozen v1–v6 runtime and resource meanings/IDs.** Current enriched Engineering and Tables profiles are separate v5/v6 variants. Do not edit the frozen identity resources and simply regenerate their expected hashes. Introduce versioned successor prompt/schema/profile/interpretation/grounding resources and explicit historical dispatch/compatibility as needed. Verify that in-flight and persisted old runs remain readable, retryable/executable where supported, and immutable in their original meaning. No silent fallback from missing historical resource to latest behavior.
2. **Registry-v1 and Phase 5 stay frozen.** Don't alter the canonical type catalog, add `EngineeringModel` tables, rewrite registry types, or mutate Equipment, EquipmentAttribute, EquipmentLineage, ProjectRevision, ModelNode or ModelConnection. If an example's meaning is absent from the registry, retain it as an appropriate raw/unmapped claim.
3. **Existing source ownership and evidence integrity remain authoritative.** Document-scoped results, revision-scoped read permissions, exact pinned processing/page/manifest/artifact identities, guarded source I/O, immutable publication, work-unit fences, active lease/token semantics, successful-unit selection, append-only retries, cancellation and historical run access must remain valid.
4. **Keep consent and budgets.** External OpenAI processing stays opt-in/disabled by default where currently configured. Do not introduce stealth calls, hidden repair loops, unbounded retries or automatic cloud OCR. Preserve call/token/page/input/timeout limits and worker-only OpenAI credentials.
5. **Maintain wire safety.** Pydantic structured responses, server-owned aliases/IDs, provider-neutral domain contracts, bounded diagnostic metadata, no raw SDK types in persistence, prompt-injection resistance (document text and upstream model output are untrusted data), no HTML/script interpretation from document text, correct error sanitization.
6. **Frontend preservation.** Existing Documents workspace/navigation and UX v1.19.2 remain authoritative except targeted new diagnostics presentation. Don't add a sidebar workspace, a Tables viewer tab or a merged family selector. Keep keyboard access, responsive behavior and per-run source scoping.
7. **No unauthorized scope expansion:** no cross-document entity resolution (7), SLD connectivity (8), reconciliation (9), full engineering study validation (10), engineer approval/verification (11), spreadsheet ingestion (6.5), automatic canonical writes, protection/settings domain registry extension, or study-tool integration (13).
8. **Phase 6H owns the old hardening/freeze goals.** Do not rebrand the full 6H load/cost/security/live-quality acceptance and production upgrade/restore rehearsal as completed Phase 6G tasks. Phase 6G still requires focused regression, correctness tests, and honest result reporting sufficient to ship its implementation for further evaluation.

If new ORM columns or a migration are truly necessary, explain why the existing `ExtractionCandidate`, `Evidence`, `CandidateEvidence`, `SourceGroup`, `ExtractedTable`, `ExtractionWorkUnit` and diagnostics structures cannot safely express the new behavior. Migrations must be forward-compatible and explicitly tested against 6F's schema (0017) and representative persisted history. Do not assume a migration is mandatory.

---

## 6. Milestones, acceptance gates and reviewable handoffs

### M1 — Diagnostic trace and Table Reconstruction failure classification

**Deliver:** stage-level loss accounting, safe provider/error taxonomy, bounded source/response diagnostic interfaces, visibility in existing run/evidence workflows, and regression fixtures for no-candidate engineering output + `INVALID_PROVIDER_RESPONSE` table reconstruction. Clearly distinguish failure before parse, after parse, during grounding, during interpretation and at publication.

**Gate:** A developer can inspect exactly where a synthetic REX-like observation disappears, and a Table Reconstruction failure exposes an actionable **safe subtype** instead of only an undifferentiated error; no extra OpenAI calls or routine raw customer payload logs. Historical run access unchanged.

### M2 — Multi-reading grounding, spatial relationships and raw observation preservation

**Deliver:** versioned multi-part anchors/relationship evidence; grounded label/value/unit/qualifier combinations across text runs; preservation of supported unmapped/invalid observations; modality fidelity; source-local scope improvements needed for forms/nameplates. Preserve exact per-fragment evidence, no fake concatenated native source spans.

**Gate:** REX-like `kVA:` / `350` and separated primary/secondary ratings yield traceable observations; grounding rejects forged/distant unrelated references; no regression of page-only visual evidence or OCR provenance; a semantically unknown supported value is retained rather than dropped.

### M3 — AI-assisted semantic mapping and contextual equipment/tag association

**Deliver:** new versioned **AI-first semantic interpretation policy** for both Engineering and Tables using AI equipment/attribute/value/qualifier/relationship proposals affirmatively when sufficiently source-supported; no deterministic lexical/alias-only gate; deterministic registry/typed/unit normalization, contradiction and ambiguity safeguards; bounded attribute-stage context even after unresolved recognition; contextual equipment classification; explicit title-block/designation tag association; multi-instance and source-local containment safeguards. Keep families separate and historical profiles frozen.

**Gate:** A novel, clearly grounded manufacturer label maps using the AI-proposed registry key **even when deterministic label lookup intentionally fails**; a registry-valid but source-inconsistent AI proposal is blocked; REX-like transformer attributes map where unambiguous, including when recognition had an unresolved type; DELTA-like `80T1` is associated with the correct source-local transformer with cited tag evidence; Eaton-like `CDP-6C` and two separate breaker mentions are preserved. Raw figures are source-grounded; typed normalization is server-computed; ambiguous/unrepresentable values remain unmapped; no invented tags, internal main breaker, provisional-to-nominal overwrite or canonical equipment write.

### M4 — Table response robustness and structured schedule understanding

**Deliver:** validated improvements to the separate Table Reconstruction/Interpretation stages and their versioned schemas/prompts, precise failure diagnostics, resilience for forms, one-equipment attribute tables and multi-equipment schedules; distinct installed versus provisioned devices and their qualifiers. Preserve atomicity, no automatic repair calls or relaxed fake geometry.

**Gate:** Representative valid structured responses are accepted; deliberate malformed/truncated responses are properly classified and blocked; Eaton-like breaker schedule keeps two installed devices and 18 provisioned positions distinct; Tables failure never causes unrelated Engineering observations to silently disappear.

### M5 — Focused regression corpus, integration and handoff (NOT Phase 6 freeze)

**Deliver:** source-independent annotated synthetic fixtures, explicit optional real-document test procedure, stage-by-stage before/after metrics, targeted PostgreSQL/storage/Celery integration for new contracts and recovery compatibility, independent test of versioned old-run read/retry, frontend diagnostics tests, and concise handoff. Update `docs/ROADMAP.md`, `docs/PROJECT_STATUS.md`, extraction docs and `docs/PHASE6G_HANDOFF.md` to describe 6G complete **only if gates pass**, with the original broad acceptance/hardening/freeze transparently listed under 6H.

**Gate:** All relevant targeted tests pass; legacy identity checks pass without refreshing expected hashes; 6F wizard/operations/evidence behavior still works; data is not silently lost in example cases; documented limitations and untested live-model behaviors remain explicit. No blanket claim of real-world OpenAI accuracy from synthetic/stub results.

### Milestone reporting format

For each M1–M5, report:

- Goal, implemented behavior, changed files, new/modified schema or migration and compatibility strategy.
- Tests actually executed and outcomes, distinguishing simulated provider tests from actual calls.
- Representative input → raw observation → grounded result → mapped/unmapped/invalid output examples and rejection reasons (sanitized).
- Known limitations/remaining risks, any design deviation, and a clear **ready / fixes required / blocked** milestone recommendation.
- When diagnostics/UI changes are made, include targeted actual React/browser checks; do not claim a whole UX redesign.

Do not progress through controversial contract/authority changes silently if they require changing accepted invariants: describe the decision and obtain review at the milestone boundary. Otherwise proceed autonomously with straightforward code organization.

---

## 7. Testing expectations — focused, meaningful coverage

Use existing test infrastructure and evaluation tools. Suggested cross-boundary tests:

- Strict Pydantic response/anchor validation and source ownership; cannot claim other-run reading aliases, arbitrary geometry, invented positions, missing source fragments, wrong original text or unsupported group relationships.
- End-to-end local extraction with stub OpenAI and actual source-preparation/layout artifacts in disposable Postgres/MinIO (and Celery when execution boundaries are under test): persisted raw and mapped/UNMAPPED/INVALID candidates, exact evidence, effective work-unit selection, idempotency and operation status.
- **AI-first authority tests:** a registry-valid, context-supported model proposal is `MAPPED` **despite deterministic synonym/label lookup failure**; a valid-looking but contextually wrong proposal is not `MAPPED`; no fabricated source value/unit is admitted; an unresolved equipment recognition does not starve the attribute stage of bounded permissible registry context; AI-proposed normalized numbers/units never bypass deterministic canonical conversion. Include registry-valid/supported and unsupported proposals, unknown key, wrong equipment type, competing qualifiers, absent association, mixed/native/OCR/visual evidence and exact value normalization.
- Title-block tag tests: explicit tag with one equipment, competing equipment, conflicting tags, untagged drawing, model/catalog mistaken for tag, independent source-local groups.
- Table tests for attribute-per-row, equipment-per-row, repeated part instances, `PROV`/SPARE versus installed, merged/conditional headers, uncertainty, malformed provider response and complete valid empty reconstruction.
- Document ownership, revision access/read-only, historical v1–v6 identity/read behavior, active old-run retry compatibility, cancellation and recovery guardrails touched by new code.
- Tests for diagnostic security: no source/body/secret/key leakage in ordinary status APIs/logs; bounded opt-in debug access; no cross-revision diagnostic data exposure.
- Frontend tests only where new diagnostics or statuses are displayed; don't modify unrelated Documents UI to accommodate extraction changes.

Each test should assert the exact behavior that protects against a documented failure, not a superficial snapshot. Report skipped tests, missing Tesseract/OCR identities, missing provider authorization or unavailable source PDFs honestly.

Three representative engineering PDF drawings are available under evals/extraction/real-world/phase6g/sources/:

- REX transformer drawing — multi-reading key/value grounding and semantic registry mapping.
- DELTA transformer drawing — source-local association of tag 80T1, compound ratings, and tap schedules.
- Eaton panelboard drawing — tag CDP-6C, multiple breaker instances, trip/frame distinctions, and installed versus provisioned devices.

Use these documents as representative regression cases for Phase 6G. Create independently reviewable expected-result annotations, validate the relevant extraction behavior, and preserve original source evidence.
Do not modify the PDFs or treat existing PowerForge extraction results as ground truth. Keep live OpenAI calls opt-in and preserve the established phase boundaries.

---

## 8. Deliverables and definition of done

Deliver:

1. `docs/PHASE6G_PLAN.md` — design and milestones, architecture tradeoffs, contract versions, source/mapping decision policies and migration/compatibility plan.
2. A versioned implementation of the scoped Phase 6G changes in the existing extraction packages, applicable worker/service/API and minimal Documents evidence/run-history diagnostics UI.
3. New/updated source observation, **AI-first semantic interpretation authority**, mapping, grounding, table and diagnostic contracts with Pydantic/ORM changes only where justified; explicitly document which semantic assertions rely on AI and which deterministic constraints PowerForge independently verifies.
4. Targeted, independently authored regression fixtures for the REX, DELTA and Eaton **structural scenarios** and negative variants, plus explicit instructions for authorized private testing of originals.
5. Per-milestone handoffs and `docs/PHASE6G_HANDOFF.md` documenting actual verification and known limitations.
6. Updated roadmap/phase status: **6G = extraction semantics/grounding/retention/table robustness; 6H = originally planned broad hardening/evaluation/performance/freeze; 6.5 after 6H and before 7**.

**Phase 6G succeeds when** PowerForge can retain source-supported engineering observations from complex form-like drawings, **use OpenAI as the primary semantic interpreter** of equipment types, field meanings, source values/qualifiers and source-local associations, safely accept AI-proposed registry mappings **without an obligatory deterministic synonym/label match** when the source warrants them, deterministically validate/normalize typed results, ground separate key/value/source parts without fabricated evidence, associate explicit equipment tags and repeated source-local instances correctly, diagnose failures including invalid table responses, and preserve every relevant immutable/history/security boundary of the existing dual-pipeline architecture.

**Phase 6G does not certify production extraction accuracy or freeze Phase 6.** Those original objectives remain the responsibility of **Phase 6H**.
