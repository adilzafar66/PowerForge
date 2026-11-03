# Phase 6A handoff — Evidence and extraction persistence

## Baseline and authority

Implementation branch: `codex/phase-6a-extraction-persistence`.
Actual base: `d48200224bbd3a5a0098ab49d666695b0f930c8c`, refreshed `origin/main` before branching.
Date: 2026-11-02 (America/Vancouver).

The exact [approved Phase 6 specification](specs/phase-6-evidence-structured-extraction.md) and [accepted ADR-008](../decisions/ADR-008-evidence-candidate-extraction-architecture.md) were already committed in that base. Their contents are unchanged, including manual-only revision settings, optional mention/group associations and the Phase 7 identity boundary. Historical accepted ADRs and Phase 5 handoffs remain unchanged. Registry-v1 and all canonical engineering semantics remain frozen.

## Delivered contracts and storage

`powerforge_extraction.contracts` defines pure, provider-neutral validated inputs; `powerforge_provenance.locations` defines normalized upright regions/source locations. Neither module imports ORM, HTTP, Celery or vendor SDKs. Separate `models` and `persistence` modules in the extraction package follow the existing classification-package convention and reuse the shared SQLAlchemy Base.

All eight logical entities are implemented:

- ExtractionRun: immutable source/processing, artifact IDs, page/stage selections, extractor/schema/registry/profile/provider/model/prompt identities, input hash, optional context fingerprint, initiating association, actor and re-extraction lineage; six run statuses, progress, timestamps and bounded errors.
- ExtractionWorkUnit: stable logical key/stage, required flag, page/artifact inputs, numbered attempts and same-key retry ancestry, five statuses, timing, reserved lease/heartbeat fields, bounded execution metadata and output counts. Lease execution/recovery is not implemented.
- Evidence: document/page/processing/unit provenance, exact artifact, source kind/method, bounded snippet, Unicode-codepoint offsets, optional normalized region and table/cell locator. Unknown geometry stays null.
- SourceGroup: immutable run-local key, producing unit, optional registry type hint, actually observed tag/label and grouping evidence. A group can be reused by later successful units through their candidate associations; it is never canonical Equipment.
- ExtractedTable: versioned `table-layout-v1` JSONB with rows, columns, header cells, spans, source locations/IDs and bounded metadata; attribute rows, equipment rows, mixed and unclassified orientations. Individual interpreted values remain relational candidates.
- ExtractionCandidate: equipment mention, attribute value or unmapped observation, raw expression/value/unit, optional group/mention, registry type/key, mapping status, typed slots, canonical unit, optional confidence/method/band and bounded diagnostics.
- CandidateEvidence: many-to-many citations with PRIMARY/SUPPORTING/CONTRADICTING role and stable position.
- ExtractionAICall: technical provider/model/prompt/schema/correlation/outcome/timing/token metadata; exact optional USD estimate requires pricing basis. No credentials, prompts or document payload fields exist.

Mapped attributes validate registry-v1 type/key/unit/value/ENUM semantics. NUMBER is Decimal/NUMERIC, INTEGER is strict signed 64-bit int/BIGINT, and API JSON uses strings for both. Explicit BOOLEAN false remains false. Unmapped/invalid observations retain raw content; tagless and isolated attributes are valid. Missing attributes do not synthesize candidates. Work-unit outputs are capped at 8 MB and diagnostics/execution metadata at 16 KB.

## Migration and integrity

`0011_extraction_persistence` follows `0010_authoring_refinement`. Its frozen DDL contains no imports of runtime registry or ORM definitions. It adds the eight tables, closed-vocabulary PostgreSQL enums, query/history indexes and one harmless composite uniqueness constraint on existing PageArtifact identity/context.

Composite foreign keys enforce run/processing/document, work-unit/run/document/processing, evidence/page/document, evidence/artifact/page/processing, group/mention/candidate and candidate/evidence ownership. Triggers additionally require completed processing, pinned artifact/page selections, compatible context/initiator, valid retry ancestry and equipment-mention association kinds. Checks reject incompatible typed slots, nonfinite numerics, out-of-range confidence/geometry/usage/cost and incomplete text offsets. Registry semantic checks and nested table/group/cell reference checks occur at the internal persistence boundary; arbitrary direct SQL is not a registry-mapping interface.

Partial unique indexes prohibit equivalent active runs, concurrent active attempts for a logical key and duplicate successful attempts. Completed runs do not block deliberate new re-extraction. Run input identity, historical attempts and published output are immutable. Completion requires success for all required logical keys; partial completion requires useful required successes plus unsuccessful required keys; FAILED cannot discard useful required successes.

Immutable-output triggers reject changes/deletes and late inserts. Deferred publication triggers reject a transaction that inserts result output without successful unit completion. Telemetry is deliberately exempt from the success-only publication guard so technical failures can survive failed attempts; it remains immutable and owned by its producing attempt.

## Internal publication boundary

`ExtractionPersistence(session, storage=None)` participates in the caller's transaction and never commits independently:

- `create_run(RunInput)` revalidates inputs and computes an order-stable SHA-256 identity. No work is scheduled.
- `create_work_unit(run_id, WorkUnitInput)` appends a validated attempt and updates logical-unit totals. There is no retry scheduler or external mutation API.
- `publish(work_unit_id, WorkUnitOutput)` revalidates inputs, locks parent run then unit, and uses a savepoint to insert groups/tables/evidence/candidates/citations/optional telemetry plus the unit success marker and progress. Failed validation or persistence rolls back the whole publication; the caller still owns the outer commit/rollback.
- `record_ai_call(work_unit_id, AICallInput)` appends technical telemetry while an attempt is running, even if that attempt subsequently fails.

The caller must use a dedicated session/unit of work, persist the chosen logical plan, transition its run/unit to RUNNING before publication and commit the outer transaction. Publication accepts no canonical IDs and calls no canonical write service. No provider or object-storage writes occur here. Text-offset evidence requires an ObjectStorage argument: publication streams and verifies the exact pinned UTF-8 artifact, counts Unicode codepoints once per artifact, and rejects offsets beyond that immutable representation. It does not use mutable page-level text counts. Missing storage or failed artifact verification aborts publication; non-offset output can still use a database-only instance.

## Read API and access

The common prefix is `/api/projects/{project_id}/revisions/{revision_id}/documents/{revision_document_id}/extraction`.

- GET the prefix: `ExtractionSummary`, latest completed/partial result and current run.
- GET `/runs`: paginated `RunList`.
- GET `/runs/{run_id}`: `RunDetail` with immutable input identity, all attempts and effective coverage.
- GET `/runs/{run_id}/candidates`: `CandidateList`, raw/normalized values, optional group summary, ordered citations, completeness/coverage and filters for kind, mapping status, source group, equipment type and attribute.
- GET `/runs/{run_id}/tables`: paginated `TableList` including versioned layout and source context.
- GET `/evidence/{evidence_id}`: `EvidenceDetail`, snippet, page/region/text/cell locator and an optional short-lived URL for the exact pinned artifact.

All responses use explicit Pydantic allowlists. Lists default to limit 50, cap at 200, accept nonnegative offsets and order deterministically with UUID tie-breakers. Provider error messages, storage keys and execution metadata are omitted. Existing domain error envelopes and signed-storage error handling are reused. There are no extraction POST endpoints or GET side effects.

Each reader resolves INCLUDED RevisionDocument membership against the path project/revision and its immutable Document. Results can be reused from inherited, superseded or otherwise read-only revisions without copying results or changing the canonical model. Unrelated membership/run/evidence access returns 404. Source-only runs apply to included revisions; context-dependent runs require their explicitly fingerprinted revision. Current processing/artifact selection is never substituted for historical pinned evidence.

Effective queries select only COMPLETED work-unit attempts; database uniqueness makes the selection unambiguous per logical key. Failed/cancelled/prior attempts remain in run detail and do not enter candidate/table results. A successful unit is never replaced. Partiality and actual required-unit coverage remain explicit. Only PRIMARY/SUPPORTING-cited candidates enter the default sourced list; `supported_only=false` also returns explicitly unsupported observations. No result is labeled engineer-verified.

## Validation

**Phase 6A is implemented and its acceptance checks passed. Phase 6B–6G remain unimplemented.**

Initial delivery full backend regression: **1,098 passed, no skips**, six existing dependency deprecation warnings, in 130.36 seconds, with live isolated PostgreSQL/MinIO. Command:

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:55436/powerforge_phase6a_final \
S3_ENDPOINT_URL=http://localhost:59006 RUN_INTEGRATION=1 \
.venv/bin/pytest -q --tb=short
```

The standalone offline contract/OpenAPI suite also passed: **16 passed**. Final lint/format/whitespace and dependency checks passed.

Focused Phase 6A suite: **32 passed**, no skips, against live disposable PostgreSQL/MinIO (six existing dependency deprecation warnings). Covers contracts/OpenAPI precision, ownership, pinned processing/artifacts, database immutability, false completion, atomic rollback after inserted output, duplicate identities/attempts, partial-success history, retry ancestry, structured table orientations, tagless/run-local grouping, many-to-many citations, technical failure telemetry, HTTP filtering/pagination, inherited/superseded/context access and SELECT-only GET requests.

Fresh empty-to-head migration passed. Dedicated scratch-database tests passed for fresh ORM/schema agreement and representative `0010` data-preserving upgrade, downgrade and re-upgrade. Existing projects/revisions/documents/pages/processing/classification/equipment/attributes/nodes/connections were compared before/after. The historical 0010 tests now explicitly target their own revision rather than assuming they are forever Alembic head.

Ruff lint, changed-file formatting, OpenAPI JSON serialization and the six-GET-only contract passed. Editable extraction/API builds and dependency metadata checks passed after registering the already-existing local classification package. `git diff --check` passed. The initial migration head was `0011_extraction_persistence`; review hardening adds `0012_extraction_terminal_guard` as the current single head; offline SQL generation for `0010_authoring_refinement:head` passed. Full-chain offline SQL generation hits the pre-existing 0006 migration's live catalog query and is not supported; actual fresh online migration passed.

Disposable infrastructure used Compose project `powerforge-phase6a`, PostgreSQL on `127.0.0.1:55436`, MinIO on `127.0.0.1:59006` and tmpfs storage. Final full regression uses database `powerforge_phase6a_final`; migration cases create and drop uniquely named scratch databases on that same disposable PostgreSQL. The normal development database/volumes were not migrated or used for test writes. The disposable containers/network were removed after validation; tmpfs test data was discarded.

## Deviations and limitations

No material architecture deviations. The approved documents were already committed, so they were preserved rather than re-added. ORM/application persistence lives in the owning extraction package, sharing the existing neutral Base, as classification already does. JSON table/group/cell and registry semantics are validated in the internal service, complementing essential database ownership/shape/immutability constraints.

No frontend code changed; frontend/browser checks were not run. No live AI calls, extraction profiles/prompts, OCR, detection/interpretation, automatic matching, reconciliation or review actions were implemented. Authentication remains the repository's existing deferred prerequisite; route membership checks do not claim a new user-authentication system. Offset pagination has normal concurrent-insertion behavior; ordering is deterministic. Phase 6B must define compatibility/profile defaults and execution policy before public start/retry/cancel operations are introduced.

The known remote CI MinIO `latest` availability issue remains outside this change. Local live storage checks use the already available image and succeed; no remote GitHub Actions pass is claimed and no infrastructure redesign was introduced.

## Review corrections before 6B

Both reported findings were confirmed and fixed on the existing implementation branch after `c3c9a42`.

Follow-up migration `0012_extraction_terminal_guard` preserves migration 0011 and upgrades databases that already applied it. A database trigger rejects every terminal parent state (COMPLETED, PARTIALLY_COMPLETED, FAILED and CANCELLED) while any required or optional attempt remains PENDING/RUNNING. Settle and flush active attempts before finalizing the run; no automatic cancellation or history rewriting is introduced. Existing parent locking serializes the check with work-unit creation/updates. Regression tests verify rejection leaves the attempt writable, valid terminal transitions after settling, and concurrent unit creation. Fresh upgrade and data-preserving 0011 upgrade/downgrade/re-upgrade are covered.

Text-offset bounds now come from the exact pinned native-text object's UTF-8 codepoints, not the stable page's mutable summary count. The storage stream uses bounded chunks and strict incremental decoding, verifies the artifact's byte size and SHA-256, closes on failures and caches the count only within one publication. Text-offset evidence requires storage; validation never falls back to page metadata. Tests cover both shorter and longer later-processing summaries, Unicode/combining characters and a multibyte character across a chunk boundary, repeated citations, corrupted/truncated/invalid UTF-8 objects, absent storage and publication rollback.

Focused review/Phase 6A checks: **48 passed**, six existing dependency warnings. Final post-review full backend regression: **1,114 passed, no skips**, six existing dependency warnings, in 109.96 seconds. The same disposable stack was recreated for review testing with database `powerforge_phase6a` on port 55436 and MinIO on port 59006, then removed after validation. Ruff lint/changed-file formatting, whitespace, dependency checks, unchanged six-GET OpenAPI contracts and offline 0011-to-head SQL generation passed. The 0011 migration tests now explicitly target 0011 rather than assuming it is forever head.

## Phase 6B handoff

Implement scheduling, prerequisite/profile selection, input compatibility policy, provider-neutral fake/real execution and explicit provider enablement. Supply ObjectStorage for text-offset publication and treat unavailable/unverifiable artifacts as publication failures. Settle/flush all active attempts, including optional ones, before terminal run transitions. Create the stable required-unit plan, then drive controlled run/attempt statuses through the existing persistence boundary. Add leases/heartbeats, stale recovery, bounded retries/backoff/budgets, cancellation and duplicate-delivery/late-completion handling. Never resend or replace a committed successful logical key; retain failures/telemetry and preserve successful siblings. Public start/retry/cancel endpoints belong to that slice. Keep provider credentials on workers and persist only sanitized failure metadata.

Subsequent 6C equipment/attribute extraction, 6D table interpretation, 6E OCR/layout, 6F extraction/evidence UI/evaluation and 6G hardening/freeze remain **unimplemented**. Phase 6 as a whole is **not complete**.
