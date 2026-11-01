/** Synthetic records only. Served to both Next SSR and the browser. */
const stamp = "2026-01-12T12:00:00Z";
export const project = {
  id: "p",
  project_number: "PF-2601",
  project_name: "North Substation",
  project_address: "120 Industrial Road",
  project_scope: "Replace the main distribution equipment.",
  client_name: "North Utilities",
  description: "Electrical distribution upgrade",
  engineer_names: ["Alex Chen", "Sam Patel"],
  status: "ACTIVE",
  created_at: stamp,
  updated_at: stamp,
  archived_at: null,
  status_before_archive: null,
  created_by: null,
  active_revision_identifier: "B",
};
export const projects = [
  project,
  ...["PAUSED", "CANCELLED", "ARCHIVED"].map((status, i) => ({
    ...project,
    id: `p${i}`,
    project_number: `PF-260${i + 2}`,
    project_name: ["Water Treatment", "Central Plant", "East Feeder"][i],
    status,
    active_revision_identifier: null,
  })),
];
export const revisions = ["C", "B", "A"].map((identifier, i) => ({
  id: ["draft", "r", "old"][i],
  project_id: "p",
  identifier,
  description: ["Review updates", "Issued for construction", "Initial design"][
    i
  ],
  status: ["DRAFT", "ACTIVE", "SUPERSEDED"][i],
  created_at: `2026-01-${15 - i}T12:00:00Z`,
  updated_at: stamp,
  created_by: null,
  based_on_revision_id: i === 2 ? null : ["r", "old"][i],
  based_on_identifier: i === 2 ? null : ["B", "A"][i],
  system_frequency: "60.0000000000000000001",
  system_phase_count: 3,
}));
export const document = {
  id: "doc",
  revision_id: "r",
  document: {
    id: "file",
    original_filename: "Substation_SLD.pdf",
    mime_type: "application/pdf",
    file_extension: "pdf",
    size_bytes: 2048,
    sha256: "a".repeat(64),
    uploaded_at: stamp,
  },
  origin: "UPLOADED",
  inherited_from_revision_id: null,
  inherited_from_revision_identifier: null,
  status: "INCLUDED",
  document_type: "SINGLE_LINE_DIAGRAM",
  document_number: "E-001",
  description: "Main single line diagram",
  notes: null,
  added_at: stamp,
  removed_at: null,
  processing: null,
  classification: { enabled: true, suggestion: null, attempt: null },
};
const audit = {
  project_id: "p",
  revision_id: "r",
  created_at: stamp,
  updated_at: stamp,
  created_by: null,
  updated_by: null,
  lifecycle_status: "ACTIVE",
  origin: "MANUAL",
  verification_state: "ENGINEER_REVIEWED",
  removed_at: null,
  removed_by: null,
};
export const equipment = {
  ...audit,
  id: "e1",
  equipment_type: "SWITCHGEAR",
  tag: "SWGR-1",
  name: "Main switchgear",
  description: null,
  lineage_id: "l1",
  inherited_from_equipment_id: null,
};
export const nodes = [
  {
    ...audit,
    id: "n1",
    kind: "ELECTRICAL_NODE",
    managed_by_profile: false,
    equipment_id: null,
    terminal_key: null,
    label: "Main bus",
    inherited_from_node_id: null,
  },
];
export const registry = {
  registry_version: "visual-fixture",
  equipment_types: [
    {
      key: "SWITCHGEAR",
      display_name: "Switchgear",
      attributes: [],
      requirements: [],
    },
  ],
  requirement_rules: [],
  unit_families: [],
};
export function fixtureResponse(url, scenario) {
  const path = url.pathname;
  if (path === "/health")
    return { status: "ok", service: "PowerForge", version: "visual-fixture" };
  if (path === "/ready")
    return {
      status: "ok",
      service: "PowerForge",
      version: "visual-fixture",
      database: "ok",
      redis: "ok",
    };
  if (path === "/api/engineering-model/registry") return registry;
  if (path === "/api/projects") {
    let items = scenario === "empty" ? [] : projects;
    if (url.searchParams.get("status"))
      items = items.filter((p) => p.status === url.searchParams.get("status"));
    if (url.searchParams.get("search"))
      items = items.filter((p) =>
        JSON.stringify(p)
          .toLowerCase()
          .includes(url.searchParams.get("search").toLowerCase()),
      );
    return { items };
  }
  if (path === "/api/projects/p")
    return scenario === "readonly"
      ? { ...project, status: "ARCHIVED" }
      : project;
  if (path === "/api/projects/p/revisions") return { items: revisions };
  const revision = path.match(
    /^\/api\/projects\/p\/revisions\/(r|draft|old)(.*)$/,
  );
  if (!revision) return undefined;
  const suffix = revision[2];
  if (!suffix) return revisions.find((r) => r.id === revision[1]);
  if (suffix === "/documents") return { items: [document] };
  if (suffix === "/documents/doc/classification")
    return { enabled: true, suggestion: null, attempt: null };
  if (suffix === "/equipment") return { items: [equipment] };
  if (suffix === "/equipment/e1") return equipment;
  if (suffix === "/equipment/e1/editor")
    return { equipment, attributes: [], terminals: [], connections: [] };
  if (suffix === "/equipment/e1/attributes") return { items: [] };
  if (suffix === "/nodes") return { items: nodes };
  if (suffix === "/connections") return { items: [] };
  return undefined;
}
