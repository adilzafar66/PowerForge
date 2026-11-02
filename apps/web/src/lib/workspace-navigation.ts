export type RevisionDestination =
  "overview" | "documents" | "equipment" | "topology";

export type EquipmentTab = "general" | "attributes" | "terminals";
export const EQUIPMENT_TABS: readonly EquipmentTab[] = [
  "general",
  "attributes",
  "terminals",
];
export function equipmentTab(value: string | null): EquipmentTab {
  return EQUIPMENT_TABS.find((tab) => tab === value) ?? "general";
}

/** Editor mode and tab only exist alongside a selected equipment id. */
export function clearEquipment(query: URLSearchParams) {
  query.delete("equipment");
  query.delete("equipmentMode");
  query.delete("equipmentTab");
}

/** Topology inspector selection never travels across revisions or workspaces. */
export function clearTopology(query: URLSearchParams) {
  query.delete("node");
  query.delete("connection");
}

/** Preserve unrelated query state, but never carry object IDs across revisions. */
export function revisionHref(
  projectId: string,
  revisionId: string,
  currentRevisionId: string | undefined,
  search: string,
  destination?: RevisionDestination,
) {
  const query = new URLSearchParams(search);
  query.delete("section");
  query.delete("page");
  query.delete("mode");
  if (revisionId !== currentRevisionId) {
    query.delete("document");
    clearEquipment(query);
    clearTopology(query);
  }
  if (destination === "overview") {
    query.set("view", "overview");
    query.delete("workspace");
    query.delete("document");
    clearEquipment(query);
    clearTopology(query);
  } else if (destination === "documents") {
    query.delete("workspace");
    query.delete("view");
    clearEquipment(query);
    clearTopology(query);
  } else if (destination) {
    query.set("workspace", "model");
    query.set("view", destination);
    query.delete("document");
    if (destination === "topology") clearEquipment(query);
    if (destination === "equipment") clearTopology(query);
  }
  return `/projects/${encodeURIComponent(projectId)}/revisions/${encodeURIComponent(revisionId)}${query.size ? `?${query}` : ""}`;
}

export type ViewerMode = "document" | "evidence";

/** Dedicated viewer route. `page` is 1-based; document mode and page 1 stay implicit. */
export function documentViewerHref(
  projectId: string,
  revisionId: string,
  documentId: string,
  options: { page?: number | null; mode?: ViewerMode } = {},
) {
  const query = new URLSearchParams();
  if (options.page && options.page > 1) query.set("page", String(options.page));
  if (options.mode === "evidence") query.set("mode", "evidence");
  return `/projects/${encodeURIComponent(projectId)}/revisions/${encodeURIComponent(revisionId)}/documents/${encodeURIComponent(documentId)}${query.size ? `?${query}` : ""}`;
}
