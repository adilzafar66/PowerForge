# Phase 6C M3 handoff — Grounding, grouping and atomic output

Branch: `codex/phase-6c-engineering-extraction`. Implementation baseline: `4577e9ff73a9988676f62573dcc7e9148ae6d7af`, including the M2 parenthetical-qualifier correction. Scope: M3 of [PHASE6C_PLAN.md](PHASE6C_PLAN.md). M4–M6 remain pending; production engineering profiles/provider execution are not enabled by this change.

## Delivered interfaces and ownership

The extraction package now separates three responsibilities:

- `engineering_sources.page_spec_for_unit(session, unit_id)` snapshots one page's source identity from the exact run/unit input IDs. It checks document/page/processing ownership, completed processing, selected pages, supported artifact types/MIME and distinct roles. It does not select latest artifacts, read mutable page text counts or commit.
- `grounding.load_page_sources(spec, storage, ...)` verifies the selected immutable objects and returns loaded native text/image bytes. This has no ORM/provider dependency and can run after the caller releases its metadata transaction. The trusted server must construct specs through the ownership loader; model responses cannot supply descriptors or storage keys.
- `engineering_output.convert_equipment(response, sources)` and `convert_attributes(response, sources, recognition_context)` revalidate M1 responses, ground observations, apply M2 and produce bounded WorkUnitOutput. They perform no DB writes, commits, scheduling or provider calls. Outputs are published with `ExtractionPersistence.publish()` in the caller's transaction, or the existing fenced coordinator path when integrated in M4/M5.

`engineering_sources.load_recognition_context(session, sources, recognition_unit_id)` loads completed EQUIPMENT_RECOGNITION outputs for the same run/document/page/processing context. It rejects foreign/incomplete context, non-engineering producers, invalid/duplicate local references, missing/mismatched evidence and inconsistent groups. Native context is rechecked against the loaded exact text, not trusted from an arbitrary metadata string. Outputs retain prior successful candidate/group/evidence IDs for immutable cross-unit references. Production stage scheduling must use committed upstream success before the next worker starts; M3 does not add that scheduling mechanism or take ownership of commits.

## Artifact verification and limits

Each selected artifact is read once through ObjectStorage with bounded chunk reads, closed on success or failure, and checked against pinned byte size/SHA-256. Native text decodes strict UTF-8. Analysis images must be actual PNGs with the exact recorded dimensions and within pixel limits. No thumbnail/current-version fallback or object writes occur. Temporary storage failures retain TransientStorageError for bounded retry by the existing execution infrastructure; this change does not relabel them as permanent invalid source data.

Default loading bounds are 2 MiB per artifact, 4 MiB combined and 20 million image pixels, with explicit caller parameters for future pinned profiles. M4/M5 must additionally enforce their model input/context bounds and preserve selected roles on retry. Native statement/evidence admission is bounded at 2,000 codepoints; oversized lines are not silently clipped into confident claims. Publication retains the existing independent pinned-text verification/offset-bound checks, including the necessary source reread inside 6A.

## Native-text grounding

Quotes and optional immediately adjacent prefix/suffix are matched verbatim in the exact pinned UTF-8 representation. There is no case/Unicode/whitespace normalization for grounding. Server-resolved offsets use Python Unicode codepoints, not bytes or UTF-16. Two surviving matches suffice to mark ambiguity without allocating all occurrences.

Unique observations use complete verified source-line evidence, so a model-selected substring cannot hide qualifiers or negation outside the fragment. Equipment tags/names must first pass M2's source-field checks against the original observed expression; surrounding line text cannot lend an unrelated field to that expression. Full-line semantic interpretation and evidence follow that check. The only compound-line exception is a fully matched explicit numeric AF/AT pair with no extra text: each field gets its actual source clause and exact offsets. Arbitrary prose, ratios or multi-field lines are not split into inferred facts.

Repeated/unresolved occurrences have null offsets and honest TEXT_PAGE grounding. They do not acquire the first occurrence's equipment context. A verified fragment in an unresolved complete-line context may be retained only as detached UNMAPPED data after its own source fields pass M2; the full-line evidence retains the qualifier. Missing/invalid quotations, invented raw expressions/tags/values and inconsistent source fields produce no supported candidate/evidence. A real but unrelated extra excerpt is not added as support. If native anchors are supplied, invalid native support cannot fall back to visual page grounding.

## Source-local groups and association

Accepted precise mentions can create tagged or tagless SourceGroups. Group/candidate/evidence IDs and local keys are deterministic within the run/logical page-stage/source context; tag strings are not identity keys. Same tags on separate pages/blocks remain distinct observations, never canonical equipment matches.

Native attribute association requires the selected reference to identify the same exact native artifact and an admitted structural block containing the attribute's actual occurrence. The equipment header must be the first line of a blank-line-delimited block. Competing recognized/ambiguous mentions, detected type headers or unsupported lines disable block association. Continuation lines require a registry/terminology attribute label (optionally with a recognized unit suffix) or an explicit rating clause. A colon alone is insufficient: unknown labels, including missed `TAG: Equipment Type` headers, disable association. A model `equipment_ref` alone, a nearest tag, a different block/page or borrowed modality does not establish membership. Detached observations remain representable without invented mentions or IDs.

This is a conservative source-text structure rule, not a universal PDF layout or physical-identity proof. Native text ordering is not guaranteed to reflect visual layout. Ambiguous/dense layouts remain unresolved; advanced layout, table interpretation and cross-page identity remain later work. SourceGroup means observations plausibly belong together within the source, not a verified physical asset.

Several candidates may share one evidence row. Attribute outputs can also cite committed recognition evidence as SUPPORTING and reference its mention/group, subject to 6A same-run ownership checks. Invalid normalization and unmapped claims retain their actual raw source and citations without normalized slots. Conflicting values remain individually visible. Exact NUMBER/INTEGER/BOOLEAN serialization is preserved through publication and HTTP reads.

## Visual and hybrid behavior

The previously approved visual policy is preserved: registry-valid model readings may become MAPPED candidates with an explicit page-level limitation. Image bytes/artifact identity are verified; transcribed text and pixel semantics are not independently verified. Evidence is VISUAL_REGION with null snippet, region, text offsets and offset convention. Candidate diagnostics say `grounding_precision=VISUAL_PAGE` and `text_verified=false`.

Visual association is explicitly `VISUAL_REPORTED`. One declared visual item on the exact image may supply its source-local context, including a tagless nameplate. Multiple visual items require an explicit unique observed tag in the attribute reading, with identifier boundaries; otherwise association is detached. This remains model-reported and can be wrong if recognition missed an item. It is not a geometric/identity proof. Representative model evaluation is still required.

Native observations use native context; visual observations cannot borrow an unrelated native qualifier or type context. Where native support fully grounds a claim, unused visual anchors do not manufacture additional supporting facts. Conflicting text/image readings are separate observations. No OCR, region extraction or calibration is implemented.

## Atomic publication and read markers

WorkUnitOutput now has closed `diagnostic_counts` keys: `rejected_ungrounded`, `rejected_source_fields`, and `detached_associations`. Values are strict nonnegative integers capped at 10,000; they cannot replace collection-count names. The publisher merges these into the existing unit `output_counts` JSON inside its savepoint before the COMPLETED write. Failed publication rolls back output and counts together; completed-unit immutability still prevents later edits. Empty diagnostic dictionaries preserve legacy collection counts. No schema migration is needed.

Evidence summary/detail read allowlists add `grounding_precision`, derived from existing source/offset/region fields: TEXT_OFFSETS, TEXT_PAGE, VISUAL_REGION, VISUAL_PAGE or PAGE_ONLY. This reports location precision, not engineering verification. Candidate diagnostics separately expose association/fragment limitations. Existing revision-document membership, effective-unit filtering, exact artifact signing and read-only behavior remain unchanged. No new routes, canonical writes or UI work were added.

## Identities and compatibility

`engineering-grounding-v1` and `tests/fixtures/extraction/grounding_v1_identity.json` pin the shipped grounding, conversion and ownership/context-loading source files. Unknown versions fail without fallback. M4 profiles must combine this identity with the unchanged M1 stage/registry/terminology and M2 interpretation identities. Future deployed algorithm changes require retained versioned readers/resources; do not silently reinterpret old pending work.

M1 prompts/schemas/manifests, M2 rules, registry-v1, migrations 0011–0013 and legacy infrastructure profiles remain unchanged. The coordinator/provider adapter are not wired to these production stages yet. Internal 6A test plans exercise the output boundary without claiming production execution availability; existing managed-run DB fencing is covered by the full regression suite.

## Actual verification

**1,365 backend tests passed, no skips**, six existing dependency deprecation warnings, in **155.44 seconds**. This includes **31 new M3 tests** and all earlier registry, canonical-model, extraction, storage, worker and migration regressions:

```sh
DATABASE_URL=postgresql+psycopg://powerforge:powerforge@localhost:55438/powerforge_phase6c_m3 \
S3_ENDPOINT_URL=http://localhost:59008 S3_PUBLIC_ENDPOINT_URL=http://localhost:59008 \
REDIS_URL=redis://localhost:56388/0 RUN_INTEGRATION=1 \
.venv/bin/pytest -q --tb=short
```

Coverage includes Unicode offsets/repeated phrases, complete-line qualifiers/negation, exact AF/AT clauses, forged excerpts/tags/fields, source stream integrity/closing/chunking, image dimensions/pixel limits, tagless/shared/repeated groups, ambiguous/missed competing headers, visual/hybrid limitations, foreign context/source inputs, historical processing artifacts, atomic rollback/count immutability, actual API precision/false/large integers and invalid/unmapped retention. The full suite also executes existing Celery/beat recovery and data-preserving migration checks; these remain infrastructure probes, not a new production-stage end-to-end claim.

The wheel builds, imports the new modules directly and reproduces the grounding fingerprint and legacy prompt identity. Ruff, changed-file formatting, dependency and whitespace checks pass. Test writes used only Compose project `powerforge-phase6c-m3`, disposable PostgreSQL/Redis/MinIO with tmpfs data, and in-memory source fixtures; normal development services/data were untouched. Disposable services are removed after validation. No frontend/browser or paid/live-model test was run, and no production-model accuracy is claimed. The synthetic visual fixture contains a drawn label but its reading was supplied by the test, not measured from a live model.

## M3 review corrections

The review of baseline `6c45bb3` identified two source-admission gaps. Equipment conversion now checks the original observation's tag/name before expanding its expression to complete-line context. A tag such as `TX-2` in a parenthetical reference outside the observed `TX-1` expression is rejected, while the complete line still supplies semantic qualifiers and evidence. Native block continuation now requires a known registry/terminology attribute label or an explicit rating clause; missed tag-prefixed headers and arbitrary colon labels disable association. Subsequent attributes remain detached UNMAPPED observations without normalized values.

Ten new cases cover borrowed tags/names, missed colon headers (including aliases/unknown types), unknown labels and valid registry/unit/terminology continuations. The invalid/unmapped publication fixture now places its independent unknown field outside the equipment block and declares no equipment reference, so it continues testing normalization failure and raw retention without relying on unsafe association. The grounding-v1 fingerprint fixture is refreshed for this correction before production profiles are enabled; M1/M2 identities and registry-v1 remain unchanged. This does not introduce a historical-profile fallback or enable execution of old identities.

Final review validation: **1,375 backend tests passed, no skips**, including **41 M3 cases** (ten added by this review), with six existing dependency warnings in **190.23 seconds**. The first full run exposed the old fixture's unsafe unknown-label association expectation; after correcting that fixture, its targeted test and the final full suite passed. Ruff, changed-file formatting and whitespace checks pass. The same disposable service configuration and test command above were used; no live provider calls were made.

## Next: M4

Implement dependent-stage planning/claims/dispatch/recovery and multimodal execution without changing admission budgets, leases, cancellation, append-only retries or publication fences. Load source snapshots in short transactions, perform model I/O after claim commit and supply only safe source-local references to providers. Keep production OpenAI/schema/profile wiring in M5 and measured evaluation in M6. A COMPLETED unit/run remains an execution result, not proof that all source information was discovered.
