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
  if (revisionId !== currentRevisionId) {
    query.delete("document");
    clearEquipment(query);
  }
  if (destination === "overview") {
    query.set("view", "overview");
    query.delete("workspace");
    query.delete("document");
    clearEquipment(query);
  } else if (destination === "documents") {
    query.delete("workspace");
    query.delete("view");
    clearEquipment(query);
  } else if (destination) {
    query.set("workspace", "model");
    query.set("view", destination);
    query.delete("document");
    if (destination === "topology") clearEquipment(query);
  }
  return `/projects/${encodeURIComponent(projectId)}/revisions/${encodeURIComponent(revisionId)}${query.size ? `?${query}` : ""}`;
}
