import { request } from "@/lib/api";

export type Lifecycle = "ACTIVE" | "REMOVED";
export type LifecycleFilter = Lifecycle | "ALL";
export type ManualState =
  "PRESENT" | "NOT_POPULATED" | "MISSING" | "NOT_APPLICABLE";
export type InformationState = ManualState | "CONFLICTING";
export type ValueType = "NUMBER" | "INTEGER" | "ENUM" | "BOOLEAN" | "TEXT";
export type Origin = "MANUAL" | "AI_EXTRACTION" | "INFERRED" | "IMPORTED";
export type Verification =
  | "UNVERIFIED"
  | "AI_EXTRACTED"
  | "SYSTEM_VALIDATED"
  | "ENGINEER_REVIEWED"
  | "ENGINEER_VERIFIED";
export type AttributeDefinition = {
  key: string;
  display_name: string;
  value_type: ValueType;
  canonical_unit: string | null;
  required: boolean;
  critical: boolean;
  allowed_values: string[];
  notes: string | null;
  display_order: number;
  requirement_group: string | null;
  requirement_condition: string | null;
  supported_input_units: string[];
};
export type Requirement = {
  rule_id: string;
  rule_type: string;
  condition_description: string;
  attributes: string[];
  engineering_rationale: string | null;
  implementation_note: string | null;
};
export type EquipmentDefinition = {
  key: string;
  display_name: string;
  attributes: AttributeDefinition[];
  requirements: Requirement[];
};
export type Registry = {
  registry_version: string;
  equipment_types: EquipmentDefinition[];
  requirement_rules: Requirement[];
  unit_families: {
    family: string;
    default_unit: string;
    supported_input_units: string[];
    notes: string | null;
  }[];
};
type Audit = {
  id: string;
  project_id: string;
  revision_id: string;
  created_at: string;
  created_by: string | null;
  updated_at: string;
  updated_by: string | null;
};
type ModelRow = Audit & {
  lifecycle_status: Lifecycle;
  origin: Origin;
  verification_state: Verification;
  removed_at: string | null;
  removed_by: string | null;
};
export type Equipment = ModelRow & {
  lineage_id: string;
  equipment_type: string;
  tag: string | null;
  name: string | null;
  description: string | null;
  inherited_from_equipment_id: string | null;
};
export type EquipmentAttribute = Audit & {
  equipment_id: string;
  attribute_key: string;
  value_type: ValueType;
  numeric_value: string | null;
  integer_value: string | null;
  text_value: string | null;
  boolean_value: boolean | null;
  unit: string | null;
  information_state: InformationState;
  verification_state: Verification;
  origin: Origin | null;
  confidence: string | null;
  inherited_from_attribute_id: string | null;
};
export type ModelNode = ModelRow & {
  managed_by_profile: boolean;
  kind: "EQUIPMENT_TERMINAL" | "ELECTRICAL_NODE";
  equipment_id: string | null;
  terminal_key: string | null;
  label: string | null;
  inherited_from_node_id: string | null;
};
export type ConnectionKind = "ELECTRICAL" | "GROUNDING" | "OTHER";
export type Direction = "UNDIRECTED" | "NOMINAL_FROM_TO";
export type ModelConnection = ModelRow & {
  from_node_id: string;
  to_node_id: string;
  connection_kind: ConnectionKind;
  direction: Direction;
  phase_configuration: string | null;
  nominal_voltage: string | null;
  nominal_voltage_unit: string | null;
  confidence: string | null;
  inherited_from_connection_id: string | null;
};
export type EquipmentInput = {
  equipment_type: string;
  tag?: string | null;
  name?: string | null;
  description?: string | null;
};
export type EquipmentPatch = Partial<EquipmentInput>;
export type AttributeInput = {
  information_state: ManualState;
  value?: string | boolean;
  unit?: string;
};
export type NodePatch = { terminal_key?: string; label?: string | null };
export type ConnectionInput = {
  from_node_id: string;
  to_node_id: string;
  connection_kind?: ConnectionKind;
  direction?: Direction;
  phase_configuration?: string | null;
  nominal_voltage?: string | null;
  nominal_voltage_unit?: string | null;
};
export type ConnectionPatch = Partial<ConnectionInput>;

const base = (p: string, r: string) =>
  `/api/projects/${encodeURIComponent(p)}/revisions/${encodeURIComponent(r)}`;
const send = <T>(path: string, method: string, body?: object) => {
  if (method === "PATCH" && (!body || Object.keys(body).length === 0)) {
    return Promise.reject(new Error("No changes to save"));
  }
  return request<T>(path, {
    method,
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
};
async function list<T>(
  path: string,
  query: Record<string, string | undefined> = {},
): Promise<T[]> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return (
    await request<{ items: T[] }>(`${path}${params.size ? `?${params}` : ""}`)
  ).items;
}
export const getEngineeringRegistry = () =>
  request<Registry>("/api/engineering-model/registry");
export const listEquipment = (
  p: string,
  r: string,
  query: {
    search?: string;
    equipment_type?: string;
    lifecycle_status?: LifecycleFilter;
  } = {},
) => list<Equipment>(`${base(p, r)}/equipment`, query);
export const getEquipment = (p: string, r: string, id: string) =>
  request<Equipment>(`${base(p, r)}/equipment/${encodeURIComponent(id)}`);
export const createEquipment = (p: string, r: string, body: EquipmentInput) =>
  send<Equipment>(`${base(p, r)}/equipment`, "POST", body);
export const updateEquipment = (
  p: string,
  r: string,
  id: string,
  body: EquipmentPatch,
) => send<Equipment>(`${base(p, r)}/equipment/${id}`, "PATCH", body);
export const removeEquipment = (p: string, r: string, id: string) =>
  send<Equipment>(`${base(p, r)}/equipment/${id}/remove`, "POST");
export const restoreEquipment = (p: string, r: string, id: string) =>
  send<Equipment>(`${base(p, r)}/equipment/${id}/restore`, "POST");
export const listAttributes = (p: string, r: string, id: string) =>
  list<EquipmentAttribute>(`${base(p, r)}/equipment/${id}/attributes`);
export const setAttribute = (
  p: string,
  r: string,
  id: string,
  key: string,
  body: AttributeInput,
) =>
  send<EquipmentAttribute>(
    `${base(p, r)}/equipment/${id}/attributes/${encodeURIComponent(key)}`,
    "PUT",
    body,
  );
export const listNodes = (
  p: string,
  r: string,
  lifecycle_status: LifecycleFilter = "ACTIVE",
) => list<ModelNode>(`${base(p, r)}/nodes`, { lifecycle_status });
export const createTerminal = (
  p: string,
  r: string,
  equipment_id: string,
  body: { terminal_key: string; label?: string | null },
) =>
  send<ModelNode>(`${base(p, r)}/nodes`, "POST", {
    ...body,
    kind: "EQUIPMENT_TERMINAL",
    equipment_id,
  });
export const createElectricalNode = (
  p: string,
  r: string,
  label: string | null,
) =>
  send<ModelNode>(`${base(p, r)}/nodes`, "POST", {
    kind: "ELECTRICAL_NODE",
    label,
  });
export const updateNode = (p: string, r: string, id: string, body: NodePatch) =>
  send<ModelNode>(`${base(p, r)}/nodes/${id}`, "PATCH", body);
export const removeNode = (p: string, r: string, id: string) =>
  send<ModelNode>(`${base(p, r)}/nodes/${id}/remove`, "POST");
export const restoreNode = (p: string, r: string, id: string) =>
  send<ModelNode>(`${base(p, r)}/nodes/${id}/restore`, "POST");
export const listConnections = (
  p: string,
  r: string,
  lifecycle_status: LifecycleFilter = "ACTIVE",
) => list<ModelConnection>(`${base(p, r)}/connections`, { lifecycle_status });
export const createConnection = (p: string, r: string, body: ConnectionInput) =>
  send<ModelConnection>(`${base(p, r)}/connections`, "POST", body);
export const updateConnection = (
  p: string,
  r: string,
  id: string,
  body: ConnectionPatch,
) => send<ModelConnection>(`${base(p, r)}/connections/${id}`, "PATCH", body);
export const removeConnection = (p: string, r: string, id: string) =>
  send<ModelConnection>(`${base(p, r)}/connections/${id}/remove`, "POST");
export const restoreConnection = (p: string, r: string, id: string) =>
  send<ModelConnection>(`${base(p, r)}/connections/${id}/restore`, "POST");

export const typeLabel = (registry: Registry, key: string) =>
  registry.equipment_types.find((t) => t.key === key)?.display_name ?? key;
export const equipmentLabel = (row: Equipment, registry: Registry) =>
  row.tag || row.name || typeLabel(registry, row.equipment_type);
export function nodeLabels(
  nodes: ModelNode[],
  equipment: Equipment[],
  registry: Registry,
): Map<string, string> {
  const owners = new Map(equipment.map((e) => [e.id, e]));
  const labels = nodes.map((n) => {
    const owner = n.equipment_id ? owners.get(n.equipment_id) : null;
    return n.kind === "ELECTRICAL_NODE"
      ? n.label || `Electrical node · ${n.id.slice(0, 8)}`
      : `${owner ? equipmentLabel(owner, registry) : "Equipment"} · ${n.terminal_key}${n.label ? ` · ${n.label}` : ""}`;
  });
  const counts = new Map<string, number>();
  labels.forEach((label) => counts.set(label, (counts.get(label) ?? 0) + 1));
  return new Map(
    nodes.map((n, i) => [
      n.id,
      counts.get(labels[i])! > 1
        ? `${labels[i]} · ${n.id.slice(0, 8)}`
        : labels[i],
    ]),
  );
}

/** Compare nullable text by its displayed draft, so untouched null/empty stays untouched. */
export function changedText(
  original: Record<string, string | null>,
  draft: Record<string, string>,
): Record<string, string | null> {
  return Object.fromEntries(
    Object.entries(draft)
      .filter(([key, value]) => value !== (original[key] ?? ""))
      .map(([key, value]) => [key, value === "" ? null : value]),
  );
}

export type EquipmentSnapshot = {
  equipment: Equipment;
  attributes: EquipmentAttribute[];
  terminals: ModelNode[];
};
export type EquipmentEditorInput = {
  general?: EquipmentPatch;
  attributes?: Record<string, AttributeInput>;
  create_terminals?: { terminal_key: string; label: string | null }[];
  update_terminals?: (NodePatch & { id: string })[];
  remove_terminals?: string[];
  restore_terminals?: string[];
};
export const getEquipmentEditor = (p: string, r: string, id: string) =>
  request<EquipmentSnapshot>(`${base(p, r)}/equipment/${id}/editor`);
export const saveEquipmentEditor = (
  p: string,
  r: string,
  id: string,
  body: EquipmentEditorInput,
) =>
  send<EquipmentSnapshot>(
    `${base(p, r)}/equipment/${id}/editor`,
    "PATCH",
    body,
  );
