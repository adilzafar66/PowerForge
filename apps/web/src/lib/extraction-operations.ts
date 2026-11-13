import { request } from "@/lib/api";
import type { RunStatus } from "@/lib/extraction";

export type RevisionScope = { projectId: string; revisionId: string };
export type ExtractionMode = "ensure" | "reextract";
export type OperationStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "PARTIAL" | "BLOCKED" | "FAILED" | "CANCELLED";
export type StepStatus = RunStatus | "REUSED" | "BLOCKED" | "WAITING";
export type OperationStep = "layout" | "extraction" | "resume";

export type SourceOption = {
  revision_document_id: string;
  filename: string | null;
  processing_run_id: string | null;
  page_count: number | null;
  available_pages: number[];
  error: string | null;
};

export type OperationSources = {
  items: SourceOption[];
  max_pages_per_document: number;
  max_documents: number;
  max_pages: number;
  read_only: boolean;
};

export type OperationSelection = {
  documents: {
    revision_document_id: string;
    processing_run_id: string;
    pages: number[];
    force_ocr_pages: number[];
  }[];
  mode: ExtractionMode;
};

export type OperationPreview = {
  items: {
    revision_document_id: string;
    filename: string | null;
    processing_run_id: string;
    error: string | null;
    pages: { page_number: number; force_ocr: boolean; reuse_preparation: boolean; reuse_layout: boolean }[];
  }[];
  profile: { key: string; provider: string; model: string; enabled: boolean };
  errors: string[];
  review_hash: string | null;
  planned_runs: number;
  provider_admissions: number | null;
  ocr_attempts: number | null;
  parallel_documents: number | null;
  consent_version: string;
};

export type AIStage = "EQUIPMENT_RECOGNITION" | "ATTRIBUTE_EXTRACTION";
export type RetryTarget = {
  page_id: string;
  page_number: number;
  stage: AIStage;
  expected_attempt: number;
  unknown_provider_outcome: boolean;
};

export type OperationChild = {
  run_id: string | null;
  status: StepStatus;
  error_code: string | null;
  attempts: number;
  retry_targets: RetryTarget[];
  stage_outcomes: { page_id: string; stage: AIStage; outcome: "RESULT" | "NO_ELIGIBLE_ATTRIBUTES" }[];
  unknown_provider_outcome: boolean;
  can_retry: boolean;
};

export type OperationDetail = {
  id: string;
  created_at: string;
  status: OperationStatus;
  cancel_requested: boolean;
  can_cancel: boolean;
  mode: ExtractionMode;
  provider_admissions: number;
  unavailable_sources: number;
  items: {
    revision_document_id: string;
    filename: string;
    processing_run_id: string;
    pages: number[];
    force_ocr_pages: number[];
    status: OperationStatus;
    blocked_reason: string | null;
    can_resume: boolean;
    layout: OperationChild;
    extraction: OperationChild;
  }[];
};

export type OperationLink = { id: string; created_at: string };
export type SkippedSource = { id: string; name: string; reason: string };

function path(scope: RevisionScope) {
  return `/api/projects/${encodeURIComponent(scope.projectId)}/revisions/${encodeURIComponent(scope.revisionId)}/extraction/operations`;
}

function readPost<T>(url: string, body: object, signal?: AbortSignal) {
  return request<T>(url, { method: "POST", body: JSON.stringify(body), signal }, { notifyWrite: false });
}

export function getOperationSources(scope: RevisionScope, ids: string[], signal?: AbortSignal) {
  return readPost<OperationSources>(`${path(scope)}/sources`, { revision_document_ids: ids }, signal);
}

export function previewExtractionOperation(scope: RevisionScope, selection: OperationSelection, signal?: AbortSignal) {
  return readPost<OperationPreview>(`${path(scope)}/preview`, selection, signal);
}

export function startExtractionOperation(scope: RevisionScope, selection: OperationSelection, reviewHash: string, requestKey: string) {
  return request<{ id: string }>(path(scope), {
    method: "POST",
    body: JSON.stringify({
      selection, review_hash: reviewHash, request_key: requestKey,
      external_processing_consent: true,
    }),
  });
}

export function getExtractionOperation(scope: RevisionScope, id: string, signal?: AbortSignal) {
  return request<OperationDetail>(`${path(scope)}/${encodeURIComponent(id)}`, { signal });
}

export function recentExtractionOperations(scope: RevisionScope, documentId: string, signal?: AbortSignal) {
  return request<{ items: OperationLink[] }>(
    `${path(scope)}?revision_document_id=${encodeURIComponent(documentId)}`, { signal },
  );
}

export function cancelExtractionOperation(scope: RevisionScope, id: string) {
  return request<OperationDetail>(`${path(scope)}/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}

export function retryExtractionOperation(
  scope: RevisionScope, id: string, documentId: string, step: OperationStep,
  expectedAttempts: number, acknowledgeUnknownOutcome: boolean, target?: RetryTarget,
) {
  return request<OperationDetail>(`${path(scope)}/${encodeURIComponent(id)}/retry`, {
    method: "POST",
    body: JSON.stringify({
      revision_document_id: documentId,
      ...(target
        ? { stage: target.stage, page_id: target.page_id, expected_attempt: target.expected_attempt }
        : { step, expected_attempts: expectedAttempts }),
      acknowledge_unknown_outcome: acknowledgeUnknownOutcome,
    }),
  });
}

export function extractionOperationHref(scope: RevisionScope, documentId: string, operationId: string) {
  const query = new URLSearchParams({ document: documentId, operation: operationId });
  return `/projects/${encodeURIComponent(scope.projectId)}/revisions/${encodeURIComponent(scope.revisionId)}?${query}`;
}

export function extractionWizardHref(
  scope: RevisionScope,
  documentId: string,
  mode: ExtractionMode,
  source?: { pages: number[]; processingRunId: string },
) {
  const query = new URLSearchParams({ document: documentId, extract: mode });
  if (source) {
    query.set("extractPages", pageRanges(source.pages));
    query.set("extractSource", source.processingRunId);
  }
  return `/projects/${encodeURIComponent(scope.projectId)}/revisions/${encodeURIComponent(scope.revisionId)}?${query}`;
}

export function parseExtractionPages(value: string, available: readonly number[], max: number) {
  const selected = new Set<number>();
  const allowed = new Set(available);
  for (const part of value.split(",")) {
    const match = /^(\d+)(?:\s*[-–]\s*(\d+))?$/.exec(part.trim());
    if (!match) return { error: "Enter page numbers or ranges, such as 1–3, 5." } as const;
    const first = Number(match[1]);
    const last = match[2] ? Number(match[2]) : first;
    if (!Number.isSafeInteger(first) || !Number.isSafeInteger(last) || first < 1 || last < first) {
      return { error: "Use ascending ranges of positive page numbers." } as const;
    }
    if (last - first + 1 > max) return { error: `Select at most ${max} pages.` } as const;
    for (let page = first; page <= last; page++) {
      if (!allowed.has(page)) return { error: `Page ${page} is outside the available pages.` } as const;
      if (selected.has(page)) return { error: `Page ${page} is listed more than once.` } as const;
      selected.add(page);
      if (selected.size > max) return { error: `Select at most ${max} pages.` } as const;
    }
  }
  return { pages: [...selected].sort((a, b) => a - b) } as const;
}

export function pageRanges(pages: readonly number[]) {
  const ranges: [number, number][] = [];
  for (const page of pages) {
    const last = ranges.at(-1);
    if (last && last[1] + 1 === page) last[1] = page;
    else ranges.push([page, page]);
  }
  return ranges.map(([first, last]) => first === last ? String(first) : `${first}–${last}`).join(", ");
}
