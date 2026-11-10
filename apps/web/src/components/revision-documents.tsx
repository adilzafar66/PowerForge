"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { isRunning, jobInterval } from "@/lib/query-hooks";

import { useExtractionStatuses } from "@/components/document-extraction-panel";
import { ExtractionOperationToast } from "@/components/extraction-operation-panel";
import { StartExtractionWizard, type WizardLaunch } from "@/components/start-extraction-wizard";
import { DocumentInspector } from "@/components/document-inspector";
import { DocumentList, type DocumentEmptyState } from "@/components/document-list";
import { DocumentUploadDialog } from "@/components/document-upload";
import {
  activeAdvancedFilterCount,
  AttentionBar,
  DocumentQuickViews,
  DocumentRegisterToolbar,
  DocumentsHeader,
} from "@/components/document-workspace-toolbar";
import { docButtonClass, DocumentsDialog } from "@/components/documents-ui";
import { ReuseDocumentDialog } from "@/components/reuse-document-dialog";
import { useUploadQueue } from "@/components/use-upload-queue";
import { Select } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { apiErrorOf } from "@/lib/api";
import {
  EMPTY_ADVANCED_FILTERS,
  attentionCount,
  countQuickViews,
  matchesAdvancedFilters,
  matchesQuickView,
  type AdvancedDocumentFilters,
  type DocumentQuickView,
  type QuickViewCounts,
} from "@/lib/document-presentation";
import {
  DOCUMENT_TYPE_OPTIONS,
  getDocument,
  acceptClassification,
  isReadOnlyErrorCode,
  listDocuments,
  reclassifyDocument,
  removeDocument,
  restoreDocument,
  retryClassification,
  retryProcessing,
  updateDocument,
  type DocumentUpdateInput,
  type RevisionDocument,
} from "@/lib/documents";
import { getExtractionStatuses, ineligibleLabel } from "@/lib/extraction";
import { guardNavigation, useNavigationBlocker } from "@/lib/navigation-guard";
import { cn } from "@/lib/utils";
import { documentViewerHref, revisionHref } from "@/lib/workspace-navigation";
import { AsyncState } from "@/components/ui/async-state";

const SEARCH_DEBOUNCE_MS = 300;

type Props = {
  projectId: string;
  revisionId: string;
  /** From `canMutate` on the server; controls that change documents render only when true. */
  canMutate: boolean;
  revisionLabel?: string;
  /** Why the package is read-only, from `readOnlyReason`. */
  readOnlyReason?: string | null;
  /** The project's active revision, offered from a read-only revision. */
  activeRevisionId?: string | null;
};

type Message = {
  tone: "success" | "warning" | "error";
  text: string;
  /** Warnings say the list was refreshed because the server state had changed. */
  refreshed?: boolean;
};

/** Leaving the inspector with unsaved edits waits for an explicit decision. */
type PendingLeave = { kind: "close" } | { kind: "navigate"; href: string };

function emptyCopy({
  items,
  narrowed,
  counts,
  search,
  advancedActive,
  view,
}: {
  items: RevisionDocument[];
  narrowed: RevisionDocument[];
  counts: QuickViewCounts;
  search: string;
  advancedActive: boolean;
  view: DocumentQuickView;
}): DocumentEmptyState {
  if (items.length === 0 && search !== "") {
    return { text: "No documents match your search", kind: "search" };
  }
  if (advancedActive && narrowed.length === 0) {
    return { text: "No documents match your filters.", kind: "filters" };
  }
  if (
    search === "" &&
    !advancedActive &&
    (items.length === 0 || (view === "all" && counts.all === 0))
  ) {
    return { text: "No documents in this revision", kind: "revision" };
  }
  if (view === "needs_review" && narrowed.length > 0) {
    return { text: "No documents need review", kind: "view" };
  }
  if (view === "issues" && narrowed.length > 0) {
    return { text: "No document issues", kind: "view" };
  }
  if (view === "removed" && narrowed.length > 0) {
    return { text: "No removed documents", kind: "view" };
  }
  return { text: "No documents in this revision", kind: "revision" };
}

export function RevisionDocuments({
  projectId,
  revisionId,
  canMutate,
  revisionLabel,
  readOnlyReason = null,
  activeRevisionId = null,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const documentParam = searchParams.get("document");
  const operationParam = searchParams.get("operation");
  const launchParam = searchParams.get("extract");
  const routeQuery = searchParams.toString();
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [advancedFilters, setAdvancedFilters] =
    useState<AdvancedDocumentFilters>(EMPTY_ADVANCED_FILTERS);
  const [quickView, setQuickView] = useState<DocumentQuickView>("all");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [wizard, setWizard] = useState<WizardLaunch | null>(null);
  const [operationToast, setOperationToast] = useState<{ id: string; documentId: string } | null>(null);
  const consumedLaunch = useRef<string | null>(null);
  useEffect(() => {
    if (!launchParam) {
      consumedLaunch.current = null;
      return;
    }
    if (!canMutate || !documentParam || !["ensure", "reextract"].includes(launchParam)
      || consumedLaunch.current === routeQuery) return;
    consumedLaunch.current = routeQuery;
    const query = new URLSearchParams(routeQuery);
    setWizard({
      documentIds: [documentParam],
      mode: launchParam === "reextract" ? "reextract" : "ensure",
      initialPages: query.get("extractPages") ?? undefined,
      sourceVersion: query.get("extractSource") ?? undefined,
    });
    query.delete("extract");
    query.delete("extractPages");
    query.delete("extractSource");
    router.replace(`${pathname}?${query}`, { scroll: false });
  }, [canMutate, documentParam, launchParam, pathname, routeQuery, router]);
  const [manualRefresh, setManualRefresh] = useState(false);
  const client = useQueryClient();
  // Processing commits before classification is enqueued. Briefly bridge that real API gap.
  const classificationGrace = useRef(new Map<string, number>());
  const documents = useQuery({
    queryKey: keys.documentList(projectId, revisionId, search),
    queryFn: async () => {
      try {
        return await listDocuments(projectId, revisionId, {
          status: "ALL",
          search,
        });
      } catch (err) {
        const { status, detail } = apiErrorOf(err);
        if (status !== 404 && status !== 409) throw err;
        setMessage({ tone: "warning", text: detail, refreshed: true });
        return listDocuments(projectId, revisionId, { status: "ALL", search });
      }
    },
    refetchInterval: (query) => {
      const now = Date.now();
      const active = query.state.data
        ?.map((row) => {
          if (
            isRunning(row.processing?.status) ||
            isRunning(row.classification.attempt?.status)
          ) {
            classificationGrace.current.delete(row.id);
            return true;
          }
          if (
            row.processing?.status === "COMPLETED" &&
            row.classification.enabled &&
            !row.classification.attempt
          ) {
            const started = classificationGrace.current.get(row.id) ?? now;
            classificationGrace.current.set(row.id, started);
            return now - started < 15_000;
          }
          return false;
        })
        .some(Boolean);
      return jobInterval(!!active, query.state.fetchFailureCount);
    },
  });
  const items = documents.data ?? null;
  const loading = documents.isFetching;
  const error = documents.error ? apiErrorOf(documents.error).detail : null;
  const [message, setMessage] = useState<Message | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(() => new Set());
  const [skipped, setSkipped] = useState<{ id: string; name: string; reason: string }[]>([]);
  const [scopeError, setScopeError] = useState<string | null>(null);
  const [scopePending, setScopePending] = useState(false);
  const scopeRequest = useRef(0);
  const [selectedId, setSelectedId] = useState<string | null>(documentParam);
  const [removing, setRemoving] = useState<RevisionDocument | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [classifyingId, setClassifyingId] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [processingError, setProcessingError] = useState<string | null>(null);
  const [reuseOpen, setReuseOpen] = useState(false);
  const [inspectorDirty, setInspectorDirty] = useState(false);
  const [pendingLeave, setPendingLeave] = useState<PendingLeave | null>(null);
  const seenParam = useRef(documentParam);
  const jobStates = useRef(new Map<string, string>());
  useEffect(() => {
    for (const row of items ?? []) {
      const state = JSON.stringify([row.processing, row.classification]);
      const previous = jobStates.current.get(row.id);
      if (previous && previous !== state)
        void client.invalidateQueries({
          queryKey: keys.document(projectId, revisionId, row.id),
        });
      jobStates.current.set(row.id, state);
    }
  }, [items, client, projectId, revisionId]);

  useEffect(() => {
    if (seenParam.current === documentParam) {
      return;
    }
    seenParam.current = documentParam;
    setSelectedId(documentParam);
  }, [documentParam]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch((current) => (current === searchInput ? current : searchInput));
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const reloadList = useCallback(() => {
    void client.invalidateQueries(
      { queryKey: [...keys.documents(projectId, revisionId), "list"] },
      { cancelRefetch: false },
    );
  }, [client, projectId, revisionId]);

  const refreshAfterChange = useCallback(
    (text: string) => {
      setMessage({ tone: "warning", text, refreshed: true });
      reloadList();
    },
    [reloadList],
  );

  const handleReadOnly = useCallback(
    (text: string) => {
      setMessage({ tone: "warning", text, refreshed: true });
      router.refresh();
      reloadList();
    },
    [router, reloadList],
  );

  const uploads = useUploadQueue({
    projectId,
    revisionId,
    onUploaded: reloadList,
    onReadOnly: handleReadOnly,
  });

  const handleMutationError = useCallback(
    (err: unknown): boolean => {
      const { status, code, detail } = apiErrorOf(err);
      if (isReadOnlyErrorCode(code)) {
        handleReadOnly(detail);
        return true;
      }
      if (status === 404 || status === 409) {
        refreshAfterChange(detail);
        return true;
      }
      return false;
    },
    [handleReadOnly, refreshAfterChange],
  );

  const showDocument = useCallback(
    (id: string) => {
      setSelectedId(id);
      const params = new URLSearchParams(searchParams.toString());
      if (params.get("document") === id) {
        return;
      }
      params.set("document", id);
      params.delete("operation");
      router.push(`${pathname}?${params.toString()}`);
    },
    [pathname, router, searchParams],
  );

  const hideDocument = useCallback(() => {
    setSelectedId(null);
    if (!searchParams.get("document")) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    params.delete("document");
    params.delete("operation");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  }, [pathname, router, searchParams]);

  const closeDocument = useCallback(() => {
    if (inspectorDirty) {
      setPendingLeave({ kind: "close" });
      return;
    }
    hideDocument();
  }, [inspectorDirty, hideDocument]);

  useNavigationBlocker(inspectorDirty, (href) =>
    setPendingLeave({ kind: "navigate", href }),
  );

  function discardAndLeave() {
    const leave = pendingLeave;
    setPendingLeave(null);
    setInspectorDirty(false);
    if (!leave) return;
    if (leave.kind === "close") hideDocument();
    else router.push(leave.href);
  }

  useEffect(() => {
    setAiError(null);
    setProcessingError(null);
    if (selectedId) setMessage(null);
  }, [selectedId]);

  const restoreRow = useCallback(
    async (row: RevisionDocument) => {
      const name = row.document.original_filename;
      try {
        await restoreDocument(projectId, revisionId, row.id);
        setMessage({ tone: "success", text: `Restored ${name}.` });
        reloadList();
      } catch (err) {
        if (!handleMutationError(err)) {
          setMessage({ tone: "error", text: apiErrorOf(err).detail });
        }
      }
    },
    [projectId, revisionId, reloadList, handleMutationError],
  );

  function navigateTo(url: string) {
    if (!guardNavigation(url)) router.push(url);
  }

  function openViewer(row: RevisionDocument, pageNumber?: number) {
    const url = documentViewerHref(projectId, revisionId, row.id, {
      page: pageNumber,
    });
    navigateTo(url);
  }

  async function acceptRow(row: RevisionDocument) {
    const predictionId = row.classification.suggestion?.prediction_id;
    if (!predictionId) {
      return;
    }
    setClassifyingId(row.id);
    setAiError(null);
    try {
      await acceptClassification(projectId, revisionId, row.id, predictionId);
      setMessage({
        tone: "success",
        text: `Accepted the suggestion for ${row.document.original_filename}.`,
      });
      reloadList();
    } catch (err) {
      if (!handleMutationError(err)) {
        setAiError(apiErrorOf(err).detail);
      }
    } finally {
      setClassifyingId(null);
    }
  }

  async function reclassifyRow(row: RevisionDocument) {
    setClassifyingId(row.id);
    setAiError(null);
    try {
      await reclassifyDocument(projectId, revisionId, row.id);
      reloadList();
    } catch (err) {
      if (!handleMutationError(err)) {
        setAiError(apiErrorOf(err).detail);
      }
    } finally {
      setClassifyingId(null);
    }
  }

  async function retryClassificationRow(row: RevisionDocument) {
    const runId = row.classification.attempt?.id;
    if (!runId) {
      return;
    }
    setClassifyingId(row.id);
    setAiError(null);
    try {
      await retryClassification(projectId, revisionId, row.id, runId);
      reloadList();
    } catch (err) {
      if (!handleMutationError(err)) {
        setAiError(apiErrorOf(err).detail);
      }
    } finally {
      setClassifyingId(null);
    }
  }

  async function retryRow(row: RevisionDocument) {
    setRetryingId(row.id);
    setProcessingError(null);
    try {
      await retryProcessing(projectId, revisionId, row.id);
      reloadList();
    } catch (err) {
      if (!handleMutationError(err)) {
        setProcessingError(apiErrorOf(err).detail);
      }
    } finally {
      setRetryingId(null);
    }
  }

  async function saveRow(row: RevisionDocument, input: DocumentUpdateInput) {
    try {
      await updateDocument(projectId, revisionId, row.id, input);
    } catch (err) {
      handleMutationError(err);
      throw err;
    }
    setMessage({
      tone: "success",
      text: `Saved changes to ${row.document.original_filename}.`,
    });
    reloadList();
  }

  async function confirmRemove(row: RevisionDocument) {
    setRemoving(null);
    const name = row.document.original_filename;
    try {
      await removeDocument(projectId, revisionId, row.id);
      setMessage({
        tone: "success",
        text: `Removed ${name} from this revision.`,
      });
      reloadList();
    } catch (err) {
      if (!handleMutationError(err)) {
        setMessage({ tone: "error", text: apiErrorOf(err).detail });
      }
    }
  }

  const all = items ?? [];
  const narrowed = all.filter((row) =>
    matchesAdvancedFilters(row, advancedFilters),
  );
  const counts = countQuickViews(narrowed);
  const totals = countQuickViews(all);
  const visible = narrowed.filter((row) => matchesQuickView(row, quickView));
  const extractionIds = all.map((row) => row.id).sort();
  const extractionStatus = useExtractionStatuses(projectId, revisionId, extractionIds);
  const statuses = extractionStatus.data ?? {};
  const eligibleChecked = new Set([...checkedIds].filter((id) =>
    canMutate && (statuses[id]?.ineligible_reason ?? null) === null
  ));
  const newlySkipped = all.flatMap((row) => {
    const reason = statuses[row.id]?.ineligible_reason;
    return checkedIds.has(row.id) && reason
      ? [{ id: row.id, name: row.document.original_filename, reason: ineligibleLabel[reason] }]
      : [];
  });
  const skippedRows = [...new Map([...skipped, ...newlySkipped].map((item) => [item.id, item])).values()];

  function toggleChecked(ids: string[], checked: boolean) {
    setCheckedIds((previous) => {
      const next = new Set(previous);
      for (const id of ids) {
        if (checked) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  async function selectScope(scope: string) {
    const sequence = ++scopeRequest.current;
    setScopeError(null);
    setScopePending(true);
    try {
      const rows = scope === "filtered"
        ? visible
        : search
          ? await client.fetchQuery({
              queryKey: keys.documentList(projectId, revisionId, ""),
              queryFn: () => listDocuments(projectId, revisionId, { status: "ALL" }),
            })
          : all;
      const candidates = scope.startsWith("type:")
        ? rows.filter((row) => row.document_type === scope.slice(5))
        : rows;
      const ids = candidates.map((row) => row.id).sort();
      const scopedStatuses = await client.fetchQuery({
        queryKey: keys.extractionStatus(projectId, revisionId, ids),
        queryFn: ({ signal }) => getExtractionStatuses(projectId, revisionId, ids, signal),
      });
      if (sequence !== scopeRequest.current) return;
      setCheckedIds(new Set(ids.filter((id) => scopedStatuses[id]?.ineligible_reason === null)));
      setSkipped(candidates.flatMap((row) => {
        const status = scopedStatuses[row.id];
        return status?.ineligible_reason === null ? [] : [{
          id: row.id,
          name: row.document.original_filename,
          reason: status?.ineligible_reason ? ineligibleLabel[status.ineligible_reason] : "Eligibility unavailable",
        }];
      }));
      if (!ids.length) setScopeError("No documents match this selection.");
    } catch (error) {
      if (sequence === scopeRequest.current) setScopeError(apiErrorOf(error).detail);
    } finally {
      if (sequence === scopeRequest.current) setScopePending(false);
    }
  }

  const advancedActive = activeAdvancedFilterCount(advancedFilters) > 0;
  const empty =
    items !== null && visible.length === 0
      ? emptyCopy({
          items,
          narrowed,
          counts,
          search,
          advancedActive,
          view: quickView,
        })
      : null;
  const footer =
    items === null
      ? null
      : quickView === "removed"
        ? `Showing ${visible.length} of ${totals.removed} removed ${totals.removed === 1 ? "document" : "documents"}`
        : `Showing ${visible.length} of ${totals.all} active ${totals.all === 1 ? "document" : "documents"}`;
  const selectedRow = items?.find((row) => row.id === selectedId);
  const selectedQuery = useQuery({
    queryKey: [
      ...keys.document(projectId, revisionId, selectedId ?? ""),
      "record",
    ],
    queryFn: () => getDocument(projectId, revisionId, selectedId!),
    enabled: !!selectedId && items !== null && !selectedRow,
    initialData: selectedRow,
    refetchInterval: (query) =>
      jobInterval(
        isRunning(query.state.data?.processing?.status) ||
          isRunning(query.state.data?.classification.attempt?.status),
        query.state.fetchFailureCount,
      ),
  });
  useEffect(() => {
    if (selectedRow)
      client.setQueryData(
        [...keys.document(projectId, revisionId, selectedRow.id), "record"],
        selectedRow,
      );
  }, [client, projectId, revisionId, selectedRow]);
  const selected = selectedRow ?? selectedQuery.data ?? null;

  function handleReuseChanged(count: number) {
    if (count > 0) {
      setMessage({
        tone: "success",
        text: `Added ${count} ${count === 1 ? "document" : "documents"} from another revision.`,
      });
      reloadList();
    }
  }

  const refreshIndicator =
    documents.isFetching && items !== null
      ? "Refreshing…"
      : manualRefresh && !documents.error
        ? "Up to date"
        : null;

  const messageLine = (className: string) =>
    message ? (
      <p
        role={message.tone === "error" ? "alert" : "status"}
        className={cn(
          "m-0 text-workspace-label",
          message.tone === "success" && "text-positive",
          message.tone === "warning" && "text-warning",
          message.tone === "error" && "text-danger",
          className,
        )}
      >
        {message.text}
        {message.refreshed
          ? documents.isFetching
            ? " Refreshing the list."
            : documents.error
              ? " Refresh failed; retry below."
              : " The list has been refreshed."
          : ""}
      </p>
    ) : null;

  const toast = operationToast ? (
    <ExtractionOperationToast
      scope={{ projectId, revisionId }}
      operation={operationToast}
      onView={(href) => {
        const target = new URL(href, window.location.href);
        const internal = target.pathname + target.search;
        if (selectedId === operationToast.documentId || !guardNavigation(internal)) {
          router.push(internal, { scroll: false });
          setOperationToast(null);
        }
      }}
      onDismiss={() => setOperationToast(null)}
    />
  ) : null;

  return (
    <section aria-label="Documents">
      <DocumentsHeader
        revisionLabel={revisionLabel}
        overviewHref={revisionHref(projectId, revisionId, revisionId, "", "overview")}
        canMutate={canMutate}
        onUpload={() => setUploadOpen(true)}
        onReuse={() => setReuseOpen(true)}
      />
      <div className="mx-auto max-w-[var(--pf-documents-max)] min-w-0 px-[34px] pt-[29px] pb-[70px] max-[1250px]:px-6 max-[850px]:px-[18px] max-[850px]:py-[22px]">
        <AttentionBar
          attention={attentionCount(totals)}
          issues={totals.issues}
          readOnlyReason={readOnlyReason}
          activeRevisionHref={
            activeRevisionId && activeRevisionId !== revisionId
              ? revisionHref(projectId, activeRevisionId, revisionId, "", "documents")
              : null
          }
          onView={setQuickView}
        />

        {messageLine("mb-3.5")}

        <div className="mb-3.5 flex items-end justify-between gap-3">
          <div className="min-w-0">
            <h2 className="m-0 text-workspace-body font-bold tracking-[-0.1px] text-ink">
              Document register
            </h2>
            <p className="m-0 mt-0.5 text-workspace-caption text-muted">
              Working documents associated with the selected project revision
            </p>
          </div>
          {refreshIndicator ? (
            <p role="status" className="m-0 shrink-0 text-workspace-caption text-muted">
              {refreshIndicator}
            </p>
          ) : null}
        </div>

        <div className="min-w-0 overflow-hidden rounded-[var(--pf-radius-lg)] border border-border bg-panel">
          <DocumentRegisterToolbar
            search={searchInput}
            onSearchChange={setSearchInput}
            filters={advancedFilters}
            onFiltersChange={setAdvancedFilters}
            refreshing={documents.isFetching}
            onRefresh={() => {
              setManualRefresh(true);
              void documents.refetch();
              if (extractionIds.length) void extractionStatus.refetch();
            }}
            selection={canMutate && items !== null ? (
              <Select
                aria-label="Select documents by scope"
                presentation="workspace"
                className="w-auto min-w-[172px] max-w-full"
                value=""
                disabled={scopePending || search.trim() !== searchInput.trim()}
                onValueChange={(value) => void selectScope(value)}
              >
                <option value="">{scopePending ? "Selecting…" : "Select documents…"}</option>
                <option value="filtered">Select eligible filtered</option>
                <option value="all">Select all eligible</option>
                {DOCUMENT_TYPE_OPTIONS.filter(({ value }) => value !== "UNKNOWN").map(({ value, label }) => (
                  <option key={value} value={`type:${value}`}>Confirmed type · {label}</option>
                ))}
              </Select>
            ) : undefined}
          />
          {extractionStatus.error && extractionIds.length > 0 && (
            <div role="alert" className="flex items-center gap-2 border-b border-border px-5 py-2 text-workspace-caption text-danger">
              Extraction statuses could not refresh.
              <button type="button" className={docButtonClass("tiny")} onClick={() => void extractionStatus.refetch()}>Retry</button>
            </div>
          )}
          {scopeError && <p role="status" className="m-0 border-b border-border px-5 py-2 text-workspace-caption text-muted">{scopeError}</p>}
          {canMutate && (eligibleChecked.size > 0 || skippedRows.length > 0) && (
            <div className="border-b border-border bg-soft/60 px-5 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p role="status" className="m-0 text-workspace-label font-semibold">{eligibleChecked.size} eligible {eligibleChecked.size === 1 ? "document" : "documents"} selected</p>
                  <p className="m-0 mt-0.5 text-workspace-caption text-muted">Only included documents with processed pages can start extraction.</p>
                </div>
                <div className="flex gap-2">
                  <button type="button" className={docButtonClass("tiny")} onClick={() => {
                    scopeRequest.current++;
                    setScopePending(false);
                    setCheckedIds(new Set());
                    setSkipped([]);
                    setScopeError(null);
                  }}>Clear selection</button>
                  {eligibleChecked.size > 0 && (
                    <button
                      type="button" className={docButtonClass("primary")} disabled={scopePending}
                      onClick={() => setWizard({ documentIds: [...eligibleChecked], skipped: skippedRows })}
                    >Start extraction</button>
                  )}
                </div>
              </div>
              {skippedRows.length > 0 && (
                <details className="mt-2 text-workspace-caption text-muted">
                  <summary className="cursor-pointer">{skippedRows.length} skipped</summary>
                  <ul className="mt-1 max-h-40 overflow-auto pl-5">
                    {skippedRows.map(({ id, name, reason }) => <li key={id}>{name} · {reason}</li>)}
                  </ul>
                </details>
              )}
            </div>
          )}
          <DocumentQuickViews
            value={quickView}
            counts={counts}
            onChange={setQuickView}
          />
          <DocumentList
            rows={items === null ? null : visible}
            selectedId={selected?.id ?? null}
            canMutate={canMutate && !scopePending}
            extractionStatuses={statuses}
            checkedIds={eligibleChecked}
            onToggle={(id) => toggleChecked([id], !eligibleChecked.has(id))}
            onToggleVisible={toggleChecked}
            loading={loading}
            error={error}
            empty={empty}
            footer={footer}
            onOpen={(row) => showDocument(row.id)}
            onRetry={reloadList}
            onClearFilters={() => setAdvancedFilters(EMPTY_ADVANCED_FILTERS)}
            onUpload={() => setUploadOpen(true)}
            onReuse={() => setReuseOpen(true)}
          />
        </div>
      </div>

      {canMutate && uploadOpen ? (
        <DocumentUploadDialog
          queue={uploads}
          revisionLabel={revisionLabel}
          onClose={() => setUploadOpen(false)}
        />
      ) : null}

      {removing ? (
        <ConfirmDialog
          presentation="workspace"
          title="Remove document from this revision?"
          message="It stays in the project and in any other revision that includes it. You can restore it from the Removed view."
          confirmLabel="Remove"
          danger
          onConfirm={() => void confirmRemove(removing)}
          onCancel={() => setRemoving(null)}
        />
      ) : null}

      {reuseOpen ? (
        <ReuseDocumentDialog
          projectId={projectId}
          revisionId={revisionId}
          onClose={() => setReuseOpen(false)}
          onChanged={handleReuseChanged}
          onReadOnly={handleReadOnly}
        />
      ) : null}

      {pendingLeave ? (
        <DocumentsDialog
          title="Discard unsaved changes?"
          description="You have unsaved document details."
          onClose={() => setPendingLeave(null)}
          footer={
            <>
              <button
                type="button"
                className={docButtonClass()}
                onClick={() => setPendingLeave(null)}
              >
                Keep editing
              </button>
              <button
                type="button"
                className={docButtonClass("danger")}
                onClick={discardAndLeave}
              >
                Discard changes
              </button>
            </>
          }
        >
          <p className="m-0 rounded-[9px] border border-[var(--pf-documents-warning-border)] bg-warning-tint px-3.5 py-3 text-workspace-caption text-warning">
            {pendingLeave.kind === "close"
              ? "Your changes will be lost if you close the inspector."
              : "Your changes will be lost if you leave this page."}
          </p>
        </DocumentsDialog>
      ) : null}

      {selectedId && (
        <AsyncState
          pending={!selected && selectedQuery.isPending}
          error={selectedQuery.error}
          retry={selectedQuery.refetch}
        />
      )}
      {selected ? (
        <DocumentInspector
          key={selected.id}
          row={selected}
          projectId={projectId}
          revisionId={revisionId}
          canMutate={canMutate}
          classifying={classifyingId === selected.id}
          retrying={retryingId === selected.id}
          aiError={aiError}
          processingError={processingError}
          onRemove={() => setRemoving(selected)}
          onRestore={() => restoreRow(selected)}
          onStateChanged={refreshAfterChange}
          notice={<>{messageLine("border-b border-border px-[21px] py-3")}{toast}</>}
          onRequestClose={closeDocument}
          onAccept={() => void acceptRow(selected)}
          onReclassify={() => void reclassifyRow(selected)}
          onRetryClassification={() => void retryClassificationRow(selected)}
          onRetryProcessing={() => void retryRow(selected)}
          onViewPages={(pageNumber) => openViewer(selected, pageNumber)}
          onNavigate={navigateTo}
          onStartExtraction={() => setWizard({ documentIds: [selected.id] })}
          extractionOperationId={operationParam}
          onSave={(input) => saveRow(selected, input)}
          onDirtyChange={setInspectorDirty}
        />
      ) : null}
      {wizard && canMutate && (
        <StartExtractionWizard
          scope={{ projectId, revisionId }}
          launch={wizard}
          onClose={() => setWizard(null)}
          onStarted={(id, documentId) => {
            setWizard(null);
            setOperationToast({ id, documentId });
            setCheckedIds(new Set());
            setSkipped([]);
            void client.invalidateQueries({ queryKey: keys.extraction(projectId, revisionId) });
          }}
        />
      )}
      {!selected && toast}
    </section>
  );
}
