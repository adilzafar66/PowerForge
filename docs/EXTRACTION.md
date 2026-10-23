# Extraction

AI extraction proposes candidate engineering data. It does not mutate the verified engineering model.

Phase 0 established interfaces and candidate contracts; Phase 4 classification is implemented. Full Evidence/ExtractionCandidate persistence and structured extraction are planned for Phase 6, as described in [ROADMAP.md](ROADMAP.md). They are not implemented through Phase 5B.

## Principles

- Do not use one enormous prompt for an entire project.
- Use specialized extractors with explicit input/output contracts.
- Validate all model output against Pydantic schemas. Never trust raw LLM output.
- Store provider, model, model version, prompt version, and timestamp with extraction metadata.
- Application domain logic must not import vendor SDKs.

## Pipeline

```
Document / DocumentPage
    → native text / OCR / visual / table inputs
    → Evidence
    → ExtractionRun
    → ExtractionCandidate
    → schema + canonical-registry validation
    → candidate records for later entity resolution / reconciliation
```

This is a conceptual traceability flow, not a frozen persistence schema. AI output remains an evidence-linked candidate. Phase 6 owns run metadata, provider/model/prompt versions, retry/versioning semantics, equipment/attribute and schedule/table extraction, OCR/layout where needed, and extraction evaluation/hardening. Candidate keys, types, and units must map to the canonical registry. Confidence is recorded at candidate/evidence level; regions use normalized upright DocumentPage coordinates, as defined in [PROVENANCE.md](PROVENANCE.md).

Candidates proceed to entity resolution (7), reconciliation/conflict management (9), deterministic validation (10), and engineer review (11). They never silently overwrite canonical values or become engineer-verified truth. Extraction may also target approved revision metadata such as `system_frequency` and `system_phase_count`: a title block stating `600 V, 3Ø, 60 Hz` supplies evidence for candidates, not permission to change canonical revision settings.

The proposed 6A–6G slices in [ROADMAP.md](ROADMAP.md) are non-binding. Study-domain/protection extraction requires approved target-domain design first.

## Specialized extractors

| Extractor | Role |
| --- | --- |
| `DocumentClassifier` | Document type + confidence |
| `EquipmentExtractor` | Equipment mentions and types |
| `AttributeExtractor` | Typed attributes with units |
| `TableExtractor` | Schedules and tabular sources |
| `SLDExtractor` | Symbols, text, components on SLDs |
| `TopologyExtractor` | Connection candidates |
| `EntityMatcher` | Duplicate / same-physical-entity candidates |

Each extractor has a versioned prompt (or equivalent artifact) and a Pydantic output schema.

## Provider abstraction

`packages/ai` defines:

- `LLMProvider`
- `VisionProvider`
- `OCRProvider`
- `EmbeddingProvider` (only if required later)

Conceptual contract:

```
extract_structured(input, schema, context) -> structured_result
```

The engineering application does not care which vendor produced the result. Swapping OpenAI, Anthropic, Gemini, or an on-prem model must not change the engineering model.

## Prompt versioning

Future extraction prompts are planned under `packages/ai/prompts/` (version-controlled). Do not bury large prompts inside random application files.

Examples:

- `equipment_extraction_v1`
- `equipment_extraction_v2`
- `sld_extraction_v1`

The prompt version is stored with the extraction result for reproducibility.

Phase 0 created that directory and a README. The implemented Phase 4 classification prompts live in their owning classification package, as described below.

## SLD extraction

SLD interpretation is not ordinary OCR. Planned pipeline (Phase 8):

```
SLD PAGE
    → IMAGE PREPROCESSING
    → SYMBOL / COMPONENT DETECTION
    → TEXT DETECTION
    → TEXT-COMPONENT ASSOCIATION
    → EQUIPMENT IDENTIFICATION
    → CONNECTION DETECTION
    → TOPOLOGY CANDIDATE
    → VALIDATION
    → ENGINEER REVIEW
```

Preserve the original image and source-page evidence, with regions normalized to the upright DocumentPage. Phase 8 produces component, terminal/connectivity, and topology candidates targeting Phase 5D ModelNode/ModelConnection semantics. The SLD is not the database.

## Entity resolution

Entity resolution is a first-class module (Phase 7). Signals include tag similarity, type, location, connected equipment, manufacturer, model, rating, voltage, document context, spatial proximity, and surrounding topology.

Planned outputs retain candidate identity, match confidence, supporting evidence, and conflicting evidence; exact contracts require a formal specification. The bridge is ExtractionCandidate → candidate physical identity → EquipmentLineage / revision-scoped Equipment. Do not automatically merge low-confidence matches.

## Phase 4 classification

Specified in `cursor/phase4_specs.txt` and [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Accepted). Complete (2026-10-12).

Phase 4 is the `DocumentClassifier` row above and nothing else in that table. It chooses a document class, and sometimes a page class, from the existing taxonomy plus `MIXED_DOCUMENT`. It does not extract equipment, attributes, tables, or topology.

The provider contract stays vendor-neutral (`ClassificationProvider`). OpenAI is the first adapter, in `extraction_worker.openai_classification`. Tests and local Compose use a fake provider. Classification prompts live in `powerforge_document_classification` (`document_classifier_v1` and `page_classifier_v1`). They are not under `packages/ai/prompts/`.

## Out of scope until named phases

- Phase 3: document processing renders pages and reads native PDF text. It does not call `OCRProvider` or any classifier
- Phase 4: classification is complete. Equipment, table, and SLD extractors stay in their own later phases
- Phase 6: Evidence/candidate persistence and structured equipment/attribute/table extraction, with OCR/layout support as needed
- Phase 7: entity resolution
- Phase 8: SLD extraction
- Phase 9: reconciliation and persistent conflict management; Phase 11 retains human decision/verification authority
