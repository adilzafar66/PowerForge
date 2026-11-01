"use client";

import { Checkbox } from "@/components/ui/checkbox";

import { Select } from "@/components/ui/select";

import { useQuery } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { useEffect, useId, useState } from "react";

import { docButtonClass, DocumentsDialog } from "@/components/documents-ui";
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
import { listRevisions } from "@/lib/projects";
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

export function ReuseDocumentDialog({
  projectId,
  revisionId,
  onClose,
  onChanged,
  onReadOnly,
}: Props) {
  const sourceFieldId = useId();
  const revisionQuery = useQuery({
    queryKey: keys.revisions(projectId),
    queryFn: () => listRevisions(projectId),
  });
  const revisions =
    revisionQuery.data?.filter((r) => r.id !== revisionId) ?? null;
  const [sourceId, setSourceId] = useState("");
  const sourceQuery = useQuery({
    queryKey: [
      ...keys.documents(projectId, sourceId),
      "list",
      { status: "INCLUDED" },
    ],
    queryFn: () => listDocuments(projectId, sourceId, { status: "INCLUDED" }),
    enabled: !!sourceId,
  });
  const targetQuery = useQuery({
    queryKey: keys.documentList(projectId, revisionId, ""),
    queryFn: () => listDocuments(projectId, revisionId, { status: "ALL" }),
  });
  const sourceDocs = sourceQuery.data ?? null;
  const present = new Map(
    targetQuery.data?.map((row) => [row.document.id, row.status]),
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [results, setResults] = useState<Map<string, Result>>(new Map());
  const requestError =
    revisionQuery.error || sourceQuery.error || targetQuery.error;
  const loadError = requestError ? apiErrorOf(requestError).detail : null;
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    if (!sourceId && revisionQuery.data)
      setSourceId(
        revisionQuery.data.find((r) => r.id !== revisionId)?.id ?? "",
      );
  }, [sourceId, revisionQuery.data, revisionId]);
  useEffect(() => {
    setSelected(new Set());
    setResults(new Map());
  }, [sourceId]);

  const sourceRevision = revisions?.find(
    (revision) => revision.id === sourceId,
  );

  function reasonUnavailable(row: RevisionDocument): string | null {
    if (
      results.get(row.id)?.kind === "added" ||
      results.get(row.id)?.kind === "restored"
    ) {
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
        await reuseDocument(projectId, revisionId, {
          source_revision_document_id: row.id,
        });
        next.set(row.id, { kind: "added" });
        addedIds.add(row.id);
        changed += 1;
      } catch (err) {
        const { code, detail, error } = apiErrorOf(err);
        if (isReadOnlyErrorCode(code)) {
          next.set(row.id, { kind: "failed", message: detail });
          for (const unsent of queue.slice(index + 1)) {
            next.set(unsent.id, {
              kind: "not_sent",
              message: "Not added. " + detail,
            });
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
            code === "document_already_in_revision" &&
            error?.existing_status === "REMOVED"
              ? error.existing_revision_document_id
              : undefined,
        });
      }
    }
    setResults(next);
    setSelected(
      (current) => new Set([...current].filter((id) => !addedIds.has(id))),
    );
    setAdding(false);
    onChanged(changed);
  }

  async function restoreExisting(row: RevisionDocument, existingId: string) {
    try {
      await restoreDocument(projectId, revisionId, existingId);
      setResults((current) =>
        new Map(current).set(row.id, { kind: "restored" }),
      );
      onChanged(1);
    } catch (err) {
      setResults((current) =>
        new Map(current).set(row.id, {
          kind: "failed",
          message: apiErrorOf(err).detail,
        }),
      );
    }
  }

  const selectable = (sourceDocs ?? []).filter(
    (row) => !reasonUnavailable(row),
  );
  const selectedCount = selectable.filter((row) => selected.has(row.id)).length;

  return (
    <DocumentsDialog
      title="Add from another revision"
      description="Reuse project documents from another revision. The file is shared, not copied, and its details are copied so you can edit them here."
      onClose={onClose}
      footer={
        <>
          <button type="button" className={docButtonClass()} onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            className={docButtonClass("primary")}
            disabled={selectedCount === 0 || adding}
            onClick={() => void addSelected()}
          >
            {adding
              ? "Adding…"
              : `Add ${selectedCount} ${selectedCount === 1 ? "document" : "documents"}`}
          </button>
        </>
      }
    >
      {revisions === null && !loadError ? (
        <p className="m-0 text-workspace-label text-muted">Loading revisions…</p>
      ) : null}

      {revisions && revisions.length === 0 ? (
        <p className="m-0 text-workspace-label text-muted">
          This project has no other revisions.
        </p>
      ) : null}

      {revisions && revisions.length > 0 ? (
        <>
          <div className="mb-3.5 flex flex-col gap-1.5">
            <label
              htmlFor={sourceFieldId}
              className="text-workspace-caption font-semibold text-muted"
            >
              Source revision
            </label>
            <Select
              id={sourceFieldId}
              aria-label="Source revision"
              value={sourceId}
              onValueChange={(value) => setSourceId(value)}
              disabled={adding}
              className="min-h-[38px] rounded-[var(--pf-radius-control)] border-border px-[11px] py-2 text-workspace-label"
            >
              {revisions.map((revision) => (
                <option key={revision.id} value={revision.id}>
                  {`Revision ${revision.identifier} (${REVISION_STATUS_STYLES[revision.status].label})`}
                </option>
              ))}
            </Select>
          </div>

          {loadError ? (
            <p role="alert" className="mb-2 text-workspace-label text-danger">
              {loadError}{" "}
              <button
                type="button"
                className={docButtonClass("tiny")}
                onClick={() => {
                  void revisionQuery.refetch();
                  void targetQuery.refetch();
                  if (sourceId) void sourceQuery.refetch();
                }}
              >
                Retry
              </button>
            </p>
          ) : null}

          <div className="min-h-[80px]">
            {sourceDocs === null ? (
              <p className="m-0 py-4 text-workspace-label text-muted">
                Loading documents…
              </p>
            ) : sourceDocs.length === 0 ? (
              <p className="m-0 py-4 text-workspace-label text-muted">
                No included documents in Revision {sourceRevision?.identifier}.
              </p>
            ) : (
              <ul className="m-0 list-none divide-y divide-[var(--pf-documents-row-border)] p-0">
                {sourceDocs.map((row) => (
                  <SourceRow
                    key={row.id}
                    row={row}
                    unavailable={reasonUnavailable(row)}
                    checked={selected.has(row.id)}
                    result={results.get(row.id)}
                    disabled={adding}
                    onToggle={() => toggle(row.id)}
                    onRestore={(existingId) =>
                      void restoreExisting(row, existingId)
                    }
                  />
                ))}
              </ul>
            )}
          </div>
        </>
      ) : null}

      {revisions === null && loadError ? (
        <p role="alert" className="m-0 text-workspace-label text-danger">
          {loadError}
        </p>
      ) : null}
    </DocumentsDialog>
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
    <li className="flex items-start gap-3 py-3">
      <Checkbox
        aria-label={`Select ${name}`}
        checked={checked}
        disabled={disabled || !!unavailable}
        onChange={onToggle}
        className="mt-0.5"
      />
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "m-0 text-workspace-label font-semibold break-all",
            unavailable ? "text-muted" : "text-ink",
          )}
        >
          {name}
        </p>
        <p className="m-0 mt-0.5 text-workspace-caption text-muted">
          {documentTypeLabel(row.document_type)} ·{" "}
          {formatFileSize(row.document.size_bytes)}
        </p>
        {unavailable &&
        result?.kind !== "added" &&
        result?.kind !== "restored" ? (
          <p className="m-0 mt-0.5 text-workspace-caption text-muted">{unavailable}</p>
        ) : null}
        {result?.kind === "added" ? (
          <p className="m-0 mt-0.5 text-workspace-caption text-positive">Added</p>
        ) : null}
        {result?.kind === "restored" ? (
          <p className="m-0 mt-0.5 text-workspace-caption text-positive">Restored</p>
        ) : null}
        {result?.kind === "failed" || result?.kind === "not_sent" ? (
          <p className="m-0 mt-0.5 text-workspace-caption text-danger">{result.message}</p>
        ) : null}
      </div>
      {result?.kind === "failed" && result.restoreId ? (
        <button
          type="button"
          className={docButtonClass("tiny")}
          aria-label={`Restore ${name}`}
          onClick={() => onRestore(result.restoreId as string)}
        >
          Restore
        </button>
      ) : null}
    </li>
  );
}
