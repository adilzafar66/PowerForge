export type RevisionDestination =
  "overview" | "documents" | "equipment" | "topology";

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
    query.delete("equipment");
  }
  if (destination === "overview") {
    query.set("view", "overview");
    query.delete("workspace");
    query.delete("document");
    query.delete("equipment");
  } else if (destination === "documents") {
    query.delete("workspace");
    query.delete("view");
    query.delete("equipment");
  } else if (destination) {
    query.set("workspace", "model");
    query.set("view", destination);
    query.delete("document");
    if (destination === "topology") query.delete("equipment");
  }
  return `/projects/${encodeURIComponent(projectId)}/revisions/${encodeURIComponent(revisionId)}${query.size ? `?${query}` : ""}`;
}
