import { describe, expect, it } from "vitest";

import {
  countQuickViews,
  deriveDocumentPresentationState,
  documentHasIssue,
  documentNeedsReview,
  EMPTY_ADVANCED_FILTERS,
  matchesAdvancedFilters,
  matchesQuickView,
  presentationFailureDetail,
  presentationStateLabel,
} from "./document-presentation";
import type {
  ClassificationAttempt,
  ClassificationSuggestion,
  DocumentType,
  ProcessingRunStatus,
  ProcessingSummary,
  RevisionDocument,
} from "./documents";

function processing(status: ProcessingRunStatus): ProcessingSummary {
  return {
    status,
    attempt_count: 1,
    pages_processed: status === "COMPLETED" ? 4 : 1,
    pages_total: 4,
    error_code: status === "FAILED" ? "RENDER_FAILED" : null,
    error_message: status === "FAILED" ? "Render failed" : null,
  };
}

function suggestion(
  predicted: DocumentType,
  accepted: boolean,
): ClassificationSuggestion {
  return {
    prediction_id: "pred-1",
    predicted_type: predicted,
    confidence_band: "HIGH",
    accepted,
    requires_page_classification: predicted === "MIXED_DOCUMENT" || predicted === "UNKNOWN",
  };
}

function attempt(status: ClassificationAttempt["status"]): ClassificationAttempt {
  return {
    id: "run-1",
    status,
    stage: "DOCUMENT",
    pages_total: 4,
    pages_classified: status === "COMPLETED" ? 4 : 0,
    error_code: status === "FAILED" ? "PROVIDER_UNAVAILABLE" : null,
  };
}

function row(
  overrides: Partial<RevisionDocument> & {
    suggestionType?: DocumentType;
    suggestionAccepted?: boolean;
  } = {},
): RevisionDocument {
  const { suggestionType, suggestionAccepted = false, ...rest } = overrides;
  return {
    id: "rd-1",
    revision_id: "rev-1",
    document: {
      id: "doc-1",
      original_filename: "SLD.pdf",
      mime_type: "application/pdf",
      file_extension: "pdf",
      size_bytes: 2048,
      sha256: "a".repeat(64),
      uploaded_at: "2026-10-01T10:00:00Z",
    },
    origin: "UPLOADED",
    inherited_from_revision_id: null,
    inherited_from_revision_identifier: null,
    status: "INCLUDED",
    document_type: "SINGLE_LINE_DIAGRAM",
    document_number: null,
    description: null,
    notes: null,
    added_at: "2026-10-01T10:00:00Z",
    removed_at: null,
    processing: processing("COMPLETED"),
    classification: {
      enabled: true,
      suggestion: suggestionType ? suggestion(suggestionType, suggestionAccepted) : null,
      attempt: suggestionType ? attempt("COMPLETED") : null,
    },
    ...rest,
  };
}

function views(document: RevisionDocument) {
  return {
    all: matchesQuickView(document, "all"),
    needsReview: matchesQuickView(document, "needs_review"),
    issues: matchesQuickView(document, "issues"),
    removed: matchesQuickView(document, "removed"),
  };
}

describe("deriveDocumentPresentationState", () => {
  it("lets removed win over processing failure, classification failure, and an unaccepted suggestion", () => {
    const document = row({
      status: "REMOVED",
      document_type: "UNKNOWN",
      processing: processing("FAILED"),
      suggestionType: "SINGLE_LINE_DIAGRAM",
      classification: {
        enabled: true,
        suggestion: suggestion("SINGLE_LINE_DIAGRAM", false),
        attempt: attempt("FAILED"),
      },
    });

    expect(deriveDocumentPresentationState(document)).toBe("removed");
    expect(documentHasIssue(document)).toBe(false);
    expect(views(document)).toEqual({
      all: false,
      needsReview: false,
      issues: false,
      removed: true,
    });
  });

  it("reports processing failed even when a suggestion exists", () => {
    const document = row({
      processing: processing("FAILED"),
      suggestionType: "PANEL_SCHEDULE",
    });

    expect(deriveDocumentPresentationState(document)).toBe("processing_failed");
    expect(document.classification.suggestion?.predicted_type).toBe("PANEL_SCHEDULE");
    expect(documentHasIssue(document)).toBe(true);
  });

  it("reports in-progress processing ahead of an unaccepted suggestion", () => {
    for (const status of ["PENDING", "RUNNING"] as const) {
      const document = row({
        processing: processing(status),
        document_type: "UNKNOWN",
        suggestionType: "FAULT_DATA",
      });
      expect(deriveDocumentPresentationState(document)).toBe("processing");
    }
  });

  it("reports classification failed only when processing completed, and keeps the suggestion", () => {
    const document = row({
      processing: processing("COMPLETED"),
      suggestionType: "TRANSFORMER_SHOP_DRAWING",
      classification: {
        enabled: true,
        suggestion: suggestion("TRANSFORMER_SHOP_DRAWING", false),
        attempt: attempt("FAILED"),
      },
    });

    expect(deriveDocumentPresentationState(document)).toBe("classification_failed");
    expect(document.classification.suggestion).toEqual(
      suggestion("TRANSFORMER_SHOP_DRAWING", false),
    );
    expect(documentNeedsReview(document)).toBe(true);
    expect(matchesQuickView(document, "needs_review")).toBe(false);
    expect(matchesQuickView(document, "issues")).toBe(true);
    expect(matchesQuickView(document, "all")).toBe(true);
  });

  it("does not treat a failed attempt as classification failed when processing is pending or absent", () => {
    const pending = row({
      processing: processing("PENDING"),
      classification: {
        enabled: true,
        suggestion: suggestion("PANEL_SCHEDULE", false),
        attempt: attempt("FAILED"),
      },
    });
    const neverProcessed = row({
      processing: null,
      classification: {
        enabled: true,
        suggestion: null,
        attempt: attempt("FAILED"),
      },
    });

    expect(deriveDocumentPresentationState(pending)).toBe("processing");
    expect(deriveDocumentPresentationState(neverProcessed)).toBe("not_started");
  });

  it("reports classifying while the latest attempt is pending or running", () => {
    for (const status of ["PENDING", "RUNNING"] as const) {
      const document = row({
        classification: {
          enabled: true,
          suggestion: null,
          attempt: attempt(status),
        },
      });
      expect(deriveDocumentPresentationState(document)).toBe("classifying");
    }
  });

  it("reports ready when processing completed and nothing needs attention", () => {
    const document = row({ suggestionType: "SINGLE_LINE_DIAGRAM", suggestionAccepted: true });

    expect(deriveDocumentPresentationState(document)).toBe("ready");
    expect(documentHasIssue(document)).toBe(false);
    expect(documentNeedsReview(document)).toBe(false);
  });

  it("reports not started when an included document has never been processed", () => {
    const document = row({ processing: null });

    expect(deriveDocumentPresentationState(document)).toBe("not_started");
    expect(documentHasIssue(document)).toBe(false);
    expect(documentNeedsReview(document)).toBe(false);
  });

  it("does not mutate the suggestion while deriving state", () => {
    const document = row({
      classification: {
        enabled: true,
        suggestion: suggestion("MIXED_DOCUMENT", false),
        attempt: attempt("FAILED"),
      },
    });
    const before = document.classification.suggestion;

    deriveDocumentPresentationState(document);

    expect(document.classification.suggestion).toBe(before);
  });
});

describe("documentNeedsReview", () => {
  it.each([
    ["UNKNOWN", "TRANSFORMER_SHOP_DRAWING"],
    ["ELECTRICAL_DRAWING", "SINGLE_LINE_DIAGRAM"],
    ["PANEL_SCHEDULE", "PANEL_SCHEDULE"],
    ["UNKNOWN", "MIXED_DOCUMENT"],
  ] as const)(
    "is true for an unaccepted suggestion when confirmed type is %s and AI says %s",
    (confirmed, predicted) => {
      const document = row({
        document_type: confirmed,
        suggestionType: predicted,
      });

      expect(documentNeedsReview(document)).toBe(true);
      expect(deriveDocumentPresentationState(document)).toBe("needs_review");
    },
  );

  it("is false when the suggestion was accepted", () => {
    const document = row({
      document_type: "SINGLE_LINE_DIAGRAM",
      suggestionType: "SINGLE_LINE_DIAGRAM",
      suggestionAccepted: true,
    });

    expect(documentNeedsReview(document)).toBe(false);
    expect(deriveDocumentPresentationState(document)).toBe("ready");
  });

  it("is false when there is no suggestion", () => {
    const document = row();

    expect(documentNeedsReview(document)).toBe(false);
    expect(deriveDocumentPresentationState(document)).toBe("ready");
  });

  it("is false for a removed document even with an unaccepted suggestion", () => {
    const document = row({
      status: "REMOVED",
      document_type: "UNKNOWN",
      suggestionType: "MOTOR_DATA",
    });

    expect(documentNeedsReview(document)).toBe(false);
  });
});

describe("quick views", () => {
  it("puts a needs-review row in All and Needs Review", () => {
    const document = row({ document_type: "UNKNOWN", suggestionType: "PANEL_SCHEDULE" });

    expect(views(document)).toEqual({
      all: true,
      needsReview: true,
      issues: false,
      removed: false,
    });
  });

  it("puts an issue row in All and Issues", () => {
    const document = row({ processing: processing("FAILED") });

    expect(views(document)).toEqual({
      all: true,
      needsReview: false,
      issues: true,
      removed: false,
    });
  });

  it("counts overlaps without adding Needs Review or Issues on top of All", () => {
    const counts = countQuickViews([
      row({ id: "review", document_type: "UNKNOWN", suggestionType: "OTHER" }),
      row({ id: "issue", processing: processing("FAILED") }),
      row({ id: "ready", suggestionType: "SINGLE_LINE_DIAGRAM", suggestionAccepted: true }),
      row({ id: "removed", status: "REMOVED", processing: processing("FAILED") }),
    ]);

    expect(counts).toEqual({ all: 3, needsReview: 1, issues: 1, removed: 1 });
  });
});

describe("matchesAdvancedFilters", () => {
  const included = row({
    document_type: "PANEL_SCHEDULE",
    origin: "INHERITED",
    processing: processing("COMPLETED"),
    suggestionType: "PANEL_SCHEDULE",
    suggestionAccepted: true,
  });

  it("matches every row when every filter is empty", () => {
    expect(matchesAdvancedFilters(included, EMPTY_ADVANCED_FILTERS)).toBe(true);
    expect(matchesAdvancedFilters(row({ processing: null }), EMPTY_ADVANCED_FILTERS)).toBe(true);
  });

  it("matches document type, origin, processing, and classification independently", () => {
    expect(matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, type: "PANEL_SCHEDULE" })).toBe(
      true,
    );
    expect(matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, type: "FAULT_DATA" })).toBe(
      false,
    );
    expect(matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, origin: "INHERITED" })).toBe(
      true,
    );
    expect(matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, origin: "UPLOADED" })).toBe(
      false,
    );
    expect(
      matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, processing: "COMPLETED" }),
    ).toBe(true);
    expect(
      matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, processing: "FAILED" }),
    ).toBe(false);

    const unprocessed = row({ processing: null });
    expect(
      matchesAdvancedFilters(unprocessed, { ...EMPTY_ADVANCED_FILTERS, processing: "NONE" }),
    ).toBe(true);
    expect(
      matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, processing: "NONE" }),
    ).toBe(false);
    expect(
      matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, classification: "ready" }),
    ).toBe(true);
    expect(
      matchesAdvancedFilters(included, { ...EMPTY_ADVANCED_FILTERS, classification: "failed" }),
    ).toBe(false);
  });

  it("filters disabled classification without turning that into a presentation state", () => {
    const document = row({
      processing: processing("COMPLETED"),
      classification: {
        enabled: false,
        suggestion: suggestion("SINGLE_LINE_DIAGRAM", false),
        attempt: attempt("FAILED"),
      },
    });

    expect(deriveDocumentPresentationState(document)).toBe("classification_failed");
    expect(
      matchesAdvancedFilters(document, { ...EMPTY_ADVANCED_FILTERS, classification: "disabled" }),
    ).toBe(true);
    expect(
      matchesAdvancedFilters(document, { ...EMPTY_ADVANCED_FILTERS, classification: "failed" }),
    ).toBe(false);
  });
});

describe("presentation labels", () => {
  it("uses one dominant label and a failure detail only for the two failure states", () => {
    expect(presentationStateLabel("ready")).toBe("Ready");
    expect(presentationStateLabel("needs_review")).toBe("Needs review");
    expect(presentationStateLabel("not_started")).toBe("Not started");
    expect(presentationStateLabel("processing_failed")).toBe("Failed");
    expect(presentationStateLabel("classification_failed")).toBe("Failed");
    expect(presentationFailureDetail("processing_failed")).toBe("Processing failed");
    expect(presentationFailureDetail("classification_failed")).toBe("Classification failed");
    expect(presentationFailureDetail("ready")).toBeNull();
    expect(presentationFailureDetail("needs_review")).toBeNull();
  });
});
