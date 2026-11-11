# Phase 6G regression corpus

`synthetic.json` defines the printed source and expected output independently of the extraction converter. The tests generate PDFs from those definitions and derive native preparation and layout before constructing the scripted provider responses. The cases cover split and distributed Engineering fields, a two-column transformer form and a breaker schedule. Additional tests cover merged headers, a long schedule, visual-only evidence, invalid provider responses and run isolation.

```sh
.venv/bin/pytest -q tests/test_phase6g_semantics.py tests/test_phase6g_provider_diagnostics.py tests/test_phase6g_tables_v4.py -m 'not integration'
```

Run the marked retry test with the repository's integration settings and disposable PostgreSQL, Redis and MinIO. It starts a Celery worker and beat, uses an SDK-compatible provider stub, and reads the resulting exact evidence through a signed MinIO URL.

## Optional private-document evaluation

1. Get approval for each source document and for sending its extraction inputs to the configured provider. Keep the original drawings, local captures and per-source results in approved private storage. The developer-local path for the supplied PDFs is `evals/extraction/real-world/phase-6g/sources/`.
2. Before running extraction, annotate the actual pages independently of model output. Record equipment roles and tags, printed values and units, qualifier text, exact source locations and expected associations. For REX and DELTA, include distributed headings and winding or rating blocks, any normal versus alternate ratings and ambiguous associations. For Eaton, check the title-block panelboard tag, the two physical branch breaker rows and the count of provisioned positions as separate observations.
3. In an authorized evaluation environment, enable external execution and the semantic-profile wizard opt-in using `EXTRACTION_EXTERNAL_ENABLED=true` and `EXTRACTION_OPERATION_SEMANTIC_PROFILES=true`. Configure the provider key only in the worker environment. Use the same committed preparation/layout, pages and source mode for both comparison runs. Record the profile, model and exact source identities. Compare historical v3 Tables with v4 Tables and run Engineering separately. Use the explicit profile selector in the extraction run API for the historical control.
4. In Run History, record each stage's provider outcome, returned observations, grounded or rejected counts, published mapped/unmapped/invalid counts and safe reason codes. Include output tokens and byte sizes where available. Check each candidate against the independent annotations and its cited source. Record eligible observations missed or misassociated, and retain visual-only claims separately from independently verified text.
5. Report the denominator, abstentions, false positives and missed observations by stage. Keep sanitized summaries separate from private evidence. Compare to the scripted results in the Phase 6G handoff.

These three source drawings were outside the executed Phase 6G checks.
