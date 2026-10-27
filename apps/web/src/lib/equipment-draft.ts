import {
  changedText,
  type AttributeDefinition,
  type EquipmentAttribute,
  type EquipmentEditorInput,
  type EquipmentSnapshot,
  type InformationState,
  type ManualState,
  type ModelNode,
} from "./engineering-model";
export type AttributeDraft = {
  state: InformationState;
  value: string;
  unit: string;
};
export type TerminalDraft = {
  id: string;
  terminal_key: string;
  label: string;
  lifecycle_status: "ACTIVE" | "REMOVED";
  managed_by_profile: boolean;
  isNew?: boolean;
};
export type EquipmentDraft = {
  general: {
    equipment_type: string;
    tag: string;
    name: string;
    description: string;
  };
  attributes: Record<string, AttributeDraft>;
  terminals: TerminalDraft[];
};
export function attributeDraft(row: EquipmentAttribute): AttributeDraft {
  const value =
    row.numeric_value ??
    row.integer_value ??
    row.text_value ??
    row.boolean_value;
  return {
    state: row.information_state,
    value: value == null ? "" : String(value),
    unit: row.unit ?? "",
  };
}
export function equipmentDraft(snapshot: EquipmentSnapshot): EquipmentDraft {
  const row = snapshot.equipment;
  return {
    general: {
      equipment_type: row.equipment_type,
      tag: row.tag ?? "",
      name: row.name ?? "",
      description: row.description ?? "",
    },
    attributes: Object.fromEntries(
      snapshot.attributes.map((a) => [a.attribute_key, attributeDraft(a)]),
    ),
    terminals: snapshot.terminals.map((n) => ({
      id: n.id,
      terminal_key: n.terminal_key!,
      label: n.label ?? "",
      lifecycle_status: n.lifecycle_status,
      managed_by_profile: n.managed_by_profile,
    })),
  };
}
export function attributeChanged(
  original: AttributeDraft,
  draft: AttributeDraft,
) {
  return (
    original.state !== draft.state ||
    (draft.state === "PRESENT" &&
      (original.value !== draft.value || original.unit !== draft.unit))
  );
}
export function editorChanges(
  snapshot: EquipmentSnapshot,
  draft: EquipmentDraft,
  definitions: AttributeDefinition[],
): { body: EquipmentEditorInput; dirty: boolean; invalid: boolean } {
  const body: EquipmentEditorInput = {};
  const general = changedText(
    {
      tag: snapshot.equipment.tag,
      name: snapshot.equipment.name,
      description: snapshot.equipment.description,
    },
    {
      tag: draft.general.tag,
      name: draft.general.name,
      description: draft.general.description,
    },
  );
  if (draft.general.equipment_type !== snapshot.equipment.equipment_type)
    Object.assign(general, { equipment_type: draft.general.equipment_type });
  if (Object.keys(general).length) body.general = general;
  let invalid = false;
  for (const [key, value] of Object.entries(draft.attributes)) {
    const row = snapshot.attributes.find((a) => a.attribute_key === key);
    if (!row || !attributeChanged(attributeDraft(row), value)) continue;
    const def = definitions.find((a) => a.key === key);
    if (!def) continue;
    const present = value.state === "PRESENT";
    const numeric = def.value_type === "NUMBER" || def.value_type === "INTEGER";
    if (
      value.state === "CONFLICTING" ||
      (present &&
        ((def.value_type === "BOOLEAN" &&
          !["true", "false"].includes(value.value)) ||
          ((numeric || def.value_type === "ENUM") && !value.value.trim())))
    )
      invalid = true;
    (body.attributes ??= {})[key] = {
      information_state: value.state as ManualState,
      ...(present
        ? {
            value:
              def.value_type === "BOOLEAN"
                ? value.value === "true"
                : numeric
                  ? value.value.trim()
                  : value.value,
            ...(numeric && value.unit ? { unit: value.unit } : {}),
          }
        : {}),
    };
  }
  for (const terminal of draft.terminals) {
    if (terminal.isNew) {
      if (!terminal.terminal_key.trim()) invalid = true;
      (body.create_terminals ??= []).push({
        terminal_key: terminal.terminal_key.trim(),
        label: terminal.label || null,
      });
      continue;
    }
    const old = snapshot.terminals.find(
      (n) => n.id === terminal.id,
    ) as ModelNode;
    if (old.lifecycle_status !== terminal.lifecycle_status) {
      (terminal.lifecycle_status === "REMOVED"
        ? (body.remove_terminals ??= [])
        : (body.restore_terminals ??= [])
      ).push(terminal.id);
    } else if (terminal.lifecycle_status === "ACTIVE") {
      const patch = changedText(
        { label: old.label },
        { label: terminal.label },
      );
      if (terminal.terminal_key !== old.terminal_key)
        Object.assign(patch, { terminal_key: terminal.terminal_key.trim() });
      if (Object.keys(patch).length) {
        if (!terminal.terminal_key.trim()) invalid = true;
        (body.update_terminals ??= []).push({ id: terminal.id, ...patch });
      }
    }
  }
  return { body, dirty: Object.keys(body).length > 0, invalid };
}
