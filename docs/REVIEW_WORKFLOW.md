# Review Workflow

The engineer review workflow is planned for **Phase 11 — Engineer review, verification, and audit**. The AI proposes; the engineer decides. Full audit/history is a future requirement, not implemented by Phase 5B's nullable actor/timestamp fields. See [ROADMAP.md](ROADMAP.md).

## Review queue

The planned queue contains:

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
- Resolve conflict
- Mark engineer-reviewed
- Mark engineer-verified
- Mark unresolved

Phase 11 must record every action in an actor-backed audit trail (who, when, previous value, new value, evidence considered).

## Conflicts

Never silently resolve conflicting engineering information.

Example:

| Source | CB-101 ampere rating |
| --- | --- |
| SLD | 400 A |
| Shop drawing | 600 A |
| Nameplate | 600 A |

Phase 9 must persist both candidate values, supporting/conflicting evidence, configurable source-priority information, agreement/disagreement, suggested resolution, confidence/explanation, and review status. For this conceptual rating example, 600 A may be suggested from source priority and agreement; it is not automatically ENGINEER_VERIFIED. Exact canonical attribute mapping and conflict/review schema require a later specification.

Phase 9 compares sources and preserves conflicts/suggestions; Phase 10 applies deterministic rules and model/study sanity checks; Phase 11 records the engineer decision. These workflows may iterate. Validation does not silently resolve conflicts.

The engineer may:

- Accept the suggested value
- Select another extracted value
- Enter a custom value
- Reject the extraction
- Mark unresolved

## Safety states

Do not present AI output as verified engineering data.

```
UNVERIFIED
AI_EXTRACTED
SYSTEM_VALIDATED
ENGINEER_REVIEWED
ENGINEER_VERIFIED
```

These are separate verification states, not automatic promotions. AI_EXTRACTED must never silently become ENGINEER_VERIFIED. Manual Phase 5B values are ENGINEER_REVIEWED, not automatically ENGINEER_VERIFIED.

## Identity and authorization prerequisite

Before Phase 11 is complete, authentication, real user identity, project authorization, and actor-backed audit records must support trustworthy verification/history. This is a hard prerequisite/subphase for Phase 11. Pull auth/authorization forward if shared or multi-user deployment requires it earlier. Do not substitute a fake users table or nullable actor IDs for identity, and do not introduce a new top-level phase solely for auth.

## UI surfaces (Phase 11, scaffolded in later UI phases)

- Review queue
- Conflicts
- Missing data
- Equipment detail with per-attribute status and evidence
- Model completeness

The engineer should always be able to see “What does the system think?” and “Why does it think that?”

## Phase 0 / Phase 11

Phase 0 documents this workflow and keeps review types in domain packages. Phase 11 implements the queue, evidence viewer, conflict resolution, verification workflow, and audit trail. Phase 1+ must not bypass this model by writing verified flags from extraction workers.
