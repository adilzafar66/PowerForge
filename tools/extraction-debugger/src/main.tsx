import { useEffect, useMemo, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import { api, errorText, type Attempt, type Detail } from "./api";
import { AssertionFields, assertions, Copy, Diagnostics, display, JsonTree, object, parseInspectorJson, type Assertion } from "./inspector";
import "./style.css";

const validationNames: Record<string, string> = {
  validated: "Fully validated", partial: "Partially validated", fatal: "Fatal response",
  empty: "Valid empty response", all_quarantined: "All assertions quarantined",
};
const validationName = (attempt: Attempt) =>
  attempt.validation ? validationNames[attempt.validation] : "Original not captured";
const date = (value: string | null) => value ? new Date(value).toLocaleString() : "Unavailable";
const retention = (row: Attempt) => row.retained === null ? "Not captured" :
  row.retained && row.expires_at && Date.parse(row.expires_at) > Date.now() ? "Within retention" : "Expired";
const ids = (row: Assertion) => `${row.publishedPosition ? "Validated " : ""}${row.collection}[${row.index}]`;

export function App() {
  const [signed, setSigned] = useState<boolean | null>(null);
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api("/attempts?limit=1", controller.signal).then(() => setSigned(true), (failure: Error) => {
      if (!controller.signal.aborted) { setSigned(false); if (failure.message !== "authentication_required") setError(errorText(failure)); }
    });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    function endSession() { setSigned(false); setError("Sign in again to view diagnostics."); }
    window.addEventListener("debugger-session-ended", endSession);
    return () => window.removeEventListener("debugger-session-ended", endSession);
  }, []);
  async function login(event: FormEvent) {
    event.preventDefault();
    setError("");
    try { await api("/login", undefined, { secret }); setSigned(true); }
    catch (failure) { setError(errorText(failure)); }
    finally { setSecret(""); }
  }
  return <>
    <header className="app-header"><div><strong>PowerForge</strong><span>Extraction Debugger</span></div>
      <div><span className="local">Local diagnostics</span>
        {signed && <button onClick={() => { setSigned(false); void api("/logout", undefined, {}).catch(() => null); }}>Sign out</button>}</div>
    </header>
    {signed === null ? <p className="notice">Checking operator session…</p> : signed ? <Workspace /> :
      <form className="login" onSubmit={login}><h1>Operator access</h1>
        <label>Startup secret<input value={secret} type="password" onChange={event => setSecret(event.target.value)}
          autoComplete="off" maxLength={1024} required /></label>
        <button className="primary">Sign in</button>{error && <p role="alert">{error}</p>}
      </form>}
  </>;
}

function Workspace() {
  const [identity, setIdentity] = useState("");
  const [query, setQuery] = useState("");
  const [validation, setValidation] = useState("");
  const [status, setStatus] = useState("");
  const [retained, setRetained] = useState("");
  const [cursors, setCursors] = useState<string[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const cursor = cursors.at(-1);
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (query) params.set("identity", query);
    if (validation) params.set("validation", validation);
    if (status) params.set("status", status);
    if (retained) params.set("retention", retained);
    if (cursor) params.set("cursor", cursor);
    setLoading(true); setError("");
    api(`/attempts?${params}`, controller.signal).then(response => response.json()).then(data => {
      setAttempts(data.items); setNext(data.next_cursor); setLoading(false);
    }).catch(failure => { if (!controller.signal.aborted) { setError(errorText(failure)); setLoading(false); } });
    return () => controller.abort();
  }, [query, validation, retained, status, cursor]);
  return <main className="workspace">
    <aside className="explorer"><h1>Attempts</h1>
      <form onSubmit={event => { event.preventDefault(); setQuery(identity.trim()); setCursors([]); }}>
        <label>Run or attempt UUID<input value={identity} onChange={event => setIdentity(event.target.value)} /></label>
        <div className="actions"><button className="primary">Search</button><button type="button"
          disabled={!identity.trim()} onClick={() => setSelected(identity.trim())}>Open attempt</button></div>
      </form>
      <div className="filters">
        <label>Validation<select value={validation} onChange={event => { setValidation(event.target.value); setCursors([]); }}>
          <option value="">Any</option>{Object.entries(validationNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <label>Execution<select value={status} onChange={event => { setStatus(event.target.value); setCursors([]); }}>
          <option value="">Any</option><option value="COMPLETED">Completed</option><option value="FAILED">Failed</option><option value="CANCELLED">Cancelled</option>
        </select></label>
        <label>Retention<select value={retained} onChange={event => { setRetained(event.target.value); setCursors([]); }}>
          <option value="">Any</option><option value="true">Within retention</option><option value="false">Expired</option>
        </select></label>
      </div>
      {loading ? <p role="status">Loading attempts…</p> : error ? <p role="alert">{error}</p> :
        attempts.length ? <ul className="attempts">{attempts.map(row => <li key={row.attempt_id}>
          <button className="attempt" aria-pressed={row.attempt_id === selected} onClick={() => setSelected(row.attempt_id)}>
            <strong>{row.document}</strong><span>Page {row.page} · Attempt {row.attempt_number}</span>
            <span className="badge">{validationName(row)}</span><span>{row.status} · {retention(row)}</span>
            <small>{row.provider} · {row.model ?? "Model unavailable"}{row.duration_ms !== null && ` · ${row.duration_ms} ms`}</small>
            <small>{row.received ?? "—"} received · {row.accepted ?? "—"} accepted · {row.quarantined ?? "—"} quarantined{row.overflowed ? ` · ${row.overflowed} overflowed` : ""}</small>
            <code>Run {row.run_id}</code><code>Attempt {row.attempt_id}</code><small>{date(row.finished_at)}</small>
          </button></li>)}</ul> : <p className="muted">No audited attempts match.</p>}
      <div className="actions"><button disabled={loading || cursors.length === 0} onClick={() => setCursors(cursors.slice(0, -1))}>Previous</button>
        <button disabled={loading || !next} onClick={() => next && setCursors([...cursors, next])}>Next</button></div>
    </aside>
    {selected ? <AttemptView key={selected} id={selected} /> :
      <div className="notice"><h2>Choose an attempt</h2><p>Search by run UUID or open a Stage 2 attempt directly.</p></div>}
  </main>;
}

function AttemptView({ id }: { id: string }) {
  const [detail, setDetail] = useState<Detail>();
  const [error, setError] = useState("");
  const [rawError, setRawError] = useState("");
  const [raw, setRaw] = useState<string>();
  const [expanded, setExpanded] = useState(false);
  const [responseSearch, setResponseSearch] = useState("");
  const [, refresh] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => refresh(value => value + 1), 15000);
    return () => window.clearInterval(timer);
  }, []);

  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("assertions");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(60);
  const [selected, setSelected] = useState("");
  const fatalJSON = detail?.fatal.some(issue => issue.category === "JSON");
  const parsed = useMemo((): unknown => {
    if (raw !== undefined && !fatalJSON) {
      try { return parseInspectorJson(raw); } catch { /* show raw text */ }
    }
  }, [raw, fatalJSON]);
  useEffect(() => {
    const controller = new AbortController();
    api(`/attempts/${encodeURIComponent(id)}`, controller.signal)
      .then(response => response.text()).then(body => setDetail(parseInspectorJson(body) as Detail))
      .catch(failure => { if (!controller.signal.aborted) setError(errorText(failure)); });
    return () => controller.abort();
  }, [id]);
  if (error) return <p className="notice" role="alert">{error}</p>;
  if (!detail) return <p className="notice" role="status">Loading attempt…</p>;
  const row = detail.attempt;
  const retained = retention(row);
  const rows = assertions(detail, parsed);
  const filtered = rows.filter(item => {
    const original = object(item.original ?? item.validated);
    const matches = filter === "all" || item.state.toLowerCase() === filter ||
      original?.origin === filter || item.collection === filter || item.candidate?.mapping_status === filter;
    return matches && (!search || [ids(item), original?.local_ref, original?.attribute_key,
      original?.raw_label, original?.raw_value, original?.proposed_value, original?.proposed_enum_value,
      original?.proposed_unit, original?.alternate_representations, original?.key, original?.label,
      original?.raw, original?.source_unit, original?.value, original?.unit, original?.alternates]
      .some(value => display(value).toLowerCase().includes(search.toLowerCase())));
  });
  const chosen = rows.find(item => ids(item) === selected);
  const matchIndex = raw === undefined || !responseSearch ? -1 : raw.toLowerCase().indexOf(responseSearch.toLowerCase());
  async function reveal() {
    setBusy(true); setRawError("");
    try {
      const response = await api(`/attempts/${id}/original`, undefined, {});
      setRaw(new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(await response.arrayBuffer()));
    }
    catch (failure) { setRawError(errorText(failure)); }
    finally { setBusy(false); }
  }
  async function exportOriginal() {
    setBusy(true);
    try {
      const response = await api(`/attempts/${id}/export`, undefined, {});
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `stage2-${row.attempt_id}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setRawError(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <div className={expanded ? "inspection inspector-expanded" : "inspection"}>
    <section className="overview">
      <h2>{row.document}</h2><p className="muted">Page {row.page} · Attempt {row.attempt_number} · Attribute extraction</p>
      <div className="badges"><span className="badge">{validationName(row)}</span><span className="badge">{row.status}</span>
        <span className="badge">{retained}</span></div>
      <dl className="metrics">{Object.entries({ Received: row.received, Accepted: row.accepted,
        Quarantined: row.quarantined, ...(row.output_version && { Overflowed: row.overflowed }), Published: row.published }).map(([label, value]) =>
        <div key={label}><dt>{label}</dt><dd>{value ?? "—"}</dd></div>)}</dl>
      <details><summary>Execution and response metadata</summary>
        <dl className="metadata">{Object.entries({
          "Run UUID": row.run_id, "Attempt UUID": row.attempt_id, "Finished": date(row.finished_at),
          "Provider and model": `${row.provider} · ${row.model ?? "Model unavailable"}`, "Recorded call duration": row.duration_ms === null ? null : `${row.duration_ms} ms`,
          "Input tokens": row.input_tokens, "Cached input tokens": row.cached_input_tokens, "Output tokens": row.output_tokens,
          "Estimated cost": row.cost === null ? null : `USD ${row.cost} · ${row.pricing_basis}`, "Output bytes": row.output_bytes,
          "Response SHA-256": row.output_sha256, "Expiry": date(row.expires_at), "Stage error": row.error_code,
          "Request SHA-256": detail.request_sha256, "Accepted SHA-256": detail.result_sha256,
          "Recognition SHA-256": detail.upstream_sha256, Schema: detail.schema_version, Prompt: detail.prompt_version,
          "Output contract": row.output_version ?? "legacy-v7",
        }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd><code>{value ?? "Unavailable"}</code>
          {label.endsWith("UUID") && typeof value === "string" && <Copy value={value} label={`Copy ${label}`} />}</dd></div>)}</dl>
      </details>
      <PerformanceSection detail={detail} />
      <Diagnostics issues={detail.fatal} fatal />
      <div className="actions"><button className="primary" disabled={retained !== "Within retention" || busy || raw !== undefined} onClick={() => void reveal()}>
        {busy ? "Verifying…" : raw === undefined ? "Reveal original response" : "Original response verified"}</button>
        <button disabled={retained !== "Within retention" || busy || !!rawError}
          onClick={() => { if (window.confirm("Export a confidential original response? Keep the file private and follow the audit retention policy.")) void exportOriginal(); }}>Export original</button>
        {raw !== undefined && <button onClick={() => { setRaw(undefined); setMode("assertions"); }}>Hide original</button>}</div>
      {rawError && <p role="alert">{rawError}</p>}
    </section>
    <section className="assertion-list">
      <h2>Assertions</h2>
      <label>Search assertions<input value={search} onChange={event => { setSearch(event.target.value); setLimit(60); }} /></label>
      <label>Show<select value={filter} onChange={event => { setFilter(event.target.value); setLimit(60); }}>
        <option value="all">All assertions</option><option value="accepted">Accepted</option><option value="quarantined">Quarantined</option>
        <option value="overflowed">Overflowed</option><option value="MAPPED">Mapped</option><option value="UNMAPPED">Unmapped</option><option value="INVALID">Invalid</option><option value="EXTRACTED">Extracted</option><option value="INFERRED">Inferred</option><option value="raw_unmapped">Raw unmapped</option>
      </select></label>
      {(["attributes", "raw_unmapped"] as const).map(collection => <section key={collection}>
        <h3>{collection === "attributes" ? "Attributes" : "Raw unmapped"}</h3>
        <ul className="attempts">{filtered.slice(0, limit).filter(item => item.collection === collection).map(item => {
          const original = object(item.original ?? item.validated);
          return <li key={ids(item)}><button className="attempt" aria-pressed={ids(item) === selected}
            onClick={() => { setSelected(ids(item)); setMode("assertions"); }}>
            <code>{ids(item)}</code><strong>{display(original?.attribute_key ?? original?.key ?? original?.raw_label ?? original?.label ?? original?.local_ref ?? item.state)}</strong>
            <span className={item.state === "Quarantined" ? "bad" : "muted"}>{item.state}{item.candidate && ` · ${item.candidate.mapping_status}`}</span>
          </button></li>;
        })}</ul></section>)}
      {!filtered.length && <p className="muted">{raw === undefined ? "Reveal the original to inspect its assertions." : "No matching assertions."}</p>}
      {limit < filtered.length && <button onClick={() => setLimit(limit + 60)}>Show more assertions</button>}
    </section>
    <section className="details">
      <h2>Inspector</h2>
      <div className="actions">{[["assertions", "Assertion"], ["tree", "JSON tree"], ["raw", "Raw text"], ["compare", "Compare"]].map(([key, label]) =>
        <button key={key} aria-pressed={mode === key} disabled={["tree", "raw"].includes(key) && raw === undefined} onClick={() => setMode(key)}>{label}</button>)}
        <button aria-pressed={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? "Restore inspector" : "Expand inspector"}</button>
      </div>
      {raw !== undefined && ["raw", "tree"].includes(mode) && <label>Search original text<input value={responseSearch}
        onChange={event => setResponseSearch(event.target.value)} /></label>}
      {responseSearch && raw !== undefined && ["raw", "tree"].includes(mode) &&
        <p role="status">{matchIndex >= 0 ? "Found in original text" : "No match in original text"}</p>}
      {mode === "raw" && raw !== undefined && <pre>{matchIndex < 0 ? raw : <>
        {raw.slice(0, matchIndex)}<mark>{raw.slice(matchIndex, matchIndex + responseSearch.length)}</mark>
        {raw.slice(matchIndex + responseSearch.length)}</>}</pre>}
      {mode === "tree" && (parsed === undefined ? <><p>Invalid JSON. Showing original text.</p><pre>{raw}</pre></> : <JsonTree value={parsed} />)}
      {mode === "compare" && (chosen ? <div className="comparison">
        <section><h3>{chosen.publishedPosition ? "Original position unavailable" : `Original · ${ids(chosen)}`}</h3>{chosen.original === undefined
          ? <p>Original content unavailable. Reveal the retained response when available.</p>
          : <><AssertionFields value={chosen.original} /><JsonTree value={chosen.original} name="Original assertion" /></>}</section>
        <section><h3>Validated and published</h3>{chosen.validated === undefined
          ? <p>{chosen.state === "Quarantined" ? "Quarantined before publication." : chosen.state === "Overflowed"
            ? "Beyond the raw-unmapped publication limit." : "Validated relationship unavailable."}</p>
          : <><AssertionFields value={chosen.validated} /><JsonTree value={chosen.validated} name="Validated assertion" /></>}
          <Publication assertion={chosen} /></section>
      </div> : <p className="muted">Select an assertion to compare its recorded representations.</p>)}
      {mode === "assertions" && (chosen ? <><h3><code>{ids(chosen)}</code></h3><p>{chosen.state}</p>
        <Diagnostics issues={chosen.issues} />
        <AssertionFields value={chosen.original ?? chosen.validated} />
        <Publication assertion={chosen} />
        {chosen.original !== undefined ? <JsonTree key={ids(chosen)} value={chosen.original} name="Original assertion" /> :
          <p className="muted">Original assertion content is unavailable.</p>}
        {chosen.publishedPosition && <JsonTree key={ids(chosen)} value={chosen.validated} name="Validated assertion" />}</> : <p className="muted">Select an assertion to inspect its fields and diagnostics.</p>)}
    </section>
  </div>;
}

function Publication({ assertion }: { assertion: Assertion }) {
  const candidate = assertion.candidate;
  if (!candidate) return null;
  const citations = object(assertion.validated)?.evidence;
  const citationKind = (index: number) => Array.isArray(citations)
    ? object(citations[index])?.kind : undefined;
  return <div className="publication">
    <p>Published <strong>{candidate.mapping_status}</strong>{candidate.reason_code && <> · <code>{candidate.reason_code}</code></>}</p>
    <AssertionFields value={candidate} persisted />
    {candidate.normalized_type && <p>Normalized <span className="muted">({candidate.normalized_type.toLowerCase()})</span> <code>{
      ["TEXT", "ENUM"].includes(candidate.normalized_type) ? JSON.stringify(candidate.normalized_value) : candidate.normalized_value
    }{candidate.normalized_unit && ` ${candidate.normalized_unit}`}</code></p>}
    {candidate.evidence.length > 0 && <details><summary>Evidence localization</summary>
      <ul>{candidate.evidence.map((item, index) => <li key={index}>
        {typeof citationKind(index) === "string" && <>{String(citationKind(index))} · </>}{item.role} · {item.localization}{item.reason_code && ` · ${item.reason_code}`}
      </li>)}</ul></details>}
  </div>;
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<App />);

function PerformanceSection({ detail }: { detail: Detail }) {
  const { attempt, performance } = detail;
  const request = performance?.request;
  const flag = (value?: boolean) => value == null ? null : value ? "Yes" : "No";
  const duration = (value?: number) => value == null ? null : `${value.toLocaleString()} ms`;
  const metadata = (values: Record<string, string | number | boolean | null | undefined>) =>
    <dl className="metadata">{Object.entries(values).map(([label, value]) =>
      <div key={label}><dt>{label}</dt><dd>{typeof value === "number" ? value.toLocaleString() : value ?? "Unavailable"}</dd></div>
    )}</dl>;
  return <details><summary>Performance</summary>
    {metadata({
      "Model": attempt.model, "Outcome": attempt.status,
      "Provider response": performance?.response_status, "Failure stage": performance?.failure_stage,
      "Pinned reasoning effort": detail.requested_reasoning_effort,
      "Provider-reported reasoning effort": performance?.reasoning_effort, "Service tier": performance?.service_tier,
      "Queue wait": duration(performance?.queue_wait_ms), "Provider call": duration(performance?.provider_call_ms),
      "Source loading": duration(performance?.source_load_ms), "Request build": duration(performance?.request_build_ms),
      "Response admission": duration(performance?.admission_ms), "Localization and normalization": duration(performance?.localization_normalization_ms),
      "Audit storage": duration(performance?.audit_store_ms), "Database publication through flush": duration(performance?.db_publish_ms),
      "Attempt through settlement": duration(performance?.attempt_total_ms),
      "Input tokens": attempt.input_tokens, "Cached input tokens": attempt.cached_input_tokens,
      "Output tokens": attempt.output_tokens, "Reasoning tokens": performance?.reasoning_tokens,
      "Visible output tokens": performance?.visible_output_tokens,
      "Stage 2 input": performance?.input_configuration, "Source projection": performance?.source_projection,
      "Available readings": performance?.available_readings,
      "Exposed readings": typeof request?.native_readings === "number" && typeof request.ocr_readings === "number" ? request.native_readings + request.ocr_readings : null,
      "Image sent": flag(request?.image_sent), "Page OCR sent": flag(request?.ocr_sent),
      "Page native text sent": flag(request?.native_sent),
      [performance?.version === 2 ? "OCR executed locally" : "OCR selected"]: performance?.ocr_selected == null ? null : performance.ocr_selected ? "Yes" : "No",
      "Native readings": request?.native_readings, "OCR readings": request?.ocr_readings,
      "Alternate readings": request?.alternate_readings, "Reading text characters": request?.reading_text_chars,
      "Uncertain readings": request?.uncertain_readings, "Conflicting or ambiguous overlaps": request?.conflicting_overlap_count,
      "Reading order links": request?.order_count, "Overlap links": request?.overlap_count,
      "Line groups": request?.line_count, "Tables": request?.table_count, "Cells": request?.cell_count,
      "Equipment occurrences": request?.equipment_count, "Eligible equipment types": request?.eligible_type_count,
      "Registry definitions": request?.registry_definition_count,
      "Image dimensions": request?.image_width != null ? `${request.image_width} × ${request.image_height} px` : null,
      "Image detail": request?.image_detail, "Encoded image bytes": request?.encoded_image_bytes,
      "Request body bytes": request?.body_bytes, "Page context bytes": request?.page_bytes,
      "Instructions bytes": request?.instructions_bytes, "Output schema bytes": request?.schema_bytes,
      "Registry catalog bytes": request?.catalog_bytes, "Recognized equipment bytes": request?.recognition_bytes,
      "Input text SHA-256": request?.input_sha256, "Profile SHA-256": performance?.profile_sha256,
      "Prompt SHA-256": performance?.prompt_sha256, "Transport schema SHA-256": performance?.schema_sha256,
    })}
    {!performance && <p className="muted">Detailed measurements are unavailable for this attempt.</p>}
  </details>;
}
