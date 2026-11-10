import { request } from "@/lib/api";
import type { CellState } from "@/lib/document-presentation";
import { documentViewerHref } from "@/lib/workspace-navigation";

export type RunFamily = "engineering" | "tables";
export type HistoryFamily = RunFamily | "enrichment";
export type RunStatus = "PENDING" | "RUNNING" | "COMPLETED" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED";
export type MappingStatus = "MAPPED" | "UNMAPPED" | "INVALID";
export type RegisterRun = {
  id: string;
  status: RunStatus;
  processing_run_id: string;
  created_at: string;
  profile_key: string;
};
export type FamilyRuns = {
  latest_attempt: RegisterRun | null;
  effective_result: RegisterRun | null;
};
export type ExtractionStatus = {
  revision_document_id: string;
  processing_run_id: string | null;
  ineligible_reason: "REMOVED" | "READ_ONLY" | "PROCESSING_REQUIRED" | "NO_PAGE_ARTIFACTS" | null;
  engineering: FamilyRuns;
  tables: FamilyRuns;
  enrichment: RegisterRun | null;
};
type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type EvidenceGroup = {
  run_id: string;
  family: RunFamily;
  source_group_id: string | null;
  label: string | null;
  tag_text: string | null;
  equipment_type_hint: string | null;
  page_numbers: number[];
  candidate_count: number;
};
export type Region = { x: string; y: string; width: string; height: string };
type CitationEvidence = {
  id: string;
  source_kind: string;
  source_snippet: string | null;
  source_page_number: number | null;
  grounding_precision: string;
  source_locator: {
    reading_basis: "NATIVE_PDF" | "OCR" | "VISUAL_REPORTED";
    geometry_basis: "NATIVE_DOCUMENT" | "OCR_ENGINE" | "NONE";
  } | null;
};
export type EvidenceDetail = CitationEvidence & {
  run_id: string;
  processing_run_id: string;
  page_number: number;
  region: Region | null;
  text_start: number | null;
  text_end: number | null;
  source_image_url: string | null;
  source_image_width_px: number | null;
  source_image_height_px: number | null;
  artifact_url_expires_seconds: number | null;
};
export type Candidate = {
  id: string;
  run_id: string;
  source_group_id: string | null;
  source_group: { label: string | null; tag_text: string | null } | null;
  kind: "EQUIPMENT_MENTION" | "ATTRIBUTE_VALUE" | "UNMAPPED_OBSERVATION";
  raw_text: string;
  raw_value: string | null;
  raw_unit: string | null;
  mapping_status: MappingStatus;
  equipment_type_key: string | null;
  observed_tag: string | null;
  attribute_key: string | null;
  numeric_value: string | null;
  integer_value: string | null;
  text_value: string | null;
  boolean_value: boolean | null;
  unit: string | null;
  reason_code: string | null;
  explanation: string | null;
  evidence: { role: "PRIMARY" | "SUPPORTING" | "CONTRADICTING"; evidence: CitationEvidence }[];
};
export type HistoryRun = Omit<RegisterRun, "profile_key"> & {
  profile_key?: string | null;
  selected_pages: number[];
  model?: string | null;
  profile_version?: string;
  error_code: string | null;
  pages_processed: number;
  input_artifact_ids?: string[];
};
export type RunDetail = {
  run: HistoryRun;
  attempts: { id: string; unit_key: string; status: string; retryable?: boolean; error_code: string | null }[];
  coverage?: { required_units: number; completed_required_units: number };
  execution?: {
    profile_key: string;
    calls_admitted: number;
    provider_calls_started: number;
    unreported_provider_calls: number;
    call_budget: number;
    input_tokens: number | null;
    output_tokens: number | null;
    estimated_cost_usd: string | null;
  } | null;
  confirmed_ocr_invocations?: number;
  results?: { id: string; page_number: number; producer_run_id: string; reused: boolean }[];
  spatial_results?: { id: string; page_number: number; prepared_result_id: string }[];
  can_retry?: boolean;
  can_cancel?: boolean;
};
type SourceBinding = {
  page_number: number;
  prepared_result_id: string;
  spatial_result_id: string;
  preparation_producer_run_id: string;
  layout_producer_run_id: string;
};
export type RawTable = { id: string; table_kind: string; layout: unknown };
export type EvidenceFilters = {
  search?: string;
  page?: number;
  equipment_hint?: string;
  mapping_status?: MappingStatus;
};
export type RunPair = Record<RunFamily, string | null>;
export type DocumentScope = { projectId: string; revisionId: string; documentId: string };

export const families = ["engineering", "tables"] as const;
export const familyLabel = { engineering: "Engineering", tables: "Tables", enrichment: "Source enrichment" };
export const ineligibleLabel = {
  REMOVED: "Removed from this revision",
  READ_ONLY: "Revision is read-only",
  PROCESSING_REQUIRED: "Source processing must complete",
  NO_PAGE_ARTIFACTS: "No processed page images are available",
};

const runStates: Record<RunStatus, CellState> = {
  PENDING: { label: "Queued", tone: "pending" },
  RUNNING: { label: "Running", tone: "running" },
  COMPLETED: { label: "Completed", tone: "ready" },
  PARTIALLY_COMPLETED: { label: "Partial", tone: "review" },
  FAILED: { label: "Failed", tone: "failed" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
};
const notExtracted: CellState = { label: "Not extracted", tone: "neutral" };

export function runState(run?: { status: RunStatus } | null): CellState {
  return run ? runStates[run.status] : notExtracted;
}

export function extractionCell(item?: ExtractionStatus): CellState {
  if (!item) return { label: "Unknown", tone: "neutral" };
  if (item.ineligible_reason === "REMOVED") return { label: "Unavailable", tone: "neutral", detail: ineligibleLabel.REMOVED };
  const runs = families.map((family) => item[family].latest_attempt);
  if (!runs.some(Boolean)) {
    if (item.ineligible_reason === "NO_PAGE_ARTIFACTS" || item.ineligible_reason === "PROCESSING_REQUIRED") {
      return { label: "Unavailable", tone: "neutral", detail: ineligibleLabel[item.ineligible_reason] };
    }
    return notExtracted;
  }
  const states = runs.map((run) => run?.status);
  const active = states.includes("RUNNING") ? "RUNNING" : states.includes("PENDING") ? "PENDING" : null;
  const detail = families.map((family) => {
    const { latest_attempt: run, effective_result: result } = item[family];
    const version = run && run.processing_run_id !== item.processing_run_id ? " (earlier source)" : "";
    const resultType = result?.status === "PARTIALLY_COMPLETED" ? "partial result" : "result";
    const available = result && result.id !== run?.id
      ? ` (previous ${resultType} available)`
      : "";
    return `${familyLabel[family]} · ${runState(run).label}${version}${available}`;
  }).join(" / ");
  const sameSource = !!item.processing_run_id && runs.every((run) => run?.processing_run_id === item.processing_run_id);
  if (active) return { ...runStates[active], detail };
  if (sameSource && states.every((status) => status === "COMPLETED")) return runStates.COMPLETED;
  if (states.includes("COMPLETED") || states.includes("PARTIALLY_COMPLETED")) return { ...runStates.PARTIALLY_COMPLETED, detail };
  return { ...runStates[states.includes("FAILED") ? "FAILED" : "CANCELLED"], detail };
}

function revisionPath(projectId: string, revisionId: string) {
  return `/api/projects/${encodeURIComponent(projectId)}/revisions/${encodeURIComponent(revisionId)}`;
}

function documentPath(scope: DocumentScope, family: HistoryFamily = "engineering") {
  const feature = family === "enrichment" ? "source-enrichment" : "extraction";
  return `${revisionPath(scope.projectId, scope.revisionId)}/documents/${encodeURIComponent(scope.documentId)}/${feature}`;
}

function queryString(parameters: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) {
    if (value != null && value !== "") query.set(key, String(value));
  }
  return `?${query}`;
}

export async function getExtractionStatuses(projectId: string, revisionId: string, ids: string[], signal?: AbortSignal) {
  const items: ExtractionStatus[] = [];
  for (let i = 0; i < ids.length; i += 100) {
    const query = new URLSearchParams();
    for (const id of ids.slice(i, i + 100)) query.append("revision_document_ids", id);
    const batch = await request<{ items: ExtractionStatus[] }>(
      `${revisionPath(projectId, revisionId)}/extraction/status?${query}`,
      { signal },
    );
    items.push(...batch.items);
  }
  return Object.fromEntries(items.map((item) => [item.revision_document_id, item]));
}

export function getGroups(scope: DocumentScope, pair: RunPair, filters: EvidenceFilters, offset: number, signal?: AbortSignal) {
  const query = queryString({ engineering_run_id: pair.engineering, tables_run_id: pair.tables, ...filters, limit: 25, offset });
  return request<Page<EvidenceGroup>>(`${documentPath(scope)}/groups${query}`, { signal });
}

export function getGroupCandidates(
  scope: DocumentScope,
  runId: string,
  family: RunFamily,
  groupId: string | null,
  filters: EvidenceFilters,
  offset: number,
  signal?: AbortSignal,
  candidateId?: string,
) {
  const query = queryString({ family, source_group_id: groupId, ungrouped: groupId === null, ...filters, candidate_id: candidateId, limit: candidateId ? 1 : 20, offset });
  return request<Page<Candidate>>(`${documentPath(scope)}/runs/${runId}/candidates${query}`, { signal });
}

export function getEvidence(scope: DocumentScope, id: string, signal?: AbortSignal) {
  return request<EvidenceDetail>(`${documentPath(scope)}/evidence/${id}?include_source_image=true`, { signal });
}

export function getHistory(scope: DocumentScope, family: HistoryFamily, offset: number, signal?: AbortSignal) {
  const query = queryString({ family: family === "enrichment" ? null : family, limit: 10, offset });
  return request<Page<HistoryRun>>(`${documentPath(scope, family)}/runs${query}`, { signal });
}

export function getRunDetail(scope: DocumentScope, family: HistoryFamily, runId: string, signal?: AbortSignal) {
  const query = family === "enrichment" ? "?viewer=true" : queryString({ family });
  return request<RunDetail>(`${documentPath(scope, family)}/runs/${runId}${query}`, { signal });
}

export function runHistoryAction(scope: DocumentScope, family: HistoryFamily, runId: string, action: "retry" | "cancel") {
  const query = family === "enrichment" ? "?viewer=true" : queryString({ family });
  return request<RunDetail>(`${documentPath(scope, family)}/runs/${runId}/${action}${query}`, { method: "POST" });
}

export function getRunSources(scope: DocumentScope, runId: string, signal?: AbortSignal) {
  return request<{ items: SourceBinding[] }>(`${documentPath(scope)}/runs/${runId}/sources`, { signal });
}

export function getRawTables(scope: DocumentScope, runId: string, offset: number, signal?: AbortSignal) {
  return request<Page<RawTable>>(`${documentPath(scope)}/runs/${runId}/tables?limit=1&offset=${offset}`, { signal });
}

export function extractionHistoryHref(scope: DocumentScope, family?: HistoryFamily, runId?: string) {
  const href = documentViewerHref(scope.projectId, scope.revisionId, scope.documentId, { mode: "evidence" });
  return `${href}&evidenceTab=history${family ? `&historyFamily=${family}` : ""}${runId ? `&historyRun=${encodeURIComponent(runId)}` : ""}`;
}

export function evidenceArtifactUrl(value: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    // The API signs the exact artifact against the configured storage endpoint.
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}
