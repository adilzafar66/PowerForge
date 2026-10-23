# PowerForge — Roadmap Documentation Reconciliation Prompt (Updated After Phase 5B)

You are performing a **documentation-only roadmap reconciliation** for PowerForge.

Do **not** implement application code, migrations, schemas, APIs, workers, UI, tests, ADRs, or Phase 5C functionality in this task.

The purpose of this task is to update PowerForge's repository documentation so the long-term roadmap reflects:

1. the architecture and decisions that have emerged through the accepted Phase 5 design;
2. the fact that **Phase 5A and Phase 5B are now implemented**;
3. newly approved product requirements for **revision-wide/system-wide frequency and phase count**;
4. the refined scope of Phases 6, 9, 11, and 13.

The repository documentation must become the durable source of truth. Do not rely on chat history.

---

# 1. Baseline

Work from the latest branch/state containing the completed Phase 5B implementation.

At the time this prompt was prepared, Phase 5B exists on:

```text
codex/phase-5b-core-persistence
```

At the time of preparation, that branch pointed to commit beginning:

```text
bf9c7e0
```

If Phase 5B has since been merged into `main`, use the updated `main`.

Do not base this documentation update on an older branch that only contains Phase 5A.

Before editing documentation, confirm the baseline includes the Phase 5A registry plus the Phase 5B persistence implementation.

Expected Phase 5A foundation includes:

```text
VerificationState.UNVERIFIED
20 canonical equipment types
296 canonical attributes
44 requirement reference rows
GET /api/engineering-model/registry
```

Expected Phase 5B foundation includes the implemented core persistence for:

```text
EquipmentLineage
Equipment
EquipmentAttribute
```

along with the associated migration/service behavior documented by the Phase 5B branch.

Do not change Phase 5B production code in this documentation task.

---

# 2. First inspect the repository

Before editing, inspect the repository for all roadmap and future-phase references.

At minimum read:

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STATUS.md
docs/ENGINEERING_MODEL.md
docs/EXTRACTION.md
docs/PROVENANCE.md
docs/TOPOLOGY.md
docs/VALIDATION.md
docs/REVIEW_WORKFLOW.md
docs/DOCUMENT_PIPELINE.md
docs/specs/phase-5-engineering-model.md
decisions/ADR-007-canonical-engineering-model-persistence.md
```

Also inspect the completed Phase 5B implementation/handoff documents if present, including any files named similarly to:

```text
docs/PHASE5B_HANDOFF.md
docs/prompts/phase-5b_codex.md
```

Search the entire repository for references to:

```text
Phase 5
Phase 5A
Phase 5B
Phase 5C
Phase 6
Phase 7
Phase 8
Phase 9
Phase 10
Phase 11
Phase 12
Phase 13
Phase 14
structured extraction
entity resolution
SLD extraction
reconciliation
validation
engineer review
visualization
exports
ETAP
SKM
EasyPower
report generation
protection settings
operating configuration
study configuration
frequency
phase_count
phase count
system frequency
system phase
authentication
authorization
audit
Evidence
ExtractionCandidate
```

Use repository search/grep rather than assuming the list above is exhaustive.

---

# 3. Preserve the existing phase numbering

PowerForge's repository uses:

```text
Phase 0 through Phase 13
```

These are **14 primary numbered phases**.

Do not renumber completed phases.

Do not change them to Phase 1–14 merely to change the counting convention.

Do not add a Phase 14 just because the roadmap contains 14 primary phases.

Preserve:

```text
0   Architecture / repository
1   Projects & revisions
2   Documents & revision inheritance
3   Document processing
4   AI document classification
4.5 Document workspace UX
5   Canonical engineering model
6   Structured extraction / evidence / candidates
7   Entity resolution
8   SLD extraction
9   Reconciliation
10  Validation
11  Engineer review
12  Visualization
13  Study-tool integration / automation / reporting
```

The changes in this task refine the definitions of later phases; they do not discard the roadmap.

---

# 4. Do not rewrite history

Completed phase documents are historical records.

Do not retroactively rewrite:

```text
Phase 0 handoffs
Phase 2 PR plans
Phase 3 plans / PR plans
Phase 4 handoffs / PR plans
Phase 4.5 PR plans
Phase 5A handoff
Phase 5B handoff
accepted ADRs
completed implementation specifications
```

unless a file contains a clearly active/global pointer such as:

```text
Current phase
Next phase
Long-term roadmap
Future phases
```

that is now misleading.

Historical statements that were correct for their phase should remain intact.

Do not modify ADR-007's accepted architectural decisions merely to describe future phases.

---

# 5. Create one canonical roadmap document

Create:

```text
docs/ROADMAP.md
```

This should become the authoritative high-level roadmap for future phases.

It must clearly state:

- the roadmap uses Phase 0–13;
- Phase 4.5 is an intentional intermediate UX phase;
- Phase 5 is subdivided into 5A–5G;
- Phase 5A and Phase 5B are implemented;
- Phase 5C is the next Phase 5 slice unless repository state has advanced further;
- completed phases keep their historical numbering;
- later phases may have internal subphases without creating additional top-level phase numbers;
- implementation specs/ADRs override the roadmap when a phase is formally specified;
- `docs/PROJECT_STATUS.md` remains authoritative for current implementation status;
- ROADMAP describes intended future scope, not implementation completion.

Cross-link ROADMAP from appropriate entry-point documentation.

---

# 6. Canonical revised roadmap

Document the roadmap substantially as follows.

## Phase 0 — Architecture and repository setup

Status: completed.

No scope change.

---

## Phase 1 — Project and revision management

Status: completed.

No scope change.

---

## Phase 2 — Document management and revision inheritance

Status: completed.

No scope change.

---

## Phase 3 — Document processing

Status: completed.

No scope change.

---

## Phase 4 — AI document classification

Status: completed.

No scope change.

---

## Phase 4.5 — Document workspace UX

Status: completed.

No scope change.

---

## Phase 5 — Canonical engineering model

Keep the approved Phase 5 architecture and subdivision, but update implementation status.

Document Phase 5 at a high level as:

```text
5A  Registry, canonical units, requirement engine — IMPLEMENTED
5B  Core persistence: EquipmentLineage, Equipment, EquipmentAttribute — IMPLEMENTED
5C  Revision model inheritance / carry_forward_model + revision-level model metadata
5D  Topology persistence: ModelNode / ModelConnection
5E  Revision-scoped engineering-model APIs
5F  Basic Engineering Model workspace UI
5G  Hardening, regression, documentation
```

Do not redesign or reimplement 5A/5B.

Important Phase 5 boundary:

- Phase 5 models the canonical **physical electrical system**.
- It deliberately does not implement the complete protection-function/settings subsystem.
- It deliberately does not implement complete operating/study configuration modeling.
- It is evidence-ready, but full Evidence/Candidate persistence starts in Phase 6.
- It does not implement AI extraction.

---

# 7. Add system-wide engineering-model attributes

A new approved PowerForge requirement is to support model-wide/system-wide attributes that apply uniformly across equipment within a revision.

These are **revision-scoped engineering-model metadata**, not duplicated per-equipment values.

They belong conceptually to the engineering-model snapshot rooted at `ProjectRevision`.

Do not create a separate `EngineeringModel` entity merely for these fields.

The two initial system-wide attributes are:

```text
system_frequency
system_phase_count
```

Naming may follow repository conventions, but the documentation must preserve the semantics below.

---

## 7.1 Unified system frequency

PowerForge should support a revision-wide electrical system frequency, for example:

```text
50 Hz
60 Hz
```

When present, this value represents the common frequency for the electrical model/revision and applies to all equipment for which frequency is relevant.

Recommended conceptual semantics:

```text
system_frequency
canonical unit: Hz
revision scoped
optional until known/configured
```

Do not duplicate the global frequency value into every EquipmentAttribute row merely to materialize the default.

Do not remove type-specific equipment frequency attributes from registry-v1 in this documentation task.

Instead, document an **effective-value model**:

1. if an equipment-specific frequency value is explicitly present, it is the equipment-specific value;
2. otherwise, if the revision-wide `system_frequency` is present, that value is the effective frequency for applicable equipment;
3. otherwise frequency remains unspecified/not available for that equipment.

A future Phase 5C design/implementation specification must decide whether equipment-specific frequency is permitted to override the revision-wide value or whether disagreement is treated as a validation conflict.

Do not silently invent that policy in this documentation task.

At minimum document that a mismatch between a configured model-wide frequency and an explicit equipment frequency must never be ignored.

It must eventually be:

```text
rejected
or
flagged deterministically
```

according to the later approved design.

---

## 7.2 Unified system phase count

PowerForge should support an optional revision-wide phase count when the model is uniformly one phase system.

Examples:

```text
1
3
```

Recommended conceptual semantics:

```text
system_phase_count
allowed common values: 1 or 3
revision scoped
optional
```

The field should be set only when one common phase count can legitimately apply across the relevant electrical system/equipment.

If the project/revision contains a meaningful mixture of single-phase and three-phase equipment, the unified `system_phase_count` should remain unset/null rather than forcing one value.

Do not use a magic value such as:

```text
0
MIXED
UNKNOWN
```

unless a later formal design explicitly approves one.

For now:

```text
NULL / absent
```

means no single system-wide phase-count assumption is being asserted.

As with frequency:

- do not duplicate the model-wide phase count into every EquipmentAttribute row merely to persist a default;
- do not remove equipment-specific `phase_count` registry fields;
- future effective-value logic may use the system-wide value when equipment-specific phase count is absent;
- explicit mismatches must eventually be validated rather than silently ignored.

---

## 7.3 Why these are model-level metadata

Document the architectural rationale:

System-wide frequency and uniform phase count are properties/assumptions of the revision's engineering-model snapshot.

They should not be repeated hundreds of times solely because many equipment definitions contain compatible attributes.

This avoids:

```text
duplicated values
mass updates when the system assumption changes
false provenance on copied values
unnecessary persistence noise
```

Equipment-specific values still remain useful when:

```text
the equipment differs from the model-wide assumption
the source document explicitly provides the value
the system contains mixed phase configurations
future validation needs to compare explicit vs model-level values
```

Do not interpret a model-level default as fabricated document evidence.

---

## 7.4 Phase placement

Document these attributes as a **Phase 5 extension** to be designed/implemented in Phase 5C, not as a new top-level phase.

Phase 5C should therefore be described as conceptually including:

```text
revision model inheritance
carry_forward_model
revision-level engineering-model metadata
system_frequency
system_phase_count
inheritance semantics for those metadata fields
```

Do not implement them in this documentation task.

Do not modify the completed Phase 5B migration/code to retrofit them here.

The future Phase 5C specification must explicitly decide:

- exact persisted field names;
- exact numeric type for frequency;
- validation constraints;
- inheritance/carry-forward behavior;
- API representation;
- effective equipment-value resolution;
- mismatch validation behavior;
- whether changing model-wide metadata on a writable revision affects already explicit equipment values (it should not silently overwrite them).

---

# 8. Expand Phase 6 materially

Rename/descriptively broaden Phase 6 to something equivalent to:

```text
Phase 6 — Evidence, Candidates & Structured Extraction
```

The exact wording may be adjusted for repository style, but it must clearly include both persistence and extraction.

Phase 6 should explicitly establish:

```text
Document / DocumentPage
        ↓
native text / OCR / visual / table inputs
        ↓
Evidence
        ↓
ExtractionRun
        ↓
ExtractionCandidate
        ↓
schema + canonical-registry validation
        ↓
candidate records for later entity resolution/reconciliation
```

## 8.1 Phase 6 ownership

Phase 6 should include:

- Evidence persistence.
- Attribute-level/document-page provenance.
- Extraction run metadata.
- Extraction candidate persistence.
- provider/model/prompt/version provenance.
- structured equipment extraction.
- structured attribute extraction.
- schedule/table extraction.
- OCR/layout support where native text or vision alone is insufficient.
- bounding-box/region linkage on upright `DocumentPage` coordinates.
- canonical registry mapping of candidate keys/types/units.
- confidence at candidate/evidence level.
- retry/versioning semantics for extraction runs.
- extraction evaluation/hardening.

AI output remains a **candidate**, never canonical truth.

Phase 6 must not silently write AI output directly into engineer-verified canonical values.

## 8.2 System-level metadata extraction

The roadmap should note that extraction may eventually produce candidates not only for equipment attributes but also for approved model-level metadata such as:

```text
system_frequency
system_phase_count
```

For example, a drawing title block or project specification may state:

```text
600 V, 3Ø, 60 Hz
```

Such extracted values must still be candidates with evidence.

They must not automatically change the canonical revision-wide settings.

## 8.3 Suggested internal Phase 6 subdivision

Document a proposed, non-binding subdivision similar to:

```text
6A  Evidence + ExtractionCandidate persistence
6B  extraction runs/provider/prompt infrastructure
6C  equipment + attribute extraction
6D  schedule/table extraction
6E  OCR/layout support where required
6F  study-domain/protection extraction support
6G  evaluation + hardening
```

Make clear these are implementation slices, not new top-level phases.

---

# 9. Explicitly capture the study-domain extension discovered during Phase 5 design

PowerForge's current Phase 5 registry is intentionally a canonical physical-equipment registry.

It is **not yet a complete coordination/arc-flash study-settings model**.

The future roadmap must explicitly acknowledge two additional canonical domains that will be required before high-fidelity study-tool automation.

## 9.1 Protection functions and study settings

Future structured modeling must support concepts such as:

```text
50
51
50N
51N
67
pickup settings
time dial / time multiplier
curve family
instantaneous pickup
short-time settings
ground-fault settings
trip-unit stages
relay setting groups
relay → breaker relationship
CT → relay relationship
```

Do not design the final database schema in this documentation task.

Do not add these as arbitrary flat Phase 5 equipment attributes.

State that a future dedicated architectural decision/ADR should define the protection/settings model before implementation.

Preserve the ADR-007 decision:

> Phase 5 does not introduce a general ProtectionFunction persistence model.

Also preserve the Phase 5 distinction that design/nameplate attributes such as:

```text
LV_BREAKER.trip_rating
LV_BREAKER.long_time_pickup
```

remain canonical equipment/design attributes and may coexist later with separate study-adjusted settings.

## 9.2 Operating / study configurations

The roadmap must explicitly recognize operating scenarios such as:

```text
NORMAL
STANDBY
ULTIMATE
EMERGENCY
MAINTENANCE
```

or project-specific equivalents.

Future modeling needs to represent scenario-dependent states such as:

- source in/out of service;
- switch/tie state;
- generator availability;
- bus configuration;
- other operating-condition overrides.

Again, do not invent the final persistence schema in this documentation task.

State that operating/study configuration modeling needs a dedicated design decision before study-tool execution/export is considered complete.

## 9.3 Placement in roadmap

Do not reopen completed Phase 5A/5B to implement these subsystems.

Document them as **post-core-Phase-5 canonical-domain extensions**, planned early enough that Phase 6 extraction and Phase 13 study integration have explicit target schemas.

If a later design review determines they deserve a dedicated top-level phase, that can be decided then.

Do not renumber the roadmap now.

---

# 10. Phase 7 — Entity Resolution

Keep Phase 7 as a first-class phase.

Clarify that its responsibility is determining whether extracted mentions/candidates refer to the same physical equipment lineage.

Signals may include:

```text
tag
equipment type
manufacturer/model
ratings
voltage
document context
location
connected equipment
spatial context
topology context
```

Outputs should remain candidates/decisions with evidence and confidence.

Do not silently merge low-confidence matches.

Entity resolution should bridge:

```text
ExtractionCandidate
        ↓
candidate physical identity
        ↓
EquipmentLineage / revision-scoped Equipment
```

without making AI the source of truth.

---

# 11. Phase 8 — SLD & Topology Extraction

Keep Phase 8.

Clarify that it produces:

- equipment/component candidates from single-line drawings;
- text/component associations;
- terminal/connectivity candidates;
- topology candidates;
- source page/bounding-box evidence.

It must target the canonical topology established in Phase 5D.

An SLD remains evidence, not the database.

Do not merge Phase 8 into generic OCR.

---

# 12. Expand Phase 9

Rename/descriptively broaden Phase 9 to something equivalent to:

```text
Phase 9 — Reconciliation & Conflict Management
```

Its contract should explicitly include persistent cross-source conflicts.

For example:

```text
SLD            CB-101 = 400 A
Shop drawing   CB-101 = 600 A
Nameplate      CB-101 = 600 A
```

The future reconciliation domain should be able to retain:

```text
candidate values
supporting evidence
conflicting evidence
source-priority information
agreement/disagreement
suggested resolution
confidence/explanation
review status
```

A suggested canonical value must **not** automatically become `ENGINEER_VERIFIED`.

Source priority remains configurable, not universally hard-coded.

Phase 9 should reconcile candidates/evidence; Phase 11 remains the human authority.

Do not design a final conflict schema in this documentation-only task unless an existing document already defines one.

---

# 13. Phase 10 — Deterministic Engineering Validation

Keep Phase 10.

Clarify that it includes:

- required/critical completeness;
- structured requirement-rule evaluation;
- engineering sanity checks;
- voltage consistency;
- topology consistency;
- duplicate tag detection;
- study-readiness checks;
- deterministic cross-model rules;
- consistency checks between revision-wide engineering-model metadata and explicit equipment values.

Examples of the latter include future checks for:

```text
system_frequency vs explicit equipment frequency
system_phase_count vs explicit equipment phase_count
```

Validation must not be an LLM treated as truth.

Validation findings should be persistent in this phase if that remains consistent with the architecture.

Validation flags problems; it does not silently resolve reconciliation conflicts.

Clarify:

```text
Phase 9  = cross-source reconciliation/conflict reasoning
Phase 10 = deterministic rule validation
Phase 11 = engineer decision/review
```

These may run iteratively in the eventual product even though they are implemented sequentially.

---

# 14. Expand Phase 11

Describe Phase 11 as something equivalent to:

```text
Phase 11 — Engineer Review, Verification & Audit
```

It should include:

```text
accept
reject
edit
merge
split
resolve conflict
mark unresolved
engineer review
engineer verification
review queues
full audit/history
```

## 14.1 Identity prerequisite

Explicitly document:

Before Phase 11 can be considered complete, PowerForge needs real actor identity sufficient to support trustworthy verification/audit:

```text
authentication
user identity
project authorization
actor-backed audit records
```

Do not create a fake users table merely for roadmap documentation.

Do not necessarily create a new top-level authentication phase.

State:

- if PowerForge requires shared/multi-user deployment earlier, auth/authorization must be pulled forward;
- otherwise it is a hard prerequisite/subphase for Phase 11 completion.

Update stale docs that currently imply authentication belongs to no future named scope.

---

# 15. Phase 12 — Model Visualization

Keep Phase 12.

Clarify that visualization is generated **from the canonical engineering model**.

Likely scope includes:

- interactive topology;
- generated one-line representation;
- equipment detail/evidence navigation;
- completeness/status overlays;
- upstream/downstream exploration;
- display of revision-wide engineering-model assumptions such as system frequency and common phase count where applicable.

React Flow or equivalent may be used here.

Visualization must not create a separate source-of-truth database.

---

# 16. Expand and rename Phase 13

Do not leave Phase 13 described merely as “Exports.”

Rename/descriptively expand it to something equivalent to:

```text
Phase 13 — Study Tool Integration, Automation & Reporting
```

This phase is the downstream consumer of the verified canonical model.

Document the long-term pipeline:

```text
Verified Canonical Model
        ↓
revision-wide model assumptions
        ↓
study configuration
        ↓
tool-neutral translation/adapters
        ↓
ETAP / SKM / EasyPower
        ↓
study execution / automation
        ↓
results ingestion
        ↓
PowerForge result representation
        ↓
engineering report generation
```

Revision-wide settings such as:

```text
system_frequency
system_phase_count
```

must be available to exporters/tool adapters where applicable without requiring duplicated per-equipment values.

## 16.1 Proposed Phase 13 slices

Document a proposed subdivision similar to:

```text
13A  tool-neutral study/export adapter contracts
13B  ETAP export/integration
13C  SKM export/integration
13D  EasyPower export/integration
13E  Windows study-tool agent / desktop automation
13F  study-results ingestion
13G  engineering report generation
13H  end-to-end validation and hardening
```

These are planning slices, not commitments that every tool must launch simultaneously.

## 16.2 Important boundary

The canonical PowerForge model must remain independent of:

```text
ETAP
SKM
EasyPower
```

Tool-specific schemas/adapters belong downstream.

Do not redesign the canonical model to mirror one vendor's internal object model.

Report generation belongs here unless later requirements justify extracting it into another top-level phase.

---

# 17. No new top-level phases now

The documentation should explicitly state that the current recommendation is:

> Keep the existing Phase 0–13 numbering and use subphases/gates for newly understood work rather than adding or renumbering top-level phases.

Do not introduce separate primary phases solely for:

```text
Provenance
OCR
Protection
Operating scenarios
Authentication
Observability
Reporting
System-level electrical metadata
```

at this time.

Instead document their current placement:

```text
System frequency / system phase count → Phase 5C model-level metadata
Evidence / provenance                 → Phase 6
OCR / table / layout extraction      → Phase 6
Protection/settings model            → post-core-5 design gate before extraction/integration needs it
Operating/study configurations       → same domain-extension window
Auth / authorization                 → Phase 11 prerequisite, or earlier if deployment requires
Full audit history                   → Phase 11
Study automation / reporting         → Phase 13
Testing/evaluation/observability     → continuous across relevant phases
```

Make clear that future ADRs/specifications can change this placement if implementation evidence requires it.

---

# 18. Documentation files to update

At minimum evaluate and update, where relevant:

```text
README.md
docs/ARCHITECTURE.md
docs/PROJECT_STATUS.md
docs/ENGINEERING_MODEL.md
docs/EXTRACTION.md
docs/PROVENANCE.md
docs/TOPOLOGY.md
docs/VALIDATION.md
docs/REVIEW_WORKFLOW.md
docs/DOCUMENT_PIPELINE.md
```

Create:

```text
docs/ROADMAP.md
```

Also update any other **current/future-facing** documentation found by repository search.

Do not mechanically edit files merely because they contain the words “Phase 6” or “Phase 13.”

Only update a historical document if its present wording incorrectly claims to be the current roadmap/source of truth.

---

# 19. README requirements

Update README to reflect actual repository state.

At minimum:

- current implemented phase must reflect Phase 5B if that branch is the baseline and Phase 5B has not yet been superseded;
- next phase should be Phase 5C;
- link to `docs/ROADMAP.md`;
- continue to say `docs/PROJECT_STATUS.md` is authoritative for implementation status;
- do not turn README into the complete roadmap.

If repository state has advanced beyond Phase 5B by execution time, use actual repository state.

---

# 20. PROJECT_STATUS requirements

`docs/PROJECT_STATUS.md` remains the implementation-status source of truth.

Keep completed phase history.

Add/update Phase 5B status based on repository reality.

If Phase 5B is complete:

```text
Current implemented phase: 5B — Core engineering-model persistence
Next: Phase 5C — Revision model inheritance and revision-level model metadata
```

or equivalent wording consistent with repository style.

The Phase 5 summary should distinguish:

```text
5A implemented
5B implemented
5C–5G not started
```

Replace vague later-phase wording such as:

```text
6–13 | Extraction through export
```

with a concise but meaningful roadmap summary aligned with `docs/ROADMAP.md`.

Do not claim future work is implemented.

---

# 21. ARCHITECTURE requirements

Update `docs/ARCHITECTURE.md` where needed so it is consistent with the revised roadmap.

In particular:

- preserve AI-not-source-of-truth philosophy;
- preserve engineering-model/tool independence;
- clarify Evidence/Candidate persistence begins with Phase 6;
- clarify system-wide frequency/common phase count are revision-level engineering-model metadata, not values that need to be duplicated on every equipment row;
- clarify protection settings and study configurations are separate future canonical domains rather than arbitrary equipment attributes;
- clarify final tool integration includes export, automation, results, and reporting;
- add ROADMAP to related documents.

Do not rewrite the entire architecture document.

---

# 22. ENGINEERING_MODEL requirements

Preserve the approved Phase 5 model and completed Phase 5B persistence.

Add documentation for revision-wide engineering-model metadata:

```text
system_frequency
system_phase_count
```

Document:

- they belong to the revision's engineering-model snapshot;
- no separate `EngineeringModel` table is implied;
- they are not duplicated into every EquipmentAttribute row merely to apply defaults;
- equipment-specific frequency/phase_count attributes remain valid canonical attributes;
- effective-value resolution must be explicitly designed in Phase 5C;
- mismatches must eventually be validated, not silently ignored;
- phase count is optional and should remain absent when no single common phase count applies.

Also retain future-boundary notes:

- Phase 5 canonical equipment/topology is not the entire future study model;
- protection-function/settings structures remain deferred;
- operating/study configurations remain deferred;
- these require explicit later design rather than arbitrary attribute growth;
- canonical equipment design values and future study settings are separate concepts.

Do not change registry-v1 in this documentation task.

Do not edit the Phase 5 JSON/XLSX.

Do not modify completed Phase 5B code.

Do not change ADR-007 unless the repository's ADR process explicitly requires a superseding ADR; this task should instead document the new Phase 5C requirement and flag whether a future ADR amendment/supplement is warranted.

---

# 23. EXTRACTION + PROVENANCE requirements

These documents should jointly make the Phase 6 boundary unambiguous.

Ensure documentation says:

```text
AI output -> candidate
candidate -> evidence/provenance linked
candidate -> later entity resolution/reconciliation/review
canonical model is not silently overwritten
```

Clarify that:

- Evidence cites stable `Document` / `DocumentPage`;
- source coordinates are normalized upright-page coordinates;
- extraction run/provider/model/prompt versions are traceable;
- table/OCR/vision/native-text inputs may all contribute;
- full Evidence persistence starts in Phase 6;
- system-wide metadata such as frequency/phase count may also be extraction candidate targets, but extracted candidates do not automatically modify canonical revision metadata.

Avoid duplicating the same large explanation verbatim across both files; cross-link instead.

---

# 24. VALIDATION + REVIEW requirements

Ensure the responsibility split is clear:

```text
Reconciliation:
    compare sources and preserve conflicts/suggestions

Validation:
    deterministic rules and study/model sanity

Review:
    engineer decision and verification
```

Validation documentation should recognize future model-wide consistency checks such as:

```text
system_frequency vs explicit equipment frequency
system_phase_count vs explicit equipment phase_count
```

Update review documentation to note the identity/auth prerequisite for meaningful audit.

Where the canonical verification vocabulary is enumerated, include:

```text
UNVERIFIED
AI_EXTRACTED
SYSTEM_VALIDATED
ENGINEER_REVIEWED
ENGINEER_VERIFIED
```

Preserve:

> AI_EXTRACTED must never silently become ENGINEER_VERIFIED.

---

# 25. TOPOLOGY requirements

Keep topology architecture intact.

Only update roadmap references where necessary:

```text
Phase 5D → manually authored canonical topology
Phase 8  → extracted topology candidates from SLD evidence
Phase 12 → visualization of canonical topology
```

Do not redesign topology.

---

# 26. Optional dedicated future-design section

In `docs/ROADMAP.md`, include a small section such as:

```text
Future ADR/design gates
```

List likely future architectural decisions without pretending they are already approved:

```text
Revision-level model metadata semantics / effective values
Protection functions / study settings
Operating / study configurations
Evidence + extraction candidate persistence
Conflict / reconciliation persistence
Authentication / authorization and audit identity
Study-tool adapter / agent boundary
Study-results representation
```

Do not assign ADR numbers.

Do not create those ADRs in this task.

For revision-level model metadata, note that the product requirement is approved but the exact Phase 5C persistence/API/effective-value design still requires formal specification.

---

# 27. Consistency checks

After editing, search the repository again for stale claims such as:

```text
Phase 5B not started
Phase 5A is the current phase
Phase 13 = exports only
Phase 6 = extraction only with no evidence/candidates
auth is not assigned to any future phase
full provenance begins in Phase 5
Phase 5 includes a general ProtectionFunction model
SLD extraction is generic OCR
AI writes directly to canonical values
frequency must be duplicated on every equipment item
phase count must be duplicated on every equipment item
```

Resolve contradictions in current/future-facing documentation.

Do not “fix” historical statements that are accurate in their historical context.

---

# 28. Documentation quality

Use concise engineering language.

Avoid speculative implementation detail where architecture has not been approved.

Use words such as:

```text
planned
proposed
future design gate
requires ADR
requires Phase 5C specification
```

for decisions that are not frozen.

Do not state the proposed Phase 6/13 subphase names as immutable contracts.

Do not invent database schemas for later phases.

Do not add product features unrelated to this prompt.

---

# 29. No code changes

This task is documentation-only.

Do not modify:

```text
*.py
*.ts
*.tsx
package manifests
database migrations
Dockerfiles
Compose
tests
registry-v1 JSON
registry-v1 XLSX
```

Do not alter completed Phase 5B persistence.

Do not implement system frequency or system phase count yet.

Do not begin Phase 5C/6 work.

Documentation checks such as Markdown/link checks, grep, formatting, or `git diff --check` are appropriate.

---

# 30. End-of-task report

At the end provide:

1. baseline branch/commit used;
2. complete list of documentation files changed;
3. whether `docs/ROADMAP.md` was created;
4. summary of roadmap changes;
5. explicit confirmation that Phase 0–13 numbering was preserved;
6. confirmation that Phase 5A and Phase 5B are documented as implemented;
7. confirmation that Phase 5C is documented as the next Phase 5 slice unless repository state has advanced;
8. description of how `system_frequency` is documented;
9. description of how optional `system_phase_count` is documented;
10. confirmation that these are revision-level model metadata rather than duplicated equipment persistence;
11. explicit summary of changes to Phases 6, 9, 11, and 13;
12. where protection/settings modeling is documented;
13. where operating/study configurations are documented;
14. where authentication/authorization is placed;
15. list of future ADR/design gates documented;
16. stale/contradictory references intentionally left untouched because they are historical;
17. documentation validation commands/results;
18. confirmation that no production code, migrations, registry files, or tests were changed.

If the documentation is reconciled successfully, finish with:

```text
PowerForge roadmap documentation is reconciled and ready for review.
```
