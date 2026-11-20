// Synthetic Documents API fixtures for the browser harness.
const id = (prefix, value) => `${prefix}0000000-0000-4000-8000-${String(value).padStart(12, "0")}`;
const created_at = "2026-01-19T10:00:00Z";
const processing_run_id = id(1, 1);
const run = {
  id: id(2, 1), status: "COMPLETED", processing_run_id, created_at, profile_key: "phase-6r",
  selected_pages: [1, 2], pages_processed: 2, model: "Synthetic extraction", profile_version: "phase-6r-profile-v1",
  profile_hash: "digest", error_code: null,
};
const enrichment = { ...run, id: id(4, 1), profile_key: "source-layout-v1" };
const groups = Array.from({ length: 30 }, (_, index) => ({
  group_id: index === 3 ? "unassigned" : id(5, index + 1),
  kind: index === 3 ? "UNASSIGNED" : "EQUIPMENT", label: index === 3 ? "Ungrouped observations" : `TX-${String(index + 1).padStart(3, "0")}`,
  tag: index === 3 ? null : `TX-${String(index + 1).padStart(3, "0")}`,
  registry_type: index === 3 ? null : "TWO_WINDING_TRANSFORMER",
  page_numbers: [index === 3 ? 2 : 1], matching_candidate_count: index === 3 ? 1 : 2,
  matching_attribute_count: 1, matching_identification_count: index === 3 ? 0 : 1, source_description: "Transformer",
}));
const numberOf = (group) => group.group_id === "unassigned" ? 4 : Number(group.group_id.slice(-12));
const candidateFor = (group) => {
  const number = numberOf(group);
  return {
    id: id(6, number), page_id: id(1, group.page_numbers[0] + 10), attempt_id: id(8, 1),
    kind: "ATTRIBUTE", equipment_id: number === 4 ? null : group.group_id,
    association: number === 4 ? "UNASSIGNED" : "UNCERTAIN", raw_unmapped: number === 4,
    origin: "EXTRACTED", attribute_display_name: number === 4 ? null : "Rated Apparent Power (kVA)",
    proposed_value: null, proposed_unit: null, inference_explanation: null, inference_basis: null,
    source_expression: null, source_display_label: null, redundant_with_id: null,
    raw_label: "Rated apparent power", raw_value: "750", raw_unit: "kVA", qualifiers: [],
    value_form: "SINGLE", conflict: false, alternate_representations: [],
    proposed_attribute_key: number === 4 ? null : "rated_apparent_power",
    normalized: number === 4 ? null : { type: "NUMBER", value: "750", unit: "kVA" },
    mapping_status: number === 4 ? "UNMAPPED" : "MAPPED", reason_code: number === 4 ? "UNSUPPORTED_ATTRIBUTE" : null,
    value_source_support: number === 4 ? "UNVERIFIED" : number === 2 ? "TEXT_MISMATCH" : "TEXT_MATCH",
    evidence_ids: [id(7, number)],
  };
};
function page(items, params, defaultLimit) {
  const limit = Number(params.get("limit") || defaultLimit);
  const cursor = Number(params.get("cursor") || 0);
  return { items: items.slice(cursor, cursor + limit), total: items.length,
    next_cursor: cursor + limit < items.length ? String(cursor + limit) : null,
    previous_cursor: cursor ? String(Math.max(0, cursor - limit)) : null };
}
export function extractionStatus(documents, params, revision) {
  return { items: params.getAll("revision_document_ids").flatMap((documentId) => {
    const row = documents.find((document) => document.id === documentId);
    if (!row) return [];
    const current = documentId === "doc";
    return [{
      revision_document_id: documentId,
      processing_run_id: row.processing?.status === "COMPLETED" ? processing_run_id : null,
      ineligible_reason: row.status === "REMOVED" ? "REMOVED" : revision === "old" ? "READ_ONLY"
        : row.processing?.status !== "COMPLETED" ? "PROCESSING_REQUIRED" : null,
      extraction: { latest_attempt: current ? run : null, effective_result: current ? run : null },
      enrichment: current ? enrichment : null,
    }];
  }) };
}
export function extractionResponse(url, tail) {
  const params = url.searchParams;
  if (tail === "/extraction/runs") return page([run], params, 10);
  const evidenceMatch = tail.match(/^\/extraction\/evidence\/([^/]+)$/);
  if (evidenceMatch) {
    const group = groups.find((group) => candidateFor(group).evidence_ids[0] === evidenceMatch[1]);
    if (!group) return { __status: 404, detail: "Evidence unavailable" };
    const candidate = candidateFor(group);
    const number = numberOf(group);
    const pageNumber = group.page_numbers[0];
    const image = id(9, pageNumber);
    const region = { x: "0.57", y: "0.371", width: "0.12", height: "0.04" };
    return {
      id: evidenceMatch[1], candidate_id: candidate.id, role: "VALUE", page_id: candidate.page_id,
      page_image_id: image, page_image: { id: image, url: `${url.origin}/fixture-assets/page-${pageNumber}.svg`, expires_seconds: 90, sha256: "digest" },
      page_image_width: 1200, page_image_height: 840, candidate_value_source_support: candidate.value_source_support,
      ...(number === 4 ? { localization: "UNRESOLVED", reason_code: "NO_CITATION" }
        : number === 3 ? { localization: "VISUAL_REPORTED", region, reported_text: "750" }
          : { localization: "RESOLVED", quote: number === 2 ? "700" : "750", modality: "NATIVE_PDF", source_issues: [],
            regions: [region, { ...region, y: "0.43" }] }),
    };
  }
  if (!tail.startsWith(`/extraction/runs/${run.id}`)) return undefined;
  if (tail.endsWith("/sources")) return { items: [1, 2].map((page_number) => ({
    page_number, page_id: id(1, page_number + 10), page_image_id: id(9, page_number),
    prepared_result_id: id(4, page_number), spatial_result_id: id(4, page_number + 10),
    prepared_manifest_hash: "digest", spatial_manifest_hash: "digest", layout_producer_run_id: enrichment.id,
  })) };
  if (tail.endsWith("/candidates")) {
    const match = groups.filter((group) => {
      const item = candidateFor(group);
      return (!params.has("search") || `${group.tag} ${group.label} ${item.raw_label}`.toLowerCase().includes(params.get("search").toLowerCase()))
        && (!params.has("page_id") || params.get("page_id") === item.page_id)
        && (!params.has("mapping_status") || params.get("mapping_status") === item.mapping_status);
    });
    if (params.get("view") === "groups") return page(match, params, 25);
    const group = groups.find((item) => item.group_id === params.get("group_id"));
    if (!group) return { __status: 404, detail: "Group unavailable" };
    return { ...page(match.includes(group) ? [candidateFor(group)] : [], params, 20), group, identification: group.kind === "UNASSIGNED" ? null : {
      id: group.group_id, page_id: candidateFor(group).page_id, attempt_id: id(8, 0),
      kind: "EQUIPMENT", display_name: group.label, source_description: "Synthetic transformer source description",
      registry_type: group.registry_type, tag: group.tag, tag_state: "PRESENT", qualification: "INSTALLED",
      raw_qualification: null, mapping_status: "MAPPED", reason_code: null, conflict: false, evidence_ids: [],
    } };
  }
  return {
    run, attempts: ["EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"].map((stage, index) => ({
      id: id(8, index), stage, page_numbers: [1], attempt_number: 1, status: "COMPLETED",
      provider_calls: 1, usage: { input_tokens: 200, output_tokens: 60 }, estimated_cost: null,
      validation_diagnostics: [], stage_diagnostics: [],
    })), coverage: { required_units: 4, completed_required_units: 4 }, execution: null,
    can_retry: false, can_cancel: false, can_browse_candidates: true,
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
      profile: { key: run.profile_key, provider: "openai", model: "Fixture model", enabled: true },
      errors: [], review_hash: "a".repeat(64), consent_version: "external-openai-v1", review_expires_at: "2026-01-20T12:00:00Z",
      planned_runs: body.documents.length,
      provider_admissions: body.documents.reduce((total, item) => total + item.pages.length, 0) * 6,
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
      unknown_provider_outcome: false, can_retry: false, retry_targets: [], stage_outcomes: [],
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
          extraction: ready ? step("COMPLETED", run.id) : step("WAITING"),
        };
      }),
    };
  }
  return undefined;
}
