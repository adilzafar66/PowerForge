# Extraction Debugger

A standalone operator tool for both Phase 6R extraction stages. FastAPI serves a
React and TypeScript build at `http://127.0.0.1:3100`. It uses the existing
audit metadata, validated results, candidates, evidence and retrieval journal.

## Prerequisites and setup

Use the PowerForge Python 3.12 virtual environment with the repository packages
installed, Node.js, and a running PowerForge database with the response-audit
migration applied. Set up the private audit bucket and lifecycle as described in
[Extraction operations](../../docs/EXTRACTION.md#extraction-response-audit).

Create an individual PostgreSQL login as the schema administrator. Inside
`psql`, run `CREATE ROLE audit_alex LOGIN;` and `\password audit_alex`.
Then apply the debugger's column-level grants from the repository root.
Set `POWERFORGE_ADMIN_DATABASE_URL` to the schema administrator's libpq
connection URL for the target database. The script grants access to the
database selected by `psql`.

```sh
psql -X -v ON_ERROR_STOP=1 -d "$POWERFORGE_ADMIN_DATABASE_URL" \
  -v debugger_operator=audit_alex \
  < tools/extraction-debugger/grant-operator.sql
```

For an existing operator, reapply this script after migration
`6r_0014f_typed_value_proposals` to grant read access to the two persisted
proposal columns.

Use a dedicated MinIO/S3 operator identity with only `s3:GetObject` on
`arn:aws:s3:::powerforge-response-audit/stage2/*` and `arn:aws:s3:::powerforge-response-audit/stage1/*`. Enable storage-side access
auditing to cover reads outside the debugger. Keep database and storage reader
credentials in an operator shell or secret manager.

Build the standalone frontend:

```sh
npm --prefix tools/extraction-debugger ci
npm --prefix tools/extraction-debugger run build
```

Set the variables listed in [env.example](env.example) in your operator shell.
Generate the startup secret with `export EXTRACTION_DEBUGGER_SECRET="$(openssl rand -hex 32)"`.
Supply the database URL in the form
`postgresql+psycopg://audit_alex:URL_ENCODED_PASSWORD@127.0.0.1:5432/powerforge`.
Use the loopback endpoint of the **audit** MinIO on your Mac, typically
`http://127.0.0.1:9010`. Set `S3_REGION` to the same storage region as the
extraction worker when overriding the PowerForge default.

From the repository root:

```sh
.venv/bin/python tools/extraction-debugger/app.py
```

Open `http://127.0.0.1:3100` and enter the startup secret. PowerForge's
ordinary Compose command does not launch this tool. The main web app does not
need to be rebuilt.

## Inspect and compare

Search using the full run or attempt UUID. A run UUID lists its extraction attempts. **Open attempt** can also look up an attempt without an audit record. The history identifies the attribute-extraction attempt UUID
separately from the run UUID.

Choose **Reveal original response** to perform a verified and journaled read.
Use **JSON tree** to expand values and copy JSON Pointer paths. **Raw text**
shows the original output even when JSON validation failed. The assertion
explorer keeps the original zero-based positions. Filter to **Quarantined** to
see sanitized errors such as `attributes[24].raw_value`.

Choose **Compare** on an assertion to see the original and validated objects
alongside the proposal and alternate representations read from the persisted
candidate, its mapping outcome, and its normalized value. The debugger uses quarantine
positions and matching local references to correlate the records. It displays
raw and proposed values with their JSON types, source and proposed units, and
any alternate representations. Historical enum proposals retain their own
label. Normalized values use their recorded type and exact stored digits.
Schema admission and engineering mapping are separate outcomes.

The exact numeric token display uses the browser's JSON source access. If an
older browser cannot recover the digits of a large integer, **Raw text** and
the verified export still provide the exact original response.

**Export original** verifies and journals another retrieval. It downloads the
exact bytes with a deterministic attempt-based filename. Treat that local
file as confidential and follow your audit retention policy.

## Security and unavailable responses

The startup command binds to IPv4 loopback. Use the documented address rather
than an alias. The app checks the socket peer, Host, Origin and a custom header
on POSTs. It issues a one-hour HttpOnly, SameSite=Strict session cookie with a
single active session per process. HTTP is used on loopback. Raw contents stay
in memory during inspection and the debugger supplies no direct object-store
URLs. Its only database write is the existing append-only retrieval journal.

After expiry, the debugger can show stored metadata, quarantine diagnostics and
validated records. Missing objects and integrity failures are reported
separately. A missing object within retention can mean that the selected bucket
is wrong or that the object was removed. For database or storage errors, check
the operator grants, credentials and service availability. Permission to
retrieve a raw response includes permission to journal that retrieval.

The app provides no extraction or retry controls and cannot recover expired or
never-retained original data. Historical reconciliation is available only where
the recorded Stage 2 payload and audit positions establish the relationship.

## Verification

Run the API and frontend suites from the repository root:

```sh
PYTHONPATH=tools/extraction-debugger .venv/bin/pytest -q -rs tools/extraction-debugger/tests
npm --prefix tools/extraction-debugger test
npm --prefix tools/extraction-debugger run build
```

For the integration suite, point `DATABASE_URL` at a disposable PostgreSQL
database with a test administrator that can create roles. Apply migrations and
run with `RUN_INTEGRATION=1`:

```sh
.venv/bin/alembic -c database/alembic.ini upgrade head
RUN_INTEGRATION=1 .venv/bin/pytest -q tests/test_extraction_debugger_integration.py
```

The optional MinIO test needs an explicitly selected retained test attempt
(`EXTRACTION_DEBUGGER_TEST_ATTEMPT`) and the operator variables. It records
one audit read. The layout smoke uses the existing PowerForge Playwright
installation and a running debugger. Set `DEBUGGER_BROWSER_PATH` to a local
Chrome executable when Playwright's bundled Chromium is unavailable, then run
`node tools/extraction-debugger/tests/layout.mjs`.

### Attempt performance

Apply migrations through `6r_0014m_recognition_audit` and rerun the operator grant script on the target database before running this debugger version. The attempt details include a **Performance** section. Attempts that reach the provider can appear even when an audit object was never created. Audit retrieval and exports still use the audited access path.

Server-owned Stage 2 attempts show the output contract and overflow separately from
quarantine. The comparison uses each assertion's original collection and index
to align the provider JSON with the expanded result and published candidate.
Overflow positions remain visible when the original object expires.

Provider duration uses a monotonic timer around the SDK call. Queue wait uses the same PostgreSQL clock for eligibility and claim and excludes backoff and Stage 1 prerequisite time. Database publication covers candidate and audit metadata staging through flush. Attempt total starts after claim and ends at the recorded settlement in the final transaction. The final commit and any subsequent redelivery are outside that measurement. Output storage time includes writer preflight and upload. The database publication time includes audit metadata. A phase can remain unavailable because the attempt did not reach it, no provider response supplied the field, or the worker lost the lease before recording the attempt. Historical records still show their original coarse call duration.

The versioned metrics object on the terminal attempt is nullable and capped at 4 KiB. The debugger reads it by work-unit ID, so it has no dedicated index. The request body count measures the SDK-compatible HTTP JSON encoding. Section byte counts use canonical JSON and the encoded-image count covers Base64 payload bytes. Source readings are counted by preferred modality. Alternate reading counts include the retained alternatives, and text character totals include both preferred and alternate transcriptions. OCR selection is recorded from the verified enrichment, including when selected OCR produced no preferred readings. Line group count is available for the compact v2 provider view. Pinned Stage 2 effort appears even when the provider times out. When supplied, the provider-reported effort appears separately. Metrics contain bounded counts, controlled labels and existing correlation hashes.


Version 2 shows the pinned Stage 2 input and source projection, local OCR execution, available and exposed reading counts, and separate native/OCR/image transmission flags. Older attempts can show **Unavailable** for these fields. Evidence details pair the admitted citation kind with the published fragment outcome when positions are available. The regional localization experiment runs only through the offline evaluator. [Stage 2 modality evaluation](../../evals/phase6r/ATTRIBUTE_SOURCE_MODALITY_EVALUATION.md)
