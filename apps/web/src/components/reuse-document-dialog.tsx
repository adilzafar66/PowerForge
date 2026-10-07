"use client";

import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { fieldClassName } from "@/components/ui/input";
import { apiErrorOf } from "@/lib/api";
import {
  documentTypeLabel,
  formatFileSize,
  isReadOnlyErrorCode,
  listDocuments,
  restoreDocument,
  reuseDocument,
  type RevisionDocument,
} from "@/lib/documents";
import { listRevisions, type Revision } from "@/lib/projects";
import { REVISION_STATUS_STYLES } from "@/lib/status-styles";
import { cn } from "@/lib/utils";

type Props = {
  projectId: string;
  revisionId: string;
  onClose: () => void;
  /** Called after each batch with the number of documents added (or restored) in it. */
  onChanged: (count: number) => void;
  onReadOnly: (message: string) => void;
};

type Result =
  | { kind: "added" }
  | { kind: "failed"; message: string; restoreId?: string }
  | { kind: "restored" }
  | { kind: "not_sent"; message: string };

type Presence = "INCLUDED" | "REMOVED";

export function ReuseDocumentDialog({
  projectId,
  revisionId,
  onClose,
  onChanged,
  onReadOnly,
}: Props) {
  const titleId = useId();
  const [revisions, setRevisions] = useState<Revision[] | null>(null);
  const [sourceId, setSourceId] = useState("");
  const [sourceDocs, setSourceDocs] = useState<RevisionDocument[] | null>(null);
  const [present, setPresent] = useState<Map<string, Presence>>(new Map());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [results, setResults] = useState<Map<string, Result>>(new Map());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    listRevisions(projectId)
      .then((all) => {
        if (cancelled) {
          return;
        }
        const others = all.filter((revision) => revision.id !== revisionId);
        setRevisions(others);
        setSourceId(others[0]?.id ?? "");
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(apiErrorOf(err).detail);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, revisionId]);

  useEffect(() => {
    if (!sourceId) {
      return;
    }
    let cancelled = false;
    setSourceDocs(null);
    setSelected(new Set());
    setResults(new Map());
    setLoadError(null);
    Promise.all([
      listDocuments(projectId, sourceId, { status: "INCLUDED" }),
      listDocuments(projectId, revisionId, { status: "ALL" }),
    ])
      .then(([source, current]) => {
        if (cancelled) {
          return;
        }
        setSourceDocs(source);
        setPresent(new Map(current.map((row) => [row.document.id, row.status])));
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(apiErrorOf(err).detail);
          setSourceDocs([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, revisionId, sourceId]);

  const sourceRevision = revisions?.find((revision) => revision.id === sourceId);

  function reasonUnavailable(row: RevisionDocument): string | null {
    if (results.get(row.id)?.kind === "added") {
      return "Added";
    }
    const state = present.get(row.document.id);
    if (state === "INCLUDED") {
      return "Already in this revision";
    }
    if (state === "REMOVED") {
      return "Removed from this revision. Restore it from the Removed view.";
    }
    return null;
  }

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function addSelected() {
    if (!sourceDocs) {
      return;
    }
    setAdding(true);
    const queue = sourceDocs.filter((row) => selected.has(row.id));
    let changed = 0;
    const next = new Map(results);
    const addedIds = new Set<string>();
    for (let index = 0; index < queue.length; index += 1) {
      const row = queue[index];
      try {
        await reuseDocument(projectId, revisionId, { source_revision_document_id: row.id });
        next.set(row.id, { kind: "added" });
        addedIds.add(row.id);
        changed += 1;
      } catch (err) {
        const { code, detail, error } = apiErrorOf(err);
        if (isReadOnlyErrorCode(code)) {
          next.set(row.id, { kind: "failed", message: detail });
          for (const unsent of queue.slice(index + 1)) {
            next.set(unsent.id, { kind: "not_sent", message: "Not added. " + detail });
          }
          setResults(new Map(next));
          setAdding(false);
          onReadOnly(detail);
          onChanged(changed);
          return;
        }
        next.set(row.id, {
          kind: "failed",
          message: detail,
          restoreId:
            code === "document_already_in_revision" && error?.existing_status === "REMOVED"
              ? error.existing_revision_document_id
              : undefined,
        });
      }
    }
    setResults(next);
    setSelected((current) => new Set([...current].filter((id) => !addedIds.has(id))));
    setAdding(false);
    onChanged(changed);
  }

  async function restoreExisting(row: RevisionDocument, existingId: string) {
    try {
      await restoreDocument(projectId, revisionId, existingId);
      setResults((current) => new Map(current).set(row.id, { kind: "restored" }));
      setPresent((current) => new Map(current).set(row.document.id, "INCLUDED"));
      onChanged(1);
    } catch (err) {
      setResults((current) =>
        new Map(current).set(row.id, { kind: "failed", message: apiErrorOf(err).detail }),
      );
    }
  }

  const selectable = (sourceDocs ?? []).filter((row) => !reasonUnavailable(row));
  const selectedCount = selectable.filter((row) => selected.has(row.id)).length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25 backdrop-blur-[2px]"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[90vh] w-[640px] flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_24px_48px_rgba(0,0,0,0.12),0_4px_8px_rgba(0,0,0,0.06)]"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id={titleId} className="mb-1 text-[16px] font-semibold text-slate-900">
          Add from another revision
        </h2>
        <p className="mb-4 text-[13px] text-slate-500">
          Pick documents from another revision of this project. The file is shared, not copied, and
          its details are copied so you can edit them here.
        </p>

        {revisions === null && !loadError ? (
          <p className="text-[13px] text-slate-400">Loading revisions…</p>
        ) : null}

        {revisions && revisions.length === 0 ? (
          <p className="text-[13px] text-slate-500">This project has no other revisions.</p>
        ) : null}

        {revisions && revisions.length > 0 ? (
          <>
            <label className="mb-3 flex items-center gap-2 text-[12.5px] font-medium text-slate-600">
              Source revision
              <select
                aria-label="Source revision"
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value)}
                disabled={adding}
                className={cn(fieldClassName, "w-auto py-1.5 text-[13px]")}
              >
                {revisions.map((revision) => (
                  <option key={revision.id} value={revision.id}>
                    {`Revision ${revision.identifier} (${REVISION_STATUS_STYLES[revision.status].label})`}
                  </option>
                ))}
              </select>
            </label>

            {loadError ? (
              <p role="alert" className="mb-2 text-[13px] text-red-600">
                {loadError}
              </p>
            ) : null}

            <div className="min-h-[80px] flex-1 overflow-y-auto rounded-xl border border-slate-200">
              {sourceDocs === null ? (
                <p className="px-4 py-6 text-[13px] text-slate-400">Loading documents…</p>
              ) : sourceDocs.length === 0 ? (
                <p className="px-4 py-6 text-[13px] text-slate-400">
                  No included documents in Revision {sourceRevision?.identifier}.
                </p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {sourceDocs.map((row) => (
                    <SourceRow
                      key={row.id}
                      row={row}
                      unavailable={reasonUnavailable(row)}
                      checked={selected.has(row.id)}
                      result={results.get(row.id)}
                      disabled={adding}
                      onToggle={() => toggle(row.id)}
                      onRestore={(existingId) => void restoreExisting(row, existingId)}
                    />
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : null}

        {revisions === null && loadError ? (
          <p role="alert" className="text-[13px] text-red-600">
            {loadError}
          </p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button
            type="button"
            disabled={selectedCount === 0 || adding}
            onClick={() => void addSelected()}
          >
            {adding
              ? "Adding…"
              : `Add ${selectedCount} ${selectedCount === 1 ? "document" : "documents"}`}
          </Button>
        </div>
      </div>
    </div>
  );
}

function SourceRow({
  row,
  unavailable,
  checked,
  result,
  disabled,
  onToggle,
  onRestore,
}: {
  row: RevisionDocument;
  unavailable: string | null;
  checked: boolean;
  result: Result | undefined;
  disabled: boolean;
  onToggle: () => void;
  onRestore: (existingId: string) => void;
}) {
  const name = row.document.original_filename;
  return (
    <li className="flex items-start gap-3 px-4 py-2.5 text-[13px]">
      <input
        type="checkbox"
        aria-label={`Select ${name}`}
        checked={checked}
        disabled={disabled || !!unavailable}
        onChange={onToggle}
        className="mt-1"
      />
      <div className="min-w-0 flex-1">
        <p className={cn("font-medium break-all", unavailable ? "text-slate-400" : "text-slate-800")}>
          {name}
        </p>
        <p className="text-[12px] text-slate-400">
          {documentTypeLabel(row.document_type)} · {formatFileSize(row.document.size_bytes)}
        </p>
        {unavailable && result?.kind !== "added" && result?.kind !== "restored" ? (
          <p className="mt-0.5 text-[12px] text-slate-500">{unavailable}</p>
        ) : null}
        {result?.kind === "added" ? (
          <p className="mt-0.5 text-[12px] text-emerald-700">Added</p>
        ) : null}
        {result?.kind === "restored" ? (
          <p className="mt-0.5 text-[12px] text-emerald-700">Restored</p>
        ) : null}
        {result?.kind === "failed" || result?.kind === "not_sent" ? (
          <p className="mt-0.5 text-[12px] text-red-600">{result.message}</p>
        ) : null}
      </div>
      {result?.kind === "failed" && result.restoreId ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          aria-label={`Restore ${name}`}
          onClick={() => onRestore(result.restoreId as string)}
        >
          Restore
        </Button>
      ) : null}
    </li>
  );
}
