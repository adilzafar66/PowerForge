import { selectOption } from "@/components/ui/control-test-helpers";
/** @vitest-environment jsdom */
import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
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

function makeRow(overrides: Partial<RevisionDocument> & { name?: string; mime?: string }) {
  const { name = "SLD_RevA.pdf", mime = "application/pdf", ...rest } = overrides;
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
  return render(<RevisionDocuments projectId={P} revisionId={R} canMutate={canMutate} />);
}

function quickView(name: string) {
  return within(screen.getByRole("group", { name: "Quick views" })).getByRole("button", {
    name: new RegExp(`^${name}\\b`),
  });
}

async function openAddMenu(user: ReturnType<typeof userEvent.setup>) {
  const [button] = await screen.findAllByRole("button", { name: "Add Documents" });
  await user.click(button);
}

const classificationDetail = vi.mocked(getClassification);

beforeEach(() => {
  nav.search = "";
  list.mockResolvedValue([]);
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
          suggestion: suggestion({ predicted_type: "TRANSFORMER_SHOP_DRAWING" }),
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

    expect(await screen.findByRole("columnheader", { name: "Document" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Type" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "State" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Origin" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Processing" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).toBeNull();

    const uploaded = screen.getByRole("row", { name: /SLD_RevB.pdf/ });
    expect(within(uploaded).getByText("Single Line Diagram")).toBeInTheDocument();
    expect(within(uploaded).getByText("Uploaded · Oct 1, 2026")).toBeInTheDocument();
    expect(within(uploaded).queryByText("Included")).toBeNull();
    expect(within(uploaded).queryByText("Uploaded")).toBeNull();

    const inherited = screen.getByRole("row", { name: /Scan.pdf/ });
    expect(within(inherited).getByText("Unclassified")).toBeInTheDocument();
    expect(within(inherited).getByText("E-101")).toBeInTheDocument();
    expect(within(inherited).getByText("AI: Transformer Shop Drawing · High")).toBeInTheDocument();
    expect(within(inherited).queryByText("Included")).toBeNull();
    expect(screen.getByRole("link", { name: "Rev 1" })).toHaveAttribute(
      "href",
      `/projects/${P}/revisions/r-1`,
    );

    const differs = screen.getByRole("row", { name: /notes.pdf/ });
    expect(within(differs).getByText("Electrical Drawing")).toBeInTheDocument();
    expect(within(differs).getByText("AI suggests: Single Line Diagram")).toBeInTheDocument();
  });

  it("shows the empty state, and a filtered empty state with Clear filters", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.queryByText("Clear filters")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Filters" }));
    await selectOption(screen.getByLabelText("Origin"), "INHERITED");
    expect(await screen.findByText("No documents match your filters.")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.getByLabelText("Origin")).toHaveValue("");
  });

  it("offers Download but not Open for a TIFF row", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "plan.tif", mime: "image/tiff" }),
      makeRow({ name: "plan.pdf" }),
    ]);
    renderWorkspace();
    await screen.findByText("plan.tif");

    await user.click(screen.getByRole("button", { name: "Actions for plan.tif" }));
    expect(screen.getByRole("menuitem", { name: "Download original" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Open original" })).toBeNull();
    await user.keyboard("{Escape}");

    await user.click(screen.getByRole("button", { name: "Actions for plan.pdf" }));
    expect(screen.getByRole("menuitem", { name: "Open original" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Download original" })).toBeInTheDocument();
  });

  it("opens the drawer from the row and leaves it closed for the overflow menu", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "a.pdf" }), makeRow({ name: "b.pdf" })]);
    renderWorkspace();

    const first = await screen.findByRole("row", { name: /a.pdf/ });
    expect(classificationDetail).not.toHaveBeenCalled();
    expect(vi.mocked(listClassificationPages)).not.toHaveBeenCalled();
    await user.click(first);
    expect(nav.push).toHaveBeenCalledWith("/projects/p-1/revisions/r-2?document=rd-a.pdf");
    const drawer = await screen.findByRole("dialog", { name: "a.pdf" });
    expect(within(drawer).getByText("Uploaded in this revision")).toBeInTheDocument();
    expect(classificationDetail).toHaveBeenCalledWith(P, R, "rd-a.pdf");
    expect(first).toHaveAttribute("aria-selected", "true");

    await user.click(screen.getByRole("row", { name: /b.pdf/ }));
    expect(await screen.findByRole("dialog", { name: "b.pdf" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "a.pdf" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Close details" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    const reopened = screen.getByRole("row", { name: /a.pdf/ });
    reopened.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog", { name: "a.pdf" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Actions for a.pdf" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("menuitem", { name: "Download original" })).toBeInTheDocument();
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
    await selectOption(screen.getByLabelText("Document type"), "CABLE_SCHEDULE");
    await selectOption(screen.getByLabelText("Origin"), "INHERITED");
    await selectOption(screen.getByLabelText("Processing state"), "COMPLETED");
    await selectOption(screen.getByLabelText("Classification state"), "ready");

    expect(screen.getByRole("button", { name: "Filters (4)" })).toBeInTheDocument();
    expect(screen.queryByText("local.pdf")).toBeNull();
    expect(screen.getByText("shop.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
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
      expect(list).toHaveBeenLastCalledWith(P, R, { status: "ALL", search: "sld" }),
    );
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("ignores a slow earlier response that finishes after a newer one", async () => {
    let resolveFirst: (rows: RevisionDocument[]) => void = () => {};
    list.mockImplementationOnce(
      () => new Promise<RevisionDocument[]>((resolve) => (resolveFirst = resolve)),
    );
    list.mockResolvedValueOnce([makeRow({ name: "fresh.pdf" })]);
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "fresh" } });
    expect(await screen.findByText("fresh.pdf")).toBeInTheDocument();

    await act(async () => {
      resolveFirst([makeRow({ name: "stale.pdf" })]);
    });
    expect(screen.getByText("fresh.pdf")).toBeInTheDocument();
    expect(screen.queryByText("stale.pdf")).toBeNull();
  });

  it("keeps classification, page, and download actions on the row", async () => {
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
    const drawer = await screen.findByRole("dialog", { name: "ready.pdf" });
    expect(within(drawer).getByRole("button", { name: "Accept suggestion" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "View pages" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Actions for ready.pdf" }));
    expect(screen.getByRole("menuitem", { name: "Download original" })).toBeInTheDocument();
  });
});

describe("RevisionDocuments errors", () => {
  it("refreshes once and tells the user when the list returns 409", async () => {
    list.mockRejectedValueOnce(apiError(409, "Revision state changed."));
    list.mockResolvedValueOnce([makeRow({ name: "after.pdf" })]);
    renderWorkspace();

    expect(await screen.findByText("after.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status")).toHaveTextContent("Revision state changed.");
  });

  it("shows other errors with Retry", async () => {
    const user = userEvent.setup();
    list.mockRejectedValueOnce(apiError(500, "Server exploded"));
    renderWorkspace();

    expect(await screen.findByRole("alert")).toHaveTextContent("Server exploded");
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
    const open = vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    download.mockResolvedValue({
      url,
      expires_at: "2026-10-01T10:05:00Z",
      filename: "a.pdf",
    });
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: "Actions for a.pdf" }));
    await user.click(screen.getByRole("menuitem", { name: "Open original" }));

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

    await user.click(await screen.findByRole("button", { name: "Actions for a.tif" }));
    await user.click(screen.getByRole("menuitem", { name: "Download original" }));

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

    await user.click(await screen.findByRole("button", { name: "Actions for a.pdf" }));
    await user.click(screen.getByRole("menuitem", { name: "Open original" }));

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

    await user.click(await screen.findByRole("button", { name: "Actions for a.pdf" }));
    await user.click(screen.getByRole("menuitem", { name: "Open original" }));

    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Document not found");
    expect(list).toHaveBeenCalledTimes(2);
  });
});

describe("RevisionDocuments upload area", () => {
  const upload = vi.mocked(uploadDocument);

  function choose(file: File) {
    fireEvent.change(screen.getByLabelText("Choose files"), { target: { files: [file] } });
  }
  const pdf = () => new File([new Uint8Array(10)], "new.pdf", { type: "application/pdf" });

  it("is absent when the revision cannot be changed and opens from Add Documents when it can", async () => {
    const user = userEvent.setup();
    const first = renderWorkspace(false);
    await waitFor(() => expect(list).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Add Documents" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Upload Documents" })).toBeNull();
    first.unmount();

    renderWorkspace(true);
    expect(screen.queryByRole("button", { name: "Upload Documents" })).toBeNull();
    await openAddMenu(user);
    expect(screen.getByRole("menuitem", { name: "Upload files" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Add from another revision" })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    expect(await screen.findByRole("button", { name: "Upload Documents" })).toBeInTheDocument();
  });

  it("reloads the list when an upload completes", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue({ duplicate_detected: false, duplicate_document_ids: [] } as never);
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    list.mockResolvedValue([makeRow({ name: "new.pdf" })]);

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    choose(pdf());

    expect(await screen.findByRole("cell", { name: /new\.pdf/ })).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("shows a notice, refreshes the page and reloads the list on a read-only 409", async () => {
    const user = userEvent.setup();
    upload.mockRejectedValue(
      Object.assign(new Error("Revision is superseded."), {
        apiError: { detail: "Revision is superseded.", code: "revision_read_only" },
        status: 409,
      }),
    );
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    choose(pdf());

    expect(await screen.findByRole("status")).toHaveTextContent("Revision is superseded.");
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
    expect(quickView("Needs Review")).toHaveTextContent("1");
    expect(quickView("Issues")).toHaveTextContent("1");
    expect(quickView("Removed")).toHaveTextContent("1");
    expect(screen.getByRole("heading", { name: "Documents 3" })).toBeInTheDocument();
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

    await user.click(quickView("Needs Review"));
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

    await user.click(quickView("Needs Review"));
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

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "missing" } });
    expect(await screen.findByText("No documents match your search")).toBeInTheDocument();
  });

  it("treats a revision that only has removed documents as empty in All", async () => {
    list.mockResolvedValue([makeRow({ name: "gone.pdf", status: "REMOVED" })]);
    renderWorkspace();

    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
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
  overrides: Partial<ClassificationAttempt> & { status: ClassificationAttempt["status"] },
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

async function openMenu(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(await screen.findByRole("button", { name: `Actions for ${name}` }));
}

async function openDrawer(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(await screen.findByRole("row", { name: new RegExp(name) }));
  return screen.findByRole("dialog", { name });
}

describe("RevisionDocuments row actions", () => {
  const remove = vi.mocked(removeDocument);
  const restore = vi.mocked(restoreDocument);
  const update = vi.mocked(updateDocument);

  it("shows download on a read-only row and hides mutations", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "a.pdf",
        processing: summary({ status: "COMPLETED", pages_processed: 1, pages_total: 1 }),
        classification: {
          enabled: true,
          suggestion: suggestion(),
          attempt: attempt({ status: "FAILED", error_code: "PROVIDER_TIMEOUT" }),
        },
      }),
    ]);
    renderWorkspace(false);

    await openMenu(user, "a.pdf");
    expect(screen.getByRole("menuitem", { name: "Download original" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Open original" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "View pages" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Retry classification" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Reclassify" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Edit metadata" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Remove from revision" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Restore to revision" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Retry processing" })).toBeNull();

    const drawer = await openDrawer(user, "a.pdf");
    expect(within(drawer).queryByRole("button", { name: "Accept suggestion" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Change type" })).toBeNull();
    expect(within(drawer).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Reclassify" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Retry processing" })).toBeNull();
    expect(within(drawer).getByRole("button", { name: "View pages" })).toBeInTheDocument();
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

    await openMenu(user, "a.pdf");
    expect(screen.getByRole("menuitem", { name: "Edit metadata" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Remove from revision" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Restore to revision" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "View pages" })).toBeNull();
    await user.keyboard("{Escape}");

    await openMenu(user, "bad.pdf");
    expect(screen.getByRole("menuitem", { name: "Retry processing" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Retry classification" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "View pages" })).toBeNull();
    await user.keyboard("{Escape}");

    await user.click(quickView("Removed"));
    await openMenu(user, "b.pdf");
    expect(screen.getByRole("menuitem", { name: "Restore to revision" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Download original" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Remove from revision" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Edit metadata" })).toBeNull();
  });

  it("removes only after confirmation and reloads the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    remove.mockResolvedValue({} as never);
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Remove from revision" }));
    expect(remove).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveTextContent("Remove document from this revision?");

    list.mockResolvedValueOnce([]);
    await user.click(screen.getByRole("button", { name: "Remove" }));

    expect(remove).toHaveBeenCalledWith(P, R, "rd-a.pdf");
    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Removed a.pdf from this revision.");
  });

  it("does nothing when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Remove from revision" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(remove).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("restores a removed row without confirmation", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "b.pdf", status: "REMOVED" })]);
    restore.mockResolvedValue({} as never);
    renderWorkspace(true);
    await user.click(quickView("Removed"));

    await openMenu(user, "b.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Restore to revision" }));

    expect(restore).toHaveBeenCalledWith(P, R, "rd-b.pdf");
    expect(await screen.findByText("Restored b.pdf.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("explains a 409 on remove and refreshes the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    remove.mockRejectedValue(
      Object.assign(new Error("Document state changed."), {
        status: 409,
        apiError: { code: "document_removed", detail: "Document state changed." },
      }),
    );
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Remove from revision" }));
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf", status: "REMOVED" })]);
    await user.click(screen.getByRole("button", { name: "Remove" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Document state changed.");
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("saves edited metadata from the drawer and reloads the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    update.mockResolvedValue(makeRow({ name: "a.pdf", document_number: "E-7" }));
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Edit metadata" }));
    const drawer = await screen.findByRole("dialog", { name: "a.pdf" });
    await user.type(within(drawer).getByLabelText("Document number"), "E-7");
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf", document_number: "E-7" })]);
    await user.click(within(drawer).getByRole("button", { name: "Save changes" }));

    expect(update).toHaveBeenCalledWith(P, R, "rd-a.pdf", { document_number: "E-7" });
    expect(await within(drawer).findByDisplayValue("E-7")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Saved changes to a.pdf.");
    expect(screen.getByRole("dialog", { name: "a.pdf" })).toBeInTheDocument();
  });

  it("opens the reuse dialog from Add from another revision", async () => {
    const user = userEvent.setup();
    vi.mocked(listRevisions).mockResolvedValue([]);
    renderWorkspace(true);

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Add from another revision" }));
    expect(await screen.findByText("This project has no other revisions.")).toBeInTheDocument();
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
        processing: summary({ status: "RUNNING", pages_processed: 1, pages_total: 4 }),
      }),
      makeRow({
        name: "done.pdf",
        processing: summary({ status: "COMPLETED", pages_processed: 4, pages_total: 4 }),
      }),
      makeRow({
        name: "bad.pdf",
        processing: summary({ status: "FAILED", error_message: "Could not read the file" }),
      }),
    ]);
    renderWorkspace(true);

    expect(await screen.findByText("Not started")).toBeInTheDocument();
    const running = screen.getByRole("row", { name: /run.pdf/ });
    expect(within(running).getByText("Processing")).toBeInTheDocument();
    expect(within(running).getByText("1 / 4")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /done.pdf/ })).getByText("Ready")).toBeInTheDocument();
    const failed = screen.getByRole("row", { name: /bad.pdf/ });
    expect(
      within(failed).getByRole("group", { name: "Failed, Processing failed" }),
    ).toBeInTheDocument();
    expect(within(failed).queryByText("Could not read the file")).toBeNull();
    expect(pages).not.toHaveBeenCalled();
    expect(retry).not.toHaveBeenCalled();
    expect(artifactUrl).not.toHaveBeenCalled();

    const drawer = await openDrawer(user, "bad.pdf");
    expect(within(drawer).getByText("Processing failed")).toBeInTheDocument();
    expect(within(drawer).getByText("Could not read the file")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Retry processing" }));
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
    await openMenu(user, "bad.pdf");
    expect(screen.getByRole("menuitem", { name: "Retry processing" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Edit metadata" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Remove from revision" })).toBeNull();
    await user.keyboard("{Escape}");

    const drawer = await openDrawer(user, "bad.pdf");
    expect(within(drawer).getByRole("button", { name: "Retry processing" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Change type" })).toBeNull();
  });

  it("opens the viewer from the drawer and leaves that document selected", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "done.pdf",
        processing: summary({ status: "COMPLETED", pages_processed: 2, pages_total: 2 }),
      }),
    ]);
    pages.mockResolvedValue([
      {
        id: "page-1",
        page_number: 1,
        source_width: "612",
        source_height: "792",
        source_unit: "POINTS",
        rotation_degrees: 0,
        native_text_char_count: 12,
        artifacts: [
          {
            artifact_type: "ANALYSIS_IMAGE",
            mime_type: "image/png",
            width_px: 1000,
            height_px: 1400,
          },
          {
            artifact_type: "THUMBNAIL",
            mime_type: "image/webp",
            width_px: 400,
            height_px: 560,
          },
        ],
      },
    ]);
    artifactUrl.mockImplementation(async (_project, _revision, _document, pageId, type) => ({
      url: `https://files.example/${type}/${pageId}`,
      expires_at: "2026-10-10T00:00:00Z",
      filename: type === "ANALYSIS_IMAGE" ? "analysis.png" : "thumbnail.webp",
    }));
    renderWorkspace(false);

    const drawer = await openDrawer(user, "done.pdf");
    await user.click(within(drawer).getByRole("button", { name: "View pages" }));

    expect(await screen.findByText("612 × 792 pt")).toBeInTheDocument();
    expect(screen.getByText("1000 × 1400 px")).toBeInTheDocument();
    await waitFor(() =>
      expect(artifactUrl).toHaveBeenCalledWith(P, R, "rd-done.pdf", "page-1", "ANALYSIS_IMAGE"),
    );
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText("612 × 792 pt")).toBeNull();
    expect(screen.getByRole("dialog", { name: "done.pdf" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /done.pdf/ })).toHaveAttribute("aria-selected", "true");
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
    expect(await within(drawer).findByText("Ratings and an outline.")).toBeInTheDocument();
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
    await user.click(within(drawer).getByRole("button", { name: "Accept suggestion" }));

    expect(accept).toHaveBeenCalledWith(P, R, "rd-shop.pdf", "pred-1");
    expect(await within(drawer).findByText("Accepted AI classification")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Accept suggestion" })).toBeNull();
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
    renderWorkspace(true);
    const drawer = await openDrawer(user, "differ.pdf");
    expect(within(drawer).getByText("AI suggestion")).toBeInTheDocument();
    expect(within(drawer).getAllByText("Single Line Diagram").length).toBeGreaterThan(0);

    await user.click(within(drawer).getByRole("button", { name: "Keep current" }));
    expect(accept).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();

    await user.click(within(drawer).getByRole("button", { name: "Use AI suggestion" }));
    expect(accept).toHaveBeenCalledWith(P, R, "rd-differ.pdf", "pred-1");
  });

  it("changes type through updateDocument", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    update.mockResolvedValue(makeRow({ name: "a.pdf", document_type: "PANEL_SCHEDULE" }));
    renderWorkspace(true);
    const drawer = await openDrawer(user, "a.pdf");
    await user.click(within(drawer).getByRole("button", { name: "Change type" }));
    await selectOption(within(drawer).getByLabelText("Document type"), "PANEL_SCHEDULE");
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf", document_type: "PANEL_SCHEDULE" })]);
    await user.click(within(drawer).getByRole("button", { name: "Save type" }));

    expect(update).toHaveBeenCalledWith(P, R, "rd-a.pdf", { document_type: "PANEL_SCHEDULE" });
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("keeps a suggestion visible when the latest attempt failed", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "again.pdf",
        document_type: "TRANSFORMER_SHOP_DRAWING",
        processing: summary({ status: "COMPLETED", pages_processed: 2, pages_total: 2 }),
        classification: {
          enabled: true,
          suggestion: suggestion(),
          attempt: attempt({ status: "FAILED", error_code: "PROVIDER_TIMEOUT" }),
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
    expect(within(drawer).getAllByText("Transformer Shop Drawing").length).toBeGreaterThan(0);
    expect(within(drawer).getByText("The classification provider timed out.")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledWith(P, R, "rd-again.pdf", "run-1");

    await user.click(within(drawer).getByRole("button", { name: "More" }));
    expect(screen.getByRole("menuitem", { name: "Reclassify" })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Reclassify" }));
    expect(reclassify).toHaveBeenCalledWith(P, R, "rd-again.pdf");
  });

  it("shows only the failure when there is no suggestion", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "empty.pdf",
        processing: summary({ status: "COMPLETED", pages_processed: 1, pages_total: 1 }),
        classification: {
          enabled: true,
          suggestion: null,
          attempt: attempt({ status: "FAILED", error_code: null }),
        },
      }),
    ]);
    renderWorkspace(true);
    const drawer = await openDrawer(user, "empty.pdf");
    expect(within(drawer).getAllByText("Classification failed").length).toBeGreaterThan(0);
    expect(within(drawer).getByText("No suggestion")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Accept suggestion" })).toBeNull();
    expect(within(drawer).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("loads mixed page predictions in the drawer and opens that page", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({
        name: "mixed.pdf",
        document_type: "MIXED_DOCUMENT",
        processing: summary({ status: "COMPLETED", pages_processed: 2, pages_total: 2 }),
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
      { page_number: 2, predicted_type: "PANEL_SCHEDULE", confidence_band: "HIGH" },
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
    await user.click(within(drawer).getByRole("button", { name: "View page classifications" }));
    expect(classificationPages).toHaveBeenCalledWith(P, R, "rd-mixed.pdf");
    expect(await within(drawer).findByRole("button", { name: /2 Panel Schedule/ })).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: /2 Panel Schedule/ }));
    expect(vi.mocked(listPages)).toHaveBeenCalledWith(P, R, "rd-mixed.pdf");
    expect(await screen.findByText("612 × 792 pt")).toBeInTheDocument();
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
      { page_number: 2, predicted_type: "PANEL_SCHEDULE", confidence_band: "HIGH" },
    ]);
    renderWorkspace(true);

    const drawer = await openDrawer(user, "mixed.pdf");
    await user.click(within(drawer).getByRole("button", { name: "View page classifications" }));
    expect(await within(drawer).findByRole("button", { name: /2 Panel Schedule/ })).toBeInTheDocument();

    await user.click(screen.getByRole("row", { name: /other.pdf/ }));
    const next = await screen.findByRole("dialog", { name: "other.pdf" });
    expect(within(next).queryByRole("button", { name: /2 Panel Schedule/ })).toBeNull();
    expect(within(next).getByRole("button", { name: "View page classifications" })).toBeInTheDocument();
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
    expect(within(drawer).getByText("Transformer Shop Drawing")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Accept suggestion" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Choose another type" })).toBeNull();
  });

  it("reopens the drawer from the document query", async () => {
    nav.search = "document=rd-a.pdf";
    list.mockResolvedValue([makeRow({ name: "a.pdf", document_number: "E-1" })]);
    renderWorkspace();
    const drawer = await screen.findByRole("dialog", { name: "a.pdf" });
    expect(drawer).toHaveTextContent("E-1");
    expect(classificationDetail).toHaveBeenCalledWith(P, R, "rd-a.pdf");
  });

  it("strips a deep-linked document query without leaving the revision", async () => {
    const user = userEvent.setup();
    nav.search = "other=1&document=rd-a.pdf";
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    const view = renderWorkspace();
    expect(await screen.findByRole("dialog", { name: "a.pdf" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close details" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(nav.back).not.toHaveBeenCalled();
    expect(nav.replace).toHaveBeenCalledWith("/projects/p-1/revisions/r-2?other=1");
    view.unmount();

    nav.replace.mockClear();
    nav.search = "document=rd-a.pdf";
    renderWorkspace();
    expect(await screen.findByRole("dialog", { name: "a.pdf" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(nav.back).not.toHaveBeenCalled();
    expect(nav.replace).toHaveBeenCalledWith("/projects/p-1/revisions/r-2");
  });
});

