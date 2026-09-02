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
