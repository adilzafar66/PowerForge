"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { docButtonClass, MiniGrid, StatusChip } from "@/components/documents-ui";
import { EvidencePagination, PanelMessage, readableKey } from "@/components/extraction-evidence-ui";
import type { UpdateEvidenceRoute } from "@/components/extraction-evidence-panel";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { apiErrorOf } from "@/lib/api";
import { getHistory, getRunDetail, getRunSources, getSourceLayout, runHistoryAction, runState, type DocumentScope, type HistoryRun, type RunAttempt, type SourceBinding } from "@/lib/extraction";
import { pageRanges } from "@/lib/extraction-operations";
import { formatDateShort } from "@/lib/projects";
import { isRunning, jobInterval } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";

const label = (stage: string) => stage === "EQUIPMENT_RECOGNITION" ? "Equipment recognition"
  : stage === "ATTRIBUTE_EXTRACTION" ? "Attribute extraction" : readableKey(stage);

export function ExtractionRunHistory({ scope, runId, update, canMutate, currentProcessingId, onReextract }: {
  scope: DocumentScope; runId: string | null; update: UpdateEvidenceRoute;
  canMutate: boolean; currentProcessingId?: string | null; onReextract: (run: HistoryRun) => void;
}) {
  const [cursor, setCursor] = useState<string | null>(null);
  const key = keys.extractionDocument(scope.projectId, scope.revisionId, scope.documentId);
  const query = useQuery({
    queryKey: [...key, "history", cursor],
    queryFn: ({ signal }) => getHistory(scope, cursor, signal),
    refetchInterval: ({ state }) => jobInterval(!!state.data?.items.some((run) => isRunning(run.status)), state.fetchFailureCount),
  });
  const select = (id: string | null) => update({ extractionRun: id, equipmentGroup: null, candidate: null, fragment: null, groupCursor: null, memberCursor: null, returnPage: null });
  return (
    <div className="space-y-3">
      <h3 className="text-workspace-label font-bold text-ink">Run history</h3>
      {runId && <RunHistoryDetail key={runId} scope={scope} runId={runId} update={update}
        canMutate={canMutate} currentProcessingId={currentProcessingId} onReextract={onReextract} />}
      {query.isPending && <p role="status">Loading run history…</p>}
      {query.error && <PanelMessage error retry={() => void query.refetch()}>{apiErrorOf(query.error).detail}</PanelMessage>}
      {query.data?.items.length === 0 && <PanelMessage>No extraction runs for this document.</PanelMessage>}
      {query.data?.items.map((run) => (
        <button key={run.id} type="button" aria-pressed={run.id === runId} onClick={() => select(run.id === runId ? null : run.id)}
          className="flex w-full items-center justify-between gap-2 rounded-md border border-border bg-panel p-3 text-left text-workspace-caption hover:bg-soft focus-visible:ring-2 focus-visible:ring-ring">
          <span><strong>{formatDateShort(run.created_at)}</strong> · Pages {pageRanges(run.selected_pages)}</span>
          <span>{runState(run).label}</span>
        </button>
      ))}
      {query.data && <EvidencePagination page={query.data} onChange={setCursor} />}
    </div>
  );
}

function RunHistoryDetail({ scope, runId, update, canMutate, currentProcessingId, onReextract }: {
  scope: DocumentScope; runId: string; update: UpdateEvidenceRoute;
  canMutate: boolean; currentProcessingId?: string | null; onReextract: (run: HistoryRun) => void;
}) {
  const client = useQueryClient();
  const key = keys.extractionDocument(scope.projectId, scope.revisionId, scope.documentId);
  const detail = useQuery({
    queryKey: [...key, "run", runId],
    queryFn: ({ signal }) => getRunDetail(scope, runId, signal),
    refetchInterval: ({ state }) => jobInterval(isRunning(state.data?.run.status), state.fetchFailureCount),
  });
  const sources = useQuery({
    queryKey: [...key, "sources", runId], queryFn: ({ signal }) => getRunSources(scope, runId, signal),
    enabled: detail.isSuccess,
  });
  const [action, setAction] = useState<"retry" | "cancel" | null>(null);
  const [acknowledge, setAcknowledge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const data = detail.data;
  if (!data) return detail.error
    ? <PanelMessage error retry={() => void detail.refetch()}>{apiErrorOf(detail.error).detail}</PanelMessage>
    : <p role="status">Loading run details…</p>;
  const { run } = data;
  const unknown = data.attempts.some((attempt) => attempt.retryable && attempt.error_code === "EXTRACTION_PROVIDER_OUTCOME_UNKNOWN");

  async function confirm() {
    if (!action || busy || (action === "retry" && unknown && !acknowledge)) return;
    setBusy(true);
    setError(null);
    try {
      await runHistoryAction(scope, runId, action, acknowledge);
      setAction(null);
      await client.invalidateQueries({ queryKey: keys.extraction(scope.projectId, scope.revisionId) });
    } catch (failure) {
      setError(apiErrorOf(failure).detail);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-md border border-border bg-panel p-3 text-workspace-caption" aria-label="Selected extraction run">
      <div className="flex items-center justify-between"><strong>Run {run.id.slice(0, 8)}</strong><StatusChip tone="gray">{runState(run).label}</StatusChip></div>
      <MiniGrid items={[
        ["Model", run.model], ["Profile", run.profile_version], ["Pages", pageRanges(run.selected_pages)],
        ["Pages completed", String(run.pages_processed)],
        ["Stages completed", `${data.coverage.completed_required_units} / ${data.coverage.required_units}`],
        ["Provider calls", data.execution ? `${data.execution.provider_calls_started} started / ${data.execution.call_budget} budgeted` : "Unavailable"],
      ]} />
      {run.error_code && <p className="text-warning">{readableKey(run.error_code)}</p>}
      {sources.error && <PanelMessage error retry={() => void sources.refetch()}>Pinned source bindings are unavailable.</PanelMessage>}
      {!!sources.data?.items.length && <details>
        <summary className="cursor-pointer font-semibold">Pinned source bindings</summary>
        <ul className="space-y-1 break-all">
          {sources.data.items.map((item) => <li key={item.page_id}>
            Page {item.page_number} · Preparation {item.prepared_result_id} · Layout {item.spatial_result_id}
            <span className="block text-muted">Preparation SHA-256 {item.prepared_manifest_hash} · Layout SHA-256 {item.spatial_manifest_hash}</span>
            <SourceLayoutDetails scope={scope} binding={item} />
          </li>)}
        </ul>
      </details>}
      <ol className="list-none space-y-2 p-0" aria-label="Extraction attempts">
        {data.attempts.map((attempt) => <Attempt key={attempt.id} attempt={attempt} />)}
      </ol>
      <div className="flex flex-wrap gap-2">
        {data.can_browse_candidates && <button type="button" className={docButtonClass("tiny")}
          onClick={() => update({ evidenceTab: null, extractionRun: run.id, equipmentGroup: null, candidate: null, fragment: null, groupCursor: null, memberCursor: null })}>Browse candidates</button>}
        {canMutate && data.can_retry && <button type="button" className={docButtonClass("tiny")}
          onClick={() => { setAcknowledge(false); setAction("retry"); }}>Retry failed stages</button>}
        {canMutate && data.can_cancel && <button type="button" className={docButtonClass("tiny")}
          onClick={() => setAction("cancel")}>Cancel run</button>}
        {canMutate && !isRunning(run.status) && currentProcessingId === run.processing_run_id && <button type="button"
          className={docButtonClass("tiny")} onClick={() => onReextract(run)}>Re-extract</button>}
      </div>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {action && <ConfirmDialog
        title={action === "retry" ? "Retry failed extraction stages?" : "Cancel extraction run?"}
        message={action === "retry" ? "Eligible failed stages can run again against this run’s pinned sources." : "Published results remain available after cancellation."}
        confirmLabel={busy ? "Submitting…" : action === "retry" ? "Retry" : "Cancel extraction"}
        danger={action === "cancel"} onConfirm={() => void confirm()} onCancel={() => { if (!busy) setAction(null); }}
        confirmDisabled={busy || (action === "retry" && unknown && !acknowledge)}
        controls={action === "retry" && unknown ? <label className="mb-4 flex gap-2">
          <input type="checkbox" checked={acknowledge} onChange={(event) => setAcknowledge(event.target.checked)} />
          I acknowledge an earlier provider outcome is unknown and another call may be charged.
        </label> : undefined}
      /> }
    </section>
  );
}

function SourceLayoutDetails({ scope, binding }: { scope: DocumentScope; binding: SourceBinding }) {
  const [open, setOpen] = useState(false);
  const layout = useQuery({
    queryKey: [...keys.extractionDocument(scope.projectId, scope.revisionId, scope.documentId), "layout", binding.spatial_result_id],
    queryFn: ({ signal }) => getSourceLayout(scope, binding, signal),
    enabled: open,
  });
  return (
    <details className="break-normal" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer">Source layout</summary>
      {open && layout.isPending && <p role="status">Loading source layout…</p>}
      {layout.error && <PanelMessage error retry={() => void layout.refetch()}>Source layout unavailable.</PanelMessage>}
      {layout.data && layout.data.manifest.tables.length === 0 && <p>No resolved tables on this page.</p>}
      {layout.data?.manifest.unresolved.map((item) => <p key={item.ref}>{readableKey(item.reason)}</p>)}
      {layout.data?.manifest.tables.map((table, index) => (
        <section key={table.ref} className="mt-2 overflow-x-auto">
          <h4>Source table {index + 1} · {table.rows} rows by {table.columns} columns</h4>
          <p>{readableKey(table.structure_basis)} · Headers {readableKey(table.header_basis).toLowerCase()}</p>
          <table className="mt-1 text-left">
            <caption className="sr-only">Source cell positions and reading counts</caption>
            <thead><tr><th scope="col">Cell</th><th scope="col">Source readings</th></tr></thead>
            <tbody>{table.cells.map((cell) => (
              <tr key={cell.ref}><td className="pr-2">Row {cell.row + 1}, column {cell.column + 1}
                {(cell.row_span > 1 || cell.column_span > 1) && ` (${cell.row_span} × ${cell.column_span})`}
              </td><td>{cell.readings.length} · {readableKey(cell.state)}</td></tr>
            ))}</tbody>
          </table>
        </section>
      ))}
    </details>
  );
}

function Attempt({ attempt }: { attempt: RunAttempt }) {
  return (
    <li className="rounded-md border border-border p-2">
      <strong>{label(attempt.stage)}</strong>
      <p>Page {pageRanges(attempt.page_numbers)} · Attempt {attempt.attempt_number} · {runState(attempt).label}</p>
      {attempt.stage_outcome === "NO_ELIGIBLE_ATTRIBUTES" && <p>Skipped: no recognized equipment eligible for attributes.</p>}
      {attempt.error_code && <p className="text-warning">{readableKey(attempt.error_code)}</p>}
      <p className="text-muted">Calls {attempt.provider_calls} · Tokens {attempt.usage ? `${attempt.usage.input_tokens} in / ${attempt.usage.output_tokens} out` : "unavailable"}
        {attempt.latency_ms != null && ` · ${attempt.latency_ms} ms`} · Cost {attempt.estimated_cost ? `${attempt.estimated_cost.amount} ${attempt.estimated_cost.currency} (${attempt.estimated_cost.pricing_version})` : "unavailable"}</p>
      {!!(attempt.validation_diagnostics.length || attempt.stage_diagnostics.length) && <details>
        <summary className="cursor-pointer">Diagnostics</summary>
        <ul className="break-words">
          {attempt.validation_diagnostics.map((issue, index) => <li key={index}>
            {readableKey(issue.category)} · {issue.error_type}{issue.path.length ? ` · ${issue.path.join(".")}` : ""}
          </li>)}
          {attempt.stage_diagnostics.map((issue, index) => <li key={index}>{readableKey(issue.code)}{issue.ref && ` · ${issue.ref}`}</li>)}
        </ul>
      </details>}
    </li>
  );
}
