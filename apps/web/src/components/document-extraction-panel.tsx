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
  getExtractionStatuses,
  ineligibleLabel,
  runState,
  type DocumentScope,
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
  const run = data?.extraction.latest_attempt;
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
          <MiniGrid items={[
            ["AI Engineering Extraction", runState(run).label],
            ["Source preparation", data.enrichment ? runState(data.enrichment).label : "No recorded preparation"],
          ]} />
          <p className="m-0 text-workspace-caption text-muted">
            {data.ineligible_reason ? ineligibleLabel[data.ineligible_reason] : "Source preparation is scheduled with extraction."}
          </p>
          {data.ineligible_reason !== "REMOVED" && (
            <div className="flex flex-wrap gap-2">
              {canMutate && !data.ineligible_reason && (
                <button type="button" className={docButtonClass("primary")} onClick={onStart}>
                  AI Engineering Extraction
                </button>
              )}
              {(data.extraction.effective_result || run) && (
                <button type="button" className={docButtonClass("tiny")} onClick={() => onNavigate(
                  extractionHistoryHref(scope, data.extraction.effective_result?.id ?? run?.id),
                )}>View run history</button>
              )}
            </div>
          )}
          {data.ineligible_reason !== "REMOVED" && (
            <ExtractionOperationPanel scope={scope} linkedId={operationId} onNavigate={onNavigate} />
          )}
          {run && <p className="text-workspace-caption text-muted">Latest run · {formatDateShort(run.created_at)}</p>}
        </div>
      )}
    </InspectorSection>
  );
}
