"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useId,
  useState,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, RotateCcw, Trash2, X } from "lucide-react";

import { DocumentClassificationPanel } from "@/components/document-classification-panel";
import {
  DocumentMetadataPanel,
  DocumentTypeSection,
} from "@/components/document-metadata-panel";
import {
  useOriginalFile,
  type DocumentMenuHandlers,
} from "@/components/document-overflow-menu";
import { DocumentProcessingPanel } from "@/components/document-processing-panel";
import { docButtonClass, StatusChip } from "@/components/documents-ui";
import { MixedDocumentPageTypes } from "@/components/mixed-document-page-types";
import { AsyncState } from "@/components/ui/async-state";
import { Sheet } from "@/components/ui/sheet";
import { documentStatusChip } from "@/lib/document-presentation";
import {
  formatFileSize,
  getClassification,
  type DocumentUpdateInput,
  type RevisionDocument,
} from "@/lib/documents";
import { formatDateShort } from "@/lib/projects";
import { isRunning, jobInterval } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

export function DocumentInspector({
  row,
  projectId,
  revisionId,
  canMutate,
  classifying,
  retrying,
  aiError,
  processingError,
  focusMetadata,
  handlers,
  notice,
  onRequestClose,
  onMetadataFocused,
  onAccept,
  onReclassify,
  onRetryClassification,
  onRetryProcessing,
  onViewPages,
  onSave,
  onDirtyChange,
}: {
  row: RevisionDocument;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  classifying: boolean;
  retrying: boolean;
  aiError: string | null;
  processingError: string | null;
  focusMetadata: boolean;
  handlers: DocumentMenuHandlers;
  /** Workspace messages, which the overlay would otherwise hide. */
  notice?: ReactNode;
  /** The caller decides whether unsaved edits allow the close. */
  onRequestClose: () => void;
  onMetadataFocused: () => void;
  onAccept: () => void;
  onReclassify: () => void;
  onRetryClassification: () => void;
  onRetryProcessing: () => void;
  onViewPages: (pageNumber?: number) => void;
  onSave: (input: DocumentUpdateInput) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const titleId = useId();
  const [typeOpen, setTypeOpen] = useState(false);
  const [typeDirty, setTypeDirty] = useState(false);
  const [metadataDirty, setMetadataDirty] = useState(false);
  const dirty = typeDirty || metadataDirty;
  const download = useOriginalFile(
    projectId,
    revisionId,
    row.id,
    handlers.onStateChanged,
  );
  const [restoring, setRestoring] = useState(false);
  const classification = useQuery({
    queryKey: [
      ...keys.document(projectId, revisionId, row.id),
      "classification",
      row.classification,
    ],
    queryFn: () => getClassification(projectId, revisionId, row.id),
    refetchInterval: (query) =>
      jobInterval(
        isRunning(query.state.data?.attempt?.status),
        query.state.fetchFailureCount,
      ),
  });
  const detail = classification.data ?? null;

  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  const file = row.document;
  const facts = [formatFileSize(file.size_bytes)];
  if (row.processing?.pages_total != null) {
    const count = row.processing.pages_total;
    facts.push(`${count} ${count === 1 ? "page" : "pages"}`);
  }
  facts.push(formatDateShort(row.added_at));
  const chip = documentStatusChip(row);
  const mixed =
    row.document_type === "MIXED_DOCUMENT" ||
    row.classification.suggestion?.predicted_type === "MIXED_DOCUMENT";
  const removed = row.status === "REMOVED";
  const chooseType = useCallback(() => setTypeOpen(true), []);

  return (
    <Sheet
      labelledBy={titleId}
      onClose={onRequestClose}
      presentation="workspace-revision"
      className="w-[min(var(--pf-documents-inspector),100%)] leading-[inherit] max-[650px]:w-full"
    >
      <div className="flex items-start justify-between gap-3.5 border-b border-border px-[21px] pt-[18px] pb-4">
        <div className="min-w-0">
          <h2
            id={titleId}
            className="m-0 text-workspace-section leading-[1.5] font-semibold [overflow-wrap:anywhere] text-ink"
          >
            {file.original_filename}
          </h2>
          <p className="m-0 mt-[5px] text-workspace-caption text-muted">
            {facts.join(" · ")}
          </p>
        </div>
        <button
          type="button"
          aria-label="Close details"
          onClick={onRequestClose}
          className={cn(docButtonClass(), "size-[34px] shrink-0 px-0")}
        >
          <X aria-hidden strokeWidth={1.9} />
        </button>
      </div>
      {notice}
      <div className="min-h-0 flex-1 overflow-y-auto px-[22px] pb-[26px]">
        <AsyncState
          pending={classification.isPending}
          error={classification.error}
          retry={classification.refetch}
        />
        <DocumentTypeSection
          row={row}
          canMutate={canMutate}
          open={typeOpen}
          onOpen={chooseType}
          onSave={onSave}
          onDirtyChange={setTypeDirty}
        >
          <div className="mb-3.5 flex items-center justify-between gap-3">
            <StatusChip tone={chip.tone}>{chip.label}</StatusChip>
            <OriginLine row={row} projectId={projectId} />
          </div>
        </DocumentTypeSection>
        <DocumentProcessingPanel
          row={row}
          busy={retrying}
          error={processingError}
          onViewPages={() => onViewPages()}
          onRetry={onRetryProcessing}
        />
        <DocumentClassificationPanel
          row={row}
          detail={detail}
          canMutate={canMutate}
          busy={classifying}
          error={aiError}
          onAccept={onAccept}
          onChooseType={chooseType}
          onReclassify={onReclassify}
          onRetry={onRetryClassification}
        >
          {mixed ? (
            <MixedDocumentPageTypes
              projectId={projectId}
              revisionId={revisionId}
              revisionDocumentId={row.id}
              onOpenPage={(pageNumber) => onViewPages(pageNumber)}
            />
          ) : null}
        </DocumentClassificationPanel>
        <DocumentMetadataPanel
          row={row}
          canMutate={canMutate}
          focusField={focusMetadata}
          onFocused={onMetadataFocused}
          onSave={onSave}
          onDirtyChange={setMetadataDirty}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-[9px] border-t border-border px-[19px] py-[13px]">
        <div className="min-w-0">
          <button
            type="button"
            className={docButtonClass()}
            disabled={download.busy !== null}
            onClick={() => void download.run("attachment")}
          >
            <Download aria-hidden strokeWidth={1.8} />
            {download.busy === "attachment" ? "Preparing…" : "Download"}
          </button>
          {download.error ? (
            <p
              role="alert"
              className="m-0 mt-1.5 text-workspace-caption text-danger"
            >
              {download.error}
            </p>
          ) : null}
        </div>
        {!canMutate ? (
          <StatusChip tone="gray">Read-only</StatusChip>
        ) : removed ? (
          <button
            type="button"
            className={docButtonClass()}
            disabled={restoring}
            onClick={() => {
              setRestoring(true);
              void Promise.resolve(handlers.onRestore(row)).finally(() =>
                setRestoring(false),
              );
            }}
          >
            <RotateCcw aria-hidden strokeWidth={1.8} />
            Restore
          </button>
        ) : (
          <button
            type="button"
            className={docButtonClass("danger")}
            onClick={() => handlers.onRemove(row)}
          >
            <Trash2 aria-hidden strokeWidth={1.8} />
            Remove
          </button>
        )}
      </div>
    </Sheet>
  );
}

function OriginLine({
  row,
  projectId,
}: {
  row: RevisionDocument;
  projectId: string;
}) {
  const className = "m-0 text-right text-workspace-caption text-muted";
  if (row.origin !== "INHERITED") {
    return <p className={className}>Uploaded in this revision</p>;
  }
  const identifier = row.inherited_from_revision_identifier;
  if (!identifier) {
    return <p className={className}>Inherited</p>;
  }
  const label = `Rev ${identifier}`;
  return (
    <p className={className}>
      Inherited from{" "}
      {row.inherited_from_revision_id ? (
        <Link
          href={`/projects/${projectId}/revisions/${row.inherited_from_revision_id}`}
          className="text-accent hover:underline"
        >
          {label}
        </Link>
      ) : (
        label
      )}
    </p>
  );
}
