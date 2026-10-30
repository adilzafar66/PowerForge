/** Stable identities contain all server filters, never local drafts or refresh counters. */
export const keys = {
  projects: ["projects"] as const,
  project: (p: string) => ["project", p] as const,
  revisions: (p: string) => ["revisions", p] as const,
  revision: (p: string, r: string) => ["revision", p, r] as const,
  registry: ["registry"] as const,
  model: (p: string, r: string) => ["model", p, r] as const,
  equipment: (p: string, r: string, filters: object = {}) =>
    ["model", p, r, "equipment", filters] as const,
  editor: (p: string, r: string, id: string) =>
    ["model", p, r, "editor", id] as const,
  nodes: (p: string, r: string) => ["model", p, r, "nodes"] as const,
  connections: (p: string, r: string) =>
    ["model", p, r, "connections"] as const,
  documents: (p: string, r: string) => ["documents", p, r] as const,
  documentList: (p: string, r: string, search: string) =>
    ["documents", p, r, "list", search] as const,
  document: (p: string, r: string, id: string) =>
    ["documents", p, r, "detail", id] as const,
};
