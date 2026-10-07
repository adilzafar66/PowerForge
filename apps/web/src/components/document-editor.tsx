"use client";

import Link from "next/link";
import { useEffect, useId, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { fieldClassName, Input, Textarea } from "@/components/ui/input";
import { Mono } from "@/components/ui/mono";
import { apiErrorOf } from "@/lib/api";
import {
  DOCUMENT_TYPE_OPTIONS,
  formatFileSize,
  originLabel,
  updateDocument,
  type DocumentType,
  type DocumentUpdateInput,
  type RevisionDocument,
} from "@/lib/documents";
import { formatDateShort } from "@/lib/projects";
import { cn } from "@/lib/utils";

type Props = {
  projectId: string;
  revisionId: string;
  document: RevisionDocument;
  canMutate: boolean;
  onClose: () => void;
  onSaved: (updated: RevisionDocument) => void;
  /** Returns true when the owner handled the failure (read-only, vanished, conflict). */
  onMutationError: (err: unknown) => boolean;
};

type TextField = "document_number" | "description" | "notes";

function nullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/** Only the fields the user actually changed, so an untouched field is never sent. */
export function changedFields(
  row: RevisionDocument,
  draft: { type: DocumentType } & Record<TextField, string>,
): DocumentUpdateInput {
  const changes: DocumentUpdateInput = {};
  if (draft.type !== row.document_type) {
    changes.document_type = draft.type;
  }
  for (const field of ["document_number", "description", "notes"] as const) {
    const next = nullable(draft[field]);
    if (next !== row[field]) {
      changes[field] = next;
    }
  }
  return changes;
}

export function DocumentEditor({
  projectId,
  revisionId,
  document: row,
  canMutate,
  onClose,
  onSaved,
  onMutationError,
}: Props) {
  const editable = canMutate && row.status === "INCLUDED";
  const titleId = useId();
  const [type, setType] = useState<DocumentType>(row.document_type);
  const [number, setNumber] = useState(row.document_number ?? "");
  const [description, setDescription] = useState(row.description ?? "");
  const [notes, setNotes] = useState(row.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const changes = changedFields(row, {
    type,
    document_number: number,
    description,
    notes,
  });
  const dirty = Object.keys(changes).length > 0;

  async function save() {
    if (!editable || !dirty) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await updateDocument(projectId, revisionId, row.id, changes);
      onSaved(updated);
    } catch (err) {
      if (onMutationError(err)) {
        onClose();
      } else {
        setError(apiErrorOf(err).detail);
        setSaving(false);
      }
    }
  }

  const file = row.document;

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
        className="max-h-[90vh] w-[560px] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_24px_48px_rgba(0,0,0,0.12),0_4px_8px_rgba(0,0,0,0.06)]"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id={titleId} className="mb-1 text-[16px] font-semibold text-slate-900">
          {editable ? "Edit document details" : "Document details"}
        </h2>
        <p className="mb-4 text-[13px] break-all text-slate-500">{file.original_filename}</p>

        {!editable ? (
          <p className="mb-4 text-[12.5px] text-slate-500">
            {row.status === "REMOVED"
              ? "This document is removed from the revision. Restore it to edit its details."
              : "This revision is read-only, so the details cannot be changed."}
          </p>
        ) : null}

        <dl className="mb-5 grid grid-cols-[120px_1fr] gap-x-4 gap-y-1.5 rounded-xl bg-slate-50 px-4 py-3 text-[12.5px]">
          <Fact label="File name">{file.original_filename}</Fact>
          <Fact label="File type">{file.mime_type}</Fact>
          <Fact label="Size">{formatFileSize(file.size_bytes)}</Fact>
          <Fact label="SHA-256">
            <Mono className="break-all text-slate-600">{file.sha256}</Mono>
          </Fact>
          <Fact label="Uploaded">{formatDateShort(file.uploaded_at)}</Fact>
          <Fact label="Added to revision">{formatDateShort(row.added_at)}</Fact>
          <Fact label="Origin">
            {originLabel(row.origin)}
            {row.origin === "INHERITED" && row.inherited_from_revision_identifier ? (
              <>
                {" from "}
                {row.inherited_from_revision_id ? (
                  <Link
                    href={`/projects/${projectId}/revisions/${row.inherited_from_revision_id}`}
                    className="text-accent hover:underline"
                  >
                    Revision {row.inherited_from_revision_identifier}
                  </Link>
                ) : (
                  <>Revision {row.inherited_from_revision_identifier}</>
                )}
              </>
            ) : null}
          </Fact>
        </dl>

        <div className="space-y-3.5">
          <Field label="Document type" htmlFor={`${titleId}-type`}>
            <select
              id={`${titleId}-type`}
              value={type}
              disabled={!editable || saving}
              onChange={(event) => setType(event.target.value as DocumentType)}
              className={cn(fieldClassName, "py-2")}
            >
              {DOCUMENT_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Document number" htmlFor={`${titleId}-number`}>
            <Input
              id={`${titleId}-number`}
              value={number}
              maxLength={128}
              disabled={!editable || saving}
              onChange={(event) => setNumber(event.target.value)}
            />
          </Field>
          <Field label="Description" htmlFor={`${titleId}-description`}>
            <Textarea
              id={`${titleId}-description`}
              rows={2}
              value={description}
              maxLength={2000}
              disabled={!editable || saving}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
          <Field label="Notes" htmlFor={`${titleId}-notes`}>
            <Textarea
              id={`${titleId}-notes`}
              rows={3}
              value={notes}
              maxLength={10000}
              disabled={!editable || saving}
              onChange={(event) => setNotes(event.target.value)}
            />
          </Field>
        </div>

        {error ? (
          <p role="alert" className="mt-3 text-[13px] text-red-600">
            {error}
          </p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {editable ? "Cancel" : "Close"}
          </Button>
          {editable ? (
            <Button type="button" disabled={!dirty || saving} onClick={() => void save()}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-slate-400">{label}</dt>
      <dd className="text-slate-700">{children}</dd>
    </>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-[12.5px] font-medium text-slate-600">
        {label}
      </label>
      {children}
    </div>
  );
}
