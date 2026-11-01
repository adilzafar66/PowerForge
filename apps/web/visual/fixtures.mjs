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
export const equipmentRows = [
  equipment,
  {
    ...equipment,
    id: "e2",
    equipment_type: "TRANSFORMER",
    tag: "TX-1",
    name: "Station service transformer",
    lineage_id: "l2",
  },
  {
    ...equipment,
    id: "e3",
    tag: "SWGR-0",
    name: "Retired switchgear",
    lineage_id: "l3",
    lifecycle_status: "REMOVED",
    removed_at: stamp,
  },
];
const terminal = (id, terminal_key, label) => ({
  ...audit,
  id,
  kind: "EQUIPMENT_TERMINAL",
  managed_by_profile: true,
  equipment_id: "e1",
  terminal_key,
  label,
  inherited_from_node_id: null,
});
export const terminals = [
  terminal("t1", "LINE", "Line side"),
  terminal("t2", "LOAD", "Load side"),
];
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
  ...terminals,
];
export const connections = [
  {
    ...audit,
    id: "c1",
    from_node_id: "t1",
    to_node_id: "n1",
    connection_kind: "ELECTRICAL",
    direction: "UNDIRECTED",
    phase_configuration: null,
    nominal_voltage: null,
    nominal_voltage_unit: null,
    confidence: null,
    inherited_from_connection_id: null,
  },
];
const definition = (key, display_name, value_type, extra = {}) => ({
  key,
  display_name,
  value_type,
  canonical_unit: null,
  required: false,
  critical: false,
  allowed_values: [],
  notes: null,
  display_order: 0,
  requirement_group: null,
  requirement_condition: null,
  supported_input_units: [],
  ...extra,
});
export const registry = {
  registry_version: "visual-fixture",
  equipment_types: [
    {
      key: "SWITCHGEAR",
      display_name: "Switchgear",
      attributes: [
        definition("nominal_voltage", "Nominal voltage", "NUMBER", {
          canonical_unit: "kV",
          required: true,
          critical: true,
          display_order: 1,
          supported_input_units: ["kV", "V"],
        }),
        definition("phase_count", "Phase count", "INTEGER", {
          required: true,
          critical: true,
          display_order: 2,
        }),
        definition("continuous_current", "Continuous current", "NUMBER", {
          canonical_unit: "A",
          required: true,
          display_order: 3,
          supported_input_units: ["A", "kA"],
        }),
        definition("interrupting_rating", "Interrupting rating", "NUMBER", {
          canonical_unit: "kA",
          critical: true,
          display_order: 4,
          requirement_condition:
            "Required when protective devices are modeled.",
          supported_input_units: ["kA"],
        }),
        definition("bus_material", "Bus material", "ENUM", {
          display_order: 5,
          allowed_values: ["COPPER", "ALUMINUM"],
          notes: "Use the manufacturer nameplate where available.",
        }),
      ],
      requirements: [],
    },
    {
      key: "TRANSFORMER",
      display_name: "Transformer",
      attributes: [],
      requirements: [],
    },
  ],
  requirement_rules: [],
  unit_families: [],
};
const attribute = (attribute_key, value_type, values) => ({
  id: `a-${attribute_key}`,
  project_id: "p",
  revision_id: "r",
  created_at: stamp,
  created_by: null,
  updated_at: stamp,
  updated_by: null,
  equipment_id: "e1",
  attribute_key,
  value_type,
  numeric_value: null,
  integer_value: null,
  text_value: null,
  boolean_value: null,
  unit: null,
  information_state: "PRESENT",
  verification_state: "ENGINEER_REVIEWED",
  origin: "MANUAL",
  confidence: null,
  inherited_from_attribute_id: null,
  ...values,
});
export const attributes = [
  attribute("nominal_voltage", "NUMBER", { numeric_value: "13.8", unit: "kV" }),
  attribute("phase_count", "INTEGER", { integer_value: "3" }),
  attribute("continuous_current", "NUMBER", {
    numeric_value: "1200",
    unit: "A",
  }),
  attribute("interrupting_rating", "NUMBER", {
    information_state: "MISSING",
    verification_state: "UNVERIFIED",
  }),
  attribute("bus_material", "ENUM", {
    information_state: "NOT_POPULATED",
    verification_state: "UNVERIFIED",
    origin: null,
  }),
];
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
  if (suffix === "/equipment") {
    const status = url.searchParams.get("lifecycle_status") || "ACTIVE";
    const type = url.searchParams.get("equipment_type");
    const search = url.searchParams.get("search")?.toLowerCase();
    return {
      items: equipmentRows.filter(
        (e) =>
          (status === "ALL" || e.lifecycle_status === status) &&
          (!type || e.equipment_type === type) &&
          (!search ||
            [e.tag, e.name, e.description].some((v) =>
              v?.toLowerCase().includes(search),
            )),
      ),
    };
  }
  if (suffix === "/equipment/e1") return equipment;
  if (suffix === "/equipment/e1/editor")
    return { equipment, attributes, terminals };
  if (suffix === "/equipment/e1/attributes") return { items: attributes };
  if (suffix === "/nodes") return { items: nodes };
  if (suffix === "/connections") return { items: connections };
  return undefined;
}
