"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";

import { docButtonClass, StatusChip, type ChipTone } from "@/components/documents-ui";
import { AsyncState } from "@/components/ui/async-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { apiErrorOf } from "@/lib/api";
import { extractionHistoryHref, families, familyLabel, type DocumentScope } from "@/lib/extraction";
import {
  cancelExtractionOperation,
  extractionOperationHref,
  getExtractionOperation,
  pageRanges,
  recentExtractionOperations,
  retryExtractionOperation,
  type OperationChild,
  type OperationDetail,
  type OperationStatus,
  type OperationStep,
  type RevisionScope,
} from "@/lib/extraction-operations";
import { formatDateShort } from "@/lib/projects";
import { jobInterval } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import { documentViewerHref } from "@/lib/workspace-navigation";

const statuses: Record<OperationStatus | OperationChild["status"], [string, ChipTone]> = {
  QUEUED: ["Queued", "gray"],
  PENDING: ["Queued", "gray"],
  RUNNING: ["Running", "blue"],
  COMPLETED: ["Completed", "green"],
  PARTIAL: ["Partial", "yellow"],
  PARTIALLY_COMPLETED: ["Partial", "yellow"],
  BLOCKED: ["Blocked", "yellow"],
  FAILED: ["Failed", "red"],
  CANCELLED: ["Cancelled", "gray"],
  REUSED: ["Reused", "green"],
  WAITING: ["Waiting", "gray"],
};

const blockedReasons: Record<string, string> = {
  SOURCE_UNAVAILABLE: "This source is unavailable in the revision.",
  REVISION_READ_ONLY: "The revision is read-only.",
  PREPARATION_UNSUCCESSFUL: "The source preparation or layout step was unsuccessful.",
  PROCESSING_DISABLED: "Local preparation or OpenAI extraction is disabled.",
  PROVIDER_UNAVAILABLE: "OpenAI is unavailable on the worker.",
  PROFILE_CHANGED: "The execution profile changed after confirmation. Review a new operation.",
  SOURCE_ARTIFACT_UNAVAILABLE: "A pinned source artifact is missing or differs from its recorded identity.",
  EXACT_SOURCE_REQUIRED: "The exact reviewed source or layout could not be verified.",
};

function useOperation(scope: RevisionScope, id: string | null) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: keys.extractionOperation(scope.projectId, scope.revisionId, id ?? ""),
    queryFn: ({ signal }) => getExtractionOperation(scope, id!, signal),
    enabled: !!id,
    refetchInterval: ({ state }) => jobInterval(
      state.data?.status === "QUEUED" || state.data?.status === "RUNNING",
      state.fetchFailureCount,
    ),
  });
  const progress = query.data && JSON.stringify(query.data.items.map((item) => [
    item.revision_document_id, item.status, item.layout.status,
    ...families.map((family) => item.profiles[family]?.status ?? null),
  ]));
  useEffect(() => {
    if (progress) void client.invalidateQueries({
      queryKey: [...keys.extraction(scope.projectId, scope.revisionId), "status"],
    });
  }, [client, progress, scope.projectId, scope.revisionId]);
  return query;
}

export function ExtractionOperationToast({
  scope, operation, onView, onDismiss,
}: {
  scope: RevisionScope;
  operation: { id: string; documentId: string };
  onView: (href: string) => void;
  onDismiss: () => void;
}) {
  const query = useOperation(scope, operation.id);
  const status = query.data?.status;
  return (
    <div role="status" className="fixed right-4 bottom-4 z-[55] flex max-w-[calc(100%-32px)] items-start gap-3 rounded-[var(--pf-radius-lg)] border border-border bg-panel p-3 shadow-lg sm:right-6 sm:bottom-6">
      <div className="min-w-0">
        <p className="m-0 text-workspace-label font-semibold text-ink">
          Extraction operation {status ? statuses[status][0].toLowerCase() : "accepted"}
        </p>
        <Link
          href={extractionOperationHref(scope, operation.documentId, operation.id)}
          className="text-workspace-caption font-semibold text-accent hover:underline"
          onClick={(event) => {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            onView(event.currentTarget.href);
          }}
        >View operation</Link>
      </div>
      <button type="button" aria-label="Dismiss extraction notification" className={docButtonClass("ghost", "tiny")} onClick={onDismiss}>
        <X aria-hidden />
      </button>
    </div>
  );
}

type Action = { kind: "cancel" } | {
  kind: "retry"; documentId: string; step: OperationStep; child?: OperationChild;
};

export function ExtractionOperationPanel({
  scope, linkedId, onNavigate,
}: {
  scope: DocumentScope;
  linkedId?: string | null;
  onNavigate: (href: string) => void;
}) {
  const client = useQueryClient();
  const recent = useQuery({
    queryKey: keys.extractionOperationsForDocument(scope.projectId, scope.revisionId, scope.documentId),
    queryFn: ({ signal }) => recentExtractionOperations(scope, scope.documentId, signal),
    retry: 1,
  });
  const [selected, setSelected] = useState<string | null>(linkedId ?? null);
  const [open, setOpen] = useState(!!linkedId);
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (linkedId) {
      setSelected(linkedId);
      setOpen(true);
    }
  }, [linkedId]);
  const latest = recent.data?.items[0]?.id;
  const id = selected ?? latest;
  const query = useOperation(scope, open ? id ?? null : null);
  const result = query.data;
  const currentDocument = result?.items.some((item) => item.revision_document_id === scope.documentId);
  const heading = useRef<HTMLHeadingElement>(null);
  const focusedOperation = open && currentDocument ? result?.id : null;
  useEffect(() => {
    if (!focusedOperation) return;
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView?.({ block: "start" });
  }, [focusedOperation]);
  const pendingCancel = action?.kind === "cancel";

  async function applyAction() {
    if (!action || !id || busy) return;
    setError(null);
    setBusy(true);
    try {
      const updated = action.kind === "cancel" ? await cancelExtractionOperation(scope, id)
        : await retryExtractionOperation(
          scope, id, action.documentId, action.step,
          action.child?.attempts ?? 0, action.child?.unknown_provider_outcome ?? false,
        );
      client.setQueryData(keys.extractionOperation(scope.projectId, scope.revisionId, id), updated);
      for (const item of updated.items) {
        void client.invalidateQueries({
          queryKey: keys.extractionDocument(scope.projectId, scope.revisionId, item.revision_document_id),
        });
      }
      setAction(null);
    } catch (failure) {
      setError(apiErrorOf(failure).detail);
      setAction(null);
      void query.refetch();
    } finally {
      setBusy(false);
    }
  }

  if (!id && !recent.error) return null;
  return (
    <div className="space-y-2">
      {recent.error && <AsyncState pending={false} error={recent.error} retry={recent.refetch} />}
      {id && (
        <>
          <button type="button" className={docButtonClass("tiny")} aria-expanded={open} onClick={() => setOpen((value) => !value)}>
            {open ? "Hide operation" : "View operation"}
          </button>
          {open && (
            <div className="space-y-3 rounded-[var(--pf-radius-control)] border border-border bg-soft/50 p-3">
              {(recent.data?.items.length ?? 0) > 1 && (
                <label className="block text-workspace-caption text-muted">
                  Saved operation
                  <select
                    className="mt-1 block w-full rounded-md border border-border bg-panel px-2 py-1 text-ink"
                    value={id} onChange={(event) => { setSelected(event.target.value); setError(null); }}
                  >
                    {!recent.data?.items.some((item) => item.id === id) && <option value={id}>{id.slice(0, 8)}</option>}
                    {recent.data?.items.map((item) => (
                      <option value={item.id} key={item.id}>{formatDateShort(item.created_at)} · {item.id.slice(0, 8)}</option>
                    ))}
                  </select>
                </label>
              )}
              <AsyncState pending={query.isPending} error={query.error} retry={query.refetch} />
              {result && !currentDocument && <p role="alert" className="m-0 text-workspace-caption text-danger">This operation is unavailable for the selected document.</p>}
              {result && currentDocument && (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 ref={heading} tabIndex={-1} className="m-0 text-workspace-label font-bold text-ink outline-none">
                      Extraction operation
                    </h3>
                    <OperationBadge status={result.status} />
                  </div>
                  <p className="m-0 break-all text-workspace-caption text-muted">Operation ID · {result.id}</p>
                  {result.cancel_requested && <p className="m-0 text-workspace-caption text-muted">Scheduling stopped. Already admitted runs may finish.</p>}
                  {result.unavailable_sources > 0 && <p className="m-0 text-workspace-caption text-muted">{result.unavailable_sources} sources are no longer available in this revision.</p>}
                  {result.items.map((item) => (
                    <OperationItem key={item.revision_document_id} scope={scope} item={item} onAction={setAction} onNavigate={onNavigate} />
                  ))}
                  {result.can_cancel && <button type="button" className={docButtonClass("tiny")} onClick={() => setAction({ kind: "cancel" })}>Cancel operation</button>}
                </>
              )}
              {error && <p role="alert" className="m-0 text-workspace-caption text-danger">{error}</p>}
            </div>
          )}
        </>
      )}
      {action && (
        <ConfirmDialog
          title={pendingCancel ? "Cancel this operation?" : "Retry this step?"}
          message={pendingCancel
            ? "Future steps will stop. Runs already admitted can continue and incur charges. Completed results are kept."
            : action.child?.unknown_provider_outcome
              ? "A previous OpenAI call may have been billed and its outcome is unknown. Another call can incur charges. Successful work is kept."
              : action.step === "layout" || action.step === "resume"
                ? "Successful source work is kept. The approved OpenAI runs can start once every required page is ready."
                : "Only eligible unsuccessful work is retried. OpenAI may process the same source again and incur charges."}
          confirmLabel={busy ? "Submitting…" : pendingCancel ? "Stop scheduling" : "Retry"}
          danger={pendingCancel}
          onConfirm={() => void applyAction()}
          onCancel={() => { if (!busy) setAction(null); }}
        />
      )}
    </div>
  );
}

function OperationBadge({ status }: { status: keyof typeof statuses }) {
  const [label, tone] = statuses[status];
  return <StatusChip tone={tone}>{label}</StatusChip>;
}

function OperationItem({
  scope, item, onAction, onNavigate,
}: {
  scope: DocumentScope;
  item: OperationDetail["items"][number];
  onAction: (action: Action) => void;
  onNavigate: (href: string) => void;
}) {
  const itemScope = { ...scope, documentId: item.revision_document_id };
  const entries = Object.entries(item.profiles) as [typeof families[number], OperationChild][];
  const resultRuns = entries.filter(([, child]) => child.run_id && ["COMPLETED", "PARTIALLY_COMPLETED"].includes(child.status));

  function viewEvidence() {
    const query = new URLSearchParams({ evidencePinned: "1", historicalPair: "1" });
    for (const [family, child] of resultRuns) query.set(`${family}Run`, child.run_id!);
    onNavigate(`${documentViewerHref(scope.projectId, scope.revisionId, item.revision_document_id, { mode: "evidence" })}&${query}`);
  }

  return (
    <div className="space-y-2 rounded-md border border-border bg-panel p-2.5 text-workspace-caption text-muted">
      <div className="flex flex-wrap items-center justify-between gap-1.5">
        <strong className="break-words text-ink">{item.filename}</strong>
        <OperationBadge status={item.status} />
      </div>
      <p className="m-0">Pages {pageRanges(item.pages)}{item.force_ocr_pages.length ? ` · Force OCR ${pageRanges(item.force_ocr_pages)}` : ""}</p>
      {item.blocked_reason && <p className="m-0 text-warning">{blockedReasons[item.blocked_reason] ?? item.blocked_reason}</p>}
      <ul className="m-0 list-none space-y-1.5 p-0">
        {([["layout", item.layout], ...entries] as [Exclude<OperationStep, "resume">, OperationChild][]).map(([step, child]) => (
          <li key={step}>
            <div className="flex flex-wrap items-center justify-between gap-1.5">
              <span>{step === "layout" ? "Preparation and layout" : familyLabel[step]} · {statuses[child.status][0]}</span>
              <span className="flex gap-1.5">
                {child.run_id && (
                  <button type="button" className="font-semibold text-accent hover:underline" onClick={() => onNavigate(extractionHistoryHref(itemScope, step === "layout" ? "enrichment" : step, child.run_id!))}>Run details</button>
                )}
                {child.can_retry && (
                  <button type="button" className="font-semibold text-accent hover:underline" onClick={() => onAction({ kind: "retry", documentId: item.revision_document_id, step, child })}>Retry</button>
                )}
              </span>
            </div>
            {child.unknown_provider_outcome && <p className="m-0 text-warning">Provider outcome unknown. The call may have been billed.</p>}
            {!child.unknown_provider_outcome && child.error_code && <p className="m-0 text-warning">{child.error_code.replaceAll("_", " ").toLowerCase()}</p>}
          </li>
        ))}
      </ul>
      {item.can_resume && <button type="button" className={docButtonClass("tiny")} onClick={() => onAction({ kind: "retry", documentId: item.revision_document_id, step: "resume" })}>Resume scheduling</button>}
      {!!resultRuns.length && <button type="button" className={docButtonClass("tiny")} onClick={viewEvidence}>View evidence</button>}
    </div>
  );
}
