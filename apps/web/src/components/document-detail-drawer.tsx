"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";

import {
  DocumentOverflowMenu,
  type DocumentMenuHandlers,
} from "@/components/document-overflow-menu";
import { DocumentOverview } from "@/components/document-overview";
import { Sheet } from "@/components/ui/sheet";
import {
  formatFileSize,
  getClassification,
  type ClassificationDetail,
  type DocumentUpdateInput,
  type RevisionDocument,
} from "@/lib/documents";

export function DocumentDetailDrawer({
  row,
  projectId,
  revisionId,
  canMutate,
  detailVersion,
  classifying,
  retrying,
  aiError,
  processingError,
  focusMetadata,
  handlers,
  onClose,
  onMetadataFocused,
  onAccept,
  onReclassify,
  onRetryClassification,
  onRetryProcessing,
  onViewPages,
  onSave,
}: {
  row: RevisionDocument;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  detailVersion: number;
  classifying: boolean;
  retrying: boolean;
  aiError: string | null;
  processingError: string | null;
  focusMetadata: boolean;
  handlers: DocumentMenuHandlers;
  onClose: () => void;
  onMetadataFocused: () => void;
  onAccept: () => void;
  onReclassify: () => void;
  onRetryClassification: () => void;
  onRetryProcessing: () => void;
  onViewPages: (pageNumber?: number) => void;
  onSave: (input: DocumentUpdateInput) => Promise<void>;
}) {
  const titleId = useId();
  const [detail, setDetail] = useState<ClassificationDetail | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    getClassification(projectId, revisionId, row.id)
      .then((value) => {
        if (!cancelled) {
          setDetail(value);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDetail(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, revisionId, row.id, detailVersion]);

  const file = row.document;
  const headerFacts = [formatFileSize(file.size_bytes)];
  if (row.processing?.pages_total != null) {
    const count = row.processing.pages_total;
    headerFacts.push(`${count} ${count === 1 ? "page" : "pages"}`);
  }
  if (row.document_number) {
    headerFacts.push(row.document_number);
  }

  return (
    <Sheet modal={false} onClose={onClose} labelledBy={titleId}>
      <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="min-w-0">
          <h2
            id={titleId}
            className="truncate text-[16px] font-semibold text-slate-900"
          >
            {file.original_filename}
          </h2>
          <p className="mt-0.5 text-[12.5px] text-slate-500">
            {headerFacts.join(" · ")}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <DocumentOverflowMenu
            row={row}
            projectId={projectId}
            revisionId={revisionId}
            canMutate={canMutate}
            handlers={handlers}
            triggerLabel="More"
          />
          <button
            type="button"
            aria-label="Close details"
            onClick={onClose}
            className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </header>
      <DocumentOverview
        row={row}
        projectId={projectId}
        revisionId={revisionId}
        canMutate={canMutate}
        detail={detail}
        classifying={classifying}
        retrying={retrying}
        aiError={aiError}
        processingError={processingError}
        focusMetadata={focusMetadata}
        onMetadataFocused={onMetadataFocused}
        onAccept={onAccept}
        onReclassify={onReclassify}
        onRetryClassification={onRetryClassification}
        onRetryProcessing={onRetryProcessing}
        onViewPages={onViewPages}
        onOpenPage={(pageNumber) => onViewPages(pageNumber)}
        onSave={onSave}
      />
    </Sheet>
  );
}
