"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { DocumentEditor } from "@/components/document-editor";
import { DocumentRowActions } from "@/components/document-row-actions";
import { DocumentUpload } from "@/components/document-upload";
import { PageViewer } from "@/components/page-viewer";
import { ReuseDocumentDialog } from "@/components/reuse-document-dialog";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { fieldClassName } from "@/components/ui/input";
import { SearchField } from "@/components/ui/search-field";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Button } from "@/components/ui/button";
import { Mono } from "@/components/ui/mono";
import { apiErrorOf } from "@/lib/api";
import {
  DOCUMENT_TYPE_OPTIONS,
  acceptClassification,
  classificationAttemptLabel,
  classificationErrorLabel,
  confidenceBandLabel,
  documentTypeLabel,
  formatFileSize,
  isReadOnlyErrorCode,
  listClassificationPages,
  listDocuments,
  originLabel,
  reclassifyDocument,
  removeDocument,
  restoreDocument,
  retryClassification,
  retryProcessing,
  type ClassificationPagePrediction,
  type ClassificationSummary,
  type DocumentOrigin,
  type DocumentStatusFilter,
  type DocumentType,
  type ProcessingSummary,
  type RevisionDocument,
} from "@/lib/documents";
import { formatDateShort } from "@/lib/projects";
import { cn } from "@/lib/utils";

const SEARCH_DEBOUNCE_MS = 300;

type Props = {
  projectId: string;
  revisionId: string;
  /** From `canMutate` on the server; controls that change documents render only when true. */
  canMutate: boolean;
};

type Filters = {
  search: string;
  type: DocumentType | "";
  origin: DocumentOrigin | "";
  view: DocumentStatusFilter;
};

const DEFAULT_FILTERS: Filters = {
  search: "",
  type: "",
  origin: "",
  view: "INCLUDED",
};

type Message = {
  tone: "success" | "warning" | "error";
  text: string;
  /** Warnings say the list was refreshed because the server state had changed. */
  refreshed?: boolean;
};

type Preset = Pick<Filters, "type" | "origin" | "view">;

const QUICK_FILTERS: { id: string; label: string; preset: Preset }[] = [
  { id: "all", label: "All", preset: { type: "", origin: "", view: "INCLUDED" } },
  { id: "uploaded", label: "Uploaded", preset: { type: "", origin: "UPLOADED", view: "INCLUDED" } },
  {
    id: "inherited",
    label: "Inherited",
    preset: { type: "", origin: "INHERITED", view: "INCLUDED" },
  },
  {
    id: "unclassified",
    label: "Unclassified",
    preset: { type: "UNKNOWN", origin: "", view: "INCLUDED" },
  },
  { id: "removed", label: "Removed", preset: { type: "", origin: "", view: "REMOVED" } },
];

const TH = "px-4 py-3 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase";

export function RevisionDocuments({ projectId, revisionId, canMutate }: Props) {
  const router = useRouter();
  const [searchInput, setSearchInput] = useState("");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [items, setItems] = useState<RevisionDocument[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [editing, setEditing] = useState<RevisionDocument | null>(null);
  const [removing, setRemoving] = useState<RevisionDocument | null>(null);
  const [viewing, setViewing] = useState<RevisionDocument | null>(null);
  const [viewerPage, setViewerPage] = useState<number | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [classifyingId, setClassifyingId] = useState<string | null>(null);
  const [reuseOpen, setReuseOpen] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const latestRequest = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) =>
        current.search === searchInput ? current : { ...current, search: searchInput },
      );
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const requestId = ++latestRequest.current;
    const isCurrent = () => requestId === latestRequest.current;

    async function load() {
      setLoading(true);
      setError(null);
      const query = {
        status: filters.view,
        document_type: filters.type,
        origin: filters.origin,
        search: filters.search,
      };
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
          // The state changed under the user: say so, then refresh once.
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
  }, [projectId, revisionId, filters, reloadToken]);

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

  /** Returns true when the failure was a state change that the page has now handled. */
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
    const predictionId = row.classification?.suggestion?.prediction_id;
    if (!predictionId) return;
    setClassifyingId(row.id);
    try {
      const updated = await acceptClassification(projectId, revisionId, row.id, predictionId);
      setItems((current) =>
        current ? current.map((item) => (item.id === updated.id ? updated : item)) : current,
      );
      setMessage({
        tone: "success",
        text: `Accepted the suggestion for ${row.document.original_filename}.`,
      });
    } catch (err) {
      if (!handleMutationError(err)) {
        setMessage({ tone: "error", text: apiErrorOf(err).detail });
      }
    } finally {
      setClassifyingId(null);
    }
  }

  async function reclassifyRow(row: RevisionDocument) {
    setClassifyingId(row.id);
    try {
      const detail = await reclassifyDocument(projectId, revisionId, row.id);
      setItems((current) =>
        current
          ? current.map((item) => (item.id === row.id ? mergeClassification(item, detail) : item))
          : current,
      );
    } catch (err) {
      setMessage({ tone: "error", text: apiErrorOf(err).detail });
    } finally {
      setClassifyingId(null);
    }
  }

  async function retryClassificationRow(row: RevisionDocument) {
    const runId = row.classification?.attempt?.id;
    if (!runId) return;
    setClassifyingId(row.id);
    try {
      const detail = await retryClassification(projectId, revisionId, row.id, runId);
      setItems((current) =>
        current
          ? current.map((item) => (item.id === row.id ? mergeClassification(item, detail) : item))
          : current,
      );
    } catch (err) {
      setMessage({ tone: "error", text: apiErrorOf(err).detail });
    } finally {
      setClassifyingId(null);
    }
  }

  async function retryRow(row: RevisionDocument) {
    setRetryingId(row.id);
    try {
      const result = await retryProcessing(projectId, revisionId, row.id);
      setItems((current) =>
        current
          ? current.map((item) =>
              item.id === row.id ? { ...item, processing: result.processing } : item,
            )
          : current,
      );
    } catch (err) {
      setMessage({ tone: "error", text: apiErrorOf(err).detail });
    } finally {
      setRetryingId(null);
    }
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

  function handleSaved(updated: RevisionDocument) {
    setEditing(null);
    setItems((current) =>
      current ? current.map((item) => (item.id === updated.id ? updated : item)) : current,
    );
    setMessage({
      tone: "success",
      text: `Saved changes to ${updated.document.original_filename}.`,
    });
    reloadList();
  }

  const filtersActive =
    filters.search !== "" ||
    filters.type !== "" ||
    filters.origin !== "" ||
    filters.view !== "INCLUDED";

  function handleReuseChanged(count: number) {
    if (count > 0) {
      setMessage({
        tone: "success",
        text: `Added ${count} ${count === 1 ? "document" : "documents"} from another revision.`,
      });
      reloadList();
    }
  }

  function clearFilters() {
    setSearchInput("");
    setFilters(DEFAULT_FILTERS);
  }

  return (
    <section aria-label="Documents">
      {canMutate ? (
        <DocumentUpload
          projectId={projectId}
          revisionId={revisionId}
          onUploaded={reloadList}
          onReadOnly={handleReadOnly}
        />
      ) : null}
      {canMutate ? (
        <div className="mb-3 flex justify-end">
          <Button type="button" variant="secondary" size="sm" onClick={() => setReuseOpen(true)}>
            Add from another revision
          </Button>
        </div>
      ) : null}

      <div
        role="group"
        aria-label="Quick filters"
        className="mb-3 flex flex-wrap items-center gap-1.5"
      >
        {QUICK_FILTERS.map(({ id, label, preset }) => {
          const active =
            filters.type === preset.type &&
            filters.origin === preset.origin &&
            filters.view === preset.view;
          return (
            <button
              key={id}
              type="button"
              aria-pressed={active}
              onClick={() => setFilters((current) => ({ ...current, ...preset }))}
              className={cn(
                "cursor-pointer rounded-full border px-3 py-1 text-[12px] font-semibold transition-colors",
                active
                  ? "border-blue-200 bg-blue-50 text-blue-700"
                  : "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700",
              )}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SearchField
          value={searchInput}
          onChange={setSearchInput}
          placeholder="Search by file name, number or description…"
        />
        <select
          aria-label="Type"
          value={filters.type}
          onChange={(event) =>
            setFilters({
              ...filters,
              type: event.target.value as DocumentType | "",
            })
          }
          className={cn(fieldClassName, "w-auto py-2 text-[13px]")}
        >
          <option value="">All types</option>
          {DOCUMENT_TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Origin"
          value={filters.origin}
          onChange={(event) =>
            setFilters({
              ...filters,
              origin: event.target.value as DocumentOrigin | "",
            })
          }
          className={cn(fieldClassName, "w-auto py-2 text-[13px]")}
        >
          <option value="">All origins</option>
          <option value="UPLOADED">Uploaded</option>
          <option value="INHERITED">Inherited</option>
        </select>
        <SegmentedControl
          label="View"
          value={filters.view}
          onChange={(view) => setFilters({ ...filters, view })}
          options={[
            { value: "INCLUDED", label: "Included" },
            { value: "REMOVED", label: "Removed" },
            { value: "ALL", label: "All" },
          ]}
        />
      </div>

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

      {editing ? (
        <DocumentEditor
          key={editing.id}
          projectId={projectId}
          revisionId={revisionId}
          document={editing}
          canMutate={canMutate}
          onClose={() => setEditing(null)}
          onSaved={handleSaved}
          onMutationError={handleMutationError}
        />
      ) : null}

      <Card>
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="border-b border-slate-100">
              <th className={cn(TH, "px-5")}>File</th>
              <th className={TH}>Confirmed Type</th>
              <th className={TH}>AI Suggestion</th>
              <th className={TH}>Origin</th>
              <th className={TH}>Status</th>
              <th className={TH}>Processing</th>
              <th className={cn(TH, "hidden lg:table-cell")}>Added</th>
              <th className={cn(TH, "text-right")}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className={cn(loading && items ? "opacity-60" : undefined)}>
            {items === null && loading ? (
              [0, 1, 2].map((row) => (
                <tr key={row} data-testid="document-skeleton" className="border-t border-slate-100">
                  <td colSpan={8} className="px-5 py-4">
                    <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
                  </td>
                </tr>
              ))
            ) : error ? (
              <tr>
                <td colSpan={8}>
                  <div className="flex flex-col items-center gap-2 py-14">
                    <p role="alert" className="text-[13.5px] text-red-600">
                      {error}
                    </p>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => setReloadToken((token) => token + 1)}
                    >
                      Retry
                    </Button>
                  </div>
                </td>
              </tr>
            ) : items && items.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <div className="flex flex-col items-center gap-2 py-16">
                    <p className="text-[13.5px] font-medium text-slate-400">
                      {filtersActive
                        ? "No documents match your filters."
                        : "No documents in this revision yet."}
                    </p>
                    {filtersActive ? (
                      <button
                        type="button"
                        onClick={clearFilters}
                        className="cursor-pointer text-[12.5px] text-accent hover:underline"
                      >
                        Clear filters
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ) : (
              items?.map((row, index) => (
                <DocumentRow
                  key={row.id}
                  row={row}
                  first={index === 0}
                  projectId={projectId}
                  revisionId={revisionId}
                  canMutate={canMutate}
                  retrying={retryingId === row.id}
                  classifying={classifyingId === row.id}
                  onStateChanged={refreshAfterChange}
                  onEdit={setEditing}
                  onRemove={setRemoving}
                  onRestore={restoreRow}
                  onRetry={retryRow}
                  onView={(pageNumber) => openViewer(row, pageNumber)}
                  onAccept={acceptRow}
                  onReclassify={reclassifyRow}
                  onRetryClassification={retryClassificationRow}
                />
              ))
            )}
          </tbody>
        </table>
      </Card>
    </section>
  );
}

function DocumentRow({
  row,
  first,
  projectId,
  revisionId,
  canMutate,
  retrying,
  classifying,
  onStateChanged,
  onEdit,
  onRemove,
  onRestore,
  onRetry,
  onView,
  onAccept,
  onReclassify,
  onRetryClassification,
}: {
  row: RevisionDocument;
  first: boolean;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  retrying: boolean;
  classifying: boolean;
  onStateChanged: (message: string) => void;
  onEdit: (row: RevisionDocument) => void;
  onRemove: (row: RevisionDocument) => void;
  onRestore: (row: RevisionDocument) => Promise<void>;
  onRetry: (row: RevisionDocument) => void;
  onView: (pageNumber?: number) => void;
  onAccept: (row: RevisionDocument) => void;
  onReclassify: (row: RevisionDocument) => void;
  onRetryClassification: (row: RevisionDocument) => void;
}) {
  const removed = row.status === "REMOVED";
  return (
    <tr className={cn(!first && "border-t border-slate-100", removed && "bg-slate-50/60")}>
      <td className="px-5 py-3.5">
        <p
          className={cn(
            "font-semibold break-all",
            removed ? "text-slate-400 line-through" : "text-slate-900",
          )}
        >
          {row.document.original_filename}
        </p>
        <p className="mt-0.5 text-[12px] text-slate-400">
          {formatFileSize(row.document.size_bytes)}
          {row.document_number ? (
            <>
              {" · "}
              <Mono className="text-slate-500">{row.document_number}</Mono>
            </>
          ) : null}
        </p>
      </td>
      <td className="px-4 py-3.5 text-slate-600">{documentTypeLabel(row.document_type)}</td>
      <td className="px-4 py-3.5">
        <ClassificationCell
          row={row}
          projectId={projectId}
          revisionId={revisionId}
          canMutate={canMutate}
          busy={classifying}
          onAccept={() => onAccept(row)}
          onChooseType={() => onEdit(row)}
          onReclassify={() => onReclassify(row)}
          onRetry={() => onRetryClassification(row)}
          onOpenPage={(pageNumber) => onView(pageNumber)}
        />
      </td>
      <td className="px-4 py-3.5">
        <span
          className={cn(
            "inline-flex rounded-full px-2 py-0.5 text-[11.5px] font-semibold",
            row.origin === "INHERITED"
              ? "bg-violet-50 text-violet-700"
              : "bg-blue-50 text-blue-700",
          )}
        >
          {originLabel(row.origin)}
        </span>
        {row.origin === "INHERITED" && row.inherited_from_revision_identifier ? (
          <p className="mt-1 text-[12px] text-slate-400">
            {row.inherited_from_revision_id ? (
              <>
                from{" "}
                <Link
                  href={`/projects/${projectId}/revisions/${row.inherited_from_revision_id}`}
                  className="text-accent hover:underline"
                >
                  Revision {row.inherited_from_revision_identifier}
                </Link>
              </>
            ) : (
              <>from Revision {row.inherited_from_revision_identifier}</>
            )}
          </p>
        ) : null}
      </td>
      <td className="px-4 py-3.5">
        <span
          className={cn(
            "inline-flex rounded-full px-2 py-0.5 text-[11.5px] font-semibold",
            removed ? "bg-slate-100 text-slate-500" : "bg-emerald-50 text-emerald-700",
          )}
        >
          {removed ? "Removed" : "Included"}
        </span>
      </td>
      <td className="px-4 py-3.5">
        <ProcessingCell
          processing={row.processing}
          retrying={retrying}
          onRetry={() => onRetry(row)}
          onView={() => onView()}
        />
      </td>
      <td className="hidden px-4 py-3.5 text-[12.5px] text-slate-400 lg:table-cell">
        {formatDateShort(row.added_at)}
      </td>
      <td className="px-4 py-3.5">
        <DocumentRowActions
          projectId={projectId}
          revisionId={revisionId}
          document={row}
          canMutate={canMutate}
          onStateChanged={onStateChanged}
          onEdit={onEdit}
          onRemove={onRemove}
          onRestore={onRestore}
        />
      </td>
    </tr>
  );
}

function ProcessingCell({
  processing,
  retrying,
  onRetry,
  onView,
}: {
  processing: ProcessingSummary | null | undefined;
  retrying: boolean;
  onRetry: () => void;
  onView: () => void;
}) {
  if (!processing) {
    return <span className="text-[13px] text-slate-400">Not started</span>;
  }
  if (processing.status === "PENDING") {
    return <span className="text-[13px] font-medium text-slate-600">Pending</span>;
  }
  if (processing.status === "RUNNING") {
    const progress =
      processing.pages_total != null
        ? ` ${processing.pages_processed}/${processing.pages_total}`
        : "";
    return (
      <span className="text-[13px] font-medium text-slate-700">Processing{progress}</span>
    );
  }
  if (processing.status === "COMPLETED") {
    return (
      <div className="flex flex-col items-start gap-1">
        <span className="text-[13px] font-medium text-emerald-700">Ready</span>
        <Button type="button" variant="secondary" size="sm" onClick={onView}>
          View pages
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="text-[13px] font-medium text-red-600">Failed</span>
      {processing.error_message ? (
        <p className="max-w-56 text-[12px] text-slate-500">{processing.error_message}</p>
      ) : null}
      <Button type="button" variant="secondary" size="sm" onClick={onRetry} disabled={retrying}>
        Retry processing
      </Button>
    </div>
  );
}

function mergeClassification(row: RevisionDocument, detail: ClassificationSummary): RevisionDocument {
  return {
    ...row,
    classification: {
      enabled: detail.enabled,
      suggestion: detail.suggestion,
      attempt: detail.attempt,
    },
  };
}

function ClassificationCell({
  row,
  projectId,
  revisionId,
  canMutate,
  busy,
  onAccept,
  onChooseType,
  onReclassify,
  onRetry,
  onOpenPage,
}: {
  row: RevisionDocument;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  busy: boolean;
  onAccept: () => void;
  onChooseType: () => void;
  onReclassify: () => void;
  onRetry: () => void;
  onOpenPage: (pageNumber: number) => void;
}) {
  const classification = row.classification;
  const suggestion = classification?.suggestion ?? null;
  const attempt = classification?.attempt ?? null;
  const stateLabel = classificationAttemptLabel(classification);
  const included = row.status === "INCLUDED";
  const canReview = canMutate && included;
  const typesDiffer = suggestion != null && suggestion.predicted_type !== row.document_type;
  const inFlight = attempt?.status === "PENDING" || attempt?.status === "RUNNING";
  const showRetry = classification?.enabled === true && attempt?.status === "FAILED";
  const showReclassify = classification?.enabled === true && suggestion != null && !inFlight;

  return (
    <div className="flex max-w-64 flex-col items-start gap-1">
      <span className="text-[13px] font-medium text-slate-700">{stateLabel}</span>
      {suggestion ? (
        <p className="text-[13px] text-slate-600">
          {documentTypeLabel(suggestion.predicted_type)}
          {suggestion.accepted ? (
            <span aria-label="Accepted"> ✓</span>
          ) : null}{" "}
          <span className="text-slate-500">{confidenceBandLabel(suggestion.confidence_band)}</span>
        </p>
      ) : null}
      {typesDiffer ? (
        <p className="text-[12px] text-slate-500">
          Confirmed: {documentTypeLabel(row.document_type)}
        </p>
      ) : null}
      {attempt?.status === "FAILED" ? (
        <p className="text-[12px] text-slate-500">{classificationErrorLabel(attempt.error_code)}</p>
      ) : null}
      {canReview && suggestion && !suggestion.accepted && !typesDiffer ? (
        <div className="flex flex-wrap gap-1">
          <Button type="button" variant="secondary" size="sm" onClick={onAccept} disabled={busy}>
            Accept
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={onChooseType} disabled={busy}>
            Choose another type
          </Button>
        </div>
      ) : null}
      {canReview && suggestion && !suggestion.accepted && typesDiffer ? (
        <div className="flex flex-wrap gap-1">
          <Button type="button" variant="secondary" size="sm" onClick={onAccept} disabled={busy}>
            Use AI Suggestion
          </Button>
          <Button type="button" variant="secondary" size="sm" disabled={busy}>
            Keep Current
          </Button>
        </div>
      ) : null}
      {showRetry || showReclassify ? (
        <div className="flex flex-wrap gap-1">
          {showRetry ? (
            <Button type="button" variant="secondary" size="sm" onClick={onRetry} disabled={busy}>
              Retry classification
            </Button>
          ) : null}
          {showReclassify ? (
            <Button type="button" variant="secondary" size="sm" onClick={onReclassify} disabled={busy}>
              Reclassify
            </Button>
          ) : null}
        </div>
      ) : null}
      {suggestion?.predicted_type === "MIXED_DOCUMENT" ? (
        <MixedPages
          projectId={projectId}
          revisionId={revisionId}
          revisionDocumentId={row.id}
          onOpenPage={onOpenPage}
        />
      ) : null}
    </div>
  );
}

function MixedPages({
  projectId,
  revisionId,
  revisionDocumentId,
  onOpenPage,
}: {
  projectId: string;
  revisionId: string;
  revisionDocumentId: string;
  onOpenPage: (pageNumber: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pages, setPages] = useState<ClassificationPagePrediction[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (!open && pages === null) {
      try {
        setPages(await listClassificationPages(projectId, revisionId, revisionDocumentId));
      } catch (err) {
        setError(apiErrorOf(err).detail);
      }
    }
    setOpen((current) => !current);
  }

  return (
    <div className="mt-1">
      <Button type="button" variant="secondary" size="sm" onClick={() => void toggle()}>
        {open ? "Hide page types" : "View page types"}
      </Button>
      {error ? <p className="mt-1 text-[12px] text-red-600">{error}</p> : null}
      {open && pages ? (
        <table className="mt-2 text-[12px]">
          <thead>
            <tr className="text-left text-slate-400">
              <th className="pr-3 font-semibold">Page</th>
              <th className="pr-3 font-semibold">AI Page Type</th>
              <th className="font-semibold">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {pages.map((page) => (
              <tr key={page.page_number}>
                <td className="pr-3">
                  <button
                    type="button"
                    className="cursor-pointer text-accent hover:underline"
                    onClick={() => onOpenPage(page.page_number)}
                  >
                    {page.page_number}
                  </button>
                </td>
                <td className="pr-3 text-slate-600">{documentTypeLabel(page.predicted_type)}</td>
                <td className="text-slate-500">{confidenceBandLabel(page.confidence_band)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
