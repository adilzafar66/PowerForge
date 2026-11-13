# ADR-009 Phase 6R unified extraction

Accepted for Phase 6R on 2026-11-13. Supersedes ADR-008 for the 6R implementation. Baseline is `dea1ed3b9423dec9c1834672519e16c2853add49`.

## Decision

Use one document-scoped extraction family with revision-scoped access and operation-based start. Each eligible page uses sequential equipment recognition and attribute extraction against the same immutable page projection. Native text, OCR, visual inputs and local table layout are shared source inputs. Attribute extraction receives the exact successful recognition result and an applicable registry projection. Record an explicit eligibility skip with zero calls when successful recognition finds no eligible type.

AI supplies source-local classification, ownership and enum interpretation. PowerForge validates permitted keys and proposals, normalizes supported values with evidenced units, and localizes citations against the pinned artifacts. Preserve raw values, qualifications, alternate assertions and uncertain or unassigned ownership. Evidence localization, association and mapping remain independent. Resolved source geometry, approximate reported regions and unresolved citations are visible in Documents.

Use versioned immutable attempts and atomic publication. Existing preparation, storage, access control and worker infrastructure support the unified flow. Extraction emits candidate observations. Canonical authoring, topology and system metadata remain manual or follow their existing independent workflows. Phase 7 owns physical identity resolution.

Ship a clean-install migration graph without legacy extraction compatibility. Reset the whole designated database at cutover under exact-target authorization. B introduces the runtime and source schema. D adds complete candidate and evidence publication. Use the 6R-C authorized live feasibility checkpoint before D and the separate held-out 6R-F benchmark after finalizing numerical gates.

## Implementation references

- [Authoritative Phase 6R specification](../docs/specs/phase-6r-extraction-redesign.md)
- [6R-A contract and migration design](../docs/specs/phase-6r-contracts-v1.md)
- [Retirement inventory](../docs/PHASE6R_A_INVENTORY.md)
- [Evaluation protocol](../evals/phase6r/README.md)
