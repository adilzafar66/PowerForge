"use client";

import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  Clock3,
  FileSearch,
  FileText,
  LoaderCircle,
  TriangleAlert,
} from "lucide-react";

import {
  DocumentOverflowMenu,
  type DocumentMenuHandlers,
} from "@/components/document-overflow-menu";
import { AddDocumentsMenu } from "@/components/document-workspace-toolbar";
import { docButtonClass, ProgressBar } from "@/components/documents-ui";
import {
  classificationCell,
  processingCell,
  type CellState,
  type CellTone,
} from "@/lib/document-presentation";
import {
  documentTypeLabel,
  formatFileSize,
  originLabel,
  type RevisionDocument,
} from "@/lib/documents";
import { formatDateShort } from "@/lib/projects";
import { cn } from "@/lib/utils";

const TH =
  "border-b border-border bg-[#f8fafb] px-[15px] py-3.5 text-left text-workspace-overline font-bold tracking-[0.62px] text-[var(--pf-text-tertiary)] uppercase";
const TD =
  "border-t border-[var(--pf-documents-row-border)] p-[15px] align-middle text-workspace-label";

const TONE_CLASS: Record<CellTone, string> = {
  ready: "text-positive",
  running: "text-accent",
  failed: "text-danger",
  pending: "text-warning",
  review: "text-warning",
  neutral: "text-muted",
};

function ToneIcon({ tone }: { tone: CellTone }) {
  const props = { "aria-hidden": true, strokeWidth: 1.9, className: "size-3.5 shrink-0" };
  if (tone === "ready") return <CircleCheck {...props} />;
  if (tone === "running")
    return (
      <LoaderCircle
        {...props}
        className={cn(props.className, "animate-spin motion-reduce:animate-none")}
      />
    );
  if (tone === "failed") return <CircleAlert {...props} />;
  if (tone === "pending") return <Clock3 {...props} />;
  if (tone === "review") return <TriangleAlert {...props} />;
  return <CircleDashed {...props} />;
}

export function CellStateView({
  state,
  progressLabel,
}: {
  state: CellState;
  progressLabel?: string;
}) {
  const dash = state.label === "—";
  return (
    <div className="min-w-0">
      <p
        className={cn(
          "m-0 flex items-center gap-1.5 text-workspace-label font-semibold",
          TONE_CLASS[state.tone],
        )}
      >
        {dash ? (
          <>
            <span aria-hidden>—</span>
            <span className="sr-only">{state.srLabel}</span>
          </>
        ) : (
          <>
            <ToneIcon tone={state.tone} />
            {state.label}
          </>
        )}
      </p>
      {state.detail ? (
        <p className="m-0 mt-[3px] text-workspace-caption text-muted">
          {state.detail}
        </p>
      ) : null}
      {state.progress != null && progressLabel ? (
        <ProgressBar value={state.progress} label={progressLabel} />
      ) : null}
    </div>
  );
}

function documentMeta(row: RevisionDocument): string {
  const facts = [];
  if (row.document_number) facts.push(row.document_number);
  facts.push(formatFileSize(row.document.size_bytes));
  if (row.processing?.pages_total != null) {
    const count = row.processing.pages_total;
    facts.push(`${count} ${count === 1 ? "page" : "pages"}`);
  }
  return facts.join(" · ");
}

export function FileIcon({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex h-10 w-[35px] shrink-0 items-center justify-center rounded-[var(--pf-radius-control)] border border-[var(--pf-documents-file-border)] bg-[var(--pf-documents-file-surface)] text-accent",
        className,
      )}
    >
      <FileText className="size-[18px]" strokeWidth={1.7} />
    </span>
  );
}

function DocumentRow({
  row,
  selected,
  projectId,
  revisionId,
  canMutate,
  handlers,
  onOpen,
}: {
  row: RevisionDocument;
  selected: boolean;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  handlers: DocumentMenuHandlers;
  onOpen: (row: RevisionDocument) => void;
}) {
  const removed = row.status === "REMOVED";
  const name = row.document.original_filename;
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
      className={cn(
        "cursor-pointer outline-none transition-colors duration-150 hover:bg-[var(--pf-equipment-row-hover)] focus-visible:[box-shadow:inset_0_0_0_2px_var(--pf-ring)]",
        selected &&
          "bg-[var(--pf-documents-row-selected)] hover:bg-[var(--pf-documents-row-selected)]",
        removed && "opacity-[0.68]",
      )}
    >
      <td className={TD}>
        <div className="flex min-w-0 items-center gap-[11px]">
          <FileIcon />
          <div className="min-w-0">
            <p
              title={name}
              className={cn(
                "m-0 truncate text-workspace-label font-semibold text-ink",
                removed && "line-through decoration-[var(--pf-text-tertiary)]",
              )}
            >
              {name}
            </p>
            <p className="m-0 mt-1 truncate text-workspace-caption text-muted">
              {documentMeta(row)}
            </p>
          </div>
        </div>
      </td>
      <td className={cn(TD, "font-semibold text-ink [overflow-wrap:anywhere]")}>
        {documentTypeLabel(row.document_type)}
      </td>
      <td className={TD}>
        <CellStateView
          state={processingCell(row)}
          progressLabel={`Processing progress for ${name}`}
        />
      </td>
      <td className={TD}>
        <CellStateView state={classificationCell(row)} />
      </td>
      <td className={cn(TD, "text-ink")}>
        <p className="m-0">{originLabel(row.origin)}</p>
        <p className="m-0 mt-[3px] text-workspace-caption text-muted">
          {formatDateShort(row.added_at)}
        </p>
      </td>
      <td className={cn(TD, "pr-3 pl-0 text-right")}>
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

export type DocumentEmptyState = {
  text: string;
  kind: "revision" | "search" | "filters" | "view";
};

const EMPTY_HINTS: Record<DocumentEmptyState["kind"], string> = {
  revision: "Upload source files or add documents from another revision.",
  search: "Try a different file name, document number or description.",
  filters: "Adjust or clear the filters to see more documents.",
  view: "Nothing in this view right now.",
};

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
  footer,
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
  empty: DocumentEmptyState | null;
  handlers: DocumentMenuHandlers;
  footer: string | null;
  onOpen: (row: RevisionDocument) => void;
  onRetry: () => void;
  onClearFilters: () => void;
  onUpload: () => void;
  onReuse: () => void;
}) {
  return (
    <>
      {rows !== null && error && (
        <div
          role="alert"
          className="flex items-center gap-3 border-b border-border px-5 py-3 text-workspace-label text-danger"
        >
          {error}
          <button type="button" className={docButtonClass("tiny")} onClick={onRetry}>
            Retry
          </button>
        </div>
      )}
      <div className="relative overflow-x-auto">
        <table
          className={cn(
            "w-full table-fixed border-collapse max-[1100px]:min-w-[860px]",
            loading && rows ? "opacity-60" : undefined,
          )}
        >
          <colgroup>
            <col className="w-[34%]" />
            <col className="w-[18%]" />
            <col className="w-[16%]" />
            <col className="w-[17%]" />
            <col className="w-[11%]" />
            <col className="w-[4%] min-w-12" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className={TH}>
                Document
              </th>
              <th scope="col" className={TH}>
                Confirmed type
              </th>
              <th scope="col" className={TH}>
                Processing
              </th>
              <th scope="col" className={TH}>
                AI classification
              </th>
              <th scope="col" className={TH}>
                Origin
              </th>
              <th scope="col" className={TH}>
                <span className="sr-only">More</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows === null && loading ? (
              [0, 1, 2].map((row) => (
                <tr key={row} data-testid="document-skeleton">
                  <td colSpan={6} className={TD}>
                    <div className="flex items-center gap-[11px]">
                      <span className="h-10 w-[35px] animate-pulse rounded-[var(--pf-radius-control)] bg-soft" />
                      <span className="h-3.5 w-1/3 animate-pulse rounded bg-soft" />
                    </div>
                  </td>
                </tr>
              ))
            ) : error && rows === null ? (
              <tr>
                <td colSpan={6}>
                  <div className="flex flex-col items-center gap-2 px-5 py-[65px] text-center">
                    <p role="alert" className="m-0 text-workspace-body text-danger">
                      {error}
                    </p>
                    <button type="button" className={docButtonClass()} onClick={onRetry}>
                      Retry
                    </button>
                  </div>
                </td>
              </tr>
            ) : empty ? (
              <tr>
                <td colSpan={6}>
                  <div className="flex flex-col items-center px-5 py-[65px] text-center">
                    <FileSearch
                      aria-hidden
                      className="size-7 text-[#a8b9c5]"
                      strokeWidth={1.6}
                    />
                    <h3 className="m-0 mt-2.5 mb-[5px] text-workspace-body font-semibold text-ink">
                      {empty.text}
                    </h3>
                    <p className="m-0 text-workspace-caption text-muted">
                      {EMPTY_HINTS[empty.kind]}
                    </p>
                    {empty.kind === "filters" ? (
                      <button
                        type="button"
                        onClick={onClearFilters}
                        className={cn(docButtonClass(), "mt-3.5")}
                      >
                        Clear filters
                      </button>
                    ) : null}
                    {empty.kind === "revision" && canMutate ? (
                      <AddDocumentsMenu
                        onUpload={onUpload}
                        onReuse={onReuse}
                        className="mt-3.5"
                      />
                    ) : null}
                  </div>
                </td>
              </tr>
            ) : (
              rows?.map((row) => (
                <DocumentRow
                  key={row.id}
                  row={row}
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
      </div>
      {footer ? (
        <div className="flex flex-wrap justify-between gap-2.5 border-t border-border px-5 py-3 text-workspace-caption text-muted">
          <span>{footer}</span>
          <span className="max-[650px]:hidden">
            Click a row to inspect details · Ordered by date added
          </span>
        </div>
      ) : null}
    </>
  );
}
