# Phase 6A implementation plan

Base: `d48200224bbd3a5a0098ab49d666695b0f930c8c` (refreshed `origin/main`).
Branch: `codex/phase-6a-extraction-persistence`.

The approved Phase 6 specification and ADR-008 are already committed at the required paths; preserve them byte-for-byte. Phase 5 and registry-v1 remain frozen.

1. Add provider-neutral extraction/provenance contracts, exact typed values, source locations, versioned table layouts and bounded telemetry.
2. Add eight ORM mappings and frozen migration 0011. Enforce composite ownership, active identity/attempt uniqueness, typed slots, completed processing inputs, immutable output and atomic successful publication.
3. Add an internal transaction-participating persistence boundary and six revision-document GET routes. Resolve INCLUDED membership, preserve inherited/historical access, select effective successful units, paginate deterministically, and sign exact artifact references.
4. Test domain semantics, live PostgreSQL publication/rollback/ownership/history, HTTP precision/access/read-only behavior and fresh/0010 upgrade/downgrade compatibility. Run backend regression, lint, formatting, dependency and OpenAPI checks.
5. Reconcile current documentation with the approved 6A–6G slices and record actual validation in PHASE6A_HANDOFF.md. Scheduling, providers, retries/recovery, AI/OCR/table interpretation and frontend remain deferred.

All five steps are complete. Initial delivery validation: 1,098 live backend tests passed (32 focused Phase 6A cases); see [PHASE6A_HANDOFF.md](PHASE6A_HANDOFF.md) for exact results and boundaries.

Review follow-up: add forward migration 0012 for terminal-state consistency and validate text-offset bounds from exact verified storage artifacts. Validation after corrections: 1,114 live backend tests passed (48 focused Phase 6A cases). See the handoff review-corrections section for exact results.
