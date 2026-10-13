"use client";

import { useState } from "react";

import { DropdownMenu, type DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { apiErrorOf } from "@/lib/api";
import {
  canOpenInline,
  getDownloadUrl,
  type DownloadDisposition,
  type RevisionDocument,
} from "@/lib/documents";

export type DocumentMenuHandlers = {
  onViewPages: (row: RevisionDocument) => void;
  onEditMetadata: (row: RevisionDocument) => void;
  onReclassify: (row: RevisionDocument) => void;
  onRetryClassification: (row: RevisionDocument) => void;
  onRetryProcessing: (row: RevisionDocument) => void;
  onRemove: (row: RevisionDocument) => void;
  onRestore: (row: RevisionDocument) => void;
  onStateChanged: (message: string) => void;
};

function included(row: RevisionDocument): boolean {
  return row.status === "INCLUDED";
}

function inFlight(row: RevisionDocument): boolean {
  const status = row.classification.attempt?.status;
  return status === "PENDING" || status === "RUNNING";
}

export function canEditDocument(row: RevisionDocument, canMutate: boolean): boolean {
  return canMutate && included(row);
}

/** Reclassify and classification retry follow the document, not revision mutability. */
export function canReclassifyDocument(row: RevisionDocument): boolean {
  return (
    included(row) &&
    row.classification.enabled &&
    row.classification.suggestion != null &&
    !inFlight(row)
  );
}

export function canRetryClassification(row: RevisionDocument): boolean {
  return included(row) && row.classification.enabled && row.classification.attempt?.status === "FAILED";
}

export function DocumentOverflowMenu({
  row,
  projectId,
  revisionId,
  canMutate,
  handlers,
  triggerLabel,
}: {
  row: RevisionDocument;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  handlers: DocumentMenuHandlers;
  /** Visible text trigger. The row menu omits this and keeps the icon button. */
  triggerLabel?: string;
}) {
  const [busy, setBusy] = useState<DownloadDisposition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);
  const name = row.document.original_filename;

  async function run(disposition: DownloadDisposition) {
    setError(null);
    setBusy(disposition);
    const tab = disposition === "inline" ? window.open("", "_blank") : null;
    try {
      const { url } = await getDownloadUrl(projectId, revisionId, row.id, disposition);
      if (disposition === "inline") {
        if (tab) {
          tab.opener = null;
          tab.location.href = url;
        } else {
          window.open(url, "_blank", "noopener");
        }
      } else {
        window.location.assign(url);
      }
    } catch (err) {
      tab?.close();
      const { status, detail } = apiErrorOf(err);
      setError(detail);
      if (status === 404 || status === 409) {
        handlers.onStateChanged(detail);
      }
    } finally {
      setBusy(null);
    }
  }

  const items: DropdownMenuItem[] = [];
  if (row.processing?.status === "COMPLETED") {
    items.push({
      id: "pages",
      label: "View pages",
      disabled: busy !== null,
      onSelect: () => handlers.onViewPages(row),
    });
  }
  items.push({
    id: "download",
    label: busy === "attachment" ? "Preparing…" : "Download original",
    disabled: busy !== null,
    onSelect: () => void run("attachment"),
  });
  if (canOpenInline(row.document)) {
    items.push({
      id: "open",
      label: busy === "inline" ? "Opening…" : "Open original",
      disabled: busy !== null,
      onSelect: () => void run("inline"),
    });
  }
  if (canEditDocument(row, canMutate)) {
    items.push({
      id: "edit",
      label: "Edit metadata",
      onSelect: () => handlers.onEditMetadata(row),
    });
  }
  if (canReclassifyDocument(row)) {
    items.push({
      id: "reclassify",
      label: "Reclassify",
      onSelect: () => handlers.onReclassify(row),
    });
  }
  if (canRetryClassification(row)) {
    items.push({
      id: "retry-classification",
      label: "Retry classification",
      onSelect: () => handlers.onRetryClassification(row),
    });
  }
  if (row.processing?.status === "FAILED") {
    items.push({
      id: "retry-processing",
      label: "Retry processing",
      onSelect: () => handlers.onRetryProcessing(row),
    });
  }
  if (canEditDocument(row, canMutate)) {
    items.push({
      id: "remove",
      label: "Remove from revision",
      destructive: true,
      separatorBefore: true,
      onSelect: () => handlers.onRemove(row),
    });
  }
  if (canMutate && !included(row)) {
    items.push({
      id: "restore",
      label: "Restore to revision",
      disabled: restoring,
      onSelect: () => {
        setRestoring(true);
        void Promise.resolve(handlers.onRestore(row)).finally(() => setRestoring(false));
      },
    });
  }

  return (
    <div
      className="inline-flex flex-col items-end gap-1"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <DropdownMenu
        items={items}
        label={`Actions for ${name}`}
        triggerLabel={triggerLabel}
        disabled={restoring}
      />
      {error ? (
        <p role="alert" className="max-w-56 text-right text-[11.5px] text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}
