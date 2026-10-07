"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { DocumentEditor } from "@/components/document-editor";
import { DocumentRowActions } from "@/components/document-row-actions";
import { DocumentUpload } from "@/components/document-upload";
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
  documentTypeLabel,
  formatFileSize,
  isReadOnlyErrorCode,
  listDocuments,
  originLabel,
  removeDocument,
  restoreDocument,
  type DocumentOrigin,
  type DocumentStatusFilter,
  type DocumentType,
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
              <th className={TH}>Type</th>
              <th className={TH}>Origin</th>
              <th className={TH}>Status</th>
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
                  <td colSpan={6} className="px-5 py-4">
                    <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
                  </td>
                </tr>
              ))
            ) : error ? (
              <tr>
                <td colSpan={6}>
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
                <td colSpan={6}>
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
                  onStateChanged={refreshAfterChange}
                  onEdit={setEditing}
                  onRemove={setRemoving}
                  onRestore={restoreRow}
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
  onStateChanged,
  onEdit,
  onRemove,
  onRestore,
}: {
  row: RevisionDocument;
  first: boolean;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  onStateChanged: (message: string) => void;
  onEdit: (row: RevisionDocument) => void;
  onRemove: (row: RevisionDocument) => void;
  onRestore: (row: RevisionDocument) => Promise<void>;
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
