import type {
  ConnectionKind,
  Direction,
  LifecycleFilter,
  ModelConnection,
  ModelNode,
} from "@/lib/engineering-model";

export function nodeKindLabel(kind: ModelNode["kind"]) {
  return kind === "ELECTRICAL_NODE" ? "Electrical node" : "Equipment terminal";
}

export function connectionKindLabel(kind: ConnectionKind) {
  return kind === "ELECTRICAL"
    ? "Electrical"
    : kind === "GROUNDING"
      ? "Grounding"
      : "Other";
}

export function directionLabel(direction: Direction) {
  return direction === "UNDIRECTED" ? "Undirected" : "Nominal from → to";
}

export function voltageText(row: ModelConnection) {
  if (row.nominal_voltage == null || row.nominal_voltage === "") return "—";
  return row.nominal_voltage_unit
    ? `${row.nominal_voltage} ${row.nominal_voltage_unit}`
    : row.nominal_voltage;
}

export function topologyCounts(
  nodes: ModelNode[],
  connections: ModelConnection[],
) {
  const activeNodes = nodes.filter(
    (row) => row.lifecycle_status === "ACTIVE",
  ).length;
  const activeConnections = connections.filter(
    (row) => row.lifecycle_status === "ACTIVE",
  ).length;
  const removed =
    nodes.filter((row) => row.lifecycle_status === "REMOVED").length +
    connections.filter((row) => row.lifecycle_status === "REMOVED").length;
  return { activeNodes, activeConnections, removed };
}

export function matchesLifecycle(
  row: { lifecycle_status: string },
  lifecycle: LifecycleFilter,
) {
  return lifecycle === "ALL" || row.lifecycle_status === lifecycle;
}

export function matchesNodeSearch(
  query: string,
  node: ModelNode,
  displayName: string,
  equipmentName: string | null,
) {
  if (!query) return true;
  const haystack = [displayName, equipmentName, node.terminal_key, node.label]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

export function matchesConnectionSearch(
  query: string,
  fromLabel: string,
  toLabel: string,
) {
  if (!query) return true;
  return `${fromLabel} ${toLabel}`.toLowerCase().includes(query);
}

export function isPositiveFiniteNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return true;
  const number = Number(trimmed);
  return Number.isFinite(number) && number > 0;
}

export function incidentActiveCount(
  nodeId: string,
  connections: ModelConnection[],
) {
  return connections.filter(
    (row) =>
      row.lifecycle_status === "ACTIVE" &&
      (row.from_node_id === nodeId || row.to_node_id === nodeId),
  ).length;
}
