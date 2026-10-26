# Provenance

Every AI-derived value must be traceable to evidence. The provenance module answers “Where did this come from?” at attribute granularity.

Full Evidence/ExtractionCandidate persistence begins in **Phase 6** and is not implemented in Phase 5. Phase 5 is evidence-ready only: canonical rows keep separate information state, origin, verification, nullable confidence, audit fields and inheritance pointers, without document/page shortcuts or verification authority. See [ROADMAP.md](ROADMAP.md) for placement and [EXTRACTION.md](EXTRACTION.md) for the extraction pipeline.

## Planned ownership

The provenance module (`packages/provenance`) provides contracts; its planned persistence responsibilities include:

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

Conceptual evidence information, not an approved final schema:

```
Evidence
    document_id
    document_page_id
    bbox
    artifact_id
    extracted_text
    confidence
    extraction_method
    model_version
```

Evidence should also support:

- Image crop / page render artifact
- OCR text
- Extraction method (`AI_VISION`, `OCR`, `TABLE`, `MANUAL`, …)
- Timestamp
- Model / provider when applicable
- Prompt version when applicable

## Attribute-level linkage

Provenance is not only “this equipment came from document X”. Each attribute can point at different evidence (SLD vs shop drawing vs nameplate).

Phase 6 retains confidence at candidate/evidence granularity, with attribute-level links rather than only equipment-level provenance. Extraction run/provider/model/prompt versions, timestamps, and retry/version history must remain traceable across native-text, OCR, table, and vision inputs. Canonical nullable confidence does not replace this provenance.

Candidates for revision-level `system_frequency` or `system_phase_count` also require evidence. A model-wide assumption or default is not document evidence, and extraction cannot automatically change canonical revision metadata. Later entity resolution, reconciliation, and review determine how candidates relate to canonical data.

## Source hierarchy

Source types (SLD, shop drawing, nameplate, schedule, photograph, specification) participate in configurable source-priority rules. Provenance records the source type so reconciliation can explain why a value was suggested.

## Planned evidence access

Future revision-scoped evidence access should let engineers inspect source page images and normalized regions without embedding entire files in the model payload. The route contract requires a later specification; no evidence API is implemented yet.

## Phase 0

Phase 0 defined evidence contracts in `packages/provenance`. Full Evidence persistence starts in Phase 6 alongside extraction candidates; Phase 5 stores canonical equipment/attributes without document/page references on those rows.

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
