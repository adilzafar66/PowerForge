# ADR-001: Engineering model independence from AI providers and analysis software

## Status

Accepted

## Date

2026-09-02

## Context

PowerForge extracts electrical engineering information from documents and builds a centralized engineering model. Two coupling risks would make the product brittle and unsafe:

1. **AI vendor coupling.** Extraction will use LLMs, vision models, and OCR. Those vendors, models, and prompt versions will change. If equipment tables, APIs, or UI flows import a specific SDK or assume a vendor-specific payload shape, changing providers becomes a domain rewrite.

2. **Analysis software coupling.** Downstream tools (ETAP, SKM, EasyPower, and others) will eventually consume the model. If the schema is designed around one vendor’s device library, study file format, or calculation engine, PowerForge becomes an adapter instead of a source of truth. Calculations and report generation are explicitly out of scope for this application phase.

The verified engineering model must remain valid even if every AI provider is replaced and even if no analysis package is ever integrated.

## Decision

The engineering model is an independent domain.

- `packages/engineering-model` and the PostgreSQL schema for equipment, attributes, connections, revisions, and verification state have **no** imports of AI vendor SDKs and **no** ETAP/SKM/EasyPower types.
- AI systems write **candidate** records through extraction contracts. Candidates are schema-validated, then validated, reconciled, and reviewed before they can become verified model state.
- Provider, model, model version, and prompt version are stored as **provenance metadata** on evidence/extraction records, not as the identity of equipment.
- `packages/ai` is the only place vendor adapters may live. Domain packages depend on provider **interfaces**, never implementations.
- Export (JSON, CSV, Excel) is a consumer of the model. Analysis-tool adapters, if added in a future product, are also consumers. They do not own the schema.
- Short-circuit, coordination, arc-flash, and report generation are not part of PowerForge’s model or API in this phase.

## Consequences

**Positive**

- The model remains the source of truth after engineer verification.
- AI providers can be swapped without migrations of equipment identity.
- Analysis software can be introduced later as exporters/adapters without retrofitting the core schema.
- Safety states (`AI_EXTRACTED` vs `ENGINEER_VERIFIED`) stay domain concepts, not vendor features.

**Negative**

- Extraction payloads must be mapped into candidate schemas instead of stored as raw vendor JSON as truth.
- Export to a given analysis tool will require an explicit adapter when that product work is in scope.

**Compliance**

Any PR that imports an AI SDK or analysis-vendor client into `packages/engineering-model`, `packages/topology`, `packages/provenance`, or `packages/validation` violates this ADR.
