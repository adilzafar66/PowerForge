"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, type DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { apiErrorOf } from "@/lib/api";
import {
  canOpenInline,
  getDownloadUrl,
  type DownloadDisposition,
  type RevisionDocument,
} from "@/lib/documents";

type Props = {
  projectId: string;
  revisionId: string;
  document: RevisionDocument;
  /** Called when the server says the revision or document changed (404 or 409). */
  onStateChanged?: (message: string) => void;
  /** When false the menu offers View details only. */
  canMutate?: boolean;
  onEdit?: (document: RevisionDocument) => void;
  onRemove?: (document: RevisionDocument) => void;
  /** Resolves when the restore has finished; errors are reported by the owner. */
  onRestore?: (document: RevisionDocument) => Promise<void>;
};

export function DocumentRowActions({
  projectId,
  revisionId,
  document,
  onStateChanged,
  canMutate = false,
  onEdit,
  onRemove,
  onRestore,
}: Props) {
  const [busy, setBusy] = useState<DownloadDisposition | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(disposition: DownloadDisposition) {
    setError(null);
    setBusy(disposition);
    // A tab opened inside the click handler is not treated as a popup after the await.
    const tab = disposition === "inline" ? window.open("", "_blank") : null;
    try {
      const { url } = await getDownloadUrl(projectId, revisionId, document.id, disposition);
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
        onStateChanged?.(detail);
      }
    } finally {
      setBusy(null);
    }
  }

  const name = document.document.original_filename;
  const [restoring, setRestoring] = useState(false);
  const included = document.status === "INCLUDED";

  const menuItems: DropdownMenuItem[] = [
    {
      id: "details",
      label: canMutate && included ? "Edit details" : "View details",
      onSelect: () => onEdit?.(document),
    },
  ];
  if (canMutate && included) {
    menuItems.push({
      id: "remove",
      label: "Remove from this revision",
      destructive: true,
      separatorBefore: true,
      onSelect: () => onRemove?.(document),
    });
  }
  if (canMutate && !included) {
    menuItems.push({
      id: "restore",
      label: "Restore",
      onSelect: () => {
        setRestoring(true);
        void (onRestore?.(document) ?? Promise.resolve()).finally(() => setRestoring(false));
      },
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5">
        {canOpenInline(document.document) ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy !== null}
            aria-label={`Open ${name}`}
            onClick={() => void run("inline")}
          >
            {busy === "inline" ? "Opening…" : "Open"}
          </Button>
        ) : null}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy !== null}
          aria-label={`Download ${name}`}
          onClick={() => void run("attachment")}
        >
          {busy === "attachment" ? "Preparing…" : "Download"}
        </Button>
        <DropdownMenu
          items={menuItems}
          label={`Actions for ${name}`}
          disabled={restoring}
        />
      </div>
      {error ? (
        <p role="alert" className="max-w-56 text-right text-[11.5px] text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}
