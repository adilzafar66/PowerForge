# PowerForge Phase 6R — AI-First Extraction Redesign

**Implementation Strategy and Architectural Specification**

| Field | Value |
|---|---|
| Status | Agreed target architecture and clean-reset implementation strategy, incorporating approved 6R-A clarifications; database reset requires explicit environment authorization |
| Date | 2026-11-13 |
| Proposed development branch | `codex/phase-6r-ai-first-redesign` |
| Base branch | `main` (includes Phase 6F) |
| Scope | Clean replacement of Phase 6 extraction code, contracts, UI, documentation, and database schema; unified extraction of prose, diagrams, and tables |
| Phase 7 boundary | Cross-page/entity identity resolution remains Phase 7 |
| Data policy | **No existing-data preservation, migration, read compatibility, or legacy execution support**; reset the entire target application database |
| Suggested repository location | `docs/PHASE6R_IMPLEMENTATION_STRATEGY.md` |

> **Purpose:** Define how to replace the current Phase 6 extraction architecture with a simpler AI-first design while preserving reusable infrastructure and the canonical engineering model **design**, but replacing obsolete code and rebuilding the application database from empty. This document describes intended behavior and implementation boundaries; it is not a claim that Phase 6R has been implemented.

**Approved clarification update — 2026-11-13:** The decisions below incorporate the approved clarifications recorded in section 8.1 of `docs/PHASE6R_IMPLEMENTATION_PLAN.md`. They are architectural requirements, not unresolved options. Final wire shapes, explicit limits and other low-level details are to be completed in 6R-A using reasonable engineering judgment within these boundaries. Numerical quality targets remain provisional until representative live results, corpus sizes and evaluation procedures have been reviewed; freeze final gates before the separate held-out evaluation. This update does not begin application implementation or authorize a database reset or an unspecified live-source run.

---

## 1. Executive decision

**Implement Phase 6R on a new branch created from `main`. Do not restart from Phase 5, Phase 6E, or Phase 6G.** The strategy is a **selective rebuild**, not a wholesale rollback or an attempt to patch every part of the existing pipeline.

- **Preserve:** document ingestion and processing, source enrichment, OCR, spatial/layout inputs, storage, execution infrastructure, source provenance, candidate/run persistence foundations, and the reusable Phase 6F Documents UI.
- **Replace:** model prompts/contracts, equipment and attribute extraction interpretation, grounding policy, extraction output conversion, and the extraction-specific portions of orchestration and UI.
- **Remove completely:** separate Engineering and Tables extraction families, table-reconstruction/table-interpretation model stages, deterministic semantic/association interpretation, historical extraction adapters, compatibility paths, and extraction-specific table workflows.
- **Keep:** table *layout data* produced locally, because the unified AI extractor needs row/column/header context to interpret schedules accurately.
- **Reset data:** wipe and recreate the **entire designated PowerForge application database** before deploying the replacement schema. No data backfill, migration, historical run reads, or dual runtime.
- **Defer to Phase 7:** deciding whether separate page-level equipment observations identify the same physical asset. No automatic cross-page deduplication in Phase 6R.

The end state should contain **one unified, versioned engineering extraction family with two sequential AI calls per selected page**, rather than two independent two-call families.

## 2. Rationale for using `main`

The Phase 6F branch was aligned with `main` when this plan was prepared. The Phase 6E branch is an ancestor but lacks the later Documents extraction workflow and operation monitoring. The Phase 6G branch was nine commits ahead of `main` at review time, but still retained architectural elements Phase 6R is intended to replace.

Starting from `main` retains investments unrelated to extraction semantics: improved workspaces, the shared design system, review/navigation components, source preparation, and operation execution. **The committed Git baseline is retained; the existing database content and obsolete database schema are not.** Rebuilding from Phase 5 or 6E would discard/recreate useful work without avoiding the core engineering-extraction rewrite.

**Branch policy:** Create `codex/phase-6r-ai-first-redesign` from the latest verified `main` when implementation begins. Record its exact base commit in the Phase 6R handoff. Do not merge the Phase 6G branch wholesale; selectively port useful ideas (especially per-stage diagnostic traces) only after reviewing whether they fit the new design.

## 3. Goals, invariants, and non-goals

### Goals

1. AI is the primary authority for identifying source-local equipment, classifying equipment to the registry, recognizing supported registry attributes, and assigning those attributes to equipment observations.
2. PowerForge performs structurally bounded validation, light source checks, raw-value preservation, reliable unit normalization, typed-value checks, persistence, and auditability—**without recreating an engineering interpretation engine**.
3. One extraction workflow handles textual prose, schedules/tables, equipment nameplates, and diagram evidence on a page.
4. Preserve unknown/unmapped and tag-less equipment observations rather than silently deleting them.
5. Preserve independently observed and conflicting raw attribute values with provenance. Never silently replace canonical engineering data.
6. Make the unified workflow observable, retryable, idempotent, cancelable, and reviewable through the existing Documents workspace.
7. Reduce provider calls and code complexity where possible without sacrificing source visibility, engineering traceability, or result quality.
8. Deliver a clean new-install schema and application: **no support for any pre-6R extraction runs, data formats, endpoints, profiles, adapters, or obsolete table outputs.**

### Architectural invariants

- Extraction outputs are **candidates and evidence**, not verified engineering-model values.
- The canonical registry remains the authority for supported equipment types, attribute keys, data types, units, and value constraints.
- `system_frequency` and `system_phase_count` remain manual-only system settings unless a separate design decision explicitly changes that policy.
- No Phase 6R extraction stage infers or persists electrical topology. **Attribute ownership** is not the same thing as **electrical connectivity**.
- Tags are optional. Matching tags are not sufficient proof that separate observations describe one physical asset.
- Original sources and derived evidence are immutable/versioned as currently intended; source coordinates and page ownership are preserved.
- External model execution remains subject to consent, deployment enablement, credentials, input size/cost limits, and provenance safeguards.
- The **reset applies to the whole designated PowerForge application database**, including projects, revisions, engineering-model records, documents metadata, extraction histories, accounts and other application tables. New records start from a clean schema; external source documents must be re-uploaded or intentionally re-seeded.
- **No legacy support** means no old extraction profile execution, old response schema acceptance, old run-history display, database backfills, compatibility aliases, or transitional UI. Old behavior may be inspected through Git history, not shipped as runtime compatibility.

### Non-goals

- Phase 7 entity resolution or cross-document deduplication.
- Phase 8 single-line topology interpretation.
- Automatic update of canonical equipment/attribute records without a later review/reconciliation mechanism.
- Replacing the entire Phase 6 job scheduler, document viewer, design system, or document-processing engine.
- Building a deterministic engineering meaning classifier or another table-specific AI extraction pipeline.
- Broadening extraction to unsupported analysis domains or unrelated files solely because the extraction engine is being redesigned.

## 4. Target architecture

```text
USER UPLOAD
    |
    v
DOCUMENT PROCESSING
    - validate and store original document
    - generate pages and image artifacts
    |
    v
LOCAL SOURCE ENRICHMENT
    - extract native text where available
    - run OCR where necessary or explicitly requested
    - preserve reading positions/order and layout geometry
    - preserve table rows/columns/headers and page imagery
    - produce stable source/evidence references
    |
    v
UNIFIED AI ENGINEERING EXTRACTION (per selected page)
    |
    +--> Call 1: Equipment discovery and registry classification
    |        output: source-local equipment observations, tag state,
    |                registry type (or null), evidence references
    |
    +--> Call 2: Attribute discovery and equipment ownership
    |        input: exact Call 1 results + allowed attributes for
    |               recognized registry types + enriched page context
    |        output: raw values, mapped attribute keys, ownership,
    |                qualifiers, evidence references
    |
    v
POWERFORGE VALIDATION
    - schema/size and reference integrity
    - lightweight source-grounding checks
    - registry key/type applicability
    - unit normalization and typed-value validation
    - MAPPED / UNMAPPED / INVALID classification
    - separate evidence/association quality indicators
    |
    v
PERSISTENCE AND DOCUMENTS REVIEW
    - versioned extraction runs, candidates, source evidence, traces
    - preserve unknown, tag-less, ambiguous, conflicting observations
    - one unified run history and evidence review experience
    |
    v
PHASE 7 (FUTURE, OUTSIDE PHASE 6R)
    - AI-assisted physical-equipment identity resolution
    - cross-page/cross-document matching with uncertainty and review
```

**Stages and call count:** The two AI stages are `EQUIPMENT_RECOGNITION` and `ATTRIBUTE_EXTRACTION`, executed sequentially per selected page. The normal case makes two model calls; retries may cause additional provider calls. Skip Call 2 only after a successful Call 1 with **zero eligible recognized equipment types**, and persist an explicit `NO_ELIGIBLE_ATTRIBUTES` result with zero-call telemetry and visible run-history coverage. Preserve unknown equipment observations. A failed, truncated or malformed Call 1 is never an eligibility skip or a successful empty result. There is no mandatory document-level third call or additional call for unsupported attributes.

## 5. Source enrichment contract

The AI must be supplied with enough information to interpret the original page, especially schedules where flattening text loses ownership. Retain these outputs from local enrichment:

- Original/rendered page image (subject to privacy, input, resolution, and model limits).
- Native text and page position information, where available.
- OCR text, confidence/quality indicators and position information when OCR is required.
- Reading sequence, alignment, bounding regions, and source reading IDs.
- Table regions and available cell/row/column/header relationships as **layout hints**, not as a separate engineering extraction stage.
- Page/document identifiers, provenance, source type, and stable evidence references.

**Important distinction:** Retire table-specific *AI extraction and interpretation*, **not** generic spatial detection of table structure. A unified page projection must include table-contained readings that the current Engineering projection may exclude. A detected table is simply another source structure available to the model. The AI can inspect the page image directly if spatial reconstruction is incomplete.

Local enrichment should not decide which breaker owns which rating or which registry field a heading means. Those are AI responsibilities. Explicit OCR controls for hybrid or unusual documents should remain available where appropriate.

## 6. Call 1 — Equipment discovery and classification

### Input

- Enriched page context and page image.
- Full permitted equipment-type catalog from the canonical registry.
- A concise, precise description of each equipment type and classification instructions. Descriptions are versioned, registry-owned metadata included in the extraction input identity; they do not change existing canonical registry keys or behavior.
- Instructions defining an **equipment observation**, including how installed devices, schedules, legend symbols, spares/future provisions, repeated references, and tag-less items should be represented conservatively.

### Model responsibilities

1. Find equipment **observations on the selected page**, not a document-wide count of unique physical assets.
2. Assign a stable *response-local reference* to each observation so Call 2 can reference it unambiguously.
3. Identify the source equipment description and, if supported, exactly one registry equipment type.
4. If no registry match is justified, return `registry_type: null` and retain the source observation as unmapped; **do not exclude it**.
5. Extract the printed tag when present. Distinguish `PRESENT`, `ABSENT`, `UNREADABLE`, and `AMBIGUOUS`; do not fabricate tags.
6. Cite page-local source evidence for the observation and any tag/classification claim.
7. Do not infer electrical connections, cross-page physical identity, or unobserved equipment.
8. Qualify observations explicitly as `INSTALLED`, `PROPOSED`, `FUTURE`, `SPARE`, `REFERENCE`, `LEGEND_ONLY`, or `UNKNOWN`, retaining original source qualifications. These are source-local roles, not inferred physical-asset identities.

Illustrative shape (not a frozen API schema):

```json
{
  "page_ref": "page-1",
  "equipment": [
    {
      "local_ref": "eq-1",
      "source_type": "Dry-type transformer",
      "registry_type": "Transformer",
      "tag": "TX-1",
      "tag_state": "PRESENT",
      "qualification": "UNKNOWN",
      "evidence_refs": ["reading-12", "region-3"]
    },
    {
      "local_ref": "eq-2",
      "source_type": "Specialized power apparatus",
      "registry_type": null,
      "tag": null,
      "tag_state": "ABSENT",
      "qualification": "UNKNOWN",
      "evidence_refs": ["region-7"]
    }
  ]
}
```

The registry key spellings in an actual response must use the existing authoritative registry definitions. The example labels above are illustrative.

### Edge-case policy

- Repeated mentions are retained as separate **source observations** when they appear at distinct places. Do not declare them duplicates based only on tag or rating.
- Two tag-less items on the same page must remain distinct when the evidence shows two devices.
- Apparatus that is only proposed, spare, or future must not be silently counted as installed equipment; retain its source qualification.
- A legend-only symbol or reference is not proof of an installed device. Retain its explicit qualification without fabricating physical equipment or inferring connectivity.
- An unknown equipment type is a useful `UNMAPPED` result, not a failure of the entire page.

## 7. Call 2 — Registry attribute extraction and ownership

### Input

- The **same** selected-page enriched source context and image, within input limits.
- The exact validated equipment observations from Call 1, including their local references, registry types, tags, and available source context.
- **Only the allowed registry attribute definitions for the recognized equipment types** on that page, with descriptions, expected data types, applicable units/enums, and relevant qualification guidance.

### Model responsibilities

1. Locate supported registry attributes in source text, tables, images, or nameplates.
2. Assign each proposed attribute to a Call 1 equipment `local_ref` when the source supports that ownership.
3. Return the exact allowed registry attribute key; do **not** mint new registry keys.
4. Return **raw source value/unit text** and source qualifiers without attempting canonical unit conversion.
5. Supply source citations with relevant equipment designation, row/header/label context when available—not merely a detached number.
6. Preserve multiple distinct source assertions when values conflict; avoid silently choosing a winner.
7. Allow `equipment_ref: null` and an explicit uncertainty indication if ownership cannot be supported. The observation may be retained as unmapped/unassigned rather than attributed to the wrong equipment.
8. Do not invent absent fields or populate attributes from engineering expectations or registry defaults.
9. For enum attributes, perform semantic interpretation in the AI stage and return **both the original source value string and the proposed exact permitted registry enum value**. PowerForge validates membership in the applicable attribute's allowed values; it does not independently interpret engineering synonyms. Simple lexical boolean conversions may be performed by PowerForge while retaining the original source string.
10. Preserve ranges, multiple ratings and qualifiers. A cited source header may establish a unit, but neither the model nor PowerForge may assume a missing unit or discard a qualifier to select an arbitrary scalar.

Illustrative output:

```json
{
  "page_ref": "page-1",
  "attributes": [
    {
      "equipment_ref": "eq-1",
      "attribute_key": "rated_apparent_power",
      "raw_value": "750",
      "raw_unit": "kVA",
      "proposed_enum_value": null,
      "qualifier": null,
      "evidence_refs": ["reading-18", "reading-19", "region-3"]
    }
  ]
}
```

Attribute keys must be validated against the exact registry for the observed type. This is a *restricted registry extraction pass*, not a request for open-ended extraction of arbitrary attributes. Include a **bounded raw-unmapped assertion extension in the same Call 2 response** for meaningful unsupported source attributes encountered within the extraction scope. It is secondary to registry-linked extraction and preserves raw label/value/unit/qualifiers, evidence, and an existing equipment reference only when supported (otherwise null), without inventing a registry key. Set explicit count, field-size and total-output limits in 6R-A. Capacity overflow fails the stage rather than silently truncating assertions. This extension must not introduce unrestricted discovery, additional AI calls, deterministic semantic mapping, or a bypass of the no-eligible-attributes skip.

`proposed_enum_value` above is illustrative wire naming, not a change to any canonical enum. For an enum assertion, retain that separate AI proposal alongside `raw_value`; validate it against the permitted values supplied for the specific registry attribute. A missing or disallowed proposal cannot be silently replaced with a locally inferred synonym or accepted as a mapped enum.

## 8. Evidence Identification and Source Localization Contract

### Design decision and responsibility boundary

**AI identifies the evidence that supports an engineering observation; PowerForge resolves the physical location of that evidence using immutable, locally enriched source artifacts.** Grounding is not a second engineering interpretation pass. Source existence and position checks establish traceability, not the correctness of a model's equipment classification, attribute meaning, or ownership assertion.

| Responsibility | Owner | Rule |
|---|---|---|
| Identify supporting equipment designation, attribute label/header, value, unit, qualifier, and contextual fragments | AI | Cite as much relevant context as is actually available; never invent a continuous quotation |
| Associate a source-local attribute observation with an equipment observation | AI | Reference a Call 1 equipment `local_ref`, or report unassigned/uncertain ownership |
| Select source readings or visible region(s) and identify the page | AI | Prefer stable reading IDs supplied by source enrichment; use visual reports only when readable evidence cannot be referenced |
| Validate cited references, page and artifact ownership | PowerForge | Reject/flag non-existent or cross-page references; do not re-infer equipment ownership |
| Resolve cited reading IDs into text spans and spatial bounding boxes | PowerForge | Look up the pinned source enrichment output, not model-estimated coordinates |
| Locate unique verbatim quotations if reading IDs are missing | PowerForge | Enabled, bounded, page-local fallback against pinned source text; never choose arbitrarily among multiple occurrences |
| Preserve AI-proposed visual regions without source text matches | PowerForge | Keep provenance and lower location-verification quality; do not label them exact/confirmed |
| Highlight evidence | Documents UI | Display exact source-derived highlights when resolved, qualified approximate regions when AI-reported, or page-level context when unresolved |

### Input and citation requirements

Call 1 and Call 2 receive stable **page-scoped reading IDs**, associated native/OCR text, available token/line geometry, layout relations (including table rows, cells and headers), and the original/rendered page image within the run's limits. Source-enrichment identifiers must be pinned to the specific document, page, preparation/layout version and artifacts; they are not document-global free-text identifiers.

For each attribute, the AI should return the **raw value**, the permitted registry attribute key, the referenced equipment `local_ref` (if supported), and **evidence sufficient to understand both the attribute meaning and equipment association** wherever available. This generally means references to relevant equipment designation, label/header, value, unit and qualifiers. Evidence may consist of multiple distinct readings, rather than one contiguous quoted sentence.

Examples:

- A printed continuous note `CB-1 HRD 600A` can be cited as one source reading or several exact sub-readings; the AI should identify that context rather than cite `600A` alone.
- For a table row `CB-1 | Schneider | 600 A` under a `Rating` header, the AI should cite the **equipment cell**, **value cell** and **rating header**, using their actual source reading IDs. It must not fabricate a verbatim string such as `CB-1 Rating: 600 A` if that exact sentence does not appear in the document.
- For a distributed nameplate or drawing annotation, separate label and value readings are valid evidence. PowerForge resolves each reading's coordinates independently; the AI supplies their engineering relationship.

Illustrative response fragment (not a frozen API schema; IDs/keys must match actual inputs):

```json
{
  "equipment_ref": "eq-1",
  "attribute_key": "rated_current",
  "raw_value": "600 A",
  "evidence": [
    {"role": "EQUIPMENT", "reading_ref": "p2-r12"},
    {"role": "LABEL", "reading_ref": "p2-r08"},
    {"role": "VALUE", "reading_ref": "p2-r15"}
  ]
}
```

The **evidence role** is an AI assertion; the locator is a PowerForge-resolved source reference. PowerForge checks that references are valid, but does not independently reconstruct the table row or decide whether the AI selected the correct breaker.

### Source localization procedure

1. Resolve each cited `reading_ref` against the **exact pinned enrichment result** for the observation's page.
2. Retrieve the native-text or OCR occurrence, source artifact identity, original text, available offsets and bounding region(s). Preserve individual parts and their separate coordinates; do not synthesize a nonexistent combined quote/span.
3. Verify document/page/artifact ownership and, where the AI provided quoted raw text, apply a bounded, whitespace-tolerant comparison to the cited reading(s). A numeric value appearing anywhere else in the document is not sufficient support for a particular cited occurrence.
4. Record the resolved evidence location(s), modality and localization quality independently of `MAPPED` / `UNMAPPED` / `INVALID` and independently of the AI's association certainty.
5. Let the UI highlight the located source fragments, preserving the visible distinction between model interpretation and verified source positioning.

Pinned source reading IDs are the primary localization method. Enable bounded, page-local verbatim quote matching against the exact pinned source as a fallback when reading IDs are missing. For a source with **multiple identical text occurrences**, require a disambiguating reading reference or other unique locator; otherwise preserve the evidence as unresolved/ambiguous. **Never arbitrarily select a matching `600 A`.** Matching source text without source-derived coordinates does not authorize a precise spatial highlight. Preserve available text offsets and use page-level spatial context when geometry is unavailable. This fallback must not conceal a fabricated or foreign reference; retain diagnostics for failed citations.

### Visual fallback when native/OCR readings are unavailable

For images, complex diagrams, or illegible/unrecognized text, the AI may return a **page-scoped approximate visual region** with reported text and modality, instead of a reading ID. Such model-proposed coordinates are *not* equivalent to coordinates measured by native text extraction/OCR. Validate page bounds and coordinate format, but do not describe the region as independently verified. Store it as a reported visual locator, optionally with a page-level fallback.

A targeted OCR check may be added later as an optional localization enhancement, **not** as a mandatory extra AI extraction call or a resurrected table pipeline. The system must function without it.

### Localization outcomes

| Outcome | Criteria | Evidence viewer behavior |
|---|---|---|
| `RESOLVED` | A citation identifies a valid occurrence/region localized by the pinned native/OCR enrichment artifact | Precise highlights only where source-derived coordinates exist; otherwise show the text location with page-level spatial context |
| `VISUAL_REPORTED` | AI reports a visual region, but there is no independently localized native/OCR occurrence | Qualified approximate region, clearly identified as AI-reported |
| `UNRESOLVED` | The citation is missing, ambiguous, non-unique, or cannot be reliably positioned | Page-level evidence/review warning; no fabricated precise highlight |

These are **localization outcomes only**, not engineering-verification grades. A `RESOLVED` citation establishes *where* the evidence is, **not** that the AI mapped it to the correct physical equipment or registry meaning. Malformed, fabricated, or foreign-source references must follow validation policy rather than being silently accepted as `RESOLVED`; an otherwise valid raw observation may be retained with its unsupported citation removed and an appropriate diagnostic.

**Implementation constraint:** Reuse the existing source enrichment and provenance machinery wherever compatible. Do not build a deterministic engineering-association engine, insist on one-line contiguous quotes, or ask the model to supply exact coordinates when PowerForge already has source-derived geometry.

## 9. PowerForge validation: thin but substantive

### Required checks

1. **Response/schema checks:** structured outputs, bounded sizes and cardinalities, required fields, value formats, unique response-local references.
2. **Ownership/reference checks:** same document/run/page; valid Call 1 equipment reference; supplied evidence locator exists; referenced registry keys/types exist and are applicable.
3. **Light source grounding:** the source/page and cited evidence exist; cited text/value is present in the claimed source when the claim is text-verifiable; normalized text comparison may tolerate harmless OCR whitespace differences. Preserve page-image-only evidence with an explicit lower verification level.
4. **Registry value validation:** normalize supported units within PowerForge; parse typed values with the registry's exact rules; check applicable numeric, enum, boolean, dimensional, and storage constraints.
5. **Provenance and integrity:** pin input identities, prompt/model/profile versions and provider calls; never publish cross-page/cross-document citations or orphan references.

### Approved value and failure policy

- **Missing units:** never use the canonical normalizer's default unit as evidence of source units. Source-supported headers can establish units. Missing or ambiguous units for dimensional values retain raw information as `UNMAPPED` with a specific reason; unsupported units under an otherwise valid interpretation may be `INVALID`. Unitless registry attributes do not require fabricated units.
- **Qualified values:** retain qualifiers, ranges and multiple ratings. Normalize only when the supported registry representation preserves the source assertion faithfully; otherwise retain raw information with an explicit unmapped reason. Never discard qualifiers or select arbitrary scalar values.
- **Enums and booleans:** AI supplies the original source value and a separate exact permitted enum proposal. PowerForge validates enum membership and may perform simple lexical boolean conversions; it must not add an engineering synonym interpreter. Preserve the raw string even when validation fails.
- **Stage failure:** malformed envelopes, duplicated identifiers, truncation and capacity overflow fail the stage; do not publish a partial stage as complete or treat it as empty success.
- **Recoverable citations:** retain otherwise valid observations when individual citations fail, remove unsupported source links, and record bounded diagnostics. Never guess a missing reference or ownership; unsupported ownership remains unassigned with diagnostics. A citation failure is not automatically an invalid-value error.

### Explicitly prohibited responsibilities

- Re-deriving an equipment type from source vocabulary as a second semantic interpreter.
- Reinterpreting table rows to decide attribute-to-equipment association.
- Determining physical-equipment duplicates, cross-page identity, or electrical topology.
- Requiring a predetermined engineering terminology alias to accept an otherwise supported AI registry proposal.
- Independently mapping engineering synonyms to registry enum values instead of validating the AI's permitted-value proposal.
- Treating document-wide appearance of a numeric value as proof it belongs to a given equipment item.

A source check establishes **traceability**, not semantic truth. A cited value may exist on the page but still be assigned to the wrong row or equipment. Keep that distinction visible and evaluate association accuracy independently. Do not automatically promote text presence into an engineer-verified claim.

## 10. Observation state and evidence quality

Retain these three interpretation states:

| State | Meaning |
|---|---|
| `MAPPED` | Supported registry key/type and successfully normalized, valid typed value |
| `UNMAPPED` | Source observation retained, but no supported registry interpretation/ownership or faithful typed normalization can be established, including missing/ambiguous dimensional units |
| `INVALID` | Supported interpretation exists, but the proposed raw value/unit cannot pass required typed-value or unit rules |

**Separate dimensions:** Source-grounding quality and AI association uncertainty must not be collapsed into the three mapping states. A syntactically valid `600 A` value can be `MAPPED` while its equipment ownership has low supporting evidence; that is *not* an invalid unit/value. Store modest, intelligible review indicators such as `TEXT_VERIFIED`, `IMAGE_ONLY`, `AMBIGUOUS_OCCURRENCE`, or `ASSOCIATION_UNCERTAIN` without turning them into another deterministic semantic engine.

Retain raw value, raw unit, original qualifiers, source citations, registry proposal (including the AI-proposed enum where applicable), normalized typed value (when valid), and relevant diagnostics separately. Observation qualification, mapping status, localization quality and association certainty remain distinct dimensions.

## 11. Page scope, tag-less equipment, and Phase 7

**Phase 6R creates source-local observations, not unique physical assets.** A transformer might appear in a one-line diagram, a schedule, and a nameplate; all three may produce valid equipment observations. Similarly, two visually similar tag-less transformers might be distinct physical assets.

Phase 6R must:

- Give each observation a unique persistent identity and retain its page/source evidence.
- Avoid cross-page deduplication, automatic merging, or canonical equipment creation based solely on extraction results.
- Preserve tag-less equipment and uncertainty rather than deleting or guessing its identity.

Phase 7 may use AI to propose that observations across pages refer to the same physical item, relying on tags, serial numbers, context, locations, specifications, and other evidence. Phase 7 must permit **unresolved** results and later review. A matching rating or tag alone does not prove a match; Phase 6R does not implement that inference.

## 12. Runtime and orchestration strategy

Reuse the **generic** job and operation infrastructure from Phase 6B/6F, but replace the old extraction-family semantics completely:

- Reuse bounded page work units, admission control, dependency handling, attempts, cancellation, backoff/retries, recovery, external-processing consent, and usage tracking where their implementations are architecture-neutral.
- Replace all separate engineering/table run-family planning with **one unified extraction family**; delete the old dispatchers, selectors and compatibility layers.
- Bind Call 2 to the successful, immutable Call 1 result from the same selected page and run.
- Use the fixed stage names `EQUIPMENT_RECOGNITION` and `ATTRIBUTE_EXTRACTION`; persist the explicit `NO_ELIGIBLE_ATTRIBUTES` result when Call 2 is skipped under section 4's rule.
- Allow partial multi-page success without marking missing pages complete.
- Ensure retries are stage-specific and do not re-call a successful prerequisite unnecessarily.
- Pin source, enrichment, registry, prompt/model/profile and provider-call identities for **new Phase 6R runs**, not for replaying old results.
- Do not require separate AI calls for tables or mandatory document-wide deduplication.
- Preserve bounded, access-controlled stage-result diagnostics and audit information, including input/result identities, provider-call references, outcomes and measured usage where available. Do not expose credentials or unbounded provider content through diagnostics.
- Report cost estimates only when measured usage and versioned pricing are available; otherwise report cost as unavailable rather than assuming zero or fabricating an estimate.

**Clean break:** Remove the old profile registration, schema parsers, prompts, adapters, retry handlers, result readers and run-family branching. No old runs or partially completed attempts will be migrated: the designated database is wiped before rollout. The replacement runtime supports only Phase 6R data contracts.

## 13. Database reset, replacement schema, and migrations

### Mandatory full-database cleanup

**The Phase 6R cutover MUST perform a full reset of the entire designated PowerForge application database.** This is a deliberate breaking change, not an incremental upgrade. Do not preserve, backfill, import, expose or migrate old application rows. The reset includes **all tables and records**, not only Phase 6 extraction data: projects, revisions, document metadata, canonical equipment/topology data, users/account records if stored locally, source-enrichment histories, operations, evidence, table outputs and migration-version tracking are all cleared. The canonical **model definitions and registry code** remain in the repository; populated canonical **model records** do not survive.

**This document instructs a future implementation/deployment step; it does not authorize an agent to wipe an unspecified, shared or production database immediately.** Before running destructive commands, the operator must identify the exact target environment and database, verify they are authorized to destroy its contents, and explicitly approve that target. If any content might be needed, make a backup/export **outside the database being wiped** first. Do not reset a shared/production environment merely because the implementation branch is checked out.

**Required reset workflow:**

1. Stop application/API servers, schedulers, extraction workers and background queues that may write to the target database.
2. Confirm and record the exact database host, database name, environment and ownership; obtain explicit approval for irreversible full deletion of that specific target.
3. Back up any data that must survive independently, if applicable. **No restore of old PowerForge application/extraction rows into the Phase 6R database is supported.**
4. Drop/recreate the entire designated application database (or equivalently destroy and recreate its fully isolated database schema), including the migration-version table. Do not selectively delete only extraction tables.
5. Initialize the **new clean-install migration chain** and apply the Phase 6R database schema from zero. Verify every foreign key, constraint, provenance locator, and two-stage work-unit dependency against the new contracts.
6. Recreate only genuinely required bootstrap records/configuration through documented seed/bootstrap logic. Re-upload or explicitly re-seed sample engineering documents when needed. Old extracted results and run history do not return.
7. Where the development stack stores artifacts or queue state outside the database (for example object storage and Redis/Celery), separately clean **only PowerForge-owned, explicitly scoped** obsolete artifacts, jobs and caches to avoid orphaned data or stale tasks. Do not delete unrelated buckets, volumes or shared service data.
8. Run clean-install migration tests, new extraction smoke tests and UI checks before allowing real extraction jobs.

### Clean schema and migration policy

- Design the persistence schema **for Phase 6R alone**: unified run family, Call 1/Call 2 attempts, equipment observations, attribute observations, evidence references/localization, statuses and run telemetry.
- Reuse existing ORM/schema components only if they fit the new contract; remove old `extracted_tables` output structures, old table-cell-specific foreign keys, legacy profile/version constraints, legacy run-family fields and obsolete compatibility triggers where they are no longer needed. Generic **source-layout table structures** may remain because they belong to local enrichment, not an AI table extraction pipeline.
- Since every target database is rebuilt empty, **no historical data migration or additive compatibility migration is required**. Refactor/squash/replace the old Phase 6 extraction migration chain (`0011`–`0017`) as needed, while keeping the complete clean-install Alembic graph valid. Preserve earlier, unrelated migration behavior only where still necessary to construct the desired current application schema. If necessary, create an explicitly documented replacement baseline.
- Do not blindly delete migration files without fixing their dependencies or the Alembic head. The existing unmerged Phase 6G `0018` revision must **not** be merged as-is or retained merely for compatibility; reconcile its migration numbering only if a genuinely new Phase 6R feature needs it.
- Do not introduce old-profile adapters, old-record read APIs, importers, dual-schema persistence, deprecation windows or compatibility switches. **There are no legacy consumers to support after the mandatory reset.**
- Validate applying migrations from a truly empty database. Do not treat an upgrade from migration `0017` or `0018` as an acceptance requirement.

### Canonical model boundary

Persist *new extraction observations* and their provenance, not automatically verified engineering-model values. The clean database does not change the Phase 7+ identity, reconciliation, and engineer-review boundaries.

## 14. API and UI changes

### API

Adapt the existing extraction routes and operations contract for **one new extraction family**. Preserve useful revision-document authorization, pagination, source identity, evidence retrieval, retries, and cancellation patterns **for new Phase 6R records only**. Delete old Engineering/Tables profile selectors, separate run summaries, old table output endpoints, historical-family query parameters and compatibility schemas. There is no backward-compatible API for pre-6R records.

The **operation-based extraction workflow is the single supported user-facing start path**: source selection → preview → consent-bound operation creation. Remove the old direct user-facing `POST /runs` start route rather than preserving a second start API. Internal run creation remains an implementation detail of the operation/runtime infrastructure. Read, retry and cancellation APIs retain appropriate scope and authorization; stage-result diagnostics are access-controlled.

### UI

Preserve the Phase 6F Documents-centered interaction model, responsive drawers, shared components, page viewer, and basic run-history UX, but **remove all support and navigation for pre-6R data**:

- One **AI Engineering Extraction** action/profile covering prose, tables, nameplates, and diagrams.
- Keep automatic source preparation with optional advanced OCR override.
- One unified operation/extraction status rather than separate Engineering and Tables progress tracks.
- Evidence browser displays equipment observations and explicit qualifications, tag-less state, registry mapping, registry-linked and bounded raw-unmapped attributes, context-rich source citations, localization quality and raw/normalized values. Enum details retain the source string separately from the AI-proposed registry enum.
- Make unmapped equipment, uncertain associations and unresolved citations visible, not hidden.
- Run History shows **only Phase 6R runs** and their two AI stages, attempts, source bindings, costs/usage and retries. It does **not** expose read-only Engineering/Tables legacy tabs or historical run links.
- Show `NO_ELIGIBLE_ATTRIBUTES` as an explicit outcome, not an executed empty attribute call. Costs are unavailable unless measured usage and versioned pricing support an estimate. Precise highlights require source-derived coordinates; AI-reported regions remain visibly approximate.
- Remove table-specific execution selectors, statuses, raw-table extraction diagnostics, dual-family controls, and obsolete historical-record UI.
- Preserve unrelated layout, navigation, tokens and design components; do not opportunistically redesign other workspaces.

The document viewer may still depict a source table region because it is **source evidence**, not a separate AI-extracted table record.

## 15. Code impact inventory (planning guide)

This is a code-review starting point. **Delete superseded code and obsolete schema after checking shared consumers; do not carry legacy adapters into the final build.**

| Area | Likely action | Examples of current paths |
|---|---|---|
| Document processing/source enrichment | Preserve, adapt projection | `packages/document-processing/`; `enrichment_*`, `layout_*`, `native_spatial.py` |
| Execution and operations | Reuse, simplify active families | `packages/extraction/src/powerforge_extraction/orchestration.py`, `execution.py`, `operations.py`, `operation_plan.py` |
| AI transport | Reuse and version | `services/extraction-worker/src/extraction_worker/openai_extraction.py`; `packages/ai/` |
| Recognition/attribute stages | Replace | `engineering_stages.py`, `engineering_output.py`, `enriched_observations.py`, `enriched_runtime.py` |
| Grounding and interpretation | Replace with thin checks | `grounding.py`, `interpretation.py`, `enriched_grounding.py`, table-specific grounding/semantics modules |
| Table-specific model extraction | Retire active path | `table_stages.py`, `table_runtime.py`, `table_output.py`, `enriched_tables.py`, table-specific prompts/profiles |
| Persistence/contracts | Rebuild for clean Phase 6R schema; delete old-record support | `contracts.py`, `models.py`, `persistence.py`, `enriched_publication.py` |
| API | Adapt run/evidence/operation contracts | `services/api/src/powerforge_api/routers/extraction.py`, `routers/extraction_operations.py`, extraction service/schema modules |
| Frontend | Refactor extraction-specific panels only | `start-extraction-wizard.tsx`, `extraction-evidence-panel.tsx`, `extraction-run-history.tsx`, `extraction-operation-panel.tsx`, `document-extraction-panel.tsx` |
| Migrations | Rewrite/squash Phase 6 extraction migration history for clean-install schema; reset database | `database/migrations/0011`–`0017`; verify new Alembic head and empty-DB install |
| Docs and evaluations | Remove obsolete active docs and runtime tests; reuse fixtures only | `docs/EXTRACTION.md`, `docs/DOCUMENT_PIPELINE.md`, `docs/ROADMAP.md`, `evals/extraction/`, `evals/tables/` |

During 6R-A, produce an actual file-by-file disposition matrix (`KEEP`, `ADAPT`, `REPLACE`, `DELETE`) including import references, API routes, profile gates, migrations, tests, and UI consumers. Delete obsolete extraction implementation, adapters, schemas, routes, UI and tests once new equivalents pass; nothing must remain solely to read or execute old data.

## 16. Milestone implementation plan

### 6R-A — Architecture, inventory, and acceptance baseline

**Objective:** Turn the agreed design into an executable implementation contract before significant code changes.

**Deliverables:**

- Finalized Call 1/Call 2 request and response schemas (including tag states, explicit observation qualifications, local IDs, provenance, uncertainty, raw source plus AI enum proposals, and the bounded raw-unmapped extension).
- Registry-owned versioned descriptions, registry projection rules, source-projection policy and prompt boundaries.
- Written validation/status contract distinguishing light grounding from engineering meaning.
- Concrete file/import/API/UI impact matrix and safe retirement sequence.
- Mandatory full-database reset plan, fresh-install schema/migration plan and explicit no-legacy-support policy.
- Baseline evaluation suite, metrics/denominators and provisional numerical targets; separate representative authorized real-world sources for preliminary 6R-C validation and a held-out 6R-F benchmark. Plan final gate review after preliminary live results and before held-out evaluation.
- Updated architecture ADR superseding the old extraction architecture for new runs.

**Exit gate:** No unresolved contradictions between registry keys, AI output contracts, source evidence, DB constraints, orchestration, and UI; no unauthorized Phase 7 responsibility moved into Phase 6R.

### 6R-B — Unified profile and infrastructure adaptation

**Objective:** Introduce a new, independently versioned extraction path using the existing infrastructure.

**Deliverables:**

- Unified profile/manifest/prompt/schema identities and two-stage page dependency plan, including the explicit successful-Call-1-only `NO_ELIGIBLE_ATTRIBUTES` skip.
- Source input projection exposing prose **and** table-contained readings/layout with page image.
- Reused consent, retries, job execution, recovery, admission limits, and metrics.
- New data contracts with stubbed provider tests; old profiles are not registered or supported.

**Exit gate:** Fake/mock end-to-end runs work for single- and multi-page documents; Call 2 can never use an unrelated or unsuccessful Call 1 result; no new table-family dispatch occurs in unified mode.

### 6R-C — AI recognition and attribute extraction

**Objective:** Implement the actual two-call AI semantics.

**Deliverables:**

- Equipment identification/classification prompt and parsed response handling.
- Registry-scoped attribute extraction prompt with Call 1 context, equipment ownership, AI enum interpretation with original source strings, and a secondary raw-unmapped assertion extension with explicit limits.
- Support for unmapped and tag-less equipment; supported attributes, qualifiers, uncertain/unassigned ownership, and conflicting observations.
- Provider errors, malformed/partial structured response behavior, and stage diagnostics.
- A **small, explicitly authorized live OpenAI feasibility test completed and reviewed before 6R-D begins**. Use a bounded representative development sample covering **prose, schedules and diagrams**, with approved source/page scope, recorded sample counts and model/profile identities, and bounded calls/spend. Measure equipment recall, attribute accuracy (returned keys, source values and enum proposals), equipment ownership correctness, evidence quality, token usage and latency per page/stage against independently annotated expectations and pinned source artifacts. Include numerators/denominators, omissions, failures and unavailable telemetry. Review a compact findings report without claiming final normalization/publication/UI acceptance or using the held-out benchmark for tuning. The comprehensive evaluation remains in 6R-F.

**Exit gate:** Mock-provider coverage for prose, nameplates, single-line page content, dense schedules, unknown/tag-less equipment, repeated mentions, and incorrect association references, plus the completed and reviewed live OpenAI feasibility report covering the three source categories and six measurement areas above. **Do not begin 6R-D before this feasibility checkpoint is complete.** Cover enum proposal membership/raw preservation, bounded raw-unmapped overflow, eligibility skipping, and recoverable citation failures. No code silently maps a missing attribute or creates a registry key. This checkpoint is not a pass/fail claim against provisional numerical performance thresholds; those remain provisional until representative live results, corpus sizes and evaluation procedures have all been reviewed, and are frozen before the separate comprehensive held-out evaluation in F.

### 6R-D — Thin validation, normalization, and publication

**Objective:** Produce durable, traceable candidates without recreating deterministic semantic extraction.

**Prerequisite:** Complete and review the small authorized live OpenAI feasibility test in 6R-C before beginning this milestone.

**Deliverables:**

- Minimal source and registry validation implementation, including pinned-reading localization, enabled unique bounded page-local quote fallback, and independently qualified visual regions.
- Raw/typed value separation, AI enum-proposal membership validation, exact source-supported unit normalization and qualifier preservation; no assumed units or arbitrary scalar selection.
- `MAPPED`, `UNMAPPED`, `INVALID` statuses plus independent evidence/association quality.
- Clean-install schema/migrations, ownership constraints and immutable Phase 6R publication.
- Targeted tests for false/ambiguous quotations, wrong-page citations, missing source geometry, repeated values, missing/ambiguous/unsupported units, qualifiers/ranges, invalid enum proposals, and bounded unsupported attributes.

**Exit gate:** Correct new sources and references survive; fabricated/broken references cannot masquerade as verified evidence; conflicting/uncertain results are retained safely; a fresh empty-database install works with no legacy tables or old-record readers.

### 6R-E — Documents UI integration and complete legacy removal

**Objective:** Make the unified pipeline the standard user workflow while removing obsolete active code.

**Deliverables:**

- Updated wizard, operation monitoring, candidate/evidence browser and run history.
- Single extraction family and no separate table-extraction controls.
- No historical extraction tabs, legacy run readers, compatibility routes or old-profile controls.
- Dependency-based deletion of old profile execution modules, prompts, adapters, schemas, old table output paths, unused tests, and old extraction UI components.
- Replace obsolete architecture and UI documentation, documenting the intentional breaking change and database reset.

**Exit gate:** End-to-end extraction and review works from Documents on a freshly initialized database; no legacy extraction profile, table-result API, read-only historical tab or compatibility handler remains; no unrelated UI regressions.

### 6R-F — Comparative evaluation, production hardening, and cutover

**Objective:** Demonstrate that the simpler architecture works on actual engineering content and is operationally reliable.

**Deliverables:**

- Gold/expected annotations for equipment observations, type mappings, tags, attribute keys/values, equipment ownership, and evidence quality.
- A separate held-out benchmark, not used for preliminary 6R-C validation or prompt tuning; numerical release gates finalized only after review of representative live results, corpus sizes and evaluation procedures, and frozen before held-out evaluation.
- Comparative baseline against the previous pipeline where repeatable and useful.
- Measured equipment precision/recall, classification, attribute recall/accuracy, association accuracy, evidence validity, latency, token usage and cost.
- Tests for mixed prose/tables, borderless/merged schedules, repeated numbers, multi-page mentions, unknown types, no-tag cases, blurry scans and source/OCR conflicts.
- Retry, timeout, cancellation, crash recovery, idempotency, authorization, bounded input/output and **empty-database installation** smoke tests.
- Destructive-reset deployment runbook, clean-install/restore procedure and final 6R handoff.

**Exit gate:** Final numerical acceptance thresholds are established only after representative live results, corpus sizes and evaluation procedures have all been reviewed; freeze them before comprehensive held-out evaluation and satisfy them with measured results. Until that combined review, the numerical performance targets in implementation-plan section 7.2 remain provisional, not C feasibility pass/fail criteria, final release gates or claims about measured performance. The small C test alone does not establish benchmark adequacy or finalize thresholds. Fixed architectural/integrity requirements remain mandatory throughout. Known failure classes are documented, reviewable, and do not silently contaminate canonical data. Live OpenAI tests with actual drawings require authorized source scope and explicit opt-in in both C and F. Do not declare success from synthetic-only or mocked-provider tests.

## 17. Documentation cleanup and replacement

Update authoritative documentation to describe **only the new Phase 6R architecture**. Remove obsolete, repo-shipped Phase 6 execution docs, schemas, prompts and examples that instruct use of old Engineering/Tables flows. Historical decisions remain recoverable through **Git history**, not through active compatibility documentation or an indefinitely supported extraction mode.

| File or area | Required action |
|---|---|
| `docs/ARCHITECTURE.md` | Replace extraction diagram and ownership descriptions |
| `docs/EXTRACTION.md` | Rewrite around unified extraction, source-local AI semantics, thin validation and new data contracts |
| `docs/DOCUMENT_PIPELINE.md` | Replace separated extraction workflow with unified source enrichment → AI extraction |
| `docs/PROVENANCE.md` | Define source localization and evidence quality for new observations |
| `docs/ROADMAP.md` | Phase 6R replaces former Phase 6 extraction design; Phase 7 boundary unchanged |
| `docs/PROJECT_STATUS.md` | Report actual rollout status and destructive reset requirement |
| `docs/specs/phase-6-evidence-structured-extraction.md` | Replace obsolete specification with new Phase 6R authority or remove it after links are redirected |
| `decisions/ADR-008-evidence-candidate-extraction-architecture.md` | Replace or supersede in current documentation with new architectural decision; no legacy runtime obligations |
| `docs/PHASE6A_*` through `docs/PHASE6F_*` and old Phase 6G materials | Remove obsolete active handoffs/prompts if superseded; Git history retains previous work |
| `evals/extraction/`, `evals/tables/` | Reuse representative **source fixtures/gold annotations** where useful; rewrite obsolete scoring/tests rather than running old extractors |
| `apps/web/design-reference/v1/` | Update extraction-specific prototypes and release notes; remove legacy extraction screens while retaining unrelated designs |

Prefer one authoritative Phase 6R architecture, revised design spec, milestone plan and final handoff. No compatibility/deprecation guide is required because existing data is intentionally destroyed.

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Call 1 misses equipment; Call 2 cannot recover it | Evaluate equipment recall explicitly; model prompt favors comprehensive source observation; retain diagnostics and allow separately approved recovery strategy |
| AI assigns a table value to the wrong device | Keep contextual row/designation evidence; measure association accuracy; do not confuse text existence with semantic proof |
| Table reading order/layout is degraded | Keep page image plus full reading/layout data; do not exclude table-contained source readings |
| Unrecognized equipment is lost | Preserve raw candidate with null registry type and source evidence |
| Tag-less cross-page duplication | Preserve source-local observations; Phase 7 handles proposed identity and uncertainty |
| Unknown/invalid units are normalized incorrectly | Retain raw value; normalize only when unambiguous; otherwise `UNMAPPED`/`INVALID` as appropriate |
| Full database reset deletes needed data | Require explicit operator authorization for the exact target, scope verification, and optional external backup before destruction; do not run on shared/production by default |
| Old migrations/ORM constraints prevent fresh install | Produce one valid clean-install Alembic chain and verify all migrations starting from a completely empty database |
| Old pipeline or UI logic lingers unintentionally | Inventory imports, routes, tests, profile registrations and UI states; require no-legacy-code audit at release gate |
| New AI model appears better only on simple fixtures | Evaluate with real authorized drawings, irregular schedules, OCR conflicts and independent gold annotations |
| Higher API costs or latency | Track tokens/latency and page sizes; maintain bounded inputs, safe retries and configurable models |

## 19. Clean replacement, destructive reset, and recovery

1. **Freeze the target design:** Record the exact `main` baseline commit and finalize Phase 6R contracts/schema. Confirm the branch includes no unrelated changes.
2. **Build and validate the new implementation:** Replace obsolete extraction modules, table extraction, contracts, API and UI in the Phase 6R branch. Test against isolated **fresh databases**; reuse only architectural infrastructure and fixture data, not legacy runtime compatibility.
3. **Explicitly authorize the destructive deployment:** An authorized operator confirms the exact PowerForge database/environment, affected services and data-loss scope. Back up any needed information to external storage first. **Do not wipe an unknown or shared database automatically.**
4. **Stop all writers and wipe the full target application database:** Drop/recreate the designated database (or its fully isolated application schema) and migration-version state. Clean explicitly scoped PowerForge-owned external object/queue artifacts and caches when necessary. All pre-6R application records, including engineering-model data, disappear.
5. **Initialize from zero:** Apply the replacement clean-install Alembic migrations and required bootstrap/seed logic. Verify no obsolete `extracted_tables`, legacy profile fields, compatibility triggers or old extraction schema are recreated.
6. **Start only Phase 6R:** Deploy the new code, run source processing and unified extraction smoke tests, and verify new evidence localization and Documents UI. Do not run legacy profiles or historical import/backfill.
7. **Recovery:** Roll back by restoring the exact prior code **and a separately retained compatible pre-reset database backup**, if one exists and is approved for restoration. A code-only rollback may be incompatible with the new schema. Otherwise restore a clean Phase 6R environment from scratch or forward-fix; **there is no promised recovery of deliberately wiped data**.

This is a **breaking, destructive reset**. It is not a rolling, no-downtime migration or a strategy for maintaining existing customer data.

## 20. Phase 6R completion definition

Phase 6R is complete only when:

- Exactly one active, unified engineering extraction family processes selected pages, including prose and tables.
- The normal extraction path consists of equipment recognition followed by registry-scoped attribute extraction; there are no separate table-specific AI calls.
- Unsupported and tag-less equipment observations remain inspectable and source-linked.
- AI owns semantic equipment recognition, attribute mapping and source-local attribute ownership. PowerForge owns thin validation, typed normalization and provenance—not a hidden second semantic interpreter.
- Phase 6R does **not** perform cross-page asset deduplication or topology inference.
- The Documents workflow runs, monitors, retries, cancels and reviews unified extraction without relying on old dual-family controls.
- The entire designated application database has been reset and clean-installed for Phase 6R, with no legacy record migration or old-schema compatibility; tests/evaluation meet agreed acceptance criteria.
- Superseded extraction code, runtime adapters, old response schemas, active docs, endpoints and legacy UI are removed, and the release handoff accurately reflects the resulting architecture.
- Fresh-install migration tests pass starting from an empty database, and the destructive-reset runbook has explicit target confirmation safeguards.

---

### Implementation handoff

The 6R-A [contract and migration design](phase-6r-contracts-v1.md) records the v1 interfaces and clean-install graph. Follow the [implementation plan](../PHASE6R_IMPLEMENTATION_PLAN.md) for the B runtime milestone and the C feasibility checkpoint.
