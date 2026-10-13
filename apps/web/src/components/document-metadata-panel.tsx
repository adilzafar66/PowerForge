"use client";

import { useEffect, useId, useState, type ReactNode } from "react";

import { changedFields } from "@/components/document-editor";
import { Button } from "@/components/ui/button";
import { fieldClassName, Input, Textarea } from "@/components/ui/input";
import { Mono } from "@/components/ui/mono";
import { apiErrorOf } from "@/lib/api";
import {
  DOCUMENT_TYPE_OPTIONS,
  documentTypeLabel,
  formatFileSize,
  type DocumentType,
  type DocumentUpdateInput,
  type RevisionDocument,
} from "@/lib/documents";
import { cn } from "@/lib/utils";

export function DocumentTypeSection({
  row,
  canMutate,
  open,
  onOpen,
  onSave,
}: {
  row: RevisionDocument;
  canMutate: boolean;
  open: boolean;
  onOpen: () => void;
  onSave: (input: DocumentUpdateInput) => Promise<void>;
}) {
  const editable = canMutate && row.status === "INCLUDED";
  const selectId = useId();
  const [type, setType] = useState<DocumentType>(row.document_type);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setType(row.document_type);
    setError(null);
  }, [row.id, row.document_type]);

  async function save() {
    if (!editable || type === row.document_type) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({ document_type: type });
      setSaving(false);
    } catch (err) {
      setError(apiErrorOf(err).detail);
      setSaving(false);
    }
  }

  return (
    <section className="px-5 py-4">
      <h3 className="mb-2 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
        Confirmed type
      </h3>
      <p className="text-[13.5px] font-medium text-slate-800">{documentTypeLabel(row.document_type)}</p>
      {editable ? (
        <div className="mt-2">
          {open ? (
            <div className="space-y-2">
              <label htmlFor={selectId} className="block text-[12.5px] font-medium text-slate-600">
                Document type
              </label>
              <select
                id={selectId}
                value={type}
                disabled={saving}
                onChange={(event) => setType(event.target.value as DocumentType)}
                className={cn(fieldClassName, "py-2")}
              >
                {DOCUMENT_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <Button
                type="button"
                size="sm"
                disabled={saving || type === row.document_type}
                onClick={() => void save()}
              >
                {saving ? "Saving…" : "Save type"}
              </Button>
            </div>
          ) : (
            <Button type="button" variant="secondary" size="sm" onClick={onOpen}>
              Change type
            </Button>
          )}
          {error ? (
            <p role="alert" className="mt-2 text-[12.5px] text-red-600">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function DocumentMetadataPanel({
  row,
  canMutate,
  focusField,
  onFocused,
  onSave,
}: {
  row: RevisionDocument;
  canMutate: boolean;
  focusField: boolean;
  onFocused: () => void;
  onSave: (input: DocumentUpdateInput) => Promise<void>;
}) {
  const editable = canMutate && row.status === "INCLUDED";
  const baseId = useId();
  const [number, setNumber] = useState(row.document_number ?? "");
  const [description, setDescription] = useState(row.description ?? "");
  const [notes, setNotes] = useState(row.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNumber(row.document_number ?? "");
    setDescription(row.description ?? "");
    setNotes(row.notes ?? "");
    setError(null);
    setSaving(false);
  }, [row.id, row.document_number, row.description, row.notes]);

  useEffect(() => {
    if (!focusField) {
      return;
    }
    document.getElementById(`${baseId}-number`)?.focus();
    onFocused();
  }, [focusField, baseId, onFocused]);

  const changes = changedFields(row, {
    type: row.document_type,
    document_number: number,
    description,
    notes,
  });
  const dirty = Object.keys(changes).length > 0;
  const file = row.document;

  async function save() {
    if (!editable || !dirty) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(changes);
      setSaving(false);
    } catch (err) {
      setError(apiErrorOf(err).detail);
      setSaving(false);
    }
  }

  return (
    <section className="border-t border-slate-100 px-5 py-4">
      <h3 className="mb-2 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
        Metadata
      </h3>
      <dl className="mb-4 grid grid-cols-[96px_1fr] gap-x-3 gap-y-1.5 text-[12.5px]">
        <dt className="text-slate-400">File name</dt>
        <dd className="break-all text-slate-700">{file.original_filename}</dd>
        <dt className="text-slate-400">File type</dt>
        <dd className="text-slate-700">{file.mime_type}</dd>
        <dt className="text-slate-400">Size</dt>
        <dd className="text-slate-700">{formatFileSize(file.size_bytes)}</dd>
        <dt className="text-slate-400">SHA-256</dt>
        <dd>
          <Mono className="break-all text-slate-600">{file.sha256}</Mono>
        </dd>
      </dl>
      <div className="space-y-3">
        <Field label="Document number" htmlFor={`${baseId}-number`}>
          <Input
            id={`${baseId}-number`}
            value={number}
            maxLength={128}
            disabled={!editable || saving}
            onChange={(event) => setNumber(event.target.value)}
          />
        </Field>
        <Field label="Description" htmlFor={`${baseId}-description`}>
          <Textarea
            id={`${baseId}-description`}
            rows={2}
            value={description}
            maxLength={2000}
            disabled={!editable || saving}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field label="Notes" htmlFor={`${baseId}-notes`}>
          <Textarea
            id={`${baseId}-notes`}
            rows={3}
            value={notes}
            maxLength={10000}
            disabled={!editable || saving}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>
      </div>
      {error ? (
        <p role="alert" className="mt-2 text-[12.5px] text-red-600">
          {error}
        </p>
      ) : null}
      {editable ? (
        <div className="mt-3">
          <Button type="button" size="sm" disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      ) : null}
    </section>
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
