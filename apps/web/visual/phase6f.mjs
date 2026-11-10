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
const historicTables = { ...tables, id: id(3, 2), status: "PARTIALLY_COMPLETED", created_at: "2026-01-18T10:00:00Z" };

const groups = Array.from({ length: 52 }, (_, index) => {
  const family = index % 2 ? "engineering" : "tables";
  const number = index + 1;
  return {
    source_group_id: number === 3 ? null : id(5, number),
    run_id: family === "engineering" ? engineering.id : tables.id,
    family,
    tag_text: number === 1 ? "TX-1" : number === 3 ? null : `TX-${String(number).padStart(3, "0")}`,
    label: number === 3 ? null : "Transformer schedule",
    equipment_type_hint: number === 3 ? null : "TWO_WINDING_TRANSFORMER",
    page_numbers: [family === "engineering" ? 1 : 2],
    candidate_count: 1,
  };
});
const allGroups = [...groups, { ...groups[0], source_group_id: id(5, 53), run_id: historicTables.id }];

const candidateFor = (group) => {
  const number = group.source_group_id ? Number(group.source_group_id.slice(-12)) : 3;
  const page = group.page_numbers[0];
  // The spatial evaluation exercises native/OCR geometry and legacy page-only citations.
  const pageOnly = number === 3;
  const invalid = number === 4;
  const source = {
    id: id(7, number), source_page_number: page,
    source_kind: pageOnly ? "VISUAL_REGION" : page === 2 ? "OCR_TEXT" : "NATIVE_TEXT",
    source_snippet: pageOnly ? null : invalid ? "LV BUS · 600 V" : "750 kVA",
    grounding_precision: pageOnly ? "VISUAL_PAGE" : "TEXT_OFFSETS",
    source_locator: pageOnly ? null : {
      reading_basis: page === 2 ? "OCR" : "NATIVE_PDF",
      geometry_basis: page === 2 ? "OCR_ENGINE" : "NATIVE_DOCUMENT",
    },
  };
  return {
    id: id(6, number), run_id: group.run_id, source_group_id: group.source_group_id,
    source_group: group.source_group_id ? { tag_text: group.tag_text, label: group.label } : null,
    kind: pageOnly ? "UNMAPPED_OBSERVATION" : "ATTRIBUTE_VALUE",
    raw_text: pageOnly ? "Cooling class" : invalid ? "Bus voltage" : "Rated power",
    raw_value: pageOnly ? "Unclear" : invalid ? "600" : "750.0", raw_unit: pageOnly ? null : invalid ? "?" : "kVA",
    mapping_status: pageOnly ? "UNMAPPED" : invalid ? "INVALID" : "MAPPED", equipment_type_key: group.equipment_type_hint,
    observed_tag: null, attribute_key: pageOnly || invalid ? null : "rated_apparent_power",
    numeric_value: pageOnly || invalid ? null : "750", integer_value: null, text_value: null, boolean_value: null,
    unit: pageOnly || invalid ? null : "kVA", reason_code: null,
    explanation: pageOnly ? "Unknown attribute" : invalid ? "Unrecognized voltage unit" : null,
    evidence: [{ role: "PRIMARY", evidence: source }],
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
  const matchesFilters = (group, candidate) =>
    (!params.get("page") || group.page_numbers.includes(Number(params.get("page"))))
    && (!params.get("equipment_hint") || group.equipment_type_hint === params.get("equipment_hint"))
    && (!params.get("mapping_status") || candidate.mapping_status === params.get("mapping_status"));
  if (tail === "/extraction/groups") {
    const search = params.get("search")?.toLowerCase();
    return pageResponse(allGroups.filter((group) => {
      if (!selected.includes(group.run_id)) return false;
      const candidate = candidateFor(group);
      const searchable = [group.tag_text, group.label, candidate.raw_text, candidate.raw_value, candidate.raw_unit];
      return matchesFilters(group, candidate) && (!search || searchable.join(" ").toLowerCase().includes(search));
    }), params);
  }
  const candidateMatch = tail.match(/^\/extraction\/runs\/([^/]+)\/candidates$/);
  if (candidateMatch) {
    const group = allGroups.find((item) => item.run_id === candidateMatch[1] && (
      item.source_group_id ? item.source_group_id === params.get("source_group_id") : params.get("ungrouped") === "true"
    ));
    const candidate = group ? candidateFor(group) : null;
    const candidateId = params.get("candidate_id");
    return pageResponse(candidate && matchesFilters(group, candidate) && (!candidateId || candidate.id === candidateId) ? [candidate] : [], params);
  }
  const evidenceMatch = tail.match(/^\/extraction\/evidence\/([^/]+)$/);
  if (evidenceMatch) {
    const group = allGroups.find((item) => candidateFor(item).evidence[0].evidence.id === evidenceMatch[1]);
    if (!group) return undefined;
    const source = candidateFor(group).evidence[0].evidence;
    const page = source.source_page_number;
    const pageOnly = source.grounding_precision === "VISUAL_PAGE";
    return {
      ...source, run_id: group.run_id, processing_run_id, page_number: page,
      region: pageOnly ? null : page === 2
        ? { x: "0.55", y: "0.286", width: "0.088", height: "0.022" }
        : source.source_snippet === "750 kVA"
          ? { x: "0.57", y: "0.371", width: "0.088", height: "0.022" }
          : { x: "0.35", y: "0.55", width: "0.18", height: "0.022" },
      text_start: pageOnly ? null : 0, text_end: source.source_snippet?.length ?? null,
      source_image_url: `${url.origin}/fixture-assets/page-${page}.svg`,
      source_image_width_px: 850, source_image_height_px: 1100, artifact_url_expires_seconds: 90,
    };
  }
  const historyRun = (run) => ({
    ...run, selected_pages: run === engineering ? [1] : [2], pages_processed: 1,
    model: run === enrichment ? null : "Fixture model", error_code: null,
  });
  if (tail === "/extraction/runs") {
    const runs = params.get("family") === "tables" ? [tables, historicTables] : [engineering];
    return pageResponse(runs.map(historyRun), params);
  }
  if (tail === "/source-enrichment/runs") return pageResponse([historyRun(enrichment)], params);
  const runMatch = tail.match(/^\/(?:extraction|source-enrichment)\/runs\/([^/]+)(?:\/(tables|sources))?$/);
  if (!runMatch) return undefined;
  const run = [engineering, tables, historicTables, enrichment].find((item) => item.id === runMatch[1]);
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
    coverage: { required_units: 2, completed_required_units: run === historicTables ? 1 : 2 },
    can_cancel: false, can_retry: false,
  };
}

const operationId = id(9, 1);
let reviewedSelection = null;
let submittedSelection = null;

export function resetOperationsFixture() {
  reviewedSelection = null;
  submittedSelection = null;
}

export function operationsFixture(url, body, documents, revision) {
  const tail = url.pathname.split("/extraction/operations")[1];
  const byId = (id) => documents.find((row) => row.id === id);
  const processingId = (doc) => doc === "doc" ? processing_run_id : id(1, 2);

  if (tail === "/sources") {
    return {
      items: body.revision_document_ids.map((documentId) => {
        const row = byId(documentId);
        return {
          revision_document_id: documentId,
          filename: row.document.original_filename,
          processing_run_id: processingId(documentId),
          page_count: row.processing.pages_total,
          available_pages: Array.from({ length: row.processing.pages_total }, (_, index) => index + 1),
          error: null,
        };
      }),
      max_documents: 20, max_pages_per_document: 50, max_pages: 150, read_only: revision === "old",
    };
  }
  if (tail === "/preview") {
    reviewedSelection = body;
    return {
      items: body.documents.map((item) => ({
        revision_document_id: item.revision_document_id,
        filename: byId(item.revision_document_id).document.original_filename,
        processing_run_id: item.processing_run_id,
        error: null,
        pages: item.pages.map((page_number) => {
          const force_ocr = item.force_ocr_pages.includes(page_number);
          const ready = item.revision_document_id === "doc" && !force_ocr;
          return { page_number, force_ocr, reuse_preparation: ready, reuse_layout: ready };
        }),
      })),
      profiles: body.families.map((family) => ({
        family, key: family === "engineering" ? engineering.profile_key : tables.profile_key,
        provider: "openai", model: "Fixture model", enabled: true,
      })),
      errors: [], review_hash: "a".repeat(64), consent_version: "external-openai-v1",
      planned_runs: body.documents.length * body.families.length,
      provider_admissions: body.documents.reduce((total, item) => total + item.pages.length, 0) * body.families.length * 6,
      ocr_attempts: 84, parallel_documents: 2,
    };
  }
  if (tail === "" && body) {
    if (body.external_processing_consent !== true
      || body.review_hash !== "a".repeat(64)
      || JSON.stringify(body.selection) !== JSON.stringify(reviewedSelection)) return undefined;
    submittedSelection = body.selection;
    return { id: operationId };
  }
  if (tail === "") {
    const documentId = url.searchParams.get("revision_document_id");
    return { items: submittedSelection?.documents.some((item) => item.revision_document_id === documentId)
      ? [{ id: operationId, created_at }] : [] };
  }
  if (tail === `/${operationId}` && submittedSelection) {
    const step = (status, run_id = null) => ({
      run_id, status, error_code: null, attempts: run_id ? 2 : 0,
      unknown_provider_outcome: false, can_retry: false,
    });
    return {
      id: operationId, created_at, status: "RUNNING", cancel_requested: false, can_cancel: true,
      mode: submittedSelection.mode, provider_admissions: 120, unavailable_sources: 0,
      items: submittedSelection.documents.map((item) => {
        const ready = item.revision_document_id === "doc";
        return {
          ...item, filename: byId(item.revision_document_id).document.original_filename,
          status: "RUNNING", blocked_reason: null, can_resume: false,
          layout: ready ? step("REUSED") : step("RUNNING", enrichment.id),
          profiles: Object.fromEntries(submittedSelection.families.map((family) => [
            family, ready ? step("COMPLETED", family === "engineering" ? engineering.id : tables.id) : step("WAITING"),
          ])),
        };
      }),
    };
  }
  return undefined;
}
