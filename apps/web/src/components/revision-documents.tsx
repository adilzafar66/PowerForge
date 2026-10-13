"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { DocumentDetailDrawer } from "@/components/document-detail-drawer";
import { DocumentList } from "@/components/document-list";
import { type DocumentMenuHandlers } from "@/components/document-overflow-menu";
import { DocumentUpload } from "@/components/document-upload";
import {
  activeAdvancedFilterCount,
  DocumentQuickViews,
  DocumentWorkspaceToolbar,
} from "@/components/document-workspace-toolbar";
import { PageViewer } from "@/components/page-viewer";
import { ReuseDocumentDialog } from "@/components/reuse-document-dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { apiErrorOf } from "@/lib/api";
import {
  EMPTY_ADVANCED_FILTERS,
  countQuickViews,
  matchesAdvancedFilters,
  matchesQuickView,
  type AdvancedDocumentFilters,
  type DocumentQuickView,
  type QuickViewCounts,
} from "@/lib/document-presentation";
import {
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
import { cn } from "@/lib/utils";

const SEARCH_DEBOUNCE_MS = 300;

type Props = {
  projectId: string;
  revisionId: string;
  /** From `canMutate` on the server; controls that change documents render only when true. */
  canMutate: boolean;
};

type Message = {
  tone: "success" | "warning" | "error";
  text: string;
  /** Warnings say the list was refreshed because the server state had changed. */
  refreshed?: boolean;
};

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
}): { text: string; kind: "revision" | "search" | "filters" | "view" } {
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

export function RevisionDocuments({ projectId, revisionId, canMutate }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const documentParam = searchParams.get("document");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [advancedFilters, setAdvancedFilters] =
    useState<AdvancedDocumentFilters>(EMPTY_ADVANCED_FILTERS);
  const [quickView, setQuickView] = useState<DocumentQuickView>("all");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [items, setItems] = useState<RevisionDocument[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(documentParam);
  const [removing, setRemoving] = useState<RevisionDocument | null>(null);
  const [viewing, setViewing] = useState<RevisionDocument | null>(null);
  const [viewerPage, setViewerPage] = useState<number | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [classifyingId, setClassifyingId] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [processingError, setProcessingError] = useState<string | null>(null);
  const [focusMetadata, setFocusMetadata] = useState(false);
  const [reuseOpen, setReuseOpen] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const latestRequest = useRef(0);
  const seenParam = useRef(documentParam);

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

  useEffect(() => {
    const requestId = ++latestRequest.current;
    const isCurrent = () => requestId === latestRequest.current;

    async function load() {
      setLoading(true);
      setError(null);
      const query = { status: "ALL" as const, search };
      try {
        const result = await listDocuments(projectId, revisionId, query);
        if (isCurrent()) {
          setItems(result);
        }
      } catch (err) {
        if (!isCurrent()) {
          return;
        }
        const { status, detail } = apiErrorOf(err);
        if (status === 404 || status === 409) {
          setMessage({ tone: "warning", text: detail, refreshed: true });
          try {
            const result = await listDocuments(projectId, revisionId, query);
            if (isCurrent()) {
              setItems(result);
            }
          } catch (retryErr) {
            if (isCurrent()) {
              setError(apiErrorOf(retryErr).detail);
            }
          }
        } else {
          setError(detail);
        }
      } finally {
        if (isCurrent()) {
          setLoading(false);
        }
      }
    }

    void load();
  }, [projectId, revisionId, search, reloadToken]);

  const reloadList = useCallback(() => setReloadToken((token) => token + 1), []);

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

  const selectDocument = useCallback(
    (id: string) => {
      setSelectedId(id);
      const params = new URLSearchParams(searchParams.toString());
      if (params.get("document") === id) {
        return;
      }
      params.set("document", id);
      router.push(`${pathname}?${params.toString()}`);
    },
    [pathname, router, searchParams],
  );

  const closeDocument = useCallback(() => {
    setSelectedId(null);
    setFocusMetadata(false);
    if (!searchParams.get("document")) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    params.delete("document");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  }, [pathname, router, searchParams]);

  useEffect(() => {
    if (!selectedId || items === null) {
      return;
    }
    if (items.some((row) => row.id === selectedId)) {
      return;
    }
    setSelectedId(null);
    const params = new URLSearchParams(searchParams.toString());
    if (!params.has("document")) {
      return;
    }
    params.delete("document");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  }, [items, pathname, router, searchParams, selectedId]);

  useEffect(() => {
    setAiError(null);
    setProcessingError(null);
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

  function openViewer(row: RevisionDocument, pageNumber?: number) {
    setViewerPage(pageNumber ?? null);
    setViewing(row);
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
      if (handleMutationError(err)) {
        return;
      }
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
      setMessage({ tone: "success", text: `Removed ${name} from this revision.` });
      reloadList();
    } catch (err) {
      if (!handleMutationError(err)) {
        setMessage({ tone: "error", text: apiErrorOf(err).detail });
      }
    }
  }

  const narrowed = (items ?? []).filter((row) => matchesAdvancedFilters(row, advancedFilters));
  const counts = countQuickViews(narrowed);
  const visible = narrowed.filter((row) => matchesQuickView(row, quickView));
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
  const selected = items?.find((row) => row.id === selectedId) ?? null;

  function handleReuseChanged(count: number) {
    if (count > 0) {
      setMessage({
        tone: "success",
        text: `Added ${count} ${count === 1 ? "document" : "documents"} from another revision.`,
      });
      reloadList();
    }
  }

  const clearMetadataFocus = useCallback(() => setFocusMetadata(false), []);

  const menuHandlers: DocumentMenuHandlers = {
    onViewPages: (row) => openViewer(row),
    onEditMetadata: (row) => {
      selectDocument(row.id);
      setFocusMetadata(true);
    },
    onReclassify: (row) => void reclassifyRow(row),
    onRetryClassification: (row) => void retryClassificationRow(row),
    onRetryProcessing: (row) => void retryRow(row),
    onRemove: setRemoving,
    onRestore: restoreRow,
    onStateChanged: refreshAfterChange,
  };

  return (
    <section aria-label="Documents">
      <DocumentWorkspaceToolbar
        documentCount={items === null ? null : counts.all}
        canMutate={canMutate}
        search={searchInput}
        onSearchChange={setSearchInput}
        filters={advancedFilters}
        onFiltersChange={setAdvancedFilters}
        onUpload={() => setUploadOpen(true)}
        onReuse={() => setReuseOpen(true)}
      />
      <DocumentQuickViews value={quickView} counts={counts} onChange={setQuickView} />
      {canMutate && uploadOpen ? (
        <DocumentUpload
          projectId={projectId}
          revisionId={revisionId}
          onUploaded={reloadList}
          onReadOnly={handleReadOnly}
        />
      ) : null}

      {message ? (
        <p
          role={message.tone === "error" ? "alert" : "status"}
          className={cn(
            "mb-3 text-[13px]",
            message.tone === "success" && "text-emerald-700",
            message.tone === "warning" && "text-amber-700",
            message.tone === "error" && "text-red-600",
          )}
        >
          {message.text}
          {message.refreshed ? " The list has been refreshed." : ""}
        </p>
      ) : null}

      {removing ? (
        <ConfirmDialog
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

      {viewing ? (
        <PageViewer
          projectId={projectId}
          revisionId={revisionId}
          revisionDocumentId={viewing.id}
          filename={viewing.document.original_filename}
          initialPageNumber={viewerPage}
          onClose={() => {
            setViewing(null);
            setViewerPage(null);
          }}
        />
      ) : null}

      <DocumentList
        rows={items === null ? null : visible}
        selectedId={selected?.id ?? null}
        projectId={projectId}
        revisionId={revisionId}
        canMutate={canMutate}
        loading={loading}
        error={error}
        empty={empty}
        handlers={menuHandlers}
        onOpen={(row) => selectDocument(row.id)}
        onRetry={reloadList}
        onClearFilters={() => setAdvancedFilters(EMPTY_ADVANCED_FILTERS)}
        onUpload={() => setUploadOpen(true)}
        onReuse={() => setReuseOpen(true)}
      />

      {selected ? (
        <DocumentDetailDrawer
          key={selected.id}
          row={selected}
          projectId={projectId}
          revisionId={revisionId}
          canMutate={canMutate}
          detailVersion={reloadToken}
          classifying={classifyingId === selected.id}
          retrying={retryingId === selected.id}
          aiError={aiError}
          processingError={processingError}
          focusMetadata={focusMetadata}
          handlers={menuHandlers}
          onClose={closeDocument}
          onMetadataFocused={clearMetadataFocus}
          onAccept={() => void acceptRow(selected)}
          onReclassify={() => void reclassifyRow(selected)}
          onRetryClassification={() => void retryClassificationRow(selected)}
          onRetryProcessing={() => void retryRow(selected)}
          onViewPages={(pageNumber) => openViewer(selected, pageNumber)}
          onSave={(input) => saveRow(selected, input)}
        />
      ) : null}
    </section>
  );
}
