# Phase 6B technical design

Base: `0acf38f14c389bf8933edc05c4c52e894b71e2d6` (refreshed origin/main).
Branch: `codex/phase-6b-extraction-orchestration`. Authority: approved Phase 6 specification, ADR-008, accepted 6A and its two review corrections. The supplied Phase 6B prompt is preserved.

## Flow and profiles

Resolve INCLUDED revision-document membership without canonical write guards; lock the immutable Document to serialize ensure/re-extract decisions. Pin the current completed processing run, exact native-text/analysis artifacts, explicit sorted pages and a fully serialized versioned execution profile. Persist the run, stable stage/page keys and delivery records in one transaction. Dispatch after commit; a periodic reconciler rediscovers persisted-but-undelivered work.

Ship an explicitly labeled deterministic fake/test source-probe profile (default manual path) and an explicitly enabled OpenAI infrastructure source-probe profile. They exercise transport, bounded structured responses, provenance and publication, not production equipment/table/OCR interpretation. Unknown/mixed classification is no barrier. Explicit profile selection overrides the default. No automatic post-processing extraction is added; no external calls are enabled by default.

Profile snapshots pin stage/input strategy, model/provider, versioned prompt/schema hash, partition size, byte/pixel/output bounds, retry/backoff/timeout/lease limits and per-run provider-call admission budget. The snapshot contributes to the existing immutable identity hash. A known pricing basis may estimate usage costs; otherwise money remains unknown. Bounded calls, tokens and input sizes provide the initial approved-equivalent spending control; no strict dollar ceiling is claimed with unknown prices.

## Ownership, concurrency and publication

Migration 0013 adds execution-control records beside existing immutable run/attempt/output records. PostgreSQL is authoritative; Celery/Redis only transport notifications. Pending delivery records act as a durable outbox with bounded re-dispatch, including send/ack crash windows.

Claims acquire a short global admission lock, then run/unit/control row locks. A pending eligible attempt receives one unguessable fencing token, lease, heartbeat and absolute execution deadline; claim commits before provider/object I/O. Duplicate deliveries cannot claim again. Global/run concurrency and total call admissions are bounded in the same transaction. A heartbeat uses separate short transactions and cannot extend past the absolute deadline.

Completion checks the current token, unexpired lease, active run and absence of cancellation under locks. It sets a transaction-local token for additional DB publication fencing and invokes 6A atomic publication with verified pinned-artifact text validation. Network provider calls never run inside a DB transaction. Stale/expired/cancelled workers cannot publish; successful outputs and attempts remain immutable. Technical failures use bounded safe categories and retain known usage; interrupted calls may have unknown charges, never invented telemetry.

## Retries, recovery and aggregate states

Failures settle their attempt before bounded transient retries append a new attempt with the same pinned logical inputs, ancestry and exponential available-at backoff. Permanent/invalid responses do not auto-retry. Manual retry of failed/partial runs appends only unsuccessful keys within the same pinned attempt budget; successful keys are never resent. Expired leases settle as interrupted failures and are retried within limits. The reconciler also re-dispatches due pending records and aggregates outcomes after restart.

Temporary object-storage access and streaming failures use a typed storage-port error, recorded as `SOURCE_UNAVAILABLE`, and enter that same bounded retry path. Missing/corrupt/invalid sources and permanent access/configuration failures do not automatically retry. Recovery selects expired leases in expiry order, then parents with only settled work to aggregate; healthy active runs cannot consume the batch ahead of newer expired work.

No parent becomes terminal while any required or optional attempt remains active. After all attempts settle, required-key successes determine COMPLETED/PARTIALLY_COMPLETED/FAILED; optional failures remain visible. Cancellation locks the run, records intent, settles pending/running attempts as CANCELLED, fences late responses and then marks the run CANCELLED, retaining successful units. Repeated cancellation is safe. A completed run cannot be retroactively cancelled.

Cancelled and completed run history remains immutable. POST retry on CANCELLED requests explicit re-extraction instead of weakening 6A guards; POST runs with re-extract creates a new linked historical run. Failed/partial runs can resume as RUNNING. Equivalent active input identities are always reused, even for repeated re-extract requests. Ensure may reuse compatible COMPLETED results. If no completed result exists, repeating ensure returns the compatible failed/partial/cancelled run without creating new billable work; continuing requires explicit retry or re-extraction. This explicitly resolves the cancelled-history ambiguity without an architectural departure.

## API, operations and verification

Preserve six existing GETs, extend safe run detail with execution/cancellation/usage/retry information, and add profile discovery plus POST start/ensure/re-extract, retry and cancel. Requests use strict allowlists and existing scoped error envelopes. No public task tokens/IDs, private keys, provider payloads or credentials.

Use the existing extraction worker with a separate extraction queue and periodic Celery beat reconciler; classification remains separate. Add fake/mocked-provider tests, live DB races/fencing/recovery/cancellation/budget tests, disposable Redis/MinIO/Celery end-to-end tests, migration upgrade/downgrade checks and full backend regression. Update current documentation and write PHASE6B_HANDOFF.md with actual results, limitations and 6C extension contracts. No frontend or canonical-model changes.

## Completion

Implemented and validated: 1,184 backend tests passed with live isolated PostgreSQL/Redis/MinIO/Celery, no skips, including 70 new 6B cases (27 covering the storage/recovery review corrections). Exact implementation boundaries, guarantees, setup, verification and deferred production extraction are recorded in [PHASE6B_HANDOFF.md](PHASE6B_HANDOFF.md).
