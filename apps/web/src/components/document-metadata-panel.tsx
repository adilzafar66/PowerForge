"use client";

import { Select } from "@/components/ui/select";

import { Pencil } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { changedFields } from "@/components/document-editor";
import {
  docButtonClass,
  InspectorSection,
  MiniGrid,
} from "@/components/documents-ui";
import { Mono } from "@/components/ui/mono";
import { apiErrorOf } from "@/lib/api";
import {
  DOCUMENT_TYPE_OPTIONS,
  documentTypeLabel,
  formatFileSize,
  originLabel,
  type DocumentType,
  type DocumentUpdateInput,
  type RevisionDocument,
} from "@/lib/documents";
import { formatDateShort } from "@/lib/projects";
import { cn } from "@/lib/utils";

const fieldControl =
  "w-full rounded-[var(--pf-radius-control)] border border-border bg-panel px-[11px] py-[9px] text-workspace-label text-ink outline-none focus:border-[#84a0b5] focus:shadow-[0_0_0_3px_#24557a12] disabled:cursor-not-allowed disabled:bg-[var(--pf-control-disabled)] disabled:text-muted";

export function DocumentTypeSection({
  row,
  canMutate,
  open,
  onOpen,
  onSave,
  onDirtyChange,
  children,
}: {
  row: RevisionDocument;
  canMutate: boolean;
  open: boolean;
  onOpen: () => void;
  onSave: (input: DocumentUpdateInput) => Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
  /** Status line above the confirmed type. */
  children?: ReactNode;
}) {
  const editable = canMutate && row.status === "INCLUDED";
  const selectId = useId();
  const [type, setType] = useState<DocumentType>(row.document_type);
  const typeTouched = useRef(false);
  const typeBaseline = useRef(row.document_type);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = editable && open && type !== typeBaseline.current;

  useEffect(() => {
    if (typeTouched.current) return;
    typeBaseline.current = row.document_type;
    setType(row.document_type);
    setError(null);
  }, [row.id, row.document_type]);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  async function save() {
    if (!editable || type === typeBaseline.current || saving) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({ document_type: type });
      typeTouched.current = false;
      typeBaseline.current = type;
      setSaving(false);
    } catch (err) {
      setError(apiErrorOf(err).detail);
      setSaving(false);
    }
  }

  return (
    <InspectorSection>
      {children}
      <h3 className="m-0 mb-3 text-workspace-overline font-bold tracking-[0.72px] text-[var(--pf-text-tertiary)] uppercase">
        Confirmed type
      </h3>
      <p className="m-0 text-workspace-body font-semibold text-ink">
        {documentTypeLabel(row.document_type)}
      </p>
      {editable ? (
        <div className="mt-[15px]">
          {open ? (
            <div className="flex flex-col gap-2.5">
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor={selectId}
                  className="text-workspace-caption font-semibold text-muted"
                >
                  Document type
                </label>
                <Select
                  id={selectId}
                  value={type}
                  disabled={saving}
                  onValueChange={(value) => {
                    typeTouched.current = true;
                    setType(value as DocumentType);
                  }}
                  className="min-h-[38px] rounded-[var(--pf-radius-control)] border-border px-[11px] py-2 text-workspace-label"
                >
                  {DOCUMENT_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <button
                  type="button"
                  className={docButtonClass("tiny", "primary")}
                  disabled={saving || type === typeBaseline.current}
                  onClick={() => void save()}
                >
                  {saving ? "Saving…" : "Save type"}
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className={docButtonClass("tiny")}
              onClick={onOpen}
            >
              <Pencil aria-hidden strokeWidth={1.8} />
              Change type
            </button>
          )}
          {error ? (
            <p role="alert" className="m-0 mt-2 text-workspace-caption text-danger">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </InspectorSection>
  );
}

export function DocumentMetadataPanel({
  row,
  canMutate,
  focusField,
  onFocused,
  onSave,
  onDirtyChange,
}: {
  row: RevisionDocument;
  canMutate: boolean;
  focusField: boolean;
  onFocused: () => void;
  onSave: (input: DocumentUpdateInput) => Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const editable = canMutate && row.status === "INCLUDED";
  const baseId = useId();
  const [number, setNumber] = useState(row.document_number ?? "");
  const [description, setDescription] = useState(row.description ?? "");
  const [notes, setNotes] = useState(row.notes ?? "");
  const touched = useRef(false);
  const baseline = useRef(row);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (touched.current) return;
    baseline.current = row;
    setNumber(row.document_number ?? "");
    setDescription(row.description ?? "");
    setNotes(row.notes ?? "");
    setError(null);
    setSaving(false);
  }, [row]);

  useEffect(() => {
    if (!focusField) {
      return;
    }
    document.getElementById(`${baseId}-number`)?.focus();
    onFocused();
  }, [focusField, baseId, onFocused]);

  const changes = changedFields(baseline.current, {
    type: baseline.current.document_type,
    document_number: number,
    description,
    notes,
  });
  const dirty = editable && Object.keys(changes).length > 0;
  const file = row.document;

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  async function save() {
    if (!editable || !dirty || saving) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(changes);
      touched.current = false;
      baseline.current = {
        ...baseline.current,
        document_number: number.trim() || null,
        description: description.trim() || null,
        notes: notes.trim() || null,
      };
      setSaving(false);
    } catch (err) {
      setError(apiErrorOf(err).detail);
      setSaving(false);
    }
  }

  return (
    <InspectorSection title="Document metadata">
      <MiniGrid
        className="mb-4"
        items={[
          ["Document no.", row.document_number || "—"],
          ["File name", file.original_filename],
          ["File type", file.mime_type],
          ["Size", formatFileSize(file.size_bytes)],
          ["Origin", originLabel(row.origin)],
          ["Status", row.status === "INCLUDED" ? "Included" : "Removed"],
          ["Added", formatDateShort(row.added_at)],
          [
            "SHA-256",
            <Mono key="sha" className="text-[11.5px] break-all text-muted">
              {file.sha256}
            </Mono>,
          ],
        ]}
      />
      <div className="flex flex-col gap-3">
        <Field label="Document number" htmlFor={`${baseId}-number`}>
          <input
            id={`${baseId}-number`}
            className={cn(fieldControl, "min-h-[38px]")}
            value={number}
            maxLength={128}
            disabled={!editable || saving}
            onChange={(event) => {
              touched.current = true;
              setNumber(event.target.value);
            }}
          />
        </Field>
        <Field label="Description" htmlFor={`${baseId}-description`}>
          <textarea
            id={`${baseId}-description`}
            rows={2}
            className={cn(fieldControl, "min-h-[75px] resize-y")}
            value={description}
            maxLength={2000}
            disabled={!editable || saving}
            onChange={(event) => {
              touched.current = true;
              setDescription(event.target.value);
            }}
          />
        </Field>
        <Field label="Notes" htmlFor={`${baseId}-notes`}>
          <textarea
            id={`${baseId}-notes`}
            rows={3}
            className={cn(fieldControl, "min-h-[75px] resize-y")}
            value={notes}
            maxLength={10000}
            disabled={!editable || saving}
            onChange={(event) => {
              touched.current = true;
              setNotes(event.target.value);
            }}
          />
        </Field>
      </div>
      {error ? (
        <p role="alert" className="m-0 mt-2 text-workspace-caption text-danger">
          {error}
        </p>
      ) : null}
      {editable ? (
        <div className="mt-3">
          <button
            type="button"
            className={docButtonClass("tiny", "primary")}
            disabled={!dirty || saving}
            onClick={() => void save()}
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      ) : (
        <p className="m-0 mt-3 text-workspace-caption text-muted">
          This document is not editable in the selected context.
        </p>
      )}
    </InspectorSection>
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
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={htmlFor}
        className="text-workspace-caption font-semibold text-muted"
      >
        {label}
      </label>
      {children}
    </div>
  );
}
