# Topology

The electrical system is represented as a graph. Topology is independently queryable and belongs to the engineering model, not to a particular drawing.

## Concepts

**Node** may represent:

- A bus
- An equipment terminal
- An electrical node

**Connection** supports:

- Source
- Destination
- Connection type
- Phase information if available
- Voltage information if available
- Evidence
- Confidence
- Verification status

Example:

```
Transformer T1
    → Breaker CB-101
    → Bus SWGR-1
    → MCC-1
```

## Source of truth

The database model is the source of truth.

A single-line diagram is:

- Evidence used to propose topology candidates
- And/or a visualization generated **from** the engineering model

Do not treat the SLD as the database. Do not create an independent visualization database. The interactive view (React Flow or equivalent, Phase 12) is generated from model nodes and connections.

## Extraction vs model

SLD extraction (Phase 8) produces **topology candidates** with evidence coordinates on the original image. Those candidates enter validation and engineer review. Only verified (or explicitly accepted) connections become part of the engineering model.

Unverified topology is a first-class review queue item.

## Queryability

Connections are relational records, not only a property nested inside equipment JSON. The API exposes topology independently, for example:

```
GET /api/projects/{id}/connections
```

Equipment detail views derive upstream/downstream from these records.

## Package

`packages/topology` owns graph contracts (node and connection types, connection kinds). Persistence of connections lives with the engineering model schema. Visualization consumes the API; it does not own topology data.
