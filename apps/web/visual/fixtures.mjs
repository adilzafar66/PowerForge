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
  processing: {
    status: "COMPLETED",
    attempt_count: 1,
    pages_processed: 2,
    pages_total: 2,
    error_code: null,
    error_message: null,
  },
  classification: {
    enabled: true,
    suggestion: {
      prediction_id: "pred-doc",
      predicted_type: "SINGLE_LINE_DIAGRAM",
      confidence_band: "HIGH",
      accepted: true,
      requires_page_classification: false,
    },
    attempt: {
      id: "run-doc",
      status: "COMPLETED",
      stage: "DOCUMENT",
      pages_total: 2,
      pages_classified: 2,
      error_code: null,
    },
  },
};
const fileOf = (id, name, size) => ({
  ...document.document,
  id: `file-${id}`,
  original_filename: name,
  size_bytes: size,
  sha256: id.padEnd(64, "0"),
});
/** One document per register state: review, running, failed, removed. */
export const documents = [
  document,
  {
    ...document,
    id: "doc-panels",
    document: fileOf("panels", "Panel_Schedules_Level2.pdf", 8_493_465),
    origin: "INHERITED",
    inherited_from_revision_id: "old",
    inherited_from_revision_identifier: "A",
    document_type: "UNKNOWN",
    document_number: "E-420",
    description: null,
    added_at: "2026-01-11T12:00:00Z",
    processing: {
      ...document.processing,
      pages_processed: 28,
      pages_total: 28,
    },
    classification: {
      enabled: true,
      suggestion: {
        ...document.classification.suggestion,
        prediction_id: "pred-panels",
        predicted_type: "PANEL_SCHEDULE",
        confidence_band: "MEDIUM",
        accepted: false,
      },
      attempt: { ...document.classification.attempt, id: "run-panels" },
    },
  },
  {
    ...document,
    id: "doc-tx",
    document: fileOf("tx", "TX1_750kVA_Shop_Drawings.pdf", 7_130_316),
    document_type: "TRANSFORMER_SHOP_DRAWING",
    document_number: null,
    description: null,
    added_at: "2026-01-12T13:00:00Z",
    processing: {
      ...document.processing,
      status: "RUNNING",
      pages_processed: 12,
      pages_total: 18,
    },
    classification: { enabled: true, suggestion: null, attempt: null },
  },
  {
    ...document,
    id: "doc-notes",
    document: fileOf("notes", "Distribution_Notes_RevB.pdf", 1_258_291),
    document_type: "ELECTRICAL_DRAWING",
    document_number: "E-002",
    description: null,
    added_at: "2026-01-10T12:00:00Z",
    processing: {
      ...document.processing,
      status: "FAILED",
      pages_processed: 0,
      pages_total: null,
      error_code: "render_failed",
      error_message: "The PDF could not be rendered.",
    },
    classification: { enabled: true, suggestion: null, attempt: null },
  },
  {
    ...document,
    id: "doc-old",
    document: fileOf("old", "Legacy_Riser_Diagram.pdf", 655_360),
    status: "REMOVED",
    removed_at: stamp,
    document_type: "OTHER",
    document_number: "E-900",
    description: null,
    added_at: "2026-01-09T12:00:00Z",
    processing: { ...document.processing, pages_processed: 1, pages_total: 1 },
    classification: { enabled: true, suggestion: null, attempt: null },
  },
];
const artifacts = [
  {
    artifact_type: "ANALYSIS_IMAGE",
    mime_type: "image/png",
    width_px: 1700,
    height_px: 2200,
  },
  {
    artifact_type: "THUMBNAIL",
    mime_type: "image/webp",
    width_px: 618,
    height_px: 800,
  },
  {
    artifact_type: "NATIVE_TEXT",
    mime_type: "text/plain",
    width_px: null,
    height_px: null,
  },
];
export const pages = [1, 2].map((page_number) => ({
  id: `page-${page_number}`,
  page_number,
  source_width: "612",
  source_height: "792",
  source_unit: "POINTS",
  rotation_degrees: 0,
  native_text_char_count: page_number === 1 ? 1840 : 0,
  artifacts: page_number === 1 ? artifacts : artifacts.slice(0, 2),
}));
function sheet(title, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="850" height="1100" viewBox="0 0 850 1100"><rect width="850" height="1100" fill="#fff"/><g fill="none" stroke="#667889"><rect x="34" y="34" width="782" height="1030"/><rect x="34" y="970" width="782" height="94"/><path d="M480 970v94M672 970v94"/></g><g fill="#182638" font-family="Arial,sans-serif"><text x="48" y="86" font-size="22" font-weight="700">${title}</text><text x="496" y="1025" font-size="18" font-weight="700">E-001</text><text x="48" y="1025" font-size="17" font-weight="700">NORTH SUBSTATION</text></g>${body}</svg>`;
}
const pageImages = {
  "page-1": sheet(
    "SINGLE LINE DIAGRAM",
    `<g stroke="#344c60" stroke-width="3" fill="none"><path d="M420 189v75M420 274v102M420 488v150"/><path d="M290 275h260M260 640h320"/><circle cx="420" cy="420" r="29"/><circle cx="420" cy="445" r="29"/><path d="M340 640v95M510 640v95"/></g><g fill="#253d50" font-family="Arial,sans-serif" font-size="16"><text x="290" y="166" font-weight="700">UTILITY SOURCE</text><text x="490" y="400" font-weight="700">TX-1</text><text x="490" y="426">750 kVA</text><text x="300" y="624">LV BUS · 600 V</text></g>`,
  ),
  "page-2": sheet(
    "TRANSFORMER SCHEDULE",
    `<g stroke="#899aa8" fill="none"><rect x="54" y="238" width="740" height="320"/><path d="M54 294h740M54 358h740M54 422h740M54 486h740M448 238v320"/></g><g fill="#253d50" font-family="Arial,sans-serif" font-size="17"><text x="75" y="334">Rated power</text><text x="474" y="334">750 kVA</text><text x="75" y="398">Primary voltage</text><text x="474" y="398">12.47 kV</text><text x="75" y="462">Secondary voltage</text><text x="474" y="462">600 V</text></g>`,
  ),
};
/** Page images for signed artifact URLs. SVG keeps the fixture dependency-free. */
export function fixtureAsset(url) {
  const match = url.pathname.match(/^\/fixture-assets\/(page-\d)\.svg$/);
  if (!match || !pageImages[match[1]]) return undefined;
  return { type: "image/svg+xml", body: pageImages[match[1]] };
}
function documentDetail(row) {
  return {
    ...row.classification,
    confidence_score: row.classification.suggestion ? 0.91 : null,
    alternatives: [],
    rationale: row.classification.suggestion
      ? "Title block and one-line symbols match a single line diagram."
      : null,
  };
}
function documentResponse(url, rest) {
  const [, id, tail = ""] = rest.match(/^\/([^/]+)(.*)$/) ?? [];
  const row = documents.find((d) => d.id === id);
  if (!row) return undefined;
  if (!tail) return row;
  if (tail === "/classification") return documentDetail(row);
  if (tail === "/classification/pages")
    return {
      items: pages.map((p) => ({
        page_number: p.page_number,
        predicted_type:
          p.page_number === 1 ? "SINGLE_LINE_DIAGRAM" : "EQUIPMENT_SCHEDULE",
        confidence_band: "HIGH",
      })),
    };
  if (tail === "/processing")
    return {
      processing: row.processing,
      processor_version: "1.4.0",
      profile_version: "2026.1",
      profile_hash: "c0ffee",
    };
  if (tail === "/pages")
    return row.processing?.status === "COMPLETED"
      ? { items: row.id === "doc" ? pages : pages.slice(0, 1) }
      : {
          __status: 409,
          detail: {
            detail: "Processing has not completed for this document.",
            code: "processing_not_complete",
          },
        };
  const artifact = tail.match(/^\/pages\/(page-\d)\/artifacts\/(\w+)\/url$/);
  if (artifact)
    return {
      url: `${url.origin}/fixture-assets/${artifact[1]}.svg`,
      expires_at: "2099-01-01T00:00:00Z",
      filename: `${artifact[1]}.png`,
    };
  if (tail === "/download-url")
    return {
      url: `${url.origin}/fixture-assets/page-1.svg`,
      expires_at: "2099-01-01T00:00:00Z",
      filename: row.document.original_filename,
    };
  return undefined;
}
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
  {
    ...audit,
    id: "t3",
    kind: "EQUIPMENT_TERMINAL",
    managed_by_profile: false,
    equipment_id: "e1",
    terminal_key: "SPARE",
    label: "Spare stub",
    inherited_from_node_id: null,
  },
  {
    ...audit,
    id: "n-removed",
    kind: "ELECTRICAL_NODE",
    managed_by_profile: false,
    equipment_id: null,
    terminal_key: null,
    label: "Spare junction",
    inherited_from_node_id: null,
    lifecycle_status: "REMOVED",
    removed_at: stamp,
  },
];
export const connections = [
  {
    ...audit,
    id: "c1",
    from_node_id: "t1",
    to_node_id: "n1",
    connection_kind: "ELECTRICAL",
    direction: "UNDIRECTED",
    phase_configuration: "3",
    nominal_voltage: "13.8",
    nominal_voltage_unit: "kV",
    confidence: null,
    inherited_from_connection_id: null,
  },
  {
    ...audit,
    id: "c2",
    from_node_id: "t1",
    to_node_id: "n1",
    connection_kind: "ELECTRICAL",
    direction: "NOMINAL_FROM_TO",
    phase_configuration: null,
    nominal_voltage: "600",
    nominal_voltage_unit: "V",
    confidence: null,
    inherited_from_connection_id: null,
  },
  {
    ...audit,
    id: "c-removed",
    from_node_id: "n-removed",
    to_node_id: "t2",
    connection_kind: "GROUNDING",
    direction: "UNDIRECTED",
    phase_configuration: null,
    nominal_voltage: null,
    nominal_voltage_unit: null,
    confidence: null,
    inherited_from_connection_id: null,
    lifecycle_status: "REMOVED",
    removed_at: stamp,
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
  if (suffix === "/documents") {
    const search = url.searchParams.get("search")?.toLowerCase();
    return {
      items: documents.filter(
        (d) =>
          !search ||
          [d.document.original_filename, d.document_number, d.description].some(
            (v) => v?.toLowerCase().includes(search),
          ),
      ),
    };
  }
  if (suffix.startsWith("/documents/"))
    return documentResponse(url, suffix.slice("/documents".length));
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
