import {
  classificationAttemptState,
  type ClassificationAttemptState,
  type DocumentOrigin,
  type DocumentType,
  type ProcessingRunStatus,
  type RevisionDocument,
} from "@/lib/documents";

/** UI-only state. Backend processing and classification models stay separate. */
export type DocumentPresentationState =
  | "removed"
  | "processing_failed"
  | "processing"
  | "classification_failed"
  | "classifying"
  | "needs_review"
  | "not_started"
  | "ready";

export type DocumentQuickView = "all" | "needs_review" | "issues" | "removed";

export type AdvancedDocumentFilters = {
  type: DocumentType | "";
  origin: DocumentOrigin | "";
  /** `NONE` matches a document that has never been processed. */
  processing: ProcessingRunStatus | "NONE" | "";
  classification: ClassificationAttemptState | "";
};

export type QuickViewCounts = {
  all: number;
  needsReview: number;
  issues: number;
  removed: number;
};

export const EMPTY_ADVANCED_FILTERS: AdvancedDocumentFilters = {
  type: "",
  origin: "",
  processing: "",
  classification: "",
};

const STATE_LABELS: Record<DocumentPresentationState, string> = {
  removed: "Removed",
  processing_failed: "Failed",
  processing: "Processing",
  classification_failed: "Failed",
  classifying: "Classifying",
  needs_review: "Needs review",
  not_started: "Not started",
  ready: "Ready",
};

/**
 * One dominant state. A failed classification attempt counts only when the
 * current processing run is completed; otherwise an earlier processing state
 * or a fall-through state wins. The row's suggestion is left untouched.
 */
export function deriveDocumentPresentationState(row: RevisionDocument): DocumentPresentationState {
  if (row.status === "REMOVED") {
    return "removed";
  }
  const processing = row.processing?.status ?? null;
  if (processing === "FAILED") {
    return "processing_failed";
  }
  if (processing === "PENDING" || processing === "RUNNING") {
    return "processing";
  }
  const attempt = row.classification.attempt?.status ?? null;
  if (attempt === "FAILED" && processing === "COMPLETED") {
    return "classification_failed";
  }
  if (attempt === "PENDING" || attempt === "RUNNING") {
    return "classifying";
  }
  if (documentNeedsReview(row)) {
    return "needs_review";
  }
  if (processing === null) {
    return "not_started";
  }
  return "ready";
}

/** Unaccepted suggestion on an included document. Ignores presentation precedence. */
export function documentNeedsReview(row: RevisionDocument): boolean {
  const suggestion = row.classification.suggestion;
  return row.status === "INCLUDED" && suggestion != null && !suggestion.accepted;
}

export function documentHasIssue(row: RevisionDocument): boolean {
  const state = deriveDocumentPresentationState(row);
  return state === "processing_failed" || state === "classification_failed";
}

export function matchesQuickView(row: RevisionDocument, view: DocumentQuickView): boolean {
  if (view === "all") {
    return row.status === "INCLUDED";
  }
  if (view === "needs_review") {
    return deriveDocumentPresentationState(row) === "needs_review";
  }
  if (view === "issues") {
    return documentHasIssue(row);
  }
  return row.status === "REMOVED";
}

export function matchesAdvancedFilters(
  row: RevisionDocument,
  filters: AdvancedDocumentFilters,
): boolean {
  if (filters.type && row.document_type !== filters.type) {
    return false;
  }
  if (filters.origin && row.origin !== filters.origin) {
    return false;
  }
  if (filters.processing === "NONE") {
    if (row.processing !== null) {
      return false;
    }
  } else if (filters.processing && row.processing?.status !== filters.processing) {
    return false;
  }
  if (
    filters.classification &&
    classificationAttemptState(row.classification) !== filters.classification
  ) {
    return false;
  }
  return true;
}

export function countQuickViews(rows: readonly RevisionDocument[]): QuickViewCounts {
  const counts: QuickViewCounts = { all: 0, needsReview: 0, issues: 0, removed: 0 };
  for (const row of rows) {
    if (matchesQuickView(row, "all")) {
      counts.all += 1;
    }
    if (matchesQuickView(row, "needs_review")) {
      counts.needsReview += 1;
    }
    if (matchesQuickView(row, "issues")) {
      counts.issues += 1;
    }
    if (matchesQuickView(row, "removed")) {
      counts.removed += 1;
    }
  }
  return counts;
}

export function presentationStateLabel(state: DocumentPresentationState): string {
  return STATE_LABELS[state];
}

/** Failure subtype for a tooltip or drawer. Null when the dominant label is enough. */
export function presentationFailureDetail(state: DocumentPresentationState): string | null {
  if (state === "processing_failed") {
    return "Processing failed";
  }
  if (state === "classification_failed") {
    return "Classification failed";
  }
  return null;
}
