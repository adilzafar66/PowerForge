"use client";

import { useId, useState, type ReactNode, type FormEvent } from "react";
import {
  ModelNotice,
  ModelSelect,
  ModelSheet,
  useModel,
} from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { apiErrorOf } from "@/lib/api";
import {
  createConnection,
  updateConnection,
  type ConnectionInput,
  type ConnectionKind,
  type ConnectionPatch,
  type Direction,
  type ModelConnection,
  type ModelNode,
} from "@/lib/engineering-model";

export function ConnectionEditorSheet({
  row,
  nodes,
  labels,
  onClose,
  children,
}: {
  row?: ModelConnection;
  nodes: ModelNode[];
  labels: Map<string, string>;
  onClose: () => void;
  children?: ReactNode;
}) {
  const { projectId, revisionId, registry, writable, changed, failed } =
    useModel();
  const id = useId();
  const editable = writable && (!row || row.lifecycle_status === "ACTIVE");
  const voltageFamily = registry.unit_families.find(
    (f) => f.family.toLowerCase() === "voltage",
  );
  const [draft, setDraft] = useState({
    from_node_id: row?.from_node_id ?? "",
    to_node_id: row?.to_node_id ?? "",
    connection_kind: row?.connection_kind ?? "ELECTRICAL",
    direction: row?.direction ?? "UNDIRECTED",
    phase_configuration: row?.phase_configuration ?? "",
    nominal_voltage: row?.nominal_voltage ?? "",
    nominal_voltage_unit:
      row?.nominal_voltage_unit ?? voltageFamily?.default_unit ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeNodes = nodes.filter((n) => n.lifecycle_status === "ACTIVE");
  const patch: ConnectionPatch = {};
  if (row) {
    if (draft.from_node_id !== row.from_node_id)
      patch.from_node_id = draft.from_node_id;
    if (draft.to_node_id !== row.to_node_id)
      patch.to_node_id = draft.to_node_id;
    if (draft.connection_kind !== row.connection_kind)
      patch.connection_kind = draft.connection_kind;
    if (draft.direction !== row.direction) patch.direction = draft.direction;
    if (draft.phase_configuration !== (row.phase_configuration ?? ""))
      patch.phase_configuration = draft.phase_configuration || null;
    if (
      draft.nominal_voltage !== (row.nominal_voltage ?? "") ||
      (draft.nominal_voltage.trim() &&
        draft.nominal_voltage_unit !==
          (row.nominal_voltage_unit ?? voltageFamily?.default_unit ?? ""))
    ) {
      patch.nominal_voltage = draft.nominal_voltage.trim() || null;
      patch.nominal_voltage_unit = draft.nominal_voltage.trim()
        ? draft.nominal_voltage_unit || null
        : null;
    }
  }
  const valid =
    !!draft.from_node_id &&
    !!draft.to_node_id &&
    draft.from_node_id !== draft.to_node_id &&
    [draft.from_node_id, draft.to_node_id].every((id) =>
      activeNodes.some((n) => n.id === id),
    );
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!editable || busy || !valid || (row && !Object.keys(patch).length))
      return;
    setBusy(true);
    setError(null);
    try {
      if (row) await updateConnection(projectId, revisionId, row.id, patch);
      else {
        const input: ConnectionInput = {
          from_node_id: draft.from_node_id,
          to_node_id: draft.to_node_id,
          connection_kind: draft.connection_kind,
          direction: draft.direction,
          phase_configuration: draft.phase_configuration || null,
        };
        if (draft.nominal_voltage.trim()) {
          input.nominal_voltage = draft.nominal_voltage.trim();
          if (draft.nominal_voltage_unit)
            input.nominal_voltage_unit = draft.nominal_voltage_unit;
        }
        await createConnection(projectId, revisionId, input);
      }
      changed();
      onClose();
    } catch (err) {
      setError(apiErrorOf(err).detail);
      failed(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <ModelSheet
      title={row ? "Edit Connection" : "Add Connection"}
      onClose={onClose}
    >
      {children}
      <form onSubmit={save} className="space-y-4">
        {(["from_node_id", "to_node_id"] as const).map((key, i) => (
          <ModelSelect
            key={key}
            label={i === 0 ? "From Node" : "To Node"}
            value={draft[key]}
            disabled={!editable || busy}
            onChange={(value) => setDraft({ ...draft, [key]: value })}
          >
            <option value="">Select active node</option>
            {nodes
              .filter(
                (n) =>
                  n.lifecycle_status === "ACTIVE" ||
                  n.id === row?.from_node_id ||
                  n.id === row?.to_node_id,
              )
              .map((n) => (
                <option
                  key={n.id}
                  value={n.id}
                  disabled={
                    n.id === draft[i === 0 ? "to_node_id" : "from_node_id"]
                  }
                >
                  {labels.get(n.id)}
                </option>
              ))}
          </ModelSelect>
        ))}
        <ModelSelect
          label="Connection Kind"
          value={draft.connection_kind}
          disabled={!editable || busy}
          onChange={(v) =>
            setDraft({ ...draft, connection_kind: v as ConnectionKind })
          }
        >
          <option value="ELECTRICAL">Electrical</option>
          <option value="GROUNDING">Grounding</option>
          <option value="OTHER">Other</option>
        </ModelSelect>
        <ModelSelect
          label="Direction"
          value={draft.direction}
          disabled={!editable || busy}
          onChange={(v) => setDraft({ ...draft, direction: v as Direction })}
        >
          <option value="UNDIRECTED">Undirected</option>
          <option value="NOMINAL_FROM_TO">Nominal from → to</option>
        </ModelSelect>
        <Field id={`${id}-phase`} label="Phase Configuration">
          <Input
            id={`${id}-phase`}
            value={draft.phase_configuration}
            disabled={!editable || busy}
            onChange={(e) =>
              setDraft({ ...draft, phase_configuration: e.target.value })
            }
          />
        </Field>
        <Field id={`${id}-voltage`} label="Nominal Voltage">
          <Input
            id={`${id}-voltage`}
            inputMode="decimal"
            value={draft.nominal_voltage}
            disabled={!editable || busy}
            onChange={(e) =>
              setDraft({ ...draft, nominal_voltage: e.target.value })
            }
          />
        </Field>
        {draft.nominal_voltage.trim() && (
          <ModelSelect
            label="Voltage Input Unit"
            value={draft.nominal_voltage_unit}
            disabled={!editable || busy}
            onChange={(v) => setDraft({ ...draft, nominal_voltage_unit: v })}
          >
            {voltageFamily?.supported_input_units.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </ModelSelect>
        )}
        <p className="text-xs text-slate-500">
          Voltage is converted on save. Nominal direction describes endpoint
          order, not calculated power flow.
        </p>
        {error && <ModelNotice>{error}</ModelNotice>}
        {editable && (
          <Button
            type="submit"
            disabled={busy || !valid || (!!row && !Object.keys(patch).length)}
          >
            {busy ? "Saving…" : row ? "Save connection" : "Create connection"}
          </Button>
        )}
      </form>
    </ModelSheet>
  );
}
