"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { DocumentOverflowMenu, type DocumentMenuHandlers } from "@/components/document-overflow-menu";
import { DocumentState } from "@/components/document-state";
import { AddDocumentsMenu } from "@/components/document-workspace-toolbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { revisionTable, revisionRowClass, revisionPrimaryClass } from "@/components/ui/revision-table";
import {
  confidenceBandLabel,
  documentTypeLabel,
  formatFileSize,
  type RevisionDocument,
} from "@/lib/documents";
import { formatDateShort } from "@/lib/projects";
import { cn } from "@/lib/utils";

const TH = revisionTable.header;

function secondaryFacts(row: RevisionDocument, projectId: string): ReactNode[] {
  const facts: ReactNode[] = [];
  if (row.document_number) {
    facts.push(<span key="number">{row.document_number}</span>);
  }
  facts.push(<span key="size">{formatFileSize(row.document.size_bytes)}</span>);
  facts.push(
    <span key="origin">
      <OriginFact row={row} projectId={projectId} />
    </span>,
  );
  if (row.processing?.pages_total != null) {
    const count = row.processing.pages_total;
    facts.push(
      <span key="pages">
        {count} {count === 1 ? "page" : "pages"}
      </span>,
    );
  }
  return facts.slice(0, 3);
}

function OriginFact({ row, projectId }: { row: RevisionDocument; projectId: string }) {
  if (row.origin !== "INHERITED") {
    return <>Uploaded · {formatDateShort(row.added_at)}</>;
  }
  const identifier = row.inherited_from_revision_identifier;
  if (!identifier) {
    return <>Inherited</>;
  }
  const label = `Rev ${identifier}`;
  if (!row.inherited_from_revision_id) {
    return <>Inherited from {label}</>;
  }
  return (
    <>
      Inherited from{" "}
      <Link
        href={`/projects/${projectId}/revisions/${row.inherited_from_revision_id}`}
        className="text-accent hover:underline"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.stopPropagation()}
      >
        {label}
      </Link>
    </>
  );
}

function TypeCell({ row }: { row: RevisionDocument }) {
  const suggestion = row.classification.suggestion;
  let hint: string | null = null;
  if (suggestion && row.document_type === "UNKNOWN") {
    hint = `AI: ${documentTypeLabel(suggestion.predicted_type)} · ${confidenceBandLabel(suggestion.confidence_band)}`;
  } else if (suggestion && suggestion.predicted_type !== row.document_type) {
    hint = `AI suggests: ${documentTypeLabel(suggestion.predicted_type)}`;
  }
  return (
    <div>
      <p className="text-slate-700">{documentTypeLabel(row.document_type)}</p>
      {hint ? <p className="mt-0.5 text-[12px] text-slate-500">{hint}</p> : null}
    </div>
  );
}

function DocumentRow({
  row,
  first,
  selected,
  projectId,
  revisionId,
  canMutate,
  handlers,
  onOpen,
}: {
  row: RevisionDocument;
  first: boolean;
  selected: boolean;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  handlers: DocumentMenuHandlers;
  onOpen: (row: RevisionDocument) => void;
}) {
  const removed = row.status === "REMOVED";
  const facts = secondaryFacts(row, projectId);
  return (
    <tr
      tabIndex={0}
      aria-selected={selected}
      onClick={(event) => {
        event.currentTarget.focus();
        onOpen(row);
      }}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) {
          return;
        }
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(row);
        }
      }}
      className={revisionRowClass(first, selected, removed)}
    >
      <td className={revisionTable.primaryCell}>
        <p
          className={revisionPrimaryClass(removed)}
        >
          {row.document.original_filename}
        </p>
        <p className="mt-0.5 flex flex-wrap gap-x-1.5 text-[12px] text-slate-400">
          {facts.map((fact, index) => (
            <span key={index} className="inline-flex items-center gap-1.5">
              {index > 0 ? <span aria-hidden>·</span> : null}
              {fact}
            </span>
          ))}
        </p>
      </td>
      <td className={revisionTable.cell}>
        <TypeCell row={row} />
      </td>
      <td className={revisionTable.cell}>
        <DocumentState row={row} />
      </td>
      <td className={revisionTable.actionsCell}>
        <DocumentOverflowMenu
          row={row}
          projectId={projectId}
          revisionId={revisionId}
          canMutate={canMutate}
          handlers={handlers}
        />
      </td>
    </tr>
  );
}

export function DocumentList({
  rows,
  selectedId,
  projectId,
  revisionId,
  canMutate,
  loading,
  error,
  empty,
  handlers,
  onOpen,
  onRetry,
  onClearFilters,
  onUpload,
  onReuse,
}: {
  rows: RevisionDocument[] | null;
  selectedId: string | null;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  loading: boolean;
  error: string | null;
  empty: { text: string; kind: "revision" | "search" | "filters" | "view" } | null;
  handlers: DocumentMenuHandlers;
  onOpen: (row: RevisionDocument) => void;
  onRetry: () => void;
  onClearFilters: () => void;
  onUpload: () => void;
  onReuse: () => void;
}) {
  return (
    <Card>
      <table className={revisionTable.table}>
        <thead className={revisionTable.head}>
          <tr className={revisionTable.headerRow}>
            <th className={cn(TH, "px-5")}>Document</th>
            <th className={TH}>Type</th>
            <th className={TH}>State</th>
            <th className={cn(TH, "text-right")}>
              <span className="sr-only">More</span>
            </th>
          </tr>
        </thead>
        <tbody className={cn(loading && rows ? "opacity-60" : undefined)}>
          {rows === null && loading ? (
            [0, 1, 2].map((row) => (
              <tr key={row} data-testid="document-skeleton" className="border-t border-slate-100">
                <td colSpan={4} className="px-5 py-4">
                  <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
                </td>
              </tr>
            ))
          ) : error ? (
            <tr>
              <td colSpan={4}>
                <div className="flex flex-col items-center gap-2 py-14">
                  <p role="alert" className="text-[13.5px] text-red-600">
                    {error}
                  </p>
                  <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
                    Retry
                  </Button>
                </div>
              </td>
            </tr>
          ) : empty ? (
            <tr>
              <td colSpan={4}>
                <div className="flex flex-col items-center gap-2 py-16">
                  <p className="text-[13.5px] font-medium text-slate-400">{empty.text}</p>
                  {empty.kind === "filters" ? (
                    <button
                      type="button"
                      onClick={onClearFilters}
                      className="cursor-pointer text-[12.5px] text-accent hover:underline"
                    >
                      Clear filters
                    </button>
                  ) : null}
                  {empty.kind === "revision" && canMutate ? (
                    <AddDocumentsMenu onUpload={onUpload} onReuse={onReuse} />
                  ) : null}
                </div>
              </td>
            </tr>
          ) : (
            rows?.map((row, index) => (
              <DocumentRow
                key={row.id}
                row={row}
                first={index === 0}
                selected={row.id === selectedId}
                projectId={projectId}
                revisionId={revisionId}
                canMutate={canMutate}
                handlers={handlers}
                onOpen={onOpen}
              />
            ))
          )}
        </tbody>
      </table>
    </Card>
  );
}
