# PowerForge Phase 5G — Hardening, Regression, Documentation, and Final Phase 5 Freeze

You are implementing **Phase 5G only** of PowerForge.

Phases **5A–5F are complete and accepted**. Phase 5G is the final Phase 5 hardening and freeze phase.

Phase 5G is **not a feature-development phase**. Its purpose is to:

- resolve known Phase 5 technical debt that can compromise correctness;
- verify the completed Phase 5 implementation across layers;
- close meaningful regression/integration coverage gaps;
- review bounded performance concerns;
- reconcile current architecture/documentation with the implementation;
- remove obsolete Phase 5 placeholders or dead code where appropriate;
- verify that Phase 6+ concepts have not leaked into the canonical model;
- perform clean-stack/final validation;
- freeze Phase 5 so Phase 6 can safely build on it.

Do **not** begin Phase 6.

---

## 1. Authoritative inputs

Before editing, inspect the repository and read the following:

```text
docs/specs/phase-5-engineering-model.md
docs/specs/registry/PowerForge_registry-v1_reference.json
decisions/ADR-007-canonical-engineering-model-persistence.md

docs/PHASE5A_HANDOFF.md
docs/PHASE5B_HANDOFF.md
docs/PHASE5C_HANDOFF.md
docs/PHASE5D_HANDOFF.md
docs/PHASE5E_HANDOFF.md
docs/PHASE5F_HANDOFF.md

docs/ENGINEERING_MODEL.md
docs/TOPOLOGY.md
docs/ARCHITECTURE.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
docs/PROVENANCE.md
docs/EXTRACTION.md
docs/VALIDATION.md
```

Also inspect the Phase 5 implementation itself, including:

```text
packages/
services/api/
apps/web/
tests/
```

and the relevant migrations:

```text
0007_engineering_model_core
0008_revision_model_metadata
0009_topology_persistence
```

Inspect existing tests before writing new ones.

### Source-of-truth order

Use this order when interpreting Phase 5G:

1. this Phase 5G prompt for hardening/freeze scope;
2. `docs/specs/phase-5-engineering-model.md`;
3. `PowerForge_registry-v1_reference.json` for exact registry-v1 metadata;
4. ADR-007;
5. accepted Phase 5A–5F implementation and handoffs;
6. current-facing architecture documentation.

Do not silently weaken an accepted Phase 5 invariant to make a test pass.

If repository reality conflicts materially with the specification, report the conflict rather than redesigning the architecture.

---

## 2. Baseline

Start from the completed Phase 5F branch:

```text
branch:
codex/phase-5f-model-workspace

accepted/current Phase 5F head at prompt preparation:
33d9e9e040c8c8131020d48f8eb4f6f15b0eaab9
```

Create/work on:

```text
codex/phase-5g-hardening
```

If Phase 5F has received additional accepted commits since the SHA above, use the latest accepted Phase 5F head and report the actual base SHA.

Do **not** start from `main` if `main` still ends at Phase 5E.

---

# 3. Phase 5G scope

Phase 5G MUST address the following areas:

```text
1. Known correctness debt
   - canonical INTEGER response precision

2. Phase 5 requirements audit
   - registry
   - persistence
   - revision inheritance
   - topology
   - APIs
   - frontend
   - lifecycle/read-only behavior

3. Cross-layer regression/integration coverage

4. Registry-v1 freeze verification

5. Clean migration / clean-stack validation

6. Bounded performance review

7. Dead Phase 5 placeholder / stale-code cleanup

8. Architecture / ADR / documentation reconciliation

9. Phase 6+ leakage audit

10. Final Phase 5 completion and freeze report
```

Phase 5G should preferably make **small corrective changes**, not broad rewrites.

---

# 4. Explicit non-goals

Phase 5G MUST NOT implement:

```text
Evidence persistence
ExtractionCandidate persistence
ExtractionRun persistence
AI extraction
OCR expansion
LLM/provider infrastructure
entity resolution
automatic SLD interpretation
automatic topology inference
reconciliation/conflict workflows
persistent validation findings
study-readiness workflows
engineer verification/approval workflows
authentication/authorization redesign
graph visualization
React Flow
ProtectionFunction persistence
relay setting models
trip-unit setting models
operating/study configuration persistence
ETAP export
SKM export
EasyPower export
short-circuit execution
coordination execution
arc-flash execution
study result persistence
report generation
parent_equipment_id
a new EngineeringModel aggregate/table
```

Do not add convenience equipment types or arbitrary canonical attributes.

Do not alter `registry-v1` merely because a future feature would benefit from a different schema.

---

# 5. Preserve the accepted Phase 5 architecture

The following decisions remain fixed.

## Aggregate root

```text
ProjectRevision
```

is the engineering-model snapshot root.

There is no separate:

```text
EngineeringModel
```

table/entity.

## Canonical model

The canonical engineering model remains:

```text
EquipmentLineage
Equipment
EquipmentAttribute
ModelNode
ModelConnection
```

plus revision-level:

```text
system_frequency
system_phase_count
```

## Registry

The canonical registry remains:

```text
registry-v1
```

with its accepted equipment taxonomy, attribute keys, value types, units, enum choices, required/critical flags, display order, and requirement metadata.

## Typed values

The persistence mapping remains conceptually:

```text
NUMBER  -> numeric_value
INTEGER -> integer_value
TEXT    -> text_value
ENUM    -> text_value
BOOLEAN -> boolean_value
```

Do not convert typed persistence into arbitrary JSON.

## Lifecycle

Preserve:

```text
ACTIVE
REMOVED
```

soft lifecycle behavior.

## Model inheritance

Document carry-forward and engineering-model carry-forward remain independent.

## Topology

Connections continue to connect `ModelNode` objects rather than Equipment directly.

Do not create an automatic terminal registry.

---

# 6. Priority correctness fix — lossless canonical INTEGER API responses

This is the first technical item to investigate and resolve.

The accepted Phase 5F frontend submits INTEGER drafts as strings so input such as:

```text
9007199254740993
```

is not converted through JavaScript `Number(...)`.

However, the accepted Phase 5E response contract currently exposes:

```python
integer_value: int | None
```

and the frontend currently receives:

```ts
integer_value: number | null
```

This is unsafe for persisted integers outside JavaScript's exact integer range.

For example:

```text
9007199254740993
```

may become:

```text
9007199254740992
```

before the UI can display or resubmit it.

This is a real cross-layer correctness issue.

## Required resolution

Make canonical INTEGER values **lossless across the API/browser boundary**.

Use one consistent external representation.

The preferred Phase 5G contract is:

```text
INTEGER persistence/domain value:
Python integer / database integer

API JSON representation:
base-10 string

frontend representation:
string | null
```

Therefore an API response should conceptually contain:

```json
{
  "value_type": "INTEGER",
  "integer_value": "9007199254740993"
}
```

not:

```json
{
  "integer_value": 9007199254740993
}
```

Do not solve this by converting the value to a JavaScript number.

Do not create mixed semantics where small integers are JSON numbers and large integers are strings.

Use one deterministic representation.

NUMBER/Decimal lossless-string behavior must remain unchanged.

## Required regression

Add cross-layer regression coverage proving that:

```text
9007199254740993
```

can travel through:

```text
manual attribute write
    ↓
database persistence
    ↓
API serialization
    ↓
JSON representation
    ↓
frontend type/decoder
    ↓
editor display/draft
    ↓
resubmission
```

without changing a digit.

Submission-only frontend tests are insufficient.

Also test a normal small INTEGER so ordinary values remain correct.

If changing the response representation affects OpenAPI, update and test the contract intentionally.

Do not add arbitrary application-level INTEGER bounds merely to avoid fixing serialization unless a genuine registry/domain invariant already enforces those bounds everywhere, including existing persisted data. At present, do not assume that such bounds exist.

---

# 7. Phase 5 requirements audit

Before adding tests, perform a requirements-to-implementation audit.

Map the Phase 5 completion criteria to existing implementation/tests.

At minimum review:

```text
registry-v1 representation
unit normalization
requirement-rule engine
equipment lineage
equipment persistence
typed attribute invariants
attribute materialization
type changes
soft lifecycle
revision metadata
revision carry-forward
document/model carry-forward independence
topology persistence
topology lifecycle cascades
topology cloning/remapping
revision-scoped ownership
mutability/read-only enforcement
API provenance protection
API error translation
frontend registry-driven editing
frontend precision behavior
frontend topology editing
frontend read-only behavior
```

The objective is to identify **actual gaps**, not to produce another test for every already-tested behavior.

---

# 8. Test philosophy for Phase 5G

Do **not** create a huge new combinatorial test suite.

Phases 5A–5F already contain extensive focused tests.

The Phase 5G testing strategy is:

```text
existing focused tests
        +
small number of missing cross-layer regressions
        +
full-suite execution
        +
clean-stack validation
```

Before adding a test:

1. locate existing coverage;
2. determine whether the Phase 5 invariant is already adequately tested;
3. add a new test only when it closes a meaningful uncovered boundary, regression, or integration path.

Avoid duplicating:

```text
all 20 equipment types
every enum value
every lifecycle permutation
every API validation rule
every frontend input type
every topology permutation
```

unless the audit finds an actual gap.

Prefer a few high-value end-to-end scenarios over dozens of redundant unit cases.

---

# 9. Cross-layer integration review

Ensure the completed system is covered across service/API boundaries for representative workflows.

At minimum determine whether existing tests already prove these scenarios:

### Canonical equipment workflow

```text
create writable revision
create equipment
all registry attributes materialize
set representative typed attributes
read through API
update equipment
remove
restore
```

### Revision inheritance

```text
base revision
equipment + attributes
topology
revision metadata
create child with carry_forward_model=true
verify independent cloned snapshot
verify lineage preservation
verify topology remapping
verify source rows remain unchanged
```

### Carry-forward independence

Prove that:

```text
carry_forward_documents
```

and:

```text
carry_forward_model
```

remain independent.

### Topology lifecycle

Representative scenario:

```text
equipment
terminal
electrical node
connection

remove equipment/terminal/node
verify accepted conservative cascade
restore object
verify connections are not silently resurrected
```

### Read-only revision behavior

Representative write operations against a non-writable revision must still be rejected at the backend regardless of frontend controls.

### Precision

Cover both:

```text
NUMBER decimal precision
INTEGER > JavaScript safe integer precision
```

Reuse existing tests where they already prove these behaviors.

Add only the gaps.

---

# 10. Registry-v1 freeze verification

`registry-v1` is now intended to be frozen at the end of Phase 5.

Verify that the version-controlled implementation still exactly matches:

```text
docs/specs/registry/PowerForge_registry-v1_reference.json
```

The audit must cover the existing snapshot mechanism for:

```text
equipment types
attribute keys
display names
value types
canonical units
supported input units
enum choices
Required
Critical
display order
requirement groups/conditions
requirement rules
```

Do not create a second registry implementation.

Do not parse the XLSX at runtime.

If a registry snapshot test already proves this completely, retain it and verify it passes rather than duplicating it.

If the test is incomplete, strengthen the existing mechanism.

The human-reviewed XLSX remains a design/reference artifact, not a runtime dependency.

---

# 11. Persistence and database integrity review

Review the Phase 5 database model and migrations for unresolved correctness issues.

Confirm that the accepted invariants remain enforced, including where applicable:

```text
same-project ownership
same-revision ownership
unique revision/lineage snapshot
attribute uniqueness
typed value slot consistency
information-state/value consistency
topology ownership
terminal shape
connection endpoint ownership
self-loop prevention
lifecycle/removal timestamp consistency
inheritance pointer safety
```

Do not redesign existing constraints merely for style.

A new migration is **not expected** for Phase 5G.

Only add a migration if the audit identifies a genuine correctness defect that cannot safely be fixed otherwise.

If fixing it requires a material persistence redesign, stop and report the conflict instead of expanding Phase 5G.

---

# 12. Migration-chain validation

Validate the complete migration chain on a clean disposable database.

At minimum prove:

```text
empty database
    ↓
alembic upgrade head
    ↓
current schema usable
```

The expected current Alembic head before Phase 5G changes is:

```text
0009_topology_persistence
```

unless a justified Phase 5G corrective migration is required.

Do not run destructive integration tests against the developer's normal database.

Use the repository's established disposable/throwaway database procedure.

Where the existing test infrastructure supports it, also retain the previously established data-preserving migration checks.

---

# 13. API contract hardening audit

Review Phase 5 API contracts for accidental inconsistencies, especially:

```text
Decimal serialization
INTEGER serialization
omitted vs null PATCH semantics
empty PATCH rejection
registry response stability
lifecycle filters
ownership scoping
read-only errors
domain-validation errors
provenance/audit anti-forgery
```

Do not expand the API into Phase 6.

Do not expose mutations for:

```text
origin
verification_state
confidence
inheritance IDs
audit actors
```

unless already deliberately accepted.

Phase 5 manual actions must not fabricate later-phase provenance or verification authority.

---

# 14. Frontend hardening audit

Verify the Engineering Model workspace still respects the accepted Phase 5F behavior after any 5G contract change.

Pay particular attention to:

```text
Documents remains default
?workspace=model
deep-linked equipment
registry-driven type choices
generic attribute editor
NUMBER precision
INTEGER precision
BOOLEAN explicit selection
ENUM registry choices
state-only saves
unit handling
type-change conflicts
terminal management
topology forms
remove/restore warnings
read-only behavior
stale state refresh
```

Do not create equipment-specific forms.

Do not introduce client-side copies of registry-v1.

Do not introduce a client-side replacement for the Python requirement evaluator.

Do not add graph visualization.

---

# 15. BOOLEAN regression preservation

Phase 5F corrected the BOOLEAN editor so transitioning an attribute to `PRESENT` does not silently invent:

```text
false
```

when the engineer has not explicitly selected a value.

Preserve that behavior.

BOOLEAN `PRESENT` must require an explicit:

```text
true
```

or:

```text
false
```

selection.

Do not allow a UI transition to `PRESENT` to manufacture engineering data.

Retain the existing regression test unless the component structure genuinely requires adjustment.

---

# 16. Bounded performance review

Phase 5G owns a **performance review**, not a scalability redesign.

Known areas to inspect include:

```text
unpaginated equipment/node/connection lists
whole-revision topology loading
bulk topology consistency checks
frontend topology/equipment request patterns
potential N+1 queries
repeated registry loading
```

Review representative model behavior and query patterns.

Look specifically for obvious defects such as:

```text
N+1 database queries
per-row API calls where bulk data already exists
accidental quadratic loops
unbounded duplicate fetching
unnecessary repeated registry requests
```

Fix clear implementation pathologies if they can be corrected locally without changing the accepted architecture.

Do **not** automatically introduce pagination, virtualization, caching infrastructure, Redis caching, a global frontend store, or a new data-fetching framework simply because future models may become large.

If unpaginated APIs remain acceptable for the current Phase 5 scope but may become a future scalability concern, document that explicitly as technical debt.

Do not invent arbitrary performance pass/fail thresholds unless the repository already defines them.

---

# 17. Dead placeholder and stale-code cleanup

Search the Phase 5 implementation for obsolete placeholders, compatibility stubs, or dead code left behind by the transition from the pre-Phase-5 architecture.

Candidates may include stale references suggesting concepts such as:

```text
a separate EngineeringModel aggregate
old equipment taxonomy
old topology placeholders
obsolete BUS placeholders
temporary Phase 5 TODOs
unused compatibility exports
dead frontend model stubs
```

Only remove code that is demonstrably dead or contradictory.

Do not use Phase 5G as an excuse for broad refactoring.

Do not remove intentionally planned Phase 6+ documentation simply because those features are not implemented yet.

Historical handoff documents are historical records and should not be rewritten.

---

# 18. Phase 6+ leakage audit

Search persistence models, APIs, services, frontend, and migrations for accidental premature implementation of later-phase concepts.

Phase 5 should not contain canonical persistence/workflows for:

```text
Evidence
ExtractionCandidate
ExtractionRun
reconciliation findings
validation findings
engineer verification decisions
graph visualization state
study configurations
protection-function settings
ETAP/SKM/EasyPower model structures
```

Existing vocabulary fields intentionally established for future compatibility, such as:

```text
origin
verification_state
confidence
```

are not themselves leakage.

The distinction is:

```text
future-compatible metadata
```

is allowed;

```text
future workflow/domain implementation
```

is not.

Do not delete valid architectural planning documents.

---

# 19. Documentation reconciliation

Reconcile the current-facing documentation with the **actual final Phase 5 implementation**.

At minimum review/update as necessary:

```text
docs/ARCHITECTURE.md
docs/ENGINEERING_MODEL.md
docs/TOPOLOGY.md
docs/PROJECT_STATUS.md
docs/ROADMAP.md
docs/PROVENANCE.md
docs/EXTRACTION.md
docs/VALIDATION.md
decisions/ADR-007-canonical-engineering-model-persistence.md
```

The docs must agree that:

```text
ProjectRevision is the aggregate root
there is no EngineeringModel table
EquipmentLineage is stable physical identity
Equipment is revision-scoped
attributes are relational and typed
registry-v1 is code-owned and frozen
canonical units are deterministic
information/origin/verification are separate
equipment uses soft lifecycle
topology uses ModelNode/ModelConnection
model carry-forward is independent
manual authoring works without AI
provenance/evidence begins later
validation workflows begin later
verification authority begins later
visualization begins later
study integration begins later
```

Do not rewrite historical `PHASE5A_HANDOFF.md` through `PHASE5F_HANDOFF.md` to make them look as though later changes had already existed.

Current-facing docs should describe the current state; historical handoffs should remain historical.

---

# 20. ADR-007 review

ADR-007 should remain the architectural record for canonical engineering-model persistence.

Review it for contradictions introduced during 5A–5F implementation.

Only make clarifying corrections that reflect already-accepted Phase 5 architecture.

Do not use 5G to change fundamental ADR decisions.

At minimum ADR-007 must still capture:

```text
ProjectRevision aggregate root
no EngineeringModel table
EquipmentLineage
revision snapshots
typed relational attributes
code-owned registry
canonical units
separate state/origin/verification concepts
soft lifecycle
node/connection topology
independent model carry-forward
provenance deferred
validation/review/export deferred
containment deferred
general protection-function model deferred
```

---

# 21. No unnecessary dependencies

Prefer:

```text
zero new runtime dependencies
zero new frontend dependencies
zero new infrastructure dependencies
```

Do not add:

```text
React Flow
Redux/global state library
new data-fetching framework
benchmark framework
browser-testing framework
```

just for Phase 5G.

Use the repository's existing tools.

If a dependency is genuinely required for a correctness fix, justify it explicitly in the handoff.

---

# 22. Full backend regression

Run the established backend checks.

Use repository-native commands discovered from the project rather than guessing if they have changed.

The final validation should include the equivalent of:

```text
ruff / linting
format checks where established
pytest without live integrations
pytest with live integrations
```

Run live integrations against the established disposable PostgreSQL/MinIO environment, not the normal development database.

Record exact commands and exact results.

Do not report skipped live tests as though they were executed.

---

# 23. Full frontend regression

From `apps/web`, run the established equivalents of:

```text
npm run lint
npm test
npx tsc --noEmit
npm run build
```

All must pass before final Phase 5 freeze.

Also run:

```text
git diff --check
```

or the repository's equivalent whitespace check.

Record exact counts/results.

---

# 24. Clean-stack validation

Because 5G is the final Phase 5 freeze, perform a clean environment validation where the repository tooling permits it.

Prefer the existing Compose/development procedure.

The goal is to verify that a fresh environment can:

```text
start required services
migrate from an empty database to head
start API
start worker as applicable
start frontend
pass basic health/readiness checks
```

Use disposable data/volumes where needed.

Do not destroy the developer's normal environment or database.

If environment limitations prevent a clean-stack check, report exactly what was not run and why.

Do not claim validation that did not occur.

---

# 25. Browser/manual smoke check

If an actual browser/manual testing capability is available, smoke-test:

```text
project/revision navigation
Documents workspace
Engineering Model workspace
create equipment
edit representative NUMBER
edit representative INTEGER
edit BOOLEAN
add terminal
add electrical node
create connection
remove/restore representative objects
create child revision with model carry-forward
read-only revision behavior
```

Specifically verify that a large INTEGER remains exact in the displayed editor after being read back from the API.

If no browser capability is available:

```text
state that explicitly
```

Do not add Playwright/Cypress solely to satisfy this item.

---

# 26. Phase 5 completion audit

Before marking Phase 5 complete, explicitly verify every master completion criterion.

Phase 5 is complete only if:

```text
registry-v1 is version-controlled and matches the reference JSON

unit normalization is deterministic and tested

equipment and attributes are revision-scoped

manual engineering-model authoring works without AI

stable lineages survive revision carry-forward

document and model carry-forward remain independent

topology nodes/connections persist and clone correctly

ownership and mutability invariants are enforced

Engineering Model UI is usable

incomplete models remain representable

typed values remain lossless across supported interfaces

no Phase 6+ tables/workflows were introduced

Phase 0–4.5 behavior still passes regression

ADR/current docs agree with implementation

full test suite passes

clean migration/stack validation is satisfactory
```

Do not declare Phase 5 frozen if a correctness issue remains unresolved.

---

# 27. Documentation/status changes after successful completion

Create:

```text
docs/PHASE5G_HANDOFF.md
```

After every acceptance criterion genuinely passes, update current-facing status to reflect:

```text
5A implemented
5B implemented
5C implemented
5D implemented
5E implemented
5F implemented
5G implemented

Phase 5 complete / frozen
Phase 6 next
```

`PROJECT_STATUS.md` should no longer describe Phase 5G as pending.

`ROADMAP.md` should identify Phase 6 as the next major implementation phase.

Do not imply that Phase 6 has started.

---

# 28. PHASE5G_HANDOFF requirements

`docs/PHASE5G_HANDOFF.md` must record at minimum:

1. base branch and exact base commit;
2. final branch/head;
3. files changed;
4. requirements audit summary;
5. tests that already existed and were relied upon;
6. new tests added and why each was necessary;
7. canonical INTEGER precision resolution;
8. exact API contract change, if any;
9. frontend precision handling;
10. registry-v1 snapshot/freeze verification;
11. persistence/invariant audit result;
12. revision-inheritance audit result;
13. topology audit result;
14. API ownership/mutability audit result;
15. frontend hardening result;
16. performance review findings;
17. any optimizations made;
18. remaining performance technical debt;
19. dead-placeholder/stale-code cleanup;
20. Phase 6+ leakage audit result;
21. documentation/ADR reconciliation;
22. migration-chain validation;
23. full backend offline test result;
24. full live integration result;
25. frontend lint/test/typecheck/build results;
26. clean-stack result;
27. browser/manual smoke result or explicit lack thereof;
28. dependency changes, ideally none;
29. remaining technical debt;
30. confirmation that no Phase 6 functionality was implemented;
31. confirmation that Phase 5 completion criteria are satisfied.

Be precise.

Do not claim a test was performed when it was not.

---

# 29. Acceptance criteria

Phase 5G is complete only when all of the following are true:

- Phase 5F is the accepted baseline;
- no Phase 5 architecture has been unnecessarily redesigned;
- the known INTEGER browser/API precision gap is resolved;
- `9007199254740993` either round-trips exactly through the accepted API/frontend contract or is rejected by an explicit, proven domain invariant;
- INTEGER handling never relies on unsafe JavaScript numeric conversion;
- NUMBER/Decimal lossless behavior remains intact;
- BOOLEAN `PRESENT` still requires an explicit value;
- registry-v1 still matches its authoritative reference;
- no runtime XLSX dependency exists;
- registry implementation remains single-source rather than duplicated;
- database ownership/typed-value/lifecycle invariants remain intact;
- revision inheritance remains transactional and snapshot-independent;
- model/document carry-forward remain independent;
- topology lifecycle and remapping remain correct;
- provenance/audit fields cannot be forged through manual APIs;
- read-only revision enforcement remains backend-authoritative;
- frontend remains registry driven;
- no hardcoded equipment-specific editor has been introduced;
- existing Phase 0–4.5 regression behavior passes;
- meaningful cross-layer coverage gaps have been closed;
- redundant/combinatorial tests were not added without justification;
- migration from an empty database to head succeeds;
- full backend regression passes;
- live integrations pass on disposable infrastructure;
- frontend lint passes;
- frontend tests pass;
- frontend typecheck passes;
- frontend production build passes;
- whitespace/diff checks pass;
- bounded performance review is complete;
- obvious N+1/pathological behavior discovered during review is corrected or explicitly documented;
- obsolete Phase 5 placeholders are removed where safe;
- current-facing docs agree with actual implementation;
- ADR-007 remains consistent with the final Phase 5 architecture;
- no Phase 6+ persistence/workflows leaked into Phase 5;
- `PHASE5G_HANDOFF.md` exists and accurately records validation;
- `PROJECT_STATUS.md` marks Phase 5 complete;
- `ROADMAP.md` identifies Phase 6 as next;
- Phase 5 is ready to be frozen.

---

# 30. Implementation discipline

Before making changes:

```text
inspect
audit
identify concrete gaps
then edit
```

Do not treat 5G as an invitation to clean up everything in the repository.

Prefer:

```text
small correctness fix
small test gap closure
small targeted cleanup
accurate documentation
```

over:

```text
large refactor
new abstraction
new framework
new persistence model
speculative optimization
```

If an issue can safely remain documented technical debt without compromising Phase 5 correctness or Phase 6 foundations, document it rather than expanding scope.

If an issue compromises canonical-model correctness, persistence integrity, API losslessness, revision isolation, or ownership/mutability, fix it before freezing Phase 5.

---

# 31. End-of-task report

When implementation is complete, report:

1. branch and base SHA;
2. final commit SHA;
3. requirements-audit outcome;
4. correctness issues found;
5. INTEGER precision solution;
6. files changed;
7. tests added and why;
8. full backend results;
9. live integration results;
10. frontend lint/test/typecheck/build results;
11. clean migration/stack result;
12. browser/manual result;
13. performance findings;
14. cleanup performed;
15. documentation changes;
16. remaining technical debt;
17. dependencies added;
18. confirmation registry-v1 remains frozen;
19. confirmation no Phase 6+ scope was implemented;
20. final Phase 5 freeze verdict.

If every acceptance criterion passes, finish exactly with:

```text
Phase 5 implementation is complete, hardened, and frozen. PowerForge is ready to proceed to Phase 6.
```

Do not begin Phase 6 until instructed.