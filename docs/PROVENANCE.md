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
