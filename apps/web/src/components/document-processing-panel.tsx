"use client";

import { FileStack, RefreshCw } from "lucide-react";

import { CellStateView } from "@/components/document-list";
import { docButtonClass, InspectorSection } from "@/components/documents-ui";
import { processingCell } from "@/lib/document-presentation";
import type { RevisionDocument } from "@/lib/documents";

function processingNote(row: RevisionDocument): string {
  const status = row.processing?.status;
  if (status === "COMPLETED") return "Page artifacts are available for review.";
  if (status === "FAILED")
    return "The latest processing attempt failed. Existing data remains available.";
  if (status === "RUNNING") return "Pages are being rendered and read.";
  if (status === "PENDING") return "Waiting for a processing worker.";
  return "Awaiting processing.";
}

export function DocumentProcessingPanel({
  row,
  busy,
  error,
  onViewPages,
  onRetry,
}: {
  row: RevisionDocument;
  busy: boolean;
  error: string | null;
  onViewPages: () => void;
  onRetry: () => void;
}) {
  const processing = row.processing;
  return (
    <InspectorSection title="Processing">
      <CellStateView
        state={processingCell(row)}
        progressLabel={`Processing progress for ${row.document.original_filename}`}
      />
      <p className="m-0 mt-2.5 text-workspace-caption text-muted">
        {processingNote(row)}
      </p>
      {processing?.status === "FAILED" && processing.error_message ? (
        <p className="m-0 mt-1.5 text-workspace-caption text-danger">
          {processing.error_message}
        </p>
      ) : null}
      <div className="mt-[15px] flex flex-wrap gap-2">
        {processing?.status === "FAILED" ? (
          <button
            type="button"
            className={docButtonClass("tiny")}
            onClick={onRetry}
            disabled={busy}
          >
            <RefreshCw aria-hidden strokeWidth={1.8} />
            Retry processing
          </button>
        ) : null}
        <button
          type="button"
          className={docButtonClass("tiny")}
          onClick={onViewPages}
        >
          <FileStack aria-hidden strokeWidth={1.8} />
          View pages / evidence
        </button>
      </div>
      {error ? (
        <p role="alert" className="m-0 mt-2 text-workspace-caption text-danger">
          {error}
        </p>
      ) : null}
    </InspectorSection>
  );
}
