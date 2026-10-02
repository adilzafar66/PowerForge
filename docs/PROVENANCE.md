# Provenance

Every AI-derived value must be traceable to evidence. The provenance module answers “Where did this come from?” at attribute granularity.

## Ownership

The provenance module (`packages/provenance`) owns:

- Source document references
- Page references
- Bounding boxes / regions
- Extraction provenance
- Evidence relationships
- Confidence
- Source hierarchy metadata

Original source files are **immutable**. Never overwrite originals. New versions are new objects.

## Document identity (Phase 2)

Phase 2 defines what evidence will point at. See [ADR-004](../decisions/ADR-004-document-storage-and-revision-inheritance.md).

- **`Document`** is the immutable artifact: stored object, original filename, size, MIME type, and **SHA-256**. Its `id` is the stable `document_id` that `Evidence` references. Its SHA-256 lets anyone verify that the bytes cited as evidence are the bytes that were uploaded. SHA-256 is not unique: identical bytes uploaded twice are two `Document`s, and provenance records which one was actually used.
- **`RevisionDocument`** is the revision-scoped interpretation: document type, number, description, notes, origin (`UPLOADED` / `INHERITED`), and `INCLUDED` / `REMOVED` status. It answers "which documents were part of revision N's package, and how were they classified at the time?"
- **Inheritance preserves identity.** A document carried from Revision 0 into Revision 1 is the same `Document` (same `document_id`, same SHA-256, same object). Evidence extracted from it is valid in every revision that includes it. `inherited_from_revision_id` records which revision it came from.
- **Replacement is a new `Document`.** A superseding drawing is a new upload with a new `document_id`; the old one is marked `REMOVED` in the new revision and stays `INCLUDED` in the old one.

### Rules for later phases

- Evidence references `document_id`. Where the revision context matters (for example "what did the engineer have in Revision 2 when this value was verified"), also record the `revision_document_id`.
- Inheritance is a **snapshot at revision-creation time**; an ACTIVE revision's package stays editable, so its document set can change after a model was built from it. Anything derived from documents must record the `Document` identity it used rather than assuming the revision's package is fixed.
- Document pages, OCR text, and other normalized artifacts (Phase 3) attach to `Document`, not `RevisionDocument`.

## Evidence

Conceptual structure:

```
Evidence
    document_id
    page_number
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

Confidence is generated from extraction evidence and may later be adjusted by reconciliation. It remains stored with the attribute, not only on the parent entity.

## Source hierarchy

Source types (SLD, shop drawing, nameplate, schedule, photograph, specification) participate in configurable source-priority rules. Provenance records the source type so reconciliation can explain why a value was suggested.

## API

Engineers retrieve evidence without loading entire files into the model payload:

```
GET /api/equipment/{id}/evidence
```

The document viewer uses page images and bounding boxes to highlight the region that produced a value.

## Phase 0

Phase 0 defines evidence contracts in `packages/provenance`. Persistence of evidence rows begins when extraction writes candidates (Phase 6) and when the engineering model stores verified attributes (Phase 5+).

Phase 2 does not create evidence. It creates the immutable `Document` and revision-scoped `RevisionDocument` records that evidence will reference.
