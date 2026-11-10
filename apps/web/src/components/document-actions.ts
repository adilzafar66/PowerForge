"use client";

import { useState } from "react";

import { apiErrorOf } from "@/lib/api";
import {
  getDownloadUrl,
  type DownloadDisposition,
  type RevisionDocument,
} from "@/lib/documents";

function included(row: RevisionDocument): boolean {
  return row.status === "INCLUDED";
}

function inFlight(row: RevisionDocument): boolean {
  const status = row.classification.attempt?.status;
  return status === "PENDING" || status === "RUNNING";
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

/** Opens or downloads the original through a short-lived signed URL. */
export function useOriginalFile(
  projectId: string,
  revisionId: string,
  revisionDocumentId: string,
  onStateChanged?: (message: string) => void,
) {
  const [busy, setBusy] = useState<DownloadDisposition | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(disposition: DownloadDisposition) {
    setError(null);
    setBusy(disposition);
    const tab = disposition === "inline" ? window.open("", "_blank") : null;
    try {
      const { url } = await getDownloadUrl(
        projectId,
        revisionId,
        revisionDocumentId,
        disposition,
      );
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

  return { busy, error, run };
}
