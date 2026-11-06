# Provenance

Every AI-derived value must be traceable to evidence. The provenance module answers “Where did this come from?” at attribute granularity.

Evidence/ExtractionCandidate persistence is introduced by **Phase 6A**, separately from the frozen Phase 5 model. See [ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md), the [approved specification](specs/phase-6-evidence-structured-extraction.md), and [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md). Phase 5 is evidence-ready only: canonical rows keep separate information state, origin, verification, nullable confidence, audit fields and inheritance pointers, without document/page shortcuts or verification authority. See [ROADMAP.md](ROADMAP.md) for placement and [EXTRACTION.md](EXTRACTION.md) for the extraction pipeline.

## Ownership

The provenance module (`packages/provenance`) provides pure source-location contracts. Phase 6A extraction persistence retains:

- Source document references
- Page references
- Bounding boxes / regions
- Extraction provenance
- Evidence relationships
- Confidence
- Source hierarchy metadata

Original source files are **immutable**. Never overwrite originals. New versions are new objects.

## Document identity (Phase 2)

Phase 2 defines, and implements, what evidence will point at. See [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md).

- **`Document`** is the immutable artifact: stored object, original filename, size, MIME type, and **SHA-256**. Its `id` is the stable `document_id` that `Evidence` references. Its SHA-256 lets anyone verify that the bytes cited as evidence are the bytes that were uploaded. SHA-256 is not unique: identical bytes uploaded twice are two `Document`s, and provenance records which one was actually used.
- **`RevisionDocument`** is the revision-scoped interpretation: document type, number, description, notes, origin (`UPLOADED` / `INHERITED`), and `INCLUDED` / `REMOVED` status. It answers "which documents were part of revision N's package, and how were they classified at the time?"
- **Inheritance preserves identity.** A document carried from Revision 0 into Revision 1 is the same `Document` (same `document_id`, same SHA-256, same object). Evidence extracted from it is valid in every revision that includes it. `inherited_from_revision_id` records which revision it came from.
- **Replacement is a new `Document`.** A superseding drawing is a new upload with a new `document_id`; the old one is marked `REMOVED` in the new revision and stays `INCLUDED` in the old one.

### Rules for later phases

- Evidence references `document_id`. Where the revision context matters (for example "what did the engineer have in Revision 2 when this value was verified"), also record the `revision_document_id`.
- Inheritance is a **snapshot at revision-creation time**; an ACTIVE revision's package stays editable, so its document set can change after a model was built from it. Anything derived from documents must record the `Document` identity it used rather than assuming the revision's package is fixed.
- Document pages, analysis images, thumbnails, and native PDF text (Phase 3) attach to `Document`, not `RevisionDocument`. OCR text is a later artifact. A processing run's outputs are derived data. They are not a second copy of the evidence.

## Evidence

Evidence records belong to one producing work unit and retain the run/document/processing context, stable DocumentPage, optional exact PageArtifact, source kind, extraction method and concise verbatim snippet. Text offsets use the explicit `UNICODE_CODEPOINT` convention and require a pinned native-text artifact; arbitrary visual offsets are rejected. Publication counts codepoints from that exact UTF-8 storage object after verifying its stored size and SHA-256. It never uses `DocumentPage.native_text_char_count`, which later processing may change. Unavailable or unverifiable text rejects publication; there is no page-count fallback. A region is either null or a complete rectangle inside the normalized upright page. Uncertain geometry remains null.

Optional table/cell locators reference schema-versioned table layouts. Candidates link to evidence many-to-many with PRIMARY, SUPPORTING or source-grounded CONTRADICTING roles. Group/table evidence references and candidate context are validated before publication. Composite FKs protect document/page/artifact/run ownership, and immutable output is committed atomically with successful work-unit completion.

## Attribute-level linkage

Provenance is not only “this equipment came from document X”. Each attribute can point at different evidence (SLD vs shop drawing vs nameplate).

Phase 6 retains confidence at candidate/evidence granularity, with attribute-level links rather than only equipment-level provenance. Extraction run/provider/model/prompt versions, timestamps, and retry/version history must remain traceable across native-text, OCR, table, and vision inputs. Canonical nullable confidence does not replace this provenance.

`system_frequency` and `system_phase_count` remain manual-only revision settings. Extraction must not produce revision-level proposals for them. Equipment-specific source statements may be mapped where justified or retained as unmapped observations. Later entity resolution, reconciliation and review determine relationships to canonical data.

## Source hierarchy

Source types (SLD, shop drawing, nameplate, schedule, photograph, specification) participate in configurable source-priority rules. Provenance records the source type so reconciliation can explain why a value was suggested.

## Evidence access

Phase 6A provides revision-document-scoped evidence detail with a source page locator, optional normalized region and a short-lived URL for the exact pinned artifact. INCLUDED document membership is required; inherited and read-only revisions may inspect the same immutable results without copies or canonical writes. Run/candidate/table lists select only successfully committed work-unit attempts. Unsupported candidates are explicitly flagged and excluded from the default sourced list. The browser extraction/evidence workspace remains deferred to 6F.

## Phase 0

Phase 0 defined evidence contracts in `packages/provenance`. Full Evidence persistence starts in Phase 6A alongside extraction candidates; Phase 5 stores canonical equipment/attributes without document/page references on those rows.

Phase 2 does not create evidence. It creates the immutable `Document` and revision-scoped `RevisionDocument` records that evidence will reference.

## Page identity (Phase 3)

Specified in `cursor/phase3_specs.txt` and [ADR-005](../decisions/ADR-005-document-processing-and-page-identity.md) (Accepted). Implemented. No evidence rows are created in Phase 3.

- **`DocumentPage` is the stable location inside a `Document`.** Page numbers start at 1. A PDF page, a whole PNG or JPEG, and a TIFF frame each become one page. The page does not change when a later run renders it at a different resolution.
- **Width and height are the upright page** after rotation normalization, in PDF points or image pixels. `rotation_degrees` is the source rotation that was applied (`0`, `90`, `180`, or `270`).
- **Coordinates, when a later phase stores them, are normalized on that upright page.** Origin is the top left. `x`, `y`, `width`, and `height` each run from 0.0 to 1.0. They are not pixels of an analysis PNG and not the unrotated PDF media box.
- **`PageArtifact` is derived.** An analysis image, a thumbnail, or native PDF text helps a viewer and a later extractor. Provenance cites the `DocumentPage`. It must not treat one PNG as the source of truth. Native text is not OCR. A page with no text layer has a zero character count and no text artifact.
- **Several processing attempts may exist.** The completed attempt is the one later phases may assume is complete. Failed attempts are not evidence and are not exposed as pages.

## Classification provenance (Phase 4)

Specified in `cursor/phase4_specs.txt` and [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Accepted). Complete (2026-10-12). No evidence rows are created in Phase 4.

- **Machine classification attaches to `Document`.** A classification run cites one completed processing run. Revisions that share the file share that result.
- **The confirmed type stays on `RevisionDocument`.** `document_type` is what the engineer accepted or typed. `accepted_classification_prediction_id`, when set, records which document-level prediction that type was accepted from.
- **Inheritance and reuse copy that id** together with the type, number, description, and notes. A reuse that supplies its own type clears the id.
- **Submitting a type clears the id**, even when the submitted value equals the stored type. That keeps a manual choice from looking like an AI accept.
- **A failed classification is not the suggestion.** Its predictions may remain stored. They are not evidence and they cannot be accepted.


## Phase 6B execution provenance

Execution adds immutable versioned profile snapshots and append-only call admission/attempt history without copying source identity. Each source-probe unit pins one exact native-text or analysis-image artifact. Workers verify artifact bytes/hash and enforce byte/pixel bounds before provider invocation. Structured source excerpts must be verbatim substrings of pinned native text; unknown geometry remains null. Fake/test observations carry explicit synthetic diagnostics and their run identifies FAKE_TEST execution. Real infrastructure probes do not manufacture engineering candidates.

Database-fenced leases prevent stale, superseded or cancelled workers from publishing through the 6A boundary. A cancellation preserves previously committed evidence/candidates; a retry appends unsuccessful attempts rather than replacing successful outputs. Cancelled/completed runs remain immutable and require explicit new re-extraction. Call telemetry stores only safe technical identities/usage/errors and optional known-basis cost estimates. Missing usage, interrupted calls and possible crash-window charges remain unknown rather than fabricated zeroes. See [PHASE6B_HANDOFF.md](PHASE6B_HANDOFF.md).

## Phase 6C M1 source-anchor contract

Engineering observation schemas now distinguish native-text quote/context anchors from page-level image anchors. They contain source roles, not trusted database identifiers, offsets or coordinates; validation checks shape and declared references only. A visual anchor has no verified text quote. Raw visual transcriptions remain observations. Future grounding must resolve exact pinned artifacts, verify native excerpts/Unicode offsets and expose the approved page-level visual limitation before publication. M1 creates no new Evidence or candidates and makes no grounding/accuracy claim; see [PHASE6C_M1_HANDOFF.md](PHASE6C_M1_HANDOFF.md).

M2 adds pure source-field consistency and semantic interpretation against **admitted local passages**. These checks do not prove that an arbitrary string was in an artifact or belonged to a particular equipment item. The M3 caller must establish passage ownership and association before interpretation, including the explicit limitation for admitted visual transcriptions. Rejected model fields must be excluded from candidate/evidence conversion; mapped interpretations remain AI candidates, not independently verified facts. No new Evidence publication is implemented by M2. See [PHASE6C_M2_HANDOFF.md](PHASE6C_M2_HANDOFF.md).

## Phase 6C M3 grounding

M3 implements that admission boundary. Source descriptors come from pinned run/unit artifact IDs, not current processing/page summary metadata. Artifact size/hash, native UTF-8 and image format/dimensions/pixel bounds are verified before conversion. Native quotations and adjacent context are matched literally, without Unicode normalization; unique occurrences produce server-calculated codepoint offsets. Repeated unresolved occurrences retain honest text/page grounding, and attributes do not inherit an arbitrary occurrence's equipment context. Complete-line evidence preserves qualifiers outside a model-selected fragment.

Source-local association uses verified native blocks with no detected competing headers/mentions; repeated tags are not merged. Recognition context is reloaded only from completed same-run/page outputs and checked against the exact target artifacts. Page-level visual readings remain explicitly unverified transcriptions, with source image identity and null text offsets/geometry/snippet. A single visual item or an explicit unique tag may support a model-reported local association; multiple tagless visual items remain detached. Native and image readings cannot borrow one another's type context.

Read API evidence summaries/details expose `grounding_precision`: TEXT_OFFSETS, TEXT_PAGE, VISUAL_REGION, VISUAL_PAGE or PAGE_ONLY. This describes source-location precision, not engineering verification or calibrated accuracy. Unsupported claims generate only bounded diagnostic counts, committed atomically with successful unit output. See [PHASE6C_M3_HANDOFF.md](PHASE6C_M3_HANDOFF.md).

## Phase 6C M4 execution provenance

Engineering page stages pin both selected modalities or require native text according to their v2 profile. Descriptor snapshots bind source loading to the original processing run/artifact IDs; every selected object is verified before use with no fallback. Attributes consume only the unique committed same-page recognition success, whose raw context remains separate untrusted request data. Retry reproduces the same source bytes, registry rendering and immutable upstream projection. M3 grounding/association checks and explicit visual limitations remain unchanged.

Run prompt/schema identity covers the complete stage manifest; individual call rows record actual stage schema and rendered-instruction hash. Attribute correlation IDs additionally retain the upstream attempt and projection hash without retaining source dumps. Waiting/blocked units make no call and consume no admission. Calls interrupted after the provider boundary retain unknown usage rather than fabricated zeroes. Synthetic stage runs/candidates remain visibly FAKE_TEST. No new tables or canonical writes were introduced; M5 adds production SDK integration below; evaluation remains pending. See [PHASE6C_M4_HANDOFF.md](PHASE6C_M4_HANDOFF.md).

## Phase 6C M5 provider provenance

Production v3 profiles pin the unchanged stage/interpretation/grounding resources, a v2 runtime, the versioned OpenAI input contract and explicit model/effort/image detail/limits. Native source text and response-local recognition context are JSON-escaped, explicitly untrusted user inputs; image bytes are sent as private data URLs with a named page-level source role. Provider input includes no database/artifact/group IDs or storage keys. Stage schema/instruction and immutable upstream call identities retain M4 reproducibility across retries.

One SDK call per admitted attempt uses SDK max_retries=0, no tools and store=false. Refusals, incomplete/malformed responses and SDK failures remain sanitized; unavailable usage, including SDK parsing/transport exceptions without exposed usage, stays unknown. Worker/beat tests use real durable storage/transport and an exclusively mocked OpenAI HTTP transport, so they prove provenance plumbing rather than model recognition quality. Explicit visual limits, conservative native grounding and canonical separation remain unchanged. See [PHASE6C_M5_HANDOFF.md](PHASE6C_M5_HANDOFF.md).

## Phase 6C M6 evaluation provenance

The synthetic corpus pins authored source bytes and independently declared claim meanings, exact typed values, statuses, occurrences and associations. Its canonical validated corpus hash includes source hashes; recorded responses additionally pin the producing manifest/interpretation/grounding resources. Reports retain those identities, the recording hash and a scorer-source hash. One-to-one source matching never uses proposed mappings/values. Failed stages keep reference denominators; page-level visual validity does not claim independent text verification. Committed results are `SCRIPTED_MOCK`; merely labeling a recording live gives `UNVERIFIED_RECORDING`, never measured model quality.

The separately opt-in live entrypoint requires an explicitly approved corpus digest and exact Document bindings. Before committing any run it checks all selected original processing artifacts against approved role/hash/size/dimensions. It uses normal versioned profiles, two admissions per case, one attempt per stage, immutable committed recognition, existing execution fences and atomic publication. Reports score only committed successful outputs and preserve published rejection counts and failed-case denominators. The internal injected-provider runner always reports `UNVERIFIED_PIPELINE` and accepts no provenance label. Only the guarded production entrypoint, which selects the worker's production factory itself, designates `LIVE_OPENAI`; measured quality additionally requires a successful call. Injected-provider tests remain unverified; no live paid call or production accuracy claim is made. See the [corpus guide](../evals/extraction/README.md) and [final handoff](PHASE6C_HANDOFF.md).

## Phase 6D M1 table contracts

Table reconstruction observations preserve raw cells, sparse/blank/unreadable states, headers, spans, source-role anchors and uncertainty. Table interpretation observations reference existing table/cell/caption aliases; these are model-local names, not database or physical identities. Provider responses cannot assert offsets, geometry, normalized slots or verification metadata. Offline layout/reference consistency does not establish source occurrence or row ownership.

M1 inspection emits only UNVERIFIED text and UNRESOLVED structure metadata. The server-only metadata vocabulary separates future native-text proof, native delimiter structure and visual-reported relationships; constructing a shape-valid object with evidence IDs is not verification. M2 must resolve actual pinned artifacts and committed ownership before admission/publication. Native token matches cannot independently verify a PDF grid, and visual reports retain page-level limits. No evidence is generated by M1. See [PHASE6D_M1_HANDOFF.md](PHASE6D_M1_HANDOFF.md).

## Phase 6D M2 — Grounding, interpretation and publication

M2 adds exact pinned table admission, independent literal-text/relationship reliability, conservative structured-cell registry interpretation, source-local groups and conversion into existing tables/evidence/relational candidates. Native structure requires a unique contiguous delimiter grid; otherwise an explicit visual reading retains page-level limits or the association remains unresolved. Committed reconstruction is revalidated for the exact run/page/artifacts before interpretation. Publisher checks now reject wrong-page/artifact/cell and unfinished upstream ownership, and existing evidence reads report actual table-cell precision and sign the historical artifact.

M1/6C resources and profile/runtime identities, registry-v1, migrations and canonical models remain unchanged. M2 introduced no production table profile or worker execution; M3 integration and M4 representative table evaluation are recorded below. Table-only ownership still requires a separate 6C prose run, and latest summaries continue selecting across profiles. See [PHASE6D_M2_HANDOFF.md](PHASE6D_M2_HANDOFF.md) for actual checks, source rules and conservative coverage limits.

## Phase 6D M3 — Table execution integration

V4 table profiles pin the reviewed M2 source/meaning rules, table manifest/runtime/input envelope, model/options and bounds. Provider context contains local aliases and actual admitted reliability rather than database/artifact IDs or storage keys. Call correlation binds the committed reconstruction attempt and canonical context hash. Value evidence reuses the immutable producer cell; visual readings retain page-level limits. Empty interpretation records a skip marker after ordinary admission and fenced publication, with no AI call row or invented zero usage. Historical prose/probe resources and execution meanings are preserved.

The table-only/prose separation and cross-profile latest-result behavior remain explicit. Real worker/SDK transport mocks verify plumbing and compatibility; M4 table evaluation is recorded below; live model accuracy remains unmeasured. See [PHASE6D_M3_HANDOFF.md](PHASE6D_M3_HANDOFF.md).

## Phase 6D M4 — Independent table evaluation

The separate offline `powerforge-eval-tables` command (`python -m powerforge_extraction.table_eval`) replays versioned reconstruction/interpretation recordings against independently authored source/table/cell/claim annotations. Source occurrences and cell coordinates select matches before proposed meanings, typed values, units or associations are scored. Reports retain missed/failed gold denominators, null empty rates, structural/header/orientation metrics, source-local association, citation/locator checks and UNMAPPED/INVALID retention. Native literal proof, visual reports and relationship reliability remain distinct. Caller-provided recording provenance cannot designate live quality. The frozen 6C evaluator and M1–M3 production resources are unchanged.

The corpus has 27 synthetic cases, 27 gold tables, 146 cells and 73 claims, including a real processed-PDF native/hybrid pair. Native abstention loses recall against the visible source gold; visual relationships retain explicit page-level limits. All 100 new tests and new extraction-wheel checks pass. At the user's request, the already verified M3 full backend/integration/migration/API/dependency checks are carried forward, not repeated. No paid model call or live accuracy measurement is claimed. See the [table corpus guide](../evals/tables/README.md) and [final handoff](PHASE6D_HANDOFF.md) for actual scores, verification evidence and remaining limits.

## Phase 6E M1 — Pure spatial source foundation

Separate versioned modules in `packages/provenance` define immutable producer/artifact/page ownership, native/OCR positioned text, token/line/block and native-primitive support, exact source occurrences, conditional native-origin correspondence and pinned prepared/spatial bindings. Pure orthogonal transforms preserve crop, scale, mirrors, quarter turns and normalized upright geometry. Missing support stays null; a resolved support envelope does not establish table/equipment ownership. M1 support resolution remains UNRESOLVED structurally and does not independently verify printed characters. Unknown OCR text coverage remains UNKNOWN.

`powerforge_ai.ocr.PositionedOCRProvider` is a typed protocol with raw image/word/box/settings identity, engine-scale confidence and local usage/failure contracts. The original generic OCR interface and all accepted 6C/6D contracts/resources stay unchanged. No engine/native adapter, production profile, API, schema migration or publisher support is enabled by M1. Existing evidence is not retrospectively upgraded. M2 must implement real processing and durable source artifacts; M3/M4 must establish actual structure and source-aware publication. Backend purpose guards on every endpoint and the future coherent 6F UI remain required.

All 92 focused tests, provenance/AI wheel checks and new resource identities pass; accepted v1–v4 wires/resources and both full frozen 6C/6D reports reproduce unchanged. No infrastructure integration or paid provider call occurred. See [PHASE6E_M1_HANDOFF.md](PHASE6E_M1_HANDOFF.md) for actual bounds/verification and [PHASE6E_PLAN.md](PHASE6E_PLAN.md) for later review gates.


## Phase 6E M2 — Durable native/OCR source preparation

The new local source-preparation profile consumes an explicitly selected completed base run/pages and produces independent immutable native/OCR text and geometry. Actual PyMuPDF 1.28.2 and Tesseract 5 adapters preserve source-local occurrences, transforms, raw readings and recognition limits. Native-plus-raster text coverage stays UNKNOWN and requires explicit whole-page OCR selection; there is no guessed coverage percentage or blanket OCR. M2 establishes neither table relationships nor engineering meaning.

Migration 0014 adds SOURCE_ENRICHMENT purpose, separate source result/artifact/binding records and purpose/lease/identity guards. Local planning/execution/publication reuse the existing durable coordinator with a dedicated CPU queue and admission pool. Source start/input discovery/history/detail/result/artifact/retry/cancel APIs enforce membership and purpose on direct IDs; ordinary extraction summaries/history ignore source jobs. Local run model/prompt/registry fields are inapplicable, and local jobs cannot publish ordinary extraction outputs or AI calls. Usage distinguishes admissions, recognition requests and confirmed engine invocations; unmeasured cost/child resources remain null.

All 271 distinct targeted checks pass, including 51 new M2 cases, real OCR/PostgreSQL/Redis/MinIO/Celery/restart and accepted extraction lifecycle/migration checks. Retained v4 source data preserves old wire/resource hashes and both frozen evaluation reports. The worker image and package wheels reproduce accepted resources; no paid calls or UI changes occurred. Deployment, actual eligibility, measured limits and remaining M3–M5 scope: [PHASE6E_M2_HANDOFF.md](PHASE6E_M2_HANDOFF.md). M3 was subsequently authorized and is recorded below; the backend separation still permits the approved coherent future 6F guided workflow.


## Phase 6E M3 — Reusable geometry-supported layout

The explicit local `source-layout-v1` profile commits SOURCE_PREPARE then SPATIAL_LAYOUT on the existing coordinator/CPU queue. Compatible completed preparations are pinned before admission and reused through immutable direct receipts preserving their actual producer; layout retry never repeats recognition. Migration 0015 adds separate immutable layout results and reuse receipts with owned-source, stage, lease and completion guards. Source history/detail expose the original preparation, receipt and spatial result; new scoped spatial manifest/artifact reads remain separate from extraction endpoints.

Versioned pure document-processing algorithms retain exact native/OCR occurrences, contextual overlap agreements/conflicts, partial reading order and unresolved geometry. Closed native borders support partitions/merged spans; a stricter repeated-alignment path supports simple borderless schedules. Header relationships require actual column coverage plus conservative explicit label cues. OCR geometry remains OCR-derived; serialized cell readings are not printed quotes, missing readings are not verified blanks, and layout supplies no engineering ownership or meaning.

The original positioned 6D PDF gains four supported cells and two header paths over its unchanged delimiter-only baseline. Real OCR, retry and killed-worker recovery are exercised. Accepted M1/M2 and 6C/6D identities/reports remain unchanged. M4 must add the enhanced extraction/evidence adapter; M5 owns representative accuracy evaluation. See [PHASE6E_M3_HANDOFF.md](PHASE6E_M3_HANDOFF.md) for exact rules, limits and verification. Stop for M3 review.
