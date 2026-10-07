"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
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
};

export function DocumentRowActions({ projectId, revisionId, document, onStateChanged }: Props) {
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
      </div>
      {error ? (
        <p role="alert" className="max-w-56 text-right text-[11.5px] text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}
