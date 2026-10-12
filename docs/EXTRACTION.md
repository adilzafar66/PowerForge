# Extraction

AI extraction proposes candidate engineering data. It does not mutate the verified engineering model.

Phase 0 defines provider interfaces, prompt versioning location, and candidate contracts. It does not call models, run OCR, or interpret SLDs.

## Principles

- Do not use one enormous prompt for an entire project.
- Use specialized extractors with explicit input/output contracts.
- Validate all model output against Pydantic schemas. Never trust raw LLM output.
- Store provider, model, model version, prompt version, and timestamp with extraction metadata.
- Application domain logic must not import vendor SDKs.

## Pipeline

```
AI OUTPUT
    → SCHEMA VALIDATION
    → DOMAIN VALIDATION
    → CANDIDATE RECORD
```

Only candidate records proceed to entity resolution, validation, and reconciliation.

## Specialized extractors (later phases)

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

Prompts live under `packages/ai/prompts/` (version-controlled). Do not bury large prompts inside random application files.

Examples:

- `equipment_extraction_v1`
- `equipment_extraction_v2`
- `sld_extraction_v1`

The prompt version is stored with the extraction result for reproducibility.

Phase 0 creates the directory and a README. No production prompts yet.

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

Preserve the original image and evidence coordinates. The SLD is not the database.

## Entity resolution

Entity resolution is a first-class module (Phase 7). Signals include tag similarity, type, location, connected equipment, manufacturer, model, rating, voltage, document context, spatial proximity, and surrounding topology.

Output includes `candidate_entity`, `match_probability`, `matching_evidence`, and `conflicting_evidence`. Do not automatically merge low-confidence matches.

## Phase 4 classification

Specified in `cursor/phase4_specs.txt` and [ADR-006](../decisions/ADR-006-ai-document-classification.md) (Accepted). Complete (2026-10-12).

Phase 4 is the `DocumentClassifier` row above and nothing else in that table. It chooses a document class, and sometimes a page class, from the existing taxonomy plus `MIXED_DOCUMENT`. It does not extract equipment, attributes, tables, or topology.

The provider contract stays vendor-neutral (`ClassificationProvider`). OpenAI is the first adapter, in `extraction_worker.openai_classification`. Tests and local Compose use a fake provider. Classification prompts live in `powerforge_document_classification` (`document_classifier_v1` and `page_classifier_v1`). They are not under `packages/ai/prompts/`.

## Out of scope until named phases

- Phase 3: document processing renders pages and reads native PDF text. It does not call `OCRProvider` or any classifier
- Phase 4: classification is complete. Equipment, table, and SLD extractors stay in their own later phases
- Phase 6: structured document extraction
- Phase 7: entity resolution
- Phase 8: SLD extraction
- Phase 9: cross-document reconciliation
