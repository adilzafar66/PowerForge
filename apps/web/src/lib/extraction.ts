import { request } from "@/lib/api";
import type { CellState } from "@/lib/document-presentation";
import { documentViewerHref } from "@/lib/workspace-navigation";

export type RunStatus = "PENDING" | "RUNNING" | "COMPLETED" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED";
export type MappingStatus = "MAPPED" | "UNMAPPED" | "INVALID";
export type RegisterRun = {
  id: string;
  status: RunStatus;
  processing_run_id: string;
  created_at: string;
  profile_key: string;
};
export type ExtractionRuns = {
  latest_attempt: RegisterRun | null;
  effective_result: RegisterRun | null;
};
export type ExtractionStatus = {
  revision_document_id: string;
  processing_run_id: string | null;
  ineligible_reason: "REMOVED" | "READ_ONLY" | "PROCESSING_REQUIRED" | "NO_PAGE_ARTIFACTS" | null;
  extraction: ExtractionRuns;
  enrichment: RegisterRun | null;
  pending_operation?: { id: string; preparing: boolean } | null;
};
export type CursorPage<T> = { items: T[]; total: number; next_cursor: string | null; previous_cursor: string | null };
export type EvidenceGroup = {
  group_id: string;
  kind: "EQUIPMENT" | "UNASSIGNED";
  label: string;
  tag: string | null;
  registry_type: string | null;
  page_numbers: number[];
  matching_candidate_count: number;
  matching_attribute_count: number;
  matching_identification_count: number;
  source_description: string | null;
};
export type Region = { x: string; y: string; width: string; height: string };
export type ValueSourceSupport = "TEXT_MATCH" | "TEXT_MISMATCH" | "UNVERIFIED";
export type ProposedValue = string | number | bigint | boolean | null;
export type AlternateRepresentation = { value: string; unit: string };
export const valueSourceSupportLabel: Record<ValueSourceSupport, string> = {
  TEXT_MATCH: "Matches cited text",
  TEXT_MISMATCH: "Cited value differs",
  UNVERIFIED: "Not verified",
};
export type EvidenceDetail = {
  id: string;
  candidate_id: string;
  role: string;
  page_id: string;
  page_image_id: string;
  page_image: { id: string; sha256: string; url: string; expires_seconds: number };
  page_image_width: number;
  page_image_height: number;
  candidate_value_source_support: ValueSourceSupport | null;
} & (
  | { localization: "RESOLVED"; modality: "NATIVE_PDF" | "OCR"; quote: string; regions: Region[]; source_issues: string[] }
  | { localization: "VISUAL_REPORTED"; region: Region; reported_text: string | null }
  | { localization: "UNRESOLVED"; reason_code: string }
);
type CandidateBase = {
  id: string;
  page_id: string;
  attempt_id: string;
  mapping_status: MappingStatus;
  reason_code: string | null;
  conflict: boolean;
  evidence_ids: string[];
};
export type Candidate = CandidateBase & (
  | {
      kind: "EQUIPMENT"; display_name: string; source_description: string; registry_type: string | null;
      tag: string | null; tag_state: string; qualification: string; raw_qualification: string | null;
    }
  | {
      kind: "ATTRIBUTE"; equipment_id: string | null; association: "ASSERTED" | "UNCERTAIN" | "UNASSIGNED";
      raw_unmapped: boolean; origin: "EXTRACTED" | "INFERRED"; attribute_display_name: string | null;
      raw_label: string | null; raw_value: string | null; raw_unit: string | null;
      proposed_value: ProposedValue; proposed_unit: string | null;
      alternate_representations: AlternateRepresentation[];
      inference_explanation: string | null;
      inference_basis: string | null;
      source_expression: string | null; source_display_label: string | null;
      redundant_with_id: string | null;
      qualifiers: string[];
      value_form: "SINGLE" | "RANGE" | "MULTIPLE" | "QUALIFIED" | "EQUIVALENT_UNITS" | null;
      proposed_attribute_key: string | null; value_source_support: ValueSourceSupport;
      normalized: { type: string; value: string | boolean; unit: string | null } | null;
    }
);
export type HistoryRun = Omit<RegisterRun, "profile_key"> & {
  selected_pages: number[];
  model: string;
  profile_version: string;
  profile_hash: string;
  error_code: string | null;
  pages_processed: number;
};
export type RunAttempt = {
  id: string; stage: string; status: RunStatus; page_numbers: number[]; attempt_number: number;
  retryable: boolean; error_code: string | null; provider_calls: number; latency_ms: number | null;
  stage_outcome: "RESULT" | "NO_ELIGIBLE_ATTRIBUTES" | null;
  result_sha256: string | null;
  usage: { input_tokens: number; output_tokens: number } | null;
  estimated_cost: { amount: string; currency: string; pricing_version: string } | null;
  validation_diagnostics: { category: string; error_type: string; path: (string | number)[] }[];
  assertion_validation?: {
    state: "VALIDATED" | "PARTIALLY_VALIDATED" | "REJECTED";
    counts: AssertionCounts | null;
    rejections: { category: string; error_type: string; path: (string | number)[] }[];
  } | null;
  stage_diagnostics: { code: string; ref?: string; citation?: number; omitted?: number }[];
};
export type AssertionCounts = { received: number; accepted: number; quarantined: number };
export type RunDetail = {
  run: HistoryRun;
  attempts: RunAttempt[];
  coverage: { required_units: number; completed_required_units: number };
  execution: { calls_admitted: number; provider_calls_started: number; unreported_provider_calls: number; call_budget: number } | null;
  can_retry: boolean;
  can_cancel: boolean;
  can_browse_candidates: boolean;
};
export type SourceBinding = {
  page_id: string; page_number: number; page_image_id: string;
  prepared_result_id: string; spatial_result_id: string;
  prepared_manifest_hash: string; spatial_manifest_hash: string;
  layout_producer_run_id: string;
  page_context_hash: string | null;
  assertion_counts?: AssertionCounts | null;
};
export type SourceLayout = {
  manifest: {
    tables: { ref: string; method: string; structure_basis: string; header_basis: string;
      rows: number; columns: number;
      cells: { ref: string; row: number; column: number; row_span: number;
        column_span: number; readings: string[]; state: string }[] }[];
    unresolved: { ref: string; reason: string }[];
  };
};
export type EvidenceFilters = {
  search?: string; page_id?: string; equipment_type?: string;
  mapping_status?: MappingStatus; kind?: Candidate["kind"];
};
export type DocumentScope = { projectId: string; revisionId: string; documentId: string };

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
  const { latest_attempt: run, effective_result: result } = item.extraction;
  if (!run && !item.pending_operation) {
    if (item.ineligible_reason === "NO_PAGE_ARTIFACTS" || item.ineligible_reason === "PROCESSING_REQUIRED") {
      return { label: "Unavailable", tone: "neutral", detail: ineligibleLabel[item.ineligible_reason] };
    }
    return notExtracted;
  }
  const earlier = run && run.processing_run_id !== item.processing_run_id;
  const resultType = result?.status === "PARTIALLY_COMPLETED" ? "partial result" : "result";
  const available = result && result.id !== run?.id ? ` (previous ${resultType} available)` : "";
  const detail = earlier || available ? `${runState(run).label}${earlier ? " (earlier source)" : ""}${available}` : undefined;
  if (item.pending_operation) {
    return {
      ...runStates[item.pending_operation.preparing ? "RUNNING" : "PENDING"],
      detail: `Waiting for exact source bindings${detail ? ` · ${detail}` : ""}`,
    };
  }
  if (earlier && run?.status === "COMPLETED") return { ...runStates.PARTIALLY_COMPLETED, detail };
  return { ...runState(run), detail };
}

function revisionPath(projectId: string, revisionId: string) {
  return `/api/projects/${encodeURIComponent(projectId)}/revisions/${encodeURIComponent(revisionId)}`;
}

function documentPath(scope: DocumentScope) {
  return `${revisionPath(scope.projectId, scope.revisionId)}/documents/${encodeURIComponent(scope.documentId)}/extraction`;
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

function runPath(scope: DocumentScope, runId: string) {
  return `${documentPath(scope)}/runs/${encodeURIComponent(runId)}`;
}

export function getGroups(scope: DocumentScope, runId: string, filters: EvidenceFilters, cursor: string | null, signal?: AbortSignal) {
  return request<CursorPage<EvidenceGroup>>(
    `${runPath(scope, runId)}/candidates${queryString({ view: "groups", ...filters, cursor })}`, { signal },
  );
}

export function getGroupCandidates(
  scope: DocumentScope, runId: string, groupId: string, filters: EvidenceFilters,
  cursor: string | null, signal?: AbortSignal, candidateId?: string,
) {
  return request<CursorPage<Candidate> & { group: EvidenceGroup; identification: Extract<Candidate, { kind: "EQUIPMENT" }> | null }>(
    `${runPath(scope, runId)}/candidates${queryString({ view: "members", group_id: groupId, ...filters, cursor, candidate_id: candidateId })}`,
    { signal },
    { read: readCandidatePage },
  );
}

async function readCandidatePage(response: Response): Promise<unknown> {
  return JSON.parse(await response.text(), (key, value, context?: { source?: string }) => {
    if (key !== "proposed_value" || typeof value !== "number" || Number.isSafeInteger(value)) return value;
    // JSON integer proposals can exceed the limit of JavaScript's Number type.
    const literal = context?.source;
    return literal && /^-?\d+$/.test(literal) ? BigInt(literal) : "Integer precision unavailable";
  });
}

export function getEvidence(scope: DocumentScope, id: string, signal?: AbortSignal) {
  return request<EvidenceDetail>(`${documentPath(scope)}/evidence/${encodeURIComponent(id)}`, { signal });
}

export function getHistory(scope: DocumentScope, cursor: string | null, signal?: AbortSignal) {
  return request<CursorPage<HistoryRun>>(`${documentPath(scope)}/runs${queryString({ limit: 10, cursor })}`, { signal });
}

export function getRunDetail(scope: DocumentScope, runId: string, signal?: AbortSignal) {
  return request<RunDetail>(runPath(scope, runId), { signal });
}

export function runHistoryAction(scope: DocumentScope, runId: string, action: "retry" | "cancel", acknowledgeUnknownOutcome = false) {
  return request<RunDetail>(`${runPath(scope, runId)}/${action}`, {
    method: "POST",
    body: action === "retry" ? JSON.stringify({ acknowledge_unknown_outcome: acknowledgeUnknownOutcome }) : undefined,
  });
}

export function getRunSources(scope: DocumentScope, runId: string, signal?: AbortSignal) {
  return request<{ items: SourceBinding[] }>(`${runPath(scope, runId)}/sources`, { signal });
}

export function getSourceLayout(scope: DocumentScope, binding: SourceBinding, signal?: AbortSignal) {
  const root = `${revisionPath(scope.projectId, scope.revisionId)}/documents/${encodeURIComponent(scope.documentId)}/source-enrichment`;
  return request<SourceLayout>(`${root}/runs/${encodeURIComponent(binding.layout_producer_run_id)}/spatial-results/${encodeURIComponent(binding.spatial_result_id)}`, { signal });
}

export function extractionHistoryHref(scope: DocumentScope, runId?: string) {
  const href = documentViewerHref(scope.projectId, scope.revisionId, scope.documentId, { mode: "evidence" });
  return `${href}&evidenceTab=history${runId ? `&extractionRun=${encodeURIComponent(runId)}` : ""}`;
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
