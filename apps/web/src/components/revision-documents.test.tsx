import { selectOption } from "@/components/ui/control-test-helpers";
/** @vitest-environment jsdom */
import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@/components/query-test-utils";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { focusManager } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const nav = vi.hoisted(() => ({
  refresh: vi.fn(),
  push: vi.fn(),
  back: vi.fn(),
  replace: vi.fn(),
  search: "",
}));
const refresh = nav.refresh;
vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/projects/p-1/revisions/r-2",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock("@/lib/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/documents")>()),
  listDocuments: vi.fn(),
  getDownloadUrl: vi.fn(),
  uploadDocument: vi.fn(),
  removeDocument: vi.fn(),
  restoreDocument: vi.fn(),
  updateDocument: vi.fn(),
  retryProcessing: vi.fn(),
  listPages: vi.fn(),
  getPageArtifactUrl: vi.fn(),
  acceptClassification: vi.fn(),
  reclassifyDocument: vi.fn(),
  retryClassification: vi.fn(),
  listClassificationPages: vi.fn(),
  getClassification: vi.fn(),
}));

vi.mock("@/lib/projects", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/projects")>()),
  listRevisions: vi.fn(),
}));

vi.mock("@/lib/extraction", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/extraction")>()),
  getExtractionStatuses: vi.fn(),
}));

vi.mock("@/lib/extraction-operations", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/extraction-operations")>()),
  recentExtractionOperations: vi.fn(),
  getExtractionOperation: vi.fn(),
  cancelExtractionOperation: vi.fn(),
}));

import {
  cancelExtractionOperation, getExtractionOperation, recentExtractionOperations,
  type OperationDetail,
} from "@/lib/extraction-operations";
import { getExtractionStatuses, type ExtractionStatus } from "@/lib/extraction";
import { RevisionDocuments } from "@/components/revision-documents";
import { listRevisions } from "@/lib/projects";
import {
  acceptClassification,
  getDownloadUrl,
  getPageArtifactUrl,
  getClassification,
  listClassificationPages,
  listDocuments,
  listPages,
  reclassifyDocument,
  removeDocument,
  restoreDocument,
  retryClassification,
  retryProcessing,
  updateDocument,
  uploadDocument,
  type ClassificationAttempt,
  type ClassificationSuggestion,
  type ProcessingSummary,
  type RevisionDocument,
} from "@/lib/documents";

const P = "p-1";
const R = "r-2";

function makeRow(
  overrides: Partial<RevisionDocument> & { name?: string; mime?: string },
) {
  const {
    name = "SLD_RevA.pdf",
    mime = "application/pdf",
    ...rest
  } = overrides;
  return {
    id: `rd-${name}`,
    revision_id: R,
    document: {
      id: `d-${name}`,
      original_filename: name,
      mime_type: mime,
      file_extension: name.split(".").pop() ?? "",
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
    processing: null,
    classification: { enabled: true, suggestion: null, attempt: null },
    ...rest,
  } as RevisionDocument;
}

function apiError(status: number, detail: string) {
  return Object.assign(new Error(detail), { apiError: { detail }, status });
}

const list = vi.mocked(listDocuments);
const download = vi.mocked(getDownloadUrl);

function renderWorkspace(canMutate = false) {
  return render(
    <RevisionDocuments projectId={P} revisionId={R} canMutate={canMutate} />,
  );
}

function quickView(name: string) {
  return within(screen.getByRole("group", { name: "Quick views" })).getByRole(
    "button",
    {
      name: new RegExp(`^${name}\\b`),
    },
  );
}

function findInspector(name: string) {
  return screen.findByRole("dialog", { name });
}

function getInspector(name: string) {
  return screen.getByRole("dialog", { name });
}

/** The overlay renders as the inspector's previous sibling in the portal. */
function clickBackdrop(user: ReturnType<typeof userEvent.setup>, name: string) {
  return user.click(getInspector(name).previousElementSibling as HTMLElement);
}

function queryInspector(name?: string) {
  if (name) return screen.queryByRole("dialog", { name });
  return (
    screen
      .queryAllByRole("dialog")
      .find((dialog) =>
        within(dialog).queryByRole("button", { name: "Close details" }),
      ) ?? null
  );
}

async function openAddMenu(user: ReturnType<typeof userEvent.setup>) {
  const [button] = await screen.findAllByRole("button", {
    name: "Add documents",
  });
  await user.click(button);
}

const classificationDetail = vi.mocked(getClassification);
const extractionStatus = vi.mocked(getExtractionStatuses);

function extractionFor(id: string, changes: Partial<ExtractionStatus> = {}): ExtractionStatus {
  return {
    revision_document_id: id,
    processing_run_id: "processing-1",
    ineligible_reason: null,
    engineering: { latest_attempt: null, effective_result: null },
    tables: { latest_attempt: null, effective_result: null },
    enrichment: null,
    ...changes,
  };
}

beforeEach(() => {
  nav.search = "";
  vi.mocked(recentExtractionOperations).mockResolvedValue({ items: [] });
  list.mockResolvedValue([]);
  extractionStatus.mockImplementation(async (_project, _revision, ids) => Object.fromEntries(ids.map((id) => [id, extractionFor(id)])));
  classificationDetail.mockResolvedValue({
    enabled: true,
    suggestion: null,
    attempt: null,
    confidence_score: null,
    alternatives: [],
    rationale: null,
  });
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("RevisionDocuments rows", () => {
  it("renders document, type, and state, with quiet secondary facts", async () => {
    list.mockResolvedValue([
      makeRow({ name: "SLD_RevB.pdf" }),
      makeRow({
        name: "Scan.pdf",
        origin: "INHERITED",
        inherited_from_revision_id: "r-1",
        inherited_from_revision_identifier: "1",
        document_type: "UNKNOWN",
        document_number: "E-101",
        classification: {
          enabled: true,
          suggestion: suggestion({
            predicted_type: "TRANSFORMER_SHOP_DRAWING",
          }),
          attempt: attempt({ status: "COMPLETED" }),
        },
      }),
      makeRow({
        name: "notes.pdf",
        document_type: "ELECTRICAL_DRAWING",
        classification: {
          enabled: true,
          suggestion: suggestion({ predicted_type: "SINGLE_LINE_DIAGRAM" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
      }),
    ]);
    renderWorkspace();

    expect(
      await screen.findByRole("columnheader", { name: "Document" }),
    ).toBeInTheDocument();
    for (const name of [
      "Confirmed type",
      "Processing",
      "AI classification",
      "Origin",
    ]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }

    const uploaded = await screen.findByRole("row", { name: /SLD_RevB.pdf/ });
    expect(
      within(uploaded).getByText("Single Line Diagram"),
    ).toBeInTheDocument();
    expect(within(uploaded).getByText("Uploaded")).toBeInTheDocument();
    expect(within(uploaded).getByText("Oct 1, 2026")).toBeInTheDocument();
    expect(within(uploaded).getByText("Not started")).toBeInTheDocument();
    expect(within(uploaded).queryByText("Included")).toBeNull();

    const inherited = screen.getByRole("row", { name: /Scan.pdf/ });
    expect(within(inherited).getByText("Unclassified")).toBeInTheDocument();
    expect(within(inherited).getByText(/^E-101 · /)).toBeInTheDocument();
    expect(within(inherited).getByText("Inherited")).toBeInTheDocument();
    expect(within(inherited).getByText("Needs review")).toBeInTheDocument();
    expect(
      within(inherited).getByText("Suggested: Transformer Shop Drawing"),
    ).toBeInTheDocument();

    const differs = screen.getByRole("row", { name: /notes.pdf/ });
    expect(within(differs).getByText("Electrical Drawing")).toBeInTheDocument();
    expect(
      within(differs).getByText("Suggested: Single Line Diagram"),
    ).toBeInTheDocument();
  });

  it("shows the empty state, and a filtered empty state with Clear filters", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    expect(
      await screen.findByText("No documents in this revision"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Clear filters")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Filters" }));
    await selectOption(screen.getByLabelText("Origin"), "INHERITED");
    expect(
      await screen.findByText("No documents match your filters."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(
      await screen.findByText("No documents in this revision"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByLabelText("Origin")).toHaveValue("");
  });

  it("offers Download for a TIFF and Open original for a PDF in the inspector", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "plan.tif", mime: "image/tiff" }),
      makeRow({ name: "plan.pdf" }),
    ]);
    renderWorkspace();

    const tiff = await openDrawer(user, "plan.tif");
    expect(within(tiff).getByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(within(tiff).queryByRole("button", { name: "Open original" })).toBeNull();
    await user.keyboard("{Escape}");

    const pdf = await openDrawer(user, "plan.pdf");
    expect(within(pdf).getByRole("button", { name: "Open original" })).toBeInTheDocument();
    expect(within(pdf).getByRole("button", { name: "Download" })).toBeInTheDocument();
  });

  it("opens the drawer from the row and keeps extraction selection independent", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "a.pdf" }),
      makeRow({ name: "b.pdf" }),
    ]);
    renderWorkspace(true);

    const first = await screen.findByRole("row", { name: /a.pdf/ });
    expect(classificationDetail).not.toHaveBeenCalled();
    expect(vi.mocked(listClassificationPages)).not.toHaveBeenCalled();
    await user.click(first);
    expect(nav.push).toHaveBeenCalledWith(
      "/projects/p-1/revisions/r-2?document=rd-a.pdf",
    );
    const drawer = await findInspector("a.pdf");
    expect(
      within(drawer).getByText("Uploaded in this revision"),
    ).toBeInTheDocument();
    expect(classificationDetail).toHaveBeenCalledWith(P, R, "rd-a.pdf");
    expect(first).toHaveAttribute("aria-selected", "true");

    await user.click(within(drawer).getByRole("button", { name: "Close details" }));
    await user.click(screen.getByRole("row", { name: /b.pdf/ }));
    expect(
      await findInspector("b.pdf"),
    ).toBeInTheDocument();
    expect(queryInspector("a.pdf")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Close details" }));
    expect(queryInspector()).toBeNull();

    const reopened = screen.getByRole("row", { name: /a.pdf/ });
    reopened.focus();
    await user.keyboard("{Enter}");
    expect(
      await findInspector("a.pdf"),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(queryInspector()).toBeNull();

    const checkbox = screen.getByRole("checkbox", { name: "Select a.pdf for extraction" });
    await waitFor(() => expect(checkbox).toBeEnabled());
    checkbox.focus();
    await user.keyboard(" ");
    expect(checkbox).toBeChecked();
    expect(queryInspector()).toBeNull();
    expect(screen.getByRole("button", { name: "Start extraction" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Actions for a.pdf" })).toBeNull();
  });

  it("reports each extraction family and selects a confirmed type without using AI suggestions", async () => {
    const user = userEvent.setup();
    const confirmed = makeRow({ name: "confirmed.pdf", document_type: "SINGLE_LINE_DIAGRAM" });
    const suggested = makeRow({
      name: "suggested.pdf",
      document_type: "UNKNOWN",
      classification: { enabled: true, suggestion: suggestion(), attempt: null },
    });
    const removed = makeRow({ name: "removed.pdf", status: "REMOVED", document_type: "SINGLE_LINE_DIAGRAM" });
    const completed = { id: "run", status: "COMPLETED" as const, processing_run_id: "processing-1", profile_key: "engineering-openai-enriched-v1", created_at: "2026-01-20T12:00:00Z" };
    list.mockResolvedValue([confirmed, suggested, removed]);
    extractionStatus.mockImplementation(async (_project, _revision, ids) => Object.fromEntries(ids.map((id) => [
      id, extractionFor(id, id === confirmed.id ? { engineering: { latest_attempt: completed, effective_result: completed } }
        : id === removed.id ? { ineligible_reason: "REMOVED" } : {}),
    ])));
    renderWorkspace(true);

    const register = await screen.findByRole("table", { name: "Documents register" });
    const headers = within(register).getAllByRole("columnheader").map((item) => item.textContent?.trim());
    expect(headers.slice(4)).toEqual(["AI classification", "AI Extraction", "Origin"]);
    const row = await screen.findByRole("row", { name: /confirmed\.pdf/ });
    expect(await within(row).findByText("Partial")).toBeInTheDocument();
    await selectOption(screen.getByRole("combobox", { name: "Select documents by scope" }), "type:SINGLE_LINE_DIAGRAM");
    expect(await screen.findByText("1 eligible document selected")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select confirmed.pdf for extraction" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Select suggested.pdf for extraction" })).not.toBeChecked();
    await user.click(screen.getByText("1 skipped"));
    expect(screen.getByText("removed.pdf · Removed from this revision")).toBeVisible();
  });

  it("keeps a compatible extraction result visible after a later attempt fails", async () => {
    const user = userEvent.setup();
    const row = makeRow({ name: "retained.pdf" });
    const completed = {
      id: "completed-run",
      status: "COMPLETED" as const,
      processing_run_id: "processing-1",
      profile_key: "engineering-openai-enriched-v1",
      created_at: "2026-01-20T12:00:00Z",
    };
    list.mockResolvedValue([row]);
    extractionStatus.mockResolvedValue({
      [row.id]: extractionFor(row.id, {
        engineering: {
          latest_attempt: {
            ...completed,
            id: "failed-run",
            status: "FAILED",
            created_at: "2026-01-21T12:00:00Z",
          },
          effective_result: completed,
        },
      }),
    });
    renderWorkspace();

    const registerRow = await screen.findByRole("row", { name: /retained\.pdf/ });
    expect(
      await within(registerRow).findByText(/Engineering · Failed \(previous result available\)/),
    ).toBeVisible();
    const drawer = await openDrawer(user, "retained.pdf");
    await user.click(await within(drawer).findByRole("button", { name: "View results" }));
    expect(nav.push).toHaveBeenLastCalledWith(
      `/projects/${P}/revisions/${R}/documents/${row.id}?mode=evidence`,
    );
  });


  it("resumes a saved operation from the document inspector URL", async () => {
    const user = userEvent.setup();
    const row = makeRow({ name: "resumed.pdf" });
    const operationId = "10000000-0000-4000-8000-000000000001";
    nav.search = new URLSearchParams({ document: row.id, operation: operationId }).toString();
    list.mockResolvedValue([row]);
    const waiting = {
      run_id: null, status: "WAITING" as const, error_code: null, attempts: 0,
      unknown_provider_outcome: false, can_retry: false,
    };
    const detail: OperationDetail = {
      id: operationId, created_at: "2026-01-20T12:00:00Z", status: "QUEUED", mode: "ensure",
      cancel_requested: false, can_cancel: true, provider_admissions: 6, unavailable_sources: 0,
      items: [{
        revision_document_id: row.id, filename: "resumed.pdf", processing_run_id: "processing-1",
        pages: [1], force_ocr_pages: [], status: "QUEUED", blocked_reason: null, can_resume: false,
        layout: waiting, profiles: { engineering: waiting },
      }],
    };
    vi.mocked(getExtractionOperation).mockResolvedValue(detail);
    vi.mocked(cancelExtractionOperation).mockResolvedValue({
      ...detail, status: "CANCELLED", can_cancel: false, cancel_requested: true,
    });
    renderWorkspace(true);
    const drawer = await findInspector("resumed.pdf");
    expect(await within(drawer).findByText(`Operation ID · ${operationId}`)).toBeVisible();
    expect(within(drawer).getByText("Engineering · Waiting")).toBeVisible();
    await user.click(within(drawer).getByRole("button", { name: "Cancel operation" }));
    expect(cancelExtractionOperation).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Stop scheduling" }));
    expect(await within(drawer).findByText("Scheduling stopped. Already admitted runs may finish.")).toBeVisible();
    expect(cancelExtractionOperation).toHaveBeenCalledWith(expect.objectContaining({ revisionId: R }), operationId);
  });

});

describe("RevisionDocuments filters", () => {
  it("loads every document once and leaves type and origin to the client", async () => {
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    expect(list).toHaveBeenCalledWith(P, R, { status: "ALL", search: "" });
  });

  it("filters type, origin, processing, and classification without another request", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "local.pdf" }),
      makeRow({
        name: "shop.pdf",
        origin: "INHERITED",
        document_type: "CABLE_SCHEDULE",
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
            prediction_id: "pred",
            predicted_type: "CABLE_SCHEDULE",
            confidence_band: "HIGH",
            accepted: true,
            requires_page_classification: false,
          },
          attempt: {
            id: "run",
            status: "COMPLETED",
            stage: "DOCUMENT",
            pages_total: 2,
            pages_classified: 2,
            error_code: null,
          },
        },
      }),
    ]);
    renderWorkspace();
    expect(await screen.findByText("local.pdf")).toBeInTheDocument();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "Filters" }));
    await selectOption(
      screen.getByLabelText("Document type"),
      "CABLE_SCHEDULE",
    );
    await selectOption(screen.getByLabelText("Origin"), "INHERITED");
    await selectOption(screen.getByLabelText("Processing"), "COMPLETED");
    await selectOption(screen.getByLabelText("AI classification"), "ready");

    expect(
      screen.getByRole("button", { name: "Filters (4)" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("local.pdf")).toBeNull();
    expect(screen.getByText("shop.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Clear all" }));
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
    expect(screen.getByText("local.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("debounces search and sends a single request for the final text", async () => {
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    const input = screen.getByLabelText("Search");

    fireEvent.change(input, { target: { value: "s" } });
    fireEvent.change(input, { target: { value: "sl" } });
    fireEvent.change(input, { target: { value: "sld" } });
    expect(list).toHaveBeenCalledTimes(1);

    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(P, R, {
        status: "ALL",
        search: "sld",
      }),
    );
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("ignores a slow earlier response that finishes after a newer one", async () => {
    let resolveFirst: (rows: RevisionDocument[]) => void = () => {};
    list.mockImplementationOnce(
      () =>
        new Promise<RevisionDocument[]>((resolve) => (resolveFirst = resolve)),
    );
    list.mockResolvedValueOnce([makeRow({ name: "fresh.pdf" })]);
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "fresh" },
    });
    expect(await screen.findByText("fresh.pdf")).toBeInTheDocument();

    await act(async () => {
      resolveFirst([makeRow({ name: "stale.pdf" })]);
    });
    expect(screen.getByText("fresh.pdf")).toBeInTheDocument();
    expect(screen.queryByText("stale.pdf")).toBeNull();
  });

  it("keeps classification, page, and download actions in the inspector", async () => {
    list.mockResolvedValue([
      makeRow({
        name: "ready.pdf",
        document_type: "PANEL_SCHEDULE",
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
            prediction_id: "pred",
            predicted_type: "PANEL_SCHEDULE",
            confidence_band: "HIGH",
            accepted: false,
            requires_page_classification: false,
          },
          attempt: {
            id: "run",
            status: "COMPLETED",
            stage: "DOCUMENT",
            pages_total: 2,
            pages_classified: 2,
            error_code: null,
          },
        },
      }),
    ]);
    renderWorkspace(true);

    const row = await screen.findByRole("row", { name: /ready.pdf/ });
    await userEvent.setup().click(row);
    const drawer = await findInspector("ready.pdf");
    expect(
      within(drawer).getByRole("button", { name: "Accept suggestion" }),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByRole("button", { name: "View pages / evidence" }),
    ).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Download" })).toBeInTheDocument();
  });
});

describe("RevisionDocuments errors", () => {
  it("polls an active classification attempt and stops after failure while retaining the completed suggestion", async () => {
    vi.useFakeTimers();
    focusManager.setFocused(true);
    try {
      const row = makeRow({
        name: "classification.pdf",
        classification: {
          enabled: true,
          suggestion: suggestion(),
          attempt: attempt({
            status: "RUNNING",
            stage: "PAGES",
            pages_total: 2,
            pages_classified: 1,
          }),
        },
      });
      list.mockResolvedValue([row]);
      const view = renderWorkspace();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20);
      });
      list.mockResolvedValue([
        {
          ...row,
          classification: {
            ...row.classification,
            attempt: attempt({ status: "FAILED" }),
          },
        },
      ]);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(list).toHaveBeenCalledTimes(2);
      expect(
        view.queryClient.getQueryData<RevisionDocument[]>(
          keys.documentList(P, R, ""),
        )?.[0].classification.suggestion,
      ).toEqual(row.classification.suggestion);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(9000);
      });
      expect(list).toHaveBeenCalledTimes(2);
    } finally {
      focusManager.setFocused(undefined);
      vi.useRealTimers();
    }
  });
  it("keeps rows visible when a later refresh fails and permits recovery", async () => {
    list.mockResolvedValue([makeRow({ name: "kept.pdf" })]);
    const view = renderWorkspace();
    await screen.findByText("kept.pdf");
    list.mockRejectedValue(apiError(500, "Refresh unavailable"));
    await act(() =>
      view.queryClient.invalidateQueries({ queryKey: keys.documents(P, R) }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Refresh unavailable",
    );
    expect(screen.getByText("kept.pdf")).toBeInTheDocument();
    list.mockResolvedValue([makeRow({ name: "fresh.pdf" })]);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText("fresh.pdf");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("preserves metadata drafts when document summaries refresh", async () => {
    const row = makeRow({ name: "draft.pdf", notes: "Original" });
    list.mockResolvedValue([row]);
    const view = renderWorkspace(true);
    await userEvent
      .setup()
      .click(await screen.findByRole("row", { name: /draft.pdf/ }));
    const notes = await screen.findByLabelText("Notes");
    fireEvent.change(notes, { target: { value: "My unsaved notes" } });
    list.mockResolvedValue([{ ...row, notes: "Changed elsewhere" }]);
    await act(() =>
      view.queryClient.invalidateQueries({
        queryKey: keys.documentList(P, R, ""),
      }),
    );
    expect(screen.getByLabelText("Notes")).toHaveValue("My unsaved notes");
  });

  it("polls real running jobs, pauses in the background, and stops on completion", async () => {
    vi.useFakeTimers();
    focusManager.setFocused(true);
    try {
      const running = makeRow({
        name: "job.pdf",
        processing: {
          status: "RUNNING",
          pages_total: 2,
          pages_processed: 1,
          error_message: null,
          attempt_count: 1,
          error_code: null,
        },
      });
      list.mockResolvedValue([running]);
      const view = renderWorkspace();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20);
      });
      expect(list).toHaveBeenCalledTimes(1);
      focusManager.setFocused(false);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(list).toHaveBeenCalledTimes(1);
      focusManager.setFocused(true);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(list.mock.calls.length).toBeGreaterThan(1);
      list.mockResolvedValue([
        {
          ...running,
          classification: { enabled: false, attempt: null, suggestion: null },
          processing: {
            ...running.processing!,
            status: "COMPLETED",
            pages_processed: 2,
          },
        },
      ]);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      const completedCalls = list.mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(12_000);
      });
      expect(list).toHaveBeenCalledTimes(completedCalls);
      view.unmount();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(list).toHaveBeenCalledTimes(completedCalls);
    } finally {
      focusManager.setFocused(undefined);
      vi.useRealTimers();
    }
  });

  it("refreshes once and tells the user when the list returns 409", async () => {
    list.mockRejectedValueOnce(apiError(409, "Revision state changed."));
    list.mockResolvedValueOnce([makeRow({ name: "after.pdf" })]);
    renderWorkspace();

    expect(await screen.findByText("after.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Revision state changed.",
    );
  });

  it("shows other errors with Retry", async () => {
    const user = userEvent.setup();
    list.mockRejectedValueOnce(apiError(500, "Server exploded"));
    renderWorkspace();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Server exploded",
    );
    list.mockResolvedValueOnce([makeRow({ name: "ok.pdf" })]);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("ok.pdf")).toBeInTheDocument();
  });
});

describe("RevisionDocuments download actions", () => {
  const url = "http://localhost:9000/bucket/key?sig=1";

  it("Open requests an inline URL and navigates the pre-opened tab", async () => {
    const user = userEvent.setup();
    const tab = { opener: "x", location: { href: "" }, close: vi.fn() };
    const open = vi
      .spyOn(window, "open")
      .mockReturnValue(tab as unknown as Window);
    download.mockResolvedValue({
      url,
      expires_at: "2026-10-01T10:05:00Z",
      filename: "a.pdf",
    });
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace();

    await openDrawer(user, "a.pdf");
    await user.click(screen.getByRole("button", { name: "Open original" }));

    await waitFor(() => expect(tab.location.href).toBe(url));
    expect(open).toHaveBeenCalledWith("", "_blank");
    expect(download).toHaveBeenCalledWith(P, R, "rd-a.pdf", "inline");
    expect(tab.opener).toBeNull();
    expect(tab.close).not.toHaveBeenCalled();
  });

  it("Download requests an attachment URL and assigns the location", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    download.mockResolvedValue({
      url,
      expires_at: "2026-10-01T10:05:00Z",
      filename: "a.tif",
    });
    list.mockResolvedValue([makeRow({ name: "a.tif", mime: "image/tiff" })]);
    renderWorkspace();

    await openDrawer(user, "a.tif");
    await user.click(
      screen.getByRole("button", { name: "Download" }),
    );

    await waitFor(() => expect(assign).toHaveBeenCalledWith(url));
    expect(download).toHaveBeenCalledWith(P, R, "rd-a.tif", "attachment");
  });

  it("closes the pre-opened tab and shows the error when the URL request fails", async () => {
    const user = userEvent.setup();
    const tab = { opener: "x", location: { href: "" }, close: vi.fn() };
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    download.mockRejectedValue(apiError(502, "Storage unavailable"));
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace();

    await openDrawer(user, "a.pdf");
    await user.click(screen.getByRole("button", { name: "Open original" }));

    expect(await screen.findByText("Storage unavailable")).toBeInTheDocument();
    expect(tab.close).toHaveBeenCalled();
    expect(tab.location.href).toBe("");
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("refreshes the list when a download reports the state changed (404)", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "open").mockReturnValue(null);
    download.mockRejectedValue(apiError(404, "Document not found"));
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    list.mockResolvedValueOnce([]);
    renderWorkspace();

    await openDrawer(user, "a.pdf");
    await user.click(screen.getByRole("button", { name: "Open original" }));

    expect(
      await screen.findByText("No documents in this revision"),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Document not found");
    expect(list).toHaveBeenCalledTimes(2);
  });
});

describe("RevisionDocuments upload area", () => {
  const upload = vi.mocked(uploadDocument);

  function choose(file: File) {
    fireEvent.change(screen.getByLabelText("Choose files"), {
      target: { files: [file] },
    });
  }
  const pdf = () =>
    new File([new Uint8Array(10)], "new.pdf", { type: "application/pdf" });

  it("is absent when the revision cannot be changed and opens from Add Documents when it can", async () => {
    const user = userEvent.setup();
    const first = renderWorkspace(false);
    await waitFor(() => expect(list).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Add documents" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Choose files" }),
    ).toBeNull();
    first.unmount();

    renderWorkspace(true);
    expect(
      screen.queryByRole("button", { name: "Choose files" }),
    ).toBeNull();
    await openAddMenu(user);
    expect(
      screen.getByRole("menuitem", { name: "Upload files" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Add from another revision" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    expect(
      await screen.findByRole("button", { name: "Choose files" }),
    ).toBeInTheDocument();
  });

  it("reloads the list when an upload completes", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue({
      duplicate_detected: false,
      duplicate_document_ids: [],
    } as never);
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    list.mockResolvedValue([makeRow({ name: "new.pdf" })]);

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    choose(pdf());

    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(
      await screen.findByRole("row", { name: /new\.pdf/ }),
    ).toBeInTheDocument();
  });

  it("keeps uploading after the dialog closes", async () => {
    const user = userEvent.setup();
    let finish: (value: unknown) => void = () => {};
    upload.mockReturnValue(
      new Promise((resolve) => (finish = resolve)) as never,
    );
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    choose(pdf());
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    list.mockResolvedValue([makeRow({ name: "new.pdf" })]);
    await act(async () => {
      finish({ duplicate_detected: false, duplicate_document_ids: [] });
    });
    expect(
      await screen.findByRole("row", { name: /new\.pdf/ }),
    ).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("shows a notice, refreshes the page and reloads the list on a read-only 409", async () => {
    const user = userEvent.setup();
    upload.mockRejectedValue(
      Object.assign(new Error("Revision is superseded."), {
        apiError: {
          detail: "Revision is superseded.",
          code: "revision_read_only",
        },
        status: 409,
      }),
    );
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    choose(pdf());

    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Revision is superseded.",
    );
    expect(refresh).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });
});

describe("RevisionDocuments quick views", () => {
  const reviewClassification = {
    enabled: true,
    suggestion: {
      prediction_id: "pred",
      predicted_type: "PANEL_SCHEDULE" as const,
      confidence_band: "HIGH" as const,
      accepted: false,
      requires_page_classification: false,
    },
    attempt: {
      id: "run",
      status: "COMPLETED" as const,
      stage: "DOCUMENT" as const,
      pages_total: 1,
      pages_classified: 1,
      error_code: null,
    },
  };
  const failedProcessing = {
    status: "FAILED" as const,
    attempt_count: 1,
    pages_processed: 0,
    pages_total: 4,
    error_code: "RENDER_FAILED",
    error_message: "Could not read the file",
  };

  function loadMixed() {
    list.mockResolvedValue([
      makeRow({ name: "ready.pdf" }),
      makeRow({
        name: "review.pdf",
        document_type: "UNKNOWN",
        classification: reviewClassification,
      }),
      makeRow({ name: "bad.pdf", processing: failedProcessing }),
      makeRow({ name: "gone.pdf", status: "REMOVED" }),
    ]);
  }

  it("counts Needs Review and Issues inside All, and Removed outside it", async () => {
    loadMixed();
    renderWorkspace();

    expect(await screen.findByText("ready.pdf")).toBeInTheDocument();
    expect(quickView("All")).toHaveTextContent("3");
    expect(quickView("Needs review")).toHaveTextContent("1");
    expect(quickView("Issues")).toHaveTextContent("1");
    expect(quickView("Removed")).toHaveTextContent("1");
    expect(
      screen.getByText("Showing 3 of 3 active documents"),
    ).toBeInTheDocument();
    expect(screen.queryByText("gone.pdf")).toBeNull();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("filters All, Needs Review, Issues, and Removed in the client", async () => {
    const user = userEvent.setup();
    loadMixed();
    renderWorkspace();
    expect(await screen.findByText("ready.pdf")).toBeInTheDocument();
    expect(screen.getByText("review.pdf")).toBeInTheDocument();
    expect(screen.getByText("bad.pdf")).toBeInTheDocument();

    await user.click(quickView("Needs review"));
    expect(screen.getByText("review.pdf")).toBeInTheDocument();
    expect(screen.queryByText("ready.pdf")).toBeNull();
    expect(screen.queryByText("bad.pdf")).toBeNull();
    expect(screen.queryByText("gone.pdf")).toBeNull();

    await user.click(quickView("Issues"));
    expect(screen.getByText("bad.pdf")).toBeInTheDocument();
    expect(screen.queryByText("review.pdf")).toBeNull();

    await user.click(quickView("Removed"));
    expect(screen.getByText("gone.pdf")).toBeInTheDocument();
    expect(screen.queryByText("bad.pdf")).toBeNull();

    await user.click(quickView("All"));
    expect(screen.getByText("ready.pdf")).toBeInTheDocument();
    expect(screen.queryByText("gone.pdf")).toBeNull();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("uses a distinct empty message for each quick view", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "ready.pdf" })]);
    renderWorkspace();
    expect(await screen.findByText("ready.pdf")).toBeInTheDocument();

    await user.click(quickView("Needs review"));
    expect(screen.getByText("No documents need review")).toBeInTheDocument();
    await user.click(quickView("Issues"));
    expect(screen.getByText("No document issues")).toBeInTheDocument();
    await user.click(quickView("Removed"));
    expect(screen.getByText("No removed documents")).toBeInTheDocument();
  });

  it("says when search matches nothing", async () => {
    list.mockImplementation(async (_project, _revision, filters) =>
      filters?.search ? [] : [makeRow({ name: "sld.pdf" })],
    );
    renderWorkspace();
    expect(await screen.findByText("sld.pdf")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "missing" },
    });
    expect(
      await screen.findByText("No documents match your search"),
    ).toBeInTheDocument();
  });

  it("treats a revision that only has removed documents as empty in All", async () => {
    list.mockResolvedValue([makeRow({ name: "gone.pdf", status: "REMOVED" })]);
    renderWorkspace();

    expect(
      await screen.findByText("No documents in this revision"),
    ).toBeInTheDocument();
    expect(screen.queryByText("gone.pdf")).toBeNull();
  });
});

function summary(
  overrides: Partial<ProcessingSummary> & Pick<ProcessingSummary, "status">,
): ProcessingSummary {
  return {
    attempt_count: 1,
    pages_processed: 0,
    pages_total: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

function suggestion(
  overrides: Partial<ClassificationSuggestion> = {},
): ClassificationSuggestion {
  return {
    prediction_id: "pred-1",
    predicted_type: "TRANSFORMER_SHOP_DRAWING",
    confidence_band: "HIGH",
    accepted: false,
    requires_page_classification: false,
    ...overrides,
  };
}

function attempt(
  overrides: Partial<ClassificationAttempt> & {
    status: ClassificationAttempt["status"];
  },
): ClassificationAttempt {
  return {
    id: "run-1",
    stage: "DOCUMENT",
    pages_total: 2,
    pages_classified: 0,
    error_code: null,
    ...overrides,
  };
}

function page(id: string, pageNumber: number) {
  return {
    id,
    page_number: pageNumber,
    source_width: "612",
    source_height: "792",
    source_unit: "POINTS" as const,
    rotation_degrees: 0,
    native_text_char_count: 0,
    artifacts: [],
  };
}

async function openDrawer(
  user: ReturnType<typeof userEvent.setup>,
  name: string,
) {
  await user.click(await screen.findByRole("row", { name: new RegExp(name) }));
  return findInspector(name);
}

describe("RevisionDocuments inspector actions", () => {
  const remove = vi.mocked(removeDocument);
  const restore = vi.mocked(restoreDocument);
  const update = vi.mocked(updateDocument);

  it("shows download on a read-only row and hides mutations", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "a.pdf",
        processing: summary({
          status: "COMPLETED",
          pages_processed: 1,
          pages_total: 1,
        }),
        classification: {
          enabled: true,
          suggestion: suggestion(),
          attempt: attempt({
            status: "FAILED",
            error_code: "PROVIDER_TIMEOUT",
          }),
        },
      }),
    ]);
    renderWorkspace(false);

    const drawer = await openDrawer(user, "a.pdf");
    expect(within(drawer).getByRole("button", { name: "Download" })).toBeEnabled();
    expect(within(drawer).getByRole("button", { name: "Open original" })).toBeEnabled();
    expect(within(drawer).queryByRole("button", { name: "Remove" })).toBeNull();
    expect(
      within(drawer).queryByRole("button", { name: "Accept suggestion" }),
    ).toBeNull();
    expect(
      within(drawer).queryByRole("button", { name: "Change type" }),
    ).toBeNull();
    expect(
      within(drawer).getByRole("button", { name: "Retry" }),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByRole("button", { name: "Reclassify" }),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByRole("button", { name: "Retry processing" }),
    ).toBeNull();
    expect(
      within(drawer).getByRole("button", { name: "View pages / evidence" }),
    ).toBeInTheDocument();
  });

  it("follows state for included, removed, and failed rows", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "a.pdf" }),
      makeRow({
        name: "bad.pdf",
        processing: summary({ status: "FAILED", error_message: "Corrupt" }),
        classification: {
          enabled: true,
          suggestion: suggestion(),
          attempt: attempt({ status: "FAILED" }),
        },
      }),
      makeRow({ name: "b.pdf", status: "REMOVED" }),
    ]);
    renderWorkspace(true);

    const included = within(await openDrawer(user, "a.pdf"));
    expect(included.getByLabelText("Document number")).toBeEnabled();
    expect(included.getByRole("button", { name: "Remove" })).toBeEnabled();
    expect(included.queryByRole("button", { name: "Restore" })).toBeNull();
    expect(included.getByRole("button", { name: "View pages / evidence" })).toBeEnabled();
    await user.keyboard("{Escape}");

    const failed = within(await openDrawer(user, "bad.pdf"));
    expect(failed.getByRole("button", { name: "Retry processing" })).toBeEnabled();
    expect(failed.getByRole("button", { name: "Retry" })).toBeEnabled();
    expect(failed.getByRole("button", { name: "View pages / evidence" })).toBeEnabled();
    await user.keyboard("{Escape}");

    await user.click(quickView("Removed"));
    const removed = within(await openDrawer(user, "b.pdf"));
    expect(removed.getByRole("button", { name: "Restore" })).toBeEnabled();
    expect(removed.getByRole("button", { name: "Download" })).toBeEnabled();
    expect(removed.queryByRole("button", { name: "Remove" })).toBeNull();
    expect(removed.getByLabelText("Document number")).toBeDisabled();
  });

  it("removes only after confirmation and reloads the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    remove.mockResolvedValue({} as never);
    renderWorkspace(true);

    const drawer = await openDrawer(user, "a.pdf");
    await user.click(within(drawer).getByRole("button", { name: "Remove" }));
    expect(remove).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Remove document from this revision?" })).toBeInTheDocument();

    list.mockResolvedValueOnce([]);
    await user.click(within(screen.getByRole("dialog", { name: "Remove document from this revision?" })).getByRole("button", { name: "Remove" }));

    expect(remove).toHaveBeenCalledWith(P, R, "rd-a.pdf");
    expect(
      await screen.findByText("No documents in this revision"),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Removed a.pdf from this revision.",
    );
  });

  it("does nothing when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace(true);

    const drawer = await openDrawer(user, "a.pdf");
    await user.click(within(drawer).getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(remove).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "Remove document from this revision?" })).toBeNull();
    expect(drawer).toBeInTheDocument();
  });

  it("restores a removed row without confirmation", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "b.pdf", status: "REMOVED" })]);
    restore.mockResolvedValue({} as never);
    renderWorkspace(true);
    await user.click(quickView("Removed"));

    const drawer = await openDrawer(user, "b.pdf");
    await user.click(within(drawer).getByRole("button", { name: "Restore" }));

    expect(restore).toHaveBeenCalledWith(P, R, "rd-b.pdf");
    await waitFor(() => expect(screen.getAllByText("Restored b.pdf.").length).toBeGreaterThan(0));
    expect(screen.queryByRole("dialog", { name: "Restore document?" })).toBeNull();
  });

  it("explains a 409 on remove and refreshes the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    remove.mockRejectedValue(
      Object.assign(new Error("Document state changed."), {
        status: 409,
        apiError: {
          code: "document_removed",
          detail: "Document state changed.",
        },
      }),
    );
    renderWorkspace(true);

    const drawer = await openDrawer(user, "a.pdf");
    await user.click(within(drawer).getByRole("button", { name: "Remove" }));
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf", status: "REMOVED" })]);
    await user.click(within(screen.getByRole("dialog", { name: "Remove document from this revision?" })).getByRole("button", { name: "Remove" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Document state changed.",
    );
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("saves edited metadata from the drawer and reloads the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    update.mockResolvedValue(
      makeRow({ name: "a.pdf", document_number: "E-7" }),
    );
    renderWorkspace(true);

    const drawer = await openDrawer(user, "a.pdf");
    await user.type(within(drawer).getByLabelText("Document number"), "E-7");
    list.mockResolvedValueOnce([
      makeRow({ name: "a.pdf", document_number: "E-7" }),
    ]);
    await user.click(
      within(drawer).getByRole("button", { name: "Save changes" }),
    );

    expect(update).toHaveBeenCalledWith(P, R, "rd-a.pdf", {
      document_number: "E-7",
    });
    expect(await within(drawer).findByDisplayValue("E-7")).toBeInTheDocument();
    expect(within(drawer).getByRole("status")).toHaveTextContent(
      "Saved changes to a.pdf.",
    );
    expect(getInspector("a.pdf")).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "Close details" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Saved changes to a.pdf.",
    );
  });

  it("opens the reuse dialog from Add from another revision", async () => {
    const user = userEvent.setup();
    vi.mocked(listRevisions).mockResolvedValue([]);
    renderWorkspace(true);

    await openAddMenu(user);
    await user.click(
      screen.getByRole("menuitem", { name: "Add from another revision" }),
    );
    expect(
      await screen.findByText("This project has no other revisions."),
    ).toBeInTheDocument();
  });
});

describe("processing and page viewer", () => {
  const retry = vi.mocked(retryProcessing);
  const pages = vi.mocked(listPages);
  const artifactUrl = vi.mocked(getPageArtifactUrl);

  it("renders state from the list and the failure detail in the drawer", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "none.pdf" }),
      makeRow({ name: "wait.pdf", processing: summary({ status: "PENDING" }) }),
      makeRow({
        name: "run.pdf",
        processing: summary({
          status: "RUNNING",
          pages_processed: 1,
          pages_total: 4,
        }),
      }),
      makeRow({
        name: "done.pdf",
        processing: summary({
          status: "COMPLETED",
          pages_processed: 4,
          pages_total: 4,
        }),
      }),
      makeRow({
        name: "bad.pdf",
        processing: summary({
          status: "FAILED",
          error_message: "Could not read the file",
        }),
      }),
    ]);
    renderWorkspace(true);

    expect(await screen.findByText("Not started")).toBeInTheDocument();
    const running = screen.getByRole("row", { name: /run.pdf/ });
    expect(within(running).getByText("Processing")).toBeInTheDocument();
    expect(within(running).getByText("1 / 4 pages")).toBeInTheDocument();
    expect(
      within(running).getByRole("progressbar", {
        name: "Processing progress for run.pdf",
      }),
    ).toHaveAttribute("aria-valuenow", "25");
    expect(
      within(screen.getByRole("row", { name: /done.pdf/ })).getByText(
        "Complete",
      ),
    ).toBeInTheDocument();
    const failed = screen.getByRole("row", { name: /bad.pdf/ });
    expect(within(failed).getByText("Failed")).toBeInTheDocument();
    expect(within(failed).getByText("Retry available")).toBeInTheDocument();
    expect(within(failed).queryByText("Could not read the file")).toBeNull();
    expect(pages).not.toHaveBeenCalled();
    expect(retry).not.toHaveBeenCalled();
    expect(artifactUrl).not.toHaveBeenCalled();

    const drawer = await openDrawer(user, "bad.pdf");
    expect(within(drawer).getAllByText("Failed").length).toBeGreaterThan(0);
    expect(
      within(drawer).getByText("Could not read the file"),
    ).toBeInTheDocument();
    await user.click(
      within(drawer).getByRole("button", { name: "Retry processing" }),
    );
    expect(retry).toHaveBeenCalledWith(P, R, "rd-bad.pdf");
  });

  it("still offers retry processing when the revision cannot be changed", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "bad.pdf",
        processing: summary({ status: "FAILED", error_message: "Corrupt" }),
      }),
    ]);
    renderWorkspace(false);
    const drawer = await openDrawer(user, "bad.pdf");
    expect(
      within(drawer).getByRole("button", { name: "Retry processing" }),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByRole("button", { name: "Change type" }),
    ).toBeNull();
  });

  it("opens the viewer route from the drawer and leaves that document selected", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "done.pdf",
        processing: summary({
          status: "COMPLETED",
          pages_processed: 2,
          pages_total: 2,
        }),
      }),
    ]);
    renderWorkspace(false);

    const drawer = await openDrawer(user, "done.pdf");
    await user.click(
      within(drawer).getByRole("button", { name: "View pages / evidence" }),
    );

    expect(nav.push).toHaveBeenCalledWith(
      `/projects/${P}/revisions/${R}/documents/rd-done.pdf`,
    );
    expect(pages).not.toHaveBeenCalled();
    expect(getInspector("done.pdf")).toBeInTheDocument();
  });
});

describe("AI classification drawer", () => {
  const accept = vi.mocked(acceptClassification);
  const reclassify = vi.mocked(reclassifyDocument);
  const retry = vi.mocked(retryClassification);
  const classificationPages = vi.mocked(listClassificationPages);
  const update = vi.mocked(updateDocument);

  it("accepts a matching suggestion and does not call classification while painting rows", async () => {
    const user = userEvent.setup();
    const row = makeRow({
      name: "shop.pdf",
      document_type: "TRANSFORMER_SHOP_DRAWING",
      classification: {
        enabled: true,
        suggestion: suggestion(),
        attempt: attempt({ status: "COMPLETED", pages_classified: 2 }),
      },
    });
    list.mockResolvedValue([row]);
    accept.mockResolvedValue(row);
    classificationDetail.mockResolvedValue({
      enabled: true,
      suggestion: suggestion(),
      attempt: attempt({ status: "COMPLETED", pages_classified: 2 }),
      confidence_score: 0.91,
      alternatives: [{ type: "PANEL_SCHEDULE", score: 0.2 }],
      rationale: "Ratings and an outline.",
    });
    renderWorkspace(true);

    expect(await screen.findByText("shop.pdf")).toBeInTheDocument();
    expect(classificationDetail).not.toHaveBeenCalled();
    expect(classificationPages).not.toHaveBeenCalled();

    const drawer = await openDrawer(user, "shop.pdf");
    expect(classificationDetail).toHaveBeenCalledTimes(1);
    expect(classificationPages).not.toHaveBeenCalled();
    expect(
      await within(drawer).findByText("Ratings and an outline."),
    ).toBeInTheDocument();
    expect(within(drawer).getByText("Score 0.91")).toBeInTheDocument();
    expect(within(drawer).getByText("Confidence")).toBeInTheDocument();
    list.mockResolvedValue([
      makeRow({
        name: "shop.pdf",
        document_type: "TRANSFORMER_SHOP_DRAWING",
        classification: {
          enabled: true,
          suggestion: suggestion({ accepted: true }),
          attempt: attempt({ status: "COMPLETED", pages_classified: 2 }),
        },
      }),
    ]);
    await user.click(
      within(drawer).getByRole("button", { name: "Accept suggestion" }),
    );

    expect(accept).toHaveBeenCalledWith(P, R, "rd-shop.pdf", "pred-1");
    expect(
      await within(drawer).findByText("Accepted AI classification"),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByRole("button", { name: "Accept suggestion" }),
    ).toBeNull();
  });

  it("uses the suggestion or keeps the current type without a mutation", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "differ.pdf",
        document_type: "ELECTRICAL_DRAWING",
        classification: {
          enabled: true,
          suggestion: suggestion({ predicted_type: "SINGLE_LINE_DIAGRAM" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
      }),
    ]);
    const view = renderWorkspace(true);
    let drawer = await openDrawer(user, "differ.pdf");
    expect(within(drawer).getByText("AI suggestion")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText("Single Line Diagram").length,
    ).toBeGreaterThan(0);

    await user.click(
      within(drawer).getByRole("button", { name: "Keep current" }),
    );
    expect(accept).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
    expect(
      within(drawer).getByText(
        "Confirmed type kept. The suggestion stays unaccepted.",
      ),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByRole("button", { name: "Use AI suggestion" }),
    ).toBeNull();
    view.unmount();

    renderWorkspace(true);
    drawer = await openDrawer(user, "differ.pdf");
    await user.click(
      within(drawer).getByRole("button", { name: "Use AI suggestion" }),
    );
    expect(accept).toHaveBeenCalledWith(P, R, "rd-differ.pdf", "pred-1");
  });

  it("changes type through updateDocument", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    update.mockResolvedValue(
      makeRow({ name: "a.pdf", document_type: "PANEL_SCHEDULE" }),
    );
    renderWorkspace(true);
    const drawer = await openDrawer(user, "a.pdf");
    await user.click(
      within(drawer).getByRole("button", { name: "Change type" }),
    );
    await selectOption(
      within(drawer).getByLabelText("Document type"),
      "PANEL_SCHEDULE",
    );
    list.mockResolvedValueOnce([
      makeRow({ name: "a.pdf", document_type: "PANEL_SCHEDULE" }),
    ]);
    await user.click(within(drawer).getByRole("button", { name: "Save type" }));

    expect(update).toHaveBeenCalledWith(P, R, "rd-a.pdf", {
      document_type: "PANEL_SCHEDULE",
    });
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("keeps a suggestion visible when the latest attempt failed", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "again.pdf",
        document_type: "TRANSFORMER_SHOP_DRAWING",
        processing: summary({
          status: "COMPLETED",
          pages_processed: 2,
          pages_total: 2,
        }),
        classification: {
          enabled: true,
          suggestion: suggestion(),
          attempt: attempt({
            status: "FAILED",
            error_code: "PROVIDER_TIMEOUT",
          }),
        },
      }),
    ]);
    retry.mockResolvedValue({
      enabled: true,
      suggestion: suggestion(),
      attempt: attempt({ status: "PENDING" }),
    });
    renderWorkspace(true);
    const drawer = await openDrawer(user, "again.pdf");
    expect(
      within(drawer).getAllByText("Transformer Shop Drawing").length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getByText("The classification provider timed out."),
    ).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledWith(P, R, "rd-again.pdf", "run-1");

    await user.click(
      within(drawer).getByRole("button", { name: "Reclassify" }),
    );
    expect(reclassify).toHaveBeenCalledWith(P, R, "rd-again.pdf");
  });

  it("shows only the failure when there is no suggestion", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "empty.pdf",
        processing: summary({
          status: "COMPLETED",
          pages_processed: 1,
          pages_total: 1,
        }),
        classification: {
          enabled: true,
          suggestion: null,
          attempt: attempt({ status: "FAILED", error_code: null }),
        },
      }),
    ]);
    renderWorkspace(true);
    const drawer = await openDrawer(user, "empty.pdf");
    expect(
      within(drawer).getAllByText("Classification failed").length,
    ).toBeGreaterThan(0);
    expect(within(drawer).queryByText("Confidence")).toBeNull();
    expect(
      within(drawer).queryByRole("button", { name: "Accept suggestion" }),
    ).toBeNull();
    expect(
      within(drawer).getByRole("button", { name: "Retry" }),
    ).toBeInTheDocument();
  });

  it("loads mixed page predictions in the drawer and opens that page", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "mixed.pdf",
        document_type: "MIXED_DOCUMENT",
        processing: summary({
          status: "COMPLETED",
          pages_processed: 2,
          pages_total: 2,
        }),
        classification: {
          enabled: true,
          suggestion: suggestion({
            predicted_type: "MIXED_DOCUMENT",
            requires_page_classification: true,
          }),
          attempt: attempt({ status: "COMPLETED", pages_classified: 2 }),
        },
      }),
    ]);
    classificationPages.mockResolvedValue([
      { page_number: 1, predicted_type: "OTHER", confidence_band: "LOW" },
      {
        page_number: 2,
        predicted_type: "PANEL_SCHEDULE",
        confidence_band: "HIGH",
      },
    ]);
    vi.mocked(listPages).mockResolvedValue([page("page-2", 2)]);
    vi.mocked(getPageArtifactUrl).mockResolvedValue({
      url: "https://files.example/page-2",
      expires_at: "2026-10-10T00:00:00Z",
      filename: "page.png",
    });
    renderWorkspace(true);

    const table = screen.getByRole("table");
    expect(await screen.findByText("mixed.pdf")).toBeInTheDocument();
    expect(within(table).queryByText("View page classifications")).toBeNull();
    expect(classificationPages).not.toHaveBeenCalled();

    const drawer = await openDrawer(user, "mixed.pdf");
    expect(classificationPages).not.toHaveBeenCalled();
    await user.click(
      within(drawer).getByRole("button", { name: "View page classifications" }),
    );
    expect(classificationPages).toHaveBeenCalledWith(P, R, "rd-mixed.pdf");
    expect(
      await within(drawer).findByRole("button", { name: /2 Panel Schedule/ }),
    ).toBeInTheDocument();
    await user.click(
      within(drawer).getByRole("button", { name: /2 Panel Schedule/ }),
    );
    expect(nav.push).toHaveBeenCalledWith(
      `/projects/${P}/revisions/${R}/documents/rd-mixed.pdf?page=2`,
    );
  });

  it("drops the previous document's page classifications when another row is selected", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "mixed.pdf",
        document_type: "MIXED_DOCUMENT",
        classification: {
          enabled: true,
          suggestion: suggestion({ predicted_type: "MIXED_DOCUMENT" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
      }),
      makeRow({
        name: "other.pdf",
        document_type: "MIXED_DOCUMENT",
        classification: {
          enabled: true,
          suggestion: suggestion({ predicted_type: "MIXED_DOCUMENT" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
      }),
    ]);
    classificationPages.mockResolvedValue([
      {
        page_number: 2,
        predicted_type: "PANEL_SCHEDULE",
        confidence_band: "HIGH",
      },
    ]);
    renderWorkspace(true);

    const drawer = await openDrawer(user, "mixed.pdf");
    await user.click(
      within(drawer).getByRole("button", { name: "View page classifications" }),
    );
    expect(
      await within(drawer).findByRole("button", { name: /2 Panel Schedule/ }),
    ).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "Close details" }));
    await user.click(screen.getByRole("row", { name: /other.pdf/ }));
    const next = await findInspector("other.pdf");
    expect(
      within(next).queryByRole("button", { name: /2 Panel Schedule/ }),
    ).toBeNull();
    expect(
      within(next).getByRole("button", { name: "View page classifications" }),
    ).toBeInTheDocument();
    expect(classificationPages).toHaveBeenCalledTimes(1);
  });

  it("hides accept on a removed row and still shows the suggestion", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "gone.pdf",
        status: "REMOVED",
        document_type: "MOTOR_DATA",
        classification: {
          enabled: true,
          suggestion: suggestion(),
          attempt: attempt({ status: "COMPLETED" }),
        },
      }),
    ]);
    renderWorkspace(true);
    await user.click(quickView("Removed"));
    const drawer = await openDrawer(user, "gone.pdf");
    expect(
      within(drawer).getByText("Transformer Shop Drawing"),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByRole("button", { name: "Accept suggestion" }),
    ).toBeNull();
    expect(
      within(drawer).queryByRole("button", { name: "Choose another type" }),
    ).toBeNull();
  });

  it("reopens the drawer from the document query", async () => {
    nav.search = "document=rd-a.pdf";
    list.mockResolvedValue([
      makeRow({ name: "a.pdf", document_number: "E-1" }),
    ]);
    renderWorkspace();
    const drawer = await findInspector("a.pdf");
    expect(drawer).toHaveTextContent("E-1");
    expect(classificationDetail).toHaveBeenCalledWith(P, R, "rd-a.pdf");
  });

  it("strips a deep-linked document query without leaving the revision", async () => {
    const user = userEvent.setup();
    nav.search = "other=1&document=rd-a.pdf";
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    const view = renderWorkspace();
    expect(
      await findInspector("a.pdf"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close details" }));
    expect(queryInspector()).toBeNull();
    expect(nav.back).not.toHaveBeenCalled();
    expect(nav.replace).toHaveBeenCalledWith(
      "/projects/p-1/revisions/r-2?other=1",
    );
    view.unmount();

    nav.replace.mockClear();
    nav.search = "document=rd-a.pdf";
    renderWorkspace();
    expect(
      await findInspector("a.pdf"),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(queryInspector()).toBeNull();
    expect(nav.back).not.toHaveBeenCalled();
    expect(nav.replace).toHaveBeenCalledWith("/projects/p-1/revisions/r-2");
  });
});

describe("document inspector", () => {
  const update = vi.mocked(updateDocument);

  it("overlays the register as a modal and closes from the backdrop", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "a.pdf" }), makeRow({ name: "b.pdf" })]);
    renderWorkspace(true);

    await openDrawer(user, "a.pdf");
    expect(nav.push).toHaveBeenLastCalledWith(
      `/projects/${P}/revisions/${R}?document=rd-a.pdf`,
    );
    expect(screen.queryByRole("row", { name: /b.pdf/ })).toBeNull();

    await clickBackdrop(user, "a.pdf");
    await waitFor(() => expect(queryInspector()).toBeNull());
    expect(screen.getByRole("row", { name: /b.pdf/ })).toBeInTheDocument();
  });

  it("closes on Escape and strips the document query", async () => {
    const user = userEvent.setup();
    nav.search = "document=rd-a.pdf";
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace(true);
    await findInspector("a.pdf");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(queryInspector()).toBeNull());
    expect(nav.replace).toHaveBeenCalledWith(`/projects/${P}/revisions/${R}`);
  });

  it("asks before discarding unsaved metadata from the backdrop, Escape, or Close", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace(true);
    const drawer = await openDrawer(user, "a.pdf");
    await user.type(within(drawer).getByLabelText("Description"), "Draft");

    const keepEditing = async () => {
      const dialog = await screen.findByRole("dialog", {
        name: "Discard unsaved changes?",
      });
      await user.click(
        within(dialog).getByRole("button", { name: "Keep editing" }),
      );
      expect(
        within(getInspector("a.pdf")).getByLabelText("Description"),
      ).toHaveValue("Draft");
    };

    await clickBackdrop(user, "a.pdf");
    await keepEditing();
    await user.keyboard("{Escape}");
    await keepEditing();

    await user.click(screen.getByRole("button", { name: "Close details" }));
    await user.click(
      within(
        await screen.findByRole("dialog", { name: "Discard unsaved changes?" }),
      ).getByRole("button", { name: "Discard changes" }),
    );
    await waitFor(() => expect(queryInspector()).toBeNull());
    expect(update).not.toHaveBeenCalled();
  });

  it("guards links and the viewer while metadata is unsaved", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "a.pdf",
        processing: summary({
          status: "COMPLETED",
          pages_processed: 1,
          pages_total: 1,
        }),
      }),
    ]);
    renderWorkspace(true);
    const drawer = await openDrawer(user, "a.pdf");
    await user.type(within(drawer).getByLabelText("Notes"), "Draft");
    nav.push.mockClear();

    await user.click(
      within(drawer).getByRole("button", { name: "View pages / evidence" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Discard unsaved changes?",
    });
    expect(dialog).toHaveTextContent(
      "Your changes will be lost if you leave this page.",
    );
    expect(nav.push).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Discard changes" }));
    expect(nav.push).toHaveBeenCalledWith(
      `/projects/${P}/revisions/${R}/documents/rd-a.pdf`,
    );
  });
});

describe("attention and read-only", () => {
  it("summarises documents that need attention and jumps to Issues", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "ok.pdf" }),
      makeRow({
        name: "review.pdf",
        document_type: "UNKNOWN",
        classification: {
          enabled: true,
          suggestion: suggestion({ predicted_type: "PANEL_SCHEDULE" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
      }),
      makeRow({
        name: "bad.pdf",
        processing: summary({ status: "FAILED", error_message: "Corrupt" }),
      }),
    ]);
    renderWorkspace(true);

    expect(
      await screen.findByText("2 documents need attention."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View issues" }));
    expect(quickView("Issues")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("bad.pdf")).toBeInTheDocument();
    expect(screen.queryByText("ok.pdf")).toBeNull();
  });

  it("hides the attention summary when nothing needs attention", async () => {
    list.mockResolvedValue([makeRow({ name: "ok.pdf" })]);
    renderWorkspace(true);
    expect(await screen.findByText("ok.pdf")).toBeInTheDocument();
    expect(screen.queryByText(/need attention/)).toBeNull();
    expect(screen.queryByText(/needs attention/)).toBeNull();
  });

  it("keeps viewing and downloads on a read-only revision but blocks changes", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    render(
      <RevisionDocuments
        projectId={P}
        revisionId={R}
        canMutate={false}
        revisionLabel="B"
        readOnlyReason="This revision has been superseded."
        activeRevisionId="r-3"
      />,
    );
    expect(await screen.findByText("Read-only.")).toBeInTheDocument();
    expect(
      screen.getByText(/This revision has been superseded\./),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "View active revision" }),
    ).toHaveAttribute("href", `/projects/${P}/revisions/r-3`);
    expect(screen.queryByRole("button", { name: "Add documents" })).toBeNull();

    const drawer = await openDrawer(user, "a.pdf");
    expect(within(drawer).getByRole("button", { name: "Download" })).toBeEnabled();
    expect(within(drawer).getByText("Read-only")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Remove" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Change type" })).toBeNull();
    expect(within(drawer).getByLabelText("Description")).toBeDisabled();
  });
});
