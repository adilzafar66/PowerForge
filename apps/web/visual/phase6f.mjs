// Synthetic read fixtures for the production UI. These do not call a worker or provider.
const id = (family, value) => `${family}0000000-0000-4000-8000-${String(value).padStart(12, "0")}`;
const created_at = "2026-01-19T10:00:00Z";
const processing_run_id = id(1, 1);
const engineering = {
  id: id(2, 1), status: "COMPLETED", processing_run_id, created_at,
  profile_key: "engineering-openai-enriched-v1",
};
const tables = { ...engineering, id: id(3, 1), profile_key: "tables-openai-enriched-v1" };
const enrichment = { ...engineering, id: id(4, 1), profile_key: "source-layout-v1" };

const groups = Array.from({ length: 52 }, (_, index) => {
  const family = index % 2 ? "engineering" : "tables";
  const number = index + 1;
  return {
    source_group_id: id(5, number),
    run_id: family === "engineering" ? engineering.id : tables.id,
    family,
    tag_text: number === 1 ? "TX-1" : `TX-${String(number).padStart(3, "0")}`,
    label: "Transformer schedule",
    equipment_type_hint: "TWO_WINDING_TRANSFORMER",
    page_numbers: [family === "engineering" ? 1 : 2],
    candidate_count: 1,
  };
});

const candidateFor = (group) => {
  const number = Number(group.source_group_id.slice(-12));
  const page = group.page_numbers[0];
  const source = {
    id: id(7, number), source_page_number: page,
    source_kind: page === 2 ? "OCR_TEXT" : "NATIVE_TEXT",
    source_snippet: "750 kVA",
    grounding_precision: "TEXT_OFFSETS",
    source_locator: {
      reading_basis: page === 2 ? "OCR" : "NATIVE_PDF",
      geometry_basis: page === 2 ? "OCR_ENGINE" : "NATIVE_DOCUMENT",
    },
  };
  return {
    id: id(6, number), run_id: group.run_id, source_group_id: group.source_group_id,
    source_group: { tag_text: group.tag_text, label: group.label },
    kind: "ATTRIBUTE_VALUE", raw_text: "Rated power", raw_value: "750.0", raw_unit: "kVA",
    mapping_status: "MAPPED", equipment_type_key: group.equipment_type_hint,
    observed_tag: null, attribute_key: "rated_apparent_power", numeric_value: "750",
    integer_value: null, text_value: null, boolean_value: null, unit: "kVA",
    reason_code: null, explanation: null, evidence: [{ role: "PRIMARY", evidence: source }],
  };
};

function pageResponse(items, params) {
  const limit = Number(params.get("limit")) || 25;
  const offset = Number(params.get("offset")) || 0;
  return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
}

export function extractionStatus(documents, params, revision) {
  return {
    items: params.getAll("revision_document_ids").flatMap((id) => {
      const row = documents.find((document) => document.id === id);
      if (!row) return [];
      const current = id === "doc";
      return [{
        revision_document_id: id,
        processing_run_id: row.processing?.status === "COMPLETED" ? processing_run_id : null,
        ineligible_reason: row.status === "REMOVED" ? "REMOVED"
          : revision === "old" ? "READ_ONLY"
          : row.processing?.status !== "COMPLETED" ? "PROCESSING_REQUIRED" : null,
        engineering: { latest_attempt: current ? engineering : null, effective_result: current ? engineering : null },
        tables: { latest_attempt: current ? tables : null, effective_result: current ? tables : null },
        enrichment: current ? enrichment : null,
      }];
    }),
  };
}

export function extractionResponse(url, tail) {
  const params = url.searchParams;
  const selected = [params.get("engineering_run_id"), params.get("tables_run_id")];
  if (tail === "/extraction/groups") {
    const search = params.get("search")?.toLowerCase();
    return pageResponse(groups.filter((group) => selected.includes(group.run_id)
      && (!params.get("page") || group.page_numbers.includes(Number(params.get("page"))))
      && (!search || `${group.tag_text} transformer rated power 750 kVA`.toLowerCase().includes(search))), params);
  }
  const candidateMatch = tail.match(/^\/extraction\/runs\/([^/]+)\/candidates$/);
  if (candidateMatch) {
    const group = groups.find((item) => item.run_id === candidateMatch[1] && item.source_group_id === params.get("source_group_id"));
    return pageResponse(group ? [candidateFor(group)] : [], params);
  }
  const evidenceMatch = tail.match(/^\/extraction\/evidence\/([^/]+)$/);
  if (evidenceMatch) {
    const group = groups.find((item) => id(7, Number(item.source_group_id.slice(-12))) === evidenceMatch[1]);
    if (!group) return undefined;
    const source = candidateFor(group).evidence[0].evidence;
    const page = source.source_page_number;
    return {
      ...source, run_id: group.run_id, processing_run_id, page_number: page,
      region: page === 2
        ? { x: "0.55", y: "0.286", width: "0.088", height: "0.022" }
        : { x: "0.57", y: "0.371", width: "0.088", height: "0.022" },
      text_start: 0, text_end: source.source_snippet.length,
      source_image_url: `${url.origin}/fixture-assets/page-${page}.svg`,
      source_image_width_px: 850, source_image_height_px: 1100, artifact_url_expires_seconds: 90,
    };
  }
  const historyRun = (run) => ({
    ...run, selected_pages: run === engineering ? [1] : [2], pages_processed: 1,
    model: run === enrichment ? null : "Fixture model", error_code: null,
  });
  if (tail === "/extraction/runs") {
    return pageResponse([historyRun(params.get("family") === "tables" ? tables : engineering)], params);
  }
  if (tail === "/source-enrichment/runs") return pageResponse([historyRun(enrichment)], params);
  const runMatch = tail.match(/^\/(?:extraction|source-enrichment)\/runs\/([^/]+)(?:\/(tables|sources))?$/);
  if (!runMatch) return undefined;
  const run = [engineering, tables, enrichment].find((item) => item.id === runMatch[1]);
  if (!run) return undefined;
  if (runMatch[2] === "sources") return { items: [] };
  if (runMatch[2] === "tables") {
    return pageResponse([{
      id: id(8, 1), table_kind: "UNCLASSIFIED", layout: {
        title: "Transformer schedule · page 2", metadata: { structure_basis: "OCR_GEOMETRY_SUPPORTED" },
        cells: [
          { id: "header", text: "Rated power", row: 0, column: 0, row_span: 1, column_span: 1, is_header: true },
          { id: "value", text: "750 kVA", row: 0, column: 1, row_span: 1, column_span: 1, is_header: false },
        ],
      },
    }], params);
  }
  return {
    run: historyRun(run), attempts: [],
    coverage: { required_units: 2, completed_required_units: 2 },
    can_cancel: false, can_retry: false,
  };
}
