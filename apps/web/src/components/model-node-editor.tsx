"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { ModelNotice, useModel } from "@/components/model-shared";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { apiErrorOf } from "@/lib/api";
import {
  changedText,
  createElectricalNode,
  createTerminal,
  updateNode,
  type ModelNode,
  type NodePatch,
} from "@/lib/engineering-model";
import { nodeKindLabel } from "@/lib/topology-presentation";

export function ModelNodeEditor({
  row,
  equipmentId,
  equipmentName,
  formId,
  onSaved,
  onDirtyChange,
}: {
  row?: ModelNode;
  equipmentId?: string;
  equipmentName?: string | null;
  formId?: string;
  onSaved: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { projectId, revisionId, writable, changed, failed } = useModel();
  const editable = writable && (!row || row.lifecycle_status === "ACTIVE");
  const terminal = !!equipmentId || row?.kind === "EQUIPMENT_TERMINAL";
  const managed = !!row?.managed_by_profile;
  const [key, setKey] = useState(row?.terminal_key ?? "");
  const [label, setLabel] = useState(row?.label ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const patch: NodePatch = row
    ? changedText({ label: row.label }, { label })
    : { label: label || null };
  if (terminal && !managed && key !== (row?.terminal_key ?? ""))
    patch.terminal_key = key.trim();
  const dirty = row
    ? Object.keys(patch).length > 0
    : Boolean(label.trim() || (terminal && key.trim()));
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!editable || busy || (row && !Object.keys(patch).length)) return;
    setBusy(true);
    setError(null);
    try {
      if (row) await updateNode(projectId, revisionId, row.id, patch);
      else if (equipmentId)
        await createTerminal(projectId, revisionId, equipmentId, {
          terminal_key: key.trim(),
          label: label || null,
        });
      else await createElectricalNode(projectId, revisionId, label || null);
      changed();
      onSaved();
    } catch (err) {
      setError(apiErrorOf(err).detail);
      failed(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      id={formId}
      aria-label="Node editor"
      onSubmit={save}
      className="space-y-4"
    >
      <Field id={`${id}-kind`} label="Node kind">
        <Input
          id={`${id}-kind`}
          value={
            terminal
              ? nodeKindLabel("EQUIPMENT_TERMINAL")
              : nodeKindLabel("ELECTRICAL_NODE")
          }
          disabled
        />
        <p className="m-0 mt-1.5 text-workspace-caption text-muted">
          Node kind and equipment ownership cannot be changed after creation.
        </p>
      </Field>
      {terminal ? (
        <>
          <Field id={`${id}-owner`} label="Owning equipment">
            <Input id={`${id}-owner`} value={equipmentName ?? "—"} disabled />
          </Field>
          <Field id={`${id}-key`} label="Terminal key" required={!managed}>
            <Input
              id={`${id}-key`}
              value={key}
              maxLength={80}
              disabled={!editable || busy || managed}
              onChange={(e) => setKey(e.target.value)}
            />
            {managed ? (
              <p className="m-0 mt-1.5 text-workspace-caption text-muted">
                Profile-managed terminal keys are controlled by the equipment
                type.
              </p>
            ) : null}
          </Field>
        </>
      ) : null}
      <Field id={`${id}-label`} label="Display label">
        <Input
          id={`${id}-label`}
          value={label}
          maxLength={120}
          placeholder="e.g. LV distribution junction"
          disabled={!editable || busy}
          onChange={(e) => setLabel(e.target.value)}
        />
        <p className="m-0 mt-1.5 text-workspace-caption text-muted">
          Leave blank to use a generated display name for standalone nodes.
        </p>
      </Field>
      {error ? <ModelNotice>{error}</ModelNotice> : null}
    </form>
  );
}
