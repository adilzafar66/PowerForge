"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { ModelNotice, ModelSelect, useModel } from "@/components/model-shared";
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
import { isPositiveFiniteNumber } from "@/lib/topology-presentation";

export function ConnectionEditorSheet({
  row,
  nodes,
  labels,
  formId,
  onClose,
  onDirtyChange,
}: {
  row?: ModelConnection;
  nodes: ModelNode[];
  labels: Map<string, string>;
  formId?: string;
  onClose: () => void;
  onDirtyChange?: (dirty: boolean) => void;
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
  const dirty = row
    ? Object.keys(patch).length > 0
    : Boolean(
        draft.from_node_id ||
        draft.to_node_id ||
        draft.phase_configuration ||
        draft.nominal_voltage ||
        draft.connection_kind !== "ELECTRICAL" ||
        draft.direction !== "UNDIRECTED",
      );
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  const distinct =
    !!draft.from_node_id &&
    !!draft.to_node_id &&
    draft.from_node_id !== draft.to_node_id;
  const activeEndpoints = [draft.from_node_id, draft.to_node_id].every(
    (nodeId) => activeNodes.some((n) => n.id === nodeId),
  );

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!editable || busy) return;
    if (!distinct || !activeEndpoints) {
      setError("Select two different active endpoint nodes.");
      return;
    }
    if (!isPositiveFiniteNumber(draft.nominal_voltage)) {
      setError("Nominal voltage must be a positive finite number.");
      return;
    }
    if (row && !Object.keys(patch).length) return;
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
    <form
      id={formId}
      aria-label="Connection editor"
      onSubmit={save}
      className="space-y-4"
    >
      {(["from_node_id", "to_node_id"] as const).map((key, i) => (
        <ModelSelect
          key={key}
          label={i === 0 ? "From node" : "To node"}
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
      <p className="m-0 text-workspace-caption text-muted">
        From and To must be different active nodes.
      </p>
      <ModelSelect
        label="Connection kind"
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
        label="Nominal direction"
        value={draft.direction}
        disabled={!editable || busy}
        onChange={(v) => setDraft({ ...draft, direction: v as Direction })}
      >
        <option value="UNDIRECTED">Undirected</option>
        <option value="NOMINAL_FROM_TO">Nominal from → to</option>
      </ModelSelect>
      <Field id={`${id}-phase`} label="Phase configuration">
        <Input
          id={`${id}-phase`}
          value={draft.phase_configuration}
          maxLength={80}
          placeholder="e.g. 3"
          disabled={!editable || busy}
          onChange={(e) =>
            setDraft({ ...draft, phase_configuration: e.target.value })
          }
        />
      </Field>
      <div className="grid grid-cols-[minmax(0,1fr)_110px] items-end gap-2.5 max-[520px]:grid-cols-1">
        <Field id={`${id}-voltage`} label="Nominal voltage">
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
        <ModelSelect
          label="Voltage unit"
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
      </div>
      <p className="m-0 text-workspace-caption text-muted">
        Exact decimal input is preserved. The server normalizes to kV. Nominal
        direction describes stored endpoint order, not electrical power flow.
      </p>
      {error ? <ModelNotice>{error}</ModelNotice> : null}
    </form>
  );
}
