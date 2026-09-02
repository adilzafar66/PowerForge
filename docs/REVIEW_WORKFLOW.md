# Review Workflow

The engineer review workflow is central. The AI proposes; the engineer decides. Every action is auditable.

## Review queue

The queue contains:

- Low-confidence values
- Conflicting values
- Potential duplicate entities
- Unknown equipment
- Unverified topology
- Missing critical attributes

Example project snapshot:

```
Equipment: 247
Verified: 198
Needs Review: 31
Conflicts: 11
Missing Critical Data: 7
```

## Engineer actions

The engineer must be able to:

- View evidence
- Accept
- Reject
- Edit
- Merge
- Split
- Mark verified
- Mark unresolved

Every action is recorded in an audit trail (who, when, previous value, new value, evidence considered).

## Conflicts

Never silently resolve conflicting engineering information.

Example:

| Source | CB-101 ampere rating |
| --- | --- |
| SLD | 400 A |
| Shop drawing | 600 A |
| Nameplate | 600 A |

The system represents a conflict on `ampere_rating` with both values, sources, a **suggested** value (e.g. 600 A from source priority + agreement), confidence of that suggestion, and `PENDING_ENGINEER_REVIEW`.

The engineer may:

- Accept the suggested value
- Select another extracted value
- Enter a custom value
- Reject the extraction
- Mark unresolved

## Safety states

Do not present AI output as verified engineering data.

```
AI_EXTRACTED → SYSTEM_VALIDATED → ENGINEER_REVIEWED → ENGINEER_VERIFIED
```

Never silently promote `AI_EXTRACTED` to `ENGINEER_VERIFIED`.

## UI surfaces (Phase 11, scaffolded in later UI phases)

- Review queue
- Conflicts
- Missing data
- Equipment detail with per-attribute status and evidence
- Model completeness

The engineer should always be able to see “What does the system think?” and “Why does it think that?”

## Phase 0 / Phase 11

Phase 0 documents this workflow and keeps review types in domain packages. Phase 11 implements the queue, evidence viewer, conflict resolution, verification workflow, and audit trail. Phase 1+ must not bypass this model by writing verified flags from extraction workers.
