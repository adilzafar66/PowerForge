# Topology

The canonical electrical topology belongs to a project revision and is stored as relational nodes and connections. An SLD is evidence for future proposals, or a visualization generated from this model; it is never the database. [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md) and the [Phase 5D prompt](prompts/phase-5d-codex.md) define the boundary.

## Domain and persistence

The infrastructure-neutral `packages/topology` exports exactly:

- `ModelNodeKind`: EQUIPMENT_TERMINAL, ELECTRICAL_NODE.
- `ConnectionKind`: ELECTRICAL, GROUNDING, OTHER.
- `ConnectionDirection`: UNDIRECTED, NOMINAL_FROM_TO.

The old `NodeKind.BUS` placeholder is removed. A physical bus, switchgear, panelboard, or MCC is BUS Equipment with terminal nodes. A pure connectivity junction is an ELECTRICAL_NODE. CABLE is Equipment with terminals, never a connection kind. Equipment creation generates normal terminals from a code-owned profile. No connections are inferred or generated.

Migration `0009_topology_persistence` adds `model_nodes` and `model_connections`. Their ORM mappings live in `powerforge_persistence.topology` on the existing shared Base.

An equipment terminal requires same-project, same-revision equipment and a nonblank terminal key. Keys are trimmed by the service and unique per equipment snapshot, including removed terminals. Electrical nodes have neither equipment nor terminal key. Node kind and equipment ownership are immutable after creation; labels may be edited; only custom terminal keys may be edited.

Connections reference two distinct nodes in the same project and revision. Composite foreign keys enforce these ownership rules. Parallel edges are allowed. UNDIRECTED is the default; NOMINAL_FROM_TO gives the stored endpoint order descriptive significance without asserting power-flow direction.

Optional `phase_configuration` is trimmed text; blank becomes null. Optional nominal voltage uses Decimal/NUMERIC, is finite and positive, and is stored with unit `kV`. Value and unit must both be null or both present. Supported voltage inputs use the existing conversion utility, such as 600 V → 0.6 kV. Optional connection confidence is finite and bounded to [0, 1]. Nodes have no confidence column.

Both tables reuse model lifecycle, origin, and verification enums, have timestamps and nullable actor UUIDs, and carry same-project non-self inheritance references. There are no document/page/geometry fields or evidence shortcuts.

## Code-owned terminal profiles

`powerforge_engineering_model.terminal_profiles` is separate from the unchanged registry-v1 attribute metadata. Every equipment type has an explicit profile:

| Equipment | Normal terminal roles |
| --- | --- |
| UTILITY_SOURCE, SYNCHRONOUS_GENERATOR | OUTPUT |
| TWO_WINDING_TRANSFORMER | PRIMARY, SECONDARY |
| BUS | BUS |
| LV_BREAKER, HV_BREAKER, RECLOSER, FUSE, SINGLE_THROW_SWITCH, CT, REACTOR, VFD, UPS | INPUT, OUTPUT |
| DOUBLE_THROW_SWITCH | SOURCE_1, SOURCE_2, COMMON |
| CABLE | END_A, END_B |
| INDUCTION_MOTOR, STATIC_LOAD, LUMPED_LOAD, CAPACITOR | INPUT |
| OVERCURRENT_RELAY | None |

Migration `0010_authoring_refinement` adds non-null `ModelNode.managed_by_profile` (false for custom/electrical nodes), adopts matching existing terminals and backfills missing roles for all equipment, including removed snapshots. Existing IDs, labels, provenance and connection endpoints are retained. Required terminals follow the owner's lifecycle; adopting a removed required terminal on active equipment reactivates that node without restoring any connections.

Equipment creation and type reconciliation run in the same transaction as attributes. Type changes preserve matching profile terminals, adopt matching custom terminals, add newly required roles, and soft-remove obsolete profile roles only if they have no active incident connections. Otherwise the entire change returns 409. Unrelated custom terminals remain unchanged. Obsolete profile terminals keep their IDs/history and managed flag; they cannot be independently restored and are only reactivated if a later type requires that role again. GROUND/NEUTRAL and other exceptional custom roles remain possible. Relay protection functions are not topology terminals.

## Manual service

`TopologyService(session)` provides `create_terminal`, `create_electrical_node`, `get_node`, `list_nodes`, `update_node`, `remove_node`, `restore_node`, and the corresponding create/get/list/update/remove/restore connection operations. Every operation takes project and revision IDs. Lists default to ACTIVE; reads by ID include removed objects, and lists accept REMOVED or all statuses.

Manual creation/edits use MANUAL and ENGINEER_REVIEWED, with null connection confidence. Ordinary callers cannot set AI origin, verification, or confidence. Removed objects must be restored before editing. Connection creation, rewiring, and restoration require active endpoints; terminal creation/restoration requires active equipment.

Writes take the existing project FOR SHARE then revision FOR UPDATE guard, refresh state, and own commit/rollback. ACTIVE/PAUSED projects with DRAFT/ACTIVE revisions are writable. Archived/cancelled projects and superseded revisions reject writes; reads remain available. Known constraint failures map to clean service errors. Structural consistency is checked on reads, mutations, and cloning; no findings are persisted.

## Conservative lifecycle

| Action | Result in the same transaction |
| --- | --- |
| Remove equipment | Soft-remove its active terminals and their active incident connections; retain attributes and unrelated topology |
| Restore equipment | Restore current-profile and custom terminals; obsolete profile terminals and all connections stay removed |
| Remove node | Soft-remove its active incident connections; required profile terminals cannot be removed independently |
| Restore node | Restore only the node; terminal equipment must be active |
| Restore connection | Both endpoints must still be active, same-revision nodes; no endpoint lifecycle changes |

Lifecycle changes preserve origin, verification, and confidence. Helpers participating in equipment mutations never commit independently. No service hard-deletes topology.

## Revision inheritance

`carry_forward_model=true` clones equipment/attributes, then ACTIVE nodes, then ACTIVE connections. Explicit ID maps remap terminal equipment references and both connection endpoints into the destination revision. Each topology row receives a new ID and audit metadata, preserves its canonical fields, `managed_by_profile` distinction and provenance, and points `inherited_from_node_id` or `inherited_from_connection_id` to the corresponding row in the actual immediate base.

Removed objects are excluded. An active terminal whose equipment cannot be cloned, or an active connection whose endpoint cannot be cloned, causes atomic inheritance failure. No meaningful active edge is silently discarded or linked to source-revision endpoints. Document inheritance, model inheritance, metadata, and optional activation remain one transaction. The public inherited model count still counts equipment only.

The source and destination are independent snapshots. Revision frequency and common phase count are not copied into topology fields. Phase 5D does not reject a single-phase equipment override in a three-phase model or infer phase/voltage data.

## Public authoring APIs — Phase 5E

Under `/api/projects/{project_id}/revisions/{revision_id}`, `/nodes` and `/connections` support GET lists and POST creates. `/nodes/{node_id}` and `/connections/{connection_id}` support PATCH, with POST `/remove` and `/restore` actions. Creates return 201; the other actions return 200 with canonical state. There are no DELETE or single-object GET routes. See [PHASE5E_HANDOFF.md](PHASE5E_HANDOFF.md) for exact endpoints and request/response contracts.

Lists return `{"items": [...]}` in stable creation-time/ID order. `lifecycle_status` defaults to ACTIVE and also accepts REMOVED or ALL for restoration workflows. Responses include lifecycle, provenance, inheritance, audit metadata, and Decimal connection voltage/confidence as JSON strings. Lists are unpaginated and retain Phase 5D's bulk consistency validation; scalability remains a hardening concern.

Manual bodies reject extra fields and cannot set origin, verification, confidence, inheritance, audit actors, or lifecycle flags. Node creation validates terminal/electrical-node shape; PATCH cannot change kind or equipment ownership. Connection endpoints resolve only within the path project/revision. PATCH omission keeps values; null can clear label/phase text/voltage, and clearing voltage also clears its canonical unit. Supplied voltage units must accompany voltage. Voltage conversion remains in TopologyService. All existing removal/restoration cascades and mutability guards apply through HTTP.

## Manual workspace — Phase 5F

The revision Engineering Model workspace uses clickable Node and Connection tables. Node columns show Node, Type, Equipment / Owner, Terminal and Lifecycle. Connection columns show From, To, Type, Direction, Voltage, Phase and Lifecycle. Rows open detail/edit sheets by click or keyboard, including read-only/removed rows. Electrical-node and connection create actions remain available on writable revisions. Profile terminals show their owner and application-managed role, with no key editing or independent removal. Custom terminals remain editable. Equipment detail's Terminals tab participates in the unified equipment draft and Save. Nodes and connections support Active/Removed/All views; parallel connections remain separate rows.

Endpoint labels combine equipment tag/name/type with terminal key or electrical-node labels, using short IDs only to disambiguate duplicates or missing names. Connection forms select distinct active endpoints and expose kind, direction, phase configuration, and decimal-safe nominal voltage. Voltage input units derive from registry unit-family metadata; the server handles conversion. PATCHes include only changed fields, with explicit null clears and no empty updates.

Equipment/node removal confirmations describe incident-connection cascades and conservative restoration. Restoring a connection is unavailable until both endpoints are active. Phase 5G uses a set of active node IDs for these per-connection checks, avoiding repeated full node-list scans. Successful lifecycle changes refresh the relevant lists. Read-only revisions hide mutation actions while retaining list visibility. There is no graph canvas or topology algorithm UI. See [PHASE5F_HANDOFF.md](PHASE5F_HANDOFF.md).

## Later phases

Phase 5G verified lifecycle, ownership and remapping invariants through full live regression and isolated clean-stack validation; Phase 5 is re-frozen after the authoring refinement. See [PHASE5G_HANDOFF.md](PHASE5G_HANDOFF.md). Phase 8 proposes topology from SLD evidence through candidates/reconciliation; Phase 12 visualizes the canonical graph. These workflows, graph algorithms, protection relations, study scenarios, and persistent findings remain unimplemented. See [PHASE5E_HANDOFF.md](PHASE5E_HANDOFF.md).
