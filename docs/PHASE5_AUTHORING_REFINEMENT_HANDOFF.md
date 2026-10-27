# Phase 5 authoring refinement handoff

Implemented on `codex/phase-5-authoring-refinement`, based on accepted Phase 5G commit `7067f693efe45ead37a60a98c8d57eb385b5c338` on `codex/phase-5g-hardening`. Work is uncommitted at this handoff; no push or merge is claimed. Authority: [authoring refinement prompt](prompts/phase-5-refinement.md), the Phase 5 specification with its explicit amendment notice, ADR-007 and unchanged registry-v1.

## Decisions and implementation

- **Automatic physical terminals:** immutable code-owned profiles cover all 20 equipment types, separately from registry-v1. Creation materializes normal terminals in the equipment transaction. Relays have no normal terminals; protection functions are not physical terminals.
- **Managed/custom distinction:** `ModelNode.managed_by_profile` is a non-null Boolean. Electrical nodes cannot be profile-managed. API writes cannot forge the flag. Managed keys cannot be changed, and required profile terminals cannot be independently removed. Labels can be edited; custom terminals retain manual key/label/lifecycle editing.
- **Type reconciliation:** matching profile nodes keep their IDs; matching custom nodes are adopted, preserving labels/provenance/endpoints; newly required roles materialize. Obsolete managed roles are soft-removed only when they have no active incident connections. Otherwise the type change returns 409 and rolls back. Unrelated custom nodes survive. Retired managed roles keep their history and cannot be independently restored; equipment restoration does not resurrect obsolete roles. A later type requiring the same role reuses/reactivates it, without restoring edges.
- **Empty state:** the Python and PostgreSQL InformationState vocabularies are exactly PRESENT, MISSING, NOT_APPLICABLE, NOT_POPULATED and CONFLICTING. Manual reset to NOT_POPULATED clears all typed values, origin and confidence and sets UNVERIFIED. MISSING/NOT_APPLICABLE retain MANUAL/ENGINEER_REVIEWED semantics. CONFLICTING is not a manual target. Materialization, untouched checks, inheritance and requirement tests use the new vocabulary.
- **One equipment transaction:** GET/PATCH `/api/projects/{project_id}/revisions/{revision_id}/equipment/{equipment_id}/editor` returns `{equipment, attributes, terminals}`. PATCH accepts only changed `general`, keyed `attributes`, `create_terminals`, `update_terminals`, `remove_terminals`, and `restore_terminals`. Request allowlists reject injected provenance/ownership fields, empty changes and duplicate terminal operations; services enforce terminal ownership and revision mutability.
- **Shared services:** the existing mutation methods still commit by default for fine-grained APIs. Within the editor they use `commit=False`, flush under the same revision lock and leave commit to the outer unit of work. Any validation or database failure rolls back everything. Explicit existing-attribute resets run before type reconciliation; other attribute edits validate against the resulting type. The canonical response is validated while the revision lock is held, before the one commit.
- **One frontend draft:** General, Attributes and Terminals share state in the Equipment sheet. Tab switches preserve edits. Sticky top-right Save and Ctrl/Cmd+S invoke the same endpoint. No per-attribute, General or terminal Save remains inside equipment editing. Save is disabled when unchanged, invalid, busy, removed or read-only. Save success resets the draft from canonical data; failure retains it. Dirty close offers Save changes, Discard changes and Keep editing; save-and-close closes only on success. Browser unload warns about dirty work. Equipment lifecycle actions are disabled while dirty. Type changes reconcile on Save; destination attributes appear after the canonical response.
- **Topology tables:** Node and Connection rows open detail/edit sheets by mouse or keyboard, including removed/read-only records. Profile terminals show the owning equipment and managed role without rename/removal controls. Electrical-node creation, custom-terminal editing, connection editing and conservative lifecycle behavior remain. Removed connections cannot be restored unless both endpoints are active. Owner-label maps and active-node sets avoid repeated per-row scans.
- **Precision:** NUMBER and INTEGER retain JSON string representation and text drafts, including `9007199254740993`. BOOLEAN PRESENT still requires an explicit True or False choice. No JavaScript Number conversion was introduced.

The word UNKNOWN still legitimately occurs in the frozen registry's grounding choices and the separate document-classification vocabulary. It is removed from **InformationState**, not from unrelated domains or historical records.

## Migration 0010_authoring_refinement

The new head is `0010_authoring_refinement`, following `0009_topology_persistence`. It replaces the PostgreSQL enum transactionally, maps NOT_EXTRACTED → NOT_POPULATED and UNKNOWN → MISSING, recreates the typed-slot constraint and changes the default to NOT_POPULATED. Existing values and other metadata are retained.

The same migration adds the managed flag/shape constraint and backfills frozen profile definitions for every equipment type. Matching terminals retain IDs, labels, semantic provenance and connection endpoints. Missing terminals are inserted with the owner's lifecycle, including removed equipment. A removed required terminal on active equipment is reactivated, without restoring connections. Custom terminals remain intact. Existing revisions, including read-only snapshots, receive this schema backfill; ordinary authoring still respects revision locks/status.

Downgrade returns NOT_POPULATED to NOT_EXTRACTED and removes the managed flag/constraint. It retains all nodes and connections to avoid deleting connected data. The original UNKNOWN/MISSING distinction cannot be recovered after consolidation; both remain MISSING on downgrade. Re-upgrade adopts the same nodes without duplication. Migrations 0001–0009 are unchanged.

## Changed areas

- Pure domain: information enum, omitted-value documentation, new `terminal_profiles.py`; registry-v1 unchanged.
- Persistence: attribute default, node flag/check constraint, new migration 0010.
- Services/API: equipment creation/type/reset behavior, topology protections/restoration/inheritance, explicit shared transaction support, new editor service and strict schemas/routes.
- Frontend: controlled attribute/terminal fields, create-only general form, unified detail drawer and draft serializer, typed editor API, table/detail topology interactions and managed-node protection.
- Tests: targeted state/profile/editor/migration coverage; existing state, topology-count and UI tests updated to new behavior. Historical migration tests compare frozen historical vocabulary/schema and seed via SQL instead of calling current services against pre-topology schemas.
- Current docs/ADR: Engineering Model, Topology, Architecture, Validation, Roadmap, Project Status and an explicit amendment notice on the original Phase 5 specification. Historical Phase 5A–5G handoffs are unchanged.

## Validation

Backend commands use the existing `.venv`; frontend commands run from `apps/web`.

| Check | Result |
| --- | --- |
| `.venv/bin/ruff check .` | Passed |
| Changed Python files: `.venv/bin/ruff format --check …` | Passed |
| `.venv/bin/pip check` | No broken requirements |
| `.venv/bin/pytest -q` | 505 passed; 559 live-integration tests skipped; six existing dependency warnings |
| Full live command below | 1,064 passed; no skips; six existing dependency warnings |
| `npm run lint` | Passed; no ESLint errors/warnings |
| `npm test` | 248 passed across 16 files |
| `npx tsc --noEmit` | Passed |
| `npm run build` | Passed |
| `git diff --check` plus new-file whitespace checks | Passed |

Disposable infrastructure was created from the repository Compose configuration as project `powerforge-refinement-validation`, with its own PostgreSQL/MinIO volumes and network and localhost ports 15432/16379/19000. The normal `powerforge` development services and data were not used for destructive testing or migrated.

```sh
docker compose -p powerforge-refinement-validation -f /tmp/powerforge-refinement-compose.json up -d postgres redis minio minio-init
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:15432/powerforge .venv/bin/alembic -c database/alembic.ini upgrade head
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:15432/powerforge REDIS_URL=redis://localhost:16379/0 S3_ENDPOINT_URL=http://localhost:19000 S3_PUBLIC_ENDPOINT_URL=http://localhost:19000 RUN_INTEGRATION=1 CI=1 .venv/bin/pytest -q
```

The clean database migrated from empty to head. Migration tests also create independent scratch databases, upgrade representative 0009 data (all equipment types, both legacy information states, matching/custom terminals, an existing connection and removed equipment), assert retained IDs/endpoints and correct backfill, then downgrade/re-upgrade without duplicates. Fresh schema checks verify enum labels and ORM column alignment. Earlier migration-chain tests remain passing.

Focused tests cover every terminal profile, automatic creation, custom adoption/preservation, connected type-change rejection and rollback, managed-key/removal protection, conservative restore, reset provenance, one-commit editor saving, rollback after a late terminal uniqueness failure, ownership/read-only/anti-forgery, same-save reset/type change, and profile/custom carry-forward. Frontend tests cover tab preservation, one combined request, keyboard saves, dirty-close choices and failed saves, explicit BOOLEAN choice, lossless INTEGER JSON decoding/display/resubmission, state-only payloads, tables opening editors, managed controls, endpoint restore guards and read-only behavior.

Counts differ from 5G because the removed information-state vocabulary eliminates obsolete/duplicate cases, while focused refinement cases are added. Existing UI scenarios now exercise the unified editor rather than removed per-row save controls. No broad combinatorial suite or new test framework was added.

Session logs: `/tmp/refinement-{live,offline,web,web-lint,web-build,tsc,migrate}.log`. Validation infrastructure is removed after completion with:

```sh
docker compose -p powerforge-refinement-validation -f /tmp/powerforge-refinement-compose.json down --volumes --remove-orphans
```

No actual browser interaction test was performed; frontend evidence is the existing jsdom suite, TypeScript checks and production build. No Playwright/Cypress dependency was added.

## Remaining debt and re-freeze verdict

Unpaginated lists and whole-revision topology checks remain scaling debt. The combined editor reuses these correctness checks and may perform repeated reads for multi-field saves; no new caching or bulk-validation architecture was introduced. Authentication/actor identity, full audit history and optimistic concurrent-editor conflict detection remain deferred. Dirty sheet close and browser unload are protected; general SPA navigation interception is not a new routing subsystem. New destination-type fields are edited after type reconciliation succeeds. Downgrade cannot reconstruct the old UNKNOWN/MISSING distinction.

Zero dependencies were added. Registry-v1 and all historical handoffs remain unchanged. No EngineeringModel table, containment hierarchy, evidence/candidate persistence, AI extraction, reconciliation, verification workflow, protection/study model, graph visualization or export capability was introduced.

**Verdict:** all authoring refinement acceptance criteria pass. Phase 5 is complete / re-frozen. Phase 6 is next / not started.
