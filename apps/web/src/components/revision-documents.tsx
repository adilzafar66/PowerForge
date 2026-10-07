"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { DocumentRowActions } from "@/components/document-row-actions";
import { Card } from "@/components/ui/card";
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
  listDocuments,
  originLabel,
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

const TH = "px-4 py-3 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase";

export function RevisionDocuments({ projectId, revisionId }: Props) {
  const [searchInput, setSearchInput] = useState("");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [items, setItems] = useState<RevisionDocument[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
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
          setNotice(detail);
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

  const refreshAfterChange = useCallback((message: string) => {
    setNotice(message);
    setReloadToken((token) => token + 1);
  }, []);

  const filtersActive =
    filters.search !== "" ||
    filters.type !== "" ||
    filters.origin !== "" ||
    filters.view !== "INCLUDED";

  function clearFilters() {
    setSearchInput("");
    setFilters(DEFAULT_FILTERS);
  }

  return (
    <section aria-label="Documents">
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
          value={filters.view}
          onChange={(view) => setFilters({ ...filters, view })}
          options={[
            { value: "INCLUDED", label: "Included" },
            { value: "REMOVED", label: "Removed" },
            { value: "ALL", label: "All" },
          ]}
        />
      </div>

      {notice ? (
        <p role="status" className="mb-3 text-[13px] text-amber-700">
          {notice} The list has been refreshed.
        </p>
      ) : null}

      <Card className="overflow-hidden">
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
                  onStateChanged={refreshAfterChange}
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
  onStateChanged,
}: {
  row: RevisionDocument;
  first: boolean;
  projectId: string;
  revisionId: string;
  onStateChanged: (message: string) => void;
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
          onStateChanged={onStateChanged}
        />
      </td>
    </tr>
  );
}
