# Phase 6R extraction quality correction

The attached correction specification is authoritative for this work. The saved
Siemens Stage 2 bundle for run `f50c1050` is the development baseline. Private
source files and provider payloads stay outside the repository.

## Implementation plan

1. **A — Diagnostic baseline.** Replay the pinned Siemens assertions through
   localization and publication. Record mapping, source support, duplication,
   tag omissions and UI behavior independently. Keep provider output immutable.
2. **B — Recognition and identity.** Version the recognition prompt and
   registry-owned assembly description. Request explicit assembly identifiers
   with source evidence. Derive concise display names from registry type and
   original page/observation order, independently of filters and pagination.
3. **C — Attribute semantics.** Add concise versioned guidance owned by the
   engineering registry. Version Stage 2 prompt/schema for raw presentation
   labels and original expressions behind inferred proposals. Clarify model/type,
   standards, current ratings, qualifiers and nonredundancy. Keep AI responsible
   for engineering interpretation.
4. **D — Validation and publication.** Version deterministic semantics. Admit
   only the documented KA notation for kA while preserving raw text and SI
   distinctions. Permit complete identifier citations to establish lexical value
   support. Record conservative same-occurrence redundancy diagnostics and keep
   every assertion. Store added optional detail in the immutable stage payload.
   Preserve the existing origin migration. Update its origin guard in a small
   forward migration to admit the new Stage 2 version without rewriting rows.
5. **E — Documents UI.** Present equipment identification separately. Use stable
   names and filter-aware attribute counts. Show redundant assertions as linked
   review details, retain direct candidate navigation, distinguish inferred
   proposals and raw source expressions, and identify unmapped presentation labels.
6. **F — Verification.** Exercise synthetic counterparts of all reported cases,
   wrong ownership, repeated facts, unit ambiguity, historical reads and profile
   fencing. Compare private offline replay with the baseline. Run backend,
   frontend and browser checks. Prepare source/model/call/budget requirements
   for a later separately authorized live comparison.

B and C depend on A. D depends on the clarified contracts in C. E uses the
publication diagnostics and API fields from B–D. F verifies the combined change.

## Confirmed baseline causes

- Recognition omitted the assembly tag from an available source reading.
  Recognition needs explicit assembly-versus-device ownership guidance.
- Stage 2 returned all 27 registry assertions as extracted. Technology and
  manufacturer classification require clearer evidence and inference guidance.
- ETU745 was returned twice with identical citations and different value-form
  annotations. Local IDs are distinct, so envelope validation correctly kept both.
- QUALIFIED/3PH and QUALIFIED/LSIG assertions remain unmapped under conservative
  scalar normalization. Source qualifiers must be chosen correctly by the AI.
- The source literal KA and proposed unit kA fail the case-sensitive unit check.
  This requires a bounded notation exception.
- Model identifiers cited with EQUIPMENT roles cannot currently establish
  lexical value support. This requires scoped identifier support.
- Registry definitions have limited semantic guidance for nearby rating fields.
  Bus bracing does not independently establish a timed withstand rating.
- The API uses source descriptions for group titles and counts identification
  rows alongside attributes. The viewer renders both as ordinary cards.
- The full page projection dominates input size. The request retains complete
  coverage. Payload reduction remains a separately measurable experiment.

Verification results and remaining model-quality uncertainty will be recorded
here after implementation.

## Implementation and version handoff

- Recognition uses `equipment_recognition_v3.txt`. Registry equipment guidance
  is `equipment-descriptions-v2`. Assembly-level identifiers belong to the BUS
  observation when their source association is supported. Each tag requires its
  actual citation. Tags and occurrence display names remain separate fields.
- Stage 2 uses `attribute_extraction_v7.txt` for the `compact-page-v1` input,
  schema `phase-6r-attributes-v5`, prompt bundle `phase-6r-stages-v8`, and aggregate
  wire identity `phase-6r-wire-v5`. The registry-owned
  `attribute-descriptions-v1` guidance explains commonly confused meanings.
  Canonical registry keys, allowed values, units and requirements are unchanged.
  The prompt explicitly limits each assertion to 12 citations and prioritizes
  evidence for the value, equipment association and interpretation. Run
  `f054d035` exceeded that local limit with the preceding prompt.
- Inference proposals add optional `source_expression`. Raw source assertions
  add optional `display_label`. These values remain in the immutable result
  payload and are exposed through the candidate API. A display label is
  explicitly identified as presentation metadata in the viewer.
- Publication uses `phase-6r-publication-v7` and the pinned
  `source-unit-interpretation-v2` policy. An extracted dimensional assertion
  carries the literal unit and a separate AI proposal from the registry.
  PowerForge verifies the notation against the proposal and its SI scale,
  requires resolved literal evidence, and uses the existing decimal converter.
  Unsupported spellings or contradictory evidence leave the assertion unmapped.
  The original value, literal unit, and proposal remain available for review. Scope unit
  evidence to the reported numeric literal and keep compound denominators
  intact. Require explicit context for bare inches and quotation marks.
- Complete resolved EQUIPMENT citations can establish literal support for
  model, catalog_number or trip_unit_model. Qualifiers, partial source tokens,
  ambiguous transcripts and inferred values retain their conservative support
  policies.
- `assertion-consistency-v1` diagnoses likely repeated representations using
  the same owner, registry key, literal value/unit and pinned reading references.
  It preserves distinct occurrences, different owners, conflicting values and
  independently qualified facts. Raw extensions are linked only when the
  literal label also agrees with an already represented fact. Every original
  result, candidate and citation is retained.
- The read API derives possible-repeat links and stable names for historical
  records. Numbering uses the original page and recognition ordinal, partitioned
  by equipment type over the whole run. Filtering and pagination never renumber
  observations. Unknown types use the same generic naming rule.
- Groups expose filter-aware attribute and identification counts independently.
  Member responses include the identification record even under attribute
  filters. The viewer gives identification, registry attributes, raw source
  facts and possible repeated representations distinct presentation areas.
  Repeated assertions remain included in counts and can be selected directly.
- `6r_0014c_quality` follows `6r_0014b_attribute_origin`. It replaces only
  the version-sensitive immutable origin guard to admit v3 assertions. It
  introduces no columns and rewrites no records. `6r_0014d_unit_proposals` admits
  v4 and extends the candidate shape to store extracted unit proposals in the
  existing column. Earlier results keep their stored values and remain readable.
  Old execution profiles fail resource/schema admission after upgrade.

Stage 2 v5 adds assertion-local schema quarantine. An invalid source value
or malformed local reference is tracked by its original array position. The
provider output is stored as exact bounded bytes. Its digest and sanitized
diagnostics survive body expiry. Candidate publication and audit linkage commit
together. See [audit storage and operator access](EXTRACTION.md#stage-2-response-audit).

Primary production changes are in `stage_contracts.py`, `stage_execution.py`,
`extraction_profile.py`, `publication.py`, `assertion_consistency.py`,
`publication_records.py`, registry `extraction_descriptions.py`, the API
`extraction_publication.py` schema/service, and the Documents
`extraction-evidence-panel.tsx` component and DTOs. The API specification and
contract handoff describe the same fields and versions.

## Offline Siemens comparison

The saved request and response hashes were checked against the exported metadata.
The source projection was independently loaded from the exact pinned preparation
and layout, with artifact checks. The original response has 27 extracted registry
assertions, zero inferred assertions, and four meaningful raw source assertions.

Before the correction, replay yielded 20 mapped and 11 unmapped candidates,
10 TEXT_MATCH and 21 UNVERIFIED states, and no duplicate diagnostics. The earlier
v4 publication replay of the same immutable assertions yielded 22 mapped
and 9 unmapped candidates, 14 TEXT_MATCH and 17 UNVERIFIED states, and one likely
redundant pair (a6 linked to a5). All 31 assertions remain present.

The four additional text matches are model identifiers already present in the
source and cited with EQUIPMENT roles. The two additional normalized quantities
are the SC and bus-bracing assertions with KA source notation. **The model's
bus-bracing-to-short-time-withstand interpretation remains an engineering error
in that saved response.** Its now-valid normalization does not improve that
interpretation. The prompt and registry guidance address the distinction; no
deterministic bracing interpretation was introduced.

The five expected equipment observations are present in the saved result. The
assembly tag is missed (zero of one expected assembly tag). The eleven-field
direct checklist of four model identifiers, four pole counts, rating plug,
catalog number and trip-unit model is present in this newer baseline, with
correct source-local model ownership. Additional broad field recall, inference
correctness and engineering mapping precision require a separately reviewed gold
set. The raw response still labels the technology proposal and all manufacturer
proposals EXTRACTED. Their origin classification is unchanged by offline replay.

The corrected synthetic response fixture explicitly covers one extracted
trip-unit model, inferred electronic technology, preserved protection functions,
SC/SCCR versus unmapped bracing, unqualified phase count, inferred line-line
voltage with its original combined expression, contextual manufacturer
inference, unsupported product standards, and ambiguous device current. Other
tests cover all three branch model identifiers, repeated devices, foreign owners,
unsupported enums, citation-free inference and missing source evidence. These
fixtures verify contracts/publication. They do not measure live AI generation.

The original request contains 252 readings and 84 applicable occurrence/attribute
combinations. Its 114,873-byte text input includes 103,528 bytes of page projection,
8,199 bytes of registry definitions, and 2,835 bytes of recognition data.
Most layout bytes describe reading geometry and ordering. An offline comparison
on the same pinned page and recognition result with the current catalog shrank
the JSON text input from 118,921 to 50,865 bytes (57.2%). The full request with
the same image and response schema shrank from 535,398 to 453,712 bytes (15.3%).
The compact input includes all 252 readings, exact coordinates and 182 order
relationships. The full pinned layout remains the basis for evidence resolution.
The calculation used a stubbed OpenAI client. Live token usage, extraction
quality and latency for the compact input remain unmeasured.

## Verification executed

- The isolated Linux harness applied the entire Alembic chain to empty
  PostgreSQL 16 and ran `pytest -q -rs` with Tesseract, Redis and MinIO.
  **1,408 passed, zero skipped.** The suite covers operation consent/admission,
  retries, cancellation, unknown outcomes, leases, source integrity and immutable
  atomic publication, alongside the quality regressions.
- The focused database run used
  `pytest -q -rs tests/test_extraction_operations.py tests/test_extraction_profile.py
  tests/test_extraction_schema.py tests/test_openai_extraction.py`.
  **73 passed, zero skipped** at that point. The later full run includes the
  final additional profile and unit ambiguity cases.
- The final host publication, consistency and profile run used
  `pytest -q tests/test_extraction_publication.py tests/test_assertion_consistency.py
  tests/test_extraction_profile.py`. **51 passed.**
- `npm test` passed **358 tests in 27 files**. TypeScript
  (`npm exec tsc -- --noEmit --incremental false`), `npm run lint` and
  `npm run build` passed.
- Synthetic Chrome evidence checks at 1440 and 390 pixels passed six captures,
  with exact/approximate evidence, deep-link reload and keyboard history
  navigation. The equipment/attribute separation and possible-repeat navigation
  also have component regression coverage. Screenshots were visually inspected.
- A disposable network-isolated copy of the populated local database upgraded
  from the origin revision to the quality revision. Candidate, fragment and
  stage-result counts/digests were unchanged, and the immutability guard rejected
  mutation. Historical completed-run browsing and execution fencing passed.
  The running application database was not upgraded by this verification.
- Ruff and `git diff --check` passed. Private source documents, request bodies,
  results and replay data remain outside the repository.

## Remaining verification and controlled live plan

No live calls were made for this correction. The prompt changes' effects on tag
recall, semantic field choice, inference classification, manufacturer ownership,
qualifier selection and duplicate generation require a new authorized response.
The fixed offline source support and normalization are measured separately above.

Before a live comparison, obtain explicit approval for the same pinned Siemens
page, the exact configured model, at most two new calls, and a token/spend ceiling.
Use one recognition and one attribute call through a new consent-bound operation,
with retries disabled for the checkpoint. Preserve current deployment limits and
deadlines. Review the BUS tag occurrence, branch ownership, ETU model/type origin,
bracing and SCCR meanings, standards, qualifiers, duplicate count and retained
unmapped facts against the source. Record finish status, usage (including
reasoning-token counts if available), latency and versioned cost or unavailable
pricing. Keep the held-out benchmark separate.

The implementation is ready for code/artifact review. The running app still uses
its installed build. No deployment or canonical engineering-model write occurred
during this correction.
