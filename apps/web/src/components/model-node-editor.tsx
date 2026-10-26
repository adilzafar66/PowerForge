"use client";

import { useId, useState, type FormEvent } from "react";
import { ModelNotice, useModel } from "@/components/model-shared";
import { Button } from "@/components/ui/button";
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

export function ModelNodeEditor({
  row,
  equipmentId,
  onSaved,
}: {
  row?: ModelNode;
  equipmentId?: string;
  onSaved: () => void;
}) {
  const { projectId, revisionId, writable, changed, failed } = useModel();
  const terminal = !!equipmentId || row?.kind === "EQUIPMENT_TERMINAL";
  const [key, setKey] = useState(row?.terminal_key ?? "");
  const [label, setLabel] = useState(row?.label ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const patch: NodePatch = row
    ? changedText({ label: row.label }, { label })
    : { label: label || null };
  if (terminal && key !== (row?.terminal_key ?? ""))
    patch.terminal_key = key.trim();
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!writable || busy || (row && !Object.keys(patch).length)) return;
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
    <form onSubmit={save} className="space-y-3">
      {terminal && (
        <Field id={`${id}-key`} label="Terminal key" required>
          <Input
            id={`${id}-key`}
            value={key}
            disabled={!writable || busy}
            onChange={(e) => setKey(e.target.value)}
          />
        </Field>
      )}
      <Field id={`${id}-label`} label="Label">
        <Input
          id={`${id}-label`}
          value={label}
          disabled={!writable || busy}
          onChange={(e) => setLabel(e.target.value)}
        />
      </Field>
      {error && <ModelNotice>{error}</ModelNotice>}
      {writable && (
        <Button
          type="submit"
          disabled={
            busy ||
            (terminal && !key.trim()) ||
            (!!row && !Object.keys(patch).length)
          }
        >
          {busy
            ? "Saving…"
            : row
              ? "Save node"
              : terminal
                ? "Create terminal"
                : "Create electrical node"}
        </Button>
      )}
    </form>
  );
}
