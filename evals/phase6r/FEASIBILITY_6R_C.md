# Phase 6R-C live feasibility checkpoint

The [correction and rerun report](FEASIBILITY_6R_C_CORRECTION.md) records the follow-up.

Run on 2026-11-13 with the approved page 1 of each of three real engineering PDFs. The pages contain engineering notes and prose, tabular ratings and schedules, and equipment drawings. The sample is separate from the held-out benchmark. The operator authorized up to six calls with retries disabled and a 2,000,000-token ceiling. Two calls were sent. Page hashes, source annotations, request projections, raw stage results, and audit records were kept outside the repository.

The run used the normal revision-scoped preview, consent, source preparation, lease, provider and stage-result path with disposable PostgreSQL and in-memory object storage. The configured model was `gpt-6-luna`, contract `phase-6r-v1`, prompt bundle `phase-6r-stages-v1`, and profile hash `0debf07fbbe4b13ec12c731c6ea5560351d7493941005b714f5bb2dc7475722a`. The run used standard pricing with uncached long-context list rates as a conservative cost estimate. [OpenAI pricing](https://developers.openai.com/api/docs/pricing)

## Page outcomes

- **Delta transformer.** Local preparation exceeded the 5,096 native drawing primitive limit. The layout prerequisite failed and zero calls were sent.
- **REX transformer.** Native preparation completed with 4,629 primitives. Local layout exceeded the 64 native grid component limit. A local-only replay reproduced that exact failure. Zero calls were sent.
- **Eaton panel drawing.** Both stages completed. The same 317 pinned readings, one detected source table, and the 1,700 × 2,200 PNG (297,310 bytes) went to both stages. Call 2 used the exact committed Call 1 output. The page contains a schedule, panel diagram, and prose notes. This gives one end-to-end mixed-content case. Performance by source stratum remains unmeasured.

The two rejected pages stay in the recall denominators. The source limits were retained and the failed pages produced no partial source projection or alternative model calls.

## Observation and evidence review

The gold checklist was written from the approved pages before receiving provider output. The denominators below describe this preliminary checklist, with one-to-one matches by source occurrence. They are provisional and do not set a release threshold.

- **Equipment recall.** Three of six annotated equipment occurrences were recovered across the sample, all on Eaton. Those were the panel bus and two populated branch positions. The upstream breaker reference was omitted. Recognition also emitted 18 proposed breakers from provision-only positions. The drawing shows these as provisions, so those proposals lack support as physical breaker observations. The two transformer occurrences were unavailable because their pages failed locally.
- **Attribute accuracy.** Six of 19 checklist attributes had the expected registry key, source value and unit across the sample. On Eaton this was 6 of 8, covering bus current and voltage and the pole count and trip rating for each populated breaker. Phase count was omitted. The short-circuit proposal preserved the series-rated qualifier but returned the incomplete unit string `A.I.C.` instead of an amperage unit. Two annotated connection enum proposals were on the blocked REX page, so their live accuracy is unavailable.
- **Ownership.** Six of seven returned assertions corresponding to Eaton checklist items linked to the expected source-local owner and met the checklist value/unit criteria. The seventh also pointed to the expected panel bus, but failed the unit check. Ownership alone was 7 of 7 for those returned assertions and 7 of 19 across the full checklist. The two identical breaker ratings came from one shared schedule row. The recognition citations did not independently distinguish the positions. Attribute assertions about provision-only positions inherit the unsupported equipment owners.
- **Evidence quality.** All 263 returned fragments used existing pinned reading IDs, 99 in recognition and 164 in attributes. There were no visual or quote-only fragments. This is a reference-validity count. Manual occurrence checks found that both installed breaker observations cited the same model and quantity rather than distinguishing their positions. The provision assertions cited provision markings and a schedule count, which did not support the asserted equipment interpretation. The short-circuit unit citation identified the `A.I.C.` portion without grounding a complete amperage unit. Final fragment localization and rendering remain part of publication.
- **Output capacity.** Eaton returned 21 equipment observations and 37 registry assertions. It returned no raw-unmapped assertions. Recognition used 139,755 request JSON bytes and 11,719 response JSON bytes. Attributes used 156,801 request JSON bytes and 22,029 response JSON bytes. These exclude the base64 image and transport wrapper. There was no provider truncation.

## Usage and latency

- Equipment recognition measured 45,584 input tokens, 4,693 output tokens, and 37.749 seconds at the provider boundary.
- Attribute extraction measured 50,410 input tokens, 8,528 output tokens, and 59.957 seconds at the provider boundary.
- Total measured use was 109,215 tokens. The conservative estimated cost was USD 0.029115. Eaton's extraction run elapsed time was 99.233 seconds, excluding earlier source preparation. Neither blocked page incurred provider usage.

The two local capacity failures and provision-only false positives are open for checkpoint review. The held-out evaluation remains in 6R-F.
