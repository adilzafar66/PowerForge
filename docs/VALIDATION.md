# Validation

Validation is deterministic. It is not an LLM “second opinion” treated as truth.

Reconciliation (cross-source agreement) and engineer review are separate modules. Validation answers: “Does this candidate or model state violate rules we can check without a model vendor?”

## Ownership

The validation module (`packages/validation`, `services/validation-worker`) owns:

- Required attributes
- Data type and unit checks
- Electrical sanity checks
- Topology consistency
- Voltage consistency
- Duplicate detection signals (deterministic)
- Impossible relationships

It does not silently write verified values into the engineering model.

## When it runs

Validation runs on candidate records after schema validation, and again on the engineering model as it is assembled. Failures are observable (structured logs, job errors, review queue items). They do not crash the pipeline without a recorded error.

## Examples (later phases)

- A breaker rating is not a number, or has an impossible unit.
- Primary and secondary voltages on a transformer are identical in a way that contradicts nameplate evidence (flag, do not auto-fix).
- A connection joins equipment in different, incompatible voltage classes without a transformer.
- Required critical attributes for a type are `MISSING` or `NOT_EXTRACTED`.
- Two equipment rows share an identical tag in the same revision.

## Relationship to other modules

| Module | Role |
| --- | --- |
| Extraction | Produces candidates; schema-validates AI output |
| Validation | Deterministic domain checks |
| Reconciliation | Resolves or records conflicts across sources |
| Review | Engineer is the authority |

Never silently resolve conflicting engineering information in validation. Conflicts become conflict records. See [REVIEW_WORKFLOW.md](REVIEW_WORKFLOW.md).

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

Phase 0 ships the package boundary and empty rule registry hook. Phase 10 implements rule execution, topology checks, and electrical consistency checks.
