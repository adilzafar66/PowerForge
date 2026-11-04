# Phase 6C handoff — Engineering extraction and evaluation

Delivered 2026-11-04 on `codex/phase-6c-engineering-extraction`. Planning baseline: `main` at `3ffb43f8fc5082817c7be5ec3d67dc94f44319f6`, including accepted 6B `5042af8`; latest main was refreshed and is already an ancestor. M6 baseline: M5 `73240c6914f1833f036f918bbf96596f5f603559`. Scope follows the [prompt](prompts/phase-6c-prompt.md) and [milestone plan](PHASE6C_PLAN.md). M1–M6 implementation is delivered. **Actual production-model accuracy remains unverified: no live provider evaluation was authorized or performed.**

The approved specification/ADR, frozen registry-v1 and canonical engineering model remain unchanged. No Phase 6C migration, public route, frontend, OCR/table reconstruction, topology, cross-document identity, reconciliation or engineer acceptance workflow was added. Detailed historical delivery records remain in the [M1](PHASE6C_M1_HANDOFF.md), [M2](PHASE6C_M2_HANDOFF.md), [M3](PHASE6C_M3_HANDOFF.md), [M4](PHASE6C_M4_HANDOFF.md) and [M5](PHASE6C_M5_HANDOFF.md) handoffs.

## Implemented architecture

Each selected page has two required logical units: EQUIPMENT_RECOGNITION, then ATTRIBUTE_EXTRACTION. Each admitted attempt permits at most one model call. Attribute dispatch and claim require the unique committed same-run/page recognition success; successful recognition is reused across attribute retry. Empty recognition still permits standalone attributes. Recognition failure settles blocked dependents before terminal aggregation. Recovery prioritizes expired/unsatisfiable work rather than repeatedly scanning healthy oldest runs.

The existing coordinator owns planning, immutable snapshots, durable delivery, call/concurrency budgets, append-only retry, cancellation, leases/deadlines, recovery and stale-worker fences. Verified initial source loading and provider I/O occur outside metadata transactions. Phase 6A publication remains atomic, including empty success markers and bounded diagnostics. The publisher separately rechecks pinned native text before committing offsets. Successful outputs/history are immutable. COMPLETED means planned execution succeeded; it does not certify discovery completeness or engineering truth.

The provider-neutral M1 observation schemas carry raw expressions, labels, values/units, nullable proposed mappings, nullable tags/names/associations and source-role anchors. They accept neither trusted database IDs nor model offsets/geometry. M2 independently interprets admitted local source meanings and checks model assertions. M3 owns exact artifact admission, source associations, grounding and conversion into WorkUnitOutput. The production adapter revalidates the selected stage schema, and execution revalidates again before conversion/publication.

Source-only candidates remain document-scoped and reusable through approved revision-document membership. Source groups are local mention context, not physical equipment identity. Candidates never write canonical equipment/attributes, topology, verification state or revision-wide system frequency/phase count. Existing read APIs/signing, exact typed serialization, inherited document access and effective-unit filtering remain authoritative.

## Production configuration and provider boundary

Existing manual extraction endpoints advertise two opt-in profiles:

- `engineering-openai-v1`: native text plus analysis image when present, including image-only pages.
- `engineering-openai-text-v1`: requires native text and excludes image inputs.

Both report ENGINEERING_EXTRACTION and a production extractor marker, not measured accuracy. Enable `EXTRACTION_ENABLED` and `EXTRACTION_EXTERNAL_ENABLED` explicitly in API/worker; keep `OPENAI_API_KEY` worker-only. The default remains `infrastructure-fake-v1` and external processing remains off. Legacy infrastructure fake/source-probe profiles continue to work. Synthetic engineering profiles remain FAKE_TEST and do not establish provider quality.

The OpenAI adapter makes one Responses `parse()` call with the selected Pydantic schema, pinned model, effort/detail, timeout and output cap. SDK retries are disabled, `store=false`, and there are no tools, repair calls or conversation state. Named native text, image and upstream projection inputs are separate untrusted data; source strings are never appended to trusted instructions. The model receives response-local references, not artifact/group/database IDs or storage keys. Safe failure categories and known usage are retained; unavailable/interrupted usage stays unknown. SDK serialization/parsing is tested with actual SDK transport mocks, not a live endpoint/account.

Common profile limits retain configured page/artifact/pixel, call, attempt, concurrency, timeout/lease and backoff bounds. Production additionally defaults to 16,384 output tokens, 4 MiB combined page bytes, 100,000 native codepoints, 64 KiB upstream projection, `high` image detail and `none` reasoning effort; rendered instructions have a versioned 128 KiB cap. Oversized inputs/responses fail without clipping or changing modalities. Material settings change the profile identity. Model/effort availability and pricing require separate operator validation; no account access or price lookup was performed here.

## Versioned resources

Production profiles use `execution-profile-v3`, `engineering-page-runtime-v2` and `openai-engineering-responses-v1`. The production runtime rules hash remains `87ef969ca1f3194ee4568a56b2dd43f15701593a481e48e64b549fca04944775`. M6 adds evaluation modules without changing production runtime resources or profile identities. Legacy v1 infrastructure and v2 synthetic wire hashes remain byte-identical; packaged retained M4 identity resources support historical readers without dynamic code execution. Unknown/unavailable resources fail without a latest-version fallback.

The stage manifest is `engineering-stage-manifest-v1`, hash `35228fc26e37ceafa6ce8952062503c1fedbad935958f41dd9937dc1ad3d87e8`. Both stages use `engineering-prompts-v1`:

- Recognition template: `1d3daff000ec34db88873a35622de7a31c27cc72d3d111311e899b95fc784ad9`; `equipment-recognition-schema-v1`: `b75b3691abcef02c63c222ac38400c164cd3d768912d59d14c0e9860e574d789`.
- Attribute template: `680369eb4df684981ed8b12a7f14f51ca4211e0635c7114a6ab215d2492d9ad8`; `attribute-extraction-schema-v1`: `d74ec3efacee12d24d2b7217f0b1c20313160ccfdce935d6d7200d1221dce53b`.

The context renderer derives metadata from registry-v1: all 20 equipment types and 296 attribute definitions, canonical/supported units, enums and notes. It creates no alternate catalog, requirement inference or default values. `engineering-registry-context-v1` projection hash is `41ede97ee551463a293c7e56353ef7ce66db2963797d8b96fde3ba52bf36c7aa`; `engineering-terminology-v1` hash is `599ded5c5ecedb872a4a8478533bf621997550cec66af16bc9cc7b3b842a3829`.

Interpretation is `engineering-interpretation-v1`, rules hash `058e80e3c771510d83e6f59dace505420a5dcb0971444ebee0d2624330f8ef05`. Grounding is `engineering-grounding-v1`, rules hash `091706197d044d6ffc5f5212b6a459524f961d4b48dab4e8ac66c9dc13de8eee`. Full manifests, explicit fixture settings and profile wire hashes are recorded in `tests/fixtures/extraction/engineering_identities_v1.json`, `engineering_execution_v1_identity.json` and `engineering_production_v1_identity.json`. Actual call rows retain stage schema/rendered-instruction identity and upstream projection correlation rather than raw source dumps.

## Interpretation, evidence and uncertainty

Scoped terminology covers transformer capacity and qualified normal impedance, LV breaker naming/AF/AT, cable material and explicitly qualified utility fault data. Shared registry normalization preserves exact Decimal/integer/text/enum/boolean types; no float round trip or fabricated default is introduced. AF and AT stay separate, as do three-phase/SLG fault current and X/R. Percent/per-unit and unsupported conversions are not guessed. Raw values/units remain intact. Nonunit parenthetical qualifiers cannot disappear during label folding. Ambiguous meanings remain UNMAPPED; supported meanings with invalid values remain INVALID. Fabricated source-field assertions are rejected separately, with bounded diagnostic counts.

Artifacts come from the run's exact selected processing/page/artifact descriptors. Actual size/SHA-256, strict native UTF-8 and PNG dimensions/pixels are checked. There is no substitution from current page metadata or later processing. Native excerpts/context match literally, without Unicode normalization. Unique occurrences receive server-calculated Unicode codepoint offsets and full-line evidence. Repeated unresolved occurrences retain honest text/page precision and do not lend arbitrary equipment context. Tags/names must occur within the original observed equipment expression before full-line semantic qualification.

Native attribute associations require the grounded source block and same source occurrence; model references alone do not establish ownership. Recognized attribute-label continuations are admitted, while unknown colon labels and missed `TAG: Equipment Type` headers stop block association. Uncertain links detach instead of borrowing another equipment's values. Repeated tags and conflicting values are retained as separate mentions/claims, without cross-page/modality identity merging.

The explicitly approved image policy permits registry-valid visual MAPPED candidates with `VISUAL_PAGE` grounding and `VISUAL_REPORTED` interpretation limits. Image evidence has null native offsets/snippets/geometry and `text_verified=false`. Page/artifact ownership is verified; transcribed text/pixels and proposed association are not independently verified. A visual result is still an AI proposal. It does not inherit an arbitrary native quote or become engineer-verified. OCR/region support remains future work.

## M6 corpus, matching and actual findings

[`evals/extraction/README.md`](../evals/extraction/README.md) documents the commands, annotations, metrics and live setup. `v1/corpus.json` has 15 synthetic single-page cases, 50 independently authored gold claims (16 equipment, 34 attributes), 13 text artifacts and three drawn PNGs. Expected meanings/values/statuses/associations are authored constants, not generated interpreter answers. Literal source spans/hashes are checked. PNG labels were visually inspected; three processor round-trip tests verify approved image-byte compatibility.

Coverage includes transformer/breaker/cable/utility semantics, exact large integers/false, Unicode, unknown and isolated claims, no equipment, repeated tags, missed competing headers, a borrowed tag, parenthetical qualifiers, invalid units/overflow/mixed enums, tagless visual equipment, breaker visuals and conflicting native/image readings. The 49 scripted observations intentionally omit one competing mention and propose one invalid borrowed tag. Their gold mentions remain in the denominator.

The offline CLI runs M1 validation, M2 interpretation and M3 grounding/conversion without SDK/DB/broker access. Matching is one-to-one within a case/modality using literal source expressions and occurrence. Correct-location matches are protected before content fallback. A smaller native raw fragment can match when its primary evidence contains the complete gold field. Proposed keys/values/statuses/reference IDs do not influence pairing. Metrics then assess meanings, typed values/units, raw preservation, association, group separation and evidence against the independent annotation. Failed/missing stages keep expected denominators; zero denominators give null. Mutation tests detect wrong mappings/values/units, omissions/duplicates, foreign artifacts, bad offsets, incorrect links/merged groups and forged visual geometry. No arbitrary accuracy target or model grader was added.

Actual committed `SCRIPTED_MOCK` replay results:

- Published candidates: 48 (14 equipment, 34 attributes), against 50 gold claims.
- Equipment precision: **14/14**; recall: **14/16**. The two deliberate recognition challenges account for missed mentions.
- Attribute detection/mapping: **34/34** each; exact typed values and canonical units: **24/24** each; raw preservation: **34/34**.
- UNMAPPED retention: **8/8**; INVALID retention: **2/2**; association correctness: **34/34**; separate source-group pairs: **2/2**.
- False candidates: **0/48**; unmatched candidates: **0/48**. Location validity and gold grounding: **48/48**, including 39 native and nine visual page-level candidates.
- Rejections: one source-field rejection and four detached associations. Honest visual location does not verify transcription.

These scores describe deterministic replay, **not OpenAI discovery precision/recall or production accuracy**. Corpus canonical SHA-256 is `f9f12cb21012d1083500e1ee1b7737184700627661a3ba4155470af741be6ab3`; evaluator `engineering-evaluation-v1` rules hash is `e9592bdf55109e9d31584f4fe7081fb27f6d27753af2c47b9f374a2c5b5f95d1`. Reports include recording/resource identities and per-case counts/issues. Exact literal matching and a closed synthetic annotation scope limit generalization. The evaluation design keeps datasets and explicit criteria separate from model outputs, consistent with the official [evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

## Live evaluation boundary and coverage claims

The optional CLI live mode requires explicit source-processing authorization expressed as an approved canonical corpus digest, exact preprocessed Document bindings, selected cases and a sufficient total call bound. API/worker external controls and credentials must already be configured. The helper neither uploads nor processes/classifies documents. It checks all selected original artifact roles/hash/size/dimensions and planned pins in one transaction before committing any run; a later bad binding rolls back the entire batch before provider I/O.

Execution uses the normal production profiles, coordinator and `execute_unit()`, not a direct SDK path. Each case pins two admissions, one attempt per stage and one concurrent attempt per run. There are no retry/repair calls in this evaluation envelope. Existing workers may claim its deliveries under the same DB limits/fences. Reports read committed successful outputs, retain failed-case gold denominators, published rejection counts, run/profile/model/admission/call counts and provenance. Timeout/interruption cancels only its own unfinished runs, preserving completed history. The polling deadline does not preempt an already-started I/O operation; pinned timeouts still apply.

Automated runner tests use injected providers and report `MOCK_PIPELINE`. Offline files claiming live origin become `UNVERIFIED_RECORDING`; a label cannot prove provider execution. Only actual successful live calls can mark the live-runner report as measured. No live report is included in this delivery. Private bindings/reports belong under gitignored `evals/extraction/private/`.

- **Architectural support:** all 20 registry-v1 types/296 definitions; metadata-wide and explicit-name interpreter regressions cover them.
- **Representative engineering fixture coverage:** four priority families—two-winding transformer, LV breaker, cable and utility source—plus unknown/tagless/isolated and adversarial association cases. This is not measured extraction coverage of every type or attribute.
- **Live-model evaluation coverage:** zero types, zero fixtures, zero paid calls. Account/model availability, production discovery accuracy, prompt-injection resistance against a live model and real visual recognition quality remain unverified.

## Verification and operational state

The full backend regression passed **1,487 tests, no skips**, with six existing dependency warnings in **249.99 seconds**: prior M5 baseline 1,445 plus 42 M6 cases. After preserving published diagnostic counts in live report reconstruction, the four runner integration tests passed again in **3.31 seconds**. The final runner test covers three fixtures/six admitted calls, including a detached association; these are injected provider calls. Other cases verify whole-batch preflight rollback, no retry/dropped denominator on stage failure and timeout cancellation isolated from unrelated runs.

The full suite includes existing data-preserving migrations, exact canonical/registry values, legacy fake/probe profiles, production SDK transport mocks, real Celery/beat/Redis/PostgreSQL/MinIO publication/retry/restart, cancellation and stale-worker fences. Fresh Alembic upgrade to head 0013 passed on a disposable database; no migration was added. Ruff, changed-file formatting, `pip check` and whitespace checks pass. Extraction/worker wheels build and import directly from archives; the packaged CLI entrypoint and complete scripted report reproduce exactly. Existing historical/production identity regression fixtures remain unchanged. No frontend/browser check was needed for this backend/CLI-only milestone.

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:55441/powerforge_phase6c_m6 \
S3_ENDPOINT_URL=http://localhost:59011 S3_PUBLIC_ENDPOINT_URL=http://localhost:59011 \
REDIS_URL=redis://localhost:56391/0 RUN_INTEGRATION=1 \
.venv/bin/pytest -q --tb=short

.venv/bin/python -m powerforge_extraction.eval \
  --corpus evals/extraction/v1/corpus.json
```

Disposable project `powerforge-phase6c-m6` used tmpfs PostgreSQL/Redis/MinIO and was removed after checks. Normal development services/data were untouched. Generated package build directories were removed. No live paid call, model-account check or customer document processing was performed.

## Evolution and future phases

Treat published prompt/schema/terminology/interpreter/grounding/runtime resources as versioned contracts. Add new identities and retained compatible readers/resources rather than changing the meaning of a deployed version. Preserve supported old manifest/profile wire serialization and immutable output interpretation. A shared algorithm change requires deliberate historical compatibility or explicit unsupported-resource failure; updating a fixture hash alone is insufficient. Regenerate reviewed resource/wire fixtures, run legacy identity and meaningful execution regressions, build wheels and reproduce hashes there. Actual calls must record selected schema/rendered inputs/usage, and each new model stage/attempt must pass ordinary admission controls.

For evaluation evolution, author gold independently, retain raw source/annotation identity and provenance, version changed matching rules, add negative controls and regenerate the clearly labeled scripted baseline. Do not tune gold or denominators to make a model look correct. Keep live reports distinct, record the evaluated model/profile/corpus and inspect actual cases before making support claims. Broader data, calibrated quality measures and an expanded evaluation harness remain Phase 6F.

Phase 6D can add bounded table/schedule stage definitions and explicit row/cell anchors through the existing planner, response schemas, artifact ownership and WorkUnitOutput publication. It must not treat response row IDs or source groups as physical identity, fabricate missing cells/default values, collapse competing readings or add unaccounted model calls. Table reconstruction is not delivered by 6C.

Phase 6E can add versioned OCR artifacts and independently verified text/region mappings. Pin exact OCR producer/artifact identities, distinguish OCR offsets from native codepoints and establish actual page geometry/text verification before increasing precision. Never retrofit visual transcriptions with fabricated native offsets or silently upgrade immutable historical VISUAL_PAGE evidence. Preserve multimodal limits and no-fallback source semantics.

Cross-document entity resolution, topology inference, reconciliation, UI, engineer acceptance/verification and engineering completeness findings remain later phases. The remaining optional 6C validation is an explicitly authorized live run on approved fixtures; its findings must be reported separately from the deterministic results above.
