"use client";

import { useQuery } from "@tanstack/react-query";

import { ExtractionOperationPanel } from "@/components/extraction-operation-panel";
import { CellStateView } from "@/components/document-list";
import { docButtonClass, InspectorSection, MiniGrid } from "@/components/documents-ui";
import { AsyncState } from "@/components/ui/async-state";
import { apiErrorOf } from "@/lib/api";
import {
  extractionCell,
  extractionHistoryHref,
  familyLabel,
  getExtractionStatuses,
  ineligibleLabel,
  runState,
  type DocumentScope,
  type HistoryFamily,
  type RegisterRun,
} from "@/lib/extraction";
import { formatDateShort } from "@/lib/projects";
import { isRunning, jobInterval } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";

export function useExtractionStatuses(projectId: string, revisionId: string, ids: string[]) {
  return useQuery({
    queryKey: keys.extractionStatus(projectId, revisionId, ids),
    queryFn: ({ signal }) => getExtractionStatuses(projectId, revisionId, ids, signal),
    enabled: ids.length > 0,
    retry: 1,
    refetchInterval: (query) => jobInterval(
      Object.values(query.state.data ?? {}).some((item) => !!item.pending_operation || [
        item.extraction.latest_attempt, item.enrichment,
      ].some((run) => isRunning(run?.status))),
      query.state.fetchFailureCount,
    ),
  });
}

export function DocumentExtractionPanel({
  scope,
  canMutate,
  onNavigate,
  onStart,
  operationId,
}: {
  scope: DocumentScope;
  canMutate: boolean;
  onNavigate: (href: string) => void;
  onStart: () => void;
  operationId?: string | null;
}) {
  const status = useExtractionStatuses(scope.projectId, scope.revisionId, [scope.documentId]);
  const data = status.data?.[scope.documentId];
  const runs: [HistoryFamily, RegisterRun | null | undefined][] = [
    ["engineering", data?.extraction.latest_attempt],
    ["enrichment", data?.enrichment],
  ];
  const recent = runs.flatMap(([family, run]) => run ? [{ family, run }] : [])
    .sort((a, b) => b.run.created_at.localeCompare(a.run.created_at));
  return (
    <InspectorSection title="AI Extraction">
      <AsyncState pending={status.isPending} error={!data ? status.error : null} retry={status.refetch} />
      {data && (
        <div className="space-y-3">
          {status.isRefetchError && (
            <p role="alert" className="text-workspace-caption text-danger">
              Extraction status could not refresh. {apiErrorOf(status.error).detail}
            </p>
          )}
          <CellStateView state={extractionCell(data)} />
          <MiniGrid items={runs.map(([family, run]) => [
            familyLabel[family],
            run && family === "enrichment"
              ? `${run.profile_key === "source-layout-v1" ? "Layout" : "Preparation"} · ${runState(run).label}`
              : run ? runState(run).label : family === "enrichment" ? "No recorded preparation" : "Not extracted",
          ])} />
          <p className="m-0 text-workspace-caption text-muted">
            {data.ineligible_reason ? ineligibleLabel[data.ineligible_reason] : "Source preparation is scheduled with extraction."}
          </p>
          {data.ineligible_reason !== "REMOVED" && (
            <div className="flex flex-wrap gap-2">
              {canMutate && !data.ineligible_reason && (
                <button type="button" className={docButtonClass("primary")} onClick={onStart}>
                  Start extraction
                </button>
              )}
              {(data.extraction.effective_result || recent.length > 0) && (
                <button type="button" className={docButtonClass("tiny")} onClick={() => onNavigate(
                  extractionHistoryHref(scope, data.extraction.effective_result ? "engineering" : undefined, data.extraction.effective_result?.id),
                )}>View run history</button>
              )}
            </div>
          )}
          {data.ineligible_reason !== "REMOVED" && (
            <ExtractionOperationPanel scope={scope} linkedId={operationId} onNavigate={onNavigate} />
          )}
          {recent.length ? (
            <div className="rounded-[var(--pf-radius-control)] border border-border bg-soft/60 p-3">
              <h3 className="m-0 text-workspace-overline font-bold uppercase tracking-wide text-muted">Recent runs</h3>
              <ul className="m-0 mt-2 list-none space-y-1.5 p-0 text-workspace-caption">
                {recent.map(({ family, run }) => (
                  <li key={run.id} className="flex justify-between gap-2">
                    <button type="button" className="text-left text-accent hover:underline" onClick={() => onNavigate(extractionHistoryHref(scope, family, run.id))}>
                      {familyLabel[family]} · {formatDateShort(run.created_at)}
                    </button>
                    <span className="font-semibold">{runState(run).label}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="m-0 text-workspace-caption text-muted">No run history for this document.</p>
          )}
        </div>
      )}
    </InspectorSection>
  );
}
