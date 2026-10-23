# Validation

Validation is deterministic. It is not an LLM “second opinion” treated as truth.

Phase 10 is the planned deterministic validation/findings phase; Phase 5A already provides pure registry validation and requirement evaluation without persisted findings. See [ROADMAP.md](ROADMAP.md). Reconciliation (Phase 9 cross-source conflict reasoning) and engineer review (Phase 11 decisions/verification) are separate responsibilities. Validation answers: “Does this candidate or model state violate rules we can check without a model vendor?”

## Ownership

Planned Phase 10 responsibilities of `packages/validation` and `services/validation-worker` include:

- Required/Critical completeness and structured requirement-rule evaluation
- Data type and unit checks
- Electrical sanity checks
- Topology consistency
- Voltage consistency
- Duplicate detection signals (deterministic)
- Impossible relationships
- Study-readiness and deterministic cross-model checks
- Revision-level system_frequency/system_phase_count consistency with explicit equipment values

It does not silently write verified values into the engineering model.

## When it runs

In the planned workflow, validation runs on candidate records after schema validation, and again on the engineering model as it is assembled. Failures are observable (structured logs, job errors, review queue items). They do not crash the pipeline without a recorded error.

## Examples (later phases)

- A breaker rating is not a number, or has an impossible unit.
- Primary and secondary voltages on a transformer are identical in a way that contradicts nameplate evidence (flag, do not auto-fix).
- A connection joins equipment in different, incompatible voltage classes without a transformer.
- Required critical attributes for a type are `MISSING` or `NOT_EXTRACTED`.
- Two equipment rows share an identical tag in the same revision (a finding, not a uniqueness constraint).
- A configured `system_frequency` disagrees with explicit equipment frequency.
- A configured `system_phase_count` disagrees with explicit equipment `phase_count`; a meaningful mixed-phase system should not assert a common count. Phase 5C must define effective-value and mismatch policy; Phase 10 adds persistent findings and cross-model checks.

## Relationship to other modules

| Module | Role |
| --- | --- |
| Extraction | Produces candidates; schema-validates AI output |
| Validation | Deterministic domain checks |
| Reconciliation (9) | Compares sources; preserves candidate values, evidence, conflicts, and suggested resolutions |
| Review (11) | Engineer decides and verifies; records actor-backed history |

Never silently resolve conflicting engineering information in validation. Phase 9 owns persistent cross-source conflicts; Phase 10 owns deterministic findings. These stages and Phase 11 review may run iteratively. See [REVIEW_WORKFLOW.md](REVIEW_WORKFLOW.md).

## Source priority

Source priority is **configuration**, not a hard-coded universal ranking:

```
SourcePriorityRule:
    equipment_type
    attribute
    source_type
    priority
```

Example: a nameplate may outrank an SLD for ampere rating; a final schedule may outrank an older drawing. Organizations configure their evidence hierarchy. Reconciliation uses these rules to **suggest** values, not to auto-verify them.

## Phase 0 / Phase 10

Phase 0 established the package boundary. Phase 5A implements pure requirement evaluation. Phase 10 is planned to persist validation findings and rule-execution history alongside topology, electrical-consistency, and study-readiness checks, subject to its formal specification. It does not silently resolve reconciliation conflicts or verify values.
