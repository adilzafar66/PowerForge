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

## Out of scope until named phases

- Phase 4: classification
- Phase 6: structured document extraction
- Phase 7: entity resolution
- Phase 8: SLD extraction
- Phase 9: cross-document reconciliation
