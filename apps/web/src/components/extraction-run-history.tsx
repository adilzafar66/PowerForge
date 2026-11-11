"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { docButtonClass, MiniGrid, StatusChip } from "@/components/documents-ui";
import { EvidencePagination, PanelMessage, readableKey } from "@/components/extraction-evidence-ui";
import type { UpdateEvidenceRoute } from "@/components/extraction-evidence-panel";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { apiErrorOf } from "@/lib/api";
import {
  familyLabel,
  getHistory,
  getRawTables,
  getRunDetail,
  getRunSources,
  runHistoryAction,
  runState,
  type DocumentScope,
  type HistoryFamily,
  type HistoryRun,
  type RawTable,
  type RunPair,
  type RunStatus,
  type StageTrace,
} from "@/lib/extraction";
import { formatDateShort } from "@/lib/projects";
import { isRunning, jobInterval } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

const chipTone = {
  PENDING: "yellow",
  RUNNING: "blue",
  COMPLETED: "green",
  PARTIALLY_COMPLETED: "yellow",
  FAILED: "red",
  CANCELLED: "gray",
} as const satisfies Record<RunStatus, string>;

const card = "rounded-[var(--pf-radius-control)] border border-border bg-panel p-3";

export function ExtractionRunHistory({
  scope, activeFamily, runId, pair, update, canMutate, currentProcessingId, onReextract,
}: {
  scope: DocumentScope;
  activeFamily: HistoryFamily;
  runId: string | null;
  pair: RunPair;
  update: UpdateEvidenceRoute;
  canMutate: boolean;
  currentProcessingId?: string | null;
  onReextract: (run: HistoryRun) => void;
}) {
  return (
    <div className="space-y-3.5">
      <p className="m-0 text-workspace-overline font-bold tracking-wide text-muted uppercase">Separate extraction runs</p>
      <PanelMessage>Engineering, Tables and source enrichment each have their own history. Choose a run to see its source version, attempts and coverage.</PanelMessage>
      {(["engineering", "tables", "enrichment"] as const).map((family) => (
        <HistorySection
          key={family}
          scope={scope}
          family={family}
          runId={activeFamily === family ? runId : null}
          pair={pair}
          update={update}
          canMutate={canMutate}
          currentProcessingId={currentProcessingId}
          onReextract={onReextract}
        />
      ))}
    </div>
  );
}

function HistorySection({
  scope, family, runId, pair, update, canMutate, currentProcessingId, onReextract,
}: {
  scope: DocumentScope;
  family: HistoryFamily;
  runId: string | null;
  pair: RunPair;
  update: UpdateEvidenceRoute;
  canMutate: boolean;
  currentProcessingId?: string | null;
  onReextract: (run: HistoryRun) => void;
}) {
  const [offset, setOffset] = useState(0);
  const queryKey = keys.extractionDocument(scope.projectId, scope.revisionId, scope.documentId);
  const history = useQuery({
    queryKey: [...queryKey, "history", family, offset],
    queryFn: ({ signal }) => getHistory(scope, family, offset, signal),
    retry: 1,
    refetchInterval: (query) => jobInterval(
      !!query.state.data?.items.some((run) => isRunning(run.status)),
      query.state.fetchFailureCount,
    ),
  });
  const selectedInList = history.data?.items.some((run) => run.id === runId);
  return (
    <section className="space-y-2" aria-label={`${familyLabel[family]} history`}>
      <h3 className="m-0 text-workspace-label font-bold text-ink">{familyLabel[family]}</h3>
      {runId && !selectedInList && (
        <div className={card}>
          <RunHistoryDetail key={runId} scope={scope} family={family} runId={runId} pair={pair} update={update} canMutate={canMutate} currentProcessingId={currentProcessingId} onReextract={onReextract} />
        </div>
      )}
      {history.isPending && <p role="status" className="text-workspace-caption text-muted">Loading runs…</p>}
      {history.error && <PanelMessage error retry={() => void history.refetch()}>{apiErrorOf(history.error).detail}</PanelMessage>}
      {history.data?.total === 0 && <PanelMessage>No {familyLabel[family].toLowerCase()} runs.</PanelMessage>}
      {history.data?.items.map((run) => (
        <div key={run.id} className={card}>
          <button
            type="button"
            aria-expanded={runId === run.id}
            className="flex w-full flex-wrap items-center justify-between gap-1.5 text-left text-workspace-label font-semibold text-ink hover:text-accent"
            onClick={() => update({ historyFamily: family, historyRun: runId === run.id ? null : run.id })}
          >
            <span>Run {run.id.slice(0, 8)}</span>
            <StatusChip tone={chipTone[run.status]}>{runState(run).label}</StatusChip>
          </button>
          <p className="m-0 mt-1 text-workspace-caption text-muted">
            {formatDateShort(run.created_at)} · {run.selected_pages.length} {run.selected_pages.length === 1 ? "page" : "pages"}
          </p>
          {runId === run.id && (
            <RunHistoryDetail key={run.id} scope={scope} family={family} runId={run.id} pair={pair} update={update} canMutate={canMutate} currentProcessingId={currentProcessingId} onReextract={onReextract} />
          )}
        </div>
      ))}
      {history.data && <EvidencePagination total={history.data.total} size={10} start={offset} onChange={setOffset} />}
    </section>
  );
}

function RunHistoryDetail({
  scope, family, runId, pair, update, canMutate, currentProcessingId, onReextract,
}: {
  scope: DocumentScope;
  family: HistoryFamily;
  runId: string;
  pair: RunPair;
  update: UpdateEvidenceRoute;
  canMutate: boolean;
  currentProcessingId?: string | null;
  onReextract: (run: HistoryRun) => void;
}) {
  const client = useQueryClient();
  const queryKey = keys.extractionDocument(scope.projectId, scope.revisionId, scope.documentId);
  const [action, setAction] = useState<"retry" | "cancel" | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: [...queryKey, "run", family, runId],
    queryFn: ({ signal }) => getRunDetail(scope, family, runId, signal),
    retry: 1,
    refetchInterval: (query) => jobInterval(isRunning(query.state.data?.run.status), query.state.fetchFailureCount),
  });
  const run = detail.data?.run;
  const sources = useQuery({
    queryKey: [...queryKey, "bindings", runId],
    queryFn: ({ signal }) => getRunSources(scope, runId, signal),
    enabled: family !== "enrichment" && !!run,
    retry: 1,
  });

  async function confirm() {
    if (!action || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      await runHistoryAction(scope, family, runId, action);
      setAction(null);
      await Promise.all([
        client.invalidateQueries({ queryKey }),
        client.invalidateQueries({ queryKey: [...keys.extraction(scope.projectId, scope.revisionId), "status"] }),
      ]);
    } catch (error) {
      setActionError(apiErrorOf(error).detail);
      setAction(null);
    } finally {
      setBusy(false);
    }
  }

  const data = detail.data;
  const usage = data?.execution;
  const hasEffective = !!data?.coverage?.completed_required_units;
  const showTableOutput = family === "tables" && hasEffective;
  const cancelled = action === "cancel";
  const boundSources = sources.data?.items ?? [];
  return (
    <div className="mt-3 space-y-3 border-t border-border pt-3">
      {detail.isPending && <p role="status" className="text-workspace-caption text-muted">Loading run detail…</p>}
      {detail.error && <PanelMessage error retry={() => void detail.refetch()}>{apiErrorOf(detail.error).detail}</PanelMessage>}
      {data && run && (
        <>
          <MiniGrid items={[
            ["Status", runState(run).label],
            ["Profile", usage?.profile_key ?? run.profile_key ?? run.profile_version ?? "Unavailable"],
            ["Model", run.model ?? (family === "enrichment" ? "Local preparation" : "Unavailable")],
            ["Source version", run.processing_run_id],
            ["Selected pages", run.selected_pages.join(", ")],
            ["Coverage", data.coverage ? `${data.coverage.completed_required_units} of ${data.coverage.required_units} required units` : `${run.pages_processed} of ${run.selected_pages.length} pages`],
            ["Attempts", data.attempts.length],
            ...(run.error_code ? [["Run error", readableKey(run.error_code)] as [string, string]] : []),
          ]} />
          {usage && <MiniGrid items={[
            ["Call admissions", `${usage.calls_admitted} of ${usage.call_budget}`],
            ["Provider calls started", usage.provider_calls_started],
            ["Unreported outcomes", usage.unreported_provider_calls],
            ["Tokens", usage.input_tokens == null || usage.output_tokens == null ? "Unavailable" : `${usage.input_tokens} in · ${usage.output_tokens} out`],
            ["Estimated cost", usage.estimated_cost_usd == null ? "Unknown" : `USD ${usage.estimated_cost_usd}`],
          ]} />}
          {family === "enrichment" && (
            <p className="m-0 text-workspace-caption text-muted">Confirmed OCR invocations · {data.confirmed_ocr_invocations ?? "Unavailable"}</p>
          )}
          <details className="text-workspace-caption text-muted">
            <summary className="cursor-pointer font-semibold text-accent">Attempts and source bindings</summary>
            <div className="mt-2 max-h-64 space-y-2 overflow-auto break-words">
              {data.attempts.map((attempt) => (
                <div key={attempt.id} className="space-y-1">
                  <p className="m-0">{readableKey(attempt.unit_key)}{attempt.attempt_number ? ` · Attempt ${attempt.attempt_number}` : ""} · {readableKey(attempt.status)}{attempt.error_code ? ` · ${readableKey(attempt.error_code)}` : ""}</p>
                  {attempt.stage_trace && <AttemptDiagnostics trace={attempt.stage_trace} />}
                </div>
              ))}
              {sources.error && <PanelMessage error retry={() => void sources.refetch()}>Exact source bindings could not load.</PanelMessage>}
              {boundSources.map((item) => (
                <MiniGrid key={item.page_number} items={[
                  ["Page", item.page_number],
                  ["Prepared result", item.prepared_result_id],
                  ["Preparation run", item.preparation_producer_run_id],
                  ["Layout result", item.spatial_result_id],
                  ["Layout run", item.layout_producer_run_id],
                ]} />
              ))}
              {data.results?.map((item) => (
                <MiniGrid key={item.id} items={[
                  ["Prepared page", item.page_number],
                  ["Result", item.id],
                  [item.reused ? "Reused from run" : "Produced by run", item.producer_run_id],
                ]} />
              ))}
              {data.spatial_results?.map((item) => (
                <MiniGrid key={item.id} items={[
                  ["Layout page", item.page_number], ["Result", item.id], ["Prepared result", item.prepared_result_id],
                  ...(item.unresolved_reasons?.length
                    ? [["Layout assessment", item.unresolved_reasons.map(readableKey).join(", ")] as [string, string]]
                    : []),
                ]} />
              ))}
              {!boundSources.length && run.input_artifact_ids?.length ? <MiniGrid items={[["Source artifacts", run.input_artifact_ids.join(", ")]]} /> : null}
            </div>
          </details>
          <div className="flex flex-wrap gap-1.5">
            {family !== "enrichment" && (hasEffective || run.status === "COMPLETED") && (
              <button type="button" className={docButtonClass("tiny")} onClick={() => {
                const chosen = { ...pair, [family]: runId };
                update({
                  evidencePinned: "1", historicalPair: "1",
                  engineeringRun: chosen.engineering, tablesRun: chosen.tables,
                  evidenceTab: null, groupRun: null, sourceGroup: null, groupReturnPage: null,
                  candidate: null, groupOffset: null, candidateOffset: null,
                });
              }}>Browse candidates</button>
            )}
            {canMutate && family !== "enrichment" && !isRunning(run.status)
              && currentProcessingId === run.processing_run_id && (
                <button type="button" className={docButtonClass("tiny")} onClick={() => onReextract(run)}>Re-extract</button>
              )}
            {canMutate && data.can_retry && (
              <button type="button" className={docButtonClass("tiny")} onClick={() => setAction("retry")}>Retry unsuccessful units</button>
            )}
            {canMutate && data.can_cancel && (
              <button type="button" className={docButtonClass("tiny")} onClick={() => setAction("cancel")}>Cancel run</button>
            )}
          </div>
          {actionError && <PanelMessage error>{actionError}</PanelMessage>}
          {showTableOutput && <RawTableOutput scope={scope} run={run} />}
        </>
      )}
      {action && (
        <ConfirmDialog
          title={cancelled ? "Cancel this run?" : "Retry unsuccessful units?"}
          message={cancelled
            ? "Completed outputs are kept. Calls already sent to a provider may still incur charges."
            : family === "enrichment"
              ? "The same pinned source will be used to retry unsuccessful local preparation units."
              : "OpenAI may process the same pinned source again for unsuccessful units. Prior call outcomes and additional cost may be unknown. Completed units are kept."}
          confirmLabel={busy ? "Submitting…" : cancelled ? "Cancel run" : "Retry units"}
          danger={cancelled}
          onConfirm={() => void confirm()}
          onCancel={() => { if (!busy) setAction(null); }}
        />
      )}
    </div>
  );
}

function AttemptDiagnostics({ trace }: { trace: StageTrace }) {
  const failure = trace.provider_detail ?? trace.reason;
  return (
    <details className="pl-2">
      <summary className="cursor-pointer text-accent">
        {failure
          ? `${readableKey(trace.phase)} · ${readableKey(failure)}`
          : `${trace.counts.PUBLISHED_CANDIDATES ?? 0} candidates · ${trace.counts.PUBLISHED_TABLES ?? 0} tables published`}
      </summary>
      <div className="mt-1 space-y-1">
        <p className="m-0">Provider · {readableKey(trace.provider_outcome)}</p>
        {trace.source && <p className="m-0">
          Input · {trace.source.native_readings} native readings · {trace.source.ocr_readings} OCR readings
          {trace.source.image_present ? " · Page image" : ""} · {trace.source.layout_tables} layout tables
          · {trace.source.withheld_readings} withheld readings · {trace.source.conflict_pairs} conflicting pairs
        </p>}
        {trace.returned && <p className="m-0">
          Returned · {Object.entries(trace.returned).map(([kind, count]) => `${readableKey(kind)} ${count}`).join(" · ")}
        </p>}
        {Object.keys(trace.counts).length > 0 && <p className="m-0">
          {Object.entries(trace.counts).map(([reason, count]) => `${readableKey(reason)} ${count}`).join(" · ")}
        </p>}
        {Object.keys(trace.reasons).length > 0 && <ul className="m-0 list-disc pl-4">
          {Object.entries(trace.reasons).map(([reason, count]) => <li key={reason}>{readableKey(reason)} · {count}</li>)}
        </ul>}
        {trace.issues.length > 0 && <ul className="m-0 list-disc pl-4">
          {trace.issues.map((issue, index) => <li key={index}>
            {readableKey(issue.reason)}{issue.path ? ` · ${issue.path}` : ""}
          </li>)}
        </ul>}
      </div>
    </details>
  );
}

function RawTableOutput({ scope, run }: { scope: DocumentScope; run: HistoryRun }) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const tables = useQuery({
    queryKey: [...keys.extractionDocument(scope.projectId, scope.revisionId, scope.documentId), "raw-tables", run.id, offset],
    queryFn: ({ signal }) => getRawTables(scope, run.id, offset, signal),
    enabled: open,
    retry: 1,
  });
  return (
    <details className="border-t border-border pt-2 text-workspace-caption" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer font-semibold text-accent">Inspect raw table output (technical)</summary>
      {open && (
        <div className="mt-2 space-y-2">
          <p className="m-0 text-muted">These are reconstructed source cells. Printed text and relationships require independent verification.</p>
          {tables.isPending && <p role="status" className="m-0 text-muted">Loading raw table output…</p>}
          {tables.error && <PanelMessage error retry={() => void tables.refetch()}>{apiErrorOf(tables.error).detail}</PanelMessage>}
          {tables.data?.total === 0 && <PanelMessage>No committed table structure for this run.</PanelMessage>}
          {tables.data?.items.map((table) => <TableCells key={table.id} table={table} />)}
          {tables.data && <EvidencePagination total={tables.data.total} size={1} start={offset} onChange={setOffset} />}
        </div>
      )}
    </details>
  );
}

type Layout = {
  title: string | null;
  metadata: { structure_basis?: string };
  cells: { id: string; text: string; row: number; column: number; row_span: number; column_span: number; is_header: boolean }[];
};

function TableCells({ table }: { table: RawTable }) {
  const layout = table.layout as Layout;
  const [offset, setOffset] = useState(0);
  const cells = layout.cells.slice(offset, offset + 20);
  return (
    <div className={cn(card, "space-y-2")}>
      <p className="m-0 break-words font-semibold text-ink">{layout.title || readableKey(table.table_kind)}</p>
      {layout.metadata.structure_basis && <p className="m-0 text-muted">Structure · {readableKey(layout.metadata.structure_basis)}</p>}
      {layout.cells.length === 0 ? <p className="m-0 text-muted">No supported cells were recorded.</p> : (
        <table className="w-full table-fixed border-collapse text-left">
          <thead><tr className="border-b border-border text-muted"><th scope="col" className="w-[40%] py-1 pr-1">Source cell</th><th scope="col" className="py-1">Recognized text</th></tr></thead>
          <tbody>{cells.map((cell) => (
            <tr key={cell.id} className="border-b border-border last:border-0">
              <th scope="row" className="py-1 pr-1 align-top font-medium text-muted">
                {cell.is_header ? "Header · " : ""}R{cell.row + 1} C{cell.column + 1}
                {(cell.row_span > 1 || cell.column_span > 1) && ` · ${cell.row_span}×${cell.column_span}`}
              </th>
              <td className="py-1 break-words whitespace-pre-wrap text-ink">{cell.text || "—"}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <EvidencePagination total={layout.cells.length} size={20} start={offset} onChange={setOffset} />
    </div>
  );
}
