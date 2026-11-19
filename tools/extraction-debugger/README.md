# Extraction Debugger

A standalone operator tool for Phase 6R Stage 2 responses. FastAPI serves a
React and TypeScript build at `http://127.0.0.1:3100`. It uses the existing
audit metadata, validated results, candidates, evidence and retrieval journal.

## Prerequisites and setup

Use the PowerForge Python 3.12 virtual environment with the repository packages
installed, Node.js, and a running PowerForge database with the response-audit
migration applied. Set up the private audit bucket and lifecycle as described in
[Extraction operations](../../docs/EXTRACTION.md#stage-2-response-audit).

Create an individual PostgreSQL login as the schema administrator. Inside
`psql`, run `CREATE ROLE audit_alex LOGIN;` and `\password audit_alex`.
Then apply the debugger's column-level grants from the repository root:

```sh
docker compose -p powerforge exec -T postgres psql -X -v ON_ERROR_STOP=1 \
  -U powerforge -d powerforge -v debugger_operator=audit_alex \
  < tools/extraction-debugger/grant-operator.sql
```

Use a dedicated MinIO/S3 operator identity with only `s3:GetObject` on
`arn:aws:s3:::powerforge-response-audit/stage2/*`. Enable storage-side access
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
`http://127.0.0.1:9010`.

From the repository root:

```sh
.venv/bin/python tools/extraction-debugger/app.py
```

Open `http://127.0.0.1:3100` and enter the startup secret. PowerForge's
ordinary Compose command does not launch this tool. The main web app does not
need to be rebuilt.

## Inspect and compare

Search using the full run or attempt UUID. A run UUID lists its audited Stage 2
attempts. **Open attempt** also looks up a historical Stage 2 attempt with no
audit record. The history identifies the attribute-extraction attempt UUID
separately from the run UUID.

Choose **Reveal original response** to perform a verified and journaled read.
Use **JSON tree** to expand values and copy JSON Pointer paths. **Raw text**
shows the original output even when JSON validation failed. The assertion
explorer keeps the original zero-based positions. Filter to **Quarantined** to
see sanitized errors such as `attributes[24].raw_value`.

Choose **Compare** on an assertion to see the original and validated objects
alongside the recorded candidate outcome. The debugger uses quarantine
positions and matching local references to correlate the records. It displays
normalized values as stored, including exact decimal strings. Schema admission
and engineering mapping are separate outcomes.

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
