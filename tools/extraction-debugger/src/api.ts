export type Issue = { category: string; error_type: string; path: (string | number)[] };
export type Collection = "attributes" | "raw_unmapped";
export type Attempt = {
  attempt_id: string; run_id: string; document: string; page: number; attempt_number: number;
  finished_at: string | null; status: string; provider: string; model: string | null;
  validation: string | null; received: number | null; accepted: number | null;
  quarantined: number | null; output_bytes: number | null; output_sha256: string | null;
  expires_at: string | null; retained: boolean | null; duration_ms: number | null;
  input_tokens: number | null; output_tokens: number | null; cached_input_tokens: number | null;
  cost: string | null; pricing_basis: string | null; published: number | null; error_code: string | null;
};
export type Rejection = { collection: Collection; index: number; issues: Issue[] };
export type PublishedCandidate = {
  ordinal: number; local_ref: string; mapping_status: string; reason_code: string | null;
  proposed_value: string | number | boolean | null;
  alternate_representations: { value: string; unit: string }[] | null;
  normalized_type: string | null; normalized_value: string | null; normalized_unit: string | null;
  evidence: { role: string; localization: string; reason_code: string | null }[];
};
type Performance = {
  version: 1 | 2;
  input_configuration?: string;
  source_projection?: string;
  available_readings?: number;
  queue_wait_ms?: number;
  source_load_ms?: number;
  request_build_ms?: number;
  provider_call_ms?: number;
  admission_ms?: number;
  localization_normalization_ms?: number;
  audit_store_ms?: number;
  db_publish_ms?: number;
  attempt_total_ms?: number;
  failure_stage?: string;
  response_status?: string;
  reasoning_tokens?: number;
  visible_output_tokens?: number;
  service_tier?: string;
  reasoning_effort?: string;
  ocr_selected?: boolean;
  profile_sha256?: string;
  prompt_sha256?: string;
  schema_sha256?: string;
  request?: Record<string, number | string | boolean | null> & {image_sent?: boolean; native_sent?: boolean; ocr_sent?: boolean};
};

export type Detail = {
  performance?: Performance | null;
  requested_reasoning_effort?: "none" | "low" | "medium" | null;
  attempt: Attempt; request_sha256: string | null; result_sha256: string | null;
  upstream_sha256: string | null; schema_version: string | null; prompt_version: string | null;
  rejections: Rejection[]; fatal: Issue[];
  validated: Record<string, unknown> | null; candidates: PublishedCandidate[];
};

export const messages: Record<string, string> = {
  authentication_failed: "The operator secret was not accepted.",
  authentication_required: "Your session ended. Sign in again.",
  invalid_request: "Check the UUID or filters.",
  attempt_not_found: "No Stage 2 attempt found for that UUID.",
  not_captured: "This attempt has no retained original response.",
  expired: "The original response has expired. Audit metadata remains available.",
  object_missing: "The original audit object is unexpectedly missing.",
  integrity_failed: "The audit object failed its size or checksum verification.",
  audit_service_unavailable: "Audit storage or the retrieval journal is unavailable.",
  service_unavailable: "The debugger could not reach its diagnostic services.",
};

export async function api(path: string, signal?: AbortSignal, action?: { secret?: string }) {
  const response = await fetch(`/api${path}`, {
    method: action ? "POST" : "GET", cache: "no-store", signal,
    headers: action ? { "X-Debugger-Request": "1", "Content-Type": "application/json" } : {},
    body: action ? JSON.stringify(action) : undefined,
  });
  if (!response.ok) {
    if (response.status === 401 && path !== "/login") window.dispatchEvent(new Event("debugger-session-ended"));
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "service_unavailable");
  }
  return response;
}

export function errorText(error: unknown) {
  return messages[error instanceof Error ? error.message : ""] ?? messages.service_unavailable;
}
