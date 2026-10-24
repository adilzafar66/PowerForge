# Topology

The canonical electrical topology belongs to a project revision and is stored as relational nodes and connections. An SLD is evidence for future proposals, or a visualization generated from this model; it is never the database. [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md) and the [Phase 5D prompt](prompts/phase-5d-codex.md) define the boundary.

## Domain and persistence

The infrastructure-neutral `packages/topology` exports exactly:

- `ModelNodeKind`: EQUIPMENT_TERMINAL, ELECTRICAL_NODE.
- `ConnectionKind`: ELECTRICAL, GROUNDING, OTHER.
- `ConnectionDirection`: UNDIRECTED, NOMINAL_FROM_TO.

The old `NodeKind.BUS` placeholder is removed. A physical bus, switchgear, panelboard, or MCC is BUS Equipment with terminal nodes. A pure connectivity junction is an ELECTRICAL_NODE. CABLE is Equipment with terminals, never a connection kind. No default terminals or connections are generated.

Migration `0009_topology_persistence` adds `model_nodes` and `model_connections`. Their ORM mappings live in `powerforge_persistence.topology` on the existing shared Base.

An equipment terminal requires same-project, same-revision equipment and a nonblank terminal key. Keys are trimmed by the service and unique per equipment snapshot, including removed terminals. Electrical nodes have neither equipment nor terminal key. Node kind and equipment ownership are immutable after creation; label and terminal key may be edited.

Connections reference two distinct nodes in the same project and revision. Composite foreign keys enforce these ownership rules. Parallel edges are allowed. UNDIRECTED is the default; NOMINAL_FROM_TO gives the stored endpoint order descriptive significance without asserting power-flow direction.

Optional `phase_configuration` is trimmed text; blank becomes null. Optional nominal voltage uses Decimal/NUMERIC, is finite and positive, and is stored with unit `kV`. Value and unit must both be null or both present. Supported voltage inputs use the existing conversion utility, such as 600 V → 0.6 kV. Optional connection confidence is finite and bounded to [0, 1]. Nodes have no confidence column.

Both tables reuse model lifecycle, origin, and verification enums, have timestamps and nullable actor UUIDs, and carry same-project non-self inheritance references. There are no document/page/geometry fields or evidence shortcuts.

## Manual service

`TopologyService(session)` provides `create_terminal`, `create_electrical_node`, `get_node`, `list_nodes`, `update_node`, `remove_node`, `restore_node`, and the corresponding create/get/list/update/remove/restore connection operations. Every operation takes project and revision IDs. Lists default to ACTIVE; reads by ID include removed objects, and lists accept REMOVED or all statuses.

Manual creation/edits use MANUAL and ENGINEER_REVIEWED, with null connection confidence. Ordinary callers cannot set AI origin, verification, or confidence. Removed objects must be restored before editing. Connection creation, rewiring, and restoration require active endpoints; terminal creation/restoration requires active equipment.

Writes take the existing project FOR SHARE then revision FOR UPDATE guard, refresh state, and own commit/rollback. ACTIVE/PAUSED projects with DRAFT/ACTIVE revisions are writable. Archived/cancelled projects and superseded revisions reject writes; reads remain available. Known constraint failures map to clean service errors. Structural consistency is checked on reads, mutations, and cloning; no findings are persisted.

## Conservative lifecycle

| Action | Result in the same transaction |
| --- | --- |
| Remove equipment | Soft-remove its active terminals and their active incident connections; retain attributes and unrelated topology |
| Restore equipment | Restore its existing removed terminals; connections stay removed |
| Remove node | Soft-remove its active incident connections |
| Restore node | Restore only the node; terminal equipment must be active |
| Restore connection | Both endpoints must still be active, same-revision nodes; no endpoint lifecycle changes |

Lifecycle changes preserve origin, verification, and confidence. Helpers participating in equipment mutations never commit independently. No service hard-deletes topology.

## Revision inheritance

`carry_forward_model=true` clones equipment/attributes, then ACTIVE nodes, then ACTIVE connections. Explicit ID maps remap terminal equipment references and both connection endpoints into the destination revision. Each topology row receives a new ID and audit metadata, preserves its canonical fields and provenance, and points `inherited_from_node_id` or `inherited_from_connection_id` to the corresponding row in the actual immediate base.

Removed objects are excluded. An active terminal whose equipment cannot be cloned, or an active connection whose endpoint cannot be cloned, causes atomic inheritance failure. No meaningful active edge is silently discarded or linked to source-revision endpoints. Document inheritance, model inheritance, metadata, and optional activation remain one transaction. The public inherited model count still counts equipment only.

The source and destination are independent snapshots. Revision frequency and common phase count are not copied into topology fields. Phase 5D does not reject a single-phase equipment override in a three-phase model or infer phase/voltage data.

## Later phases

Phase 5E will expose revision-scoped authoring APIs. Phase 5F supplies the basic Engineering Model workspace. Phase 8 proposes topology from SLD evidence through candidates/reconciliation; Phase 12 visualizes the canonical graph. These workflows, graph algorithms, protection relations, study scenarios, and persistent findings are outside Phase 5D. See [PHASE5D_HANDOFF.md](PHASE5D_HANDOFF.md).
